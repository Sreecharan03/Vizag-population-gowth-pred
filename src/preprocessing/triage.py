"""Phase 3 Part 3.2: SCL-only scene triage and deterministic selection."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable, Iterable

import numpy as np

from src.preprocessing.catalogue import SceneRecord


@dataclass(frozen=True)
class TriageRecord:
    object_key: str
    product_id: str
    epoch: int
    sensing_date: str
    tile: str
    cloud_fraction: float
    shadow_fraction: float
    nodata_fraction: float
    usable_fraction: float
    unusable_fraction: float
    aoi_pixels: int
    selected: bool = False
    selection_rank: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_scl_metrics(
    scl: np.ndarray,
    aoi_mask: np.ndarray,
    *,
    nodata_classes: Iterable[int] = (0, 1),
    shadow_classes: Iterable[int] = (3,),
    cloud_classes: Iterable[int] = (8, 9, 10, 11),
) -> dict[str, float | int]:
    """Calculate mutually exclusive SCL fractions inside the exact AOI mask."""
    if scl.shape != aoi_mask.shape:
        raise ValueError("SCL array and AOI mask must have identical shapes")
    values = scl[np.asarray(aoi_mask, dtype=bool)]
    if values.size == 0:
        raise ValueError("AOI mask contains zero pixels")
    nodata = np.isin(values, tuple(nodata_classes))
    shadow = np.isin(values, tuple(shadow_classes))
    cloud = np.isin(values, tuple(cloud_classes))
    unusable = nodata | shadow | cloud
    total = values.size
    return {
        "cloud_fraction": float(cloud.sum() / total),
        "shadow_fraction": float(shadow.sum() / total),
        "nodata_fraction": float(nodata.sum() / total),
        "usable_fraction": float((~unusable).sum() / total),
        "unusable_fraction": float(unusable.sum() / total),
        "aoi_pixels": int(total),
    }


def in_season(sensing_date: str, start_month_day: str, end_month_day: str) -> bool:
    """Return whether a sensing timestamp falls in an inclusive month-day window."""
    value = datetime.strptime(sensing_date, "%Y%m%dT%H%M%S").strftime("%m-%d")
    if start_month_day <= end_month_day:
        return start_month_day <= value <= end_month_day
    return value >= start_month_day or value <= end_month_day


def triage_scenes(
    scenes: Iterable[SceneRecord],
    *,
    read_scl: Callable[[SceneRecord], tuple[np.ndarray, np.ndarray]],
    top_k_per_epoch: int,
    start_month_day: str,
    end_month_day: str,
    nodata_classes: Iterable[int] = (0, 1),
    shadow_classes: Iterable[int] = (3,),
    cloud_classes: Iterable[int] = (8, 9, 10, 11),
) -> list[TriageRecord]:
    """Read SCL once per eligible scene, score it, and select best K/epoch."""
    if top_k_per_epoch <= 0:
        raise ValueError("top_k_per_epoch must be positive")
    candidates = [
        scene for scene in scenes
        if scene.complete and scene.preferred and scene.covers_required_tile
        and scene.level == "L2A"
        and in_season(scene.sensing_date, start_month_day, end_month_day)
    ]

    provisional: list[TriageRecord] = []
    for scene in candidates:
        scl, aoi_mask = read_scl(scene)
        metrics = calculate_scl_metrics(
            scl,
            aoi_mask,
            nodata_classes=nodata_classes,
            shadow_classes=shadow_classes,
            cloud_classes=cloud_classes,
        )
        provisional.append(
            TriageRecord(
                object_key=scene.object_key,
                product_id=scene.product_id,
                epoch=scene.epoch,
                sensing_date=scene.sensing_date,
                tile=scene.tile,
                **metrics,
            )
        )

    result: list[TriageRecord] = []
    epochs = sorted({record.epoch for record in provisional})
    for epoch in epochs:
        ordered = sorted(
            (record for record in provisional if record.epoch == epoch),
            key=lambda record: (
                record.unusable_fraction,
                record.cloud_fraction,
                record.nodata_fraction,
                record.sensing_date,
                record.product_id,
            ),
        )
        ranks = {record.product_id: rank for rank, record in enumerate(ordered[:top_k_per_epoch], start=1)}
        for record in ordered:
            values = record.to_dict()
            values["selected"] = record.product_id in ranks
            values["selection_rank"] = ranks.get(record.product_id)
            result.append(TriageRecord(**values))
    return sorted(result, key=lambda record: (record.epoch, record.selection_rank or 10**9, record.sensing_date))


def selected_scenes_jsonl(records: Iterable[TriageRecord]) -> str:
    return "".join(
        json.dumps(record.to_dict(), sort_keys=True) + "\n"
        for record in records if record.selected
    )


def cloud_triage_csv(records: Iterable[TriageRecord]) -> str:
    rows = [record.to_dict() for record in records]
    if not rows:
        return ""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
