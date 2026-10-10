"""Phase 2 Part 2.2: requirements spec & reconciliation.

Computes which Sentinel-2 tiles the buffered study boundary actually
intersects (via the real MGRS grid, not guessed), builds
configs/data_requirements.yaml, diffs it against Part 2.1's inventory, and
writes results/phase2/missing_report.md. Read-only — this part only
decides what's missing, Part 2.5 fetches it (with explicit approval).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import geopandas as gpd
import mgrs
import numpy as np
from shapely.geometry import Point

from src.utils.io import load_config, resolve_path

# Grid step for sampling the buffered boundary when computing which MGRS
# 100km tiles it intersects — fine enough not to miss a tile that only
# grazes the boundary's edge, coarse enough to stay fast.
_TILE_SAMPLE_STEP_DEG = 0.02  # ~2 km at this latitude

_REQUIRED_SMALL_DATASETS = ("worldpop", "dem", "worldcover", "osm")


def compute_required_tiles(buffered_gdf: gpd.GeoDataFrame, *, step_deg: float = _TILE_SAMPLE_STEP_DEG) -> list[str]:
    """Returns the sorted list of Sentinel-2 tile IDs (e.g. "T44QQE") whose
    MGRS 100km square the buffered boundary actually falls within —
    computed via the real MGRS grid (the `mgrs` library), not assumed from
    whatever happens to already be in B2.
    """
    wgs84 = buffered_gdf.to_crs("EPSG:4326")
    geom = wgs84.geometry.union_all()
    minx, miny, maxx, maxy = geom.bounds

    converter = mgrs.MGRS()
    tiles: set[str] = set()
    for x in np.arange(minx, maxx, step_deg):
        for y in np.arange(miny, maxy, step_deg):
            if geom.contains(Point(x, y)):
                tiles.add("T" + converter.toMGRS(y, x, MGRSPrecision=0))

    if not tiles:
        raise ValueError("No MGRS tiles found intersecting the buffered boundary — check the geometry/grid step")
    return sorted(tiles)


def build_data_requirements(
    required_tiles: list[str], temporal_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    temporal_config = temporal_config if temporal_config is not None else load_config("temporal")
    return {
        "sentinel2": {
            "required_tiles": required_tiles,
            "epochs": temporal_config["epochs"],
            "dry_season_window": temporal_config["dry_season_window"],
        },
        "small_datasets": {
            "worldpop": {"required": True, "years": list(temporal_config["epochs"])},
            "dem": {"required": True},
            "worldcover": {"required": True, "note": "needed for Phase 5's built-up cross-check on overlapping years"},
            "osm": {"required": True, "note": "roads/amenities for Phase 4 — may be fetched live via osmnx rather than pre-cached"},
        },
    }


def _load_inventory(manifest_path: Path | None = None) -> list[dict[str, Any]]:
    path = manifest_path if manifest_path is not None else resolve_path("data.manifests") / "b2_inventory.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"Inventory manifest not found at {path} — run Phase 2 Part 2.1 first")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def reconcile_sentinel2(
    requirements: dict[str, Any], inventory: list[dict[str, Any]]
) -> dict[str, Any]:
    required_tiles = set(requirements["sentinel2"]["required_tiles"])
    required_epochs = requirements["sentinel2"]["epochs"]

    raw_scenes = [e for e in inventory if e.get("source") == "sentinel2" and e.get("format") == "zip"]

    counts: dict[tuple[str, int], int] = defaultdict(int)
    tiles_present: set[str] = set()
    for e in raw_scenes:
        if not e.get("tile") or not e.get("sensing_date"):
            continue
        tiles_present.add(e["tile"])
        year = int(e["sensing_date"][:4])
        counts[(e["tile"], year)] += 1

    coverage = []
    missing = []
    for tile in sorted(required_tiles):
        for epoch in required_epochs:
            count = counts.get((tile, epoch), 0)
            coverage.append({"tile": tile, "epoch": epoch, "scene_count": count})
            if count == 0:
                missing.append({"tile": tile, "epoch": epoch})

    extra_tiles = sorted(tiles_present - required_tiles)

    return {"coverage": coverage, "missing": missing, "extra_tiles_present": extra_tiles}


def reconcile_small_datasets(
    requirements: dict[str, Any], inventory: list[dict[str, Any]]
) -> dict[str, Any]:
    other_keys = [e["key"] for e in inventory if e.get("source") == "other"]
    results: dict[str, Any] = {}

    worldpop_years_needed = set(requirements["small_datasets"]["worldpop"]["years"])
    worldpop_years_present = {
        int(key.rsplit("/", 2)[-2])
        for key in other_keys
        if "worldpop/clipped/" in key and key.rsplit("/", 2)[-2].isdigit()
    }
    missing_worldpop_years = sorted(worldpop_years_needed - worldpop_years_present)
    results["worldpop"] = {
        "years_present": sorted(worldpop_years_present),
        "years_missing": missing_worldpop_years,
        "status": "OK" if not missing_worldpop_years else "MISSING_YEARS",
    }

    for name in ("dem", "worldcover", "osm"):
        present = any(f"/{name}/" in key.lower() or f"raw_small/{name}" in key.lower() for key in other_keys)
        results[name] = {"status": "OK" if present else "MISSING"}

    return results


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".part")
    tmp_path.write_text(content)
    import os

    os.replace(tmp_path, path)


def write_data_requirements(data: dict[str, Any]) -> Path:
    import yaml

    path = resolve_path("configs.data_requirements")
    header = (
        "# Auto-generated by Phase 2 Part 2.2 (src/acquisition/reconcile.py) from configs/temporal.yaml\n"
        "# and the real boundary geometry — required_tiles are computed via the actual MGRS grid, not\n"
        "# assumed from whatever happens to already be in B2.\n\n"
    )
    _atomic_write_text(path, header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return path


def generate_missing_report(
    s2_recon: dict[str, Any], small_recon: dict[str, Any], *, avg_scene_bytes: float | None = None
) -> str:
    lines = ["# Missing Data Report (Phase 2, Part 2.2)", ""]

    lines += ["## Sentinel-2 tile/epoch coverage", ""]
    for row in s2_recon["coverage"]:
        status = "OK" if row["scene_count"] > 0 else "MISSING"
        lines.append(f"- `{row['tile']}` / {row['epoch']}: {row['scene_count']} scene(s) — {status}")

    lines += ["", "## Sentinel-2 — missing (tile, epoch) pairs", ""]
    if s2_recon["missing"]:
        est = f" (~{avg_scene_bytes / (1024**2):.0f} MB/scene estimate)" if avg_scene_bytes else ""
        for item in s2_recon["missing"]:
            lines.append(f"- `{item['tile']}` / {item['epoch']}{est} — needs fetching from Copernicus (Part 2.5)")
    else:
        lines.append("_(none — every required tile/epoch combination has at least one raw scene already in B2)_")

    lines += ["", "## Tiles present in B2 but not strictly required", ""]
    if s2_recon["extra_tiles_present"]:
        lines.append(
            f"- {', '.join(s2_recon['extra_tiles_present'])} — present and usable, but outside the "
            "current buffered boundary's strict MGRS intersection. Not wasted; would become required "
            "if the buffer distance in configs/boundary.yaml is increased."
        )
    else:
        lines.append("_(none)_")

    lines += ["", "## Small datasets (WorldPop, DEM, WorldCover, OSM)", ""]
    wp = small_recon["worldpop"]
    lines.append(
        f"- `worldpop`: years present {wp['years_present']}, missing {wp['years_missing'] or 'none'} — {wp['status']}"
    )
    for name in ("dem", "worldcover", "osm"):
        lines.append(f"- `{name}`: {small_recon[name]['status']}")

    lines += [
        "",
        "## Cost estimate",
        "",
        "B2 egress/transaction pricing for this account is still unconfirmed (plan.md Assumption A5) — "
        "any fetch of the missing items above should get an explicit byte/request estimate and user "
        "approval before running, per plan.md Section 0's data-safety rules. Nothing is fetched by this "
        "report.",
        "",
    ]

    return "\n".join(lines)


def write_missing_report(content: str) -> Path:
    path = resolve_path("results") / "phase2" / "missing_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def run_reconciliation(buffered_gdf: gpd.GeoDataFrame) -> dict[str, Any]:
    """Orchestrates compute_required_tiles -> build_data_requirements ->
    reconcile -> write both outputs. Read-only w.r.t. B2 and local raw data.
    """
    required_tiles = compute_required_tiles(buffered_gdf)
    requirements = build_data_requirements(required_tiles)
    requirements_path = write_data_requirements(requirements)

    inventory = _load_inventory()
    s2_recon = reconcile_sentinel2(requirements, inventory)
    small_recon = reconcile_small_datasets(requirements, inventory)

    raw_scenes = [e for e in inventory if e.get("source") == "sentinel2" and e.get("format") == "zip"]
    avg_scene_bytes = (sum(e["size_bytes"] for e in raw_scenes) / len(raw_scenes)) if raw_scenes else None

    report = generate_missing_report(s2_recon, small_recon, avg_scene_bytes=avg_scene_bytes)
    report_path = write_missing_report(report)

    return {
        "required_tiles": required_tiles,
        "requirements_path": requirements_path,
        "report_path": report_path,
        "sentinel2_reconciliation": s2_recon,
        "small_dataset_reconciliation": small_recon,
    }
