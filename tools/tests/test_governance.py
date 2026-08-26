"""What only the Python side of the governance rule promises.

`convener_ops.governance` reads whatever is in the repository -- hand-edited YAML, a
half-finished migration, a config from an older schema -- and runs unattended in
a scheduled job, so it degrades to the safe empty answer instead of raising. Its
TypeScript twin has no such guards and needs none: the browser only sees data
the app itself just wrote. See the module docstring.

The shapes below cannot be expressed in `governance-cases.json`, because the
TypeScript types forbid them; the rule these guards protect is pinned there,
in `active_board_cases`, and read by both languages.
"""

from __future__ import annotations

from typing import Any

from conftest import board_member

from convener_ops.governance import (
    active_board,
    add_working_days,
    decide,
    eligible_voters,
    working_days_elapsed,
)

ON = "2026-01-20"


def test_a_malformed_config_yields_no_board_rather_than_raising() -> None:
    assert active_board({}, ON) == ([], [])
    assert active_board({"board": "nope"}, ON) == ([], [])
    assert active_board({"board": None}, ON) == ([], [])


def test_a_malformed_member_is_skipped_rather_than_raising() -> None:
    board: list[Any] = ["nope", {}, None, board_member(login="ada")]
    assert active_board({"board": board}, ON) == (["ada"], [])


def test_a_member_without_a_usable_login_is_dropped() -> None:
    # An empty or non-string login can never be matched against a ballot's
    # voter, and `assign_lead` returning it would be indistinguishable from
    # "no assignment": it is not a board member for any purpose here.
    board = [board_member(login=""), board_member(login=17), board_member(login=None)]
    assert active_board({"board": board}, ON) == ([], [])


def test_a_non_string_unavailable_until_declares_no_absence() -> None:
    # Comparing an int against an ISO string would raise; a value this
    # malformed carries no absence to honour, so it is read as none.
    board = [board_member(login="ada", unavailable_until=20260201)]
    assert active_board({"board": board}, ON) == (["ada"], [])


def test_a_ballot_without_a_voter_key_neither_recuses_nor_raises() -> None:
    # Both halves of `decide` read the voter the same tolerant way: a ballot
    # missing the key must not take a member out of the denominator, and must
    # not blow up the job either.
    ballots: list[dict[str, Any]] = [
        {"value": "recused"},
        {"voter": "ada", "value": "yes"},
        {"value": "yes"},
    ]
    assert eligible_voters(["ada", "grace", "carol"], [], ballots) == [
        "ada",
        "grace",
        "carol",
    ]
    outcome = decide(["ada", "grace", "carol"], [], ballots)
    assert outcome.eligible == 3
    assert outcome.yes == 1


def test_an_unparsable_date_computes_no_deadline_rather_than_raising() -> None:
    # A hand-edited `opened_on` must not close a window and must not crash the
    # nightly job: no deadline can be computed, so the caller leaves the
    # window open.
    assert add_working_days("not-a-date", 3) == ""
    assert add_working_days("2026-02-30", 3) == ""
    assert add_working_days("", 3) == ""


def test_an_unusable_window_length_computes_no_deadline() -> None:
    # `objection_window_working_days` comes from a YAML file a human can edit.
    assert add_working_days("2026-08-17", "3") == ""
    assert add_working_days("2026-08-17", 3.0) == ""
    assert add_working_days("2026-08-17", None) == ""
    # `bool` is an `int` in Python; `True` is not a day count.
    assert add_working_days("2026-08-17", True) == ""


def test_a_negative_window_is_the_identity_as_it_is_in_typescript() -> None:
    assert add_working_days("2026-08-19", -3) == "2026-08-19"


def test_an_unparsable_span_reads_as_no_time_elapsed() -> None:
    # Zero elapsed means "the window has not run", so nothing is parked or
    # accepted on a date nothing could make sense of.
    assert working_days_elapsed("not-a-date", "2026-08-20") == 0
    assert working_days_elapsed("2026-08-17", "not-a-date") == 0
