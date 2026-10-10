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
| Tests | **211/211 passing** (`pytest tests/` from repo root) |
| Phase 0 (scaffolding) | **All 5 parts done** — repo init, path resolution, logging+validation, geospatial stack + B2 connectivity, full storage layer (backends/manifest/guard/evict). Implementation complete; formal Gate checklist walk-through with the user hasn't happened as a distinct step, but every item on it is independently satisfied (see `progress.md`). |
| Phase 1 (boundary & config) | **Fully complete, Gate confirmed.** Part 1.1: real GVMC boundary from OpenStreetMap (relation 17493324, 625.15 km²), cross-checked exact match against B2's existing copy, user confirmed `results/phase1_boundary_check.png` 2026-10-10 ("yes"). Part 1.2: `temporal.yaml` (epochs `[2018,2020,2022,2024]` — confirmed against the real B2 inventory, not assumed), `grid.yaml` (500 m), `label.yaml` (5/10/20%, primary 10%). |
| Phase 2 (B2 inventory) | **Fully complete, Gate confirmed.** 6/6 parts done. 2.1 (out of order, ahead of Phase 1): full real inventory, 1,474 objects, 205.85 GB — confirms A1. 2.2: real tile requirements via MGRS — only `T44QQE` strictly required; DEM/WorldCover/OSM confirmed missing (then). 2.3: 86/86 raw scenes integrity-audited OK. 2.4: fetched DEM+WorldCover+OSM, 9/9 verified, uploaded to B2, local preserved. 2.5: re-confirmed zero Sentinel-2 gaps. 2.6: manifests backed up to B2, resume-drill proven by test. **A1–A5 all confirmed** (A5 — B2 pricing — confirmed 2026-10-10: user on a paid plan, pricing accepted). |
| Phase 3 (preprocessing) | **Part 3.0 (read-strategy benchmark) complete, ADR-001 Accepted** — user approved strategy (b), direct remote windowed reads via `/vsizip/vsis3/` (2.8x faster, 98.5% less data, zero staging disk vs. fetch-to-staging). This is the locked-in read approach for the rest of Phase 3. Next: Part 3.1 (scene catalogue & epoch feasibility). |
| Git repo? | Initialized (`main` branch), remote `origin` = `git@github.com:Sreecharan03/Vizag-population-gowth-pred.git`, pushed via a repo-scoped SSH deploy key (see `handoff.md` §1a if it needs recreating on a new Studio). All work through Part 3.0 is committed and pushed — check `git log` for anything past this snapshot's date. |
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

**[`../README.md`](../README.md)** is the human-facing summary (status table, setup instructions, repo
layout) — created 2026-10-10. Keep it in sync whenever a phase's status changes (see `handoff.md` §3).

## Update rule

At the end of every approved "part" (per `plan.md` Section 0's PROPOSE→WAIT→IMPLEMENT→TEST→REPORT→WAIT
loop), and any time a bug is hit/fixed, a config value is confirmed, or a plan deviation is discussed:
update the relevant child file(s) listed above. Treat this as an implicit last step of every REPORT. Full
checklist of what to update is in [`handoff.md`](handoff.md) Section 3.
