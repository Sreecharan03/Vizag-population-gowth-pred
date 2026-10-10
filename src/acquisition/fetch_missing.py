"""Phase 2 Part 2.4: fetch missing small datasets (DEM, WorldCover, OSM).

WorldPop is skipped — already present (Part 2.2 confirmed all 4 years).
Default is dry_run=True (estimate only, no transfer); a real run needs
dry_run=False explicitly, per plan.md Section 0's data-safety rules. Every
heavy operation goes through the storage guard first. Upload to B2 is
copy-only — nothing local is ever deleted by this module, and a file that
fails verification is never uploaded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd

from src.acquisition.sources import dem, osm, worldcover
from src.storage.guard import check_budget
from src.utils.io import resolve_path

# Mirrors the B2 prefix convention Part 2.1's inventory found already in
# use for WorldPop ("vizag-geoai/data/raw/worldpop/...") — NOT the local
# "raw_small" directory name, which is a local-only Tier distinction.
DEFAULT_B2_RAW_PREFIX = "vizag-geoai/data/raw/"


def estimate_fetch(buffered_gdf: gpd.GeoDataFrame) -> dict[str, Any]:
    """Dry-run: computes required tiles and their sizes via head_object
    only — no content download, no OSM query (Overpass has no cheap
    size-only estimate; its transfer is small by construction — scoped to
    the AOI, not a regional extract).
    """
    dem_tiles = dem.required_dem_tiles(buffered_gdf)
    dem_sizes = dem.estimate_dem_sizes(dem_tiles)

    wc_tiles = worldcover.required_worldcover_tiles(buffered_gdf)
    wc_sizes = worldcover.estimate_worldcover_sizes(wc_tiles)

    dem_total = sum(dem_sizes.values())
    wc_total = sum(wc_sizes.values())

    return {
        "dem_tiles": dem_tiles,
        "dem_sizes": dem_sizes,
        "dem_total_bytes": dem_total,
        "worldcover_tiles": wc_tiles,
        "worldcover_sizes": wc_sizes,
        "worldcover_total_bytes": wc_total,
        "estimated_total_bytes": dem_total + wc_total,
    }


def _fetch_verify_upload(
    paths: list[Path], verify_fn, backend, b2_prefix: str
) -> dict[str, Any]:
    verifications = []
    uploaded = []
    skipped = []
    for p in paths:
        v = verify_fn(p)
        v["key"] = p.name
        verifications.append(v)
        if v["status"] == "OK":
            key = f"{b2_prefix}{p.name}"
            backend.upload(p, key)
            uploaded.append(key)
        else:
            skipped.append({"file": str(p), "reason": v.get("reason")})
    return {
        "local_paths": paths,
        "verifications": verifications,
        "uploaded_keys": uploaded,
        "skipped": skipped,
        "all_ok": len(skipped) == 0,
    }


def run_fetch_missing(
    buffered_gdf: gpd.GeoDataFrame,
    backend,
    *,
    dry_run: bool = True,
    b2_raw_prefix: str = DEFAULT_B2_RAW_PREFIX,
) -> dict[str, Any]:
    estimate = estimate_fetch(buffered_gdf)

    if dry_run:
        return {"dry_run": True, **estimate}

    check_budget(estimate["estimated_total_bytes"])

    results: dict[str, Any] = {"dry_run": False, "datasets": {}}

    dem_dir = resolve_path("data.raw_small") / "dem"
    dem_paths = dem.fetch_dem_tiles(estimate["dem_tiles"], dem_dir)
    results["datasets"]["dem"] = _fetch_verify_upload(
        dem_paths, dem.verify_dem_file, backend, f"{b2_raw_prefix}dem/"
    )

    wc_dir = resolve_path("data.raw_small") / "worldcover"
    wc_paths = worldcover.fetch_worldcover_tiles(estimate["worldcover_tiles"], wc_dir)
    results["datasets"]["worldcover"] = _fetch_verify_upload(
        wc_paths, worldcover.verify_worldcover_file, backend, f"{b2_raw_prefix}worldcover/"
    )

    osm_dir = resolve_path("data.raw_small") / "osm"
    osm_path_dict = osm.fetch_osm_data(buffered_gdf, osm_dir)
    results["datasets"]["osm"] = _fetch_verify_upload(
        list(osm_path_dict.values()), osm.verify_osm_file, backend, f"{b2_raw_prefix}osm/"
    )

    report = _generate_fetch_report(results)
    results["report_path"] = write_fetch_report(report)

    return results


def _generate_fetch_report(results: dict[str, Any]) -> str:
    lines = ["# Fetch Report — Small Datasets (Phase 2, Part 2.4)", ""]
    lines.append("WorldPop skipped — already present and verified complete (Part 2.2).")
    lines.append("")
    for name, info in results["datasets"].items():
        lines.append(f"## {name}")
        lines.append("")
        for v in info["verifications"]:
            status_line = f"- `{v['key']}`: {v['status']}"
            if v["status"] == "OK":
                status_line += f" ({v.get('size_bytes', v.get('feature_count'))})"
            else:
                status_line += f" — {v.get('reason')}"
            lines.append(status_line)
        lines.append(f"- Uploaded to B2 (copy-only): {len(info['uploaded_keys'])} file(s)")
        if info["skipped"]:
            lines.append(f"- **Skipped upload (failed verification):** {info['skipped']}")
        lines.append("")
    return "\n".join(lines)


def write_fetch_report(content: str) -> Path:
    path = resolve_path("results") / "phase2" / "fetch_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path
