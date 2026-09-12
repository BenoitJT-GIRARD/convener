"""The terms this work is under, and the notice its two interfaces display.

Four files answer for four different things, and the whole point of
D-29 is that they are separate rather than one:

* ``LICENSE`` -- the GNU Affero General Public License, version 3, in the
  Free Software Foundation's own words, from the file's first byte, with
  this program's own notice below the licence text and, in that notice,
  a pointer to the one added term.
* ``ADDITIONAL-TERM.md`` -- that term: the name declined under section
  7's paragraph e, what the declining does and does not withhold, and why
  it is not a further restriction within the meaning of section 10.
* ``TRADEMARK.md`` -- what that term reserves, what a duplicate names
  its own series, what the licence obliges it to keep, what it may then
  write about where its product came from, and that all of it is asked in
  good faith.
* ``NOTICE.json`` -- the Appropriate Legal Notice both interfaces print in
  their footer, in the sense section 0 of the licence defines the phrase.

**Where the added term sits, and why it is not in ``LICENSE``.** GitHub
detects a repository's licence with ``licensee``, which normalises the
file -- copyright lines removed, everything from *END OF TERMS AND
CONDITIONS* onwards removed -- and then compares what is left with the
texts it knows. What survives that normalisation has to match, and the
tolerance for prose this repository adds above the licence text is zero:
measured on a branch through ``GET /repos/{owner}/{repo}/license``, a
single 56-character line above the licence was enough to return
``NOASSERTION``, and the same file with that line below the licence text
returned ``AGPL-3.0``. So the term has a file of its own, and the notice
saying where to find it -- which is the second of the two things section 7
accepts, *state it, or say where it is to be found* -- sits below the
licence text, where the detector does not read and a reader still does.

**Why that is worth the detour.** An undetected licence reads as
``Other`` in GitHub's own About panel and as ``NOASSERTION`` to every
SPDX scanner, and this product exists to be picked up by volunteer-run
societies who have no lawyer to ask what ``Other`` means.

**Why any of this needs a test at all.** Each of the four fails silently
when it fails. A ``LICENSE`` quietly replaced by a permissive one still
looks like a licence file; a notice with its warranty sentence dropped
still looks like a footer credit; a declaration moved into ``declarations/``
still builds. None of those shows up as a broken page, and the second is
the one that matters most: section 5 obliges a modified version's
interfaces to display an Appropriate Legal Notice **only where the
original's do**, so a notice that stops being one stops obliging anybody,
and nothing anywhere goes red.

**What is checked here, and what is checked elsewhere.** This module holds
the four files and the two templates that read the last of them. That the
notice actually reaches a *rendered* page is a different claim, made
against real output on both sides: ``tools/tests/repository/test_site.py`` builds the
showcase and reads its footer, and ``app/tests/components/notice.test.tsx`` renders
the cockpit's own. A template referencing a field and a page displaying it
are not the same statement, and neither test is a substitute for the
other.

**What is deliberately not checked.** Whether the wording is legally
effective. No test decides that, and one claiming to would be read as if
it had.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess  # nosec B404
from typing import Any

import pytest

from convener_ops.declaration import boundary, needles
from convener_ops.declaration.paths import repo_root

ROOT = repo_root()

LICENCE = ROOT / "LICENSE"
ADDED_TERM = ROOT / "ADDITIONAL-TERM.md"
TRADE_MARKS = ROOT / "TRADEMARK.md"
DECLARATION = ROOT / "NOTICE.json"

SHOWCASE_LAYOUT = ROOT / "site" / "src" / "_includes" / "layout.njk"
COCKPIT_LAYOUT = ROOT / "app" / "src" / "components" / "Layout.tsx"

SHOWCASE_READER = ROOT / "site" / "scripts" / "notice.cjs"
COCKPIT_READER = ROOT / "app" / "scripts" / "notice.mjs"

#: The first line of the licence as the Foundation publishes it, indent
#: included, and the last. Where the Foundation's file starts and stops
#: inside this one -- found rather than counted, so adding a paragraph to
#: the notice below it cannot silently move what the digest is taken over.
#:
#: The first line is also the first line of `LICENSE`, and
#: `test_the_licence_text_starts_at_the_first_byte_of_the_file` is what
#: says so: everything this repository adds is below the Foundation's
#: last line, which is the only arrangement GitHub's detector reads as
#: the AGPL.
AGPL_FIRST_LINE = "                    GNU AFFERO GENERAL PUBLIC LICENSE"
AGPL_LAST_LINE = "<https://www.gnu.org/licenses/>."

#: SHA-256 of https://www.gnu.org/licenses/agpl-3.0.txt, the whole file,
#: LF line endings, trailing newline included.
#:
#: A digest rather than a second copy of the text to compare against: a
#: fixture holding the licence would be the licence written twice, and the
#: failure this guards against -- somebody swapping in a different licence,
#: or editing a sentence of this one -- is exactly the failure a second
#: copy would let through as long as both copies were edited. One byte's
#: difference and this fails.
AGPL_SHA256 = "0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0"

#: Every field of the declaration, and the whole of it. The same list both
#: readers carry; ``test_both_readers_answer_with_the_same_notice`` below
#: is what holds the three together, so this is not a fourth spelling of
#: it that could drift on its own.
FIELDS = (
    "product",
    "copyright",
    "terms",
    "warranty",
    "licence_name",
    "licence_url",
)


def declaration() -> dict[str, Any]:
    loaded = json.loads(DECLARATION.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def licence_text() -> str:
    return LICENCE.read_text(encoding="utf-8")


def _licence_bounds() -> tuple[int, int]:
    """Where the Foundation's own file starts and stops inside this one."""
    text = licence_text()
    assert text.startswith(f"{AGPL_FIRST_LINE}\n"), (
        f"{LICENCE.name} does not open on {AGPL_FIRST_LINE!r} -- either the "
        "licence text is not in it at all, its first line has been "
        "reflowed, or something has been written above it. The last of the "
        "three is the one that costs: GitHub reads nothing above the "
        "licence text as part of the licence, so a line there is a "
        "repository whose terms report as NOASSERTION."
    )
    end = text.rindex(f"\n{AGPL_LAST_LINE}\n")
    return 0, end + len(AGPL_LAST_LINE) + 2


def licence_body() -> str:
    """The licence itself, first line to last, and nothing else."""
    start, end = _licence_bounds()
    return licence_text()[start:end]


def applied_notice() -> str:
    """Everything this repository writes below the licence text.

    This program's own notice -- what it is, whose it is, and that one
    added term supplements the licence -- in the place the Foundation's
    own closing section tells a program to write it, and below the line
    GitHub's detector stops reading at.
    """
    _start, end = _licence_bounds()
    return licence_text()[end:]


# -------------------------------------------------------------------------- #
# The licence
# -------------------------------------------------------------------------- #


def test_the_licence_text_is_the_official_one_byte_for_byte() -> None:
    """D-29: the official text, unmodified, or it is not the AGPL.

    The failure this refuses is not vandalism. It is the ordinary one --
    a licence replaced during a rewrite by a shorter, friendlier,
    permissive one, or a clause reflowed by an editor that trims trailing
    space -- and every one of those leaves a file that still reads as a
    licence to anybody scrolling past it.
    """
    digest = hashlib.sha256(licence_body().encode("utf-8")).hexdigest()
    assert digest == AGPL_SHA256, (
        f"{LICENCE.name}'s licence text is not the GNU Affero General "
        "Public License, version 3, as the Free Software Foundation "
        f"publishes it: got {digest}, expected {AGPL_SHA256}. Nothing in "
        "this repository may paraphrase, trim or reflow it."
    )


def test_the_licence_text_starts_at_the_first_byte_of_the_file() -> None:
    """Nothing above the licence, because GitHub reads nothing above it.

    ``licensee``, which GitHub runs, throws away copyright lines and
    everything from *END OF TERMS AND CONDITIONS* onwards, then compares
    what is left with the licences it knows. Prose this repository adds
    above the licence text survives that and so has to match too, which it
    cannot: measured against
    ``GET /repos/BenoitJT-GIRARD/convener/license?ref=<branch>``, one
    56-character line above the licence returned ``NOASSERTION`` and the
    same file with that line moved below the licence text returned
    ``AGPL-3.0``. There is no budget to spend here, which is why the whole
    of this program's own notice is below rather than trimmed to fit.
    """
    assert licence_text().startswith(AGPL_FIRST_LINE), (
        f"{LICENCE.name} no longer opens on the licence's own first line. "
        "Whatever is above it, GitHub's detector reads the file as an "
        "unrecognised licence and the repository's terms report as "
        "NOASSERTION to everybody who never opens the file."
    )


def test_the_licence_names_the_holder_and_the_year() -> None:
    """A copyright notice is the first thing section 0 asks a notice to
    carry, and the licence file is where the claim itself is made."""
    assert re.search(r"^Copyright \(C\) \d{4} \S", applied_notice(), re.MULTILINE), (
        f"{LICENCE.name} states no copyright line in the notice below the licence text"
    )


def test_the_added_term_is_stated_as_one_section_7_permits() -> None:
    """The term is a section 7 term or it is nothing.

    Section 7 admits five kinds of supplementary term and calls everything
    else a further restriction, which a recipient may strip and which
    would make the work non-free besides. So the term has to *say* which
    kind it is: this test reads the file that carries it for the section
    it invokes, the right it declines, and the document that qualifies it.
    """
    text = ADDED_TERM.read_text(encoding="utf-8")
    for expected, why in (
        ("section 7", "the section that authorises an added term"),
        ("paragraph e", "the one kind of term this actually is"),
        ("trademark law", "the words section 7's paragraph e uses"),
        ("Convener", "the name the term is about"),
        ("assets/brand/convener/", "where the marks it is about actually are"),
        ("TRADEMARK.md", "where a reader is sent for what the term covers"),
        ("further restriction", "the thing it has to say it is not"),
    ):
        assert expected in text, (
            f"{ADDED_TERM.name} does not name {expected!r} -- "
            f"{why}. Without it the term reads as a preference rather "
            "than as a term section 7 permits."
        )


def test_nothing_this_repository_adds_sits_inside_the_licence_text() -> None:
    """Below, never inside.

    A term interleaved with the licence's own clauses would make the text
    around it no longer the official one -- which the digest above would
    catch -- and would also read, to anybody quoting a clause out of it,
    as part of the Foundation's words rather than as this project's
    addition.
    """
    body = licence_body()
    assert ADDED_TERM.name not in body
    assert "TRADEMARK.md" not in body
    assert "Convener" not in body


# -------------------------------------------------------------------------- #
# The licence and the term it names
# -------------------------------------------------------------------------- #

#: A file this repository owns, as `LICENSE` writes one: capitals, digits
#: and hyphens, carrying a Markdown extension. Narrow on purpose -- the
#: licence text quotes plenty of ordinary words and no URL is of this
#: shape, so what this finds is a pointer at a file of ours and nothing
#: else.
NAMED_FILE = re.compile(r"\b[A-Z][A-Z0-9-]*\.md\b")


def tracked_at_the_root() -> frozenset[str]:
    """Every file `git ls-files` reports at the repository root.

    The index rather than the directory: a pointer is kept by whoever
    clones this repository, and a file sitting unstaged in somebody's
    working copy reaches none of them.
    """
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return frozenset(name for name in listed if "/" not in name)


def test_the_licence_names_only_files_this_repository_carries() -> None:
    """One half of the pair, and the half that decays quietly.

    The term used to be inside `LICENSE`, where it could not go missing.
    It is now a file with a pointer at it, and a pointer is a claim about
    something else: rename the file, or drop it from a commit that moved
    the rest, and `LICENSE` goes on telling every recipient to read a
    document that is not there. A licence naming a file nobody can open
    is worse than one naming none, because section 7 accepts *say where
    it is to be found* and this would be a file that says it and does not.
    """
    named = sorted(set(NAMED_FILE.findall(licence_text())))
    assert named, (
        f"{LICENCE.name} names no file of this repository at all. The "
        "added term lives outside it now, so a licence that points at "
        "nothing is a licence that has quietly dropped the term."
    )
    missing = [name for name in named if name not in tracked_at_the_root()]
    assert missing == [], (
        f"{LICENCE.name} sends a reader to {missing}, which this "
        "repository does not track at its root. Everybody who receives "
        "this work receives that pointer, and section 7 lets a term be "
        "carried by a notice saying where to find it -- so a pointer at "
        "a file that is not there is the term itself going missing."
    )


def test_the_licence_is_what_points_at_the_added_term() -> None:
    """The other half: a term nothing points at.

    `ADDITIONAL-TERM.md` is not a page somebody finds by browsing; it is
    the one document `LICENSE` has to hand a recipient, and it is
    reachable only because `LICENSE` names it. A rewrite of the notice
    below the licence text that drops the name leaves both files intact,
    both readable, and the term attached to nothing.
    """
    assert ADDED_TERM.name in tracked_at_the_root(), (
        f"{ADDED_TERM.name} is not tracked at the root of this "
        "repository, and it is the file carrying the one term section 7 "
        "adds to the licence."
    )
    assert ADDED_TERM.name in applied_notice(), (
        f"{LICENCE.name} no longer names {ADDED_TERM.name} in the notice "
        "below the licence text, so nothing in the licence says where the "
        "added term is to be found. Section 7 admits a term stated in the "
        "file or a notice saying where it lives; this is neither."
    )


# -------------------------------------------------------------------------- #
# The name
# -------------------------------------------------------------------------- #


def trade_mark_prose() -> str:
    """`TRADEMARK.md` with its line breaks taken out.

    The file is prose wrapped at the width the rest of this repository
    wraps at, so where a sentence breaks is a decision an editor makes and
    a reader never sees. Searching the raw text for a phrase of more than
    two words is therefore a check that a reflow can turn red without
    changing a word, which is the kind of control this repository throws
    away rather than lives with.
    """
    return " ".join(TRADE_MARKS.read_text(encoding="utf-8").split())


#: What `TRADEMARK.md` has to say, and why each one is a sentence the file
#: stops working without. Read in order below, and the order is half of what
#: is held here.
TRADE_MARK_STATEMENTS: tuple[tuple[str, str], ...] = (
    ("however it is cased or spaced", "what the grant does not hand over"),
    ("naming its own series", "what a duplicate is doing, in its own name"),
    ("identity.series", "the field that name actually goes in"),
    (
        "names the software, not the series",
        "what `product` in `NOTICE.json` is, and the inversion it is not",
    ),
    ("kept intact", "the obligation sections 4 and 5 put on the notice"),
    (
        "an accurate description of an origin",
        "the permission that follows that obligation",
    ),
    ("good faith", "that all of it is asked rather than enforced"),
)


def test_the_trade_mark_document_states_what_it_reserves_asks_and_permits() -> None:
    """Seven statements, and the file is not doing its job without all seven.

    It has one reader -- somebody about to take this code and make their
    own product of it -- and one job: tell them what the licence does not
    hand over, what their own series is called and where that name is set,
    what the licence obliges them to keep, what they may then write about
    where their product came from, and that the rest is asked rather than
    enforced. Each is one heading and a short list, and each is the kind of
    sentence a later edit drops without leaving a hole a reader would
    notice.

    **The second of them used to read ``rename``, and the verb was the
    defect.** Two rewrites of that page told a reader "an instance is
    yours -- but keep the notice", and both were rejected for the same
    two reasons: *yours* attached to the running software rather than to
    what an operator writes into it, and the two halves read as opposed,
    so the notice arrived as a price extracted for having customised
    anything. The page now stands on one axis -- a series and the software
    it runs on are two different things, each with its own name -- and
    ``rename`` cannot survive it: a duplicate is not renaming Convener, it
    is naming its own series, which never carried that name. The needle is
    the new verb, and it is a needle rather than a note because the old
    one would have gone on passing: the sentence that replaced it still
    contains the word ``rename``, in the clause that refuses it.

    **The third and the fourth are here because the row of five passed
    green over a sentence that was wrong.** ``Naming your own series`` said
    one field carried the series' name into the software -- ``product`` in
    ``NOTICE.json`` -- and every word of that was checkable and false. The
    footer prints ``{{ notice.product }} . {{ notice.copyright }}``, and
    ``copyright`` is the line the licence obliges a duplicate to keep, so a
    duplicate following that sentence published its own series' name
    against this project's copyright: the exact inversion of the axis the
    page exists to state. The series' name was already displayed anyway,
    from the instance's own declaration, at the top of every page. Two
    needles rather than one, because the correction is two claims and
    either could be dropped on its own: ``identity.series`` is where the
    name goes, and ``names the software, not the series`` is what the field
    a reader was being sent to is actually for. Neither is a phrase the old
    sentence contained, which is what makes them needles rather than notes
    -- a sweep for ``product`` or for ``NOTICE.json`` would have passed
    over the defect word for word.

    ``an accurate description of an origin`` is the one that earns this
    project its attribution. A reader who does not know they may write
    "built on Convener" either
    omits the credit or opens an issue to ask; the right to describe an
    origin accurately exists whether this file says so or not, so saying
    nothing buys no protection and costs a good-faith reader the line.
    """
    text = trade_mark_prose()
    for expected, why in TRADE_MARK_STATEMENTS:
        assert expected in text, (
            f"{TRADE_MARKS.name} no longer says anything about "
            f"{expected!r} -- {why}. This file is one reader's whole "
            "answer on the name, and half an answer reads as the whole one."
        )


def test_the_ask_comes_before_the_list_and_the_obligation_before_the_permission() -> (
    None
):
    """The order the sentences come in, which is what the document *is*.

    The same five statements arranged the other way round make a different
    file. A good-faith ask that closes a page, after a list of everything
    the claim does not reach, reads as a shrug over the list; at the top it
    sets the register for everything under it. And a permission to name the
    origin, standing on its own, reads as an open door; behind the
    obligation the licence already imposes, it reads as the condition it is.

    Neither is checkable by reading for a phrase, which is why this is a
    second test and not a sixth row above: both failures leave every
    sentence in place.
    """
    text = trade_mark_prose()

    assert text.index("good faith") < text.index("## What is reserved"), (
        f"{TRADE_MARKS.name} asks for good faith after it has listed what "
        "it reserves. Below the list the ask reads as a shrug over it; "
        "above, it is the register the list is read in."
    )
    assert text.index("kept intact") < text.index(
        "an accurate description of an origin"
    ), (
        f"{TRADE_MARKS.name} permits naming the origin before it states the "
        "obligation sections 4 and 5 impose. Permission first reads as an "
        "open door; obligation first makes the permission a condition."
    )


# -------------------------------------------------------------------------- #
# The notice
# -------------------------------------------------------------------------- #


def test_the_notice_belongs_to_the_product_and_to_no_instance() -> None:
    """The boundary's own answer, asked of the declaration's real path.

    Not a claim in a comment: `declarations/boundary.yml` hands named paths to
    the instance and everything else is the product's, so this is the
    question that decides whether a duplicate would inherit this file or
    be expected to write its own. A notice an instance owns is a notice a
    modified version may empty, which is the one thing section 5 exists to
    prevent.
    """
    declared = boundary.load(ROOT)
    relative = DECLARATION.relative_to(ROOT).as_posix()
    assert declared.owner_of(relative) == boundary.PRODUCT


def test_the_notice_declares_every_field_and_leaves_none_empty() -> None:
    """Half a notice is not an Appropriate Legal Notice."""
    data = declaration()
    assert data.get("v") == 1
    assert FIELDS, "this sweep has nothing to look for"
    for field in FIELDS:
        value = data.get(field)
        assert isinstance(value, str) and value.strip(), (
            f"{DECLARATION.name}: {field} is missing or empty"
        )


def test_the_notice_states_each_of_the_four_things_section_0_asks_for() -> None:
    """Section 0's definition, clause by clause.

    An Appropriate Legal Notice displays a copyright notice, says there is
    no warranty, says a licensee may convey the work under this licence,
    and says how to read a copy of it. Four separate assertions rather
    than one over the whole sentence, because the way this decays is one
    clause at a time -- a footer trimmed for width keeps the name and
    drops the warranty, and what is left looks exactly like a credit.
    """
    data = declaration()

    assert re.match(r"Copyright © \d{4} \S", data["copyright"])

    assert "no warranty" in data["warranty"].lower(), (
        "the warranty disclaimer no longer says there is none"
    )

    terms = data["terms"]
    assert "redistribute" in terms and "modify" in terms, (
        "the notice no longer says a licensee may convey the work"
    )
    assert "GNU Affero General Public License" in terms, (
        "the notice no longer says under which licence"
    )

    assert data["licence_url"].startswith("https://"), (
        "the notice's licence link is not an address a reader can open"
    )
    assert data["licence_name"].strip(), "the licence link has no text"


def test_the_notice_writes_nothing_this_instance_declared() -> None:
    """The product's statement about itself, and only that.

    Swept against the declared identity rather than eyeballed: the same
    needles every other sweep here reads. A notice
    carrying an organisation's name would be a notice every duplicate had
    to edit, and one every duplicate edits is one a modified version can
    empty without anybody noticing it had.
    """
    data = declaration()
    haystack = "\n".join(str(data[field]) for field in FIELDS)
    found = [
        name
        for name, needle in needles.needles(ROOT).items()
        if any(needles.contains(haystack, form) for form in needles.forms(needle))
    ]
    assert found == [], (
        f"{DECLARATION.name} writes this instance's own {found} -- the "
        "notice says who wrote the software, never who is running it"
    )


# -------------------------------------------------------------------------- #
# The two readers, and the two templates
# -------------------------------------------------------------------------- #


def _node(script: str) -> str:
    if shutil.which("node") is None:  # pragma: no cover
        pytest.skip("node is not on PATH -- cannot run either reader")
    result = subprocess.run(  # nosec B603
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        # Named rather than left to the platform: the notice carries the
        # holder's name and a copyright sign, and a Windows console's own
        # code page decodes both into replacement characters -- which
        # would make this test fail on a difference nothing in either file
        # has.
        encoding="utf-8",
        check=True,
        timeout=60,
    )
    return result.stdout.strip()


def test_both_readers_answer_with_the_same_notice() -> None:
    """One declaration, two readers, and a way to tell.

    The showcase's build and the cockpit's build cannot share a module:
    one is CommonJS loaded by Eleventy at config time, the other ESM
    imported by Vite. Two readers is D-14's own answer to that, and its
    own condition -- the two are held to one another rather than trusted
    to agree -- is this test. Both are asked, in their own runtime, and
    both answers are compared with the file they read.
    """
    expected = {field: declaration()[field] for field in FIELDS}

    from_cjs = _node(
        "console.log(JSON.stringify("
        f"require({str(SHOWCASE_READER.as_posix())!r}).notice()))"
    )
    assert json.loads(from_cjs) == expected

    from_mjs = _node(
        f"import({COCKPIT_READER.as_uri()!r})"
        ".then(m => console.log(JSON.stringify(m.notice())))"
    )
    assert json.loads(from_mjs) == expected


# -------------------------------------------------------------------------- #
# The one field a duplicate edits
# -------------------------------------------------------------------------- #

#: Declarations this repository does not ship, with what each one makes
#: `product` a second spelling of. The first is the exact defect
#: `TRADEMARK.md` sent a duplicate into for as long as it said one field
#: carried the series' name into the software.
_EXAMPLE_IDENTITY = {
    "series": "Monthly Reading Group",
    "organisation": "The Example Collective",
}

TAKES_THE_INSTANCES_NAME: tuple[tuple[str, dict[str, str], str], ...] = (
    ("Monthly Reading Group", _EXAMPLE_IDENTITY, "series"),
    ("The Example Collective", _EXAMPLE_IDENTITY, "organisation"),
    # Case and surrounding space are a rendering of a name, never a
    # different name, and the failure this refuses is not a typo.
    ("  the EXAMPLE collective ", _EXAMPLE_IDENTITY, "organisation"),
)

NAMES_THE_SOFTWARE: tuple[tuple[str, dict[str, str]], ...] = (
    ("Convener", _EXAMPLE_IDENTITY),
    # A name of the software that merely contains one of the instance's --
    # this is equality, not a substring sweep, because "Monthly Reading
    # Group Tools" is a plausible name for a fork and refusing it would be
    # a control somebody turns off.
    ("Monthly Reading Group Tools", _EXAMPLE_IDENTITY),
    # A declaration with no identity in it at all: unreadable is refused
    # where it is read, and an identity that declares no name is nothing
    # for `product` to be a second spelling of.
    ("Convener", {}),
    # Both sides empty. An empty `product` is already refused a few lines
    # earlier, and this says the emptiness never becomes a match of its own.
    ("", {"series": "", "organisation": ""}),
)


def _asked_of_both(
    cases: tuple[tuple[str, dict[str, str]], ...],
) -> tuple[list[str | None], list[str | None]]:
    """The same list of declarations put to both readers, each in its own
    runtime, one process per side.

    One call rather than one per case, and one list of answers rather than
    a boolean: an answer that names the *wrong* field would pass a test
    that only asked whether something was refused.
    """
    argument = json.dumps([[product, declared] for product, declared in cases])
    from_cjs = _node(
        f"const cases = {argument};"
        f"const m = require({str(SHOWCASE_READER.as_posix())!r});"
        "console.log(JSON.stringify("
        "cases.map(([p, d]) => m.namesTheInstance(p, d))))"
    )
    from_mjs = _node(
        f"const cases = {argument};"
        f"import({COCKPIT_READER.as_uri()!r}).then(m => console.log(JSON.stringify("
        "cases.map(([p, d]) => m.namesTheInstance(p, d)))))"
    )
    return json.loads(from_cjs), json.loads(from_mjs)


def test_both_readers_refuse_a_product_that_is_the_instances_own_name() -> None:
    """`product` names the software, and a build stops when it names the
    series instead.

    **Why a control at all, beside a sentence in `TRADEMARK.md`.** The
    sentence was there, it was wrong, and its own author was the reader it
    misled: it said one field carried the series' name into the software
    and named `product`. A duplicate following it published its own
    series' name against this project's `copyright`, which sections 4 and
    5 oblige it to keep. A rewritten sentence fixes the page; it does not
    stop the next reader, so the build refuses as well.

    **Where it lives, and why not somewhere new.** In the two readers that
    already refuse a missing or empty field, because those are what every
    build of either interface goes through -- so a duplicate that edits
    the notice and builds learns it there rather than in a suite it may
    never run.

    **Its relation to `test_the_notice_writes_nothing_this_instance_
    declared` above**, which sweeps every field of the notice for every
    value this instance declares and would already fail on this one. That
    sweep is broader and this is not a second copy of it: it runs here,
    over this repository, and says a value leaked; this runs in the build
    a duplicate is doing, over the duplicate's own declaration, and says
    what the field is for.
    """
    cases = tuple(
        (product, declared) for product, declared, _ in TAKES_THE_INSTANCES_NAME
    )
    expected = [field for _, _, field in TAKES_THE_INSTANCES_NAME]
    assert _asked_of_both(cases) == (expected, expected)


def test_neither_reader_refuses_a_product_that_names_the_software() -> None:
    """Narrowness, proved rather than asserted -- including the shipped
    answer, which is what makes the sweep above a control and not a rule
    that would refuse this repository's own notice."""
    empty: list[str | None] = [None] * len(NAMES_THE_SOFTWARE)
    assert _asked_of_both(NAMES_THE_SOFTWARE) == (empty, empty)


def test_both_readers_refuse_in_the_same_words() -> None:
    """Two refusals, one message, and what it has to say.

    The message is the whole of the control's value: a build that stops
    without saying which field is wrong, what it is for, and where the
    series' name was supposed to go leaves a duplicate guessing at the
    file the licence obliges it to keep. So the text is read here, and
    both sides are read, because two readers drifting is D-14's own named
    risk.
    """
    argument = json.dumps(["Monthly Reading Group", "series"])
    from_cjs = _node(
        f"const a = {argument};"
        f"console.log(require({str(SHOWCASE_READER.as_posix())!r}).refusal(a[0], a[1]))"
    )
    from_mjs = _node(
        f"const a = {argument};"
        f"import({COCKPIT_READER.as_uri()!r})"
        ".then(m => console.log(m.refusal(a[0], a[1])))"
    )
    assert from_cjs == from_mjs, (
        "the two readers refuse the same declaration in different words, so "
        "which build a duplicate happens to run decides what it is told"
    )

    for expected, why in (
        ("product names the software", "what the field is for"),
        ("never the series running on it", "what it is not"),
        (
            "identity.organisation and identity.series",
            "where the series' name is already printed, and has been all along",
        ),
        ("sections 4 and 5", "why the line beside it cannot simply be edited"),
        ("TRADEMARK.md", "the page that carries the whole of the distinction"),
    ):
        assert expected in from_cjs, (
            f"the refusal does not name {expected!r} -- {why}. A build that "
            "stops without it is a build somebody works around."
        )


def test_the_showcase_prints_every_field_of_the_notice() -> None:
    """The colophon every public page carries."""
    template = SHOWCASE_LAYOUT.read_text(encoding="utf-8")
    missing = [f for f in FIELDS if f"notice.{f}" not in template]
    assert missing == [], (
        f"{SHOWCASE_LAYOUT.name} no longer prints {missing} -- a page that "
        "displays part of a notice displays no Appropriate Legal Notice"
    )


def test_the_cockpit_prints_every_field_of_the_notice() -> None:
    """The cockpit's own footer, which is a second interactive interface
    and therefore a second obligation under section 5."""
    component = COCKPIT_LAYOUT.read_text(encoding="utf-8")
    missing = [f for f in FIELDS if f"notice.{f}" not in component]
    assert missing == [], (
        f"{COCKPIT_LAYOUT.name} no longer prints {missing} -- a footer that "
        "displays part of a notice displays no Appropriate Legal Notice"
    )
