"""No passage of the handbook is written twice.

The information architecture asks for one home per notion. Reading the
handbook as a volunteer asks for the opposite, and rightly: whoever lands
halfway
down a page needs the rule in front of them, not a link to it. The two meet in
one rule -- a repeated passage is *included* from its source (see
``app/src/content/transclude.ts``) -- and this module is what makes that rule
enforceable rather than aspirational.

**The threshold.** Two pages sharing a run of text of at least
``MIN_DUPLICATE_CHARS`` characters, once punctuation and formatting are taken
off, are treated as a copy. The number is a judgement and it is worth writing
down why it is this one.

Too low and the test fires on text that is not a copy of anything. Below a
hundred characters this repository's shared text is *forms*: the two-line
sign-off that closes an e-mail (68 characters), "Most volunteers are
Contributors and Event Hosts." (49), "Inactive is not a departure and not a
judgement." (48). None of those is a notion with a home; they are conventions
and echoes. Forcing them through an include would put an attribution line and a
link in the middle of an e-mail a volunteer is about to paste into their mail
client -- a worse outcome than the drift it prevented, and the drift is
harmless: nobody acts differently because two sign-offs disagree.

Too high and it catches nothing. An ordinary English sentence runs fifteen to
twenty words, ninety to a hundred and thirty characters. Set the bar at a
paragraph and the test would have passed on the day it was written while the
handbook still held its copies, because the copies were never paragraph-exact:
the second page had appended a sentence to the first page's, which is precisely
how a copy looks a year after it was made.

A hundred characters is a full statement of something -- long enough that two
volunteers writing independently do not land on it, short enough that a copy
with a sentence added on the end is still caught. It is deliberately measured
over sentences, not paragraphs, for that reason.

**What is not compared.** Fenced code blocks (a command or a YAML sample is a
literal, and two pages showing the same command are not two sources of a rule),
and the include lines themselves.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

#: Where a duplicate becomes a copy. See the module docstring for the argument.
MIN_DUPLICATE_CHARS = 100

_REPO = Path(__file__).resolve().parents[3]
_DOCS = _REPO / "docs"

#: The rule `app/scripts/handbook-files.mjs` applies, read out of that file by
#: ``test_the_skip_list_is_the_one_the_app_applies`` below: a directory added
#: to one side and not the other silently shrinks what this test looks at, and
#: shrinking it is invisible -- the sweep still passes, over less.
#:
#: This is a *superset* of what the app copies, and used to be described as
#: the same set. It stopped being that when `copy-handbook.mjs` moved to the
#: allowlist `app/src/content/registry.ts` already held: the registry names 80
#: published paths today, this walk finds 88 markdown pages. The difference is
#: pages committed under `docs/` that nothing has registered yet, and sweeping
#: them for copies is the stricter reading of the rule -- a copy made in an
#: unregistered page is a copy the day somebody registers it.
_SKIP_DIRS = {"superpowers", "stylesheets", "app"}

#: Where the app's copy of the same rule lives, and the form it is written in.
_HANDBOOK_FILES = Path("app/scripts/handbook-files.mjs")
_APP_SKIP_DIRS = re.compile(r"export const SKIP_DIRS = new Set\(\[(.*?)\]\)", re.S)

_FENCE = re.compile(r"^\s*```", re.M)
_INCLUDE_LINE = re.compile(r"^[ \t]*\{\{>[^}]*\}\}[ \t]*$", re.M)
_SENTENCE_END = re.compile(r"(?<=[.!?:])\s+")


def served_pages() -> list[Path]:
    """Every markdown page under `docs/` outside the three directories
    `handbook-files.mjs` skips -- every page a reader of the documentation can
    open, and a superset of what the app copies. See `_SKIP_DIRS` above for
    which of the two sets this is and why."""
    out = []
    for path in sorted(_DOCS.rglob("*.md")):
        rel = path.relative_to(_DOCS)
        if _SKIP_DIRS & set(rel.parts[:-1]):
            continue
        out.append(path)
    return out


def _without_code(text: str) -> str:
    """Drop fenced blocks, keeping the prose around them."""
    kept, fenced = [], False
    for line in text.split("\n"):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            kept.append(line)
    return "\n".join(kept)


def normalise(text: str) -> str:
    """Prose as prose, with the formatting and the punctuation taken off.

    Emphasis, links and list bullets are how a sentence is *presented*; two
    pages that differ only in whether a word is bold are the same sentence
    twice. Everything outside the ASCII alphabet is dropped rather than
    transliterated: it makes the comparison insensitive to which dash or
    quotation mark somebody's editor produced, and it keeps a failure message
    printable on any terminal.
    """
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return " ".join(re.sub(r"[^A-Za-z0-9]+", " ", text).lower().split())


def passages(text: str) -> list[str]:
    """The comparable units of a page: its sentences, normalised."""
    body = _INCLUDE_LINE.sub("", _without_code(text))
    out = []
    for block in re.split(r"\n\s*\n", body):
        for sentence in _SENTENCE_END.split(" ".join(block.split())):
            normalised = normalise(sentence)
            if len(normalised) >= MIN_DUPLICATE_CHARS:
                out.append(normalised)
    return out


def duplicates(pages: dict[str, str]) -> list[tuple[str, list[str]]]:
    """Passages appearing in more than one page, with the pages that hold them."""
    where: dict[str, set[str]] = defaultdict(set)
    for name, text in pages.items():
        for passage in passages(text):
            where[passage].add(name)
    return sorted(
        ((p, sorted(files)) for p, files in where.items() if len(files) > 1),
        key=lambda item: item[0],
    )


def _handbook() -> dict[str, str]:
    return {
        path.relative_to(_DOCS).as_posix(): path.read_text(encoding="utf-8")
        for path in served_pages()
    }


def test_the_skip_list_is_the_one_the_app_applies() -> None:
    """The two copies of "which directories never reach a volunteer".

    Not a formality. Dropping two directories from `_SKIP_DIRS` -- which
    silently removes two whole sections of the handbook from the
    no-duplicate sweep -- left every test in this module green, because
    nothing read the other side. The docstring on `_SKIP_DIRS` claimed this
    pin before it existed, which is worse than claiming nothing: it is what a
    reviewer trusts instead of looking.
    """
    source = (_REPO / _HANDBOOK_FILES).read_text(encoding="utf-8")
    listed = _APP_SKIP_DIRS.search(source)
    assert listed is not None, (
        f"{_HANDBOOK_FILES.as_posix()} no longer declares SKIP_DIRS in the form "
        "this test reads, so the two skip lists are no longer held together."
    )
    assert set(re.findall(r"'([^']+)'", listed.group(1))) == _SKIP_DIRS


def test_the_sweep_covers_the_pages_the_app_serves() -> None:
    """An empty walk would make every assertion below pass for free."""
    names = set(_handbook())
    assert "handbook/workflow/4-after.md" in names
    assert "handbook/governance/board-rules.md" in names
    assert "handbook/toolkit/intro-scripts.md" in names
    assert not any(name.startswith("superpowers/") for name in names)


def test_the_detector_finds_a_copy_when_there_is_one() -> None:
    """The rule is only worth having if the test can see a violation.

    Two pages, the second holding the first's sentence with one appended --
    the shape a copy actually takes -- and the report names both files.
    """
    shared = (
        "A recording goes online only when two separate permissions are in "
        "hand, from two separate parties, and neither can be read off the other."
    )
    found = duplicates(
        {
            "handbook/governance/board-rules.md": f"# Rules\n\n{shared}\n",
            "handbook/workflow/4-after.md": (
                f"# After\n\n{shared} Ask the speaker first.\n"
            ),
        }
    )
    assert [files for _, files in found] == [
        ["handbook/governance/board-rules.md", "handbook/workflow/4-after.md"]
    ]


def test_the_detector_leaves_a_shared_short_sentence_alone() -> None:
    """A form is not a notion. The sign-off two e-mails share is not a copy."""
    sign_off = "Best regards, {{ host_1.name }} for {{ instance.organisation }} team"
    assert len(normalise(sign_off)) < MIN_DUPLICATE_CHARS
    assert (
        duplicates(
            {
                "handbook/toolkit/emails/invitation.md": sign_off,
                "handbook/toolkit/emails/outreach-sourcing.md": sign_off,
            }
        )
        == []
    )


def test_a_fenced_block_shared_by_two_pages_is_not_a_copy() -> None:
    """The same command on two pages is one command, not two sources of a rule.

    Both halves are asserted: the command is long enough to trip the threshold,
    and it trips it when it is prose and not when it is fenced. A fence filter
    that quietly swallowed everything would pass the first assertion alone.
    """
    command = (
        "uv run convener-register --check --verbose --repository "
        "example-instance/example-cockpit --since 2026-01-01 --until 2026-12-31"
    )
    assert len(normalise(command)) >= MIN_DUPLICATE_CHARS
    fenced = "\n".join(["# Page", "", "```bash", command, "```", ""])
    assert duplicates({"operating/standing-up.md": fenced, "a/b.md": fenced}) == []
    assert duplicates({"operating/standing-up.md": command, "a/b.md": command}) != []


def test_no_paragraph_appears_twice_across_the_handbook() -> None:
    """Two identical passages mean a copy, so two sources that will diverge.

    The threshold is length: a short sentence can coincide. What cannot is a
    hundred characters of prose in two files, and when it happens the fix is
    not to reword one of them -- it is to include it from the other.
    """
    found = duplicates(_handbook())
    assert found == [], "\n".join(
        f"{' and '.join(files)} share: {passage[:120]}" for passage, files in found
    )
