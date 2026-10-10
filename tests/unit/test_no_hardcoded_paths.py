"""Static lint: every src/ module must resolve paths via src.utils.io.resolve_path(),
never embed a literal path to a project directory. See plan.md Section 1's
validation rule. src/utils/io.py itself is exempt — it IS the resolution
mechanism and legitimately references config file names.
"""

import ast

from src.utils.io import find_repo_root

_EXEMPT_RELATIVE_FILES = {"src/utils/io.py"}

_PROJECT_TOP_DIRS = (
    "configs",
    "data",
    "src",
    "tests",
    "notebooks",
    "models",
    "predictions",
    "results",
    "logs",
)


def _iter_src_python_files():
    repo_root = find_repo_root()
    src_root = repo_root / "src"
    for path in sorted(src_root.rglob("*.py")):
        rel = path.relative_to(repo_root).as_posix()
        if path.name == "__init__.py" or rel in _EXEMPT_RELATIVE_FILES:
            continue
        yield path, rel


def _looks_like_project_path_literal(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if " " in value or "\n" in value:
        # A real path literal never contains whitespace; this excludes prose
        # (docstrings, error messages) that merely mentions a path, e.g.
        # "configs/storage.yaml's budget_gb is not set".
        return False
    if len(value) <= 1:
        # Excludes bare separator characters like "/" used in str.split("/") —
        # not a path on their own.
        return False
    if value.startswith("/") and value != "//":
        return True
    return any(value == d or value.startswith(f"{d}/") for d in _PROJECT_TOP_DIRS)


def _resolve_path_argument_ids(tree: ast.AST) -> set[int]:
    """IDs of Constant nodes that are arguments to a resolve_path(...) call.

    A dotted key like "logs" or "data.staging" passed *into* resolve_path() is
    the sanctioned way to reference a project path — that's the whole point of
    the helper — so those literals are exempt from the hardcoded-path check.
    Anything else (e.g. a literal passed to open()/Path() directly) is not.
    """
    allowed_ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        func_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if func_name != "resolve_path":
            continue
        for arg in (*node.args, *(kw.value for kw in node.keywords)):
            if isinstance(arg, ast.Constant):
                allowed_ids.add(id(arg))
    return allowed_ids


def _non_path_usage_ids(tree: ast.AST) -> set[int]:
    """IDs of Constant nodes used in a way that structurally can't be a
    local project path construction:
    - a dict key (e.g. {"results": ...})
    - the operand of an `in`/`not in` membership test (e.g. "/IMG_DATA/" in s)
    - a literal fragment inside an f-string (e.g. f"{a}/map/{b}") — these
      build arbitrary strings (often remote object-storage keys, as in
      Part 2.4's worldcover.py), not standalone path literals passed to
      open()/Path(); a real hardcoded path is always a complete, standalone
      string constant, never an f-string fragment.
    All are common, legitimate uses of a string that happens to collide
    with a project top-dir name or start with "/".
    """
    exempt_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant):
                    exempt_ids.add(id(key))
        elif isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            if any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
                for operand in operands:
                    if isinstance(operand, ast.Constant):
                        exempt_ids.add(id(operand))
        elif isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.Constant):
                    exempt_ids.add(id(value))
    return exempt_ids


def test_no_hardcoded_paths():
    offenders = []
    for path, rel in _iter_src_python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        exempt_ids = _resolve_path_argument_ids(tree) | _non_path_usage_ids(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or id(node) in exempt_ids:
                continue
            if _looks_like_project_path_literal(node.value):
                offenders.append(f"{rel}:{node.lineno}: {node.value!r}")

    assert not offenders, (
        "Hardcoded project paths found outside src/utils/io.py — resolve via "
        "src.utils.io.resolve_path() instead:\n" + "\n".join(offenders)
    )


def test_resolve_path_arguments_are_exempt_not_a_loophole():
    # The exemption only covers the literal argument *inside* a resolve_path(...)
    # call — a stray hardcoded path elsewhere in the same file must still be caught.
    source = (
        "from src.utils.io import resolve_path\n"
        "def f():\n"
        "    good = resolve_path('data.staging')\n"
        "    bad = 'data/staging'\n"
    )
    tree = ast.parse(source)
    exempt_ids = _resolve_path_argument_ids(tree)
    flagged = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and id(node) not in exempt_ids
        and _looks_like_project_path_literal(node.value)
    ]
    assert flagged == ["data/staging"]


def test_path_literal_detector_actually_detects_violations():
    # Guards against the main test above passing vacuously just because src/ is
    # still small — proves the detector logic itself is not a no-op.
    assert _looks_like_project_path_literal("data/staging")
    assert _looks_like_project_path_literal("results/phase1_boundary_check.png")
    assert _looks_like_project_path_literal("/etc/passwd")
    assert not _looks_like_project_path_literal("https://example.com/data")
    assert not _looks_like_project_path_literal("hello")
    assert not _looks_like_project_path_literal(42)


def test_path_literal_detector_excludes_prose_mentioning_a_path():
    # Regression: an error message/docstring that starts with a project top
    # dir but is prose (contains whitespace) must not be flagged — only a
    # standalone path literal should be. Caught for real in Part 0.5's
    # src/storage/guard.py error messages.
    assert not _looks_like_project_path_literal("configs/storage.yaml's budget_gb is not set")
    assert not _looks_like_project_path_literal("data/staging is nearly full")


def test_path_literal_detector_excludes_bare_separator_characters():
    # Regression: str.split("/") or rsplit("/", 1) use the literal "/" as a
    # delimiter, not a path — caught for real in Part 2.1's product_id.py.
    assert not _looks_like_project_path_literal("/")
    assert not _looks_like_project_path_literal("")
    assert _looks_like_project_path_literal("/etc/passwd")  # still catches real absolute paths


def test_non_path_usage_ids_exempts_dict_keys():
    # Regression: {"results": results} in a return dict — "results" here is
    # a dict key/label, not a path — caught for real in Part 2.3's
    # integrity.py (run_integrity_audit's return value).
    source = "def f():\n    return {'results': 1, 'other': 2}\n"
    tree = ast.parse(source)
    exempt_ids = _non_path_usage_ids(tree)
    dict_node = next(n for n in ast.walk(tree) if isinstance(n, ast.Dict))
    assert all(id(k) in exempt_ids for k in dict_node.keys)


def test_non_path_usage_ids_exempts_membership_test_operands():
    # Regression: "/IMG_DATA/" in some_string — a substring containment
    # check, not a path construction — caught for real in Part 2.3's
    # integrity.py (check_zip_band_completeness).
    source = "def f(n):\n    return '/IMG_DATA/' in n\n"
    tree = ast.parse(source)
    exempt_ids = _non_path_usage_ids(tree)
    compare_node = next(n for n in ast.walk(tree) if isinstance(n, ast.Compare))
    assert id(compare_node.left) in exempt_ids


def test_non_path_usage_exemption_is_not_a_loophole_for_real_hardcoded_paths():
    # A literal used as a dict VALUE (not key) or outside a membership test
    # must still be caught.
    source = "def f():\n    bad = {'key': 'data/staging'}\n"
    tree = ast.parse(source)
    exempt_ids = _non_path_usage_ids(tree)
    flagged = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and id(node) not in exempt_ids and _looks_like_project_path_literal(node.value)
    ]
    assert flagged == ["data/staging"]


def test_non_path_usage_ids_exempts_fstring_fragments():
    # Regression: f"{a}/map/{b}" — "/map/" is a literal fragment of an
    # f-string building an arbitrary (often remote) string, not a
    # standalone path literal — caught for real in Part 2.4's
    # sources/worldcover.py key-building code.
    source = "def f(a, b):\n    return f'{a}/map/{b}'\n"
    tree = ast.parse(source)
    exempt_ids = _non_path_usage_ids(tree)
    joined = next(n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr))
    fragment = next(v for v in joined.values if isinstance(v, ast.Constant))
    assert id(fragment) in exempt_ids


def test_fstring_exemption_is_not_a_loophole_for_a_standalone_literal():
    # A real hardcoded path sitting next to an f-string must still be caught.
    source = "def f(a):\n    ok = f'{a}/map/'\n    bad = 'data/staging'\n"
    tree = ast.parse(source)
    exempt_ids = _non_path_usage_ids(tree)
    flagged = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and id(node) not in exempt_ids and _looks_like_project_path_literal(node.value)
    ]
    assert flagged == ["data/staging"]
