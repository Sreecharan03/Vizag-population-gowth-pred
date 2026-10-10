"""Phase 2 Part 2.3: integrity audit of existing data (cheap only).

Verifies raw Sentinel-2 .SAFE.zip archives are complete (all 6 required
bands + SCL + top-level metadata present) by reading ONLY the zip's
central directory via HTTP range requests — never downloading the archive
content. Never re-hashes the full ~183 GB raw archive (plan.md's explicit
instruction: "do not download 190 GB to hash it; deeper verification
happens lazily at first read in Phase 3").

Also records B2's ETag per object (a checksum B2 already exposes) as a
drift-detection fingerprint — not a content-verification check, since
multipart-uploaded objects' ETags aren't plain MD5s and there's no
independent second copy to compare against yet.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from src.utils.io import resolve_path

REQUIRED_BAND_CODES = ("B02", "B03", "B04", "B08", "B11", "B12")
REQUIRED_SCL_MARKER = "SCL"

DEFAULT_MIN_SCENE_BYTES = 20 * 1024 * 1024  # 20 MB — far below any real full scene
DEFAULT_MAX_SCENE_BYTES = 3 * 1024 * 1024 * 1024  # 3 GB — generous upper bound


class _RangeReadFile:
    """A minimal seekable/readable file-like object backed by a storage
    backend's open_range(), so zipfile can read just the central directory
    (near the end of the file) without downloading the archive content.
    """

    def __init__(self, backend, key: str, size: int):
        self._backend = backend
        self._key = key
        self._size = size
        self._pos = 0

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._size + offset
        else:
            raise ValueError(f"invalid whence: {whence}")
        return self._pos

    def tell(self) -> int:
        return self._pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self._size - self._pos
        n = max(0, min(n, self._size - self._pos))
        data = self._backend.open_range(self._key, self._pos, n)
        self._pos += len(data)
        return data

    def seekable(self) -> bool:
        return True


def check_zip_band_completeness(backend, key: str, size_bytes: int) -> dict[str, Any]:
    """Returns band-completeness info for a raw .SAFE.zip, reading only the
    zip's central directory (cheap). Never raises on a corrupt zip —
    returns status="CORRUPT" instead, so a batch audit can continue.
    """
    try:
        range_file = _RangeReadFile(backend, key, size_bytes)
        with zipfile.ZipFile(range_file) as zf:
            names = zf.namelist()
    except zipfile.BadZipFile as e:
        return {
            "status": "CORRUPT",
            "error": str(e),
            "missing_bands": list(REQUIRED_BAND_CODES) + [REQUIRED_SCL_MARKER],
            "has_metadata": False,
            "entry_count": 0,
        }

    img_data_names = [n for n in names if "/IMG_DATA/" in n and n.endswith(".jp2")]
    missing = [band for band in REQUIRED_BAND_CODES if not any(f"_{band}_" in n for n in img_data_names)]
    if not any(f"_{REQUIRED_SCL_MARKER}_" in n for n in img_data_names):
        missing.append(REQUIRED_SCL_MARKER)

    has_metadata = any(n.endswith("MTD_MSIL2A.xml") for n in names)

    status = "OK" if not missing and has_metadata else "INCOMPLETE"
    return {
        "status": status,
        "missing_bands": missing,
        "has_metadata": has_metadata,
        "entry_count": len(names),
    }


def check_size_sanity(
    size_bytes: int, *, min_bytes: int = DEFAULT_MIN_SCENE_BYTES, max_bytes: int = DEFAULT_MAX_SCENE_BYTES
) -> bool:
    return min_bytes <= size_bytes <= max_bytes


def audit_scene(
    backend,
    entry: dict[str, Any],
    *,
    min_bytes: int = DEFAULT_MIN_SCENE_BYTES,
    max_bytes: int = DEFAULT_MAX_SCENE_BYTES,
) -> dict[str, Any]:
    """Audits one raw-scene inventory entry: size sanity, zip band
    completeness, and the B2 ETag (recorded, not verified against
    anything). Catches any backend/network error so one bad scene doesn't
    abort the whole batch — matches plan.md's "unit fails, batch
    continues" pattern.
    """
    key = entry["key"]
    size_bytes = entry["size_bytes"]
    result: dict[str, Any] = {"key": key, "tile": entry.get("tile"), "epoch": entry.get("sensing_date", "")[:4]}

    result["size_ok"] = check_size_sanity(size_bytes, min_bytes=min_bytes, max_bytes=max_bytes)
    result["size_bytes"] = size_bytes

    try:
        result["etag"] = backend.stat(key).etag
    except Exception:
        result["etag"] = None

    try:
        completeness = check_zip_band_completeness(backend, key, size_bytes)
    except Exception as e:
        completeness = {
            "status": "ERROR",
            "error": str(e),
            "missing_bands": [],
            "has_metadata": False,
            "entry_count": 0,
        }
    result.update(completeness)

    result["overall_status"] = "OK" if result["size_ok"] and completeness["status"] == "OK" else "FAILED"
    return result


def run_integrity_audit(
    backend,
    inventory: list[dict[str, Any]],
    required_tiles: list[str],
    *,
    min_bytes: int = DEFAULT_MIN_SCENE_BYTES,
    max_bytes: int = DEFAULT_MAX_SCENE_BYTES,
) -> dict[str, Any]:
    """Audits every raw .SAFE.zip scene belonging to a required tile.
    Scoped to required tiles only (not the extra tiles also present in
    B2) — read only what's needed, per plan.md Section 1A.4.
    """
    required_set = set(required_tiles)
    scenes = [
        e
        for e in inventory
        if e.get("source") == "sentinel2" and e.get("format") == "zip" and e.get("tile") in required_set
    ]

    results = [audit_scene(backend, e, min_bytes=min_bytes, max_bytes=max_bytes) for e in scenes]

    ok_count = sum(1 for r in results if r["overall_status"] == "OK")
    failed = [r for r in results if r["overall_status"] != "OK"]

    report = _generate_report(results, ok_count, failed, required_tiles)
    report_path = write_integrity_report(report)

    return {
        "audited_count": len(results),
        "ok_count": ok_count,
        "failed_count": len(failed),
        "results": results,
        "report_path": report_path,
    }


def _generate_report(
    results: list[dict[str, Any]], ok_count: int, failed: list[dict[str, Any]], required_tiles: list[str]
) -> str:
    lines = [
        "# Integrity Audit Report (Phase 2, Part 2.3)",
        "",
        f"Scope: raw `.SAFE.zip` scenes for required tile(s) {required_tiles} only "
        "(extra tiles already in B2 are not audited — not needed yet).",
        "",
        f"**Audited:** {len(results)} scene(s). **OK:** {ok_count}. **Failed:** {len(failed)}.",
        "",
        "Method: zip central-directory read via HTTP range requests only — no scene content was "
        "downloaded. Size sanity checked against a generous plausible range. B2's ETag is recorded "
        "per scene as a future drift-detection fingerprint, not verified against an independent copy "
        "(multipart-uploaded ETags aren't plain content MD5s).",
        "",
        "## Failed scenes",
        "",
    ]
    if failed:
        for r in failed:
            reason = r.get("error") or f"missing: {r.get('missing_bands')}" or "size out of range"
            lines.append(f"- `{r['key']}` — {r['status']} ({reason})")
    else:
        lines.append("_(none — every audited scene has all 6 bands + SCL + metadata, and a sane size)_")

    return "\n".join(lines)


def write_integrity_report(content: str) -> Path:
    path = resolve_path("results") / "phase2" / "integrity_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path
