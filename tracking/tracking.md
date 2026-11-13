# Vizag GeoAI — Tracking Hub

**Read this file FIRST in any new session.** This directory is the
persistent memory of the project — a set of files that let a brand-new LLM session, with zero conversation
history, pick up exactly where the last session left off with no manual re-explanation from the user.

[`../plan.md`](../plan.md) at repo root is the *static* operating manual — what to build and how. The files
in this directory are the *dynamic* record of what has actually happened. If the two ever disagree,
`plan.md` is authoritative on *what to build*; this directory is authoritative on *what's been done so far*.

## Current Status Snapshot

| Field | Value |
|---|---|
| Last updated | 2026-11-13 |
| Compute | Modal only — profile `sankar132095`, environment `main`; local checkout is source/control-plane only |
| Persistent storage | Backblaze B2 only; Modal container disk is ephemeral scratch |
| Tests | **414 passed, one known synthetic all-NaN warning** in Modal on 2026-11-13, including Dynamic World identity, download and two-band QC-mask regression coverage. |
| Phase 0 (scaffolding) | **All 5 parts done** — repo init, path resolution, logging+validation, geospatial stack + B2 connectivity, full storage layer (backends/manifest/guard/evict). Implementation complete; formal Gate checklist walk-through with the user hasn't happened as a distinct step, but every item on it is independently satisfied (see `progress.md`). |
| Phase 1 (boundary & config) | **Fully complete, Gate confirmed.** Part 1.1: real GVMC boundary from OpenStreetMap (relation 17493324, 625.15 km²), cross-checked exact match against B2's existing copy, user confirmed `results/phase1_boundary_check.png` 2026-10-10 ("yes"). Part 1.2: `temporal.yaml` (epochs `[2018,2020,2022,2024]` — confirmed against the real B2 inventory, not assumed), `grid.yaml` (500 m), `label.yaml` (5/10/20%, primary 10%). |
| Phase 2 (B2 inventory) | **Fully complete, Gate confirmed.** 6/6 parts done. 2.1 (out of order, ahead of Phase 1): full real inventory, 1,474 objects, 205.85 GB — confirms A1. 2.2: real tile requirements via MGRS — only `T44QQE` strictly required; DEM/WorldCover/OSM confirmed missing (then). 2.3: 86/86 raw scenes integrity-audited OK. 2.4: fetched DEM+WorldCover+OSM, 9/9 verified, uploaded to B2, local preserved. 2.5: re-confirmed zero Sentinel-2 gaps. 2.6: manifests backed up to B2, resume-drill proven by test. **A1–A5 all confirmed** (A5 — B2 pricing — confirmed 2026-10-10: user on a paid plan, pricing accepted). |
| Phase 3 (preprocessing) | **Complete: 8/8 and user gate-confirmed (2026-11-10).** Review evidence and the affected-index-only outlier rule are approved. Original rasters remain unchanged; Part 4.2 subsequently implemented the policy. |
| Phase 4 (grid & features) | **Complete: 4/4 technically complete.** Contract 4.4.0 contains 25,484 cell-year rows, 69 columns, all 6,371 cells and four epochs; 6,355 cells are model-eligible and 16 remain explicitly ineligible. |
| Phase 5 (labels) | **Part 5.1 in progress.** Fixed index rules failed the scientific gate. Earth Engine uses a dedicated service account plus a custom least-privilege `earthengine.thumbnails.create` role. The create-only 2022 Dynamic World pilot is published and reviewed. Its 11.86% mode-built fraction and WorldCover audit (precision 0.451, recall 0.902) require stratified spatial validation before any four-epoch batch. Parts 5.2/5.3 are unstarted. |
| Git repo? | Reconnected safely on 2026-11-04. Local `main` is attached to `origin/main`; remote is `https://github.com/Sreecharan03/Vizag-population-gowth-pred.git`. The user approved documenting and publishing the recovered checkpoint on 2026-11-06. |
| B2 / storage config | **Fully confirmed.** Bucket `satilliate-images`, endpoint `https://s3.us-east-005.backblazeb2.com`, read scope verified against real data. Studio budget: **150 GB max** in `configs/storage.yaml` — everything beyond that stays in B2 only. |
| Infrastructure version | **0.2.0** — Modal compute + B2 persistent storage migration remotely verified |
| Standing rules (persistent memory, apply every session) | Use verified geographic sources; follow one-part approvals and explicit transfer approval; preserve B2 and local files. User authorized this checkpoint's commit/push on 2026-11-09; follow latest instructions for future releases. |

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

**[`../README.md`](../README.md)** is the human-facing summary (status table, setup instructions, repo
layout) — created 2026-10-10. Keep it in sync whenever a phase's status changes (see `handoff.md` §3).

## Update rule

At the end of every approved "part" (per `plan.md` Section 0's PROPOSE→WAIT→IMPLEMENT→TEST→REPORT→WAIT
loop), and any time a bug is hit/fixed, a config value is confirmed, or a plan deviation is discussed:
update the relevant child file(s) listed above. Treat this as an implicit last step of every REPORT. Full
checklist of what to update is in [`handoff.md`](handoff.md) Section 3.
