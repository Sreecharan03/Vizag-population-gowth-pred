# Bugs & Fixes Log

Every bug hit during implementation, with root cause and fix, so a future session never re-debugs the same
thing. Log a bug here **before** reporting back to the user for the part it occurred in.

| Date | Symptom | Root cause | Fix | Files affected | Phase/Part |
|---|---|---|---|---|---|
| 2026-09-29 | `boto3` S3 calls to B2 (`head_bucket`/`list_objects_v2`) failed with `InvalidAccessKeyId: Malformed Access Key Id` (403), repeatedly, across multiple regenerated secrets | The credential in use was the **Master Application Key**, whose `keyID` always equals the 12-char Account ID. This is valid for B2's native API (confirmed via direct `b2_authorize_account` call — succeeded every time) but is rejected by B2's S3-compatible gateway, which requires a real non-master Application Key's longer (~25-char) `keyID`. Compounded by an earlier, separate mistake: the `BUCKET-ID` env var holds B2's internal bucket ID (hex), not the bucket *name* the S3 API's `Bucket=` parameter needs. | Created a genuine non-master Application Key scoped to the bucket (25-char keyID, 31-char secret) via B2 console → App Keys → "Add a New Application Key" (not "reset master key"); used the real bucket name (`satilliate-images`, from the console) instead of `BUCKET-ID`'s value. | `.env` (user-side), no repo code | Phase 0, Part 0.4 |
| — | *(none else yet)* | | | | |

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
