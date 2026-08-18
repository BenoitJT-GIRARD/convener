"""The governance rule, for writing.

`app/src/state/governance.ts` implements the same rule for display, and both are
pinned by `tests/fixtures/governance-cases.json`. A change here that is not
mirrored there is a defect: the volunteer would see one threshold while this
side applied another.

Pure: no filesystem, no clock, no environment.

Tolerant here, strict there
---------------------------
This module never raises on malformed input; its TypeScript twin has no such
guards at all. That asymmetry is deliberate, not an oversight, and it is not a
divergence of the rule itself -- on well-formed input the two agree exactly,
which is what the shared fixture pins.

The browser only ever sees data the app itself just wrote through a typed
mutation path, so `Config` and `Speaker` really do hold the shapes their types
promise; a guard there would be dead code that the coverage gate then has to
carry. Python reads whatever is in the repository: hand-edited YAML, a
half-finished migration, a config written by an older schema. It also runs
unattended in a scheduled job, where a raised exception is a silent no-op
overnight rather than a red screen a volunteer can react to. So every entry
point here degrades to the safe empty answer -- no eligible voters, no
unavailability -- instead of throwing.

Do not "harmonise" the two by deleting these guards: the next hand-edit to
`config.yaml` is what they are for. Add guards to the TypeScript side only if
it ever starts reading repository data directly.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

#: An ISO calendar day, the only date form stored in the two data files.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: A vote needs at least this many yes ballots in absolute terms, whatever the
#: ratio says. Guards a board shrunk by recusals from approving on two voices.
MINIMUM_YES = 3

#: Below this many eligible members the vote is suspended rather than decided on
#: a bar that has become meaningless.
MINIMUM_ELIGIBLE = 3


@dataclass(frozen=True)
class Outcome:
    eligible: int
    threshold: int
    yes: int
    decided: bool
    suspended: bool


def threshold_for(eligible: int) -> int:
    """Two thirds of the eligible board, rounded up, never below the floor.

    6 -> 4 and 9 -> 6, matching the two examples the handbook states.
    """
    return max(math.ceil(2 * eligible / 3), MINIMUM_YES)


def active_board(config: dict[str, Any], on: str) -> tuple[list[str], list[str]]:
    """Active board logins as of `on`, and the subset of them unavailable that
    day -- the `BoardMember` records reduced to the two flat lists `decide`
    consumes.

    `on` is an ISO `YYYY-MM-DD` string, the form the dates are stored in and
    the form the TypeScript side takes; a caller holding a `date` passes
    `d.isoformat()`. Both halves come back as lists, in board order, so the
    result is directly comparable with `activeBoard`'s and with the shared
    fixture. A caller wanting membership tests builds its own set.

    `status: inactive` leaves the board's denominator entirely; an unavailable
    member is still a member, only out of `N`. Inactive is not a departure and
    not a verdict: the entry, its `login` and its `joined_on` all stay in the
    file, `board.ts::seat` reactivates that same entry rather than adding a
    second one, and the annual meeting is what settles the question (G-09).
    Reading it as "gone for good" here would be wrong in both directions -- it
    would invite deleting the record, and it would make a return look like a
    new arrival.
    `unavailable_until` is inclusive: away *on* that date, back the day after.
    An empty value declares no absence. A value that is not a date is compared
    as it stands, which puts anything unparsable after the `on` date and so
    counts the member as away -- the conservative reading, since it shrinks the
    denominator rather than silently letting an absent member carry a vote.

    The single implementation of this mapping: `convener_ops.proposal` and
    `convener_ops.sweep` both call it, and it mirrors
    `app/src/state/board.ts::activeBoard`, pinned together by
    `tools/tests/fixtures/governance-cases.json`'s `active_board_cases`.
    """
    board = config.get("board") if isinstance(config, dict) else None
    if not isinstance(board, list):
        return [], []

    logins: list[str] = []
    unavailable: list[str] = []
    for member in board:
        if not isinstance(member, dict) or member.get("status") != "active":
            continue
        login = member.get("login")
        if not isinstance(login, str) or not login:
            continue
        logins.append(login)
        until = member.get("unavailable_until")
        until = until if isinstance(until, str) else ""
        if until and until >= on:
            unavailable.append(login)
    return logins, unavailable


def last_ballot_on(speakers: Sequence[Any], login: str) -> str:
    """The most recent day `login` cast a ballot, as an ISO string, or `''`.

    The `last_vote_on` the board model calls derived: it is computed from
    `speakers.yml` on every read and never written to `config.yml`, for the
    same reason the vote threshold is never written -- a stored copy is a
    second truth that can drift from the ballots it claims to summarise.

    Every ballot counts, whatever its value: an `abstain` and a `recused` are
    both a member turning up and saying something. Only silence is silence.
    Ballots whose date is missing or not an ISO day are skipped rather than
    compared as they stand: unlike `active_board`, where an unparsable date
    shrinks the denominator and so errs toward caution, an unparsable date
    here would err toward calling a member silent, and nothing about a
    volunteer's standing should rest on a typo.

    Python-only. No browser screen derives this today, so it has no twin in
    `app/src/state/` and no entry in the shared fixture -- adding one would
    pin a rule that only one side implements.
    """
    if not isinstance(speakers, Sequence) or isinstance(speakers, str | bytes):
        return ""
    latest = ""
    for entry in speakers:
        if not isinstance(entry, dict):
            continue
        selection = entry.get("selection")
        if not isinstance(selection, dict):
            continue
        ballots = selection.get("ballots")
        if not isinstance(ballots, list):
            continue
        for raw_ballot in ballots:
            if not isinstance(raw_ballot, dict):
                continue
            if raw_ballot.get("voter") != login:
                continue
            day = raw_ballot.get("date")
            if not isinstance(day, str) or not _DATE_RE.match(day):
                continue
            if day > latest:
                latest = day
    return latest


def eligible_voters(
    board: Sequence[str],
    unavailable: Iterable[str],
    ballots: Sequence[dict[str, Any]],
) -> list[str]:
    away = set(unavailable)
    recused = {b.get("voter") for b in ballots if b.get("value") == "recused"}
    return [login for login in board if login not in away and login not in recused]


def decide(
    board: Sequence[str],
    unavailable: Iterable[str],
    ballots: Sequence[dict[str, Any]],
) -> Outcome:
    voters = eligible_voters(board, unavailable, ballots)
    eligible = len(voters)
    threshold = threshold_for(eligible)
    voter_set = set(voters)
    # Count distinct voters, not distinct ballots: a hand-edited ballot list
    # may repeat a voter, and repetition must not inflate a yes count.
    yes_voters = {
        b.get("voter")
        for b in ballots
        if b.get("value") == "yes" and b.get("voter") in voter_set
    }
    yes = len(yes_voters)
    suspended = eligible < MINIMUM_ELIGIBLE
    return Outcome(
        eligible=eligible,
        threshold=threshold,
        yes=yes,
        decided=(not suspended and yes >= threshold),
        suspended=suspended,
    )
