import numpy as np
import pandas as pd
import pytest

from src.grid.feature_assembly import add_past_population_growth, validate_assembled


def test_population_growth_uses_only_immediate_past_epoch():
    frame = pd.DataFrame({"grid_id": ["a"]*4, "epoch": [2018, 2020, 2022, 2024],
                          "population_total": [100.0, 110.0, 121.0, 130.0]})
    result = add_past_population_growth(frame, [2018, 2020, 2022, 2024])
    assert result["population_growth_source_epoch"].tolist() == [pd.NA, 2018, 2020, 2022]
    assert np.allclose(result["population_growth_prior_interval_fraction"].iloc[1:],
                       [0.10, 0.10, 9/121])


def test_population_growth_refuses_missing_intermediate_epoch():
    frame = pd.DataFrame({"grid_id": ["a"]*3, "epoch": [2018, 2022, 2024],
                          "population_total": [100.0, 121.0, 130.0]})
    with pytest.raises(RuntimeError, match="non-immediate"):
        add_past_population_growth(frame, [2018, 2020, 2022, 2024])


def test_validator_preserves_only_support_explained_source_nulls():
    rows = []
    for epoch in (2018, 2020):
        rows.append({"grid_id": "a", "epoch": epoch, "population_growth_source_epoch":
                     pd.NA if epoch == 2018 else 2018,
                     "population_growth_prior_interval_available": epoch != 2018,
                     "population_growth_prior_interval_absolute": np.nan if epoch == 2018 else 1.0,
                     "population_growth_prior_interval_fraction_defined": epoch != 2018,
                     "population_growth_prior_interval_fraction": np.nan if epoch == 2018 else 0.1,
                     "model_eligible_cell": False, "ndvi_usable_pixel_count": 0,
                     "ndvi_unfiltered_mean_diagnostic": np.nan, "ndvi_filtered_mean": np.nan,
                     "elevation_valid_pixel_count": 0, "elevation_mean_m": np.nan,
                     "slope_valid_pixel_count": 0, "slope_mean_degrees": np.nan})
    frame = pd.DataFrame(rows)
    config = {"expected_rows": 2, "expected_cells": 1, "expected_eligible_cells": 0,
              "epochs": [2018, 2020], "roles": ["ndvi"]}
    validate_assembled(frame, config)
    frame.loc[0, "model_eligible_cell"] = True
    with pytest.raises(RuntimeError, match="Eligible"):
        validate_assembled(frame, config)
