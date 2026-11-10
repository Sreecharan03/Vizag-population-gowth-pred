"""Validated COG publication primitives for Phase 3 scene extraction."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rio_cogeo.cogeo import cog_translate, cog_validate
from rio_cogeo.profiles import cog_profiles

REFLECTANCE_BANDS = ("B02", "B03", "B04", "B08", "B11", "B12")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_cog(path: Path) -> None:
    result = cog_validate(str(path), strict=True)
    valid = result[0] if isinstance(result, tuple) else bool(result)
    if not valid:
        raise RuntimeError(f"COG validation failed for {path.name}: {result}")


def _translate_to_cog(source: Path, destination: Path, *, floating: bool) -> None:
    profile = cog_profiles.get("deflate")
    profile.update({"blockxsize": 512, "blockysize": 512, "BIGTIFF": "IF_SAFER"})
    if floating:
        profile["predictor"] = 3
    cog_translate(str(source), str(destination), profile, in_memory=False, quiet=True)
    _validate_cog(destination)


def write_scene_cogs(
    reflectance: np.ndarray,
    scl: np.ndarray,
    *,
    transform: Affine,
    crs: str,
    reflectance_path: Path,
    scl_path: Path,
    scene_id: str,
    contract_version: str,
    source_object_key: str,
    source_size_bytes: int,
    source_etag: str,
    processing_baseline: str,
    quantification_value: float,
    band_offsets: dict[str, float],
) -> dict:
    """Write and reopen-validate separate reflectance and categorical COGs."""
    if reflectance.ndim != 3 or reflectance.shape[0] != 6:
        raise ValueError("reflectance must have shape (6, height, width)")
    if scl.shape != reflectance.shape[1:]:
        raise ValueError("SCL shape must match reflectance spatial shape")
    if reflectance.dtype != np.float32 or scl.dtype != np.uint8:
        raise TypeError("reflectance must be float32 and SCL must be uint8")
    reflectance_path, scl_path = Path(reflectance_path), Path(scl_path)
    reflectance_path.parent.mkdir(parents=True, exist_ok=True)
    scl_path.parent.mkdir(parents=True, exist_ok=True)
    reflectance_tmp = reflectance_path.with_suffix(".source.tif")
    scl_tmp = scl_path.with_suffix(".source.tif")
    height, width = scl.shape
    if set(band_offsets) != set(REFLECTANCE_BANDS):
        raise ValueError("band_offsets must contain exactly the six reflectance bands")
    common_tags = {
        "scene_id": scene_id,
        "contract_version": contract_version,
        "source_object_key": source_object_key,
        "source_size_bytes": str(int(source_size_bytes)),
        "source_etag": source_etag,
        "processing_baseline": processing_baseline,
        "quantification_value": format(float(quantification_value), ".15g"),
        "band_offsets": ",".join(
            f"{band}:{format(float(band_offsets[band]), '.15g')}"
            for band in REFLECTANCE_BANDS
        ),
    }
    try:
        with rasterio.open(
            reflectance_tmp, "w", driver="GTiff", width=width, height=height,
            count=6, dtype="float32", crs=crs, transform=transform,
            nodata=-9999.0, tiled=True, blockxsize=512, blockysize=512,
            compress="deflate", predictor=3, BIGTIFF="IF_SAFER",
        ) as dst:
            dst.write(reflectance)
            dst.descriptions = REFLECTANCE_BANDS
            dst.update_tags(**common_tags, units="unitless_BOA_reflectance")
        with rasterio.open(
            scl_tmp, "w", driver="GTiff", width=width, height=height,
            count=1, dtype="uint8", crs=crs, transform=transform,
            nodata=0, tiled=True, blockxsize=512, blockysize=512,
            compress="deflate", predictor=2, BIGTIFF="IF_SAFER",
        ) as dst:
            dst.write(scl, 1)
            dst.set_band_description(1, "SCL")
            dst.update_tags(**common_tags, units="Sentinel-2_scene_class")
        _translate_to_cog(reflectance_tmp, reflectance_path, floating=True)
        _translate_to_cog(scl_tmp, scl_path, floating=False)
    finally:
        reflectance_tmp.unlink(missing_ok=True)
        scl_tmp.unlink(missing_ok=True)

    with rasterio.open(reflectance_path) as src:
        if src.count != 6 or src.dtypes != ("float32",) * 6 or src.nodata != -9999.0:
            raise RuntimeError("Reflectance COG schema validation failed")
        if src.transform != transform or src.crs.to_string() != crs:
            raise RuntimeError("Reflectance COG spatial validation failed")
        if tuple(src.descriptions) != REFLECTANCE_BANDS:
            raise RuntimeError("Reflectance COG band-order validation failed")
        for key, value in common_tags.items():
            if src.tags().get(key) != value:
                raise RuntimeError(f"Reflectance COG provenance validation failed: {key}")
    with rasterio.open(scl_path) as src:
        if src.count != 1 or src.dtypes != ("uint8",) or src.nodata != 0:
            raise RuntimeError("SCL COG schema validation failed")
        if src.transform != transform or src.crs.to_string() != crs:
            raise RuntimeError("SCL COG spatial validation failed")
        for key, value in common_tags.items():
            if src.tags().get(key) != value:
                raise RuntimeError(f"SCL COG provenance validation failed: {key}")
    return {
        "reflectance": {"bytes": reflectance_path.stat().st_size, "sha256": _sha256(reflectance_path)},
        "scl": {"bytes": scl_path.stat().st_size, "sha256": _sha256(scl_path)},
    }

