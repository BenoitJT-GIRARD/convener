"""The numbers the handbook states, against the files they are configuration in.

A page that states a number the code also holds is a copy, and this repository
has paid for that four times: the schema appendix drifted twice, the
preparation countdown drifted six windows out of date, and both did it
*underneath a sentence claiming they could not*. A marker is not a control.

`docs/handbook/workflow/4-after.md` carried the same shape. It typed the view-counting
window as prose and then said "the handbook and the form cannot end up
claiming different windows" - but only the form's label is derived
(`viewCountLabel`, `app/src/state/phases.ts`); nothing read the page. Setting
`view_count_window_days: 60` left the form saying 60 and the page saying 30,
under the sentence saying that could not happen.

This module is the control the sentence names. It is on the Python side
because the number is `instance/data/config.yml`'s, which is the series' own file
rather than a test double: the app suite deliberately reads doubles so that a
Board edit cannot turn a screen test red, and this claim is precisely a claim
about what the Board has set.

**Every claim of this shape, not the one that was noticed.** Five more pages
state a declared number in prose and are read here for the same reason: the
inactivity window, the publication objection window, the vote window, the four
turnaround targets, the length of a session, and the pair of bounds the
Settings screen computes. Each is a number a duplicate can change in a file it
owns, under a sentence in a file the product owns, which is exactly the
arrangement nothing notices going wrong.

**Why a test and not a derivation.** These sentences are prose with a number
in them, not tables; rendering them from the declaration would mean a
generated handbook page for the sake of six numbers, and a reader who lands
mid-page would be reading a generated paragraph they cannot edit. So the
number stays written where it reads best and the claim is bound instead - the
same trade `tools/scripts/generate_schema_doc.py` did *not* make, because a schema
appendix is a table and this is not.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import yaml

from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.yaml_safe import safe_load

ROOT = repo_root()
PAGE = Path("docs/handbook/workflow/4-after.md")
GATES = Path("docs/handbook/governance/board-rules.md")
OPERATIONS = Path("docs/operating/operations.md")
HOSTING = Path("docs/handbook/workflow/3-hosting.md")
DRAIN_WORKFLOW = Path(".github/workflows/sweep-and-notify.yml")

#: The sentence the page states the window in. Written as a pattern rather
#: than searched for loosely: `contains("30")` would pass on any page that
#: mentions T-30, which is a different number about a different thing.
_WINDOW = re.compile(r"reads them \*\*(\d+) days after the talk\*\*")

#: The handbook writes a short window in words rather than digits, and a
#: test that only knew digits would pass straight over "twelve months".
#: Only as far as the numbers actually declared: a spelled-out ninety is
#: not a form anything here writes.
_SPELLED: Final = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}

_INACTIVITY = re.compile(r"The window is \*\*([a-z]+) months\*\*")
_OBJECTION_PROSE = re.compile(r"object within \*\*([a-z]+) working days\*\*")
_OBJECTION_ROW = re.compile(r"\| Publication objection window \((\d+)\)")
_VOTE_ROW = re.compile(r"\| Vote window \((\d+)\)")
_TARGETS_PROSE = re.compile(
    r"a decision on a suggested speaker \((\d+) days\), a follow-up on an "
    r"invitation with no answer \((\d+)\), a forum summary after the talk "
    r"\((\d+)\), the recording after the talk \((\d+)\)"
)
_TARGETS_ROW = re.compile(r"\| Turnaround targets \((\d+) / (\d+) / (\d+) / (\d+)\)")
_SESSION = re.compile(r"## Plan for the day \(~(\d+) minutes\)")

#: The three numbers the thresholds section states. The subtraction is
#: written with a typographic minus sign, so the operator is matched as
#: "whatever is not a digit" rather than as a character somebody has to
#: keep re-typing correctly.
_ALARM_FLOOR = re.compile(r"cron period in\s+`[^`]+` \((\d+) hours today\)")
_ALARM_CEILING = re.compile(r"minus the same margin \((\d+)\D+(\d+) = (\d+) today\)")
_ALARM_MEETS = re.compile(r"Those two meet at (\d+)")

#: A cron this module is willing to read a period out of: a fixed minute
#: and hour, every day. `app/src/settings/bounds.ts::drainCadence` refuses
#: anything else for the same reason -- a period nobody can compute is not
#: a floor anybody should be shown -- and this refuses it too rather than
#: assuming a day.
_DAILY_CRON = re.compile(r"^\d+ \d+ \* \* \*$")
_HOURS_PER_DAY: Final = 24


def _config() -> dict[str, Any]:
    loaded = safe_load(
        (ROOT / "instance" / "data" / "config.yml").read_text(encoding="utf-8")
    )
    assert isinstance(loaded, dict)
    return loaded


def _declaration(name: str) -> dict[str, Any]:
    loaded = safe_load((ROOT / "instance" / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _page(path: Path) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _stated(path: Path, pattern: re.Pattern[str]) -> re.Match[str]:
    found = pattern.search(_page(path))
    assert found is not None, (
        f"{path.as_posix()} no longer states this number in the form this "
        "test reads; the page and the file it is configuration in can drift "
        f"again. Pattern: {pattern.pattern}"
    )
    return found


def _drain_period_hours() -> int:
    """How long a drain waits between runs, read out of its own schedule."""
    workflow = yaml.safe_load(_page(DRAIN_WORKFLOW))
    schedule = workflow[True]["schedule"]
    assert len(schedule) == 1, (
        f"{DRAIN_WORKFLOW.as_posix()} declares {len(schedule)} cron entries; "
        "a period cannot be read out of more than one"
    )
    cron = schedule[0]["cron"]
    assert _DAILY_CRON.match(cron), (
        f"{DRAIN_WORKFLOW.as_posix()} schedules {cron!r}, which is not a "
        "fixed daily run -- the floor the handbook states is twice this "
        "period, and there is no honest number to compare it against"
    )
    return _HOURS_PER_DAY


def test_the_page_states_the_window_the_configuration_sets() -> None:
    page = (ROOT / PAGE).read_text(encoding="utf-8")
    stated = _WINDOW.search(page)
    assert stated is not None, (
        f"{PAGE.as_posix()} no longer states the view-counting window in the "
        "form this test reads; the page and instance/data/config.yml can drift again."
    )
    assert int(stated.group(1)) == _config()["view_count_window_days"]


def test_the_operations_page_states_the_inactivity_window_it_is_set_to() -> None:
    """`inactivity_months` is the number the sweep counts on; the page
    beside the rule writes it out in words."""
    stated = _stated(OPERATIONS, _INACTIVITY).group(1)
    assert stated == _SPELLED[_config()["inactivity_months"]], (
        f"{OPERATIONS.as_posix()} says the inactivity window is {stated}, "
        f"and instance/data/config.yml sets it to {_config()['inactivity_months']}"
    )


def test_the_gates_page_states_the_objection_window_it_is_set_to() -> None:
    """Twice on one page -- once in the rule, once in the table of units --
    and both are read, because a correction that reached one of them is
    exactly how this page ends up disagreeing with itself."""
    declared = _config()["objection_window_working_days"]
    assert _stated(GATES, _OBJECTION_PROSE).group(1) == _SPELLED[declared]
    assert int(_stated(GATES, _OBJECTION_ROW).group(1)) == declared


def test_the_gates_page_states_the_vote_window_it_is_set_to() -> None:
    assert int(_stated(GATES, _VOTE_ROW).group(1)) == _config()["vote_window_days"]


def test_the_gates_page_states_the_turnaround_targets_it_is_set_to() -> None:
    """Four numbers from two places, and the page writes all four twice.

    Three are `sla_days`; the first is `vote_window_days`, because the
    board's own deadline is the day `sweep.py` parks an expired lead on and
    holding it twice let a file say the board was on time the morning the
    job parked the lead (`app/src/state/sla.ts::SLA_STEPS`).
    """
    config = _config()
    sla = config["sla_days"]
    expected = (
        config["vote_window_days"],
        sla["invitation_follow_up"],
        sla["summary_after_delivery"],
        sla["recording_after_delivery"],
    )
    prose = tuple(int(n) for n in _stated(GATES, _TARGETS_PROSE).groups())
    row = tuple(int(n) for n in _stated(GATES, _TARGETS_ROW).groups())
    assert prose == expected, (
        f"{GATES.as_posix()} states turnaround targets {prose}, and the "
        f"configuration sets {expected}"
    )
    assert row == expected


def test_the_hosting_page_states_the_session_length_it_is_set_to() -> None:
    """The heading a host reads on the morning of the talk, against the
    length every calendar entry is generated at."""
    stated = int(_stated(HOSTING, _SESSION).group(1))
    assert stated == _config()["seminar_duration_minutes"], (
        f"{HOSTING.as_posix()} plans a {stated}-minute day, and "
        f"instance/data/config.yml sets seminar_duration_minutes to "
        f"{_config()['seminar_duration_minutes']}"
    )


def test_the_operations_page_states_the_coupled_bounds_it_computes() -> None:
    """The one place the handbook does arithmetic on two declarations.

    `app/src/settings/bounds.ts` computes the same floor and ceiling and
    refuses a value outside them; the page states what they come to today,
    in three numbers and a subtraction. Every one of them is read back out
    of the declarations here -- the margin from the drain's own cron, the
    ceiling from `queue_beyond_hours`, and the value the two meet at from
    `alarm_after_hours` -- so raising the lane threshold without rewriting
    the paragraph fails rather than leaving a worked example that no longer
    works.
    """
    margin = 2 * _drain_period_hours()
    queue_beyond_hours = _declaration("registration-lanes.yml")["queue_beyond_hours"]
    alarm_after_hours = _declaration("queue-drain.yml")["alarm_after_hours"]

    floor = int(_stated(OPERATIONS, _ALARM_FLOOR).group(1))
    stated_ceiling = tuple(int(n) for n in _stated(OPERATIONS, _ALARM_CEILING).groups())
    meets = int(_stated(OPERATIONS, _ALARM_MEETS).group(1))

    assert floor == margin, (
        f"{OPERATIONS.as_posix()} states a floor of {floor} hours; twice the "
        f"drain's own period is {margin}"
    )
    ceiling = (queue_beyond_hours, margin, queue_beyond_hours - margin)
    assert stated_ceiling == ceiling, (
        f"{OPERATIONS.as_posix()} works the ceiling out as {stated_ceiling}, "
        f"and the declarations make it {queue_beyond_hours} - {margin} = "
        f"{queue_beyond_hours - margin}"
    )
    assert meets == alarm_after_hours, (
        f"{OPERATIONS.as_posix()} says the two bounds meet at {meets}, and "
        f"instance/queue-drain.yml holds alarm_after_hours: {alarm_after_hours}"
    )
    assert meets == floor == queue_beyond_hours - margin, (
        f"{OPERATIONS.as_posix()} says the two bounds meet, and with these "
        "declarations they no longer do -- the paragraph claims a coupling "
        "that has come apart"
    )
