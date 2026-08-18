"""The governance rule, for writing.

`app/src/state/governance.ts` implements the same rule for display, and both are
pinned by `tests/fixtures/governance-cases.json`. A change here that is not
mirrored there is a defect: the volunteer would see one threshold while this
side applied another.

Pure: no filesystem, no clock, no environment.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

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


def eligible_voters(
    board: Sequence[str],
    unavailable: Iterable[str],
    ballots: Sequence[dict[str, Any]],
) -> list[str]:
    away = set(unavailable)
    recused = {b["voter"] for b in ballots if b.get("value") == "recused"}
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
