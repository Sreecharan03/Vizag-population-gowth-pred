# Part 3.7 — archive completion

**Completed:** 10 November 2026. **Part 3.7 complete; Phase 3 visual/scientific gate pending.**

This is the final publication receipt. The original [storage report](storage_report.md),
[read-only audit record](storage_audit.json), and other archived reports remain unchanged
historical snapshots. Their pending-publication wording is superseded by this receipt
and the verified B2 completion manifest, not by rewriting those frozen files.

## Completed work

1. Implemented a separate copy-only publisher; the existing storage audit remains read-only.
2. Ran the full Modal Python 3.12 regression suite: **338 passed**, one existing
   synthetic all-NaN composite warning, 6.67 seconds.
3. Revalidated every approved source size/hash: **16 files, 122,487 bytes**.
4. Refreshed the production identity audit and matched all 94 object references
   (92 rasters plus two critical manifests) to the approved saved audit.
5. Checked every proposed destination across paginated current/historical versions
   and delete markers; all 17 were absent before publication.
6. Acquired a persistent atomic Modal publication reservation. Published each
   snapshot once, verified its exact returned version, bytes and SHA-256, and
   confirmed one current version. No automatic function or SDK retries were used.
7. Published the completion manifest **last** and verified its exact-version read-back.
8. Rechecked namespace totals and unchanged production identities. No raw/processed
   raster payload was read, uploaded, copied, overwritten or deleted.
9. Eviction was an explicit no-op: no local staging/scene stacks required eviction.
   Older B2 pilot outputs and all original local snapshots were preserved.

## Published archive

Bucket: `satilliate-images`. Snapshot root:

`vizag-geoai/v2/results/phase3/archive/contract-3.7.0/`

Each of the 16 files retains its approved relative path under that root.
Exact source paths, object keys, returned versions, hashes and read-back flags are
in [archive_completion.json](archive_completion.json).

| New payload | Objects | Bytes |
|---|---:|---:|
| Approved report/config snapshots | 16 | 122,487 |
| Completion manifest | 1 | 41,766 |
| **Total newly stored** | **17** | **164,253** |
| Approved maximum | 17 | 188,023 |

Completion manifest:

- Key: `vizag-geoai/v2/manifests/phase3_archive_manifest.contract-3.7.0.json`
- SHA-256: `ff68fede445abd5f73c9f4de97d340aaae56fe49ca89e69bf91ee76904cccf4f`
- Version: `4_z2250dbc1f968e033a7050713_f1170602218c53f54_d20261110_m121247_c005_v0501053_t0031_u01794312767501`
- Exact bytes, hash and single current version: verified.

The manifest references the existing 92 production rasters and two critical
manifests, all 16 newly archived snapshots, their exact versions/hashes, eviction
status and scientific/audit limitations. This is evidence archiving in the approved
B2-only architecture, not an independent second offsite replica or a full source-code backup.

## Storage after publication

| Measure | Result |
|---|---:|
| V2 current objects | 117 |
| V2 object versions | 117 |
| V2 delete markers | 0 |
| V2 current/version bytes | 13,795,150,258 |
| Unchanged production rasters | 92 |
| Unchanged production raster bytes | 13,419,102,871 |
| Existing manifest payload bytes read | 52,501 |
| Raster payload bytes transferred | 0 |

V2 totals include the preserved old pilot pair and the earlier catalogue/selection/
triage/feasibility records. They are not full-bucket totals or local Tier-2 usage.
The original read-only audit observed no staging/processed/derived files in the
checkout or fresh audit container. No claim is made about historical terminated
workers, other containers or account volumes. Application scratch remains capped
at 20 GB; this publication used in-memory small payloads, not raster scratch.
The old 150 GB Studio budget remains historical; no config cap was invented.

## Validation limits and safety

- This completion verifies archive bytes and object identities. It does not rerun
  raster content hashes, COG validation, index formulas or coverage calculations.
- The 64 scene-stack hash references come from the byte-verified extraction manifest;
  those objects lack SHA-256 metadata. Prior content audits remain their evidence.
- All 16 payloads were frozen before transfer; only explicitly allowlisted bytes
  were passed to the worker. No .env, credentials, Git metadata or unrelated assets
  were included. Configured bucket/prefix/secret names are non-secret identifiers.
- The cooperative persistent reservation remains in place with successful results.
  Do not remove it or rerun the publication action. An ordinary B2 PUT is not an
  atomic conditional create against unrelated external writers; exclusive ownership
  of this new namespace was required. No conflicting writer or duplicate version
  was observed.
- No errors occurred in this publication or its 338-test regression. An ambiguous
  upload would have stopped immediately, preserved created objects, and required
  an explicitly approved reconciliation before any retry.
- Actual billing was not queried; the approved estimates are not measured charges.
- No Git staging, commit, push, cleanup deletion or existing-object overwrite occurred.

## Execution evidence

- [Publication run](https://modal.com/apps/sankar132095/main/ap-3S8TpYOPO33bqm09TURfzc) — successful completion, Python **3.12.10**.
- [Full regression](https://modal.com/apps/sankar132095/main/ap-tMNwJnJVrAMyFX9HjBXdej) — 338 passed, one existing warning.
- [Approved transfer plan](../../docs/phase-3.7-archive-completion-plan.md).
- Implementation: `src/storage/archive_publish.py`, policy: `configs/archive_publication.yaml`.

## Phase 3 gate — not automatically approved

All eight implementation parts, **3.0–3.7**, are now complete. The Phase 3 gate
still requires review of RGB composites, observation-count maps, index samples
for all four epochs, feasibility and storage evidence.

The rare extreme 2018 index values and slight 2022 outliers remain preserved and
require scientific/source review and an approved downstream policy before feature
aggregation. No clipping, new threshold or data rewrite was performed.
**No Phase 4 grid, feature aggregation or model training was started.** Additional
preview/source-QC raster reads require their own workload/transfer proposal and
approval; completion of Part 3.7 is not approval to skip that gate.

