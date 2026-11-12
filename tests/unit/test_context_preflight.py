from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.grid.context_preflight import build_report, pin_metadata, temporal_assessment


class FakeClient:
    def __init__(self, items, markers=None):
        self.items = items
        self.markers = markers or []

    def get_paginator(self, operation):
        assert operation == "list_object_versions"
        def pages(**kwargs):
            key = kwargs["Prefix"]
            item = self.items[key]
            versions = item.get("versions") or [{"Key": key, "Size": item["size"],
                                                   "VersionId": item["version"], "IsLatest": True}]
            return iter([{"Versions": versions, "DeleteMarkers": self.markers}])
        return SimpleNamespace(paginate=pages)

    def head_object(self, *, Bucket, Key, VersionId):
        item = self.items[Key]
        return {"VersionId": VersionId, "ContentLength": item["size"], "ETag": '"etag"',
                "LastModified": datetime(2026, 10, 10, tzinfo=timezone.utc),
                "Metadata": item.get("metadata", {})}


def test_metadata_pin_selects_one_exact_version_without_payload_read():
    client = FakeClient({"k": {"size": 12, "version": "v1"}})
    record = pin_metadata(client, "b", {"key": "k", "expected_bytes": 12})
    assert record["version_id"] == "v1" and record["payload_validation_required"] is True


def test_metadata_pin_rejects_ambiguous_history_and_size_drift():
    item = {"size": 12, "version": "v1", "versions": [
        {"Key": "k", "Size": 12, "VersionId": "v1", "IsLatest": True},
        {"Key": "k", "Size": 10, "VersionId": "v0", "IsLatest": False},
    ]}
    with pytest.raises(RuntimeError, match="ambiguous"):
        pin_metadata(FakeClient({"k": item}), "b", {"key": "k", "expected_bytes": 12})
    with pytest.raises(RuntimeError, match="size"):
        pin_metadata(FakeClient({"k": {"size": 12, "version": "v1"}}), "b",
                     {"key": "k", "expected_bytes": 13})


def test_temporal_gate_blocks_2026_osm_from_historical_training():
    config = {"feature_epochs": [2018, 2020, 2022, 2024], "osm_acquisition_date": "2026-10-10",
              "worldpop": [{"year": year} for year in (2018, 2020, 2022, 2024)]}
    result = temporal_assessment(config)
    assert result["osm"]["future_relative_to_epochs"] == [2018, 2020, 2022, 2024]
    assert result["osm"]["may_use_as_2018_2024_predictor"] is False
    assert result["worldpop"]["allowed_mapping"]["2024"] == 2024


def test_report_is_metadata_only_and_aggregation_not_started():
    config = {"contract_version": "4.3.0", "maximum_objects": 2,
              "feature_epochs": [2018, 2020, 2022, 2024], "osm_acquisition_date": "2026-10-10",
              "worldpop": [{"year": year} for year in (2018, 2020, 2022, 2024)]}
    records = [{"key": "a", "bytes": 10}, {"key": "b", "bytes": 20}]
    report = build_report(config, records, "3.12.10")
    assert report["payload_bytes_read"] == 0 and report["b2_writes"] == 0
    assert report["aggregation_started"] is False and report["known_payload_bytes"] == 30
