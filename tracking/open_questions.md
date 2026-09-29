# Open Questions / Assumptions Pending Confirmation

Values and assumptions that must come from the user — never guessed, per `plan.md` Section 0's rule that
credentials, bucket names, storage limits, and similar values must be stated explicitly and paused on.

## Storage assumptions (from `plan.md` Section 1A.2, to confirm at Part 2.1)

| ID | Assumption | Status | Confirmed value |
|---|---|---|---|
| A1 | The ~190 GB is already in a B2 bucket (not just a local/external drive) | **Unconfirmed** | — |
| A2 | B2 bucket exposes an S3-compatible endpoint; app key has ≥read scope | **Unconfirmed** | — |
| A3 | User-provided Lightning storage cap → `studio.budget_gb` | **Unconfirmed** | — |
| A4 | Stored Sentinel-2 format: unzipped `.SAFE` vs `.zip` | **Unconfirmed** | — |
| A5 | B2 egress/transaction pricing checked by user for their account | **Unconfirmed** | — |

## Other pending user inputs

| Needed for | What's needed | Status |
|---|---|---|
| `configs/b2.yaml` (Part 0.4) | B2 endpoint URL, bucket name, prefixes | Not provided |
| B2 credentials | `B2_KEY_ID` / `B2_APP_KEY` (or S3-style equivalents), via Studio secrets/env vars only | Not confirmed present — a `.env` file exists at repo root; confirm it's gitignored and never becomes the credential source read into configs/logs |
| `configs/storage.yaml` (Part 0.4) | Real Lightning storage plan cap (`budget_gb`) | Not provided |
| `configs/boundary.yaml` (Part 1.1) | GVMC boundary source: shapefile or official URL | Not provided |

## How to resolve these

Do not proceed past the part that needs a given value without it. When the user supplies a value, update
the "Confirmed value" / "Status" column here immediately, and log the event in
[`changelog.md`](changelog.md).
