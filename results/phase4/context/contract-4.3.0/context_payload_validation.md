# Part 4.3b context payload validation

Status: **validated_with_scientific_blockers**.

- Exact payload read/hash: 33,794,987 bytes
- Sources hashed: 6
- B2 writes: 0
- Aggregation started: no

## WorldPop

- 2018: `7e9838b22fc3fc1f13e9b3e70a596473d9f7a2585f827e78328053655bd59011`; sum=2432559.496390; valid/nodata=144,415/245,697
- 2020: `81435b938bb469e53538bfc8c5145dc635cc122a443070b1c2f8a04b3f4a9b96`; sum=2489316.247611; valid/nodata=144,415/245,697
- 2022: `81435b938bb469e53538bfc8c5145dc635cc122a443070b1c2f8a04b3f4a9b96`; sum=2489316.247611; valid/nodata=144,415/245,697
- 2024: `81435b938bb469e53538bfc8c5145dc635cc122a443070b1c2f8a04b3f4a9b96`; sum=2489316.247611; valid/nodata=144,415/245,697

Pixel-unique epoch payloads: 2 of 4.
Duplicate pixel groups: `[[2020, 2022, 2024]]`.
Population-growth calculation allowed: **False**.

## OSM

- roads: 116,806 valid features, CRS `EPSG:4326`, SHA-256 `db59286c4b05bbfa26326258be346e6721a48f39c6e1ba90c3d73ba88556bb92`
- amenities: 627 valid features, CRS `EPSG:4326`, SHA-256 `4d3f26049af5647a33920cb82e1baed36e7b8fbbb99fff38c0ce708287019548`
  - Hospitals: 306; clinics: 76; education features: 245

## Scientific gate

The 2026 OSM snapshot is structurally usable as dated context evidence but is blocked from
2018-2024 historical training. Duplicate WorldPop epoch pixels, if listed above, block
population-growth calculation until provenance-correct epoch rasters are obtained.
