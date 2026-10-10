# Vizag GeoAI

Explainable multimodal GeoAI system for Visakhapatnam (Vizag), India — predicts urban expansion and
infrastructure pressure from Sentinel-2 satellite time series, population data, OpenStreetMap, and terrain,
using a leakage-safe, temporally-validated ML pipeline with SHAP explainability.

**Full build plan:** [`plan.md`](plan.md) — the authoritative, phase-by-phase operating manual.
**Live project status:** [`tracking/`](tracking/) — current phase/part, what's confirmed, what's still
open. Start at [`tracking/tracking.md`](tracking/tracking.md).

## Status (as of 2026-10-10)

| Phase | Status |
|---|---|
| 0 — Project scaffolding & environment | ✅ Complete |
| 1 — Study boundary & configuration | ✅ Complete, gate-confirmed |
| 2 — B2 inventory, reconciliation & acquisition | ✅ Complete, gate-confirmed |
| 3 — Advanced Sentinel-2 preprocessing | 🔄 Starting |
| 4–11 | Not started |

**196/196 tests passing.** See [`tracking/progress.md`](tracking/progress.md) for the full phase/part
breakdown.

### What's confirmed about the data so far

- Raw Sentinel-2 archive: **280 scenes, 182.82 GB**, zipped `.SAFE.zip` format, covering all 4 planned
  epochs (2018, 2020, 2022, 2024) for the tile that actually matters (`T44QQE`) — verified complete
  (all 6 bands + SCL + metadata) via Phase 2 Part 2.3's integrity audit, not just assumed from file counts.
- Study boundary: GVMC administrative boundary fetched from OpenStreetMap (never estimated), 625.15 km²,
  buffered 5 km — see [`results/phase1_boundary_check.png`](results/phase1_boundary_check.png).
- Small datasets (WorldPop, DEM, WorldCover, OSM roads/amenities) are all fetched, verified, and backed up
  to B2.
- Full real inventory report: [`results/phase2/inventory_report.md`](results/phase2/inventory_report.md).

## Project layout

```
plan.md               — the authoritative build plan (read this for what/why)
tracking/              — live status, architecture notes, decisions, open questions (read this for what's
                          actually been done)
configs/                — all non-secret configuration (paths, boundary, temporal, grid, label, storage, b2)
src/
  acquisition/          — B2 inventory, reconciliation, integrity checks, small-dataset fetching
  storage/               — backend abstraction (B2/Local/Fake), manifest state machine, storage guard, safe_evict
  utils/                  — config loading, path resolution, logging, validation, secret redaction
data/                   — NOT in git; Tier 2 working set lives here, raw data lives in Backblaze B2
tests/                  — unit + integration tests, all against FakeBackend (no real B2 credentials needed)
results/                — reports, figures, QC images (in git)
```

## Setup

Requires Python 3.11–3.12.

```bash
pip install -e ".[dev]"
```

B2 credentials are read from environment variables (never committed) — see a local `.env` (gitignored) or
Lightning Studio secrets:

```
Backbaze-keyID=<your B2 application key ID>
Backbaze-applicationKey=<your B2 application key secret>
```

The bucket name and endpoint are non-secret and already set in [`configs/b2.yaml`](configs/b2.yaml).

## Running tests

```bash
pytest tests/
```

Every test runs against `FakeBackend` (in-memory) — nothing in the test suite touches real B2 credentials
or the network.

## How this project is built

This repo follows a strict one-part-at-a-time workflow (see `plan.md` Section 0): each unit of work is
proposed, approved, implemented, tested, and reported before the next one starts. Every phase ends in a
**Phase Gate** that a human explicitly confirms before the next phase begins. `tracking/` is the persistent
record of that process — read it before `plan.md` if you're picking this project up fresh.
