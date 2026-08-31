"""One way in per tree, and `README.md` is where a reader is handed it.

`tools/tests/test_docs_directory.py` holds every page under `docs/` to one
of three trees. That rule says where a page sits and nothing about how
anybody arrives: three trees existed with nothing at the front door saying
which was whose, so a reader who opened the repository chose by directory
name and found out from the contents.

Three claims are pinned here, and both halves of each are read out of the
repository rather than transcribed:

* **Every tree has an index.** The trees come from the tracked files under
  `docs/`, so a fourth tree added tomorrow needs one too, with nothing
  here to edit.
* **Every index is named in `README.md`, and every entry point `README.md`
  offers is a tree.** Derived from the file's own links, so an index that
  stops being reachable fails, and so does a link left behind by a tree
  that was renamed or removed.
* **Each index names the other two.** That is what a reader who opened the
  wrong tree needs: the way out on the page they landed on, rather than
  back at a README they did not come through.

**What is not held here.** Whether an index says anything worth reading is
not a property a test can carry. What a test can carry is that the three
exist, that they are reachable, and that they name each other.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final

import pytest
from test_cross_references import _tracked

from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()

#: The directory this module is about, spelt with its separator for the
#: reason `test_docs_directory.py` spells it that way: a sibling whose name
#: merely opens with it is not inside it.
DOCS: Final = "docs/"

#: The file a tree is entered through, relative to the tree.
INDEX: Final = "index.md"

#: The one file that hands a reader the three. Named here, read below.
README: Final = "README.md"

#: An inline Markdown link's target. Reference-style links are matched by
#: nothing here and are used by none of these files.
LINK: Final = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def trees(tracked: Iterable[str]) -> tuple[str, ...]:
    """Every tree under `docs/`, read from the files this repository tracks.

    A directory holding a tracked file is a tree. Nothing sits at the root
    of `docs/` -- `test_docs_directory.py` refuses that -- so the first
    segment after `docs/` is a tree's name whenever there is one.
    """
    found = set()
    for name in tracked:
        if not name.startswith(DOCS):
            continue
        rest = name[len(DOCS) :]
        if "/" in rest:
            found.add(rest.split("/", 1)[0])
    return tuple(sorted(found))


def entry_points(text: str) -> tuple[str, ...]:
    """Every tree a text offers a way into, read from its own links.

    A link at `docs/<tree>/index.md` is an entry point and names its tree.
    Every other link `README.md` carries -- and it carries many, into
    single pages under `docs/` and out of `docs/` entirely -- is not one.
    """
    found = set()
    tail = f"/{INDEX}"
    for href in LINK.findall(text):
        target = href.split("#", 1)[0]
        if not target.startswith(DOCS) or not target.endswith(tail):
            continue
        rest = target[len(DOCS) : -len(tail)]
        if rest and "/" not in rest:
            found.add(rest)
    return tuple(sorted(found))


def siblings_missing(indexes: Mapping[str, str]) -> tuple[str, ...]:
    """Every `tree -> sibling` an index fails to name, as `"a -> b"`.

    `indexes` maps a tree's name to its index's text. A page under
    `docs/a/` reaches `docs/b/index.md` as `../b/index.md`, which is the
    form looked for.
    """
    absent = []
    for tree in sorted(indexes):
        targets = {href.split("#", 1)[0] for href in LINK.findall(indexes[tree])}
        for other in sorted(indexes):
            if other != tree and f"../{other}/{INDEX}" not in targets:
                absent.append(f"{tree} -> {other}")
    return tuple(absent)


def _index_of(tree: str) -> Path:
    return ROOT / DOCS / tree / INDEX


def _indexes() -> dict[str, str]:
    return {
        tree: _index_of(tree).read_text(encoding="utf-8")
        for tree in trees(_tracked())
        if _index_of(tree).is_file()
    }


# ------------------------------------------------------------------ #
# The repository as it stands.
# ------------------------------------------------------------------ #


def test_there_are_trees_to_be_entered() -> None:
    # Non-vacuity: every sweep below passes over a `docs/` holding no tree
    # at all, and that is not a repository this rule describes.
    assert trees(_tracked())


def test_every_tree_carries_an_index() -> None:
    carried = set(_tracked())
    unentered = [
        tree for tree in trees(carried) if f"{DOCS}{tree}/{INDEX}" not in carried
    ]
    assert not unentered, (
        f"{unentered} hold pages and no {INDEX} -- a reader who opens one "
        "reads its filenames to find out whether it is theirs."
    )


def test_the_readme_offers_a_way_into_every_tree() -> None:
    offered = set(entry_points((ROOT / README).read_text(encoding="utf-8")))
    carried = set(trees(_tracked()))
    assert not carried - offered, (
        f"{sorted(carried - offered)} sit under {DOCS} and {README} links "
        "to neither. A tree nobody is sent to is a tree nobody reads."
    )
    assert not offered - carried, (
        f"{sorted(offered - carried)} are linked from {README} and are no "
        f"tree under {DOCS}. A renamed tree leaves this link behind it."
    )


def test_every_entry_point_the_readme_offers_is_tracked() -> None:
    carried = set(_tracked())
    text = (ROOT / README).read_text(encoding="utf-8")
    absent = [
        tree for tree in entry_points(text) if f"{DOCS}{tree}/{INDEX}" not in carried
    ]
    assert not absent, f"{README} points into {absent}, which nothing here carries"


def test_each_index_names_the_other_trees() -> None:
    unmapped = siblings_missing(_indexes())
    assert not unmapped, (
        f"{list(unmapped)} -- an index naming no sibling leaves a reader in "
        "the wrong tree with the README as their only way out."
    )


@pytest.mark.parametrize("tree", trees(_tracked()))
def test_each_index_holds_prose(tree: str) -> None:
    assert _index_of(tree).read_text(encoding="utf-8").strip()


# ------------------------------------------------------------------ #
# The rules bite, against repositories somebody made up.
# ------------------------------------------------------------------ #


def test_a_tree_is_a_directory_holding_a_tracked_file() -> None:
    assert trees(
        ("docs/handbook/roles.md", "docs/operating/tools.md", "README.md")
    ) == (
        "handbook",
        "operating",
    )


def test_a_file_at_the_root_of_docs_names_no_tree() -> None:
    # `test_docs_directory.py` refuses that file. This module reads no tree
    # out of it.
    assert trees(("docs/index.md",)) == ()


def test_a_sibling_of_docs_is_not_a_tree() -> None:
    assert trees(("docsite/page.md",)) == ()


def test_an_entry_point_is_a_link_at_a_tree_s_index() -> None:
    text = "[a](docs/handbook/index.md) and [b](docs/operating/index.md#what-is-here)"
    assert entry_points(text) == ("handbook", "operating")


def test_a_link_to_a_single_page_is_not_an_entry_point() -> None:
    assert entry_points("[r](docs/handbook/roles.md)") == ()


def test_an_index_deeper_than_a_tree_is_not_an_entry_point() -> None:
    # `docs/handbook/toolkit/index.md` is a page inside a tree rather than
    # the way into one, and a README link to it says nothing about a tree.
    assert entry_points("[t](docs/handbook/toolkit/index.md)") == ()


def test_a_tree_with_no_index_is_reported() -> None:
    tracked = {"docs/handbook/index.md", "docs/operating/tools.md"}
    assert [
        tree for tree in trees(tracked) if f"docs/{tree}/index.md" not in tracked
    ] == ["operating"]


def test_an_index_naming_no_sibling_is_refused() -> None:
    assert siblings_missing({"a": "[b](../b/index.md)", "b": "nothing"}) == ("b -> a",)


def test_an_index_naming_every_sibling_is_admitted() -> None:
    assert (
        siblings_missing({"a": "[b](../b/index.md)", "b": "[a](../a/index.md)"}) == ()
    )


def test_a_sibling_named_with_an_anchor_still_counts() -> None:
    pages = {"a": "[b](../b/index.md#what-is-not-here)", "b": "[a](../a/index.md)"}
    assert siblings_missing(pages) == ()


def test_a_lone_tree_owes_no_sibling() -> None:
    assert siblings_missing({"a": "nothing"}) == ()
