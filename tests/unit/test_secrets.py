from pathlib import Path

from src.utils.secrets import get_known_secret_values, redact, scan_files_for_leaked_secrets


def test_get_known_secret_values_filters_by_name_pattern():
    env = {
        "Backbaze-applicationKey": "longenoughsecretvalue123",
        "MY_API_TOKEN": "anotherlongsecretvalue456",
        "PATH": "/usr/bin:/bin",  # not credential-like by name
        "HOME": "/home/user",  # not credential-like by name
    }
    values = get_known_secret_values(env)
    assert "longenoughsecretvalue123" in values
    assert "anotherlongsecretvalue456" in values
    assert "/usr/bin:/bin" not in values
    assert "/home/user" not in values


def test_get_known_secret_values_excludes_short_values():
    env = {"SOME_KEY": "short"}  # below the minimum length threshold
    assert get_known_secret_values(env) == []


def test_get_known_secret_values_excludes_empty_values():
    env = {"SOME_SECRET": ""}
    assert get_known_secret_values(env) == []


def test_redact_replaces_known_secret_values():
    text = "connecting with key=abc123supersecret to the bucket"
    result = redact(text, secrets=["abc123supersecret"])
    assert "abc123supersecret" not in result
    assert "***REDACTED***" in result


def test_redact_leaves_non_secret_text_untouched():
    text = "nothing sensitive here"
    assert redact(text, secrets=["abc123supersecret"]) == text


def test_redact_longer_secret_first_avoids_partial_mask():
    # "abc123" is a substring of "abc123extended" — if the shorter one were
    # redacted first, the longer one would never match as a whole again.
    text = "token abc123extended in use"
    result = redact(text, secrets=["abc123", "abc123extended"])
    assert "abc123extended" not in result
    assert result.count("***REDACTED***") == 1


def test_scan_files_for_leaked_secrets_finds_match(tmp_path):
    leaky_file = tmp_path / "oops.yaml"
    leaky_file.write_text("key: supersecretvalue123\n")
    clean_file = tmp_path / "fine.yaml"
    clean_file.write_text("key: just a normal value\n")

    findings = scan_files_for_leaked_secrets(
        [leaky_file, clean_file], secrets=["supersecretvalue123"]
    )
    assert str(leaky_file) in findings
    assert str(clean_file) not in findings


def test_scan_files_for_leaked_secrets_skips_missing_files(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    assert scan_files_for_leaked_secrets([missing], secrets=["anything"]) == {}


def test_secret_scan_finds_no_keys_in_repo_configs_or_logs():
    """The actual plan-mandated test: real secrets (if any are loaded into
    the environment, e.g. via .env) must never appear in configs/ or logs/.
    """
    from dotenv import load_dotenv

    from src.utils.io import find_repo_root

    repo_root = find_repo_root()
    load_dotenv(repo_root / ".env")

    secrets = get_known_secret_values()
    if not secrets:
        import pytest

        pytest.skip("No credential-like env vars loaded in this environment to check against")

    paths = []
    for directory in ("configs", "logs"):
        dir_path = repo_root / directory
        if dir_path.is_dir():
            paths.extend(p for p in dir_path.rglob("*") if p.is_file())

    findings = scan_files_for_leaked_secrets(paths, secrets=secrets)
    assert not findings, f"Secret values found leaked in: {list(findings.keys())}"
