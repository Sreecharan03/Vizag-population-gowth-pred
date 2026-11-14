import numpy as np
import pandas as pd
import pytest

from src.labels.growth_labels import (
    aggregate_class_fraction,
    build_transition_labels,
    manifest_output_identity,
    validate_transition_labels,
)


def _policy():
    return {
        "expected_cells": 2, "expected_rows": 6,
        "transitions": [[2018, 2020, "training"], [2020, 2022, "training"],
                        [2022, 2024, "temporal_holdout"]],
        "candidate_threshold_pct": 10, "already_built_exclusion_pct": 90,
        "water_fraction_exclusion_threshold": 0.5,
        "protected_area_status": "unavailable",
    }


def _inputs():
    built = pd.DataFrame([
        {"grid_id": cell, "epoch": epoch, "evidence_available": True,
         "modal_built_fraction": value}
        for cell, values in {"a": [0.10, 0.20, 0.15, 0.30],
                             "b": [0.95, 0.96, 0.97, 0.98]}.items()
        for epoch, value in zip([2018, 2020, 2022, 2024], values)
    ])
    eligibility = pd.DataFrame([
        {"grid_id": cell, "epoch": epoch, "model_eligible_cell": True}
        for cell in ["a", "b"] for epoch in [2018, 2020, 2022, 2024]
    ])
    water = pd.DataFrame([
        {"grid_id": cell, "epoch": epoch, "water_evidence_available": True,
         "water_valid_pixel_count": 10, "water_pixel_count": 0, "water_fraction": 0.0}
        for cell in ["a", "b"] for epoch in [2018, 2020, 2022]
    ])
    return built, eligibility, water


def test_aggregate_class_fraction_uses_valid_pixels_only():
    result = aggregate_class_fraction(
        np.array([[0, 6], [255, 0]], dtype="uint8"),
        np.array([[1, 1], [2, 2]], dtype="int32"),
        expected_cells=2, target_class=0, nodata=255)
    assert result["water_valid_pixel_count"].tolist() == [2, 1]
    assert result["water_fraction"].tolist() == [0.5, 1.0]


def test_already_built_is_excluded_before_label_assignment():
    frame = build_transition_labels(*_inputs(), _policy())
    rows = frame[frame.grid_id == "b"]
    assert rows.excluded_already_built.all()
    assert rows.growth_label_candidate.isna().all()


def test_negative_delta_is_retained_as_zero():
    frame = build_transition_labels(*_inputs(), _policy())
    row = frame[(frame.grid_id == "a") & (frame.start_epoch == 2020)].iloc[0]
    assert row.negative_delta_flag
    assert row.growth_label_candidate == 0


def test_water_exclusion_uses_start_epoch_only():
    built, eligibility, water = _inputs()
    water.loc[(water.grid_id == "a") & (water.epoch == 2020),
              ["water_pixel_count", "water_fraction"]] = [5, 0.5]
    frame = build_transition_labels(built, eligibility, water, _policy())
    rows = frame[frame.grid_id == "a"].set_index("start_epoch")
    assert not rows.loc[2018, "excluded_majority_water"]
    assert rows.loc[2020, "excluded_majority_water"]
    assert not rows.loc[2022, "excluded_majority_water"]


def test_builder_rejects_missing_endpoint_instead_of_using_intermediate_year():
    built, eligibility, water = _inputs()
    built = built[~((built.grid_id == "a") & (built.epoch == 2022))]
    with pytest.raises(ValueError, match="missing endpoint"):
        build_transition_labels(built, eligibility, water, _policy())


def test_transition_validation_accepts_complete_contract():
    frame = build_transition_labels(*_inputs(), _policy())
    validate_transition_labels(frame, _policy())


@pytest.mark.parametrize("outputs", [
    {"table": {"key": "table.parquet", "bytes": 10, "sha256": "abc"}},
    [{"key": "table.parquet", "bytes": 10, "sha256": "abc"}],
])
def test_manifest_output_identity_supports_mapping_and_list(outputs):
    identity = manifest_output_identity({"outputs": outputs}, "table.parquet")
    assert identity["sha256"] == "abc"


def test_manifest_output_identity_rejects_missing_key():
    with pytest.raises(ValueError, match="exactly one"):
        manifest_output_identity({"outputs": []}, "table.parquet")
