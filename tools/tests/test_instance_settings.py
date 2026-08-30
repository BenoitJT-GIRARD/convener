"""This side of the boundary between the thresholds' arithmetic and the
form that now offers those thresholds for editing.

Three of the four files in `config/` that
`config/boundary.yml` hands to the instance are numbers a maintainer
edits, and until this check existed the only thing standing between a
maintainer and an illegal one was a test -- run later, somewhere else, by
somebody else. `instance/queue-drain.yml`'s `alarm_after_hours` is the sharp case:
**both** its bounds are derived from other declarations, and with this
repository's current settings they meet exactly at 48, so there is
precisely one legal value and nothing in the file says so. A file cannot
refuse; a form can, and `app/src/settings/bounds.ts` is the form's copy of
this arithmetic.

Two copies is one more than this project usually allows, and the reason it
is allowed here is the one D-14 gives: the decision does not move, the
*answer* is pinned. `tools/tests/fixtures/instance-settings.json` holds the
cases; this module answers them from `registration_routing` and
`queue_watch`, and `app/tests/settings-bounds.test.ts` answers them from
the browser's copy. A bound the cockpit computed differently from the one
the scheduled job enforces would be worse than no form at all -- a
volunteer told a value is fine, and a daily job that goes red on it -- so
the cases below are what stops the two drifting.

Nothing here reads the live repository: `test_queue_watch.py` already holds
this instance's own settings against these same functions. What this module
holds is the *rule*, on worked values, including the two that matter most
-- one hour below the floor and one hour above the ceiling.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from typing import Any, Final

import pytest

from convener_ops import actions_usage, queue_watch
from convener_ops.declaration import boundary
from convener_ops.declaration.paths import repo_root
from convener_ops.journey import registration_routing

_FIXTURE: Final = (
    repo_root() / "tools" / "tests" / "fixtures" / "instance-settings.json"
)

_LOADED: Final[dict[str, Any]] = json.loads(_FIXTURE.read_text(encoding="utf-8"))

#: `on:` parses to the boolean `True` under PyYAML's YAML-1.1 resolver, and
#: `drain_period_hours` reads that key. The browser's YAML reader resolves it
#: to the string `"on"` instead, which is exactly why the fixture carries the
#: `schedule:` list rather than a workflow document: the two languages
#: disagree about the *key*, and they must not be allowed to disagree about
#: the answer.
_ON_KEY_UNDER_YAML_1_1: Final = True

#: Every setting the cockpit's form offers, read from the shared fixture
#: rather than restated here -- the browser reads the same rows to build the
#: form, so a key added on one side only fails on the other.
_EDITED: Final[list[dict[str, Any]]] = list(_LOADED["edited"]["keys"])

#: The minimum each file's own parser puts on a whole number, taken from
#: those rows. `warn_at_share` is absent because its interval is ]0, 1] and
#: its lower end is open -- `kind: share` in the fixture, and the one row
#: this mapping deliberately does not carry.
_PARSER_MINIMUM: Final[dict[tuple[str, str], int]] = {
    (row["file"], row["key"]): row["least"] for row in _EDITED if row["kind"] == "whole"
}


def _cadence_cases() -> list[dict[str, Any]]:
    return list(_LOADED["drain_cadence"]["cases"])


def _bounds_cases() -> list[dict[str, Any]]:
    return list(_LOADED["bounds"]["cases"])


def _settings_cases() -> list[dict[str, Any]]:
    return list(_LOADED["settings"]["cases"])


def _by_file(name: str) -> list[tuple[int, dict[str, Any]]]:
    """Every edited row belonging to one file, with its index -- so a test
    can build that file's whole shape out of the fixture instead of naming
    its keys a second time."""
    return [(index, row) for index, row in enumerate(_EDITED) if row["file"] == name]


def _admissible(case: dict[str, Any]) -> tuple[float, float]:
    """The range this repository's own arithmetic leaves for one case's
    key, as `(lowest, highest)`.

    Composed from `registration_routing` and `queue_watch` rather than
    written out, so a change to either moves this and the fixture goes red
    on the value it was pinning -- which is the point of pinning it.
    """
    context = case["context"]
    period = int(context["period_hours"])
    key = case["key"]
    file = case["file"]

    if file == "instance/queue-drain.yml" and key == "alarm_after_hours":
        floor, ceiling = queue_watch.alarm_bounds(
            period, int(context["queue_beyond_hours"])
        )
        return float(floor), float(ceiling)
    if file == "instance/queue-drain.yml" and key == "max_silent_days":
        return float(queue_watch.silence_floor_days(period)), math.inf
    if file == "instance/registration-lanes.yml" and key == "queue_beyond_hours":
        # Both ends of the same coupling, seen from the other file. The lane
        # threshold's own floor is `floor_hours`; its *coupled* floor is
        # whatever leaves the alarm already written next door still legal,
        # which is that alarm plus the same two periods. The larger of the
        # two is the one that bites, and neither is a number typed here.
        alarm = int(context["alarm_after_hours"])
        coupled = alarm + registration_routing.floor_hours(period)
        return float(max(registration_routing.floor_hours(period), coupled)), math.inf
    if file == "instance/actions-budget.yml" and key == "warn_at_share":
        # `budget_from_data` refuses anything outside ]0, 1]. The open lower
        # end is why this function returns floats: the bound is not "at least
        # nought", it is "more than nought".
        return math.nextafter(0.0, 1.0), 1.0
    return float(_PARSER_MINIMUM[(file, key)]), math.inf


@pytest.mark.parametrize("case", _cadence_cases(), ids=lambda c: c["why"])
def test_a_schedule_means_the_same_number_of_hours_on_this_side(
    case: dict[str, Any],
) -> None:
    """`drain_period_hours` answers every shared cadence case the way the
    browser's copy has to. A refusal is an answer too: `hours: null` means
    the shape is one no arithmetic here will put a number on, and a floor
    built on a guessed cadence is a registration that misses its seminar."""
    workflow: dict[str | bool, Any] = {
        _ON_KEY_UNDER_YAML_1_1: {"schedule": case["schedule"]}
    }
    if case["hours"] is None:
        with pytest.raises(registration_routing.CronShapeError):
            registration_routing.drain_period_hours(workflow)
        return
    assert registration_routing.drain_period_hours(workflow) == case["hours"]


def test_the_cadence_cases_cover_both_verdicts() -> None:
    """Neither verdict passes for free -- the same guard
    `edition-prefix.json`'s own test keeps on its cases."""
    cases = _cadence_cases()
    assert any(case["hours"] is not None for case in cases)
    assert any(case["hours"] is None for case in cases)


@pytest.mark.parametrize("case", _bounds_cases(), ids=lambda c: c["why"])
def test_the_bounds_are_what_the_fixture_pins(case: dict[str, Any]) -> None:
    period = int(case["period_hours"])
    floor, ceiling = queue_watch.alarm_bounds(period, int(case["queue_beyond_hours"]))
    assert floor == case["alarm_floor"]
    assert ceiling == case["alarm_ceiling"]
    assert registration_routing.floor_hours(period) == case["lane_floor"]
    assert queue_watch.silence_floor_days(period) == case["silence_floor_days"]


def test_one_pinned_case_is_this_repositorys_own_meeting_point() -> None:
    """The fixture is not a set of invented numbers with a live case
    missing from it: today's cadence and lane threshold are among the cases,
    and they are the ones where the floor and the ceiling meet."""
    today = [
        case
        for case in _bounds_cases()
        if case["period_hours"] == 24 and case["queue_beyond_hours"] == 96
    ]
    assert len(today) == 1
    assert today[0]["alarm_floor"] == today[0]["alarm_ceiling"]


def test_at_least_one_pinned_case_has_the_bounds_crossing() -> None:
    """A crossed pair is a finding about the settings, not a broken test,
    and `alarm_bounds` says so in its own docstring. It has to be exercised,
    or the browser's copy could quietly clamp instead of reporting."""
    assert any(case["alarm_ceiling"] < case["alarm_floor"] for case in _bounds_cases())


@pytest.mark.parametrize("case", _settings_cases(), ids=lambda c: c["why"])
def test_every_typed_value_is_judged_the_same_way_on_this_side(
    case: dict[str, Any],
) -> None:
    lowest, highest = _admissible(case)
    inside = lowest <= float(case["value"]) <= highest
    assert inside == case["accepted"], (
        f"{case['key']} = {case['value']!r} in {case['file']}: this side puts "
        f"the admissible range at {lowest}..{highest}, and the fixture says "
        f"{'accepted' if case['accepted'] else 'refused'} ({case['why']})"
    )


@pytest.mark.parametrize("case", _settings_cases(), ids=lambda c: c["why"])
def test_a_refused_case_names_which_end_refused_it(case: dict[str, Any]) -> None:
    """`bound` is not decoration: it is the word the browser's refusal has
    to contain, so a message reading only "invalid" fails on the other
    side. Here it only has to agree with the arithmetic."""
    lowest, highest = _admissible(case)
    value = float(case["value"])
    if case["accepted"]:
        assert case["bound"] is None
        return
    assert case["bound"] in {"floor", "ceiling", "coupling"}
    if case["bound"] == "ceiling":
        assert value > highest
    else:
        assert value < lowest


def test_every_edited_key_is_one_a_parser_already_knows() -> None:
    """The form offers no key this repository's own closed-shape parsers
    would refuse to read back. `thresholds_from_data`, `threshold_from_data`
    and `budget_from_data` each refuse, by name, anything that is not their
    exact shape -- so a key the form invented would be a value written into
    a file the next scheduled run cannot parse at all.

    Driven against the parsers themselves rather than against a list: each
    file is built with only the keys the fixture declares for it, and has to
    come back out of its own reader intact.
    """
    offered = {(row["file"], row["key"]) for row in _EDITED}

    drain = {row["key"]: 2 for _, row in _by_file("instance/queue-drain.yml")}
    parsed = queue_watch.thresholds_from_data(
        {"v": queue_watch.CONFIG_FILE_VERSION, **drain}
    )
    assert set(drain) == {"alarm_after_hours", "max_silent_days"}
    assert parsed.alarm_after_hours == 2

    lanes = {row["key"]: 96 for _, row in _by_file("instance/registration-lanes.yml")}
    assert set(lanes) == {"queue_beyond_hours"}
    assert (
        registration_routing.threshold_from_data(
            {"v": registration_routing.CONFIG_FILE_VERSION, **lanes}
        )
        == 96
    )

    budget = {
        row["key"]: (0.5 if row["kind"] == "share" else 1)
        for _, row in _by_file("instance/actions-budget.yml")
    }
    resolved = actions_usage.budget_from_data(
        {"v": actions_usage.USAGE_FILE_VERSION, **budget}
    )
    assert set(budget) == {
        field.name for field in dataclasses.fields(actions_usage.Budget)
    }
    assert resolved.warn_at_share == 0.5

    for case in _settings_cases():
        assert (case["file"], case["key"]) in offered


def test_the_declared_instance_paths_are_what_the_boundary_derives() -> None:
    """The other half of the same pin. The settings screen has to say what
    this instance owns, and the honest answer is already computed --
    `boundary.Boundary.instance_paths`, from `config/boundary.yml`'s own
    list plus each `config/` file's own `owner:`. The browser derives it
    too, from the same bytes; the fixture is what makes a disagreement
    between the two a failing test rather than a screen offering to edit a
    file upstream owns."""
    declared = boundary.load()
    assert list(declared.instance_paths) == _LOADED["instance_paths"]["paths"]


def test_the_parsers_agree_with_the_minimums_this_module_states() -> None:
    """The fixture's `least` is a claim about a parser, so it is driven
    rather than trusted: each parser is handed its own minimum and one below
    it, and has to accept the first and refuse the second. This is what the
    browser's own floor for these keys rests on -- a form that accepted a
    value the reader refuses would write a file the next scheduled run stops
    on."""
    lanes = registration_routing.CONFIG_FILE_VERSION
    drain = queue_watch.CONFIG_FILE_VERSION

    least = _PARSER_MINIMUM[("instance/queue-drain.yml", "alarm_after_hours")]
    assert queue_watch.thresholds_from_data(
        {"v": drain, "alarm_after_hours": least, "max_silent_days": least}
    ) == queue_watch.Thresholds(alarm_after_hours=least, max_silent_days=least)
    with pytest.raises(ValueError, match="alarm_after_hours"):
        queue_watch.thresholds_from_data(
            {"v": drain, "alarm_after_hours": least - 1, "max_silent_days": least}
        )

    assert (
        registration_routing.threshold_from_data({"v": lanes, "queue_beyond_hours": 1})
        == 1
    )
    with pytest.raises(ValueError, match="queue_beyond_hours"):
        registration_routing.threshold_from_data({"v": lanes, "queue_beyond_hours": 0})

    budget = {
        "v": actions_usage.USAGE_FILE_VERSION,
        "monthly_minutes": 1,
        "window_days": 1,
        "warn_at_share": 1,
        "submissions_per_day": 1,
        "max_runs": 1,
        "max_silent_days": 0,
    }
    assert actions_usage.budget_from_data(dict(budget)).max_silent_days == 0
    with pytest.raises(ValueError, match="max_silent_days"):
        actions_usage.budget_from_data({**budget, "max_silent_days": -1})
    with pytest.raises(ValueError, match="warn_at_share"):
        actions_usage.budget_from_data({**budget, "warn_at_share": 0})
    with pytest.raises(ValueError, match="warn_at_share"):
        actions_usage.budget_from_data({**budget, "warn_at_share": 1.25})


def test_the_fixture_is_read_from_the_one_path_both_sides_name() -> None:
    """A guard against the boundary quietly becoming two files: the
    browser's side resolves the same path from `app/tests/`, and a fixture
    moved on one side only would leave the other reading a stale copy."""
    assert _FIXTURE.is_file()
    assert Path("tools/tests/fixtures/instance-settings.json") == _FIXTURE.relative_to(
        repo_root()
    )
