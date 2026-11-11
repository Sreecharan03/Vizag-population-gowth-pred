# Phase 4 — approved feature rule and prediction-quality plan

Date: 10 November 2026; status updated 11 November 2026.
**Phase 3 evidence and the specific downstream outlier rule are user-approved.**
Parts 4.1 and 4.2 are complete. Part 4.2's final exact-version review approved >=50%
usable support for every required index/epoch plus valid elevation and slope; all QC rows remain preserved.
No claim of prediction accuracy is made by closing the preprocessing gate.

## 1. Decision and immutable evidence

After inspecting the generated Phase 3 review evidence, the user approved the
specific rule: preserve all original rasters, exclude only already-flagged values
from each affected index's feature mean, retain counts/coverage, do not clip or
automatically discard entire grid squares, and keep an empty usable mean missing.

This decision supersedes the pending-approval status recorded in the immutable
published QC artifacts. Those artifacts and receipts are historical evidence and
must not be rewritten or republished. Their hashes remain valid. The approved
policy is recorded separately in `configs/feature_aggregation.yaml`.

The review found 11,378 unique outlier pixels in 2018, 12 in 2022 and none in
2020/2024. Negative ratio terms explain the excursions mathematically; strong
cancellation amplifies the largest 2018 cases. Individual physical source-scene
causes were not established. Approval does not make all retained reflectance
physically trustworthy or turn indices into ground-truth land-cover classes.

## 2. Exact downstream rule — no new arbitrary threshold

For index k, use the existing Part 3.6 nominal range [-1,1] and tolerance 1e-6.
A usable pixel is finite, not source nodata, and within [-1-1e-6, 1+1e-6].
Source nodata already includes the approved denominator guard and insufficient
composite observations; do not restore those pixels or replace missing values with zero.

For each cell, year and index:

```text
usable = original-valid AND NOT already-flagged-out-of-range
feature_mean = sum(index over usable pixels) / usable_pixel_count
if usable_pixel_count == 0: feature_mean = NaN
```

Only the affected index is excluded at that pixel. Do not drop other index values,
all pixels in a square, or whole squares solely because an outlier exists.
Do not clip an extreme to -1/+1; do not rewrite any original COG.
No broader negative-reflectance exclusion or new denominator threshold is approved.

The report must carry AOI candidate pixels, original-valid/nodata counts,
out-of-range exclusion count, usable count, usable/AOI fraction, exclusion/original-valid
fraction and filtered/unfiltered diagnostic means for every cell/index/year.
Pixel denominators and edge-cell handling must be explicit in Part 4.2; do not
make a partial boundary cell look data-poor by counting pixels outside the AOI.

Zero usable pixels means unknown, not no growth. Low-but-nonzero support also needs
review. A minimum usable-fraction threshold is **not invented here**: Part 4.2 must
first report support distributions and obtain approval. Model-ready export must
refuse unresolved support policy. No automatic imputation or silent row removal.

## 3. Accuracy safeguards, in implementation order

| Stage | Required evidence before proceeding |
|---|---|
| 4.1 grid | One fixed metric grid for every year; unique permanent IDs; no overlap/gaps; correct CRS, extent and boundary fractions |
| 4.2 satellite/terrain | Per-cell support/exclusions; filtered versus unfiltered mean sensitivity; missing-value report and spatial/epoch distribution checks; approved support policy |
| 4.3 population/infrastructure | Verify actual product dates, units, population-count versus density semantics and coverage; past-only population growth; no present-day OSM silently relabelled as historical |
| 4.4 joins | Exact row-count/ID agreement; no accidental duplicates/drops; explicit unknown/water/undevelopable flags; leakage assertions and feature summary gate |
| 5 labels | Built-fraction labels validated with time-appropriate independent evidence; 5/10/20 percentage-point sensitivity; do not treat raw NDBI as built-up ground truth |
| 6–8 evaluation | Prespecified training transitions and untouched 2022→2024 holdout; spatial-block evaluation; train-only preprocessing/tuning; class-imbalance baselines and uncertainty estimates |
| probabilities/scenarios | Check probability calibration and temporal/spatial performance; do not turn a two-year score into a validated 2030 six-year forecast without a justified, evaluated horizon method |

The configured training transitions remain 2018→2020 and 2020→2022; holdout remains
2022→2024. Do not choose exclusion/support rules by maximizing held-out label performance.
Inspect filtering's effect per cell, not just the small city-wide mean difference.
Report performance honestly; no plan or preprocessing pass guarantees correct predictions.

The public demo's fictional analytics are not training data, labels, performance
evidence or real forecasts. Infrastructure-pressure scores require separately
defined/validated accessibility assumptions; they are not measured infrastructure capacity.

## 4. Completed Part 4.1 contract

### Proposed grid contract

- Construct 500 m × 500 m full squares in EPSG:32644 over the approved buffered boundary.
- Proposed fixed metric anchor: (0,0) m in that CRS; IDs derive from integer
  easting/northing bin indices plus the CRS identifier, not row ordering or a year.
  The northing bin is not the source raster's top-down row number.
- Keep every square with positive-area AOI intersection, including edge squares.
  Retain full-square geometry plus within-AOI area/fraction; do not turn clipped
  boundary slivers into purported full 500 m squares or silently exclude water.
- Persist the web/interchange GeoJSON in EPSG:4326, while computing construction,
  area/overlap/coverage and IDs in metric EPSG:32644. Reprojection invariants are tested.
- This step produces geometry only: no features, label assignments, trained models,
  predictions, external downloads, OSM queries or classification decisions.
- Source imagery bbox bounds imply at most **12,862 candidate squares** for the
  proposed anchor. This is an upper bound, not the final intersecting cell count.

### Exact input

Restore the previously verified 32,768-byte buffered boundary into guarded Modal
scratch and hash it before grid work; no raster payloads are needed.

```text
Bucket: satilliate-images
Key: vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson
Version: 4_z2250dbc1f968e033a7050713_f114e6b26c000f3d2_d20260927_m183835_c005_v0501031_t0014_u01790534315534
Bytes: 32768
SHA-256: afe9ed8aad6f3f37d628f8ecb3b772bc4ae051d8251517d0cdea6ca8ded9df49
```

### Proposed new outputs and caps

```text
vizag-geoai/v2/derived/grid/contract-4.1.0/analysis_grid.geojson
vizag-geoai/v2/results/phase4/grid/contract-4.1.0/grid_validation.json
vizag-geoai/v2/results/phase4/grid/contract-4.1.0/grid_preview.png
vizag-geoai/v2/manifests/analysis_grid_manifest.contract-4.1.0.json
```

Per-file caps: GeoJSON 8 MiB; validation JSON 512 KiB; preview 3 MiB; manifest
256 KiB. Enforce 12 MiB maximum total new payload and 36 MiB maximum combined
stored/read-back/local-viewing payload. The actual final grid count and output
bytes cannot be claimed before construction. Preserve existing outputs; stop
if any proposed key has a current/historical version or delete marker.

### Workload, tests and stopping conditions

- Modal Python 3.12, profile `sankar132095`, environment `main`.
- Proposed one 1-CPU/2-GiB worker, no GPU, 600-second timeout; sequential publication.
- Planning runtime 3–10 minutes after implementation/testing, excluding builds/queueing.
  Planning compute allowance under US$0.05, not a billing guarantee; account terms apply.
- Unit/integration fixtures test stable IDs despite feature ordering, exact metric
  square sizes, valid geometry, edge fractions, full AOI coverage, non-overlap,
  CRS round-trip, unchanged source boundary, missing/empty inputs and idempotent
  refusal of current/historical destination collisions. Run full Modal regression.
- Use explicit source identity and bounded staging guards. No other writer to the
  new namespace. Hold persistent cooperative publication reservation; no SDK/function
  automatic retries; supported single PUTs and exact-version hash/byte read-back.
  Commit manifest last. No destructive cleanup or blind retry on ambiguous outcomes.
- Save new local review copies without overwrite; update tracking. User reviews the
  grid before approving Part 4.2. Stop/report any error immediately.

## 5. Approval boundary

Approval of Phase 3, its downstream rule and the exact Part 4.1 workload is recorded.
Part 4.1 completed on Modal on 11 November 2026: 6,371 cells, zero AOI gap/overlap,
and four new exact-version/hash-verified objects totaling 2,936,091 bytes. The user
approved the preview. The source boundary and all rasters remain unchanged. This
approval does not authorize Part 4.2, Git staging/commit/push or later Phase 4 parts.

The next-step workload and its approval boundary are defined in
[`phase-4.2-feature-aggregation-proposal.md`](phase-4.2-feature-aggregation-proposal.md).
The exact next unit is a metadata-only source/schema preflight; it performs no raster
pixel reads and no B2 writes.
