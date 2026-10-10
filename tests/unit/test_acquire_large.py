from __future__ import annotations

from src.acquisition.acquire_large import check_remaining_large_items, write_resume_status_report


def _requirements():
    return {
        "sentinel2": {
            "required_tiles": ["T44QQE"],
            "epochs": [2018, 2020, 2022, 2024],
            "dry_season_window": {"start_month_day": "12-01", "end_month_day": "03-31"},
        }
    }


def _entry(tile, year):
    return {
        "key": f"data/raw/sentinel2/{year}/fake_{tile}_{year}.SAFE.zip",
        "size_bytes": 500_000_000,
        "source": "sentinel2",
        "format": "zip",
        "tile": tile,
        "sensing_date": f"{year}0115T045000",
    }


def test_check_remaining_large_items_nothing_missing():
    inventory = [_entry("T44QQE", y) for y in [2018, 2020, 2022, 2024]]
    result = check_remaining_large_items(_requirements(), inventory)
    assert result["missing"] == []


def test_check_remaining_large_items_detects_a_real_gap():
    inventory = [_entry("T44QQE", y) for y in [2018, 2020, 2022]]  # 2024 missing
    result = check_remaining_large_items(_requirements(), inventory)
    assert {"tile": "T44QQE", "epoch": 2024} in result["missing"]


def test_write_resume_status_report_nothing_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.acquisition.acquire_large.resolve_path", lambda key: tmp_path)
    inventory = [_entry("T44QQE", y) for y in [2018, 2020, 2022, 2024]]
    result = check_remaining_large_items(_requirements(), inventory)

    path = write_resume_status_report(result)
    content = path.read_text()
    assert "Nothing to resume" in content
    assert path == tmp_path / "phase2" / "part_2_5_resume_status.md"


def test_write_resume_status_report_lists_missing_items(tmp_path, monkeypatch):
    monkeypatch.setattr("src.acquisition.acquire_large.resolve_path", lambda key: tmp_path)
    inventory = [_entry("T44QQE", y) for y in [2018, 2020, 2022]]
    result = check_remaining_large_items(_requirements(), inventory)

    path = write_resume_status_report(result)
    content = path.read_text()
    assert "still need fetching" in content
    assert "T44QQE" in content and "2024" in content
    assert "NOT fetched by this run" in content
