"""One shape for the heading of every README inside a directory.

Twelve of them, and four shapes. Two repeated the name of the directory
the reader had just clicked -- `# site`, `# screenshots`. Three set that
name as a path in backticks -- ``# `instance/public-data/` ``. The rest
named the thing: `# Design tokens`, `# The example instance`,
`# Authentication relay`. The last is the one worth keeping, because a
heading is the first line of the page and the directory's name is the one
fact the reader already has.

**Two shapes are refused, and only two.** A heading that is the
directory's own name, letter for letter with case ignored; and a heading
whose whole content is a path in backticks. Both are mechanical, both are
what was actually found here, and neither asks whether a title is a good
one -- `docs/engineering/content-rules.md` section 7 says which of its
rules are a reviewer's and this module claims to be none of them.

**Why letter for letter and not something looser.** `# Form relay` over
`services/form-relay/` is a prose title and has to stay one: it reads as
a noun phrase, and the two differ only by a hyphen. A rule that
normalised punctuation away would refuse it, and a control that fires on
correct prose is a control somebody turns off --
`test_writing_rules.py` makes the same argument for its own narrowness,
about the same class of sentence. What is left is the literal shape: a
heading indistinguishable from the breadcrumb above it.

**The repository's own `README.md` is outside this by the rule rather
than by an exception.** It sits in no directory a reader clicked, and the
name of the directory a clone happens to land in is not a fact this
repository holds; `git ls-files` gives that file no directory component
at all, which is the same statement in the form this module reads.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
from pathlib import PurePosixPath
from typing import Final

import pytest

from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()

#: The file this module is about.
README: Final = "README.md"

#: A level-one heading. The first one in the file is the page's own title;
#: `assets/brand/convener/README.md` opens with an HTML comment above it,
#: so the first *line* is not the same thing as the first heading.
H1: Final = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)

#: A heading that is one backticked run holding a path separator, and
#: nothing else: ``# `instance/keys/events/` ``.
BACKTICKED_PATH: Final = re.compile(r"^`[^`]*/[^`]*`$")


def tracked_readmes() -> tuple[str, ...]:
    """Every `README.md` this repository tracks inside a directory.

    The index rather than a walk: a README in somebody's working copy is
    not a page this repository publishes. The repository's own front page
    has no directory component and is not one of these -- see the module
    docstring.
    """
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", f"*{README}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return tuple(sorted(name for name in listed if "/" in name))


def heading_of(text: str) -> str | None:
    """The first level-one heading in `text`, or `None` if it has none."""
    found = H1.search(text)
    return found.group(1) if found else None


def echoes_its_directory(path: str, heading: str) -> bool:
    """Whether `heading` is the name of the directory `path` sits in.

    Letter for letter, case ignored. See the module docstring for why the
    comparison is not looser than that.
    """
    return heading.strip().casefold() == PurePosixPath(path).parent.name.casefold()


def is_a_backticked_path(heading: str) -> bool:
    return bool(BACKTICKED_PATH.match(heading.strip()))


# ------------------------------------------------------------------ #
# The repository as it stands.
# ------------------------------------------------------------------ #


def test_there_are_readmes_to_read() -> None:
    # Non-vacuity: every sweep below passes over a repository with no
    # README inside any directory, and that is not this one.
    assert tracked_readmes()


@pytest.mark.parametrize("name", tracked_readmes())
def test_every_readme_opens_with_a_heading(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    assert heading_of(text), (
        f"{name} carries no level-one heading -- a reader who opens it is "
        "shown the first paragraph and nothing that says what the page is."
    )


@pytest.mark.parametrize("name", tracked_readmes())
def test_no_readme_heading_is_its_own_directory_name(name: str) -> None:
    heading = heading_of((ROOT / name).read_text(encoding="utf-8")) or ""
    assert not echoes_its_directory(name, heading), (
        f"{name} is headed with the name of the directory it sits in "
        f"({heading!r}) -- which the reader read on the way here. Say what "
        "the thing is instead."
    )


@pytest.mark.parametrize("name", tracked_readmes())
def test_no_readme_heading_is_a_path(name: str) -> None:
    heading = heading_of((ROOT / name).read_text(encoding="utf-8")) or ""
    assert not is_a_backticked_path(heading), (
        f"{name} is headed with its own path ({heading!r}). A path is a "
        "location rather than a description, and the reader followed one "
        "to get here."
    )


# ------------------------------------------------------------------ #
# The rules bite, against headings somebody made up.
# ------------------------------------------------------------------ #


def test_a_bare_directory_name_is_refused() -> None:
    assert echoes_its_directory("site/README.md", "site")
    assert echoes_its_directory("assets/screenshots/README.md", "Screenshots")


def test_a_prose_title_over_a_hyphenated_directory_is_admitted() -> None:
    # The sentence the narrowness is for: `services/form-relay/README.md`
    # is headed `# Form relay` and stays.
    assert not echoes_its_directory("services/form-relay/README.md", "Form relay")


def test_a_prose_title_naming_the_thing_is_admitted() -> None:
    assert not echoes_its_directory(
        "examples/the-example-collective/README.md", "The example instance"
    )
    assert not is_a_backticked_path("The example instance")


def test_a_backticked_path_is_refused() -> None:
    assert is_a_backticked_path("`instance/public-data/`")
    assert is_a_backticked_path("`docs/handbook/`")


def test_a_backticked_word_that_is_no_path_is_admitted() -> None:
    # `# `brand.json`` names a file in the directory rather than the
    # directory, and this rule says nothing about it.
    assert not is_a_backticked_path("`brand.json`")


def test_the_heading_is_the_first_one_and_not_the_first_line() -> None:
    text = "<!-- cspell:ignore currentColor -->\n# Convener - the product's own mark\n"
    assert heading_of(text) == "Convener - the product's own mark"


def test_a_page_with_no_heading_reads_as_none() -> None:
    assert heading_of("no heading here\n") is None


def test_the_repositorys_own_front_page_is_not_swept() -> None:
    # It has no directory component, so `tracked_readmes` never yields it.
    assert README not in tracked_readmes()
