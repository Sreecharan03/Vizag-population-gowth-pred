# Part 4.2 DEM integrity and schema validation

Status: **passed**.

- Version-pinned payload read: 46,382,829 bytes
- B2 writes: 0
- Feature aggregation started: no

## Verified tiles

### `Copernicus_DSM_COG_10_N17_00_E082_00_DEM.tif`

- SHA-256: `7959862a0f0dc6fb742d37dedd3dc47754a9dc32272dd3dae4c8d89b99095026`
- Version: `4_z2250dbc1f968e033a7050713_f20004cc62dd58dfb_d20261010_m191329_c005_v0501050_t0057_u01791659609592`
- Schema: 3600 × 3600, float32, EPSG:4326
- Elevation: -2.590 to 1584.418 m
- Valid/nodata pixels: 12,960,000 / 0

### `Copernicus_DSM_COG_10_N17_00_E083_00_DEM.tif`

- SHA-256: `fd8b5c09fc1f1d28deb78f287c830e1c0041ee7eabb813f8bc2b25456653fd29`
- Version: `4_z2250dbc1f968e033a7050713_f2002970276968e1d_d20261010_m191330_c005_v0501041_t0049_u01791659610769`
- Schema: 3600 × 3600, float32, EPSG:4326
- Elevation: -4.972 to 591.159 m
- Valid/nodata pixels: 12,960,000 / 0

Both sources are strict COGs with compatible one-degree GLO-30 schemas.
This validates the DEM inputs only; Part 4.2 feature aggregation remains separate.
