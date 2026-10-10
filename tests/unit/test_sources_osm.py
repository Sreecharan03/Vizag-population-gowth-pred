from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from src.acquisition.sources.osm import fetch_osm_data, verify_osm_file

_BOUNDARY_POLY = Polygon([(83.1, 17.6), (83.2, 17.6), (83.2, 17.7), (83.1, 17.7)])


def _gdf(polygon=_BOUNDARY_POLY):
    return gpd.GeoDataFrame({"id": [1]}, geometry=[polygon], crs="EPSG:4326")


def test_fetch_osm_data_writes_roads_and_amenities(tmp_path, monkeypatch):
    fake_roads = gpd.GeoDataFrame(
        {"highway": ["primary", "secondary"], "oneway": [[True], [False]]},  # list-typed col on purpose
        geometry=[LineString([(83.1, 17.6), (83.2, 17.7)]), LineString([(83.1, 17.7), (83.2, 17.6)])],
        crs="EPSG:4326",
    )
    fake_amenities = gpd.GeoDataFrame(
        {"amenity": ["hospital", "school"]},
        geometry=[Point(83.15, 17.65), Point(83.16, 17.66)],
        crs="EPSG:4326",
    )

    monkeypatch.setattr("src.acquisition.sources.osm.fetch_osm_roads", lambda gdf: fake_roads)
    monkeypatch.setattr("src.acquisition.sources.osm.fetch_osm_amenities", lambda gdf: fake_amenities)

    paths = fetch_osm_data(_gdf(), tmp_path)

    assert paths["roads"].exists()
    assert paths["amenities"].exists()

    roads_back = gpd.read_file(paths["roads"])
    assert len(roads_back) == 2
    amenities_back = gpd.read_file(paths["amenities"])
    assert len(amenities_back) == 2


def test_verify_osm_file_missing(tmp_path):
    result = verify_osm_file(tmp_path / "nope.gpkg")
    assert result["status"] == "FAILED"


def test_verify_osm_file_empty(tmp_path):
    empty_gdf = gpd.GeoDataFrame({"id": []}, geometry=[], crs="EPSG:4326")
    path = tmp_path / "empty.gpkg"
    empty_gdf.to_file(path, driver="GPKG")

    result = verify_osm_file(path)
    assert result["status"] == "FAILED"
    assert "no features" in result["reason"]


def test_verify_osm_file_valid(tmp_path):
    gdf = gpd.GeoDataFrame({"id": [1, 2]}, geometry=[Point(83.1, 17.6), Point(83.2, 17.7)], crs="EPSG:4326")
    path = tmp_path / "valid.gpkg"
    gdf.to_file(path, driver="GPKG")

    result = verify_osm_file(path)
    assert result["status"] == "OK"
    assert result["feature_count"] == 2
