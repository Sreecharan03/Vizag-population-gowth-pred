# Handoff Instructions for a New LLM Session (Support)

If you are a new session — new Studio, context reset, or a different LLM entirely — picking this project
up cold, follow these steps in order.

## 1. Orient yourself

1. Read [`tracking.md`](tracking.md) (the hub) — it links everything below and gives the current status
   snapshot.
2. Read [`overview.md`](overview.md) for the condensed project summary and phase list.
3. Read [`progress.md`](progress.md) to know exactly which phase/part is next and whether anything is
   mid-flight.
4. Skim [`architecture.md`](architecture.md) so you understand the storage-tier constraints before touching
   anything data-related.
5. Check [`open_questions.md`](open_questions.md) for anything still waiting on the user — **do not guess
   these values.**
6. Only after all of the above, read [`../plan.md`](../plan.md) in full for the authoritative spec of the
   phase you're about to work on.

## 1a. If you're in a brand-new Studio (git/SSH does not carry over)

The GitHub remote is `git@github.com:Sreecharan03/Vizag-population-gowth-pred.git`, pushed via a
repo-scoped **deploy key** generated on the *previous* Studio's disk (`~/.ssh/id_ed25519_vizag`). SSH keys
are local to the Studio's filesystem and do not follow you to a new Studio automatically. If `git push`
fails with a permission error here, generate a new keypair, ask the user to add it as a deploy key (with
write access) at the repo's Settings → Deploy keys page, verify with `ssh -T git@github.com`, then proceed.
Do not fall back to embedding a token in the remote URL or committing any key material.

## 2. Rules while working

- **All Visakhapatnam geographic/boundary/distance data must come from verified open sources**
  (OpenStreetMap, official GVMC/Survey of India data, Copernicus, WorldPop, ESA WorldCover, etc.). Never
  estimate, approximate, or infer a geographic fact from general knowledge — if a verified source isn't
  reachable, stop and ask the user rather than guessing. This applies especially to Phase 1's boundary
  config and Phase 4's OSM distance aggregation.
- **Routine `git add`/`commit`/`push` to `origin` does not need a separate approval round** once a part is
  implemented, tested, and tracking files are updated — the user pre-authorized this standing practice.
  This does **not** cover destructive git operations (force-push, history rewrite, branch deletion) or
  anything that would stage `.env` or `data/` — those still require explicit confirmation.

- **Never re-download the raw Sentinel-2 data.** ~190 GB is reportedly already downloaded; B2 is the
  source of truth once Assumption A1 is confirmed (see `open_questions.md`).
- **Never guess a config value, credential, bucket name, or storage limit.** If it's marked unconfirmed in
  `open_questions.md`, stop and ask the user.
- **Follow the one-part-at-a-time loop** from `plan.md` Section 0 exactly:
  `PROPOSE (next part only) → WAIT for explicit "yes" → IMPLEMENT only that part → TEST (incl. full
  regression suite) → REPORT in plain language → WAIT again.`
  Never bundle multiple parts into one approval. Never skip a phase gate.
- **Do not re-propose or re-implement a part already marked done** in `progress.md` unless the user
  explicitly asks you to revisit it.
- **Data-safety rules apply to every heavy operation:** print estimated bytes/source/destination/
  reversibility before any download/upload/move/delete and get explicit "yes"; default to `--dry-run`;
  never run a delete-flag command against B2 or `data/`; local raw deletion only via `safe_evict()`.

## 3. Before you report back to the user

- If you hit a bug, log it in [`bugs_and_fixes.md`](bugs_and_fixes.md) (symptom / root cause / fix) —
  **before** reporting the part as done.
- If a config value or assumption got confirmed, update [`open_questions.md`](open_questions.md)
  immediately.
- If a new `.md` file was created anywhere in the repo, add a row to [`md_index.md`](md_index.md).
- Update [`progress.md`](progress.md) (status table + per-part log row) for the part you just finished.
- Add a one-line entry to [`changelog.md`](changelog.md).
- If you locked in an architectural decision (e.g., an ADR), record it in
  [`architecture.md`](architecture.md)'s decisions log.

Treat "update the tracking files" as an implicit last step of every REPORT in the plan's workflow loop —
this is what makes the next session's handoff free of manual re-explanation.

## 4. If the plan itself seems wrong or incomplete

Do not silently improvise a fix. Stop, flag it to the user, propose the specific plan change, wait for
approval, then update both `../plan.md` and this file's changelog to reflect the agreed change.
