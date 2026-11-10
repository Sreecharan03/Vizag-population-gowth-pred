"""Phase 3 Part 3.1: scene catalogue and epoch feasibility.

This module is deliberately pixel-free. It transforms the Phase 2 B2 inventory
into a raw-scene catalogue and reports whether each configured epoch has L2A
coverage for every required MGRS tile.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable

from src.acquisition.product_id import parse_object_key


@dataclass(frozen=True)
class SceneRecord:
    object_key: str
    size_bytes: int
    product_id: str
    mission: str
    level: str
    sensing_date: str
    epoch: int
    processing_baseline: str
    relative_orbit: str
    tile: str
    processing_date: str
    format: str
    complete: bool
    covers_required_tile: bool
    duplicate: bool = False
    preferred: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_inventory_jsonl(content: str | bytes) -> list[dict[str, Any]]:
    """Parse inventory JSONL content, rejecting malformed/non-object rows."""
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Inventory line {line_number} is not a JSON object")
        records.append(value)
    return records


def build_scene_catalogue(
    inventory: Iterable[dict[str, Any]],
    *,
    required_tiles: Iterable[str],
) -> list[SceneRecord]:
    """Build one record per raw Sentinel-2 archive and mark duplicates.

    A duplicate group is the same mission/acquisition/orbit/tile processed more
    than once. The complete product with the highest baseline and latest
    processing date is preferred; no object is removed or modified.
    """
    required = set(required_tiles)
    provisional: list[SceneRecord] = []

    for item in inventory:
        if item.get("source") != "sentinel2" or item.get("format") != "zip":
            continue
        parsed = parse_object_key(str(item.get("key", "")))
        required_fields = (
            parsed.product_id,
            parsed.mission,
            parsed.level,
            parsed.sensing_date,
            parsed.processing_baseline,
            parsed.relative_orbit,
            parsed.tile,
            parsed.processing_date,
        )
        if not all(required_fields):
            continue
        statuses = set(item.get("statuses") or [])
        complete = not ({"INCOMPLETE", "SUSPECT_SIZE"} & statuses)
        provisional.append(
            SceneRecord(
                object_key=parsed.key,
                size_bytes=int(item.get("size_bytes", 0)),
                product_id=parsed.product_id,
                mission=parsed.mission,
                level=parsed.level.removeprefix("MSI"),
                sensing_date=parsed.sensing_date,
                epoch=int(parsed.sensing_date[:4]),
                processing_baseline=parsed.processing_baseline,
                relative_orbit=parsed.relative_orbit,
                tile=parsed.tile,
                processing_date=parsed.processing_date,
                format=parsed.format,
                complete=complete,
                covers_required_tile=parsed.tile in required,
            )
        )

    groups: dict[tuple[str, str, str, str], list[SceneRecord]] = defaultdict(list)
    for scene in provisional:
        groups[(scene.mission, scene.sensing_date, scene.relative_orbit, scene.tile)].append(scene)

    result: list[SceneRecord] = []
    for group in groups.values():
        preferred = max(
            group,
            key=lambda scene: (
                scene.complete,
                scene.processing_baseline,
                scene.processing_date,
                scene.product_id,
            ),
        )
        is_duplicate = len(group) > 1
        for scene in group:
            values = scene.to_dict()
            values["duplicate"] = is_duplicate
            values["preferred"] = scene.product_id == preferred.product_id
            result.append(SceneRecord(**values))

    return sorted(result, key=lambda scene: (scene.epoch, scene.sensing_date, scene.tile, scene.product_id))


def assess_epoch_feasibility(
    scenes: Iterable[SceneRecord],
    *,
    epochs: Iterable[int],
    required_tiles: Iterable[str],
) -> list[dict[str, Any]]:
    """Summarize candidate coverage and halt-worthy feasibility problems."""
    scene_list = list(scenes)
    required = set(required_tiles)
    summaries: list[dict[str, Any]] = []

    for epoch in epochs:
        epoch_scenes = [scene for scene in scene_list if scene.epoch == int(epoch)]
        candidates = [
            scene
            for scene in epoch_scenes
            if scene.covers_required_tile and scene.complete and scene.preferred
        ]
        l2a = [scene for scene in candidates if scene.level == "L2A"]
        l1c = [scene for scene in candidates if scene.level == "L1C"]
        covered_tiles = {scene.tile for scene in l2a}
        missing_tiles = sorted(required - covered_tiles)

        issues: list[str] = []
        if not l2a:
            issues.append("no_complete_l2a_candidates")
        if l1c and not l2a:
            issues.append("l1c_only_epoch")
        if missing_tiles:
            issues.append("missing_required_tile_coverage")

        dates = sorted(datetime.strptime(scene.sensing_date, "%Y%m%dT%H%M%S") for scene in candidates)
        summaries.append(
            {
                "epoch": int(epoch),
                "all_raw_scenes": len(epoch_scenes),
                "candidate_scenes": len(candidates),
                "l2a_scenes": len(l2a),
                "l1c_scenes": len(l1c),
                "tiles": sorted({scene.tile for scene in candidates}),
                "required_tiles": sorted(required),
                "missing_required_tiles": missing_tiles,
                "date_start": dates[0].date().isoformat() if dates else None,
                "date_end": dates[-1].date().isoformat() if dates else None,
                "processing_baselines": sorted({scene.processing_baseline for scene in candidates}),
                "duplicate_records": sum(scene.duplicate for scene in epoch_scenes),
                "issues": issues,
                "feasible": not issues,
            }
        )
    return summaries


def catalogue_jsonl(scenes: Iterable[SceneRecord]) -> str:
    return "".join(json.dumps(scene.to_dict(), sort_keys=True) + "\n" for scene in scenes)


def generate_feasibility_report(summaries: Iterable[dict[str, Any]]) -> str:
    rows = list(summaries)
    lines = [
        "# Epoch Feasibility — Phase 3, Part 3.1",
        "",
        "Pixel data was not read. Boundary coverage is assessed against the required MGRS tiles",
        "computed in Phase 2; cloud usability is assessed separately in Part 3.2.",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"## {row['epoch']} — {'FEASIBLE' if row['feasible'] else 'HALT / USER DECISION REQUIRED'}",
                "",
                f"- Raw archive records: {row['all_raw_scenes']}",
                f"- Complete preferred candidates on required tiles: {row['candidate_scenes']}",
                f"- L2A / L1C: {row['l2a_scenes']} / {row['l1c_scenes']}",
                f"- Tiles: {', '.join(row['tiles']) or '(none)'}",
                f"- Date spread: {row['date_start'] or '(none)'} to {row['date_end'] or '(none)'}",
                f"- Processing baselines: {', '.join(row['processing_baselines']) or '(none)'}",
                f"- Duplicate records: {row['duplicate_records']}",
                f"- Issues: {', '.join(row['issues']) or 'none'}",
                "",
            ]
        )
    overall = all(row["feasible"] for row in rows)
    lines.extend(
        [
            "## Decision",
            "",
            "All configured epochs pass catalogue-level L2A/tile feasibility. User confirmation is still required."
            if overall
            else "At least one epoch failed catalogue-level feasibility. Stop and obtain a user decision.",
            "",
        ]
    )
    return "\n".join(lines)
