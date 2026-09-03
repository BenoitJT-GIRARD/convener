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

**`tools/tests/cli/` mirrors `cli/`, and the ceiling above does not reach
it.** The test tree carried the same defect one directory over --
`test_cli.py`, 7 795 lines, the tests of six sub-packages' commands in one
alphabet and larger than the module it was about. What found it was not its
size: it was that its name said `cli`, which is a package, where every
other module in that directory is named after something in it. So the rule
below is the mirror rather than a number, and it is the same rule
`test_every_module_of_the_command_line_is_named_after_a_sub_package` holds
one tree over, read from the test side.

**And the half of that rule that is not about the mirror holds everywhere.**
`tools/tests/cli/` mirrors a package, so it can be asked the strong
question -- is this module named after something in the package it mirrors
-- and no other test directory can. What every one of them can be asked is
the question that actually found `test_cli.py`: is this module named after
the directory it is sitting in. That question lived inside the mirror and
nowhere else, so two modules on the other side of the tree carried their
own directory's name with nothing to say so: the tests of
`derivation/repository.py` and the tests of `governance/rule.py`, each
named after the package holding it. They are
`tools/tests/derivation/test_repository.py` and
`tools/tests/governance/test_rule.py` now, and
`test_no_test_module_is_named_after_the_package_that_holds_it` is that
question asked of the whole tree.

A suffix is not the same thing and is not refused:
`tools/tests/governance/test_governance_fixture.py` is about the fixture the
two languages share and `tools/tests/derivation/test_derivation_guard.py`
about `derivation/derivation_guard.py`, and each names a subject the
directory has rather than the directory. What the rule refuses is the name
that says only *everything behind this door*, because that is a file with
no subject and it grows until somebody measures it.

A number was measured and not taken. `CEILING` applied to `tools/tests/`
is born refusing three modules this has nothing to do with --
`repository/test_workflows.py` at 6 001, `repository/test_site.py` at
2 915, `publication/test_brand.py` at 2 053 -- and a control that is red
on the day it is written is one somebody turns off. Any number those three
pass is 6 002 or more, and `test_cli.py` is the only file in this
repository's history that has ever been above it: a ceiling picked to name
one file is a list of one wearing a number's clothes. The two largest
modules the split produced are 1 738 and 1 653 lines, under the package's
own ceiling, and they got there by mirroring rather than by being counted.
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Iterable
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

#: Every test of this repository's Python. `COMMAND_LINE_TESTS` is one
#: directory of it, and the strong mirror rule reaches only that one; the
#: rule about a module named after its own directory reaches all of this.
TESTS: Final = repo_root() / "tools" / "tests"

#: Where the tests of `convener_ops/cli/` live, mirroring it directory for
#: directory.
COMMAND_LINE_TESTS: Final = TESTS / "cli"

#: The one module under `tools/tests/cli/` named after nothing in
#: `convener_ops/cli/`, and the reason it is not a hole in the rule: D-14's
#: file-format boundary is a property of the whole store as both languages
#: read it, so it is about `cli/store.py` and about `site/`'s and
#: `services/`' own parsers at once, and naming it after either half would
#: say the boundary has one side. A second entry here wants an argument of
#: the same kind, in writing, next to this one.
CROSSES_THE_MIRROR: Final = frozenset({"yaml_boundary"})

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


def command_line_modules() -> frozenset[str]:
    """Every name a module of `convener_ops/cli/` carries, its
    sub-packages included, read off the package rather than listed."""
    return frozenset(
        path.stem if path.suffix == ".py" else path.name
        for path in COMMAND_LINE.rglob("*")
        if (path.suffix == ".py" and path.stem != "__init__")
        or (path.is_dir() and (path / "__init__.py").is_file())
    )


def test_the_mirror_reads_both_trees() -> None:
    """Non-vacuity, on both sides at once: an empty package or an empty
    test directory makes the rule below a comparison between two empty
    sets, which passes."""
    assert len(command_line_modules()) >= 10, (
        f"`convener_ops/cli/` reads as {sorted(command_line_modules())}, "
        "which is not the package this mirrors"
    )
    found = sorted(
        path.name for path in COMMAND_LINE_TESTS.rglob("test_*.py") if path.is_file()
    )
    assert len(found) >= 10, (
        f"`tools/tests/cli/` holds {found}, which is not a mirrored test "
        "tree -- the rule below would pass over an empty directory"
    )


def test_every_test_module_of_the_command_line_is_named_after_one() -> None:
    """The rule `test_cli.py` broke, from the side that broke it.

    A test module in `tools/tests/cli/` is named after the module of
    `convener_ops/cli/` it exercises, optionally with a suffix saying
    which half of it -- `test_certificate_delivery.py` beside
    `test_certificate.py`, because one command module dispatches into two
    of the package's own. A module named after the *package* is the tests
    of everything behind it in one file, which is what 7 795 lines in one
    alphabet was.
    """
    known = command_line_modules()
    unplaced = sorted(
        path.relative_to(COMMAND_LINE_TESTS).as_posix()
        for path in COMMAND_LINE_TESTS.rglob("test_*.py")
        if (stem := path.stem[len("test_") :]) not in CROSSES_THE_MIRROR
        and not any(stem == name or stem.startswith(f"{name}_") for name in known)
    )

    assert unplaced == [], (
        f"{unplaced} sit in `tools/tests/cli/` under a name no module of "
        "`convener_ops/cli/` carries. A test module is named after what it "
        "is about, and the way in is not a subject: a module named after "
        f"the package holds the tests of all {len(known)} of them, which "
        "is the file this rule exists downstream of"
    )


def test_the_mirror_can_tell_a_package_name_from_a_module_name() -> None:
    """The positive control, on the name that was there: `cli` is a
    directory of `convener_ops/`, not a module of `convener_ops/cli/`, and
    a rule that admitted it would admit the file it was written for."""
    known = command_line_modules()
    assert not any(name == "cli" or "cli".startswith(f"{name}_") for name in known), (
        "`cli` reads as a module of `convener_ops/cli/`, so the rule above "
        "would admit `test_cli.py` back"
    )
    assert "certificate" in known and "journey" in known


def named_after_their_package(paths: Iterable[Path]) -> list[str]:
    """Every path whose module name is exactly its own directory's name.

    Takes the paths rather than walking, so the rule can be shown what it
    refuses without this repository having to hold one.
    """
    return sorted(
        path.as_posix()
        for path in paths
        if path.stem.removeprefix("test_") == path.parent.name
    )


def test_the_rule_reads_a_package_name_apart_from_a_subject() -> None:
    """Both directions, on names this tree has held.

    A rule refusing nothing and a rule refusing everything both leave an
    empty list behind on the day they are written."""
    made_up = [
        Path("governance/test_governance.py"),
        Path("derivation/test_derivation.py"),
        Path("governance/test_rule.py"),
        Path("governance/test_governance_fixture.py"),
        Path("derivation/test_derivation_guard.py"),
        Path("cli/journey/test_attendance.py"),
    ]

    assert named_after_their_package(made_up) == [
        "derivation/test_derivation.py",
        "governance/test_governance.py",
    ]


def test_no_test_module_is_named_after_the_package_that_holds_it() -> None:
    """`test_cli.py`'s rule, on every directory of the test tree.

    The mirror above can only be asked of `tools/tests/cli/`, because it is
    the only directory mirroring a package name for name. This is the half
    that needs no mirror, and it is the half that actually found
    `test_cli.py`: a module whose name is its own directory's holds the
    tests of everything behind that directory, which is a file with no
    subject and no reason to stop growing.
    """
    modules = sorted(TESTS.rglob("test_*.py"))
    assert len(modules) > 100, (
        f"the walk found {len(modules)} test modules, which is not this "
        "repository's test tree -- the rule below would pass over nothing"
    )
    named = named_after_their_package(path.relative_to(TESTS) for path in modules)

    assert named == [], (
        f"{named} carry the name of the directory holding them rather than "
        "of anything inside it. A test module is named after its subject, "
        "and a package is not a subject: `tests/cli/test_cli.py` reached "
        "7 795 lines under that name before its own directory's rule was "
        "written, and this is that rule with no mirror needed"
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
