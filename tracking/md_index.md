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
| `docs/decisions/ADR-001-read-strategy.md` | *(not yet created — Phase 3 Part 3.0)* Records the chosen Sentinel-2 read strategy | Anyone touching `src/preprocessing/` |
| `results/final_report.md` | *(not yet created — Phase 11)* Final write-up assembled from metrics/figures/SHAP plots | Humans, final deliverable |

*(As phases progress, add a row for any new `.md` file — e.g. future ADRs, or any prose report a phase
produces. Most phase reports are `.csv`/`.png` per `plan.md`, but if a phase adds a markdown report, list
it here too.)*
