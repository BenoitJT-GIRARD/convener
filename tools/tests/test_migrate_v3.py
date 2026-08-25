"""The v2 -> v3 migration (scripts/migrate_v3.py).

The transformations are pure and tested here before they are ever pointed
at `data/`, because the file they rewrite holds real people's names, e-mail
addresses and affiliations. Two properties matter more than the rest:

* nothing outside the migrated fields is touched -- pinned field by field
  on a realistic record rather than on a minimal one;
* the migration is idempotent -- a second run must not double anybody's
  ballots, which is the one way an accidental re-run could change a vote.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import EDITIONS
from migrate_v3 import (
    _ascii,
    ballot_voters,
    main,
    migrate_config,
    migrate_speaker,
    migrate_speakers,
)
from migrate_v4 import migrate_speakers as migrate_speakers_v4
from migrate_v5 import migrate_speakers as migrate_speakers_v5

from convener_ops.cli import SPEAKERS_HEADER
from convener_ops.validate import validate_config, validate_speakers


def v2_speaker(**overrides: Any) -> dict[str, Any]:
    """A speaker in the shape `data/speakers.yml` actually had before the
    migration -- same keys, same order, values shortened."""
    base: dict[str, Any] = {
        "id": "spk-001",
        "name": "Anonymous",
        "gender": "undisclosed",
        "email": "Anonymous@example.ac.uk",
        "affiliation": "University of Example",
        "country": "UK",
        "title": "depressive-like behaviours in rodents",
        "abstract": "",
        "conflicts_of_interest": "",
        "source": "organizer",
        "proposed_by": "Anonymous",
        "links": [],
        "host_1": "Anonymous",
        "host_2": "",
        "status": "delivered",
        "selection": {"votes_for": ["Anonymous", "Anonymous"], "decided_on": ""},
        "edition_code": "MRG-01",
        "date": "2025-02-05",
        "time": "",
        "zoom_link": "",
        "youtube_url": "",
        "forum_thread": "",
        "runbook_progress": {},
        "metrics": {
            "registrations": None,
            "live_peak": 60,
            "youtube_views_30d": None,
            "forum_replies": None,
        },
        "notes": "TEC review: Y",
    }
    base.update(overrides)
    return base


def v2_config(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "season": 2026,
        "next_edition_number": 5,
        "vote_threshold": 3,
        "overlap_window_days": 7,
        "board_members": ["Anonymous"],
        "seminar_duration_minutes": 90,
    }
    base.update(overrides)
    return base


# --- speakers -------------------------------------------------------------


def test_votes_for_becomes_one_yes_ballot_per_voter() -> None:
    migrated = migrate_speaker(v2_speaker())
    ballots = migrated["selection"]["ballots"]
    assert [b["voter"] for b in ballots] == ["Anonymous", "Anonymous"]
    assert {b["value"] for b in ballots} == {"yes"}
    assert "votes_for" not in migrated["selection"]


def test_a_ballot_takes_its_date_from_decided_on_when_there_is_one() -> None:
    migrated = migrate_speaker(
        v2_speaker(selection={"votes_for": ["Anonymous"], "decided_on": "2025-01-31"})
    )
    assert migrated["selection"]["ballots"][0]["date"] == "2025-01-31"
    assert migrated["selection"]["decided_on"] == "2025-01-31"


def test_a_ballot_has_an_empty_date_when_no_decision_was_recorded() -> None:
    # No date is invented: the v2 file recorded when a vote was decided, and
    # for most leads it recorded nothing at all.
    migrated = migrate_speaker(v2_speaker())
    assert migrated["selection"]["ballots"][0]["date"] == ""
    assert migrated["selection"]["opened_on"] == ""


def test_every_speaker_gains_an_undisclosed_career_stage() -> None:
    assert migrate_speaker(v2_speaker())["career_stage"] == "undisclosed"


def test_a_delivered_speaker_gains_a_pending_publication_consent() -> None:
    # The recording exists, so consent is something to go and ask for.
    for status in ("delivered", "archived"):
        migrated = migrate_speaker(v2_speaker(status=status))
        assert migrated["publication"]["consent"] == "pending"


def test_a_speaker_who_never_delivered_gains_an_empty_consent() -> None:
    for status in ("lead", "invited", "confirmed", "parked"):
        migrated = migrate_speaker(v2_speaker(status=status, edition_code="", date=""))
        assert migrated["publication"]["consent"] == ""


def test_assigned_to_is_added_empty_and_proposed_by_is_left_alone() -> None:
    # Ruling P2-15: proposed_by is the submitter, self-reported and often
    # not a board login at all. The migration adds the owner field beside
    # it; it never derives one from the other.
    migrated = migrate_speaker(v2_speaker())
    assert migrated["assigned_to"] == ""
    assert migrated["proposed_by"] == "Anonymous"


def test_no_field_outside_the_migration_is_touched() -> None:
    before = v2_speaker()
    migrated = migrate_speaker(before)
    added = {"career_stage", "assigned_to", "publication"}
    for key, value in before.items():
        if key == "selection":
            continue
        assert migrated[key] == value, key
    assert set(migrated) - set(before) == added


def test_the_migrated_keys_keep_the_order_of_the_type() -> None:
    # The file is read by hand and reviewed as a diff: new keys sit beside
    # the field they belong with, so the diff reads as added lines.
    keys = list(migrate_speaker(v2_speaker()))
    assert keys.index("career_stage") == keys.index("gender") + 1
    assert keys.index("assigned_to") == keys.index("proposed_by") + 1
    assert keys.index("publication") == keys.index("selection") + 1


def test_a_speaker_missing_the_usual_anchors_still_gains_every_field() -> None:
    migrated = migrate_speaker({"id": "spk-999", "name": "X", "status": "lead"})
    assert migrated["career_stage"] == "undisclosed"
    assert migrated["assigned_to"] == ""
    assert migrated["publication"]["consent"] == ""


def test_a_non_mapping_entry_is_passed_through_untouched() -> None:
    assert migrate_speakers(["not a mapping"]) == ["not a mapping"]


def test_migrating_twice_changes_nothing() -> None:
    once = migrate_speakers([v2_speaker()])
    twice = migrate_speakers(once)
    assert twice == once
    assert len(twice[0]["selection"]["ballots"]) == 2


# --- config ---------------------------------------------------------------


def test_board_members_become_active_members_with_no_joining_date() -> None:
    board = migrate_config(v2_config())["board"]
    assert board[0]["login"] == "Anonymous"
    assert board[0]["status"] == "active"
    assert board[0]["joined_on"] == ""
    assert board[0]["unavailable_until"] == ""
    assert "board_members" not in migrate_config(v2_config())


def test_vote_threshold_is_deleted() -> None:
    # Deleted, not moved: the threshold is computed from the eligible board.
    assert "vote_threshold" not in migrate_config(v2_config())


def test_the_new_configuration_keys_get_their_specified_values() -> None:
    migrated = migrate_config(v2_config())
    assert migrated["vote_window_days"] == 14
    assert migrated["objection_window_working_days"] == 3
    assert migrated["board_min"] == 5
    assert migrated["board_max"] == 9
    assert migrated["balance_window_months"] == 24
    assert migrated["nominations"] == []
    assert migrated["sla_days"]["invitation_follow_up"] == 30
    # No `lead_decision`: the board's deadline is `vote_window_days` (F-13).
    assert "lead_decision" not in migrated["sla_days"]


def test_values_already_set_are_kept() -> None:
    migrated = migrate_config(v2_config(vote_window_days=21))
    assert migrated["vote_window_days"] == 21


def test_people_who_actually_voted_join_the_board() -> None:
    # The v2 file declared one member while four people had been voting.
    # Their ballots have to belong to members, or every one of them is
    # invalid; nothing is merged, since two entries that turn out to be the
    # same person is a decision for the Board, not for a migration.
    migrated = migrate_config(v2_config(), ["Anonymous", "Anonymous"])
    assert [m["login"] for m in migrated["board"]] == ["Anonymous", "Anonymous", "Anonymous"]


def test_a_voter_already_declared_is_not_added_twice() -> None:
    migrated = migrate_config(v2_config(board_members=["Anonymous"]), ["Anonymous"])
    assert [m["login"] for m in migrated["board"]] == ["Anonymous"]


def test_ballot_voters_lists_each_voter_once_in_order_of_appearance() -> None:
    speakers = migrate_speakers(
        [
            v2_speaker(selection={"votes_for": ["Anonymous", "Anonymous"], "decided_on": ""}),
            v2_speaker(
                id="spk-002",
                edition_code="MRG-02",
                selection={"votes_for": ["Anonymous", "Anonymous"], "decided_on": ""},
            ),
        ]
    )
    assert ballot_voters(speakers) == ["Anonymous", "Anonymous", "Anonymous"]


def test_migrating_the_config_twice_changes_nothing() -> None:
    once = migrate_config(v2_config(), ["Anonymous"])
    twice = migrate_config(once, ["Anonymous", "Anonymous"])
    # Not even the second call's extra voter: an already-migrated board is
    # the Board's own record from then on, and no re-run may edit it.
    assert twice == once
    assert [m["login"] for m in twice["board"]] == ["Anonymous", "Anonymous"]


# --- the two halves together ----------------------------------------------


V4_FIELDS = (
    "photo_url",
    "bio",
    "linkedin",
    "seed_questions",
    "candidate_dates",
    "checklist",
)

#: Task 16, schema v5's own single addition -- the same "named exhaustively,
#: not merely tolerated" discipline `V4_FIELDS` above already follows.
V5_FIELDS = ("survey_enabled",)


def test_the_migrated_data_passes_the_validator() -> None:
    """What this one-shot produces is v3, and the validator now reads v5.

    The gap is named rather than tolerated: the errors this asserts are the
    exhaustive list of what schema v4 and schema v5 ask for and the v3
    migration cannot know about -- the six v4 fields that were never in a
    v2 file to migrate, plus v5's own single addition, `survey_enabled`
    (task 16), which did not exist when this migration was written and
    which the validator now requires unconditionally, regardless of which
    schema version a record claims. Anything else the validator finds
    still fails here.

    The gap closes in two steps, not one, and each is named separately:
    `scripts/migrate_v4.py` closes the six v4 fields but leaves
    `survey_enabled` still missing (`expected_v5_gap` below), and
    `scripts/migrate_v5.py` closes that. The third assertion runs all
    three one-shots in the order they were actually run against `data/`
    and asserts the validator then finds nothing at all. Naming each gap
    and naming what closes it is what keeps this assertion exhaustive
    instead of merely tolerant -- a v3 output that grew a further defect
    would still fail here, at every stage.
    """
    expected_v4_gap = sorted(
        f"speakers[{index}] ({sid}): missing {field}"
        for index, sid in enumerate(("spk-001", "spk-002"))
        for field in (*V4_FIELDS, *V5_FIELDS)
    )
    expected_v5_gap = sorted(
        f"speakers[{index}] ({sid}): missing {field}"
        for index, sid in enumerate(("spk-001", "spk-002"))
        for field in V5_FIELDS
    )
    speakers = migrate_speakers(
        [
            v2_speaker(
                selection={
                    "votes_for": ["Anonymous", "Anonymous", "Anonymous", "Anonymous"],
                    "decided_on": "",
                }
            ),
            v2_speaker(id="spk-002", status="lead", edition_code="", date=""),
        ]
    )
    config = migrate_config(v2_config(), ballot_voters(speakers))
    logins = {m["login"] for m in config["board"]}
    assert (
        sorted(validate_speakers(speakers, logins, editions=EDITIONS))
        == expected_v4_gap
    )
    assert (
        sorted(
            validate_speakers(migrate_speakers_v4(speakers), logins, editions=EDITIONS)
        )
        == expected_v5_gap
    )
    # The config has gaps of the same kind, and they are named the same way.
    # The promotion channels are configuration somebody writes, not data a
    # migration can derive: there was nothing in a v2 config to turn into
    # them, and inventing seven here would be this script deciding on the
    # collaborators' behalf what the list holds. `instructions` (phase 4,
    # R-6) is the same story a season later: this migration predates it
    # entirely and has no more business inventing join instructions than it
    # does channels. `eligibility_share` (phase 4 S:5, round 1 review) is a
    # third instance of the identical shape: an accreditation-driven number
    # nobody has decided yet, so `migrate_config` has no more business
    # inventing it than it does the other two. A v3 config that grew any
    # other defect still fails this line.
    assert validate_config(config) == [
        "config.yml: missing keys ['channels', 'eligibility_share', 'instructions']"
    ]
    assert (
        validate_speakers(
            migrate_speakers_v5(migrate_speakers_v4(speakers)),
            logins,
            editions=EDITIONS,
        )
        == []
    )


# --- the script as it is actually run -------------------------------------


def test_main_writes_both_files_and_a_second_run_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    speakers_path = data / "speakers.yml"
    config_path = data / "config.yml"
    speakers_path.write_text(
        yaml.safe_dump([v2_speaker()], sort_keys=False), encoding="utf-8"
    )
    config_path.write_text(
        yaml.safe_dump(v2_config(), sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main([]) == 0
    written = speakers_path.read_text(encoding="utf-8")
    assert written.startswith(SPEAKERS_HEADER)
    assert "ballots:" in written
    assert "votes_for" not in written

    after_first = (written, config_path.read_text(encoding="utf-8"))
    assert main([]) == 0
    assert (
        speakers_path.read_text(encoding="utf-8"),
        config_path.read_text(encoding="utf-8"),
    ) == after_first
    assert "already migrated" in capsys.readouterr().out


def test_a_dry_run_prints_the_diff_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    speakers_path = data / "speakers.yml"
    config_path = data / "config.yml"
    before = yaml.safe_dump([v2_speaker(name="Andre Anonymous Anonymous")], sort_keys=False)
    speakers_path.write_text(before, encoding="utf-8")
    config_path.write_text(
        yaml.safe_dump(v2_config(), sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "+    ballots:" in out
    assert "-    votes_for:" in out
    assert "nothing written" in out
    assert speakers_path.read_text(encoding="utf-8") == before


def test_the_dry_run_prints_nothing_a_windows_console_cannot_render() -> None:
    # The operator reads this diff on a console that renders non-ASCII as
    # mojibake, and it is a diff of records about real people: an escaped
    # name still shows a change, a mojibake one hides it.
    printed = _ascii("affiliation: Universite du Quebec a Montreal\u00e9")
    assert printed.isascii()
    assert r"\xe9" in printed
