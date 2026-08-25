"""The v3 -> v4 migration (scripts/migrate_v4.py).

The transformations are pure and tested here before they are ever pointed
at `data/`, because the file they rewrite holds 31 real people's names,
e-mail addresses, affiliations and abstracts. Three properties matter more
than the rest:

* nothing outside the five new fields is touched -- pinned field by field on
  a realistic record rather than on a minimal one;
* a field that is already there keeps what it has, never an empty default;
* the migration is idempotent -- a second run is a no-op down to the byte,
  which is the only thing standing between an accidental re-run and 31
  blanked biographies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import EDITIONS
from migrate_v4 import (
    NEW_FIELDS,
    _ascii,
    main,
    migrate_speaker,
    migrate_speakers,
)

from convener_ops.cli import SPEAKERS_HEADER, dump_speakers
from convener_ops.validate import validate_speakers


def v3_speaker(**overrides: Any) -> dict[str, Any]:
    """A speaker in the shape `data/speakers.yml` actually has before this
    migration -- same keys, same order, values shortened."""
    base: dict[str, Any] = {
        "id": "spk-001",
        "name": "Anonymous",
        "gender": "undisclosed",
        "career_stage": "undisclosed",
        "email": "Anonymous@example.ac.uk",
        "affiliation": "University of Example",
        "country": "UK",
        "title": "depressive-like behaviours in rodents",
        "abstract": "",
        "conflicts_of_interest": "",
        "source": "organizer",
        "proposed_by": "Anonymous",
        "assigned_to": "",
        "links": [],
        "host_1": "Anonymous",
        "host_2": "",
        "status": "delivered",
        "selection": {
            "ballots": [
                {
                    "voter": "Anonymous",
                    "value": "yes",
                    "comment": "",
                    "coi_reason": "",
                    "date": "",
                }
            ],
            "opened_on": "",
            "decided_on": "",
        },
        "publication": {
            "consent": "pending",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "",
        },
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


# --- what is added --------------------------------------------------------


def test_the_four_text_fields_are_added_empty() -> None:
    migrated = migrate_speaker(v3_speaker())
    for field in ("photo_url", "bio", "linkedin", "seed_questions"):
        assert migrated[field] == "", field


def test_candidate_dates_is_added_as_an_empty_list() -> None:
    assert migrate_speaker(v3_speaker())["candidate_dates"] == []


def test_each_speaker_gets_its_own_candidate_dates_list() -> None:
    # A shared mutable default would give every record the same object, and
    # one later edit would silently appear in all 31 of them.
    first, second = migrate_speakers([v3_speaker(), v3_speaker(id="spk-002")])
    first["candidate_dates"].append({"date": "", "time": "", "answer": ""})
    assert second["candidate_dates"] == []


def test_the_checklist_is_added_empty() -> None:
    # Empty is the whole of it. A line nobody is down for is the hosts', which
    # is exactly what every line meant before this field existed, so the
    # migration preserves today's behaviour rather than guessing at an owner.
    assert migrate_speaker(v3_speaker())["checklist"] == {}


def test_the_checklist_is_never_filled_in_from_the_lead_owner() -> None:
    # `assigned_to` is the board member who owns the lead; an item owner is
    # who owes one line of the runbook. Two notions, two fields, and the
    # migration derives neither from the other -- the phase 2 defect that lost
    # `proposed_by` started as exactly this kind of convenience.
    migrated = migrate_speaker(v3_speaker(assigned_to="Anonymous", host_1="Anonymous"))
    assert migrated["checklist"] == {}
    assert migrated["assigned_to"] == "Anonymous"


def test_each_speaker_gets_its_own_checklist() -> None:
    first, second = migrate_speakers([v3_speaker(), v3_speaker(id="spk-002")])
    first["checklist"]["scheduled/T-30/visuals"] = {"assignee": "Anonymous"}
    assert second["checklist"] == {}


def test_consent_is_not_touched() -> None:
    # Asking the 31 speakers for their consent is a human act; the migration
    # has no business deciding it, not even for a speaker who never delivered.
    for consent in ("", "pending", "granted", "refused"):
        speaker = v3_speaker()
        speaker["publication"] = {**speaker["publication"], "consent": consent}
        assert migrate_speaker(speaker)["publication"]["consent"] == consent


# --- what is not touched --------------------------------------------------


def test_no_field_outside_the_migration_is_touched() -> None:
    before = v3_speaker()
    migrated = migrate_speaker(before)
    for key, value in before.items():
        assert migrated[key] == value, key
    assert set(migrated) - set(before) == set(NEW_FIELDS)


def test_an_existing_value_is_never_overwritten() -> None:
    before = v3_speaker(
        photo_url="https://example.org/Anonymous.jpg",
        bio="Reads rodents for a living.",
        linkedin="Anonymous-Anonymous",
        seed_questions="What first drew you to the model?",
        candidate_dates=[{"date": "2026-06-01", "time": "12:30", "answer": ""}],
        # A name already put against a line of the runbook. The migration
        # must not read it as an absence and blank it: `assignee` is who owes
        # that line, and it is not derived from anything -- least of all from
        # `assigned_to`, which is who owns the lead.
        checklist={"scheduled/T-30/visuals": {"assignee": "Anonymous"}},
    )
    migrated = migrate_speaker(before)
    for field in NEW_FIELDS:
        assert migrated[field] == before[field], field


def test_a_partially_migrated_record_gains_only_what_it_lacks() -> None:
    before = v3_speaker(bio="Already written.")
    migrated = migrate_speaker(before)
    assert migrated["bio"] == "Already written."
    assert migrated["photo_url"] == ""


def test_an_existing_empty_string_is_not_added_a_second_time() -> None:
    # An empty value is an answer, not an absence: it keeps its own place.
    before = v3_speaker(bio="")
    keys = list(migrate_speaker(before))
    assert keys.count("bio") == 1


def test_the_migrated_keys_keep_the_order_of_the_type() -> None:
    # The file is read by hand and reviewed as a diff: new keys sit beside
    # the field they belong with, so the diff reads as added lines.
    keys = list(migrate_speaker(v3_speaker()))
    assert keys.index("photo_url") == keys.index("country") + 1
    assert keys.index("bio") == keys.index("photo_url") + 1
    assert keys.index("linkedin") == keys.index("bio") + 1
    assert keys.index("seed_questions") == keys.index("abstract") + 1
    assert keys.index("candidate_dates") == keys.index("edition_code") + 1
    # Who owes each line sits directly after whether each line is done: the
    # two are read together on every screen that shows a journey.
    assert keys.index("checklist") == keys.index("runbook_progress") + 1


def test_a_speaker_missing_the_usual_anchors_still_gains_every_field() -> None:
    migrated = migrate_speaker({"id": "spk-999", "name": "X", "status": "lead"})
    assert set(migrated) - {"id", "name", "status"} == set(NEW_FIELDS)


def test_a_non_mapping_entry_is_passed_through_untouched() -> None:
    assert migrate_speakers(["not a mapping"]) == ["not a mapping"]


# --- idempotence ----------------------------------------------------------


def test_migrating_twice_changes_nothing() -> None:
    once = migrate_speakers([v3_speaker()])
    twice = migrate_speakers(once)
    assert twice == once


def test_migrating_twice_produces_the_same_bytes() -> None:
    # The property that matters is about the file, not about the dict: the
    # serialised form of a second run must be byte-identical to the first.
    once = dump_speakers(migrate_speakers([v3_speaker()]))
    twice = dump_speakers(migrate_speakers(yaml.safe_load(once)))
    assert twice == once


def test_a_re_run_does_not_blank_a_field_someone_filled_in_since() -> None:
    once = migrate_speakers([v3_speaker()])
    once[0]["bio"] = "Written by a volunteer after the migration."
    once[0]["candidate_dates"] = [
        {"date": "2026-06-01", "time": "12:30", "answer": "accepted"}
    ]
    once[0]["checklist"] = {"scheduled/T-30/visuals": {"assignee": "Anonymous"}}
    twice = migrate_speakers(once)
    assert twice[0]["bio"] == "Written by a volunteer after the migration."
    assert twice[0]["candidate_dates"][0]["answer"] == "accepted"
    assert twice[0]["checklist"] == {"scheduled/T-30/visuals": {"assignee": "Anonymous"}}


# --- the migration against the validator ----------------------------------


def test_the_migrated_data_passes_the_validator() -> None:
    """The validator now also requires `survey_enabled` (task 16, schema
    v5), which this migration does not add -- `test_migrate_v3.py`'s own
    `test_the_migrated_data_passes_the_validator` names that gap
    exhaustively at every stage; this one only needs the fact that it
    exists, so a record freshly migrated to v4 alone is expected to still
    be missing it here."""
    speakers = migrate_speakers(
        [
            v3_speaker(),
            v3_speaker(id="spk-002", status="lead", edition_code="", date=""),
        ]
    )
    assert validate_speakers(speakers, {"Anonymous"}, editions=EDITIONS) == [
        "speakers[0] (spk-001): missing survey_enabled",
        "speakers[1] (spk-002): missing survey_enabled",
    ]


# --- the script as it is actually run -------------------------------------


def _write(tmp_path: Path, speakers: list[dict[str, Any]]) -> Path:
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    path = data / "speakers.yml"
    path.write_text(yaml.safe_dump(speakers, sort_keys=False), encoding="utf-8")
    return path


def test_main_writes_the_file_and_a_second_run_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, [v3_speaker()])
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main([]) == 0
    written = path.read_text(encoding="utf-8")
    assert written.startswith(SPEAKERS_HEADER)
    assert "candidate_dates: []" in written

    assert main([]) == 0
    assert path.read_text(encoding="utf-8") == written
    assert "already migrated" in capsys.readouterr().out


def test_a_dry_run_prints_the_diff_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, [v3_speaker(name="Andre Anonymous Anonymous")])
    before = path.read_text(encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "+  photo_url: ''" in out
    assert "+  candidate_dates: []" in out
    assert "-  name:" not in out
    assert "nothing written" in out
    assert path.read_text(encoding="utf-8") == before


def test_the_dry_run_prints_nothing_a_windows_console_cannot_render() -> None:
    # The operator reads this diff on a console that renders non-ASCII as
    # mojibake, and it is a diff of records about real people: an escaped
    # name still shows a change, a mojibake one hides it.
    printed = _ascii("affiliation: Universite du Quebec a Montrealé")
    assert printed.isascii()
    assert r"\xe9" in printed
