"""The shared fixture is the contract between the two implementations.

Two green suites in two languages proved insufficient in phase 1: the browser
wrote `time: 12:30` and Python read the integer 750. Both sides now read the
same cases from one file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from convener_ops.governance import (
    active_board,
    add_working_days,
    decide,
    threshold_for,
    working_days_elapsed,
)

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "governance-cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", CASES["threshold_cases"], ids=lambda c: c["name"])
def test_threshold_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    assert threshold_for(case["eligible"]) == case["expected"]


@pytest.mark.parametrize("case", CASES["decision_cases"], ids=lambda c: c["name"])
def test_decision_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    outcome = decide(
        board=case["board"],
        unavailable=case["unavailable"],
        ballots=case["ballots"],
    )
    assert outcome.eligible == case["eligible"]
    assert outcome.threshold == case["threshold"]
    assert outcome.yes == case["yes"]
    assert outcome.decided is case["decided"]
    assert outcome.suspended is case["suspended"]


@pytest.mark.parametrize("case", CASES["active_board_cases"], ids=lambda c: c["name"])
def test_active_board_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    """The `BoardMember` -> (logins, unavailable) step, pinned across both
    languages.

    `decision_cases` start from flat lists of logins, so they pin `decide` but
    say nothing about how a board record becomes one of those lists -- which is
    exactly where the two Python copies of this mapping once drifted apart
    without either suite noticing. `app/tests/board.test.ts` runs these same
    cases through `activeBoard`.
    """
    logins, unavailable = active_board({"board": case["board"]}, case["on"])
    assert logins == case["logins"]
    assert unavailable == case["unavailable"]
    away = set(unavailable)
    assert [login for login in logins if login not in away] == case["eligible"]


@pytest.mark.parametrize(
    "case", CASES["working_day_cases"]["add"], ids=lambda c: c["name"]
)
def test_add_working_days_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    assert add_working_days(case["from"], case["days"]) == case["expected"]


@pytest.mark.parametrize(
    "case", CASES["working_day_cases"]["elapsed"], ids=lambda c: c["name"]
)
def test_working_days_elapsed_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    assert working_days_elapsed(case["from"], case["to"]) == case["expected"]


@pytest.mark.parametrize(
    "case", CASES["working_day_cases"]["add"], ids=lambda c: c["name"]
)
def test_elapsed_inverts_add_on_every_shared_case(case: dict[str, Any]) -> None:
    """The two are one rule read from either end, so the fixture's `add` cases
    also pin `working_days_elapsed`: a window opened on `from` has run exactly
    when this many working days have elapsed."""
    assert working_days_elapsed(case["from"], case["expected"]) == case["days"]
