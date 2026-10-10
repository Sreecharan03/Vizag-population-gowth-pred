# B2 Inventory Report (Phase 2, Part 2.1)

**Total objects:** 1474
**Total size:** 205.846 GB (expected ~225 GB per plan.md — within range)

## By source

- `boundary`: 2 object(s)
- `other`: 6 object(s)
- `sentinel2`: 1466 object(s)

## By tile

- `T44QPE`: 392 object(s)
- `T44QQE`: 344 object(s)
- `T44QQF`: 384 object(s)

## By source + format (size breakdown)

- `boundary/n/a`: 2 object(s), 0.00 GB
- `other/n/a`: 6 object(s), 3.44 GB
- `sentinel2/mosaic_derivative`: 346 object(s), 5.99 GB
- `sentinel2/processed_derivative`: 840 object(s), 13.59 GB
- `sentinel2/zip`: 280 object(s), 182.82 GB

## Duplicates (flagged only — nothing deleted)

_(none found)_

## Incomplete products (excluded from use unless re-fetched)

- `S2A_20180516T045701_R119` (missing:refl,scl)
- `S2B_20180401T045649_R119` (missing:refl,scl)
- `S2A_20200515T045701_R119` (missing:refl,scl)
- `S2B_20200311T045659_R119` (missing:refl,scl)
- `S2B_20200420T045649_R119` (missing:refl,scl)
- `S2B_20200430T045649_R119` (missing:refl,scl)
- `S2A_20220306T045701_R119` (missing:refl,scl)
- `S2B_20220120T050119_R119` (missing:refl,scl)
- `S2B_20220127T045039_R076` (missing:refl,scl)
- `S2A_20240514T045701_R119` (missing:refl,scl)

## Suspect size (zero-byte or < 100 bytes)

_(none found)_

## Unknown / junk (never marked for deletion)

_(none found)_

## Assumption check (plan.md A1–A5)

- **A1** (raw data already in B2): CONFIRMED — 280 raw `.SAFE.zip` archive(s) totaling 182.82 GB found under `data/raw/sentinel2/`, covering years ['2018', '2020', '2022', '2024'].
- **A4** (SAFE vs zip format): raw archives are stored as whole zipped `.SAFE.zip` files (not unzipped `.SAFE` folders, not bare `.zip`) — this decides the Phase 3 read strategy (ADR-001): either extract to staging first, or read directly from the zip via GDAL's /vsizip/.
