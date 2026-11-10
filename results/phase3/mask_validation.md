# Phase 3.4 SCL Mask Validation

Validated read-only in Modal on 2026-11-05 against all 32 contract-3.3.2 SCL COGs.
The run read 24,659,693 compressed SCL bytes and wrote nothing to B2.

## Locked policy

- Valid SCL classes: 4 vegetation, 5 not-vegetated, 6 water, 7 unclassified.
- Invalid SCL classes: 0 nodata, 1 defective, 3 cloud shadow, 8/9 cloud,
  10 cirrus, 11 snow/ice.
- Class 2 dark/topographic shadow is invalid by conservative default and remains configurable.
- Classes 3, 8, 9, 10 and 11 receive circular dilation by 2 canonical 10 m pixels.
- Unknown SCL values are invalid. None occurred in the 32-scene validation.
- SCL validity is combined with reflectance validity and the AOI.
- Masks are generated in memory during compositing; no redundant mask rasters are written.

## Real-data results

| Epoch | Valid after policy | Class 2 excluded | Additional dilation loss |
|---|---:|---:|---:|
| 2018 | 98.0681% | 0.4404% | 0.1944% |
| 2020 | 96.4687% | 0.1066% | 0.4083% |
| 2022 | 85.0791% | 0.1787% | 0.2277% |
| 2024 | 71.4366% | 0.1576% | 0.1089% |

The maximum class-2 fraction in one scene was 0.9845%; the maximum additional
dilation loss was 1.4687%. These effects are small relative to the already-recorded
partial orbital coverage in selected 2022 and 2024 scenes. Part 3.5 must still
produce `valid_obs_count` and halt if combined spatial coverage is inadequate.

## Scientific limitation

Sentinel-2 SCL can label dark roofs as shadow and bright roofs as cloud. The
configurable policy makes that tradeoff explicit but cannot eliminate it. Later
QC figures must show masked urban areas before composites are accepted.
