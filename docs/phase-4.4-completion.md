# Phase 4.4 feature-assembly record

## Production error and correction

The first production attempt (`ap-xu66Du13ROH4VFY7platYu`) stopped before its first B2 write.
The initial validator incorrectly treated all source-feature nulls as unexpected. Real Part 4.2
evidence intentionally preserves three satellite edge cells per epoch without a 10 m pixel centre
and 15 terrain cells without valid DEM support. This produced 12 null rows per index mean and 60
repeated terrain null rows across four epochs.

The correction does not impute or discard these rows. Source means may be null only when their
corresponding usable/valid support count is zero, and every such row must be model-ineligible.
Eligible rows containing any source-feature null still fail closed. Population-growth nulls remain
controlled separately by explicit availability and denominator-defined flags.

## Completed production run

The corrected Modal run `ap-oVzU63TWtILbwHolnRgNCk` completed on 2026-11-12. It read the exact pinned Part 4.2 and Part 4.3.1 object versions, assembled the feature table, validated it, and then created four new B2 objects. Every object was read back by its exact version and SHA-256 verified. The manifest was published last.

| Artifact | B2 key | Bytes | SHA-256 |
|---|---|---:|---|
| Assembled table | `vizag-geoai/v2/derived/features/contract-4.4.0/assembled_cell_epoch_features.parquet` | 3,825,959 | `426a7d21dbb1c33980f31dbf4c7a0d9e1d1d95aa16f5e67a27f72db427a2a9f5` |
| Feature summary | `vizag-geoai/v2/results/phase4/assembly/contract-4.4.0/feature_summary.json` | 808 | `078b34fe45cac1e2cb92027320a075345d49dbff11b954166b1db70af0388261` |
| Null report | `vizag-geoai/v2/results/phase4/assembly/contract-4.4.0/null_report.csv` | 2,646 | `2c61616b9f09e418317a5c184639c9c0e82970f76b7e726530f60bbb7f6740e5` |
| Manifest | `vizag-geoai/v2/manifests/feature_assembly_manifest.contract-4.4.0.json` | 3,150 | `ffc4005294979eb462286ab1716f7aa82d68681079329116fbece5d2cc2f4b5a` |

The final table has 25,484 unique cell-epoch rows, 69 columns, 6,371 unique cells, and exactly four epochs: 2018, 2020, 2022 and 2024. The approved Part 4.2 rule marks 6,355 cells eligible and 16 ineligible without dropping either group. Population growth is available only for the 19,113 rows with an immediately preceding epoch; 12,632 rows also have a non-zero prior-population denominator and therefore a defined growth fraction. The first epoch never receives a future-derived value.

Validation found no unexpected null columns. The expected support-explained nulls are 12 rows for each satellite index mean/diagnostic and 60 rows for each terrain mean. The full Modal regression suite passed 405 tests with one pre-existing synthetic all-NaN warning before the successful production run. The local immutable receipt is `results/phase4/assembly/contract-4.4.0/feature_assembly_receipt.json`.

## Phase 4 result

Parts 4.1 through 4.4 are technically complete. Phase 4 produced the validated 500 m grid, satellite/terrain features, historical population/accessibility context, and one versioned leakage-safe feature table. This document and the null report present the formal Phase 4 user-review gate; Phase 5 must not begin until that gate is accepted. Label construction and modeling belong to later phases, so Phase 4 does not claim a trained model or prediction accuracy.
