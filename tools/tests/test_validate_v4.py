"""Schema v4: the fields the checklists ask for, on the write side.

`app/tests/types-shape.test.ts` is the other half of this module. The two
languages read and write the same file, so a field required by the browser
and merely tolerated here would be a divergence of exactly the class this
project has hit four times -- the app writing what the validator refuses, or
the validator passing what the app then cannot read.

Two properties, stated on both sides:

- **An absent key is a defect.** The record is incomplete, and nothing
  downstream can tell that apart from an answer of "none".
- **An empty value is an answer.** A speaker who gives no biography is a
  speaker with `bio: ''`, and that file is well formed.

Everything here is a whole record from `conftest.speaker()` with one thing
taken away or changed, so a failure names the one thing.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import speaker

from convener_ops.validate import DATE_ANSWERS, SPEAKER_TEXT_V4, validate_speakers

BOARD = frozenset({"Anonymous"})

#: The six fields schema v4 adds, as a volunteer would name them.
NEW_FIELDS = (*SPEAKER_TEXT_V4, "candidate_dates", "checklist")


def _slot(**overrides: Any) -> dict[str, Any]:
    base = {"date": "2026-06-01", "time": "12:30", "answer": ""}
    base.update(overrides)
    return base


def test_a_whole_record_is_accepted() -> None:
    assert validate_speakers([speaker()], BOARD) == []


@pytest.mark.parametrize("field", NEW_FIELDS)
def test_a_record_that_leaves_out_a_new_field_is_reported(field: str) -> None:
    entry = speaker()
    del entry[field]
    errors = validate_speakers([entry], BOARD)
    assert [e for e in errors if f"missing {field}" in e], errors
    # Named by id, so the line points at a record and not at an offset into
    # a 1700-line file.
    assert all("spk-001" in error for error in errors), errors


@pytest.mark.parametrize("field", SPEAKER_TEXT_V4)
def test_an_empty_value_is_an_answer_and_not_a_missing_field(field: str) -> None:
    assert validate_speakers([speaker(**{field: ""})], BOARD) == []


@pytest.mark.parametrize("field", SPEAKER_TEXT_V4)
def test_a_new_field_that_is_not_text_is_reported(field: str) -> None:
    errors = validate_speakers([speaker(**{field: ["a list"]})], BOARD)
    assert [e for e in errors if f"{field} must be a string" in e], errors


def test_every_missing_field_is_listed_at_once() -> None:
    """The operator fixing a file wants the list, not the first line of it.

    The browser stops at the first defect -- it has one reader in front of
    it and no way to show ten sentences -- and this side does not, which is
    the same split phase 2 settled for the hand-edited fixture.
    """
    entry = speaker()
    for field in NEW_FIELDS:
        del entry[field]
    joined = " | ".join(validate_speakers([entry], BOARD))
    for field in NEW_FIELDS:
        assert f"missing {field}" in joined


def test_a_new_field_left_empty_is_not_confused_with_one_left_out() -> None:
    """The distinction itself, stated once in one place.

    `entry.get(key)` reads `''` and an absent key as the same falsy thing.
    Every field below is empty and the record is well formed; the same
    record with the keys removed is not.
    """
    blank = speaker(photo_url="", bio="", linkedin="", seed_questions="")
    assert validate_speakers([blank], BOARD) == []
    stripped = {k: v for k, v in blank.items() if k not in SPEAKER_TEXT_V4}
    assert len(validate_speakers([stripped], BOARD)) == len(SPEAKER_TEXT_V4)


class TestCandidateDates:
    """The slots put to the speaker, and the answers to them."""

    def test_a_well_formed_list_of_slots_is_accepted(self) -> None:
        entry = speaker(
            candidate_dates=[
                _slot(date="2026-06-01", answer="accepted"),
                _slot(date="2026-06-08", time="09:05", answer="declined"),
                _slot(date="2026-06-15", answer=""),
            ]
        )
        assert validate_speakers([entry], BOARD) == []

    def test_an_empty_list_is_a_speaker_nobody_has_written_to_yet(self) -> None:
        assert validate_speakers([speaker(candidate_dates=[])], BOARD) == []

    def test_a_slot_that_is_not_a_list_is_reported(self) -> None:
        entry = speaker(candidate_dates="the 1st or the 8th")
        errors = validate_speakers([entry], BOARD)
        assert any("candidate_dates: must be a list" in e for e in errors), errors

    def test_a_slot_typed_as_one_line_of_prose_is_reported(self) -> None:
        # What a hand edit produces: the day written out instead of a
        # mapping of the three things a slot is.
        entry = speaker(candidate_dates=["Monday the 1st, midday"])
        errors = validate_speakers([entry], BOARD)
        assert any("candidate_dates[0]: not a mapping" in e for e in errors), errors

    @pytest.mark.parametrize("key", ["date", "time", "answer"])
    def test_a_slot_missing_a_key_is_reported_with_that_key(self, key: str) -> None:
        slot = _slot()
        del slot[key]
        errors = validate_speakers([speaker(candidate_dates=[slot])], BOARD)
        assert any(f"missing keys ['{key}']" in e for e in errors), errors

    def test_a_slot_with_no_day_is_not_a_proposal(self) -> None:
        errors = validate_speakers([speaker(candidate_dates=[_slot(date="")])], BOARD)
        assert any("date must be YYYY-MM-DD" in e for e in errors), errors

    def test_a_bare_time_that_yaml_read_as_a_number_is_reported(self) -> None:
        # `12:30` unquoted is the integer 750 under stock resolvers. The
        # loader keeps it text (yaml_safe.py); if a hand edit ever gets one
        # past that, it is caught here rather than compared against a string.
        errors = validate_speakers([speaker(candidate_dates=[_slot(time=750)])], BOARD)
        assert any("time must be HH:MM" in e for e in errors), errors

    def test_there_is_no_word_for_probably(self) -> None:
        assert frozenset({"accepted", "declined", ""}) == DATE_ANSWERS
        assert "pending" not in DATE_ANSWERS
        entry = speaker(candidate_dates=[_slot(answer="maybe")])
        errors = validate_speakers([entry], BOARD)
        assert any("invalid answer 'maybe'" in e for e in errors), errors

    def test_the_same_slot_offered_twice_reads_as_two_answers_to_one_question(
        self,
    ) -> None:
        entry = speaker(
            candidate_dates=[
                _slot(answer="accepted"),
                _slot(answer="declined"),
            ]
        )
        errors = validate_speakers([entry], BOARD)
        assert any("duplicate slot" in e for e in errors), errors

    def test_the_slot_that_is_wrong_is_named_by_its_position(self) -> None:
        entry = speaker(
            candidate_dates=[_slot(), _slot(date="2026-06-08", answer="yes")]
        )
        errors = validate_speakers([entry], BOARD)
        assert any("candidate_dates[1]" in e for e in errors), errors
        assert not any("candidate_dates[0]" in e for e in errors), errors


class TestChecklist:
    """Who owes each line of the journey.

    The rule the rest of this module states -- absent is a defect, empty is
    an answer -- holds here too, and the answer that matters is `{}`: nobody
    is down for anything. That is not an unfinished record. It is what every
    record has always been, because until now the app knew about two hosts
    and nothing else, and it is where every line stays until somebody
    chooses otherwise.
    """

    def test_an_empty_checklist_is_the_normal_state(self) -> None:
        assert validate_speakers([speaker(checklist={})], BOARD) == []

    def test_a_named_owner_is_accepted(self) -> None:
        entry = speaker(checklist={"scheduled/T-30/visuals": {"assignee": "Anonymous"}})
        assert validate_speakers([entry], BOARD) == []

    def test_an_item_owner_is_not_checked_against_the_board(self) -> None:
        # `assigned_to` has to be a sitting board member; an item owner does
        # not, and the two rules are deliberately different. A line of a
        # runbook is often owed by a host who never sat on the board, and
        # making one field answer to the other's rule is the first step
        # towards making one field answer to the other's value.
        entry = speaker(
            assigned_to="Anonymous",
            checklist={"scheduled/T-30/visuals": {"assignee": "Anonymous"}},
        )
        assert "Anonymous" not in BOARD
        assert validate_speakers([entry], BOARD) == []

    def test_a_blank_owner_is_an_answer(self) -> None:
        entry = speaker(checklist={"scheduled/T-30/visuals": {"assignee": ""}})
        assert validate_speakers([entry], BOARD) == []

    def test_a_missing_checklist_is_reported(self) -> None:
        entry = speaker()
        del entry["checklist"]
        errors = validate_speakers([entry], BOARD)
        assert any("missing checklist" in e for e in errors), errors

    def test_a_checklist_that_is_not_a_mapping_is_reported(self) -> None:
        errors = validate_speakers([speaker(checklist=["Anonymous"])], BOARD)
        assert any("checklist: must be a mapping" in e for e in errors), errors

    def test_a_bare_name_where_a_block_belongs_is_reported(self) -> None:
        entry = speaker(checklist={"scheduled/T-30/visuals": "Anonymous"})
        errors = validate_speakers([entry], BOARD)
        assert any("not a mapping" in e for e in errors), errors

    def test_a_line_with_no_owner_key_at_all_is_reported(self) -> None:
        entry = speaker(checklist={"scheduled/T-30/visuals": {}})
        errors = validate_speakers([entry], BOARD)
        assert any("missing assignee" in e for e in errors), errors

    def test_a_key_this_app_does_not_use_is_reported(self) -> None:
        entry = speaker(
            checklist={"scheduled/T-30/visuals": {"assignee": "Anonymous", "due": "soon"}}
        )
        errors = validate_speakers([entry], BOARD)
        assert any("unknown keys ['due']" in e for e in errors), errors

    def test_an_owner_that_is_not_a_login_is_reported(self) -> None:
        entry = speaker(checklist={"scheduled/T-30/visuals": {"assignee": "e mma"}})
        errors = validate_speakers([entry], BOARD)
        assert any("invalid assignee" in e for e in errors), errors

    def test_the_line_that_is_wrong_is_named(self) -> None:
        entry = speaker(
            checklist={
                "scheduled/T-30/visuals": {"assignee": "Anonymous"},
                "scheduled/T-21/linkedin": {"assignee": 7},
            }
        )
        errors = validate_speakers([entry], BOARD)
        assert any("'scheduled/T-21/linkedin'" in e for e in errors), errors
        assert not any("'scheduled/T-30/visuals'" in e for e in errors), errors
