"""The JS/Python file-format boundary (decision D-14).

`app/tests/yaml.test.ts` writes `fixtures/speakers-from-app.yml` and
`fixtures/config-from-app.yml` from `serializeSpeakers` / `serializeConfig`
and asserts they are byte-for-byte the files checked in here. This module is
the other half: it loads those same bytes with this package's loader, writes
them back out with this package's writer, and asserts nothing moved.

That is the whole point of the fixture. Two suites that each merely *parse*
without error prove only that both languages can read the file; they say
nothing about the two writing it the same way, and three of the four
cross-language defects this project has actually hit were exactly that --
`time: 12:30` read back as the integer 750, `to_lead` still writing a
superseded shape, `assigned_to` overwritten. A byte comparison catches the
whole class at once.

The two fixtures are read against each other, not in isolation: the board in
`config-from-app.yml` is the board `speakers-from-app.yml`'s ballots are
validated against, so a login added on one side without the other fails here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from convener_ops.cli import CONFIG_HEADER, SPEAKERS_HEADER, dump_config, dump_speakers
from convener_ops.validate import validate_config, validate_speakers
from convener_ops.yaml_safe import safe_load

FIXTURES = Path(__file__).parent / "fixtures"
SPEAKERS_FIXTURE = FIXTURES / "speakers-from-app.yml"
CONFIG_FIXTURE = FIXTURES / "config-from-app.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _speakers() -> list[dict[str, Any]]:
    loaded = safe_load(_text(SPEAKERS_FIXTURE))
    assert isinstance(loaded, list)
    return loaded


def _config() -> dict[str, Any]:
    loaded = safe_load(_text(CONFIG_FIXTURE))
    assert isinstance(loaded, dict)
    return loaded


def _board_logins() -> list[str]:
    return [member["login"] for member in _config()["board"]]


def test_speakers_fixture_survives_a_python_rewrite_byte_for_byte() -> None:
    """The round-trip: browser writes, Python reads and writes back.

    A single field either side formats differently -- a quote, an
    indentation, a block scalar -- shows up here as a diff, before it shows
    up in `data/speakers.yml` as a whole-file rewrite by whichever side
    saved last.
    """
    assert dump_speakers(_speakers()) == _text(SPEAKERS_FIXTURE)


def test_config_fixture_survives_a_python_rewrite_byte_for_byte() -> None:
    assert dump_config(_config()) == _text(CONFIG_FIXTURE)


def test_both_fixtures_carry_the_header_the_two_languages_agree_on() -> None:
    assert _text(SPEAKERS_FIXTURE).startswith(SPEAKERS_HEADER)
    assert _text(CONFIG_FIXTURE).startswith(CONFIG_HEADER)


def test_the_validator_accepts_what_the_browser_actually_writes() -> None:
    assert validate_config(_config()) == []
    assert validate_speakers(_speakers(), _board_logins()) == []


@pytest.mark.parametrize(
    ("index", "expected"),
    [(0, "12:30"), (2, "09:05")],
)
def test_a_bare_time_stays_text_and_never_becomes_a_sexagesimal_int(
    index: int, expected: str
) -> None:
    """`12:30` as the integer 750 is the defect this fixture was born from.

    `09:05` is its neighbour: PyYAML's own int resolver would have left that
    one alone (it requires 1-9 as the first digit), and it is here so the
    agreement is about the bytes rather than about which times happen to be
    dangerous.
    """
    time = _speakers()[index]["time"]
    assert isinstance(time, str)
    assert time == expected
    assert f"time: '{expected}'" in _text(SPEAKERS_FIXTURE)


def test_dates_stay_text_and_never_become_date_objects() -> None:
    speakers = _speakers()
    assert speakers[0]["date"] == "2026-06-01"
    assert isinstance(speakers[0]["date"], str)
    assert isinstance(speakers[0]["selection"]["opened_on"], str)
    assert isinstance(_config()["board"][0]["joined_on"], str)


def test_a_yes_ballot_is_the_string_and_not_the_boolean_true() -> None:
    values = [b["value"] for b in _speakers()[0]["selection"]["ballots"]]
    assert values == ["yes", "abstain", "recused", "yes"]


def test_text_that_looks_like_a_boolean_or_a_number_stays_text() -> None:
    odd = _speakers()[2]
    assert odd["title"] == "yes"
    assert odd["country"] == "NO"
    assert odd["proposed_by"] == "on"
    assert odd["affiliation"] == "0123"
    assert odd["notes"] == "3.14"
    assert odd["name"] == "True"
    assert odd["abstract"] == "null"
    for key in ("title", "country", "proposed_by", "affiliation", "notes", "name"):
        assert isinstance(odd[key], str), key
    assert odd["selection"]["ballots"][0]["comment"] == "~"


def test_an_empty_string_is_kept_as_an_empty_string_not_as_none() -> None:
    """Empty and absent are different facts, and only one of them is here.

    Every string on `spk-102` is `''` -- including `assigned_to`, a login
    that is legitimately empty until `assignLead` names someone. Read as
    `None`, an empty `assigned_to` would still be falsy and nothing would
    notice; an empty `host_1` read as `None` would reach the digest as the
    word "None". A file with the keys *missing* is a different question,
    covered by `test_hand_edited.py`.
    """
    blank = _speakers()[1]
    for key in ("assigned_to", "proposed_by", "host_1", "host_2", "date", "time"):
        assert blank[key] == ""
        assert isinstance(blank[key], str)
    assert blank["publication"]["consent"] == ""
    assert blank["links"] == []
    assert blank["runbook_progress"] == {}
    assert blank["checklist"] == {}
    assert blank["selection"]["ballots"] == []


def test_a_recorded_zero_is_not_a_metric_nobody_filled_in() -> None:
    full, blank, _ = _speakers()
    assert full["metrics"]["registrations"] == 0
    assert blank["metrics"]["registrations"] is None


def test_accented_characters_survive_the_crossing_unescaped() -> None:
    full = _speakers()[0]
    assert full["name"] == "Bénédicte Ångström"
    assert full["proposed_by"] == "Émilie Dupré"
    assert full["affiliation"] == "Université de Genève"
    assert full["selection"]["ballots"][0]["comment"].endswith("nôtre.")
    # Written as the characters themselves, not as \uXXXX escapes: a board
    # member reading the diff on GitHub has to recognise the name.
    assert "Bénédicte" in _text(SPEAKERS_FIXTURE)


def test_proposed_by_and_assigned_to_are_two_fields_and_stay_two() -> None:
    """The defect that overwrote one with the other, pinned.

    `proposed_by` is the submitter's self-reported name -- not a login, not
    checked against the board. `assigned_to` is the board member handling
    the follow-up. On `spk-101` they differ, so a writer that merged them
    could not produce this file.
    """
    full = _speakers()[0]
    assert full["proposed_by"] == "Émilie Dupré"
    assert full["assigned_to"] == "alice"
    assert full["assigned_to"] in _board_logins()
    assert full["proposed_by"] not in _board_logins()


def test_the_item_owner_and_the_lead_owner_cross_as_two_separate_fields() -> None:
    """The same defect one grain further down, pinned before it happens.

    `assigned_to` is who owns the *lead*; `checklist[...]["assignee"]` is who
    owes *one line of the runbook*. On `spk-103` they hold different logins,
    so a writer -- on either side -- that derived one from the other could not
    produce this file. `spk-101` carries an owner that is the empty string,
    which is legal and means the same as no entry: nobody in particular.
    """
    full, blank, odd = _speakers()
    assert odd["assigned_to"] == "bob"
    assert odd["checklist"] == {"scheduled/T-21/linkedin": {"assignee": "erin"}}
    assert full["checklist"]["scheduled/T-30/visuals"]["assignee"] == "ada"
    assert full["checklist"]["delivered/forum-summary"]["assignee"] == ""
    # A block map inside a block map, whose keys carry slashes: the one shape
    # in the model nothing else has, and the indentation both writers have to
    # agree on.
    assert "\n".join(
        ("  checklist:", "    scheduled/T-30/visuals:", "      assignee: ada")
    ) in _text(SPEAKERS_FIXTURE)
    assert blank["checklist"] == {}


def test_a_multi_line_abstract_is_written_as_a_literal_block_by_both_sides() -> None:
    """The one shape whose formatting the two writers disagreed on.

    js-yaml writes `|-`; PyYAML's default is a quoted scalar with the breaks
    folded through blank lines. Same text either way, different bytes -- so
    an abstract typed into the browser form was rewritten by the next sweep,
    and back again by the next save.
    """
    assert "abstract: |-\n" in _text(SPEAKERS_FIXTURE)
    assert _speakers()[0]["abstract"] == (
        "First paragraph of the abstract.\nSecond paragraph, after a break."
    )


def test_a_multi_line_bio_is_written_as_a_literal_block_too() -> None:
    """The same disagreement, on the field it would next have shown up on.

    A biography is the one new field a speaker writes at length, so it is
    the one that would have been rewritten by whichever side saved last.
    Pinned here rather than left to the abstract, which is the field the
    two writers happened to be compared on first.
    """
    assert "bio: |-\n" in _text(SPEAKERS_FIXTURE)
    assert _speakers()[0]["bio"] == (
        "Directrice de recherche à Genève.\nElle étudie le campagnol depuis 2011."
    )


def test_an_apostrophe_and_an_accent_cross_together() -> None:
    """`seed_questions` is free text a speaker typed, in their own language.

    The apostrophe is what decides between a plain and a quoted scalar and
    the accent is what decides between the character and an escape; both
    writers have to make both calls the same way, which is what the byte
    comparison above is asserting and what this reads back.
    """
    questions = _speakers()[0]["seed_questions"]
    assert questions.startswith("Qu'est-ce")
    assert "modèle" in questions
    assert "élevage" in questions.lower()
    # As the characters themselves, not as \\uXXXX escapes.
    assert "Qu'est-ce" in _text(SPEAKERS_FIXTURE)


def test_the_proposed_slots_cross_as_a_block_sequence_of_mappings() -> None:
    """A list of mappings nested under a speaker: one level deeper than any
    list this fixture carried before, and the shape `noArrayIndent` governs.

    The hours are quoted for the same reason `time` is: `09:05` and `12:30`
    are text, and a slot read back as the integer 750 would be proposed to
    nobody.
    """
    slots = _speakers()[0]["candidate_dates"]
    assert slots == [
        {"date": "2026-05-18", "time": "12:30", "answer": "declined"},
        {"date": "2026-06-01", "time": "12:30", "answer": "accepted"},
        {"date": "2026-06-15", "time": "09:05", "answer": ""},
    ]
    assert all(isinstance(slot["time"], str) for slot in slots)
    text = _text(SPEAKERS_FIXTURE)
    assert "candidate_dates:\n  - date: '2026-05-18'\n" in text
    # No answer at all is the empty answer, written out rather than left out.
    assert "answer: ''\n" in text
    assert _speakers()[1]["candidate_dates"] == []


def test_a_seed_question_that_reads_like_a_time_is_still_text() -> None:
    assert _speakers()[2]["seed_questions"] == "12:30"


def test_the_speaker_fixture_carries_the_whole_governance_record() -> None:
    """Guards against the fixture being trimmed back to a shape neither side
    would accept in practice: without ballots, a publication with objections
    and a career stage, this file would pin almost nothing."""
    full = _speakers()[0]
    assert full["career_stage"] == "group-leader"
    assert len(full["selection"]["ballots"]) == 4
    assert full["selection"]["ballots"][2]["coi_reason"] != ""
    assert full["publication"]["consent"] == "granted"
    objections = full["publication"]["objections"]
    assert len(objections) == 2
    assert objections[0]["resolved_on"] == "2026-06-12"
    # A standing objection is one with no resolution date, not one flagged.
    assert objections[1]["resolved_on"] == ""


def test_the_config_fixture_carries_every_window_the_two_languages_read() -> None:
    cfg = _config()
    for key in (
        "season",
        "vw_counter",
        "overlap_window_days",
        "seminar_duration_minutes",
        "board_min",
        "board_max",
        "vote_window_days",
        "objection_window_working_days",
        "inactivity_months",
        "balance_window_months",
        "view_count_window_days",
    ):
        assert isinstance(cfg[key], int), key
    # Three, not four: the board's decision deadline is `vote_window_days`
    # above, checked as an integer with the rest (F-13).
    assert set(cfg["sla_days"]) == {
        "invitation_follow_up",
        "summary_after_delivery",
        "recording_after_delivery",
    }


def test_the_config_fixture_carries_board_records_and_nominations() -> None:
    cfg = _config()
    assert [m["status"] for m in cfg["board"]] == [
        "active",
        "active",
        "active",
        "active",
        "inactive",
    ]
    assert cfg["board"][1]["unavailable_until"] == "2026-09-01"
    assert [n["outcome"] for n in cfg["nominations"]] == [
        "deferred",
        "waiting",
        "accepted",
    ]
    # A nomination objection is {member, reason, date} -- no `resolved_on`,
    # unlike a publication objection. The two shapes are both in the
    # fixture, and they are not the same shape.
    deferred = cfg["nominations"][0]["objections"][0]
    assert set(deferred) == {"member", "reason", "date"}
