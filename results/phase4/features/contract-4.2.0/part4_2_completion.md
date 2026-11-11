# Part 4.2 completion record

Status: **complete; scientific gate approved on 11 November 2026**.

## Verified execution

- Corrected full batch: `ap-Dz1CfM1F43J7c3bAnkHkcH`.
- Exact input: 1,358,958,178 bytes across 24 hash-verified sources.
- Satellite table: 25,484 rows (6,371 cells x four epochs); terrain table: 6,371 rows.
- Six create-only B2 outputs: 3,308,109 bytes; every exact version was read back and hash verified.
- Completion manifest published last.
- Read-only final review: `ap-wKjNJgIpGetKO9w1nqLs01`; all six hashes and both table schemas revalidated; B2 writes: 0.

## Corrected error

The first full run (`ap-Zg1HmnbqJUBIEqChOBfVv9`) stopped before publication because independently
bilinear-reprojecting adjacent DEM tiles created an artificial overlap above the conservative seam
tolerance. No B2 output existed. The correction mosaics the exact adjacent tiles once in native
EPSG:4326 and performs one bilinear reprojection to the metric grid. A synthetic adjacent-tile test
was added before controlled resume. The failed reservation history was preserved.

## Scientific review and approved policy

The exact published support map was visually reviewed. Support is predominantly complete; reduced
support is localized and includes boundary fragments. Minimum five-index support has median 1.0,
fifth percentile 0.992 and first percentile 0.901864.

Downstream eligibility requires at least 0.50 usable fraction for every required index and epoch,
plus valid elevation and slope. All rows and QC fields remain preserved; downstream assembly must
flag ineligible rows rather than deleting evidence or filling missing values with zero. Source
rasters remain unclipped and holdout labels were not used to select this rule.

At 0.50, 6,355 of 6,371 cells are eligible across all epochs. Fifteen cells lack terrain and one
additional cell falls below 50% support. Tested alternatives retain 6,300 cells at 80%, 6,184 at
90%, and 6,034 at 95%; those additional losses are not justified by the observed distribution.

Part 4.2 creates features and QC evidence only. Population and OSM aggregation remain Part 4.3;
labels, training and predictions have not started.
