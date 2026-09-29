# Phase-by-Phase Progress

**Read after [`tracking.md`](tracking.md).** This is the live status table against the 12 phases defined in
[`../plan.md`](../plan.md). Update the Status / Parts-done / Gate columns as work happens — this table is
the fastest way for a new session to see exactly where things stand.

Statuses: `Not started` / `In progress` / `Blocked` / `Gate pending` / `Complete`.

| Phase | Title | Status | Parts done | Phase Gate confirmed? |
|---|---|---|---|---|
| 0 | Project scaffolding & environment | In progress | 2/5 | No |
| 1 | Study boundary & configuration | Not started | 0/2 | No |
| 2 | B2 inventory, reconciliation & acquisition | Not started | 0/6 | No |
| 3 | Advanced Sentinel-2 preprocessing | Not started | 0/8 | No |
| 4 | Grid construction & feature aggregation | Not started | 0/4 | No |
| 5 | Label generation | Not started | 0/3 | No |
| 6 | Dataset assembly & split | Not started | 0/4 | No |
| 7 | Baseline model (E1) | Not started | 0/2 | No |
| 8 | Multimodal models & ablation (E2–E4) | Not started | 0/3 | No |
| 9 | Explainability (SHAP) | Not started | 0/3 | No |
| 10 | 2030 prediction & Infrastructure Pressure Index | Not started | 0/3 | No |
| 11 | Final report, reproducibility & documentation | Not started | 0/3 | No |

## Current position (detail)

- **Current phase:** Phase 0, in progress.
- **Current part:** Part 0.2 (`configs/paths.yaml` + `resolve_path()`) complete. Part 0.3
  (`src/utils/logging.py` + `validation.py`) is next — not yet proposed/approved.
- **Blocking on user input?** Not for Part 0.3. Parts 0.4–0.5 and Phase 2 will still need B2 credentials,
  bucket name, and the Studio storage budget — see [`open_questions.md`](open_questions.md).

## Per-part log

As each part is implemented, add a row here (most recent first) with a one-line result. Full narrative
detail (what broke, what was decided) belongs in [`changelog.md`](changelog.md) and
[`bugs_and_fixes.md`](bugs_and_fixes.md); this table stays terse and scannable.

| Part | Date completed | Tests passing? | One-line result |
|---|---|---|---|
| 0.1 | 2026-09-29 | N/A (no tests specified for this part; verified by `git status` clean + `pyproject.toml` valid) | Repo init: `pyproject.toml` (Python 3.11–3.12, Part-0.1 core libs pinned), `.gitignore` (secrets, data/, models/, predictions/, logs/, Studio env noise), `git init` + GitHub remote (`origin`) wired via a repo-scoped SSH deploy key. |
| 0.2 | 2026-09-29 | 10/10 passing (`pytest tests/`) | `configs/paths.yaml` (every path from `plan.md` Section 1) + `src/utils/io.py`: `find_repo_root()` (cwd-independent), `load_config()`, `resolve_path()`, `ConfigError`, and `find_duplicate_paths()` for the "two keys, one path" edge case (warns, doesn't fail). Added `tests/unit/test_io.py` and the Phase-0-mandated `tests/unit/test_no_hardcoded_paths.py` lint test (includes a self-check that the detector isn't vacuous). Installed `pytest`+`pyyaml`; added `pyyaml` to `pyproject.toml`. |
