"""Vote-window expiry: a lead whose vote window closes without a decision must
be parked, never declined. A refusal is always a deliberate act (handbook);
letting a window silently produce one would be the worst, least visible
failure of this system.

Factories below are defined locally rather than imported from conftest.py:
another task owns that fixture concurrently, so this file stays self
contained (only the minimal fields this module's tests actually exercise).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from convener_ops.governance.governance import (
    DEFAULT_VOTE_WINDOW_DAYS,
    PARIS,
    vote_window_days,
)
from convener_ops.sweep import expire_votes


def ballot(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "voter": "carol",
        "value": "yes",
        "comment": "",
        "coi_reason": "",
        "date": "2026-01-08",
    }
    base.update(overrides)
    return base


def board_member(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "login": "carol",
        "joined_on": "2024-01-01",
        "status": "active",
        "unavailable_until": "",
    }
    base.update(overrides)
    return base


def config(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "vote_window_days": 10,
        "board": [
            board_member(login="carol"),
            board_member(login="grace"),
            board_member(login="ada"),
        ],
    }
    base.update(overrides)
    return base


def lead(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "spk-001",
        "status": "lead",
        "selection": {"ballots": [], "opened_on": "2026-01-01", "decided_on": ""},
    }
    base.update(overrides)
    return base


def test_a_lead_past_its_window_without_the_threshold_is_parked() -> None:
    row = lead(selection={"ballots": [], "opened_on": "2026-01-01", "decided_on": ""})
    now = datetime(2026, 1, 20, tzinfo=UTC)  # 19 days after opening, window is 10
    swept, changes = expire_votes([row], config(), now)
    assert swept[0]["status"] == "parked"
    assert changes == ["spk-001: lead -> parked (vote window expired)"]


def test_a_lead_that_reached_the_threshold_is_untouched() -> None:
    row = lead(
        selection={
            "ballots": [
                ballot(voter="carol"),
                ballot(voter="grace"),
                ballot(voter="ada"),
            ],
            "opened_on": "2026-01-01",
            "decided_on": "",
        }
    )
    now = datetime(2026, 1, 20, tzinfo=UTC)
    swept, changes = expire_votes([row], config(), now)
    assert swept[0]["status"] == "lead"
    assert changes == []


def test_a_lead_still_inside_its_window_is_untouched() -> None:
    row = lead(selection={"ballots": [], "opened_on": "2026-01-15", "decided_on": ""})
    now = datetime(2026, 1, 20, tzinfo=UTC)  # 5 days in, window is 10
    swept, changes = expire_votes([row], config(), now)
    assert swept[0]["status"] == "lead"
    assert changes == []


def test_no_lead_ever_reaches_decline_board_by_expiry() -> None:
    """Protects the handbook rule that a refusal is always a deliberate act.

    The input is the state where a naive implementation would write a
    rejection: the window has elapsed on a deliberating board (5 eligible,
    threshold 4) that cast real ballots and stopped one short - a vote the
    board effectively did not carry. The answer is still `parked`, and no
    terminal rejection value appears anywhere in the result.
    """
    row = lead(
        selection={
            "ballots": [ballot(voter="carol", value="yes")],
            "opened_on": "2026-01-01",
            "decided_on": "",
        }
    )
    cfg = config(
        board=[
            board_member(login=name)
            for name in ("carol", "grace", "ada", "linus", "edsger")
        ]
    )
    now = datetime(2026, 1, 20, 12, tzinfo=UTC)
    swept, changes = expire_votes([row], cfg, now)
    assert swept[0]["status"] == "parked"
    trace = repr(swept) + repr(changes)
    assert "decline-board" not in trace
    assert "decline-speaker" not in trace


def test_a_suspended_vote_does_not_expire() -> None:
    # Only 2 eligible members (below MINIMUM_ELIGIBLE=3): the board could not
    # have decided even in principle, so expiring here would punish the
    # candidate for a staffing problem, not for the board's inaction.
    row = lead(selection={"ballots": [], "opened_on": "2026-01-01", "decided_on": ""})
    cfg = config(board=[board_member(login="carol"), board_member(login="grace")])
    now = datetime(2026, 1, 20, tzinfo=UTC)  # well past the window
    swept, changes = expire_votes([row], cfg, now)
    assert swept[0]["status"] == "lead"
    assert changes == []


def test_the_input_is_not_mutated() -> None:
    rows = [lead()]
    expire_votes(rows, config(), datetime(2026, 1, 20, tzinfo=UTC))
    assert rows[0]["status"] == "lead"


def test_other_statuses_are_never_touched() -> None:
    rows = [
        lead(id="spk-001", status="scheduled"),
        lead(id="spk-002", status="archived"),
    ]
    swept, changes = expire_votes(rows, config(), datetime(2026, 1, 20, tzinfo=UTC))
    assert changes == []
    assert [r["status"] for r in swept] == ["scheduled", "archived"]


# --- The vote window itself -------------------------------------------------


def test_the_closing_day_of_the_window_is_still_the_board_s_to_use() -> None:
    # Opened on the 1st with a 10-day window: the 11th is the last day the
    # board may still vote, so nothing may happen to the lead that day.
    row = lead(selection={"ballots": [], "opened_on": "2026-01-01", "decided_on": ""})
    now = datetime(2026, 1, 11, 23, tzinfo=PARIS)
    swept, changes = expire_votes([row], config(), now)
    assert swept[0]["status"] == "lead"
    assert changes == []


def test_the_day_after_the_window_closes_parks_the_lead() -> None:
    row = lead(selection={"ballots": [], "opened_on": "2026-01-01", "decided_on": ""})
    now = datetime(2026, 1, 12, 9, tzinfo=PARIS)
    swept, changes = expire_votes([row], config(), now)
    assert swept[0]["status"] == "parked"
    assert changes == ["spk-001: lead -> parked (vote window expired)"]


def test_the_window_closes_on_the_paris_calendar_not_the_utc_one() -> None:
    # 00:30 Paris on the 12th is still 23:30 UTC on the 11th. Reading the
    # UTC date would leave this lead inside its window for two more hours.
    row = lead(selection={"ballots": [], "opened_on": "2026-01-01", "decided_on": ""})
    now = datetime(2026, 1, 11, 23, 30, tzinfo=UTC)
    assert now.astimezone(PARIS).day == 12
    swept, changes = expire_votes([row], config(), now)
    assert swept[0]["status"] == "parked"
    assert changes == ["spk-001: lead -> parked (vote window expired)"]


# --- The default window -----------------------------------------------------


def test_the_default_window_is_fourteen_days() -> None:
    assert DEFAULT_VOTE_WINDOW_DAYS == 14
    assert vote_window_days({}) == 14


@pytest.mark.parametrize("value", [0, -1, "10", 10.5, None, True, [10]])
def test_an_unusable_window_falls_back_to_the_default(value: object) -> None:
    # A missing or nonsensical value must degrade to "do nothing yet", never
    # to "act on everything": a window of 0 would park every open lead the
    # day after it opened, and the scheduled job runs with no validation pass.
    assert vote_window_days({"vote_window_days": value}) == DEFAULT_VOTE_WINDOW_DAYS


def test_a_configured_window_is_honoured() -> None:
    assert vote_window_days({"vote_window_days": 21}) == 21


def test_a_config_without_the_key_uses_fourteen_days_end_to_end() -> None:
    row = lead(selection={"ballots": [], "opened_on": "2026-01-01", "decided_on": ""})
    cfg = config()
    del cfg["vote_window_days"]
    # Day 14 is still inside the window; only day 15 expires it.
    inside, changes = expire_votes([row], cfg, datetime(2026, 1, 15, tzinfo=PARIS))
    assert inside[0]["status"] == "lead"
    assert changes == []
    outside, changes = expire_votes([row], cfg, datetime(2026, 1, 16, tzinfo=PARIS))
    assert outside[0]["status"] == "parked"


def test_an_inactive_member_shrinks_n_enough_to_suspend_an_expiry() -> None:
    # Three declared members, one of them gone for good: N drops to 2, below
    # MINIMUM_ELIGIBLE, so the lead waits for a board able to deliberate
    # rather than being parked for a staffing problem.
    row = lead(selection={"ballots": [], "opened_on": "2026-01-01", "decided_on": ""})
    cfg = config(
        board=[
            board_member(login="carol"),
            board_member(login="grace"),
            board_member(login="ada", status="inactive"),
        ]
    )
    swept, changes = expire_votes([row], cfg, datetime(2026, 1, 20, tzinfo=PARIS))
    assert swept[0]["status"] == "lead"
    assert changes == []


def test_a_lead_without_a_selection_block_is_left_alone() -> None:
    # A hand-edited file can lose the block entirely; there is no window to
    # measure, so the job must not invent one.
    row = lead(selection=None)
    swept, changes = expire_votes([row], config(), datetime(2026, 1, 20, tzinfo=PARIS))
    assert swept[0]["status"] == "lead"
    assert changes == []


def test_a_malformed_ballot_list_reads_as_no_ballots_cast() -> None:
    row = lead(
        selection={"ballots": "none", "opened_on": "2026-01-01", "decided_on": ""}
    )
    swept, changes = expire_votes([row], config(), datetime(2026, 1, 20, tzinfo=PARIS))
    assert swept[0]["status"] == "parked"
    assert changes == ["spk-001: lead -> parked (vote window expired)"]
