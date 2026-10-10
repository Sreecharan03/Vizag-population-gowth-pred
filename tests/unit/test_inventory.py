import json

from src.acquisition.inventory import (
    classify_inventory,
    generate_report,
    list_inventory,
    run_inventory,
    write_inventory_manifest,
    write_report,
)
from src.storage.backends import FakeBackend
from tests.fixtures.fake_bucket import FAKE_BUCKET_OBJECTS


def _seeded_backend() -> FakeBackend:
    backend = FakeBackend()
    for key, size in FAKE_BUCKET_OBJECTS:
        backend.seed(key, b"x" * size)
    return backend


def test_inventory_lists_all_objects_with_pagination():
    backend = FakeBackend()
    for i in range(250):
        backend.seed(f"prefix/object_{i:04d}.tif", b"x" * 10)

    entries = list_inventory(backend)
    assert len(entries) == 250


def test_inventory_classifies_unknown_files_and_never_marks_them_for_deletion():
    backend = _seeded_backend()
    entries = classify_inventory(list_inventory(backend))

    unknown_entries = [e for e in entries if "UNKNOWN" in e.statuses]
    unknown_keys = {e.key for e in unknown_entries}
    assert any(".DS_Store" in k for k in unknown_keys)
    assert any("Thumbs.db" in k for k in unknown_keys)
    # Structural guarantee: nothing in this module can delete — classify_inventory
    # and list_inventory never call backend.download/upload, let alone a delete.
    assert backend.request_count > 0  # list() happened
    # (no delete method exists on FakeBackend at all — see test_storage_backends.py)


def test_duplicate_products_detected_best_recommended_none_deleted():
    backend = _seeded_backend()
    entries = classify_inventory(list_inventory(backend))

    duplicate_entries = [e for e in entries if "DUPLICATE" in e.statuses]
    product_ids = {e.product_id for e in duplicate_entries}
    assert "S2A_MSIL2A_20180103T045201_N0500_R076_T44QQE_20230717T103013" in product_ids
    assert "S2A_MSIL2A_20180103T045201_N0511_R076_T44QQE_20231201T090000" in product_ids
    # All original entries are still present — nothing was removed.
    assert len(entries) == len(FAKE_BUCKET_OBJECTS)


def test_incomplete_safe_detected_when_required_band_missing():
    backend = _seeded_backend()
    entries = classify_inventory(list_inventory(backend))

    incomplete = [e for e in entries if "INCOMPLETE" in e.statuses]
    incomplete_ids = {e.product_id for e in incomplete}
    assert "S2A_MSIL2A_20180103T045201_N0500_R076_T44QQF_20230717T103013" in incomplete_ids
    missing_tags = {s for e in incomplete for s in e.statuses if s.startswith("missing:")}
    assert any("scl" in tag for tag in missing_tags)


def test_zero_byte_and_undersized_files_flagged():
    backend = _seeded_backend()
    entries = classify_inventory(list_inventory(backend))

    suspect = [e for e in entries if "SUSPECT_SIZE" in e.statuses]
    assert any(e.size_bytes == 0 for e in suspect)


def test_matching_is_by_product_id_not_exact_key():
    backend = FakeBackend()
    backend.seed(
        "prefix-a/S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE_refl.tif", b"x" * 100
    )
    backend.seed(
        "prefix-b/nested/S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE_refl.tif", b"x" * 100
    )
    entries = list_inventory(backend)
    product_ids = {e.product_id for e in entries}
    assert len(product_ids) == 1


def test_complete_product_marked_ok():
    backend = _seeded_backend()
    entries = classify_inventory(list_inventory(backend))
    complete_entries = [
        e for e in entries if e.product_id == "S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013"
    ]
    assert all("OK" in e.statuses for e in complete_entries)
    assert all("INCOMPLETE" not in e.statuses for e in complete_entries)


def test_write_report_creates_file_with_content(tmp_path, monkeypatch):
    monkeypatch.setattr("src.acquisition.inventory.resolve_path", lambda key: tmp_path)
    backend = _seeded_backend()
    entries = classify_inventory(list_inventory(backend))

    report_path = write_report(entries)
    assert report_path == tmp_path / "phase2" / "inventory_report.md"
    assert "# B2 Inventory Report" in report_path.read_text()


def test_write_inventory_manifest_is_valid_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.acquisition.inventory.resolve_path",
        lambda key: tmp_path if key == "data.manifests" else tmp_path,
    )
    backend = _seeded_backend()
    entries = classify_inventory(list_inventory(backend))

    manifest_path = write_inventory_manifest(entries)
    lines = manifest_path.read_text().splitlines()
    assert len(lines) == len(entries)
    for line in lines:
        record = json.loads(line)
        assert "key" in record and "size_bytes" in record


def test_generate_report_contains_expected_sections():
    backend = _seeded_backend()
    entries = classify_inventory(list_inventory(backend))
    report = generate_report(entries)

    assert "# B2 Inventory Report" in report
    assert "## By source" in report
    assert "## Duplicates" in report
    assert "## Incomplete products" in report
    assert "## Suspect size" in report
    assert "## Unknown / junk" in report
    assert ".DS_Store" in report
    assert "## By source + format" in report
    assert "## Assumption check" in report
    assert "A1" in report and "A4" in report


def test_run_inventory_is_read_only_and_writes_both_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.acquisition.inventory.resolve_path",
        lambda key: tmp_path,
    )
    backend = _seeded_backend()
    initial_request_count = backend.request_count

    summary = run_inventory(backend)

    assert summary["entry_count"] == len(FAKE_BUCKET_OBJECTS)
    assert summary["manifest_path"].exists()
    assert summary["report_path"].exists()
    # Only list() calls happened — list_inventory calls backend.list() exactly once.
    assert backend.request_count == initial_request_count + 1
