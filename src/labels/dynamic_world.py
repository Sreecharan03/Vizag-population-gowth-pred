"""Fail-closed identity matching for Phase 5.1 Dynamic World inputs."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

import numpy as np


_PRODUCT_ID = re.compile(
    r"^S2[AB]_MSIL2A_(?P<sensing>\d{8}T\d{6})_[^_]+_[^_]+_T(?P<tile>\d{2}[A-Z]{3})_"
)


def fetch_transient_http(
    url_factory: Callable[[], str],
    request_get: Callable[..., object],
    sleep: Callable[[float], None],
    *,
    timeout_seconds: int = 300,
    retry_delays_seconds: Sequence[float] = (2, 5, 10, 20),
) -> bytes:
    """Fetch bytes with bounded retries for transient HTTP/network failures."""
    transient_statuses = {429, 500, 502, 503, 504}
    delays = tuple(float(value) for value in retry_delays_seconds)
    for attempt in range(len(delays) + 1):
        try:
            response = request_get(url_factory(), timeout=timeout_seconds)
        except Exception:
            if attempt == len(delays):
                raise
            sleep(delays[attempt])
            continue
        status = int(response.status_code)
        if status < 400:
            return bytes(response.content)
        if status not in transient_statuses or attempt == len(delays):
            response.raise_for_status()
        sleep(delays[attempt])
    raise RuntimeError("unreachable transient HTTP retry state")


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


def apply_aoi_nodata(
    values: np.ndarray, inside_aoi: np.ndarray, *, nodata: int | float
) -> np.ndarray:
    """Return a copy with every pixel outside the approved 2D AOI set to nodata."""
    array = np.asarray(values)
    mask = np.asarray(inside_aoi, dtype=bool)
    if array.ndim != 3 or mask.ndim != 2 or array.shape[1:] != mask.shape:
        raise ValueError("raster bands and AOI mask have incompatible shapes")
    masked = array.copy()
    masked[:, ~mask] = nodata
    return masked


def aggregate_cell_evidence(
    built_probability: np.ndarray,
    temporal_stddev: np.ndarray,
    valid_count: np.ndarray,
    label_mode: np.ndarray,
    cell_labels: np.ndarray,
    *,
    expected_cells: int,
    probability_nodata: float = -9999.0,
    count_nodata: int = 0,
    label_nodata: int = 255,
) -> dict[str, np.ndarray]:
    """Aggregate aligned Dynamic World evidence into stable numbered grid cells."""
    arrays = [np.asarray(value) for value in (
        built_probability, temporal_stddev, valid_count, label_mode, cell_labels)]
    if any(value.ndim != 2 for value in arrays) or len({value.shape for value in arrays}) != 1:
        raise ValueError("Dynamic World evidence arrays must be aligned 2D grids")
    probability, uncertainty, support, mode, cells = arrays
    valid = probability != probability_nodata
    if (not np.array_equal(uncertainty != probability_nodata, valid)
            or not np.array_equal(support != count_nodata, valid)
            or not np.array_equal(mode != label_nodata, valid)):
        raise ValueError("Dynamic World evidence nodata masks differ")
    candidate = valid & (cells > 0)
    ids = cells[candidate].astype("int64", copy=False)
    if ids.size == 0 or ids.min() < 1 or ids.max() > expected_cells:
        raise ValueError("cell label raster contains no valid in-contract pixels")
    counts = np.bincount(ids, minlength=expected_cells + 1)[1:]
    probabilities = probability[candidate].astype("float64", copy=False)
    uncertainties = uncertainty[candidate].astype("float64", copy=False)
    supports = support[candidate].astype("float64", copy=False)
    if (not np.isfinite(probabilities).all() or not np.isfinite(uncertainties).all()
            or np.any(probabilities < 0) or np.any(probabilities > 1)
            or np.any(uncertainties < 0) or np.any(uncertainties > 1)
            or np.any(supports < 1)):
        raise ValueError("valid Dynamic World evidence contains invalid values")
    probability_sum = np.bincount(ids, weights=probabilities,
                                  minlength=expected_cells + 1)[1:]
    probability_square_sum = np.bincount(
        ids, weights=probabilities ** 2, minlength=expected_cells + 1)[1:]
    uncertainty_sum = np.bincount(ids, weights=uncertainties,
                                  minlength=expected_cells + 1)[1:]
    support_sum = np.bincount(ids, weights=supports,
                              minlength=expected_cells + 1)[1:]
    built_count = np.bincount(ids, weights=(mode[candidate] == 6),
                              minlength=expected_cells + 1)[1:]
    support_min = np.full(expected_cells + 1, np.iinfo("uint16").max, dtype="uint16")
    np.minimum.at(support_min, ids, support[candidate].astype("uint16", copy=False))
    supported = counts > 0
    mean_probability = np.full(expected_cells, np.nan, dtype="float64")
    mean_probability[supported] = probability_sum[supported] / counts[supported]
    spatial_variance = np.full(expected_cells, np.nan, dtype="float64")
    spatial_variance[supported] = np.maximum(
        probability_square_sum[supported] / counts[supported]
        - mean_probability[supported] ** 2, 0)
    modal_fraction = np.full(expected_cells, np.nan, dtype="float64")
    modal_fraction[supported] = built_count[supported] / counts[supported]
    mean_uncertainty = np.full(expected_cells, np.nan, dtype="float64")
    mean_uncertainty[supported] = uncertainty_sum[supported] / counts[supported]
    mean_support = np.full(expected_cells, np.nan, dtype="float64")
    mean_support[supported] = support_sum[supported] / counts[supported]
    minimum_support = support_min[1:].astype("int64")
    minimum_support[~supported] = 0
    return {
        "evidence_available": supported,
        "aoi_pixel_count": counts.astype("int64"),
        "mean_built_probability": mean_probability,
        "spatial_stddev_built_probability": np.sqrt(spatial_variance),
        "modal_built_pixel_count": built_count.astype("int64"),
        "modal_built_fraction": modal_fraction,
        "mean_temporal_stddev": mean_uncertainty,
        "mean_valid_observation_count": mean_support,
        "minimum_valid_observation_count": minimum_support,
    }


def spatially_distributed_samples(
    mask: np.ndarray, *, grid_rows: int = 3, grid_columns: int = 4
) -> list[tuple[int, int]]:
    """Choose one deterministic candidate nearest each spatial-block centre."""
    candidate = np.asarray(mask, dtype=bool)
    if candidate.ndim != 2 or grid_rows < 1 or grid_columns < 1:
        raise ValueError("sample mask/grid dimensions are invalid")
    height, width = candidate.shape
    samples: list[tuple[int, int]] = []
    for block_row in range(grid_rows):
        row_start = block_row * height // grid_rows
        row_end = (block_row + 1) * height // grid_rows
        for block_column in range(grid_columns):
            column_start = block_column * width // grid_columns
            column_end = (block_column + 1) * width // grid_columns
            locations = np.argwhere(
                candidate[row_start:row_end, column_start:column_end]
            )
            if locations.size == 0:
                continue
            centre = np.array([(row_end - row_start - 1) / 2,
                               (column_end - column_start - 1) / 2])
            local_row, local_column = locations[
                np.argmin(np.sum((locations - centre) ** 2, axis=1))
            ]
            samples.append((row_start + int(local_row), column_start + int(local_column)))
    if not samples:
        raise ValueError("sample stratum contains no candidate pixels")
    return samples
