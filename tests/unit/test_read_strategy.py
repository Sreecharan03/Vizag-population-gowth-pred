from __future__ import annotations

import io
import os
import zipfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

from src.preprocessing.read_strategy import (
    build_vsizip_path,
    build_vsizip_vsis3_path,
    fetch_to_staging,
    find_band_inner_paths,
    generate_benchmark_report,
    parse_curl_verbose_log,
    read_band_window_local,
    vsis3_credentials,
    write_adr,
    write_benchmark_report,
)
from src.storage.backends import FakeBackend

_GRANULE_PREFIX = "S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE/GRANULE/L2A_T44QPE_A013229_20180103T050148/IMG_DATA"

# A real libcurl verbose log excerpt (format matches what CPL_CURL_VERBOSE=YES
# actually produces — captured from a real run against B2 during Part 3.0).
_SAMPLE_CURL_LOG = """\
* Host s3.us-east-005.backblazeb2.com:443 was resolved.
> GET /satilliate-images/vizag-geoai/data/raw/sentinel2/2018/scene.SAFE.zip HTTP/1.1
Range: bytes=0-16383
< HTTP/1.1 206
< Content-Range: bytes 0-16383/125743775
> GET /satilliate-images/vizag-geoai/data/raw/sentinel2/2018/scene.SAFE.zip HTTP/1.1
Range: bytes=125730816-125743774
< HTTP/1.1 206
< Content-Range: bytes 125730816-125743774/125743775
"""


# --- pure path builders -------------------------------------------------------


def test_build_vsizip_path():
    assert build_vsizip_path("/tmp/scene.zip", "inner/band.jp2") == "/vsizip//tmp/scene.zip/inner/band.jp2"


def test_build_vsizip_vsis3_path():
    path = build_vsizip_vsis3_path("my-bucket", "data/scene.zip", "inner/band.jp2")
    assert path == "/vsizip/vsis3/my-bucket/data/scene.zip/inner/band.jp2"


# --- parse_curl_verbose_log (the core measurement logic) ---------------------


def test_parse_curl_verbose_log_counts_requests_and_bytes():
    stats = parse_curl_verbose_log(_SAMPLE_CURL_LOG)
    assert stats["request_count"] == 2
    # 16384 bytes from the first range + 12959 bytes from the second
    assert stats["bytes_transferred"] == 16384 + (125743774 - 125730816 + 1)


def test_parse_curl_verbose_log_empty_text():
    stats = parse_curl_verbose_log("")
    assert stats == {"request_count": 0, "bytes_transferred": 0}


def test_parse_curl_verbose_log_ignores_non_range_lines():
    log = "* some unrelated debug line\n* another one\n"
    stats = parse_curl_verbose_log(log)
    assert stats["request_count"] == 0
    assert stats["bytes_transferred"] == 0


# --- vsis3_credentials ---------------------------------------------------------


def test_vsis3_credentials_sets_and_restores_env(monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    with vsis3_credentials("key123", "secret456", "s3.example.com"):
        assert os.environ["AWS_ACCESS_KEY_ID"] == "key123"
        assert os.environ["AWS_S3_ENDPOINT"] == "s3.example.com"
        assert os.environ["AWS_VIRTUAL_HOSTING"] == "FALSE"
    assert "AWS_ACCESS_KEY_ID" not in os.environ


def test_vsis3_credentials_restores_previous_value(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "original")
    with vsis3_credentials("key123", "secret456", "s3.example.com"):
        assert os.environ["AWS_ACCESS_KEY_ID"] == "key123"
    assert os.environ["AWS_ACCESS_KEY_ID"] == "original"


# --- find_band_inner_paths -----------------------------------------------------


def _build_fake_safe_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for band, res in [("B02", "10m"), ("B03", "10m"), ("B04", "10m"), ("B08", "10m"), ("B11", "20m"), ("B12", "20m"), ("SCL", "20m")]:
            zf.writestr(f"{_GRANULE_PREFIX}/R{res}/T44QPE_20180103T045201_{band}_{res}.jp2", b"fakejp2")
        zf.writestr("S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE/MTD_MSIL2A.xml", b"<xml/>")
    return buf.getvalue()


def test_find_band_inner_paths_resolves_all_bands():
    backend = FakeBackend()
    data = _build_fake_safe_zip()
    backend.seed("scene.zip", data)

    paths = find_band_inner_paths(backend, "scene.zip", len(data))
    assert set(paths.keys()) == {"B02", "B03", "B04", "B08", "B11", "B12", "SCL"}
    assert paths["B02"].endswith("_B02_10m.jp2")


# --- fetch_to_staging ------------------------------------------------------------


def test_fetch_to_staging_downloads_and_reports_stats(tmp_path):
    backend = FakeBackend()
    data = b"x" * 5000
    backend.seed("scene.zip", data)

    stats = fetch_to_staging(backend, "scene.zip", tmp_path)
    assert stats["local_path"].exists()
    assert stats["local_path"].read_bytes() == data
    assert stats["bytes_transferred"] == 5000
    assert stats["request_count"] == 1
    assert stats["peak_staging_bytes"] == 5000


# --- read_band_window_local (real local zip+raster, no network) --------------


def test_read_band_window_local_reads_correct_window(tmp_path):
    inner_tif = tmp_path / "band.tif"
    data = np.arange(400, dtype="uint16").reshape(20, 20)
    transform = from_origin(83.0, 18.0, 10, 10)
    with rasterio.open(
        inner_tif, "w", driver="GTiff", height=20, width=20, count=1, dtype="uint16", crs="EPSG:32644", transform=transform
    ) as dst:
        dst.write(data, 1)

    zip_path = tmp_path / "scene.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(inner_tif, arcname="inner/band.tif")

    stats = read_band_window_local(zip_path, "inner/band.tif", window=((0, 5), (0, 5)))
    assert stats["shape"] == (5, 5)


# --- report generation ----------------------------------------------------------


def _fake_results():
    return {
        "strategy_a": [
            {"scene": "s1", "elapsed_s": 2.5, "bytes_transferred": 500_000_000, "request_count": 1, "peak_staging_bytes": 500_000_000}
        ],
        "strategy_b": [
            {"scene": "s1", "elapsed_s": 0.3, "bytes_transferred": 200_000, "request_count": 4, "peak_staging_bytes": 0}
        ],
    }


def test_generate_benchmark_report_contains_both_strategies():
    report = generate_benchmark_report(_fake_results())
    assert "# Read-Strategy Benchmark" in report
    assert "Strategy (a): fetch-to-staging" in report
    assert "Strategy (b): direct remote windowed read" in report
    assert "s1" in report


def test_write_benchmark_report_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("src.preprocessing.read_strategy.resolve_path", lambda key: tmp_path)
    path = write_benchmark_report("# test content\n")
    assert path == tmp_path / "phase3" / "read_benchmark.md"
    assert path.read_text() == "# test content\n"


def test_write_adr_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("src.preprocessing.read_strategy.resolve_path", lambda key: tmp_path)
    path = write_adr("Use strategy (b)", "It transfers far fewer bytes.")
    assert path == tmp_path / "ADR-001-read-strategy.md"
    content = path.read_text()
    assert "Use strategy (b)" in content
    assert "It transfers far fewer bytes." in content
