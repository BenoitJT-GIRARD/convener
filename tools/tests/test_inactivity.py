"""Inactivity (G-09): a member who has gone silent stops counting toward `N`.

Every test here is about a named, unpaid volunteer, so the shape of the rule
matters as much as its arithmetic: it proposes, it never decides; it moves one
word in one field and removes nothing; and it refuses to speak at all when the
record cannot say when a silence began.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import ballot, board_member, config, nomination, speaker

from convener_ops import cli
from convener_ops.governance import MINIMUM_ELIGIBLE, active_board, last_ballot_on
from convener_ops.sweep import (
    _inactivity_months,
    _months_before,
    sweep_inactive_members,
)
from convener_ops.validate import validate_config

#: Every test reads the clock from here, in UTC, so the Paris conversion the
#: function does is exercised rather than bypassed.
NOW = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


def voted(login: str, day: str, **overrides: Any) -> dict[str, Any]:
    """A speaker whose selection carries one ballot from `login` on `day`."""
    base: dict[str, Any] = {
        "id": f"spk-{login}",
        "selection": {
            "ballots": [ballot(voter=login, date=day)],
            "opened_on": day,
            "decided_on": "",
        },
    }
    base.update(overrides)
    return speaker(**base)


def statuses(cfg: dict[str, Any]) -> dict[str, str]:
    return {m["login"]: m["status"] for m in cfg["board"]}


def with_three_recent(*members: dict[str, Any]) -> list[dict[str, Any]]:
    """`members`, followed by three seated too recently to be silent.

    Headroom, so that a test about one member's silence is not quietly a test
    about the MINIMUM_ELIGIBLE floor instead -- the floor has its own tests.
    """
    return [
        *members,
        *(
            board_member(login=login, joined_on="2026-08-01")
            for login in ("grace", "ada", "hopper")
        ),
    ]


# --------------------------------------------------------------- #
# The rule itself
# --------------------------------------------------------------- #


def test_a_member_silent_past_the_threshold_is_proposed_inactive() -> None:
    cfg = config(inactivity_months=6, board=with_three_recent(board_member()))
    speakers = [voted("Anonymous", "2025-06-01"), voted("ada", "2026-07-15")]
    proposed, prompts = sweep_inactive_members(cfg, speakers, NOW)

    assert statuses(proposed)["Anonymous"] == "inactive"
    assert [line.split(":")[0] for line in prompts] == ["Anonymous"]


def test_a_recently_active_member_does_not_move() -> None:
    cfg = config(inactivity_months=6)
    speakers = [voted(login, "2026-08-01") for login in ("Anonymous", "grace", "ada")]
    proposed, prompts = sweep_inactive_members(cfg, speakers, NOW)

    assert set(statuses(proposed).values()) == {"active"}
    assert prompts == []


def test_the_threshold_day_itself_is_still_a_day_to_vote_on() -> None:
    # Inclusive, the same reading expire_votes gives the vote window: silence
    # bites the day after the threshold, never on it.
    cfg = config(inactivity_months=6, board=with_three_recent(board_member()))
    on_the_day = [voted("Anonymous", "2026-02-18")]
    proposed, prompts = sweep_inactive_members(cfg, on_the_day, NOW)
    assert statuses(proposed)["Anonymous"] == "active"
    assert prompts == []

    the_day_before = [voted("Anonymous", "2026-02-17")]
    proposed, prompts = sweep_inactive_members(cfg, the_day_before, NOW)
    assert statuses(proposed)["Anonymous"] == "inactive"


def test_a_member_who_never_voted_is_counted_from_the_day_they_joined() -> None:
    cfg = config(
        inactivity_months=6,
        board=[
            board_member(login="Anonymous", joined_on="2026-07-01"),
            board_member(login="grace", joined_on="2020-01-01"),
            board_member(login="ada", joined_on="2020-01-01"),
        ],
    )
    speakers = [voted("grace", "2026-08-01"), voted("ada", "2026-08-01")]
    proposed, prompts = sweep_inactive_members(cfg, speakers, NOW)

    assert statuses(proposed)["Anonymous"] == "active"
    assert prompts == []


def test_a_member_who_never_voted_and_joined_long_ago_is_proposed() -> None:
    cfg = config(
        inactivity_months=6,
        board=with_three_recent(board_member(joined_on="2020-01-01")),
    )
    proposed, prompts = sweep_inactive_members(cfg, [], NOW)

    assert statuses(proposed)["Anonymous"] == "inactive"
    assert "no ballot since 2020-01-01" in prompts[0]


def test_the_later_of_the_last_ballot_and_joined_on_is_what_counts() -> None:
    # A member re-seated after a spell away: board.ts::seat rewrites joined_on,
    # so old ballots must not put them straight back on the list.
    cfg = config(
        inactivity_months=6,
        board=[
            board_member(login="Anonymous", joined_on="2026-08-10"),
            board_member(login="grace"),
            board_member(login="ada"),
        ],
    )
    speakers = [
        voted("Anonymous", "2024-01-05"),
        voted("grace", "2026-08-01"),
        voted("ada", "2026-08-01"),
    ]
    proposed, prompts = sweep_inactive_members(cfg, speakers, NOW)

    assert statuses(proposed)["Anonymous"] == "active"
    assert prompts == []


def test_any_ballot_value_counts_as_turning_up() -> None:
    cfg = config(inactivity_months=6)
    speakers = [
        speaker(
            id="spk-001",
            selection={
                "ballots": [
                    ballot(voter="Anonymous", value="abstain", date="2026-08-01"),
                    ballot(
                        voter="grace",
                        value="recused",
                        coi_reason="co-author",
                        date="2026-08-01",
                    ),
                ],
                "opened_on": "2026-08-01",
                "decided_on": "",
            },
        ),
        voted("ada", "2026-08-01"),
    ]
    proposed, prompts = sweep_inactive_members(cfg, speakers, NOW)

    assert prompts == []
    assert set(statuses(proposed).values()) == {"active"}


def test_the_most_recent_ballot_across_all_speakers_is_the_one_read() -> None:
    assert (
        last_ballot_on(
            [voted("ada", "2024-01-01"), voted("ada", "2026-03-04")],
            "ada",
        )
        == "2026-03-04"
    )


def test_a_ballot_with_an_unusable_date_is_skipped_not_trusted() -> None:
    # An unparsable date must never be the thing that calls someone silent.
    assert last_ballot_on([voted("ada", "not-a-date")], "ada") == ""
    mixed = [voted("ada", "2026-03-04"), voted("ada", "9999")]
    assert last_ballot_on(mixed, "ada") == "2026-03-04"


def test_last_ballot_on_tolerates_malformed_repository_data() -> None:
    assert last_ballot_on("not a list", "ada") == ""
    assert last_ballot_on([None, {}, {"selection": 3}], "ada") == ""
    assert last_ballot_on([{"selection": {"ballots": "no"}}], "ada") == ""
    stray = [{"selection": {"ballots": [None, {"voter": "x"}]}}]
    assert last_ballot_on(stray, "ada") == ""


# --------------------------------------------------------------- #
# It proposes; it never decides, and it never removes
# --------------------------------------------------------------- #


def test_the_proposal_never_removes_a_member_or_loses_their_history() -> None:
    cfg = config(
        inactivity_months=6,
        board=with_three_recent(board_member(joined_on="2019-05-04")),
    )
    speakers = [voted("Anonymous", "2024-01-05")]
    proposed, _ = sweep_inactive_members(cfg, speakers, NOW)

    assert [m["login"] for m in proposed["board"]] == [
        "Anonymous",
        "grace",
        "ada",
        "hopper",
    ]
    entry = proposed["board"][0]
    assert entry["joined_on"] == "2019-05-04"
    # One word in one field, and nothing else about the seat changed.
    assert entry == {**cfg["board"][0], "status": "inactive"}


def test_the_proposal_only_leaves_the_denominator_and_is_undone_by_one_word() -> None:
    cfg = config(
        inactivity_months=6,
        board=[
            board_member(login="Anonymous", joined_on="2019-05-04"),
            board_member(login="grace"),
            board_member(login="ada"),
            board_member(login="hopper"),
        ],
    )
    speakers = [voted(login, "2026-08-01") for login in ("grace", "ada", "hopper")]
    proposed, _ = sweep_inactive_members(cfg, speakers, NOW)

    assert active_board(proposed, "2026-08-18")[0] == ["grace", "ada", "hopper"]

    # The way back: one word, and the board is exactly what it was.
    proposed["board"][0]["status"] = "active"
    assert active_board(proposed, "2026-08-18")[0] == [
        "Anonymous",
        "grace",
        "ada",
        "hopper",
    ]
    assert proposed["board"] == cfg["board"]


def test_the_wording_names_a_silence_and_a_way_back_never_a_person() -> None:
    cfg = config(
        inactivity_months=6,
        board=with_three_recent(board_member(joined_on="2019-05-04")),
    )
    speakers = [voted("Anonymous", "2024-01-05")]
    _, prompts = sweep_inactive_members(cfg, speakers, NOW)

    line = prompts[0]
    assert line.startswith("Anonymous: no ballot since 2024-01-05;")
    assert "the seat is kept" in line
    assert "the annual meeting decides" in line
    assert "undoes it" in line
    # Nothing here is a judgement, and nothing reads as final.
    for verdict in ("removed", "expelled", "dropped", "failed", "negligent", "left"):
        assert verdict not in line.lower()


def test_the_prompts_stay_ascii_so_a_terminal_can_print_them() -> None:
    cfg = config(
        inactivity_months=6,
        board=with_three_recent(board_member(joined_on="2019-05-04")),
    )
    _, prompts = sweep_inactive_members(cfg, [], NOW)
    assert prompts
    for line in prompts:
        line.encode("ascii")


def _repo(tmp_path: Path, cfg: dict[str, Any], speakers: list[dict[str, Any]]) -> Path:
    """A repository root holding the two data files, for `cli.sweep`."""
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "speakers.yml").write_text(yaml.safe_dump(speakers), encoding="utf-8")
    (data / "config.yml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return tmp_path


def _speaking_case() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A board with one member long silent and three seated too recently to
    be, plus the ballot that dates the silence. Enough for the rule to speak."""
    cfg = config(
        inactivity_months=6,
        board=with_three_recent(board_member(joined_on="2019-05-04")),
    )
    return cfg, [voted("Anonymous", "2024-01-05")]


def test_the_scheduled_job_reports_the_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # G-09 says the rule is operated by the scheduled task. Detection is the
    # half it operates: `convener-sweep` prints the lines.
    cfg, speakers = _speaking_case()
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(_repo(tmp_path, cfg, speakers)))

    assert cli.sweep() == 0
    out = capsys.readouterr().out
    assert "Anonymous: no ballot since 2024-01-05;" in out
    # The wording rule holds wherever the lines are printed, heading included.
    for verdict in ("removed", "expelled", "dropped", "failed", "negligent", "left"):
        assert verdict not in out.lower()
    out.encode("ascii")


def test_the_scheduled_job_never_writes_an_inactivity_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The other half is not the scheduled task's: applying a proposal is a human
    # act on the Board screen, because a job with nobody's name on it must not
    # be able to change a volunteer's standing overnight. So the proposed config
    # must reach no writer -- what the sweep writes is byte-identical whether or
    # not the rule had anything to propose.
    speaking, speakers = _speaking_case()
    # The same data, with the rule not adopted: nothing to propose, everything
    # else about the run unchanged.
    silent = copy.deepcopy(speaking)
    del silent["inactivity_months"]

    written: list[bytes] = []
    for index, cfg in enumerate((speaking, silent)):
        root = _repo(tmp_path / str(index), cfg, copy.deepcopy(speakers))
        monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
        assert cli.sweep() == 0
        prompted = "no ballot since" in capsys.readouterr().out
        assert prompted is (cfg is speaking)
        written.append((root / "data" / "speakers.yml").read_bytes())
        # The config file is not a thing this command writes at all.
        assert yaml.safe_load(
            (root / "data" / "config.yml").read_text(encoding="utf-8")
        ) == yaml.safe_load(yaml.safe_dump(cfg))

    # Non-trivially so: both runs really did write a swept file.
    assert b"status: parked" in written[0]
    assert written[0] == written[1]
    # And the board on disk is untouched: every member still reads `active`.
    for index in (0, 1):
        on_disk = yaml.safe_load(
            (tmp_path / str(index) / "data" / "config.yml").read_text(encoding="utf-8")
        )
        assert {m["status"] for m in on_disk["board"]} == {"active"}


# --------------------------------------------------------------- #
# Contradictory states that cannot be constructed
# --------------------------------------------------------------- #


def test_a_member_who_declared_an_absence_is_not_silent() -> None:
    cfg = config(
        inactivity_months=6,
        board=with_three_recent(
            board_member(joined_on="2019-05-04", unavailable_until="2026-09-30")
        ),
    )
    proposed, prompts = sweep_inactive_members(cfg, [], NOW)

    assert statuses(proposed)["Anonymous"] == "active"
    assert prompts == []


def test_an_absence_ending_today_still_shelters_the_member() -> None:
    # unavailable_until is inclusive, the reading active_board applies.
    def cfg_until(until: str) -> dict[str, Any]:
        return config(
            inactivity_months=6,
            board=with_three_recent(
                board_member(joined_on="2019-05-04", unavailable_until=until)
            ),
        )

    proposed, _ = sweep_inactive_members(cfg_until("2026-08-18"), [], NOW)
    assert statuses(proposed)["Anonymous"] == "active"

    proposed, _ = sweep_inactive_members(cfg_until("2026-08-17"), [], NOW)
    assert statuses(proposed)["Anonymous"] == "inactive"


def test_a_member_the_board_is_still_admitting_is_left_alone() -> None:
    cfg = config(
        inactivity_months=6,
        board=with_three_recent(board_member(joined_on="2019-05-04")),
        nominations=[nomination(candidate="Anonymous", outcome="waiting")],
    )
    proposed, prompts = sweep_inactive_members(cfg, [], NOW)

    assert statuses(proposed)["Anonymous"] == "active"
    assert prompts == []


def test_a_member_the_board_is_arguing_about_is_left_alone_too() -> None:
    """A deferred nomination with a standing objection is not a settled one.

    `board.ts::isUnsettled` has always read it that way -- it refuses a second
    nomination for the candidate until the objection is withdrawn -- but this
    sweep mirrored the narrower `isPending` and read only the outcome. A
    member seated years ago, nominated again and deferred over a written
    objection, could therefore be proposed inactive by the nightly job out of
    the very file that recorded the objection: two contradictory papers about
    one person, in front of the same annual meeting. The pair is pinned by
    `fixtures/governance-cases.json::unsettled_nomination_cases`.
    """
    cfg = config(
        inactivity_months=6,
        board=with_three_recent(board_member(joined_on="2019-05-04")),
        nominations=[
            nomination(
                candidate="Anonymous",
                outcome="deferred",
                objections=[
                    {
                        "member": "grace",
                        "reason": "I want to hear from them at the meeting.",
                        "date": "2026-02-03",
                    }
                ],
            )
        ],
    )
    proposed, prompts = sweep_inactive_members(cfg, [], NOW)

    assert statuses(proposed)["Anonymous"] == "active"
    assert prompts == []


def test_a_deferral_nobody_still_objects_to_does_not_shield_a_member() -> None:
    """The other side of the same rule, and the reason it is not just
    "deferred is unsettled": an objection that has been withdrawn is removed,
    not flagged, so a `deferred` carrying none is a question with nothing left
    to answer. Shielding on the outcome alone would let a hand-edited word in
    `config.yml` put a member permanently beyond the inactivity rule."""
    cfg = config(
        inactivity_months=6,
        board=with_three_recent(board_member(joined_on="2019-05-04")),
        nominations=[nomination(candidate="Anonymous", outcome="deferred")],
    )
    proposed, prompts = sweep_inactive_members(cfg, [], NOW)

    assert statuses(proposed)["Anonymous"] == "inactive"
    assert len(prompts) == 1


def test_an_already_inactive_member_is_never_proposed_twice() -> None:
    cfg = config(
        inactivity_months=6,
        board=[
            board_member(login="Anonymous", joined_on="2019-05-04", status="inactive"),
            board_member(login="grace"),
            board_member(login="ada"),
            board_member(login="hopper"),
        ],
    )
    speakers = [voted(login, "2026-08-01") for login in ("grace", "ada", "hopper")]
    proposed, prompts = sweep_inactive_members(cfg, speakers, NOW)

    assert prompts == []
    assert statuses(proposed)["Anonymous"] == "inactive"


def test_a_login_listed_twice_is_one_person_and_moves_as_one() -> None:
    cfg = config(
        inactivity_months=6,
        board=[
            board_member(login="Anonymous", joined_on="2019-05-04"),
            board_member(login="Anonymous", joined_on="2019-05-04"),
            board_member(login="grace"),
            board_member(login="ada"),
            board_member(login="hopper"),
        ],
    )
    speakers = [voted(login, "2026-08-01") for login in ("grace", "ada", "hopper")]
    proposed, prompts = sweep_inactive_members(cfg, speakers, NOW)

    assert [m["status"] for m in proposed["board"]] == [
        "inactive",
        "inactive",
        "active",
        "active",
        "active",
    ]
    assert len(prompts) == 1


def test_the_proposal_leaves_an_accepted_nomination_still_valid() -> None:
    # A member seated by nomination who later goes quiet: the acceptance and
    # the inactive seat must be able to coexist, or the rule could never touch
    # anyone the board itself admitted.
    cfg = config(
        inactivity_months=6,
        board=[
            board_member(login="Anonymous"),
            board_member(login="grace", joined_on="2019-05-04"),
            board_member(login="ada"),
            board_member(login="hopper"),
        ],
        nominations=[nomination(candidate="grace", outcome="accepted")],
    )
    speakers = [voted(login, "2026-08-01") for login in ("Anonymous", "ada", "hopper")]
    proposed, prompts = sweep_inactive_members(cfg, speakers, NOW)

    assert statuses(proposed)["grace"] == "inactive"
    assert prompts
    assert validate_config(proposed) == []


# --------------------------------------------------------------- #
# The board that is already wrong
# --------------------------------------------------------------- #


def test_the_rule_stops_before_the_board_can_no_longer_decide_anything() -> None:
    cfg = config(
        inactivity_months=6,
        board=[
            board_member(login="Anonymous", joined_on="2019-01-01"),
            board_member(login="grace", joined_on="2019-02-01"),
            board_member(login="ada", joined_on="2019-03-01"),
            board_member(login="hopper", joined_on="2026-08-01"),
        ],
    )
    proposed, prompts = sweep_inactive_members(cfg, [], NOW)

    # Longest silence first, and only until MINIMUM_ELIGIBLE remain.
    assert statuses(proposed) == {
        "Anonymous": "inactive",
        "grace": "active",
        "ada": "active",
        "hopper": "active",
    }
    assert len(active_board(proposed, "2026-08-18")[0]) == MINIMUM_ELIGIBLE
    held_back = [line for line in prompts if "not proposed" in line]
    assert [line.split(":")[0] for line in held_back] == ["grace", "ada"]
    assert "a vote needs" in held_back[0]


def test_a_board_already_at_the_floor_moves_nobody() -> None:
    cfg = config(
        inactivity_months=6,
        board=[
            board_member(login="Anonymous", joined_on="2019-01-01"),
            board_member(login="grace", joined_on="2019-02-01"),
            board_member(login="ada", joined_on="2019-03-01"),
        ],
    )
    proposed, prompts = sweep_inactive_members(cfg, [], NOW)

    assert set(statuses(proposed).values()) == {"active"}
    assert len(prompts) == 3
    assert all("not proposed" in line for line in prompts)


def test_the_live_config_proposes_nobody_while_joined_on_is_blank() -> None:
    # data/config.yml as it stands: five entries for four people, no joined_on
    # anywhere. A rule that guessed a start date would shrink a board that is
    # already mis-declared.
    cfg = config(
        inactivity_months=6,
        board_min=5,
        board=[
            board_member(login=login, joined_on="")
            for login in ("Anonymous", "Anonymous", "Anonymous", "Anonymous", "Anonymous")
        ],
    )
    proposed, prompts = sweep_inactive_members(cfg, [], NOW)

    assert set(statuses(proposed).values()) == {"active"}
    assert prompts == []


def test_board_min_is_not_what_holds_the_rule_back() -> None:
    # `board_min` is a target and this rule is keyed on `MINIMUM_ELIGIBLE`
    # instead, so a board declared larger than it is does not switch the rule
    # off: a target the board has not reached is not a reason to keep counting
    # a member who has stopped voting, and a target below what a vote needs
    # would be a licence to strip the board of the members it needs.
    cfg = config(
        inactivity_months=6,
        board_min=5,
        board=[
            board_member(login="Anonymous", joined_on="2019-01-01"),
            board_member(login="grace"),
            board_member(login="ada"),
            board_member(login="hopper"),
        ],
    )
    speakers = [voted(login, "2026-08-01") for login in ("grace", "ada", "hopper")]
    proposed, _ = sweep_inactive_members(cfg, speakers, NOW)

    assert statuses(proposed)["Anonymous"] == "inactive"


# --------------------------------------------------------------- #
# Reads its arguments, and only its arguments
# --------------------------------------------------------------- #


def test_the_transformation_never_touches_the_config_it_was_given() -> None:
    cfg = config(
        inactivity_months=6,
        board=[
            board_member(login="Anonymous", joined_on="2019-05-04"),
            board_member(login="grace"),
            board_member(login="ada"),
            board_member(login="hopper"),
        ],
    )
    speakers = [voted(login, "2026-08-01") for login in ("grace", "ada", "hopper")]
    before = copy.deepcopy(cfg)

    proposed, _ = sweep_inactive_members(cfg, speakers, NOW)
    assert cfg == before

    # And the result is detached: editing it cannot reach back into the input.
    proposed["board"][1]["status"] = "inactive"
    assert cfg == before


def test_the_answer_follows_the_config_passed_in_not_one_read_earlier() -> None:
    # The Python twin of task 11's "the transform must read its `current`
    # argument": call twice with two different configs and the two answers must
    # differ, so no threshold or board can have been captured from the first.
    speakers = [voted("grace", "2026-08-01"), voted("ada", "2026-08-01")]
    board = [
        board_member(login="Anonymous", joined_on="2026-05-01"),
        board_member(login="grace"),
        board_member(login="ada"),
        board_member(login="hopper", joined_on="2026-08-01"),
    ]
    lenient, no_prompts = sweep_inactive_members(
        config(inactivity_months=6, board=board), speakers, NOW
    )
    strict, prompts = sweep_inactive_members(
        config(inactivity_months=1, board=board), speakers, NOW
    )

    assert no_prompts == []
    assert statuses(lenient)["Anonymous"] == "active"
    assert statuses(strict)["Anonymous"] == "inactive"
    assert prompts


# --------------------------------------------------------------- #
# Degradation on data this job reads unattended
# --------------------------------------------------------------- #


@pytest.mark.parametrize("value", [None, 0, -3, True, "6", 1.5])
def test_an_unusable_threshold_proposes_nobody(value: Any) -> None:
    assert _inactivity_months({"inactivity_months": value}) is None
    cfg = config(
        inactivity_months=value,
        board=[
            board_member(login="Anonymous", joined_on="2019-05-04"),
            board_member(login="grace"),
            board_member(login="ada"),
            board_member(login="hopper"),
        ],
    )
    proposed, prompts = sweep_inactive_members(cfg, [], NOW)
    assert set(statuses(proposed).values()) == {"active"}
    assert prompts == []


def test_a_missing_threshold_key_proposes_nobody() -> None:
    cfg = config()
    del cfg["inactivity_months"]
    _, prompts = sweep_inactive_members(cfg, [], NOW)
    assert prompts == []


def test_malformed_repository_data_degrades_to_saying_nothing() -> None:
    assert sweep_inactive_members("not a config", [], NOW) == ({}, [])  # type: ignore[arg-type]
    assert sweep_inactive_members(config(board="not a list"), [], NOW)[1] == []
    cfg = config(
        inactivity_months=6,
        board=[None, {"login": 3, "status": "active"}, {"status": "active"}],
        nominations="not a list",
    )
    assert sweep_inactive_members(cfg, "not a list", NOW)[1] == []  # type: ignore[arg-type]


def test_a_joined_on_that_is_not_a_date_supports_no_proposal() -> None:
    cfg = config(
        inactivity_months=6,
        board=[
            board_member(login="Anonymous", joined_on="04/05/2019"),
            board_member(login="grace"),
            board_member(login="ada"),
            board_member(login="hopper"),
        ],
    )
    speakers = [voted(login, "2026-08-01") for login in ("grace", "ada", "hopper")]
    proposed, prompts = sweep_inactive_members(cfg, speakers, NOW)

    assert statuses(proposed)["Anonymous"] == "active"
    assert prompts == []


# --------------------------------------------------------------- #
# Calendar arithmetic
# --------------------------------------------------------------- #


def test_months_are_calendar_months_clamped_to_the_shorter_month() -> None:
    from datetime import date

    assert _months_before(date(2026, 8, 18), 6) == date(2026, 2, 18)
    assert _months_before(date(2026, 8, 31), 6) == date(2026, 2, 28)
    assert _months_before(date(2024, 8, 29), 6) == date(2024, 2, 29)
    assert _months_before(date(2026, 3, 15), 6) == date(2025, 9, 15)
    assert _months_before(date(2026, 1, 31), 1) == date(2025, 12, 31)
    assert _months_before(date(2026, 1, 1), 12) == date(2025, 1, 1)


def test_an_absurd_threshold_reaches_the_start_of_the_calendar_not_a_crash() -> None:
    from datetime import date

    assert _months_before(date(2026, 8, 18), 12 * 5000) == date.min
