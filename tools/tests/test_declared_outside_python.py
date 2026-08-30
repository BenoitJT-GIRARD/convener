"""Dotted paths this project declares where no Python file can be checked.

Two kinds of reference live outside any `.py` file and are therefore
invisible to mypy, to ruff and to every import the suite makes:

* the console commands in `tools/pyproject.toml`'s `[project.scripts]`,
  which name a module and an attribute in a string;
* the inline programs workflow steps run with `python -c`, which import
  from this package and reach for paths inside the repository.

Both broke silently when the package gained sub-packages and when the
instance's paths moved. A grep for a filename finds neither: one names a
module inside a TOML string, the other uses `from convener_ops import
<module>`, which contains no dotted path at all. Nothing was red, and
three workflow steps would have failed on their next run.
"""

from __future__ import annotations

import ast
import importlib
import re
import tomllib

import pytest

from convener_ops.declaration import boundary
from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.yaml_safe import safe_load

ROOT = repo_root()
WORKFLOWS = ROOT / ".github" / "workflows"


def entry_points() -> dict[str, str]:
    """Every console command this package declares, and what it points at."""
    data = tomllib.loads(
        (ROOT / "tools" / "pyproject.toml").read_text(encoding="utf-8")
    )
    scripts = data["project"]["scripts"]
    assert len(scripts) > 40, f"only {len(scripts)} entry points found; the file moved"
    return dict(scripts)


def run_blocks() -> list[tuple[str, str]]:
    """Every `run:` script in every workflow, with the file it came from."""
    found: list[tuple[str, str]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = safe_load(path.read_text(encoding="utf-8")) or {}
        for job in (document.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                script = step.get("run")
                if script:
                    found.append((path.name, script))
    assert len(found) > 40, f"only {len(found)} run blocks found; the parse is wrong"
    return found


def imported_names(script: str) -> set[tuple[str, str]]:
    """Every `(module, name)` an inline program imports from this package.

    `from convener_ops.journey import eventkeys` gives a dotted path;
    `from convener_ops import eventkeys` gives none, the module's name
    being the imported *name*. A grep for a path misses the second, which
    is the spelling that broke.

    The imported name may be a module or an attribute of one, and the
    import itself does not say which, so both are returned and the check
    accepts either.
    """
    found: set[tuple[str, str]] = set()
    for line in script.splitlines():
        text = line.strip().rstrip("'\"")
        if not text.startswith(("from convener_ops", "import convener_ops")):
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("convener_ops"):
                    for alias in node.names:
                        found.add((node.module, alias.name))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("convener_ops"):
                        parent, _, leaf = alias.name.rpartition(".")
                        found.add((parent or alias.name, leaf))
    return found


def test_every_console_command_resolves() -> None:
    """A command nobody in the suite runs is still a command somebody runs."""
    broken: list[str] = []
    for name, target in entry_points().items():
        module_name, _, attribute = target.partition(":")
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            broken.append(f"{name} -> {target} (no such module)")
            continue
        if not callable(getattr(module, attribute, None)):
            broken.append(f"{name} -> {target} (no such attribute)")
    assert not broken, (
        "these console commands do not resolve: "
        + "; ".join(broken)
        + ". They are declared in tools/pyproject.toml, which no test imports, "
        "so moving or renaming a module leaves them broken with every gate green."
    )


def test_every_inline_program_imports_what_it_says() -> None:
    """The imports inside a workflow's `python -c` are real imports."""
    broken: list[str] = []
    seen = 0
    for name, script in run_blocks():
        for module_name, imported in sorted(imported_names(script)):
            seen += 1
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                broken.append(f"{name}: {module_name}")
                continue
            if hasattr(module, imported):
                continue
            try:
                importlib.import_module(f"{module_name}.{imported}")
            except ImportError:
                broken.append(f"{name}: {module_name}.{imported}")
    assert seen, "no inline program imports this package; the extraction is wrong"
    assert not broken, (
        "these workflow steps import something that does not exist: "
        + "; ".join(broken)
        + ". Nothing type-checks a program written inside a YAML string, so it "
        "fails on the runner rather than here."
    )


#: A path built from quoted segments (`root / "data" / "speakers.yml"`) and
#: a path written whole (`instance/public-data/x.json`). Only the first
#: segment decides: `root / "instance" / "keys"` is the path today,
#: `root / "keys"` is where it used to be.
QUOTED_CHAIN = re.compile(r'(?:/\s*"[A-Za-z0-9_.-]+"\s*)+')
QUOTED_SEGMENT = re.compile(r'"([A-Za-z0-9_.-]+)"')
BARE_PATH = re.compile(r'(?<![A-Za-z0-9_/."-])([a-z][a-z0-9-]*)/')


def first_segments(line: str) -> set[str]:
    """The first component of every path this line builds."""
    heads: set[str] = set()
    for chain in QUOTED_CHAIN.finditer(line):
        segments = QUOTED_SEGMENT.findall(chain.group(0))
        if segments:
            heads.add(segments[0])
    heads.update(BARE_PATH.findall(line))
    return heads


def test_no_inline_program_reaches_a_path_the_instance_has_left() -> None:
    """A path written inside a YAML string is invisible to the path sweeps.

    `tests/declaration/test_paths.py` reads Python files. A program
    embedded in a workflow is a string to every tool this repository
    runs, so the same literal survives there after the directory it names
    has moved.
    """
    retired = {entry.path.rstrip("/") for entry in boundary.load(ROOT).retired}
    retired = {name for name in retired if "/" not in name}
    assert retired, "the declaration retires no directory; this check has no subject"
    offences: list[str] = []
    for name, script in run_blocks():
        for line in script.splitlines():
            if first_segments(line) & retired:
                offences.append(f"{name}: {line.strip()[:80]}")
    assert not offences, (
        "these workflow steps reach for a path the instance no longer owns: "
        + "; ".join(offences)
        + ". config/boundary.yml's retired list says where each went."
    )


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        (
            "from convener_ops.journey import eventkeys",
            ("convener_ops.journey", "eventkeys"),
        ),
        ("from convener_ops import cli", ("convener_ops", "cli")),
        ("import convener_ops.cli", ("convener_ops", "cli")),
    ],
)
def test_the_import_reader_sees_both_spellings(
    script: str, expected: tuple[str, str]
) -> None:
    """Without this the sweep above passes by reading nothing."""
    assert expected in imported_names(script)


@pytest.mark.parametrize(
    ("line", "head"),
    [
        ('keys_dir = root / "keys" / "events"', "keys"),
        ('root / "instance" / "keys" / "events"', "instance"),
        ("git add instance/public-data/x.json", "instance"),
        ('(repo_root() / "data" / "speakers.yml")', "data"),
    ],
)
def test_the_path_reader_takes_the_first_segment_only(line: str, head: str) -> None:
    """`instance/keys` is where the directory is; `keys` is where it was."""
    assert head in first_segments(line)
