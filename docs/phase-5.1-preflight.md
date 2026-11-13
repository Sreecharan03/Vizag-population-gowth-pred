# Phase 5.1 built-up classification preflight

## Status

The read-only Modal run `ap-dU3AeibKf2cToxvrFA9dBU` passed on 2026-11-12.
It used only B2 object-version listing and HEAD metadata calls: zero raster pixel
reads and zero B2 writes. The full Modal regression run
`ap-oqmKvJAVCorm8fqNQBdAMY` passed 407 tests with one pre-existing synthetic
all-NaN warning.

## Pinned inputs

- 20 approved contract-3.6.0 index COGs: five indices for each of 2018, 2020,
  2022 and 2024, totaling 1,309,726,569 bytes.
- ESA WorldCover 2021 v200 tile:
  `vizag-geoai/data/raw/worldcover/ESA_WorldCover_10m_2021_v200_N15E081_Map.tif`
  (39,539,634 bytes), version
  `4_z2250dbc1f968e033a7050713_f2002970276968e28_d20261010_m191332_c005_v0501046_t0011_u01791659612896`.

The legacy WorldCover object has no SHA-256 metadata. Its multipart ETag is not
treated as a payload hash. The next pilot must read and hash that exact version
before it can be used as reference evidence.

## Scientific interpretation

WorldCover provides one 2021 reference, not separate 2020 and 2022 ground-truth
labels. It may cross-check the bracketing Sentinel-2 classifications for 2020 and
2022, with the one-year temporal offset disclosed. It must not be copied into all
epochs or presented as two independently dated references.

Built fraction cannot be derived from the Phase 4 cell-level mean NDBI. Part 5.1
must classify valid 10 m pixels using an explicit multi-index decision and then
compute built-pixel fraction within each 500 m cell. Raw NDBI alone is prohibited.

## Next gate

Run a bounded Modal raster-header and pixel pilot before production classification.
It must verify exact versions and hashes, grid/CRS/nodata compatibility, WorldCover
class semantics, and compare documented candidate multi-index rules against
WorldCover class 50 for spatially stratified samples from both 2020 and 2022.
Report confusion matrices, precision, recall, F1, balanced accuracy, coverage and
2020-versus-2022 stability. The pilot creates no production classification outputs.

## Full-pixel pilot result — scientific gate failed

Modal run `ap-RPrppXevOdvK4JnsyhgOpE` read and hash-verified 431,376,252 bytes,
including the exact WorldCover version and the required 2020/2022 index COGs. The
WorldCover SHA-256 is
`c8688cf916236e6df08aa076ac813bd3562a122b8feae92c92de6b78989e24e6`.
All 30 configured multi-index rules were evaluated over approximately 15.3 million
valid overlapping pixels in each bracketing epoch. B2 writes remained zero.

The objectively selected rule was `NDBI > -0.05`, `NDVI < 0.40`, `MNDWI < 0`, and
`NDBI > NDVI`. Its results were insufficient for label production:

| Metric | 2020 | 2022 |
|---|---:|---:|
| Balanced accuracy | 0.5643 | 0.5670 |
| F1 | 0.2266 | 0.2342 |
| Precision | 0.4815 | 0.5105 |
| Recall | 0.1482 | 0.1520 |
| Predicted built fraction | 0.0338 | 0.0326 |
| WorldCover built fraction | 0.1098 | 0.1096 |

The rule misses about 85% of WorldCover built pixels. Its low predicted fraction is
stable across the two epochs, but stability does not make the large systematic
under-detection acceptable. Part 5.1 therefore remains blocked at its scientific
method gate. No classification raster, cell built-fraction table or manifest was
published, and Parts 5.2/5.3 were not started.

## Dynamic World replacement design

Primary-source review selected Google Dynamic World V1 as the single primary,
time-aware label source. It is not fused with WorldCover, GHSL or an index classifier.
Each epoch uses all eligible `T44QQE` observations from 1 January through 31 March.
Assets sharing one sensing token are reduced before temporal composition so a duplicated
acquisition cannot receive extra weight. Outputs retain built-probability median, temporal
standard deviation, valid-observation count and label mode. Probabilities are model
confidence values, not physical subpixel impervious fractions.

Earth Engine metadata planning found 23, 33, 32 and 30 tile assets for 2018, 2020,
2022 and 2024 respectively (118 total). The planning audit found complete AOI coverage
and per-location minima of 5-6 observations. Forced one-to-one matching against the 32
selected Phase 3 scenes was rejected because Dynamic World legitimately omits some
Sentinel-2 acquisitions; arbitrary substitution would be scientifically incorrect.

## Authentication and least privilege

Modal uses service account `vizag-modal-ee@vizag-geoai-ee-20261112.iam.gserviceaccount.com`.
The Viewer role supports metadata computations but not download creation. The first pilot
stopped with `earthengine.thumbnails.create` denied and zero B2 writes. Project custom role
`vizagEarthEngineThumbnailCreator` adds only that permission; the broader Writer role was
deliberately not granted. A 64x64 probe then verified 4,096 valid pixels, zero exports and
zero B2 access.

## Published 2022 pilot

Modal run `ap-wLyycPqfUrxigh2z2o9EyH` published the create-only contract-5.1.0 pilot:

| Object | Bytes | SHA-256 |
|---|---:|---|
| `dynamic_world_2022_built_statistics.tif` | 250,336,151 | `15bd85f65c76f190b6fa7dccf8beb65bb70d8671a17365f800307af6e8f4d4e9` |
| `dynamic_world_2022_valid_count.tif` | 1,075,185 | `b6c821dcd1e4ea83912cb90a62e6b595e0b84080c4e55bcc7f56371730ff7e6b` |
| `dynamic_world_2022_label_mode.tif` | 2,540,656 | `f4008ffdc8d62550571ce13815bb423e1d667228d68725c4dda21aa205d1ee8b` |
| `dynamic_world_2022_pilot_manifest.json` | 3,235 | `7453940c80b47608b77b218b63882094b87655c74c28bdc02ae951f28c7baeaa` |

All raster outputs are strict COGs on the approved 5,866 x 5,417 EPSG:32644 grid and
passed remote B2 reopen. Coverage is 100%; valid count is 5-32, built median is
0.01657-0.77745 and temporal standard deviation is 0.00023-0.30727.

One pre-publication run found a QC implementation error: a 2D validity mask was applied
to the band axis of a `(2, height, width)` array. Publication follows QC, so it wrote
nothing. The fix is isolated in `built_statistics_qc`, rejects partial nodata and has two
regression tests. The full Modal suite is 414 passed with one known synthetic all-NaN warning.

## Scientific review and current gate

Read-only Modal run `ap-5U2xu4joBNHGe8oBrYRHrH` measured 11.859% mode-built pixels.
Mode-built probability quantiles are 0.261 (P05), 0.594 (median) and 0.732 (P95).
WorldCover 2021 is an audit with a disclosed one-year temporal/product-semantics caveat,
not training truth: balanced accuracy 0.916, recall 0.902, precision 0.451 and F1 0.602.
High recall but modest precision means the additional detections must be inspected spatially.

The next gate is a deterministic stratified review of agreement/disagreement, confidence,
uncertainty, coast, port/industrial, hillside and dense-urban samples using the project's
own dated Sentinel-2 evidence. Do not run the 2018/2020/2024 batch until that review is
approved. Cell built fractions and Parts 5.2/5.3 have not started.
