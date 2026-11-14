import pandas as pd
import pytest

from src.labels.threshold_sensitivity import (
    build_comparison,
    build_threshold_sensitivity,
    label_change_summary,
    validate_threshold_sensitivity,
)


def _source():
    return pd.DataFrame([
        {"grid_id": cell, "start_epoch": 2018, "end_epoch": 2020,
         "split": "training", "delta_built_fraction": delta,
         "negative_delta_flag": delta < 0, "label_eligible": eligible}
        for cell, delta, eligible in [("a", 0.15, True), ("b", -0.02, False)]
    ])


def test_sensitivity_produces_all_configured_thresholds_and_nullable_exclusions():
    frame = build_threshold_sensitivity(_source(), [20, 5, 10])
    assert set(frame.threshold_pct) == {5, 10, 20}
    assert frame.loc[~frame.label_eligible, "growth_label"].isna().all()
    labels = frame[frame.label_eligible].set_index("threshold_pct").growth_label
    assert labels.to_dict() == {5: 1, 10: 1, 20: 0}


def test_negative_delta_is_zero_at_every_threshold():
    source = _source()
    source.loc[1, "label_eligible"] = True
    frame = build_threshold_sensitivity(source, [5, 10, 20])
    assert frame.loc[frame.negative_delta_flag, "growth_label"].eq(0).all()


def test_validation_rejects_non_nested_positive_sets():
    source = _source().iloc[[0]]
    frame = build_threshold_sensitivity(source, [5, 10, 20])
    frame.loc[frame.threshold_pct == 20, "growth_label"] = 1
    frame.loc[frame.threshold_pct == 10, "growth_label"] = 0
    with pytest.raises(RuntimeError, match="do not match|not nested"):
        validate_threshold_sensitivity(
            frame, expected_cells=1, expected_rows=3, expected_source_rows=1,
            thresholds_pct=[5, 10, 20], transitions=[[2018, 2020, "training"]])


def test_comparison_reports_every_transition_threshold_and_imbalance():
    frame = build_threshold_sensitivity(_source(), [5, 10, 20])
    report = build_comparison(frame, 0.05)
    assert len(report) == 3
    assert report["imbalance_warning"].tolist() == [True, True, True]


def test_label_change_summary_counts_adjacent_changes():
    frame = build_threshold_sensitivity(_source(), [5, 10, 20])
    result = label_change_summary(frame, [5, 10, 20])
    assert result["5_to_10"]["changed_labels"] == 0
    assert result["10_to_20"]["changed_labels"] == 1
