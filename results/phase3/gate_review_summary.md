# Phase 3 gate review — completion and findings

Completed: **10 November 2026**. **Evidence ready; human gate and eligibility-policy approval pending.**

## Outcome

Created, published and exact-version/hash verified four QC figures, three review
reports and one final manifest. Local viewing copies match the verified B2 bytes.
All 28 input raster versions and full byte hashes were checked, strict COG/schema
checks passed, and native pixel counts, masks, coverage and index formulas match
the prior published QC. Original data and the earlier archive snapshots are unchanged.

| Year | AOI coverage with at least four observations | Distinct pixels outside the nominal range in any index | Share of AOI |
|---|---:|---:|---:|
| 2018 | 99.6693% | 11,378 | 0.0741045% |
| 2020 | 99.9107% | 0 | 0% |
| 2022 | 99.7986% | 12 | 0.0000782% |
| 2024 | 99.3729% | 0 | 0% |

All four years pass the already-approved 99% coverage gate. Counts above are the
pixel-wise union across indices, not a sum of overlapping per-index counts.

## Open the actual evidence

- [2018 QC figure](qc_2018.png)
- [2020 QC figure](qc_2020.png)
- [2022 QC figure](qc_2022.png)
- [2024 QC figure](qc_2024.png)
- [Detailed review, including existing epoch feasibility](review.md)
- [Native statistics, source identities and bounded samples](range_review.json)
- [Sampled coordinates and reflectance terms](range_review.csv)
- [Publication receipt with every output hash/version](gate_review_receipt.json)
- [Verified review manifest](phase3_gate_review.v1.json)

The four images were visually inspected for readable titles, correct year labels,
buffered-boundary overlays and consistency with the measured tables. This is not
independent ground-truth validation of land-cover accuracy.

## Main scientific finding

Every range outlier in 2018 and 2022 has at least one negative term in its index
ratio. In 2022 the same 12 pixels have negative B08 reflectance and slight NDVI,
NDBI and NDWI excursions. The largest 2018 excursions are amplified by strong
cancellation between positive and negative denominator terms. Not every small
range excursion involves severe cancellation; the JSON reports the distributions.

One actual 2018 sample, using the two corrected reflectance measurements in NDBI:

```text
B11 =  0.011893750168383121
B08 = -0.011900000274181366

NDBI = (B11 - B08) / (B11 + B08)
Denominator = -0.000006250105798244476
Stored NDBI = -3806.935546875
```

That denominator is above the existing absolute 1e-6 guard in magnitude, so the
finite result was correctly preserved under the approved numerical contract.
It is not a physically meaningful built-up probability. Matching bytes/formulas
does not establish physical reliability of the underlying corrected reflectance.
No individual source-scene physical cause is established by this composite-only
review. Deeper scene investigation, if desired, requires its own approved workload.

Global means are included with and without range outliers as sensitivity diagnostics.
For example, 2018 NDBI is -0.00173789 with all valid values versus -0.00361139 with
range outliers omitted. A small global difference does not prove small effects in
individual future 500 m cells. No omission rule, clipping, new denominator threshold,
scene exclusion or feature aggregation has been implemented.

## Reading the figures correctly

- RGB is a true-colour preview with a common display-only reflectance stretch.
- Observation maps show clear-image availability out of eight selected scenes.
  The sharp count differences in 2022/2024 reflect differing observation availability;
  they are not predicted urban boundaries or proof of a physical land-cover break.
- Index colours saturate at [-1,1] for display. Unmodified native values drive all
  counts and flags, including rare extremes hidden by averaged previews.
- In the **outlier-location panel**, grey means no flagged pixel is displayed in
  that bin; it must not be read as missing source coverage. In the RGB/index/count
  panels, grey denotes unavailable display data/background.
- Samples select the largest absolute values per index, not a representative
  sample. Coordinates are transformed from actual raster pixel centres; no locality
  names or land-use labels were guessed.
- These are QC images, not classification maps, model predictions or accuracy metrics.

## Execution and transfer record

- [Production run](https://modal.com/apps/sankar132095/main/ap-TzE1Q1IpjSls5mOpRKwUU0)
  — successful exit, Modal Python **3.12.10**, one 2-CPU/4-GiB worker, no GPU.
- [Final full regression](https://modal.com/apps/sankar132095/main/ap-v1cTbgBMQkgATLgptXLloe)
  — **357 passed**, one existing synthetic all-NaN composite warning, 7.94 seconds.
- Input payload: **2,778,034,701 bytes**, below the approved 2,779,050,509 cap.
  Includes 28 rasters, two manifests, a 32,768-byte buffered boundary and the
  1,314-byte existing feasibility report. No raw archive or scene-stack payload read.
- Newly stored artifacts: **5,389,770 bytes** across eight objects.
- Stored + exact-version read-back + local viewing payload: **16,169,310 bytes**,
  below the approved 48 MiB limit. No claim about actual provider billing is made.
- All eight destinations were absent across current/historical versions before work.
  All four native reviews finished before the first artifact PUT; manifest was last.
- SDK/function retries were disabled. The successful persistent reservation remains
  in `vizag-phase3-gate-review-v1`; do not rerun the job or remove the reservation.
- No existing object overwrite, source rewrite, clipping, deletion, Git staging,
  commit, push, Phase 4 grid construction or model training occurred. Only newly
  generated temporary Modal scratch copies were disposed of by the job.

Review root: `vizag-geoai/v2/results/phase3/gate_review/v1/`.
Manifest: `vizag-geoai/v2/manifests/phase3_gate_review.v1.json`.
Manifest SHA-256: `7ad2d07ab0b118d33bb8e572e982f9958ea6accefde8641e6d23eee7e556dee0`.

This summary is a new local interpretation/control-plane document. It does not
overwrite the seven published review artifacts or publish an additional B2 object.

## Decision still needed before Phase 4

The user must review the four figures, feasibility and archived storage evidence,
then agree how flagged index values are handled downstream, or request deeper
source-scene investigation. Preserve original COGs regardless of that choice.
An explicit scientifically justified eligibility/aggregation policy must be recorded
before feature means are calculated. No policy or Phase 3 gate approval is inferred
from successful artifact generation or passing software tests.
