import json

import pytest

from src.grid.osm_history import boundary_bbox, build_probe_report, inspect_snapshot, probe_history


class Response:
    ok = True
    status_code = 200
    headers = {"Content-Type": "application/json", "X-Request-ID": "r"}

    def __init__(self, body=None):
        self._body = body or {"result": [{"value": 3}]}
        self.content = json.dumps(self._body, sort_keys=True).encode()
        self.text = self.content.decode()

    def json(self):
        return self._body


class Session:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response()


def config():
    return {"api_root": "https://api.test/v2", "endpoint": "/stats/features/count.json",
            "timeout_seconds": 10, "maximum_response_bytes": 10000,
            "timestamps": ["2018-12-31T23:59:59Z", "2020-12-31T23:59:59Z"],
            "filters": {"roads": "highway=*", "amenities": "amenity=*"},
            "contract_version": "v", "boundary": {"key": "boundary"}}


def test_probe_covers_timestamp_filter_product_and_never_serializes_key():
    session = Session()
    rows = probe_history(session, "private", [82.0, 17.0, 83.0, 18.0], config())
    assert len(rows) == 4 and len(session.calls) == 4
    assert all(call[1]["headers"]["Authorization"] == "private" for call in session.calls)
    report = build_probe_report(config(), [82.0, 17.0, 83.0, 18.0],
                                {"type": "FeatureCollection", "features": []}, rows, "3.12")
    assert "private" not in json.dumps(report)
    assert report["b2_writes"] == 0 and report["payload_features_downloaded"] == 0


def test_boundary_bbox_requires_valid_wgs84_feature_collection():
    boundary = {"type": "FeatureCollection", "features": [{"type": "Feature",
        "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[
            [82.0, 17.0], [83.0, 17.0], [83.0, 18.0], [82.0, 18.0], [82.0, 17.0]
        ]]}}]}
    assert boundary_bbox(boundary) == [82.0, 17.0, 83.0, 18.0]
    with pytest.raises(RuntimeError, match="FeatureCollection"):
        boundary_bbox({"type": "Polygon", "coordinates": []})


def test_snapshot_inspection_enforces_count_and_geometry(tmp_path):
    import geopandas as gpd
    import pandas as pd
    from shapely.geometry import LineString
    path = tmp_path/"roads.parquet"
    frame = gpd.GeoDataFrame({
        "osm_type": ["way", "way"], "osm_id": [1, 2],
        "edit_timestamp": pd.to_datetime(["2018-01-01T00:00:00Z", "2018-02-01T00:00:00Z"]),
        "valid_to_timestamp": pd.to_datetime(["2019-01-01T00:00:00Z", "2019-01-01T00:00:00Z"]),
        "tags": [{"highway": "road"}, {"highway": "road"}],
    }, geometry=[
        LineString([(82, 17), (82.1, 17.1)]), LineString([(82.2, 17.2), (82.3, 17.3)])
    ], crs="EPSG:4326").rename_geometry("geom")
    frame.to_parquet(path)
    result = inspect_snapshot(path, timestamp="2018-12-31T23:59:59Z", expected_rows=2)
    assert result["rows"] == 2 and result["crs"] == "EPSG:4326"
    assert result["duplicate_geometries"] == 0
    with pytest.raises(RuntimeError, match="differ"):
        inspect_snapshot(path, timestamp="2018-12-31T23:59:59Z", expected_rows=3)
