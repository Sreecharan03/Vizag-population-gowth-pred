from __future__ import annotations

import json

import geopandas as gpd
import yaml
from shapely.geometry import Polygon

from src.acquisition.reconcile import (
    build_data_requirements,
    compute_required_tiles,
    generate_missing_report,
    reconcile_sentinel2,
    reconcile_small_datasets,
    run_reconciliation,
    write_data_requirements,
    write_missing_report,
)

# A small polygon tightly around Vizag's real centroid (83.23E, 17.73N) —
# known (from a real run) to fall within a single MGRS tile, T44QQE.
_VIZAG_CENTROID_POLYGON = Polygon(
    [(83.20, 17.70), (83.26, 17.70), (83.26, 17.76), (83.20, 17.76), (83.20, 17.70)]
)


def _temporal_config():
    return {
        "epochs": [2018, 2020, 2022, 2024],
        "dry_season_window": {"start_month_day": "12-01", "end_month_day": "03-31"},
    }


# --- compute_required_tiles --------------------------------------------------


def test_compute_required_tiles_matches_known_vizag_tile():
    gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[_VIZAG_CENTROID_POLYGON], crs="EPSG:4326")
    tiles = compute_required_tiles(gdf)
    assert tiles == ["T44QQE"]


# --- build_data_requirements --------------------------------------------------


def test_build_data_requirements_structure():
    reqs = build_data_requirements(["T44QQE"], _temporal_config())
    assert reqs["sentinel2"]["required_tiles"] == ["T44QQE"]
    assert reqs["sentinel2"]["epochs"] == [2018, 2020, 2022, 2024]
    assert reqs["small_datasets"]["worldpop"]["years"] == [2018, 2020, 2022, 2024]
    for name in ("dem", "worldcover", "osm"):
        assert reqs["small_datasets"][name]["required"] is True


# --- reconcile_sentinel2 ------------------------------------------------------


def _inventory_entry(*, tile, year, source="sentinel2", fmt="zip", key=None):
    return {
        "key": key or f"data/raw/sentinel2/{year}/fake_{tile}_{year}.SAFE.zip",
        "size_bytes": 500_000_000,
        "source": source,
        "format": fmt,
        "tile": tile,
        "sensing_date": f"{year}0115T045000",
    }


def test_reconcile_sentinel2_all_present():
    reqs = build_data_requirements(["T44QQE"], _temporal_config())
    inventory = [_inventory_entry(tile="T44QQE", year=y) for y in [2018, 2020, 2022, 2024]]

    result = reconcile_sentinel2(reqs, inventory)
    assert result["missing"] == []
    assert all(row["scene_count"] >= 1 for row in result["coverage"])


def test_reconcile_sentinel2_detects_missing_epoch():
    reqs = build_data_requirements(["T44QQE"], _temporal_config())
    inventory = [_inventory_entry(tile="T44QQE", year=y) for y in [2018, 2020, 2022]]  # 2024 missing

    result = reconcile_sentinel2(reqs, inventory)
    assert {"tile": "T44QQE", "epoch": 2024} in result["missing"]
    assert len(result["missing"]) == 1


def test_reconcile_sentinel2_detects_extra_tiles():
    reqs = build_data_requirements(["T44QQE"], _temporal_config())
    inventory = [_inventory_entry(tile="T44QQE", year=2018)] + [
        _inventory_entry(tile="T44QPE", year=2018),
        _inventory_entry(tile="T44QQF", year=2018),
    ]

    result = reconcile_sentinel2(reqs, inventory)
    assert result["extra_tiles_present"] == ["T44QPE", "T44QQF"]


def test_reconcile_sentinel2_ignores_non_raw_entries():
    reqs = build_data_requirements(["T44QQE"], _temporal_config())
    # Only a processed derivative exists, no raw zip - must still count as missing.
    inventory = [_inventory_entry(tile="T44QQE", year=2018, source="sentinel2", fmt="processed_derivative")]

    result = reconcile_sentinel2(reqs, inventory)
    assert {"tile": "T44QQE", "epoch": 2018} in result["missing"]


# --- reconcile_small_datasets --------------------------------------------------


def test_reconcile_small_datasets_worldpop_all_years_present():
    reqs = build_data_requirements(["T44QQE"], _temporal_config())
    inventory = [
        {"key": f"vizag-geoai/data/raw/worldpop/clipped/{y}/worldpop_{y}.tif", "source": "other"}
        for y in [2018, 2020, 2022, 2024]
    ]
    result = reconcile_small_datasets(reqs, inventory)
    assert result["worldpop"]["status"] == "OK"
    assert result["worldpop"]["years_missing"] == []


def test_reconcile_small_datasets_worldpop_missing_year():
    reqs = build_data_requirements(["T44QQE"], _temporal_config())
    inventory = [
        {"key": f"vizag-geoai/data/raw/worldpop/clipped/{y}/worldpop_{y}.tif", "source": "other"}
        for y in [2018, 2020, 2022]
    ]
    result = reconcile_small_datasets(reqs, inventory)
    assert result["worldpop"]["status"] == "MISSING_YEARS"
    assert result["worldpop"]["years_missing"] == [2024]


def test_reconcile_small_datasets_dem_worldcover_osm_missing_when_absent():
    reqs = build_data_requirements(["T44QQE"], _temporal_config())
    result = reconcile_small_datasets(reqs, [])
    assert result["dem"]["status"] == "MISSING"
    assert result["worldcover"]["status"] == "MISSING"
    assert result["osm"]["status"] == "MISSING"


def test_reconcile_small_datasets_dem_present():
    reqs = build_data_requirements(["T44QQE"], _temporal_config())
    inventory = [{"key": "vizag-geoai/data/raw_small/dem/vizag_dem.tif", "source": "other"}]
    result = reconcile_small_datasets(reqs, inventory)
    assert result["dem"]["status"] == "OK"


# --- generate_missing_report --------------------------------------------------


def test_generate_missing_report_contains_expected_sections():
    reqs = build_data_requirements(["T44QQE"], _temporal_config())
    inventory = [_inventory_entry(tile="T44QQE", year=y) for y in [2018, 2020, 2022]]
    s2_recon = reconcile_sentinel2(reqs, inventory)
    small_recon = reconcile_small_datasets(reqs, [])

    report = generate_missing_report(s2_recon, small_recon, avg_scene_bytes=500_000_000)
    assert "# Missing Data Report" in report
    assert "## Sentinel-2 tile/epoch coverage" in report
    assert "## Sentinel-2 — missing" in report
    assert "T44QQE" in report and "2024" in report
    assert "## Small datasets" in report
    assert "## Cost estimate" in report


def test_generate_missing_report_no_missing_says_so():
    reqs = build_data_requirements(["T44QQE"], _temporal_config())
    inventory = [_inventory_entry(tile="T44QQE", year=y) for y in [2018, 2020, 2022, 2024]]
    s2_recon = reconcile_sentinel2(reqs, inventory)
    small_recon = reconcile_small_datasets(reqs, [])

    report = generate_missing_report(s2_recon, small_recon)
    assert "none — every required tile/epoch" in report


# --- write_data_requirements / write_missing_report ---------------------------


def test_write_data_requirements_creates_valid_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr("src.acquisition.reconcile.resolve_path", lambda key: tmp_path / "data_requirements.yaml")
    reqs = build_data_requirements(["T44QQE"], _temporal_config())

    path = write_data_requirements(reqs)
    loaded = yaml.safe_load(path.read_text())
    assert loaded["sentinel2"]["required_tiles"] == ["T44QQE"]


def test_write_missing_report_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("src.acquisition.reconcile.resolve_path", lambda key: tmp_path)
    path = write_missing_report("# test report\n")
    assert path == tmp_path / "phase2" / "missing_report.md"
    assert path.read_text() == "# test report\n"


# --- run_reconciliation (full orchestration) -----------------------------------


def test_run_reconciliation_end_to_end(tmp_path, monkeypatch):
    manifest_path = tmp_path / "b2_inventory.jsonl"
    entries = [_inventory_entry(tile="T44QQE", year=y) for y in [2018, 2020, 2022]]
    manifest_path.write_text("\n".join(json.dumps(e) for e in entries))

    def fake_resolve_path(key):
        if key == "configs.data_requirements":
            return tmp_path / "data_requirements.yaml"
        if key == "data.manifests":
            return tmp_path
        if key == "results":
            return tmp_path / "results"
        raise AssertionError(f"unexpected resolve_path key: {key}")

    monkeypatch.setattr("src.acquisition.reconcile.resolve_path", fake_resolve_path)
    monkeypatch.setattr("src.acquisition.reconcile.load_config", lambda name: _temporal_config())

    gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[_VIZAG_CENTROID_POLYGON], crs="EPSG:4326")
    result = run_reconciliation(gdf)

    assert result["required_tiles"] == ["T44QQE"]
    assert result["requirements_path"].exists()
    assert result["report_path"].exists()
    assert {"tile": "T44QQE", "epoch": 2024} in result["sentinel2_reconciliation"]["missing"]
