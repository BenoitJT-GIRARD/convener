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

from convener_ops.sweep import expire_votes


def ballot(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "voter": "Anonymous",
        "value": "yes",
        "comment": "",
        "coi_reason": "",
        "date": "2026-01-08",
    }
    base.update(overrides)
    return base


def board_member(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "login": "Anonymous",
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
            board_member(login="Anonymous"),
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
                ballot(voter="Anonymous"),
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

    Written as its own assertion (not folded into the "parked" test above) so
    that a future refactor changing the target status cannot silently start
    declining leads by expiry without a test noticing.
    """
    row = lead(selection={"ballots": [], "opened_on": "2026-01-01", "decided_on": ""})
    now = datetime(2026, 1, 20, tzinfo=UTC)
    swept, _ = expire_votes([row], config(), now)
    assert swept[0]["status"] != "decline-board"


def test_a_suspended_vote_does_not_expire() -> None:
    # Only 2 eligible members (below MINIMUM_ELIGIBLE=3): the board could not
    # have decided even in principle, so expiring here would punish the
    # candidate for a staffing problem, not for the board's inaction.
    row = lead(selection={"ballots": [], "opened_on": "2026-01-01", "decided_on": ""})
    cfg = config(board=[board_member(login="Anonymous"), board_member(login="grace")])
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
