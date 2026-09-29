# Project Overview

**Read after [`tracking.md`](tracking.md).** This is the condensed summary. The full authoritative spec
lives in [`../plan.md`](../plan.md) at repo root — this file never duplicates its detail, only summarizes
it so a new session gets oriented fast.

## What this project is

Explainable multimodal GeoAI system for Visakhapatnam (Vizag), India, that predicts urban expansion and
infrastructure pressure.

Pipeline, end to end:

```
Sentinel-2 time series (2018–2024/25)
   → cloud-free composites & spectral indices (NDVI, NDBI, NDWI, MNDWI, BSI)
   → 500 m analysis grid
   → multimodal feature aggregation (satellite + population + OSM roads/amenities + terrain)
   → leakage-safe binary growth labels (ΔBuiltFraction ≥ τ)
   → baseline model (logistic regression, E1)
   → multimodal tree-ensemble ablation (E2 +population, E3 +roads, E4 full)
   → SHAP explainability (global, local, spatial)
   → 2030 growth-probability prediction
   → Infrastructure Pressure Index (equal-weighted + entropy-weighted)
```

## Non-negotiable constraints

- **~190 GB of Sentinel-2 data is already downloaded** (expected total ~225 GB). It must never be
  re-downloaded from Copernicus. See [`architecture.md`](architecture.md) for the storage-tier design that
  enforces this.
- **Backblaze B2 is the permanent source of truth.** Nothing is ever deleted from B2. The Lightning Studio
  disk is scratch + a capped working set only.
- **One-part-at-a-time workflow.** Every unit of implementation ("part," the smallest item under a phase's
  "Implementation steps" in `plan.md`) requires: PROPOSE → explicit user "yes" → IMPLEMENT only that part →
  TEST (incl. full regression) → REPORT in plain language → WAIT again. Never bundle parts. Every phase
  ends in a **Phase Gate** needing explicit user confirmation before the next phase starts.

## The 12 phases (see `plan.md` for full detail on each)

| # | Phase | One-line objective |
|---|---|---|
| 0 | Project scaffolding & environment | Working empty-but-correct skeleton + storage layer |
| 1 | Study boundary & configuration | Lock GVMC boundary, CRS, buffer, temporal/grid/label params |
| 2 | B2 inventory, reconciliation & acquisition | Find what's already in B2; fetch only what's missing |
| 3 | Advanced Sentinel-2 preprocessing | Budget-aware composites + indices, never materializing full archive |
| 4 | Grid construction & feature aggregation | Build 500 m grid, aggregate all sources onto it |
| 5 | Label generation | Leakage-safe growth label, threshold sensitivity (5/10/20%) |
| 6 | Dataset assembly & split | Leakage check, temporal holdout + spatial-block CV, E1–E4 datasets |
| 7 | Baseline model (E1) | Logistic regression sanity-check of the whole pipeline |
| 8 | Multimodal models & ablation (E2–E4) | RF/XGBoost/LightGBM, ablation comparison with bootstrap CIs |
| 9 | Explainability (SHAP) | Global, local, spatial SHAP for the selected best model |
| 10 | 2030 prediction & Infrastructure Pressure Index | Growth probability + accessibility-gap pressure index |
| 11 | Final report, reproducibility & documentation | End-to-end rerun proof, final report, polished README |

For current status against this list, see [`progress.md`](progress.md).
