import json

import pytest

from src.storage.evict import EvictionRefused, safe_evict


def _storage_config(ledger_path):
    return {"eviction": {"ledger": str(ledger_path)}}


def test_safe_evict_refuses_without_verified_b2_copy(tmp_path):
    target = tmp_path / "raw_scene.tif"
    target.write_bytes(b"data")
    ledger = tmp_path / "ledger.jsonl"

    with pytest.raises(EvictionRefused, match="B2 copy not verified"):
        safe_evict(
            target,
            b2_verified=False,
            derivative_validated=True,
            object_key="scene-1",
            storage_config=_storage_config(ledger),
        )

    assert target.exists(), "refused eviction must not delete the file"
    assert not ledger.exists(), "refused eviction must write nothing to the ledger"


def test_safe_evict_refuses_without_validated_derivative(tmp_path):
    target = tmp_path / "raw_scene.tif"
    target.write_bytes(b"data")
    ledger = tmp_path / "ledger.jsonl"

    with pytest.raises(EvictionRefused, match="derivative not validated"):
        safe_evict(
            target,
            b2_verified=True,
            derivative_validated=False,
            object_key="scene-1",
            storage_config=_storage_config(ledger),
        )

    assert target.exists()
    assert not ledger.exists()


def test_safe_evict_refuses_when_path_missing(tmp_path):
    target = tmp_path / "does_not_exist.tif"
    ledger = tmp_path / "ledger.jsonl"

    with pytest.raises(EvictionRefused, match="does not exist"):
        safe_evict(
            target,
            b2_verified=True,
            derivative_validated=True,
            object_key="scene-1",
            storage_config=_storage_config(ledger),
        )

    assert not ledger.exists()


def test_safe_evict_writes_ledger_entry_on_success(tmp_path):
    target = tmp_path / "raw_scene.tif"
    target.write_bytes(b"data")
    ledger = tmp_path / "ledger.jsonl"

    safe_evict(
        target,
        b2_verified=True,
        derivative_validated=True,
        object_key="scene-1",
        reason="composite built",
        storage_config=_storage_config(ledger),
    )

    assert not target.exists(), "successful eviction must delete the local file"
    assert ledger.exists()
    entries = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(entries) == 1
    assert entries[0]["object_key"] == "scene-1"
    assert entries[0]["outcome"] == "EVICTED"
    assert entries[0]["reason"] == "composite built"


def test_safe_evict_appends_multiple_entries(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    for i in range(3):
        target = tmp_path / f"scene_{i}.tif"
        target.write_bytes(b"data")
        safe_evict(
            target,
            b2_verified=True,
            derivative_validated=True,
            object_key=f"scene-{i}",
            storage_config=_storage_config(ledger),
        )

    entries = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(entries) == 3
    assert {e["object_key"] for e in entries} == {"scene-0", "scene-1", "scene-2"}
