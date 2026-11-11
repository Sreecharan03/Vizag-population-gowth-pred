import geopandas as gpd
import numpy as np
from shapely.geometry import box
from rasterio.transform import from_origin

from src.grid.feature_aggregation_pilot import build_cell_labels


def test_cell_labels_use_centres_and_boundary_mask():
    grid = gpd.GeoDataFrame({"grid_id": ["a", "b"]},
                            geometry=[box(0, 0, 2, 2), box(2, 0, 4, 2)], crs="EPSG:32644")
    boundary = gpd.GeoDataFrame(geometry=[box(0, 0, 3, 2)], crs="EPSG:32644")
    labels, ordered = build_cell_labels(grid, boundary, out_shape=(2, 4),
                                        transform=from_origin(0, 2, 1, 1),
                                        raster_crs="EPSG:32644", expected_cells=2)
    assert ordered["grid_id"].tolist() == ["a", "b"]
    assert labels.tolist() == [[1, 1, 2, 0], [1, 1, 2, 0]]
