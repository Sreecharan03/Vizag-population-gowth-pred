import pytest

from src.storage.guard import BudgetExceededError, BudgetNotSetError, check_budget

_BYTES_PER_GB = 1024**3


def test_storage_guard_refuses_when_budget_is_null():
    config = {"studio": {"budget_gb": None}}
    with pytest.raises(BudgetNotSetError, match="not set"):
        check_budget(1, storage_config=config)


def test_storage_guard_blocks_when_projected_size_exceeds_budget(monkeypatch):
    config = {"studio": {"budget_gb": 1}}  # 1 GB budget
    monkeypatch.setattr("src.storage.guard.current_tier2_bytes", lambda: 0)
    monkeypatch.setattr("src.storage.guard.current_staging_bytes", lambda: 0)

    with pytest.raises(BudgetExceededError, match="would exceed"):
        check_budget(2 * _BYTES_PER_GB, storage_config=config)


def test_storage_guard_allows_when_within_budget(monkeypatch):
    config = {"studio": {"budget_gb": 10}}
    monkeypatch.setattr("src.storage.guard.current_tier2_bytes", lambda: 0)
    monkeypatch.setattr("src.storage.guard.current_staging_bytes", lambda: 0)

    check_budget(1 * _BYTES_PER_GB, storage_config=config)  # must not raise


def test_storage_guard_accounts_for_existing_usage(monkeypatch):
    config = {"studio": {"budget_gb": 1}}
    monkeypatch.setattr("src.storage.guard.current_tier2_bytes", lambda: int(0.9 * _BYTES_PER_GB))
    monkeypatch.setattr("src.storage.guard.current_staging_bytes", lambda: 0)

    # 0.9 GB already used + 0.2 GB more would exceed the 1 GB budget.
    with pytest.raises(BudgetExceededError):
        check_budget(int(0.2 * _BYTES_PER_GB), storage_config=config)
