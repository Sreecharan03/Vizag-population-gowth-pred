"""Chunked dry-season median composites and coverage gates for Phase 3.5."""

from __future__ import annotations

from dataclasses import dataclass

import dask.array as da
import numpy as np


class CoverageInsufficientError(RuntimeError):
    """Raised when an epoch cannot meet its approved observation-coverage gate."""


@dataclass(frozen=True)
class CoverageGate:
    min_valid_observations: int
    min_aoi_coverage_fraction: float

    def __post_init__(self) -> None:
        if self.min_valid_observations < 1:
            raise ValueError("min_valid_observations must be at least 1")
        if not 0 < self.min_aoi_coverage_fraction <= 1:
            raise ValueError("min_aoi_coverage_fraction must be in (0, 1]")

    @classmethod
    def from_mapping(cls, values: dict) -> "CoverageGate":
        if values.get("min_valid_observations") is None:
            raise ValueError("composite.min_valid_observations must be approved")
        if values.get("min_aoi_coverage_fraction") is None:
            raise ValueError("composite.min_aoi_coverage_fraction must be approved")
        return cls(
            min_valid_observations=int(values["min_valid_observations"]),
            min_aoi_coverage_fraction=float(values["min_aoi_coverage_fraction"]),
        )


def estimate_chunk_working_bytes(
    *, scene_count: int, band_count: int, chunk_size_pixels: int
) -> int:
    """Conservative memory estimate for one float32 chunk plus masks/work arrays."""
    if scene_count < 1 or band_count < 1 or chunk_size_pixels < 1:
        raise ValueError("scene_count, band_count and chunk_size_pixels must be positive")
    pixels = chunk_size_pixels * chunk_size_pixels
    input_bytes = scene_count * band_count * pixels * 4
    mask_bytes = scene_count * pixels
    output_bytes = band_count * pixels * 4 + pixels
    # nanmedian can allocate temporary partitions; use a 2x input allowance.
    return input_bytes * 2 + mask_bytes + output_bytes


def chunked_median_composite(
    reflectance: da.Array,
    valid_masks: da.Array,
    *,
    min_valid_observations: int = 1,
    output_nodata: float = -9999.0,
) -> tuple[da.Array, da.Array]:
    """Return lazy median (band,y,x) and valid count (y,x) arrays."""
    if reflectance.ndim != 4:
        raise ValueError("reflectance must have shape (scene, band, y, x)")
    if valid_masks.ndim != 3:
        raise ValueError("valid_masks must have shape (scene, y, x)")
    if (
        reflectance.shape[0] != valid_masks.shape[0]
        or reflectance.shape[2:] != valid_masks.shape[1:]
    ):
        raise ValueError("reflectance and valid-mask dimensions do not agree")
    if not np.issubdtype(reflectance.dtype, np.floating):
        raise TypeError("reflectance must have a floating dtype")
    if min_valid_observations < 1 or min_valid_observations > reflectance.shape[0]:
        raise ValueError(
            "min_valid_observations must be between 1 and the scene count"
        )

    # A median requires the complete eight-scene axis in each spatial task.
    reflectance = reflectance.rechunk({0: -1})
    valid_masks = valid_masks.rechunk({0: -1})
    masked = da.where(valid_masks[:, None, :, :], reflectance, np.nan)
    median = da.nanmedian(masked, axis=0).astype("float32")
    valid_count = valid_masks.sum(axis=0, dtype="uint8").astype("uint8")
    median = da.where(
        valid_count[None, :, :] >= min_valid_observations,
        median,
        output_nodata,
    ).astype("float32")
    return median, valid_count


def assess_coverage(
    valid_obs_count: np.ndarray,
    aoi_mask: np.ndarray,
    gate: CoverageGate,
) -> dict[str, int | float | bool]:
    """Evaluate and fail when too little AOI has the required observations."""
    counts = np.asarray(valid_obs_count)
    inside = np.asarray(aoi_mask, dtype=bool)
    if counts.ndim != 2 or counts.shape != inside.shape:
        raise ValueError("valid_obs_count and aoi_mask must be matching 2-D arrays")
    aoi_pixels = int(inside.sum())
    if aoi_pixels == 0:
        raise ValueError("AOI mask contains zero pixels")
    sufficient_pixels = int(
        ((counts >= gate.min_valid_observations) & inside).sum()
    )
    coverage_fraction = sufficient_pixels / aoi_pixels
    result: dict[str, int | float | bool] = {
        "aoi_pixels": aoi_pixels,
        "sufficient_pixels": sufficient_pixels,
        "min_valid_observations": gate.min_valid_observations,
        "coverage_fraction": coverage_fraction,
        "min_aoi_coverage_fraction": gate.min_aoi_coverage_fraction,
        "passed": coverage_fraction >= gate.min_aoi_coverage_fraction,
        "minimum_count": int(counts[inside].min()),
        "median_count": float(np.median(counts[inside])),
        "maximum_count": int(counts[inside].max()),
    }
    if not result["passed"]:
        raise CoverageInsufficientError(
            "epoch coverage gate failed: "
            f"{coverage_fraction:.4%} < {gate.min_aoi_coverage_fraction:.4%} "
            f"at >= {gate.min_valid_observations} observations"
        )
    return result
