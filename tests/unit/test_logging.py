from src.utils.io import resolve_path
from src.utils.logging import get_run_logger


def test_logging_creates_timestamped_file_and_is_appendable():
    ts = "20260101T000000Z_test"
    logger = get_run_logger("phase0_test", run_timestamp=ts)
    log_path = resolve_path("logs") / f"phase0_test_{ts}.log"

    logger.info("first message")
    for handler in logger.handlers:
        handler.flush()
    assert log_path.is_file()
    first_contents = log_path.read_text()
    assert "first message" in first_contents

    # A second call for the same phase+timestamp must append, not truncate.
    logger_again = get_run_logger("phase0_test", run_timestamp=ts)
    logger_again.info("second message")
    for handler in logger_again.handlers:
        handler.flush()
    second_contents = log_path.read_text()
    assert "first message" in second_contents
    assert "second message" in second_contents

    log_path.unlink()


def test_different_timestamps_create_separate_files():
    logger_a = get_run_logger("phase0_test", run_timestamp="tsA")
    logger_b = get_run_logger("phase0_test", run_timestamp="tsB")

    path_a = resolve_path("logs") / "phase0_test_tsA.log"
    path_b = resolve_path("logs") / "phase0_test_tsB.log"

    logger_a.info("only in A")
    logger_b.info("only in B")
    for handler in logger_a.handlers + logger_b.handlers:
        handler.flush()

    assert "only in A" in path_a.read_text()
    assert "only in B" not in path_a.read_text()
    assert "only in B" in path_b.read_text()

    path_a.unlink()
    path_b.unlink()


def test_empty_phase_name_rejected():
    import pytest

    with pytest.raises(ValueError):
        get_run_logger("")
