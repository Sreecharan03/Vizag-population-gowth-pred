# Phase 5.3 — Threshold sensitivity and Phase 5 gate

Phase 5.3 was implemented and scientifically reviewed on 14 November 2026 under contract
`5.3.0-threshold-sensitivity-v1`. It reuses only the immutable Phase 5.2 delta and eligibility
evidence; it does not inspect model scores or alter exclusions.

## Results

| Transition | Eligible | 5% positives | 10% positives | 20% positives |
|---|---:|---:|---:|---:|
| 2018–2020 training | 4,558 | 1,397 (30.65%) | 884 (19.39%) | 361 (7.92%) |
| 2020–2022 training | 4,495 | 375 (8.34%) | 147 (3.27%) | 36 (0.80%) |
| 2022–2024 holdout | 4,504 | 1,365 (30.31%) | 746 (16.56%) | 223 (4.95%) |

Across 13,557 eligible cell-transition rows, 1,360 labels (10.03%) change between 5% and 10%,
and 1,157 labels (8.53%) change between 10% and 20%. Positive sets were validated as nested:
every 20% positive is also positive at 10%, and every 10% positive is also positive at 5%.

The 10% threshold remains the recommendation because it was predeclared in the project design,
avoids selecting the target from downstream model performance, is less vulnerable to small
classification fluctuations than 5%, and avoids the extreme 0.80% positive rate produced by 20%
for the 2020–2022 training transition. This does not guarantee higher model accuracy; class
imbalance must be handled and evaluated in later modeling phases.

## Immutable B2 outputs

- `vizag-geoai/v2/derived/labels/contract-5.3.0/threshold_sensitivity_labels.parquet`
  — 108,602 bytes, SHA-256 `d71ae5fd7070cf9b2cc3c751abf58675bb6c1cfa7bf09373494e48285650a515`
- `vizag-geoai/v2/results/phase5/contract-5.3.0/phase5_threshold_sensitivity.csv`
  — 974 bytes, SHA-256 `51fe47ab51075588affec5d71744e67b5a11f5baa0949ffa8b5a209717b95bba`
- `vizag-geoai/v2/results/phase5/contract-5.3.0/threshold_sensitivity_summary.json`
  — 1,047 bytes, SHA-256 `e66d9c0eff5eb27462260670848472e9d4a01c42485306312398bf224749da24`
- `vizag-geoai/v2/manifests/threshold_sensitivity_manifest.contract-5.3.0.json`
  — 1,749 bytes, SHA-256 `8153107ce33166ac5f5da7cee3951da8749f96ef428fec6f6e14221a08d4c5a5`

The build checked all destinations for absence twice and published the manifest last. The
independent review reopened the exact versions, recomputed hashes, compared the published CSV to
a fresh calculation, and performed zero writes.

## Verification and error history

- Initial regression run `ap-4XTJWZDT946kDrXQwZzBdJ` stopped before B2 access because a new
  synthetic fixture contained duplicate source keys. The production uniqueness validator correctly
  rejected it. The fixture was corrected to use distinct cells.
- Regression run `ap-2J5ERCTDVppwvUmPDsNZeV`: 436 passed with one known synthetic all-NaN warning.
- Production build `ap-Y8cNsxI8o2f51TyG9XGQUv`: four create-only writes.
- Scientific review `ap-CBozP1PAnpG76yC5AsHzt0`: passed with zero writes.

## Phase 5 gate decision

The user explicitly confirmed the 10-percentage-point primary threshold on 14 November 2026 after
reviewing the sensitivity results. Phase 5 is therefore complete and its gate is closed. Phase 6
must use the immutable 10% label without selecting or changing the target based on model scores.
