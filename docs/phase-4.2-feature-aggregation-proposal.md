# Part 4.2 — feature aggregation proposal

Prepared: 11 November 2026. Final status: **Part 4.2 complete; full batch, publication,
exact-version review and support-policy gate passed**.

## Purpose

Aggregate the five approved Sentinel-2 indices for each year onto the 6,371 fixed
500 m cells, then add static elevation and slope features. Preserve missing values,
record support/exclusion counts, and prevent a table from being labelled model-ready
until the minimum usable-support rule is reviewed and approved.

Part 4.2 does not create labels, train a model, use the public demo, query OSM, or
produce predictions. Population and infrastructure features remain Part 4.3.

## Why the work is split into two guarded units

The 20 index COGs have byte count, SHA-256 and version pins. Part 4.2a initially found
that the two Copernicus GLO-30 DEM objects lacked SHA-256 object metadata. A later
approved, version-pinned payload gate established their hashes and real half-pixel-
aligned bounds. The strict DEM gate and a one-index real-data aggregation pilot have
now passed; their evidence is recorded below.

No support threshold will be invented before seeing real per-cell distributions.

## Part 4.2a — exact next step: source and schema preflight

### Modal workload

- Modal Python 3.12 only; profile `sankar132095`, environment `main`.
- One worker: 0.5 CPU, 1 GiB memory, no GPU, 300-second timeout, retries disabled.
- Run the full Modal regression suite first.
- Read only small manifests plus object/version metadata; **no raster payload or pixel reads**.

### Inputs

- Exact Part 4.1 grid manifest: 1,591 bytes.
- Exact Part 3.6 index manifest: 17,788 bytes.
- Pinned buffered boundary: 32,768 bytes.
- List/head/version metadata for the 20 index COGs and the two DEM objects under
  `vizag-geoai/data/raw/dem/`.
- Expected DEM filenames and Phase 2 byte counts:
  - `Copernicus_DSM_COG_10_N17_00_E082_00_DEM.tif`: 37,750,448 bytes.
  - `Copernicus_DSM_COG_10_N17_00_E083_00_DEM.tif`: 8,632,381 bytes.

Maximum payload read: **65,536 bytes**. Object metadata requests are not counted as
payload bytes. Stop if a source has multiple versions, a delete marker, a byte-count
mismatch, absent SHA metadata requiring a later payload hash, an unexpected CRS/
nodata/schema, or a changed grid/index identity.

### Proposed preflight outputs

Local review files only; no B2 write in 4.2a:

```text
results/phase4/features/contract-4.2.0/source_preflight.json
results/phase4/features/contract-4.2.0/source_preflight.md
```

Maximum combined local output: 256 KiB, create-only. Report the exact pinned sources,
total input bytes for aggregation, raster schemas, required reprojection/resampling,
estimated block reads and refined runtime/cost. No source or existing output changes.

Estimated runtime after implementation/testing: 1–3 minutes, excluding image build/
queueing. Planning compute allowance: under US$0.02, not a billing guarantee.

## Part 4.2b — provisional aggregation, separately approved after 4.2a

This is a bounded design, not current authorization.

### Known source scale

- 20 version-pinned index COGs: 1,309,726,569 compressed bytes.
- Two expected DEM files: 46,382,829 compressed bytes.
- Grid GeoJSON: 2,816,012 bytes.
- Boundary: 32,768 bytes.
- Known total before small manifests: **1,358,958,178 bytes** (~1.266 GiB).

The 4.2a report must replace this planning total with exact current identities and a
hard transfer cap before 4.2b approval.

### Aggregation contract

- Process raster blocks/chunks once; never issue one remote request per cell.
- Use fixed grid IDs from contract 4.1.0 for every epoch.
- Define candidate pixels as raster pixel centres inside the buffered AOI and cell;
  report edge-cell denominators explicitly.
- For each cell/year/index, carry AOI candidates, source-valid/nodata, already-flagged
  out-of-range exclusions, usable count, usable/AOI fraction, exclusion/source-valid
  fraction, raw diagnostic mean and approved filtered mean.
- Usable index values are finite, not nodata and inside `[-1-1e-6, 1+1e-6]`.
  Exclude only the affected index value. Never clip values, rewrite COGs, replace
  missing with zero or drop whole cells automatically.
- Mosaic the two Copernicus DEM tiles in their verified source grid, reproject with
  continuous-data bilinear resampling to the analysis CRS, derive slope in metric
  coordinates with documented units, and aggregate elevation/slope once per cell.
- Produce provisional features and support diagnostics, **not a model-ready table**.
  Export must carry `support_policy_status=pending_user_approval`.
- Report filtered-versus-unfiltered sensitivity by epoch, index and spatial cell.
  Do not use labels or the future holdout to choose a support threshold.

### Proposed create-only B2 outputs

```text
vizag-geoai/v2/derived/features/contract-4.2.0/satellite_cell_features.parquet
vizag-geoai/v2/derived/features/contract-4.2.0/terrain_cell_features.parquet
vizag-geoai/v2/results/phase4/features/contract-4.2.0/support_summary.json
vizag-geoai/v2/results/phase4/features/contract-4.2.0/support_summary.csv
vizag-geoai/v2/results/phase4/features/contract-4.2.0/support_maps.png
vizag-geoai/v2/manifests/feature_aggregation_manifest.contract-4.2.0.json
```

Planning caps, to be confirmed after 4.2a: 64 MiB combined new payload and 192 MiB
combined stored/read-back/local-review payload. Manifest is published last. Refuse
any current/historical destination collision or delete marker. Use a persistent
cooperative reservation, SDK/function retries disabled, exact-version hash/byte
read-back and no destructive cleanup or blind ambiguous-write retry.

### Validation gates before a final feature table

- Exactly 6,371 unique grid IDs in each epoch and in the static terrain table.
- No duplicate/lost cells, CRS/grid drift or unreported missing values.
- Per-cell counts reconcile with global raster totals and the Phase 3 range audit.
- Support distributions and maps reviewed for every epoch/index.
- Filtered/unfiltered sensitivity reported, especially the 2018 outlier locations.
- Elevation/slope ranges, nodata and seam behaviour reviewed.
- User selects a minimum usable-support policy after inspecting evidence.
- Only then may a final model-ready Part 4.2 table be proposed/published.

Preliminary 4.2b planning allowance: one 2-CPU/8-GiB Modal worker, no GPU,
30–60 minutes and under US$0.50 compute, excluding B2 transaction/egress pricing.
These are planning estimates, not authorization or billing guarantees; 4.2a must
refine them from actual schemas and transfer behaviour.

## Approval boundary

The user subsequently authorized 4.2a, bounded DEM validation, the aggregation core,
pilot, full 4.2b batch and final scientific review. The six proposed B2 outputs were
created once and verified. No label, model or prediction operation occurred.

## Part 4.2a execution result

Modal run `ap-Aa5eCAKVU7wPh0pwIn3I4W` completed on Python 3.12.10 after the full
suite passed 371 tests with one existing warning.

- Small pinned payload read: 52,147 bytes.
- Raster payload/pixel reads: 0 bytes.
- B2 writes: 0.
- 20 index COGs: 1,309,726,569 bytes, identities matched the approved manifest.
- Grid: 2,816,012 bytes, identity matched contract 4.1.0.
- Two DEM objects: 46,382,829 bytes, one current/historical version each and exact
  Phase 2 sizes; both lack SHA-256 metadata.
- Known aggregation input: 1,358,958,178 bytes before small manifests.

The next gate is a version-pinned download/hash and raster-header validation of only
the two DEM files (46,382,829 bytes). Proposed Modal workload: one 1-CPU/2-GiB worker,
no GPU, 10-minute timeout, retries disabled; expected runtime 2–5 minutes and planning
compute under US$0.05. It writes no B2 objects and saves a create-only local JSON/Markdown
receipt under the existing feature-review directory. Stop on hash/read/header/schema,
version or byte-count mismatch. Approval of this gate does not authorize the 1.36 GB
index aggregation or any feature-table publication.

## Subsequent DEM gate and Part 4.2b pilot results

An evidence-first probe showed that the Copernicus files use valid half-pixel-aligned
outer bounds rather than integer-degree outer bounds. The contract was corrected from
observed exact-version evidence; the source files were not altered. Modal run
`ap-XtNy5uLjfsykXJySgzFpbI` then passed the strict DEM gate:

- 46,382,829 exact-version bytes read and SHA-256 verified; B2 writes: 0.
- Both 3,600 x 3,600 float32 EPSG:4326 rasters are strict COGs at 1/3600 degree.
- Their adjacent seam is exact; all 25,920,000 pixels reconcile.
- E082 elevation range: -2.590 to 1,584.418 m; E083: -4.972 to 591.159 m.
- Evidence: `results/phase4/features/contract-4.2.0/dem_validation.{json,md}`.

The calculation core implements pixel-centre assignment, per-cell AOI/valid/nodata/
excluded/usable counts, raw diagnostic and filtered means, count reconciliation and
metric slope. The approved rule excludes an out-of-range value only from its affected
index; it does not clip source rasters, drop cells or fill missing means with zero.
The complete Modal suite passed 381 tests with one existing synthetic all-NaN warning
before the real-data pilot.

Modal run `ap-ESKgft4wckfIBJXclDGxns` processed the exact pinned 2024 NDVI, grid and
boundary (68,049,624 bytes) without a B2 write:

- 6,371 unique grid rows retained; 15,353,996 AOI candidate pixel centres.
- 15,257,709 usable pixels; 96,287 nodata; zero out-of-range exclusions.
- 6,368 cells have usable pixels. Three extremely small edge fragments contain no
  10 m pixel centre and remain present with missing values.
- Median usable fraction is 1.0; fifth percentile is 0.9656.
- Filtered cell-mean NDVI range is -0.370898 to 0.807501.
- Status remains `pilot_passed_pending_support_policy_review`.
- Evidence: `results/phase4/features/contract-4.2.0/satellite_pilot_2024_ndvi.{json,md}`.

## Final full-batch and scientific-gate result

The first full attempt `ap-Zg1HmnbqJUBIEqChOBfVv9` stopped before publication because
independently reprojecting adjacent DEM tiles created an artificial overlap above the
seam tolerance. B2 writes were zero. The corrected method mosaics the exact tiles once
in native EPSG:4326 and then performs one bilinear reprojection; regression coverage was
added before controlled resume.

Corrected run `ap-Dz1CfM1F43J7c3bAnkHkcH` read and hashed 1,358,958,178 bytes across
24 pinned sources, produced 25,484 satellite rows and 6,371 terrain rows, and published
six create-only objects totaling 3,308,109 bytes with the manifest last. Every exact
version passed byte/hash read-back.

Read-only review `ap-wKjNJgIpGetKO9w1nqLs01` reverified all six hashes, reopened and
validated both Parquet tables, and visually reviewed the exact support map. The approved
downstream rule requires >=0.50 usable fraction for every required index and epoch plus
valid elevation and slope. It retains 6,355 of 6,371 cells across all epochs. All 6,371
rows and QC fields remain preserved; ineligible cells must be flagged downstream, never
silently dropped or zero-filled. Part 4.2 is complete. Part 4.3 is next.
