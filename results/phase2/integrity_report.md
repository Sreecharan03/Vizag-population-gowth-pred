# Integrity Audit Report (Phase 2, Part 2.3)

Scope: raw `.SAFE.zip` scenes for required tile(s) ['T44QQE'] only (extra tiles already in B2 are not audited — not needed yet).

**Audited:** 86 scene(s). **OK:** 86. **Failed:** 0.

Method: zip central-directory read via HTTP range requests only — no scene content was downloaded. Size sanity checked against a generous plausible range. B2's ETag is recorded per scene as a future drift-detection fingerprint, not verified against an independent copy (multipart-uploaded ETags aren't plain content MD5s).

## Failed scenes

_(none — every audited scene has all 6 bands + SCL + metadata, and a sane size)_