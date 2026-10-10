from __future__ import annotations

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon

from src.acquisition.sources.dem import required_dem_tiles, verify_dem_file


def _gdf(polygon):
    return gpd.GeoDataFrame({"id": [1]}, geometry=[polygon], crs="EPSG:4326")


def test_required_dem_tiles_single_tile_fully_inside():
    # Fully within N17/E083 (lat 17-18, lon 83-84).
    poly = Polygon([(83.1, 17.1), (83.2, 17.1), (83.2, 17.2), (83.1, 17.2)])
    tiles = required_dem_tiles(_gdf(poly))
    assert len(tiles) == 1
    assert tiles[0]["tile_id"] == "N17_00_E083_00"


def test_required_dem_tiles_spans_two_tiles():
    # Matches the real buffered GVMC boundary: spans the 83deg longitude edge.
    poly = Polygon([(82.95, 17.6), (83.3, 17.6), (83.3, 17.9), (82.95, 17.9)])
    tiles = required_dem_tiles(_gdf(poly))
    tile_ids = {t["tile_id"] for t in tiles}
    assert tile_ids == {"N17_00_E082_00", "N17_00_E083_00"}


def test_required_dem_tiles_key_format():
    poly = Polygon([(83.1, 17.1), (83.2, 17.1), (83.2, 17.2), (83.1, 17.2)])
    tiles = required_dem_tiles(_gdf(poly))
    assert tiles[0]["key"] == "Copernicus_DSM_COG_10_N17_00_E083_00_DEM/Copernicus_DSM_COG_10_N17_00_E083_00_DEM.tif"


def test_verify_dem_file_missing(tmp_path):
    result = verify_dem_file(tmp_path / "does_not_exist.tif")
    assert result["status"] == "FAILED"


def test_verify_dem_file_too_small(tmp_path):
    f = tmp_path / "tiny.tif"
    f.write_bytes(b"x" * 10)
    result = verify_dem_file(f)
    assert result["status"] == "FAILED"


def test_verify_dem_file_not_a_raster(tmp_path):
    f = tmp_path / "not_a_raster.tif"
    f.write_bytes(b"not a real geotiff" * 100)
    result = verify_dem_file(f)
    assert result["status"] == "FAILED"


def test_verify_dem_file_valid_geotiff(tmp_path):
    f = tmp_path / "valid.tif"
    data = np.zeros((50, 50), dtype="float32")  # large enough to clear the min-size check
    transform = from_origin(83.0, 18.0, 0.0003, 0.0003)
    with rasterio.open(
        f, "w", driver="GTiff", height=50, width=50, count=1, dtype="float32", crs="EPSG:4326", transform=transform
    ) as dst:
        dst.write(data, 1)

    result = verify_dem_file(f)
    assert result["status"] == "OK"
    assert result["crs"]
    assert result["shape"] == (50, 50)
