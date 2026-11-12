# Phase 4.3 context-feature completion

Status: **complete** on 12 November 2026. Part 4.4 feature assembly is the next gate; no model has
been trained and no prediction accuracy is claimed.

## Authoritative sources

- WorldPop Global2 R2025A, 100 m, CC BY 4.0, DOI `10.5258/SOTON/WP00839`, for 2018, 2020,
  2022 and 2024.
- OpenStreetMap history through ohsome API v2.1.0 at `23:59:59Z` on 31 December of each epoch.
- Approved 6,371-cell, 500 m analysis grid from contract 4.1.0.

Legacy WorldPop rasters were rejected because their epoch pixels were identical. The live 2026
OSM extract was rejected for historical training. Neither rejected source enters the approved table.

## Output and validation

The final table contains 25,484 rows (`6,371 × 4`), unique on `(grid_id, epoch)`. It stores AOI
fraction, population total/density, road length/density, amenity count and nearest-amenity distance.
Validation requires exact epoch and grid coverage with no duplicate keys, missing values,
non-finite values or negative metrics.

Approved B2 artifacts:

- `vizag-geoai/v2/derived/features/contract-4.3.1/context_cell_features.parquet`
- `vizag-geoai/v2/results/phase4/context/contract-4.3.1/context_feature_summary.json`
- `vizag-geoai/v2/manifests/context_feature_manifest.contract-4.3.1.json`

All were exact-version read back and SHA-256 verified. Final production run:
`ap-jA33oh65sIRu9Q8hSSTujJ`. The preceding full suite passed 402 tests with the existing synthetic
all-NaN median warning.

## Scientific correction

The immutable 4.3.0 table used clipped AOI area for road-density normalization. Tiny boundary
slivers produced an unstable maximum near 159,679 km/km². It is preserved for audit but superseded.
Contract 4.3.1 uses the fixed 0.25 km² analysis-cell denominator and carries `aoi_fraction`; its
observed road-density range is 0–43.2143 km/km².
