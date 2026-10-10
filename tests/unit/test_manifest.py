import threading

import pytest

from src.storage.manifest import (
    InvalidTransitionError,
    Manifest,
    ManifestRecord,
    ManifestState,
)


def _record(key: str, state: ManifestState) -> ManifestRecord:
    return ManifestRecord(object_key=key, state=state)


def test_manifest_upsert_and_get_round_trip(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")
    manifest.upsert(_record("scene-1", ManifestState.LISTED))

    got = manifest.get("scene-1")
    assert got is not None
    assert got.object_key == "scene-1"
    assert got.state == ManifestState.LISTED


def test_manifest_get_missing_key_returns_none(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")
    assert manifest.get("does-not-exist") is None


def test_manifest_state_transition_allowed(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")
    manifest.upsert(_record("scene-1", ManifestState.LISTED))
    manifest.upsert(_record("scene-1", ManifestState.PLANNED))

    assert manifest.get("scene-1").state == ManifestState.PLANNED


def test_manifest_invalid_transition_raises(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")
    manifest.upsert(_record("scene-1", ManifestState.LISTED))

    with pytest.raises(InvalidTransitionError, match="LISTED -> ARCHIVED"):
        manifest.upsert(_record("scene-1", ManifestState.ARCHIVED))

    # The invalid attempt must not have changed the stored state.
    assert manifest.get("scene-1").state == ManifestState.LISTED


def test_manifest_failed_state_allows_retry_to_planned(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")
    manifest.upsert(_record("scene-1", ManifestState.LISTED))
    manifest.upsert(_record("scene-1", ManifestState.FAILED))
    manifest.upsert(_record("scene-1", ManifestState.PLANNED))  # retry

    assert manifest.get("scene-1").state == ManifestState.PLANNED


def test_manifest_enforce_transition_can_be_disabled(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")
    manifest.upsert(_record("scene-1", ManifestState.LISTED))
    manifest.upsert(_record("scene-1", ManifestState.ARCHIVED), enforce_transition=False)

    assert manifest.get("scene-1").state == ManifestState.ARCHIVED


def test_manifest_atomic_write_survives_simulated_crash(tmp_path):
    import src.storage.manifest as manifest_module

    manifest_path = tmp_path / "manifest.jsonl"
    manifest = Manifest(manifest_path)
    manifest.upsert(_record("scene-1", ManifestState.LISTED))
    original_contents = manifest_path.read_text()

    real_replace = manifest_module.os.replace

    def _crash_before_replace(*args, **kwargs):
        raise OSError("simulated crash mid-write")

    manifest_module.os.replace = _crash_before_replace
    try:
        with pytest.raises(OSError, match="simulated crash"):
            manifest.upsert(_record("scene-2", ManifestState.LISTED))
    finally:
        manifest_module.os.replace = real_replace

    # The original manifest must be untouched — os.replace() never happened,
    # so the "crash" could not have corrupted it.
    assert manifest_path.read_text() == original_contents
    # But a stale .part temp file is left behind, as a crash artifact would be.
    part_files = list(tmp_path.glob("*.part"))
    assert len(part_files) == 1

    removed = manifest.cleanup_stale_part_files()
    assert len(removed) == 1
    assert list(tmp_path.glob("*.part")) == []

    # The manifest itself still works correctly after cleanup — resume with
    # no duplicated/corrupted data.
    manifest.upsert(_record("scene-2", ManifestState.LISTED))
    assert manifest.get("scene-1").state == ManifestState.LISTED
    assert manifest.get("scene-2").state == ManifestState.LISTED


def test_manifest_cleanup_removes_stale_part_files_only(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")
    manifest.upsert(_record("scene-1", ManifestState.LISTED))

    stray_part = tmp_path / "leftover.jsonl.part"
    stray_part.write_text("garbage from a crash\n")

    removed = manifest.cleanup_stale_part_files()
    assert stray_part in removed
    assert not stray_part.exists()
    # The real manifest file must be unaffected.
    assert manifest.get("scene-1").state == ManifestState.LISTED


def test_manifest_file_lock_prevents_concurrent_corruption(tmp_path):
    manifest = Manifest(tmp_path / "manifest.jsonl")
    num_per_thread = 50

    def _writer(prefix: str):
        for i in range(num_per_thread):
            manifest.upsert(_record(f"{prefix}-{i}", ManifestState.LISTED), enforce_transition=False)

    t1 = threading.Thread(target=_writer, args=("a",))
    t2 = threading.Thread(target=_writer, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    records = manifest.all_records()
    keys = {r.object_key for r in records}
    expected = {f"a-{i}" for i in range(num_per_thread)} | {f"b-{i}" for i in range(num_per_thread)}
    assert keys == expected, "concurrent writes lost or corrupted records"
