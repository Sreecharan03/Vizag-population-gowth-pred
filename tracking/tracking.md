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
| Repo initialized (Phase 0)? | **Parts 0.1–0.3 done**, Part 0.4 **in progress** — repo init, `configs/paths.yaml` + `src/utils/io.py`, `src/utils/logging.py` + `validation.py` (32/32 tests passing). B2 connectivity confirmed working (see below) but Part 0.4 isn't closed out yet — still need geospatial stack install, `configs/b2.yaml`/`storage.yaml`, JP2 driver check, Part 0.4 edge-case tests |
| Current phase | Phase 0 — Project scaffolding & environment (in progress, 3/5 parts complete, 0.4 partially done) |
| Current part | Part 0.4, blocked on one input: **Studio storage budget (`budget_gb`)** — asked, not yet answered. Everything else needed for 0.4 (B2 creds/endpoint/bucket) is confirmed. |
| Git repo? | Initialized (`main` branch), remote `origin` = `git@github.com:Sreecharan03/Vizag-population-gowth-pred.git`, pushed via a repo-scoped SSH deploy key (see `handoff.md` §1a if it needs recreating on a new Studio) |
| B2 / storage config confirmed? | **B2: yes.** Bucket `satilliate-images`, endpoint `https://s3.us-east-005.backblazeb2.com`, read scope verified with a non-master Application Key. **Storage budget: no, still needed.** See [`open_questions.md`](open_questions.md). |
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
