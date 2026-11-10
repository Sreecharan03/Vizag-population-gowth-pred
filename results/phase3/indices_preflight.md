# Phase 3.6 preparation and metadata-only preflight

Date: 10 November 2026. **Historical preflight record.** The subsequently approved
production batch completed; see [indices_validation.md](indices_validation.md).
The sections below retain the preparation/approval sequence rather than describe the current state.

## Authentication and tests

Modal token verified in workspace/profile `sankar132095`, environment `main`.
Remote verification confirmed Python 3.12.10 and B2 credential presence without
printing secret values or accessing B2 objects. The restricted network sandbox
could not reach Modal; the explicitly approved network-enabled execution worked.

Full regression: **287 passed, one existing all-NaN synthetic-composite warning,
9.02 seconds**. No test failed. The warning is in the existing composite test,
not the new index tests. A later client background-thread shutdown message occurred
after successful test completion.

- Verification run: https://modal.com/apps/sankar132095/main/ap-IfMUo7MF8xiLgt9QgRFBdp
- Regression run: https://modal.com/apps/sankar132095/main/ap-PCnAXLYiCtYchdm9E2bpMx
- Metadata plan: https://modal.com/apps/sankar132095/main/ap-8qLYzxp9DpKIZor7lJmlSV

## Verified plan results

No raster pixels were read and no B2 objects were written. All four sources have
exactly one live/historical version, with SHA-256 metadata matching the independently
audited Part 3.5 identities. All 20 proposed output keys and the manifest have zero
current or historical versions.

| Epoch | Source composite compressed bytes |
|---|---:|
| 2018 | 369,765,288 |
| 2020 | 365,060,102 |
| 2022 | 366,699,998 |
| 2024 | 364,384,445 |
| Total | **1,465,909,833** |

Each uncompressed float32 index has 127,104,488 pixel bytes; all 20 together have
2,542,089,760 pixel bytes, before compression, GeoTIFF metadata and COG overviews.
Actual compressed output and network traffic have not yet been measured.

## Proposed output destinations

```text
vizag-geoai/v2/processed/sentinel2/indices/contract-3.6.0/<epoch>/ndvi.tif
vizag-geoai/v2/processed/sentinel2/indices/contract-3.6.0/<epoch>/ndbi.tif
vizag-geoai/v2/processed/sentinel2/indices/contract-3.6.0/<epoch>/ndwi.tif
vizag-geoai/v2/processed/sentinel2/indices/contract-3.6.0/<epoch>/mndwi.tif
vizag-geoai/v2/processed/sentinel2/indices/contract-3.6.0/<epoch>/bsi.tif
vizag-geoai/v2/manifests/indices_manifest.contract-3.6.0.jsonl
```

`<epoch>` is exactly 2018, 2020, 2022 or 2024. Bucket: `satilliate-images`.

## Batch proposal awaiting the separate transfer/write approval

- Four epoch tasks; at most two simultaneous workers; proposed request 2 CPU cores
  and 4 GiB memory per worker; 512-pixel blocks; no GPU.
- Download each cropped composite once to bounded Modal scratch and verify its hash.
  Expected source payload is 1.466 GB. No raw Sentinel-2 archives are fetched.
- Approximate compressed raster outputs: 1–2 GB, uncertain until generated. Budget
  temporary files conservatively and run the storage guard before the download/write.
- Validate all five local outputs before publishing an epoch. Recompute formulas,
  mask/denominator behavior and statistics; check exact grid, nodata, strict COGs,
  provenance and finite values. Preserve finite range outliers for review.
- Refuse any destination with a current or historical version. Recheck before PUT,
  use exclusive namespace ownership, and stop on any upload ambiguity/error.
- Stream/hash and audit output pixels after publication; this adds output-read
  traffic beyond the 1.466 GB input payload. Manifest is created only after validation.
- Estimated wall time including checks: 15–45 minutes. Estimated Modal compute:
  roughly $0.10–$0.75, not a measured benchmark or spending cap.

Pricing reference checked 10 November 2026: [Modal](https://modal.com/pricing)
lists $0.0000131 per core-second and $0.00000222 per GiB-second, plus network egress
after the plan's allowance. [Backblaze](https://www.backblaze.com/cloud-storage/pricing)
lists $6.95/TB/month, free transactions and egress up to 3× average monthly storage;
overage is $0.01/GB. Actual account allowances and usage are not inspected here.

The raster publication worker and independent output audit are still to be completed
and tested before any approved batch execution. Part 3.6 is not marked complete.

## Subsequent execution checkpoint

The user approved this workload. Writer, independent full-resolution validator,
version-history protections and no-retry publication tests were completed. Full
Modal regression: **295 passed, one existing warning, 7.18 seconds**.
Regression run: https://modal.com/apps/sankar132095/main/ap-i4sswEjQfFFK9ovkI1aEG7 .

The approved batch was launched at
https://modal.com/apps/sankar132095/main/ap-dI7A4YpZCjqreUvxOudKke .
Its fresh metadata preflight again found all 21 destinations absent. This launch
record alone does not certify batch completion; retain the final manifest/audit
evidence before marking Part 3.6 complete.
