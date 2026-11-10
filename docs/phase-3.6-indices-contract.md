# Phase 3.6 spectral-index contract

Updated: 10 November 2026. Contract `3.6.0`; inputs are the independently audited
`3.5.0` composites. User approved the production workload on this date. Production
completion is recorded separately in the validation report after all audits pass.

Production completed successfully on this date: see
[`results/phase3/indices_validation.md`](../results/phase3/indices_validation.md) and its adjacent
structured JSON evidence. The 20 COGs passed all byte/pixel audits. Scientific range-QC review
remains open before downstream use; do not silently clip or rerun the populated contract.

## Definitions and formulas

Corrected BOA reflectance band order is B02 (blue), B03 (green), B04 (red), B08
(near-infrared), B11 (shortwave-infrared 1), B12 (shortwave-infrared 2).

| Output | Formula |
|---|---|
| NDVI | `(B08 - B04) / (B08 + B04)` |
| NDBI | `(B11 - B08) / (B11 + B08)` |
| NDWI | `(B03 - B08) / (B03 + B08)` |
| MNDWI | `(B03 - B11) / (B03 + B11)` |
| BSI | `((B11 + B04) - (B08 + B02)) / ((B11 + B04) + (B08 + B02))` |

NDWI is the green/NIR open-water variant, not the NIR/SWIR moisture variant.
Indices are indicators, not built-up labels or proof of vegetation/water/buildings.

## Numerical rules implemented and tested

- Require corrected floating reflectance in the exact six-band order.
- Preserve the source composite's all-band validity: any nonfinite/nodata source
  band makes every index nodata at that pixel.
- Calculate in float64; persist float32 with `-9999.0` nodata.
- Guard `abs(denominator) <= 1e-6` in reflectance units, independently per index.
- A guarded denominator produces explicit nodata; it never substitutes zero or
  leaves a NaN/Inf in the persisted output.
- Nominal range is `[-1, 1]`, with `1e-6` reporting tolerance. Negative corrected
  reflectance can produce a finite value beyond that range. Preserve and count it;
  do not silently clip it or reject the underlying reflectance.
- Report source-valid/invalid, denominator-guarded, negative-denominator,
  nonfinite-result, output-valid/nodata and out-of-range counts plus extrema.
- Fail closed if a finite computed value collides with the reserved nodata value.
- Process 512-pixel blocks. Index formulas are pixelwise and need no spatial halo.

The contract and pinned input SHA-256 identities are in `configs/preprocessing.yaml`.
`src/preprocessing/indices.py` implements the numerical kernel. Tests in
`tests/unit/test_preprocessing_indices.py` and `test_preprocessing_index_products.py`
passed in the full **295-test Modal run**, with one existing composite warning.

## Implemented publication workflow

Produce 20 single-band COGs, five per epoch, with exact source grid, CRS, transform,
shape and full-resolution formula provenance. Publish a four-row JSONL manifest
containing source identity, per-index hashes, sizes and QC statistics only after
all epochs validate. Preserve full-resolution values; COG overview resampling
is `average`, documented in raster tags separately from analytical pixel values.

`src/preprocessing/index_products.py` implements blockwise writing and a second,
independently expressed full-resolution reference calculation. The Modal worker
downloads a version-pinned source and verifies its full SHA-256 before calculation.
It validates all five local COGs, publishes each once with SDK retries disabled,
then downloads exact output versions and checks hashes and every pixel again.

Per-epoch persistent Modal Dict reservations use atomic skip-if-exists. Successful
and failed states retain checkpoint evidence. Existing reservations halt a rerun;
they are not silently cleared. An abort record stops peer workers before subsequent
publication checks. An error can leave an additive partial batch, which must be
inspected; it is not deleted or blindly retried.

The original storage guard, the configured 20 GiB scratch budget and actual free
disk are checked before downloading. Conservative projection covers temporary
source TIFFs, COG copies/overviews and verification copies, with extra headroom.

Read-only preflight checks every page of current/historical object versions,
compares source hash metadata with the prior independent audit, and reports
collisions. Metadata comparison is not a new byte-stream hash pass. Production
must verify downloaded source bytes before calculation, validate outputs locally,
recheck destination absence immediately before writes, and independently verify
published bytes/pixels. A failed or ambiguous write stops; no blind overwrite or
retry. B2 absence-check plus PUT is not an atomic conditional write, so require
exclusive ownership of the destination namespace while publishing.

No raw archive is read. No existing output is rewritten. No deletion, staging,
Git commit or push is part of this processing approval.
