"""Phase 2 Part 2.1: read-only B2 inventory.

Lists every object behind a backend (paginated — the backend itself
handles that), parses each key via product_id.py, classifies it, and
writes:
  - data/manifests/b2_inventory.jsonl  (one record per object)
  - results/phase2/inventory_report.md (plain-language summary)

Strictly read-only: never calls download/upload on the backend, never
deletes or overwrites anything.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.acquisition.product_id import KNOWN_DERIVATIVE_KINDS, ParsedKey, parse_object_key
from src.utils.io import resolve_path

SUSPECT_SIZE_MIN_BYTES = 100
EXPECTED_TOTAL_GB = 225  # plan.md's documented expectation — a sanity reference, not a hard check

_STATUS_INCOMPLETE = "INCOMPLETE"
_STATUS_SUSPECT_SIZE = "SUSPECT_SIZE"
_STATUS_DUPLICATE = "DUPLICATE"
_STATUS_OK = "OK"
_STATUS_UNKNOWN = "UNKNOWN"
_STATUS_BOUNDARY = "BOUNDARY"
_STATUS_OTHER = "OTHER"


@dataclass
class InventoryEntry:
    key: str
    size_bytes: int
    source: str
    format: str
    product_id: str | None
    tile: str | None
    sensing_date: str | None
    processing_baseline: str | None
    processing_date: str | None
    derivative_kind: str | None
    statuses: list[str]

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def _entry_from_parsed(parsed: ParsedKey, size_bytes: int) -> InventoryEntry:
    statuses: list[str] = []
    if size_bytes < SUSPECT_SIZE_MIN_BYTES:
        statuses.append(_STATUS_SUSPECT_SIZE)

    if parsed.source == "boundary":
        statuses.append(_STATUS_BOUNDARY)
    elif parsed.source == "unknown":
        statuses.append(_STATUS_UNKNOWN)
    elif parsed.source == "other":
        statuses.append(_STATUS_OTHER)
    # sentinel2 entries get OK/INCOMPLETE/DUPLICATE added by classify_inventory()

    return InventoryEntry(
        key=parsed.key,
        size_bytes=size_bytes,
        source=parsed.source,
        format=parsed.format,
        product_id=parsed.product_id,
        tile=parsed.tile,
        sensing_date=parsed.sensing_date,
        processing_baseline=parsed.processing_baseline,
        processing_date=parsed.processing_date,
        derivative_kind=parsed.derivative_kind,
        statuses=statuses,
    )


def list_inventory(backend, prefix: str = "") -> list[InventoryEntry]:
    """Paginated (the backend itself pages internally), read-only listing.
    Never calls download/upload/delete on the backend.
    """
    entries = []
    for obj in backend.list(prefix=prefix):
        parsed = parse_object_key(obj.key)
        entries.append(_entry_from_parsed(parsed, obj.size_bytes))
    return entries


def classify_inventory(entries: list[InventoryEntry]) -> list[InventoryEntry]:
    """Adds completeness (per product_id) and duplicate (per
    duplicate_group_key) statuses to sentinel2 processed_derivative
    entries. Never removes or mutates anything else about an entry;
    duplicates are flagged, never deleted.
    """
    by_product_id: dict[str, list[InventoryEntry]] = defaultdict(list)
    for e in entries:
        if e.source == "sentinel2" and e.format in ("processed_derivative", "mosaic_derivative") and e.product_id:
            by_product_id[e.product_id].append(e)

    for product_id, group in by_product_id.items():
        present_kinds = {e.derivative_kind for e in group}
        if present_kinds >= KNOWN_DERIVATIVE_KINDS:
            for e in group:
                e.statuses.append(_STATUS_OK)
        else:
            missing = KNOWN_DERIVATIVE_KINDS - present_kinds
            for e in group:
                e.statuses.append(_STATUS_INCOMPLETE)
                e.statuses.append(f"missing:{','.join(sorted(missing))}")

    # Duplicate detection: same (mission, sensing_date, orbit, tile) but a
    # different product_id string (i.e. a different baseline/processing run).
    by_dup_group: dict[tuple, set[str]] = defaultdict(set)
    for e in entries:
        if e.source != "sentinel2" or not e.product_id:
            continue
        parsed = parse_object_key(e.key)
        dup_key = parsed.duplicate_group_key
        if dup_key:
            by_dup_group[dup_key].add(e.product_id)

    duplicate_product_ids: set[str] = {pid for pids in by_dup_group.values() if len(pids) > 1 for pid in pids}
    if duplicate_product_ids:
        for e in entries:
            if e.product_id in duplicate_product_ids:
                e.statuses.append(_STATUS_DUPLICATE)

    return entries


def recommended_product_id(entries: list[InventoryEntry], duplicate_group_key_entries: list[InventoryEntry]) -> str | None:
    """Among a group of duplicate entries (same acquisition, different
    processing runs), recommend the complete one with the highest baseline
    (then latest processing date) — never implies deleting the others.
    """
    candidates = [e for e in duplicate_group_key_entries if _STATUS_OK in e.statuses]
    pool = candidates or duplicate_group_key_entries
    best = max(pool, key=lambda e: (e.processing_baseline or "", e.processing_date or ""))
    return best.product_id


def _atomic_write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".part")
    with tmp_path.open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def write_inventory_manifest(entries: list[InventoryEntry]) -> Path:
    path = resolve_path("data.manifests") / "b2_inventory.jsonl"
    _atomic_write_jsonl(path, [e.to_json_dict() for e in entries])
    return path


def generate_report(entries: list[InventoryEntry]) -> str:
    total_bytes = sum(e.size_bytes for e in entries)
    total_gb = total_bytes / (1024**3)

    by_source: Counter[str] = Counter(e.source for e in entries)
    by_tile: Counter[str] = Counter(e.tile for e in entries if e.tile)

    duplicates = [e for e in entries if _STATUS_DUPLICATE in e.statuses]
    incomplete = [e for e in entries if _STATUS_INCOMPLETE in e.statuses]
    suspect = [e for e in entries if _STATUS_SUSPECT_SIZE in e.statuses]
    unknown = [e for e in entries if _STATUS_UNKNOWN in e.statuses]

    lines = [
        "# B2 Inventory Report (Phase 2, Part 2.1)",
        "",
        f"**Total objects:** {len(entries)}",
        f"**Total size:** {total_gb:.3f} GB (expected ~{EXPECTED_TOTAL_GB} GB per plan.md — "
        f"{'within range' if total_gb <= EXPECTED_TOTAL_GB * 1.1 else 'EXCEEDS expectation, investigate'})",
        "",
        "## By source",
        "",
    ]
    for source, count in sorted(by_source.items()):
        lines.append(f"- `{source}`: {count} object(s)")

    lines += ["", "## By tile", ""]
    if by_tile:
        for tile, count in sorted(by_tile.items()):
            lines.append(f"- `{tile}`: {count} object(s)")
    else:
        lines.append("_(no tiles identified)_")

    lines += ["", "## By source + format (size breakdown)", ""]
    by_format: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for e in entries:
        bucket_key = (e.source, e.format)
        by_format[bucket_key][0] += 1
        by_format[bucket_key][1] += e.size_bytes
    for (source, fmt), (count, size_bytes) in sorted(by_format.items()):
        lines.append(f"- `{source}/{fmt}`: {count} object(s), {size_bytes / (1024**3):.2f} GB")

    lines += ["", "## Duplicates (flagged only — nothing deleted)", ""]
    if duplicates:
        by_group: dict[tuple, list[InventoryEntry]] = defaultdict(list)
        for e in duplicates:
            parsed = parse_object_key(e.key)
            by_group[parsed.duplicate_group_key].append(e)
        for group_key, group_entries in by_group.items():
            product_ids = sorted({e.product_id for e in group_entries})
            recommended = recommended_product_id(entries, group_entries)
            lines.append(f"- tile/orbit/date `{group_key}`: {len(product_ids)} versions {product_ids} — recommend `{recommended}`")
    else:
        lines.append("_(none found)_")

    lines += ["", "## Incomplete products (excluded from use unless re-fetched)", ""]
    if incomplete:
        seen = set()
        for e in incomplete:
            if e.product_id in seen:
                continue
            seen.add(e.product_id)
            missing_tag = next((s for s in e.statuses if s.startswith("missing:")), "")
            lines.append(f"- `{e.product_id}` ({missing_tag})")
    else:
        lines.append("_(none found)_")

    lines += ["", "## Suspect size (zero-byte or < 100 bytes)", ""]
    if suspect:
        for e in suspect:
            lines.append(f"- `{e.key}` ({e.size_bytes} bytes)")
    else:
        lines.append("_(none found)_")

    lines += ["", "## Unknown / junk (never marked for deletion)", ""]
    if unknown:
        for e in unknown:
            lines.append(f"- `{e.key}`")
    else:
        lines.append("_(none found)_")

    raw_zip_entries = [e for e in entries if e.source == "sentinel2" and e.format == "zip"]
    raw_zip_gb = sum(e.size_bytes for e in raw_zip_entries) / (1024**3)
    raw_zip_years = sorted({e.sensing_date[:4] for e in raw_zip_entries if e.sensing_date})

    lines += [
        "",
        "## Assumption check (plan.md A1–A5)",
        "",
        f"- **A1** (raw data already in B2): {'CONFIRMED' if raw_zip_entries else 'NOT CONFIRMED'} — "
        f"{len(raw_zip_entries)} raw `.SAFE.zip` archive(s) totaling {raw_zip_gb:.2f} GB found under "
        f"`data/raw/sentinel2/`, covering years {raw_zip_years or 'none'}.",
        f"- **A4** (SAFE vs zip format): raw archives are stored as whole zipped `.SAFE.zip` files "
        "(not unzipped `.SAFE` folders, not bare `.zip`) — this decides the Phase 3 read strategy "
        "(ADR-001): either extract to staging first, or read directly from the zip via GDAL's /vsizip/.",
        "",
    ]

    return "\n".join(lines)


def write_report(entries: list[InventoryEntry]) -> Path:
    path = resolve_path("results") / "phase2" / "inventory_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_report(entries))
    return path


def run_inventory(backend, prefix: str = "") -> dict[str, Any]:
    """Orchestrates list -> classify -> write manifest -> write report.
    Read-only end to end. Returns a small summary dict for the caller.
    """
    entries = list_inventory(backend, prefix=prefix)
    entries = classify_inventory(entries)
    manifest_path = write_inventory_manifest(entries)
    report_path = write_report(entries)
    return {
        "entry_count": len(entries),
        "total_bytes": sum(e.size_bytes for e in entries),
        "manifest_path": manifest_path,
        "report_path": report_path,
    }
