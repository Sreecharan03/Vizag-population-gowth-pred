"""Official WorldPop Global2 R2025A discovery and acquisition helpers."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from src.storage.archive_publish import exact_versions, require_new_keys


def parse_boundary(body: bytes) -> dict:
    import geopandas as gpd

    boundary = json.loads(body)
    if boundary.get("type") not in {"Feature", "FeatureCollection", "Polygon", "MultiPolygon"}:
        raise RuntimeError("WorldPop request boundary is not valid GeoJSON")
    if boundary["type"] == "FeatureCollection":
        features = boundary.get("features", [])
    elif boundary["type"] == "Feature":
        features = [boundary]
    else:
        features = [{"type": "Feature", "properties": {}, "geometry": boundary}]
    if not features:
        raise RuntimeError("WorldPop request boundary contains no geometry")
    crs_name = (boundary.get("crs", {}).get("properties", {}).get("name") or "EPSG:4326")
    frame = gpd.GeoDataFrame.from_features(features, crs=crs_name)
    if frame.empty or frame.geometry.isna().any() or not frame.geometry.is_valid.all():
        raise RuntimeError("WorldPop request boundary geometry is empty or invalid")
    frame = frame.to_crs("EPSG:4326")
    minimum_x, minimum_y, maximum_x, maximum_y = map(float, frame.total_bounds)
    if not (-180 <= minimum_x <= maximum_x <= 180 and -90 <= minimum_y <= maximum_y <= 90):
        raise RuntimeError("WorldPop request boundary reprojection did not produce longitude/latitude")
    # The API accepts GeoJSON but requires WGS84 coordinates. Do not retain the legacy
    # GeoJSON CRS member after transforming; RFC 7946 coordinates are longitude/latitude.
    return json.loads(frame.to_json(drop_id=True))


def validate_catalog(catalog: dict, config: dict) -> dict:
    years = [int(value) for value in catalog.get("years", [])]
    required = [int(value) for value in config["years"]]
    if (catalog.get("dataset") != config["expected_dataset"]
            or catalog.get("release") != config["expected_release"]
            or int(catalog.get("resolution_m", -1)) != config["expected_resolution_m"]
            or not set(required).issubset(years)):
        raise RuntimeError("WorldPop catalog differs from the approved release contract")
    return {"dataset": catalog["dataset"], "release": catalog["release"],
            "resolution_m": int(catalog["resolution_m"]), "available_years": years,
            "licence": catalog.get("licence"), "citation": catalog.get("citation")}


def probe_official_api(session, boundary: dict, config: dict) -> dict:
    catalog_response = session.get(config["catalog_url"], timeout=config["timeout_seconds"])
    catalog_response.raise_for_status()
    catalog = validate_catalog(catalog_response.json(), config)
    descriptions = []
    for year in config["years"]:
        payload = {"geojson": boundary, "year": int(year), "resolution": config["request_resolution"],
                   "layer": config["request_layer"], "describe": True}
        response = session.post(config["raster_url"], json=payload, timeout=config["timeout_seconds"])
        if not response.ok:
            try:
                error_body = response.json()
            except ValueError:
                error_body = {"text": response.text[:4096]}
            return {"catalog": catalog, "descriptions": descriptions,
                    "boundary_sha256": hashlib.sha256(json.dumps(boundary, sort_keys=True,
                                                                   separators=(",", ":")).encode()).hexdigest(),
                    "api_error": {"year": int(year), "status_code": int(response.status_code),
                                  "content_type": response.headers.get("Content-Type"),
                                  "request_id": response.headers.get("X-Request-ID"),
                                  "body": error_body},
                    "boundary_summary": {"type": boundary.get("type"),
                                         "feature_count": len(boundary.get("features", []))
                                         if boundary.get("type") == "FeatureCollection" else None}}
        content_type = response.headers.get("Content-Type", "")
        if "json" not in content_type.lower():
            raise RuntimeError(f"WorldPop describe request did not return JSON for {year}")
        description = response.json()
        descriptions.append({"year": int(year), "description": description,
                             "request_id": response.headers.get("X-Request-ID")})
    return {"catalog": catalog, "descriptions": descriptions,
            "boundary_sha256": hashlib.sha256(json.dumps(boundary, sort_keys=True,
                                                           separators=(",", ":")).encode()).hexdigest()}


def build_probe_report(api_result: dict, config: dict, remote_python: str) -> dict:
    if not api_result.get("api_error") and [item["year"] for item in api_result["descriptions"]] != config["years"]:
        raise RuntimeError("WorldPop probe did not cover the exact approved years")
    status = ("official_api_probe_rejected_download_not_started" if api_result.get("api_error")
              else "official_api_probe_passed_download_not_started")
    return {"status": status, "part": "4.3-worldpop-probe",
            "contract_version": config["contract_version"], "remote_python": remote_python,
            "source": api_result["catalog"], "boundary_sha256": api_result["boundary_sha256"],
            "descriptions": api_result["descriptions"], "payload_rasters_downloaded": 0,
            "b2_writes": 0, "legacy_objects_preserved": True,
            "planned_output_prefix": config["output_prefix"],
            "api_error": api_result.get("api_error"),
            "boundary_summary": api_result.get("boundary_summary")}


def render_probe_markdown(report: dict) -> bytes:
    lines = ["# Official WorldPop replacement probe", "",
             f"Status: **{report['status']}**.", "",
             f"- Dataset: {report['source']['dataset']} {report['source']['release']}",
             f"- Resolution: {report['source']['resolution_m']} m",
             f"- Boundary request hash: `{report['boundary_sha256']}`",
             "- Raster payloads downloaded: 0", "- B2 writes: 0",
             f"- Planned create-only prefix: `{report['planned_output_prefix']}`", "",
             "## Year descriptions", ""]
    for item in report["descriptions"]:
        lines.append(f"- {item['year']}: `{json.dumps(item['description'], sort_keys=True)}`")
    if report.get("api_error"):
        lines += ["", "## API rejection", "",
                  f"- Year: {report['api_error']['year']}",
                  f"- HTTP status: {report['api_error']['status_code']}",
                  f"- Request ID: `{report['api_error']['request_id']}`",
                  f"- Response: `{json.dumps(report['api_error']['body'], sort_keys=True)}`",
                  f"- Boundary summary: `{json.dumps(report.get('boundary_summary'), sort_keys=True)}`"]
    lines += ["", "All four years will be downloaded from one release before any population growth is calculated.", ""]
    return "\n".join(lines).encode()


def download_raster(session, boundary: dict, expected: dict, config: dict, destination: Path) -> dict:
    payload = {"geojson": boundary, "year": int(expected["year"]),
               "resolution": config["request_resolution"], "layer": config["request_layer"]}
    response = session.post(config["raster_url"], json=payload, timeout=config["timeout_seconds"], stream=True)
    response.raise_for_status()
    if "tiff" not in response.headers.get("Content-Type", "").lower():
        raise RuntimeError(f"WorldPop raster response is not TIFF for {expected['year']}")
    digest, total = hashlib.sha256(), 0
    with Path(destination).open("xb") as output:
        for block in response.iter_content(chunk_size=1024 * 1024):
            if not block:
                continue
            total += len(block)
            if total > config["maximum_single_raster_bytes"]:
                raise RuntimeError(f"WorldPop raster exceeds approved cap for {expected['year']}")
            digest.update(block)
            output.write(block)
    if total == 0:
        raise RuntimeError(f"WorldPop returned an empty raster for {expected['year']}")
    return {"year": int(expected["year"]), "bytes": total, "sha256": digest.hexdigest(),
            "request_id": response.headers.get("X-Request-ID"),
            "header_total_population": float(response.headers["X-Total-Population"])
            if response.headers.get("X-Total-Population") else None}


def inspect_official_raster(path: Path, expected: dict, config: dict) -> dict:
    import rasterio

    contract = config["expected"]
    with rasterio.open(path) as src:
        if (src.count != 1 or src.crs is None or src.crs.to_string() != contract["crs"]
                or src.width != contract["width"] or src.height != contract["height"]
                or src.nodata != contract["nodata"]):
            raise RuntimeError(f"Official WorldPop raster schema mismatch for {expected['year']}")
        if any(abs(actual-wanted) > contract["bounds_tolerance_degrees"]
               for actual, wanted in zip(src.bounds, contract["bounds"])):
            raise RuntimeError(f"Official WorldPop bounds mismatch for {expected['year']}")
        data = src.read(1, masked=True)
        values = data.compressed().astype("float64", copy=False)
        if not values.size or not np.isfinite(values).all() or float(values.min()) < 0:
            raise RuntimeError(f"Official WorldPop values invalid for {expected['year']}")
        total = float(values.sum(dtype="float64"))
        tolerance = max(1.0, abs(float(expected["total_population"])) * 1e-6)
        if not math.isclose(total, float(expected["total_population"]), abs_tol=tolerance, rel_tol=0):
            raise RuntimeError(f"Official WorldPop population total mismatch for {expected['year']}")
        pixel_digest = hashlib.sha256(np.ascontiguousarray(data.filled(0)).tobytes()
                                      + np.ascontiguousarray(np.ma.getmaskarray(data)).tobytes()).hexdigest()
        return {"year": int(expected["year"]), "width": src.width, "height": src.height,
                "crs": src.crs.to_string(), "nodata": src.nodata, "bounds": list(src.bounds),
                "dtype": src.dtypes[0], "valid_pixels": int(values.size),
                "nodata_pixels": int(data.size-values.size), "minimum": float(values.min()),
                "maximum": float(values.max()), "mean": float(values.mean()),
                "total_population": total, "pixel_sha256": pixel_digest}


def validate_raster_set(records: list[dict], config: dict) -> None:
    years = [record["year"] for record in records]
    expected_years = [item["year"] for item in config["expected"]["years"]]
    if years != expected_years or len({record["sha256"] for record in records}) != len(records):
        raise RuntimeError("WorldPop batch lacks exact years or has duplicate payloads")
    if len({record["pixel_sha256"] for record in records}) != len(records):
        raise RuntimeError("WorldPop batch has duplicate epoch pixels")


def resolve_output_key(config: dict, year: int) -> str:
    """Resolve YAML's integer year keys explicitly and reject ambiguous aliases."""
    outputs = config.get("outputs", {})
    if year not in outputs or str(year) in outputs:
        raise RuntimeError(f"WorldPop output mapping must contain one integer key for {year}")
    key = outputs[year]
    if not isinstance(key, str) or not key:
        raise RuntimeError(f"WorldPop output mapping is invalid for {year}")
    return key


def publish_worldpop(client, bucket: str, records: list[dict], config: dict, provenance: dict) -> dict:
    output_keys = [resolve_output_key(config, record["year"]) for record in records]
    require_new_keys(client, bucket, [*output_keys, config["manifest_key"]])
    published = []
    for record, key in zip(records, output_keys):
        body = Path(record.pop("local_path")).read_bytes()
        response = client.put_object(Bucket=bucket, Key=key, Body=body,
                                     Metadata={"sha256": record["sha256"],
                                               "contract-version": config["contract_version"],
                                               "data-year": str(record["year"])},
                                     ContentType="image/tiff")
        version_id = response.get("VersionId")
        versions = exact_versions(client, bucket, key)
        if (len(versions) != 1 or versions[0].get("VersionId") != version_id
                or int(versions[0].get("Size", -1)) != len(body)):
            raise RuntimeError(f"WorldPop publication identity mismatch: {key}")
        fetched = client.get_object(Bucket=bucket, Key=key, VersionId=version_id)["Body"]
        try:
            readback = fetched.read(len(body)+1)
        finally:
            fetched.close()
        if readback != body or hashlib.sha256(readback).hexdigest() != record["sha256"]:
            raise RuntimeError(f"WorldPop publication readback mismatch: {key}")
        published.append({"year": record["year"], "key": key, "version_id": version_id,
                          "bytes": len(body), "sha256": record["sha256"],
                          "total_population": record["total_population"],
                          "pixel_sha256": record["pixel_sha256"]})
    manifest = {"status": "complete", "contract_version": config["contract_version"],
                "dataset": config["dataset"], "release": config["release"], "doi": config["doi"],
                "licence": config["licence"], "provenance": provenance, "outputs": published}
    manifest_body = (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()
    manifest_sha = hashlib.sha256(manifest_body).hexdigest()
    response = client.put_object(Bucket=bucket, Key=config["manifest_key"], Body=manifest_body,
                                 Metadata={"sha256": manifest_sha,
                                           "contract-version": config["contract_version"]},
                                 ContentType="application/json")
    manifest_version = response.get("VersionId")
    versions = exact_versions(client, bucket, config["manifest_key"])
    if (len(versions) != 1 or versions[0].get("VersionId") != manifest_version
            or int(versions[0].get("Size", -1)) != len(manifest_body)):
        raise RuntimeError("WorldPop manifest publication identity mismatch")
    fetched = client.get_object(Bucket=bucket, Key=config["manifest_key"], VersionId=manifest_version)["Body"]
    try:
        readback = fetched.read(len(manifest_body)+1)
    finally:
        fetched.close()
    if readback != manifest_body or hashlib.sha256(readback).hexdigest() != manifest_sha:
        raise RuntimeError("WorldPop manifest publication readback mismatch")
    manifest["manifest"] = {"key": config["manifest_key"], "version_id": manifest_version,
                            "bytes": len(manifest_body), "sha256": manifest_sha}
    manifest["b2_writes"] = len(published)+1
    return manifest
