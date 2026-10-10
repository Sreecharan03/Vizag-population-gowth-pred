# Vizag GeoAI — Tracking Hub

**Read this file FIRST in any new session (especially a new Lightning Studio).** This directory is the
persistent memory of the project — a set of files that let a brand-new LLM session, with zero conversation
history, pick up exactly where the last session left off with no manual re-explanation from the user.

[`../plan.md`](../plan.md) at repo root is the *static* operating manual — what to build and how. The files
in this directory are the *dynamic* record of what has actually happened. If the two ever disagree,
`plan.md` is authoritative on *what to build*; this directory is authoritative on *what's been done so far*.

## Current Status Snapshot

| Field | Value |
|---|---|
| Last updated | 2026-10-10 |
| Studio | Lightning AI Studio, workspace `/teamspace/studios/this_studio` |
| Tests | **196/196 passing** (`pytest tests/` from repo root) |
| Phase 0 (scaffolding) | **All 5 parts done** — repo init, path resolution, logging+validation, geospatial stack + B2 connectivity, full storage layer (backends/manifest/guard/evict). Implementation complete; formal Gate checklist walk-through with the user hasn't happened as a distinct step, but every item on it is independently satisfied (see `progress.md`). |
| Phase 1 (boundary & config) | **Fully complete, Gate confirmed.** Part 1.1: real GVMC boundary from OpenStreetMap (relation 17493324, 625.15 km²), cross-checked exact match against B2's existing copy, user confirmed `results/phase1_boundary_check.png` 2026-10-10 ("yes"). Part 1.2: `temporal.yaml` (epochs `[2018,2020,2022,2024]` — confirmed against the real B2 inventory, not assumed), `grid.yaml` (500 m), `label.yaml` (5/10/20%, primary 10%). |
| Phase 2 (B2 inventory) | **All 6 parts done — Phase 2 fully implemented.** 2.1 (out of order, ahead of Phase 1): full real inventory, 1,474 objects, 205.85 GB — confirms A1 (280 `.SAFE.zip` raw archives, 182.82 GB, all 4 epochs). 2.2: real tile requirements via the MGRS grid — only `T44QQE` strictly required; DEM/WorldCover/OSM confirmed missing. 2.3: 86/86 required raw scenes integrity-audited OK. 2.4: fetched DEM+WorldCover+OSM (public/no-auth sources), 9/9 verified, uploaded to B2, local preserved. 2.5: re-confirmed zero Sentinel-2 gaps, nothing to fetch. 2.6: backed up manifests to B2, resume-drill guarantee proven by test. **⚠️ Phase 2 Gate not fully satisfied yet — Assumption A5 (B2 pricing) is still unconfirmed; `plan.md` requires the user to confirm A1–A5 at this gate.** |
| Git repo? | Initialized (`main` branch), remote `origin` = `git@github.com:Sreecharan03/Vizag-population-gowth-pred.git`, pushed via a repo-scoped SSH deploy key (see `handoff.md` §1a if it needs recreating on a new Studio). All work through Phase 1 (complete) is committed and pushed — check `git log` for anything past this snapshot's date. |
| B2 / storage config | **Fully confirmed.** Bucket `satilliate-images`, endpoint `https://s3.us-east-005.backblazeb2.com`, read scope verified against real data. Studio budget: **150 GB max** in `configs/storage.yaml` — everything beyond that stays in B2 only. |
| Standing rules (persistent memory, apply every session) | (1) All Vizag geo/boundary data must come from verified sources (OSM, official govt, etc.) — never estimated; enforced in `src/acquisition/boundary.py`. (2) Routine git commit+push no longer needs per-instance approval — do it after every completed part. |

Full detail: [`progress.md`](progress.md).

## Files in this directory

| File | What's in it |
|---|---|
| [`overview.md`](overview.md) | Condensed project overview: pipeline, constraints, phase list |
| [`architecture.md`](architecture.md) | Technical architecture: storage tiers, backend abstraction, repo layout, config status, decisions log |
| [`progress.md`](progress.md) | Phase-by-phase status table and per-part completion log |
| [`changelog.md`](changelog.md) | Reverse-chronological log of decisions and completed parts |
| [`bugs_and_fixes.md`](bugs_and_fixes.md) | Bug log (symptom/root cause/fix) + known plan-level risks to watch for |
| [`open_questions.md`](open_questions.md) | Unconfirmed assumptions/config values only the user can supply — never guess these |
| [`md_index.md`](md_index.md) | Index of every markdown file in the whole repo |
| [`handoff.md`](handoff.md) | Step-by-step instructions for a new/cold session: what to read, what rules to follow, what to update before reporting back |

**Recommended read order for a new session:** this file → `overview.md` → `progress.md` →
`architecture.md` → `open_questions.md` → `handoff.md` → then `../plan.md` in full.

## Update rule

At the end of every approved "part" (per `plan.md` Section 0's PROPOSE→WAIT→IMPLEMENT→TEST→REPORT→WAIT
loop), and any time a bug is hit/fixed, a config value is confirmed, or a plan deviation is discussed:
update the relevant child file(s) listed above. Treat this as an implicit last step of every REPORT. Full
checklist of what to update is in [`handoff.md`](handoff.md) Section 3.
