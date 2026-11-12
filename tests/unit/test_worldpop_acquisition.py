import json

import pytest

from src.grid.worldpop_acquisition import build_probe_report, parse_boundary, probe_official_api, validate_catalog


class Response:
    def __init__(self, body, content_type="application/json", status_code=200):
        self.body = body
        self.status_code = status_code
        self.ok = 200 <= status_code < 400
        self.text = json.dumps(body)
        self.headers = {"Content-Type": content_type, "X-Request-ID": "request"}

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class Session:
    def __init__(self, catalog, rejection=None):
        self.catalog = catalog
        self.rejection = rejection
        self.posts = []

    def get(self, url, timeout):
        return Response(self.catalog)

    def post(self, url, json, timeout):
        self.posts.append(json)
        if self.rejection:
            return Response(self.rejection, status_code=422)
        return Response({"year": json["year"], "estimated_cells": 10})


def config():
    return {"catalog_url": "catalog", "raster_url": "raster", "timeout_seconds": 10,
            "expected_dataset": "WorldPop Global2", "expected_release": "R2025A",
            "expected_resolution_m": 100, "years": [2018, 2020, 2022, 2024],
            "request_resolution": "100m", "request_layer": "population",
            "contract_version": "v", "output_prefix": "out"}


def test_catalog_and_describe_probe_cover_one_consistent_release():
    cfg = config()
    session = Session({"dataset": "WorldPop Global2", "release": "R2025A",
                       "resolution_m": 100, "years": list(range(2015, 2031))})
    result = probe_official_api(session, {"type": "Polygon", "coordinates": []}, cfg)
    assert [item["year"] for item in result["descriptions"]] == cfg["years"]
    assert [item["year"] for item in session.posts] == cfg["years"]
    report = build_probe_report(result, cfg, "3.12.10")
    assert report["payload_rasters_downloaded"] == 0 and report["b2_writes"] == 0


def test_catalog_rejects_wrong_release_or_missing_year():
    cfg = config()
    with pytest.raises(RuntimeError, match="catalog"):
        validate_catalog({"dataset": "WorldPop Global2", "release": "old",
                          "resolution_m": 100, "years": cfg["years"]}, cfg)


def test_probe_preserves_structured_api_rejection_without_raising():
    cfg = config()
    catalog = {"dataset": "WorldPop Global2", "release": "R2025A",
               "resolution_m": 100, "years": list(range(2015, 2031))}
    result = probe_official_api(Session(catalog, {"error": "validation_error",
                                                  "field_errors": {"geojson": "bad"}}),
                                {"type": "FeatureCollection", "features": []}, cfg)
    report = build_probe_report(result, cfg, "3.12.10")
    assert report["status"] == "official_api_probe_rejected_download_not_started"
    assert report["api_error"]["status_code"] == 422
    assert report["payload_rasters_downloaded"] == 0 and report["b2_writes"] == 0


def test_boundary_must_be_geojson():
    source = {"type": "FeatureCollection",
              "crs": {"type": "name", "properties": {"name": "EPSG:32644"}},
              "features": [{"type": "Feature", "properties": {},
                            "geometry": {"type": "Polygon", "coordinates": [[
                                [700000, 1900000], [701000, 1900000], [701000, 1901000],
                                [700000, 1901000], [700000, 1900000]] ]}}]}
    parsed = parse_boundary(json.dumps(source).encode())
    coordinates = parsed["features"][0]["geometry"]["coordinates"][0]
    assert parsed["type"] == "FeatureCollection"
    assert all(-180 <= point[0] <= 180 and -90 <= point[1] <= 90 for point in coordinates)
    assert "crs" not in parsed
    with pytest.raises(RuntimeError, match="GeoJSON"):
        parse_boundary(b'{"type":"not-geojson"}')
