# ADR-001: Sentinel-2 Read Strategy

## Decision

Use strategy (b): direct remote windowed reads via GDAL's /vsizip/vsis3/ virtual
filesystem chain, reading each required band's windowed region straight out of the remote
.SAFE.zip in B2. Never fetch-to-staging as the default path for Phase 3 band extraction.

## Rationale

Benchmarked both strategies on 2 real scenes from the required tile (T44QQE),
reading a representative 2000x2000 pixel window of band B02 (see results/phase3/read_benchmark.md):

| Metric | (a) fetch-to-staging | (b) direct remote (/vsizip/vsis3/) |
|---|---|---|
| Avg wall time | 3.96 s | 1.39 s (2.8x faster) |
| Avg bytes transferred | 606.3 MB | 8.89 MB (98.5% less) |
| Avg request count | 1.0 | 43.0 |
| Avg peak staging disk | 606.3 MB | 0.0 MB |

Strategy (b) wins decisively on every dimension that matters for this project's storage-budget
constraint (Section 1A): it transfers roughly 1.5% of the data that strategy (a) does for the
same useful output, uses zero staging disk (directly satisfying golden rule #1 - raw never
lives fully on the Studio), and is faster despite needing more HTTP requests (the requests are
small/cheap; the dominant cost in strategy (a) is transferring and writing nearly a gigabyte of
data we do not need).

The only real strategy-(a) overhead is a larger number of small requests per scene (43 vs 1).
Given the plan's data-safety emphasis on bytes transferred and disk usage over raw request
count, and that B2's pricing is primarily storage/egress-based (per Assumption A5, confirmed
by the user - a paid plan, pricing accepted), this tradeoff clearly favors strategy (b).

Scope note: this result is for reading a WINDOWED region (our actual use case - every Phase 3
read is clipped to the buffered study boundary). If a future need ever required reading the
ENTIRE scene (not windowed), the two strategies would converge since the full content would be
transferred either way; that is not this project's access pattern for raw scenes.

## Status

**Accepted — 2026-10-10.** User explicitly approved strategy (b) ("yes, use this approach"). This is the
read strategy for the remainder of Phase 3's band extraction.

See `results/phase3/read_benchmark.md` for the measurements this decision is based on.
