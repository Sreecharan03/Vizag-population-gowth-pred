"""Version-pinned DEM payload/hash and scientific raster validation."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np

from src.storage.archive_publish import exact_versions


def download_and_hash(client, bucket, spec, destination):
    versions = exact_versions(client, bucket, spec["key"])
    if (len(versions) != 1 or not versions[0].get("IsLatest")
            or versions[0].get("VersionId") != spec["version_id"]
            or int(versions[0].get("Size", -1)) != spec["bytes"]):
        raise RuntimeError(f"DEM identity/history changed: {spec['key']}")
    head = client.head_object(Bucket=bucket, Key=spec["key"], VersionId=spec["version_id"])
    if head.get("VersionId") != spec["version_id"] or int(head["ContentLength"]) != spec["bytes"]:
        raise RuntimeError(f"DEM HEAD identity changed: {spec['key']}")
    response = client.get_object(Bucket=bucket, Key=spec["key"], VersionId=spec["version_id"])
    stream, digest, total = response["Body"], hashlib.sha256(), 0
    try:
        with Path(destination).open("xb") as output:
            for block in stream.iter_chunks(chunk_size=4*1024*1024):
                if not block:
                    continue
                total += len(block)
                if total > spec["bytes"]:
                    raise RuntimeError(f"DEM payload exceeded approved bytes: {spec['key']}")
                digest.update(block)
                output.write(block)
    finally:
        stream.close()
    if total != spec["bytes"]:
        raise RuntimeError(f"DEM payload byte count mismatch: {spec['key']}")
    return digest.hexdigest()


def inspect_dem_header(path, spec):
    """Report a DEM header without imposing a scientific/schema contract."""
    import rasterio

    with rasterio.open(path) as src:
        if src.width <= 0 or src.height <= 0 or src.count <= 0 or src.crs is None:
            raise RuntimeError("DEM header is missing required structural metadata")
        transform = src.transform
        return {
            "key": spec["key"], "bytes": spec["bytes"],
            "version_id": spec["version_id"], "sha256": None,
            "driver": src.driver, "crs": src.crs.to_string(),
            "width": src.width, "height": src.height, "band_count": src.count,
            "dtypes": list(src.dtypes), "nodata": src.nodata,
            "transform": list(transform)[:6], "bounds": list(src.bounds),
            "resolution_degrees": [abs(transform.a), abs(transform.e)],
            "block_shapes": [list(shape) for shape in src.block_shapes],
            "tiled": bool(src.profile.get("tiled", False)),
            "compression": src.compression.name if src.compression else None,
        }


def render_header_probe_markdown(report):
    lines = ["# Part 4.2 DEM evidence-first header probe", "",
             f"Status: **{report['status']}**.", "",
             f"- Exact version-pinned payload read: {report['input_bytes']:,} bytes",
             "- B2 writes: 0", "- Feature aggregation started: no", "",
             "## Observed headers", ""]
    for item in report["sources"]:
        lines += [f"### `{Path(item['key']).name}`", "",
                  f"- SHA-256: `{item['sha256']}`",
                  f"- Version: `{item['version_id']}`",
                  f"- CRS: `{item['crs']}`",
                  f"- Dimensions/bands: {item['width']} x {item['height']} x {item['band_count']}",
                  f"- Data types: `{item['dtypes']}`; nodata: `{item['nodata']}`",
                  f"- Transform: `{item['transform']}`",
                  f"- Bounds: `{item['bounds']}`",
                  f"- Resolution: `{item['resolution_degrees']}` degrees",
                  f"- Blocks: `{item['block_shapes']}`; tiled: `{item['tiled']}`; compression: `{item['compression']}`", ""]
    lines += ["This probe records evidence only; it does not approve or alter the DEM validation contract.", ""]
    return "\n".join(lines).encode()


def inspect_dem(path, spec, config):
    import rasterio
    from rio_cogeo.cogeo import cog_validate

    valid, errors, warnings = cog_validate(path, strict=True)
    if not valid:
        raise RuntimeError(f"DEM is not a strict COG: {errors}; {warnings}")
    with rasterio.open(path) as src:
        if (src.count != config["expected_band_count"]
                or src.crs is None or src.crs.to_string() != config["expected_crs"]
                or src.dtypes[0] != config["expected_dtype"]):
            raise RuntimeError("DEM band count, CRS or dtype differs from approved contract")
        transform = src.transform
        resolution = (abs(transform.a), abs(transform.e))
        expected_resolution = config["expected_pixel_size_degrees"]
        tolerance = config["pixel_size_tolerance_degrees"]
        if (transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0
                or any(abs(value-expected_resolution) > tolerance for value in resolution)):
            raise RuntimeError("DEM transform/resolution is not the expected north-up GLO-30 grid")
        expected_bounds = spec["expected_bounds"]
        if any(abs(actual-expected) > tolerance for actual, expected in zip(src.bounds, expected_bounds)):
            raise RuntimeError("DEM bounds do not match its approved one-degree tile")
        valid_pixels = nodata_pixels = 0
        minimum, maximum, total = math.inf, -math.inf, 0.0
        for _, window in src.block_windows(1):
            data = src.read(1, window=window, masked=True)
            values = data.compressed().astype("float64", copy=False)
            nodata_pixels += int(data.size-values.size)
            if values.size:
                if not np.isfinite(values).all():
                    raise RuntimeError("DEM contains nonfinite values outside its nodata mask")
                valid_pixels += int(values.size)
                minimum = min(minimum, float(values.min()))
                maximum = max(maximum, float(values.max()))
                total += float(values.sum(dtype="float64"))
        if valid_pixels == 0 or valid_pixels+nodata_pixels != src.width*src.height:
            raise RuntimeError("DEM has no valid cells or inconsistent pixel accounting")
        # Broad plausibility bounds reject corrupt/scaled values without asserting a local terrain model.
        if minimum < -500 or maximum > 9000 or minimum > maximum:
            raise RuntimeError("DEM elevation range is physically implausible")
        return {"key": spec["key"], "bytes": spec["bytes"], "version_id": spec["version_id"],
                "sha256": None, "strict_cog": True, "crs": src.crs.to_string(),
                "dtype": src.dtypes[0], "band_count": src.count,
                "width": src.width, "height": src.height, "nodata": src.nodata,
                "transform": list(transform)[:6], "bounds": list(src.bounds),
                "resolution_degrees": list(resolution), "valid_pixels": valid_pixels,
                "nodata_pixels": nodata_pixels, "minimum_elevation_m": minimum,
                "maximum_elevation_m": maximum, "mean_elevation_m": total/valid_pixels}


def validate_pair(records, config):
    if len(records) != 2 or sum(item["bytes"] for item in records) != config["maximum_input_bytes"]:
        raise RuntimeError("DEM validation did not cover the exact approved pair/byte budget")
    fields = ("crs", "dtype", "band_count", "resolution_degrees", "nodata")
    if any(records[0][field] != records[1][field] for field in fields):
        raise RuntimeError("DEM tiles have incompatible schemas")
    if abs(records[0]["bounds"][2]-records[1]["bounds"][0]) > config["pixel_size_tolerance_degrees"]:
        raise RuntimeError("DEM tiles do not share the expected adjacent seam")
    return {"status": "passed", "part": "4.2-dem-gate",
            "contract_version": config["contract_version"],
            "input_bytes": config["maximum_input_bytes"], "b2_writes": 0,
            "sources": records, "sources_hashed": 2, "strict_cogs": 2,
            "part4_2b_started": False}


def require_expected_hash(record, spec):
    if record.get("sha256") != spec.get("sha256"):
        raise RuntimeError(f"DEM SHA-256 differs from approved contract: {spec['key']}")


def render_markdown(report):
    lines = ["# Part 4.2 DEM integrity and schema validation", "",
             f"Status: **{report['status']}**.", "",
             f"- Version-pinned payload read: {report['input_bytes']:,} bytes",
             "- B2 writes: 0", "- Feature aggregation started: no", "",
             "## Verified tiles", ""]
    for item in report["sources"]:
        lines += [f"### `{Path(item['key']).name}`", "",
                  f"- SHA-256: `{item['sha256']}`",
                  f"- Version: `{item['version_id']}`",
                  f"- Schema: {item['width']} × {item['height']}, {item['dtype']}, {item['crs']}",
                  f"- Elevation: {item['minimum_elevation_m']:.3f} to {item['maximum_elevation_m']:.3f} m",
                  f"- Valid/nodata pixels: {item['valid_pixels']:,} / {item['nodata_pixels']:,}", ""]
    lines += ["Both sources are strict COGs with compatible one-degree GLO-30 schemas.",
              "This validates the DEM inputs only; Part 4.2 feature aggregation remains separate.", ""]
    return "\n".join(lines).encode()
