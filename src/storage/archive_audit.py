"""Read-only archive identity audit; never downloads raster payloads."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json


READ_OPERATIONS = frozenset({
    "ListObjectsV2", "ListObjectVersions", "HeadObject", "GetObject",
})


def reject_non_read_api(model, **kwargs):
    """Botocore before-call hook: fail before any non-read request is sent."""
    if model.name not in READ_OPERATIONS:
        raise RuntimeError(f"Read-only audit refused API operation: {model.name}")


def audit_archive(client, *, bucket, root, manifest_specs, composite_specs,
                  expected_epochs, index_names, expected_scene_count,
                  manifest_read_limit_bytes, include_manifest_rows=False):
    """Compare current B2 identities with pinned manifests and prior audit hashes.

    The only GETs are the two caller-pinned small JSONL manifests. Raster hashes
    are checked against stored metadata, not recomputed from their payloads.
    Missing objects, changed identities, historical duplicates and delete markers
    halt immediately. Unreferenced objects are reported, never removed.
    """
    if len(manifest_specs) != 2:
        raise ValueError("Expected extraction and index manifest specifications")
    requests = Counter()
    inventory, versions, markers = {}, defaultdict(list), defaultdict(list)
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=root):
        requests["list_objects_v2_pages"] += 1
        for item in page.get("Contents", []):
            inventory[item["Key"]] = {"bytes": int(item["Size"])}
    for page in client.get_paginator("list_object_versions").paginate(Bucket=bucket, Prefix=root):
        requests["list_object_versions_pages"] += 1
        for item in page.get("Versions", []):
            versions[item["Key"]].append(item)
        for item in page.get("DeleteMarkers", []):
            markers[item["Key"]].append(item)

    heads, checked = {}, {}

    def identity(item, *, require_hash):
        key = item["key"]
        if not key.startswith(root):
            raise RuntimeError(f"Reference outside approved namespace: {key}")
        if key not in inventory:
            raise RuntimeError(f"Missing current B2 object: {key}")
        vv = versions[key]
        if len(vv) != 1 or not vv[0].get("IsLatest") or markers[key]:
            raise RuntimeError(f"Unexpected version history: {key}")
        if key not in heads:
            heads[key] = client.head_object(Bucket=bucket, Key=key)
            requests["head_object"] += 1
        head = heads[key]
        size = int(item["bytes"])
        if int(head["ContentLength"]) != size or inventory[key]["bytes"] != size or int(vv[0]["Size"]) != size:
            raise RuntimeError(f"Size drift: {key}")
        version = head.get("VersionId")
        if version != vv[0]["VersionId"] or (item.get("version_id") and version != item["version_id"]):
            raise RuntimeError(f"Version drift: {key}")
        stored_hash = head.get("Metadata", {}).get("sha256")
        if (require_hash or stored_hash) and stored_hash != item.get("sha256"):
            raise RuntimeError(f"SHA-256 metadata drift: {key}")
        checked[key] = {"key": key, "bytes": size, "version_id": version,
                        "sha256": item.get("sha256"),
                        "sha256_metadata_present": bool(stored_hash)}
        return head

    manifests, manifests_read = [], []
    for item in manifest_specs:
        if not 0 < item["bytes"] <= manifest_read_limit_bytes:
            raise RuntimeError("Manifest exceeds approved small-read limit")
        head = identity(item, require_hash=True)
        response = client.get_object(Bucket=bucket, Key=item["key"], VersionId=head["VersionId"])
        requests["get_object"] += 1
        stream = response["Body"]
        try:
            body = stream.read(item["bytes"] + 1)
        finally:
            stream.close()
        if len(body) != item["bytes"] or hashlib.sha256(body).hexdigest() != item["sha256"]:
            raise RuntimeError(f"Manifest bytes/hash mismatch: {item['key']}")
        manifests.append([json.loads(line) for line in body.decode("utf-8").splitlines() if line])
        manifests_read.append({**checked[item["key"]], "payload_sha256_verified": True})

    scenes, epochs = manifests
    epoch_set = set(expected_epochs)
    if (len(scenes) != expected_scene_count
            or len({r["scene_id"] for r in scenes}) != expected_scene_count
            or set(r["epoch"] for r in scenes) != epoch_set
            or len(epochs) != len(epoch_set)
            or set(r["epoch"] for r in epochs) != epoch_set):
        raise RuntimeError("Unexpected manifest scene/epoch membership")
    scene_outputs = []
    for row in scenes:
        if set(row["outputs"]) != {"reflectance", "scl"}:
            raise RuntimeError("Incomplete extraction pair in manifest")
        scene_outputs.extend(row["outputs"].values())
    for item in scene_outputs:
        identity(item, require_hash=False)
    for item in composite_specs:
        identity(item, require_hash=True)
    index_outputs = []
    composite_by_key = {item["key"]: item for item in composite_specs}
    for row in epochs:
        if not row.get("source_sha256_verified") or not row.get("remote_full_resolution_audit"):
            raise RuntimeError("Missing completed index audit evidence")
        if set(row["outputs"]) != set(index_names):
            raise RuntimeError("Incomplete index set in manifest")
        source = row["source"]
        expected_source = composite_by_key.get(source["key"])
        if expected_source is None or any(source[k] != expected_source[k] for k in ("bytes", "sha256")):
            raise RuntimeError("Index source differs from pinned composite")
        identity(source, require_hash=True)
        for item in row["outputs"].values():
            if not item.get("remote_sha256_verified") or not item.get("remote_pixel_audit"):
                raise RuntimeError("Incomplete published index audit flags")
            identity(item, require_hash=True)
            index_outputs.append(item)

    groups = {}
    raster_keys = set()
    for name, items in (("scene_stacks", scene_outputs),
                        ("composites_and_counts", composite_specs),
                        ("indices", index_outputs)):
        keys = {item["key"] for item in items}
        if len(keys) != len(items) or raster_keys.intersection(keys):
            raise RuntimeError("Duplicate output references in manifests")
        raster_keys.update(keys)
        groups[name] = {"objects": len(items), "bytes": sum(i["bytes"] for i in items)}
    namespace_groups = defaultdict(lambda: {"objects": 0, "bytes": 0})
    for key, item in inventory.items():
        suffix = key[len(root):]
        prefix = "/".join(suffix.split("/")[:4]) if suffix.startswith("processed/") else suffix.split("/")[0]
        namespace_groups[prefix]["objects"] += 1
        namespace_groups[prefix]["bytes"] += item["bytes"]
    result = {
        "read_only": True, "time_utc": datetime.now(timezone.utc).isoformat(),
        "bucket": bucket, "root": root,
        "inventory_current_objects": len(inventory),
        "inventory_current_bytes": sum(i["bytes"] for i in inventory.values()),
        "all_version_count": sum(len(vv) for vv in versions.values()),
        "all_version_bytes": sum(i["Size"] for vv in versions.values() for i in vv),
        "delete_markers": sum(len(mm) for mm in markers.values()),
        "verified_groups": groups, "verified_raster_objects": len(raster_keys),
        "verified_raster_bytes": sum(checked[k]["bytes"] for k in raster_keys),
        "manifest_bytes_read": sum(item["bytes"] for item in manifests_read),
        "manifests": manifests_read, "requests": dict(requests),
        "namespace_groups": dict(namespace_groups),
        "other_objects": [{"key": key, **inventory[key], "versions": len(versions[key]),
                           "delete_markers": len(markers[key])}
                          for key in sorted(inventory) if key not in checked],
        "checked_identities": sorted(checked.values(), key=lambda item: item["key"]),
        "raster_payloads_read": 0,
        "raster_hashes_recomputed": False,
        "scene_outputs_without_hash_metadata": sum(not checked[i["key"]]["sha256_metadata_present"] for i in scene_outputs),
    }
    if include_manifest_rows:
        result["manifest_rows"] = manifests
    return result
