"""Parses a B2 object key into structured Sentinel-2 product metadata, or
classifies it as a boundary file / other / unknown.

Matching is done on the parsed PRODUCT ID (mission, sensing date, orbit,
tile, baseline, processing date), never on the exact key string — a
differently-prefixed copy of the same acquisition is still recognized as
the same product (plan.md Phase 2: "matched by parsed product ID, not
exact key, to avoid re-downloading what already exists").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Standard ESA Sentinel-2 product ID:
#   S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013
#   mission_level_sensingdate_baseline_orbit_tile_processingdate
_SENTINEL2_RE = re.compile(
    r"(?P<mission>S2[AB])_"
    r"(?P<level>MSIL[12][AC])_"
    r"(?P<sensing_date>\d{8}T\d{6})_"
    r"(?P<baseline>N\d{4})_"
    r"(?P<orbit>R\d{3})_"
    r"(?P<tile>T\d{2}[A-Z]{3})_"
    r"(?P<proc_date>\d{8}T\d{6})"
)

# This bucket's existing processed outputs are flattened as
# "<product_id>.SAFE_<kind>.<ext>" rather than a real .SAFE folder tree.
_PROCESSED_DERIVATIVE_RE = re.compile(r"^\.SAFE_(?P<kind>[a-zA-Z0-9]+)\.")

KNOWN_DERIVATIVE_KINDS = {"refl", "scl", "qa"}

# A second, shorter naming convention found in this bucket under .../mosaic/:
# a tile-merged composite has no tile ID or baseline at all, e.g.
# "S2A_20180103T045201_R076_refl.tif".
_MOSAIC_RE = re.compile(
    r"^(?P<mission>S2[AB])_(?P<sensing_date>\d{8}T\d{6})_(?P<orbit>R\d{3})_"
    r"(?P<kind>refl|scl|qa)\.\w+$"
)


@dataclass(frozen=True)
class ParsedKey:
    key: str
    source: str  # "sentinel2" | "boundary" | "other" | "unknown"
    format: str  # "SAFE" | "zip" | "processed_derivative" | "unrecognized" | "n/a"
    product_id: str | None = None
    mission: str | None = None
    level: str | None = None
    sensing_date: str | None = None
    processing_baseline: str | None = None
    relative_orbit: str | None = None
    tile: str | None = None
    processing_date: str | None = None
    derivative_kind: str | None = None

    @property
    def duplicate_group_key(self) -> tuple | None:
        """Identifies "the same acquisition" regardless of processing
        baseline/date — used to detect reprocessed duplicates.
        """
        if self.mission is None:
            return None
        return (self.mission, self.sensing_date, self.relative_orbit, self.tile)


# OS/filesystem junk that occasionally ends up in a bucket — always
# classified "unknown", never "other", regardless of having an extension.
_KNOWN_JUNK_BASENAMES = {".ds_store", "thumbs.db", "desktop.ini", "icon\r", ".spotlight-v100", ".trashes"}


def _basename(key: str) -> str:
    return key.rsplit("/", 1)[-1]


def parse_object_key(key: str) -> ParsedKey:
    basename = _basename(key)
    path_segments = key.split("/")

    if basename.lower() in _KNOWN_JUNK_BASENAMES:
        return ParsedKey(key=key, source="unknown", format="n/a")

    match = _SENTINEL2_RE.search(basename)
    if match:
        remainder = basename[match.end() :]
        fields = dict(
            product_id=match.group(0),
            mission=match.group("mission"),
            level=match.group("level"),
            sensing_date=match.group("sensing_date"),
            processing_baseline=match.group("baseline"),
            relative_orbit=match.group("orbit"),
            tile=match.group("tile"),
            processing_date=match.group("proc_date"),
        )
        if remainder in (".zip", ".SAFE.zip"):
            return ParsedKey(key=key, source="sentinel2", format="zip", **fields)
        deriv_match = _PROCESSED_DERIVATIVE_RE.match(remainder)
        if deriv_match:
            return ParsedKey(
                key=key,
                source="sentinel2",
                format="processed_derivative",
                derivative_kind=deriv_match.group("kind"),
                **fields,
            )
        return ParsedKey(key=key, source="sentinel2", format="unrecognized", **fields)

    mosaic_match = _MOSAIC_RE.match(basename)
    if mosaic_match:
        synthetic_id = f"{mosaic_match.group('mission')}_{mosaic_match.group('sensing_date')}_{mosaic_match.group('orbit')}"
        return ParsedKey(
            key=key,
            source="sentinel2",
            format="mosaic_derivative",
            product_id=synthetic_id,
            mission=mosaic_match.group("mission"),
            sensing_date=mosaic_match.group("sensing_date"),
            relative_orbit=mosaic_match.group("orbit"),
            derivative_kind=mosaic_match.group("kind"),
        )

    # Raw unzipped .SAFE folder: some ancestor path segment ends with ".SAFE"
    # exactly (a real directory boundary), with per-band files inside it.
    for segment in path_segments:
        if segment.endswith(".SAFE"):
            inner_match = _SENTINEL2_RE.search(segment)
            fields = {}
            if inner_match:
                fields = dict(
                    product_id=inner_match.group(0),
                    mission=inner_match.group("mission"),
                    level=inner_match.group("level"),
                    sensing_date=inner_match.group("sensing_date"),
                    processing_baseline=inner_match.group("baseline"),
                    relative_orbit=inner_match.group("orbit"),
                    tile=inner_match.group("tile"),
                    processing_date=inner_match.group("proc_date"),
                )
            return ParsedKey(key=key, source="sentinel2", format="SAFE", **fields)

    if "boundaries" in path_segments:
        return ParsedKey(key=key, source="boundary", format="n/a")

    # Anything else recognizable as project output vs. true junk (.DS_Store,
    # thumbnails, etc.) — classified "other", never "unknown", only when it
    # at least has a plausible extension; otherwise "unknown".
    if "." in basename and not basename.startswith("."):
        return ParsedKey(key=key, source="other", format="n/a")

    return ParsedKey(key=key, source="unknown", format="n/a")
