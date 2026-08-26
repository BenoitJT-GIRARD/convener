from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import EDITIONS, board_member, config, speaker

from convener_ops.published import EditionPrefix
from convener_ops.validate import (
    board_target_report,
    validate_config,
    validate_speakers,
)

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "governance-cases.json").read_text(
        encoding="utf-8"
    )
)


def test_a_minimal_lead_is_valid() -> None:
    assert validate_speakers([speaker()], editions=EDITIONS) == []


def test_top_level_must_be_a_list() -> None:
    errors = validate_speakers({"id": "spk-001"}, editions=EDITIONS)
    assert errors == ["speakers.yml: top-level must be a list"]


def test_config_top_level_must_be_a_mapping() -> None:
    # Symmetric with validate_speakers's own "top-level must be a list"
    # above -- a config.yml that is a YAML list or scalar at the top level
    # (a hand-edit gone wrong) must be named as the defect it is.
    assert validate_config([1, 2, 3]) == ["config.yml: top-level must be a mapping"]


def test_a_non_mapping_entry_in_speakers_is_rejected_not_skipped() -> None:
    errors = validate_speakers(["not-a-mapping", speaker()], editions=EDITIONS)
    assert any(e == "speakers[0]: not a mapping" for e in errors)


def test_duplicate_id_is_rejected() -> None:
    errors = validate_speakers(
        [speaker(), speaker(name="Grace Hopper")], editions=EDITIONS
    )
    assert any("duplicate id 'spk-001'" in e for e in errors)


def test_a_missing_id_is_reported() -> None:
    s = speaker()
    del s["id"]
    errors = validate_speakers([s], editions=EDITIONS)
    assert any("missing id" in e for e in errors)


def test_unknown_status_is_rejected() -> None:
    errors = validate_speakers([speaker(status="bogus-status")], editions=EDITIONS)
    assert any("invalid status 'bogus-status'" in e for e in errors)


@pytest.mark.parametrize("key", ["name", "status"])
def test_a_missing_required_field_is_reported(key: str) -> None:
    s = speaker()
    del s[key]
    errors = validate_speakers([s], editions=EDITIONS)
    assert any(f"missing {key}" in e for e in errors)


def test_an_invalid_gender_is_reported() -> None:
    errors = validate_speakers([speaker(gender="not-a-gender")], editions=EDITIONS)
    assert any("invalid gender 'not-a-gender'" in e for e in errors)


def test_scheduled_requires_edition_date_and_two_hosts() -> None:
    errors = validate_speakers([speaker(status="scheduled")], editions=EDITIONS)
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
        ],
        editions=EDITIONS,
    )
    assert any("duplicate edition_code 'MRG-01'" in e for e in errors)


def test_malformed_date_and_time_are_rejected() -> None:
    errors = validate_speakers(
        [speaker(date="08/01/2026", time="12h30")], editions=EDITIONS
    )
    joined = " | ".join(errors)
    assert "date must be YYYY-MM-DD" in joined
    assert "time must be HH:MM" in joined


def test_a_malformed_edition_code_is_reported() -> None:
    errors = validate_speakers([speaker(edition_code="5")], editions=EDITIONS)
    assert any("edition_code must match MRG-N" in e for e in errors)


def test_an_edition_code_past_four_digits_is_rejected() -> None:
    """`EditionPrefix.pattern` bounds the digit run at four (`MRG-9999`)
    rather than leaving it unbounded: an unbounded id can grow
    `registration_code_modules`'s own QR version past the point where a
    printed poster's QR module drops below the scannable floor
    (`formats.SCANNABLE_QR_MODULE_MM`) -- `cli.py::render_visuals` is the
    check that runs that arithmetic for real, but a record this malformed
    should never pass `convener-validate` in the first place."""
    errors = validate_speakers([speaker(edition_code="MRG-99999")], editions=EDITIONS)
    assert any("edition_code must match MRG-N" in e for e in errors)


def test_a_four_digit_edition_code_is_still_accepted() -> None:
    errors = validate_speakers([speaker(edition_code="MRG-9999")], editions=EDITIONS)
    assert not any("edition_code must match MRG-N" in e for e in errors)


def test_the_edition_pattern_follows_the_declaration() -> None:
    """The shape is no longer the product's.

    `EDITION_RE` used to fix `MRG-` and one to four digits here -- the
    initials of the series that happens to run this repository, in the
    product's own validator, which is why a duplicate running a reading
    group numbered its sessions `MRG-1`. The pattern is built from whatever
    `config/instance.json` declares now, so the same record is valid under
    one instance and refused under another."""
    reading_group = EditionPrefix(value="MRG")
    assert (
        validate_speakers([speaker(edition_code="MRG-1")], editions=reading_group) == []
    )
    # A prefix that is nobody's. This used to be the prefix of the instance
    # running the repository, which made the
    # counter-example the one string a derivation is bound to rewrite --
    # and rewriting it turned the negative case into a second copy of the
    # positive one, silently.
    assert any(
        "edition_code must match MRG-N" in error
        for error in validate_speakers(
            [speaker(edition_code="ZZZ-1")], editions=reading_group
        )
    )


def test_an_edition_already_assigned_stops_the_prefix_being_changed() -> None:
    """The freeze, and where it actually bites.

    An edition code is not a label that can be reworded: it is in a
    published address (`/events/mrg-05/`, D-19), on every certificate issued
    for that event, and in `keys/events/mrg-05.pub` together with the
    repository secret derived from it. Nothing renumbers those.

    So there is no separate guard -- there is the derivation, read from
    the other end. A declaration moved after editions were assigned makes
    every one of them fail against the pattern built from it, and this is
    the clause that says *why* rather than reporting five unrelated shape
    errors: a whole file numbered under one other prefix is not five
    typing mistakes."""
    assigned = [
        speaker(id="spk-001", edition_code="MRG-1"),
        speaker(id="spk-002", edition_code="MRG-2"),
    ]
    errors = validate_speakers(assigned, editions=EditionPrefix(value="RG"))
    renames = [error for error in errors if "never renumbered" in error]
    assert len(renames) == 1, errors
    assert "2 edition_code(s) are numbered MRG-" in renames[0]
    assert "declares edition_prefix 'RG'" in renames[0]
    assert "/events/mrg-1/" in renames[0]
    assert "keys/events/mrg-1.pub" in renames[0]


def test_a_code_that_is_simply_malformed_is_not_reported_as_a_rename() -> None:
    """The other half of the clause above. `5` is a record somebody typed
    wrongly, not a repository whose declaration moved, and telling its
    author that an edition is never renumbered would send them to the
    wrong file."""
    errors = validate_speakers([speaker(edition_code="5")], editions=EDITIONS)
    assert not any("never renumbered" in error for error in errors)
    assert any("edition_code must match MRG-N" in error for error in errors)


@pytest.mark.parametrize("key", ["host_1", "host_2"])
def test_a_non_string_host_is_reported(key: str) -> None:
    errors = validate_speakers([speaker(**{key: 123})], editions=EDITIONS)
    assert any(f"{key} must be a string" in e for e in errors)


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


def test_a_turnaround_target_must_be_a_whole_number() -> None:
    """The four `sla_days` values are day counts, and nothing said so.

    `validate_config` used to check the four keys were *present* and never
    what they held, while `app/src/data/validate.ts::readSlaDays` reads each
    one with `whole()`. So `invitation_follow_up: "thirty"` passed CI and
    then took the whole app down on load - the one place a data error must
    not surface, because a volunteer reading it has no way back to the file.

    The message names the key by its path, because "sla_days must be a
    mapping" would send somebody looking at the wrong line of a file whose
    four lines look alike.
    """
    for key in ("invitation_follow_up", "summary_after_delivery"):
        sla = {**config()["sla_days"], key: "fourteen"}
        errors = validate_config(config(sla_days=sla))
        assert any(f"sla_days.{key} must be an integer" in e for e in errors), errors


def test_a_turnaround_target_is_not_a_flag() -> None:
    """`True` is an `int` in Python and is a day count nowhere.

    Left unrefused it would pass here and fail in the browser, which reads
    the same value with `Number.isInteger`; `governance._is_count` already
    turns it away on the other side of this package.
    """
    sla = {**config()["sla_days"], "recording_after_delivery": True}
    errors = validate_config(config(sla_days=sla))
    wanted = "sla_days.recording_after_delivery must be an integer"
    assert any(wanted in e for e in errors), errors

    errors = validate_config(config(vote_window_days=False))
    assert any("vote_window_days must be an integer" in e for e in errors)


def test_an_unreadable_sla_days_is_reported_once() -> None:
    """One sentence about the mapping, not five about a mapping that is not one."""
    errors = validate_config(config(sla_days="later"))
    assert any("sla_days must be a mapping" in e for e in errors)
    assert not any("must be an integer" in e for e in errors), errors


def test_a_missing_sla_days_key_is_reported_once_not_twice() -> None:
    # Reported once, by the missing-keys check -- must not also trip
    # "sla_days must be a mapping" (guarded by `"sla_days" in cfg`, for the
    # same reason as the board check above) or be read as an empty mapping.
    cfg = config()
    del cfg["sla_days"]
    errors = validate_config(cfg)
    assert any("missing keys ['sla_days']" in e for e in errors)
    assert not any("sla_days must be a mapping" in e for e in errors)
    assert not any("sla_days." in e for e in errors)


def test_a_stored_lead_decision_sla_is_reported_as_obsolete() -> None:
    # Schema v3: the board's decision deadline is vote_window_days, not
    # a fourth sla_days entry -- a file that still carries the old key would
    # leave whoever set it believing the board had that many days instead.
    cfg = config()
    cfg["sla_days"] = {**cfg["sla_days"], "lead_decision": 20}
    errors = validate_config(cfg)
    assert any("sla_days.lead_decision is obsolete" in e for e in errors)


def test_eligibility_share_is_required_configuration_not_a_constant() -> None:
    """A threshold that only ever lives as a
    Python default is a constant with extra steps, and alignment with an
    accreditation body's requirement has to happen by editing this file.

    Both languages have to require it, or the browser writes a file the
    certificate calculation refuses -- or, worse, the other way round, and
    a config without the key reaches `data/` where the eligibility
    calculation then falls back to a default nobody chose to write down.
    """
    cfg = config()
    del cfg["eligibility_share"]
    errors = validate_config(cfg)
    assert any("missing keys ['eligibility_share']" in e for e in errors)

    assert validate_config(config(eligibility_share=0.6666666666666666)) == []


def test_a_configured_eligibility_share_within_range_is_valid() -> None:
    assert validate_config(config(eligibility_share=0.5)) == []
    # The boundaries of ]0, 1]: 0 excluded, 1 included.
    assert validate_config(config(eligibility_share=1)) == []


def test_eligibility_share_of_zero_is_rejected_by_name() -> None:
    errors = validate_config(config(eligibility_share=0))
    assert any("eligibility_share must be a number in ]0, 1]" in e for e in errors), (
        errors
    )


def test_eligibility_share_above_one_is_rejected() -> None:
    errors = validate_config(config(eligibility_share=1.5))
    assert any("eligibility_share must be a number in ]0, 1]" in e for e in errors)


def test_a_negative_eligibility_share_is_rejected() -> None:
    errors = validate_config(config(eligibility_share=-0.5))
    assert any("eligibility_share must be a number in ]0, 1]" in e for e in errors)


def test_eligibility_share_is_not_a_flag() -> None:
    # `bool` first, the same reason `sla_days` entries and every other
    # CONFIG_INTS setting check it: `isinstance(True, int)` is true in
    # Python, and `true` is not a share of anything.
    errors = validate_config(config(eligibility_share=True))
    assert any("eligibility_share must be a number in ]0, 1]" in e for e in errors)


def test_eligibility_share_must_be_a_number() -> None:
    errors = validate_config(config(eligibility_share="two thirds"))
    assert any("eligibility_share must be a number in ]0, 1]" in e for e in errors)


def test_config_board_member_must_look_like_a_login() -> None:
    # Schema v3: board_members (flat login list) was replaced by board
    # (a list of BoardMember mappings). The rule this
    # test pins - a malformed login is rejected - is unchanged; only the
    # shape of the data it is expressed against has moved.
    errors = validate_config(config(board=[board_member(login="not a login!")]))
    assert any("invalid board member" in e for e in errors)


def test_a_non_list_board_is_reported() -> None:
    errors = validate_config(config(board="not-a-list"))
    assert any("board must be a list" in e for e in errors)


def test_a_non_mapping_board_member_is_reported() -> None:
    errors = validate_config(config(board=["not-a-mapping"]))
    assert any("invalid board member" in e for e in errors)


def test_a_missing_board_key_is_reported_once_not_twice() -> None:
    # A config.yml with no "board" key at all -- a hand-edit or an
    # in-progress migration -- is reported once, by the missing-keys check.
    # It must not also trip "board must be a list" (that check is guarded
    # by `"board" in cfg`, precisely so an absent key doesn't double up with
    # a present-but-wrong-type one), and must not be iterated as an empty
    # or None board either.
    cfg = config()
    del cfg["board"]
    errors = validate_config(cfg)
    assert any("missing keys ['board']" in e for e in errors)
    assert not any("board must be a list" in e for e in errors)
    assert not any("invalid board member" in e for e in errors)


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
