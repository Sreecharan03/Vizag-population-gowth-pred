from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Polygon

from src.acquisition.fetch_missing import estimate_fetch, run_fetch_missing
from src.storage.backends import FakeBackend


def _gdf():
    poly = Polygon([(83.1, 17.6), (83.2, 17.6), (83.2, 17.7), (83.1, 17.7)])
    return gpd.GeoDataFrame({"id": [1]}, geometry=[poly], crs="EPSG:4326")


def test_estimate_fetch_combines_dem_and_worldcover_sizes(monkeypatch):
    monkeypatch.setattr(
        "src.acquisition.sources.dem.required_dem_tiles",
        lambda gdf: [{"tile_id": "T1", "key": "k1", "filename": "f1.tif"}],
    )
    monkeypatch.setattr("src.acquisition.sources.dem.estimate_dem_sizes", lambda tiles: {"T1": 1000})
    monkeypatch.setattr(
        "src.acquisition.sources.worldcover.required_worldcover_tiles",
        lambda gdf: [{"tile_id": "W1", "key": "wk1", "filename": "w1.tif"}],
    )
    monkeypatch.setattr("src.acquisition.sources.worldcover.estimate_worldcover_sizes", lambda tiles: {"W1": 2000})

    result = estimate_fetch(_gdf())
    assert result["dem_total_bytes"] == 1000
    assert result["worldcover_total_bytes"] == 2000
    assert result["estimated_total_bytes"] == 3000


def test_run_fetch_missing_dry_run_touches_nothing(monkeypatch):
    monkeypatch.setattr("src.acquisition.sources.dem.required_dem_tiles", lambda gdf: [])
    monkeypatch.setattr("src.acquisition.sources.dem.estimate_dem_sizes", lambda tiles: {})
    monkeypatch.setattr("src.acquisition.sources.worldcover.required_worldcover_tiles", lambda gdf: [])
    monkeypatch.setattr("src.acquisition.sources.worldcover.estimate_worldcover_sizes", lambda tiles: {})

    backend = FakeBackend()
    result = run_fetch_missing(_gdf(), backend, dry_run=True)

    assert result["dry_run"] is True
    assert backend.request_count == 0


def test_run_fetch_missing_real_run_uploads_only_verified_files(tmp_path, monkeypatch):
    monkeypatch.setattr("src.acquisition.fetch_missing.resolve_path", lambda key: tmp_path)

    good_dem = tmp_path / "good_dem.tif"
    good_dem.write_bytes(b"x" * 100)
    bad_dem = tmp_path / "bad_dem.tif"
    bad_dem.write_bytes(b"x" * 100)

    monkeypatch.setattr("src.acquisition.sources.dem.required_dem_tiles", lambda gdf: [{"tile_id": "T1"}])
    monkeypatch.setattr("src.acquisition.sources.dem.estimate_dem_sizes", lambda tiles: {"T1": 100})
    monkeypatch.setattr("src.acquisition.sources.dem.fetch_dem_tiles", lambda tiles, dest: [good_dem, bad_dem])
    monkeypatch.setattr(
        "src.acquisition.sources.dem.verify_dem_file",
        lambda p: {"status": "OK", "size_bytes": 100} if p == good_dem else {"status": "FAILED", "reason": "bad"},
    )

    good_wc = tmp_path / "good_wc.tif"
    good_wc.write_bytes(b"y" * 100)
    monkeypatch.setattr("src.acquisition.sources.worldcover.required_worldcover_tiles", lambda gdf: [{"tile_id": "W1"}])
    monkeypatch.setattr("src.acquisition.sources.worldcover.estimate_worldcover_sizes", lambda tiles: {"W1": 100})
    monkeypatch.setattr("src.acquisition.sources.worldcover.fetch_worldcover_tiles", lambda tiles, dest: [good_wc])
    monkeypatch.setattr(
        "src.acquisition.sources.worldcover.verify_worldcover_file", lambda p: {"status": "OK", "size_bytes": 100}
    )

    good_osm = tmp_path / "good_osm.gpkg"
    good_osm.write_bytes(b"z" * 100)
    monkeypatch.setattr(
        "src.acquisition.sources.osm.fetch_osm_data", lambda gdf, dest: {"roads": good_osm}
    )
    monkeypatch.setattr(
        "src.acquisition.sources.osm.verify_osm_file", lambda p: {"status": "OK", "feature_count": 5}
    )

    backend = FakeBackend()
    result = run_fetch_missing(_gdf(), backend, dry_run=False)

    assert result["dry_run"] is False
    dem_result = result["datasets"]["dem"]
    assert dem_result["uploaded_keys"] == ["vizag-geoai/data/raw/dem/good_dem.tif"]
    assert len(dem_result["skipped"]) == 1
    assert backend.exists("vizag-geoai/data/raw/dem/good_dem.tif")
    assert not backend.exists("vizag-geoai/data/raw/dem/bad_dem.tif")

    assert result["datasets"]["worldcover"]["all_ok"] is True
    assert result["datasets"]["osm"]["all_ok"] is True
    assert result["report_path"].exists()
    report_text = result["report_path"].read_text()
    assert "bad_dem.tif" in report_text or "bad" in report_text
