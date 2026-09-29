"""Shared validation assertions reused by every later phase.

These work on plain values (numpy arrays, CRS identifiers, bounding-box
tuples) rather than importing geopandas/rasterio directly, since the full
geospatial stack isn't installed until Phase 0 Part 0.4. Any CRS-like object
exposing to_epsg()/to_string() (e.g. a pyproj.CRS, once installed) works for
assert_crs, as does a plain "EPSG:xxxx" string or int.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np


class ValidationError(Exception):
    """Raised when a shared data-quality assertion fails."""


def _normalize_crs(crs: object) -> str:
    if crs is None:
        raise ValidationError("CRS is None — cannot validate an undefined CRS")
    if isinstance(crs, bool):
        raise ValidationError(f"CRS must be a string, int, or CRS-like object, got bool: {crs!r}")
    if isinstance(crs, int):
        return f"EPSG:{crs}"
    if isinstance(crs, str):
        normalized = crs.strip().upper()
        if not normalized:
            raise ValidationError("CRS string is empty — cannot validate an undefined CRS")
        return normalized
    to_epsg = getattr(crs, "to_epsg", None)
    if callable(to_epsg):
        epsg = to_epsg()
        if epsg is not None:
            return f"EPSG:{epsg}"
    to_string = getattr(crs, "to_string", None)
    if callable(to_string):
        return str(to_string()).strip().upper()
    return str(crs).strip().upper()


def assert_crs(actual_crs: object, expected_crs: object) -> None:
    """Raise ValidationError unless actual_crs matches expected_crs.

    Comparison is on normalized string form, so "EPSG:32644", 32644, and a
    pyproj.CRS for the same CRS are all treated as equal.
    """
    actual_norm = _normalize_crs(actual_crs)
    expected_norm = _normalize_crs(expected_crs)
    if actual_norm != expected_norm:
        raise ValidationError(f"CRS mismatch: expected {expected_norm!r}, got {actual_norm!r}")


def assert_bounds_within(bounds: Sequence[float], allowed_bounds: Sequence[float]) -> None:
    """Raise ValidationError unless `bounds` (minx, miny, maxx, maxy) lies
    entirely within `allowed_bounds`, and neither box is degenerate/inverted.
    """
    if len(bounds) != 4 or len(allowed_bounds) != 4:
        raise ValidationError(
            f"bounds must be (minx, miny, maxx, maxy); got {bounds!r} / {allowed_bounds!r}"
        )
    minx, miny, maxx, maxy = bounds
    a_minx, a_miny, a_maxx, a_maxy = allowed_bounds
    if minx > maxx or miny > maxy:
        raise ValidationError(f"bounds is degenerate/inverted: {bounds!r}")
    if a_minx > a_maxx or a_miny > a_maxy:
        raise ValidationError(f"allowed_bounds is degenerate/inverted: {allowed_bounds!r}")
    if not (a_minx <= minx and a_miny <= miny and maxx <= a_maxx and maxy <= a_maxy):
        raise ValidationError(f"bounds {bounds!r} is not within allowed bounds {allowed_bounds!r}")


def assert_no_nan(array: "np.ndarray | Iterable[float]", *, name: str = "array") -> None:
    """Raise ValidationError if any element of `array` is NaN, or if it's empty.

    Never silently drops or coerces NaNs — a downstream 0 must never be used
    to mean "confirmed empty" when the real answer is "unknown."
    """
    arr = np.asarray(array, dtype=float)
    if arr.size == 0:
        raise ValidationError(f"{name} is empty — cannot validate")
    nan_count = int(np.isnan(arr).sum())
    if nan_count:
        raise ValidationError(f"{name} contains {nan_count} NaN value(s) out of {arr.size}")


def assert_nodata_consistent(
    array: np.ndarray,
    nodata_mask: np.ndarray,
    *,
    nodata_value: float = math.nan,
    name: str = "array",
) -> None:
    """Raise ValidationError unless `array` and `nodata_mask` fully agree:
    every pixel flagged nodata actually holds `nodata_value` (default NaN),
    and no pixel NOT flagged nodata accidentally holds that same sentinel
    (which would make real data silently look like missing data, or vice
    versa — e.g. an orbit-edge nodata stripe must stay nodata, never read as
    a real 0 reflectance value).
    """
    arr = np.asarray(array, dtype=float)
    mask = np.asarray(nodata_mask, dtype=bool)
    if arr.shape != mask.shape:
        raise ValidationError(f"{name}: array shape {arr.shape} != nodata_mask shape {mask.shape}")
    if arr.size == 0:
        raise ValidationError(f"{name} is empty — cannot validate")

    is_sentinel = np.isnan(arr) if math.isnan(nodata_value) else (arr == nodata_value)

    missing_flagged_nodata = int(np.sum(mask & ~is_sentinel))
    if missing_flagged_nodata:
        raise ValidationError(
            f"{name}: {missing_flagged_nodata} pixel(s) flagged nodata but not set to "
            f"the nodata value {nodata_value!r}"
        )

    falsely_nodata = int(np.sum(~mask & is_sentinel))
    if falsely_nodata:
        raise ValidationError(
            f"{name}: {falsely_nodata} valid pixel(s) unexpectedly hold the nodata sentinel "
            f"value {nodata_value!r} — this would be silently treated as missing data"
        )
