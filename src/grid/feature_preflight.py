"""Part 4.2a metadata-only source pinning; never reads raster payloads."""
from __future__ import annotations

import hashlib
import json

from src.storage.archive_publish import exact_versions


def read_pinned_small(client, bucket, spec):
    versions = exact_versions(client, bucket, spec["key"])
    if (len(versions) != 1 or not versions[0].get("IsLatest")
            or versions[0].get("VersionId") != spec["version_id"]
            or int(versions[0].get("Size", -1)) != spec["bytes"]):
        raise RuntimeError(f"Pinned small source identity/history changed: {spec['key']}")
    response = client.get_object(Bucket=bucket, Key=spec["key"], VersionId=spec["version_id"])
    stream = response["Body"]
    try:
        body = stream.read(spec["bytes"]+1)
    finally:
        stream.close()
    if len(body) != spec["bytes"] or hashlib.sha256(body).hexdigest() != spec["sha256"]:
        raise RuntimeError(f"Pinned small source bytes/hash changed: {spec['key']}")
    return body


def pin_dem_metadata(client, bucket, specs):
    records = []
    for spec in specs:
        versions = exact_versions(client, bucket, spec["key"])
        if (len(versions) != 1 or not versions[0].get("IsLatest")
                or int(versions[0].get("Size", -1)) != spec["expected_bytes"]):
            raise RuntimeError(f"DEM identity/history/size mismatch: {spec['key']}")
        version = versions[0]["VersionId"]
        head = client.head_object(Bucket=bucket, Key=spec["key"], VersionId=version)
        metadata = head.get("Metadata", {})
        etag = head.get("ETag", "").strip('"') or None
        sha256 = metadata.get("sha256")
        if (head.get("VersionId") != version or int(head["ContentLength"]) != spec["expected_bytes"]):
            raise RuntimeError(f"DEM HEAD identity mismatch: {spec['key']}")
        records.append({"key": spec["key"], "bytes": spec["expected_bytes"],
                        "version_id": version, "etag": etag, "sha256_metadata": sha256,
                        "payload_hash_required": not bool(sha256)})
    return records


def validate_manifests(grid_body, index_body, expected_indices):
    grid = json.loads(grid_body)
    if (grid.get("contract_version") != "4.1.0"
            or grid.get("status") != "validated_grid_pending_user_review"
            or grid.get("geometry_only") is not True):
        raise RuntimeError("Part 4.1 manifest contract/status mismatch")
    grid_outputs = {item["name"]: item for item in grid.get("outputs", [])}
    grid_item = grid_outputs.get("analysis_grid.geojson")
    if not grid_item or grid_item.get("bytes") != 2816012:
        raise RuntimeError("Part 4.1 grid identity missing from manifest")
    manifest_rows = [json.loads(line) for line in index_body.decode().splitlines() if line.strip()]
    rows = []
    for manifest_row in manifest_rows:
        epoch = int(manifest_row.get("epoch", -1))
        outputs = manifest_row.get("outputs", {})
        for role, output in outputs.items():
            rows.append({"epoch": epoch, "role": role, **output})
    identities = {(item["epoch"], item["role"]): item for item in expected_indices}
    if len(manifest_rows) != 4 or len(rows) != 20 or len(identities) != 20:
        raise RuntimeError("Expected exactly four epochs and 20 index identities")
    for row in rows:
        key = (row["epoch"], row["role"])
        expected = identities.get(key)
        if expected is None or any(row.get(field) != expected[field]
                                   for field in ("key", "bytes", "sha256", "version_id")):
            raise RuntimeError("Index manifest differs from approved Phase 3 identities")
    return grid_item, rows


def build_report(config, grid_item, index_rows, dem_records, remote_python):
    payload_bytes = sum(config[name]["bytes"] for name in ("grid_manifest", "index_manifest", "boundary"))
    if payload_bytes > config["maximum_payload_bytes"]:
        raise RuntimeError("Part 4.2a payload budget exceeded")
    index_bytes = sum(row["bytes"] for row in index_rows)
    dem_bytes = sum(item["bytes"] for item in dem_records)
    needs_hash = [item["key"] for item in dem_records if item["payload_hash_required"]]
    return {
        "status": ("preflight_complete_dem_payload_hash_required" if needs_hash
                   else "preflight_complete_sources_fully_pinned"),
        "part": "4.2a", "contract_version": config["contract_version"],
        "remote_python": remote_python, "metadata_only": True,
        "raster_payload_bytes_read": 0, "small_payload_bytes_read": payload_bytes,
        "b2_writes": 0, "grid": grid_item, "index_count": len(index_rows),
        "index_bytes": index_bytes, "dem_sources": dem_records, "dem_bytes": dem_bytes,
        "known_aggregation_input_bytes": index_bytes+dem_bytes+grid_item["bytes"]+config["boundary"]["bytes"],
        "dem_payload_hash_required": needs_hash,
        "schema_validation_status": "deferred_to_separately_approved_header_or_payload_read",
        "part4_2b_started": False,
    }


def render_markdown(report):
    lines = ["# Part 4.2a source preflight", "", f"Status: **{report['status']}**.", "",
             f"- Modal Python: `{report['remote_python']}`",
             f"- Small verified payload read: {report['small_payload_bytes_read']:,} bytes",
             "- Raster payload/pixel reads: 0 bytes", "- B2 writes: 0",
             f"- Index sources: {report['index_count']} ({report['index_bytes']:,} bytes)",
             f"- DEM sources: {len(report['dem_sources'])} ({report['dem_bytes']:,} bytes)",
             f"- Known aggregation input: {report['known_aggregation_input_bytes']:,} bytes", "",
             "## DEM identities", ""]
    for item in report["dem_sources"]:
        lines.append(f"- `{item['key']}` — {item['bytes']:,} bytes, version `{item['version_id']}`, "
                     f"payload SHA-256 metadata: {'present' if item['sha256_metadata'] else 'absent'}")
    lines += ["", "## Gate", ""]
    if report["dem_payload_hash_required"]:
        lines += ["The legacy Phase 2 DEM uploads do not carry SHA-256 object metadata.",
                  "A separately approved, version-pinned DEM payload read/hash and raster-header",
                  "validation is required before aggregation. Part 4.2b has not started."]
    else:
        lines += ["All source identities include SHA-256 metadata. Raster schema/header validation",
                  "still requires a separately approved bounded read before aggregation."]
    lines.append("")
    return "\n".join(lines).encode()
