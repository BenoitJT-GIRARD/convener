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
from .registration import Registration, matching_code, normalize_email


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
    a sequence, so word order plays no part in the comparison at all."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return frozenset(stripped.casefold().split())


def _match_by_code(
    display_name: str, registrations: Sequence[Registration], event: MatchEvent
) -> Registration | None:
    """Cascade level 1. The first registration (input order) whose own
    code the display name carries -- a display name that somehow carried
    two different registrants' codes at once is not a case this cascade
    tries to disambiguate, the same first-match idiom
    `registration.find_by_email` and `platform.find_speaker` already use
    rather than proving uniqueness."""
    for registration in registrations:
        code = matching_code(event.event_id, registration.email, event.salt)
        if code is not None and _display_name_carries_code(display_name, code):
            return registration
    return None


def _match_by_address(
    email: str, registrations: Sequence[Registration]
) -> Registration | None:
    """Cascade level 2: the row's own address, compared through
    `normalize_email` -- the same comparison `upsert` and `find_by_email`
    already use."""
    target = normalize_email(email)
    for registration in registrations:
        if normalize_email(registration.email) == target:
            return registration
    return None


def _match_by_name(
    display_name: str, registrations: Sequence[Registration]
) -> Registration | None:
    """Cascade level 3, the weakest rung by design (spec S:5 ranks it
    last): the display name's word set against the registrant's own first
    name and surname as a set."""
    target = _name_tokens(display_name)
    for registration in registrations:
        candidate = _name_tokens(f"{registration.first_name} {registration.surname}")
        if candidate == target:
            return registration
    return None


def _resolve(
    row: AttendanceRow, registrations: Sequence[Registration], event: MatchEvent
) -> Registration | None:
    """The cascade, in order, each level tried only once the one above it
    found nothing. Level 1 is tried unconditionally; levels 2 and 3 are
    tried only when `row.email` is not `None` -- see the module
    docstring's "Why level 1 alone is tried for a telephone row" section."""
    by_code = _match_by_code(row.display_name, registrations, event)
    if by_code is not None or row.email is None:
        return by_code
    return _match_by_address(row.email, registrations) or _match_by_name(
        row.display_name, registrations
    )


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
    unmatched_totals: dict[str, tuple[str, str, int]] = {}
    unreachable: list[UnreachableAttendee] = []

    for row in rows:
        registration = _resolve(row, registrations, event)
        if registration is not None:
            matched_totals[registration] = (
                matched_totals.get(registration, 0) + row.duration_seconds
            )
            continue

        if row.email is not None:
            key = normalize_email(row.email)
            seen_name, seen_email, total = unmatched_totals.get(
                key, (row.display_name, row.email, 0)
            )
            unmatched_totals[key] = (
                seen_name,
                seen_email,
                total + row.duration_seconds,
            )
            continue

        unreachable.append(
            UnreachableAttendee(
                display_name=row.display_name,
                duration_seconds=row.duration_seconds,
            )
        )

    return Matched(
        matched=tuple(
            MatchedAttendee(registration=registration, duration_seconds=duration)
            for registration, duration in matched_totals.items()
        ),
        unmatched=tuple(
            UnmatchedAttendee(
                display_name=seen_name, email=seen_email, duration_seconds=total
            )
            for seen_name, seen_email, total in unmatched_totals.values()
        ),
        unreachable=tuple(unreachable),
    )
