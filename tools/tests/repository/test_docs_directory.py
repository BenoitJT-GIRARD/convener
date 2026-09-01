"""Where a page under `docs/` has to sit.

`docs/` served three readers out of one flat directory. The volunteer's
manual, the operator's reference and the engineering record sat beside
each other, and nothing on the way in said which part was whose: two
index files at the root, one written for a volunteer and one for a
developer, were the visible end of it.

The three readers are three directories now -- `handbook/`, `operating/`
and `engineering/` -- and this module is what keeps them that way. It
reads the tracked tree and refuses a file under `docs/` sitting in none
of them, so a page dropped back at the root is a failing check rather
than the start of a fourth flat tree. `docs/engineering/content-rules.md`
states the same three in prose, for a person, and one of the checks below
holds that statement to this list.

**An exception is named here, with its reason beside it.** `EXCEPTIONS`
is the one place a path outside the three may be admitted, and it holds
one: `docs/README.md`, the page GitHub renders when a person opens the
directory. Both halves are refused -- a tracked file nobody named, and a
name nobody tracks -- which is the shape
`tools/scripts/generate_directory_map.py::purposes_for` already uses for
its own table, and for the same reason: a list that may only grow is a
list that stops describing anything. A path that stops being an exception
comes off this one on the commit that moves it.

**Tracked files, and only those.** `docs/handbook/assets/` held a
designer's own working material beside the three templates a volunteer
downloads: `.gitignore` named it, no clone ever had it, and a sweep of
the disk would have placed ten files nobody here can place. It sits
under `instance/data/`, beside the charter it is the source of, since
2026-09-01; the reading is the index either way, because nothing this
repository does not carry is anybody's to place.

**What this does not cover.** Whether a page is published at all is
`app/src/content/registry.ts`'s answer and
`app/tests/registered-links.test.ts`'s to hold, and whether a link
resolves is that suite's too. This module asks one question, about where
a file sits.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final

import pytest

from convener_ops.declaration.paths import repo_root
from repository.test_cross_references import _tracked

ROOT: Final = repo_root()

#: The directory this module is about, spelt with its separator so that a
#: sibling whose name merely begins with it is never read as inside it.
DOCS: Final = "docs/"

#: One tree per reader, and the reader each is written for.
TREES: Final[Mapping[str, str]] = {
    "handbook": "the volunteer's manual, which the cockpit serves",
    "operating": "the operator's reference",
    "engineering": "how the system is built, and why",
}

#: The page stating the same three for a person. Read rather than trusted:
#: a tree added here and not there leaves a reader with two answers.
CONTENT_RULES: Final = "docs/engineering/content-rules.md"

#: Every path under `docs/` allowed to sit outside the three trees, with
#: the argument for it. One entry, and the two sweeps below are what keep
#: an entry from becoming a place to put whatever nobody wanted to place.
EXCEPTIONS: Final[Mapping[str, str]] = {
    "docs/README.md": (
        "What GitHub renders when a person opens docs/ in a browser, and "
        "the only file that can be it: GitHub renders a directory's "
        "README.md and looks for nothing else. It sits outside the three "
        "trees because it is how a reader picks one -- three rows of "
        "tree, reader and index, and no page of any tree named on it. A "
        "file of this name was deleted on the commit that made the three "
        "trees, and it was a different thing: a second layout of the "
        "handbook, which docs/handbook/index.md already was."
    ),
}


def misplaced(tracked: Iterable[str], exceptions: Mapping[str, str]) -> tuple[str, ...]:
    """Every tracked path under `docs/` in none of the three trees.

    A file directly at the root of `docs/` has no tree at all, and a file
    under a fourth directory has one nobody declared. Both are the same
    answer, because both leave a reader with nothing that says who the
    page is for.
    """
    found = []
    for name in sorted(tracked):
        if not name.startswith(DOCS) or name in exceptions:
            continue
        rest = name[len(DOCS) :]
        head = rest.split("/", 1)[0] if "/" in rest else ""
        if head not in TREES:
            found.append(name)
    return tuple(found)


def unclaimed(tracked: Iterable[str], exceptions: Mapping[str, str]) -> tuple[str, ...]:
    """Every exception naming a path this repository does not track.

    The other half of the rule. Without it an entry outlives the file it
    was written for, and the list slowly becomes a record of what used to
    need excusing.
    """
    carried = set(tracked)
    return tuple(sorted(path for path in exceptions if path not in carried))


# ------------------------------------------------------------------ #
# The repository as it stands.
# ------------------------------------------------------------------ #


def test_every_page_under_docs_sits_in_one_of_the_three_trees() -> None:
    outside = misplaced(_tracked(), EXCEPTIONS)
    assert not outside, (
        f"{list(outside)} sit under docs/ in none of "
        f"{sorted(TREES)} -- which tree a page is in is what says who it "
        "is written for, so a page in none of them is a page nobody is "
        "told to read. Move it, or name it in EXCEPTIONS with the reason."
    )


def test_every_exception_names_a_file_this_repository_tracks() -> None:
    stale = unclaimed(_tracked(), EXCEPTIONS)
    assert not stale, (
        f"{list(stale)} are excused in EXCEPTIONS and are not tracked. An "
        "entry for a file that is not there excuses nothing and hides the "
        "next one: take it off on the commit that moves the file."
    )


def test_every_exception_carries_a_reason() -> None:
    empty = sorted(path for path, reason in EXCEPTIONS.items() if not reason.strip())
    assert not empty, f"{empty} are excused with no argument written down"


@pytest.mark.parametrize("tree", sorted(TREES))
def test_each_tree_holds_pages(tree: str) -> None:
    # Non-vacuity, one tree at a time: the sweep above passes over an
    # empty `docs/` and over a `docs/` that lost two of its three trees,
    # and neither is a repository this rule is describing.
    carried = [name for name in _tracked() if name.startswith(f"{DOCS}{tree}/")]
    assert carried, f"docs/{tree}/ holds no tracked file"


def test_the_content_rules_state_the_same_three_trees() -> None:
    text = (ROOT / CONTENT_RULES).read_text(encoding="utf-8")
    unstated = sorted(tree for tree in TREES if f"`{tree}/`" not in text)
    assert not unstated, (
        f"{CONTENT_RULES} does not name {unstated} -- it is where a person "
        "reads this rule, and this module is where it is enforced. The two "
        "have to name the same directories."
    )


# ------------------------------------------------------------------ #
# The rule bites, against a tree somebody made up.
# ------------------------------------------------------------------ #


def test_a_page_at_the_root_of_docs_is_refused() -> None:
    tracked = ("docs/index.md", "docs/handbook/roles.md")
    assert misplaced(tracked, {}) == ("docs/index.md",)


def test_a_fourth_tree_is_refused() -> None:
    assert misplaced(("docs/notes/kept.md",), {}) == ("docs/notes/kept.md",)


def test_a_named_exception_is_admitted() -> None:
    assert misplaced(("docs/index.md",), {"docs/index.md": "a reason"}) == ()


def test_an_exception_naming_nothing_is_refused() -> None:
    assert unclaimed(("docs/handbook/roles.md",), {"docs/index.md": "a reason"}) == (
        "docs/index.md",
    )


def test_nothing_outside_docs_is_this_module_s_business() -> None:
    # Including a sibling whose name opens with the same five letters --
    # the reason `DOCS` carries its separator.
    assert misplaced(("README.md", "app/src/main.tsx", "docsite/page.md"), {}) == ()
