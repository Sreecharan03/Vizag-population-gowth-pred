"""Guarded indices from corrected six-band composites; no implicit clipping."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

BAND_NAMES = ("B02", "B03", "B04", "B08", "B11", "B12")
INDEX_FORMULAS = {
    "ndvi": "(B08 - B04) / (B08 + B04)",
    "ndbi": "(B11 - B08) / (B11 + B08)",
    "ndwi": "(B03 - B08) / (B03 + B08)",
    "mndwi": "(B03 - B11) / (B03 + B11)",
    "bsi": "((B11 + B04) - (B08 + B02)) / ((B11 + B04) + (B08 + B02))",
}


@dataclass(frozen=True)
class IndexPolicy:
    output_nodata: float = -9999.0
    denominator_epsilon: float = 1e-6
    nominal_min: float = -1.0
    nominal_max: float = 1.0
    range_tolerance: float = 1e-6

    def __post_init__(self) -> None:
        values = (self.output_nodata, self.denominator_epsilon, self.nominal_min,
                  self.nominal_max, self.range_tolerance)
        if not all(np.isfinite(value) for value in values):
            raise ValueError("index policy values must be finite")
        if self.denominator_epsilon <= 0 or self.range_tolerance < 0:
            raise ValueError("epsilon must be positive and tolerance non-negative")
        if self.nominal_min >= self.nominal_max:
            raise ValueError("nominal range must be increasing")
        if self.nominal_min <= self.output_nodata <= self.nominal_max:
            raise ValueError("nodata must lie outside the nominal index range")

    @classmethod
    def from_mapping(cls, values: Mapping) -> "IndexPolicy":
        if values.get("output_dtype") != "float32":
            raise ValueError("index contract requires float32 outputs")
        if values.get("preserve_out_of_range_for_qc") is not True:
            raise ValueError("index contract must preserve out-of-range values for QC")
        if tuple(values.get("names", ())) != tuple(INDEX_FORMULAS):
            raise ValueError("index contract requires exactly the five ordered indices")
        if dict(values.get("formulas", {})) != INDEX_FORMULAS:
            raise ValueError("configured formulas do not match the tested implementation")
        return cls(
            output_nodata=float(values["output_nodata"]),
            denominator_epsilon=float(values["denominator_epsilon"]),
            nominal_min=float(values["nominal_range"][0]),
            nominal_max=float(values["nominal_range"][1]),
            range_tolerance=float(values["range_tolerance"]),
        )


def compute_indices(
    reflectance: np.ndarray,
    *,
    band_names: tuple[str, ...] = BAND_NAMES,
    input_nodata: float = -9999.0,
    policy: IndexPolicy | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, dict]]:
    """Compute one bounded (6, y, x) block and report every exclusion/range flag.

    All six bands must be finite/non-nodata at a pixel, matching the composite
    contract. Each index then independently guards its own denominator. Negative
    corrected reflectance and mathematically finite out-of-range indices remain
    unchanged for scientific review.
    """
    policy = policy or IndexPolicy()
    values = np.asarray(reflectance)
    if values.ndim != 3 or values.shape[0] != 6 or min(values.shape[1:]) < 1:
        raise ValueError("reflectance must have nonempty shape (6, y, x)")
    if tuple(band_names) != BAND_NAMES:
        raise ValueError("reflectance band order must match the six-band contract")
    if not np.issubdtype(values.dtype, np.floating):
        raise TypeError("indices require corrected floating-point reflectance")
    if not np.isfinite(input_nodata):
        raise ValueError("input_nodata must be finite")

    source_valid = np.all(np.isfinite(values) & (values != input_nodata), axis=0)
    # Float64 arithmetic avoids avoidable float32 cancellation/overflow.
    blue, green, red, nir, swir, _ = values.astype("float64")
    with np.errstate(invalid="ignore", over="ignore"):
        terms = {
            "ndvi": (nir - red, nir + red),
            "ndbi": (swir - nir, swir + nir),
            "ndwi": (green - nir, green + nir),
            "mndwi": (green - swir, green + swir),
            "bsi": ((swir + red) - (nir + blue),
                    (swir + red) + (nir + blue)),
        }
    outputs, statistics = {}, {}
    for name, (numerator, denominator) in terms.items():
        denominator_ok = np.isfinite(denominator) & (
            np.abs(denominator) > policy.denominator_epsilon
        )
        eligible = source_valid & denominator_ok & np.isfinite(numerator)
        result = np.full(source_valid.shape, np.nan, dtype="float64")
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            np.divide(numerator, denominator, out=result, where=eligible)
        output_valid = eligible & np.isfinite(result) & (
            np.abs(result) <= np.finfo("float32").max
        )
        output = np.full(source_valid.shape, policy.output_nodata, dtype="float32")
        output[output_valid] = result[output_valid].astype("float32")
        if np.any(output_valid & (output == policy.output_nodata)):
            raise ValueError(f"{name}: finite index collides with reserved nodata value")
        finite_values = output[output_valid]
        out_of_range = output_valid & (
            (output < policy.nominal_min - policy.range_tolerance)
            | (output > policy.nominal_max + policy.range_tolerance)
        )
        statistics[name] = {
            "pixels": int(source_valid.size),
            "source_valid_pixels": int(source_valid.sum()),
            "source_invalid_pixels": int((~source_valid).sum()),
            "guarded_denominator_pixels": int((source_valid & ~denominator_ok).sum()),
            "negative_denominator_pixels": int((source_valid & (denominator < 0)).sum()),
            "nonfinite_result_pixels": int((eligible & ~output_valid).sum()),
            "valid_pixels": int(output_valid.sum()),
            "nodata_pixels": int((~output_valid).sum()),
            "out_of_range_pixels": int(out_of_range.sum()),
            "minimum": float(finite_values.min()) if finite_values.size else None,
            "maximum": float(finite_values.max()) if finite_values.size else None,
        }
        outputs[name] = output
    return outputs, statistics
