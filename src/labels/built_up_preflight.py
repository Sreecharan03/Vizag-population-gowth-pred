"""Read-only Part 5.1 source-identity preflight."""
from __future__ import annotations

from src.storage.archive_publish import exact_versions


def approved_index_sources(gate_config: dict, config: dict) -> list[dict]:
    wanted_epochs = set(config["epochs"])
    wanted_roles = set(config["roles"])
    rows = [item for item in gate_config["sources"]
            if item.get("epoch") in wanted_epochs and item.get("role") in wanted_roles]
    identities = {(int(item["epoch"]), item["role"]): item for item in rows}
    expected = {(epoch, role) for epoch in wanted_epochs for role in wanted_roles}
    if set(identities) != expected or len(rows) != len(expected):
        raise RuntimeError("Part 5.1 requires exactly five approved indices for every epoch")
    for item in rows:
        if not all(item.get(name) for name in ("key", "version_id", "sha256")) or item["bytes"] <= 0:
            raise RuntimeError("Part 5.1 index identity is incomplete")
    return sorted(rows, key=lambda item: (item["epoch"], item["role"]))


def pin_worldcover(client, bucket: str, spec: dict) -> dict:
    versions = exact_versions(client, bucket, spec["key"])
    if len(versions) != 1 or not versions[0].get("IsLatest"):
        raise RuntimeError("WorldCover must have exactly one current object version")
    item = versions[0]
    if int(item.get("Size", -1)) != int(spec["expected_bytes"]):
        raise RuntimeError("WorldCover size differs from the verified Phase 2 acquisition")
    head = client.head_object(Bucket=bucket, Key=spec["key"], VersionId=item["VersionId"])
    if int(head.get("ContentLength", -1)) != int(spec["expected_bytes"]):
        raise RuntimeError("WorldCover HEAD identity mismatch")
    return {"key": spec["key"], "bytes": spec["expected_bytes"],
            "version_id": item["VersionId"], "etag": head.get("ETag", "").strip('"'),
            "sha256_metadata": head.get("Metadata", {}).get("sha256"),
            "product_year": spec["product_year"], "product_version": spec["product_version"]}


def build_preflight_report(config: dict, indices: list[dict], worldcover: dict) -> dict:
    if config.get("production_writes_allowed") is not False:
        raise RuntimeError("Part 5.1 preflight must prohibit production writes")
    return {"status": "source_identity_preflight_passed_header_pilot_pending",
            "part": "5.1", "contract_version": config["contract_version"],
            "b2_writes": 0, "pixel_reads": 0, "index_count": len(indices),
            "index_bytes": sum(item["bytes"] for item in indices),
            "worldcover": worldcover, "crosscheck_epochs": config["crosscheck_epochs"],
            "temporal_interpretation": "2021 WorldCover cross-checks bracketing 2020 and 2022 classifications; it is not two dated references",
            "next_gate": "Modal raster-header and bounded pixel pilot; no production classification"}
