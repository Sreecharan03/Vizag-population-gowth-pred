# Bugs & Fixes Log

Every bug hit during implementation, with root cause and fix, so a future session never re-debugs the same
thing. Log a bug here **before** reporting back to the user for the part it occurred in.

| Date | Symptom | Root cause | Fix | Files affected | Phase/Part |
|---|---|---|---|---|---|
| — | *(none yet — implementation has not started)* | | | | |

## Known plan-level risks to watch for (not bugs yet, but flagged in `plan.md` as likely failure points)

These aren't bugs — they're places `plan.md` itself calls out as high-risk. Move a row to the table above
if/when it actually manifests as an issue.

| Risk | Where it's called out in `plan.md` | Why it matters |
|---|---|---|
| Feature leakage across epochs | Phase 6, Part 6.1 | "the single most likely way this project fails a viva" — leakage check gate cannot be skipped |
| Epoch has only L1C or too few clear L2A scenes | Phase 3, D10 / Part 3.1 | Could invalidate the temporal design (2018/2020/2022/2024-25) if ignored |
| SCL misclassifying bright/dark roofs as cloud/shadow | Phase 3, Part 3.4 | Known limitation; must be documented, not silently accepted |
| Mixed Sentinel-2 processing baselines (BOA_ADD_OFFSET) | Phase 3, D5 | 2018 vs 2024 NDBI difference could reflect a processing change, not real growth, if offset isn't applied |
| B2 assumption A1 (raw data actually in B2, not just local/external drive) | Phase 2, Part 2.1 | If false, first job becomes uploading 190 GB to B2 before any old disk is deleted |
