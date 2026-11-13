# Phase-by-Phase Progress

**Read after [`tracking.md`](tracking.md).** This is the live status table against the 12 phases defined in
[`../plan.md`](../plan.md). Update the Status / Parts-done / Gate columns as work happens — this table is
the fastest way for a new session to see exactly where things stand.

Statuses: `Not started` / `In progress` / `Blocked` / `Gate pending` / `Complete`.

| Phase | Title | Status | Parts done | Phase Gate confirmed? |
|---|---|---|---|---|
| 0 | Project scaffolding & environment | Gate pending | 5/5 | No |
| 1 | Study boundary & configuration | Complete | 2/2 | **Yes** — boundary visual confirmed by user 2026-10-10 (`phase1_boundary_check.png`); Part 1.2 configs are plain config files with no separate visual gate per plan.md |
| 2 | B2 inventory, reconciliation & acquisition | Complete | 6/6 | **Yes** — A1–A5 all confirmed 2026-10-10; nothing deleted/overwritten anywhere throughout |
| 3 | Advanced Sentinel-2 preprocessing | Complete | 8/8 | Yes — user approved review evidence and the affected-index-only outlier exclusion rule on 2026-11-10; originals remain unchanged |
| 4 | Grid construction & feature aggregation | In progress | 2/4 | No |
| 5 | Label generation | Not started | 0/3 | No |
| 6 | Dataset assembly & split | Not started | 0/4 | No |
| 7 | Baseline model (E1) | Not started | 0/2 | No |
| 8 | Multimodal models & ablation (E2–E4) | Not started | 0/3 | No |
| 9 | Explainability (SHAP) | Not started | 0/3 | No |
| 10 | 2030 prediction & Infrastructure Pressure Index | Not started | 0/3 | No |
| 11 | Final report, reproducibility & documentation | Not started | 0/3 | No |

## Current position (detail)

- **Infrastructure migration verified 2026-11-04:** project version 0.2.0 uses Modal as the only
  compute/test plane and Backblaze B2 as the only persistent runtime store. Modal Python 3.12.10,
  geospatial imports and normalized B2 secret presence were verified remotely. Full regression:
  **211/211 passed in Modal (4.23 s)**. No B2 objects were accessed or changed.
- **Part 3.1 complete and confirmed (2026-11-04):** complete real inventory processed in Modal; 280 raw
  archives catalogued; all four epochs have complete L2A coverage of required tile `T44QQE`; outputs
  written and size-verified under `vizag-geoai/v2/`; 219/219 tests pass remotely. User explicitly
  confirmed epochs `[2018, 2020, 2022, 2024]`.
- **Part 3.2 complete and confirmed (2026-11-04):** 56 complete dry-season L2A scenes triaged from B2
  using SCL windows only; 32 selected (8 per epoch). Mean usable coverage: 2018=98.70%, 2020=96.98%,
  2022=85.49%, 2024=71.70%. Cloud/shadow rates are low, but 2022/2024 contain partial-coverage nodata
  (13.56%/27.82% mean). User approved the selection with this limitation recorded; Phase 3.5 must inspect
  `valid_obs_count` and halt if combined coverage is inadequate.
- **Part 3.3 complete (2026-11-05):** all 32 selected scenes were extracted to 64 immutable
  contract-3.3.2 COGs. The verified 32-row manifest is 34,713 bytes with SHA-256
  `9168f92fb3ed33694c06b643e9d8a533899206cd8bf0a77633ed93955e8ebe6e`. Final audit found
  32 complete pairs and zero partial pairs; no existing COG was overwritten.
- **Part 3.4 complete (2026-11-05):** configurable in-memory SCL masks use classes 4/5/6/7 as valid,
  conservatively exclude class 2, and dilate cloud/shadow classes by a circular 2 pixels. Read-only
  validation scanned all 32 SCL COGs (24,659,693 compressed bytes), found zero unknown values, and measured
  epoch valid fractions 98.07%/96.47%/85.08%/71.44%.
- **Part 3.5 complete (2026-11-06):** approved threshold is 4 valid observations with at least 99% AOI
  coverage. Four six-band median composites and four count rasters were published as immutable
  contract-3.5.0 strict COGs (1,468,221,549 bytes total). Independent read-only audit streamed and matched
  every SHA-256, confirmed one version per key, validated schema/grid/provenance, and proved pixel-level
  agreement between count ≥4 and composite validity. Coverage: 2018=99.6693%, 2020=99.9107%,
  2022=99.7986%, 2024=99.3729%.
- **Part 3.6 production complete (2026-11-10):** user approved the workload; full Modal suite
  **295 passed, one existing warning**. Downloaded and byte-hashed the four audited composites
  (1,465,909,833 bytes), created 20 immutable index COGs (1,309,726,569 bytes), downloaded the exact
  published versions and verified hashes, strict COGs, grids/provenance and every index pixel.
  Created one 17,788-byte manifest with SHA-256
  `4fb908c22737c7fc8de60f6ac4a36a5522d3d1e538b1bc330e8b4bb951dd0fcb` after all four audits.
  Range QC remains open: 2018 has rare extreme finite values; 2022 has 12 slight outliers each in
  NDVI/NDBI/NDWI. Preserved and reported, not clipped; review before features/models. Evidence:
  `results/phase3/indices_validation.md` and `.json`.
- **Part 3.7 read-only audit approved and completed (2026-11-10):** source-based Modal launch
  works on remote Python 3.12.10; full regression **315 passed**, one existing warning.
  Verified presence/size/version identities for all 92 expected rasters (13,419,102,871 bytes),
  SHA metadata for 28 composite/count/index rasters, and full hashes of both critical manifests
  (52,501 bytes read). V2 contains 100 objects/versions, 13,794,986,005 bytes, no delete markers.
  Two older pilot rasters are preserved. No raster payload read, B2 write, eviction or Git mutation.
  Evidence: `results/phase3/storage_report.md` and `storage_audit.json`.
- **Part 3.7 publication complete (2026-11-10):** user explicitly approved the exact transfer.
  Full regression **338 passed**, one existing warning. Rechecked the 94 existing references
  against the approved snapshot, then published 16 frozen snapshots (122,487 bytes) and the
  completion manifest last (41,766 bytes). All 17 exact-version read-back/hash checks passed;
  total new payload **164,253 bytes**, below the approved 188,023-byte cap. V2 now contains
  117 current objects/versions, 13,795,150,258 bytes, zero delete markers. All 92 production
  rasters unchanged; no raster payload transfer, overwrite, deletion or Git mutation.
  Eviction was not required. Evidence: `results/phase3/archive_completion.md` and `.json`.
- **Phase 3 gate evidence generated and verified (2026-11-10):** approved source-based Modal
  run `ap-TzE1Q1IpjSls5mOpRKwUU0` completed successfully; full regression **357 passed**, one
  existing warning. Read/hash checked all 28 pinned raster versions, recomputed native formula,
  mask/range/coverage statistics, and matched all prior index counts. Four figures plus three
  review reports and a final manifest were published and exact-version verified, then saved
  locally without overwrite. Input 2,778,034,701 bytes; new output 5,389,770 bytes;
  stored/readback/viewing payload 16,169,310 bytes, within the approved 48 MiB cap.
  Unique outlier pixels: 2018=11,378; 2020=0; 2022=12; 2024=0. Every flagged ratio has a negative
  term; largest 2018 excursions have strong denominator cancellation. Original rasters unchanged.
  Evidence: `results/phase3/gate_review_summary.md`, `review.md`, four `qc_<epoch>.png` files,
  `range_review.json`/`.csv`, `gate_review_receipt.json` and `phase3_gate_review.v1.json`.
- **Phase 3 gate approved (2026-11-10):** user approved the review evidence, then explicitly
  approved affected-index-only exclusion of already-flagged out-of-range values from future
  feature means. Preserve original COGs, carry per-cell exclusions/support counts, keep empty
  means missing; do not clip or drop whole cells automatically. Policy recorded separately
  in `configs/feature_aggregation.yaml`; Part 4.2 later implemented the rule. Final review
  approved >=50% per-index/per-epoch support plus valid terrain; this is a data-eligibility
  policy, not a promise of prediction accuracy.
- **Part 4.1 complete and visually approved (2026-11-11):** Modal Python 3.12.10 restored and
  hash-verified the pinned 32,768-byte boundary, built 6,371 fixed 500 m squares (5,912 full and
  459 edge), and validated stable IDs, exact dimensions, EPSG:4326 interchange, zero AOI gap and
  zero overlap. Four create-only B2 outputs totaling 2,936,091 bytes were exact-version/read-back/
  hash verified. Full Modal suite: 367 passed, one existing warning. The user approved the preview.
  Part 4.2 subsequently started under separately approved guarded units.
- **Part 4.2a source preflight complete (2026-11-11):** 371 Modal tests passed, then the
  metadata-only job read 52,147 bytes across three pinned small objects and pinned all 20 index
  COGs plus both DEM object versions. Raster payload reads=0 and B2 writes=0. The two legacy DEM
  uploads have correct single-version sizes (46,382,829 bytes combined) but no SHA-256 metadata.
  The later approved version-pinned DEM gate passed; this preflight remains historical evidence.
- **Part 4.2 DEM gate and satellite pilot passed (2026-11-11):** the corrected half-pixel-aligned
  DEM contract passed exact-version hashes, strict COG/schema/seam checks and all 25,920,000 pixels
  with zero B2 writes (`ap-XtNy5uLjfsykXJySgzFpbI`). The aggregation core then passed 381 Modal
  tests. A create-only 2024 NDVI pilot (`ap-ESKgft4wckfIBJXclDGxns`) retained all 6,371 grid rows,
  reconciled 15,353,996 AOI candidates, 15,257,709 usable and 96,287 nodata pixels, and found zero
  out-of-range values. Three tiny edge cells have no 10 m pixel centre and remain missing. This
  was a historical pilot gate; the subsequent full batch and policy review completed successfully.
- **Part 4.2 complete (2026-11-11):** corrected full batch `ap-Dz1CfM1F43J7c3bAnkHkcH`
  produced 25,484 satellite rows and 6,371 terrain rows. Six create-only outputs totaling
  3,308,109 bytes were exact-version hash/read-back verified with the manifest last. Read-only
  review `ap-wKjNJgIpGetKO9w1nqLs01` revalidated all outputs and the support map. Approved
  eligibility is >=50% usable support for every required index/epoch plus valid elevation/slope,
  retaining 6,355 cells across all epochs while preserving every evidence row.
- **Part 4.3 complete (2026-11-12):** official WorldPop Global2 R2025A rasters and authentic
  ohsome API v2 historical OSM snapshots were acquired for 2018/2020/2022/2024. Final Modal
  aggregation `ap-jA33oh65sIRu9Q8hSSTujJ` produced 25,484 unique rows for all 6,371 cells and four
  epochs with no missing, non-finite or negative metrics. Contract 4.3.1 supersedes the preserved
  4.3.0 table after review replaced unstable tiny-edge road-density denominators with the fixed
  0.25 km² analysis-cell denominator and retained `aoi_fraction`. Full regression: 402 passed,
  one existing warning.
- **Part 4.4 technically complete; Phase 4 gate presented (2026-11-12):** corrected Modal production run
  `ap-oVzU63TWtILbwHolnRgNCk` assembled the pinned Part 4.2 and 4.3.1 sources into 25,484
  unique rows, 69 columns, 6,371 cells and four epochs. It retained 6,355 eligible and 16
  explicitly ineligible cells. The first attempt stopped before writing because the validator
  rejected legitimate zero-support source nulls; the corrected fail-closed rule accepts them
  only when support is zero and the row is ineligible, with no imputation or row deletion.
  Four create-only B2 objects totaling 3,832,563 bytes were exact-version/read-back/hash
  verified with the manifest last. Leakage-safe growth uses only the immediately preceding
  epoch. Full Modal regression: 405 passed, one existing warning.
- **Part 5.1 source preflight passed (2026-11-12):** read-only Modal run
  `ap-dU3AeibKf2cToxvrFA9dBU` pinned all 20 approved index COGs (1,309,726,569
  bytes) and the single 39,539,634-byte WorldCover 2021 v200 object with zero
  pixel reads and zero B2 writes. WorldCover lacks SHA-256 metadata, so its exact
  version must be payload-hashed in the bounded header/pixel pilot. The 2021 map
  will cross-check bracketing 2020/2022 classifications and will not be represented
  as two dated references. Full Modal regression: 407 passed, one existing warning.
- **Part 5.1 fixed-rule scientific pilot failed safely (2026-11-12):** full-pixel
  Modal run `ap-RPrppXevOdvK4JnsyhgOpE` evaluated 30 multi-index rules against the
  2021 WorldCover built class for both bracketing epochs. The best rule reached only
  0.564/0.567 balanced accuracy, 0.227/0.234 F1 and 0.148/0.152 recall in 2020/2022,
  predicting about 3.3% built versus WorldCover's 11.0%. This systematic undercount
  fails the label-quality gate. The run wrote zero B2 objects; no classification or
  labels were published, and Parts 5.2/5.3 remain unstarted. A time-aware validated
  reference/classifier is required before Part 5.1 can complete.
- **Part 5.1 Dynamic World design and access gate passed (2026-11-12/13):** primary-source
  review selected `GOOGLE/DYNAMICWORLD/V1` as one time-aware label source, with WorldCover/GHSL
  restricted to independent audits. Earth Engine project `vizag-geoai-ee-20261112` is registered
  non-commercially. Metadata planning found 118 exact `T44QQE` observations across the four
  January-March windows and 100% AOI coverage; sampled per-pixel valid-count minima were 5-6.
  Exact matching to the eight Phase 3 scenes was abandoned after authentic Dynamic World gaps
  proved that one-to-one substitution was invalid.
- **Part 5.1 least-privilege download correction (2026-11-13):** the first pilot stopped before
  writes because `roles/earthengine.viewer` lacks `earthengine.thumbnails.create`. Instead of
  granting broad Writer access, custom role `vizagEarthEngineThumbnailCreator` contains only that
  permission. A 64x64 Modal probe returned 4,096 valid pixels with zero B2 access and zero exports.
- **Part 5.1 2022 Dynamic World pilot published (2026-11-13):** Modal run
  `ap-wLyycPqfUrxigh2z2o9EyH` composed 32 equal-weight acquisitions and published three strict,
  create-only COGs plus a manifest under `vizag-geoai/v2/labels/dynamic_world/contract-5.1.0/2022/`.
  All 31,776,122 pixels are valid; valid count is 5-32 (mean 15.574); built median is
  0.01657-0.77745 and temporal standard deviation 0.00023-0.30727. A prior attempt exposed a
  two-band/2D-mask QC indexing bug before publication; the tested helper fix raised the suite to
  414 passed, one known warning. No object was written by either failed attempt.
- **Part 5.1 pilot scientific review requires a spatial gate (2026-11-13):** read-only run
  `ap-5U2xu4joBNHGe8oBrYRHrH` measured an 11.859% Dynamic World mode-built fraction. The explicitly
  non-authoritative WorldCover 2021 audit achieved 0.916 balanced accuracy, 0.902 recall, 0.451
  precision and 0.602 F1. The next action is deterministic stratified spatial review. The
  2018/2020/2024 batch, cell fractions, Phase 5.2 and Phase 5.3 remain unstarted.
- **Part 3.3.1 validation history (2026-11-04):** accuracy-first float32 reflectance plus separate SCL
  COG design approved. Complete read-only Modal metadata/header scan passed for all 32 scenes and 224
  required assets. Baselines are 04.00/05.00/05.10; every required offset mapping and frozen grid invariant
  passed. JP2 nodata tags are unset, so pixel-level nodata semantics are the next mandatory validation gate.
  Pixel validation is now complete: per-band DN=0 must be masked before radiometry/resampling and combined
  with (not replaced by) the SCL mask. All 32 scenes completed via preemption-resilient epoch units; 235 tests pass.
  Persisted nodata `-9999.0` is approved and the fail-closed metadata-driven conversion is implemented;
  real-pixel statistics now pass across all 32 scenes and mixed baselines with stable cross-epoch scaling.
  Rare out-of-nominal values are recorded, not clipped. 242/242 tests pass; no extraction output yet.
  Spatial/resampling validation also passed all 32 scenes: exact window equivalence, one frozen 10 m grid,
  nodata-safe bilinear SWIR, and class-safe nearest SCL. 247/247 tests pass. Part 3.3.1 contract validation is complete.
  The one-scene 2018 pilot COG pair is now remotely validated after resuming at the final checkpoint without
  overwrite: reflectance 375,165,086 bytes and SCL 481,974 bytes. The GDAL `.tif` VSI allowlist omission is
  fixed with regression coverage; 249/249 Modal tests pass. Batch extraction of the remaining scenes has not started.
  The subsequent read-only batch preflight passed: all 32 source archives exist (26,094,806,854 bytes total),
  output pairs are 1 complete / 31 absent / 0 partial, and the extraction manifest does not yet exist.
  Batch planning and overwrite-safety checks are covered by 257/257 passing Modal tests. Awaiting separate
  approval before any extraction output or manifest is written.
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
| 3.6 | 2026-11-10 | 295 passed, one existing warning in Modal | Published and independently byte/pixel-audited 20 index COGs plus a verified manifest. Finite 2018 extremes and 12 slight 2022 outliers per affected index flagged for scientific review before downstream use. |
| 3.5 | 2026-11-06 | Latest user-supplied regression `ExitCode.OK`, one warning; count omitted in excerpt; independent audit passed | Four contract-3.5.0 epoch composites plus count rasters passed strict COG, streamed hash, single-version, coverage and pixel-validity gates. |
| 3.4 | 2026-11-05 | 266/266 passing in Modal | Configurable SCL validity and 20 m cloud/shadow dilation validated read-only across all 32 SCL COGs; zero unknown classes and no B2 writes. |
| 3.3 | 2026-11-05 | 260/260 passing in Modal | Extracted and validated 32 reflectance/SCL pairs under immutable contract-3.3.2 paths; published and audited a 32-row SHA-256-identified manifest without overwriting existing outputs. |
| 3.2 | 2026-11-04 | 226/226 passing in Modal | 56 complete real dry-season scenes triaged with SCL-only windows; 32 selected (8/epoch) and user-approved. Very low cloud/shadow, but partial-coverage nodata recorded for 2022 (13.56%) and 2024 (27.82%); Phase 3.5 valid-observation gate is mandatory. |
| 3.1 | 2026-11-04 | 219/219 passing in Modal | Full real B2 inventory parsed into a 280-scene catalogue. Required-tile L2A candidates: 2018=19, 2020=22, 2022=21, 2024=24; no L1C-only epochs, gaps or duplicates. Two new v0.2 B2 outputs written and verified. User confirmed epochs `[2018, 2020, 2022, 2024]`. |
| 0.1 | 2026-09-29 | N/A (no tests specified for this part; verified by `git status` clean + `pyproject.toml` valid) | Repo init: `pyproject.toml` (Python 3.11–3.12, Part-0.1 core libs pinned), `.gitignore` (secrets, data/, models/, predictions/, logs/, Studio env noise), `git init` + GitHub remote (`origin`) wired via a repo-scoped SSH deploy key. |
| 0.2 | 2026-09-29 | 10/10 passing (`pytest tests/`) | `configs/paths.yaml` (every path from `plan.md` Section 1) + `src/utils/io.py`: `find_repo_root()` (cwd-independent), `load_config()`, `resolve_path()`, `ConfigError`, and `find_duplicate_paths()` for the "two keys, one path" edge case (warns, doesn't fail). Added `tests/unit/test_io.py` and the Phase-0-mandated `tests/unit/test_no_hardcoded_paths.py` lint test (includes a self-check that the detector isn't vacuous). Installed `pytest`+`pyyaml`; added `pyyaml` to `pyproject.toml`. |
| 0.3 | 2026-09-29 | 32/32 passing (`pytest tests/`) | `src/utils/logging.py`: `get_run_logger(phase, run_timestamp=...)` → append-safe `logs/<phase>_<timestamp>.log`. `src/utils/validation.py`: `assert_crs`, `assert_bounds_within`, `assert_no_nan`, `assert_nodata_consistent` (two-directional — catches both "nodata not masked" and "valid pixel misread as nodata"), all raising `ValidationError`. Refined `test_no_hardcoded_paths` to exempt only the literal *argument inside* a `resolve_path(...)` call (was about to false-positive on `resolve_path("logs")` since the dotted key and the path happen to be spelled the same). Credential-redaction in the logger is deliberately deferred to Part 0.4 (that's where `plan.md` places its edge case/test, and no secret ever flows through logging yet). |
| 0.4 | 2026-10-10 | 48/48 passing (`pytest tests/`) | Installed full geospatial stack (rasterio/GDAL incl. JP2OpenJPEG — verified via a real lossless write+read round-trip, not just a static driver-table check; rioxarray, dask, geopandas, pyarrow, rio-cogeo) + boto3/python-dotenv; resolved a numpy2 dependency conflict across the whole stack (see `bugs_and_fixes.md`) and updated `pyproject.toml` pins to match. Confirmed B2 connectivity end-to-end (bucket `satilliate-images`, endpoint `s3.us-east-005.backblazeb2.com`, read scope). New: `src/utils/env_check.py` (`check_jp2_driver_available`, `check_b2_credentials_present`, `NoCredentialsError`/`MissingDriverError`/`AuthFailedError`/`ReadOnlyKeyError` taxonomy — the latter two defined now, raised later by Part 0.5's real backend), `src/utils/secrets.py` (name-pattern-based credential detection, `redact()`, `scan_files_for_leaked_secrets()`), logger now redacts credential-like values automatically. Wrote `configs/b2.yaml` (endpoint+bucket confirmed; prefixes left `null`, pending Phase 2 inventory) and `configs/storage.yaml` (`budget_gb` confirmed at **150 GB** on 2026-10-10 — everything beyond that must stay in B2 only, per the user). **Part 0.4 is now complete.** |
| 0.5 | 2026-10-10 | 78/78 passing (`pytest tests/`) | `src/storage/backends.py`: `StorageBackend`-shaped `LocalBackend`, `FakeBackend` (byte/request counters), `B2Backend` (real boto3 S3-compatible calls, maps `ClientError` codes to `AuthFailedError`/`ReadOnlyKeyError`). **No backend exposes any delete method** — structurally enforced, plus a static AST scan confirming no code path calls one. `src/storage/manifest.py`: `Manifest`/`ManifestRecord`/`ManifestState` — the full `LISTED→...→EVICTED`/`FAILED` state machine, atomic writes (temp file + `os.replace`), a portable cross-process/thread file lock, stale-`.part`-file cleanup. `src/storage/guard.py`: `check_budget()` against the real 150 GB cap, refuses on `budget_gb: null` or projected overage, never frees space itself. `src/storage/evict.py`: `safe_evict()` — refuses (writes nothing) unless both B2-verified and derivative-validated; only a successful eviction gets a ledger entry. Manually verified `B2Backend` end-to-end against the real `satilliate-images` bucket (listed the known boundary files) — not an automated test, per the plan's "tests never touch real B2" rule. Caught and fixed a false positive in the Part 0.2 hardcoded-path lint (prose error messages starting with `"configs/..."` were being flagged) — narrowed the detector to exclude any string containing whitespace, with a regression test. **This was the last part of Phase 0.** |
| 2.1 | 2026-10-10 | 105/105 passing (`pytest tests/`) | **Done ahead of Phase 1**, by explicit user choice, to avoid redoing work that might already exist in B2. `src/acquisition/product_id.py`: parses a B2 key into Sentinel-2 product metadata (mission/level/sensing date/baseline/orbit/tile/processing date), matching by parsed product ID not exact key string; handles 3 real naming variants found in the bucket (`.SAFE.zip` raw archive, `.SAFE_<kind>.<ext>` per-scene derivative, and a shorter mosaic-composite naming with no tile ID). `src/acquisition/inventory.py`: paginated read-only listing, classification (complete/incomplete/duplicate/suspect-size/boundary/other/unknown — junk like `.DS_Store`/`Thumbs.db` always "unknown", never marked for deletion), writes `data/manifests/b2_inventory.jsonl` + `results/phase2/inventory_report.md`. **Ran for real against `satilliate-images`:** 1,474 objects, 205.85 GB. Two parser gaps found and fixed mid-run (a mosaic-naming variant and the raw `.SAFE.zip` extension) — see `bugs_and_fixes.md`. **Confirmed Assumption A1**: the raw ~190 GB archive is real and in B2 (280 `.SAFE.zip` files, 182.82 GB, all 4 epochs present) — it wasn't visible in Part 0.4's small 10-key sample. **Confirmed A4**: zipped, not unzipped. |
| 1.1 | 2026-10-10 | 121/121 passing (`pytest tests/`) | `src/acquisition/boundary.py`: `fetch_osm_boundary()` queries OpenStreetMap Nominatim for the real GVMC administrative boundary (never estimated), validates it's actually an administrative entity (`category=="boundary"`, plausible `type`) before accepting; `reproject_and_buffer()` to `EPSG:32644` + configurable buffer; `check_area_sanity()`; `cross_check_against_existing()` compares against whatever's already in B2 without trusting it as ground truth; `plot_boundary_check()` writes the Phase 1 Gate PNG. `configs/boundary.yaml` created with the real retrieval metadata (OSM relation 17493324, retrieved 2026-10-10). **Ran for real:** matched "Visakhapatnam, Visakhapatnam Urban..." (OSM relation 17493324), area 625.15 km². **Cross-check vs. the B2 boundary file found by Part 2.1: IoU = 1.0, exact area match** — the existing B2 file is geometrically identical to this freshly-verified OSM fetch, so it was almost certainly already built the same way. `results/phase1_boundary_check.png` generated — reviewed, matches Vizag's real shape (coastal, irregular). **User confirmed the gate 2026-10-10 ("yes").** |
| 1.2 | 2026-10-10 | 131/131 passing (`pytest tests/`) | `configs/temporal.yaml` (epochs `[2018,2020,2022,2024]` — confirmed against the real B2 inventory, not assumed; training pairs 2018→2020/2020→2022; holdout 2022→2024; prediction target 2030), `configs/grid.yaml` (500 m cells, documented rationale), `configs/label.yaml` (sensitivity thresholds 5/10/20%, primary 10%, already-built exclusion 90%). No test is named for this part in `plan.md` (same gap as Part 0.3) — wrote 10 tests anyway, including a check that the temporal holdout pair can't overlap/leak into the training pairs. **Phase 1 is now fully complete; no further gate action needed** (the plan's Phase 1 Gate criterion is specifically the boundary visual, already confirmed in Part 1.1). |
| 2.2 | 2026-10-10 | 146/146 passing (`pytest tests/`) | `src/acquisition/reconcile.py`: `compute_required_tiles()` — computes which Sentinel-2 MGRS tiles the buffered boundary actually intersects using the real MGRS grid (the `mgrs` library, point-sampled at ~2km density), not assumed from whatever's already in B2. **Finding: only `T44QQE` is strictly required** given the current 5km buffer — `T44QPE`/`T44QQF` (also present in B2) are extra, not wasted, would become required if the buffer distance increases. `reconcile_sentinel2()`/`reconcile_small_datasets()` diff requirements against Part 2.1's inventory. Writes `configs/data_requirements.yaml` and `results/phase2/missing_report.md`. **Ran for real:** zero missing (tile,epoch) pairs for Sentinel-2 (19-24 scenes per epoch for T44QQE); WorldPop fully covered (all 4 years); **DEM, WorldCover, and OSM data are entirely missing** — not yet fetched by anyone, confirmed absent from the real inventory. Added `mgrs` to `pyproject.toml`. 15 new tests, 146/146 total passing. |
| 2.3 | 2026-10-10 | 164/164 passing (`pytest tests/`) | `src/acquisition/integrity.py`: `check_zip_band_completeness()` reads ONLY a raw `.SAFE.zip`'s central directory via HTTP range requests (no content download) to verify all 6 bands (B02/B03/B04/B08/B11/B12) + SCL + `MTD_MSIL2A.xml` are present — a genuinely cheap check, proven in tests to transfer well under half the archive size. `check_size_sanity()`, `audit_scene()` (catches per-scene errors so one bad file doesn't abort the batch), `run_integrity_audit()` (scoped to required tiles only, per Section 1A.4's "read only what's needed"). Added `etag: str \\| None` to `ObjectInfo` (`backends.py`) — B2's ETag recorded as a drift-detection fingerprint, not verified against anything (multipart-upload ETags aren't plain content MD5s). **Ran for real against all 86 required-tile (T44QQE) raw scenes: 86/86 OK** — every scene has all 6 bands + SCL + metadata, sane size, zero corruption. Caught 2 more hardcoded-path-lint false positives mid-build (a dict key `"results"` and a substring-membership-test operand `"/IMG_DATA/"` both coincidentally matched the path-literal heuristic) — narrowed the lint further with 3 new regression tests. 164/164 total passing. |
| 2.4 | 2026-10-10 | 185/185 passing (`pytest tests/`) | `src/acquisition/sources/{dem,worldcover,osm}.py` + `src/acquisition/fetch_missing.py`. DEM: Copernicus GLO-30 (AWS Open Data `s3://copernicus-dem-30m`, public, no auth), tile IDs computed from the real buffered-boundary geometry (1° grid). WorldCover: ESA WorldCover 10m 2021 (`s3://esa-worldcover`, public), 3° grid. OSM: roads + amenities fetched live via Overpass (through osmnx), scoped to the buffered boundary — not a regional extract. `run_fetch_missing()` defaults to `dry_run=True` (estimate only); real run checks the storage guard first, verifies every file (valid raster/CRS for DEM+WorldCover, non-empty valid geometries for OSM) before upload, and **skips uploading anything that fails verification**. WorldPop skipped — already present. **Ran for real (user-approved):** dry-run estimated ~86 MB (DEM 46.4 MB + WorldCover 39.5 MB); real fetch got DEM (2 tiles, both OK), WorldCover (1 tile, OK), OSM (116,806 road features/30.5 MB + 627 amenities/300 KB, both OK) — **9/9 files verified OK, 0 skipped**, all uploaded to B2 under `vizag-geoai/data/raw/{dem,worldcover,osm}/` (matching the existing WorldPop prefix convention, not a new `raw_small`-named B2 prefix), local copies preserved in `data/raw_small/`. Confirmed present in both places post-upload. Caught one more hardcoded-path-lint false positive (an f-string literal fragment `"/map/"` building a remote S3 key) — narrowed with 2 more regression tests. 185/185 total passing. |
| 2.5 | 2026-10-10 | 196/196 passing (`pytest tests/`) | `src/acquisition/acquire_large.py`: `check_remaining_large_items()` re-reconciles fresh (not cached from Part 2.2) against the current `configs/data_requirements.yaml` and the real inventory. **Ran for real: still zero missing (tile, epoch) pairs** — nothing to fetch, consistent with Part 2.2. The full stream-through staging/upload/verify/evict flow for large items is deliberately not built speculatively — there's no real missing item to validate it against right now; it gets built if/when one actually appears (e.g. buffer distance increases, or a new epoch is added). `results/phase2/part_2_5_resume_status.md` written. |
| 2.6 | 2026-10-10 | 196/196 passing (`pytest tests/`) | `src/acquisition/backup.py`: `backup_manifests_to_b2()` mirrors `data/manifests/` to B2 (copy-only) under `configs/b2.yaml`'s newly-set `manifests_backup` prefix (`vizag-geoai/data/manifests/` — didn't exist before, no legacy-naming conflict unlike `processed_backup`, which is still deliberately `null`). Added `Manifest.pending()` (`src/storage/manifest.py`) — returns records not yet in a terminal state, the actual resumable worklist. **Resume drill proven by test, not just asserted**: `test_pending_simulates_a_resume_with_zero_duplicate_work` processes a 2-item worklist, "crashes" one mid-flight, reloads via a brand-new `Manifest` instance on the same file (simulating a Studio restart), and confirms only the interrupted item gets reprocessed — the completed one is never touched again. **Ran for real:** `b2_inventory.jsonl` (632,216 bytes) backed up and confirmed present in B2. `results/phase2/part_2_6_backup_status.md` written. **This was the last part of Phase 2** — all 6 parts done, though the Phase 2 Gate itself still needs the user on Assumption A5 (B2 pricing), per `plan.md`'s explicit gate checklist. |
| 3.0 | 2026-10-10 | 211/211 passing (`pytest tests/`) | `src/preprocessing/read_strategy.py`: benchmarks strategy (a) fetch-to-staging vs. (b) direct remote windowed read via GDAL's `/vsizip/vsis3/` chain against B2. `parse_curl_verbose_log()` (pure, unit-tested) measures real bytes transferred + request count by parsing libcurl's verbose output captured at the OS stderr-fd level — `read_band_window_remote()` itself isn't unit tested (needs live network/credentials), consistent with the project's established pattern. Refactored `integrity.py`'s private `_RangeReadFile` into a shared public `RangeReadFile` in `src/storage/backends.py` (now used by both Part 2.3 and Part 3.0) and added `list_zip_contents()`. Added `docs.decisions` to `configs/paths.yaml` rather than hardcoding the path. **Ran for real on 2 scenes from T44QQE:** strategy (b) won decisively — 2.8x faster (1.39s vs 3.96s avg), 98.5% less data (8.89 MB vs 606.3 MB avg), zero staging disk vs up to 928 MB. `results/phase3/read_benchmark.md` + `docs/decisions/ADR-001-read-strategy.md` written. **User approved strategy (b) 2026-10-10 — ADR-001 marked Accepted.** 15 new tests, 211/211 total passing. |
