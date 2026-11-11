# Open Questions / Assumptions Pending Confirmation

Values and assumptions that must come from the user — never guessed, per `plan.md` Section 0's rule that
credentials, bucket names, storage limits, and similar values must be stated explicitly and paused on.

## Storage assumptions (from `plan.md` Section 1A.2, to confirm at Part 2.1)

| ID | Assumption | Status | Confirmed value |
|---|---|---|---|
| A1 | The ~190 GB is already in a B2 bucket (not just a local/external drive) | **Confirmed by full Phase 2 Part 2.1 inventory (2026-10-10)** | Bucket `satilliate-images` has **1,474 objects, 205.85 GB total**, under prefix `vizag-geoai/`. Breakdown: raw Sentinel-2 `.SAFE.zip` archives — **280 files, 182.82 GB**, under `data/raw/sentinel2/<year>/`, covering all 4 planned epochs (2018/2020/2022/2024) — this is the actual ~190 GB the plan refers to. Plus already-processed output: 840 per-scene masked derivatives (13.59 GB, 3 tiles: T44QPE/T44QQE/T44QQF) and 346 mosaic-composite files (5.99 GB, 10 of which are incomplete — missing refl+scl). Plus boundary geojsons (2 files) and WorldPop rasters (6 files, 3.44 GB) already fetched. **Correction to the earlier 2026-09-29 note below:** that was based on a 10-key sample and wrongly implied no raw archive existed — the full inventory found it. |
| A2 | B2 bucket exposes an S3-compatible endpoint; app key has ≥read scope | **Confirmed** | Endpoint `https://s3.us-east-005.backblazeb2.com`, bucket `satilliate-images`. Read scope verified via `list_objects_v2` and a real full-bucket inventory run. Write scope not yet tested. Must use a genuine non-master Application Key (25-char keyID) — the master key's ID (=account ID, 12 chars) is rejected by the S3-compatible gateway even though valid for B2's native API. |
| A3 | User-provided Lightning storage cap → `studio.budget_gb` | **Confirmed** | **150 GB** max on the Studio; everything beyond that must stay in Backblaze B2 only (Tier 0, not counted against this budget) — matches the plan's own tier design. Set 2026-10-10. |
| A4 | Stored Sentinel-2 format: unzipped `.SAFE` vs `.zip` | **Confirmed: zipped** | Raw archives are whole zipped `.SAFE.zip` files (not unzipped `.SAFE` folders, not bare `.zip`) — decides the Phase 3 Part 3.0 read-strategy benchmark (ADR-001): extract-to-staging vs GDAL `/vsizip/` direct read. |
| A5 | B2 egress/transaction pricing checked by user for their account | **Confirmed** | User is on a paid B2 plan and has accepted the pricing (2026-10-10). No dollar figures recorded — just confirmed it's checked and accepted, not a blocker. |

## Other pending user inputs

Remaining research choices: validate historical built-up labels and contextual source dates; finalize
accessibility indicators, normalization and weights; resolve the 2024–2030 six-year forecast horizon.
The discussed `IPI = growth probability × accessibility gap` is a proposal, not an implemented or
universally standardized formula. Locality dry-run numbers are illustrative. A separate public demo
dashboard is built; the scientific prediction system remains planned.

**Part 3.6 range QC (2026-11-10; downstream rule subsequently approved):** 2018 has under 0.074% range outliers per index but severe
extrema (e.g. NDBI -3806.94 to 2208.96); 2022 has 12 slight outliers each in NDVI/NDBI/NDWI.
The outputs are formula-correct, not clipped, and all byte/pixel audits pass. This does not make the
extremes physically trustworthy. See `results/phase3/indices_validation.md`; do not invent thresholds.

**Gate review completed and user-approved (2026-11-10):** actual native union is 11,378
pixels in 2018 (0.0741045% of AOI), 12 in 2022, zero in 2020/2024. All flagged ratios have
negative terms; severe 2018 excursions are amplified by denominator cancellation. Four figures,
bounded actual-coordinate samples and full statistics are in `results/phase3/gate_review_summary.md`
and linked artifacts. The percentages above are not interchangeable with per-index valid-pixel
fractions. The physical cause within individual source scenes is not established. User explicitly
approved excluding only already-flagged values from each affected index's future mean, preserving
originals, carrying counts/coverage, keeping empty means missing and not dropping whole cells.
No clipping, broader negative-reflectance mask or new denominator threshold is authorized.
Part 4.2 implemented this rule and its final review approved at least 50% usable support for every
required index and epoch plus valid elevation and slope. This retains 6,355 of 6,371 cells while
preserving every evidence row. Date-safe population/OSM features, label validation and the six-year
forecast method remain unresolved quality choices; do not guess.

| Needed for | What's needed | Status |
|---|---|---|
| Modal+B2 foundation (v0.2.0) | Named Modal Secret `vizag-b2`, non-mutating remote environment verification and full regression suite. | **Resolved (2026-11-04).** Secret contains only `B2_KEY_ID` and `B2_APPLICATION_KEY`; Python 3.12.10 and geospatial imports verified remotely; 211/211 tests passed in Modal. No B2 objects were accessed or changed. |
| Git/GitHub versioning | Commit and push the recovered implementation checkpoint after reviewing the exact diff and receiving explicit approval. | **Resolved 2026-11-06.** User explicitly requested documentation through validated Part 3.5 and publication to GitHub. No tag was requested. |
| `configs/b2.yaml` (Part 0.4) | B2 endpoint URL, bucket name, prefixes | **Resolved (2026-10-10).** Endpoint + bucket confirmed. `raw_sentinel2`/`raw_other` prefixes now filled in from Part 2.1's real inventory. `processed_backup`/`manifests_backup` deliberately still `null` — a Phase 3 Part 3.0 design decision (reuse the bucket's existing legacy `processed/` prefix or use a new one), not yet made. |
| B2 credentials | Actual `.env` var names (not the plan's placeholder `B2_KEY_ID`/`B2_APP_KEY`): `Backbaze-keyID`, `Backbaze-applicationKey`, plus `BUCKET-ID` (holds the B2 bucket ID, not name — unused; real bucket name `satilliate-images` is hardcoded in code/config instead) and `Backbaze-keyName` (unused, informational only). `.env` is gitignored — confirmed never committed. | **Resolved and working** |
| `configs/storage.yaml` (Part 0.4) | Real Lightning storage plan cap (`budget_gb`) | **Resolved (2026-10-10).** User set 150 GB max. |
| `configs/boundary.yaml` (Part 1.1) | GVMC boundary source: shapefile or official URL | **Resolved (2026-10-10).** Fetched fresh from OpenStreetMap Nominatim (relation 17493324) and written to `configs/boundary.yaml` + `data/boundaries/`. Cross-checked against the B2 file Part 2.1 found: exact match (IoU = 1.0), confirming that file's provenance was legitimate too. **User visually confirmed `results/phase1_boundary_check.png` on 2026-10-10** ("yes"). |
| DEM, WorldCover, OSM data (Phase 2 Part 2.4 / needed by Phase 4–5) | **Resolved (2026-10-10).** Fetched from verified public sources (Copernicus GLO-30 DEM, ESA WorldCover 10m 2021, OSM via Overpass/osmnx scoped to the buffered boundary) after the user approved a dry-run estimate (~86 MB). 9/9 files verified OK, uploaded to B2 under `vizag-geoai/data/raw/{dem,worldcover,osm}/`, local copies preserved in `data/raw_small/`. | **Resolved** |

## How to resolve these

Do not proceed past the part that needs a given value without it. When the user supplies a value, update
the "Confirmed value" / "Status" column here immediately, and log the event in
[`changelog.md`](changelog.md).
