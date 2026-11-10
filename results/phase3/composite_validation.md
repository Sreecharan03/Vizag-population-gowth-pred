# Phase 3.5 Composite Validation

**Completed:** 2026-11-06  
**Contract:** `3.5.0`  
**Execution:** Modal (`sankar132095`, environment `main`)  
**Persistent store:** Backblaze B2, bucket `satilliate-images`

## Approved policy

- Eight selected dry-season scenes per epoch.
- Six-band median composite: B02, B03, B04, B08, B11, B12.
- A pixel is emitted only with at least **4 valid observations**; otherwise its
  composite value is `-9999.0`.
- The observation-count raster preserves counts 0–8 inside the AOI and uses
  `255` outside it.
- Every epoch must retain at least **99%** of AOI pixels at the four-observation
  threshold.
- SCL validity follows the approved Part 3.4 policy, including a circular
  two-pixel dilation. Production processing uses a two-pixel chunk halo so
  dilation remains correct across chunk boundaries.

The four-observation threshold was selected after a read-only full-scene
preflight. It is the strongest common threshold retaining at least 99% AOI
coverage in every epoch; raising the threshold to five would reduce 2024
coverage to 45.8736%.

## Final coverage

| Epoch | AOI pixels | Pixels with ≥4 observations | Coverage | Median count |
|---:|---:|---:|---:|---:|
| 2018 | 15,353,996 | 15,303,223 | 99.6693% | 8 |
| 2020 | 15,353,996 | 15,340,292 | 99.9107% | 8 |
| 2022 | 15,353,996 | 15,323,080 | 99.7986% | 6 |
| 2024 | 15,353,996 | 15,257,709 | 99.3729% | 4 |

All four epochs passed the approved 99% gate.

## Published immutable outputs

All keys are under
`vizag-geoai/v2/processed/sentinel2/composites/contract-3.5.0/`.

| Epoch | Object | Bytes | SHA-256 |
|---:|---|---:|---|
| 2018 | `2018/composite.tif` | 369,765,288 | `995ea0d48d95f803b9e4f22694b16a6451e1f3b2605ada292765dd00a2a30d3f` |
| 2018 | `2018/valid_obs_count.tif` | 690,143 | `42b813402a33c3551f92d8d63b23779aac817621fdde0a8fa0b2979657c43d14` |
| 2020 | `2020/composite.tif` | 365,060,102 | `8c6113e09f59456292ba742d1a97bcfd3581524d8ac2502935d9fb9d3d331dc7` |
| 2020 | `2020/valid_obs_count.tif` | 667,922 | `de531c86f3efda0b072c3581c7a67bd3cbe15c90ff1b56555af49ed1943b92f9` |
| 2022 | `2022/composite.tif` | 366,699,998 | `f8a7db985126f1c4e0acf18f9d52e338b656c1b7e76ffdde6311d72cc89e5404` |
| 2022 | `2022/valid_obs_count.tif` | 530,604 | `c25a807d366875f449f3851214d1dc4b5fb9c17d1f5e46183f05f67ce9c3f72c` |
| 2024 | `2024/composite.tif` | 364,384,445 | `55fa556063dc14d8f3bd221e153d90bd302277fc9a59f5179a4dbf07ff8d9395` |
| 2024 | `2024/valid_obs_count.tif` | 423,047 | `834c035e462a3c1530030b6e3ccce263f80adad68b88233ecac47f354b7329f1` |

Total published and independently hashed: **1,468,221,549 bytes**.

## Independent audit gates

The post-publication audit was read-only and passed all gates:

- exactly one current/historical B2 version for every output;
- exact streamed SHA-256 equals the stored publication metadata;
- strict COG validation for all eight objects;
- expected CRS, transform, dimensions, datatypes, nodata and band order;
- contract, epoch, scene-count and coverage-threshold provenance tags;
- count values restricted to 0–8 inside the AOI;
- pixel-for-pixel agreement between count ≥4 and six-band composite validity;
- recomputed coverage remains above 99% for every epoch.

No object was overwritten or deleted during generation or audit.
