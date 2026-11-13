"""Part 5.1 multi-index built-pixel classification and reference metrics."""
from __future__ import annotations

import itertools
import numpy as np


def candidate_rules(config: dict) -> list[dict]:
    pilot = config["pilot"]
    rules = [{"name": f"ndbi_{n:+.2f}_ndvi_{v:.2f}_mndwi_{w:.2f}",
              "ndbi_min": float(n), "ndvi_max": float(v), "mndwi_max": float(w),
              "require_ndbi_gt_ndvi": bool(pilot["require_ndbi_gt_ndvi"])}
             for n, v, w in itertools.product(pilot["ndbi_thresholds"], pilot["ndvi_caps"], pilot["mndwi_caps"])]
    if len({rule["name"] for rule in rules}) != len(rules) or not rules:
        raise RuntimeError("Built-up candidate rule grid is empty or non-unique")
    return rules


def valid_index_mask(arrays: dict[str, np.ndarray], nodata: dict[str, float | None]) -> np.ndarray:
    valid = np.ones(next(iter(arrays.values())).shape, dtype=bool)
    for role, values in arrays.items():
        valid &= np.isfinite(values)
        if nodata.get(role) is not None:
            valid &= values != nodata[role]
    return valid


def classify(arrays: dict[str, np.ndarray], rule: dict, valid: np.ndarray) -> np.ndarray:
    built = ((arrays["ndbi"] > rule["ndbi_min"])
             & (arrays["ndvi"] < rule["ndvi_max"])
             & (arrays["mndwi"] < rule["mndwi_max"])
             & valid)
    if rule["require_ndbi_gt_ndvi"]:
        built &= arrays["ndbi"] > arrays["ndvi"]
    return built


def confusion(predicted: np.ndarray, reference: np.ndarray, valid: np.ndarray) -> dict[str, int]:
    p, r = predicted[valid], reference[valid]
    return {"tp": int(np.count_nonzero(p & r)), "tn": int(np.count_nonzero(~p & ~r)),
            "fp": int(np.count_nonzero(p & ~r)), "fn": int(np.count_nonzero(~p & r))}


def metrics(counts: dict[str, int]) -> dict[str, float | int]:
    tp, tn, fp, fn = (counts[k] for k in ("tp", "tn", "fp", "fn"))
    def ratio(a, b): return float(a / b) if b else 0.0
    precision, recall = ratio(tp, tp+fp), ratio(tp, tp+fn)
    specificity = ratio(tn, tn+fp)
    return {**counts, "pixels": tp+tn+fp+fn, "precision": precision, "recall": recall,
            "specificity": specificity, "f1": ratio(2*precision*recall, precision+recall),
            "balanced_accuracy": (recall+specificity)/2,
            "predicted_built_fraction": ratio(tp+fp, tp+tn+fp+fn),
            "reference_built_fraction": ratio(tp+fn, tp+tn+fp+fn)}


def select_rule(per_rule: dict[str, dict[int, dict]]) -> dict:
    scored = []
    for name, epochs in per_rule.items():
        if set(epochs) != {2020, 2022}:
            raise RuntimeError("Rule selection requires both bracketing epochs")
        worst = min(epochs[year]["balanced_accuracy"] for year in epochs)
        drift = abs(epochs[2022]["predicted_built_fraction"]-epochs[2020]["predicted_built_fraction"])
        mean_f1 = sum(epochs[year]["f1"] for year in epochs)/2
        scored.append((worst, mean_f1, -drift, name))
    winner = max(scored)
    return {"name": winner[3], "worst_year_balanced_accuracy": winner[0],
            "mean_f1": winner[1], "predicted_fraction_drift": -winner[2]}
