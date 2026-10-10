"""safe_evict(): the ONLY sanctioned way a local raw file is removed
(plan.md Section 1A.4 golden rule #7).

Refuses — raises EvictionRefused, deletes nothing, writes nothing to the
ledger — unless BOTH preconditions hold: the B2 copy is verified, and the
derivative has been validated. Only a successful eviction is logged.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.utils.io import find_repo_root, load_config


class EvictionRefused(Exception):
    """Raised when safe_evict()'s preconditions aren't met. Nothing is
    deleted and nothing is written to the ledger when this is raised.
    """


def _ledger_path(storage_config: dict[str, Any] | None = None) -> Path:
    config = storage_config if storage_config is not None else load_config("storage")
    ledger_rel = config["eviction"]["ledger"]
    return find_repo_root() / ledger_rel


def _append_ledger(ledger_path: Path, object_key: str, local_path: Path, reason: str) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "object_key": object_key,
        "local_path": str(local_path),
        "outcome": "EVICTED",
        "reason": reason,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with ledger_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def safe_evict(
    local_path: Path,
    *,
    b2_verified: bool,
    derivative_validated: bool,
    object_key: str,
    reason: str = "",
    storage_config: dict[str, Any] | None = None,
) -> None:
    """Delete `local_path` only if its B2 copy is verified AND its
    derivative has been validated, and `local_path` actually exists.

    Raises EvictionRefused (deleting and writing nothing) if any
    precondition fails. On success, deletes the file and appends exactly
    one entry to the eviction ledger.
    """
    local_path = Path(local_path)

    if not b2_verified:
        raise EvictionRefused(f"Refusing to evict {local_path}: B2 copy not verified")
    if not derivative_validated:
        raise EvictionRefused(f"Refusing to evict {local_path}: derivative not validated")
    if not local_path.exists():
        raise EvictionRefused(f"Refusing to evict {local_path}: path does not exist")

    local_path.unlink()
    _append_ledger(_ledger_path(storage_config), object_key, local_path, reason)
