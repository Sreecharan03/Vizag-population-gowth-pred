"""Phase 5.3 threshold-sensitivity analysis for immutable transition evidence."""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_threshold_sensitivity(source: pd.DataFrame, thresholds_pct: list[int]) -> pd.DataFrame:
    """Expand each transition row across thresholds without changing eligibility."""
    required = {
        "grid_id", "start_epoch", "end_epoch", "split", "delta_built_fraction",
        "negative_delta_flag", "label_eligible",
    }
    missing = required - set(source.columns)
    if missing or source[["grid_id", "start_epoch", "end_epoch"]].duplicated().any():
        raise ValueError(f"source transition schema or uniqueness is invalid: {sorted(missing)}")
    thresholds = sorted({int(value) for value in thresholds_pct})
    if not thresholds or any(value <= 0 or value >= 100 for value in thresholds):
        raise ValueError("threshold percentages must be unique values within (0,100)")
    frames = []
    for threshold_pct in thresholds:
        frame = source[[
            "grid_id", "start_epoch", "end_epoch", "split",
            "delta_built_fraction", "negative_delta_flag", "label_eligible",
        ]].copy()
        frame["threshold_pct"] = threshold_pct
        frame["threshold_fraction"] = threshold_pct / 100.0
        frame["growth_label"] = pd.array(
            np.where(frame["label_eligible"],
                     frame["delta_built_fraction"].ge(threshold_pct / 100.0), None),
            dtype="Int8")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True).sort_values(
        ["grid_id", "start_epoch", "end_epoch", "threshold_pct"]
    ).reset_index(drop=True)


def validate_threshold_sensitivity(
    frame: pd.DataFrame, *, expected_cells: int, expected_rows: int,
    expected_source_rows: int, thresholds_pct: list[int], transitions: list[list],
) -> None:
    """Validate completeness, null policy, recomputation and monotonic nesting."""
    keys = ["grid_id", "start_epoch", "end_epoch", "threshold_pct"]
    thresholds = sorted({int(value) for value in thresholds_pct})
    expected_transitions = {(int(a), int(b)) for a, b, *_ in transitions}
    actual_transitions = set(map(tuple, frame[["start_epoch", "end_epoch"]]
                                 .drop_duplicates().to_numpy()))
    if (len(frame) != expected_rows or frame[keys].duplicated().any()
            or frame["grid_id"].nunique() != expected_cells
            or set(frame["threshold_pct"].unique()) != set(thresholds)
            or actual_transitions != expected_transitions
            or len(frame.drop_duplicates(keys[:-1])) != expected_source_rows):
        raise RuntimeError("threshold-sensitivity completeness or uniqueness gate failed")
    excluded = ~frame["label_eligible"]
    if frame.loc[excluded, "growth_label"].notna().any():
        raise RuntimeError("excluded sensitivity rows contain labels")
    eligible = frame.loc[~excluded]
    expected = eligible["delta_built_fraction"].ge(eligible["threshold_fraction"]).astype("int8")
    if (eligible["growth_label"].isna().any()
            or not eligible["growth_label"].astype("int8").reset_index(drop=True)
            .equals(expected.reset_index(drop=True))):
        raise RuntimeError("sensitivity labels do not match their thresholds")
    if frame.loc[frame["negative_delta_flag"] & ~excluded, "growth_label"].ne(0).any():
        raise RuntimeError("negative deltas were not retained as label zero")
    wide = eligible.pivot(index=["grid_id", "start_epoch", "end_epoch"],
                          columns="threshold_pct", values="growth_label")
    for lower, higher in zip(thresholds[:-1], thresholds[1:]):
        if (wide[higher].astype(int) > wide[lower].astype(int)).any():
            raise RuntimeError(f"positive labels are not nested at {lower}% and {higher}%")


def build_comparison(frame: pd.DataFrame, imbalance_warning_fraction: float) -> pd.DataFrame:
    """Summarize class balance for every transition and threshold."""
    rows = []
    for (start, end, split, threshold), group in frame.groupby(
            ["start_epoch", "end_epoch", "split", "threshold_pct"], sort=True):
        eligible = group[group["label_eligible"]]
        labels = eligible["growth_label"].astype(int)
        positives = int(labels.sum())
        positive_fraction = float(labels.mean()) if len(labels) else np.nan
        rows.append({
            "transition": f"{start}-{end}", "start_epoch": int(start),
            "end_epoch": int(end), "split": split, "threshold_pct": int(threshold),
            "total_rows": len(group), "eligible_rows": len(eligible),
            "excluded_rows": int((~group["label_eligible"]).sum()),
            "positive_labels": positives, "negative_labels": int(len(labels) - positives),
            "positive_fraction": positive_fraction,
            "imbalance_warning": bool(positive_fraction < imbalance_warning_fraction
                                      or positive_fraction > 1 - imbalance_warning_fraction),
            "negative_delta_rows": int(group["negative_delta_flag"].sum()),
        })
    return pd.DataFrame(rows)


def label_change_summary(frame: pd.DataFrame, thresholds_pct: list[int]) -> dict:
    """Count eligible cells whose labels change between adjacent thresholds."""
    eligible = frame[frame["label_eligible"]]
    wide = eligible.pivot(index=["grid_id", "start_epoch", "end_epoch"],
                          columns="threshold_pct", values="growth_label")
    thresholds = sorted({int(value) for value in thresholds_pct})
    result = {}
    for lower, higher in zip(thresholds[:-1], thresholds[1:]):
        changed = wide[lower].astype(int).ne(wide[higher].astype(int))
        result[f"{lower}_to_{higher}"] = {
            "changed_labels": int(changed.sum()),
            "eligible_rows": len(wide),
            "changed_fraction": float(changed.mean()),
        }
    return result
