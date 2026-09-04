"""The rule that keeps the example instance's records the age they were
written to be, and the fixture that keeps this side of it and the cockpit
build's side answering the same thing.

`tools/tests/fixtures/example-dates.json` is the boundary itself; every case
below is read out of it rather than typed here, so a case added there is a
case both languages answer on the commit that adds it.

Beyond the boundary, three properties of the file the rule is for: it still
validates after being shifted, nothing in it is overdue on the day it is
written for, and the day it says it is written for is the anchor.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import example_dates
import pytest
import yaml

from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.published import EditionPrefix
from convener_ops.governance.validate import validate_config, validate_speakers

ROOT = repo_root()
FIXTURE = ROOT / "tools" / "tests" / "fixtures" / "example-dates.json"
EXAMPLE = ROOT / "examples" / "the-example-collective" / "instance"


def fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def test_the_fixture_states_the_anchor_this_module_states() -> None:
    """The one value both languages have to agree on before any case below
    means anything."""
    assert fixture()["anchor"] == example_dates.ANCHOR


@pytest.mark.parametrize("case", fixture()["shifts"], ids=lambda c: str(c["today"]))
def test_the_shift_is_whole_weeks_from_the_anchor(case: dict[str, Any]) -> None:
    days = example_dates.shift_days(case["today"])
    assert days == case["days"], case["why"]
    assert days % 7 == 0, "a shift that is not whole weeks moves a Thursday session"


@pytest.mark.parametrize("case", fixture()["texts"], ids=lambda c: str(c["why"])[:40])
def test_a_document_is_moved_by_replacing_the_days_in_it(case: dict[str, Any]) -> None:
    assert example_dates.shifted(case["given"], case["today"]) == case["expected"], (
        case["why"]
    )


def test_the_fixture_is_read_rather_than_restated() -> None:
    """A fixture nobody could fail is not a boundary. Both lists have to
    carry cases, and the shifts have to disagree with each other."""
    data = fixture()
    assert len(data["shifts"]) >= 5
    assert len(data["texts"]) >= 4
    assert len({case["days"] for case in data["shifts"]}) >= 4


def test_the_examples_own_present_is_never_ahead_of_the_day_it_is_read_on() -> None:
    """The property the floor buys, and the reason a record written as *due
    in seven days* is never read as overdue: the fixture's own present lands
    between zero and six days behind the real one, on either side of the
    anchor."""
    anchor = dt.date.fromisoformat(example_dates.ANCHOR)
    for offset in range(-400, 400):
        day = anchor + dt.timedelta(days=offset)
        present = anchor + dt.timedelta(days=example_dates.shift_days(day.isoformat()))
        assert 0 <= (day - present).days <= 6, day


def test_the_pinned_day_replaces_the_clock_and_a_broken_one_stops() -> None:
    assert example_dates.today({example_dates.TODAY_ENV: "2026-08-20"}) == "2026-08-20"
    assert example_dates.today({}) == dt.date.today().isoformat()
    with pytest.raises(ValueError, match="not a YYYY-MM-DD day"):
        example_dates.today({example_dates.TODAY_ENV: "the day of the shoot"})


def _shifted_store(day: str) -> tuple[Any, Any]:
    config = yaml.safe_load(
        example_dates.shifted(
            (EXAMPLE / "data" / "config.yml").read_text(encoding="utf-8"), day
        )
    )
    speakers = yaml.safe_load(
        example_dates.shifted(
            (EXAMPLE / "data" / "speakers.yml").read_text(encoding="utf-8"), day
        )
    )
    return config, speakers


@pytest.mark.parametrize("day", ["2026-09-03", "2026-08-20", "2029-04-19"])
def test_the_example_still_validates_once_it_has_been_moved(day: str) -> None:
    """A substitution over text could produce a day the calendar has not got
    -- 29 February in a year that has none is the case a naive "add a year"
    would hit. Whole weeks cannot, and this is that claim checked against the
    real store rather than argued."""
    config, speakers = _shifted_store(day)
    declaration = json.loads((EXAMPLE / "config.json").read_text(encoding="utf-8"))
    assert validate_config(config) == []
    assert (
        validate_speakers(
            speakers,
            [member["login"] for member in config["board"]],
            editions=EditionPrefix(declaration["edition_prefix"]),
        )
        == []
    )


def test_nobody_voted_before_they_joined_the_board() -> None:
    """The reason the board's own file is dated too rather than left where it
    was: ballots move and seats would not, and a member would then have voted
    a year before they were seated."""
    config, speakers = _shifted_store(example_dates.ANCHOR)
    joined = {member["login"]: member["joined_on"] for member in config["board"]}
    for speaker in speakers:
        for ballot in speaker["selection"]["ballots"]:
            assert ballot["date"] >= joined[ballot["voter"]], (
                f"{speaker['id']}: {ballot['voter']} voted on {ballot['date']} "
                f"and joined on {joined[ballot['voter']]}"
            )
