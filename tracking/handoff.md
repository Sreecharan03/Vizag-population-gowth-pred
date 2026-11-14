# Handoff Instructions for a New LLM Session (Support)

If you are a new session — new machine, context reset, or a different LLM entirely — picking this project
up cold, follow these steps in order.

## 1. Orient yourself

1. Read [`tracking.md`](tracking.md) (the hub) — it links everything below and gives the current status
   snapshot.
2. Read [`overview.md`](overview.md) for the condensed project summary and phase list.
3. Read [`progress.md`](progress.md) to know exactly which phase/part is next and whether anything is
   mid-flight.
4. Skim [`architecture.md`](architecture.md) so you understand the storage-tier constraints before touching
   anything data-related.
5. Check [`open_questions.md`](open_questions.md) for anything still waiting on the user — **do not guess
   these values.**
6. Only after all of the above, read [`../plan.md`](../plan.md) in full for the authoritative spec of the
   phase you're about to work on.

## 1a. Runtime and Git context (v0.2.0)

All project compute/tests run in Modal and all persistent runtime artifacts live in Backblaze B2. The local
checkout is source/control-plane only. Use Modal profile `sankar132095`, environment `main`, and inject B2
credentials through the named Modal Secret `vizag-b2`; never mount or upload `.env`.

Git metadata was safely restored on 2026-11-04. The user explicitly approved committing and pushing the
recovered checkpoint to `origin/main` on 2026-11-09 and renewed that authorization on
2026-11-10, requesting accurate documentation and a professional README first.
Verify the current commit and remote with Git;
do not infer them from this historical note. Never force-push or include credentials or runtime data.

Current checkpoint (2026-11-14): Phases 3, 4 and 5 are complete. Corrected Dynamic World contract
5.1.1, transition-label contract 5.2.0 and sensitivity contract 5.3.0 are populated and immutable.
The user explicitly confirmed 10 percentage points as the primary growth threshold after reviewing
5%/10%/20% sensitivity. Full Modal regression **436 passed, one known synthetic all-NaN warning**.
Phase 6 dataset assembly and leakage validation is next. Do not rerun populated Phase 5 contracts.
User approved Part 3.6 and the production run created 20 index COGs (1,309,726,569 bytes), independently
downloaded/hashed and fully pixel-audited them, then published one exact-byte-verified 17,788-byte manifest.
Read `results/phase3/indices_validation.md`, its machine-readable `.json`, and
`docs/phase-3.6-indices-contract.md` before proceeding.

**Known scientific QC and approved handling:** 2018 contains rare extreme finite index outliers;
2022 contains 12 slight outliers each in NDVI/NDBI/NDWI. The user has approved the review evidence
and affected-index-only exclusion of already-flagged values from future feature means. Preserve
original COGs, record per-cell exclusions/usable coverage, keep empty means missing, and do not
clip or automatically drop whole cells. Policy: `configs/feature_aggregation.yaml`. Its actual
Part 4.2 implements this rule. Approved eligibility requires >=50% usable support for every
required index/epoch plus valid elevation and slope; all QC rows remain preserved.
17 near-zero 2018 NDVI denominators became nodata under the approved guard.

**Phase 3 gate review evidence and the specific downstream rule are now user-approved.** Read
`results/phase3/gate_review_summary.md`, `review.md`, `range_review.json`/`.csv`, all four
`qc_<epoch>.png` files and `gate_review_receipt.json`. Approved run
`ap-TzE1Q1IpjSls5mOpRKwUU0` used 2,778,034,701 input bytes and published eight exact-version/
hash-verified artifacts totaling 5,389,770 bytes; stored/readback/local viewing payload is
16,169,310 bytes (within 48 MiB). Native unique outliers: 2018=11,378, 2022=12, others=0.
All flagged ratios have a negative term; severe 2018 cases show cancellation. A composite-only
review does not establish individual source-scene physical causes. Only affected-index exclusion
of flagged values is approved: no clipping, broader negative-reflectance mask or new denominator
threshold. Published review/receipt pending flags are immutable historical snapshots, superseded
by the later decision in `docs/phase-4-prediction-quality-plan.md`. Part 4.1 completed and was
visually approved on 2026-11-11. Part 4.2 was later separately approved and completed; do not infer permission for later parts. Do not rerun `part3-gate-review`, overwrite its outputs or clear the
successful persistent reservation `vizag-phase3-gate-review-v1`. Output manifest is
`vizag-geoai/v2/manifests/phase3_gate_review.v1.json`.

Authentication works when the command has network access; do not recreate credentials for sandbox
connectivity failures. Source/output contract 3.6.0 is populated: do not rerun `part3-indices-build`.
Per-epoch persistent Modal reservations retain successful results; no lock is silently removed.
**Part 3.7 read-only audit is approved and passed.** Read `results/phase3/storage_report.md`
and `storage_audit.json`: 92 expected rasters present, 13,419,102,871 bytes; 100 v2 objects and
versions, zero delete markers. Two manifests byte-hashed; no raster payload read or B2 write.
**Part 3.7 publication is also approved and complete.** Read `results/phase3/archive_completion.md`
and `.json`: 16 frozen snapshots (122,487 bytes) plus one completion manifest (41,766 bytes),
all exact-version read-back/hash verified; 164,253 new bytes. V2 now has 117 objects/versions,
13,795,150,258 bytes, zero delete markers. Existing production identities unchanged.
The original audit reports are preserved historical snapshots; pending-publication wording
in them is superseded by the completion receipt. Phase 3 gate was subsequently user-approved;
Part 4.1 is complete and visually approved. Do not rerun `part3-archive-publish` or remove its persistent
reservation: the successful result remains in `vizag-phase3-archive-publication-3-7-0`.
The 16 allowlisted source files remain frozen by `configs/archive_publication.yaml`.
Use source-based `modal run -e main modal_app.py --action part3-storage-audit`, not an in-memory
`serialized=True` function: local Python 3.11 can launch the approved remote Python 3.12 image.
The active workspace is `sankar132095`; do not reinstall Python or recreate credentials to fix
the previously introduced serialization mismatch. The fixed test suite is self-contained and
does not depend on local markdown reports being present in the remote image.

**Part 4.1 grid publication is complete; do not rerun it.** Modal run
`ap-0XT8PeoGerm8Mu7VlDv49j` restored the pinned 32,768-byte boundary and created 6,371 fixed
500 m cells (5,912 full, 459 edge). Four `contract-4.1.0` objects totaling 2,936,091 bytes were
created once and exact-version/read-back/hash verified. The persistent reservation is
`vizag-phase4-grid-4-1-0`; preserve it. Local evidence is under
`results/phase4/grid/contract-4.1.0/`. The user approved the preview on 2026-11-11.
Part 4.2 is complete. Do not rerun its populated six-output contract.

**Phase 5 is complete and gate-approved; do not rerun populated contracts 5.1.1, 5.2.0 or 5.3.0.** The original
contract 5.1.0 rectangle-wide pilot is preserved but scientifically superseded. Contract 5.1.1
applies the exact buffered GVMC AOI and contains four epoch COG sets. Final cell aggregation produced
25,484 unique rows under `vizag-geoai/v2/derived/labels/contract-5.1.1/`; 6,368 cells have evidence
and three tiny edge slivers are explicitly unsupported. Final read-only review run
`ap-UIhfWQiQ18QWOb2OEsEJa4` passed. Part 5.2 preserved 19,113 cell-transition rows and passed
exact-version review. Part 5.3 validated 57,339 sensitivity rows; the user confirmed 10 percentage
points as primary. Phase 6 is next; do not treat WorldCover as training truth or select the target
using downstream model scores. Read `docs/phase-5.2-completion.md` and
`docs/phase-5.3-completion.md` before proceeding.

**Part 4.2a metadata-only preflight completed; do not mistake it for aggregation.** Run
`ap-Aa5eCAKVU7wPh0pwIn3I4W` read 52,147 bytes from three pinned small objects, pinned all 20 index
COGs and both DEM versions, read zero raster payload bytes and made zero B2 writes. Both legacy DEM
uploads lacked SHA-256 metadata; the later strict payload gate resolved that historical blocker.
Corrected full batch `ap-Dz1CfM1F43J7c3bAnkHkcH` published six verified outputs, manifest last.
Read-only review `ap-wKjNJgIpGetKO9w1nqLs01` approved >=50% support for every required index/epoch
plus valid elevation/slope, retaining 6,355 cells. Preserve all rows and QC fields. Evidence is in
`results/phase4/features/contract-4.2.0/`; Part 4.3 is next. See
`docs/phase-4.2-feature-aggregation-proposal.md`.

The reviewed 19-page academic report and vector diagrams are in `results/project_report/`. Identity
fields remain placeholders. Dashboard illustrations and the pressure-index discussion are proposals;
no trained model or real predictions have been built. A separate public demo UI now exists in
`sites/vizag-growth-demo/`, with its own source repository and real geographic layers but fictional
analytics. A two-year model is not yet a validated 2030 forecast.

### Historical SSH note

The current remote is HTTPS: `https://github.com/Sreecharan03/Vizag-population-gowth-pred.git`.
The historical remote was `git@github.com:Sreecharan03/Vizag-population-gowth-pred.git`, pushed via a
repo-scoped **deploy key** generated on the *previous* Studio's disk (`~/.ssh/id_ed25519_vizag`). SSH keys
are local to the Studio's filesystem and do not follow you to a new Studio automatically. If `git push`
fails with a permission error here, stop and report the authentication blocker. Ask for approval
before provisioning any replacement credential or changing the remote/authentication configuration.
Do not fall back to embedding a token in the remote URL or committing any key material.

## 2. Rules while working

- **All Visakhapatnam geographic/boundary/distance data must come from verified open sources**
  (OpenStreetMap, official GVMC/Survey of India data, Copernicus, WorldPop, ESA WorldCover, etc.). Never
  estimate, approximate, or infer a geographic fact from general knowledge — if a verified source isn't
  reachable, stop and ask the user rather than guessing. This applies especially to Phase 1's boundary
  config and Phase 4's OSM distance aggregation.
- **Git authorization:** the user explicitly authorized this checkpoint's commit/push on 2026-11-09.
  Follow the latest user instructions for later releases; older blanket authorizations do not override
  a subsequent request to obtain approval.
  This does **not** cover destructive git operations (force-push, history rewrite, branch deletion) or
  anything that would stage `.env` or `data/` — those still require explicit confirmation.

- **Never re-download the raw Sentinel-2 data.** Confirmed in B2: 280 `.SAFE.zip` scenes, 182.82 GB,
  all 4 planned epochs, integrity-audited OK (Phase 2 Parts 2.1/2.3). B2 is the permanent source of truth.
- **Never guess a config value, credential, bucket name, or storage limit.** If it's marked unconfirmed in
  `open_questions.md`, stop and ask the user.
- **Follow the one-part-at-a-time loop** from `plan.md` Section 0 exactly:
  `PROPOSE (next part only) → WAIT for explicit "yes" → IMPLEMENT only that part → TEST (incl. full
  regression suite) → REPORT in plain language → WAIT again.`
  Never bundle multiple parts into one approval. Never skip a phase gate.
- **Do not re-propose or re-implement a part already marked done** in `progress.md` unless the user
  explicitly asks you to revisit it.
- **Data-safety rules apply to every heavy operation:** print estimated bytes/source/destination/
  reversibility before any download/upload/move/delete and get explicit "yes"; default to `--dry-run`;
  never run a delete-flag command against B2 or `data/`; local raw deletion only via `safe_evict()`.

## 3. Before you report back to the user

- If you hit a bug, log it in [`bugs_and_fixes.md`](bugs_and_fixes.md) (symptom / root cause / fix) —
  **before** reporting the part as done.
- If a config value or assumption got confirmed, update [`open_questions.md`](open_questions.md)
  immediately.
- If a new `.md` file was created anywhere in the repo, add a row to [`md_index.md`](md_index.md).
- Update [`progress.md`](progress.md) (status table + per-part log row) for the part you just finished.
- Add a one-line entry to [`changelog.md`](changelog.md).
- If you locked in an architectural decision (e.g., an ADR), record it in
  [`architecture.md`](architecture.md)'s decisions log.
- If a phase completed or its real status changed materially, update `../README.md`'s status table too —
  it's a human-facing summary and goes stale fast otherwise.
- **Before every `git add`/commit, run the real secret-scan** (`src.utils.secrets.scan_files_for_leaked_secrets`
  against every staged file, with `get_known_secret_values()` loaded from `.env` via `load_dotenv`) — this
  has caught nothing so far, but it's cheap insurance and is now standard practice, not optional.

Treat "update the tracking files" as an implicit last step of every REPORT in the plan's workflow loop —
this is what makes the next session's handoff free of manual re-explanation.

## 4. If the plan itself seems wrong or incomplete

Do not silently improvise a fix. Stop, flag it to the user, propose the specific plan change, wait for
approval, then update both `../plan.md` and this file's changelog to reflect the agreed change.
