"""Where a module of `convener_ops` sits is what its name says it is about.

Forty-three modules in one directory, listed alphabetically, told a reader
nothing: `agenda.py`, `announce.py`, `attendance.py` are three unrelated jobs
in a row, and the only way to find the one holding a rule was to open files
until one of them held it. They sit in seven sub-packages now, one per
subject, and the rules that keep them there are the ones this module holds.

**Nothing sits at the package root.** `cli.py` did, and the reason it was
left there was that it is the way in -- which was taken to mean it could not
be placed. It reached 6 166 lines, a fifth of the package and three and a
half times the next largest, and it held the console commands of all six
other sub-packages side by side in one alphabet: the defect the first
paragraph above describes, one directory down. `cli/` is a sub-package like
the rest now, with one module per sub-package it dispatches into, and a
module at the root is the drawer this structure exists to close.

**Each sub-package says what it gathers, in one sentence.** The directory
name is a label; the sentence is what tells a reader whether the module they
are looking for is behind it. One sentence rather than a paragraph is a
limit with a purpose -- a sub-package needing two is a sub-package holding
two subjects -- and the reason a module docstring, which may be as long as
its module needs, is not held to the same rule.

The root `__init__.py` stays empty, and that is the same rule seen from the
other side. Re-exporting the flat names from it would keep `from
convener_ops import sweep` working, and every import in this repository
would then go on saying nothing about where anything is.

**`convener_ops/cli/__init__.py` is the one `__init__.py` that re-exports,
and it re-exports exactly one thing.** `tools/pyproject.toml` names a module
and an attribute in a string, `convener_ops.cli:validate`, and those strings
are a published surface: they are the command names an operator types and
every workflow runs, so they do not move when a function does. That is a
reason to re-export the console commands and no reason at all to re-export
anything else, so the check below is an equality against the declaration
rather than a floor -- a helper added to that file would put the flat names
back one at a time.

**No module grows past the ceiling.** The one that did was invisible from a
directory listing, which is why nothing caught it: every gate this
repository runs reads a module's contents, and none of them reads its size.
The ceiling is not a style preference and it is not sharp. It sits above the
largest module the package has, with room, so reaching it means a module has
roughly doubled the one below it rather than drifted a few lines over. A
module that reaches it is being asked to split, and this is what asks.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path
from typing import Final

import convener_ops
import convener_ops.cli
from convener_ops.declaration.paths import repo_root

PACKAGE = Path(convener_ops.__file__).parent
COMMAND_LINE = Path(convener_ops.cli.__file__).parent

#: Where the console commands are declared, outside Python.
DECLARATION: Final = repo_root() / "tools" / "pyproject.toml"

#: The two modules of `cli/` that are not named after a sub-package, each
#: because it holds something every command module needs and no command
#: module owns: the dialect the store's own YAML files are written in, and
#: the file a workflow step reads its predecessor's answer out of.
SHARED: Final = frozenset({"store", "step_output"})

#: The most lines a module of this package may hold. See this module's own
#: docstring for what the number is and is not.
CEILING: Final = 2000

#: A sentence ends and something else begins. Applied to the docstring with
#: its own line breaks collapsed, so a sentence wrapped across three lines
#: still reads as one.
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


def sub_packages() -> list[Path]:
    """Every sub-package of `convener_ops`, read off the directory rather
    than listed here: adding one puts it under both rules below on the
    commit that adds it."""
    return sorted(
        path
        for path in PACKAGE.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    )


def declared_commands() -> dict[str, str]:
    """Every console command `tools/pyproject.toml` declares, and what it
    points at."""
    data = tomllib.loads(DECLARATION.read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]
    assert isinstance(scripts, dict) and scripts, "no console command is declared"
    return {str(name): str(target) for name, target in scripts.items()}


def docstring_of(path: Path) -> str | None:
    return ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))


def test_the_walk_finds_the_sub_packages() -> None:
    """A read that found nothing would make both rules below pass over an
    empty directory."""
    found = [path.name for path in sub_packages()]

    assert len(found) >= 5, (
        f"{PACKAGE.name} holds {found}, which is not a package that was "
        "grouped -- either the walk is reading the wrong directory or the "
        "sub-packages are gone"
    )


def test_no_module_sits_at_the_package_root() -> None:
    """The rule, on the real package."""
    at_root = sorted(
        path.name for path in PACKAGE.glob("*.py") if path.name != "__init__.py"
    )

    assert at_root == [], (
        f"{at_root} sit at the root of `convener_ops`, where nothing but "
        "`__init__.py` belongs. Every module goes in the sub-package whose "
        "subject it is about; a module that fits none of them is a "
        "sub-package this package is missing, never a file left in the "
        "hallway"
    )


def test_every_sub_package_says_what_it_gathers() -> None:
    """A directory with an empty `__init__.py` is a folder, not a
    sub-package: it groups files without saying what the grouping is."""
    silent = [
        path.name for path in sub_packages() if not (docstring_of(path / "__init__.py"))
    ]

    assert silent == [], (
        f"{silent} carry no docstring in their `__init__.py`. A "
        "sub-package's own file is where a reader is told what is behind "
        "the directory name"
    )


def test_every_sub_package_says_it_in_one_sentence() -> None:
    """One sentence, measured rather than trusted to a review."""
    offending: list[str] = []
    for path in sub_packages():
        docstring = docstring_of(path / "__init__.py")
        if docstring is None:
            continue
        collapsed = " ".join(docstring.split())
        sentences = SENTENCE_END.findall(collapsed)
        if len(sentences) != 1 or not collapsed.endswith((".", "!", "?")):
            offending.append(f"{path.name}: {len(sentences)} sentence(s)")

    assert offending == [], (
        f"{offending} -- a sub-package states what it gathers in one "
        "sentence. Needing a second one is the signal that the directory "
        "is holding two subjects and wants splitting, not that the "
        "sentence wants extending"
    )


def test_the_package_root_re_exports_nothing() -> None:
    """The other side of the first rule. A `from .maintenance.sweep import
    sweep` written here would let every old flat import go on working, and
    the structure would then be invisible at every call site -- which is
    the whole of what moving the files bought."""
    body = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8")).body

    assert body == [] or (len(body) == 1 and isinstance(body[0], ast.Expr)), (
        "`convener_ops/__init__.py` holds code. It carries a docstring or "
        "nothing at all: an import here is a re-export, and a re-export "
        "puts the flat names back"
    )


def test_every_module_of_the_command_line_is_named_after_a_sub_package() -> None:
    """`cli/` mirrors what it dispatches into, so a reader looking for the
    command that certifies an attendee reads the same word twice."""
    known = {path.name for path in sub_packages()} | SHARED
    unplaced = sorted(
        path.stem
        for path in COMMAND_LINE.glob("*.py")
        if path.stem != "__init__" and path.stem not in known
    )

    assert unplaced == [], (
        f"{unplaced} sit in `convener_ops/cli/` under a name no sub-package "
        f"of `convener_ops` carries and that {sorted(SHARED)} does not "
        "account for. A command whose subject is none of them is a "
        "sub-package this package is missing"
    )


def test_the_command_line_re_exports_exactly_what_is_declared() -> None:
    """The one re-export in this package, held to the declaration that
    makes it necessary rather than to a floor."""
    declared = {
        target.partition(":")[2]
        for target in declared_commands().values()
        if target.partition(":")[0] == "convener_ops.cli"
    }
    assert len(declared) > 40, (
        f"only {len(declared)} commands are declared against "
        "`convener_ops.cli`; the declaration moved and this check has "
        "almost no subject"
    )
    exported = set(convener_ops.cli.__all__)

    assert exported == declared, (
        "`convener_ops/cli/__init__.py` re-exports "
        f"{sorted(exported - declared)} that no console command names, and "
        f"is missing {sorted(declared - exported)} that one does. It "
        "carries the declared surface and nothing else: a helper added "
        "here is a flat name put back, and a command missing here is a "
        "console script that cannot start"
    )


def test_every_re_exported_name_is_actually_imported() -> None:
    """A re-export that resolves is not yet a re-export of the right thing:
    `__all__` and the imports beneath it are two lists, and a name in one
    and not the other satisfies the equality above."""
    missing = [
        name for name in convener_ops.cli.__all__ if not hasattr(convener_ops.cli, name)
    ]

    assert missing == [], (
        f"{missing} are in `convener_ops.cli.__all__` and are not imported "
        "into it -- the console scripts naming them fail at start-up, "
        "where no gate here would see it"
    )


def test_no_module_of_the_package_grows_past_the_ceiling() -> None:
    """The rule that was missing when one module reached 6 166 lines."""
    oversized = sorted(
        f"{path.relative_to(PACKAGE).as_posix()}: {count}"
        for path in PACKAGE.rglob("*.py")
        if (count := len(path.read_text(encoding="utf-8").splitlines())) > CEILING
    )

    assert oversized == [], (
        f"{oversized} are over {CEILING} lines. A module that long holds "
        "more than one subject -- the way in that held every command of "
        "six sub-packages did -- and the fix is the sub-package it is "
        "asking for, never a higher ceiling"
    )


def test_the_size_sweep_is_recursive() -> None:
    """A non-recursive `glob` reads the root of a package that has nothing
    at its root, and reports every module under it clean."""
    counted = {path.relative_to(PACKAGE).as_posix() for path in PACKAGE.rglob("*.py")}

    assert len(counted) > 50, (
        f"the size sweep reads {len(counted)} modules of a package that "
        "ships far more; a flat walk over a package whose root is empty "
        "measures nothing at all"
    )
    assert any("/" in name for name in counted), (
        "the size sweep reached no module inside a sub-package, which is "
        "every module this package has"
    )
