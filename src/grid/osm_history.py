"""Guarded historical OSM feasibility checks using the official ohsome API v2."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def boundary_bbox(boundary: dict) -> list[float]:
    from shapely.geometry import shape
    from shapely.ops import unary_union

    features = boundary.get("features", [])
    if boundary.get("type") != "FeatureCollection" or not features:
        raise RuntimeError("Historical OSM boundary must be a non-empty FeatureCollection")
    geometries = [shape(item["geometry"]) for item in features]
    union = unary_union(geometries)
    if union.is_empty or not union.is_valid:
        raise RuntimeError("Historical OSM boundary geometry is empty or invalid")
    bbox = [float(value) for value in union.bounds]
    if not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
        raise RuntimeError("Historical OSM boundary is not longitude/latitude")
    return bbox


def probe_history(session, api_key: str, bbox: list[float], config: dict) -> list[dict]:
    if not api_key:
        raise RuntimeError("OHSOME_API_KEY is empty")
    expected_calls = len(config["timestamps"]) * len(config["filters"])
    if expected_calls > 10:
        raise RuntimeError("Historical OSM probe request count exceeds approved bound")
    records = []
    url = config["api_root"].rstrip("/") + config["endpoint"]
    for timestamp in config["timestamps"]:
        for feature_class, osm_filter in config["filters"].items():
            payload = {"aoi": bbox, "filter": osm_filter, "time": timestamp}
            response = session.post(
                url, json=payload, headers={"Authorization": api_key},
                timeout=config["timeout_seconds"],
            )
            if len(response.content) > config["maximum_response_bytes"]:
                raise RuntimeError(f"ohsome probe response exceeds cap: {feature_class} {timestamp}")
            if not response.ok:
                try:
                    detail = response.json()
                except ValueError:
                    detail = {"text": response.text[:2048]}
                raise RuntimeError(
                    f"ohsome probe failed for {feature_class} {timestamp}: "
                    f"HTTP {response.status_code}: {json.dumps(detail, sort_keys=True)}"
                )
            if "json" not in response.headers.get("Content-Type", "").lower():
                raise RuntimeError(f"ohsome probe returned non-JSON: {feature_class} {timestamp}")
            body = response.json()
            if not isinstance(body, dict) or not body:
                raise RuntimeError(f"ohsome probe returned invalid JSON: {feature_class} {timestamp}")
            records.append({
                "timestamp": timestamp, "feature_class": feature_class,
                "filter": osm_filter, "response": body,
                "response_bytes": len(response.content),
                "response_sha256": hashlib.sha256(response.content).hexdigest(),
                "request_id": response.headers.get("X-Request-ID"),
            })
    if len(records) != expected_calls:
        raise RuntimeError("Historical OSM probe did not cover the exact contract")
    return records


def build_probe_report(config: dict, bbox: list[float], boundary: dict,
                       records: list[dict], remote_python: str) -> dict:
    return {
        "status": "historical_osm_probe_passed_extraction_not_started",
        "contract_version": config["contract_version"],
        "api_root": config["api_root"], "remote_python": remote_python,
        "boundary_source": config["boundary"], "aoi_bbox": bbox,
        "boundary_sha256": hashlib.sha256(json.dumps(
            boundary, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "timestamps": config["timestamps"], "records": records,
        "requests_made": len(records), "payload_features_downloaded": 0,
        "b2_writes": 0,
    }


def render_probe_markdown(report: dict) -> bytes:
    lines = ["# Historical OSM feasibility probe", "",
             f"Status: **{report['status']}**.", "",
             f"- API: `{report['api_root']}`",
             f"- AOI bounding box: `{report['aoi_bbox']}`",
             f"- Authenticated count requests: {report['requests_made']}",
             "- Feature payloads downloaded: 0", "- B2 writes: 0", "",
             "## Contract coverage", ""]
    for item in report["records"]:
        lines.append(
            f"- {item['timestamp']} / {item['feature_class']}: "
            f"{item['response_bytes']} bytes, `{item['response_sha256']}`"
        )
    lines += ["", "Historical feature extraction remains gated on this probe.", ""]
    return "\n".join(lines).encode()


def download_snapshot(session, api_key: str, bbox: list[float], *, timestamp: str,
                      osm_filter: str, config: dict, destination: Path) -> dict:
    url = config["api_root"].rstrip("/") + "/" + config["extraction_endpoint"].lstrip("/")
    response = session.post(
        url, json={"aoi": bbox, "filter": osm_filter, "time": timestamp, "clip": True},
        headers={"Authorization": api_key}, timeout=240, stream=True,
    )
    if not response.ok:
        try:
            detail = response.json()
        except ValueError:
            detail = {"text": response.text[:2048]}
        raise RuntimeError(f"ohsome extraction failed: HTTP {response.status_code}: "
                           f"{json.dumps(detail, sort_keys=True)}")
    digest, total = hashlib.sha256(), 0
    with Path(destination).open("xb") as output:
        for block in response.iter_content(chunk_size=1024*1024):
            if not block:
                continue
            total += len(block)
            if total > config["maximum_pilot_bytes"]:
                raise RuntimeError("ohsome extraction pilot exceeds byte cap")
            digest.update(block)
            output.write(block)
    if total == 0:
        raise RuntimeError("ohsome extraction pilot returned an empty payload")
    return {"bytes": total, "sha256": digest.hexdigest(),
            "content_type": response.headers.get("Content-Type")}


def inspect_snapshot(path: Path, *, timestamp: str, expected_rows: int) -> dict:
    import geopandas as gpd

    frame = gpd.read_parquet(path)
    if len(frame) != expected_rows:
        raise RuntimeError(f"ohsome extraction rows differ from count: {len(frame)} != {expected_rows}")
    if frame.crs is None or frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise RuntimeError("ohsome extraction has missing CRS/geometry")
    geometry_types = {str(key): int(value) for key, value in frame.geom_type.value_counts().items()}
    required = {"osm_type", "osm_id", "edit_timestamp", "valid_to_timestamp", "tags", "geom"}
    if not required.issubset(frame.columns):
        raise RuntimeError("ohsome extraction schema lacks required columns")
    if frame[["osm_type", "osm_id"]].duplicated().any():
        raise RuntimeError("ohsome extraction contains duplicate OSM identities")
    if frame["edit_timestamp"].max() > __import__("pandas").Timestamp(timestamp):
        raise RuntimeError("ohsome extraction contains a future edit")
    return {"timestamp": timestamp, "rows": len(frame), "columns": list(frame.columns),
            "dtypes": {name: str(dtype) for name, dtype in frame.dtypes.items()},
            "crs": frame.crs.to_string(), "geometry_types": geometry_types,
            "bounds": [float(value) for value in frame.total_bounds],
            "duplicate_geometries": int(frame.geometry.to_wkb().duplicated().sum())}


def snapshot_key(config: dict, spec: dict) -> str:
    return (config["output_prefix"].rstrip("/") + f"/{int(spec['year'])}/"
            + f"{spec['feature_class']}_{int(spec['year'])}.parquet")


def publish_snapshots(client, bucket: str, records: list[dict], config: dict,
                      provenance: dict) -> dict:
    from src.storage.archive_publish import exact_versions, require_new_keys

    keys = [snapshot_key(config, item) for item in config["snapshots"]]
    require_new_keys(client, bucket, [*keys, config["manifest_key"]])
    published = []
    for record, key in zip(records, keys):
        body = Path(record.pop("local_path")).read_bytes()
        response = client.put_object(
            Bucket=bucket, Key=key, Body=body, ContentType="application/vnd.apache.parquet",
            Metadata={"sha256": record["sha256"], "contract-version": config["contract_version"],
                      "data-year": str(record["year"]), "feature-class": record["feature_class"]},
        )
        version = response.get("VersionId")
        versions = exact_versions(client, bucket, key)
        if (len(versions) != 1 or versions[0].get("VersionId") != version
                or int(versions[0].get("Size", -1)) != len(body)):
            raise RuntimeError(f"Historical OSM publication identity mismatch: {key}")
        stream = client.get_object(Bucket=bucket, Key=key, VersionId=version)["Body"]
        try:
            readback = stream.read(len(body)+1)
        finally:
            stream.close()
        if readback != body or hashlib.sha256(readback).hexdigest() != record["sha256"]:
            raise RuntimeError(f"Historical OSM publication readback mismatch: {key}")
        published.append({k: v for k, v in record.items() if k != "columns"}
                         | {"key": key, "version_id": version})
    manifest = {"status": "complete", "contract_version": config["contract_version"],
                "source": "ohsome API v2", "provenance": provenance, "outputs": published}
    body = (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()
    digest = hashlib.sha256(body).hexdigest()
    response = client.put_object(Bucket=bucket, Key=config["manifest_key"], Body=body,
        ContentType="application/json", Metadata={"sha256": digest,
                                                   "contract-version": config["contract_version"]})
    version = response.get("VersionId")
    versions = exact_versions(client, bucket, config["manifest_key"])
    if len(versions) != 1 or versions[0].get("VersionId") != version:
        raise RuntimeError("Historical OSM manifest publication identity mismatch")
    stream = client.get_object(Bucket=bucket, Key=config["manifest_key"], VersionId=version)["Body"]
    try:
        readback = stream.read(len(body)+1)
    finally:
        stream.close()
    if readback != body or hashlib.sha256(readback).hexdigest() != digest:
        raise RuntimeError("Historical OSM manifest readback mismatch")
    manifest["manifest"] = {"key": config["manifest_key"], "version_id": version,
                            "bytes": len(body), "sha256": digest}
    manifest["b2_writes"] = len(published)+1
    return manifest
