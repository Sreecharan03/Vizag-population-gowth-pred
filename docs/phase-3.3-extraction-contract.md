# Phase 3.3 Scientific Extraction Contract

Status: Approved and validated; revision 3.3.2 approved 2026-11-05  
Scope: Part 3.3 extraction  
Compute: Modal only  
Persistent storage: Backblaze B2 only

## 1. Purpose

This contract defines the scientific and technical invariants that every
Sentinel-2 scene extraction must satisfy before batch processing is allowed.
It deliberately separates extraction from cloud-mask construction, which is
owned by Part 3.4.

## 2. Approved inputs

- Input inventory: the 32 scenes approved after Phase 3.2 triage.
- Source products: Sentinel-2 Level-2A SAFE archives stored in B2.
- Reads must be direct, windowed reads from B2-hosted archives.
- A run must use the immutable source-object identity recorded in the selected
  scene manifest (object key plus available version/checksum/size metadata).
- Missing, ambiguous, corrupt, or duplicate required band assets are hard
  failures for that scene. They must not be guessed or silently substituted.

## 3. Required source bands

| Band | Native resolution | Role | Output resampling |
|---|---:|---|---|
| B02 | 10 m | Blue reflectance | None unless grid alignment requires a window-edge adjustment |
| B03 | 10 m | Green reflectance | None unless grid alignment requires a window-edge adjustment |
| B04 | 10 m | Red reflectance | None unless grid alignment requires a window-edge adjustment |
| B08 | 10 m | NIR reflectance | None unless grid alignment requires a window-edge adjustment |
| B11 | 20 m | SWIR-1 reflectance | Bilinear to the canonical 10 m grid |
| B12 | 20 m | SWIR-2 reflectance | Bilinear to the canonical 10 m grid |
| SCL | 20 m | Scene classification | Nearest-neighbour to the canonical 10 m grid |

No other image band may be read merely for convenience.

## 4. Canonical spatial grid

- The canonical CRS is `EPSG:32644`, as approved in `configs/boundary.yaml`.
  A scene CRS must still be read and verified from the raster, never assumed
  from its tile name.
- Output pixel size is exactly 10 m by 10 m in that projected CRS.
- The study geometry is the verified GVMC OSM relation `17493324`, buffered by
  exactly 5,000 m in `EPSG:32644`. The buffered boundary object is
  `vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson`.
- The buffered project boundary is already expressed in the canonical CRS and
  is used to calculate the read window.
- Output bounds are snapped outward to the canonical 10 m grid using a single
  fixed grid origin shared by every scene and epoch.
- Every reflectance band and SCL output for a scene must have identical CRS,
  transform, width, height, and bounds.
- Reprojection is forbidden when the source and canonical grids already match.
- A one-pixel shift, shape mismatch, or transform mismatch is a failed output.

All selected scenes are from required tile `T44QQE`. A read-only Modal probe of
an approved real scene confirmed the authoritative native grid origin as
`x=699960`, `y=2000040`: the 10 m transform is
`[10, 0, 699960, 0, -10, 2000040]`, and the 20 m assets use the same origin.
This origin is frozen in `configs/preprocessing.yaml`; every later scene must
match it or fail validation.

## 5. Radiometric conversion

Reflectance bands must be converted independently using metadata from their
own source product:

`BOA_reflectance = (DN + BOA_ADD_OFFSET) / QUANTIFICATION_VALUE`

Rules:

1. Read `QUANTIFICATION_VALUE`, processing baseline, and the band-specific
   `BOA_ADD_OFFSET` from product metadata.
2. For products whose metadata legitimately has no BOA offset, use zero only
   after confirming that the processing baseline is governed by the pre-offset
   convention. Missing required offset metadata on an offset-era product is a
   scene failure.
3. Match offsets by the metadata band identifier, not by XML list position.
4. Identify nodata before applying the offset or scale. Source nodata must not
   become valid reflectance.
5. Use float32 for radiometric calculations. The persisted representation is
   a decision gate in Section 7; it is not silently selected here.
6. Do not silently clamp negative reflectance or values above one during
   extraction. Count, report, and review them first. This intentionally raises
   a conflict with `plan.md` line 427, which currently says to clip and log;
   the plan must be amended only after human approval of the scientific rule.
7. Never apply scale or offset twice. Persist the exact parameters used in the
   output manifest.

## 6. Nodata and validity

- Source nodata is derived from authoritative product metadata and band masks;
  it is not inferred from low reflectance.
- Reflectance nodata is represented by a declared float nodata value and a
  validity mask. NaN may be used only if all downstream readers and COG checks
  are proven to preserve it consistently.
- SCL nodata remains categorical nodata and must never be treated as SCL class
  zero without recording that distinction in the validity mask.
- Resampling must not interpolate across invalid reflectance pixels as though
  they were valid zeros.
- Boundary-exterior pixels and source-coverage gaps remain invalid.

Persisted reflectance nodata is `-9999.0` in float32, approved by the user on
2026-11-04. A separate validity mask must agree with that sentinel in both
directions. This value is applied before radiometry and resampling.

Complete pixel validation established the source validity rule: each
reflectance band's DN `0` is invalid independently of SCL, and SCL invalid
classes are an additional mask rather than a substitute. DN-zero pixels must
be masked before offset/quantification and before B11/B12 bilinear resampling,
so they can never become `-0.1` reflectance or contaminate neighbouring pixels.

The real JP2 probe reported `nodata=None` in every raster header, including
SCL. Consequently, the implementation must not rely on a GDAL nodata tag. The
authoritative DN/SCL nodata interpretation remains a separate validation item
and must be proven before any corrected raster is written.

## 7. Output artifact decision gate

The repository contains a real design conflict that must be resolved before
implementation:

- `plan.md` decision D6 says scene stacks are stored as DN `uint16` plus mask.
- Part 3.3 says the metadata offset is applied before the clipped stack is
  written.
- Persisting corrected reflectance as plain `uint16` would require a documented
  scale/offset encoding and careful signed-range handling; otherwise corrected
  negative values are lost or wrapped.

### Approved design

Store reflectance and SCL as separate COGs because they have different data
types, meanings, nodata rules, and overview resampling requirements:

1. Reflectance COG: six float32 bands ordered `B02, B03, B04, B08, B11, B12`.
2. SCL COG: one categorical integer band, resampled only with nearest-neighbour.

This accuracy-first option was approved by the user on 2026-11-04: the metadata correction is explicit in the
pixels, negative corrected reflectance is preserved for QC, and categorical SCL
cannot accidentally receive continuous-data overview resampling. Its cost is
larger reflectance objects than a carefully scaled integer representation.

The rejected alternative was a scaled signed-integer reflectance COG with explicit scale,
offset, valid range, and round-trip error tolerance. It may reduce storage but
adds quantisation and reader-compatibility risk. Keeping raw DN `uint16` would
defer radiometric correction and contradict the current Part 3.3 processing
order, so it is not recommended.

Each COG must include:

- CRS, affine transform, bounds, dimensions, nodata, band descriptions, units,
  source scene identifier, source-object identity, and processing-contract
  version;
- internal tiling, lossless compression, and valid internal overviews;
- a checksum calculated after the completed object is written;
- validation demonstrating that it is readable through B2-backed GDAL access.

Versioned keys, confirmed against `configs/compute.yaml`'s isolated v0.2 prefix.
Contract 3.3.2 adds the contract version to the immutable object namespace so
scientifically different outputs can never collide or require overwrite:

- `vizag-geoai/v2/processed/sentinel2/scene_stacks/contract-3.3.2/<epoch>/<scene-id>_reflectance.tif`
- `vizag-geoai/v2/processed/sentinel2/scene_stacks/contract-3.3.2/<epoch>/<scene-id>_scl.tif`
- `vizag-geoai/v2/manifests/scene_extraction_manifest.jsonl`

These keys do not reuse the legacy `vizag-geoai/data/processed/sentinel2/`
objects. `configs/b2.yaml:processed_backup` remains unrelated and unset.

Revision 3.3.2 requires both COGs to embed the source object key, source size,
source ETag, processing baseline, quantification value and all six band offsets.
The earlier unversioned pilot pair is preserved unchanged and is explicitly not
a completed artifact under this contract.

## 8. Publication and resumability

- Completion is manifest-driven, not inferred merely from object existence.
- An output is complete only when both COGs pass validation and their checksums
  and contract version are recorded in the manifest.
- Incomplete staging objects must never use final object keys.
- A retry may skip a scene only after revalidating its manifest entry and both
  persisted output identities.
- A changed source identity, contract version, processing parameter, checksum,
  or failed COG check invalidates the prior completion record.
- One scene failure is recorded and isolated; it must not conceal failures or
  terminate processing of unrelated scenes.

## 9. Part 3.3.1 acceptance gate

Part 3.3.1 is approved only when all of the following are explicit and reviewed:

- real-scene verification and freezing of the fixed grid origin (the CRS,
  boundary object, and 5,000 m buffer are now confirmed);
- exact metadata fields and baseline rules used for radiometric conversion;
- persisted reflectance nodata representation;
- the approved float32-reflectance plus separate SCL design is represented
  identically in configuration and implementation;
- B2 key layout and processing-contract version;
- measurable tolerances for later window-equivalence and pixel-alignment tests.

No extraction implementation or full-data run is authorized by approval of this
document alone.

## 10. Real-scene probe evidence (2026-11-04)

The read-only Modal probe used approved scene
`S2A_MSIL2A_20180304T044701_N0500_R076_T44QQE_20230904T140422` and wrote no
B2 object.

- Acquisition epoch: 2018; product processing baseline: `05.00`. This proves
  acquisition year cannot be used as a proxy for offset rules.
- `BOA_QUANTIFICATION_VALUE`: `10000`.
- `BOA_ADD_OFFSET`: `-1000` for metadata band IDs 0 through 12.
- Product metadata explicitly maps numeric IDs to physical bands; conversion
  must use that mapping rather than list position.
- B02/B03/B04/B08: `EPSG:32644`, 10 m, 10980 x 10980, identical transform.
- B11/B12/SCL: `EPSG:32644`, 20 m, 5490 x 5490, identical origin.
- Source reflectance dtype: `uint16`; SCL dtype: `uint8`.
- Raster-header nodata: unset for every probed asset.
- The probe read only the 54,987-byte product XML, ZIP ranges, and raster
  headers; it performed no pixel extraction and no persistent write.

### Complete selected-scene validation

The same read-only validation then passed over the complete approved dataset:
32 scenes and 224 required raster headers.

- Epoch counts: 2018=8, 2020=8, 2022=8, 2024=8.
- Processing baselines: `04.00`=1, `05.00`=16, `05.10`=15.
- All 32 products are offset-era products and contain the physical-band
  mapping and BOA offset entry required for B02/B03/B04/B08/B11/B12.
- Every required archive band exists; no selected object key is duplicated.
- All 224 assets use `EPSG:32644` and origin `(699960, 2000040)`.
- All 10 m bands are 10980 x 10980; all 20 m bands/SCL are 5490 x 5490.
- Every raster header has nodata unset, so pixel validity cannot be delegated
  to a raster nodata tag.
- The scan read metadata and headers only and wrote nothing to B2.

The first complete scan correctly halted on a validator defect: metadata uses
names such as `B2`, while SAFE assets use `B02`. The parser now canonicalizes
numeric physical-band names (`B2` to `B02`) while preserving `B8A`; regression
coverage was added and the corrected complete scan passed.

### Complete pixel-level nodata evidence

All 32 scenes and six reflectance bands were measured over the buffered
boundary on Modal. Aggregate DN-zero fractions match the earlier coverage
finding: approximately 13.56% in 2022 and 27.82% in 2024; 2018/2020 are nearly
complete. Native 20 m SCL had no class-zero pixels inside the measured
boundary, so SCL class zero does not encode the large orbit-edge gaps. Tiny
10 m SCL-zero counts arose only after grid reprojection/window edges and must
not be used to override band validity. No corrected output or B2 object was
written.

The initial 32-scene in-memory run was preempted by Modal after scene 21 and
restarted from scene 1. Validation was therefore split into four independent
8-scene epoch units, run at maximum concurrency 2. All four units completed;
future production work must checkpoint per scene rather than per batch.

### Complete real-pixel radiometric evidence

Read-only conversion statistics were calculated for all 32 approved scenes.
All selected products, including the mixed `04.00`, `05.00`, and `05.10`
baselines, resolved to product-metadata parameters offset `-1000` and
quantification `10000` for every required reflectance band.

Median of the eight per-scene medians by epoch:

| Band | 2018 | 2020 | 2022 | 2024 |
|---|---:|---:|---:|---:|
| B02 | 0.04235 | 0.05620 | 0.04990 | 0.05460 |
| B03 | 0.06240 | 0.07130 | 0.06740 | 0.07275 |
| B04 | 0.07305 | 0.06345 | 0.06400 | 0.07070 |
| B08 | 0.20210 | 0.22250 | 0.21980 | 0.21730 |
| B11 | 0.21615 | 0.19910 | 0.19215 | 0.19230 |
| B12 | 0.14975 | 0.12325 | 0.11940 | 0.12165 |

The scale is stable across processing baselines; no factor-of-ten or offset
discontinuity is present. Rare valid negative and above-one values occur and
remain available for QC as approved. DN-zero gaps were excluded before
conversion, reproducing the 2022/2024 partial-coverage findings. No COG or B2
object was written.

### Complete spatial and resampling evidence

All 32 scenes passed real, read-only spatial validation. The buffered boundary
snaps to the canonical 10 m output grid:

- bounds: `(706610, 1936220, 765270, 1990390)`;
- shape: `5417 x 5866` pixels;
- transform: `[10, 0, 706610, 0, -10, 1990390]`;
- CRS: `EPSG:32644`.

For every scene, the direct B02 window was byte-for-byte equal to the same
area sliced from a larger reference window. B11/B12 were converted with source
DN-zero masked first, then bilinearly resampled with explicit `-9999` nodata;
no nodata value contaminated valid output. SCL was resampled using nearest
neighbour and produced no class absent from its source (apart from destination
nodata class 0). All output shapes and transforms matched the frozen grid.
