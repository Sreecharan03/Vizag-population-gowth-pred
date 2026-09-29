# Changelog

Reverse-chronological. One entry per approved part, config value set, plan deviation, or other notable
decision. Keep entries short (1–3 lines) — narrative "why" belongs here, but implementation detail belongs
in the code/tests themselves, and status belongs in [`progress.md`](progress.md).

| Date | Entry |
|---|---|
| 2026-09-29 | **New standing rule:** all Visakhapatnam geographic/boundary/distance data must come from verified open sources (OpenStreetMap, official GVMC/Survey of India, Copernicus, WorldPop, ESA WorldCover, etc.) — never estimated or fabricated. Applies especially to Phase 1 boundary work and Phase 4 OSM distance aggregation. Saved as a persistent memory (`feedback_verified_geodata`). |
| 2026-09-29 | **New standing rule:** routine `git add`/`commit`/`push` to the project's GitHub repo no longer needs per-instance approval (user: "we need to push and commit correctly ... i wont say multiple times"). Destructive git ops (force-push, history rewrite) and anything touching `.env`/`data/` still require explicit confirmation. Saved as a persistent memory (`feedback_git_workflow`). |
| 2026-09-29 | Wired GitHub remote `origin` → `git@github.com:Sreecharan03/Vizag-population-gowth-pred.git`. No SSH key or `gh` auth existed in this Studio; generated a dedicated ed25519 keypair (`~/.ssh/id_ed25519_vizag`) and the user added it as a **repo-scoped deploy key with write access** (least-privilege — not an account-wide key). Verified via `ssh -T git@github.com`. **Note:** this key lives only on this Studio's disk — a brand-new Studio will need a new deploy key added (see `handoff.md`). |
| 2026-09-29 | Implemented Phase 0 **Part 0.1** (repo init): `pyproject.toml` (Python 3.11–3.12, Part-0.1 dependency list from `plan.md`), `.gitignore` (secrets, `data/`, `models/`, `predictions/`, `logs/`, plus Studio shell/IDE noise since the repo root doubles as `$HOME` here), `git init -b main`, local git identity set. First commit + push follows immediately after this changelog update. |
| 2026-09-29 | Split the single `tracking.md` into child files under `tracking/`: `overview.md`, `architecture.md`, `progress.md`, `changelog.md` (this file), `bugs_and_fixes.md`, `open_questions.md`, `md_index.md`, `handoff.md`. `tracking.md` is now a short hub/index that links to each. |
| 2026-09-29 | Created `tracking/tracking.md` as the persistent cross-session handoff document (later split into child files, see entry above). No implementation work done yet — repo is pre-Phase-0. |
