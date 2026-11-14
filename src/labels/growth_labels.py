"""Leakage-safe Phase 5.2 transition-label construction."""
from __future__ import annotations

import numpy as np
import pandas as pd


def manifest_output_identity(manifest: dict, key: str) -> dict:
    """Return one output identity from either supported manifest representation."""
    outputs = manifest.get("outputs")
    if isinstance(outputs, dict):
        matches = [value for value in outputs.values()
                   if isinstance(value, dict) and value.get("key") == key]
    elif isinstance(outputs, list):
        matches = [value for value in outputs
                   if isinstance(value, dict) and value.get("key") == key]
    else:
        raise ValueError("manifest outputs must be a mapping or list")
    if len(matches) != 1:
        raise ValueError(f"manifest must contain exactly one output for {key}")
    identity = matches[0]
    if not all(field in identity for field in ("key", "bytes", "sha256")):
        raise ValueError(f"manifest output identity is incomplete for {key}")
    return identity


def aggregate_class_fraction(
    classes: np.ndarray,
    cells: np.ndarray,
    *,
    expected_cells: int,
    target_class: int,
    nodata: int,
) -> dict[str, np.ndarray]:
    """Aggregate a categorical raster into per-cell target-class fractions."""
    if classes.shape != cells.shape or classes.ndim != 2:
        raise ValueError("class and cell rasters must be aligned 2D grids")
    valid = (classes != nodata) & (cells > 0)
    ids = cells[valid].astype("int64", copy=False)
    if ids.size == 0 or ids.min() < 1 or ids.max() > expected_cells:
        raise ValueError("cell raster has no valid in-contract pixels")
    counts = np.bincount(ids, minlength=expected_cells + 1)[1:]
    target = np.bincount(
        ids,
        weights=(classes[valid] == target_class),
        minlength=expected_cells + 1,
    )[1:]
    fractions = np.full(expected_cells, np.nan, dtype="float64")
    supported = counts > 0
    fractions[supported] = target[supported] / counts[supported]
    return {
        "water_evidence_available": supported,
        "water_valid_pixel_count": counts.astype("int64"),
        "water_pixel_count": target.astype("int64"),
        "water_fraction": fractions,
    }


def build_transition_labels(
    built: pd.DataFrame,
    eligibility: pd.DataFrame,
    water: pd.DataFrame,
    policy: dict,
) -> pd.DataFrame:
    """Build all contracted transitions using endpoint evidence only."""
    required_built = {"grid_id", "epoch", "evidence_available", "modal_built_fraction"}
    required_eligibility = {"grid_id", "epoch", "model_eligible_cell"}
    required_water = {
        "grid_id", "epoch", "water_evidence_available", "water_valid_pixel_count",
        "water_pixel_count", "water_fraction",
    }
    for frame, required, name in (
        (built, required_built, "built"),
        (eligibility, required_eligibility, "eligibility"),
        (water, required_water, "water"),
    ):
        missing = required - set(frame.columns)
        if missing or frame[["grid_id", "epoch"]].duplicated().any():
            raise ValueError(f"{name} evidence schema or key uniqueness is invalid: {sorted(missing)}")

    cell_eligibility = eligibility.groupby("grid_id")["model_eligible_cell"].agg(["min", "max"])
    if not cell_eligibility["min"].eq(cell_eligibility["max"]).all():
        raise ValueError("model eligibility changes between epochs")
    eligible_map = cell_eligibility["min"].astype(bool)
    built_index = built.set_index(["grid_id", "epoch"])
    water_index = water.set_index(["grid_id", "epoch"])
    all_cells = sorted(built["grid_id"].astype(str).unique())
    if len(all_cells) != int(policy["expected_cells"]):
        raise ValueError("built evidence cell count differs from contract")

    threshold = float(policy["candidate_threshold_pct"]) / 100.0
    already_built = float(policy["already_built_exclusion_pct"]) / 100.0
    water_threshold = float(policy["water_fraction_exclusion_threshold"])
    rows: list[pd.DataFrame] = []
    for start, end, split in policy["transitions"]:
        keys_start = pd.MultiIndex.from_product([all_cells, [int(start)]], names=["grid_id", "epoch"])
        keys_end = pd.MultiIndex.from_product([all_cells, [int(end)]], names=["grid_id", "epoch"])
        if not keys_start.isin(built_index.index).all() or not keys_end.isin(built_index.index).all():
            raise ValueError(f"missing endpoint built evidence for {start}-{end}")
        start_built = built_index.loc[keys_start].reset_index(drop=True)
        end_built = built_index.loc[keys_end].reset_index(drop=True)
        if not keys_start.isin(water_index.index).all():
            raise ValueError(f"missing start-year water evidence for {start}-{end}")
        start_water = water_index.loc[keys_start].reset_index(drop=True)
        frame = pd.DataFrame({
            "grid_id": all_cells,
            "start_epoch": int(start),
            "end_epoch": int(end),
            "split": str(split),
            "built_fraction_t1": start_built["modal_built_fraction"].to_numpy(),
            "built_fraction_t2": end_built["modal_built_fraction"].to_numpy(),
            "built_evidence_t1": start_built["evidence_available"].astype(bool).to_numpy(),
            "built_evidence_t2": end_built["evidence_available"].astype(bool).to_numpy(),
            "model_eligible_cell": pd.Series(all_cells).map(eligible_map).astype(bool),
            "water_evidence_t1": start_water["water_evidence_available"].astype(bool).to_numpy(),
            "water_valid_pixel_count_t1": start_water["water_valid_pixel_count"].to_numpy(),
            "water_pixel_count_t1": start_water["water_pixel_count"].to_numpy(),
            "water_fraction_t1": start_water["water_fraction"].to_numpy(),
        })
        frame["delta_built_fraction"] = frame["built_fraction_t2"] - frame["built_fraction_t1"]
        frame["negative_delta_flag"] = frame["delta_built_fraction"].lt(0).fillna(False)
        frame["excluded_missing_evidence"] = ~(
            frame["built_evidence_t1"] & frame["built_evidence_t2"] & frame["water_evidence_t1"]
        )
        frame["excluded_analysis_ineligible"] = ~frame["model_eligible_cell"]
        frame["excluded_already_built"] = frame["built_fraction_t1"].ge(already_built).fillna(False)
        frame["excluded_majority_water"] = frame["water_fraction_t1"].ge(water_threshold).fillna(False)
        exclusion_columns = [
            "excluded_missing_evidence", "excluded_analysis_ineligible",
            "excluded_already_built", "excluded_majority_water",
        ]
        frame["label_eligible"] = ~frame[exclusion_columns].any(axis=1)
        frame["growth_label_candidate"] = pd.array(
            np.where(frame["label_eligible"], frame["delta_built_fraction"].ge(threshold), None),
            dtype="Int8",
        )
        frame["candidate_threshold_fraction"] = threshold
        frame["protected_area_status"] = str(policy["protected_area_status"])
        rows.append(frame)
    return pd.concat(rows, ignore_index=True).sort_values(
        ["grid_id", "start_epoch", "end_epoch"]
    ).reset_index(drop=True)


def validate_transition_labels(frame: pd.DataFrame, policy: dict) -> None:
    """Enforce completeness, exclusion, endpoint and label invariants."""
    keys = ["grid_id", "start_epoch", "end_epoch"]
    expected_transitions = {(int(a), int(b)) for a, b, _ in policy["transitions"]}
    actual_transitions = set(map(tuple, frame[["start_epoch", "end_epoch"]].drop_duplicates().to_numpy()))
    if (len(frame) != int(policy["expected_rows"]) or frame[keys].duplicated().any()
            or frame["grid_id"].nunique() != int(policy["expected_cells"])
            or actual_transitions != expected_transitions):
        raise RuntimeError("transition completeness or uniqueness gate failed")
    excluded = ~frame["label_eligible"]
    if frame.loc[excluded, "growth_label_candidate"].notna().any():
        raise RuntimeError("excluded rows contain labels")
    labels = frame.loc[~excluded, "growth_label_candidate"]
    if labels.isna().any() or not set(labels.astype(int).unique()).issubset({0, 1}):
        raise RuntimeError("eligible rows do not contain binary labels")
    expected_delta = frame["built_fraction_t2"] - frame["built_fraction_t1"]
    if not np.allclose(frame["delta_built_fraction"], expected_delta, equal_nan=True):
        raise RuntimeError("built-fraction delta is inconsistent with endpoints")
    threshold = float(policy["candidate_threshold_pct"]) / 100.0
    expected_label = frame.loc[~excluded, "delta_built_fraction"].ge(threshold).astype("int8")
    if not labels.astype("int8").reset_index(drop=True).equals(expected_label.reset_index(drop=True)):
        raise RuntimeError("candidate labels differ from the configured threshold")
    if frame.loc[frame["negative_delta_flag"] & ~excluded, "growth_label_candidate"].ne(0).any():
        raise RuntimeError("eligible negative deltas were not retained as label zero")
