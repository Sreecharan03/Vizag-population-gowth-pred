# Phase 3 gate review — approved workload

Status: **approved and completed successfully** on 10 November 2026. This plan is not gate approval.
Final evidence and findings: [gate review summary](../results/phase3/gate_review_summary.md).
Run: https://modal.com/apps/sankar132095/main/ap-TzE1Q1IpjSls5mOpRKwUU0
Final pre-run regression: **357 passed**, one existing synthetic all-NaN warning,
7.94 seconds: https://modal.com/apps/sankar132095/main/ap-v1cTbgBMQkgATLgptXLloe

## Purpose

Prepare the missing Phase 3 visual/scientific review before any Phase 4 work.
Create four year-specific images, native-resolution range/source diagnostics and
an exact-version-verified review manifest. Do not modify the index/composite data,
clip values, approve an eligibility policy or approve the Phase 3 gate automatically.

## Approved inputs and byte limits

All existing rasters use the previously audited source keys, versions, sizes and
hashes frozen in `configs/gate_review.yaml`.

| Input | Count | Bytes |
|---|---:|---:|
| Contract 3.5.0 composites/counts | 8 | 1,468,221,549 |
| Contract 3.6.0 indices | 20 | 1,309,726,569 |
| Two critical manifests | 2 | 52,501 |
| Existing feasibility report | 1 | 1,314 |
| Existing buffered boundary | 1 | at most 1,048,576 |
| **Maximum input payload** | | **2,779,050,509** |

Boundary: `vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson`.
Feasibility: `vizag-geoai/v2/results/epoch_feasibility.md`.
No raw satellite archive or scene-stack payload is read. Metadata checks are
additional small requests, not hidden raster reads. Input downloads are exact
version-pinned, streamed and hashed once. Disable SDK/function automatic retries.

## Measurements and figures

- Native 512-pixel blocks verify grid alignment, nodata, count classes/AOI,
  count >=4 versus composite validity, >=99% AOI coverage, and every index formula.
- Recompute all existing index statistics and compare exactly with the hash-pinned
  published index manifest; stop on disagreement.
- Record per-index range counts/extrema and their unique pixel-wise union; never
  sum overlapping index counts and call that unique affected area.
- Record negative reflectance by band, negative ratio terms/denominators among
  outliers, absolute denominators, continuous cancellation-ratio distributions,
  and bounded samples of largest absolute values with derived coordinates.
- Global means excluding range outliers are sensitivity diagnostics only, not
  an approved eligibility mask or 500 m feature table.
- Four 3x3 figures show RGB, observation counts, five indices, native outlier
  locations and a plain-language quality summary. Use the existing verified
  buffered boundary; no invented locality labels or unverified map geometry.
- Preview colour limits/overviews affect display only. Native outlier maps count
  every flagged source pixel in each preview bin, avoiding lost rare extrema.
- No causal claim about individual source scenes is made from a composite alone.
  If deeper scene-level review is needed, propose that workload separately.

## Outputs

Bucket: `satilliate-images`. New review root:
`vizag-geoai/v2/results/phase3/gate_review/v1/`.

| New file | Per-file limit |
|---|---:|
| qc_2018.png | 3 MiB |
| qc_2020.png | 3 MiB |
| qc_2022.png | 3 MiB |
| qc_2024.png | 3 MiB |
| range_review.json | 2 MiB |
| range_review.csv | 1 MiB |
| review.md | 256 KiB |
| phase3_gate_review.v1.json (manifest namespace below) | 256 KiB |

Manifest key: `vizag-geoai/v2/manifests/phase3_gate_review.v1.json`.
Enforce **16 MiB maximum total newly stored payload** and **48 MiB maximum**
combined stored bytes + exact-version read-back + local viewing copies.
Local viewing files are created once under `results/phase3/`; an additional small
control-plane receipt is `gate_review_receipt.json`. No existing file is overwritten.
No broad results/workspace upload; only the seven generated artifacts and final
manifest are published. No credentials, .env, raw data or Git metadata is uploaded.

## Runtime and protection gates

- Source-based Modal Python 3.12; profile `sankar132095`, environment `main`.
- One sequential worker, 2 CPU/4 GiB, no GPU, maximum one worker, 1,800-second
  timeout. This is within the approved ceiling of two workers.
- One epoch's seven temporary input rasters at a time. Check project storage guard,
  application 20 GiB staging cap and actual free disk before each epoch.
  Dispose only of the job's own newly generated Modal scratch copies.
- All eight output keys must be absent across paginated versions/delete markers
  before raster work; reserve the new namespace with an atomic persistent Modal
  reservation. Ordinary PUTs are not atomic create-only against unrelated writers:
  exclusive namespace ownership is required, and collisions halt the job.
- Complete all four native reviews before any artifact PUT. Enforce per-file and
  total byte budgets, upload each new artifact once, read back exact returned
  versions, compare bytes/SHA-256 and require one version. Manifest is last.
- Preserve all originals and any partial new outputs on error. Stop and report;
  no blind retries, rollback deletion or automatic lock removal.
- Check source versions remain unchanged. Verify returned local viewing bytes
  against published identities before creating files using exclusive-create mode.

## Estimates, not measured billing

Approved planning runtime: 10–25 minutes, excluding builds/queueing.
Planning compute allowance: US$0.25, not a hard account cap; network charges depend
on account terms. See [Modal pricing](https://modal.com/pricing). Actual account
billing is not queried by this job.

## Human decision remains separate

Successful artifact generation means the evidence is ready, not that the data is
physically trustworthy for every application. The user must inspect images,
feasibility/storage evidence and outlier diagnostics; decide whether deeper source
review is needed; approve a scientifically justified downstream policy and the
Phase 3 gate. No Phase 4 grid, feature aggregation, training, Git staging, commit,
push, existing-object overwrite or deletion is authorized by this QC run.

