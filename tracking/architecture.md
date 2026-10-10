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

`src/storage/backends.py` (Phase 0 Part 0.5, **built**) — one interface (`list`, `stat`, `open_range`,
`download`, `upload`, `exists`) with three implementations: `B2Backend` (S3-compatible, maps `ClientError`
codes to `AuthFailedError`/`ReadOnlyKeyError`), `LocalBackend`, `FakeBackend` (in-memory, byte/request
counters). **No backend exposes any delete method** — enforced structurally (`dir()` check) and by a static
AST scan of all of `src/` for `delete_object`/`delete_objects`/`delete_bucket` calls. Tests use
`FakeBackend` exclusively; `B2Backend`'s error-mapping is tested by injecting a fake boto3 client (still no
real network/credentials needed) — manually verified once against the real bucket, not as an automated
test, per the plan's "tests never touch real B2" rule.

`src/storage/manifest.py` (**built**) — `Manifest`/`ManifestRecord`/`ManifestState`, the full state machine
from Section 1A.6, atomic writes (temp file + `os.replace`, so a crash mid-write can never corrupt the
real file), a portable file lock (`O_CREAT|O_EXCL`, works across processes and threads), and
`cleanup_stale_part_files()` for crash recovery.

`src/storage/guard.py` (**built**) — `check_budget(projected_bytes)` against `configs/storage.yaml`'s
150 GB cap; refuses (never deletes anything to "make room") if the budget is `null` or would be exceeded.

`src/storage/evict.py` (**built**) — `safe_evict()`, the only sanctioned local-delete path. Refuses and
writes nothing to the ledger unless both the B2 copy is verified and the derivative is validated; only a
successful eviction gets a ledger entry.

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
| `configs/storage.yaml` | Studio budget, staging cap, eviction rules (no secrets) | **Created (Part 0.4)** — everything filled in except `budget_gb` (`null`, still waiting on the user) |
| `configs/b2.yaml` | B2 endpoint, bucket, prefixes (no secrets) | **Created (Part 0.4)** — endpoint + bucket confirmed; prefixes left `null` pending Phase 2 Part 2.1's inventory |
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
| Secret detection is name-pattern-based, not hardcoded var names | Phase 0, Part 0.4 | 2026-10-10 | `src/utils/secrets.py` treats any env var whose NAME matches `KEY\|SECRET\|TOKEN\|PASSWORD\|CREDENTIAL` (case-insensitive) as holding a secret value to redact/scan for — rather than hardcoding this project's actual (unconventionally-named) `Backbaze-keyID`/`Backbaze-applicationKey` vars. Stays correct if those names ever change. |
| `AuthFailedError`/`ReadOnlyKeyError` defined in Part 0.4, raised in Part 0.5 | Phase 0, Part 0.4/0.5 | 2026-10-10 | `src/utils/env_check.py` defines the full credential-error taxonomy `plan.md` calls for (`NoCredentials`, `AuthFailed`, `ReadOnlyKey`), but only `NoCredentialsError` is actually raised in Part 0.4 (presence-only check, no network call). The other two require a real connection attempt, which is Part 0.5's `B2Backend`'s job — don't forget to actually raise them there, not just leave the classes unused. |
| numpy2 forced a coordinated dependency upgrade | Phase 0, Part 0.4 | 2026-10-10 | Current `rasterio`/`geopandas`/`rioxarray` require `numpy>=2`, incompatible with the originally-pinned `scikit-learn`/`matplotlib`/`scipy`. Upgraded the whole set together (see `bugs_and_fixes.md`) and updated `pyproject.toml` pins accordingly — if a future `pip install` of any single package complains about numpy, reinstall the whole numpy-dependent set together rather than one package at a time. |
| Boundary source: OSM Nominatim, validated by category/type, never trusted blindly | Phase 1, Part 1.1 | 2026-10-10 | `fetch_osm_boundary()` rejects a match unless `category=="boundary"` and `type` is a plausible admin-level value — catches a wrong POI match even though the query string already targets the right name. The HTTP call is injectable (`http_get` param) so tests never hit the live network, matching the `FakeBackend`-only testing philosophy used elsewhere. |
| Existing B2 data is cross-checked, never assumed trustworthy | Phase 1, Part 1.1 | 2026-10-10 | `cross_check_against_existing()` compares a freshly-fetched (verified-source) boundary against whatever's already in B2, reporting IoU/area agreement — it never treats the B2 file as ground truth on its own. In this run they matched exactly (IoU=1.0), which is itself useful evidence the existing file's provenance was legitimate — but the check exists precisely because that isn't knowable in advance. |
