from __future__ import annotations

import pytest

from src.acquisition.backup import backup_manifests_to_b2, write_backup_report
from src.storage.backends import FakeBackend


def test_backup_manifests_to_b2_uploads_all_files(tmp_path, monkeypatch):
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    (manifests_dir / "b2_inventory.jsonl").write_text('{"a": 1}\n')
    (manifests_dir / "nested").mkdir()
    (manifests_dir / "nested" / "state.jsonl").write_text('{"b": 2}\n')

    monkeypatch.setattr("src.acquisition.backup.resolve_path", lambda key: manifests_dir)

    backend = FakeBackend()
    config = {"prefixes": {"manifests_backup": "vizag-geoai/data/manifests/"}}

    result = backup_manifests_to_b2(backend, b2_config=config)

    assert set(result["uploaded"]) == {
        "vizag-geoai/data/manifests/b2_inventory.jsonl",
        "vizag-geoai/data/manifests/nested/state.jsonl",
    }
    assert backend.exists("vizag-geoai/data/manifests/b2_inventory.jsonl")
    assert backend.exists("vizag-geoai/data/manifests/nested/state.jsonl")


def test_backup_manifests_to_b2_refuses_without_prefix_set():
    backend = FakeBackend()
    config = {"prefixes": {"manifests_backup": None}}
    with pytest.raises(ValueError, match="not set"):
        backup_manifests_to_b2(backend, b2_config=config)


def test_backup_manifests_to_b2_handles_missing_directory(tmp_path, monkeypatch):
    missing_dir = tmp_path / "does_not_exist"
    monkeypatch.setattr("src.acquisition.backup.resolve_path", lambda key: missing_dir)

    backend = FakeBackend()
    config = {"prefixes": {"manifests_backup": "vizag-geoai/data/manifests/"}}
    result = backup_manifests_to_b2(backend, b2_config=config)
    assert result["uploaded"] == []


def test_write_backup_report_contains_expected_sections(tmp_path, monkeypatch):
    monkeypatch.setattr("src.acquisition.backup.resolve_path", lambda key: tmp_path)
    result = {"uploaded": ["vizag-geoai/data/manifests/b2_inventory.jsonl"], "prefix": "vizag-geoai/data/manifests/"}

    path = write_backup_report(result)
    content = path.read_text()
    assert "Manifest Backup & Resume Drill Status" in content
    assert "b2_inventory.jsonl" in content
    assert "## Resume drill" in content
    assert "Zero duplicate transfers" in content
