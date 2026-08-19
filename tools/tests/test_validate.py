from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import board_member, config, speaker

from convener_ops.validate import board_target_report, validate_config, validate_speakers

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "governance-cases.json").read_text(
        encoding="utf-8"
    )
)


def test_a_minimal_lead_is_valid() -> None:
    assert validate_speakers([speaker()]) == []


def test_top_level_must_be_a_list() -> None:
    errors = validate_speakers({"id": "spk-001"})
    assert errors == ["speakers.yml: top-level must be a list"]


def test_duplicate_id_is_rejected() -> None:
    errors = validate_speakers([speaker(), speaker(name="Grace Hopper")])
    assert any("duplicate id 'spk-001'" in e for e in errors)


def test_unknown_status_is_rejected() -> None:
    errors = validate_speakers([speaker(status="bogus-status")])
    assert any("invalid status 'bogus-status'" in e for e in errors)


def test_scheduled_requires_edition_date_and_two_hosts() -> None:
    errors = validate_speakers([speaker(status="scheduled")])
    joined = " | ".join(errors)
    assert "requires edition_code" in joined
    assert "requires date" in joined
    assert "requires both host_1 and host_2" in joined


def test_duplicate_edition_code_is_rejected() -> None:
    common = {
        "status": "scheduled",
        "host_1": "A",
        "host_2": "B",
        "edition_code": "MRG-01",
    }
    errors = validate_speakers(
        [
            speaker(id="spk-001", date="2026-01-08", **common),
            speaker(id="spk-002", date="2026-02-12", **common),
        ]
    )
    assert any("duplicate edition_code 'MRG-01'" in e for e in errors)


def test_malformed_date_and_time_are_rejected() -> None:
    errors = validate_speakers([speaker(date="08/01/2026", time="12h30")])
    joined = " | ".join(errors)
    assert "date must be YYYY-MM-DD" in joined
    assert "time must be HH:MM" in joined


def test_config_missing_keys_are_reported() -> None:
    cfg = config()
    del cfg["season"]
    errors = validate_config(cfg)
    assert any("missing keys ['season']" in e for e in errors)


def test_the_view_counting_window_is_configuration_on_this_side_too() -> None:
    """The window a view count is read off is a convention, so it is a setting.

    Both languages have to require it, or the browser writes a file the
    scheduled jobs refuse - or, worse, the other way round, and a config
    without the key reaches `data/` where the app then reads `undefined`
    into a label. `docs/workflow/4-after.md` states the convention itself.
    """
    cfg = config()
    del cfg["view_count_window_days"]
    errors = validate_config(cfg)
    assert any("missing keys ['view_count_window_days']" in e for e in errors)

    errors = validate_config(config(view_count_window_days="thirty"))
    assert any("view_count_window_days must be an integer" in e for e in errors)

    assert validate_config(config(view_count_window_days=90)) == []


def test_config_board_member_must_look_like_a_login() -> None:
    # Schema v3: board_members (flat login list) was replaced by board
    # (a list of BoardMember mappings) in Task 1 / Task 4. The rule this
    # test pins - a malformed login is rejected - is unchanged; only the
    # shape of the data it is expressed against has moved.
    errors = validate_config(config(board=[board_member(login="not a login!")]))
    assert any("invalid board member" in e for e in errors)


def test_valid_config_produces_no_error() -> None:
    assert validate_config(config()) == []


@pytest.mark.parametrize(
    "case", CASES["board_headcount_cases"], ids=lambda c: c["name"]
)
def test_the_headcount_bounds_count_active_members(case: dict[str, Any]) -> None:
    """The same table `app/tests/board.test.ts` reads.

    `board.resolveNominations` counts active members before it seats anyone,
    so counting entries here would let the app write a config this function
    then rejects in CI - a file rejected by the validator of the very tool
    that wrote it.

    The two bounds are read apart because they are different kinds of thing:
    the ceiling is a rule and fails the file, the floor is a target and is
    reported. The fixture's `within` is the arithmetic both languages agree
    on; which side of it the case falls on decides which channel speaks.
    """
    cfg = config(
        board=case["board"],
        board_min=case["board_min"],
        board_max=case["board_max"],
    )
    errors = validate_config(cfg)
    over = [e for e in errors if "over board_max" in e]
    assert bool(over) is (case["active"] > case["board_max"]), errors
    if over:
        assert f"board has {case['active']} active members" in over[0]

    report = board_target_report(cfg)
    assert (report is not None) is (case["active"] < case["board_min"]), report
    if report is not None:
        assert f"board has {case['active']} active members" in report
        # And the shortfall is not smuggled back in as an error.
        assert not [e for e in errors if "active members" in e]

    assert (not over and report is None) is case["within"], (errors, report)


def test_a_board_under_its_target_is_reported_and_not_rejected() -> None:
    """A target that could fail a run would be a rule wearing a softer word.

    A board of two is under any declared target and under the floor a vote
    needs, and it is still a file the tools accept: the act that fixes it is
    a nomination, and a validator that refused the file would refuse the
    commit that carried the fix.
    """
    cfg = config(
        board=[board_member(login="a"), board_member(login="b")],
        board_min=5,
        board_max=9,
    )
    assert validate_config(cfg) == []
    report = board_target_report(cfg)
    assert report is not None
    assert "below its target of 5" in report
    assert report.isascii()


def test_the_target_report_says_nothing_about_a_file_it_cannot_read() -> None:
    # A malformed board or a missing target is validate_config's to report;
    # stating a headcount from a file nobody could parse would invent one.
    assert board_target_report({"board": "nonsense", "board_min": 5}) is None
    assert board_target_report(config(board=[board_member()])) is not None
    assert board_target_report({"board": [], "board_min": "five"}) is None
    assert board_target_report("nonsense") is None
