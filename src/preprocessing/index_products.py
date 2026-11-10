"""Bounded index COG writing, full-resolution validation and create-only checks."""
from __future__ import annotations

import contextlib
import hashlib
from pathlib import Path

import numpy as np
import rasterio
from rio_cogeo.cogeo import cog_translate, cog_validate
from rio_cogeo.profiles import cog_profiles

from src.preprocessing.indices import BAND_NAMES, INDEX_FORMULAS, IndexPolicy, compute_indices


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def object_versions(client, bucket: str, key: str) -> list[dict]:
    return [
        item
        for page in client.get_paginator("list_object_versions").paginate(Bucket=bucket, Prefix=key)
        for group in ("Versions", "DeleteMarkers")
        for item in page.get(group, []) if item.get("Key") == key
    ]


def require_absent(client, bucket: str, keys: list[str]) -> None:
    for key in keys:
        if object_versions(client, bucket, key):
            raise FileExistsError(f"Refusing an existing current/historical destination: {key}")


def put_new_object(client, bucket: str, key: str, body, *, metadata: dict, content_type: str):
    """One ordinary PUT after all-version absence check; callers disable SDK retries.

    This is not an atomic conditional PUT. Callers must hold exclusive namespace
    ownership. An exception is deliberately propagated, never retried here.
    """
    require_absent(client, bucket, [key])
    return client.put_object(
        Bucket=bucket, Key=key, Body=body, Metadata=metadata, ContentType=content_type,
    )


def _merge_stats(total: dict, block: dict) -> None:
    for name, stats in block.items():
        if name not in total:
            total[name] = dict(stats)
            continue
        for key, value in stats.items():
            if key == "minimum":
                if value is not None:
                    total[name][key] = value if total[name][key] is None else min(total[name][key], value)
            elif key == "maximum":
                if value is not None:
                    total[name][key] = value if total[name][key] is None else max(total[name][key], value)
            else:
                total[name][key] += value


def validate_index_products(
    source_path,
    paths: dict,
    *,
    policy: IndexPolicy,
    provenance: dict[str, str],
) -> dict:
    """Check each pixel against an independently expressed index reference."""
    if set(paths) != set(INDEX_FORMULAS):
        raise ValueError("must validate exactly five index products")
    totals = {name: {"valid_pixels": 0, "nodata_pixels": 0, "out_of_range_pixels": 0}
              for name in INDEX_FORMULAS}
    with contextlib.ExitStack() as stack:
        source = stack.enter_context(rasterio.open(source_path))
        datasets = {}
        for name, path in paths.items():
            valid, errors, warnings = cog_validate(str(path), strict=True, quiet=True)
            if not valid:
                raise RuntimeError(f"{name}: strict COG validation failed: {errors}; {warnings}")
            dataset = stack.enter_context(rasterio.open(path))
            if (dataset.count != 1 or dataset.dtypes != ("float32",)
                    or dataset.nodata != policy.output_nodata or dataset.shape != source.shape
                    or dataset.transform != source.transform or dataset.crs != source.crs
                    or dataset.descriptions != (name.upper(),)):
                raise RuntimeError(f"{name}: output grid/schema mismatch")
            tags = dataset.tags()
            for key, value in {**provenance, "formula": INDEX_FORMULAS[name]}.items():
                if tags.get(key) != value:
                    raise RuntimeError(f"{name}: output provenance mismatch: {key}")
            datasets[name] = dataset
        for _, window in source.block_windows(1):
            values = source.read(window=window).astype("float64")
            inside = np.all(np.isfinite(values) & (values != source.nodata), axis=0)
            blue, green, red, nir, swir, _ = values
            # Express pairs separately from the production kernel for audit.
            terms = {"ndvi": (nir, red), "ndbi": (swir, nir), "ndwi": (green, nir),
                     "mndwi": (green, swir), "bsi": (swir + red, nir + blue)}
            for name, (left, right) in terms.items():
                denominator = left + right
                valid = inside & (np.abs(denominator) > policy.denominator_epsilon)
                expected = np.full(inside.shape, policy.output_nodata, dtype="float64")
                np.divide(left - right, denominator, out=expected, where=valid)
                actual = datasets[name].read(1, window=window)
                if not np.isfinite(actual).all():
                    raise RuntimeError(f"{name}: nonfinite persisted pixels")
                if not np.array_equal(actual != policy.output_nodata, valid):
                    raise RuntimeError(f"{name}: nodata/denominator-mask mismatch")
                if not np.array_equal(actual[valid], expected[valid].astype("float32")):
                    raise RuntimeError(f"{name}: full-resolution formula mismatch")
                totals[name]["valid_pixels"] += int(valid.sum())
                totals[name]["nodata_pixels"] += int((~valid).sum())
                totals[name]["out_of_range_pixels"] += int((valid & (
                    (actual < policy.nominal_min - policy.range_tolerance)
                    | (actual > policy.nominal_max + policy.range_tolerance)
                )).sum())
    for name, stats in totals.items():
        if stats["valid_pixels"] == 0:
            raise RuntimeError(f"{name}: no valid output pixels")
    return totals


def write_index_products(
    source_path: Path,
    output_paths: dict[str, Path],
    *,
    policy: IndexPolicy,
    provenance: dict[str, str],
    chunk_size: int = 512,
) -> dict:
    """Write local temporary COGs only; never touch B2 or existing files."""
    if set(output_paths) != set(INDEX_FORMULAS):
        raise ValueError("exactly five output paths are required")
    output_paths = {name: Path(path) for name, path in output_paths.items()}
    temporary = {name: path.with_suffix(".source.tif") for name, path in output_paths.items()}
    if len(set(output_paths.values()) | set(temporary.values())) != 10:
        raise ValueError("output and temporary paths must be distinct")
    for path in (*output_paths.values(), *temporary.values()):
        if path.exists():
            raise FileExistsError(f"Preserving existing local path: {path.name}")
    if chunk_size < 16 or chunk_size % 16:
        raise ValueError("COG chunk size must be a positive multiple of 16")
    statistics = {}
    with rasterio.open(source_path) as source, contextlib.ExitStack() as stack:
        if (source.count != 6 or source.dtypes != ("float32",) * 6
                or source.descriptions != BAND_NAMES or source.nodata != -9999.0):
            raise RuntimeError("source composite schema mismatch")
        destinations = {}
        for name, path in temporary.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            destination = stack.enter_context(rasterio.open(
                path, "w", driver="GTiff", width=source.width, height=source.height,
                count=1, dtype="float32", crs=source.crs, transform=source.transform,
                nodata=policy.output_nodata, tiled=True, blockxsize=chunk_size,
                blockysize=chunk_size, compress="deflate", predictor=3, BIGTIFF="IF_SAFER",
            ))
            destination.set_band_description(1, name.upper())
            destination.update_tags(
                **provenance, formula=INDEX_FORMULAS[name], units="unitless_index",
                denominator_epsilon=str(policy.denominator_epsilon),
                range_policy="preserve_finite_outliers_and_report",
                overview_resampling="average",
            )
            destinations[name] = destination
        from rasterio.windows import Window
        for top in range(0, source.height, chunk_size):
            for left in range(0, source.width, chunk_size):
                window = Window(left, top, min(chunk_size, source.width-left),
                                min(chunk_size, source.height-top))
                outputs, block_stats = compute_indices(
                    source.read(window=window), input_nodata=source.nodata, policy=policy,
                )
                _merge_stats(statistics, block_stats)
                for name, array in outputs.items():
                    destinations[name].write(array, 1, window=window)
    for name, stats in statistics.items():
        if stats["valid_pixels"] == 0 or stats["nonfinite_result_pixels"]:
            raise RuntimeError(f"{name}: empty or numerically invalid index output")
    for name, destination in output_paths.items():
        profile = dict(cog_profiles.get("deflate"))
        profile.update(blockxsize=chunk_size, blockysize=chunk_size, predictor=3, BIGTIFF="IF_SAFER")
        cog_translate(str(temporary[name]), str(destination), profile, quiet=True,
                      in_memory=False, overview_resampling="average")
    validation = validate_index_products(
        source_path, output_paths, policy=policy, provenance=provenance,
    )
    for name in INDEX_FORMULAS:
        for key in ("valid_pixels", "nodata_pixels", "out_of_range_pixels"):
            if statistics[name][key] != validation[name][key]:
                raise RuntimeError(f"{name}: QC disagrees with written pixels: {key}")
    return {
        name: {"bytes": path.stat().st_size, "sha256": sha256_file(path),
               "statistics": statistics[name], "strict_cog": True,
               "local_formula_audit": True}
        for name, path in output_paths.items()
    }
