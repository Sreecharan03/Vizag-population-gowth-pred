"""Phase 3 Part 3.0: read-strategy benchmark.

Compares two strategies for reading Sentinel-2 bands out of the raw
.SAFE.zip archives in B2 — must happen before any other Phase 3 work,
per plan.md, since it decides how every later step reads imagery:

  (a) fetch-to-staging: download the whole zip via the backend
      abstraction, then read bands from the local copy via GDAL's
      /vsizip/ virtual filesystem
  (b) direct-remote: read bands straight out of the remote zip via
      /vsizip/vsis3/ — HTTP range requests only, the archive's full
      content is never downloaded

Measures wall time, bytes transferred, request count, and peak staging
disk for each, on real scenes, so the choice is evidence-based.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from src.acquisition.integrity import list_zip_contents
from src.utils.io import resolve_path

REQUIRED_BAND_CODES = ("B02", "B03", "B04", "B08", "B11", "B12", "SCL")


def build_vsizip_path(local_zip_path: "str | Path", inner_path: str) -> str:
    """GDAL virtual path to read `inner_path` out of a LOCAL zip file."""
    return f"/vsizip/{local_zip_path}/{inner_path}"


def build_vsizip_vsis3_path(bucket: str, zip_key: str, inner_path: str) -> str:
    """GDAL virtual path to read `inner_path` out of a REMOTE zip in an
    S3-compatible bucket, via HTTP range requests only.
    """
    return f"/vsizip/vsis3/{bucket}/{zip_key}/{inner_path}"


def find_band_inner_paths(backend, zip_key: str, size_bytes: int) -> dict[str, str]:
    """Resolves each required band's full path inside the zip (the
    GRANULE directory name varies per scene) by listing the central
    directory only — no content download.
    """
    names = list_zip_contents(backend, zip_key, size_bytes)
    img_data_names = [n for n in names if "/IMG_DATA/" in n and n.endswith(".jp2")]

    resolved: dict[str, str] = {}
    for band in REQUIRED_BAND_CODES:
        match = next((n for n in img_data_names if f"_{band}_" in n), None)
        if match:
            resolved[band] = match
    return resolved


@contextmanager
def vsis3_credentials(key_id: str, application_key: str, endpoint: str) -> Iterator[None]:
    """Temporarily sets the GDAL/AWS env vars /vsis3/ needs for a non-AWS
    S3-compatible endpoint (B2). Restores whatever was there before on
    exit — never leaves credentials sitting in the environment longer
    than the read itself needs.
    """
    overrides = {
        "AWS_ACCESS_KEY_ID": key_id,
        "AWS_SECRET_ACCESS_KEY": application_key,
        "AWS_S3_ENDPOINT": endpoint,
        "AWS_VIRTUAL_HOSTING": "FALSE",
        "AWS_HTTPS": "YES",
        "GDAL_DISABLE_READDIR_ON_OPEN": "YES",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".jp2,.zip",
    }
    previous = {k: os.environ.get(k) for k in overrides}
    try:
        os.environ.update(overrides)
        yield
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


_CONTENT_RANGE_RE = re.compile(r"Content-Range:\s*bytes\s+(\d+)-(\d+)/(\d+)")
_GET_REQUEST_RE = re.compile(r"^> GET ", re.MULTILINE)


def parse_curl_verbose_log(log_text: str) -> dict[str, int]:
    """Pure function: parses libcurl's verbose output (CPL_CURL_VERBOSE=YES)
    and returns {"request_count": N, "bytes_transferred": total}. Counts
    actual HTTP requests issued and sums the real byte ranges returned
    (Content-Range headers) — not the full target file's size.
    """
    request_count = len(_GET_REQUEST_RE.findall(log_text))
    bytes_transferred = sum(end - start + 1 for start, end, _total in (
        (int(g) for g in m.groups()) for m in _CONTENT_RANGE_RE.finditer(log_text)
    ))
    return {"request_count": request_count, "bytes_transferred": bytes_transferred}


def fetch_to_staging(backend, zip_key: str, dest_dir: Path) -> dict[str, Any]:
    """Strategy (a), step 1: downloads the full zip via the backend
    abstraction. Stats use the backend's known Content-Length — exactly
    what gets transferred for a whole-object GET.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / Path(zip_key).name

    info = backend.stat(zip_key)
    t0 = time.monotonic()
    backend.download(zip_key, dest_path)
    elapsed = time.monotonic() - t0

    return {
        "local_path": dest_path,
        "elapsed_s": elapsed,
        "bytes_transferred": info.size_bytes,
        "request_count": 1,
        "peak_staging_bytes": dest_path.stat().st_size,
    }


def read_band_window_local(local_zip_path: Path, inner_path: str, window) -> dict[str, Any]:
    """Strategy (a), step 2: windowed read from the now-local zip via
    /vsizip/ — no network at all at this point.
    """
    import rasterio

    vsi_path = build_vsizip_path(local_zip_path, inner_path)
    t0 = time.monotonic()
    with rasterio.open(vsi_path) as src:
        data = src.read(1, window=window)
    elapsed = time.monotonic() - t0
    return {"elapsed_s": elapsed, "shape": data.shape}


def read_band_window_remote(
    bucket: str,
    zip_key: str,
    inner_path: str,
    window,
    *,
    key_id: str,
    application_key: str,
    endpoint: str,
) -> dict[str, Any]:
    """Strategy (b): windowed read straight from the remote zip via
    /vsizip/vsis3/ — HTTP range requests only, never a full download.
    Measures real bytes transferred and request count by capturing
    libcurl's verbose log at the OS file-descriptor level (GDAL's
    CPL_CURL_VERBOSE writes directly to the process's stderr fd, not
    through Python's logging/stdout — this is the only reliable way to
    capture it without a separate GDAL Python binding).

    Not exercised by the unit test suite (needs a real network + real B2
    credentials) — only `parse_curl_verbose_log`'s parsing logic is unit
    tested directly. This function is run manually against real scenes
    for the actual benchmark.
    """
    import rasterio

    vsi_path = build_vsizip_vsis3_path(bucket, zip_key, inner_path)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        log_path = f.name

    saved_stderr_fd = os.dup(2)
    log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    try:
        os.dup2(log_fd, 2)
        os.close(log_fd)
        os.environ["CPL_CURL_VERBOSE"] = "YES"

        t0 = time.monotonic()
        with vsis3_credentials(key_id, application_key, endpoint):
            with rasterio.open(vsi_path) as src:
                data = src.read(1, window=window)
        elapsed = time.monotonic() - t0
    finally:
        os.dup2(saved_stderr_fd, 2)
        os.close(saved_stderr_fd)
        os.environ.pop("CPL_CURL_VERBOSE", None)

    log_text = Path(log_path).read_text(errors="ignore")
    Path(log_path).unlink(missing_ok=True)
    stats = parse_curl_verbose_log(log_text)

    return {"elapsed_s": elapsed, "shape": data.shape, **stats}


def run_benchmark(
    backend,
    bucket: str,
    scene_keys: list[str],
    window,
    *,
    staging_dir: Path,
    key_id: str,
    application_key: str,
    endpoint: str,
) -> dict[str, Any]:
    """Runs both strategies for each scene (one representative band, B02,
    is enough to compare the mechanisms — all bands follow the same
    read path). Staging is cleared after each scene's strategy-(a)
    measurement (golden rule #5: one unit of work at a time, staging
    emptied after).
    """
    results: dict[str, list[dict[str, Any]]] = {"strategy_a": [], "strategy_b": []}

    for scene_key in scene_keys:
        info = backend.stat(scene_key)
        inner_paths = find_band_inner_paths(backend, scene_key, info.size_bytes)
        inner_path = inner_paths.get("B02")
        if not inner_path:
            continue

        fetch_stats = fetch_to_staging(backend, scene_key, staging_dir)
        read_stats = read_band_window_local(fetch_stats["local_path"], inner_path, window)
        results["strategy_a"].append(
            {
                "scene": scene_key,
                "elapsed_s": fetch_stats["elapsed_s"] + read_stats["elapsed_s"],
                "bytes_transferred": fetch_stats["bytes_transferred"],
                "request_count": fetch_stats["request_count"],
                "peak_staging_bytes": fetch_stats["peak_staging_bytes"],
            }
        )
        fetch_stats["local_path"].unlink()  # staging cleared after each unit

        remote_stats = read_band_window_remote(
            bucket, scene_key, inner_path, window, key_id=key_id, application_key=application_key, endpoint=endpoint
        )
        results["strategy_b"].append(
            {
                "scene": scene_key,
                "elapsed_s": remote_stats["elapsed_s"],
                "bytes_transferred": remote_stats["bytes_transferred"],
                "request_count": remote_stats["request_count"],
                "peak_staging_bytes": 0,
            }
        )

    return results


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def generate_benchmark_report(results: dict[str, list[dict[str, Any]]]) -> str:
    a, b = results["strategy_a"], results["strategy_b"]
    lines = [
        "# Read-Strategy Benchmark (Phase 3, Part 3.0)",
        "",
        f"Scenes benchmarked: {len(a)}",
        "",
        "## Strategy (a): fetch-to-staging",
        "",
        f"- Avg wall time: {_avg([r['elapsed_s'] for r in a]):.2f} s",
        f"- Avg bytes transferred: {_avg([r['bytes_transferred'] for r in a]) / (1024**2):.1f} MB",
        f"- Avg request count: {_avg([r['request_count'] for r in a]):.1f}",
        f"- Avg peak staging disk: {_avg([r['peak_staging_bytes'] for r in a]) / (1024**2):.1f} MB",
        "",
        "## Strategy (b): direct remote windowed read (/vsizip/vsis3/)",
        "",
        f"- Avg wall time: {_avg([r['elapsed_s'] for r in b]):.2f} s",
        f"- Avg bytes transferred: {_avg([r['bytes_transferred'] for r in b]) / (1024**2):.2f} MB",
        f"- Avg request count: {_avg([r['request_count'] for r in b]):.1f}",
        f"- Avg peak staging disk: {_avg([r['peak_staging_bytes'] for r in b]) / (1024**2):.1f} MB",
        "",
        "## Per-scene detail",
        "",
    ]
    for ra, rb in zip(a, b):
        lines.append(
            f"- `{ra['scene']}`: (a) {ra['elapsed_s']:.2f}s / {ra['bytes_transferred']/(1024**2):.1f} MB / "
            f"{ra['request_count']} req vs (b) {rb['elapsed_s']:.2f}s / {rb['bytes_transferred']/(1024**2):.2f} MB / "
            f"{rb['request_count']} req"
        )
    return "\n".join(lines)


def write_benchmark_report(content: str) -> Path:
    path = resolve_path("results") / "phase3" / "read_benchmark.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def write_adr(decision: str, rationale: str) -> Path:
    content = f"""# ADR-001: Sentinel-2 Read Strategy

## Decision

{decision}

## Rationale

{rationale}

## Status

Accepted — {time.strftime("%Y-%m-%d")}

See `results/phase3/read_benchmark.md` for the measurements this decision is based on.
"""
    path = resolve_path("docs.decisions") / "ADR-001-read-strategy.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path
