"""What names this instance, and what still names it on purpose.

Two facts live here because two modules need exactly the same ones and a
second copy of either would be the defect this whole phase exists to end:

1. **The needles** -- every writable form of what `instance/config.json`
   and the charter in force declare. They are **not written here any
   more**: they have a second reader outside the suite
   (`convener_ops.derivation.derivation_guard`, which asks the same question of every
   blob of every ref before a public push), and a derivation with two
   readers belongs in the package. `convener_ops.declaration.needles` owns it; the names
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
than a simplification.** The last two that did are closed: the
demonstration points at `instances/example/`, and the
poster's wordmark and strapline are derived from the declaration. The machinery below
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

from convener_ops.declaration.needles import contains, forms, needles
from convener_ops.declaration.published import unconfigured

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
        owner="the example instance",
        reason=(
            "The showcase's committed build fixture: a copy of "
            "`instance/public-data/events-public.json`, refreshed by "
            "`publish-showcase.yml` before every real build. It carries "
            "this instance's identity and not only its programme, which "
            "is why the entry is load-bearing rather than a courtesy: "
            "every record's id, and both `forum_thread` slugs, carry the "
            "declared edition prefix in both of the forms it reaches an "
            "artefact as. Remove the entry and the source sweep names "
            "this file and that needle. What it reaches is nothing "
            "*built*, which is the separate claim `carried_into` makes: a "
            "second instance's build regenerates it from that instance's "
            "own `instance/data/speakers.yml` before Eleventy ever reads it. "
            "Two corrections live in this sentence, both of the same "
            'shape. It once said "no needle here matches '
            'it", which was false the day it was written. It then said '
            "the matching needles were `identity.forum` "
            "and `identity.forum_host`, which stopped being true when "
            "both forum addresses were replaced with a "
            "reserved-domain one and the sentence was left describing them. "
            "An exemption justified by a fact that is not true is an "
            "exemption the next reader deletes, and the sweep then fails "
            "for a reason nobody was warned about -- so the reason names "
            "the needle that actually matches, and nothing else."
        ),
    ),
    Deferred(
        path=Path("project-words.txt"),
        owner="the cspell dictionary",
        reason=(
            "A list of words, not prose: the spell checker has to know "
            "this organisation's name is spelled that way because the "
            "repository's own history and specs write it. Nothing builds "
            "this file -- but it does ship, into the derived product "
            "repository, which is why this entry was reread. "
            "Eight of its entries were parts of people's names, and "
            "not one of them was reachable from anything cspell actually "
            "lints -- `cspell.json` ignores `instance/data/speakers.yml` outright "
            "and lints no `.json` at all -- so they came out and the run "
            "stayed green. Dead weight that happened to be somebody's "
            "name is the worst kind to leave in a shipped file. Two "
            "outlived that pass, each held by exactly one open decision, "
            "and both left with it: `docs/operating/contacts.md` and "
            "`docs/operating/operations.md` named four founders between "
            "them, both are linted, and cspell failed on seven "
            "occurrences the moment either word went. Those two pages "
            "name roles now, nothing linted spells either word, and the "
            "entries came out with the prose that held them. What is "
            "left in this file that names anybody is this organisation, "
            "which is the whole of the reason above."
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


# ------------------------------------------------------------------ #
# When the instance running this repository is the product's example
# ------------------------------------------------------------------ #

#: Why a test about the separation of two instances cannot run in a
#: repository that ships only one.
#:
#: `convener_ops.derivation.repository` lays `instances/example/` into every path
#: the boundary hands to the instance, because a product repository with
#: those paths merely deleted neither starts its own suite nor builds --
#: `paths.repo_root` finds a repository by `instance/data/config.yml` and the
#: product's default charter has no `motif`. The consequence is exact and
#: not a compromise: **in the derived repository the instance and the
#: example are the same instance**, so every needle agrees with itself,
#: every "second copy" is the example's own file, and a build made as the
#: example legitimately carries the example's identity.
#:
#: A test whose subject is the *difference* between two instances
#: therefore has no subject there, and asserting it anyway would make it
#: fail for the one reason it cannot fix. It comes back the moment a
#: duplicate edits its own declaration -- which is the same moment
#: `published.unconfigured` stops naming anything, and the same moment
#: the showcase's own banner goes quiet. One condition, three readers.
ONE_INSTANCE: Final = (
    "the instance running this repository is the product's own example "
    "(published.unconfigured names every declared value), so there is no "
    "second instance for this to be about -- it runs again as soon as a "
    "duplicate declares its own"
)


def ships_the_example_as_its_instance(root: Path | None = None) -> bool:
    """Whether `root`'s declaration is still the example's, value for value.

    Asked of `published.unconfigured`, which is product code and the
    definition rather than a second opinion on it: the same answer drives
    the banner the showcase prints and the one the cockpit prints above
    its sign-in screen.
    """
    return bool(unconfigured(root))
