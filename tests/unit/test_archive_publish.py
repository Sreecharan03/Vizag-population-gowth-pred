from copy import deepcopy
import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from src.storage.archive_publish import (
    ArchivePublicationError, load_approved_payloads, publish_archive,
    reject_non_archive_api, validate_payloads,
)
from src.utils.io import load_config


class FakeClient:
    def __init__(self):
        self.objects, self.history, self.puts, self.gets, self.streams = {}, [], [], [], []
        self.markers = []
        self.fail_put = self.corrupt_get = self.bad_head = self.no_version = False

    def add(self, key, body, digest=None, version=None):
        version = version or f"version-{len(self.history)}"
        self.objects[key] = {"body": body, "version": version, "sha256": digest}
        self.history.append({"Key": key, "Size": len(body), "VersionId": version, "IsLatest": True})
        return version

    def get_paginator(self, operation):
        def paginate(**kwargs):
            prefix = kwargs["Prefix"]
            if operation == "list_objects_v2":
                values = [{"Key": k, "Size": len(v["body"])} for k, v in self.objects.items() if k.startswith(prefix)]
                return iter([{}, {"Contents": values}])
            assert operation == "list_object_versions"
            return iter([{}, {"Versions": [v for v in self.history if v["Key"].startswith(prefix)],
                              "DeleteMarkers": [v for v in self.markers if v["Key"].startswith(prefix)]}])
        return SimpleNamespace(paginate=paginate)

    def put_object(self, *, Bucket, Key, Body, Metadata, ContentType):
        self.puts.append(Key)
        assert Key not in self.objects, "Existing object must not be overwritten"
        version = self.add(Key, Body, Metadata["sha256"])
        if self.fail_put:
            raise ConnectionError("ambiguous PUT outcome")
        return {} if self.no_version else {"VersionId": version}

    def head_object(self, *, Bucket, Key, VersionId):
        item = self.objects[Key]
        assert VersionId == item["version"]
        return {"ContentLength": len(item["body"]) + int(self.bad_head),
                "VersionId": item["version"], "Metadata": {"sha256": item["sha256"]}}

    def get_object(self, *, Bucket, Key, VersionId):
        assert Key != "v2/production.tif", "Production raster must never be downloaded"
        item = self.objects[Key]
        assert VersionId == item["version"]
        self.gets.append(Key)
        stream = io.BytesIO(b"corrupt" if self.corrupt_get else item["body"])
        self.streams.append(stream)
        return {"Body": stream}


def fixture():
    client = FakeClient()
    client.add("v2/production.tif", b"123456789", "a" * 64, "original")
    refs = [{"key": "v2/production.tif", "bytes": 9, "sha256": "a" * 64, "version_id": "original"}]
    audit = {"read_only": True, "raster_payloads_read": 0, "verified_raster_objects": 1,
             "verified_raster_bytes": 9, "checked_identities": refs,
             "inventory_current_objects": 1, "inventory_current_bytes": 9,
             "time_utc": "2026-11-10T00:00:00+00:00", "manifest_bytes_read": 0}
    payloads = [{"path": "evidence.json", "body": json.dumps({"audit": audit}).encode()},
                {"path": "report.md", "body": b"approved snapshot"}]
    total = sum(len(p["body"]) for p in payloads)
    policy = {"contract_version": "3.7.0", "destination_prefix": "v2/archive/",
              "manifest_key": "v2/completion.json", "expected_file_count": 2,
              "expected_payload_bytes": total, "maximum_manifest_bytes": 65536,
              "maximum_new_bytes": total + 65536, "expected_raster_objects": 1,
              "expected_raster_bytes": 9, "expected_existing_references": 1,
              "snapshot_audit_path": "evidence.json",
              "payloads": [{"path": p["path"], "bytes": len(p["body"]),
                            "sha256": hashlib.sha256(p["body"]).hexdigest()} for p in payloads]}
    return client, dict(bucket="bucket", root="v2/", payloads=payloads, policy=policy, audit=audit)


def test_manifest_last_exact_readbacks_and_originals_preserved():
    client, args = fixture()
    original = deepcopy(client.objects["v2/production.tif"])
    states = []
    result = publish_archive(client, **args, checkpoint=lambda state: states.append(deepcopy(state)))
    assert client.puts == ["v2/archive/evidence.json", "v2/archive/report.md", "v2/completion.json"]
    assert result["new_object_count"] == 3 and result["namespace_current_objects"] == 4
    assert result["new_bytes"] == sum(len(client.objects[k]["body"]) for k in client.puts)
    assert result["phase3_gate"] == "pending"
    assert client.objects["v2/production.tif"] == original
    assert len(client.gets) == 3 and all(s.closed for s in client.streams)
    record = json.loads(client.objects["v2/completion.json"]["body"])
    assert record["status"] == "archive_complete" and len(record["archived_snapshots"]) == 2
    assert record["existing_objects"] == args["audit"]["checked_identities"]
    assert states[-1]["status"] == "complete"


@pytest.mark.parametrize("kind", ["history", "marker", "manifest_collision"])
def test_later_page_collisions_halt_before_any_put(kind):
    client, args = fixture()
    key = args["policy"]["manifest_key"] if kind == "manifest_collision" else "v2/archive/report.md"
    if kind == "marker":
        client.markers.append({"Key": key, "VersionId": "deleted"})
    else:
        client.history.append({"Key": key, "VersionId": "old", "IsLatest": False, "Size": 1})
    with pytest.raises(FileExistsError):
        publish_archive(client, **args)
    assert client.puts == []


@pytest.mark.parametrize("kind", ["changed_body", "missing_file", "extra_file", "duplicate_file", "byte_budget"])
def test_approved_file_set_or_source_drift_refused_before_put(kind):
    client, args = fixture()
    if kind == "changed_body":
        args["payloads"][1]["body"] = b"changed"
    elif kind == "missing_file":
        args["payloads"].pop()
    elif kind == "extra_file":
        args["payloads"].append({"path": "unapproved.md", "body": b"extra"})
    elif kind == "duplicate_file":
        args["payloads"][1] = deepcopy(args["payloads"][0])
    else:
        args["policy"]["maximum_new_bytes"] = 1
    with pytest.raises(ValueError):
        publish_archive(client, **args)
    assert client.puts == []


@pytest.mark.parametrize("failure", ["fail_put", "corrupt_get", "bad_head", "no_version"])
def test_ambiguous_or_invalid_first_upload_never_retried_or_cleaned_up(failure):
    client, args = fixture()
    setattr(client, failure, True)
    states = []
    with pytest.raises(ArchivePublicationError, match="Archive stopped"):
        publish_archive(client, **args, checkpoint=states.append)
    assert len(client.puts) == 1
    assert client.puts[0] in client.objects
    assert "v2/completion.json" not in client.objects
    assert states[-1]["status"] == "failed"
    assert states[-1]["attempted_key"] == client.puts[0]
    assert all(s.closed for s in client.streams)


def test_failed_second_upload_preserves_first_and_does_not_publish_marker():
    client, args = fixture()
    def checkpoint(state):
        if len(state["verified_objects"]) == 1:
            client.fail_put = True
    with pytest.raises(ArchivePublicationError, match="preserved 1 verified"):
        publish_archive(client, **args, checkpoint=checkpoint)
    assert len(client.puts) == 2 and len(client.objects) == 3
    assert "v2/completion.json" not in client.objects


def test_existing_reference_version_drift_refused():
    client, args = fixture()
    args["audit"]["checked_identities"][0]["version_id"] = "changed"
    with pytest.raises(ValueError, match="changed since"):
        publish_archive(client, **args)
    assert not client.puts


def test_manifest_byte_cap_halts_without_completion_marker():
    client, args = fixture()
    args["policy"]["maximum_manifest_bytes"] = 1
    with pytest.raises(ArchivePublicationError, match="manifest exceeds"):
        publish_archive(client, **args)
    assert len(client.puts) == 2 and "v2/completion.json" not in client.objects


def test_loader_copies_only_approved_files_without_modification(tmp_path):
    client, args = fixture()
    for p in args["payloads"]:
        (tmp_path / p["path"]).write_bytes(p["body"])
    (tmp_path / ".env").write_text("never upload")
    actual = load_approved_payloads(tmp_path, args["policy"])
    assert actual == args["payloads"]
    assert (tmp_path / ".env").read_text() == "never upload"


@pytest.mark.parametrize("op", ["DeleteObject", "DeleteObjects", "CopyObject", "CreateMultipartUpload"])
def test_publication_api_guard_rejects_destructive_or_unapproved_operations(op):
    with pytest.raises(RuntimeError, match="refused API operation"):
        reject_non_archive_api(SimpleNamespace(name=op))


def test_publication_api_guard_allows_ordinary_put():
    reject_non_archive_api(SimpleNamespace(name="PutObject"))


def test_approved_publication_configuration_is_exact_and_bounded():
    policy = load_config("archive_publication")
    assert len(policy["payloads"]) == policy["expected_file_count"] == 16
    assert sum(p["bytes"] for p in policy["payloads"]) == policy["expected_payload_bytes"] == 122487
    assert policy["expected_payload_bytes"] + policy["maximum_manifest_bytes"] == policy["maximum_new_bytes"] == 188023
    assert len({p["path"] for p in policy["payloads"]}) == 16
    assert all(".env" not in p["path"] for p in policy["payloads"])
