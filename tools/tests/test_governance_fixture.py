"""The shared fixture is the contract between the two implementations.

Two green suites in two languages once proved insufficient: the browser
wrote `time: 12:30` and Python read the integer 750. Both sides now read the
same cases from one file.
"""

from __future__ import annotations

import json
import re
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
from convener_ops.notify import due_date, overdue, overdue_text, waiting_since
from convener_ops.paths import repo_root
from convener_ops.sweep import _unsettled_candidates

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
    when this many working days have elapsed.

    A case that cannot be computed inverts to nothing rather than to its day
    count: there is no day to count to.
    """
    if case["expected"] == "":
        assert working_days_elapsed(case["from"], case["expected"]) == 0
        return
    assert working_days_elapsed(case["from"], case["expected"]) == case["days"]


@pytest.mark.parametrize("case", CASES["lateness_cases"], ids=lambda c: c["name"])
def test_overdue_wording_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    """The sentences the daily digest carries are the screens' sentences.

    The overdue list belongs in the digest, and that wording already
    existed in `app/src/state/sla.ts`. A digest that reworded it
    would be the fifth cross-language divergence in this repository, so both
    halves read these cases: `app/tests/governance-fixture.test.ts` runs them
    through `lateness`, `overdueText` and `waitingSince`.

    `days`, `overdue_text` and `waiting_since` are asserted only on the
    `overdue` arm, because on the other two arms they do not exist to assert --
    `notify.overdue` returns `None` and `Lateness` carries no count.
    """
    speaker = case["speaker"]
    config = case["config"]
    late = overdue(speaker, config, case["today"])
    deadline = due_date(speaker, config)

    if case["state"] == "none":
        assert deadline is None
        assert late is None
        return

    assert deadline is not None
    assert deadline.step == case["step"]
    assert deadline.due == case["due"]
    assert deadline.since == case["since"]

    if case["state"] == "due":
        assert late is None
        return

    assert late is not None
    assert late.days == case["days"]
    assert overdue_text(late) == case["overdue_text"]
    assert waiting_since(late) == case["waiting_since"]


@pytest.mark.parametrize(
    "case", CASES["unsettled_nomination_cases"], ids=lambda c: c["name"]
)
def test_unsettled_nominations_match_the_shared_fixture(case: dict[str, Any]) -> None:
    """The nomination question, pinned across the two languages.

    `board.ts::isUnsettled` refuses a second nomination while this is true;
    `sweep.py::_unsettled_candidates` keeps the same candidate off the
    inactivity proposal. This module reads the cases through the Python one,
    `app/tests/nominations.test.ts` through the browser's. The Python copy
    mirrored the narrower `isPending` before these cases existed -- it read
    only the outcome -- so a member with a deferred nomination standing
    against them could be proposed inactive by the nightly sweep.
    """
    candidates = _unsettled_candidates({"nominations": [case["nomination"]]})
    expected = {case["nomination"]["candidate"]} if case["unsettled"] else set()
    assert candidates == expected


#: Every case block the fixture carries, excluding the underscore-prefixed
#: prose comments that document individual blocks -- those are not data
#: either language reads, and would trivially "match" their own block's
#: name if counted.
_TOP_LEVEL_KEYS = [key for key in CASES if not key.startswith("_")]


def _corpus(directory: Path, pattern: str) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(directory.glob(pattern))
    )


def _is_read(key: str, corpus: str) -> bool:
    """Whether `key` is used as a fixture lookup somewhere in `corpus`.

    Checked textually, the same way `handbook-registry.mjs` already checks
    fixture-file completeness in this project: a quoted subscript
    (`CASES["name"]`, the shape every Python reader of this fixture uses) or
    a dotted property access (`cases.name`, the shape the TypeScript readers
    use, since a JSON import types every key as a real property). Neither
    pattern matches a bare, unquoted mention in prose, so a comment that
    merely names a block does not count as reading it.
    """
    escaped = re.escape(key)
    quoted = re.search(rf"""(['"]){escaped}\1""", corpus)
    dotted = re.search(rf"\.{escaped}\b", corpus)
    return bool(quoted or dotted)


def test_every_top_level_fixture_key_is_read_by_somebody() -> None:
    """Entry 4 of the deferred-work register.

    Neither this module nor `app/tests/governance-fixture.test.ts` used to
    assert that every top-level block of `governance-cases.json` is read by
    *somebody* -- either language's suite, anywhere, not only by the two
    files most obviously named after the fixture. A block can otherwise sit
    unread indefinitely, which is exactly the drift D-14's shared fixture
    exists to prevent: cases were added here precisely because reading them
    from one language and not the other let two implementations disagree
    without either suite noticing.

    "Read by somebody" does not require both languages to read the same
    block -- some blocks describe a rule with no browser-side counterpart
    (the webhook-signature cases, for instance, exercised only by
    `test_proposal.py`) -- only that at least one real test, in either
    language, actually looks the block up.
    """
    corpus = "\n".join(
        [
            _corpus(Path(__file__).parent, "test_*.py"),
            _corpus(repo_root() / "app" / "tests", "*.test.ts"),
            _corpus(repo_root() / "app" / "tests", "*.test.tsx"),
        ]
    )
    unread = [key for key in _TOP_LEVEL_KEYS if not _is_read(key, corpus)]
    assert unread == [], f"fixture key(s) read by nobody: {unread}"


def test_the_completeness_check_itself_has_something_to_check() -> None:
    """An empty `_TOP_LEVEL_KEYS` would pass the test above vacuously -- the
    same guard every other sweep in this suite puts on its own walk."""
    assert len(_TOP_LEVEL_KEYS) > 0


def test_the_unsettled_fixture_still_covers_both_kinds_of_deferral() -> None:
    """Guards the cases themselves: a deferral whose objection stands and one
    whose objections have all been withdrawn answer differently, and a fixture
    that lost either would pass on an implementation reading only the outcome
    -- which is exactly the implementation this pair replaced."""
    deferred = [
        case
        for case in CASES["unsettled_nomination_cases"]
        if case["nomination"]["outcome"] == "deferred"
    ]
    assert sorted(case["unsettled"] for case in deferred) == [False, True]
