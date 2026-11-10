import io
import json
from copy import deepcopy

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from src.preprocessing.gate_review import review_epoch, render_epoch_png
from src.preprocessing.gate_review_job import check_output_budget, reports, verify_source_pins
from src.preprocessing.indices import BAND_NAMES, INDEX_FORMULAS, IndexPolicy, compute_indices
from src.utils.io import load_config


@pytest.fixture
def source(tmp_path):
    values = np.broadcast_to(np.array([.1, .18, .2, .3, .35, .25], dtype="float32")[:, None, None], (6, 32, 40)).copy()
    values[:, 0, :] = -9999
    values[2, 5, 5] = -.1
    values[4, 6, 6] = -.29
    values[2, 7, 7] = -.3
    values[:, 8, 8] = 0
    outputs, stats = compute_indices(values)
    count = np.full((32, 40), 4, dtype="uint8")
    count[0, :] = 0
    paths = {}
    arrays = {"composite": values, "valid_obs_count": count[None],
              **{name: array[None] for name, array in outputs.items()}}
    for name, array in arrays.items():
        path = tmp_path / f"{name}.tif"
        with rasterio.open(path, "w", driver="GTiff", height=32, width=40, count=array.shape[0],
                           dtype=array.dtype, crs="EPSG:32644", transform=from_origin(706610, 1990390, 10, 10),
                           nodata=255 if name == "valid_obs_count" else -9999) as ds:
            ds.write(array)
            ds.descriptions = BAND_NAMES if name == "composite" else (name.upper(),)
        paths[name] = path
    with rasterio.open(paths["composite"]) as ds:
        geometry = box(*ds.bounds)
    config = deepcopy(load_config("gate_review"))
    config.update(expected_aoi_pixels=1280, minimum_aoi_coverage_fraction=.9,
                  chunk_size_pixels=11, preview_max_side=8, samples_per_index=2, figure_dpi=55)
    return paths, geometry, config, stats


def scan(source, **kwargs):
    paths, geometry, config, stats = source
    return review_epoch(paths, geometry=geometry, policy=IndexPolicy(), config=config,
                        expected_statistics=kwargs.get("expected_statistics", stats))


def test_native_qc_matches_prior_counts_and_preserves_rare_outliers(source):
    result, previews = scan(source)
    assert result["unique_outlier_pixels"] == 2
    assert int(previews["union_hits"].sum()) == 2
    assert sum(s["out_of_range_pixels"] for s in result["statistics"].values()) == 4
    assert result["statistics"]["ndvi"]["guarded_denominator_pixels"] == 2
    assert result["coverage_fraction"] == 1240/1280
    assert result["diagnostics"]["ndbi"]["negative_term_outliers"] == 1
    assert result["diagnostics"]["ndbi"]["cancellation_ratios"]["minimum"] < .1
    assert result["prior_statistics_match"]
    for sample in result["samples"]:
        assert np.isfinite([sample["longitude"], sample["latitude"], sample["denominator"]]).all()
        assert sample["observations"] == 4


def test_native_results_are_independent_of_preview_size(source):
    first, _ = scan(source)
    source[2]["preview_max_side"] = 40
    second, _ = scan(source)
    assert first == second


def test_native_results_are_independent_of_chunk_boundaries(source):
    first, _ = scan(source)
    source[2]["chunk_size_pixels"] = 16
    second, _ = scan(source)
    assert first["statistics"] == second["statistics"]
    assert first["samples"] == second["samples"]
    assert first["unique_outlier_pixels"] == second["unique_outlier_pixels"]


@pytest.mark.parametrize("kind", ["index", "count", "grid", "prior_stats", "coverage", "aoi"])
def test_inconsistent_evidence_halts(source, kind):
    paths, geometry, config, stats = source
    if kind == "index":
        with rasterio.open(paths["ndvi"], "r+") as ds:
            values = ds.read(1); values[10, 10] = .9; ds.write(values, 1)
    elif kind == "count":
        with rasterio.open(paths["valid_obs_count"], "r+") as ds:
            values = ds.read(1); values[10, 10] = 3; ds.write(values, 1)
    elif kind == "grid":
        with rasterio.open(paths["ndvi"], "r+") as ds:
            ds.transform = from_origin(0, 0, 10, 10)
    elif kind == "prior_stats":
        stats["ndvi"]["out_of_range_pixels"] += 1
    elif kind == "coverage":
        config["minimum_aoi_coverage_fraction"] = .99
    else:
        config["expected_aoi_pixels"] += 1
    with pytest.raises(RuntimeError):
        scan(source)


def test_review_png_and_reports_keep_gate_pending_without_modifying_sources(source):
    before = {k: p.read_bytes() for k, p in source[0].items()}
    summary, previews = scan(source)
    image = render_epoch_png(2018, summary, previews, geometry=source[1], config=source[2])
    assert image.startswith(b"\x89PNG\r\n\x1a\n") and len(image) < 3*1024*1024
    summary["epoch"] = 2018
    blobs = reports([summary], config=source[2], sources=[], auxiliary=[], feasibility_text="Existing report", input_bytes=12)
    record = json.loads(blobs["range_review.json"])
    assert not record["phase3_gate_approved"] and not record["eligibility_policy_approved"]
    assert "qc_2018.png" in blobs["review.md"].decode()
    assert blobs["range_review.csv"].decode().startswith("epoch,index,row,col")
    assert before == {k: p.read_bytes() for k, p in source[0].items()}


def test_output_budget_accounts_for_storage_readback_and_local_copies():
    config = load_config("gate_review")
    blobs = {name: b"small output" for name in config["file_caps"]}
    assert check_output_budget(blobs, config, include_manifest=True) == sum(map(len, blobs.values()))
    changed = deepcopy(config)
    changed["maximum_output_transfer_bytes"] = 1
    with pytest.raises(RuntimeError, match="budget exceeded"):
        check_output_budget(blobs, changed, include_manifest=True)


def test_extra_outputs_are_not_approved():
    config = load_config("gate_review")
    blobs = {name: b"x" for name in config["file_caps"]}
    blobs["unapproved.tif"] = b"x"
    with pytest.raises(ValueError):
        check_output_budget(blobs, config, include_manifest=True)


def test_all_source_pins_and_exact_byte_limits():
    config = load_config("gate_review")
    audit = {"checked_identities": deepcopy(config["sources"])}
    verify_source_pins(audit, config)
    assert sum(i["bytes"] for i in config["sources"]) == 2777948118
    assert 2777948118+52501+1314+1048576 == config["maximum_input_bytes"]
    assert config["maximum_new_output_bytes"]*3 == config["maximum_output_transfer_bytes"] == 48*1024*1024
    audit["checked_identities"][0]["version_id"] = "changed"
    with pytest.raises(RuntimeError, match="source identity drift"):
        verify_source_pins(audit, config)
