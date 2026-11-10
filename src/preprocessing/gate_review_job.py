"""Bounded transfer and publication helpers for the separately approved QC job."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from src.storage.archive_publish import exact_versions, require_new_keys, _put_and_verify


def verify_source_pins(audit, config):
    current = {i["key"]: i for i in audit["checked_identities"]}
    sources = config["sources"]
    if len(sources) != 28 or len({s["key"] for s in sources}) != 28:
        raise ValueError("QC must use exactly 28 unique approved rasters")
    if sum(s["bytes"] for s in sources) != config["expected_raster_bytes"]:
        raise ValueError("QC raster byte budget changed")
    for item in sources:
        other = current.get(item["key"])
        if other is None or any(item[k] != other[k] for k in ("bytes", "sha256", "version_id")):
            raise RuntimeError(f"QC source identity drift: {item['key']}")
    for epoch in (2018, 2020, 2022, 2024):
        if {s["role"] for s in sources if s["epoch"] == epoch} != {
            "composite", "valid_obs_count", "ndvi", "ndbi", "ndwi", "mndwi", "bsi"}:
            raise ValueError("QC epoch source set incomplete")


def output_keys(config):
    manifest_name = Path(config["manifest_key"]).name
    return {name: (config["manifest_key"] if name == manifest_name else config["output_prefix"] + name)
            for name in config["file_caps"]}


def pin_small_object(client, bucket, key, limit, expected_size=None):
    head = client.head_object(Bucket=bucket, Key=key)
    size = int(head["ContentLength"])
    if not 0 < size <= limit or (expected_size is not None and size != expected_size):
        raise RuntimeError(f"Small QC input exceeds approved size: {key}")
    vv = exact_versions(client, bucket, key)
    if len(vv) != 1 or not vv[0].get("IsLatest") or vv[0].get("VersionId") != head.get("VersionId"):
        raise RuntimeError(f"Small QC input has unexpected history: {key}")
    stream = client.get_object(Bucket=bucket, Key=key, VersionId=head["VersionId"])["Body"]
    try:
        body = stream.read(size+1)
    finally:
        stream.close()
    digest = hashlib.sha256(body).hexdigest()
    if len(body) != size or (head.get("Metadata", {}).get("sha256") not in (None, digest)):
        raise RuntimeError(f"Small QC input bytes/hash mismatch: {key}")
    return body, {"key": key, "bytes": size, "version_id": head["VersionId"], "sha256": digest}


def download_pinned(client, bucket, item, destination):
    """One version-pinned streaming GET; create a fresh scratch file only."""
    response = client.get_object(Bucket=bucket, Key=item["key"], VersionId=item["version_id"])
    stream = response["Body"]
    digest, total = hashlib.sha256(), 0
    try:
        with Path(destination).open("xb") as output:
            for block in stream.iter_chunks(chunk_size=4*1024*1024):
                if block:
                    total += len(block)
                    if total > item["bytes"]:
                        raise RuntimeError("Pinned QC raster exceeded expected bytes")
                    digest.update(block)
                    output.write(block)
    finally:
        stream.close()
    if total != item["bytes"] or digest.hexdigest() != item["sha256"]:
        raise RuntimeError(f"Downloaded QC raster hash mismatch: {item['key']}")
    return total


def check_output_budget(blobs, config, *, include_manifest):
    manifest_name = Path(config["manifest_key"]).name
    expected = set(config["file_caps"])
    if not include_manifest:
        expected.remove(manifest_name)
    if set(blobs) != expected:
        raise ValueError("Unexpected QC output file set")
    for name, body in blobs.items():
        if not isinstance(body, bytes) or len(body) > config["file_caps"][name]:
            raise RuntimeError(f"QC output exceeds approved file cap: {name}")
    total = sum(map(len, blobs.values()))
    reserve = 0 if include_manifest else config["file_caps"][manifest_name]
    if (total+reserve > config["maximum_new_output_bytes"]
            or 3*(total+reserve) > config["maximum_output_transfer_bytes"]):
        raise RuntimeError("QC output/readback/local-copy budget exceeded")
    return total


def reports(epochs, *, config, sources, auxiliary, feasibility_text, input_bytes):
    review = {"schema_version": 1, "status": "evidence_generated_review_pending",
        "phase3_gate_approved": False, "eligibility_policy_approved": False,
        "input_bytes": input_bytes, "source_rasters": sources, "auxiliary": auxiliary,
        "epochs": epochs, "feasibility_report": feasibility_text,
        "display_only": {"rgb_min": config["rgb_display_min"], "rgb_max": config["rgb_display_max"],
                         "index_colours_saturate_at": [-1, 1], "overviews_may_be_used_for_previews": True},
        "limitations": ["Samples select the largest absolute values, not a representative sample.",
            "Native outlier counts and maps do not depend on averaged previews.",
            "A matching formula does not establish physical reliability or land-cover accuracy.",
            "No scene-level investigation, reclassification, clipping, rewriting or eligibility decision performed.",
            "Nominal-only means are sensitivity diagnostics, not approved feature values."]}
    fields = ["epoch", "index", "row", "col", "value", "observations", "easting_m", "northing_m",
              "longitude", "latitude", "left_term", "right_term", "denominator", "cancellation_ratio", "bands"]
    csv_text = io.StringIO(newline="")
    writer = csv.DictWriter(csv_text, fieldnames=fields)
    writer.writeheader()
    for epoch in epochs:
        for sample in epoch["samples"]:
            writer.writerow({"epoch": epoch["epoch"], **sample,
                             "bands": json.dumps(sample["bands"], sort_keys=True, separators=(",", ":"))})
    lines = ["# Phase 3 visual/scientific review", "",
             "**Evidence generated; user visual review and downstream eligibility policy remain pending.**", "",
             "## Key — what the panels mean", "",
             "RGB: true-colour reflectance preview. Count: clear observations out of eight.",
             "NDVI: vegetation contrast; NDBI: built-surface contrast; NDWI/MNDWI: water contrast;",
             "BSI: bare-soil contrast. These are continuous signals, not classified land cover or predictions.", "",
             "Grey indicates unavailable display data. RGB uses a common 0–0.30 display stretch.",
             "Index colours saturate at [-1,1] for display only; source values are unchanged.",
             "Previews may use overviews. Counts, formula checks and flagged locations are measured natively.", "",
             "## Measurements", "", "| Year | AOI coverage at >=4 observations | Unique outlier pixels |",
             "|---|---:|---:|"]
    for epoch in epochs:
        lines.append(f"| {epoch['epoch']} | {epoch['coverage_fraction']:.4%} | {epoch['unique_outlier_pixels']:,} |")
    lines += ["", "Outlier sets overlap across indices; the unique count is their pixel-wise union.", "",
              "| Year | Index | Range outliers | Outliers with negative ratio term | Minimum | Maximum | Minimum cancellation ratio |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for epoch in epochs:
        for name, stats in epoch["statistics"].items():
            diagnostic = epoch["diagnostics"][name]
            ratio = diagnostic["cancellation_ratios"]
            ratio_text = f"{ratio['minimum']:.8g}" if ratio else "not applicable"
            lines.append(f"| {epoch['epoch']} | {name.upper()} | {stats['out_of_range_pixels']:,} | "
                         f"{diagnostic['negative_term_outliers']:,} | {stats['minimum']:.6g} | {stats['maximum']:.6g} | {ratio_text} |")
    lines += ["", "## How to interpret the numerical diagnostics", "",
        "Each index is a ratio of a difference to a sum. Its two ratio terms are recorded in the CSV.",
        "For BSI the terms are sums of bands. Opposite-sign terms can yield ratios beyond [-1,1].",
        "Cancellation ratio = abs(left + right) / (abs(left) + abs(right)); smaller values mean",
        "stronger cancellation. It is a continuous diagnostic, not a new accepted/rejected threshold.",
        "Negative corrected reflectance is preserved by the approved contract. This review identifies",
        "its mathematical effects; it does not establish the physical cause in an individual source scene.", "",
        "The JSON includes global means both with all valid values and with range outliers omitted",
        "as a sensitivity diagnostic only. These are not 500 m features and do not authorize exclusion.", "",
        "## Review images", ""]
    for epoch in epochs:
        lines += [f"### {epoch['epoch']}", "", f"![QC {epoch['epoch']}](qc_{epoch['epoch']}.png)", ""]
    lines += ["## Existing epoch-feasibility evidence", "",
              "This is the exact existing report, read from a pinned B2 version; catalogue feasibility",
              "was not recomputed in this review.", ""]
    lines += ["> " + line for line in feasibility_text.splitlines()]
    lines += ["", "## Decision still required", "",
        "Inspect the actual images, count/range tables and sampled locations. Decide whether deeper",
        "source-scene review is needed and approve a scientifically justified downstream eligibility",
        "policy before aggregation. No automatic clipping or omission has been implemented.",
        "This review does not approve the Phase 3 gate or start Phase 4.", ""]
    return {"range_review.json": (json.dumps(review, indent=2, allow_nan=False)+"\n").encode(),
            "range_review.csv": csv_text.getvalue().encode(), "review.md": "\n".join(lines).encode()}


def publish_review(client, *, bucket, blobs, config, source_records, auxiliary, input_bytes, checkpoint):
    """All native audits finish before the first review artifact PUT."""
    check_output_budget(blobs, config, include_manifest=False)
    keys = output_keys(config)
    require_new_keys(client, bucket, list(keys.values()))
    published = []
    for name, body in blobs.items():
        checkpoint({"status": "publishing", "attempted_key": keys[name], "published": list(published)})
        identity = _put_and_verify(client, bucket, keys[name], body, config["version"])
        published.append({"name": name, **identity})
        checkpoint({"status": "artifact_verified", "published": list(published)})
    manifest_name = Path(config["manifest_key"]).name
    record = {"schema_version": 1, "status": "review_evidence_complete_gate_pending",
        "phase3_gate_approved": False, "eligibility_policy_approved": False,
        "input_bytes": input_bytes, "source_rasters": source_records, "auxiliary": auxiliary,
        "outputs": published, "original_rasters_rewritten": False, "display_limits_are_not_data_clipping": True}
    body = (json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
    all_blobs = {**blobs, manifest_name: body}
    total = check_output_budget(all_blobs, config, include_manifest=True)
    checkpoint({"status": "publishing_manifest", "attempted_key": config["manifest_key"], "published": list(published)})
    manifest = _put_and_verify(client, bucket, config["manifest_key"], body, config["version"])
    published.append({"name": manifest_name, **manifest})
    for item in source_records:
        vv = exact_versions(client, bucket, item["key"])
        if len(vv) != 1 or vv[0].get("VersionId") != item["version_id"] or not vv[0].get("IsLatest"):
            raise RuntimeError("QC source identity changed during review")
    checkpoint({"status": "complete", "published": published})
    return {"status": "review_evidence_complete_gate_pending", "phase3_gate_approved": False,
            "eligibility_policy_approved": False, "outputs": published, "input_bytes": input_bytes,
            "new_output_bytes": total, "output_payload_transfer_bytes": 3*total,
            "source_rasters_unchanged": True}, all_blobs
