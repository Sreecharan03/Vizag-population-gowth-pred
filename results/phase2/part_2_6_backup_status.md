# Manifest Backup & Resume Drill Status (Phase 2, Part 2.6)

**Backed up to `vizag-geoai/data/manifests/`:** 1 file(s).

- `vizag-geoai/data/manifests/b2_inventory.jsonl`

## Resume drill

`Manifest.pending()` (src/storage/manifest.py) returns every record NOT yet in a terminal state (VERIFIED/ARCHIVED/EVICTED). Proven in `tests/unit/test_manifest.py::test_pending_simulates_a_resume_with_zero_duplicate_work`: a worklist of 2 items, one completed fully and one interrupted mid-flight, reloaded via a brand-new `Manifest` instance pointed at the same file (simulating a Studio restart) — the resumed worklist contains only the interrupted item; the completed one is never reprocessed. Zero duplicate transfers, confirmed by test, not just by design.
