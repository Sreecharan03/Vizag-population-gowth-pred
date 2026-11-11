# Phase 4.1 grid review

Part 4.1 completed on Modal Python 3.12.10 and was visually approved on
11 November 2026.

- Fixed grid: 500 m × 500 m full squares in EPSG:32644, anchored at (0,0).
- Interchange file: GeoJSON in EPSG:4326.
- Retained cells: 6,371 (5,912 full cells; 459 positive-intersection edge cells).
- Buffered AOI area: 1,535,397,424.6073387 m².
- Validation: zero missing AOI area, zero overlap, intersection-area error
  0.0000007152557373046875 m², maximum CRS round-trip displacement
  0.0000000022088254290877697 m.
- Output payload: 2,936,091 new bytes; all four B2 objects were created once and
  exact-version/read-back/SHA-256 verified.
- Full Modal regression: 367 passed, one existing synthetic all-NaN median warning.

Review [the grid preview](grid_preview.png) and [machine-readable validation](grid_validation.json).
The colour encodes the fraction of each complete square that intersects the buffered study area;
it is not a growth probability or prediction. Water and boundary cells remain in the grid.

Modal runs:

- Tests: `ap-tRht1LG4QIJXGAMj0NfLtI`
- Production: `ap-0XT8PeoGerm8Mu7VlDv49j`

Part 4.2 feature aggregation has not started and requires separate workload approval.
