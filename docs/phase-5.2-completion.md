# Phase 5.2 — Binary growth-label completion

Phase 5.2 completed on 14 November 2026 under contract
`5.2.0-growth-transition-labels-v1`. The production build and independent read-only scientific
review ran on Modal. Part 5.3 must still test the configured 5%, 10% and 20% thresholds before the
10% candidate becomes the primary label.

## Method

For every grid cell and contracted transition:

`delta_built_fraction = built_fraction(t2) - built_fraction(t1)`

The candidate label is one when the delta is at least 0.10 and zero otherwise. Only the two
transition endpoints are used. Negative deltas remain label zero and carry a diagnostic flag.
Rows excluded before assignment retain a null label.

The three transitions are 2018–2020 and 2020–2022 for training, plus 2022–2024 as the temporal
holdout. Every transition preserves all 6,371 grid cells.

Exclusions are recorded independently rather than collapsed:

- missing endpoint or start-year water evidence;
- Phase 4.4 analysis-ineligible cell;
- start-year built fraction at least 90%;
- start-year Dynamic World modal water fraction at least 50%.

No pinned protected-area dataset exists in the current project contracts. The output therefore
records `protected_area_status=unavailable`; it does not invent a protected-area or physical
undevelopability classification.

## Validated results

| Transition | Eligible | Excluded | Positive | Negative | Negative-delta diagnostic |
|---|---:|---:|---:|---:|---:|
| 2018–2020 | 4,558 | 1,813 | 884 | 3,674 | 795 |
| 2020–2022 | 4,495 | 1,876 | 147 | 4,348 | 2,208 |
| 2022–2024 | 4,504 | 1,867 | 746 | 3,758 | 712 |

The table contains exactly 19,113 unique cell-transition rows and 6,371 unique cells. The marked
class imbalance, particularly in 2020–2022, is retained and reported rather than resampled during
label construction.

## Immutable B2 outputs

- `vizag-geoai/v2/derived/labels/contract-5.2.0/growth_transition_labels.parquet`
  — 189,600 bytes, SHA-256 `a86ba09786f15870085252d29f3c78d50334dba8f64617b5a95537222f115f45`
- `vizag-geoai/v2/results/phase5/contract-5.2.0/growth_transition_summary.json`
  — 1,089 bytes, SHA-256 `cad222d292ecb8a486c330345e2f321aff06d1509bab85e94617503c3598fe00`
- `vizag-geoai/v2/results/phase5/contract-5.2.0/exclusion_report.csv`
  — 504 bytes, SHA-256 `f0b3a4c549cb7cd756cd3d78bd1b21a0a2aa3e85ead1cab9579a7bb58426c243`
- `vizag-geoai/v2/manifests/growth_transition_manifest.contract-5.2.0.json`
  — 5,935 bytes, SHA-256 `d56ee92a88d220ed807ee417c393b2224c5f4f64bcc424fe28784a575975f632`

All destinations were checked for absence before processing and again immediately before
publication. The manifest was published last. The independent review reopened exact B2 versions,
recomputed payload hashes, validated table keys, deltas, exclusion/null behavior and labels, and
performed zero writes.

## Verification evidence

- Regression run `ap-Pnevrrx1MwnBVHUE1va9Rr`: 431 passed, one known synthetic all-NaN warning.
- Production build `ap-eAuC6334uvJpSeEkSuKx5T`: four create-only B2 writes.
- Scientific review `ap-4TEs5xAWlxbVzHQqyhHGe9`: passed, zero B2 writes.

The earlier build `ap-ol0vylFKcK9qsYzvSXvRil` stopped before publication because the Phase 4.4
manifest represents `outputs` as a list. The parser was corrected to locate the exact table key
and verify its hash and byte size; regression tests now cover both list and mapping representations.
