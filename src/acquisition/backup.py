"""Phase 2 Part 2.6: back up data/manifests/ to B2.

Copy-only — mirrors every manifest file to B2 under configs/b2.yaml's
manifests_backup prefix. Never deletes or overwrites anything on the B2
side beyond a normal object overwrite of its own backup copy (the local
manifest is always the source of truth; this just mirrors it).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils.io import load_config, resolve_path


def backup_manifests_to_b2(backend, *, b2_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = b2_config if b2_config is not None else load_config("b2")
    prefix = config["prefixes"]["manifests_backup"]
    if not prefix:
        raise ValueError("configs/b2.yaml prefixes.manifests_backup is not set — refusing to guess a prefix")

    manifests_dir = resolve_path("data.manifests")
    if not manifests_dir.is_dir():
        return {"uploaded": [], "prefix": prefix}

    uploaded = []
    for local_path in sorted(manifests_dir.rglob("*")):
        if not local_path.is_file():
            continue
        rel = local_path.relative_to(manifests_dir).as_posix()
        key = f"{prefix}{rel}"
        backend.upload(local_path, key)
        uploaded.append(key)

    return {"uploaded": uploaded, "prefix": prefix}


def write_backup_report(result: dict[str, Any]) -> Path:
    lines = [
        "# Manifest Backup & Resume Drill Status (Phase 2, Part 2.6)",
        "",
        f"**Backed up to `{result['prefix']}`:** {len(result['uploaded'])} file(s).",
        "",
    ]
    for key in result["uploaded"]:
        lines.append(f"- `{key}`")

    lines += [
        "",
        "## Resume drill",
        "",
        "`Manifest.pending()` (src/storage/manifest.py) returns every record NOT yet in a terminal state "
        "(VERIFIED/ARCHIVED/EVICTED). Proven in "
        "`tests/unit/test_manifest.py::test_pending_simulates_a_resume_with_zero_duplicate_work`: a "
        "worklist of 2 items, one completed fully and one interrupted mid-flight, reloaded via a brand-new "
        "`Manifest` instance pointed at the same file (simulating a Studio restart) — the resumed worklist "
        "contains only the interrupted item; the completed one is never reprocessed. Zero duplicate "
        "transfers, confirmed by test, not just by design.",
        "",
    ]

    content = "\n".join(lines)
    path = resolve_path("results") / "phase2" / "part_2_6_backup_status.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path
