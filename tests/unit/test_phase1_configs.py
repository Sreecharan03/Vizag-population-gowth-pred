"""Validates configs/temporal.yaml, grid.yaml, label.yaml (Phase 1 Part
1.2). plan.md doesn't name explicit tests for this part (same gap as
Part 0.3's validation.py — see tracking/progress.md) — written anyway
since every later phase (4, 5, 6, 10) depends on these being well-formed
and internally consistent.
"""

from src.utils.io import load_config


def test_temporal_config_loads_and_has_expected_epochs():
    config = load_config("temporal")
    assert config["epochs"] == sorted(config["epochs"])
    assert config["epochs"] == [2018, 2020, 2022, 2024]


def test_temporal_training_pairs_are_consecutive_known_epochs():
    config = load_config("temporal")
    epochs = config["epochs"]
    for pair in config["training_transition_pairs"]:
        t1, t2 = pair
        assert t1 in epochs and t2 in epochs
        assert epochs.index(t2) == epochs.index(t1) + 1, f"{pair} is not consecutive in {epochs}"


def test_temporal_holdout_pair_is_consecutive_and_after_training():
    config = load_config("temporal")
    epochs = config["epochs"]
    holdout_t1, holdout_t2 = config["temporal_holdout_pair"]
    assert epochs.index(holdout_t2) == epochs.index(holdout_t1) + 1

    last_training_epoch = max(e for pair in config["training_transition_pairs"] for e in pair)
    assert holdout_t1 >= last_training_epoch, (
        "temporal holdout must not start before training transitions end, or a later "
        "epoch's data could leak into an earlier training signal"
    )


def test_temporal_holdout_pair_not_duplicated_in_training_pairs():
    config = load_config("temporal")
    holdout = tuple(config["temporal_holdout_pair"])
    training_pairs = [tuple(p) for p in config["training_transition_pairs"]]
    assert holdout not in training_pairs


def test_temporal_prediction_target_is_after_last_epoch():
    config = load_config("temporal")
    assert config["prediction_target_year"] > max(config["epochs"])


def test_grid_cell_size_is_positive():
    config = load_config("grid")
    assert config["cell_size_m"] > 0


def test_grid_exclusions_is_a_list():
    config = load_config("grid")
    assert isinstance(config["exclusions"], list)


def test_label_sensitivity_thresholds_sorted_and_in_valid_percent_range():
    config = load_config("label")
    thresholds = config["sensitivity_thresholds_pct"]
    assert thresholds == sorted(thresholds)
    assert all(0 < t < 100 for t in thresholds)


def test_label_primary_threshold_is_one_of_the_sensitivity_thresholds():
    config = load_config("label")
    assert config["primary_threshold_pct"] in config["sensitivity_thresholds_pct"]


def test_label_already_built_exclusion_is_above_all_growth_thresholds():
    config = load_config("label")
    max_growth_threshold = max(config["sensitivity_thresholds_pct"])
    assert config["already_built_exclusion_pct"] > max_growth_threshold
    assert 0 < config["already_built_exclusion_pct"] <= 100
