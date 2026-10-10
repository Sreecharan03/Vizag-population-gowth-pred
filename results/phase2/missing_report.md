# Missing Data Report (Phase 2, Part 2.2)

## Sentinel-2 tile/epoch coverage

- `T44QQE` / 2018: 19 scene(s) — OK
- `T44QQE` / 2020: 22 scene(s) — OK
- `T44QQE` / 2022: 21 scene(s) — OK
- `T44QQE` / 2024: 24 scene(s) — OK

## Sentinel-2 — missing (tile, epoch) pairs

_(none — every required tile/epoch combination has at least one raw scene already in B2)_

## Tiles present in B2 but not strictly required

- T44QPE, T44QQF — present and usable, but outside the current buffered boundary's strict MGRS intersection. Not wasted; would become required if the buffer distance in configs/boundary.yaml is increased.

## Small datasets (WorldPop, DEM, WorldCover, OSM)

- `worldpop`: years present [2018, 2020, 2022, 2024], missing none — OK
- `dem`: MISSING
- `worldcover`: MISSING
- `osm`: MISSING

## Cost estimate

B2 egress/transaction pricing for this account is still unconfirmed (plan.md Assumption A5) — any fetch of the missing items above should get an explicit byte/request estimate and user approval before running, per plan.md Section 0's data-safety rules. Nothing is fetched by this report.
