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
`cleanup_stale_part_files()` for crash recovery. `pending(terminal_states=...)` (added Phase 2 Part 2.6)
returns the resumable worklist — any future resumable fetch should build its work loop from this, not
re-derive its own "what's left to do" logic.

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
| `configs/b2.yaml` | B2 endpoint, bucket, prefixes (no secrets) | **Created (Part 0.4), prefixes filled in (Part 2.1, 2026-10-10)** — endpoint, bucket, `raw_sentinel2`/`raw_other` all confirmed from the real inventory; `processed_backup`/`manifests_backup` deliberately still `null`, pending a Phase 3 Part 3.0 design decision |
| `configs/boundary.yaml` | Study area source, CRS (`EPSG:32644`), buffer distance | Not created (Part 1.1) |
| `configs/temporal.yaml` | Epochs, transition pairs, holdout split | **Created (Part 1.2)** — epochs `[2018,2020,2022,2024]` confirmed against the real B2 inventory, not assumed |
| `configs/grid.yaml` | Grid cell size (500 m), exclusions | **Created (Part 1.2)** |
| `configs/label.yaml` | Growth threshold values (5/10/20%, primary 10%) | **Created (Part 1.2)** |
| `configs/model.yaml` | Model hyperparameters per experiment | Not created (Phase 8) |
| `configs/data_requirements.yaml` | What data each epoch/source needs | **Created (Part 2.2)** — auto-generated from the real buffered boundary + `temporal.yaml`; only `T44QQE` is the strictly-required Sentinel-2 tile |

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
| Required Sentinel-2 tiles computed from the real MGRS grid, not inferred from B2 | Phase 2, Part 2.2 | 2026-10-10 | `compute_required_tiles()` point-samples the buffered boundary and converts to MGRS via the `mgrs` library — same principle as the boundary rule: don't assume data already in B2 is correct/sufficient, verify independently. Result: only `T44QQE` is strictly required at the current 5km buffer; `T44QPE`/`T44QQF` in B2 are extra. If `configs/boundary.yaml`'s `buffer_distance_m` is ever increased, rerun Part 2.2 — the required-tiles set could grow. |
| Zip integrity checked via range-read central-directory parsing, not download | Phase 2, Part 2.3 | 2026-10-10 | `check_zip_band_completeness()` wraps a backend's `open_range()` in a minimal seekable file-like object (`_RangeReadFile`) so Python's `zipfile` can locate and parse just the end-of-central-directory + central directory — listing every internal filename without fetching any band content. Proven in a test to transfer well under half the archive size. This is the same "triage before heavy reads" principle Phase 3's SCL-first design uses, applied one phase earlier. Reusable pattern — Phase 3 can lean on the same `_RangeReadFile` approach for windowed JP2 reads. |
| B2's ETag recorded, not verified | Phase 2, Part 2.3 | 2026-10-10 | `ObjectInfo.etag` is populated from B2's `head_object` response. Multipart-uploaded objects (most of our raw archives, given their size) have an ETag of the form `<hash>-<part_count>`, which is **not** a plain content MD5 — there's no independent second copy to compare against anyway at this stage. It's stored purely as a future drift-detection fingerprint (if a later read sees a different ETag for the same key, something changed), not as proof of current correctness. |
| Small-dataset B2 prefix mirrors the existing WorldPop convention, not `plan.md`'s literal local dir name | Phase 2, Part 2.4 | 2026-10-10 | `fetch_missing.DEFAULT_B2_RAW_PREFIX = "vizag-geoai/data/raw/"` — the local directory is `data/raw_small/<source>/` (per `plan.md`'s Section 1 layout), but on B2 it's uploaded under `data/raw/<source>/` to match where WorldPop already lives in the bucket (found by Part 2.1's inventory), rather than introducing a parallel `raw_small`-named B2 prefix that would fragment the structure. |
| DEM/WorldCover sources chosen for no-auth public access | Phase 2, Part 2.4 | 2026-10-10 | `plan.md` doesn't pin exact DEM/WorldCover providers. Chose Copernicus GLO-30 (`s3://copernicus-dem-30m`) and ESA WorldCover 10m 2021 (`s3://esa-worldcover`) — both public AWS Open Data buckets needing no credentials, avoiding a new auth dependency on the user (vs. e.g. OpenTopography's API-key-gated SRTM access). OSM fetched live via Overpass/osmnx scoped to the AOI, not a regional extract — keeps it genuinely small (it still came out to 30.5 MB of roads, more than the rough pre-fetch guess, because the AOI is dense urban area — logged honestly in the changelog rather than quietly revising the earlier estimate). |
| Part 2.5's large-item acquisition flow not built speculatively | Phase 2, Part 2.5 | 2026-10-10 | `plan.md`'s Part 2.5 describes a full stream-through flow (staging → upload → verify → `safe_evict()`) for missing large items, but Part 2.2/2.5's reconciliation found zero missing Sentinel-2 items for the required tile. Building that flow now, with nothing real to validate it against, risks writing something wrong that looks tested. `check_remaining_large_items()` just re-confirms (fresh) there's nothing to do; the real flow gets built if/when an actual gap appears. |
| `manifests_backup` prefix set now; `processed_backup` still deferred | Phase 2, Part 2.6 | 2026-10-10 | Originally both were deferred to Phase 3 Part 3.0 (see the Part 0.4 decision above), but Part 2.6 explicitly needs `manifests_backup` now to do its job. Set it to `vizag-geoai/data/manifests/` — a prefix that didn't previously exist in the bucket, so no legacy-naming conflict (unlike `processed/`, which already holds prior-run outputs). `processed_backup` remains `null` until Phase 3 actually produces something to back up. |
| Resumability proven by test, not just by design | Phase 2, Part 2.6 | 2026-10-10 | `Manifest.pending()` plus `test_pending_simulates_a_resume_with_zero_duplicate_work` (Part 0.5's `Manifest` class, extended here) is the actual mechanism any future resumable fetch (Part 2.5's large-item flow, Phase 3's scene processing) should use to build its worklist — call `.pending()` after a restart and only that list needs reprocessing, never the already-terminal records. |
| Read strategy: direct remote windowed reads (`/vsizip/vsis3/`), not fetch-to-staging | Phase 3, Part 3.0 | 2026-10-10 | Benchmarked on 2 real scenes: strategy (b) transfers ~1.5% of the bytes strategy (a) does for the same windowed output, is 2.8x faster, and uses zero staging disk — see `docs/decisions/ADR-001-read-strategy.md` and `results/phase3/read_benchmark.md`. GDAL needs plain `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_S3_ENDPOINT` env vars for `/vsis3/` against a non-AWS S3-compatible endpoint (B2) — rasterio's `Env()` context manager explicitly blocks setting these directly ("AWS credentials are handled exclusively by boto3"), so `vsis3_credentials()` sets/restores plain `os.environ` instead. **Status: Accepted** — user approved 2026-10-10 ("yes, use this approach"). This is now the locked-in read approach for the rest of Phase 3. |
| `RangeReadFile` promoted to a shared utility | Phase 3, Part 3.0 | 2026-10-10 | Was a private class duplicated inside Part 2.3's `integrity.py`; Part 3.0 needed the identical capability (read a remote object's bytes lazily via `open_range()`) to list a zip's contents before resolving each band's inner path. Moved to `src/storage/backends.py` as public `RangeReadFile`; `integrity.py` now imports it. Any future code needing lazy range-based reads of a remote object should reuse this rather than re-implementing it. |
