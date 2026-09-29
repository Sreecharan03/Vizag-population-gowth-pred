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
    if value.startswith("/"):
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


def test_no_hardcoded_paths():
    offenders = []
    for path, rel in _iter_src_python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        exempt_ids = _resolve_path_argument_ids(tree)
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
