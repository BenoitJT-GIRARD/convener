"""The terms this work is under, and the notice its two interfaces display.

Three files answer for three different things, and the whole point of
D-29 is that they are three and not one:

* ``LICENSE`` -- the GNU Affero General Public License, version 3, in the
  Free Software Foundation's own words, plus one added term at its head
  declining the name under section 7's paragraph e.
* ``TRADEMARK.md`` -- what that term covers, what a fork renames, and how
  little an unregistered mark is worth.
* ``NOTICE.json`` -- the Appropriate Legal Notice both interfaces print in
  their footer, in the sense section 0 of the licence defines the phrase.

**Why any of this needs a test at all.** Each of the three fails silently
when it fails. A ``LICENSE`` quietly replaced by a permissive one still
looks like a licence file; a notice with its warranty sentence dropped
still looks like a footer credit; a declaration moved into ``config/``
still builds. None of those shows up as a broken page, and the second is
the one that matters most: section 5 obliges a modified version's
interfaces to display an Appropriate Legal Notice **only where the
original's do**, so a notice that stops being one stops obliging anybody,
and nothing anywhere goes red.

**What is checked here, and what is checked elsewhere.** This module holds
the three declarations and the two templates that read them. That the
notice actually reaches a *rendered* page is a different claim, made
against real output on both sides: ``tools/tests/test_site.py`` builds the
showcase and reads its footer, and ``app/tests/notice.test.tsx`` renders
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
TRADE_MARKS = ROOT / "TRADEMARK.md"
DECLARATION = ROOT / "NOTICE.json"

SHOWCASE_LAYOUT = ROOT / "site" / "src" / "_includes" / "layout.njk"
COCKPIT_LAYOUT = ROOT / "app" / "src" / "components" / "Layout.tsx"

SHOWCASE_READER = ROOT / "site" / "scripts" / "notice.cjs"
COCKPIT_READER = ROOT / "app" / "scripts" / "notice.mjs"

#: The first line of the licence as the Foundation publishes it, indent
#: included. Where the head this repository adds stops and the licence
#: itself begins -- found rather than counted, so adding a paragraph to
#: the head cannot silently move what the digest below is taken over.
AGPL_FIRST_LINE = "                    GNU AFFERO GENERAL PUBLIC LICENSE"

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


def licence_head() -> str:
    """Everything this repository added above the licence itself."""
    text = licence_text()
    marker = f"\n{AGPL_FIRST_LINE}\n"
    assert marker in text, (
        f"{LICENCE.name} carries no line reading {AGPL_FIRST_LINE!r} -- "
        "either the licence text is not in it at all, or its first line "
        "has been reflowed, and neither is a state this file may be in"
    )
    return text[: text.index(marker) + 1]


def licence_body() -> str:
    """The licence itself, from its own first line to the end of file."""
    text = licence_text()
    marker = f"\n{AGPL_FIRST_LINE}\n"
    return text[text.index(marker) + 1 :]


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


def test_the_licence_names_the_holder_and_the_year() -> None:
    """A copyright notice is the first thing section 0 asks a notice to
    carry, and the licence file is where the claim itself is made."""
    head = licence_head()
    assert re.search(r"^Copyright \(C\) \d{4} \S", head, re.MULTILINE), (
        f"{LICENCE.name} states no copyright line above the licence text"
    )


def test_the_added_term_is_stated_as_one_section_7_permits() -> None:
    """The term is a section 7 term or it is nothing.

    Section 7 admits five kinds of supplementary term and calls everything
    else a further restriction, which a recipient may strip and which
    would make the work non-free besides. So the term has to *say* which
    kind it is, and say it where the licence it supplements is: this test
    reads the head of the licence file for the section it invokes, the
    right it declines, and the document that qualifies it.
    """
    head = licence_head()
    for expected, why in (
        ("SECTION 7", "the section that authorises an added term"),
        ("paragraph e", "the one kind of term this actually is"),
        ("trademark law", "the words section 7's paragraph e uses"),
        ("Convener", "the name the term is about"),
        ("brand/convener/", "where the marks it is about actually are"),
        ("TRADEMARK.md", "where a reader is sent for what it is worth"),
        ("further restriction", "the thing it has to say it is not"),
    ):
        assert expected in head, (
            f"{LICENCE.name}'s added term does not name {expected!r} -- "
            f"{why}. Without it the term reads as a preference rather "
            "than as a term section 7 permits."
        )


def test_the_added_term_sits_above_the_licence_it_supplements() -> None:
    """Above, never inside.

    A term interleaved with the licence's own clauses would make the text
    below no longer the official one -- which the digest above would catch
    -- and would also read, to anybody quoting a clause out of it, as part
    of the Foundation's words rather than as this project's addition.
    """
    text = licence_text()
    assert text.index("SECTION 7") < text.index(AGPL_FIRST_LINE)
    assert "TRADEMARK.md" not in licence_body()


# -------------------------------------------------------------------------- #
# The name
# -------------------------------------------------------------------------- #


def test_the_trade_mark_document_states_the_limit_of_its_own_claim() -> None:
    """A document claiming more protection than it has is worse than none.

    So the honest half is checked as strictly as the claim: that the name
    is held back is easy to write and easy to believe, and it is the
    sentences admitting that the mark is unregistered, that registration
    costs money this project does not spend, and that none of it binds
    somebody who does not care, that a later edit would quietly drop
    first.
    """
    text = TRADE_MARKS.read_text(encoding="utf-8")
    for expected, why in (
        ("unregistered", "what the mark actually is"),
        ("registration", "the only thing that would constrain anybody"),
        ("EUIPO", "who would register it, and for what fee"),
        ("passing off", "the only route an unregistered mark has"),
        ("rename", "what is actually being asked of a fork"),
        ("does not care", "who this stops, which is nobody"),
    ):
        assert expected in text, (
            f"{TRADE_MARKS.name} no longer says anything about "
            f"{expected!r} -- {why}. This file's whole value is that it "
            "does not overstate what an unlicensed name is worth."
        )


# -------------------------------------------------------------------------- #
# The notice
# -------------------------------------------------------------------------- #


def test_the_notice_belongs_to_the_product_and_to_no_instance() -> None:
    """The boundary's own answer, asked of the declaration's real path.

    Not a claim in a comment: `config/boundary.yml` hands named paths to
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
    needles `derivation_guard` refuses a public push over. A notice
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
