"""The delivery map in `docs/superpowers/README.md`, read against the files.

That file calls itself the entry point -- "quelqu'un qui reprend le travail,
humain ou agent, le lit en premier" -- and its table of phases is the first
thing read there. By phase 11 it had drifted twice over: it skipped phase 9
entirely and renumbered everything after it (calling the instance separation
"9" when it is 10, this phase "10" when it is 11, `convener` "11" when it is
12), and it gave three already-merged phases as "spec écrite, à revalider".

Nothing read it, which is the whole of why. Two facts are read here, and
both come out of the repository rather than out of prose:

1. **One row per spec, and no row without one.** `specs/…-phase-N-….md` is
   where a phase gets its number; a phase whose spec exists and whose row
   does not is a phase the entry point does not mention, and a row whose
   spec does not exist is a number somebody invented.
2. **A phase that has filed a bilan is not "à revalider".**
   `phase-N-bilan.md` is written at the end of a phase, so a row still
   telling a reader to revalidate its spec at the opening is a row about a
   phase that closed. This is one-directional on purpose: phase 7 merged
   without a bilan, so "has no bilan" says nothing at all.

**What this deliberately does not check is the label.** Binding a row's
words to its spec's own title would catch a mislabelled row -- the precise
shape of the drift above -- and it would cost relabelling three delivered
phases whose table entry is shorter than their spec's title ("Gouvernance
produit" for "La gouvernance dans le produit", and two more). That is the
maintainer's call about their own document, not a test's.
"""

from __future__ import annotations

import re

from convener_ops.paths import repo_root

ROOT = repo_root()
SUPERPOWERS = ROOT / "docs" / "superpowers"
MAP = SUPERPOWERS / "README.md"

#: The header row of the one table this module is about. The file carries a
#: second table ("Quel fichier répond à quoi"), so the table is found by
#: what it says it holds rather than by being the first one.
_HEADER = "| | Phase | État |"

#: `specs/2026-08-24-phase-9-file-soumissions-publiques.md` -> 9.
_SPEC_NUMBER = re.compile(r"-phase-(\d+)-")

_ROW = re.compile(r"^\|(?P<number>[^|]*)\|(?P<label>[^|]*)\|(?P<state>[^|]*)\|\s*$")

#: What a row says when it is telling a reader the phase has not started.
_UNOPENED = "à revalider"


def _rows() -> list[tuple[str, str, str]]:
    """Every row of the phase table, as its three cells, stripped."""
    lines = MAP.read_text(encoding="utf-8").splitlines()
    assert _HEADER in lines, f"{MAP.name} no longer carries the phase table"
    out: list[tuple[str, str, str]] = []
    for line in lines[lines.index(_HEADER) + 1 :]:
        if not line.startswith("|"):
            break
        match = _ROW.match(line)
        if match is None:
            continue  # the `|---|---|---|` separator
        cells = (
            match.group("number").strip(),
            match.group("label").strip(),
            match.group("state").strip(),
        )
        if set(cells[0]) <= {"-"} and cells[1].startswith("-"):
            continue  # the separator again, under a different spelling
        out.append(cells)
    return out


def _numbered_rows() -> list[tuple[int, str, str]]:
    """The rows that carry a phase number. The others are the three steps
    that are deliberately not phases (`| — |`): the services hookup, the
    launch, the security audit."""
    return [
        (int(number), label, state)
        for number, label, state in _rows()
        if number.isdigit()
    ]


def _spec_numbers() -> list[int]:
    return sorted(
        int(match.group(1))
        for path in (SUPERPOWERS / "specs").glob("*phase-*.md")
        if (match := _SPEC_NUMBER.search(path.name))
    )


def test_the_table_is_actually_read() -> None:
    # Non-vacuity: an empty parse would make every assertion below pass for
    # free, and this table is exactly the kind of thing a reformat breaks.
    rows = _rows()
    assert len(rows) > 10, f"only {len(rows)} rows parsed out of {MAP.name}"
    assert len(_numbered_rows()) > 6
    assert len(_spec_numbers()) > 6


def test_every_phase_with_a_spec_has_a_row_and_no_row_invents_one() -> None:
    numbered = _numbered_rows()
    listed = [number for number, _, _ in numbered]
    specs = _spec_numbers()
    assert listed == specs, (
        "the entry point's phase table and specs/ disagree about which "
        f"phases exist: the table lists {listed}, the specs are {specs}"
    )
    # `listed == specs` with `specs` sorted also settles the order and the
    # absence of a duplicate, which is what stops a renumbering from
    # leaving two rows claiming the same phase.


def test_no_phase_that_has_filed_a_bilan_is_still_waiting_to_open() -> None:
    filed = {
        int(match.group(1))
        for path in SUPERPOWERS.glob("phase-*-bilan.md")
        if (match := re.search(r"phase-(\d+)-bilan", path.name))
    }
    assert filed, "no phase has filed a bilan -- this test has no subject"
    stale = [
        (number, state)
        for number, _, state in _numbered_rows()
        if number in filed and _UNOPENED in state
    ]
    assert stale == [], (
        "these phases have filed a bilan and the entry point still tells a "
        f"reader to revalidate their spec at the opening: {stale}"
    )


def test_the_wording_this_looks_for_is_still_in_use() -> None:
    # Otherwise the test above would pass on the day somebody reworded the
    # state column, and go on passing while saying nothing.
    states = [state for _, _, state in _numbered_rows()]
    assert any(_UNOPENED in state for state in states), (
        f"no row says {_UNOPENED!r} any more, so the check above is vacuous"
    )
