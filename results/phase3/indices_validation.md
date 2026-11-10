# Phase 3.6 spectral indices — production validation

Completed: **10 November 2026**. Contract `3.6.0`.

## Outcome

All **20 single-band index COGs** were created once, downloaded again from their exact
published versions, independently byte-hashed, and audited at full resolution against
separately expressed formulas. All 20 passed strict COG, grid/schema, provenance,
nodata/denominator-mask and formula checks. No existing composite or other B2 object
was overwritten or deleted. This is computational/provenance validation, not a claim
of land-cover classification accuracy or prediction performance.

The user explicitly approved the proposed workload before execution. Part 3.5 stayed
unchanged. No raw satellite archive was downloaded. No Git staging, commit or push was run.

## Execution evidence

- Production run: https://modal.com/apps/sankar132095/main/ap-dI7A4YpZCjqreUvxOudKke
- Full regression: https://modal.com/apps/sankar132095/main/ap-i4sswEjQfFFK9ovkI1aEG7
- Regression result: **295 passed, one existing synthetic all-NaN composite warning, 7.18 s**.
- Four epoch tasks, at most two simultaneous workers; each requested 2 CPU cores and 4 GiB RAM.
- Input composites: **1,465,909,833 bytes**; actual SHA-256 verified before processing.
- Published raster payload: **1,309,726,569 bytes** (approximately 1.22 GiB).
- Auditing downloaded the same raster payload again. Scientific pixel calculations
  ran only in Modal, using bounded 512-pixel blocks and guarded scratch usage.
- The pre-run time/cost figures were estimates. Actual charges are not measured here;
  consult the Modal/account usage record rather than treating the estimate as a bill.

| Epoch | Five COGs, total bytes | Raster audits | Source byte hash |
|---|---:|---|---|
| 2018 | 328,001,361 | 5/5 | Passed |
| 2020 | 326,554,452 | 5/5 | Passed |
| 2022 | 328,099,870 | 5/5 | Passed |
| 2024 | 327,070,886 | 5/5 | Passed |

## Manifest

- Key: `vizag-geoai/v2/manifests/indices_manifest.contract-3.6.0.jsonl`
- Size: **17,788 bytes**, four rows.
- SHA-256: `4fb908c22737c7fc8de60f6ac4a36a5522d3d1e538b1bc330e8b4bb951dd0fcb`
- Version ID: `4_z2250dbc1f968e033a7050713_f106f523b12a40a6e_d20261110_m043035_c005_v0501017_t0048_u01794285035687`
- Created after all four successful full-resolution output audits; read-back compared
  byte-for-byte; exactly one historical/current manifest version confirmed.

All raster keys use
`vizag-geoai/v2/processed/sentinel2/indices/contract-3.6.0/<epoch>/<index>.tif`.
The structured audit record, including all source/output versions, hashes and QC
counts, is [indices_validation.json](indices_validation.json). That local JSON is
an evidence summary, not a byte-identical copy of the B2 JSONL manifest.

## QC finding requiring scientific review before downstream aggregation/modeling

The contract preserves negative corrected reflectance and finite out-of-range index
values; it never silently clips them. **2018 contains rare but large range outliers**,
particularly when positive/negative bands nearly cancel in the denominator. The
largest per-index outlier fraction is below 0.074% of valid pixels, but extremes
such as NDBI -3806.94 to 2208.96 could distort ordinary feature means. **2022 has
12 slight outliers in each of NDVI, NDBI and NDWI.** The affected sets can overlap;
these per-index counts must not be added and described as unique pixels.

2020 and 2024 have no nominal-range outliers. In 2018, 17 NDVI denominators at or
below the absolute `1e-6` guard were assigned explicit nodata. No NaN/Inf persisted.
Larger finite excursions were retained, counted and verified as mathematically
consistent with the source data. They are QC flags, not silently corrected values.

Do not interpret these extrema as physically meaningful vegetation/built-up scores.
A later approved review must examine their spatial/source context and establish a
scientifically justified aggregation/eligibility policy before grid features/models
consume them. No clipping, new threshold, scene exclusion or data rewrite has been
performed in response to this finding.

| Epoch | Index | Valid pixels | Guarded denominators | Outside nominal range | Fraction of valid pixels | Minimum | Maximum |
|---|---|---:|---:|---:|---:|---:|---:|
| 2018 | NDVI | 15,303,206 | 17 | 11,300 | 0.073841% | -379.000641 | 341.000610 |
| 2018 | NDBI | 15,303,223 | 0 | 11,075 | 0.072370% | -3806.935547 | 2208.962646 |
| 2018 | NDWI | 15,303,223 | 0 | 11,079 | 0.072397% | -30.230734 | 25.941164 |
| 2018 | MNDWI | 15,303,223 | 0 | 4 | 0.000026% | -1.113512 | 0.887664 |
| 2018 | BSI | 15,303,223 | 0 | 1,974 | 0.012899% | -2.444227 | 17.627453 |
| 2020 | NDVI | 15,340,292 | 0 | 0 | 0.000000% | -0.828037 | 0.891545 |
| 2020 | NDBI | 15,340,292 | 0 | 0 | 0.000000% | -0.838952 | 0.711303 |
| 2020 | NDWI | 15,340,292 | 0 | 0 | 0.000000% | -0.834327 | 0.895455 |
| 2020 | MNDWI | 15,340,292 | 0 | 0 | 0.000000% | -0.827505 | 0.878724 |
| 2020 | BSI | 15,340,292 | 0 | 0 | 0.000000% | -0.556742 | 0.577441 |
| 2022 | NDVI | 15,323,080 | 0 | 12 | 0.000078% | -1.016064 | 0.898067 |
| 2022 | NDBI | 15,323,080 | 0 | 12 | 0.000078% | -0.880447 | 1.096786 |
| 2022 | NDWI | 15,323,080 | 0 | 12 | 0.000078% | -0.856627 | 1.009112 |
| 2022 | MNDWI | 15,323,080 | 0 | 0 | 0.000000% | -0.803426 | 0.853982 |
| 2022 | BSI | 15,323,080 | 0 | 0 | 0.000000% | -0.581626 | 0.584503 |
| 2024 | NDVI | 15,257,709 | 0 | 0 | 0.000000% | -0.698061 | 0.894135 |
| 2024 | NDBI | 15,257,709 | 0 | 0 | 0.000000% | -0.855951 | 0.821720 |
| 2024 | NDWI | 15,257,709 | 0 | 0 | 0.000000% | -0.810143 | 0.789880 |
| 2024 | MNDWI | 15,257,709 | 0 | 0 | 0.000000% | -0.851246 | 0.845375 |
| 2024 | BSI | 15,257,709 | 0 | 0 | 0.000000% | -0.599130 | 0.704923 |

## Raster identities

| Relative output | Bytes | SHA-256 |
|---|---:|---|
| 2018/ndvi.tif | 66,118,226 | `cb5a55bc354de9329759923080eb4b44b0968d1de5dc897da05b8c14ffaa093a` |
| 2018/ndbi.tif | 68,446,385 | `818d1c3cf6b6a67a97dfc39ce781b647e620abdc903face7b7ca43cb62bddc94` |
| 2018/ndwi.tif | 63,611,030 | `9373bc5174c9077d5def1e9c610efabe03b77be812a6d1e0ba80721bdd0a2c64` |
| 2018/mndwi.tif | 62,805,656 | `09d6a4afe4f2864b5a4bfbafa6919892822cefb4440bcb1fe80924aa8bbca196` |
| 2018/bsi.tif | 67,020,064 | `2d0631cd1571cdf1900121a13be80bd8057a8b4025d56aed67522c98b84a19a4` |
| 2020/ndvi.tif | 64,708,200 | `6831d54b136f03edd3a0180381fc13b53474d5c28584256cb784ef37872a18b3` |
| 2020/ndbi.tif | 68,212,309 | `1a9eb4e7e3ec51db9a4a8f1524e2ac0ed9f01c1337896f754c2fe0c227223995` |
| 2020/ndwi.tif | 63,465,865 | `7b6815de3d323cbf86ac8abee8f7f5b49288e331d648b1ea0d298856404c6852` |
| 2020/mndwi.tif | 62,343,334 | `ff01e7da0b1b8bbd81cbb64cd2107f96cfdeaa3d093709df49e2d6ebd1074d39` |
| 2020/bsi.tif | 67,824,744 | `c8f17670b21e8f3779127f9e7f0e5548858cdf6b0ee90449b2f8d40e9505d549` |
| 2022/ndvi.tif | 65,201,594 | `461bdc70d7d23a73437139e7560dbbafdcf2ad1ab01875c33a68c14b47a4bd2e` |
| 2022/ndbi.tif | 68,321,428 | `b3f7e6acbd160a6ba761405c3e8c87e71c67e170d14090a2c6c9d89f8b8e9aaa` |
| 2022/ndwi.tif | 63,491,012 | `2bd2f2ccb847bdd05e7b532cb019fe118f8b696b0ebfd4bb362bfd483c29b0bb` |
| 2022/mndwi.tif | 63,049,753 | `b68fe5ee19e0755fc62c2638c469cd0e02bb20e0b8ff5cbccbee74764320f15f` |
| 2022/bsi.tif | 68,036,083 | `7a0692317871c738f41b207cd7997063cff6f91e247339099e6d156481370748` |
| 2024/ndvi.tif | 65,200,844 | `b167b67822fe4eac9a1e79fc0ee56eafdf4cdeb41fdc9d4e96ef8608859d954f` |
| 2024/ndbi.tif | 68,146,232 | `6b21b29985f7e7c6d34c945a99c2b0f3271b907d7a84cf08e09ddf24b458c979` |
| 2024/ndwi.tif | 63,326,793 | `010524a6f7ee6e828581d7559e24193e62465c5f22e507b2a8ef967d41d83e2a` |
| 2024/mndwi.tif | 62,688,669 | `fb3da2d3b3393244c8f1d6fb56b6a71363d8b15fe8ce8f3cd0c82fe8eece0063` |
| 2024/bsi.tif | 67,708,348 | `e1af85d7ce170e258fa6863e1865d59e28fb1996cd5db2ed430fbaa0ca79b5b9` |

## Publication protections and remaining work

All destination version histories were checked before the batch and again before
publication. Atomic per-epoch Modal Dict reservations prevent duplicate workers in
this workflow; B2 check-then-PUT itself is not atomic against an independent external
writer. SDK request retries were disabled for publication. Persistent success records
retain recovery evidence; the build refuses reruns against existing destinations or
reservations. Do not rerun `part3-indices-build` on contract 3.6.0.

**Part 3.6 implementation and production validation are complete; scientific range-QC
review remains open before downstream use.** Phase 3 is 7/8 parts complete. Part 3.7
archive/storage reporting is next and needs its own proposal/approval; no eviction,
additional backup writes, grid building or model training has started.

