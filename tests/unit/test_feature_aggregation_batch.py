import numpy as np
import geopandas as gpd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from src.grid.feature_aggregation_batch import build_terrain


def _write_tile(path, left, values):
    with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=1,
                       dtype="float32", crs="EPSG:4326",
                       transform=from_origin(left, 1, .5, .5)) as dst:
        dst.write(np.asarray(values, dtype="float32"), 1)


def test_adjacent_dems_are_mosaicked_before_single_reprojection(tmp_path):
    left, right = tmp_path/"left.tif", tmp_path/"right.tif"
    _write_tile(left, 0, [[10, 20], [10, 20]])
    _write_tile(right, 1, [[30, 40], [30, 40]])
    grid = gpd.GeoDataFrame({"grid_id": ["a"]}, geometry=[box(0, 0, 2, 1)], crs="EPSG:4326")
    boundary = grid.copy()
    config = {"analysis_crs": "EPSG:3857", "terrain_resolution_m": 50000,
              "expected_cells": 1}
    frame, summary = build_terrain([left, right], grid, boundary, config)
    assert len(frame) == 1 and np.isfinite(frame.loc[0, "elevation_mean_m"])
    assert 10 <= summary["elevation_min_m"] <= 40
    assert 0 <= summary["slope_max_degrees"] <= 90
