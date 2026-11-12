# Part 4.3a context-source preflight

Status: **preflight_complete_payload_and_temporal_gates_pending**.

- Modal Python: `3.12.10`
- Exact objects pinned: 8
- Known later payload: 36,612,590 bytes
- Payload bytes read: 0
- B2 writes: 0
- Aggregation started: no

## Exact current objects

- `vizag-geoai/data/raw/worldpop/clipped/2018/worldpop_2018.tif` — 741,928 bytes, version `4_z2250dbc1f968e033a7050713_f105b5f94828115f6_d20260928_m053159_c005_v0501048_t0044_u01790573519555`, SHA-256 metadata: absent
- `vizag-geoai/data/raw/worldpop/clipped/2020/worldpop_2020.tif` — 739,457 bytes, version `4_z2250dbc1f968e033a7050713_f105b5f9482811602_d20260928_m053159_c005_v0501048_t0027_u01790573519628`, SHA-256 metadata: absent
- `vizag-geoai/data/raw/worldpop/clipped/2022/worldpop_2022.tif` — 739,457 bytes, version `4_z2250dbc1f968e033a7050713_f105b5f948281160a_d20260928_m053159_c005_v0501048_t0020_u01790573519695`, SHA-256 metadata: absent
- `vizag-geoai/data/raw/worldpop/clipped/2024/worldpop_2024.tif` — 739,457 bytes, version `4_z2250dbc1f968e033a7050713_f105b5f948281160e_d20260928_m053159_c005_v0501048_t0027_u01790573519739`, SHA-256 metadata: absent
- `vizag-geoai/data/raw/osm/roads.gpkg` — 30,527,488 bytes, version `4_z2250dbc1f968e033a7050713_f20003e0a3b07d0e2_d20261010_m191638_c005_v0501043_t0007_u01791659798271`, SHA-256 metadata: absent
- `vizag-geoai/data/raw/osm/amenities.gpkg` — 307,200 bytes, version `4_z2250dbc1f968e033a7050713_f1119c10bd362886c_d20261010_m191638_c005_v0501051_t0005_u01791659798967`, SHA-256 metadata: absent
- `vizag-geoai/v2/manifests/analysis_grid_manifest.contract-4.1.0.json` — 1,591 bytes, version `4_z2250dbc1f968e033a7050713_f107668eb973be40c_d20261111_m115846_c005_v0501044_t0007_u01794398326723`, SHA-256 metadata: present
- `vizag-geoai/v2/derived/grid/contract-4.1.0/analysis_grid.geojson` — 2,816,012 bytes, version `4_z2250dbc1f968e033a7050713_f10475e8a42d77e32_d20261111_m115845_c005_v0501051_t0054_u01794398325165`, SHA-256 metadata: present

## Temporal gate

WorldPop years match the four feature epochs, but payload/schema/provenance validation is still required.
The OSM extract is dated 2026-10-10 and is later than every feature epoch.
It may be aggregated as explicitly dated context evidence, but it must not enter historical training rows
unless suitable historical OSM snapshots are obtained and validated. Part 4.4 must enforce this in code.
