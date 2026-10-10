# Markdown Files Index

Every `.md` file in the project, what it's for, and who should read it. Update this table whenever a
markdown file is added, moved, or removed anywhere in the repo — not just under `tracking/`.

| Path | Purpose | Audience |
|---|---|---|
| `plan.md` (repo root) | Static operating manual: full phase-by-phase spec, edge cases, tests, phase gates | Any LLM session; read after the `tracking/` files |
| `tracking/tracking.md` | Hub/index — current status snapshot, links to every file below | Any LLM session; **read this FIRST** |
| `tracking/overview.md` | Condensed project overview and phase list | Any LLM session, second read |
| `tracking/architecture.md` | Technical architecture: storage tiers, backend abstraction, repo layout, config status, ADR log | Anyone implementing `src/` |
| `tracking/progress.md` | Phase-by-phase status table + per-part log | Anyone checking "what's done" |
| `tracking/changelog.md` | Reverse-chronological record of decisions and completed parts | Anyone wanting project history |
| `tracking/bugs_and_fixes.md` | Bug log (symptom/root cause/fix) + known plan-level risks | Anyone debugging or about to touch a risky area |
| `tracking/open_questions.md` | Unconfirmed assumptions and values only the user can supply | Anyone about to touch B2, storage config, or the boundary |
| `tracking/md_index.md` (this file) | Index of every markdown file in the repo | Anyone looking for a doc |
| `tracking/handoff.md` | Step-by-step instructions for a new/cold LLM session picking up the project | A brand-new session, read right after `tracking.md` |
| `README.md` | *(not yet created — Phase 0/11)* Short human-facing project summary | Humans / new contributors |
| `results/phase2/inventory_report.md` | **Created (Phase 2 Part 2.1, 2026-10-10)** — real B2 inventory: 1,474 objects, 205.85 GB, confirms the raw archive's existence/location/format (A1/A4), lists incomplete mosaic products | Anyone planning Phase 2 Part 2.2+ or Phase 3 |
| `results/phase2/missing_report.md` | **Created (Phase 2 Part 2.2, 2026-10-10)** — only `T44QQE` strictly required by the current buffer; zero Sentinel-2 gaps; DEM/WorldCover/OSM confirmed missing (at the time) | Anyone planning Phase 2 Part 2.4+ |
| `results/phase2/integrity_report.md` | **Created (Phase 2 Part 2.3, 2026-10-10)** — 86/86 required raw scenes verified complete via cheap zip-central-directory reads | Anyone starting Phase 3 preprocessing |
| `results/phase2/fetch_report.md` | **Created (Phase 2 Part 2.4, 2026-10-10)** — DEM/WorldCover/OSM fetch results: 9/9 files verified OK, uploaded to B2 | Anyone using these small datasets in Phase 4 |
| `results/phase2/part_2_5_resume_status.md` | **Created (Phase 2 Part 2.5, 2026-10-10)** — confirms zero Sentinel-2 items remain to fetch | Reference only |
| `results/phase2/part_2_6_backup_status.md` | **Created (Phase 2 Part 2.6, 2026-10-10)** — manifest backup confirmation + resume-drill summary | Reference only |
| `docs/decisions/ADR-001-read-strategy.md` | *(not yet created — Phase 3 Part 3.0)* Records the chosen Sentinel-2 read strategy | Anyone touching `src/preprocessing/` |
| `results/final_report.md` | *(not yet created — Phase 11)* Final write-up assembled from metrics/figures/SHAP plots | Humans, final deliverable |

*(As phases progress, add a row for any new `.md` file — e.g. future ADRs, or any prose report a phase
produces. Most phase reports are `.csv`/`.png` per `plan.md`, but if a phase adds a markdown report, list
it here too.)*
