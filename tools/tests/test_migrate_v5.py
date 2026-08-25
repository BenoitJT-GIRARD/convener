"""The v4 -> v5 migration (scripts/migrate_v5.py).

Schema v5 adds one field, `survey_enabled` (task 16, phase 4 spec S:6).
This mirrors test_migrate_v4.py's own shape, cut down to one field: the
transformation is pure and tested here before it is ever pointed at
`data/`, because the file it rewrites holds 31 real people's records.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import EDITIONS
from migrate_v5 import NEW_FIELDS, _ascii, main, migrate_speaker, migrate_speakers

from convener_ops.cli import SPEAKERS_HEADER, dump_speakers
from convener_ops.validate import validate_speakers


def v4_speaker(**overrides: Any) -> dict[str, Any]:
    """A speaker in the shape `data/speakers.yml` actually has before this
    migration -- same keys, same order, values shortened."""
    base: dict[str, Any] = {
        "id": "spk-001",
        "name": "Alba Quennell",
        "gender": "undisclosed",
        "career_stage": "undisclosed",
        "email": "Anonymous@example.ac.uk",
        "affiliation": "University of Example",
        "country": "UK",
        "photo_url": "",
        "bio": "",
        "linkedin": "",
        "title": "depressive-like behaviours in rodents",
        "abstract": "",
        "seed_questions": "",
        "conflicts_of_interest": "",
        "source": "organizer",
        "proposed_by": "Bram Oosterlin",
        "assigned_to": "",
        "links": [],
        "host_1": "Bram Oosterlin",
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
        "candidate_dates": [],
        "date": "2025-02-05",
        "time": "",
        "zoom_link": "",
        "youtube_url": "",
        "forum_thread": "",
        "runbook_progress": {},
        "checklist": {},
        "metrics": {
            "registrations": None,
            "live_peak": 60,
            "youtube_views_30d": None,
            "forum_replies": None,
        },
        "notes": "second reading: Y",
    }
    base.update(overrides)
    return base


# --- what is added --------------------------------------------------------


def test_survey_enabled_is_added_false() -> None:
    assert migrate_speaker(v4_speaker())["survey_enabled"] is False


def test_no_field_outside_the_migration_is_touched() -> None:
    before = v4_speaker()
    migrated = migrate_speaker(before)
    for key, value in before.items():
        assert migrated[key] == value, key
    assert set(migrated) - set(before) == set(NEW_FIELDS)


def test_an_existing_value_is_never_overwritten() -> None:
    # A re-run must never reset a switch an organiser has since turned on.
    before = v4_speaker(survey_enabled=True)
    migrated = migrate_speaker(before)
    assert migrated["survey_enabled"] is True


def test_the_migrated_keys_keep_the_order_of_the_type() -> None:
    keys = list(migrate_speaker(v4_speaker()))
    assert keys.index("survey_enabled") == keys.index("forum_thread") + 1


def test_a_speaker_missing_the_usual_anchor_still_gains_the_field() -> None:
    migrated = migrate_speaker({"id": "spk-999", "name": "X", "status": "lead"})
    assert set(migrated) - {"id", "name", "status"} == set(NEW_FIELDS)


def test_a_non_mapping_entry_is_passed_through_untouched() -> None:
    assert migrate_speakers(["not a mapping"]) == ["not a mapping"]


# --- idempotence ----------------------------------------------------------


def test_migrating_twice_changes_nothing() -> None:
    once = migrate_speakers([v4_speaker()])
    twice = migrate_speakers(once)
    assert twice == once


def test_migrating_twice_produces_the_same_bytes() -> None:
    once = dump_speakers(migrate_speakers([v4_speaker()]))
    twice = dump_speakers(migrate_speakers(yaml.safe_load(once)))
    assert twice == once


def test_a_re_run_does_not_reset_a_switch_someone_turned_on_since() -> None:
    once = migrate_speakers([v4_speaker()])
    once[0]["survey_enabled"] = True
    twice = migrate_speakers(once)
    assert twice[0]["survey_enabled"] is True


# --- the migration against the validator ----------------------------------


def test_the_migrated_data_passes_the_validator() -> None:
    speakers = migrate_speakers(
        [
            v4_speaker(),
            v4_speaker(id="spk-002", status="lead", edition_code="", date=""),
        ]
    )
    assert validate_speakers(speakers, {"Anonymous"}, editions=EDITIONS) == []


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
    path = _write(tmp_path, [v4_speaker()])
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main([]) == 0
    written = path.read_text(encoding="utf-8")
    assert written.startswith(SPEAKERS_HEADER)
    assert "survey_enabled: false" in written

    assert main([]) == 0
    assert path.read_text(encoding="utf-8") == written
    assert "already migrated" in capsys.readouterr().out


def test_a_dry_run_prints_the_diff_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, [v4_speaker(name="Cyra Adeyemo-Lund")])
    before = path.read_text(encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "+  survey_enabled: false" in out
    assert "-  name:" not in out
    assert "nothing written" in out
    assert path.read_text(encoding="utf-8") == before


def test_the_dry_run_prints_nothing_a_windows_console_cannot_render() -> None:
    printed = _ascii("affiliation: Universite du Quebec a Montrealé")
    assert printed.isascii()
    assert r"\xe9" in printed
