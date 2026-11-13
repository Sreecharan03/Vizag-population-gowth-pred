import numpy as np
import pytest

from src.labels.dynamic_world import (
    built_statistics_qc,
    selected_scene_identity,
    validate_exact_matches,
)


def _scene(epoch: int, number: int) -> dict:
    stamp = f"{epoch}01{number + 1:02d}T050159"
    product = f"S2B_MSIL2A_{stamp}_N0510_R119_T44QQE_{stamp}"
    return {"product_id": product, "epoch": epoch, "sensing_date": stamp}


def test_selected_scene_identity_parses_timestamp_and_tile():
    identity = selected_scene_identity(_scene(2024, 0))
    assert identity["tile"] == "44QQE"
    assert identity["sensing_time_utc"] == "2024-01-01T05:01:59Z"


def test_validate_exact_matches_accepts_one_per_scene():
    scenes = [_scene(epoch, number) for epoch in (2018, 2020, 2022, 2024) for number in range(8)]
    candidates = {}
    for scene in scenes:
        identity = selected_scene_identity(scene)
        candidates[scene["product_id"]] = [{
            "system:index": f'{identity["sensing_timestamp"]}_20180101T050900_T44QQE',
            "system:time_start": identity["sensing_time_ms"] + 471_000,
        }]
    matches = validate_exact_matches(scenes, candidates)
    assert len(matches) == 32
    assert matches[0]["epoch"] == 2018


def test_validate_exact_matches_rejects_ambiguous_candidate():
    scenes = [_scene(epoch, number) for epoch in (2018, 2020, 2022, 2024) for number in range(8)]
    candidates = {}
    for scene in scenes:
        identity = selected_scene_identity(scene)
        candidates[scene["product_id"]] = [{
            "system:index": f'{identity["sensing_timestamp"]}_20180101T050900_T44QQE',
            "system:time_start": identity["sensing_time_ms"] + 471_000,
        }]
    candidates[scenes[0]["product_id"]].append(candidates[scenes[0]["product_id"]][0])
    with pytest.raises(ValueError, match="exactly one"):
        validate_exact_matches(scenes, candidates)


def test_built_statistics_qc_applies_2d_mask_across_two_bands():
    values = np.array([
        [[0.1, -9999.0], [0.7, 0.9]],
        [[0.2, -9999.0], [0.3, 0.4]],
    ], dtype="float32")
    result = built_statistics_qc(values, nodata=-9999.0)
    assert result["valid_pixels"] == 3
    assert result["coverage_fraction"] == 0.75
    assert result["built_median_min"] == pytest.approx(0.1)
    assert result["built_stddev_max"] == pytest.approx(0.4)


def test_built_statistics_qc_rejects_partial_nodata():
    values = np.array([[[0.2]], [[-9999.0]]], dtype="float32")
    with pytest.raises(ValueError, match="inconsistent nodata"):
        built_statistics_qc(values, nodata=-9999.0)
