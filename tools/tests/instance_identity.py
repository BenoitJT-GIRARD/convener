"""What names this instance, and what still names it on purpose.

Two facts live here because two modules need exactly the same ones and a
second copy of either would be the defect this whole phase exists to end:

1. **The needles** -- every writable form of what `config/instance.json`
   and the charter in force declare. `test_second_instance.py` sweeps a
   *build* for them; anything looking for "this instance's identity" in
   text should derive it from here rather than from a literal.
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

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Final

from convener_ops import brand, published

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

#: A needle short enough that an accidental run of the same letters inside
#: minified output is plausible is matched on word boundaries instead of
#: as a bare substring. Only the short name qualifies today ("TEC"), and
#: the alternative -- dropping it from the sweep -- would drop the one
#: form of this instance's name that its own templates use most.
_WORD_BOUNDED = re.compile(r"^[A-Za-z0-9]{1,5}$")


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
            "this instance's speakers rather than its name, which is why "
            "no needle here matches it -- and a second instance's build "
            "regenerates it from its own `data/speakers.yml` before "
            "Eleventy ever reads it, which is why it reaches nothing "
            "built."
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


def needles(root: Path) -> dict[str, str]:
    """Every writable form of what one instance declares about itself.

    Derived, never typed: the address and the identity from
    `config/instance.json` through the reader that owns them, the palette
    from the charter in force through `brand.source`. A needle nobody can
    derive is a needle that goes stale the day the declaration moves.

    Both derived forms of a declared value are here as well as the value
    itself, because a copy does not have to be a copy of the whole thing
    to be one: a page can write the origin without the path, a poster can
    write the forum's registrable domain without the `www.`, and an
    architecture note can write the repository's name without its owner.

    Every field of the identity is here by enumeration, not by hand, and
    the reason is below in the code. Nothing about the *address* half is
    enumerable the same way -- `Published` derives four different shapes
    from one string -- so those four stay written out.

    Deliberately absent, so that every needle below can be *proved* to
    match something in a real build rather than passing green by matching
    nothing (`test_second_instance.py`):

    - **`published.Published.publish_repository`.** It is where a build is
      pushed, read by two workflows and by nothing that renders. Its two
      halves are already needles (`host`, `path_prefix`).
    - **`motif.ribbon_width_ratio`.** The templates multiply it by a
      dimension and write the product, so the ratio itself never reaches
      an artefact.
    - **`typography`.** Both the product's default charter and this
      instance's name the two faces the product ships and serves from its
      own origin (D-17). A face is not an identity here; naming one that
      is not shipped would build a page that silently falls back.
    - **`black` and `white`.** Two colours in the charter's own palette
      that are nobody's identity, and that appear in every stylesheet ever
      written.
    """
    address = published.load(root)
    identity = published.load_identity(root)
    found = {
        "published_url": address.url,
        "origin": address.origin,
        "host": address.host,
        "path_prefix": address.path_prefix,
    }
    # Every declared identity field, enumerated from the declaration's own
    # list rather than written out again here. Phase 11 task 3 is why: it
    # added `strapline`, the poster's own hero line, and the eight fields
    # below were a hand-typed dict -- so the new one was not a needle, and
    # the sweep of a second instance's build passed green over a poster
    # hard-typing this instance's motto. Found by breaking it on purpose
    # and watching nothing fail. A field that a duplicate declares is a
    # field a duplicate's artefacts print; there is no such thing as one
    # this sweep should not look for.
    found.update({name: getattr(identity, name) for name in published.IDENTITY_FIELDS})
    found.update(
        {
            "forum_host": identity.forum_host,
            "forum_domain": identity.forum_host.removeprefix("www."),
            "repository_name": identity.repository.partition("/")[2],
        }
    )
    for name, value in brand.colours(brand.load(root)).items():
        if value in ("#ffffff", "#000000"):
            continue
        found[f"colour.{name}"] = value
    return found


def contains(text: str, needle: str) -> bool:
    """Whether `text` writes `needle`, on word boundaries when the needle
    is short enough for a coincidence to be plausible."""
    if _WORD_BOUNDED.match(needle):
        return re.search(rf"\b{re.escape(needle)}\b", text) is not None
    return needle in text


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
