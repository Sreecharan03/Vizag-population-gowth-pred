# Technical Architecture

**Read after [`tracking.md`](tracking.md) and [`overview.md`](overview.md).** Full detail is in
[`../plan.md`](../plan.md) Sections 1 and 1A — this file summarizes it and tracks which architectural
decisions have actually been locked in (as opposed to just specified in the plan).

## Storage tiers

| Tier | Location | Contents | Rule |
|---|---|---|---|
| 0 — Cold raw | Backblaze B2 | Full raw Sentinel-2 archive + everything downloaded so far | Read-only, source of truth, never deleted |
| 1 — Staging | `data/staging/` (Studio) | In-flight raw objects, one unit of work at a time | Hard-capped (`staging.max_gb`), emptied after each unit |
| 2 — Hot working set | `data/processed/`, `data/derived/`, `data/raw_small/` (Studio) | Clipped stacks, composites, indices, grid, features, labels, models | Must fit `studio.budget_gb` |
| 3 — Warm backup | B2 (separate prefix) | Backup of Tier 2 + manifests + models + results | Lets a fresh Studio rebuild without reprocessing |

Manifest state machine (one record per object/unit of work):

```
LISTED → PLANNED → FETCHING → FETCHED → VERIFIED → PROCESSED → ARCHIVED → EVICTED
                       └────────────► FAILED(reason, retries, last_error)
```

`safe_evict()` is the *only* sanctioned path to remove a local raw file, and only fires if: (a) its B2 copy
is verified, (b) its derivative exists and passed validation, (c) the action is written to the eviction
ledger (`data/manifests/eviction_ledger.jsonl`).

Golden rules enforced by tests (full list in `plan.md` Section 1A.4): raw never lives fully on Studio; clip
at ingest to the buffered boundary; read only the 6 needed bands (B02,B03,B04,B08,B11,B12) + SCL; SCL-first
triage before pulling 10 m bands; one unit of work at a time; COG/Parquet-only outputs; storage guard before
every heavy operation; secrets only via env vars, never in `configs/`.

## Backend abstraction

`src/storage/backends.py` (Phase 0 Part 0.5) — one interface (`list`, `stat`, `open_range`, `download`,
`upload`, `exists`) with three implementations: `B2Backend` (S3-compatible), `LocalBackend`, `FakeBackend`
(in-memory, byte/request counters). All acquisition/preprocessing code depends only on the interface; tests
use `FakeBackend` exclusively — nothing in `tests/` may require real B2 credentials.

## Target repo layout

Full tree is in `plan.md` Section 1 — not reproduced here to avoid two copies drifting apart. Key
top-level dirs once scaffolding exists:

```
configs/    — boundary, temporal, grid, label, model, paths, storage, b2, data_requirements (all non-secret)
data/       — NOT in git; manifests, staging (capped), raw_small, boundaries, processed, derived, external_validation
src/        — storage, acquisition, preprocessing, grid, labels, features, splitting, models, explainability,
              prediction, infra_pressure, utils
tests/      — unit, integration, fixtures
models/     — gitignored, saved model artifacts
predictions/— gitignored, output rasters/maps
results/    — metrics, SHAP plots, figures (in git)
logs/       — gitignored, per-phase run logs
```

**Path rule (enforced from Phase 0 onward):** every file destination must resolve through
`configs/paths.yaml` via `resolve_path()` — never a literal path string inside a processing module.
Checked by `tests/unit/test_no_hardcoded_paths.py`.

## Config files and their status

| Config | Purpose | Status |
|---|---|---|
| `configs/paths.yaml` | Single source of truth for all directory paths | **Created (Part 0.2)** |
| `configs/storage.yaml` | Studio budget, staging cap, eviction rules (no secrets) | Not created (Part 0.4); `budget_gb` must come from user |
| `configs/b2.yaml` | B2 endpoint, bucket, prefixes (no secrets) | Not created (Part 0.4); values must come from user |
| `configs/boundary.yaml` | Study area source, CRS (`EPSG:32644`), buffer distance | Not created (Part 1.1) |
| `configs/temporal.yaml` | Epochs, transition pairs, holdout split | Not created (Part 1.2) |
| `configs/grid.yaml` | Grid cell size (500 m), exclusions | Not created (Part 1.2) |
| `configs/label.yaml` | Growth threshold values (5/10/20%, primary 10%) | Not created (Part 1.2) |
| `configs/model.yaml` | Model hyperparameters per experiment | Not created (Phase 8) |
| `configs/data_requirements.yaml` | What data each epoch/source needs | Not created (Part 2.2) |

Secrets (`B2_KEY_ID`, `B2_APP_KEY` or S3-style equivalents) come from **Lightning Studio secrets /
environment variables only** — never from a repo file. If you find a `.env` file in this repo, treat it as
a local-only credential holder that must stay out of git (`.gitignore`) and must never be read into logs,
configs, or committed anywhere; confirm it's gitignored before touching it.

## Architectural decisions log

Fill in as ADRs and irreversible design choices get made (e.g., Phase 3 Part 3.0's read-strategy decision).

| Decision | Phase/Part | Date | Notes |
|---|---|---|---|
| `validation.py` avoids hard dependency on geopandas/rasterio/pyproj | Phase 0, Part 0.3 | 2026-09-29 | Those aren't installed until Part 0.4. `assert_crs` duck-types any CRS-like object (string, int, or one exposing `to_epsg()`/`to_string()`) instead of importing `pyproj.CRS` directly, so shared assertions work before and after the geospatial stack lands. |
| `assert_nodata_consistent` checks both directions | Phase 0, Part 0.3 | 2026-09-29 | Not just "no sentinel where valid" but also "sentinel present everywhere flagged nodata" — matches Phase 3's "nodata stays nodata, never read as 0 reflectance" and Phase 4's "empty cell → NaN, never coerced to 0" concerns from `plan.md`. |
| Credential redaction lives in Part 0.4, not the Part 0.3 logger | Phase 0, Part 0.3/0.4 | 2026-09-29 | `plan.md` places the redaction edge case and its test (`test_logger_redacts_credential_patterns`) under Parts 0.4–0.5, and no secret flows through logging yet — deferred rather than scope-creeping into 0.3. Must not be forgotten when 0.4 is implemented. |
