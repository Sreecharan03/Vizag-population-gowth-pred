"""Fail-closed identity matching for Phase 5.1 Dynamic World inputs."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Mapping, Sequence

import numpy as np


_PRODUCT_ID = re.compile(
    r"^S2[AB]_MSIL2A_(?P<sensing>\d{8}T\d{6})_[^_]+_[^_]+_T(?P<tile>\d{2}[A-Z]{3})_"
)


def selected_scene_identity(scene: Mapping) -> dict[str, object]:
    """Extract the timestamp and MGRS tile that identify an approved L2A scene."""
    product_id = scene.get("product_id") or scene.get("scene_id")
    if not isinstance(product_id, str):
        raise ValueError("selected scene lacks product_id/scene_id")
    match = _PRODUCT_ID.match(product_id)
    if not match:
        raise ValueError(f"unsupported Sentinel-2 L2A product identifier: {product_id}")
    sensing = match.group("sensing")
    declared = scene.get("sensing_date")
    if declared is not None and declared != sensing:
        raise ValueError(f"{product_id}: sensing_date disagrees with product identifier")
    epoch = int(scene["epoch"])
    if int(sensing[:4]) != epoch:
        raise ValueError(f"{product_id}: epoch disagrees with sensing timestamp")
    instant = datetime.strptime(sensing, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    return {
        "product_id": product_id,
        "epoch": epoch,
        "sensing_timestamp": sensing,
        "sensing_time_utc": instant.isoformat().replace("+00:00", "Z"),
        "sensing_time_ms": int(instant.timestamp() * 1000),
        "tile": match.group("tile"),
    }


def validate_exact_matches(
    selected: Sequence[Mapping], candidates_by_product: Mapping[str, Sequence[Mapping]]
) -> list[dict[str, object]]:
    """Require one unique Dynamic World observation for every approved scene."""
    if len(selected) != 32:
        raise ValueError(f"expected 32 approved scenes, found {len(selected)}")
    matches: list[dict[str, object]] = []
    seen_assets: set[str] = set()
    epoch_counts: dict[int, int] = {}
    for scene in selected:
        identity = selected_scene_identity(scene)
        product_id = str(identity["product_id"])
        candidates = list(candidates_by_product.get(product_id, ()))
        if len(candidates) != 1:
            raise ValueError(
                f"{product_id}: expected exactly one Dynamic World match, found {len(candidates)}"
            )
        candidate = candidates[0]
        asset_id = candidate.get("system:index")
        time_ms = candidate.get("system:time_start")
        expected_prefix = f'{identity["sensing_timestamp"]}_'
        expected_suffix = f'_T{identity["tile"]}'
        if (not isinstance(asset_id, str) or not asset_id.startswith(expected_prefix)
                or not asset_id.endswith(expected_suffix)):
            raise ValueError(f"{product_id}: Dynamic World index is not an exact sensing-token/tile match")
        offset_ms = int(time_ms) - int(identity["sensing_time_ms"])
        if offset_ms < 0 or offset_ms > 15 * 60 * 1000:
            raise ValueError(f"{product_id}: Dynamic World tile time exceeds the sanity window")
        if asset_id in seen_assets:
            raise ValueError(f"Dynamic World asset matched more than once: {asset_id}")
        seen_assets.add(asset_id)
        epoch = int(identity["epoch"])
        epoch_counts[epoch] = epoch_counts.get(epoch, 0) + 1
        matches.append({**identity, "dynamic_world_index": asset_id,
                        "tile_time_offset_seconds": offset_ms // 1000})
    expected = {2018: 8, 2020: 8, 2022: 8, 2024: 8}
    if epoch_counts != expected:
        raise ValueError(f"unexpected exact-match epoch counts: {epoch_counts}")
    return sorted(matches, key=lambda row: (int(row["epoch"]), str(row["sensing_timestamp"])))


def built_statistics_qc(values: np.ndarray, *, nodata: float) -> dict[str, float | int]:
    """Validate a two-band built median/stddev raster using a shared 2D mask."""
    array = np.asarray(values)
    if array.ndim != 3 or array.shape[0] != 2:
        raise ValueError("built statistics must have shape (2, height, width)")
    band_valid = array != nodata
    partial_nodata = np.any(band_valid, axis=0) & ~np.all(band_valid, axis=0)
    if partial_nodata.any():
        raise ValueError("built statistics bands have inconsistent nodata masks")
    valid = np.all(band_valid, axis=0)
    if not valid.any():
        raise ValueError("built statistics contain no valid pixels")
    selected = array[:, valid]
    if not np.isfinite(selected).all():
        raise ValueError("built statistics contain nonfinite valid pixels")
    if (selected < 0).any() or (selected > 1).any():
        raise ValueError("built statistics fall outside [0, 1]")
    return {
        "valid_pixels": int(valid.sum()),
        "coverage_fraction": float(valid.mean()),
        "built_median_min": float(selected[0].min()),
        "built_median_max": float(selected[0].max()),
        "built_stddev_min": float(selected[1].min()),
        "built_stddev_max": float(selected[1].max()),
    }
