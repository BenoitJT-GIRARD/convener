"""Which tests read the shipped `instance/` tree, and why it has to be written down.

Almost every test in this suite builds the data it reads. A very few instead
read the files this repository actually ships -- `instance/data/speakers.yml`
above all -- and those few are the entire reason a *data* change ever needed
a test run.

That distinction used to be invisible, and it was expensive. `quality.yml`
carried `push: branches: [main]` with no path filter at all, so every write
to a data file ran the whole code suite: lint, type-check, four package test
runs.

Measured on the instance this product was derived for, on 2026-09-13, over
400 runs and the 472 jobs they contained: **428 billed minutes, 36% of the
1175 the repository spent that day** -- and a volunteer ticking one runbook
box paid for a full run of it. `security.yml` added 51.

That 428 is the number to look at rather than the wall-clock one, and the
gap between them is the lesson. This workflow's runs *elapse* about 275
seconds each, which reads like 142 minutes across 31 runs. GitHub bills
each **job** separately, rounded up to the whole minute, and this workflow
has four of them -- `python` (128), `web` (114), `workflow-schema` (93),
`relays` (93). A run is not a unit of cost; a job is.

The narrowing is only safe if the few really are few, so that was measured
rather than assumed: three plausible hand-edits were made to the shipped
`speakers.yml` and the whole suite was run after each. Exactly one test
noticed any of them.

So the few are marked `shipped_data`, `validate-data.yml` runs that
selection on every write under `instance/`, and `quality.yml` and
`security.yml` no longer wake for a data-only commit. This module keeps the
marker honest: a test that starts reading the shipped tree without it fails
here, by name, rather than becoming a guard that quietly stopped running.

**The reader below is an AST reader, and the first version of it was not.**
That version matched text, so it called a test a shipped-data reader for
naming `instance/data/**` inside an assertion message, and flagged two
tests of `.github/workflows/` that merely had the word in them. Marking
those would have been worse than missing them: the marker would have come
to mean "mentions the data", `validate-data.yml` would run workflow tests
on every data write, and the one honest signal would be buried. What a test
*reads* is a path expression, so the reader reads path expressions.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

from convener_ops.declaration.paths import repo_root

MARKER = "shipped_data"

#: The tests directory, read as source rather than imported: this asks what
#: each test *says*, and importing would only tell us what it did once.
TESTS_DIR = Path(__file__).resolve().parent.parent

#: The one way this package names the checkout. A read of a shipped file
#: goes through it, so a path expression rooted here is the whole search
#: space -- there is no second spelling to miss.
ROOT_CALL = "repo_root"

#: First segments that put a path inside the shipped instance tree: the
#: directory name itself, and the constants `declaration/paths.py` hands
#: out for the three sub-trees the instance owns.
INSTANCE_ROOTS = frozenset(
    {"instance", "DATA_DIR", "PUBLIC_DATA_DIR", "KEYS_DIR", "INSTANCE_DIR"}
)


def _segments(node: ast.expr) -> list[str] | None:
    """The `/`-joined segments of a path expression rooted at `repo_root()`.

    `None` when the expression is not such a path. A segment is a string
    literal's value or a bare name's identifier, so both
    `repo_root() / "instance" / "data" / "speakers.yml"` and
    `repo_root() / DATA_DIR / "speakers.yml"` read the same way.
    """
    parts: list[str] = []
    current = node
    while isinstance(current, ast.BinOp) and isinstance(current.op, ast.Div):
        right = current.right
        if isinstance(right, ast.Constant) and isinstance(right.value, str):
            parts.append(right.value)
        elif isinstance(right, ast.Name):
            parts.append(right.id)
        else:
            parts.append("?")
        current = current.left
    if not parts:
        return None
    rooted = (
        isinstance(current, ast.Call)
        and isinstance(current.func, ast.Name)
        and current.func.id == ROOT_CALL
    )
    return list(reversed(parts)) if rooted else None


def _reads_shipped_data(source: str) -> bool:
    """Does this source read a file under the shipped `instance/` tree?"""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.BinOp):
            continue
        parts = _segments(node)
        if parts and parts[0] in INSTANCE_ROOTS:
            return True
    return False


def _test_functions() -> list[tuple[Path, ast.FunctionDef, str]]:
    """Every `test_*` function in the suite, with its own source."""
    out: list[tuple[Path, ast.FunctionDef, str]] = []
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                out.append((path, node, ast.get_source_segment(source, node) or ""))
    return out


def _carries_marker(node: ast.FunctionDef) -> bool:
    return any(
        isinstance(decorator, ast.Attribute)
        and decorator.attr == MARKER
        and isinstance(decorator.value, ast.Attribute)
        and decorator.value.attr == "mark"
        for decorator in node.decorator_list
    )


def test_the_reader_tells_a_shipped_read_from_everything_that_resembles_one() -> None:
    """The control, and the reason this reader is an AST reader.

    Every probe below was a false positive for the text-matching version,
    or would be for a reader that only looked at the first segment of a
    literal. A reader that cannot tell them apart marks the wrong tests,
    and a marker on the wrong tests is worse than no marker at all.
    """
    assert _reads_shipped_data(
        'path = repo_root() / "instance" / "data" / "speakers.yml"'
    )
    assert _reads_shipped_data(
        'text = (repo_root() / DATA_DIR / "config.yml").read_text()'
    )
    assert _reads_shipped_data(
        'p = repo_root() / PUBLIC_DATA_DIR / "events-public.json"'
    )

    # A workflow file, reached the same way. Two real tests do exactly
    # this, and the text reader marked both.
    assert not _reads_shipped_data(
        'p = repo_root() / ".github" / "workflows" / "sweep-and-notify.yml"'
    )
    # The path named in an assertion message rather than opened. This is
    # what made the reader flag its own tests.
    assert not _reads_shipped_data(
        'assert "instance/data/**" in ignored, "instance/data still wakes it"'
    )
    # A fixture the test built itself, naming the constant on the way.
    assert not _reads_shipped_data('p = tmp_path / DATA_DIR / "speakers.yml"')
    # A declaration, not an instance record.
    assert not _reads_shipped_data('d = repo_root() / "declarations" / "boundary.yml"')


def test_the_reader_finds_the_tests_it_is_supposed_to_find() -> None:
    """Positive control on the real suite. A reader that matched nothing
    would let every assertion below pass by finding no work to do, which
    is the one way this module could be quietly useless."""
    found = [
        f"{path.name}::{node.name}"
        for path, node, body in _test_functions()
        if _reads_shipped_data(body)
    ]
    assert found, (
        "no test in this suite reads the shipped instance tree, according "
        "to this module's own reader -- either the suite lost its anchors "
        "or the reader stopped recognising them; both are failures"
    )


def test_every_test_reading_the_shipped_instance_carries_the_marker() -> None:
    """The rule itself.

    An unmarked test that reads the shipped tree is not a bookkeeping
    slip: `validate-data.yml` selects on this marker, so such a test would
    stop running on the one kind of change it exists to watch -- and it
    would keep passing in every other run, which is how a guard goes quiet
    without anybody noticing.
    """
    missing = [
        f"{path.relative_to(repo_root()).as_posix()}::{node.name}"
        for path, node, body in _test_functions()
        if _reads_shipped_data(body) and not _carries_marker(node)
    ]
    assert not missing, (
        "these tests read the shipped instance/ tree but carry no "
        f"@pytest.mark.{MARKER}:\n  "
        + "\n  ".join(missing)
        + f"\n\nAdd the marker. `validate-data.yml` runs `-m {MARKER}` on "
        "every write under instance/, and quality.yml no longer wakes for "
        "one, so an unmarked reader of the shipped tree is a guard that "
        "has stopped watching the change it was written for."
    )


def test_the_marker_is_on_nothing_that_does_not_read_the_shipped_tree() -> None:
    """The converse, and it is not symmetry for its own sake: a marker
    handed to a test that reads no shipped data makes `validate-data.yml`
    run it on every data write, and makes the marker mean "somewhere near
    the data" instead of "reads it". Both of the tests this rule was
    first applied to turned out to read `.github/workflows/`."""
    stray = [
        f"{path.relative_to(repo_root()).as_posix()}::{node.name}"
        for path, node, body in _test_functions()
        if _carries_marker(node) and not _reads_shipped_data(body)
    ]
    assert not stray, (
        f"these tests carry @pytest.mark.{MARKER} but read nothing under "
        "the shipped instance/ tree:\n  " + "\n  ".join(stray)
    )


def test_the_marker_is_registered_so_a_typo_is_an_error() -> None:
    """`--strict-markers` is not on, so an unregistered marker is a
    warning and a misspelled one silently selects nothing. Registering it
    is what makes `-m shipped_data` in a workflow mean something."""
    config = tomllib.loads(
        (repo_root() / "tools" / "pyproject.toml").read_text(encoding="utf-8")
    )
    markers = config["tool"]["pytest"]["ini_options"]["markers"]
    assert any(entry.split(":")[0].strip() == MARKER for entry in markers), (
        f"{MARKER} is used by the suite and selected by validate-data.yml "
        "but is not registered in tools/pyproject.toml"
    )


def test_the_selection_a_workflow_runs_is_not_empty() -> None:
    """The end of the chain: `-m shipped_data` has to select something. A
    marker registered, documented and applied to nothing is a workflow
    step that passes by doing nothing at all."""
    marked = [node.name for _, node, _ in _test_functions() if _carries_marker(node)]
    assert marked, (
        f"`pytest -m {MARKER}` selects no test, so validate-data.yml's "
        "own step runs an empty suite and reports success"
    )


@pytest.mark.parametrize("workflow", ["quality.yml", "security.yml"])
def test_the_code_checks_no_longer_wake_for_a_data_only_push(workflow: str) -> None:
    """The saving itself, read off the files that make it.

    `paths-ignore`, never `paths`: a run is skipped only when *every*
    changed file matches, so a commit touching code and data still runs
    these in full. That is the safe direction -- a path forgotten here
    merely runs a check that did not strictly have to run, where a path
    forgotten from a `paths:` list would skip one that did.
    """
    from convener_ops.declaration.yaml_safe import safe_load

    workflows = repo_root() / ".github" / "workflows"
    data = safe_load((workflows / workflow).read_text(encoding="utf-8"))
    push = data[True]["push"]
    ignored = set(push.get("paths-ignore", []))

    assert "paths" not in push, (
        f"{workflow} lists `paths:` for its push trigger -- these are the "
        "checks whose absence is the defect, so their trigger may only "
        "ever be narrowed by `paths-ignore:`"
    )
    assert "instance/data/**" in ignored, (
        f"{workflow} wakes again for a write under instance/data/. Between "
        "the two of them that was 479 billed minutes of a 2000-minute "
        "monthly allowance, in one 47-minute session, re-running checks "
        f"over unchanged source. The tests that do read that tree are "
        f"marked `{MARKER}` and run by validate-data.yml instead."
    )
