import numpy as np
import pytest

from src.labels.dynamic_world import (
    aggregate_cell_evidence,
    apply_aoi_nodata,
    built_statistics_qc,
    fetch_transient_http,
    selected_scene_identity,
    spatially_distributed_samples,
    validate_exact_matches,
)


class _Response:
    def __init__(self, status_code: int, content: bytes = b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        raise RuntimeError(f"HTTP {self.status_code}")


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


def test_apply_aoi_nodata_masks_all_bands_without_mutating_source():
    values = np.arange(12, dtype="float32").reshape(2, 2, 3)
    original = values.copy()
    inside = np.array([[True, False, True], [False, True, False]])
    result = apply_aoi_nodata(values, inside, nodata=-9999.0)
    assert np.array_equal(values, original)
    assert np.array_equal(result[:, inside], values[:, inside])
    assert np.all(result[:, ~inside] == -9999.0)


def test_apply_aoi_nodata_rejects_mismatched_shape():
    with pytest.raises(ValueError, match="incompatible shapes"):
        apply_aoi_nodata(np.zeros((2, 3, 4)), np.zeros((3, 3)), nodata=-1)


def test_fetch_transient_http_refreshes_url_and_retries_500():
    urls, sleeps = [], []
    responses = iter([_Response(500), _Response(200, b"tile")])
    result = fetch_transient_http(
        lambda: f"url-{len(urls) + 1}",
        lambda url, timeout: (urls.append((url, timeout)) or next(responses)),
        sleeps.append,
        retry_delays_seconds=(2,),
    )
    assert result == b"tile"
    assert urls == [("url-1", 300), ("url-2", 300)]
    assert sleeps == [2.0]


def test_fetch_transient_http_does_not_retry_nontransient_status():
    sleeps = []
    with pytest.raises(RuntimeError, match="HTTP 400"):
        fetch_transient_http(
            lambda: "url", lambda url, timeout: _Response(400), sleeps.append)
    assert sleeps == []


def test_aggregate_cell_evidence_preserves_soft_and_classified_metrics():
    probability = np.array([[0.2, 0.8], [0.4, 0.6]], dtype="float32")
    uncertainty = np.array([[0.1, 0.2], [0.3, 0.4]], dtype="float32")
    support = np.array([[5, 6], [7, 8]], dtype="uint16")
    mode = np.array([[1, 6], [6, 6]], dtype="uint8")
    cells = np.array([[1, 1], [2, 2]], dtype="int32")
    result = aggregate_cell_evidence(
        probability, uncertainty, support, mode, cells, expected_cells=2)
    assert np.allclose(result["mean_built_probability"], [0.5, 0.5])
    assert np.allclose(result["modal_built_fraction"], [0.5, 1.0])
    assert np.array_equal(result["minimum_valid_observation_count"], [5, 7])
    assert np.array_equal(result["aoi_pixel_count"], [2, 2])


def test_aggregate_cell_evidence_preserves_zero_pixel_edge_cell_with_flag():
    shape = (1, 1)
    result = aggregate_cell_evidence(
        np.full(shape, 0.5), np.full(shape, 0.1), np.full(shape, 5),
        np.full(shape, 6), np.full(shape, 1), expected_cells=2)
    assert result["evidence_available"].tolist() == [True, False]
    assert result["aoi_pixel_count"].tolist() == [1, 0]
    assert np.isnan(result["modal_built_fraction"][1])
    assert result["minimum_valid_observation_count"].tolist() == [5, 0]


def test_spatially_distributed_samples_is_deterministic_and_block_balanced():
    mask = np.ones((6, 8), dtype=bool)
    samples = spatially_distributed_samples(mask, grid_rows=2, grid_columns=2)
    assert samples == [(1, 1), (1, 5), (4, 1), (4, 5)]


def test_spatially_distributed_samples_rejects_empty_stratum():
    with pytest.raises(ValueError, match="no candidate"):
        spatially_distributed_samples(np.zeros((3, 3), dtype=bool))
