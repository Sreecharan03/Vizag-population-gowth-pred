"""Phase 2 Part 2.5: resume the remaining large items (if any).

Only items the user explicitly approves from missing_report.md may ever be
fetched — this module never fetches anything on its own initiative. It
re-reconciles fresh (not reusing Part 2.2's cached result) against the
current requirements and the real inventory, so a stale "nothing missing"
conclusion is never trusted blindly.

If a future run finds real missing items, the actual stream-through flow
(source -> data/staging/ -> upload to B2 -> verify -> safe_evict()) needs
to be built then, against a real item to validate it against — not built
speculatively now with nothing real to exercise it on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.acquisition.reconcile import reconcile_sentinel2
from src.utils.io import load_config, resolve_path


def check_remaining_large_items(
    requirements: dict[str, Any] | None = None, inventory: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Re-reconciles Sentinel-2 requirements against the current
    inventory (freshly loaded, not cached) and returns what — if
    anything — still needs fetching.
    """
    requirements = requirements if requirements is not None else load_config("data_requirements")
    if inventory is None:
        manifest_path = resolve_path("data.manifests") / "b2_inventory.jsonl"
        inventory = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]

    return reconcile_sentinel2(requirements, inventory)


def write_resume_status_report(result: dict[str, Any]) -> Path:
    lines = ["# Resume / Remaining Large Items Status (Phase 2, Part 2.5)", ""]
    if result["missing"]:
        lines += [
            f"**{len(result['missing'])} (tile, epoch) pair(s) still need fetching** — NOT fetched by "
            "this run. Per plan.md Section 0, each item needs the user's explicit approval (estimated "
            "bytes/source/destination) before any transfer; this part only identifies what's missing, "
            "it never fetches on its own initiative.",
            "",
        ]
        for item in result["missing"]:
            lines.append(f"- `{item['tile']}` / {item['epoch']}")
    else:
        lines.append(
            "**Nothing to resume.** Re-reconciled against the current `configs/data_requirements.yaml` "
            "and the real B2 inventory: every required (tile, epoch) combination already has at least "
            "one raw scene in B2 (confirmed by Part 2.2, re-confirmed here). No large-item acquisition "
            "runs in this part."
        )

    content = "\n".join(lines)
    path = resolve_path("results") / "phase2" / "part_2_5_resume_status.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path
