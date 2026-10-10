from __future__ import annotations

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon

from src.acquisition.sources.worldcover import required_worldcover_tiles, verify_worldcover_file


def _gdf(polygon):
    return gpd.GeoDataFrame({"id": [1]}, geometry=[polygon], crs="EPSG:4326")


def test_required_worldcover_tiles_matches_real_vizag_tile():
    # The real buffered GVMC boundary (lat ~17.5-18.0, lon ~82.95-83.50) —
    # known from a real run to resolve to exactly one tile, N15E081.
    poly = Polygon([(82.95, 17.50), (83.50, 17.50), (83.50, 17.99), (82.95, 17.99)])
    tiles = required_worldcover_tiles(_gdf(poly))
    assert len(tiles) == 1
    assert tiles[0]["tile_id"] == "N15E081"


def test_required_worldcover_tiles_spans_two_tiles():
    # A polygon crossing the 18deg latitude tile boundary needs 2 tiles.
    poly = Polygon([(83.0, 17.5), (83.1, 17.5), (83.1, 18.5), (83.0, 18.5)])
    tiles = required_worldcover_tiles(_gdf(poly))
    tile_ids = {t["tile_id"] for t in tiles}
    assert tile_ids == {"N15E081", "N18E081"}


def test_required_worldcover_tiles_key_and_filename_format():
    poly = Polygon([(82.95, 17.50), (83.50, 17.50), (83.50, 17.99), (82.95, 17.99)])
    tiles = required_worldcover_tiles(_gdf(poly))
    assert tiles[0]["key"] == "v200/2021/map/ESA_WorldCover_10m_2021_v200_N15E081_Map.tif"
    assert tiles[0]["filename"] == "ESA_WorldCover_10m_2021_v200_N15E081_Map.tif"


def test_verify_worldcover_file_missing(tmp_path):
    result = verify_worldcover_file(tmp_path / "nope.tif")
    assert result["status"] == "FAILED"


def test_verify_worldcover_file_valid_geotiff(tmp_path):
    f = tmp_path / "valid.tif"
    data = np.zeros((100, 100), dtype="uint8")  # large enough to clear the min-size check
    transform = from_origin(81.0, 18.0, 0.0001, 0.0001)
    with rasterio.open(
        f, "w", driver="GTiff", height=100, width=100, count=1, dtype="uint8", crs="EPSG:4326", transform=transform
    ) as dst:
        dst.write(data, 1)

    result = verify_worldcover_file(f)
    assert result["status"] == "OK"
