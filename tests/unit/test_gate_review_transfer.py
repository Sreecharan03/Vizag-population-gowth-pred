import hashlib
import io
from types import SimpleNamespace

import pytest

from src.preprocessing.gate_review_job import download_pinned, pin_small_object, publish_review
from src.utils.io import load_config


class Stream(io.BytesIO):
    def iter_chunks(self, chunk_size):
        while block := self.read(chunk_size):
            yield block


class FakeClient:
    def __init__(self):
        self.items, self.puts, self.streams, self.markers = {}, [], [], []
        self.fail_put = False

    def get_paginator(self, operation):
        assert operation == "list_object_versions"
        def pages(**kwargs):
            prefix = kwargs["Prefix"]
            return iter([{}, {"Versions": [{"Key": k, "Size": len(v["body"]), "VersionId": v["version"], "IsLatest": True}
                                          for k, v in self.items.items() if k.startswith(prefix)],
                              "DeleteMarkers": [m for m in self.markers if m["Key"].startswith(prefix)]}])
        return SimpleNamespace(paginate=pages)

    def put_object(self, *, Bucket, Key, Body, Metadata, ContentType):
        assert Key not in self.items
        self.puts.append((Key, ContentType))
        version = "v" + str(len(self.puts))
        self.items[Key] = {"body": Body, "version": version, "sha256": Metadata["sha256"]}
        if self.fail_put:
            raise ConnectionError("ambiguous")
        return {"VersionId": version}

    def head_object(self, *, Bucket, Key, VersionId=None):
        item = self.items[Key]
        return {"ContentLength": len(item["body"]), "VersionId": item["version"], "Metadata": {"sha256": item["sha256"]}}

    def get_object(self, *, Bucket, Key, VersionId):
        item = self.items[Key]
        assert item["version"] == VersionId
        stream = Stream(item["body"])
        self.streams.append(stream)
        return {"Body": stream}


def test_manifest_last_and_png_content_type_and_exact_readbacks():
    config = load_config("gate_review")
    manifest_name = "phase3_gate_review.v1.json"
    blobs = {name: b"new review data" for name in config["file_caps"] if name != manifest_name}
    client = FakeClient()
    result, payloads = publish_review(client, bucket="bucket", blobs=blobs, config=config,
                                     source_records=[], auxiliary=[], input_bytes=10, checkpoint=lambda s: None)
    assert len(client.puts) == 8 and client.puts[-1][0] == config["manifest_key"]
    assert client.puts[0][1] == "image/png"
    assert len(payloads) == 8 and all(s.closed for s in client.streams)
    assert not result["phase3_gate_approved"] and not result["eligibility_policy_approved"]
    assert result["output_payload_transfer_bytes"] == 3*sum(map(len, payloads.values()))


def test_collision_before_any_qc_output_put():
    config = load_config("gate_review")
    blobs = {n: b"review" for n in config["file_caps"] if n != "phase3_gate_review.v1.json"}
    client = FakeClient()
    client.markers = [{"Key": config["manifest_key"], "VersionId": "deleted"}]
    with pytest.raises(FileExistsError):
        publish_review(client, bucket="bucket", blobs=blobs, config=config,
                       source_records=[], auxiliary=[], input_bytes=10, checkpoint=lambda s: None)
    assert not client.puts


def test_ambiguous_qc_put_stops_once_preserves_object_and_leaves_no_manifest():
    config = load_config("gate_review")
    blobs = {n: b"review" for n in config["file_caps"] if n != "phase3_gate_review.v1.json"}
    client = FakeClient(); client.fail_put = True
    with pytest.raises(ConnectionError):
        publish_review(client, bucket="bucket", blobs=blobs, config=config,
                       source_records=[], auxiliary=[], input_bytes=10, checkpoint=lambda s: None)
    assert len(client.puts) == 1 and len(client.items) == 1
    assert config["manifest_key"] not in client.items


def test_small_input_pin_limit_and_download_hash(tmp_path):
    client = FakeClient()
    body = b"existing input"
    digest = hashlib.sha256(body).hexdigest()
    client.items["input"] = {"body": body, "version": "pinned", "sha256": digest}
    actual, info = pin_small_object(client, "bucket", "input", 100)
    assert actual == body and info["version_id"] == "pinned"
    with pytest.raises(RuntimeError, match="approved size"):
        pin_small_object(client, "bucket", "input", 1)
    path = tmp_path / "scratch.tif"
    assert download_pinned(client, "bucket", info, path) == len(body)
    assert path.read_bytes() == body
    with pytest.raises(FileExistsError):
        download_pinned(client, "bucket", info, path)
    assert all(s.closed for s in client.streams)


def test_bad_source_hash_stops_and_preserves_only_generated_scratch(tmp_path):
    client = FakeClient()
    client.items["input"] = {"body": b"bytes", "version": "pinned", "sha256": "a"*64}
    with pytest.raises(RuntimeError, match="hash mismatch"):
        download_pinned(client, "bucket", {"key": "input", "bytes": 5, "version_id": "pinned", "sha256": "a"*64}, tmp_path / "scratch.tif")
    assert (tmp_path / "scratch.tif").exists()
