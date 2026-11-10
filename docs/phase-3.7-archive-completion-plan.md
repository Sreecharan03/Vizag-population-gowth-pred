# Part 3.7 — archive completion proposal

Status: **explicitly approved and executed successfully on 10 November 2026**.
This document preserves the approved plan and frozen payload table. Final execution
evidence is in [archive completion](../results/phase3/archive_completion.md):
17 objects, 164,253 new bytes; 338 tests passed. The Phase 3 visual/scientific gate remains pending.

## Scope and existing evidence

The approved read-only audit found all 92 expected production rasters and both
critical manifests already durable in B2, with no extra historical versions or
delete markers. Production raster bytes: 13,419,102,871. Do not duplicate that
payload to another prefix. Raw data and both older pilot rasters remain untouched.
No local staging/processed/derived files were found to evict; eviction is an
explicit no-op for this completion, not permission to delete B2 objects.

## Exact transfer proposal

Bucket: `satilliate-images`. Profile `sankar132095`, environment `main`.
Source: the following existing files in the local control-plane checkout, passed
as explicitly allowlisted bytes to a source-based Modal Python 3.12 function.
No directory-wide mount of results or the workspace; never upload .env, secrets,
Git metadata, raw imagery, or unrelated report/UI assets.

Each destination is exactly `vizag-geoai/v2/results/phase3/archive/contract-3.7.0/` plus the source's
relative path below. There are **16 fixed payloads totaling 122,487 bytes**.

| Relative source path / destination suffix | Bytes | SHA-256 |
|---|---:|---|
| `results/phase3/storage_report.md` | 6,573 | `ef6167492126b5b57fc32327bfd461649601b1d35b9ca946eebcccc081a0cceb` |
| `results/phase3/storage_audit.json` | 45,408 | `d479185ce1f4204b71574f9aa8a9d3c679c81b38793a5e24fd8dc82a362e2f8e` |
| `results/phase3/indices_validation.md` | 8,674 | `24a69a661aecb11e777719bbdfb0e0c10f4702b79e84c88b1a8133e1e2568b91` |
| `results/phase3/indices_validation.json` | 25,017 | `ddcd1640676522bdf408542fbeddcf7790eae22bf60445ba8b2f4b98dfeed82e` |
| `results/phase3/composite_validation.md` | 3,295 | `b00b7cc9c174fc66273e178c81e133b3dec4f6e91ce6b471f7eeca096787fd7a` |
| `results/phase3/mask_validation.md` | 1,650 | `ccd8049411f69580c1c40fb61b0a8bdd701946cde333dbc8bdd3137e0ee2f447` |
| `results/phase3/read_benchmark.md` | 766 | `fa51203df61a5292d8ab0aa8b7374ab41ab8c329a3adcf0aa5794ffc0439f2cf` |
| `docs/phase-3.3-extraction-contract.md` | 15,032 | `f4a3ab8cd961e545060c2d46ede08510632d5849767ff1f71ab1686710ca1088` |
| `docs/phase-3.6-indices-contract.md` | 4,834 | `cd100783c3acadcb5f312d136158a02b67ea9cc59d8cf12c948ddb47e724ffe3` |
| `docs/decisions/ADR-001-read-strategy.md` | 2,275 | `4d6c30507cdeff643f1c394e8a66f402ea2b66eee87d247fe554fe65d10d9ca7` |
| `configs/archive.yaml` | 1,591 | `d20d77d4581a4fbf4e663ff858e35ed23f7c73024a954d6841ed2faa0e020aae` |
| `configs/preprocessing.yaml` | 2,491 | `9e421f1216dfb1277ec0af72f22a35fabfea25d0e542b7be02a13a2263019423` |
| `configs/compute.yaml` | 740 | `73dfd60d27ba50c11336fb21638a497e210146c93be17d7145ad5572f3dd41a4` |
| `configs/storage.yaml` | 1,079 | `82beb95ffbb9265b0d576f442f77b406444480b267de75372ebf9409ba69a51f` |
| `configs/temporal.yaml` | 1,427 | `02c25730a8c13cfbfa94e32c48517cdac97e7b00fac29ce3e537ebb4fc27d86c` |
| `configs/boundary.yaml` | 1,635 | `cec063e5d56ccde9eb701d4001cb61d9939e4d7dbce56e9a6c715e0b4ac23785` |

The only additional B2 object is the completion record:

`vizag-geoai/v2/manifests/phase3_archive_manifest.contract-3.7.0.json`

It will reference the existing 92 rasters and two pinned manifests, record exact
versions/hashes for the 16 newly archived payloads, and state the audit's limits.
Its generated size is not yet exact; enforce **65,536 bytes maximum** before PUT.
Maximum new B2 payload: **188,023 bytes**, at most 17 new objects. No existing
manifest is updated. The original reports remain dated snapshots, including
historic statements that publication was pending; the new completion manifest
and separate local receipt provide final publication status.

## Ordered execution after approval

1. Implement a separate plan/publication action; do not change the read-only audit
   into a writer. Store destination/payload policy in configs, not guessed paths.
2. Write fake-backend tests for all failure and protection cases; run the full
   Modal regression suite. Current validated baseline: 315 passed, one existing
   synthetic all-NaN composite warning. Stop/report any error.
3. Recheck all 16 source sizes/hashes against this frozen proposal; refuse drift.
   Refresh the read-only identity audit and require all production objects intact.
   Audit small-manifest reads add 52,501 bytes; no raster payload is read.
4. Use paginated version listings to prove all 17 proposed destinations absent,
   including historical versions/delete markers. Report collisions and stop.
5. Obtain an atomic Modal reservation for this publication and require no other
   writer to the new namespace. This prevents cooperative duplicate jobs; it is
   **not** a claim of atomic B2 create-only semantics against unrelated writers.
6. Upload each absent allowlisted payload once, using ordinary supported B2 PUTs.
   Function/SDK automatic retries remain disabled. No undocumented conditional
   header, overwrite, delete, rollback cleanup, or broad sync is used.
7. HEAD and read back each exact returned version; compare bytes/SHA-256 and
   require a single version. Preserve the original local files unchanged.
8. Publish the bounded completion manifest last, only after all 16 pass. Verify
   its exact bytes/hash and single version by read-back. Refresh storage totals.
9. Create new local completion receipt/report, preserving the existing audit
   snapshots; update README/tracking. Mark Part 3.7 complete only after evidence
   publication passes. Keep the overall Phase 3 gate explicitly pending.

On any error, stop immediately and report which objects were already created.
Leave them intact. A later approved resume must reconcile exact identities rather
than blindly issuing PUTs again. There is no destructive cleanup path.

## Modal workload, storage and estimates

- Source-based `modal run`, remote Python 3.12; no `serialized=True` function.
- One sequential publication worker: 0.25 CPU, 512 MiB RAM, no GPU, 600-second
  timeout, maximum one publication container; regression is a separate job.
- Archive data fits in memory; no raster scratch. Apply the configured storage
  guard if any scratch allocation is introduced. Do not repurpose the physical
  Modal disk quota as a smaller application cap.
- New B2 payload maximum 188,023 bytes. Read-back of newly uploaded objects is
  at most the same size, plus 52,501 bytes for manifest audit and metadata reads.
  Existing raw/processed rasters have zero planned transfer bytes.
- Planning estimate: **3–10 minutes runtime** after implementation/tests, including
  startup and verification; image rebuilds, queueing or provider delays can add time.
- Planning compute allowance: **under US$0.05**, not an account spending cap or
  measured bill. At published Modal rates, 0.25 CPU + 0.5 GiB for 600 seconds is
  approximately US$0.00263 for that worker alone; tests/builds/egress are separate.
- At B2's published US$6.95/TB/month rate, at most 188,023 additional bytes adds
  approximately US$0.00000131/month before account-specific terms. Account
  contracts, rounding, credits and taxes can differ. No claim that all usage is free.

Pricing checked against [Modal pricing](https://modal.com/pricing) and
[Backblaze pricing](https://www.backblaze.com/cloud-storage/pricing).

## Not part of this transfer approval

No Git staging, commit, push, deletion, overwrite, scene re-extraction, index
clipping, feature aggregation, model training or Phase 4 work.

The Phase 3 **visual/scientific gate** remains separate: inspect RGB composites,
observation counts and index samples for all four epochs, review feasibility,
and establish an approved policy for the rare extreme 2018 and slight 2022 index
outliers before downstream aggregation. This archive package neither fixes those
values nor auto-approves their use. A proposal for preview/source-QC reads is
required before those additional raster transfers.

## Approval requested

Approve implementation and this exact copy-only publication workload, including
up to 188,023 new bytes, exact-version verification reads, the two small existing
manifest reads, and no eviction. Approval does not authorize unrelated writers or
Phase 4. If any source changes or a destination is populated, stop and report.

