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
| `configs/b2.yaml` (Part 0.4) | B2 endpoint URL, bucket name, prefixes | Endpoint + bucket confirmed (see A2 above). Prefix taxonomy (raw vs processed vs backup) still needs Phase 2 Part 2.1's inventory. |
| B2 credentials | Actual `.env` var names (not the plan's placeholder `B2_KEY_ID`/`B2_APP_KEY`): `Backbaze-keyID`, `Backbaze-applicationKey`, plus `BUCKET-ID` (holds the B2 bucket ID, not name — unused; real bucket name `satilliate-images` is hardcoded in code/config instead) and `Backbaze-keyName` (unused, informational only). `.env` is gitignored — confirmed never committed. | **Resolved and working** |
| `configs/storage.yaml` (Part 0.4) | Real Lightning storage plan cap (`budget_gb`) | **Still needed — blocking Part 0.4 completion** |
| `configs/boundary.yaml` (Part 1.1) | GVMC boundary source: shapefile or official URL | Confirmed existing: `gvmc_boundary.geojson` + buffered version in B2 under `vizag-geoai/data/boundaries/` (full inventory, 2026-10-10). Still needs a trust/provenance check (was it built from a verified source? see `handoff.md`'s geodata rule) before reuse in Phase 1 Part 1.1 — provenance isn't recorded anywhere yet. |

## How to resolve these

Do not proceed past the part that needs a given value without it. When the user supplies a value, update
the "Confirmed value" / "Status" column here immediately, and log the event in
[`changelog.md`](changelog.md).
