from copy import deepcopy
import hashlib
import io
import json
import re
from types import SimpleNamespace

import pytest

from src.storage.archive_audit import audit_archive, reject_non_read_api
from src.utils.io import load_config


class FakeClient:
    """Only read methods exist. Any raster GET is an explicit test failure."""

    def __init__(self):
        self.objects, self.bodies, self.history = {}, {}, []
        self.gets, self.streams = [], []

    def add(self, key, size, digest=None, body=None):
        self.objects[key] = {"ContentLength": size, "VersionId": key + "-version",
                             "Metadata": {"sha256": digest} if digest else {}}
        self.history.append({"Key": key, "Size": size, "VersionId": key + "-version", "IsLatest": True})
        if body is not None:
            self.bodies[key] = body

    def get_paginator(self, operation):
        if operation == "list_objects_v2":
            contents = [{"Key": k, "Size": v["ContentLength"]} for k, v in self.objects.items()]
            pages = [{"Contents": contents[:2]}, {"Contents": contents[2:]}]
        else:
            assert operation == "list_object_versions"
            pages = [{"Versions": self.history[:2]},
                     {"Versions": self.history[2:], "DeleteMarkers": getattr(self, "markers", [])}]
        return SimpleNamespace(paginate=lambda **kwargs: iter(pages))

    def head_object(self, *, Bucket, Key):
        return deepcopy(self.objects[Key])

    def get_object(self, *, Bucket, Key, VersionId):
        assert Key in self.bodies, "Raster payload must not be read"
        assert VersionId == self.objects[Key]["VersionId"]
        self.gets.append(Key)
        stream = io.BytesIO(self.bodies[Key])
        self.streams.append(stream)
        return {"Body": stream}


def fixture():
    client = FakeClient()
    source = {"key": "v2/composite.tif", "bytes": 12, "sha256": "a" * 64,
              "version_id": "v2/composite.tif-version"}
    count = {"key": "v2/count.tif", "bytes": 3, "sha256": "b" * 64}
    index = {"key": "v2/ndvi.tif", "bytes": 6, "sha256": "c" * 64,
             "version_id": "v2/ndvi.tif-version", "remote_sha256_verified": True,
             "remote_pixel_audit": True}
    scenes = [{"scene_id": "scene-one", "epoch": 2018, "outputs": {
        "reflectance": {"key": "v2/reflectance.tif", "bytes": 20, "sha256": "d" * 64},
        "scl": {"key": "v2/scl.tif", "bytes": 4, "sha256": "e" * 64}}}]
    epochs = [{"epoch": 2018, "source": source, "source_sha256_verified": True,
               "remote_full_resolution_audit": True, "outputs": {"ndvi": index}}]
    for item in (source, count, index):
        client.add(item["key"], item["bytes"], item["sha256"])
    for item in scenes[0]["outputs"].values():
        client.add(item["key"], item["bytes"])
    specs = []
    for key, rows in (("v2/extraction.jsonl", scenes), ("v2/indices.jsonl", epochs)):
        body = (json.dumps(rows[0]) + "\n").encode()
        digest = hashlib.sha256(body).hexdigest()
        client.add(key, len(body), digest, body)
        specs.append({"key": key, "bytes": len(body), "sha256": digest})
    args = dict(bucket="bucket", root="v2/", manifest_specs=specs,
                composite_specs=[source, count], expected_epochs=[2018],
                index_names=["ndvi"], expected_scene_count=1,
                manifest_read_limit_bytes=10000)
    return client, args


def test_paginated_read_only_audit_reads_only_two_manifests():
    client, args = fixture()
    result = audit_archive(client, **args)
    assert result["verified_raster_objects"] == 5
    assert result["verified_raster_bytes"] == 45
    assert result["scene_outputs_without_hash_metadata"] == 2
    assert result["requests"]["list_object_versions_pages"] == 2
    assert result["requests"]["get_object"] == 2
    assert client.gets == [i["key"] for i in args["manifest_specs"]]
    assert all(stream.closed for stream in client.streams)
    assert not result["raster_hashes_recomputed"]
    assert result["raster_payloads_read"] == 0


def test_optional_manifest_rows_do_not_add_payload_reads():
    client, args = fixture()
    result = audit_archive(client, **args, include_manifest_rows=True)
    assert len(result["manifest_rows"]) == 2
    assert result["manifest_rows"][1][0]["epoch"] == 2018
    assert len(client.gets) == 2


@pytest.mark.parametrize("failure", ["missing", "size", "hash", "version", "history", "marker"])
def test_identity_drift_or_later_page_version_history_halts(failure):
    client, args = fixture()
    key = "v2/ndvi.tif"
    if failure == "missing":
        del client.objects[key]
    elif failure == "size":
        client.objects[key]["ContentLength"] += 1
    elif failure == "hash":
        client.objects[key]["Metadata"]["sha256"] = "f" * 64
    elif failure == "version":
        client.objects[key]["VersionId"] = "changed-version"
    elif failure == "history":
        client.history.append({"Key": key, "VersionId": "old", "IsLatest": False, "Size": 6})
    else:
        client.markers = [{"Key": key, "VersionId": "deleted", "IsLatest": False}]
    with pytest.raises(RuntimeError):
        audit_archive(client, **args)
    assert len(client.gets) == 2


def test_manifest_payload_tampering_halts_and_closes_stream():
    client, args = fixture()
    key = args["manifest_specs"][0]["key"]
    client.bodies[key] = b"bad manifest"
    with pytest.raises(RuntimeError, match="bytes/hash mismatch"):
        audit_archive(client, **args)
    assert len(client.gets) == 1
    assert client.streams[0].closed


def test_manifest_limit_halts_before_get():
    client, args = fixture()
    args["manifest_read_limit_bytes"] = 1
    with pytest.raises(RuntimeError, match="small-read limit"):
        audit_archive(client, **args)
    assert client.gets == []


def test_unreferenced_objects_are_reported_not_removed():
    client, args = fixture()
    client.add("v2/old-pilot.tif", 10)
    before = deepcopy(client.objects)
    result = audit_archive(client, **args)
    assert result["other_objects"] == [{"key": "v2/old-pilot.tif", "bytes": 10,
                                        "versions": 1, "delete_markers": 0}]
    assert client.objects == before


@pytest.mark.parametrize("operation", ["PutObject", "DeleteObject", "DeleteObjects", "CopyObject", "CreateMultipartUpload"])
def test_non_read_api_blocked_before_request(operation):
    with pytest.raises(RuntimeError, match="refused API operation"):
        reject_non_read_api(SimpleNamespace(name=operation))


@pytest.mark.parametrize("operation", ["ListObjectsV2", "ListObjectVersions", "HeadObject", "GetObject"])
def test_read_api_allowed(operation):
    reject_non_read_api(SimpleNamespace(name=operation))


def test_archive_pins_are_complete_and_match_source_contract():
    config = load_config("archive")
    source_hashes = load_config("preprocessing")["indices"]["source_composite_sha256"]
    assert set(config["composites"]) == set(load_config("temporal")["epochs"])
    for epoch, products in config["composites"].items():
        assert set(products) == {"composite", "valid_obs_count"}
        assert products["composite"]["sha256"] == source_hashes[epoch]
        for identity in products.values():
            assert identity["bytes"] > 0
            assert re.fullmatch(r"[a-f0-9]{64}", identity["sha256"])
    assert sum(i["bytes"] for products in config["composites"].values()
               for i in products.values()) == 1468221549
    assert config["expected_scene_count"] == 32
    assert sum(i["bytes"] for i in config["manifests"].values()) == 52501
