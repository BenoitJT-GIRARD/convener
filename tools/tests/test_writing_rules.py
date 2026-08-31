"""Two of the four writing rules, on the pages a reader outside this
project opens.

`docs/engineering/content-rules.md` section 7 is where those four rules are
stated. They came out of a house style this repository had rather than
chose: every development brief asked for the alternative that had been
rejected and for the reasoning behind the choice, and the prose absorbed
both. Pages ended up defending decisions against readers who had proposed
nothing, and narrating their own act of stating things.

**Two of the four are literal shapes and are held here.**

* **No hollow antithesis** (rule 2). "X, not Y" where Y is a suspicion of
  carelessness nobody voiced: *not an accident*, *not an oversight*, *not a
  preference*, *not an afterthought*. `HOLLOW_NEGATIONS` below is the closed
  list of those, and it is a closed list for the reason
  `test_prose_language.py::FRENCH_WORDS` is one -- the general rule needs a
  dictionary, the narrow one needs a list somebody can read and argue with.
* **No meta-commentary** (rule 3). A page describing its own act of stating:
  *worth saying out loud*, *stated rather than left to be discovered*.

**Two of the four are not testable, and no test here pretends otherwise.**

* **Rule 1** -- do not argue against an alternative the reader has not
  proposed -- turns on what a reader had in mind. Nothing in a file answers
  that.
* **Rule 4** -- the first paragraph says what the thing is -- turns on
  whether a paragraph defines or positions, which is the same judgement one
  clause further in.

A test for either would accept every page it read, because there is no
observable it could refuse on. That is a check that cannot fail, and this
repository has found five of those in the last two phases: they pass on the
day they are written, they pass again after the defect they were aimed at
comes back, and their existence is what stops anybody looking. Rules 1 and 4
are a reviewer's, and saying so here is what keeps somebody from writing the
sixth.

**Why the shapes are narrow.** ", not " appears about two hundred times in
these pages and is overwhelmingly correct: "a link, not an upload", "square
brackets, not double braces", "spoken, not projected" each tell a reader what
to do. A rule against the punctuation would fire on all of them, and a
control that cries on correct prose is a control somebody disables. What the
closed list catches is the other thing -- a negated term describing the
*quality of the decision* rather than anything in the subject.
`test_the_detector_leaves_a_legitimate_contrast_alone` pins five of those
correct sentences and `test_the_pinned_legitimate_sentences_are_real` reads
each one back out of the page it lives on, so the narrowness is proved rather
than asserted.

**The one page this does not sweep** is `docs/engineering/content-rules.md`
itself, which states both rules by quoting the shapes they refuse.
`test_prose_language.py` skips itself for the identical reason: the examples
are the explanation.
"""

from __future__ import annotations

import re
from pathlib import Path

from test_no_literal_copies import served_pages

from convener_ops.declaration.paths import repo_root

ROOT = repo_root()

#: The page that states the rules, and the one page they are not swept on.
#: See the module docstring's last paragraph.
SELF_DESCRIBING = "docs/engineering/content-rules.md"

#: What a hollow antithesis negates. Every one of these describes how a
#: decision was arrived at rather than anything in the subject, which is what
#: makes ", not an oversight" a defence and ", not an upload" an instruction.
#: Closed and short on purpose: a word earns its place by being one a page
#: only ever reaches for to pre-empt a reader's suspicion.
HOLLOW_NEGATIONS = frozenset(
    {
        "accident",
        "accidents",
        "afterthought",
        "afterthoughts",
        "arbitrary",
        "aspirational",
        "coincidence",
        "coincidences",
        "compromise",
        "compromises",
        "cosmetic",
        "courtesies",
        "courtesy",
        "decoration",
        "decorations",
        "defect",
        "defects",
        "formalities",
        "formality",
        "luxuries",
        "luxury",
        "niceties",
        "nicety",
        "omission",
        "omissions",
        "oversight",
        "oversights",
        "preference",
        "preferences",
        "preferred",
        "simplification",
        "simplifications",
        "taste",
        "theoretical",
        "whim",
        "whims",
    }
)

#: `, not <hollow>`, with the hedges and the article a real sentence puts
#: between them. Anchored on the comma because the appositive is what this
#: rule is about: "this is a rule, not a courtesy". A page that argues the
#: same point at length is rule 1's, and rule 1 is nobody's test.
HOLLOW_ANTITHESIS = re.compile(
    r",\s+not\s+(?:merely\s+|simply\s+|just\s+|only\s+)?(?:an?\s+|the\s+)?(?:"
    + "|".join(sorted(HOLLOW_NEGATIONS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)

#: A page narrating its own act of stating. Two shapes, both literal.
#:
#: `<verb of stating> rather than left` is the whole of the first, and the
#: verbs are listed rather than left open: "the participant is told so rather
#: than left to assume" is about a participant and survives, which is why
#: `told` is not among them.
#:
#: `worth saying` is the whole of the second, and it is deliberately not
#: `worth <anything>`: "worth knowing both before the day", "worth running
#: before the first step" and "worth reading that sentence twice" are advice
#: to a reader about an act of their own, and all three are on pages this
#: module sweeps.
META_COMMENTARY = re.compile(
    r"\b(?:stated|said|named|recorded|spelled\s+out|set\s+down|written\s+down)"
    r"\s+rather\s+than\s+left\b"
    r"|\bworth\s+(?:saying|stating|spelling\s+out)\b",
    re.IGNORECASE,
)


def swept() -> list[tuple[str, str]]:
    """Every page rule 7 applies to, with its text.

    The pages under `docs/` come from `test_no_literal_copies.served_pages`
    -- every markdown page in the three documentation trees, which is a
    superset of the 80 the cockpit's registry publishes, so a page written
    today is held to the rule before anybody registers it. The pages at the
    repository root are the other half of what `cspell.json` already gates,
    and are what whoever arrives at the repository reads first.
    """
    pages: list[tuple[str, str]] = []
    for path in list(served_pages()) + sorted(ROOT.glob("*.md")):
        relative = path.relative_to(ROOT).as_posix()
        if relative == SELF_DESCRIBING:
            continue
        pages.append((relative, path.read_text(encoding="utf-8")))
    return pages


def offences(pattern: re.Pattern[str], pages: list[tuple[str, str]]) -> list[str]:
    """Every match, named as `path:line: the phrase`.

    The phrase and not the paragraph: a failure has to say what to look for
    without reprinting somebody's page into a pytest report.
    """
    found: list[str] = []
    for name, text in pages:
        for number, line in enumerate(text.splitlines(), 1):
            for match in pattern.finditer(line):
                found.append(f"{name}:{number}: {match.group(0).strip()}")
    return found


# ------------------------------------------------------------------ #
# The sweep is real.
# ------------------------------------------------------------------ #


def test_the_sweep_reads_every_tree_the_rule_applies_to() -> None:
    """The guard `test_prose_language.py` and `test_second_instance.py` both
    put on their own walks: a corpus that quietly went empty, or lost a whole
    tree, would make the two rules below pass by reading nothing."""
    pages = swept()
    names = [name for name, _ in pages]

    assert SELF_DESCRIBING not in names, (
        "the page that states the rules is being swept for the shapes it "
        "quotes, which refuses the definition of the rule"
    )
    for tree in ("docs/handbook/", "docs/operating/", "docs/engineering/"):
        assert any(name.startswith(tree) for name in names), (
            f"no page under {tree} reached the sweep -- a whole tree of the "
            "documentation is passing over vacuously"
        )
    assert any("/" not in name for name in names), (
        "no page at the repository root reached the sweep, so the rule is "
        "unheld on the first pages anybody reads"
    )
    assert all(text.strip() for _, text in pages), (
        "a page reached the sweep with no text in it at all"
    )


# ------------------------------------------------------------------ #
# The two rules.
# ------------------------------------------------------------------ #


def test_no_page_defends_a_choice_against_a_hollow_alternative() -> None:
    """Content rule 2. The negated half of these was never anybody's
    proposal: a reader who has not decided the choice was careless is being
    answered anyway, and one who has is not persuaded by a denial. Say what
    the thing is; the argument for it is a decision record."""
    found = offences(HOLLOW_ANTITHESIS, swept())

    assert found == [], (
        "these pages answer a suspicion no reader raised -- state what the "
        f"thing is, and put the argument in a decision record: {found}"
    )


def test_no_page_narrates_its_own_act_of_stating() -> None:
    """Content rule 3. A page saying that something is worth saying has
    spent a sentence not saying it."""
    found = offences(META_COMMENTARY, swept())

    assert found == [], (
        f"these pages describe their own act of stating instead of stating: {found}"
    )


# ------------------------------------------------------------------ #
# Both directions. A detector that fires on nothing and a detector that
# fires on everything both pass the two tests above.
# ------------------------------------------------------------------ #

#: The shapes the rules name, in the words `content-rules.md` names them in,
#: plus the ones this repository published until they were rewritten --
#: `docs/operating/standing-up.md`'s own opening among them.
MUST_FIRE = (
    (
        HOLLOW_ANTITHESIS,
        "The split is forced, not preferred, and D-15 is the argument in full.",
    ),
    (
        HOLLOW_ANTITHESIS,
        "This is a decision, not an omission, and the tests pin it.",
    ),
    (
        HOLLOW_ANTITHESIS,
        "A deliberate aim, not an afterthought.",
    ),
    (
        HOLLOW_ANTITHESIS,
        "It is a known, disclosed limit, not an oversight.",
    ),
    (
        HOLLOW_ANTITHESIS,
        "Two consequences that are controls, not preferences.",
    ),
    (
        META_COMMENTARY,
        "What publication does cost, stated rather than left to be discovered.",
    ),
    (
        META_COMMENTARY,
        "The bus factor, stated rather than left for someone to notice.",
    ),
    (
        META_COMMENTARY,
        "That is worth saying out loud.",
    ),
)

#: Sentences on these pages today that are contrasts a reader acts on, and
#: that neither rule may touch. Read back out of the file each came from by
#: `test_the_pinned_legitimate_sentences_are_real`, so none of them can
#: quietly become an invented example of prose nobody writes.
MUST_NOT_FIRE = (
    (
        "docs/operating/schema.md",
        "A link, not an upload: the repository holds records, not media.",
    ),
    (
        "docs/handbook/governance/selection-criteria.md",
        "A genuine preference, not a hard rule",
    ),
    (
        "docs/handbook/toolkit/certificate.md",
        "written in **square brackets**, not double",
    ),
    (
        "docs/handbook/toolkit/intro-scripts.md",
        "Read them out loud once before",
    ),
    (
        "docs/operating/standing-up.md",
        "the participant is told so rather than left to assume",
    ),
)


def test_the_detector_fires_on_the_shape_it_names() -> None:
    """Break it and watch it fire. Every sentence here is one this
    repository published until the rule was written, or one
    `content-rules.md` quotes as the shape it refuses."""
    for pattern, sentence in MUST_FIRE:
        assert pattern.search(sentence) is not None, (
            f"the detector reads {sentence!r} as acceptable prose, so the "
            "rule it is supposed to hold is not held at all"
        )


def test_the_detector_leaves_a_legitimate_contrast_alone() -> None:
    """The other direction, and the one that decides whether anybody keeps
    this test. Each sentence below contrasts two things a reader chooses
    between -- a link against an upload, brackets against braces, reading
    aloud against reading silently -- and every one has to survive both
    patterns."""
    for source, sentence in MUST_NOT_FIRE:
        assert HOLLOW_ANTITHESIS.search(sentence) is None, (
            f"{source} carries a contrast a reader acts on and the "
            f"hollow-antithesis rule refuses it: {sentence!r}"
        )
        assert META_COMMENTARY.search(sentence) is None, (
            f"{source} carries a sentence about a person's own act and the "
            f"meta-commentary rule reads it as the page's: {sentence!r}"
        )


def test_the_pinned_legitimate_sentences_are_real() -> None:
    """An invented example proves nothing about prose anybody writes. Each
    sentence above is read back out of the page it was taken from, so
    rewording one fails here -- loudly, with the page named -- rather than
    leaving the must-not-fire set describing a repository that no longer
    exists."""
    for source, sentence in MUST_NOT_FIRE:
        text = (ROOT / source).read_text(encoding="utf-8")
        assert sentence in text, (
            f"{source} no longer carries {sentence!r} -- this module pins it "
            "as a contrast the rule must not refuse, so replace it with a "
            "sentence that page does carry"
        )


def test_the_rule_is_stated_where_writing_happens() -> None:
    """The page and the module are one rule with two halves, and the half a
    writer reads is the page. A module holding a rule no published page
    states is a rule nobody can comply with on purpose."""
    text = (ROOT / SELF_DESCRIBING).read_text(encoding="utf-8")

    assert "How a page is written" in text, (
        f"{SELF_DESCRIBING} no longer states the writing rules this module holds"
    )
    assert Path(__file__).name in text, (
        f"{SELF_DESCRIBING} states the rules without naming the module that "
        "holds two of them, so a writer reading the page cannot tell which "
        "two are checked"
    )
