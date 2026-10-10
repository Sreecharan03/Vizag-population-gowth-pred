"""Credential-value detection used by log redaction and the repo secret scan.

Treats any environment variable whose NAME looks credential-like (KEY,
SECRET, TOKEN, PASSWORD, CREDENTIAL — case-insensitive) as holding a secret
VALUE that must never appear verbatim in a log file or a tracked repo file.
Deliberately name-pattern-based rather than hardcoding this project's actual
env var names (e.g. "Backbaze-keyID"), so detection stays correct even if
those names change.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_CREDENTIAL_NAME_RE = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)", re.IGNORECASE)
_MIN_SECRET_LENGTH = 8  # shorter values are too likely to cause false-positive redaction

_REDACTED = "***REDACTED***"


def get_known_secret_values(env: dict | None = None) -> list[str]:
    """Return environment-variable values that look like secrets based on
    their variable NAME, long enough to be worth redacting. Sorted longest
    first so a secret that's a substring of another is never partially
    masked by the shorter one going first.
    """
    env = os.environ if env is None else env
    values = {value for name, value in env.items() if value and len(value) >= _MIN_SECRET_LENGTH and _CREDENTIAL_NAME_RE.search(name)}
    return sorted(values, key=len, reverse=True)


def redact(text: str, secrets: list[str] | None = None) -> str:
    """Replace every occurrence of a known secret value in `text` with a
    fixed placeholder.
    """
    secrets = get_known_secret_values() if secrets is None else secrets
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, _REDACTED)
    return text


def scan_files_for_leaked_secrets(paths: list[Path], secrets: list[str] | None = None) -> dict[str, list[str]]:
    """Return {file_path: [matched secret values]} for any file in `paths`
    that contains a known secret value verbatim.

    Callers must never print the matched values themselves (the dict values
    exist for assertions/counts, not for display) — report file paths only.
    """
    secrets = get_known_secret_values() if secrets is None else secrets
    findings: dict[str, list[str]] = {}
    for path in paths:
        if not path.is_file():
            continue
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        hits = [s for s in secrets if s and s in content]
        if hits:
            findings[str(path)] = hits
    return findings
