import numpy as np
import pytest

from src.grid.feature_aggregation import (
    aggregate_continuous, aggregate_labeled_values, slope_degrees,
    validate_feature_frames, validate_index_aggregation,
)


def test_index_aggregation_preserves_counts_and_excludes_only_bad_values():
    labels = np.array([[1, 1, 2], [1, 2, 0]])
    values = np.array([[0.2, np.nan, 1.2], [-9999.0, -0.4, 0.9]])
    result = aggregate_labeled_values(values, labels, 2, nodata=-9999.0)
    assert result["aoi_pixel_count"].tolist() == [3, 2]
    assert result["input_valid_pixel_count"].tolist() == [1, 2]
    assert result["nodata_pixel_count"].tolist() == [2, 0]
    assert result["out_of_range_excluded_pixel_count"].tolist() == [0, 1]
    assert result["usable_pixel_count"].tolist() == [1, 1]
    assert result["filtered_mean"].tolist() == pytest.approx([0.2, -0.4])
    assert result["unfiltered_mean_diagnostic"].tolist() == pytest.approx([0.2, 0.4])
    validate_index_aggregation(result, expected_cells=2, candidate_total=5)


def test_empty_cell_mean_is_nan_but_quality_fractions_are_finite():
    result = aggregate_labeled_values(np.array([[np.nan]]), np.array([[1]]), 2)
    assert np.isnan(result["filtered_mean"]).all()
    assert np.isfinite(result["usable_fraction_of_aoi_pixels"]).all()
    validate_index_aggregation(result, expected_cells=2, candidate_total=1)


def test_reconciliation_rejects_changed_counts():
    result = aggregate_labeled_values(np.array([[0.1]]), np.array([[1]]), 1)
    result["usable_pixel_count"][0] += 1
    with pytest.raises(RuntimeError, match="reconcile"):
        validate_index_aggregation(result, expected_cells=1, candidate_total=1)


def test_metric_plane_has_expected_slope_and_mask():
    y, x = np.mgrid[:4, :5]
    elevation = 2.0*x
    slope = slope_degrees(elevation, 1.0)
    assert slope == pytest.approx(np.degrees(np.arctan(2.0)))
    mask = np.ones_like(elevation, dtype=bool)
    mask[0, 0] = False
    assert np.isnan(slope_degrees(elevation, 1.0, mask)[0, 0])


def test_continuous_aggregation_and_feature_frame_contract():
    import pandas as pd
    continuous = aggregate_continuous(
        np.array([[10.0, 20.0, np.nan]]), np.array([[1, 1, 2]]), 2)
    assert continuous["mean"][0] == 15 and np.isnan(continuous["mean"][1])
    sat = pd.DataFrame({"grid_id": ["a", "b"], "epoch": [2018, 2018]})
    for name, values in {
        "aoi_pixel_count": [2, 1], "input_valid_pixel_count": [2, 0],
        "nodata_pixel_count": [0, 1], "out_of_range_excluded_pixel_count": [0, 0],
        "usable_pixel_count": [2, 0], "usable_fraction_of_aoi_pixels": [1.0, 0.0],
        "exclusion_fraction_of_input_valid_pixels": [0.0, 0.0],
        "unfiltered_mean_diagnostic": [0.1, np.nan], "filtered_mean": [0.1, np.nan],
    }.items():
        sat[f"ndvi_{name}"] = values
    terrain = pd.DataFrame({"grid_id": ["a", "b"],
                            "elevation_mean_m": [5.0, np.nan],
                            "slope_mean_degrees": [1.0, np.nan]})
    validate_feature_frames(sat, terrain, expected_cells=2, epochs=[2018], roles=["ndvi"])
