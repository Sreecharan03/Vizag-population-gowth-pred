import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from src.grid.feature_preflight import read_pinned_small, pin_dem_metadata, build_report, validate_manifests


class FakeClient:
    def __init__(self, items, markers=None):
        self.items, self.markers = items, markers or []

    def get_paginator(self, operation):
        assert operation == "list_object_versions"
        def pages(**kwargs):
            prefix = kwargs["Prefix"]
            vv = [{"Key": key, "Size": len(value["body"]), "VersionId": value["version"],
                   "IsLatest": True} for key, value in self.items.items() if key.startswith(prefix)]
            return iter([{}, {"Versions": vv, "DeleteMarkers": self.markers}])
        return SimpleNamespace(paginate=pages)

    def get_object(self, *, Bucket, Key, VersionId):
        item = self.items[Key]
        assert VersionId == item["version"]
        return {"Body": io.BytesIO(item["body"])}

    def head_object(self, *, Bucket, Key, VersionId):
        item = self.items[Key]
        return {"VersionId": item["version"], "ContentLength": len(item["body"]),
                "ETag": '"etag"', "Metadata": item.get("metadata", {})}


def test_small_pin_is_exact_version_size_and_hash():
    body = b"manifest"
    spec = {"key": "small", "version_id": "v1", "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest()}
    assert read_pinned_small(FakeClient({"small": {"body": body, "version": "v1"}}), "b", spec) == body
    with pytest.raises(RuntimeError, match="identity"):
        read_pinned_small(FakeClient({"small": {"body": body, "version": "v2"}}), "b", spec)


def test_dem_metadata_reports_missing_hash_without_payload_get():
    body = b"x"*12
    client = FakeClient({"dem": {"body": body, "version": "dem-v1"}})
    records = pin_dem_metadata(client, "b", [{"key": "dem", "expected_bytes": len(body)}])
    assert records[0]["payload_hash_required"] is True
    client.items["dem"]["metadata"] = {"sha256": "a"*64}
    assert pin_dem_metadata(client, "b", [{"key": "dem", "expected_bytes": len(body)}])[0]["sha256_metadata"] == "a"*64


def test_report_blocks_aggregation_when_dem_hash_is_missing():
    config = {"contract_version": "4.2.0", "maximum_payload_bytes": 100,
              "grid_manifest": {"bytes": 1}, "index_manifest": {"bytes": 2}, "boundary": {"bytes": 3}}
    grid = {"bytes": 4}
    rows = [{"bytes": 10} for _ in range(20)]
    dem = [{"key": "dem", "bytes": 12, "payload_hash_required": True, "sha256_metadata": None}]
    report = build_report(config, grid, rows, dem, "3.12.10")
    assert report["status"] == "preflight_complete_dem_payload_hash_required"
    assert report["raster_payload_bytes_read"] == 0 and not report["part4_2b_started"]
    assert report["known_aggregation_input_bytes"] == 219


def test_manifest_validation_flattens_four_epochs_and_matches_pins():
    grid_item = {"name": "analysis_grid.geojson", "bytes": 2816012, "key": "grid"}
    grid_body = json.dumps({"contract_version": "4.1.0",
                            "status": "validated_grid_pending_user_review",
                            "geometry_only": True, "outputs": [grid_item]}).encode()
    manifest_rows, expected = [], []
    for epoch in (2018, 2020, 2022, 2024):
        outputs = {}
        for role in ("ndvi", "ndbi", "ndwi", "mndwi", "bsi"):
            info = {"key": f"{epoch}/{role}", "bytes": 10, "sha256": role,
                    "version_id": f"v-{epoch}-{role}"}
            outputs[role] = info
            expected.append({"epoch": epoch, "role": role, **info})
        manifest_rows.append({"epoch": epoch, "outputs": outputs})
    index_body = ("\n".join(json.dumps(row) for row in manifest_rows)+"\n").encode()
    actual_grid, rows = validate_manifests(grid_body, index_body, expected)
    assert actual_grid == grid_item and len(rows) == 20
    bad = [dict(item) for item in expected]
    bad[0]["version_id"] = "drift"
    with pytest.raises(RuntimeError, match="differs"):
        validate_manifests(grid_body, index_body, bad)
