"""One way in per tree, and `README.md` is where a reader is handed it.

`tools/tests/test_docs_directory.py` holds every page under `docs/` to one
of three trees. That rule says where a page sits and nothing about how
anybody arrives: three trees existed with nothing at the front door saying
which was whose, so a reader who opened the repository chose by directory
name and found out from the contents.

Four claims are pinned here, and both halves of each are read out of the
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
* **`docs/engineering/content-rules.md` says which trees the cockpit
  renders, and the content registry agrees.** Both sides derived: the
  registry's own `file:` values against the one line that page gives each
  tree. A reader is told which of the three they will meet signed in and
  which they will only ever meet in the repository, and the sentence
  saying so cannot outlive the arrangement it describes.

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

#: Where the content registry names the file behind every key it publishes,
#: and the page telling a person which of the trees a reader meets in the
#: cockpit. Read, both of them, rather than transcribed.
REGISTRY: Final = "app/src/content/registry.ts"
CONTENT_RULES: Final = "docs/engineering/content-rules.md"

#: The claim each tree's own line in `CONTENT_RULES` has to make, and the
#: form of it that says the cockpit renders no page from that tree. One
#: phrase rather than a shape per tree: the sentence a reader needs is the
#: same sentence in all three, and only its object changes.
SERVES: Final = "The cockpit serves"
SERVES_NOTHING: Final = "The cockpit serves nothing"

#: One tree's line in `CONTENT_RULES`, opening with the tree's own name in
#: the form that page writes it: `- **`handbook/`** -- ...`.
BULLET: Final = re.compile(r"^- \*\*`([a-z-]+)/`\*\*.*$", re.MULTILINE)

#: A `file:` value, and the delimiters of the one object literal such a
#: value may be read out of. `app/scripts/handbook-registry.mjs` already
#: had to learn this: a sweep over the whole source reads a path out of an
#: ordinary explanatory comment, including one written to warn against
#: that very path. `_registered_files` slices the literal and drops the
#: comments inside it, the same two steps that script takes.
REGISTERED_FILE: Final = re.compile(r"file:\s*'([^']+)'")
REGISTRY_OPENS: Final = "export const CONTENT_REGISTRY"
REGISTRY_CLOSES: Final = "\n};"
LINE_COMMENT: Final = re.compile(r"^\s*//.*$", re.MULTILINE)


def trees(tracked: Iterable[str]) -> tuple[str, ...]:
    """Every tree under `docs/`, read from the files this repository tracks.

    A directory holding a tracked file is a tree, so the first segment
    after `docs/` is a tree's name whenever there is one. A file directly
    at the root names no tree and contributes nothing here --
    `docs/README.md` is one, and is the only one
    `test_docs_directory.py` admits.
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


def served_trees(registry: str) -> frozenset[str]:
    """Every tree the cockpit renders a page from, read from the registry.

    A registered `file:` is a path under `docs/`, so its first segment is
    the tree. An entry with no segment at all belongs to no tree and says
    nothing here.
    """
    return frozenset(
        value.split("/", 1)[0] for value in _registered_files(registry) if "/" in value
    )


def _registered_files(registry: str) -> tuple[str, ...]:
    """Every `file:` the registry's own object literal names.

    The literal alone, with its `//` comments removed -- see
    `REGISTERED_FILE`'s note for what a sweep over the whole source reads
    instead.
    """
    start = registry.find(REGISTRY_OPENS)
    if start == -1:
        return ()
    end = registry.find(REGISTRY_CLOSES, start + len(REGISTRY_OPENS))
    if end == -1:
        return ()
    block = LINE_COMMENT.sub("", registry[start + len(REGISTRY_OPENS) : end])
    return tuple(REGISTERED_FILE.findall(block))


def tree_bullets(rules: str) -> dict[str, str]:
    """Each tree's own line in `CONTENT_RULES`, by tree name.

    The page gives one line per tree and opens it with the tree's name in
    backticks, which is what is matched. A second line about the same tree
    would replace the first here; the page writes one.
    """
    return {match.group(1): match.group(0) for match in BULLET.finditer(rules)}


def _registry() -> str:
    return (ROOT / REGISTRY).read_text(encoding="utf-8")


def _content_rules() -> str:
    return (ROOT / CONTENT_RULES).read_text(encoding="utf-8")


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
        ("docs/handbook/roles.md", "docs/operating/standing-up.md", "README.md")
    ) == (
        "handbook",
        "operating",
    )


def test_a_file_at_the_root_of_docs_names_no_tree() -> None:
    # `test_docs_directory.py` admits one such file by name and refuses
    # every other. Either way this module reads no tree out of one.
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
    tracked = {"docs/handbook/index.md", "docs/operating/standing-up.md"}
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


def test_the_content_rules_say_which_trees_the_cockpit_serves() -> None:
    """Which trees the cockpit draws from, read from the registry and from
    the page that tells a person the same thing.

    That page used to call the handbook "the tree the cockpit serves", then
    "all three trees". Both were sentences about `registry.ts` written in a
    file nothing compared with it, and both were wrong by the time anybody
    read them -- the second one from the commit that took the last
    `operating/` page out of the registry.

    So the claim is derived on both sides. `served_trees` reads the
    registry's own `file:` values; `tree_bullets` reads the one line
    `content-rules.md` gives each tree; and a bullet says *nothing from
    here* exactly for the trees the registry does not draw from. Neither
    half is a list anybody maintains, so a page registered in a new tree,
    or the last page of a tree unregistered, fails here on the commit that
    does it.
    """
    bullets = tree_bullets(_content_rules())
    served = served_trees(_registry())
    carried = set(trees(_tracked()))

    unstated = sorted(carried - set(bullets))
    assert not unstated, (
        f"{unstated} sit under {DOCS} and {CONTENT_RULES} gives them no "
        "line -- a tree a reader is not told the audience of."
    )
    silent = sorted(tree for tree, line in bullets.items() if SERVES not in line)
    assert not silent, (
        f"{silent} carry no '{SERVES}' in {CONTENT_RULES} -- whether the "
        "cockpit renders a tree is the thing a reader most needs said, and "
        "it is what this check reads."
    )
    wrong = sorted(
        f"{tree}: the page says "
        f"{'nothing' if SERVES_NOTHING in line else 'served'}, "
        f"the registry says {'served' if tree in served else 'nothing'}"
        for tree, line in bullets.items()
        if (SERVES_NOTHING in line) == (tree in served)
    )
    assert not wrong, (
        f"{CONTENT_RULES} and app/src/content/registry.ts disagree about "
        f"which trees the cockpit renders: {wrong}. The registry is the "
        "answer; the page is where a person reads it."
    )


def test_a_served_tree_is_read_out_of_the_registry_s_own_literal() -> None:
    source = (
        "export const CONTENT_REGISTRY = {\n"
        "  'a': { file: 'handbook/roles.md', anchor: null },\n"
        "  'b': { file: 'engineering/schema.md', anchor: null },\n"
        "};\n"
    )
    assert served_trees(source) == frozenset({"handbook", "engineering"})


def test_a_path_named_only_in_a_comment_is_no_tree() -> None:
    # The defect `handbook-registry.mjs` found in its own first version: a
    # comment warning against publishing a path read back out as a path
    # published.
    source = (
        "export const CONTENT_REGISTRY = {\n"
        "  // never file: 'operating/operations.md' -- it names every secret\n"
        "  'a': { file: 'handbook/roles.md', anchor: null },\n"
        "};\n"
    )
    assert served_trees(source) == frozenset({"handbook"})


def test_a_registry_with_no_literal_names_no_tree() -> None:
    assert served_trees("nothing here") == frozenset()


def test_a_tree_s_line_is_found_by_its_own_name() -> None:
    page = (
        "## 6 - Three trees\n\n"
        "- **`handbook/`** - the manual. The cockpit serves most of it.\n"
        "- **`operating/`** - the operator's. The cockpit serves nothing.\n"
    )
    assert sorted(tree_bullets(page)) == ["handbook", "operating"]
    assert SERVES_NOTHING in tree_bullets(page)["operating"]
    assert SERVES_NOTHING not in tree_bullets(page)["handbook"]


def test_prose_naming_a_tree_outside_a_line_is_not_a_bullet() -> None:
    assert tree_bullets("A page under `handbook/` is a volunteer's.") == {}
