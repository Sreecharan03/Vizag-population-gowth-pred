"""Pixel-level nodata relationship measurements for Sentinel-2 L2A."""

from __future__ import annotations

import numpy as np


def compare_dn_zero_to_scl_zero(
    dn: np.ndarray,
    scl_on_dn_grid: np.ndarray,
    inside_boundary: np.ndarray,
) -> dict[str, int | float]:
    """Compare DN=0 and SCL=0 inside a common spatial grid.

    This function measures the relationship; it does not silently declare
    either source authoritative or mutate any pixels.
    """
    if dn.shape != scl_on_dn_grid.shape or dn.shape != inside_boundary.shape:
        raise ValueError("DN, SCL, and boundary masks must have identical shapes")
    inside = inside_boundary.astype(bool, copy=False)
    dn_zero = (dn == 0) & inside
    scl_zero = (scl_on_dn_grid == 0) & inside
    comparable = int(inside.sum())
    both_zero = int((dn_zero & scl_zero).sum())
    dn_only = int((dn_zero & ~scl_zero).sum())
    scl_only = int((scl_zero & ~dn_zero).sum())
    union = both_zero + dn_only + scl_only
    return {
        "inside_pixels": comparable,
        "dn_zero_pixels": int(dn_zero.sum()),
        "scl_zero_pixels": int(scl_zero.sum()),
        "both_zero_pixels": both_zero,
        "dn_zero_scl_valid_pixels": dn_only,
        "scl_zero_dn_nonzero_pixels": scl_only,
        "mismatch_pixels": dn_only + scl_only,
        "mismatch_fraction_of_union": (dn_only + scl_only) / union if union else 0.0,
    }

