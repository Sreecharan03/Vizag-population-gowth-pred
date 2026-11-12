# Official WorldPop replacement probe

Status: **official_api_probe_rejected_download_not_started**.

- Dataset: WorldPop Global2 R2025A
- Resolution: 100 m
- Boundary request hash: `6c5226c1bbf857ec0c1d4091a5c594d5332419d96c606cf3eaaf9f576793c7cc`
- Raster payloads downloaded: 0
- B2 writes: 0
- Planned create-only prefix: `vizag-geoai/v2/raw/worldpop/global2-r2025a`

## Year descriptions


## API rejection

- Year: 2018
- HTTP status: 422
- Request ID: `ee777deb-b8b8-4523-ad31-ac31ab0640d0`
- Response: `{"details": {"value": 765261.8352807416}, "error": "invalid_geometry", "message": "Longitudes must be between -180 and 180 (got 765261.8353). Split shapes that cross longitude 180 into a MultiPolygon.", "request_id": "ee777deb-b8b8-4523-ad31-ac31ab0640d0", "timestamp": 1794466234.04077}`
- Boundary summary: `{"feature_count": 1, "type": "FeatureCollection"}`

All four years will be downloaded from one release before any population growth is calculated.
