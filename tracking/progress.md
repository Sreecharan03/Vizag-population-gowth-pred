# Phase-by-Phase Progress

**Read after [`tracking.md`](tracking.md).** This is the live status table against the 12 phases defined in
[`../plan.md`](../plan.md). Update the Status / Parts-done / Gate columns as work happens — this table is
the fastest way for a new session to see exactly where things stand.

Statuses: `Not started` / `In progress` / `Blocked` / `Gate pending` / `Complete`.

| Phase | Title | Status | Parts done | Phase Gate confirmed? |
|---|---|---|---|---|
| 0 | Project scaffolding & environment | Gate pending | 5/5 | No |
| 1 | Study boundary & configuration | Not started | 0/2 | No |
| 2 | B2 inventory, reconciliation & acquisition | In progress (started ahead of Phase 1, by user's call) | 1/6 | No |
| 3 | Advanced Sentinel-2 preprocessing | Not started | 0/8 | No |
| 4 | Grid construction & feature aggregation | Not started | 0/4 | No |
| 5 | Label generation | Not started | 0/3 | No |
| 6 | Dataset assembly & split | Not started | 0/4 | No |
| 7 | Baseline model (E1) | Not started | 0/2 | No |
| 8 | Multimodal models & ablation (E2–E4) | Not started | 0/3 | No |
| 9 | Explainability (SHAP) | Not started | 0/3 | No |
| 10 | 2030 prediction & Infrastructure Pressure Index | Not started | 0/3 | No |
| 11 | Final report, reproducibility & documentation | Not started | 0/3 | No |

## Current position (detail)

- **Current phase:** Phase 0 implementation complete (Gate still pending explicit user walk-through).
  **Phase 2 Part 2.1 also done**, started ahead of Phase 1 by the user's explicit choice (to avoid
  redoing boundary/preprocessing work that might already exist in B2). 105/105 tests passing.
- **Next:** Phase 1 (study boundary & configuration) — now informed by real knowledge of what's in B2
  (see `open_questions.md` A1/A4). Part 1.1 should explicitly check the existing
  `vizag-geoai/data/boundaries/gvmc_boundary.geojson` for provenance before deciding whether to reuse it
  or rebuild from a freshly-verified source.
- **Plan gap flagged:** `plan.md`'s Phase 0 "Test cases" list doesn't name any test for `validation.py`
  (only logging's test is named), even though `validation.py` is an explicit Part 0.3 deliverable reused by
  every later phase. Wrote 18 tests for it anyway rather than leaving shared assertions untested — see
  `changelog.md`. Not treated as a plan deviation requiring a stop, since it's purely additive.

## Per-part log

As each part is implemented, add a row here (most recent first) with a one-line result. Full narrative
detail (what broke, what was decided) belongs in [`changelog.md`](changelog.md) and
[`bugs_and_fixes.md`](bugs_and_fixes.md); this table stays terse and scannable.

| Part | Date completed | Tests passing? | One-line result |
|---|---|---|---|
| 0.1 | 2026-09-29 | N/A (no tests specified for this part; verified by `git status` clean + `pyproject.toml` valid) | Repo init: `pyproject.toml` (Python 3.11–3.12, Part-0.1 core libs pinned), `.gitignore` (secrets, data/, models/, predictions/, logs/, Studio env noise), `git init` + GitHub remote (`origin`) wired via a repo-scoped SSH deploy key. |
| 0.2 | 2026-09-29 | 10/10 passing (`pytest tests/`) | `configs/paths.yaml` (every path from `plan.md` Section 1) + `src/utils/io.py`: `find_repo_root()` (cwd-independent), `load_config()`, `resolve_path()`, `ConfigError`, and `find_duplicate_paths()` for the "two keys, one path" edge case (warns, doesn't fail). Added `tests/unit/test_io.py` and the Phase-0-mandated `tests/unit/test_no_hardcoded_paths.py` lint test (includes a self-check that the detector isn't vacuous). Installed `pytest`+`pyyaml`; added `pyyaml` to `pyproject.toml`. |
| 0.3 | 2026-09-29 | 32/32 passing (`pytest tests/`) | `src/utils/logging.py`: `get_run_logger(phase, run_timestamp=...)` → append-safe `logs/<phase>_<timestamp>.log`. `src/utils/validation.py`: `assert_crs`, `assert_bounds_within`, `assert_no_nan`, `assert_nodata_consistent` (two-directional — catches both "nodata not masked" and "valid pixel misread as nodata"), all raising `ValidationError`. Refined `test_no_hardcoded_paths` to exempt only the literal *argument inside* a `resolve_path(...)` call (was about to false-positive on `resolve_path("logs")` since the dotted key and the path happen to be spelled the same). Credential-redaction in the logger is deliberately deferred to Part 0.4 (that's where `plan.md` places its edge case/test, and no secret ever flows through logging yet). |
| 0.4 | 2026-10-10 | 48/48 passing (`pytest tests/`) | Installed full geospatial stack (rasterio/GDAL incl. JP2OpenJPEG — verified via a real lossless write+read round-trip, not just a static driver-table check; rioxarray, dask, geopandas, pyarrow, rio-cogeo) + boto3/python-dotenv; resolved a numpy2 dependency conflict across the whole stack (see `bugs_and_fixes.md`) and updated `pyproject.toml` pins to match. Confirmed B2 connectivity end-to-end (bucket `satilliate-images`, endpoint `s3.us-east-005.backblazeb2.com`, read scope). New: `src/utils/env_check.py` (`check_jp2_driver_available`, `check_b2_credentials_present`, `NoCredentialsError`/`MissingDriverError`/`AuthFailedError`/`ReadOnlyKeyError` taxonomy — the latter two defined now, raised later by Part 0.5's real backend), `src/utils/secrets.py` (name-pattern-based credential detection, `redact()`, `scan_files_for_leaked_secrets()`), logger now redacts credential-like values automatically. Wrote `configs/b2.yaml` (endpoint+bucket confirmed; prefixes left `null`, pending Phase 2 inventory) and `configs/storage.yaml` (`budget_gb` confirmed at **150 GB** on 2026-10-10 — everything beyond that must stay in B2 only, per the user). **Part 0.4 is now complete.** |
| 0.5 | 2026-10-10 | 78/78 passing (`pytest tests/`) | `src/storage/backends.py`: `StorageBackend`-shaped `LocalBackend`, `FakeBackend` (byte/request counters), `B2Backend` (real boto3 S3-compatible calls, maps `ClientError` codes to `AuthFailedError`/`ReadOnlyKeyError`). **No backend exposes any delete method** — structurally enforced, plus a static AST scan confirming no code path calls one. `src/storage/manifest.py`: `Manifest`/`ManifestRecord`/`ManifestState` — the full `LISTED→...→EVICTED`/`FAILED` state machine, atomic writes (temp file + `os.replace`), a portable cross-process/thread file lock, stale-`.part`-file cleanup. `src/storage/guard.py`: `check_budget()` against the real 150 GB cap, refuses on `budget_gb: null` or projected overage, never frees space itself. `src/storage/evict.py`: `safe_evict()` — refuses (writes nothing) unless both B2-verified and derivative-validated; only a successful eviction gets a ledger entry. Manually verified `B2Backend` end-to-end against the real `satilliate-images` bucket (listed the known boundary files) — not an automated test, per the plan's "tests never touch real B2" rule. Caught and fixed a false positive in the Part 0.2 hardcoded-path lint (prose error messages starting with `"configs/..."` were being flagged) — narrowed the detector to exclude any string containing whitespace, with a regression test. **This was the last part of Phase 0.** |
| 2.1 | 2026-10-10 | 105/105 passing (`pytest tests/`) | **Done ahead of Phase 1**, by explicit user choice, to avoid redoing work that might already exist in B2. `src/acquisition/product_id.py`: parses a B2 key into Sentinel-2 product metadata (mission/level/sensing date/baseline/orbit/tile/processing date), matching by parsed product ID not exact key string; handles 3 real naming variants found in the bucket (`.SAFE.zip` raw archive, `.SAFE_<kind>.<ext>` per-scene derivative, and a shorter mosaic-composite naming with no tile ID). `src/acquisition/inventory.py`: paginated read-only listing, classification (complete/incomplete/duplicate/suspect-size/boundary/other/unknown — junk like `.DS_Store`/`Thumbs.db` always "unknown", never marked for deletion), writes `data/manifests/b2_inventory.jsonl` + `results/phase2/inventory_report.md`. **Ran for real against `satilliate-images`:** 1,474 objects, 205.85 GB. Two parser gaps found and fixed mid-run (a mosaic-naming variant and the raw `.SAFE.zip` extension) — see `bugs_and_fixes.md`. **Confirmed Assumption A1**: the raw ~190 GB archive is real and in B2 (280 `.SAFE.zip` files, 182.82 GB, all 4 epochs present) — it wasn't visible in Part 0.4's small 10-key sample. **Confirmed A4**: zipped, not unzipped. |
