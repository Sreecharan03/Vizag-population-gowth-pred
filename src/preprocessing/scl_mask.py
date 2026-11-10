"""Configurable Sentinel-2 SCL validity masks for Phase 3.4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

KNOWN_SCL_CLASSES = frozenset(range(12))


@dataclass(frozen=True)
class MaskPolicy:
    valid_classes: frozenset[int]
    invalid_classes: frozenset[int]
    dark_class_2_valid: bool
    dilate_classes: frozenset[int]
    dilation_radius_pixels: int
    unknown_classes_invalid: bool

    @classmethod
    def from_mapping(cls, values: Mapping) -> "MaskPolicy":
        """Parse and fail-closed validate the mask configuration."""
        policy = cls(
            valid_classes=frozenset(int(value) for value in values["valid_classes"]),
            invalid_classes=frozenset(int(value) for value in values["invalid_classes"]),
            dark_class_2_valid=bool(values["dark_class_2_valid"]),
            dilate_classes=frozenset(int(value) for value in values["dilate_classes"]),
            dilation_radius_pixels=int(values["dilation_radius_pixels"]),
            unknown_classes_invalid=bool(values["unknown_classes_invalid"]),
        )
        if policy.dilation_radius_pixels < 0:
            raise ValueError("dilation_radius_pixels must be non-negative")
        if not policy.valid_classes or not policy.valid_classes <= KNOWN_SCL_CLASSES:
            raise ValueError("valid_classes must be non-empty known SCL classes")
        if not policy.invalid_classes <= KNOWN_SCL_CLASSES:
            raise ValueError("invalid_classes contains an unknown SCL class")
        if policy.valid_classes & policy.invalid_classes:
            raise ValueError("valid_classes and invalid_classes must be disjoint")
        if 2 in policy.valid_classes or 2 in policy.invalid_classes:
            raise ValueError("class 2 must be controlled only by dark_class_2_valid")
        expected = KNOWN_SCL_CLASSES - {2}
        if policy.valid_classes | policy.invalid_classes != expected:
            raise ValueError("valid_classes and invalid_classes must cover classes 0..11 except 2")
        if not policy.dilate_classes <= policy.invalid_classes:
            raise ValueError("dilate_classes must be a subset of invalid_classes")
        return policy


def dilate_mask(mask: np.ndarray, radius_pixels: int) -> np.ndarray:
    """Dilate a 2-D boolean mask with a circular integer-pixel footprint."""
    source = np.asarray(mask, dtype=bool)
    if source.ndim != 2:
        raise ValueError("mask must be two-dimensional")
    if radius_pixels < 0:
        raise ValueError("radius_pixels must be non-negative")
    if radius_pixels == 0 or not source.any():
        return source.copy()
    height, width = source.shape
    result = source.copy()
    radius_squared = radius_pixels * radius_pixels
    for dy in range(-radius_pixels, radius_pixels + 1):
        for dx in range(-radius_pixels, radius_pixels + 1):
            if dx * dx + dy * dy > radius_squared:
                continue
            src_y0, src_y1 = max(0, -dy), min(height, height - dy)
            src_x0, src_x1 = max(0, -dx), min(width, width - dx)
            dst_y0, dst_y1 = max(0, dy), min(height, height + dy)
            dst_x0, dst_x1 = max(0, dx), min(width, width + dx)
            result[dst_y0:dst_y1, dst_x0:dst_x1] |= source[
                src_y0:src_y1, src_x0:src_x1
            ]
    return result


def build_valid_mask(
    scl: np.ndarray,
    policy: MaskPolicy,
    *,
    reflectance_valid: np.ndarray | None = None,
    aoi_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, int | float | list[int]]]:
    """Build the final validity mask and return auditable pixel statistics."""
    scl_array = np.asarray(scl)
    if scl_array.ndim != 2:
        raise ValueError("SCL must be a two-dimensional array")
    if not np.issubdtype(scl_array.dtype, np.integer):
        raise TypeError("SCL must have an integer dtype")
    shape = scl_array.shape
    for name, candidate in (
        ("reflectance_valid", reflectance_valid),
        ("aoi_mask", aoi_mask),
    ):
        if candidate is not None and np.asarray(candidate).shape != shape:
            raise ValueError(f"{name} shape must match SCL")

    accepted = set(policy.valid_classes)
    if policy.dark_class_2_valid:
        accepted.add(2)
    unknown = ~np.isin(scl_array, tuple(KNOWN_SCL_CLASSES))
    if unknown.any() and not policy.unknown_classes_invalid:
        values = sorted(int(value) for value in np.unique(scl_array[unknown]))
        raise ValueError(f"unknown SCL classes encountered: {values}")

    valid_before_dilation = np.isin(scl_array, tuple(sorted(accepted)))
    dilation_seed = np.isin(scl_array, tuple(sorted(policy.dilate_classes)))
    dilated_invalid = dilate_mask(dilation_seed, policy.dilation_radius_pixels)
    valid = valid_before_dilation & ~dilated_invalid & ~unknown
    if reflectance_valid is not None:
        valid &= np.asarray(reflectance_valid, dtype=bool)
    if aoi_mask is not None:
        valid &= np.asarray(aoi_mask, dtype=bool)

    considered = np.ones(shape, dtype=bool)
    if aoi_mask is not None:
        considered &= np.asarray(aoi_mask, dtype=bool)
    considered_count = int(considered.sum())
    valid_count = int((valid & considered).sum())
    statistics: dict[str, int | float | list[int]] = {
        "considered_pixels": considered_count,
        "valid_pixels": valid_count,
        "valid_fraction": valid_count / considered_count if considered_count else 0.0,
        "dilation_seed_pixels": int((dilation_seed & considered).sum()),
        "dilated_invalid_pixels": int((dilated_invalid & considered).sum()),
        "unknown_pixels": int((unknown & considered).sum()),
        "observed_classes": [int(value) for value in np.unique(scl_array[considered])],
    }
    return valid, statistics


def mask_policy_markdown(policy: MaskPolicy) -> str:
    """Render the policy text embedded into later Phase 3 QC reports."""
    class_two = "valid" if policy.dark_class_2_valid else "invalid"
    return "\n".join(
        [
            "### SCL mask policy",
            "",
            f"- Valid classes: {sorted(policy.valid_classes)}",
            f"- Invalid classes: {sorted(policy.invalid_classes)}",
            f"- Class 2 (dark/topographic shadow): {class_two}",
            f"- Dilated classes: {sorted(policy.dilate_classes)}",
            f"- Circular dilation radius: {policy.dilation_radius_pixels} pixels",
            "- Unknown SCL values: invalid" if policy.unknown_classes_invalid else "- Unknown SCL values: error",
            "- Limitation: SCL can misclassify dark or bright roofs; masked urban area must be reviewed in QC.",
        ]
    ) + "\n"
