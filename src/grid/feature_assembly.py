"""Leakage-safe Phase 4.4 feature assembly."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _require_unique(frame, keys, expected_rows, name):
    if len(frame) != expected_rows or frame[keys].duplicated().any():
        raise RuntimeError(f"{name} row count or key uniqueness differs from contract")


def add_past_population_growth(frame: pd.DataFrame, epochs: list[int]) -> pd.DataFrame:
    result = frame.sort_values(["grid_id", "epoch"]).copy()
    previous = result.groupby("grid_id", sort=False)["population_total"].shift(1)
    previous_epoch = result.groupby("grid_id", sort=False)["epoch"].shift(1)
    expected_previous = {epoch: epochs[index-1] if index else None
                         for index, epoch in enumerate(epochs)}
    available = result["epoch"].map(expected_previous).notna()
    if not result.loc[available, "epoch"].map(expected_previous).eq(previous_epoch[available]).all():
        raise RuntimeError("Population growth would use a non-immediate or future epoch")
    result["population_growth_source_epoch"] = previous_epoch.astype("Int64")
    result["population_growth_prior_interval_available"] = available
    result["population_growth_prior_interval_absolute"] = result["population_total"] - previous
    denominator_valid = available & previous.gt(0)
    result["population_growth_prior_interval_fraction_defined"] = denominator_valid
    result["population_growth_prior_interval_fraction"] = np.where(
        denominator_valid,
        result["population_growth_prior_interval_absolute"] / previous,
        np.nan,
    )
    return result


def assemble_features(satellite, terrain, context, config):
    keys = ["grid_id", "epoch"]
    _require_unique(satellite, keys, config["expected_rows"], "Satellite")
    _require_unique(context, keys, config["expected_rows"], "Context")
    _require_unique(terrain, ["grid_id"], config["expected_cells"], "Terrain")
    if set(satellite["epoch"]) != set(config["epochs"]) or set(context["epoch"]) != set(config["epochs"]):
        raise RuntimeError("Feature source epochs differ from contract")
    assembled = satellite.merge(terrain, on="grid_id", how="inner", validate="many_to_one")
    assembled = assembled.merge(context, on=keys, how="inner", validate="one_to_one")
    if len(assembled) != config["expected_rows"]:
        raise RuntimeError("Feature assembly join lost or duplicated rows")
    support_columns = [f"{role}_usable_fraction_of_aoi_pixels" for role in config["roles"]]
    assembled["epoch_support_eligible"] = assembled[support_columns].ge(
        config["minimum_usable_fraction"]).all(axis=1)
    terrain_valid = assembled[["elevation_mean_m", "slope_mean_degrees"]].notna().all(axis=1)
    cell_support = assembled.groupby("grid_id")["epoch_support_eligible"].all()
    cell_terrain = pd.Series(terrain_valid.to_numpy(), index=assembled["grid_id"]).groupby(level=0).all()
    eligibility = cell_support & cell_terrain
    assembled["model_eligible_cell"] = assembled["grid_id"].map(eligibility)
    assembled = add_past_population_growth(assembled, config["epochs"])
    return assembled


def validate_assembled(frame, config):
    _require_unique(frame, ["grid_id", "epoch"], config["expected_rows"], "Assembled")
    if frame["grid_id"].nunique() != config["expected_cells"]:
        raise RuntimeError("Assembled table cell count differs from contract")
    eligible = frame.loc[frame["model_eligible_cell"], "grid_id"].nunique()
    if eligible != config["expected_eligible_cells"]:
        raise RuntimeError(f"Eligible cell count changed: {eligible}")
    first = frame["epoch"].eq(config["epochs"][0])
    if frame.loc[first, "population_growth_prior_interval_available"].any():
        raise RuntimeError("First epoch incorrectly has prior population growth")
    if frame.loc[~first, "population_growth_prior_interval_available"].eq(False).any():
        raise RuntimeError("Later epoch lacks prior population interval")
    if frame.loc[first, "population_growth_source_epoch"].notna().any():
        raise RuntimeError("First epoch contains a growth source year")
    previous_map = dict(zip(config["epochs"][1:], config["epochs"][:-1]))
    actual = frame.loc[~first, "population_growth_source_epoch"].astype(int)
    if not actual.eq(frame.loc[~first, "epoch"].map(previous_map)).all():
        raise RuntimeError("Growth source epoch violates past-only contract")
    permitted_nulls = {
        "population_growth_source_epoch",
        "population_growth_prior_interval_absolute",
        "population_growth_prior_interval_fraction",
    }
    for role in config["roles"]:
        for column in (f"{role}_unfiltered_mean_diagnostic", f"{role}_filtered_mean"):
            missing = frame[column].isna()
            if not missing.eq(frame[f"{role}_usable_pixel_count"].eq(0)).all():
                raise RuntimeError(f"{role} mean nulls do not match zero usable support")
            if frame.loc[missing, "model_eligible_cell"].any():
                raise RuntimeError(f"Eligible rows contain missing {role} means")
            permitted_nulls.add(column)
    for column, support in (("elevation_mean_m", "elevation_valid_pixel_count"),
                            ("slope_mean_degrees", "slope_valid_pixel_count")):
        missing = frame[column].isna()
        if not missing.eq(frame[support].eq(0)).all():
            raise RuntimeError(f"{column} nulls do not match zero valid support")
        if frame.loc[missing, "model_eligible_cell"].any():
            raise RuntimeError(f"Eligible rows contain missing {column}")
        permitted_nulls.add(column)
    unexpected = {name: int(count) for name, count in frame.isna().sum().items()
                  if count and name not in permitted_nulls}
    if unexpected:
        raise RuntimeError(f"Unexpected assembled feature nulls: {unexpected}")
    absolute_null = frame["population_growth_prior_interval_absolute"].isna()
    if not absolute_null.eq(first).all():
        raise RuntimeError("Absolute population growth null pattern is invalid")
    fraction_null = frame["population_growth_prior_interval_fraction"].isna()
    if not fraction_null.eq(~frame["population_growth_prior_interval_fraction_defined"]).all():
        raise RuntimeError("Population growth fraction null/flag mismatch")


def build_reports(frame, config):
    nulls = pd.DataFrame({"column": frame.columns,
                          "null_count": [int(frame[name].isna().sum()) for name in frame.columns]})
    nulls["null_fraction"] = nulls["null_count"] / len(frame)
    summary = {
        "status": "passed", "contract_version": config["contract_version"],
        "rows": len(frame), "columns": len(frame.columns),
        "unique_cells": int(frame["grid_id"].nunique()),
        "epochs": sorted(map(int, frame["epoch"].unique())),
        "eligible_cells": int(frame.loc[frame["model_eligible_cell"], "grid_id"].nunique()),
        "ineligible_cells": int(frame.loc[~frame["model_eligible_cell"], "grid_id"].nunique()),
        "growth_rows_available": int(frame["population_growth_prior_interval_available"].sum()),
        "growth_fraction_rows_defined": int(frame["population_growth_prior_interval_fraction_defined"].sum()),
        "expected_source_nulls": {name: int(frame[name].isna().sum()) for name in frame.columns
                                  if frame[name].isna().any()
                                  and not name.startswith("population_growth_")},
        "unexpected_null_columns": [],
    }
    return summary, nulls
