"""Sentinel-2 Level-2A radiometric metadata parsing.

This module is pure and network-free. Remote archive access remains in the
Modal control worker so the parser can be tested without credentials.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from xml.etree import ElementTree as ET

import numpy as np


class RadiometryMetadataError(ValueError):
    """Raised when required Level-2A radiometric metadata is absent/invalid."""


@dataclass(frozen=True)
class RadiometryMetadata:
    processing_baseline: str
    quantification_value: float
    offsets_by_band_id: dict[str, float]
    physical_band_by_id: dict[str, str]

    def as_dict(self) -> dict:
        return asdict(self)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _elements(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == local_name]


def _required_text(root: ET.Element, local_name: str) -> str:
    matches = _elements(root, local_name)
    if not matches or not matches[0].text or not matches[0].text.strip():
        raise RadiometryMetadataError(f"Missing required metadata field: {local_name}")
    return matches[0].text.strip()


def normalize_physical_band(value: str) -> str:
    """Normalize Sentinel metadata names (B2) to archive codes (B02)."""
    band = value.strip().upper()
    if band == "B8A":
        return band
    if band.startswith("B") and band[1:].isdigit():
        return f"B{int(band[1:]):02d}"
    raise RadiometryMetadataError(f"Invalid physical band name: {value}")


def parse_l2a_radiometry_metadata(xml: bytes | str) -> RadiometryMetadata:
    """Parse the product-level MTD_MSIL2A XML without relying on namespaces.

    Offsets remain keyed by the XML ``band_id``. The product's own
    Spectral_Information entries provide the physical-band mapping, avoiding a
    fragile hard-coded assumption about numeric band order.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise RadiometryMetadataError("Invalid MTD_MSIL2A XML") from exc

    baseline = _required_text(root, "PROCESSING_BASELINE")
    try:
        quantification = float(_required_text(root, "BOA_QUANTIFICATION_VALUE"))
    except ValueError as exc:
        raise RadiometryMetadataError("BOA_QUANTIFICATION_VALUE is not numeric") from exc
    if quantification <= 0:
        raise RadiometryMetadataError("BOA_QUANTIFICATION_VALUE must be positive")

    offsets: dict[str, float] = {}
    for element in _elements(root, "BOA_ADD_OFFSET"):
        band_id = element.attrib.get("band_id")
        if band_id is None or not element.text:
            raise RadiometryMetadataError("BOA_ADD_OFFSET lacks band_id or value")
        try:
            offsets[str(band_id)] = float(element.text.strip())
        except ValueError as exc:
            raise RadiometryMetadataError(f"Invalid BOA_ADD_OFFSET for band_id={band_id}") from exc

    physical_by_id: dict[str, str] = {}
    for element in _elements(root, "Spectral_Information"):
        band_id = element.attrib.get("bandId") or element.attrib.get("band_id")
        physical = element.attrib.get("physicalBand") or element.attrib.get("physical_band")
        if band_id is not None and physical:
            physical_by_id[str(band_id)] = normalize_physical_band(physical)

    return RadiometryMetadata(
        processing_baseline=baseline,
        quantification_value=quantification,
        offsets_by_band_id=offsets,
        physical_band_by_id=physical_by_id,
    )


def parameters_for_band(metadata: RadiometryMetadata, physical_band: str) -> tuple[float, float]:
    """Return (offset, quantification) using the product's own band mapping."""
    band = normalize_physical_band(physical_band)
    ids = [band_id for band_id, physical in metadata.physical_band_by_id.items() if physical == band]
    if len(ids) != 1:
        raise RadiometryMetadataError(f"Expected exactly one metadata mapping for {band}, found {len(ids)}")
    band_id = ids[0]
    baseline = float(metadata.processing_baseline)
    if baseline >= 4.0:
        if band_id not in metadata.offsets_by_band_id:
            raise RadiometryMetadataError(f"Offset-era product lacks BOA_ADD_OFFSET for {band}")
        offset = metadata.offsets_by_band_id[band_id]
    else:
        offset = metadata.offsets_by_band_id.get(band_id, 0.0)
    return offset, metadata.quantification_value


def convert_dn_to_reflectance(
    dn: np.ndarray,
    *,
    offset: float,
    quantification_value: float,
    output_nodata: float = -9999.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert one L2A DN array while preserving DN=0 as invalid.

    Returns ``(float32_reflectance, valid_mask)``. Values are deliberately not
    clipped; later QC must measure out-of-nominal reflectance before any policy
    decision.
    """
    if quantification_value <= 0:
        raise RadiometryMetadataError("quantification_value must be positive")
    if not np.issubdtype(dn.dtype, np.integer):
        raise TypeError("Source DN array must have an integer dtype")
    valid = dn != 0
    result = np.full(dn.shape, output_nodata, dtype=np.float32)
    result[valid] = (dn[valid].astype(np.float32) + np.float32(offset)) / np.float32(quantification_value)
    return result, valid


def reflectance_statistics(values: np.ndarray, valid_mask: np.ndarray) -> dict[str, float | int]:
    """Exact QC statistics over valid converted pixels only."""
    if values.shape != valid_mask.shape:
        raise ValueError("values and valid_mask must have identical shapes")
    valid = values[valid_mask]
    if valid.size == 0:
        return {"valid_pixels": 0, "negative_pixels": 0, "above_one_pixels": 0}
    p01, p50, p99 = np.percentile(valid, [1, 50, 99])
    return {
        "valid_pixels": int(valid.size),
        "negative_pixels": int((valid < 0).sum()),
        "above_one_pixels": int((valid > 1).sum()),
        "minimum": float(valid.min()),
        "p01": float(p01),
        "median": float(p50),
        "p99": float(p99),
        "maximum": float(valid.max()),
    }

