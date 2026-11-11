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
| `README.md` | **Created (2026-10-10, ahead of Phase 3).** Human-facing project summary, current phase status, repo layout, setup/test instructions. Not yet the "polished" Phase 11 Part 11.3 version (that comes with final results/figures) — update it whenever a phase completes, don't let it go stale. | Humans / new contributors |
| `results/phase2/inventory_report.md` | **Created (Phase 2 Part 2.1, 2026-10-10)** — real B2 inventory: 1,474 objects, 205.85 GB, confirms the raw archive's existence/location/format (A1/A4), lists incomplete mosaic products | Anyone planning Phase 2 Part 2.2+ or Phase 3 |
| `results/phase2/missing_report.md` | **Created (Phase 2 Part 2.2, 2026-10-10)** — only `T44QQE` strictly required by the current buffer; zero Sentinel-2 gaps; DEM/WorldCover/OSM confirmed missing (at the time) | Anyone planning Phase 2 Part 2.4+ |
| `results/phase2/integrity_report.md` | **Created (Phase 2 Part 2.3, 2026-10-10)** — 86/86 required raw scenes verified complete via cheap zip-central-directory reads | Anyone starting Phase 3 preprocessing |
| `results/phase2/fetch_report.md` | **Created (Phase 2 Part 2.4, 2026-10-10)** — DEM/WorldCover/OSM fetch results: 9/9 files verified OK, uploaded to B2 | Anyone using these small datasets in Phase 4 |
| `results/phase2/part_2_5_resume_status.md` | **Created (Phase 2 Part 2.5, 2026-10-10)** — confirms zero Sentinel-2 items remain to fetch | Reference only |
| `results/phase2/part_2_6_backup_status.md` | **Created (Phase 2 Part 2.6, 2026-10-10)** — manifest backup confirmation + resume-drill summary | Reference only |
| `docs/decisions/ADR-001-read-strategy.md` | **Created (Phase 3 Part 3.0, 2026-10-10).** Records the chosen Sentinel-2 read strategy (direct remote windowed reads via `/vsizip/vsis3/`). **Status: Accepted** — user approved 2026-10-10 | Anyone touching `src/preprocessing/` |
| `results/phase3/read_benchmark.md` | **Created (Phase 3 Part 3.0, 2026-10-10).** Real measurements backing ADR-001: wall time, bytes transferred, request count, peak staging disk for both strategies | Reference for ADR-001's rationale |
| `results/phase3/mask_validation.md` | **Created (Phase 3 Part 3.4, 2026-11-05).** Locked SCL mask policy and real 32-scene class-2, dilation and validity measurements | Anyone implementing or reviewing composites and QC |
| `results/phase3/composite_validation.md` | **Created (Phase 3 Part 3.5, 2026-11-06).** Approved coverage policy, immutable output hashes, final epoch coverage and independent read-only audit results | Anyone implementing indices or reviewing composite provenance/QC |
| `docs/phase-3.6-indices-contract.md` | Validated five-index contract, numerical guard/range policy and publication safeguards; production completed | Part 3.6 implementers/reviewers |
| `results/phase3/indices_preflight.md` | Historical preparation and approved workload record; superseded for completion by production validation | Auditing the approval/execution sequence |
| `results/phase3/indices_validation.md` | Production evidence for 20 audited index COGs, manifest hash, per-index QC/range flags and next-step restrictions; structured identities in adjacent `.json` | Anyone implementing archive reporting, features or models |
| `results/phase3/storage_report.md` | Approved read-only Part 3.7 audit: 92 raster identities, two manifest hashes, namespace totals, preserved pilot and storage/gate limitations; exact identities in `storage_audit.json` | Archive, restore and Phase 3 gate reviewers |
| `docs/phase-3.7-archive-completion-plan.md` | Approved and executed 16-file archive proposal, frozen sizes/hashes, new B2 keys, estimates and safeguards; final evidence in archive completion receipt | Archive approval/execution reviewers |
| `results/phase3/archive_completion.md` | Final Part 3.7 publication receipt: 17 verified new objects, 164,253 bytes, unchanged production identities and separate pending Phase 3 gate; versions/hashes in adjacent `.json` | Phase 3 gate, archive and restore reviewers |
| `docs/phase-3-qc-review-plan.md` | Approved four-epoch visual/native QC workload, exact input/output byte limits, source pins, display limitations, publication safeguards and separate human gate | Phase 3 review implementers and user |
| `results/phase3/review.md` | Published exact-version-verified detailed QC report, four figure links, native range/cancellation measurements and the existing feasibility text; gate explicitly pending | User and scientific reviewers |
| `results/phase3/gate_review_summary.md` | Local completion/interpretation summary, actual 2018 ratio example, image-reading notes and remaining decision; publication identities in `gate_review_receipt.json` | User and Phase 3 gate reviewers |
| `docs/phase-4-prediction-quality-plan.md` | Approved Phase 3 outlier policy, accuracy safeguards, completed Part 4.1 contract and link to the next proposal | Phase 4 implementers and user |
| `docs/phase-3.3-extraction-contract.md` | Frozen radiometry, band, nodata, grid and COG extraction contract | Preprocessing implementers/reviewers |
| `results/project_report/README.md` | Reviewed academic report, architecture assets, regeneration instructions and draft limitations | Student, guide and contributors |
| `results/phase4/grid/contract-4.1.0/README.md` | Part 4.1 verified grid summary, preview meaning and Modal run identities | Anyone reviewing or consuming the 500 m grid |
| `docs/phase-4.2-feature-aggregation-proposal.md` | Part 4.2 preflight, DEM correction, full-batch publication, scientific review and approved support policy | Phase 4 implementers and reviewers |
| `results/phase4/features/contract-4.2.0/part4_2_completion.md` | Final Part 4.2 execution, corrected error, verified outputs and 50% support/terrain eligibility rule | Downstream feature consumers |
| `results/final_report.md` | *(not yet created — Phase 11)* Final write-up assembled from metrics/figures/SHAP plots | Humans, final deliverable |

*(As phases progress, add a row for any new `.md` file — e.g. future ADRs, or any prose report a phase
produces. Most phase reports are `.csv`/`.png` per `plan.md`, but if a phase adds a markdown report, list
it here too.)*
