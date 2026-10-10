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
| A5 | B2 egress/transaction pricing checked by user for their account | **Unconfirmed** | — |

## Other pending user inputs

| Needed for | What's needed | Status |
|---|---|---|
| `configs/b2.yaml` (Part 0.4) | B2 endpoint URL, bucket name, prefixes | **Resolved (2026-10-10).** Endpoint + bucket confirmed. `raw_sentinel2`/`raw_other` prefixes now filled in from Part 2.1's real inventory. `processed_backup`/`manifests_backup` deliberately still `null` — a Phase 3 Part 3.0 design decision (reuse the bucket's existing legacy `processed/` prefix or use a new one), not yet made. |
| B2 credentials | Actual `.env` var names (not the plan's placeholder `B2_KEY_ID`/`B2_APP_KEY`): `Backbaze-keyID`, `Backbaze-applicationKey`, plus `BUCKET-ID` (holds the B2 bucket ID, not name — unused; real bucket name `satilliate-images` is hardcoded in code/config instead) and `Backbaze-keyName` (unused, informational only). `.env` is gitignored — confirmed never committed. | **Resolved and working** |
| `configs/storage.yaml` (Part 0.4) | Real Lightning storage plan cap (`budget_gb`) | **Resolved (2026-10-10).** User set 150 GB max. |
| `configs/boundary.yaml` (Part 1.1) | GVMC boundary source: shapefile or official URL | **Resolved (2026-10-10).** Fetched fresh from OpenStreetMap Nominatim (relation 17493324) and written to `configs/boundary.yaml` + `data/boundaries/`. Cross-checked against the B2 file Part 2.1 found: exact match (IoU = 1.0), confirming that file's provenance was legitimate too. **User visually confirmed `results/phase1_boundary_check.png` on 2026-10-10** ("yes"). |
| DEM, WorldCover, OSM data (Phase 2 Part 2.4 / needed by Phase 4–5) | **Resolved (2026-10-10).** Fetched from verified public sources (Copernicus GLO-30 DEM, ESA WorldCover 10m 2021, OSM via Overpass/osmnx scoped to the buffered boundary) after the user approved a dry-run estimate (~86 MB). 9/9 files verified OK, uploaded to B2 under `vizag-geoai/data/raw/{dem,worldcover,osm}/`, local copies preserved in `data/raw_small/`. | **Resolved** |

## How to resolve these

Do not proceed past the part that needs a given value without it. When the user supplies a value, update
the "Confirmed value" / "Status" column here immediately, and log the event in
[`changelog.md`](changelog.md).
