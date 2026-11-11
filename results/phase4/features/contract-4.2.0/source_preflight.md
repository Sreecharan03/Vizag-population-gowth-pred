# Part 4.2a source preflight

Status: **preflight_complete_dem_payload_hash_required**.

- Modal Python: `3.12.10`
- Small verified payload read: 52,147 bytes
- Raster payload/pixel reads: 0 bytes
- B2 writes: 0
- Index sources: 20 (1,309,726,569 bytes)
- DEM sources: 2 (46,382,829 bytes)
- Known aggregation input: 1,358,958,178 bytes

## DEM identities

- `vizag-geoai/data/raw/dem/Copernicus_DSM_COG_10_N17_00_E082_00_DEM.tif` — 37,750,448 bytes, version `4_z2250dbc1f968e033a7050713_f20004cc62dd58dfb_d20261010_m191329_c005_v0501050_t0057_u01791659609592`, payload SHA-256 metadata: absent
- `vizag-geoai/data/raw/dem/Copernicus_DSM_COG_10_N17_00_E083_00_DEM.tif` — 8,632,381 bytes, version `4_z2250dbc1f968e033a7050713_f2002970276968e1d_d20261010_m191330_c005_v0501041_t0049_u01791659610769`, payload SHA-256 metadata: absent

## Gate

The legacy Phase 2 DEM uploads do not carry SHA-256 object metadata.
A separately approved, version-pinned DEM payload read/hash and raster-header
validation is required before aggregation. Part 4.2b has not started.
