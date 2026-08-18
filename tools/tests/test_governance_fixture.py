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

from convener_ops.governance import decide, threshold_for

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
