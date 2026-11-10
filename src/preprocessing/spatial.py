"""Canonical grid and nodata-aware resampling for Phase 3 extraction."""

from __future__ import annotations

import math

import numpy as np
from affine import Affine
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject


def snap_bounds_outward(
    bounds: tuple[float, float, float, float],
    *,
    origin_x: float,
    origin_y: float,
    pixel_size: float,
) -> tuple[float, float, float, float]:
    """Snap left/bottom outward down and right/top outward up to one grid."""
    if pixel_size <= 0:
        raise ValueError("pixel_size must be positive")
    left, bottom, right, top = bounds
    if not left < right or not bottom < top:
        raise ValueError("bounds must have positive width and height")
    return (
        origin_x + math.floor((left - origin_x) / pixel_size) * pixel_size,
        origin_y + math.floor((bottom - origin_y) / pixel_size) * pixel_size,
        origin_x + math.ceil((right - origin_x) / pixel_size) * pixel_size,
        origin_y + math.ceil((top - origin_y) / pixel_size) * pixel_size,
    )


def grid_from_bounds(
    bounds: tuple[float, float, float, float], pixel_size: float
) -> tuple[Affine, int, int]:
    left, bottom, right, top = bounds
    width = int(round((right - left) / pixel_size))
    height = int(round((top - bottom) / pixel_size))
    if width <= 0 or height <= 0:
        raise ValueError("grid dimensions must be positive")
    return from_origin(left, top, pixel_size, pixel_size), width, height


def resample_array(
    source: np.ndarray,
    *,
    src_transform: Affine,
    src_crs,
    dst_transform: Affine,
    dst_crs,
    dst_shape: tuple[int, int],
    method: str,
    src_nodata,
    dst_nodata,
    dst_dtype,
) -> np.ndarray:
    """Resample one array with an explicit, restricted scientific method."""
    methods = {"nearest": Resampling.nearest, "bilinear": Resampling.bilinear}
    if method not in methods:
        raise ValueError(f"Unsupported resampling method: {method}")
    destination = np.full(dst_shape, dst_nodata, dtype=dst_dtype)
    reproject(
        source=source,
        destination=destination,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=src_nodata,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        dst_nodata=dst_nodata,
        resampling=methods[method],
        init_dest_nodata=True,
    )
    return destination

