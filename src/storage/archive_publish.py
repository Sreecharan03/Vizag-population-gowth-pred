"""Small, explicitly allowlisted archive publication; never mutates old objects."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath


class ArchivePublicationError(RuntimeError):
    """A partial archive is preserved; callers must not blindly retry."""


def reject_non_archive_api(model, **kwargs):
    if model.name not in {"ListObjectsV2", "ListObjectVersions", "HeadObject", "GetObject", "PutObject"}:
        raise RuntimeError(f"Archive publisher refused API operation: {model.name}")


def load_approved_payloads(repo_root, policy):
    root = Path(repo_root).resolve()
    payloads = []
    for spec in policy["payloads"]:
        relative = PurePosixPath(spec["path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in spec["path"]:
            raise ValueError("Unsafe archive source path")
        source = (root / relative).resolve()
        if not source.is_relative_to(root):
            raise ValueError("Archive source escapes repository")
        payloads.append({"path": spec["path"], "body": source.read_bytes()})
    validate_payloads(payloads, policy)
    return payloads


def validate_payloads(payloads, policy):
    specs = {spec["path"]: spec for spec in policy["payloads"]}
    if (len(specs) != policy["expected_file_count"] or len(payloads) != len(specs)
            or {p["path"] for p in payloads} != set(specs)):
        raise ValueError("Archive must contain the exact approved file set")
    for payload in payloads:
        body, spec = payload["body"], specs[payload["path"]]
        if (not isinstance(body, bytes) or len(body) != spec["bytes"]
                or hashlib.sha256(body).hexdigest() != spec["sha256"]):
            raise ValueError(f"Approved archive source drift: {payload['path']}")
        path = PurePosixPath(payload["path"])
        if path.is_absolute() or ".." in path.parts or "\\" in payload["path"]:
            raise ValueError("Unsafe archive payload path")
    total = sum(len(p["body"]) for p in payloads)
    if total != policy["expected_payload_bytes"] or total + policy["maximum_manifest_bytes"] > policy["maximum_new_bytes"]:
        raise ValueError("Archive payload exceeds the approved byte budget")
    return total


def exact_versions(client, bucket, key):
    return [item for page in client.get_paginator("list_object_versions").paginate(Bucket=bucket, Prefix=key)
            for group in ("Versions", "DeleteMarkers") for item in page.get(group, [])
            if item.get("Key") == key]


def require_new_keys(client, bucket, keys):
    for key in keys:
        if exact_versions(client, bucket, key):
            raise FileExistsError(f"Archive destination has a current/historical version: {key}")


def validate_existing_evidence(audit, payloads, policy):
    if (not audit.get("read_only") or audit.get("raster_payloads_read") != 0
            or audit["verified_raster_objects"] != policy["expected_raster_objects"]
            or audit["verified_raster_bytes"] != policy["expected_raster_bytes"]
            or len(audit["checked_identities"]) != policy["expected_existing_references"]):
        raise ValueError("Fresh audit does not cover the approved production archive")
    body = next(p["body"] for p in payloads if p["path"] == policy["snapshot_audit_path"])
    saved = json.loads(body)["audit"]
    fields = ("key", "bytes", "sha256", "version_id")
    identity = lambda rows: sorted(tuple(r.get(k) for k in fields) for r in rows)
    if identity(saved["checked_identities"]) != identity(audit["checked_identities"]):
        raise ValueError("Production identities changed since the approved audit snapshot")
    if len({i["key"] for i in audit["checked_identities"]}) != policy["expected_existing_references"]:
        raise ValueError("Duplicate existing archive references")


def _put_and_verify(client, bucket, key, body, contract):
    require_new_keys(client, bucket, [key])
    digest = hashlib.sha256(body).hexdigest()
    response = client.put_object(
        Bucket=bucket, Key=key, Body=body,
        Metadata={"sha256": digest, "contract-version": contract},
        ContentType=("application/geo+json" if key.endswith(".geojson") else
                     "image/png" if key.endswith(".png") else
                     "text/csv; charset=utf-8" if key.endswith(".csv") else
                     "application/json" if key.endswith(".json") else
                     "text/markdown; charset=utf-8" if key.endswith(".md") else "text/yaml; charset=utf-8"),
    )
    version = response.get("VersionId")
    if not version:
        raise RuntimeError(f"Archive PUT did not return a version: {key}")
    head = client.head_object(Bucket=bucket, Key=key, VersionId=version)
    if (head.get("VersionId") != version or int(head["ContentLength"]) != len(body)
            or head.get("Metadata", {}).get("sha256") != digest):
        raise RuntimeError(f"Archive uploaded identity mismatch: {key}")
    stream = client.get_object(Bucket=bucket, Key=key, VersionId=version)["Body"]
    try:
        readback = stream.read(len(body) + 1)
    finally:
        stream.close()
    if readback != body or hashlib.sha256(readback).hexdigest() != digest:
        raise RuntimeError(f"Archive read-back mismatch: {key}")
    versions = exact_versions(client, bucket, key)
    if (len(versions) != 1 or versions[0].get("VersionId") != version
            or not versions[0].get("IsLatest") or int(versions[0].get("Size", -1)) != len(body)):
        raise RuntimeError(f"Archive version history changed after PUT: {key}")
    return {"key": key, "bytes": len(body), "sha256": digest, "version_id": version,
            "exact_version_readback_verified": True}


def publish_archive(client, *, bucket, root, payloads, policy, audit, checkpoint=None):
    """Publish approved payloads once, then the completion manifest last.

    Caller holds the cooperative namespace reservation and disables all automatic
    retries. Existing objects are never changed. An ambiguous PUT is propagated
    without reconciliation writes; confirmed objects and the attempted key are
    retained in the caller's progress ledger for an explicitly approved resume.
    """
    validate_payloads(payloads, policy)
    validate_existing_evidence(audit, payloads, policy)
    prefix, manifest_key = policy["destination_prefix"], policy["manifest_key"]
    keys = [prefix + p["path"] for p in payloads] + [manifest_key]
    if len(set(keys)) != len(keys) or any(not k.startswith(root) for k in keys):
        raise ValueError("Archive destinations are not unique approved-namespace keys")
    require_new_keys(client, bucket, keys)
    verified, attempted = [], None

    def progress(status):
        if checkpoint:
            checkpoint({"status": status, "attempted_key": attempted,
                        "verified_objects": list(verified)})

    try:
        for payload in payloads:
            attempted = prefix + payload["path"]
            progress("publishing")
            item = _put_and_verify(client, bucket, attempted, payload["body"], policy["contract_version"])
            verified.append({"source_path": payload["path"], **item})
            progress("verified_payload")
        record = {
            "schema_version": 1, "contract_version": policy["contract_version"],
            "part": "3.7", "status": "archive_complete", "phase3_gate": "pending_user_visual_scientific_review",
            "created_utc": datetime.now(timezone.utc).isoformat(), "bucket": bucket,
            "source_audit_utc": audit["time_utc"],
            "existing_objects": audit["checked_identities"], "archived_snapshots": verified,
            "production_raster_objects": audit["verified_raster_objects"],
            "production_raster_bytes": audit["verified_raster_bytes"],
            "snapshot_payload_bytes": policy["expected_payload_bytes"],
            "eviction": "not_required_no_local_scene_stacks; no deletion performed",
            "limitations": [
                "Raster payload hashes were not recomputed during Part 3.7.",
                "64 scene stacks have hash references in the verified extraction manifest, not SHA metadata.",
                "This is B2 persistence, not an independent second offsite replica.",
                "Archived reports are historical snapshots; their pending-publication text is superseded by this record.",
                "2018 extreme and slight 2022 index outliers remain pending scientific review before aggregation.",
            ],
        }
        body = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if (len(body) > policy["maximum_manifest_bytes"]
                or len(body) + policy["expected_payload_bytes"] > policy["maximum_new_bytes"]):
            raise RuntimeError("Completion manifest exceeds approved byte budget")
        attempted = manifest_key
        progress("publishing_completion_manifest")
        manifest = _put_and_verify(client, bucket, manifest_key, body, policy["contract_version"])
        verified.append(manifest)
        progress("manifest_verified")

        inventory, histories, markers = {}, {}, []
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=root):
            inventory.update({i["Key"]: int(i["Size"]) for i in page.get("Contents", [])})
        for page in client.get_paginator("list_object_versions").paginate(Bucket=bucket, Prefix=root):
            for item in page.get("Versions", []):
                histories.setdefault(item["Key"], []).append(item)
            markers.extend(page.get("DeleteMarkers", []))
        added = sum(i["bytes"] for i in verified)
        if (len(inventory) != audit["inventory_current_objects"] + len(verified)
                or sum(inventory.values()) != audit["inventory_current_bytes"] + added):
            raise RuntimeError("Post-publication namespace counts/bytes changed unexpectedly")
        for item in audit["checked_identities"] + verified:
            vv = histories.get(item["key"], [])
            if (inventory.get(item["key"]) != item["bytes"] or len(vv) != 1
                    or vv[0].get("VersionId") != item["version_id"]
                    or not vv[0].get("IsLatest") or any(m["Key"] == item["key"] for m in markers)):
                raise RuntimeError(f"Post-publication identity drift: {item['key']}")
        result = {
            "status": "complete", "part": "3.7", "phase3_gate": "pending",
            "manifest": manifest, "archived_snapshots": verified[:-1],
            "new_object_count": len(verified), "new_bytes": added,
            "production_raster_objects": audit["verified_raster_objects"],
            "production_raster_bytes": audit["verified_raster_bytes"],
            "namespace_current_objects": len(inventory), "namespace_current_bytes": sum(inventory.values()),
            "namespace_versions": sum(len(vv) for vv in histories.values()),
            "namespace_delete_markers": len(markers), "raster_payload_bytes_read": 0,
            "existing_manifest_bytes_read": audit["manifest_bytes_read"],
            "eviction": "not_required; nothing deleted", "production_identities_unchanged": True,
        }
        progress("complete")
        return result
    except Exception as exc:
        progress("failed")
        raise ArchivePublicationError(
            f"Archive stopped; preserved {len(verified)} verified new objects. "
            f"Attempted key (outcome may be ambiguous): {attempted}. {type(exc).__name__}: {exc}"
        ) from exc
