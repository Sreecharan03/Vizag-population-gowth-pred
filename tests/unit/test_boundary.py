from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import Polygon, mapping

from src.acquisition.boundary import (
    BoundaryError,
    build_gvmc_boundary,
    check_area_sanity,
    cross_check_against_existing,
    fetch_osm_boundary,
    plot_boundary_check,
    reproject_and_buffer,
)
from src.storage.backends import FakeBackend

# A small valid polygon roughly around real Vizag coordinates (not the real
# boundary — just a geometrically valid stand-in for fixture purposes).
_FAKE_POLYGON = Polygon(
    [
        (83.15, 17.65),
        (83.35, 17.65),
        (83.35, 17.85),
        (83.15, 17.85),
        (83.15, 17.65),
    ]
)

_SELF_INTERSECTING_POLYGON_COORDS = [
    (83.15, 17.65),
    (83.35, 17.85),
    (83.35, 17.65),
    (83.15, 17.85),
    (83.15, 17.65),
]


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json_data


def _geojson_feature_collection(geom, *, category="boundary", place_type="local_authority", display_name="Fake GVMC, Andhra Pradesh, India"):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {
                    "osm_type": "relation",
                    "osm_id": 12345,
                    "display_name": display_name,
                    "category": category,
                    "type": place_type,
                },
            }
        ],
    }


def _fake_http_get_factory(response_json):
    def _fake_get(url, params=None, headers=None, timeout=None):
        assert "User-Agent" in headers
        return _FakeResponse(response_json)

    return _fake_get


# --- fetch_osm_boundary ------------------------------------------------------


def test_fetch_osm_boundary_returns_geometry_and_metadata():
    fake_get = _fake_http_get_factory(_geojson_feature_collection(_FAKE_POLYGON))
    result = fetch_osm_boundary("Fake query", http_get=fake_get)
    assert result["geometry"]["type"] == "Polygon"
    assert result["osm_id"] == 12345
    assert result["display_name"] == "Fake GVMC, Andhra Pradesh, India"


def test_fetch_osm_boundary_raises_on_no_match():
    fake_get = _fake_http_get_factory({"type": "FeatureCollection", "features": []})
    with pytest.raises(BoundaryError, match="no match"):
        fetch_osm_boundary("Nonexistent place", http_get=fake_get)


def test_fetch_osm_boundary_raises_on_non_polygon_geometry():
    response = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [83.2, 17.7]},
                "properties": {"osm_type": "node", "osm_id": 1, "display_name": "x", "category": "boundary", "type": "local_authority"},
            }
        ],
    }
    fake_get = _fake_http_get_factory(response)
    with pytest.raises(BoundaryError, match="no polygon geometry"):
        fetch_osm_boundary("query", http_get=fake_get)


def test_fetch_osm_boundary_rejects_non_administrative_match():
    fake_get = _fake_http_get_factory(
        _geojson_feature_collection(_FAKE_POLYGON, category="shop", place_type="supermarket")
    )
    with pytest.raises(BoundaryError, match="doesn't look like an administrative boundary"):
        fetch_osm_boundary("query", http_get=fake_get)


def test_fetch_osm_boundary_wraps_network_errors():
    def _raising_get(*args, **kwargs):
        import requests

        raise requests.exceptions.ConnectionError("network down")

    with pytest.raises(BoundaryError, match="request failed"):
        fetch_osm_boundary("query", http_get=_raising_get)


# --- reproject_and_buffer / check_area_sanity --------------------------------


def _fake_gdf():
    return gpd.GeoDataFrame({"id": [1]}, geometry=[_FAKE_POLYGON], crs="EPSG:4326")


def test_boundary_loads_and_is_valid_geometry():
    gdf = _fake_gdf()
    assert gdf.geometry.iloc[0].is_valid


def test_boundary_reprojected_to_target_crs():
    gdf = _fake_gdf()
    reprojected, _ = reproject_and_buffer(gdf, "EPSG:32644", 1000)
    assert reprojected.crs.to_epsg() == 32644


def test_buffered_boundary_area_greater_than_unbuffered():
    gdf = _fake_gdf()
    reprojected, buffered = reproject_and_buffer(gdf, "EPSG:32644", 1000)
    assert buffered.geometry.area.sum() > reprojected.geometry.area.sum()


def test_invalid_buffer_distance_rejected_at_config_load():
    gdf = _fake_gdf()
    with pytest.raises(BoundaryError, match="must be > 0"):
        reproject_and_buffer(gdf, "EPSG:32644", 0)
    with pytest.raises(BoundaryError, match="must be > 0"):
        reproject_and_buffer(gdf, "EPSG:32644", -500)


def test_boundary_area_within_sanity_bounds():
    gdf = _fake_gdf()
    reprojected, _ = reproject_and_buffer(gdf, "EPSG:32644", 1000)
    area = check_area_sanity(reprojected, min_km2=1, max_km2=10_000_000)
    assert area > 0


def test_boundary_area_sanity_check_rejects_implausible_area():
    gdf = _fake_gdf()
    reprojected, _ = reproject_and_buffer(gdf, "EPSG:32644", 1000)
    with pytest.raises(BoundaryError, match="outside the sane range"):
        check_area_sanity(reprojected, min_km2=1, max_km2=0.001)


# --- cross_check_against_existing --------------------------------------------


def test_cross_check_against_existing_returns_none_when_no_existing_file():
    gdf = _fake_gdf().to_crs("EPSG:32644")
    backend = FakeBackend()
    result = cross_check_against_existing(gdf, backend, "data/boundaries/gvmc_boundary.geojson")
    assert result is None


def test_cross_check_against_existing_detects_agreement(tmp_path):
    gdf = _fake_gdf().to_crs("EPSG:32644")

    existing_path = tmp_path / "existing.geojson"
    gdf.to_crs("EPSG:4326").to_file(existing_path, driver="GeoJSON")

    backend = FakeBackend()
    backend.seed("data/boundaries/gvmc_boundary.geojson", existing_path.read_bytes())

    result = cross_check_against_existing(gdf, backend, "data/boundaries/gvmc_boundary.geojson")
    assert result is not None
    assert result["agrees"] is True
    assert result["iou"] > 0.9


def test_cross_check_against_existing_detects_disagreement(tmp_path):
    gdf = _fake_gdf().to_crs("EPSG:32644")

    far_away_polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    far_gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[far_away_polygon], crs="EPSG:4326")
    existing_path = tmp_path / "existing.geojson"
    far_gdf.to_file(existing_path, driver="GeoJSON")

    backend = FakeBackend()
    backend.seed("data/boundaries/gvmc_boundary.geojson", existing_path.read_bytes())

    result = cross_check_against_existing(gdf, backend, "data/boundaries/gvmc_boundary.geojson")
    assert result["agrees"] is False
    assert result["iou"] == 0.0


# --- build_gvmc_boundary (full orchestration) --------------------------------


def test_build_gvmc_boundary_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr("src.acquisition.boundary.resolve_path", lambda key: tmp_path)
    fake_get = _fake_http_get_factory(_geojson_feature_collection(_FAKE_POLYGON))

    config = {
        "source": {"query": "Fake GVMC query"},
        "crs": "EPSG:32644",
        "buffer_distance_m": 2000,
        "sanity": {"min_area_km2": 1, "max_area_km2": 10_000_000},
    }

    result = build_gvmc_boundary(config, http_get=fake_get)

    assert result["boundary_path"].exists()
    assert result["buffered_path"].exists()
    assert result["area_km2"] > 0
    assert result["osm_id"] == 12345

    written = gpd.read_file(result["boundary_path"])
    assert written.crs.to_epsg() == 32644


def test_plot_boundary_check_creates_png(tmp_path):
    gdf = _fake_gdf().to_crs("EPSG:32644")
    reprojected, buffered = reproject_and_buffer(gdf, "EPSG:32644", 1000)

    output_path = tmp_path / "phase1_boundary_check.png"
    result_path = plot_boundary_check(reprojected, buffered, output_path)

    assert result_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
