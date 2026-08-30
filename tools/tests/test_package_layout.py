"""Where a module of `convener_ops` sits is what its name says it is about.

Forty-three modules in one directory, listed alphabetically, told a reader
nothing: `agenda.py`, `announce.py`, `attendance.py` are three unrelated jobs
in a row, and the only way to find the one holding a rule was to open files
until one of them held it. They sit in six sub-packages now, one per subject,
and the two rules that keep them there are the ones this module holds.

**`cli.py` stays at the root**, because it is the way in: every console entry
point `tools/pyproject.toml` declares but four resolves to a function in it,
and it imports from every sub-package there is. Nothing else may join it. A
module left at the root is a module nobody had to place, and a root that
accepts one is the drawer this structure exists to close.

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
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import convener_ops

PACKAGE = Path(convener_ops.__file__).parent

#: The one module allowed to sit beside the sub-packages.
ENTRY_POINT = "cli.py"

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


def test_no_module_sits_at_the_package_root_but_the_command_line() -> None:
    """The rule, on the real package."""
    at_root = sorted(
        path.name
        for path in PACKAGE.glob("*.py")
        if path.name not in {ENTRY_POINT, "__init__.py"}
    )

    assert at_root == [], (
        f"{at_root} sit at the root of `convener_ops`, where only "
        f"`{ENTRY_POINT}` belongs. Every other module goes in the "
        "sub-package whose subject it is about; a module that fits none of "
        "them is a sub-package this package is missing, never a file left "
        "in the hallway"
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
