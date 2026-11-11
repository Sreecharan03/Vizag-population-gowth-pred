"""Pinned boundary restore and bounded, fail-closed grid publication."""
from __future__ import annotations

import hashlib
import json

from src.storage.archive_publish import exact_versions, require_new_keys, _put_and_verify


MANIFEST = "analysis_grid_manifest.contract-4.1.0.json"


def verify_source_identity(client, bucket, source):
    versions = exact_versions(client, bucket, source["key"])
    if (len(versions) != 1 or not versions[0].get("IsLatest")
            or versions[0].get("VersionId") != source["version_id"]
            or int(versions[0].get("Size", -1)) != source["bytes"]):
        raise RuntimeError("Grid source version/history differs from approved boundary")
    head = client.head_object(Bucket=bucket, Key=source["key"], VersionId=source["version_id"])
    if (head.get("VersionId") != source["version_id"] or head["ContentLength"] != source["bytes"]
            or head.get("Metadata", {}).get("sha256") not in (None, source["sha256"])):
        raise RuntimeError("Grid source metadata differs from approved boundary")


def restore_boundary(client, bucket, source, destination):
    verify_source_identity(client, bucket, source)
    response = client.get_object(Bucket=bucket, Key=source["key"], VersionId=source["version_id"])
    stream = response["Body"]
    try:
        body = stream.read(source["bytes"]+1)
    finally:
        stream.close()
    if len(body) != source["bytes"] or hashlib.sha256(body).hexdigest() != source["sha256"]:
        raise RuntimeError("Grid source byte count/SHA-256 differs from approved boundary")
    with destination.open("xb") as output:
        output.write(body)
    return body


def check_payloads(blobs, config, *, with_manifest):
    expected = set(config["outputs"])
    if not with_manifest:
        expected.remove(MANIFEST)
    if set(blobs) != expected or set(config["outputs"]) != set(config["file_caps"]):
        raise ValueError("Grid payload set differs from the approved four outputs")
    if len(set(config["outputs"].values())) != 4:
        raise ValueError("Grid destination keys must be unique")
    for name, body in blobs.items():
        if not isinstance(body, bytes) or not 0 < len(body) <= config["file_caps"][name]:
            raise ValueError("Grid output exceeds its per-file byte cap")
    reserve = 0 if with_manifest else config["file_caps"][MANIFEST]
    total = sum(map(len, blobs.values())) + reserve
    # Include a bounded local receipt in addition to storage/readback/local payloads.
    if (total > config["maximum_new_bytes"]
            or 3*total+config["file_caps"]["grid_validation.json"] > config["maximum_output_transfer_bytes"]):
        raise ValueError("Grid combined output budget exceeded")
    return sum(map(len, blobs.values()))


def publish_grid(client, *, bucket, config, blobs, checkpoint):
    """Caller owns a persistent reservation; no retries or destructive cleanup."""
    check_payloads(blobs, config, with_manifest=False)
    if any(not key.startswith("vizag-geoai/v2/") for key in config["outputs"].values()):
        raise ValueError("Grid destination outside approved v2 namespace")
    require_new_keys(client, bucket, list(config["outputs"].values()))
    verify_source_identity(client, bucket, config["source"])
    verified = []
    for name, body in blobs.items():
        key = config["outputs"][name]
        checkpoint({"status": "publishing", "attempted_key": key, "outputs": list(verified)})
        record = _put_and_verify(client, bucket, key, body, config["contract_version"])
        verified.append({"name": name, **record})
        checkpoint({"status": "artifact_verified", "outputs": list(verified)})
    verify_source_identity(client, bucket, config["source"])
    record = {"contract_version": config["contract_version"], "part": "4.1",
              "status": "validated_grid_pending_user_review", "source_boundary": config["source"],
              "outputs": verified, "geometry_only": True, "source_unchanged": True,
              "existing_outputs_overwritten": False, "input_bytes": config["source"]["bytes"],
              "metric_crs": config["metric_crs"], "anchor_m": config["anchor_m"]}
    manifest_body = (json.dumps(record, sort_keys=True, separators=(",", ":"))+"\n").encode()
    all_blobs = {**blobs, MANIFEST: manifest_body}
    total = check_payloads(all_blobs, config, with_manifest=True)
    checkpoint({"status": "publishing_manifest", "attempted_key": config["outputs"][MANIFEST],
                "outputs": list(verified)})
    manifest = _put_and_verify(client, bucket, config["outputs"][MANIFEST],
                               manifest_body, config["contract_version"])
    verified.append({"name": MANIFEST, **manifest})
    verify_source_identity(client, bucket, config["source"])
    for item in verified:
        vv = exact_versions(client, bucket, item["key"])
        if (len(vv) != 1 or vv[0].get("VersionId") != item["version_id"]
                or not vv[0].get("IsLatest")):
            raise RuntimeError("Grid publication version identity drift")
    result = {"status": "validated_grid_pending_user_review", "part": "4.1",
              "outputs": verified, "new_output_bytes": total, "output_payload_bytes": 3*total,
              "boundary_input_bytes": config["source"]["bytes"], "source_unchanged": True,
              "part4_2_started": False}
    checkpoint({"status": "complete", "result": result})
    return result, all_blobs
