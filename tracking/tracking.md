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
| Repo initialized (Phase 0)? | **All 5 parts done** — repo init, path resolution, logging+validation, geospatial stack + B2 connectivity, and the full storage layer (backends/manifest/guard/evict). |
| Current phase | Phase 0 implementation complete (Gate still pending explicit walk-through). **Phase 2 Part 2.1 also done** — started ahead of Phase 1 by the user's explicit choice. 105/105 tests passing. |
| Current part | Phase 1 Part 1.1 (boundary) complete and run for real — fetched from OSM, cross-checked against B2's existing file (exact match, IoU=1.0). `results/phase1_boundary_check.png` generated, **awaiting the user's visual Phase 1 Gate sign-off**. Next: Part 1.2 (`temporal.yaml`/`grid.yaml`/`label.yaml`). 121/121 tests passing. |
| ⚠️ Major finding (2026-10-10, supersedes the 2026-09-29 one below) | Full inventory of `satilliate-images`: **1,474 objects, 205.85 GB**. The raw ~190 GB Sentinel-2 archive **is confirmed present** — 280 `.SAFE.zip` files, 182.82 GB, all 4 epochs (2018/2020/2022/2024), under `data/raw/sentinel2/<year>/`. Also present: 840 already-processed per-scene derivatives (13.59 GB), 346 mosaic composites (5.99 GB, 10 incomplete), boundary geojsons, and WorldPop rasters already fetched. Zero duplicates, zero true junk. Full report: `results/phase2/inventory_report.md`. See `open_questions.md` for A1/A4 now being fully confirmed. |
| Git repo? | Initialized (`main` branch), remote `origin` = `git@github.com:Sreecharan03/Vizag-population-gowth-pred.git`, pushed via a repo-scoped SSH deploy key (see `handoff.md` §1a if it needs recreating on a new Studio) |
| B2 / storage config confirmed? | **Yes, both.** Bucket `satilliate-images`, endpoint `https://s3.us-east-005.backblazeb2.com`, read scope verified. Studio budget: **150 GB max**, everything beyond that stays in B2 only (user, 2026-10-10). |
| ⚠️ Major finding (2026-09-29) | B2 bucket already contains a `vizag-geoai/` prefix with **existing processed outputs** from prior work (boundary GeoJSONs, 2018 masked Sentinel-2 scene stacks) — survived even though the local codebase was deleted. **Do not blindly rebuild Phase 1/3 from scratch** — Phase 2 Part 2.1's inventory must map what's there first. Full detail in `changelog.md` and `open_questions.md`. |
| Standing rules (persistent memory) | (1) All Vizag geo/boundary data must come from verified sources (OSM, official govt, etc.) — never estimated. (2) Routine git commit+push no longer needs per-instance approval. |

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
