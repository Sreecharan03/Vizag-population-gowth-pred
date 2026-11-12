"""Part 4.3b exact-version validation for WorldPop and OSM context sources."""
from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from src.storage.archive_publish import exact_versions


def download_and_hash(client, bucket: str, spec: dict, destination: Path) -> str:
    versions = exact_versions(client, bucket, spec["key"])
    if (len(versions) != 1 or not versions[0].get("IsLatest")
            or versions[0].get("VersionId") != spec["version_id"]
            or int(versions[0].get("Size", -1)) != int(spec["bytes"])):
        raise RuntimeError(f"Context source identity/history changed: {spec['key']}")
    head = client.head_object(Bucket=bucket, Key=spec["key"], VersionId=spec["version_id"])
    if (head.get("VersionId") != spec["version_id"]
            or int(head.get("ContentLength", -1)) != int(spec["bytes"])):
        raise RuntimeError(f"Context source HEAD identity changed: {spec['key']}")
    response = client.get_object(Bucket=bucket, Key=spec["key"], VersionId=spec["version_id"])
    stream, digest, total = response["Body"], hashlib.sha256(), 0
    try:
        with Path(destination).open("xb") as output:
            for block in stream.iter_chunks(chunk_size=4 * 1024 * 1024):
                if not block:
                    continue
                total += len(block)
                if total > int(spec["bytes"]):
                    raise RuntimeError(f"Context payload exceeded approved bytes: {spec['key']}")
                digest.update(block)
                output.write(block)
    finally:
        stream.close()
    if total != int(spec["bytes"]):
        raise RuntimeError(f"Context payload byte count mismatch: {spec['key']}")
    return digest.hexdigest()


def inspect_worldpop(path: Path, spec: dict, config: dict) -> dict:
    import rasterio

    with rasterio.open(path) as src:
        if src.count != config["expected_worldpop_band_count"] or src.crs is None:
            raise RuntimeError(f"WorldPop band count/CRS invalid: {spec['key']}")
        data = src.read(1, masked=True)
        values = data.compressed().astype("float64", copy=False)
        if not values.size or not np.isfinite(values).all() or float(values.min()) < 0:
            raise RuntimeError(f"WorldPop contains no usable population or invalid values: {spec['key']}")
        mask = np.ma.getmaskarray(data)
        pixel_digest = hashlib.sha256()
        pixel_digest.update(np.ascontiguousarray(data.filled(0)).tobytes())
        pixel_digest.update(np.ascontiguousarray(mask).tobytes())
        transform = src.transform
        tags = {str(key): str(value) for key, value in sorted(src.tags().items())}
        return {
            "year": int(spec["year"]), "key": spec["key"], "bytes": int(spec["bytes"]),
            "version_id": spec["version_id"], "payload_sha256": None,
            "pixel_sha256": pixel_digest.hexdigest(), "driver": src.driver,
            "crs": src.crs.to_string(), "width": src.width, "height": src.height,
            "band_count": src.count, "dtype": src.dtypes[0], "nodata": src.nodata,
            "transform": list(transform)[:6], "bounds": list(src.bounds),
            "resolution": [abs(transform.a), abs(transform.e)],
            "valid_pixels": int(values.size), "nodata_pixels": int(data.size-values.size),
            "minimum": float(values.min()), "maximum": float(values.max()),
            "mean": float(values.mean()), "sum": float(values.sum(dtype="float64")),
            "tags": tags,
        }


def inspect_osm(path: Path, spec: dict) -> dict:
    import geopandas as gpd

    frame = gpd.read_file(path)
    if frame.empty or frame.crs is None or frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise RuntimeError(f"OSM source is empty or lacks CRS/geometry: {spec['key']}")
    if not frame.geometry.is_valid.all():
        raise RuntimeError(f"OSM source contains invalid geometry: {spec['key']}")
    geometry_types = dict(sorted(Counter(frame.geometry.geom_type).items()))
    role = spec["role"]
    result = {"role": role, "key": spec["key"], "bytes": int(spec["bytes"]),
              "version_id": spec["version_id"], "payload_sha256": None,
              "crs": frame.crs.to_string(), "feature_count": int(len(frame)),
              "geometry_types": geometry_types, "columns": sorted(map(str, frame.columns))}
    if role == "roads":
        if not set(geometry_types).issubset({"LineString", "MultiLineString"}):
            raise RuntimeError("OSM roads contain non-linear geometry")
    elif role == "amenities":
        if "amenity" not in frame.columns:
            raise RuntimeError("OSM amenities lack the amenity field")
        counts = {str(key): int(value) for key, value in frame["amenity"].fillna("<missing>").value_counts().items()}
        result["amenity_counts"] = dict(sorted(counts.items()))
        result["hospital_features"] = counts.get("hospital", 0)
        result["clinic_features"] = counts.get("clinic", 0)
        result["education_features"] = sum(counts.get(name, 0) for name in ("school", "college", "university"))
        if result["hospital_features"] == 0 or result["education_features"] == 0:
            raise RuntimeError("OSM amenities lack required hospital or education features")
    else:
        raise RuntimeError(f"Unknown OSM role: {role}")
    return result


def assess_worldpop(records: list[dict]) -> dict:
    schema_fields = ("crs", "width", "height", "transform", "bounds", "resolution", "dtype", "nodata")
    reference = records[0]
    compatible = all(all(record[field] == reference[field] for field in schema_fields)
                     for record in records[1:])
    groups = defaultdict(list)
    for record in records:
        groups[record["pixel_sha256"]].append(record["year"])
    duplicate_groups = [years for years in groups.values() if len(years) > 1]
    if not compatible:
        raise RuntimeError("WorldPop epoch rasters do not share one aligned schema")
    return {"schema_compatible": True, "duplicate_pixel_groups": duplicate_groups,
            "unique_pixel_payloads": len(groups),
            "growth_calculation_allowed": not duplicate_groups,
            "status": ("blocked_duplicate_epoch_pixels" if duplicate_groups else "passed")}


def build_report(config: dict, worldpop: list[dict], osm: list[dict]) -> dict:
    sources = [*worldpop, *osm]
    if (len(worldpop) != 4 or len(osm) != 2
            or sum(item["bytes"] for item in sources) != config["maximum_input_bytes"]):
        raise RuntimeError("Context validation did not cover the exact approved sources/bytes")
    worldpop_assessment = assess_worldpop(worldpop)
    osm_assessment = {
        "snapshot_date": config["osm_snapshot_date"],
        "historical_training_allowed": False,
        "status": "blocked_future_snapshot_for_2018_2024_training",
        "dated_context_aggregation_allowed": True,
    }
    blockers = []
    if not worldpop_assessment["growth_calculation_allowed"]:
        blockers.append("worldpop_duplicate_epoch_pixels")
    blockers.append("osm_snapshot_postdates_all_feature_epochs")
    return {"status": "validated_with_scientific_blockers", "part": "4.3b",
            "contract_version": config["contract_version"],
            "input_bytes": config["maximum_input_bytes"], "sources_hashed": len(sources),
            "b2_writes": 0, "aggregation_started": False, "worldpop": worldpop,
            "osm": osm, "worldpop_assessment": worldpop_assessment,
            "osm_assessment": osm_assessment, "blockers": blockers}


def render_markdown(report: dict) -> bytes:
    lines = ["# Part 4.3b context payload validation", "",
             f"Status: **{report['status']}**.", "",
             f"- Exact payload read/hash: {report['input_bytes']:,} bytes",
             f"- Sources hashed: {report['sources_hashed']}", "- B2 writes: 0",
             "- Aggregation started: no", "", "## WorldPop", ""]
    for item in report["worldpop"]:
        lines.append(f"- {item['year']}: `{item['payload_sha256']}`; sum={item['sum']:.6f}; "
                     f"valid/nodata={item['valid_pixels']:,}/{item['nodata_pixels']:,}")
    assessment = report["worldpop_assessment"]
    lines += ["", f"Pixel-unique epoch payloads: {assessment['unique_pixel_payloads']} of 4.",
              f"Duplicate pixel groups: `{assessment['duplicate_pixel_groups']}`.",
              f"Population-growth calculation allowed: **{assessment['growth_calculation_allowed']}**.",
              "", "## OSM", ""]
    for item in report["osm"]:
        lines.append(f"- {item['role']}: {item['feature_count']:,} valid features, CRS `{item['crs']}`, "
                     f"SHA-256 `{item['payload_sha256']}`")
        if item["role"] == "amenities":
            lines.append(f"  - Hospitals: {item['hospital_features']}; clinics: {item['clinic_features']}; "
                         f"education features: {item['education_features']}")
    lines += ["", "## Scientific gate", "",
              "The 2026 OSM snapshot is structurally usable as dated context evidence but is blocked from",
              "2018-2024 historical training. Duplicate WorldPop epoch pixels, if listed above, block",
              "population-growth calculation until provenance-correct epoch rasters are obtained.", ""]
    return "\n".join(lines).encode()
