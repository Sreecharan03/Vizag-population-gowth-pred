from __future__ import annotations

import io
import zipfile

from src.acquisition.integrity import (
    DEFAULT_MAX_SCENE_BYTES,
    DEFAULT_MIN_SCENE_BYTES,
    audit_scene,
    check_size_sanity,
    check_zip_band_completeness,
    list_zip_contents,
    run_integrity_audit,
)
from src.storage.backends import FakeBackend

_ALL_BANDS = ("B02", "B03", "B04", "B08", "B11", "B12")


def _build_fake_safe_zip(bands=_ALL_BANDS, include_scl=True, include_metadata=True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        base = "FAKE_PRODUCT.SAFE/GRANULE/L2A_FAKE/IMG_DATA"
        for b in bands:
            res = "10m" if b in ("B02", "B03", "B04", "B08") else "20m"
            zf.writestr(f"{base}/R{res}/T99XXX_20180101T000000_{b}_{res}.jp2", b"fake jp2 bytes")
        if include_scl:
            zf.writestr(f"{base}/R20m/T99XXX_20180101T000000_SCL_20m.jp2", b"fake scl bytes")
        if include_metadata:
            zf.writestr("FAKE_PRODUCT.SAFE/MTD_MSIL2A.xml", b"<xml/>")
    return buf.getvalue()


def _seeded_entry(backend: FakeBackend, key: str, data: bytes) -> dict:
    backend.seed(key, data)
    return {
        "key": key,
        "size_bytes": len(data),
        "source": "sentinel2",
        "format": "zip",
        "tile": "T44QQE",
        "sensing_date": "20180101T000000",
    }


# --- check_size_sanity --------------------------------------------------------


def test_check_size_sanity_within_range():
    assert check_size_sanity(500 * 1024 * 1024)


def test_check_size_sanity_too_small():
    assert not check_size_sanity(100)


def test_check_size_sanity_too_large():
    assert not check_size_sanity(DEFAULT_MAX_SCENE_BYTES + 1)


def test_check_size_sanity_boundary_values():
    assert check_size_sanity(DEFAULT_MIN_SCENE_BYTES)
    assert check_size_sanity(DEFAULT_MAX_SCENE_BYTES)


# --- check_zip_band_completeness ----------------------------------------------


def test_check_zip_band_completeness_all_present():
    backend = FakeBackend()
    data = _build_fake_safe_zip()
    backend.seed("fake.zip", data)

    result = check_zip_band_completeness(backend, "fake.zip", len(data))
    assert result["status"] == "OK"
    assert result["missing_bands"] == []
    assert result["has_metadata"] is True


def test_check_zip_band_completeness_missing_band():
    backend = FakeBackend()
    data = _build_fake_safe_zip(bands=("B02", "B03", "B04", "B08", "B11"))  # B12 missing
    backend.seed("fake.zip", data)

    result = check_zip_band_completeness(backend, "fake.zip", len(data))
    assert result["status"] == "INCOMPLETE"
    assert result["missing_bands"] == ["B12"]


def test_check_zip_band_completeness_missing_scl():
    backend = FakeBackend()
    data = _build_fake_safe_zip(include_scl=False)
    backend.seed("fake.zip", data)

    result = check_zip_band_completeness(backend, "fake.zip", len(data))
    assert result["status"] == "INCOMPLETE"
    assert "SCL" in result["missing_bands"]


def test_check_zip_band_completeness_missing_metadata():
    backend = FakeBackend()
    data = _build_fake_safe_zip(include_metadata=False)
    backend.seed("fake.zip", data)

    result = check_zip_band_completeness(backend, "fake.zip", len(data))
    assert result["status"] == "INCOMPLETE"
    assert result["has_metadata"] is False


def test_check_zip_band_completeness_corrupt_zip():
    backend = FakeBackend()
    garbage = b"this is not a zip file at all" * 100
    backend.seed("corrupt.zip", garbage)

    result = check_zip_band_completeness(backend, "corrupt.zip", len(garbage))
    assert result["status"] == "CORRUPT"
    assert set(result["missing_bands"]) == set(_ALL_BANDS) | {"SCL"}


def test_list_zip_contents_returns_all_names():
    backend = FakeBackend()
    data = _build_fake_safe_zip()
    backend.seed("fake.zip", data)

    names = list_zip_contents(backend, "fake.zip", len(data))
    assert any(n.endswith("MTD_MSIL2A.xml") for n in names)
    assert any("_B02_" in n for n in names)


def test_list_zip_contents_raises_on_corrupt_zip():
    import pytest

    backend = FakeBackend()
    garbage = b"not a zip" * 100
    backend.seed("corrupt.zip", garbage)

    with pytest.raises(zipfile.BadZipFile):
        list_zip_contents(backend, "corrupt.zip", len(garbage))


def test_check_zip_band_completeness_reads_only_central_directory_not_full_content():
    backend = FakeBackend()
    # Make the fake "band" content large to prove we don't download it all.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        base = "FAKE.SAFE/GRANULE/L2A_FAKE/IMG_DATA"
        for b in _ALL_BANDS:
            res = "10m" if b in ("B02", "B03", "B04", "B08") else "20m"
            zf.writestr(f"{base}/R{res}/X_{b}_{res}.jp2", b"X" * 200_000)  # 200KB "fake" band each
        zf.writestr(f"{base}/R20m/X_SCL_20m.jp2", b"X" * 200_000)
        zf.writestr("FAKE.SAFE/MTD_MSIL2A.xml", b"<xml/>")
    data = buf.getvalue()
    backend.seed("fake.zip", data)

    check_zip_band_completeness(backend, "fake.zip", len(data))
    # zipfile only needs the end-of-central-directory + central directory,
    # not the ~1.4MB of "band" content — must transfer well under the full size.
    assert backend.bytes_transferred < len(data) // 2


# --- audit_scene ---------------------------------------------------------------


def test_audit_scene_ok():
    backend = FakeBackend()
    data = _build_fake_safe_zip()
    entry = _seeded_entry(backend, "scene.zip", data)

    result = audit_scene(backend, entry, min_bytes=10, max_bytes=10_000_000)
    assert result["overall_status"] == "OK"
    assert result["size_ok"] is True


def test_audit_scene_failed_when_incomplete():
    backend = FakeBackend()
    data = _build_fake_safe_zip(bands=("B02", "B03"))  # several bands missing
    entry = _seeded_entry(backend, "scene.zip", data)

    result = audit_scene(backend, entry)
    assert result["overall_status"] == "FAILED"


def test_audit_scene_failed_when_size_implausible():
    backend = FakeBackend()
    data = b"too small"
    entry = _seeded_entry(backend, "scene.zip", data)

    result = audit_scene(backend, entry)
    assert result["overall_status"] == "FAILED"
    assert result["size_ok"] is False


# --- run_integrity_audit --------------------------------------------------------


def test_run_integrity_audit_scopes_to_required_tiles_only(tmp_path, monkeypatch):
    monkeypatch.setattr("src.acquisition.integrity.resolve_path", lambda key: tmp_path)
    backend = FakeBackend()
    ok_data = _build_fake_safe_zip()

    inventory = [
        _seeded_entry(backend, "required_tile.zip", ok_data),
    ]
    extra_entry = dict(_seeded_entry(backend, "extra_tile.zip", ok_data))
    extra_entry["tile"] = "T44QPE"  # not in required_tiles
    inventory.append(extra_entry)

    result = run_integrity_audit(backend, inventory, required_tiles=["T44QQE"], min_bytes=10, max_bytes=10_000_000)

    assert result["audited_count"] == 1  # only the required-tile scene
    assert result["ok_count"] == 1
    assert result["failed_count"] == 0
    assert result["report_path"].exists()
    assert "Integrity Audit Report" in result["report_path"].read_text()


def test_run_integrity_audit_reports_failures(tmp_path, monkeypatch):
    monkeypatch.setattr("src.acquisition.integrity.resolve_path", lambda key: tmp_path)
    backend = FakeBackend()
    bad_data = _build_fake_safe_zip(bands=("B02",))
    inventory = [_seeded_entry(backend, "bad_scene.zip", bad_data)]

    result = run_integrity_audit(backend, inventory, required_tiles=["T44QQE"])

    assert result["failed_count"] == 1
    report_text = result["report_path"].read_text()
    assert "bad_scene.zip" in report_text
    assert "none — every audited scene" not in report_text
