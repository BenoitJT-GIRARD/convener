"""Schema v5: the post-event survey's per-event switch, on the write side.

The same two-language discipline `test_validate_v4.py`'s own module
docstring states, applied to the one field schema v5 adds:

- **An absent key is a defect.** A record with no `survey_enabled` at all
  is a record nobody finished migrating, not a record whose survey is off.
- **`False` is an answer.** The switch is off by default -- optional means
  absent by default -- and a record that says so
  explicitly is well formed.

Everything here is a whole record from `conftest.speaker()` with one thing
taken away or changed, so a failure names the one thing -- the same idiom
`test_validate_v4.py` uses.
"""

from __future__ import annotations

import pytest
from conftest import EDITIONS, speaker

from convener_ops.validate import SPEAKER_BOOL_V5, validate_speakers

BOARD = frozenset({"carol"})


def test_a_whole_record_is_accepted() -> None:
    assert validate_speakers([speaker()], BOARD, editions=EDITIONS) == []


@pytest.mark.parametrize("field", SPEAKER_BOOL_V5)
def test_a_record_that_leaves_out_the_switch_is_reported(field: str) -> None:
    entry = speaker()
    del entry[field]
    errors = validate_speakers([entry], BOARD, editions=EDITIONS)
    assert [e for e in errors if f"missing {field}" in e], errors
    assert all("spk-001" in error for error in errors), errors


@pytest.mark.parametrize("value", [False, True])
def test_either_boolean_value_is_a_complete_answer(value: bool) -> None:
    assert (
        validate_speakers([speaker(survey_enabled=value)], BOARD, editions=EDITIONS)
        == []
    )


@pytest.mark.parametrize("value", ["false", 0, 1, None, "true"])
def test_a_switch_that_is_not_a_boolean_is_reported(value: object) -> None:
    """`0`/`1` are the attacker-reachable near-miss: Python's own `bool` is
    an `int` subclass in the other direction, but nothing here should
    accept the reverse -- a stored `0` or `1` is not a boolean, and must be
    refused exactly like any other wrong type."""
    errors = validate_speakers(
        [speaker(survey_enabled=value)], BOARD, editions=EDITIONS
    )
    assert [e for e in errors if "survey_enabled must be a boolean" in e], errors


def test_a_switch_left_out_is_not_confused_with_one_left_false() -> None:
    """The distinction itself, stated once: `entry.get(key)` reads `False`
    and an absent key as the same falsy thing; `in` does not."""
    off = speaker(survey_enabled=False)
    assert validate_speakers([off], BOARD, editions=EDITIONS) == []
    stripped = {k: v for k, v in off.items() if k != "survey_enabled"}
    errors = validate_speakers([stripped], BOARD, editions=EDITIONS)
    assert len(errors) == 1
    assert "missing survey_enabled" in errors[0]
