import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.grid.grid_job import MANIFEST, check_payloads, publish_grid, restore_boundary
from src.utils.io import load_config


class Stream(io.BytesIO):
    pass


class FakeClient:
    def __init__(self):
        self.items = {}
        self.markers = []
        self.puts = []
        self.fail_put = False

    def get_paginator(self, operation):
        assert operation == "list_object_versions"
        def pages(**kwargs):
            prefix = kwargs["Prefix"]
            versions = [{"Key": key, "Size": len(item["body"]), "VersionId": item["version"],
                         "IsLatest": True} for key, item in self.items.items() if key.startswith(prefix)]
            markers = [item for item in self.markers if item["Key"].startswith(prefix)]
            return iter([{}, {"Versions": versions, "DeleteMarkers": markers}])
        return SimpleNamespace(paginate=pages)

    def head_object(self, *, Bucket, Key, VersionId=None):
        item = self.items[Key]
        assert VersionId in (None, item["version"])
        return {"ContentLength": len(item["body"]), "VersionId": item["version"],
                "Metadata": {"sha256": item["sha256"]}}

    def get_object(self, *, Bucket, Key, VersionId):
        item = self.items[Key]
        assert VersionId == item["version"]
        return {"Body": Stream(item["body"])}

    def put_object(self, *, Bucket, Key, Body, Metadata, ContentType):
        assert Key not in self.items
        self.puts.append((Key, ContentType))
        version = f"new-{len(self.puts)}"
        self.items[Key] = {"body": Body, "version": version, "sha256": Metadata["sha256"]}
        if self.fail_put:
            raise ConnectionError("ambiguous")
        return {"VersionId": version}


def setup_client(config):
    client = FakeClient()
    body = b'{"type":"FeatureCollection"}'
    source = {**config["source"], "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
              "version_id": "boundary-v1"}
    client.items[source["key"]] = {"body": body, "version": source["version_id"],
                                    "sha256": source["sha256"]}
    return client, {**config, "source": source}, body


def blobs():
    return {"analysis_grid.geojson": b'{"type":"FeatureCollection","features":[]}',
            "grid_validation.json": b'{"status":"passed"}', "grid_preview.png": b"PNG"}


def test_restore_is_version_pinned_hashed_and_create_only(tmp_path):
    client, config, body = setup_client(load_config("grid_build"))
    target = tmp_path / "boundary.geojson"
    assert restore_boundary(client, "bucket", config["source"], target) == body
    assert target.read_bytes() == body
    with pytest.raises(FileExistsError):
        restore_boundary(client, "bucket", config["source"], target)
    client.items[config["source"]["key"]]["body"] += b"drift"
    with pytest.raises(RuntimeError, match="history"):
        restore_boundary(client, "bucket", config["source"], tmp_path / "other.geojson")


def test_publication_is_manifest_last_exact_readback_and_geojson_content_type():
    client, config, _ = setup_client(load_config("grid_build"))
    result, local = publish_grid(client, bucket="bucket", config=config, blobs=blobs(),
                                 checkpoint=lambda state: None)
    assert len(client.puts) == 4 and client.puts[-1][0] == config["outputs"][MANIFEST]
    assert client.puts[0][1] == "application/geo+json"
    assert set(local) == set(config["outputs"])
    assert result["status"] == "validated_grid_pending_user_review"
    assert result["output_payload_bytes"] == 3*sum(map(len, local.values()))
    assert result["part4_2_started"] is False


def test_collision_or_delete_marker_refuses_before_any_put():
    client, config, _ = setup_client(load_config("grid_build"))
    client.markers = [{"Key": config["outputs"][MANIFEST], "VersionId": "deleted"}]
    with pytest.raises(FileExistsError):
        publish_grid(client, bucket="bucket", config=config, blobs=blobs(), checkpoint=lambda state: None)
    assert not client.puts


def test_ambiguous_put_stops_once_without_manifest():
    client, config, _ = setup_client(load_config("grid_build"))
    client.fail_put = True
    with pytest.raises(ConnectionError, match="ambiguous"):
        publish_grid(client, bucket="bucket", config=config, blobs=blobs(), checkpoint=lambda state: None)
    assert len(client.puts) == 1
    assert config["outputs"][MANIFEST] not in client.items


def test_caps_and_exact_payload_set_are_enforced():
    config = load_config("grid_build")
    assert check_payloads(blobs(), config, with_manifest=False) == sum(map(len, blobs().values()))
    with pytest.raises(ValueError, match="payload set"):
        check_payloads({"unexpected": b"x"}, config, with_manifest=False)
    oversized = {**blobs(), "grid_preview.png": b"x"*(config["file_caps"]["grid_preview.png"]+1)}
    with pytest.raises(ValueError, match="per-file"):
        check_payloads(oversized, config, with_manifest=False)
