import os
import warnings

import pytest

from src.utils.io import (
    ConfigError,
    find_duplicate_paths,
    find_repo_root,
    load_config,
    resolve_path,
)


def _iter_leaf_dotted_keys(node, prefix=""):
    if isinstance(node, dict):
        for key, value in node.items():
            dotted = f"{prefix}.{key}" if prefix else key
            yield from _iter_leaf_dotted_keys(value, dotted)
    else:
        yield prefix


def test_config_loads_and_resolves_all_declared_paths():
    paths_config = load_config("paths")
    repo_root = find_repo_root()

    leaf_keys = list(_iter_leaf_dotted_keys(paths_config))
    assert leaf_keys, "configs/paths.yaml should declare at least one path"

    for dotted_key in leaf_keys:
        resolved = resolve_path(dotted_key)
        assert resolved.is_absolute()
        assert resolved.is_relative_to(repo_root)


def test_missing_config_key_raises_configerror():
    with pytest.raises(ConfigError, match="no key 'does.not.exist'"):
        resolve_path("does.not.exist")


def test_resolve_path_non_leaf_key_raises_configerror():
    # 'data' is a mapping, not a path string — must fail clearly, not return a dict.
    with pytest.raises(ConfigError, match="does not resolve to a path string"):
        resolve_path("data")


def test_load_config_missing_file_raises_configerror():
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config("this_config_does_not_exist")


def test_find_repo_root_independent_of_cwd(tmp_path):
    repo_root = find_repo_root()
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        # find_repo_root is cached on first call in the test session, but the
        # underlying logic must never depend on cwd — re-derive it manually to
        # prove that, bypassing the cache.
        assert find_repo_root.__wrapped__() == repo_root
    finally:
        os.chdir(original_cwd)


def test_duplicate_paths_detected_but_not_raised():
    mapping = {
        "a": {"one": "shared/path", "two": "shared/path"},
        "b": "unique/path",
    }
    duplicates = find_duplicate_paths(mapping)
    assert duplicates == {"shared/path": ["a.one", "a.two"]}


def test_no_duplicates_for_all_unique_paths():
    mapping = {"a": "path/a", "b": "path/b"}
    assert find_duplicate_paths(mapping) == {}


def test_resolve_path_warns_on_real_duplicate_but_does_not_raise():
    # configs/paths.yaml is expected to have no duplicates today; this proves the
    # warning path itself is non-fatal by calling it directly rather than relying
    # on paths.yaml happening to contain a duplicate.
    from src.utils.io import _warn_on_duplicate_paths

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _warn_on_duplicate_paths({"a": "same", "b": "same"})
        assert any("same" in str(w.message) for w in caught)
