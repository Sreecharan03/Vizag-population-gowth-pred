# Visakhapatnam GeoAI — End-to-End Implementation Plan

**Project:** Explainable Multimodal GeoAI for Urban Expansion & Infrastructure Pressure Prediction — Visakhapatnam
**Purpose of this file:** This is the operating manual for building the project with Claude Code. It defines a strict phase-by-phase workflow, the directory structure that must exist at the end of each phase, the edge cases each phase must handle, the tests that must pass before moving on, and the human-in-the-loop checkpoint protocol. Keep this file at the repo root as `PLAN.md` (or `CLAUDE.md`) so Claude Code reads it at the start of every session.

> **Revision 2 — environment & storage constraints (supersedes any earlier "download everything" assumption).**
> - Work happens in a **new Lightning AI Studio**. Studio persistent storage is limited and billed beyond the plan's tier, so **the Studio cannot hold the full ~190–225 GB raw dataset**.
> - About **190 GB of Vizag data (mostly Sentinel-2) is already downloaded** and must **not be downloaded again from the original providers**. The expected full set is ~225 GB, so roughly **35 GB remains** — *to be confirmed by inventory, never assumed*.
> - **Backblaze B2 is the source of truth for raw data.** The Studio is only a scratch + working area. See **Section 1A** (storage strategy), **Phase 0.4–0.5** (environment + storage layer), **Phase 2** (B2 inventory + resume the remaining part) and **Phase 3** (budget-aware preprocessing).

---

## 0. How to work through this plan (read this first)

This is not a "build everything" instruction. It is a **one-part-at-a-time, human-approved** workflow. Follow this loop exactly, for every phase and every part within a phase:

```
1. PROPOSE  → Read the relevant phase section below. Post a short plan for the
              NEXT PART ONLY (not the whole phase): what files will be created/
              changed, what it will do, what edge cases it will handle, what
              tests will be written. End with: "Reply 'yes' to implement this,
              or tell me what to change."
2. WAIT     → Do not write any code until the user replies "yes" (or gives
              corrected instructions). If corrected, revise the plan and ask
              again. Never skip ahead to the next part on your own.
3. IMPLEMENT→ Once approved, implement exactly that part. Nothing more.
4. TEST     → Run the test suite for that part (and the regression suite for
              everything built so far). Fix failures before reporting back.
5. REPORT   → Tell the user, in plain language: what was built, where the
              files are, what the tests checked and their result (pass/fail
              counts), any edge case that could not be fully handled and why,
              and what the NEXT PART will be.
6. WAIT     → Stop. Do not start the next part until the user says "yes"
              again.
```

**Rules that apply throughout:**
- Never implement more than one "part" per approval. A "part" is the smallest unit listed under each phase's **Implementation steps**.
- Never skip the edge-case handling or the tests for a part to "move faster" — a part is not done until its tests pass.
- If a test fails, fix it and re-run before reporting back; do not report a failing part as done.
- If any step needs credentials, a bucket name, a storage limit, or a manual action from the user (B2 keys, Lightning storage cap, etc.), say so explicitly and pause. Never guess these values and never hardcode them.
- **Data-safety rules (the ~190 GB is irreplaceable time and money):**
  - Before ANY command that downloads, uploads, moves or deletes data, print the **estimated bytes, source, destination and whether it is reversible**, and get an explicit "yes" — even inside an already-approved part.
  - **Never** run `rclone sync`, `rclone move`, `b2 delete`, `aws s3 rm`, `rm -rf data/...` or any command with a delete flag against B2 or `data/`. Use **copy-only** semantics. Deleting a local raw object is allowed only through the project's `safe_evict()` function (Section 1A, rule 7).
  - Every heavy operation calls the **storage guard** first (Section 1A). If the guard says the Studio budget would be exceeded, stop and report; do not "make room" by deleting things.
  - Default every acquisition/eviction command to `--dry-run`. A real run needs a separate, explicit approval.
- Every phase ends with a **Phase Gate**: a short checklist the user should be able to visually confirm before the project moves to the next phase.
- Config values (paths, dates, thresholds) belong in `configs/`, never hardcoded inside processing scripts.

---

## 1. Repository layout (target end-state)

This is what the repository looks like once every phase is complete. Individual phases below only create the parts relevant to them — do not create empty placeholder folders for future phases ahead of time.

```
vizag-geoai/
├── PLAN.md                        # this file
├── README.md                      # short human-facing project summary
├── pyproject.toml / requirements.txt
├── .gitignore
├── configs/
│   ├── boundary.yaml               # study area, CRS, buffer
│   ├── temporal.yaml                # epochs, transition pairs, holdout split
│   ├── grid.yaml                     # grid size, exclusions
│   ├── label.yaml                     # threshold(s), sensitivity values
│   ├── model.yaml                      # model hyperparameters per experiment
│   ├── paths.yaml                       # all directory paths, single source of truth
│   ├── storage.yaml                      # Studio budget, staging cap, eviction rules (NO secrets)
│   ├── b2.yaml                            # endpoint, bucket, prefixes (NO secrets)
│   └── data_requirements.yaml              # what data each epoch/source needs (drives inventory diff)
├── data/                            # NOT in git. Only Tier 2 (+ tiny staging) lives here long-term
│   ├── manifests/                  # inventory, plans, state machine, eviction ledger (backed up to B2)
│   ├── staging/                    # Tier 1: in-flight raw objects, hard-capped, emptied after each unit of work
│   ├── raw_small/                  # small raw sources kept locally: WorldPop, OSM, DEM, WorldCover (also in B2)
│   ├── boundaries/                 # study boundary files
│   ├── processed/                  # Tier 2: clipped scene stacks, composites, indices (COG)
│   ├── derived/                    # Tier 2: grid, aggregated features, labels (Parquet)
│   └── external_validation/        # census, any manual ground-truth samples
#   NOTE: there is intentionally NO data/raw/sentinel2/ full copy. Raw Sentinel-2 lives in B2 (Tier 0).
├── src/
│   ├── __init__.py
│   ├── storage/                    # backend abstraction (B2 / local / fake), manifest, storage guard, safe_evict
│   ├── acquisition/                # inventory, reconciliation, resumable fetch of missing data
│   ├── preprocessing/              # masking, reprojection, compositing, indices
│   ├── grid/                       # grid construction, feature aggregation
│   ├── labels/                     # built-up classification, label generation
│   ├── features/                   # final feature table assembly, leakage checks
│   ├── splitting/                  # temporal + spatial-block split logic
│   ├── models/                     # baseline, tree ensembles, training loops
│   ├── explainability/             # SHAP computation and spatial mapping
│   ├── prediction/                 # 2030 inference
│   ├── infra_pressure/             # accessibility + pressure index
│   └── utils/                      # shared I/O, logging, validation helpers
├── tests/
│   ├── unit/                       # one test module per src/ submodule
│   ├── integration/                # cross-module pipeline tests
│   └── fixtures/                   # tiny synthetic datasets for fast tests
├── notebooks/                      # exploratory only, nothing pipeline-critical lives here
├── models/                         # saved trained model artifacts (.pkl/.json), gitignored
├── predictions/                    # output rasters/maps, gitignored
├── results/                        # metrics tables, SHAP plots, figures
└── logs/                           # run logs per phase, gitignored
```

**Validation rule for this phase:** before any phase writes a file, it must resolve the destination path through `configs/paths.yaml` — never a literal string path inside a processing module. This is checked by a lint test (`tests/unit/test_no_hardcoded_paths.py`) from Phase 0 onward.

---

## 1A. Storage & data strategy (NEW — governs every phase)

### 1A.1 Situation

| Fact | Consequence for the plan |
|---|---|
| ~190 GB already downloaded (mostly Sentinel-2 for Vizag), ~225 GB expected in total | **Do not re-download** satellite data from Copernicus. Only the remaining ~35 GB (verify!) may be fetched, and only after inventory proves it is missing |
| Lightning AI charges for persistent storage beyond the plan tier | Studio disk must stay under a **user-set budget**; the full raw set never sits on the Studio |
| Backblaze B2 holds (or will hold) the raw data | B2 = **Tier 0 source of truth**; the pipeline *reads from* it and never mutates it |
| A Sentinel-2 tile covers roughly 110 × 110 km, but the study area + buffer is a small fraction of that | **Clip at ingest** — the working set shrinks by one to two orders of magnitude |
| Only 6 spectral bands + SCL are used (B02, B03, B04, B08, B11, B12, SCL) | **Read only those files** — skip other bands, TCI, AOT, WVP, R60m, previews |

### 1A.2 Assumptions to CONFIRM at Part 2.1 (do not silently rely on them)

- **A1.** The ~190 GB is already in a B2 bucket. *If it is instead still on an old Studio disk / external drive, the first job is to upload it to B2 (copy-only, verified) **before that disk is deleted**.*
- **A2.** The B2 bucket exposes the S3-compatible endpoint, and the provided application key has at least **read** scope (and **write** scope only if remaining data will be added to B2).
- **A3.** The user provides the real Lightning storage cap → `studio.budget_gb` in `configs/storage.yaml`. The plan works with any number; it must be set explicitly.
- **A4.** The stored Sentinel-2 format is known: unzipped `.SAFE` folders vs `.zip` archives (this decides the read strategy in Phase 3.0).
- **A5.** B2 egress and per-request (transaction) pricing has been checked by the user for their account; the benchmark in Phase 3.0 records request counts so cost can be estimated before a large run.

### 1A.3 The four storage tiers

| Tier | Location | Contents | Lifetime | Size rule |
|---|---|---|---|---|
| **0 — Cold raw** | B2 | Full raw archive (all Sentinel-2, everything downloaded so far) | Permanent, **read-only for this project** | Not counted against Studio |
| **1 — Staging** | `data/staging/` (Studio) | Raw objects currently being processed (one unit of work / small batch) | Minutes; emptied after each unit | Hard cap `staging.max_gb` |
| **2 — Hot working set** | `data/processed`, `data/derived`, `data/raw_small` (Studio) | Clipped scene stacks, composites, indices, grid, features, labels, models | Persistent | Must fit `studio.budget_gb` with margin |
| **3 — Warm backup** | B2 (separate prefix) | Backup of Tier 2 + manifests + models + results | Permanent | Lets a brand-new Studio be rebuilt without re-processing |

### 1A.4 Golden rules (each one is enforced by a test)

1. **Raw never lives fully on the Studio.** Only Tier 1 (capped) and Tier 2.
2. **Clip early.** Every read is windowed to the buffered study boundary; full tiles are never written to disk.
3. **Read only what is needed.** Band-subset + window, not whole products.
4. **Triage before heavy reads.** Use the small SCL layer (and metadata) to compute study-area cloud fraction first; pull 10 m bands only for the scenes that will actually be used.
5. **One unit of work at a time.** Unit = one scene → one clipped stack. Process, validate, record, evict staging, next.
6. **Cloud-friendly outputs.** COG (zstd/deflate + predictor) for rasters, Parquet for tables. No uncompressed GeoTIFF, no shapefile for large tables.
7. **`safe_evict()` is the only way a local raw file is removed**, and only if (a) its B2 copy is verified, (b) its derivative exists and passed validation, (c) the action is written to the eviction ledger. Never delete anything from B2.
8. **Storage guard before every heavy operation** (download, extract, composite, training). It checks free disk, current Tier 1/Tier 2 size, and projected growth vs budget.
9. **Secrets never touch the repo.** Credentials come from Lightning Studio secrets / environment variables (`B2_KEY_ID`, `B2_APP_KEY`, or the S3-style equivalents). `configs/` holds only non-secret settings.
10. **All state lives in a manifest**, so a Studio stop/restart/crash resumes exactly where it left off with no duplicated work.

### 1A.5 Config skeletons (values marked `null` MUST be supplied by the user)

```yaml
# configs/storage.yaml
studio:
  workspace_root: null        # auto-detected; Claude Code confirms with `pwd` and `df -h`
  budget_gb: null             # USER MUST SET: Lightning plan limit minus safety margin
  warn_at_pct: 70
  hard_stop_at_pct: 90
staging:
  path: data/staging
  max_gb: 20                  # cap for in-flight raw objects
  max_concurrent_units: 2
tier2:
  target_max_gb: null         # set after Part 1.1 (area) and Part 3.2 (scene count)
eviction:
  require_b2_verified: true
  require_derivative_validated: true
  ledger: data/manifests/eviction_ledger.jsonl
```

```yaml
# configs/b2.yaml   (NO secrets in this file)
endpoint_url: null            # S3-compatible endpoint, provided by user
bucket: null
prefixes:
  raw_sentinel2: null
  raw_other: null
  processed_backup: null
  manifests_backup: null
```

### 1A.6 Manifest state machine (one record per object / unit of work)

```
LISTED → PLANNED → FETCHING → FETCHED → VERIFIED → PROCESSED → ARCHIVED → EVICTED
                       └────────────► FAILED(reason, retries, last_error)
```
Record fields: `object_key`, `size_bytes`, `checksum` (whatever B2 exposes), `source`, `tile`, `sensing_date`, `epoch`, `processing_baseline`, `state`, `derivative_paths`, `timestamps`. Stored as JSON-lines under `data/manifests/` and backed up to B2 after every phase.

### 1A.7 Storage-budget worksheet (fill from real numbers, do not trust these estimates)

| Item | How to compute | Rough illustration* |
|---|---|---|
| Clipped pixels per band | (study area + buffer km²) × 10⁶ ÷ 100 m² | 1,500 km² → ~15 M pixels |
| One clipped scene stack (6 bands uint16 + SCL, compressed) | pixels × 7 layers × ~1–2 bytes | roughly 0.1–0.25 GB |
| Kept scenes | selected scenes per epoch × epochs | e.g. 10 × 4 = 40 scenes ≈ 4–10 GB |
| Composites + indices | epochs × (6 bands + 5 indices + count layer) | < 2 GB |
| Grid/features/labels/models/results | Parquet + pickles | typically < 2 GB |

\*Illustration only, assuming a 1,500 km² area. Recompute from the real boundary at Part 1.1 and record the result in `configs/storage.yaml → tier2.target_max_gb`.

### 1A.8 Backend abstraction (so tests never touch real data or the network)

`src/storage/backends.py` defines one interface (`list`, `stat`, `open_range`, `download`, `upload`, `exists`) with three implementations: `B2Backend` (S3-compatible), `LocalBackend`, and `FakeBackend` (in-memory/tmp-dir with byte and request counters). **All acquisition and preprocessing code depends only on the interface.** Tests use `FakeBackend`; nothing in `tests/` may require B2 credentials.

---

## Phase 0 — Project scaffolding & environment

**Objective:** a working, empty-but-correct skeleton the rest of the project builds into. Nothing analytical happens here.

**Directory structure created in this phase**
```
vizag-geoai/
├── PLAN.md, README.md, pyproject.toml, .gitignore
├── configs/paths.yaml
├── src/__init__.py, src/utils/{__init__.py, io.py, logging.py, validation.py}
└── tests/{unit,integration,fixtures}/__init__.py
```

**Implementation steps (one part = one approval cycle each)**
1. **Part 0.1** — Repo init: `pyproject.toml`/`requirements.txt` pinning Python + core libs (geopandas, rasterio, rioxarray, xarray, GDAL bindings, numpy, pandas, scikit-learn, xgboost, lightgbm, shap, osmnx, pysal, matplotlib, pytest), `.gitignore` (data/raw, models/, predictions/, logs/, .venv).
2. **Part 0.2** — `configs/paths.yaml` with every directory path from Section 1, plus `src/utils/io.py` with a single `load_config()` / `resolve_path()` pair everything else must use.
3. **Part 0.3** — `src/utils/logging.py` (structured run logging to `logs/<phase>_<timestamp>.log`) and `src/utils/validation.py` (shared assertions: CRS check, bounds check, nodata check, no-NaN check — reused by every later phase).
4. **Part 0.4** — **Lightning Studio environment & tooling.** Confirm workspace path and free disk (`pwd`, `df -h`); clone repo into the Studio's persistent workspace; install geospatial stack (rasterio/GDAL with **JP2 (OpenJPEG) support**, rioxarray, dask, geopandas, pyarrow, `rio-cogeo`), `rclone` and/or `boto3` for B2's S3-compatible API; load B2 credentials **from Studio secrets / environment variables only**; add `.env` and `data/` to `.gitignore`. Print (never log) whether credentials are present. Ask the user for the storage cap and B2 endpoint/bucket → write `configs/storage.yaml` and `configs/b2.yaml`.
5. **Part 0.5** — **Storage layer** (`src/storage/`): `backends.py` (B2/Local/Fake, Section 1A.8), `manifest.py` (state machine, JSON-lines, atomic writes), `guard.py` (`check_budget(projected_bytes)`), `evict.py` (`safe_evict()` with ledger). Built and fully tested **before any data is touched**.

**Edge cases & validations (Phase 0)**
| Edge case | Handling |
|---|---|
| `paths.yaml` missing a key a module needs | `resolve_path()` raises a clear `ConfigError`, not a `KeyError` |
| Two config keys point to the same physical path | Startup check warns (not fails) — could be intentional |
| Repo run from a different working directory | All paths resolved relative to repo root via a detected marker file, not `os.getcwd()` |

**Test cases (Phase 0)**
- `test_config_loads_and_resolves_all_declared_paths`
- `test_missing_config_key_raises_configerror`
- `test_logging_creates_timestamped_file_and_is_appendable`
- `test_no_hardcoded_paths` (static scan of `src/` for path-like string literals outside `configs/`)

**Edge cases & validations (Parts 0.4–0.5)**
| Edge case | Handling |
|---|---|
| GDAL build lacks the JP2 driver (Sentinel-2 bands are `.jp2`) | Environment check fails fast with the exact missing driver and install hint, before any data step |
| B2 credentials missing / wrong / read-only | Distinct, clear errors: `NoCredentials`, `AuthFailed`, `ReadOnlyKey`; nothing is retried blindly |
| Credentials accidentally present in a config file, log or notebook | Secret-scan test fails the build; logger redacts key patterns |
| Studio restarted mid-operation | Manifest + atomic writes guarantee the next run resumes; leftover `*.part` files are detected and cleaned |
| Two processes touch the manifest at once | File lock; second process waits or exits with a clear message |
| `safe_evict()` called on an object whose B2 copy is unverified or derivative invalid | Refuses, raises `EvictionRefused`, writes nothing |
| Budget config left as `null` | Any heavy operation refuses to run and tells the user which value to set |

**Test cases (Parts 0.4–0.5)**
- `test_env_check_detects_missing_jp2_driver`
- `test_missing_or_readonly_credentials_raise_distinct_errors`
- `test_secret_scan_finds_no_keys_in_repo_configs_or_logs`
- `test_logger_redacts_credential_patterns`
- `test_manifest_atomic_write_survives_simulated_crash`
- `test_manifest_file_lock_prevents_concurrent_corruption`
- `test_storage_guard_blocks_when_projected_size_exceeds_budget`
- `test_storage_guard_refuses_when_budget_is_null`
- `test_safe_evict_refuses_without_verified_b2_copy`
- `test_safe_evict_refuses_without_validated_derivative`
- `test_safe_evict_writes_ledger_entry_on_success`
- `test_fake_backend_counts_bytes_and_requests`
- `test_no_code_path_calls_backend_delete_on_b2` (static + spy test)

**Phase Gate:** `pytest tests/` passes; repo installs cleanly in a fresh Studio; user confirms (1) storage cap and B2 endpoint/bucket are set in config, (2) credentials are supplied via secrets (never files), (3) `df -h` output looks as expected. `PLAN.md` and `README.md` render correctly.

---

## Phase 1 — Study boundary & configuration

**Objective:** lock the GVMC study area, CRS, buffer, and temporal/grid/label parameters that every later phase depends on.

**Directory structure added**
```
data/boundaries/gvmc_boundary.geojson
data/boundaries/gvmc_boundary_buffered.geojson
configs/{boundary.yaml, temporal.yaml, grid.yaml, label.yaml}
src/acquisition/boundary.py
tests/unit/test_boundary.py
```

**Implementation steps**
1. **Part 1.1** — `boundary.yaml` (source of the GVMC boundary — user-supplied shapefile or official source URL, working CRS `EPSG:32644`, buffer distance) + `src/acquisition/boundary.py` to load, reproject, and buffer it, writing both files above.
2. **Part 1.2** — `temporal.yaml` (epochs: 2018, 2020, 2022, 2024/25; training pairs; temporal holdout pair; prediction target 2030) and `grid.yaml` (500 m cell size; documented rationale as a comment, not just a number) and `label.yaml` (threshold values to sensitivity-test: 5%, 10%, 20%; primary = 10%).

**Edge cases & validations (Phase 1)**
| Edge case | Handling |
|---|---|
| Boundary file has invalid/self-intersecting geometry | `shapely.make_valid` applied, logged, test asserts validity post-fix |
| Boundary CRS is geographic (WGS84) not projected | Auto-reprojected to `EPSG:32644`; raw CRS never silently assumed |
| Buffer distance = 0 or negative in config | Config validation rejects at load time with a clear message |
| Boundary area implausibly small/large (e.g. wrong file supplied) | Sanity-check against an expected area range (configurable), warns loudly |

**Test cases (Phase 1)**
- `test_boundary_loads_and_is_valid_geometry`
- `test_boundary_reprojected_to_target_crs`
- `test_buffered_boundary_area_greater_than_unbuffered`
- `test_invalid_buffer_distance_rejected_at_config_load`
- `test_boundary_area_within_sanity_bounds`

**Phase Gate:** user visually confirms the plotted boundary+buffer (a quick PNG saved to `results/phase1_boundary_check.png`) matches the intended GVMC area before Phase 2 starts.

---

## Phase 2 — B2 inventory, reconciliation & resumable acquisition of the remaining data

**Objective:** find out *exactly* what is already in B2, decide what (if anything) is still missing, and fetch **only** the missing part — resumably, within the storage budget, without ever deleting or overwriting existing data. **No satellite data that is already in B2 is downloaded again from Copernicus.**

**Directory structure added**
```
data/manifests/{b2_inventory.jsonl, requirements_diff.jsonl, missing.jsonl, acquisition_state.jsonl}
data/raw_small/{worldpop, osm, dem, worldcover}/...
configs/data_requirements.yaml
results/phase2/{inventory_report.md, missing_report.md}
src/acquisition/{inventory.py, product_id.py, reconcile.py, integrity.py, fetch_missing.py, sources/*.py}
tests/unit/test_acquisition_*.py
tests/fixtures/fake_bucket/            # tiny fake bucket tree incl. complete, incomplete, duplicate, junk entries
```

**Implementation steps (one approval per part)**
1. **Part 2.1 — Read-only B2 inventory.** List the bucket/prefixes (paginated, checkpointed), parse each key into structured metadata (source, tile, sensing date, processing level, baseline, format `.SAFE` vs `.zip`), write `b2_inventory.jsonl`. Produce `inventory_report.md`: totals by source / year / tile, total size vs the expected ~225 GB, duplicates, junk, suspicious sizes. **No downloads, no writes to B2.** Confirms assumptions A1–A5.
2. **Part 2.2 — Requirements spec & reconciliation.** Write `configs/data_requirements.yaml` (required Sentinel-2 tiles that intersect the buffered boundary, epochs and dry-season windows, WorldPop years, OSM, DEM, WorldCover). Diff against the inventory → `missing_report.md` with **estimated bytes per missing item and estimated B2 egress/requests**. User decides what is truly needed.
3. **Part 2.3 — Integrity audit of existing data (cheap first).** Check completeness per product (required band files + metadata present), size sanity, and any checksum B2 already exposes. Do **not** download 190 GB to hash it; deeper verification happens lazily at first read in Phase 3.
4. **Part 2.4 — Small datasets.** Fetch WorldPop, OSM, DEM, WorldCover (small) directly into `data/raw_small/`, verify, and copy to B2 (copy-only). Skip anything already present.
5. **Part 2.5 — Resume the remaining large items (if any).** Only items the user approved from `missing_report.md`. **Stream-through** flow per unit: source → `data/staging/` → upload to B2 → verify → `safe_evict()`. Default `--dry-run`; real run needs a separate "yes". Rate-limit aware and resumable from `acquisition_state.jsonl`.
6. **Part 2.6 — Backup manifests & resume drill.** Sync `data/manifests/` to B2; simulate a Studio restart and prove the state machine resumes with zero duplicate transfers.

**Edge cases & validations (Phase 2)**
| Edge case | Handling |
|---|---|
| Bucket contains junk / non-product files (`.DS_Store`, thumbnails, logs) | Classified `unknown`, reported, **never** marked for deletion |
| Same product present twice (zip + SAFE, re-upload, different processing baselines) | Duplicates detected by parsed product ID; recommend one (complete, highest baseline) but **delete nothing** |
| Incomplete SAFE (a required band or metadata file missing) | State `INCOMPLETE`; excluded from Phase 3 unless the user approves re-fetching that one product |
| Zero-byte or implausibly small band file | Flagged `SUSPECT_SIZE`; excluded until re-checked |
| Bucket has 100k+ objects | Paginated listing with checkpointing; never loads everything into memory |
| Key restricted to a prefix / read-only scope | Inventory still works; acquisition refuses with `ReadOnlyKey` and tells the user what scope is needed |
| Boundary intersects a second Sentinel-2 tile not in the bucket | Reconciliation flags the missing tile explicitly (a likely part of the remaining ~35 GB) |
| Object present in B2 under a different naming/prefix than expected | Matched by **parsed product ID**, not exact key, to avoid re-downloading what already exists |
| Provider product is offline / needs ordering (long-term archive) | Marked `OFFLINE`, retried on a schedule, never an infinite loop |
| Provider quota / rate limit hit | Back off, persist state, resume later; no partial file is ever marked complete |
| Interrupted transfer leaves `*.part` | Detected on resume and discarded; only verified files advance state |
| Studio disk would exceed budget while staging | Storage guard blocks **before** the transfer starts |
| Estimated egress/request cost is large | Shown in the plan for approval; nothing runs without "yes" |

**Test cases (Phase 2)** — all run against `FakeBackend`, never real B2
- `test_inventory_lists_all_objects_with_pagination`
- `test_inventory_classifies_unknown_files_and_never_marks_them_for_deletion`
- `test_product_id_parsing_from_safe_and_zip_names`
- `test_duplicate_products_detected_best_recommended_none_deleted`
- `test_incomplete_safe_detected_when_required_band_missing`
- `test_zero_byte_and_undersized_files_flagged`
- `test_reconciliation_flags_missing_tile_from_boundary_intersection`
- `test_matching_is_by_product_id_not_exact_key`
- `test_acquisition_dry_run_is_default_and_transfers_nothing`
- `test_acquisition_refuses_when_projected_staging_exceeds_cap`
- `test_acquisition_skips_items_already_in_b2`
- `test_acquisition_resumes_from_manifest_after_simulated_crash`
- `test_part_files_discarded_on_resume`
- `test_offline_product_not_retried_forever`
- `test_read_only_key_allows_inventory_but_blocks_acquisition`
- `test_no_delete_or_overwrite_calls_issued_to_backend_in_phase2` (spy asserts zero)
- `test_secrets_never_appear_in_logs_or_reports`

**Phase Gate:** user reads `inventory_report.md` and `missing_report.md`, confirms assumptions A1–A5, and approves the exact list of items (if any) to fetch. **Nothing has been deleted or overwritten anywhere.**

---

## Phase 3 — Advanced Sentinel-2 preprocessing under a storage budget

**Objective:** turn the (already-acquired) raw Sentinel-2 archive in B2 into per-epoch cloud-free composites and spectral indices **without ever materialising the full archive on the Studio**. Processing order stays: *triage → window-read only needed bands → mask → resample → offset-correct → clip → composite → indices*, but every step is designed around bytes read, bytes stored and resumability.

**Design decisions (recorded before coding)**
| # | Decision | Rationale |
|---|---|---|
| D1 | **Scene catalogue first**, from the Phase 2 inventory — no pixel reads | Know tiles, dates, baselines, formats per epoch before touching data |
| D2 | **SCL-first triage**: compute study-area cloud fraction from the small 20 m SCL layer, select the best *K* scenes per epoch window, and only then read 10 m bands | Avoids reading bands for scenes that would be discarded |
| D3 | **Band subset + spatial window**: B02, B03, B04, B08 (10 m), B11, B12 (20 m), SCL (20 m); window = buffered-boundary bbox in the tile's CRS | Cuts bytes read/stored by a large factor |
| D4 | **Read strategy chosen by measurement** (Part 3.0): (a) fetch needed files to staging then read, vs (b) GDAL `/vsis3/` windowed reads straight from B2 | Depends on whether data is stored as `.SAFE` folders or `.zip`, and on B2 request pricing; decision saved as `docs/decisions/ADR-001-read-strategy.md` |
| D5 | **Radiometric consistency across epochs**: apply the `BOA_ADD_OFFSET` / quantification value from each product's metadata (processing baseline ≥ 04.00 changed the L2A offset) | Otherwise a 2018 vs 2024 NDBI difference partly reflects a processing change, not the city |
| D6 | **Outputs are COG** (deflate/zstd + predictor); scene stacks stored as DN `uint16` + mask, composites/indices as compressed `float32`/scaled `int16` | Small, cloud-optimised, resumable |
| D7 | **No intermediates on disk** beyond the clipped scene stack and the final composite | Prevents silent disk bloat |
| D8 | **Median composite computed in chunks (dask)** with bounded memory | Avoids RAM/disk blow-ups |
| D9 | **Unit of work = one scene → one clipped stack**, tracked in the manifest | Crash-safe, parallel-safe, evictable |
| D10 | **Epoch feasibility check**: confirm each planned epoch (2018, 2020, 2022, 2024/25) has usable **L2A** coverage of the study area; if an epoch only has L1C or too few clear scenes, **stop and ask the user** (options: run atmospheric correction on L1C — disk-heavy, use TOA with a documented limitation, or shift the epoch) | Global L2A availability for older dates may be incomplete; this can invalidate the temporal design if ignored |

**Directory structure added**
```
data/processed/sentinel2/
├── scene_stacks/<epoch>/<scene_id>.tif        # clipped 6-band + SCL/mask COG
├── composites/<epoch>/composite.tif           # dry-season median COG
├── composites/<epoch>/valid_obs_count.tif
└── indices/<epoch>/{ndvi,ndbi,ndwi,mndwi,bsi}.tif
data/manifests/{scene_catalogue.jsonl, selected_scenes.jsonl, processing_state.jsonl}
docs/decisions/ADR-001-read-strategy.md
results/phase3/{read_benchmark.md, epoch_feasibility.md, cloud_triage.csv, storage_report.md, qc_<epoch>.png}
src/preprocessing/{catalogue.py, triage.py, extract_scene.py, scl_mask.py, radiometry.py, composite.py, indices.py, archive.py}
tests/unit/test_preprocessing_*.py, tests/integration/test_scene_to_composite.py
tests/fixtures/{tiny_scene_safe/, tiny_scene_zip/, fake_mtd_baseline_0206.xml, fake_mtd_baseline_0511.xml}
```

**Implementation steps (one approval per part)**
0. **Part 3.0 — Read-strategy benchmark.** On 1–2 real scenes, measure for strategies (a) and (b): wall time, bytes transferred, **request count**, peak staging disk. Write `read_benchmark.md` + ADR-001. **User approves the strategy before anything else runs.**
1. **Part 3.1 — Scene catalogue & epoch feasibility.** Parse the Phase 2 inventory into `scene_catalogue.jsonl` (tile, date, baseline, level, format, completeness). Report per epoch: scene count, tiles, date spread, L2A vs L1C, processing baselines, boundary coverage. **User confirms/adjusts the epoch set** (may update `temporal.yaml`).
2. **Part 3.2 — SCL triage.** Read only SCL (windowed) for candidate scenes; compute cloud/shadow/nodata fraction over the buffered boundary; select best *K* per epoch (config), dedupe same-day/duplicate products → `selected_scenes.jsonl` + `cloud_triage.csv`. **User reviews selection.**
3. **Part 3.3 — Per-scene extraction worker.** For each selected scene (concurrency ≤ `max_concurrent_units`): storage-guard check → fetch/window-read needed bands only (per ADR-001) → resample (SCL nearest, B11/B12 bilinear, to 10 m) → apply metadata offset → clip to boundary bbox → write clipped stack COG → validate → update manifest → evict staging. Idempotent and resumable.
4. **Part 3.4 — Mask construction.** From SCL: configurable valid classes (default valid: 4 vegetation, 5 not-vegetated, 6 water, 7 unclassified; invalid: 0, 1, 3, 8, 9, 10; class 2 "dark/topographic shadow" configurable), plus configurable dilation of cloud/shadow to catch fringes. Record the choices in config and in the QC report (dark roofs and bright roofs can be misclassified by SCL — a known limitation to state in the thesis).
5. **Part 3.5 — Dry-season median composites** per epoch from validated stacks, plus a `valid_obs_count` raster; halt and report if an epoch falls below the minimum-valid-pixel threshold.
6. **Part 3.6 — Spectral indices** (NDVI, NDBI, NDWI, MNDWI, BSI) per epoch with guarded division and range checks.
7. **Part 3.7 — Archive & evict.** Sync `data/processed/` + manifests to B2 (copy-only, Tier 3), verify, then (per config) `safe_evict()` scene stacks that are no longer needed. Produce `storage_report.md`: Tier 1 empty, Tier 2 size vs budget.

**Edge cases & validations (Phase 3)**
| Edge case | Handling |
|---|---|
| Epoch has only L1C, or too few clear L2A scenes | Halt at Part 3.1 and ask the user (design decision D10); never silently mix L1C and L2A |
| Mixed processing baselines across epochs (offset changed) | Offset read from each product's metadata and applied; a test proves reflectance scales agree on synthetic data |
| Same acquisition present as multiple baselines / duplicates | Deduplicate; prefer the latest complete baseline; log the choice |
| Scene only partly covers the study window (orbit-edge nodata stripe) | Nodata stays nodata (never 0 reflectance); triage counts it as unusable area |
| Study window spans two tiles / overlap | Mosaic **after** masking; overlapping valid pixels resolved deterministically |
| A required band file missing or the JP2 is corrupt | Unit marked `FAILED(reason)`, batch continues, scene excluded, reported at the end |
| SCL marks bright built-up roofs as cloud / dark roofs as shadow | Mask thresholds are config; QC report shows how much urban area is masked; documented as a limitation |
| Epoch composite below minimum valid-pixel % | Halt + report; do not emit a low-quality composite silently |
| Division by zero in an index (e.g. NIR+Red = 0) | Guarded → nodata, not NaN propagating downstream |
| Reflectance outside physical range after resampling | Clipped with logged pixel count |
| Staging fills up during a batch | Storage guard blocks the next unit; no unit starts if projected staging > cap |
| B2 throttling / timeouts | Retry with exponential backoff; persist state; resume |
| Studio restarts mid-scene | Partial outputs discarded; unit restarts from manifest state; no duplicate/partial files |
| Median composite exceeds RAM | Chunked computation (dask) with a tested memory bound |
| S2A and S2B acquisitions on adjacent days | Both allowed as distinct observations; same-day duplicates deduped |
| `safe_evict()` requested before B2 copy/derivative validated | Refused (from Phase 0.5) |

**Test cases (Phase 3)** — run on tiny synthetic fixtures via `FakeBackend`
- `test_catalogue_parses_tile_date_baseline_level_format`
- `test_epoch_feasibility_flags_l1c_only_epoch_and_halts`
- `test_scl_triage_selects_lowest_cloud_scenes_per_epoch`
- `test_triage_reads_only_scl_not_10m_bands` (byte counter on fake backend)
- `test_only_required_band_files_are_fetched`
- `test_boa_offset_applied_for_baseline_ge_0400_not_before`
- `test_mixed_baseline_epochs_produce_consistent_reflectance_scale`
- `test_windowed_read_equals_full_read_then_clip_on_fixture`
- `test_scl_resampled_nearest_and_swir_bilinear`
- `test_partial_coverage_scene_nodata_not_treated_as_zero_reflectance`
- `test_duplicate_same_day_scenes_deduped_prefer_latest_baseline`
- `test_corrupt_jp2_marks_unit_failed_and_batch_continues`
- `test_missing_band_file_marks_unit_failed_not_crash`
- `test_staging_never_exceeds_cap_during_batch` (instrumented)
- `test_unit_of_work_is_idempotent_on_rerun`
- `test_resume_after_kill_mid_scene_leaves_no_partial_outputs`
- `test_mask_class_config_changes_valid_pixel_set`
- `test_cloud_shadow_dilation_expands_mask_by_configured_pixels`
- `test_composite_median_correct_on_known_synthetic_stack`
- `test_composite_chunked_memory_bounded`
- `test_valid_obs_count_raster_written_and_correct`
- `test_all_cloud_epoch_halts_and_reports`
- `test_index_divide_by_zero_guarded_and_range_plausible`
- `test_outputs_are_valid_cog` (`rio cogeo validate`)
- `test_raw_evicted_only_after_derivative_valid_and_b2_verified`
- `test_tier2_size_report_within_budget_and_tier1_empty_after_run`
- `test_full_scene_to_composite_pipeline_on_fixture_end_to_end` (integration)

**Phase Gate:** user reviews, per epoch, the RGB composite + `valid_obs_count` map + index sample (`results/phase3/qc_<epoch>.png`), `epoch_feasibility.md`, and `storage_report.md` (Tier 1 empty, Tier 2 within budget, backup verified in B2) before grid construction starts.

---

## Phase 4 — Grid construction & feature aggregation

**Objective:** build the 500 m analysis grid and aggregate every data source onto it, per epoch. **Inputs come only from Tier-2 processed products (Section 1A) — never directly from staging or from B2.** If a needed product is missing from Tier 2, restore it from the Tier-3 backup instead of reprocessing raw data.

**Directory structure added**
```
data/derived/grid/analysis_grid.geojson
data/derived/features/<epoch>/feature_table.parquet
src/grid/{build_grid.py, aggregate_satellite.py, aggregate_population.py, aggregate_osm.py, aggregate_terrain.py}
tests/unit/test_grid_*.py
```

**Implementation steps**
1. **Part 4.1** — Grid construction over the buffered boundary at the configured cell size, each cell with a stable unique ID.
2. **Part 4.2** — Satellite index aggregation (zonal mean per cell per epoch) + terrain aggregation (elevation, slope — computed once, static).
3. **Part 4.3** — Population aggregation (density + growth-rate-from-past-intervals-only) + OSM aggregation (distance-to-road, road density, distance-to-hospital, distance-to-school).
4. **Part 4.4** — Assemble the per-epoch feature table (join all sources on grid ID), with a leakage-safe rule: population growth rate as a feature must only use *already-elapsed* intervals, enforced by an assertion, not just convention.

**Edge cases & validations (Phase 4)**
| Edge case | Handling |
|---|---|
| A grid cell falls entirely outside actual imagery coverage (edge of buffer) | Flagged nodata, excluded from modeling but retained in the grid for map completeness |
| A grid cell overlaps a water body / protected area | Tagged `undevelopable` per the label design rules, carried through as a feature flag, not silently dropped |
| Zonal aggregation over a cell with zero valid source pixels | Result is NaN, explicitly, never coerced to 0 (0 would falsely mean "confirmed empty") |
| OSM distance calculation for a cell with no road within a large search radius | Distance capped at a configurable max with a flag column `beyond_max_distance`, not left unbounded |
| Duplicate or overlapping grid cells from a bug in construction | Uniqueness of grid ID and non-overlap asserted immediately after construction |
| Feature table join produces row-count mismatch across sources | Hard assertion failure — never a silent left-join that drops or duplicates rows |

**Test cases (Phase 4)**
- `test_grid_cells_are_unique_and_non_overlapping`
- `test_grid_covers_full_buffered_boundary`
- `test_zonal_aggregation_returns_nan_not_zero_for_empty_cells`
- `test_population_growth_feature_only_uses_past_intervals` (constructs a synthetic case and asserts a future-interval value is never used)
- `test_osm_distance_capped_and_flagged_beyond_max`
- `test_feature_table_row_count_matches_grid_cell_count_exactly`
- `test_undevelopable_cells_flagged_not_dropped`

**Phase Gate:** user reviews the assembled feature table's summary statistics (`results/phase4_feature_summary.csv` + a null-rate report) before labels are generated.

---

## Phase 5 — Label generation

**Objective:** produce the leakage-safe binary growth label per cell per transition period, with threshold sensitivity testing.

**Directory structure added**
```
data/derived/labels/<transition_period>/labels.parquet
results/phase5_threshold_sensitivity.csv
src/labels/{built_up_classification.py, growth_label.py, threshold_sensitivity.py}
tests/unit/test_labels_*.py
```

**Implementation steps**
1. **Part 5.1** — Per-epoch built-up classification from Sentinel-2 indices (not raw NDBI — a thresholded/classified decision), cross-checked against ESA WorldCover for the two overlapping years only.
2. **Part 5.2** — Binary growth label: `ΔBuiltFraction ≥ τ` between t1→t2, with exclusion masks (already-built, water, undevelopable) applied before label assignment.
3. **Part 5.3** — Threshold sensitivity run at τ = 5%, 10%, 20%; produces the comparison table and recommends τ = 10% as primary, exactly as specified in the project design.

**Edge cases & validations (Phase 5)**
| Edge case | Handling |
|---|---|
| A cell is already > 90% built-up at t1 | Excluded from the positive-label candidate pool (can't "grow" further), documented count reported |
| Built-up classification disagrees with WorldCover by a large margin for a cell | Logged as a label-uncertainty case, not silently trusted either direction |
| ΔBuiltFraction is negative (apparent shrinkage — classification noise) | Retained as label 0, not treated as an error, but flagged for the uncertainty report |
| A transition period has an extreme class imbalance (e.g. <1% positive) | Detected and reported before training, not discovered as a surprise in Phase 7 |
| Threshold sensitivity run changes which cells are positive by a large margin between τ values | Explicitly surfaced in the sensitivity report — this is the signal the design doc says to look for |

**Test cases (Phase 5)**
- `test_already_built_cells_excluded_from_positive_pool`
- `test_label_uses_only_t1_and_t2_built_fraction_never_intermediate_epoch`
- `test_negative_delta_built_fraction_labeled_zero_not_error`
- `test_class_imbalance_report_generated_for_every_transition_period`
- `test_threshold_sensitivity_produces_all_three_configured_values`
- `test_worldcover_crosscheck_flags_large_disagreements`

**Phase Gate:** user reviews `results/phase5_threshold_sensitivity.csv` and explicitly confirms τ = 10% (or a different value) as primary before dataset assembly.

---

## Phase 6 — Dataset assembly & train/validation/test split

**Objective:** assemble final modeling datasets per experiment (E1–E4) and split them correctly — temporal holdout plus spatial-block cross-validation.

**Directory structure added**
```
data/derived/datasets/{E1_satellite_only, E2_plus_population, E3_plus_roads, E4_full}/...
src/splitting/{temporal_split.py, spatial_block_cv.py}
src/features/leakage_check.py
tests/unit/test_splitting_*.py, tests/unit/test_leakage_check.py
```

**Implementation steps**
1. **Part 6.1** — Automated leakage check module: for every feature in every dataset, assert its source epoch is ≤ the label's t1 (never t2 or later). This runs as a gate, not just a test.
2. **Part 6.2** — Temporal holdout split (train on 2018→2020 and 2020→2022 transitions, test on 2022→2024).
3. **Part 6.3** — Spatial-block cross-validation setup (super-grid partitioning of the 500 m cells into contiguous blocks for CV folds).
4. **Part 6.4** — Assemble the four experiment-specific feature sets (E1 satellite-only … E4 full multimodal) from the Phase 4 feature table.

**Edge cases & validations (Phase 6)**
| Edge case | Handling |
|---|---|
| A feature accidentally sourced from a later epoch than its label | Leakage check fails the build immediately, names the offending column |
| Spatial blocks end up highly imbalanced in size/class ratio | Block size auto-adjusted within a configured range; imbalance reported, not silently accepted |
| A cell falls on a spatial-block boundary ambiguously | Deterministic assignment rule (e.g. centroid-based), tested for stability across re-runs |
| Temporal holdout set turns out too small to be statistically meaningful | Minimum-size check with an explicit warning surfaced to the user |
| E1–E4 datasets end up with different row counts due to missing features in some cells | Explicitly documented per-experiment row count; not silently reconciled by dropping rows across all experiments |

**Test cases (Phase 6)**
- `test_leakage_check_fails_build_when_feature_epoch_after_label_t1`
- `test_temporal_split_no_row_appears_in_both_train_and_test`
- `test_spatial_block_assignment_is_deterministic_across_reruns`
- `test_spatial_block_size_within_configured_bounds`
- `test_minimum_holdout_size_warning_triggers_below_threshold`
- `test_each_experiment_dataset_has_documented_row_count`

**Phase Gate:** user confirms the leakage-check report is clean (zero violations) and the split sizes look reasonable before any model training begins. **This gate cannot be skipped or soft-approved** — leakage is the single most likely way this project fails a viva.

---

## Phase 7 — Baseline model (E1, Logistic Regression)

**Objective:** the simplest working model, satellite-only, to sanity-check the whole pipeline end-to-end before adding complexity.

**Directory structure added**
```
models/E1_logistic_regression/model.pkl
results/E1_metrics.json
src/models/{base_trainer.py, logistic_baseline.py}
tests/unit/test_baseline_model.py
```

**Implementation steps**
1. **Part 7.1** — `base_trainer.py`: shared training/evaluation scaffolding (metrics computation, model saving, results logging) that every later model reuses — build this once, correctly, here.
2. **Part 7.2** — Logistic regression training on E1, evaluated on both the temporal holdout and spatial-block CV, reporting PR-AUC, F1, ROC-AUC, Cohen's kappa, Brier score.

**Edge cases & validations (Phase 7)**
| Edge case | Handling |
|---|---|
| Feature scaling not applied before logistic regression | Enforced by the trainer (fails fast if an unscaled feature set is passed) |
| Severe class imbalance causes the model to predict only the majority class | Detected via a trivial-classifier check (compare against always-predict-majority baseline) before reporting results as meaningful |
| NaNs remain in the feature matrix at training time | Training refuses to start; NaNs must be resolved upstream (Phase 4/5), never silently imputed inside the trainer without it being an explicit, logged decision |
| Metric computation on an empty test fold | Raises, rather than returning a misleading `0.0` |

**Test cases (Phase 7)**
- `test_trainer_rejects_unscaled_features`
- `test_trainer_rejects_nan_containing_matrix`
- `test_baseline_beats_trivial_majority_classifier` (regression test — if this ever fails, something upstream broke)
- `test_metrics_all_five_reported_and_in_valid_ranges`
- `test_empty_fold_raises_not_silently_returns_zero`

**Phase Gate:** user reviews `results/E1_metrics.json` and confirms the baseline is "sane" (better than trivial, no NaNs, no crashes) before multimodal experiments begin.

---

## Phase 8 — Multimodal models & ablation (E2–E4)

**Objective:** Random Forest / XGBoost / LightGBM trained on E2, E3, E4; the ablation comparison that is a core contribution of the project.

**Directory structure added**
```
models/{E2_plus_population, E3_plus_roads, E4_full}/<model_name>/model.pkl
results/ablation_comparison.csv
src/models/{tree_ensembles.py, ablation_runner.py}
tests/unit/test_tree_ensembles.py, tests/integration/test_ablation_pipeline.py
```

**Implementation steps**
1. **Part 8.1** — Random Forest + XGBoost + LightGBM training scaffolding on top of `base_trainer.py`, with hyperparameters from `configs/model.yaml`.
2. **Part 8.2** — Run all three models on E2, E3, E4 (9 runs total), each with temporal + spatial-block evaluation.
3. **Part 8.3** — Ablation comparison report: metric deltas between E1→E2→E3→E4 with bootstrap confidence intervals (per the design doc — not bare point estimates).

**Edge cases & validations (Phase 8)**
| Edge case | Handling |
|---|---|
| A later experiment (e.g. E4) performs *worse* than an earlier one (e.g. E3) | Reported as-is, not "corrected" — this is a legitimate, reportable finding |
| Bootstrap CI computation with too few samples in a fold | Minimum sample-size guard, warns rather than producing an unstable CI silently |
| Hyperparameter config missing a required key for one of the three models | Fails at config-load time, not mid-training |
| Training run interrupted partway (e.g. 6 of 9 runs done) | Resumable — already-completed runs are not silently re-run and overwritten unless `--force` |
| Two models produce identical metrics (possible bug: same data accidentally passed twice) | Sanity check flags suspiciously identical results across different experiments |

**Test cases (Phase 8)**
- `test_all_nine_model_experiment_combinations_run_without_error`
- `test_ablation_report_includes_bootstrap_ci_not_just_point_estimate`
- `test_worse_performing_experiment_reported_not_suppressed`
- `test_training_resumable_after_interruption`
- `test_suspiciously_identical_results_across_experiments_flagged`
- `test_missing_hyperparameter_key_fails_at_config_load`

**Phase Gate:** user reviews `results/ablation_comparison.csv` and picks (or confirms Claude's recommendation of) the best model to carry forward into explainability and prediction.

---

## Phase 9 — Explainability (SHAP)

**Objective:** TreeSHAP global, local, and spatial explanations for the selected best model.

**Directory structure added**
```
results/shap/{global_importance.png, local_examples/, spatial_shap_maps/}
src/explainability/{compute_shap.py, spatial_shap_map.py}
tests/unit/test_explainability.py
```

**Implementation steps**
1. **Part 9.1** — Global SHAP importance + summary/beeswarm plot for the selected model.
2. **Part 9.2** — Local explanations for a small set of illustrative cells (e.g. the walkthrough examples used in the presentation).
3. **Part 9.3** — Spatial SHAP maps: one map per key feature, showing where it pushes predictions up/down across the study area.

**Edge cases & validations (Phase 9)**
| Edge case | Handling |
|---|---|
| SHAP values computed on a non-tree model by mistake | Trainer refuses — TreeSHAP requires a tree-based model, checked at call time |
| SHAP values for a feature all sum near zero (feature contributes almost nothing) | Reported, not dropped from the plot — absence of importance is itself informative |
| Spatial SHAP map has cells with missing feature values | Rendered as an explicit "no data" color, never interpolated silently |
| SHAP computation is slow on the full grid | Documented runtime; a `--sample` flag for fast local iteration during development, full run for the final report |

**Test cases (Phase 9)**
- `test_shap_rejects_non_tree_model`
- `test_shap_values_sum_consistent_with_model_output` (SHAP's additivity property, a strong correctness check)
- `test_spatial_shap_map_renders_nodata_explicitly_not_interpolated`
- `test_local_explanation_generated_for_each_walkthrough_cell`

**Phase Gate:** user reviews the SHAP global-importance plot and at least one spatial SHAP map, and confirms the "top drivers" make domain sense (e.g. distance-to-road, population growth) before moving to final prediction.

---

## Phase 10 — 2030 prediction & Infrastructure Pressure Index

**Objective:** apply the best model to 2024/25 features to predict 2030 growth probability, then combine with accessibility data into the pressure index.

**Directory structure added**
```
predictions/2030_growth_probability.tif
predictions/infrastructure_pressure_equal_weighted.tif
predictions/infrastructure_pressure_entropy_weighted.tif
src/prediction/predict_2030.py
src/infra_pressure/{accessibility_gap.py, pressure_index.py}
tests/unit/test_prediction.py, tests/unit/test_infra_pressure.py
```

**Implementation steps**
1. **Part 10.1** — 2030 prediction using 2024/25-epoch features, with the extrapolation-horizon caveat attached as raster metadata, not just prose.
2. **Part 10.2** — Accessibility-gap composite (road/hospital/school distance + current built-up density).
3. **Part 10.3** — Infrastructure Pressure Index — equal-weighted primary, entropy-weighted robustness check, both computed and compared.

**Edge cases & validations (Phase 10)**
| Edge case | Handling |
|---|---|
| A cell has a valid growth probability but missing accessibility data | Excluded from the pressure index with an explicit nodata flag, not defaulted to a neutral value |
| Equal- and entropy-weighted rankings diverge sharply for some cells | Explicitly surfaced in a comparison report — this is a designed finding, not an error |
| Extrapolation horizon (2025→2030) flagged nowhere in the output | Build-time check that the output raster's metadata contains the horizon caveat, fails if absent |
| Pressure index score out of expected [0,1] (or configured) range | Range-checked before saving |

**Test cases (Phase 10)**
- `test_prediction_raster_metadata_contains_extrapolation_caveat`
- `test_missing_accessibility_data_excluded_not_defaulted`
- `test_pressure_index_within_expected_range`
- `test_equal_vs_entropy_weighting_divergence_report_generated`

**Phase Gate:** user reviews the final growth-probability map and both pressure-index maps side by side before the final report is compiled.

---

## Phase 11 — Final report, reproducibility & documentation

**Objective:** everything needed for someone else (or future-you) to re-run this end to end, plus the write-up.

**Directory structure added**
```
results/final_report.md
results/figures/
README.md   (rewritten to be the short, polished, human-facing summary)
```

**Implementation steps**
1. **Part 11.1** — End-to-end reproducibility check: a single `make all` / `run_pipeline.sh` that re-runs every phase from a **brand-new Studio** using only (a) the git repo, (b) B2 credentials, and (c) the B2 raw archive + Tier-3 backup, and produces identical (or documented-as-stochastic) results. Includes a **"rebuild Tier 2 from B2 backup"** drill that proves the Studio can be deleted and recreated without re-processing raw data or re-downloading from Copernicus.
2. **Part 11.2** — Final report assembly: pulls metrics, figures, and SHAP plots already generated into `results/final_report.md`.
3. **Part 11.3** — Polished top-level `README.md` for the repository (distinct from this `PLAN.md`).

**Edge cases & validations (Phase 11)**
| Edge case | Handling |
|---|---|
| A re-run produces different results due to unseeded randomness | All random seeds fixed and documented; any remaining nondeterminism explicitly called out |
| A phase's output is missing when the report assembler runs | Report assembly fails loudly, naming the missing artifact, rather than producing a report with silent gaps |

**Test cases (Phase 11)**
- `test_full_pipeline_reruns_with_fixed_seeds_reproduces_metrics_within_tolerance`
- `test_report_assembly_fails_loudly_on_missing_artifact`

**Phase Gate:** user does a final read-through of `results/final_report.md` and the repo `README.md` — project complete.

---

## Appendix A — Standing instructions for Claude Code (paste-ready)

> Follow `PLAN.md` exactly. Storage is a first-class constraint: the Studio holds only Tier 1 (capped staging) and Tier 2 (processed products); raw data lives in B2 and is never re-downloaded from the original provider if it already exists there; nothing is ever deleted from B2; local raw files are removed only via `safe_evict()`; every transfer or eviction is dry-run first and needs explicit user approval. Work one part at a time, per the loop in Section 0. Never implement more than the single approved part. Always run and report test results before asking to proceed. If you discover a problem with the plan itself (e.g. a phase's edge case list is incomplete), stop and flag it to the user rather than silently improvising a fix — propose the plan change, wait for approval, then continue.

## Appendix B — Quick reference: what "done" means for a part

A part is only reportable as complete when **all** of the following are true:
- [ ] Code implements exactly the approved part, nothing more
- [ ] All edge cases listed for that part are handled (not just the happy path)
- [ ] All test cases listed for that part exist and pass
- [ ] The full existing test suite (regression) still passes
- [ ] No hardcoded paths, no silent NaN/None coercion, no bare `except:`
- [ ] A one-paragraph plain-language summary is ready to give the user
