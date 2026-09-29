# Open Questions / Assumptions Pending Confirmation

Values and assumptions that must come from the user — never guessed, per `plan.md` Section 0's rule that
credentials, bucket names, storage limits, and similar values must be stated explicitly and paused on.

## Storage assumptions (from `plan.md` Section 1A.2, to confirm at Part 2.1)

| ID | Assumption | Status | Confirmed value |
|---|---|---|---|
| A1 | The ~190 GB is already in a B2 bucket (not just a local/external drive) | **Confirmed, and more** | Bucket `satilliate-images` contains not just raw data but existing `vizag-geoai/` processed outputs (boundaries, 2018 masked scene stacks) — see changelog 2026-09-29. Full inventory still needed (Phase 2 Part 2.1), not just this 10-key sample. |
| A2 | B2 bucket exposes an S3-compatible endpoint; app key has ≥read scope | **Confirmed** | Endpoint `https://s3.us-east-005.backblazeb2.com`, bucket `satilliate-images`. Read scope verified via `list_objects_v2`. Write scope not yet tested. Must use a genuine non-master Application Key (25-char keyID) — the master key's ID (=account ID, 12 chars) is rejected by the S3-compatible gateway even though valid for B2's native API. |
| A3 | User-provided Lightning storage cap → `studio.budget_gb` | **Still unconfirmed** | Needed to finish Part 0.4 / write `configs/storage.yaml`. |
| A4 | Stored Sentinel-2 format: unzipped `.SAFE` vs `.zip` | **Partially contradicted** | Sample keys aren't raw `.SAFE`/`.zip` at all — they're already-processed per-scene products (`..._refl.tif`, `..._scl.tif`, `..._qa.json`). Where the actual raw archive lives (same bucket, different prefix?) is still unknown — Phase 2 Part 2.1 must map this. |
| A5 | B2 egress/transaction pricing checked by user for their account | **Unconfirmed** | — |

## Other pending user inputs

| Needed for | What's needed | Status |
|---|---|---|
| `configs/b2.yaml` (Part 0.4) | B2 endpoint URL, bucket name, prefixes | Endpoint + bucket confirmed (see A2 above). Prefix taxonomy (raw vs processed vs backup) still needs Phase 2 Part 2.1's inventory. |
| B2 credentials | Actual `.env` var names (not the plan's placeholder `B2_KEY_ID`/`B2_APP_KEY`): `Backbaze-keyID`, `Backbaze-applicationKey`, plus `BUCKET-ID` (holds the B2 bucket ID, not name — unused; real bucket name `satilliate-images` is hardcoded in code/config instead) and `Backbaze-keyName` (unused, informational only). `.env` is gitignored — confirmed never committed. | **Resolved and working** |
| `configs/storage.yaml` (Part 0.4) | Real Lightning storage plan cap (`budget_gb`) | **Still needed — blocking Part 0.4 completion** |
| `configs/boundary.yaml` (Part 1.1) | GVMC boundary source: shapefile or official URL | Possibly already resolved — a `gvmc_boundary.geojson` already exists in B2 under `vizag-geoai/data/boundaries/`. Needs Phase 2 inventory + a trust/provenance check (was it built from a verified source? see `handoff.md`'s geodata rule) before reuse. |

## How to resolve these

Do not proceed past the part that needs a given value without it. When the user supplies a value, update
the "Confirmed value" / "Status" column here immediately, and log the event in
[`changelog.md`](changelog.md).
