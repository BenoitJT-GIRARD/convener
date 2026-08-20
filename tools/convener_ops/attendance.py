"""Join attendance rows off the platform (task 2's `AttendanceRow`) against
this event's registrations (task 6/7's `Registration`), per spec S:5's
appariement.

Three outcomes, not two
------------------------
A person who showed up is **matched** (their `Registration`, with all their
connections' durations summed), **unmatched** (an address the cascade could
not tie to any registration -- the host resolves this by hand, per S:5's
"reprise manuelle"), or **unreachable** (no address at all: a telephone
joiner). The third is not a flavour of the second. `platform.py`'s own
module docstring already draws this line and calls it a boundary, not a
matching weakness to keep improving: "no matching cascade this project can
build, present or future, will ever reach them by address or by normalised
name, for want of both." Folding "unreachable" into "unmatched" would hand
a host a name to go chase down an address that was never collected --
`Matched` keeps the two apart so nothing built on top of this module can
make that mistake either.

The cascade, in spec S:5's order
----------------------------------
1. **The matching code**, found inside the display name. Tried for every
   row, *including* one with no address -- the code depends only on what
   the participant typed, never on what the platform collected about them,
   so a phone joiner who somehow did carry the code (see "Why level 1 alone
   is tried for a telephone row" below) is still reachable through it.
2. **The exact address** -- `registration.normalize_email`, the same
   comparison `upsert` and `find_by_email` already use, reused rather than
   re-derived so this module cannot quietly disagree with them about what
   "the same address" means.
3. **The normalised name** -- casse, accents, ordre des mots (spec S:5).
   Tried only once 1 and 2 have both found nothing.

Only tried in that order, and only when the level above found nothing: a
code beats a contradicting address, and an address beats a contradicting
name, by construction -- `_resolve` returns the first level's answer and
never lets a later level overrule it. `test_attendance.py` proves this
directly, not just level by level in isolation: a code is tested as
*winning* against an address that names someone else, and an address is
tested as winning against a name that reads as someone else.

Ties are never resolved by guessing
----------------------------------------
"The level above found nothing" means zero candidates, specifically --
finding *more than one* equally-good candidate at a level is a third
outcome, not a variant of "found nothing" that falls through to try the
next level anyway. Two registrants who normalise to the same word set
("Marie Martin" twice, or, since level 3 compares a *set*, "Jean Martin"
against "Martin Jean") are a real, reviewed case: resolving either tie by
position in `registrations` would let who signed up first -- a fact with
no relationship to who was in the room -- silently decide whose
certificate names whose presence, and the tie would flip if the file's
entries were simply written in the other order. So a tie stops the
cascade exactly where an unambiguous match would: `_settle` returns no
registration and every tied candidate; `_resolve` does not then try a
weaker level to break it, the same way it does not let a weaker level
override an unambiguous answer. The row lands in `unmatched`, and
`UnmatchedAttendee.tied_with` carries every tied candidate's address, so
the host is resolving a named ambiguity, not restarting from nothing.

Why level 1 alone is tried for a telephone row
------------------------------------------------
`AttendanceRow.email` is `None` for a telephone joiner (`platform.py`'s
"email boundary"). Levels 2 and 3 both need something the platform never
collected from a phone call: 2 needs the address outright, and 3 needs a
*name* -- which, empirically, a dial-in participant does not have either,
because the platform shows the calling number as the display name, not
free text (measured against the real platform, not assumed -- see the
phase 4 spec's revalidation table). So `_resolve` does not even offer a
`None`-email row to levels 2 or 3; it would only ever compare a phone
number against an address or a name and fail, and skipping it outright
says plainly *why* it fails rather than leaving that to be discovered by
reading a comparison that can never succeed. Level 1 is offered regardless,
because nothing about it depends on there being an address at all -- a
telephone system that does let a caller type or announce free text could
still carry the code, and this module does not assume that never happens.

How much punctuation and case a matching code absorbs, and why here
-------------------------------------------------------------------------
`registration.matching_code` always returns upper case and says plainly
that whoever compares a typed name against it "must case-fold the typed
side first". The confirmation e-mail (`confirmation.py::MATCHING_INSTRUCTION`
and the worked example that follows it) tells a participant their display
name should read exactly `Ada Lovelace WXYZ-2345` -- the code sits beside a
name, separated by a space, and carries its own internal hyphen. Two kinds
of drift follow from a participant re-typing that on their own keyboard:
case (a phone keyboard that auto-capitalises, or one that does not), and
separators (the hyphen dropped, doubled, turned into a space, or wrapped in
parentheses).

This module absorbs both, and nothing else. `_code_signature` case-folds
the text and then keeps only alphanumeric characters, discarding every
other character outright -- so `WXYZ-2345`, `wxyz2345`, `wxyz 2345` and
`(WXYZ) 2345` all reduce to the same signature, and the code is found by a
substring search of one signature inside the other. What it deliberately
does *not* do is tolerate a wrong letter or digit: no edit-distance
fuzzing, no confusable-character substitution beyond what
`_CODE_ALPHABET` already excludes at generation time. A code that is
missed for want of some punctuation this module did not anticipate becomes
one line in the host's clean-up list -- a nuisance, corrected by looking at
the unmatched entry next to a room roster. A code matched with a wrong
character forgiven would bind one participant's certificate to another
person's presence, silently, which is the one failure spec S:5's
"empêche de revendiquer la présence d'autrui" exists to rule out. Between
"the host does a little more manual work" and "the wrong person is
recognised as present", this module chooses to fail toward the former
every time punctuation is not exactly what was asked for but the letters
and digits themselves are.

Durations sum per person -- once, here, by address
-------------------------------------------------------
`platform.py`'s own docstring names this module as the one place that
sums a reconnection's several rows into one duration, and the one place
that decides what "per person" means to do it: the address. For a matched
row that is the `Registration` the cascade resolved to (which is, in the
end, still keyed by its own address); for an unmatched row it is the row's
own normalised address, since two unmatched rows sharing an address are
still one unresolved person, not two entries for a host to puzzle over
separately. An unreachable row is never summed with another: there is no
address to group by, and inventing one -- by display name, which is
typically just the calling number and can legitimately repeat or vary
between two unrelated calls -- would be exactly the kind of invention the
task brief rules out ("aucune reprise manuelle ne peut inventer ce qu'elle
n'a jamais eu"). Each unreachable row stands for itself.

Nobody disappears in silence
---------------------------------
Every row this module is handed lands in exactly one of the three output
sequences -- `test_attendance.py::test_no_attendance_row_is_lost...` checks
this directly, by summing durations in against durations out and by
counting distinct people. `unmatched` is deliberately a short, returned
list rather than a side effect: the host resolves it after the event
(spec S:5), and a caller (`cli.py`, later) decides how to put it in front
of a human -- this module never prints or writes anything itself, the same
"every module but `cli.py` is pure" rule every other module in this
package already follows.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from .platform import AttendanceRow
from .registration import (
    Registration,
    looks_like_a_matching_code,
    matching_code,
    normalize_email,
)


@dataclass(frozen=True)
class MatchEvent:
    """The two facts `match` needs about the event itself, neither of which
    lives on an `AttendanceRow` or a `Registration`: `event_id` scopes a
    matching code to one event (two events sharing a salt must not derive
    the same code for the same address), and `salt` is
    `CONVENER_MATCHING_SALT`, read once by the caller and passed in rather than
    read from the environment here -- this module is pure, like every
    `convener_ops` module but `cli.py`. `salt` is `None` exactly when
    `matching_code` already treats that as ordinary (D-13): level 1 then
    never finds anything, and the cascade falls through to level 2 for
    every row, which is `matching_code`'s own documented fallback, not a
    special case this module adds.
    """

    event_id: str
    salt: str | None


@dataclass(frozen=True)
class MatchedAttendee:
    """One registrant who was found in the room, with every connection's
    `duration_seconds` already summed."""

    registration: Registration
    duration_seconds: int


@dataclass(frozen=True)
class UnmatchedAttendee:
    """One address the cascade could not tie to a registration -- present
    in the room, absent from every level's answer. The host's short list
    (spec S:5's "reprise manuelle"); `display_name` is the first spelling
    seen for this address, kept only because a host resolving this by hand
    needs something to recognise, not because this module treats it as
    authoritative the way a matched `Registration`'s own fields are."""

    display_name: str
    email: str
    duration_seconds: int
    #: The registered addresses that tied at whichever cascade level
    #: produced this outcome -- non-empty only when a level found more
    #: than one equally-good candidate (two registrants sharing a
    #: normalised name, say) and the cascade refused to guess between
    #: them; empty when no level found any candidate at all. Gives the
    #: host something concrete to act on beyond "this address matched
    #: nobody" -- see the module docstring's "Ties are never resolved by
    #: guessing" section. When several summed rows disagree on which tie
    #: was found (rare: it would mean the same address appeared alongside
    #: two different ambiguous display names), the first one seen wins,
    #: the same "first spelling seen" rule `display_name` already
    #: follows.
    tied_with: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnreachableAttendee:
    """One telephone joiner: no address, so no cascade level past the code
    could ever have reached them. Not a host-resolvable case -- see the
    module docstring's "boundary, not weakness" framing -- kept here only
    so the accounting in `Matched` never has to lose them to explain where
    they went."""

    display_name: str
    duration_seconds: int


@dataclass(frozen=True)
class Matched:
    """`match`'s whole answer: every person the input rows named, sorted
    into the three outcomes above and nowhere else."""

    matched: tuple[MatchedAttendee, ...]
    unmatched: tuple[UnmatchedAttendee, ...]
    unreachable: tuple[UnreachableAttendee, ...]


def _code_signature(text: str) -> str:
    """Case-folded, punctuation- and whitespace-stripped: what both a
    matching code and a display name are reduced to before comparing. See
    the module docstring's "How much punctuation and case a matching code
    absorbs" section for what this does and does not forgive."""
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _display_name_carries_code(display_name: str, code: str) -> bool:
    return _code_signature(code) in _code_signature(display_name)


def _name_tokens(text: str) -> frozenset[str]:
    """The case-, accent- and word-order-insensitive form spec S:5 asks
    the normalised-name level to compare on: NFKD-decompose so an accented
    letter splits into its base letter plus a combining mark, drop every
    combining mark, casefold, then split into a set of words -- a set, not
    a sequence, so word order plays no part in the comparison at all.

    Used as-is for a registrant's own `first_name`/`surname`: a matching
    code is never part of anyone's real name, so there is nothing to strip
    there. `_name_tokens_for_matching` below is the display-name-only
    variant that does strip one."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return frozenset(stripped.casefold().split())


def _name_tokens_for_matching(display_name: str) -> frozenset[str]:
    """Level 3's own tokenisation of a display name: `_name_tokens`, minus
    any token shaped like a matching code (`looks_like_a_matching_code`).

    The confirmation e-mail's worked example
    (`confirmation.MATCHING_INSTRUCTION`) reads `Ada Lovelace WXYZ-2345` --
    the participant's real name *plus* the code, never the code instead of
    the name. Comparing that display name's raw token set against a
    two-word registrant name would make the exact instruction being
    followed the reason a match fails, and would leave level 3's only
    reachable population as people who ignored the e-mail -- the opposite
    of what `_NO_CODE_FALLBACK` (`cli.py`) promises. Shape-only, not
    correctness: a *mistyped* code is still dropped, because level 3
    exists precisely for when the code did not work at level 1."""
    return frozenset(
        token
        for token in _name_tokens(display_name)
        if not looks_like_a_matching_code(token)
    )


def _code_candidates(
    display_name: str, registrations: Sequence[Registration], event: MatchEvent
) -> list[Registration]:
    """Cascade level 1: every registration whose own code the display name
    carries -- not collapsed to a single answer here. `_resolve` decides
    what zero, one, or more than one candidate means at this level; a
    display name carrying two different registrants' codes at once is not
    a person to guess about either -- see `_settle`."""
    return [
        registration
        for registration in registrations
        if (code := matching_code(event.event_id, registration.email, event.salt))
        is not None
        and _display_name_carries_code(display_name, code)
    ]


def _address_candidates(
    email: str, registrations: Sequence[Registration]
) -> list[Registration]:
    """Cascade level 2: every registration whose own address, compared
    through `normalize_email` -- the same comparison `upsert` and
    `find_by_email` already use -- equals the row's. `upsert` deduplicates
    addresses within one event, so two registrations sharing an address
    should not occur in practice; `_settle` guards it anyway, for free,
    against a caller that hands `match` a list built some other way."""
    target = normalize_email(email)
    return [
        registration
        for registration in registrations
        if normalize_email(registration.email) == target
    ]


def _name_candidates(
    display_name: str, registrations: Sequence[Registration]
) -> list[Registration]:
    """Cascade level 3, the weakest rung by design (spec S:5 ranks it
    last): every registration whose first name and surname, as a word
    set, equal the display name's -- with any token shaped like a
    matching code dropped first (`_name_tokens_for_matching`), since the
    confirmation e-mail's own instruction keeps the participant's real
    name in the display name *alongside* the code, not instead of it. Two
    registrants who happen to share a normalised name is exactly the case
    `_settle` exists for: this level is a coincidence of spelling, not
    proof of identity, so more than one equally-good candidate must never
    be resolved by which one happens to come first in the list."""
    target = _name_tokens_for_matching(display_name)
    if not target:
        return []
    return [
        registration
        for registration in registrations
        if _name_tokens(f"{registration.first_name} {registration.surname}") == target
    ]


@dataclass(frozen=True)
class _Resolution:
    """One row's answer from the cascade. `registration` is set when
    exactly one candidate was found at some level; `tied` holds every
    candidate found at whichever level stopped the cascade with more than
    one -- an ambiguous signal is never overridden by trying a weaker
    level next, the same way an unambiguous signal already overrides a
    contradicting weaker one. Both `registration is None` and `tied ==
    ()` together means no level found any candidate at all."""

    registration: Registration | None
    tied: tuple[Registration, ...] = ()


def _settle(candidates: list[Registration]) -> _Resolution:
    """The tie rule every cascade level shares: a single candidate is the
    answer, and more than one is not a person to guess about -- so the
    row lands in `unmatched`, carrying every tied candidate's address,
    where a host with the room roster can tell two same-named registrants
    apart. Reviewed and found wanting: the first-match idiom `find_speaker`
    and `find_by_email` use elsewhere in this package resolves on keys
    unique by construction (an event id, a deduplicated address); a code
    or a normalised name carries no such guarantee, and picking the first
    candidate in input order would let who signed up first -- a fact with
    no relationship to who was in the room -- silently decide whose
    certificate gets whose presence."""
    if len(candidates) == 1:
        return _Resolution(registration=candidates[0])
    return _Resolution(registration=None, tied=tuple(candidates))


def _address(row: AttendanceRow) -> str | None:
    """`row.email`, with a blank string folded into `None`. `platform.py`'s
    own reader already upholds "a blank cell is `None`, never `''`" (its
    "email boundary" section), so a well-formed `AttendanceRow` never
    exercises the blank branch here -- this is `match` *enforcing* that
    invariant rather than only trusting the one caller this package ships
    to have already kept it, against a hand-built row (a test double, or a
    future `Platform` implementation) that does not."""
    if row.email is None:
        return None
    stripped = row.email.strip()
    return stripped or None


def _duration(row: AttendanceRow) -> int:
    """`row.duration_seconds`, floored at zero. `platform.py`'s CSV reader
    rejects a negative duration outright, as a malformed row; `platform_fcc.py`
    deliberately does not -- it returns the provider's own figure exactly as
    received, anomalous or not, because a reader has no side channel of its
    own to report it through and correcting it there would hide a fact
    about the response. `match` is the one place both paths' rows are
    summed into a total this project may put in front of an accreditation
    body, and a negative contribution has no reading as time spent present
    -- so it is floored here, at the aggregation step, without touching or
    rejecting the row itself: `AttendanceRow.duration_seconds` stays
    exactly what was read, for anyone who inspects the row directly."""
    return max(0, row.duration_seconds)


def _resolve(
    row: AttendanceRow, registrations: Sequence[Registration], event: MatchEvent
) -> _Resolution:
    """The cascade, in order. Each level is tried only once the level
    above it found *no* candidate at all -- finding exactly one candidate
    at any level stops the cascade with a match, and finding more than
    one stops it with a tie: a level-1 tie (two codes in one display
    name) is not overridden by trying the address next, the same
    reasoning that already keeps a clean level-1 match from being
    overridden by a contradicting address. Level 1 is tried
    unconditionally; levels 2 and 3 are tried only when the row carries
    an address -- see the module docstring's "Why level 1 alone is tried
    for a telephone row" section."""
    code_candidates = _code_candidates(row.display_name, registrations, event)
    if code_candidates:
        return _settle(code_candidates)

    address = _address(row)
    if address is None:
        return _Resolution(registration=None)

    address_candidates = _address_candidates(address, registrations)
    if address_candidates:
        return _settle(address_candidates)

    name_candidates = _name_candidates(row.display_name, registrations)
    if name_candidates:
        return _settle(name_candidates)

    return _Resolution(registration=None)


def match(
    rows: list[AttendanceRow],
    registrations: Sequence[Registration],
    event: MatchEvent,
) -> Matched:
    """Join `rows` against `registrations` through the cascade above, and
    sum durations per person -- see the module docstring's "Durations sum
    per person" section for what "per person" means at each of the three
    outcomes.

    Deterministic in every input, and order-preserving in one specific
    sense: within each of the three output sequences, entries appear in
    the order their person was first seen in `rows`."""
    matched_totals: dict[Registration, int] = {}
    unmatched_totals: dict[str, tuple[str, str, int, tuple[str, ...]]] = {}
    unreachable: list[UnreachableAttendee] = []

    for row in rows:
        resolution = _resolve(row, registrations, event)
        if resolution.registration is not None:
            matched_totals[resolution.registration] = matched_totals.get(
                resolution.registration, 0
            ) + _duration(row)
            continue

        address = _address(row)
        if address is not None:
            key = normalize_email(address)
            seen_name, seen_email, total, seen_tied = unmatched_totals.get(
                key, (row.display_name, address, 0, ())
            )
            if not seen_tied and resolution.tied:
                seen_tied = tuple(candidate.email for candidate in resolution.tied)
            unmatched_totals[key] = (
                seen_name,
                seen_email,
                total + _duration(row),
                seen_tied,
            )
            continue

        unreachable.append(
            UnreachableAttendee(
                display_name=row.display_name,
                duration_seconds=_duration(row),
            )
        )

    return Matched(
        matched=tuple(
            MatchedAttendee(registration=registration, duration_seconds=duration)
            for registration, duration in matched_totals.items()
        ),
        unmatched=tuple(
            UnmatchedAttendee(
                display_name=seen_name,
                email=seen_email,
                duration_seconds=total,
                tied_with=seen_tied,
            )
            for seen_name, seen_email, total, seen_tied in unmatched_totals.values()
        ),
        unreachable=tuple(unreachable),
    )
