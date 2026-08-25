"""What names this instance, and what still names it on purpose.

Two facts live here because two modules need exactly the same ones and a
second copy of either would be the defect this whole phase exists to end:

1. **The needles** -- every writable form of what `config/instance.json`
   and the charter in force declare. They are **not written here any
   more**: phase 12 gave them a second reader outside the suite
   (`convener_ops.derivation_guard`, which asks the same question of every
   blob of every ref before a public push), and a derivation with two
   readers belongs in the package. `convener_ops.needles` owns it; the names
   are re-exported below so every reader of this module keeps working and
   nobody has two places to look. `test_second_instance.py` sweeps a
   *build* for them; anything looking for "this instance's identity" in
   text should derive it from there rather than from a literal.
2. **The deferred register** -- the files that knowingly still carry this
   instance's identity, each with the phase that owns it.
   `test_published.py` uses it to exempt those files from its *source*
   sweep; `test_second_instance.py` uses it to allow exactly the phrases
   they contribute to a *built* artefact, and no others. One list, two
   readings, so a file cannot be quietly forgiven on one side while the
   other still refuses it -- and so removing an entry without fixing the
   file fails both.

**Why the deferred entries are phrases and not files.** The source sweep
can exempt `app/src/data/demo.ts` by name because a source file is one
file. A build is not: `demo.ts`'s two strings end up inside the same
minified bundle as everything else the cockpit is made of, so exempting
that bundle would blind the build sweep to every other leak in it. So an
entry names the built artefacts it may reach (`carried_into`) and the
sweep removes from those artefacts only the literal runs of text the
deferred *source* actually contains. What is left is still swept. The
blind spot is therefore one known phrase in one named artefact, not a
file, and it closes by itself the day the source stops carrying the
phrase.

**No entry claims a built artefact today, and that is a result rather
than a simplification.** Phase 11 closed the last two that did: task 2
pointed the demonstration at `instances/example/` and task 3 derived the
poster's wordmark and strapline from the declaration. The machinery below
(`carried_into`, `allowance`, `literal_runs`, `allowed_for`,
`claimed_by_any`) stays exactly as it was -- it is what an entry has to
say for itself the next time one is needed, and
`test_second_instance.py::test_the_sweep_sees_what_the_deferred_register_
accounts_for` still holds it to that the moment one appears. What changed
is the arithmetic that test does: with nothing claimed, "the sweep must
find what the register accounts for" has no subject, and the sweep
finding *nothing at all* is the outcome the phase was for.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Final

from convener_ops.needles import contains, forms, needles

__all__ = [
    "BINARY_SUFFIXES",
    "DEFERRED",
    "Deferred",
    "allowance",
    "allowed_for",
    "claimed_by_any",
    "contains",
    "forms",
    "literal_runs",
    "needles",
]

#: Files whose bytes no text sweep can read. A `.png` carrying a wordmark
#: is a real identity surface and this is exactly where that surface stops
#: being visible -- see `test_second_instance.py`'s own docstring, which
#: names the three that exist rather than leaving the gap implied.
BINARY_SUFFIXES: Final = frozenset(
    {".png", ".jpg", ".jpeg", ".ico", ".pdf", ".woff2", ".woff", ".ttf"}
)

#: What a literal run of text ends at, when harvesting one out of a source
#: file. Quotes close a string in every language here; `<` and `>` close
#: an element in the HTML and SVG these sources emit; a newline closes a
#: line. Deliberately generous: a harvested phrase that is too short is a
#: narrower exemption, which fails safe, while one that is too long simply
#: stops matching and fails loudly.
_LITERAL_EDGES: Final = "\"'`\n\r<>"


@dataclass(frozen=True)
class Deferred:
    """One file that still names this instance, and the phase that owns it.

    `carried_into` is the part a build sweep needs and a source sweep does
    not: the built artefacts this file's identity legitimately reaches
    today, as glob patterns relative to a built repository's root. An
    empty tuple is a claim, not an omission -- it says this file reaches
    no built artefact at all, and `test_second_instance.py` fails if it
    turns out to reach one.
    """

    path: Path
    owner: str
    reason: str
    carried_into: tuple[str, ...] = ()


#: Everything that still names this instance on purpose, with the phase
#: that owns each. Not a general exemption: adding an entry here is a
#: decision, the reason sits beside the path, and both sweeps refuse the
#: file again the moment its entry is removed.
DEFERRED: Final = (
    Deferred(
        path=Path("site/src/_data/events.json"),
        owner="phase 11 (the example instance)",
        reason=(
            "The showcase's committed build fixture: a copy of "
            "`public-data/events-public.json`, refreshed by "
            "`publish-vitrine.yml` before every real build. It carries "
            "this instance's identity and not only its speakers, which is "
            "why the entry is load-bearing rather than a courtesy: two of "
            "the source sweep's four needles match it -- `identity.forum` "
            "and `identity.forum_host`, twice each, inside the two "
            "`forum_thread` values that two of its five records hold -- "
            "and its ids and thread slugs carry the edition prefix in both "
            "cases besides. Remove the entry and the source sweep names "
            "this file and that needle. What it reaches is nothing "
            "*built*, which is the separate claim `carried_into` makes: a "
            "second instance's build regenerates it from that instance's "
            "own `data/speakers.yml` before Eleventy ever reads it. Until "
            'phase 11 task 8 this reason said the opposite -- "no needle '
            'here matches it" -- which was false the day it was written; '
            "an exemption justified by a fact that is not true is an "
            "exemption the next reader deletes, and the sweep then fails "
            "for a reason nobody was warned about."
        ),
    ),
    Deferred(
        path=Path("project-words.txt"),
        owner="the cspell dictionary",
        reason=(
            "A list of words, not prose: the spell checker has to know "
            "this organisation's name is spelled that way because the "
            "repository's own history and specs write it. Nothing builds "
            "this file and nothing ships it."
        ),
    ),
)


def literal_runs(text: str, values: Iterable[str]) -> frozenset[str]:
    """Every run of `text` around an occurrence of one of `values`, cut at
    the nearest quote, angle bracket or line end and stripped.

    This is what turns "this file is allowed to name the instance" into
    "these exact phrases are allowed, wherever this file's output goes".
    Stripping matters: a template block indented in its source and
    re-indented in its output would otherwise stop matching and turn a
    known exemption into a mystery failure.
    """
    runs: set[str] = set()
    for value in values:
        start = text.find(value)
        while start != -1:
            left = start
            while left > 0 and text[left - 1] not in _LITERAL_EDGES:
                left -= 1
            right = start + len(value)
            while right < len(text) and text[right] not in _LITERAL_EDGES:
                right += 1
            run = text[left:right].strip()
            if run:
                runs.add(run)
            start = text.find(value, start + 1)
    return frozenset(runs)


def allowance(root: Path, wanted: Mapping[str, str]) -> dict[str, frozenset[str]]:
    """For each glob a deferred entry claims, the phrases that entry's own
    source contributes to it.

    Read from the source file every time rather than written down: a
    phrase typed here would be a copy of the very literal the entry exists
    to record, free to disagree with it the day somebody rewords the
    sentence.
    """
    by_pattern: dict[str, set[str]] = {}
    for entry in DEFERRED:
        if not entry.carried_into:
            continue
        text = (root / entry.path).read_text(encoding="utf-8")
        runs = literal_runs(text, [v for v in wanted.values() if v in text])
        for pattern in entry.carried_into:
            by_pattern.setdefault(pattern, set()).update(runs)
    return {pattern: frozenset(runs) for pattern, runs in by_pattern.items()}


def allowed_for(
    relative: str, patterns: Mapping[str, frozenset[str]]
) -> frozenset[str]:
    """The phrases a given built artefact may carry, from every deferred
    entry whose glob matches it."""
    runs: set[str] = set()
    for pattern, phrases in patterns.items():
        if fnmatch(relative, pattern):
            runs.update(phrases)
    return frozenset(runs)


def claimed_by_any(relative: str) -> bool:
    """Whether some deferred entry claims to reach this built artefact."""
    return any(
        fnmatch(relative, pattern)
        for entry in DEFERRED
        for pattern in entry.carried_into
    )
