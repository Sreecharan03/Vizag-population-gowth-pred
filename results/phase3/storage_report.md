# Phase 3.7 — read-only archive and storage audit

Date: 10 November 2026. **Read-only audit complete; archive-report publication and the Phase 3 gate remain pending.**

## Result

All **92 expected production rasters** are present in Backblaze B2 and match the
checked identities. The two critical manifests were read from their exact versions
and their complete SHA-256 hashes match the pinned publication records.
No raster payload was downloaded, and no object was uploaded, overwritten, copied
or deleted. The raw/legacy namespaces were not inventoried again.

| Production group | Objects | Bytes |
|---|---:|---:|
| Contract 3.3.2 scene stacks (32 reflectance/SCL pairs) | 64 | 10,641,154,753 |
| Contract 3.5.0 composites and counts | 8 | 1,468,221,549 |
| Contract 3.6.0 indices | 20 | 1,309,726,569 |
| **Production raster total** | **92** | **13,419,102,871** |

The complete `vizag-geoai/v2/` namespace contains **100 current objects,
13,794,986,005 bytes** (13.795 GB / approximately 12.85 GiB).
There are exactly 100 object versions and zero delete markers; no extra historical
versions were observed. This is not a full-bucket storage or billing report.

Six other objects are preserved: scene catalogue (148,413 bytes), scene selection
(16,687), cloud triage CSV (17,159), feasibility report (1,314), and the older pilot
reflectance/SCL pair (375,165,086 + 481,974). The pilot is outside the production
contract prefix. Its presence is not permission to delete it.

## What was verified — and what was not

- Paginated current-object and version listings; every expected object exists.
- Current/listed version agreement, exactly one version per checked key, no
  delete markers, and exact expected sizes for all 92 rasters and both manifests.
- Stored SHA-256 metadata matches the pinned identities for all eight
  composite/count rasters and 20 index rasters.
- Extraction and index manifest payload hashes match exactly. Total payload read:
  **52,501 bytes** (34,713 + 17,788).
- Existing index manifest flags confirm the completed source/hash/full-resolution
  audits recorded during Part 3.6; this audit does not perform those audits again.
- The 64 scene stacks have no SHA-256 object metadata. Their byte hashes remain in
  the verified extraction manifest; this audit checks presence, size and unique
  current versions, **not a fresh payload-hash comparison** for these rasters.
- No raster content hashes, COG structure, pixel formulas or coverage maps were
  recomputed. Prior Part 3.3/3.5/3.6 audits are the content-validation evidence.
- Catalogue, selected-scenes, triage and feasibility objects were listed, not
  downloaded or freshly content-hashed.
- B2 persistence is the approved architecture, not a second independent offsite
  replica. No claim of independent disaster-recovery replication is made.

Exact object versions and hash references are in
[storage_audit.json](storage_audit.json).

## Runtime storage and budgets

Current architecture uses Modal ephemeral scratch and B2-only persistent runtime
storage, superseding the original Studio hot-working-set model.
The fresh audit container had no staging, processed or derived files.
The local checkout likewise has no `data/staging`, `data/processed` or
`data/derived` directory; it retains one 632,216-byte manifest file.

This demonstrates the observed checkout and audit-container state only. It is not
an inspection of historical terminated workers, other running containers or all
account volumes. No eviction was requested or executed.

The configured application scratch cap remains **20 GB**; this metadata-only audit
creates no raster scratch. The historical Studio cap remains **150 GB**, and
`tier2.target_max_gb` remains unset. B2-resident production totals must not be
misrepresented as local Tier-2 usage or compared with that historical cap as if
all files were resident locally.

## Execution and tests

- [Audit run](https://modal.com/apps/sankar132095/main/ap-6z0LeTusIAEINIEKXjEKl6) — successful exit, remote Python **3.12.10**.
- [Full regression](https://modal.com/apps/sankar132095/main/ap-9M4vz5BCCmXboSz6SZncVQ) — **315 passed**, one existing
  synthetic all-NaN composite warning, 7.12 seconds.
- Requests: one current-list page, one version-list page, **94 HEADs and two GETs**.
  SDK and function automatic retries disabled; the job stops on a request error.
- Botocore request hook blocks every API operation except LIST, HEAD and GET.
  Code permits GET only for the two size-limited, pinned manifests.
- Tests use fake B2 responses exclusively, covering later-page version history,
  delete markers, identity drift, manifest corruption, read-size limits,
  unchanged unreferenced objects, and rejection of write/copy/delete requests.
- No new cost claim: actual charges were not queried. This was one 0.25-CPU,
  512-MiB, no-GPU worker; no bulk egress or new B2 stored payload was introduced.

## Remaining work and approval gates

1. **No missing production raster copy was found.** Under the approved B2-only
   architecture, do not redundantly copy all 13.419 GB to another B2 prefix.
2. The new local storage report/audit record and current validation documentation
   have **not** been published to B2. Propose exact new destination keys, bytes,
   absence/version checks and cost/runtime before any copy-only publication.
   The absent legacy `processed_backup` config value is not a reason to invent a
   backup destination or change the architecture.
3. Phase 3 visual gate remains pending: RGB composites, observation-count maps
   and index samples for each epoch; no `qc_<epoch>.png` files were found locally.
   The existing B2 feasibility report is listed, but was not reviewed here.
4. Review the preserved rare 2018 extreme index values and 12 slight 2022
   excursions per affected index; approve a scientifically justified downstream
   policy before feature aggregation. Do not clip, rewrite or invent thresholds.
5. **No Phase 4 grid, feature aggregation, model training, eviction, Git staging,
   commit or push was started.** Part 3.7 is not marked fully complete and the
   Phase 3 gate is not approved by this read-only audit.

## Re-run command

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
modal run -e main modal_app.py --action part3-storage-audit
```

Use the configured active Modal profile `sankar132095`. This source-code workflow
runs the audit on Python 3.12 without serializing a Python 3.11 function.
No local Python reinstall, credential recreation or VS Code restart was needed.

