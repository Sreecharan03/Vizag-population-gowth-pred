"""Part 4.3a metadata-only source and temporal-suitability preflight."""
from __future__ import annotations

from datetime import date

from src.storage.archive_publish import exact_versions


def pin_metadata(client, bucket: str, spec: dict) -> dict:
    """Pin one exact current object without opening its payload."""
    versions = exact_versions(client, bucket, spec["key"])
    if len(versions) != 1 or not versions[0].get("IsLatest"):
        raise RuntimeError(f"Source has ambiguous version history: {spec['key']}")
    version = versions[0]
    if int(version.get("Size", -1)) != int(spec["expected_bytes"]):
        raise RuntimeError(f"Source size differs from approved inventory: {spec['key']}")
    version_id = version.get("VersionId")
    head = client.head_object(Bucket=bucket, Key=spec["key"], VersionId=version_id)
    if (head.get("VersionId") != version_id
            or int(head.get("ContentLength", -1)) != int(spec["expected_bytes"])):
        raise RuntimeError(f"Source HEAD identity mismatch: {spec['key']}")
    last_modified = head.get("LastModified")
    return {
        "key": spec["key"],
        "bytes": int(spec["expected_bytes"]),
        "version_id": version_id,
        "etag": head.get("ETag", "").strip('"') or None,
        "last_modified": last_modified.isoformat() if last_modified else None,
        "sha256_metadata": head.get("Metadata", {}).get("sha256"),
        "payload_validation_required": True,
    }


def temporal_assessment(config: dict) -> dict:
    epochs = [int(value) for value in config["feature_epochs"]]
    worldpop_years = [int(item["year"]) for item in config["worldpop"]]
    if worldpop_years != epochs or len(set(worldpop_years)) != len(epochs):
        raise RuntimeError("WorldPop years must match the four feature epochs exactly")
    osm_date = date.fromisoformat(config["osm_acquisition_date"])
    future_epochs = [epoch for epoch in epochs if osm_date.year > epoch]
    return {
        "worldpop": {
            "status": "year_matched_payload_provenance_pending",
            "allowed_mapping": {str(epoch): epoch for epoch in epochs},
            "growth_rule": "only already-elapsed intervals; assertion required in Part 4.4",
        },
        "osm": {
            "snapshot_date": osm_date.isoformat(),
            "status": "blocked_for_historical_training_without_historical_snapshots",
            "future_relative_to_epochs": future_epochs,
            "may_aggregate_as_dated_context_evidence": True,
            "may_use_as_2018_2024_predictor": False,
        },
    }


def build_report(config: dict, records: list[dict], remote_python: str) -> dict:
    if len(records) != int(config["maximum_objects"]):
        raise RuntimeError("Part 4.3a object count differs from the approved bound")
    keys = [item["key"] for item in records]
    if len(set(keys)) != len(keys):
        raise RuntimeError("Part 4.3a source keys are not unique")
    assessment = temporal_assessment(config)
    return {
        "status": "preflight_complete_payload_and_temporal_gates_pending",
        "part": "4.3a",
        "contract_version": config["contract_version"],
        "remote_python": remote_python,
        "metadata_only": True,
        "payload_bytes_read": 0,
        "b2_writes": 0,
        "object_count": len(records),
        "known_payload_bytes": sum(item["bytes"] for item in records),
        "sources": records,
        "temporal_assessment": assessment,
        "aggregation_started": False,
    }


def render_markdown(report: dict) -> bytes:
    lines = [
        "# Part 4.3a context-source preflight", "",
        f"Status: **{report['status']}**.", "",
        f"- Modal Python: `{report['remote_python']}`",
        f"- Exact objects pinned: {report['object_count']}",
        f"- Known later payload: {report['known_payload_bytes']:,} bytes",
        "- Payload bytes read: 0", "- B2 writes: 0", "- Aggregation started: no", "",
        "## Exact current objects", "",
    ]
    for item in report["sources"]:
        lines.append(
            f"- `{item['key']}` — {item['bytes']:,} bytes, version `{item['version_id']}`, "
            f"SHA-256 metadata: {'present' if item['sha256_metadata'] else 'absent'}"
        )
    osm = report["temporal_assessment"]["osm"]
    lines += ["", "## Temporal gate", "",
              "WorldPop years match the four feature epochs, but payload/schema/provenance validation is still required.",
              f"The OSM extract is dated {osm['snapshot_date']} and is later than every feature epoch.",
              "It may be aggregated as explicitly dated context evidence, but it must not enter historical training rows",
              "unless suitable historical OSM snapshots are obtained and validated. Part 4.4 must enforce this in code.", ""]
    return "\n".join(lines).encode()
