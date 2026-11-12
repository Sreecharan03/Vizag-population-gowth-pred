import pandas as pd
import pytest

from src.grid.context_aggregation import validate_context_frame


def test_context_validation_requires_complete_unique_nonnegative_rows():
    config = {"expected_cells": 2, "years": [2018, 2020]}
    rows = []
    for year in config["years"]:
        for cell in ("a", "b"):
            rows.append({"grid_id": cell, "epoch": year, "population_total": 1.0,
                         "aoi_fraction": 1.0,
                         "population_density_per_km2": 2.0, "road_length_m": 3.0,
                         "road_density_km_per_km2": 4.0, "amenity_count": 1,
                         "nearest_amenity_distance_m": 5.0})
    frame = pd.DataFrame(rows)
    validate_context_frame(frame, config)
    with pytest.raises(RuntimeError, match="uniqueness"):
        validate_context_frame(pd.concat([frame, frame.iloc[[0]]]), config)
