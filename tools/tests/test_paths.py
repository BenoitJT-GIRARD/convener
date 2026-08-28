"""`repo_root`, and the one place an instance path is written down.

`config/boundary.yml` declares which paths belong to the instance;
`convener_ops/paths.py` turns each of them into a named constant, read from
that declaration; every other module in the package builds the paths it
touches out of those constants. This module holds the third of those three
statements. It walks every module the package ships and fails on one that
writes an instance path out in a string of its own, with the list of paths
it refuses read from the declaration at run time.

**What counts as writing a path out.** A string constant whose value is,
or begins with, a declared instance path -- `"data/config.yml"`,
`"public-data/registration-routing.json"` -- and a `/` chain that spells
one segment by segment: `Path("data") / "events"`, `root / "data" /
"speakers.yml"`, `Path("docs") / "governance" / "register.md"`. The chain
is read the way `Path` reads it, so a constant that is only a *fragment* of
a path is caught in the position it actually occupies.

**A bare word is a path only where the code uses it as one.** `"data"` on
its own, with no separator in it, is refused inside a `/` chain and
admitted everywhere else, because three places in this package hold that
exact string meaning something else: `cli.py::handle_proposal` and
`platform_fcc.py` both read a `data` key off a JSON payload a third party
sends, and `commit_format.DOMAIN` is the domain word a decision commit's
subject carries. Each of those is a name in somebody else's vocabulary
that happens to be spelt like this repository's directory, and each would
survive the directory being moved. Refusing them would need three
exemptions for a rule with four entries.

**A comment or a docstring may name a path, and this sweep leaves it
alone.** The distinction `test_cross_references.py` draws between code and
prose, applied to the other half: that module reads a file's comments and
docstrings and ignores its code, and this one reads a file's code and
ignores its comments and docstrings. Prose that names `data/config.yml` is
explaining something to a reader, and the paragraph around it usually has
to be rewritten by hand anyway when the path moves. Prose is where the
argument for a path lives, and an argument that cannot quote the path it
is about is worth less than the duplication it saves.

**What this does not cover.** `tools/tests/` builds instance paths under
`tmp_path` in hundreds of fixtures, and `site/`, `app/`, `services/` and
the workflows name them in their own languages. This sweep is the Python
package only. The wider tree is what the later move has to reckon with;
what this fixes is the part of it that is one import away from a constant.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from test_cross_references import _tracked

from convener_ops import boundary, paths
from convener_ops.paths import (
    DATA_DIR,
    KEYS_DIR,
    PUBLIC_DATA_DIR,
    REGISTER_PATH,
    by_last_component,
    handed,
    repo_root,
)

ROOT = repo_root()

#: The package this sweep reads, and the one file inside it that is
#: allowed to write an instance path out: `paths.py` is where the
#: constants are.
PACKAGE = "tools/convener_ops/"
HOME = "tools/convener_ops/paths.py"


def declared_instance_paths() -> tuple[str, ...]:
    """The paths `config/boundary.yml` hands to the instance, read now.

    The declaration's own list, parsed by the module that owns its format.
    Adding an entry there adds a refusal here on the same commit.
    """
    return tuple(entry.path for entry in boundary.load(ROOT).handed)


def offence(value: str, *, as_path: bool) -> str | None:
    """The declared instance path `value` writes out, if it writes one."""
    written = value.replace("\\", "/").rstrip("/")
    if not written:
        return None
    for declared in declared_instance_paths():
        name = declared.rstrip("/")
        if written == name and (as_path or "/" in name):
            return declared
        if declared.endswith("/") and written.startswith(name + "/"):
            return declared
    return None


def joined(node: ast.expr) -> list[str] | None:
    """The string segments of a `/` chain, in order, or `None`.

    `Path("docs") / "governance" / "register.md"` gives three segments and
    `root / "data" / "speakers.yml"` gives two: a chain rooted in something
    this cannot read -- a variable, a call, a constant of the package --
    contributes the segments to its right, which is the suffix a path
    joined onto it would end in.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Path"
    ):
        segments: list[str] = []
        for argument in node.args:
            found = joined(argument)
            if found is None:
                return None
            segments += found
        return segments
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = joined(node.right)
        if right is None:
            return None
        left = joined(node.left)
        return right if left is None else left + right
    return None


def docstrings(tree: ast.Module) -> set[int]:
    """Every docstring node in `tree`, by identity.

    A docstring is a string *statement*, which is a distinction only a
    parser can make -- the same reason `test_cross_references._python_prose`
    reads them through `ast` rather than through a pattern over
    triple-quoted strings.
    """
    carries_one = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, carries_one):
            body = getattr(node, "body", [])
            first = body[0] if body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                found.add(id(first.value))
    return found


def _path_operands(node: ast.expr) -> list[ast.Constant]:
    """The strings `node` uses as a path segment in its own right.

    A single one of them spells a whole entry on its own -- `root /
    "public-data"`, `Path("data")` -- which is what tells a bare word used
    as a path apart from the same word used as a key.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        sides = [node.left, node.right]
    elif (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Path"
    ):
        sides = list(node.args)
    else:
        return []
    return [
        side
        for side in sides
        if isinstance(side, ast.Constant) and isinstance(side.value, str)
    ]


def offences_in(source: str) -> list[tuple[int, str, str]]:
    """Every instance path one module's *code* writes out.

    Each offence is the line, the string as it is written, and the
    declared path it spells.
    """
    tree = ast.parse(source)
    prose = docstrings(tree)
    found: list[tuple[int, str, str]] = []
    accounted: set[int] = set()
    segments_of_a_path: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp | ast.Call):
            continue
        for element in _path_operands(node):
            segments_of_a_path.add(id(element))
        segments = joined(node)
        if segments is None or len(segments) < 2:
            continue
        written = "/".join(segment.strip("/") for segment in segments)
        declared = offence(written, as_path=True)
        if declared is not None:
            found.append((node.lineno, written, declared))
        for inner in ast.walk(node):
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                accounted.add(id(inner))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in prose or id(node) in accounted:
            continue
        declared = offence(node.value, as_path=id(node) in segments_of_a_path)
        if declared is not None:
            found.append((node.lineno, node.value, declared))
    return sorted(found)


def swept() -> list[tuple[str, str]]:
    """Every module of the package this sweep reads, with its source."""
    return [
        (name, (ROOT / name).read_text(encoding="utf-8"))
        for name in _tracked()
        if name.startswith(PACKAGE) and name.endswith(".py") and name != HOME
    ]


# ------------------------------------------------------------------ #
# Finding the repository.
# ------------------------------------------------------------------ #


def test_repo_root_honours_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    assert repo_root() == tmp_path.resolve()


def test_repo_root_walks_upward_to_find_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CONVENER_REPO_ROOT", raising=False)
    (tmp_path / DATA_DIR).mkdir()
    (tmp_path / DATA_DIR / "config.yml").write_text("season: 2026\n", encoding="utf-8")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)

    assert repo_root(nested) == tmp_path.resolve()


def test_repo_root_raises_when_no_marker_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CONVENER_REPO_ROOT", raising=False)
    nested = tmp_path / "x" / "y"
    nested.mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        repo_root(nested)


# ------------------------------------------------------------------ #
# The constants are the declaration's, and nothing else.
# ------------------------------------------------------------------ #


def test_every_constant_is_a_path_the_declaration_hands_to_the_instance() -> None:
    """The four names against the four entries, both read at run time.

    A constant answering something the declaration does not say would be
    the hand-copied list this module exists to make impossible.
    """
    named = {DATA_DIR, KEYS_DIR, PUBLIC_DATA_DIR, REGISTER_PATH}
    declared = {Path(path) for path in declared_instance_paths()}

    assert named == declared, (
        f"paths.py names {sorted(str(p) for p in named)} and "
        f"{boundary.DECLARATION_PATH.as_posix()} hands over "
        f"{sorted(str(p) for p in declared)}. Every entry in that "
        "declaration needs a constant here, and every constant here has to "
        "be one of its entries."
    )


def test_a_constant_whose_path_left_the_declaration_is_refused() -> None:
    """`handed` answers from the declaration, so a path that stops being
    the instance's stops having a constant -- loudly, at import, naming
    what the declaration does hand over."""
    with pytest.raises(ValueError, match="no path ending in 'invoices'"):
        handed("invoices")


def test_two_declared_paths_ending_in_the_same_name_are_refused() -> None:
    """The one shape that would make a constant ambiguous. Held against a
    declaration made up here, so the rule is exercised rather than the
    accident that this repository has no such pair today."""
    entries = (
        boundary.Handed(path="data/", reason="the instance's records"),
        boundary.Handed(path="archive/data/", reason="last season's"),
    )

    with pytest.raises(ValueError, match="two declared instance paths end in 'data'"):
        by_last_component(entries)


def test_the_root_marker_sits_inside_the_declared_data_directory() -> None:
    """`repo_root` finds a repository by a file it has to name before the
    declaration can be read. That one spelling is held against the
    constant the declaration gives, so the two cannot drift apart."""
    assert paths._MARKER.parent == DATA_DIR


# ------------------------------------------------------------------ #
# The sweep is real: it reads code, from every module the package ships.
# ------------------------------------------------------------------ #


def test_the_sweep_reads_every_module_the_package_ships() -> None:
    """A walk that quietly found nothing would make the rule below pass
    over an empty list."""
    read = {name for name, _ in swept()}
    shipped = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / PACKAGE).glob("*.py")
        if path.relative_to(ROOT).as_posix() != HOME
    }

    assert read == shipped, (
        f"the sweep reads {len(read)} of the {len(shipped)} modules "
        f"{PACKAGE} ships. Every one of them has to be read, or a path "
        "written out in the ones it misses is held by nothing."
    )


def test_the_declaration_this_sweep_reads_is_not_empty() -> None:
    """An empty list of refused paths would make the rule below vacuous."""
    declared = declared_instance_paths()

    assert len(declared) >= 4, (
        f"{boundary.DECLARATION_PATH.as_posix()} hands {len(declared)} "
        "paths to the instance, and this sweep refuses exactly those. A "
        "declaration this short refuses almost nothing."
    )


# ------------------------------------------------------------------ #
# The rule itself.
# ------------------------------------------------------------------ #


def test_no_module_writes_an_instance_path_out() -> None:
    """An instance path is named once, in `paths.py`, from the
    declaration.

    Reach for the constant. `DATA_DIR / "config.yml"`,
    `root / DATA_DIR / "speakers.yml"`, `KEYS_DIR / "events"`,
    `PUBLIC_DATA_DIR / "registration-routing.json"`, and
    `f"{LEDGER_PATH.as_posix()} ..."` for a message that has to name the
    file it could not read.
    """
    written = [
        f"{name}:{line}: {value!r} writes out {declared}"
        for name, source in swept()
        for line, value, declared in offences_in(source)
    ]

    assert not written, (
        "these write out a path config/boundary.yml hands to the instance, "
        "which paths.py already names from that declaration:\n" + "\n".join(written)
    )


# ------------------------------------------------------------------ #
# The rule bites, and it leaves the three lookalikes alone.
# ------------------------------------------------------------------ #


REFUSED = (
    'PATH = Path("data") / "config.yml"',
    'path = root / "data" / "speakers.yml"',
    'path = repo_root() / "keys" / "events" / f"{event_id}.pub"',
    'out = root / "public-data"',
    'REGISTER = Path("docs") / "governance" / "register.md"',
    'EVENTS = Path("data")',
    'raise ValueError("data/queue-ledger.yml holds no usable handled list")',
    'return f"data/events/{event_id}/registrations.enc"',
)

ADMITTED = (
    'fields = payload.get("data", {}).get("fields")',
    'wrapped = payload.get("data")',
    'DOMAIN: Final = "data"',
    'PATH = DATA_DIR / "config.yml"',
    'path = root / DATA_DIR / "speakers.yml"',
    'KEYS = paths.KEYS_DIR / "events"',
    'raise ValueError(f"{LEDGER_PATH.as_posix()} holds no usable handled list")',
    'DEFAULT_PATH: Final = Path("brand") / "convener" / "brand.json"',
    'TOOLKIT_DIR: Final = Path("docs") / "toolkit"',
    'BUDGET_PATH: Final = Path("config") / "actions-budget.yml"',
    '"""data/config.yml is the instance\'s own board configuration."""',
)


@pytest.mark.parametrize("source", REFUSED)
def test_a_written_out_instance_path_is_caught(source: str) -> None:
    assert offences_in(source), f"{source!r} writes out an instance path"


@pytest.mark.parametrize("source", ADMITTED)
def test_a_lookalike_is_left_alone(source: str) -> None:
    """The load-bearing half. Three of these are a `data` key in somebody
    else's vocabulary, four are the constants this rule asks for, and the
    rest are product paths and a docstring naming a path in prose."""
    assert not offences_in(source), f"{source!r} is not a written-out path"
