"""Config loading and path resolution.

This is the single entry point every other module must use to read a config file
or turn a declared path into a real filesystem path. No module outside this file
may embed a literal path string — see tests/unit/test_no_hardcoded_paths.py.
"""

from __future__ import annotations

import functools
import warnings
from pathlib import Path
from typing import Any

import yaml

_ROOT_MARKER = "pyproject.toml"


class ConfigError(Exception):
    """Raised for any config-loading or path-resolution failure.

    Callers get this instead of a bare FileNotFoundError/KeyError/YAMLError so
    error handling upstream can be consistent and the message is always
    actionable (which file, which key).
    """


@functools.lru_cache(maxsize=1)
def find_repo_root() -> Path:
    """Locate the repo root by walking up from this file until _ROOT_MARKER is found.

    Never relies on os.getcwd(), so path resolution is identical no matter what
    directory the pipeline is invoked from.
    """
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / _ROOT_MARKER).is_file():
            return candidate
    raise ConfigError(
        f"Could not locate repo root: no '{_ROOT_MARKER}' found in any parent directory of {here}"
    )


@functools.lru_cache(maxsize=None)
def load_config(name: str) -> dict[str, Any]:
    """Load configs/<name>.yaml and return it as a dict.

    Raises ConfigError if the file is missing, empty, or fails to parse.
    """
    path = find_repo_root() / "configs" / f"{name}.yaml"
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with path.open("r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse config file {path}: {exc}") from exc
    if data is None:
        raise ConfigError(f"Config file is empty: {path}")
    if not isinstance(data, dict):
        raise ConfigError(f"Config file {path} must contain a mapping at the top level, got {type(data).__name__}")
    return data


def find_duplicate_paths(mapping: dict[str, Any]) -> dict[str, list[str]]:
    """Given a nested dict of dotted-key -> relative-path-string, return any
    relative path that is declared under more than one dotted key.

    Pure function (no I/O) so it's directly unit-testable without a real config
    file. Used to implement the "two config keys point to the same physical
    path" edge case: this never raises — duplicates are reported, not rejected,
    since a duplicate may be intentional (e.g. an alias).
    """
    flat: dict[str, str] = {}

    def _walk(node: Any, prefix: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                dotted = f"{prefix}.{key}" if prefix else key
                _walk(value, dotted)
        elif isinstance(node, str):
            flat[prefix] = node

    _walk(mapping, "")

    by_path: dict[str, list[str]] = {}
    for dotted_key, rel_path in flat.items():
        by_path.setdefault(rel_path, []).append(dotted_key)

    return {path: keys for path, keys in by_path.items() if len(keys) > 1}


def _warn_on_duplicate_paths(paths_config: dict[str, Any]) -> None:
    duplicates = find_duplicate_paths(paths_config)
    for rel_path, dotted_keys in duplicates.items():
        warnings.warn(
            f"paths.yaml: keys {dotted_keys} all resolve to the same path '{rel_path}' "
            "— confirm this is intentional (e.g. an alias), not a copy-paste error.",
            stacklevel=3,
        )


def resolve_path(dotted_key: str, must_exist: bool = False) -> Path:
    """Resolve a dotted key from configs/paths.yaml (e.g. 'data.staging') to an
    absolute Path under the repo root.

    Raises ConfigError if the key doesn't exist or doesn't resolve to a string,
    never a bare KeyError. Pass must_exist=True to additionally require the
    resolved path to already exist on disk.
    """
    paths_config = load_config("paths")
    _warn_on_duplicate_paths(paths_config)

    node: Any = paths_config
    parts = dotted_key.split(".")
    for i, part in enumerate(parts):
        if not isinstance(node, dict) or part not in node:
            raise ConfigError(
                f"configs/paths.yaml has no key '{dotted_key}' (failed resolving '{'.'.join(parts[: i + 1])}')"
            )
        node = node[part]

    if not isinstance(node, str):
        raise ConfigError(
            f"configs/paths.yaml key '{dotted_key}' does not resolve to a path string "
            f"(got {type(node).__name__}: {node!r}); check that this is a leaf key"
        )

    resolved = (find_repo_root() / node).resolve()
    if must_exist and not resolved.exists():
        raise ConfigError(f"Resolved path for '{dotted_key}' does not exist: {resolved}")
    return resolved
