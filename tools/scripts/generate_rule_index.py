"""One index of the governance rules, derived from the pages that state them.

Fifteen rules carry a number, and until this file existed no page listed
them. `docs/handbook/governance/board-rules.md` said "a few of the numbered
rules are written on other pages" and named none of them, so the only way to
find where a rule was stated was to search the repository for its number. The
numbering had the same shape: two numbers in the middle of the sequence were
stated nowhere, cited nowhere and retired nowhere, and nothing could say
whether they had ever existed.

The index is generated for the reason
`tools/scripts/generate_directory_map.py` gives about the root: a
hand-written list of the rules would be right on the day it was written and
wrong at the next rule, with nothing able to say so.

What a number is
----------------
**A rule's number is its place in one walk of `docs/`.** The three trees in
the order `docs/README.md` lists them -- the volunteer's handbook, the
operator's manual, the engineering reference -- then the pages of a tree in
path order, then the rules of a page in the order they are written. The walk
is the whole of the order: nothing about a rule's weight is in its number,
and the number's only job is to be a handle that a commit message, a comment
or another page can reach for.

The tree order is read out of `docs/README.md`'s own table rather than
written here, so the front page and this index cannot come to disagree about
which tree a reader meets first. A rule stated on a page under none of those
trees raises, because the walk would have nowhere to put it.

**A rule written between two others takes the number of its place, and every
rule after it moves up one.** That is the price of an order that means
something, and it is a price this repository can pay: nothing outside it
cites a `G-NN`, `git grep -E "G-[0-9]{2}"` lists the whole of what does, and
`tools/tests/repository/test_cross_references.py` fails on any citation left
behind.

**A rule that is withdrawn keeps its number.** `RETIRED` below declares it,
the walk skips it, and no later rule takes it -- the same thing
`declarations/boundary.yml`'s `retired:` does for a path the instance used to
own. Renumbering on every withdrawal would move rules that did not change. So
the sequence is continuous in the sense that can be held: every number from
`G-01` to the highest is either stated by a page or declared retired here,
and `held` refuses any other state.

What is derived, and what is not
--------------------------------
**The rules** come from the pages, in the two shapes a page uses to *name* a
rule rather than to cite one: a heading ending in `(G-NN)`, and the bold run
that opens a paragraph or a list item. Those two shapes are `RULE_HEADING`
and `RULE_LEAD` below, and `tools/tests/repository/test_cross_references.py`
imports them from here rather than carrying a second copy: the sweep that
refuses a citation nothing publishes and the index that lists what is
published have to agree about what publishing a rule looks like, and one
definition is how they agree.

**Each rule's name** is the page's own title for it, with the number taken
off. Nothing curates it here. A row that reads oddly in the table reads oddly
on the page too, and the repair is the heading rather than a second name kept
in this file, which is the copy this generator exists to remove.

**Where a rule is stated** is the page the walk found it on, and one page
may state it. Two pages titling the same number is refused by name: an index
whose *stated in* column held two answers would be answering the one question
it exists for with a shrug. The case that existed was inactivity, titled both
in `board-rules.md` and in `operations.md`, on a page whose own last sentence
sent a reader to the other one for the full description.

Spliced, not written whole
--------------------------
`docs/handbook/governance/board-rules.md` is a hand-authored page. Only the
text between the two markers is this script's, in the shape
`generate_directory_map.py` already uses: read the committed file, keep
everything outside the markers as it stands, replace what is between them. A
missing marker raises, because a check comparing a file with itself reports
success on a page with nowhere left to write.

Pure, so `--check` means something
----------------------------------
The rendering reads the pages and nothing else: no clock, no network, no
environment. Two runs over the same commit produce byte-identical files, so a
difference can only be an edit made outside those inputs.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python scripts/generate_rule_index.py            # write the page
    uv run python scripts/generate_rule_index.py --check    # assert only

There is no mode that prints the block: the page is written in the handbook's
British English, and nothing this repository's Python writes to a terminal is
allowed to be non-ASCII.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, NamedTuple

from convener_ops.declaration.paths import repo_root

#: The page the index is spliced into, relative to the repository root: the
#: one that already carried the sentence this index replaces.
DOC_PATH: Final = Path("docs") / "handbook" / "governance" / "board-rules.md"

#: The documentation root the walk reads.
DOCS: Final = Path("docs")

#: The page whose table gives the three trees their order. Named here for
#: the failure messages; the reading is `tree_order` below.
TREES_PAGE: Final = DOCS / "README.md"

#: How the script is invoked, quoted in the page and in every failure
#: message. One string, so the two cannot come to name two commands.
COMMAND: Final = "uv run python scripts/generate_rule_index.py"

#: Markers wrapping the generated block inside the hand-authored page.
_BEGIN: Final = (
    "<!-- BEGIN GENERATED RULE INDEX -- tools/scripts/generate_rule_index.py -->"
)
_END: Final = (
    "<!-- END GENERATED RULE INDEX -- "
    "edit tools/scripts/generate_rule_index.py, not this block -->"
)

#: A published page titling one of its sections with a governance rule's
#: number: `## Inactivity (G-14)`. The number sits at the very end of the
#: heading, which is what separates naming a rule from mentioning one --
#: `**Handover is manual and deliberate, exactly as G-16 provides for:**` in
#: `docs/engineering/decisions/d-28-architect-and-board-permissions.md`
#: cites the rule, it does not state it.
RULE_HEADING: Final = re.compile(
    r"^#{1,6}[ \t]+[^\n]*?\((G-\d{2})\)[ \t]*$", re.MULTILINE
)

#: The same act on a page whose rules are paragraphs rather than sections:
#: `**Declaring an absence (G-06)** is something you do for yourself.`, and
#: `- **Diversity (G-11).** A deliberate aim, across career stage`. The bold
#: run opens the line -- after a list marker, if there is one -- and closes
#: on the number, so it is a title in everything but markup.
RULE_LEAD: Final = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?\*\*[^*\n]*?\((G-\d{2})\)[.,]?\*\*", re.MULTILINE
)

#: One row of `docs/README.md`'s table of trees.
_TREE_ROW: Final = re.compile(r"^\|\s*\[`(?P<tree>[a-z-]+)/`\]\(", re.MULTILINE)

#: A rule's number where a title carries it.
_NUMBER: Final = re.compile(r"\(G-\d{2}\)")


#: Numbers a rule used to carry and no rule will carry again, each with what
#: the rule was and the day it went. The two holes the numbering had before
#: it was made continuous are not in here: they were holes nobody could
#: account for rather than withdrawals, which is why they were closed up.
#:
#: An entry is added on the same commit that takes the rule off its page.
#: `held` reads this mapping and the pages together, so a rule removed
#: without an entry fails as a hole in the sequence, and an entry for a
#: number a page still states fails as a contradiction. The other half is in
#: `tools/tests/repository/test_cross_references.py`, which resolves a
#: citation of a retired number against this mapping: the page says a
#: citation of one still leads somewhere, and the sweep that refuses a
#: number nothing publishes has to agree.
RETIRED: Final[Mapping[str, str]] = {
    "G-04": (
        "Joining the Board, under which a nomination carried on seven "
        "calendar days of silence. Withdrawn on 2026-09-04, when the "
        "Board's own agreement became what appoints a member."
    ),
}


class Rule(NamedTuple):
    """One rule, as the walk met it."""

    #: `G-NN`, exactly as the page writes it.
    number: str
    #: The page's own title for the rule, with the number taken off.
    title: str
    #: The page that states it, relative to the repository root.
    page: str


# --------------------------------------------------------------------------
# What the pages state, in the order a reader walks them
# --------------------------------------------------------------------------


def tree_order(text: str) -> tuple[str, ...]:
    """The trees in the order `docs/README.md` lists them.

    Read rather than listed, so that reordering the front page's table
    reorders this index and fails `--check` on the same commit. A page with
    no such table raises: an empty order would put every rule outside the
    walk at once.
    """
    trees = tuple(match.group("tree") for match in _TREE_ROW.finditer(text))
    if not trees:
        raise ValueError(
            f"{TREES_PAGE.as_posix()}: no tree is listed in the shape "
            "`| [`handbook/`](handbook/index.md) |`, so the order the rules "
            "are numbered in cannot be read"
        )
    return trees


def title_of(match: str) -> str:
    """A page's own name for a rule, with the markup and the number off.

    `### The bar (G-01)` and `- **Diversity (G-11).**` both reduce to what a
    reader would call the rule out loud.
    """
    text = re.sub(r"^[ \t]*[#>]+[ \t]*", "", match.strip())
    text = re.sub(r"^[-*+][ \t]+", "", text)
    text = text.strip().strip("*").strip()
    text = _NUMBER.sub("", text).strip()
    return text.rstrip(".,: ").replace("|", "\\|")


def declarations_in(text: str) -> list[tuple[int, str, str]]:
    """Every rule one page states, as `(offset, number, title)`.

    Titling, not mentioning: see `RULE_HEADING` and `RULE_LEAD`. A page is
    free to cite a rule stated elsewhere, and doing so must not put it in
    this index on the strength of the citation alone.
    """
    found = []
    for pattern in (RULE_HEADING, RULE_LEAD):
        for match in pattern.finditer(text):
            found.append((match.start(), match.group(1), title_of(match.group(0))))
    return sorted(found)


def declared_rule_ids(text: str) -> set[str]:
    """Every governance rule one page states as its own.

    The set `tools/tests/repository/test_cross_references.py` resolves a
    `G-NN` citation against. The same reading as `declarations_in` with the
    order and the titles dropped, and it is here rather than there so that
    the sweep and this index cannot come to disagree about what stating a
    rule looks like.
    """
    return {number for _, number, _ in declarations_in(text)}


def pages_in_walk_order(root: Path, trees: Sequence[str]) -> list[Path]:
    """Every page of the three trees, in the order the numbering walks them.

    Tree by tree in the front page's order, and inside a tree by path. A
    page belonging to no tree is left out here and caught in
    `rules_in_walk_order`, where the rule it might state is what makes the
    omission matter.

    A tree the front page names and the repository does not hold raises: a
    walk that quietly skipped it would number the rules of the two trees
    that are there and report success.

    The sort key is the path as this repository writes it, forward slashes
    and the case the file carries, rather than the `Path` ordering: that
    one folds case and compares the platform's own separator, so a page
    whose name held a capital would sit in one place on a maintainer's
    Windows machine and in another on the runner, and `--check` would
    refuse in continuous integration what it had just passed locally.
    """
    pages: list[Path] = []
    for tree in trees:
        directory = root / DOCS / tree
        if not directory.is_dir():
            raise ValueError(
                f"{TREES_PAGE.as_posix()} lists `{tree}/` and "
                f"{(DOCS / tree).as_posix()} is not a directory, so the walk "
                "that gives a rule its number cannot read it"
            )
        pages.extend(
            sorted(
                directory.rglob("*.md"),
                key=lambda path: path.relative_to(root).as_posix(),
            )
        )
    return pages


def _outside_the_trees(root: Path, walked: Sequence[Path]) -> list[str]:
    """Every page under `docs/` that states a rule and is not on the walk."""
    inside = {path.resolve() for path in walked}
    return [
        path.relative_to(root).as_posix()
        for path in sorted((root / DOCS).rglob("*.md"))
        if path.resolve() not in inside
        and declared_rule_ids(path.read_text(encoding="utf-8"))
    ]


def _stated_twice(rules: Sequence[Rule]) -> dict[str, list[str]]:
    """Each number more than one page titles, with the pages that do."""
    seen: dict[str, list[str]] = {}
    for rule in rules:
        seen.setdefault(rule.number, []).append(rule.page)
    return {number: pages for number, pages in seen.items() if len(pages) > 1}


def rules_in_walk_order(root: Path) -> tuple[Rule, ...]:
    """Every rule the pages state, in the order the numbering follows.

    Raises on a rule stated outside the three trees, because the walk has
    nowhere to put it, and on a number two pages state, because the index's
    own *stated in* column would then have two answers.
    """
    trees = tree_order((root / TREES_PAGE).read_text(encoding="utf-8"))
    walked = pages_in_walk_order(root, trees)

    outside = _outside_the_trees(root, walked)
    if outside:
        raise ValueError(
            "tools/scripts/generate_rule_index.py: "
            f"{', '.join(outside)} states a governance rule and sits under "
            f"none of the trees {TREES_PAGE.as_posix()} lists "
            f"({', '.join(trees)}), so the walk that gives a rule its number "
            "has nowhere to put it"
        )

    rules = [
        Rule(number=number, title=title, page=path.relative_to(root).as_posix())
        for path in walked
        for _, number, title in declarations_in(path.read_text(encoding="utf-8"))
    ]

    twice = _stated_twice(rules)
    if twice:
        said = "; ".join(
            f"{number} on {', '.join(pages)}" for number, pages in sorted(twice.items())
        )
        raise ValueError(
            "tools/scripts/generate_rule_index.py: "
            f"{said}. One page states a rule and every other page cites it: "
            "take the number out of the title on the page that defers to the "
            "other, and the citation left behind still resolves"
        )
    return tuple(rules)


# --------------------------------------------------------------------------
# The sequence
# --------------------------------------------------------------------------


def sequence_for(count: int, retired: Mapping[str, str]) -> tuple[str, ...]:
    """The numbers `count` rules carry, in walk order, given the retirements.

    `G-01` upwards with every retired number skipped, which is the whole of
    the numbering rule as something a machine can compute: the first rule the
    walk meets carries the first number no withdrawal has taken, the second
    carries the second, and a hole in what comes out is a hole nothing
    declared.
    """
    numbers: list[str] = []
    candidate = 1
    while len(numbers) < count:
        number = f"G-{candidate:02d}"
        if number not in retired:
            numbers.append(number)
        candidate += 1
    return tuple(numbers)


def held(rules: Sequence[Rule], retired: Mapping[str, str]) -> tuple[Rule, ...]:
    """`rules`, refused unless they carry the sequence the walk derives.

    Two states raise, and between them they are the whole of what makes the
    sequence continuous and ascending:

    * a number a page states and `RETIRED` also declares -- one of the two
      is describing a rule that is not there;
    * a rule carrying anything but the number its place in the walk gives
      it, which covers a gap, a repeat and a pair out of order in one
      comparison.
    """
    stated = {rule.number for rule in rules}
    both = sorted(stated & set(retired))
    if both:
        raise ValueError(
            "tools/scripts/generate_rule_index.py: "
            f"{', '.join(both)} is declared retired in RETIRED and still "
            "stated by a page. A retired number names a rule no page "
            "carries: either the entry goes, or the title does"
        )
    expected = sequence_for(len(rules), retired)
    carried = tuple(rule.number for rule in rules)
    if carried != expected:
        first = next(
            index
            for index, (was, wanted) in enumerate(zip(carried, expected, strict=True))
            if was != wanted
        )
        raise ValueError(
            "tools/scripts/generate_rule_index.py: the rules do not carry "
            "the sequence the walk gives them. Reading "
            f"{DOCS.as_posix()} in order, rule {first + 1} is "
            f"{carried[first]} on {rules[first].page} where the sequence "
            f"reaches {expected[first]}. A number is a rule's place in that "
            "walk, and a number no rule carries is either a gap to close or "
            "a withdrawal to declare in RETIRED"
        )
    return tuple(rules)


# --------------------------------------------------------------------------
# The block
# --------------------------------------------------------------------------


_PREAMBLE: Final = f"""\
*The table below is generated from the pages themselves: every rule that
carries a number, what its own page calls it, and where it is stated. Do not
edit this block — run*
`{COMMAND}`
*from `tools/` and commit what it writes.*
"""

_RETIRED_LEAD: Final = """\
And the numbers no rule carries any more. Each was a rule once, and no later
rule takes it:
"""


def render_block(rules: Sequence[Rule], retired: Mapping[str, str]) -> str:
    """The text between the markers, for exactly these inputs.

    Pure, and takes everything it prints as an argument, so the rendering
    can be exercised against rules somebody made up rather than only against
    whatever this repository happens to state today.
    """
    rows = ["| Rule | What it is | Stated in |", "|---|---|---|"]
    for rule in rules:
        rows.append(f"| {rule.number} | {rule.title} | `{rule.page}` |")
    blocks = [_PREAMBLE, "\n".join(rows)]
    if retired:
        gone = [f"- **{number}** — {retired[number]}" for number in sorted(retired)]
        blocks.append(_RETIRED_LEAD)
        blocks.append("\n".join(gone))
    return "\n".join(block.rstrip("\n") + "\n" for block in blocks)


def splice(current: str, inner: str) -> str:
    """`current`, with the text between the markers replaced by `inner`.

    Raises rather than guessing when a marker is missing: silently leaving
    the file untouched would make `--check` compare the page with itself and
    report a match on a page with nowhere left to write to.
    """
    if _BEGIN not in current or _END not in current:
        raise ValueError(
            f"{DOC_PATH.as_posix()}: markers not found ({_BEGIN!r} / {_END!r}); "
            "the generated block cannot be located"
        )
    before, _, rest = current.partition(_BEGIN)
    _, _, after = rest.partition(_END)
    return f"{before}{_BEGIN}\n{inner}{_END}{after}"


def rule_index(root: Path) -> str:
    """The whole of the page, with this repository's own index of the rules."""
    rules = held(rules_in_walk_order(root), RETIRED)
    if not rules:
        raise ValueError(
            f"no page under {DOCS.as_posix()} titles a section or a "
            "paragraph with a governance rule's number -- an index of "
            "nothing would pass every check it is compared against"
        )
    inner = render_block(rules, RETIRED)
    return splice((root / DOC_PATH).read_text(encoding="utf-8"), inner)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the index of the numbered governance rules in "
        "docs/handbook/governance/board-rules.md."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if the committed page is not what the pages derive",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    path = root / DOC_PATH
    try:
        rendered = rule_index(root)
    except (OSError, ValueError) as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if args.check:
        if current != rendered:
            # Naming the file, the reason and the command, and repairing
            # nothing: a check that wrote the file it was checking would
            # pass on a repository that still held the wrong index.
            print(
                f"{DOC_PATH.as_posix()} is not the index the pages under "
                f"{DOCS.as_posix()} derive.",
                file=sys.stderr,
            )
            print(
                f"That block is generated, not authored: run `{COMMAND}` from "
                "`tools/` and commit the file it writes.",
                file=sys.stderr,
            )
            return 1
        print(f"{DOC_PATH.as_posix()} matches the rules the pages state")
        return 0

    if current == rendered:
        print(f"{DOC_PATH.as_posix()} unchanged")
        return 0
    path.write_text(rendered, encoding="utf-8", newline="")
    print(f"wrote {DOC_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
