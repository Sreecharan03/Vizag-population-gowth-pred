"""Storage guard: checks projected disk usage against the Studio budget
before any heavy operation (plan.md Section 1A.4 golden rule #8).

Never "makes room" by deleting anything if the budget would be exceeded —
it only refuses and reports. The only sanctioned deletion path is
src.storage.evict.safe_evict(), called separately and explicitly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils.io import load_config, resolve_path

_BYTES_PER_GB = 1024**3

_TIER2_PATH_KEYS = ("data.processed", "data.derived", "data.raw_small")
_STAGING_PATH_KEY = "data.staging"


class StorageGuardError(Exception):
    """Base class for storage guard refusals."""


class BudgetNotSetError(StorageGuardError):
    """configs/storage.yaml's studio.budget_gb is null."""


class BudgetExceededError(StorageGuardError):
    """The projected operation would push usage past the configured budget."""


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def current_tier2_bytes() -> int:
    return sum(_dir_size_bytes(resolve_path(key)) for key in _TIER2_PATH_KEYS)


def current_staging_bytes() -> int:
    return _dir_size_bytes(resolve_path(_STAGING_PATH_KEY))


def check_budget(projected_additional_bytes: int, *, storage_config: dict[str, Any] | None = None) -> None:
    """Raise BudgetNotSetError if studio.budget_gb is null, or
    BudgetExceededError if (current Tier 1 + Tier 2 usage + the projected
    addition) would exceed the configured budget. Raises, never deletes.
    """
    config = storage_config if storage_config is not None else load_config("storage")
    budget_gb = config.get("studio", {}).get("budget_gb")
    if budget_gb is None:
        raise BudgetNotSetError(
            "configs/storage.yaml studio.budget_gb is not set — refusing to run any heavy "
            "operation until the user sets a real value."
        )

    budget_bytes = budget_gb * _BYTES_PER_GB
    current_bytes = current_tier2_bytes() + current_staging_bytes()
    projected_total = current_bytes + projected_additional_bytes

    if projected_total > budget_bytes:
        raise BudgetExceededError(
            f"Projected usage {projected_total / _BYTES_PER_GB:.2f} GB would exceed the "
            f"{budget_gb} GB budget (current: {current_bytes / _BYTES_PER_GB:.2f} GB, "
            f"adding: {projected_additional_bytes / _BYTES_PER_GB:.2f} GB). Refusing to proceed — "
            "this guard never frees space by deleting anything."
        )
