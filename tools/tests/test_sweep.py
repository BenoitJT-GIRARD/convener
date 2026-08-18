from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from conftest import config, speaker

from convener_ops.sweep import sweep


def _scheduled(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": "scheduled",
        "edition_code": "MRG-05",
        "date": "2026-01-08",
        "time": "12:30",
        "host_1": "H1",
        "host_2": "H2",
    }
    base.update(overrides)
    return speaker(**base)


def test_a_finished_seminar_becomes_delivered() -> None:
    now = datetime(2026, 1, 8, 13, 1, tzinfo=UTC)  # 14:01 Paris
    swept, changes = sweep([_scheduled()], config(), now)
    assert swept[0]["status"] == "delivered"
    assert changes == ["spk-001: scheduled -> delivered"]


def test_an_ongoing_seminar_is_untouched() -> None:
    now = datetime(2026, 1, 8, 12, 0, tzinfo=UTC)  # 13:00 Paris
    swept, changes = sweep([_scheduled()], config(), now)
    assert swept[0]["status"] == "scheduled"
    assert changes == []


def test_summer_time_is_handled() -> None:
    now = datetime(2026, 7, 9, 12, 1, tzinfo=UTC)  # 14:01 Paris
    swept, _ = sweep([_scheduled(date="2026-07-09")], config(), now)
    assert swept[0]["status"] == "delivered"


def test_a_row_without_time_flips_the_next_day() -> None:
    row = _scheduled(time="")
    same_day = datetime(2026, 1, 8, 23, 0, tzinfo=UTC)
    next_day = datetime(2026, 1, 9, 8, 0, tzinfo=UTC)
    assert sweep([row], config(), same_day)[1] == []
    assert sweep([row], config(), next_day)[1] != []


def test_other_statuses_are_never_touched() -> None:
    rows = [
        speaker(id="spk-001", status="lead"),
        speaker(id="spk-002", status="archived"),
    ]
    swept, changes = sweep(rows, config(), datetime(2030, 1, 1, tzinfo=UTC))
    assert changes == []
    assert [r["status"] for r in swept] == ["lead", "archived"]


def test_the_input_is_not_mutated() -> None:
    rows = [_scheduled()]
    sweep(rows, config(), datetime(2026, 1, 8, 13, 1, tzinfo=UTC))
    assert rows[0]["status"] == "scheduled"
