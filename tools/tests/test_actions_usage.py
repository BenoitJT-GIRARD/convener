"""What the runs really cost, and the alarm before the
budget runs out.

Every minute this project has ever written down is a `timeout-minutes`
ceiling; nothing here has ever run on GitHub. This module holds the three
layers that make the measurement mean something:

* `actions_usage.py`'s pure arithmetic -- the per-job rounding GitHub
  actually bills by, the split into the half that cannot surprise anyone
  and the halves that can, and the boundaries the alarm turns on.
* `cli.py`'s three commands, driven end to end against a temporary
  repository root and a fixture file. **The "prove it" the brief asks for
  by name lives here**: data that crosses the line, watched going off, and
  data one unit below it, watched staying quiet -- for both alarms.
* The two workflow files, read as text, pinned against the properties no
  offline command can see: that this feature added no job and no workflow,
  that the job goes red whether or not a notification channel exists, and
  that the second, independent schedule still asks whether the alarm
  itself is still running.

**No test here reaches the network**, which is a project-wide rule and not
a preference: the API calls live in a `gh` step in the workflow, and every
payload below is a fixture written in this file.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from conftest import WorkflowYaml

from convener_ops import actions_usage
from convener_ops.cli import (
    actions_usage_window,
    check_actions_usage_liveness,
    record_actions_usage,
)
from convener_ops.paths import repo_root
from convener_ops.yaml_safe import safe_load

_ROOT = repo_root()
_SWEEP_PATH = _ROOT / ".github" / "workflows" / "sweep-and-notify.yml"
_WATCHDOG_PATH = _ROOT / ".github" / "workflows" / "retention-watchdog.yml"
_WORKFLOWS = _ROOT / ".github" / "workflows"


#: The thresholds this repository actually ships. The simulations below run
#: against these rather than against numbers invented here, so "it fires"
#: means it fires on the file a maintainer would edit.
#: Read on demand, never while this module loads.
#: `config/actions-budget.yml` is a path `config/boundary.yml` hands to the
#: instance, and a derived repository is entitled not to have it until the
#: derivation lays an example's own file there. At module scope the read
#: took this whole module down at collection -- eighty tests, none of them
#: about where the file is -- with a stack trace instead of a sentence.
@cache
def _real_budget() -> actions_usage.Budget:
    return actions_usage.budget_from_data(
        safe_load(actions_usage.budget_path(_ROOT).read_text(encoding="utf-8"))
    )


def _run(
    *,
    run_id: int = 1,
    name: str = "Quality",
    event: str = "push",
    day: str = "2026-08-20",
    jobs: tuple[int, ...] = (60_000,),
    runner: str = "UBUNTU",
) -> dict[str, Any]:
    """One collected payload, in the exact shape the workflow's collector
    step writes: the run as `GET /actions/runs` reports it, paired with
    what `GET /actions/runs/<id>/timing` answered for it."""
    return {
        "run": {
            "id": run_id,
            "name": name,
            "event": event,
            "created_at": f"{day}T05:00:12Z",
        },
        "timing": {
            "billable": {
                runner: {
                    "total_ms": sum(jobs),
                    "jobs": len(jobs),
                    "job_runs": [
                        {"job_id": i, "duration_ms": ms} for i, ms in enumerate(jobs)
                    ],
                }
            },
            "run_duration_ms": sum(jobs),
        },
    }


def _summarise(
    payloads: list[Any],
    *,
    today: date = date(2026, 8, 24),
    budget: actions_usage.Budget | None = None,
    truncated: bool = False,
) -> actions_usage.Usage:
    return actions_usage.summarise(
        payloads,
        observed_on=today,
        budget=budget or _real_budget(),
        truncated=truncated,
    )


# ==================================================================== #
# The thresholds: configuration, refused rather than guessed
# ==================================================================== #


def test_the_committed_thresholds_parse() -> None:
    """`config/actions-budget.yml` is the file a maintainer edits, and the
    one file that decides when the alarm goes off. If it stops parsing,
    every command below refuses to run rather than falling back to a
    number written in Python."""
    assert _real_budget().monthly_minutes == 2000
    assert _real_budget().window_days >= 1
    assert 0 < _real_budget().warn_at_share <= 1
    assert _real_budget().submissions_per_day >= 1


def test_the_thresholds_are_not_constants_in_a_python_file() -> None:
    """A number a maintainer might want to change does not belong in a
    `.py` file. `Budget` has no defaults, so there is nothing for
    `budget_from_data` to silently complete a partial file with."""
    with pytest.raises(TypeError):
        actions_usage.Budget()  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "not a mapping",
        {"v": 2},
        {"v": 1},
        {
            "v": 1,
            "monthly_minutes": 2000,
            "window_days": 7,
            "warn_at_share": 0,
            "submissions_per_day": 20,
            "max_runs": 200,
            "max_silent_days": 2,
        },
        {
            "v": 1,
            "monthly_minutes": 2000,
            "window_days": 7,
            "warn_at_share": 1.5,
            "submissions_per_day": 20,
            "max_runs": 200,
            "max_silent_days": 2,
        },
        {
            "v": 1,
            "monthly_minutes": 2000,
            "window_days": 0,
            "warn_at_share": 0.75,
            "submissions_per_day": 20,
            "max_runs": 200,
            "max_silent_days": 2,
        },
        {
            "v": 1,
            "monthly_minutes": 2000,
            "window_days": True,
            "warn_at_share": 0.75,
            "submissions_per_day": 20,
            "max_runs": 200,
            "max_silent_days": 2,
        },
    ],
)
def test_budget_from_data_refuses_anything_not_the_exact_shape(data: Any) -> None:
    with pytest.raises(ValueError):
        actions_usage.budget_from_data(data)


def test_window_start_counts_today_in() -> None:
    """A seven-day window is today and the six days before it, not today
    and the seven before it -- the collector fetches from this day and the
    projection divides by the same number."""
    today = date(2026, 8, 24)
    since = actions_usage.window_start(today, _real_budget())
    assert (today - since).days == _real_budget().window_days - 1
    assert since.isoformat() == "2026-08-18"


# ==================================================================== #
# The arithmetic GitHub actually bills by
# ==================================================================== #


@pytest.mark.parametrize(
    ("duration_ms", "expected"),
    [
        (0, 0),
        (1, 1),
        (20_000, 1),
        (60_000, 1),
        (60_001, 2),
        (119_999, 2),
        (-5, 0),
        ("nonsense", 0),
        (None, 0),
        (True, 0),
    ],
)
def test_a_job_bills_whole_minutes_rounded_up(duration_ms: Any, expected: int) -> None:
    assert actions_usage.billed_minutes(duration_ms) == expected


def test_the_rounding_is_per_job_which_is_the_whole_point() -> None:
    """Eight jobs of twenty seconds bill eight minutes, not one. Rounding
    a run's total instead of each job's own duration is the single
    mistake that would make this measurement agree with a wall clock and
    disagree with the invoice."""
    eight_short_jobs = _run(jobs=(20_000,) * 8)
    usage = _summarise([eight_short_jobs])
    assert usage.billed_minutes == 8
    assert eight_short_jobs["timing"]["run_duration_ms"] == 160_000


def test_a_skipped_job_bills_nothing() -> None:
    """`sweep-and-notify.yml`'s own two jobs exclude each other on an
    `if:`. A job GitHub skips never gets a runner, and GitHub reports it
    with no billable entry at all -- an ordinary answer, so zero, not
    unreadable."""
    payload = {
        "run": {
            "id": 9,
            "name": "Sweep and notify the board",
            "event": "schedule",
            "created_at": "2026-08-24T05:00:00Z",
        },
        "timing": {"billable": {}, "run_duration_ms": 0},
    }
    usage = _summarise([payload])
    assert usage.billed_minutes == 0
    assert usage.unreadable == 0


def test_both_halves_are_counted_separately() -> None:
    """An alarm that watched only the scheduled half would be watching the
    half that cannot surprise anyone."""
    usage = _summarise(
        [
            _run(run_id=1, event="schedule", jobs=(60_000,) * 3),
            _run(run_id=2, event="repository_dispatch", jobs=(90_000,)),
            _run(run_id=3, event="push", jobs=(60_000,) * 5),
            _run(run_id=4, event="pull_request", jobs=(60_000,) * 2),
        ]
    )
    assert usage.scheduled_minutes == 3
    assert usage.submission_minutes == 2
    assert usage.development_minutes == 7
    assert usage.billed_minutes == 12
    assert dict(usage.by_event)["schedule"] == 3
    assert dict(usage.by_event)["repository_dispatch"] == 2


def test_the_submission_rate_is_counted_per_day_and_reported_at_its_peak() -> None:
    """A monthly counter announces on the 28th that nothing is left. What
    has to be visible is the day an announcement brings hundreds of
    registrations at once."""
    payloads = [
        _run(run_id=i, event="repository_dispatch", day="2026-08-22") for i in range(3)
    ] + [
        _run(run_id=100 + i, event="repository_dispatch", day="2026-08-23")
        for i in range(11)
    ]
    usage = _summarise(payloads)
    assert usage.busiest_submission_day == "2026-08-23"
    assert usage.busiest_submissions == 11
    assert dict(usage.submissions_by_day) == {"2026-08-22": 3, "2026-08-23": 11}


def test_a_submission_still_counts_towards_the_rate_when_its_cost_is_unreadable() -> (
    None
):
    """That a submission *happened* is legible from the run alone. Losing
    it from the rate because one API call failed would hide the burst as
    well as the bill."""
    payload = _run(run_id=7, event="repository_dispatch")
    payload["timing"] = None
    usage = _summarise([payload])
    assert usage.busiest_submissions == 1
    assert usage.unreadable == 1
    assert usage.billed_minutes == 0


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not a mapping",
        {"run": None},
        {"run": {"id": "not an int", "created_at": "2026-08-20T05:00:00Z"}},
        {"run": {"id": 1, "created_at": "not a timestamp"}},
        {"run": {"id": 1}},
    ],
)
def test_a_run_this_cannot_read_is_counted_as_a_run_it_could_not_cost(
    payload: Any,
) -> None:
    """Never dropped, never zeroed. A question that could not be answered
    is not the answer 'nothing' -- this repository already paid for
    reading one as the other once, in retention.yml."""
    usage = _summarise([payload])
    assert usage.runs == 1
    assert usage.unreadable == 1


def test_a_timing_answer_with_no_job_breakdown_falls_back_to_the_os_total() -> None:
    """Rounds once instead of once per job, so it understates a multi-job
    run -- named in the code rather than passed off as exact."""
    payload = {
        "run": {
            "id": 3,
            "name": "Quality",
            "event": "push",
            "created_at": "2026-08-20T05:00:00Z",
        },
        "timing": {"billable": {"UBUNTU": {"total_ms": 150_000, "jobs": 4}}},
    }
    usage = _summarise([payload])
    assert usage.billed_minutes == 3


def test_a_timing_answer_with_no_billable_section_at_all_is_zero_not_unreadable() -> (
    None
):
    """The same call as a skipped job, in the shape GitHub uses when it
    omits the section entirely. An ordinary answer either way."""
    payload = _run(run_id=4)
    payload["timing"] = {"run_duration_ms": 0}
    usage = _summarise([payload])
    assert usage.billed_minutes == 0
    assert usage.unreadable == 0


def test_a_billable_entry_that_is_not_a_mapping_is_skipped_not_guessed_at() -> None:
    payload = _run(run_id=5)
    payload["timing"] = {"billable": {"UBUNTU": "nonsense"}}
    usage = _summarise([payload])
    assert usage.billed_minutes == 0
    assert usage.foreign_runner_oses == ()


def test_the_projection_turns_a_window_into_a_monthly_rate() -> None:
    budget = actions_usage.budget_from_data(
        {
            "v": 1,
            "monthly_minutes": 2000,
            "window_days": 10,
            "warn_at_share": 0.75,
            "submissions_per_day": 20,
            "max_runs": 200,
            "max_silent_days": 2,
        }
    )
    usage = _summarise([_run(jobs=(60_000,) * 100)], budget=budget)
    assert usage.billed_minutes == 100
    assert usage.projected_monthly_minutes == round(100 / 10 * 30.4)


# ==================================================================== #
# The alarm: it fires, and it stays quiet -- at the boundary
# ==================================================================== #


def _minute_runs(count: int, *, event: str = "push") -> list[Any]:
    """`count` runs that each bill exactly one minute."""
    return [_run(run_id=i, event=event, jobs=(60_000,)) for i in range(count)]


def _rate_boundary() -> int:
    """The smallest number of one-minute runs in a window whose projected
    monthly figure reaches the warning line. Derived rather than typed, so
    this test keeps meaning what it says when the committed thresholds
    move."""
    minutes = 0
    while True:
        minutes += 1
        usage = _summarise(_minute_runs(0))
        projected = round(minutes / _real_budget().window_days * 30.4)
        if projected >= actions_usage.warn_at(_real_budget()):
            assert usage.billed_minutes == 0
            return minutes


def test_the_rate_alarm_fires_at_the_line() -> None:
    usage = _summarise(_minute_runs(_rate_boundary()))
    kinds = {alarm.kind for alarm in actions_usage.alarms(usage, _real_budget())}
    assert actions_usage.RATE_ALARM in kinds


def test_the_rate_alarm_stays_quiet_one_minute_below_the_line() -> None:
    usage = _summarise(_minute_runs(_rate_boundary() - 1))
    assert actions_usage.alarms(usage, _real_budget()) == ()


def test_the_submission_alarm_fires_on_the_days_burst_not_on_the_month() -> None:
    """Twenty in one day fires even though twenty one-minute runs are
    nothing at all against a 2,000-minute month -- which is the entire
    reason this alarm is separate from the rate one."""
    usage = _summarise(
        _minute_runs(_real_budget().submissions_per_day, event="repository_dispatch")
    )
    kinds = {alarm.kind for alarm in actions_usage.alarms(usage, _real_budget())}
    assert kinds == {actions_usage.SUBMISSIONS_ALARM}
    assert usage.projected_monthly_minutes < actions_usage.warn_at(_real_budget())


def test_the_submission_alarm_stays_quiet_one_submission_below() -> None:
    usage = _summarise(
        _minute_runs(
            _real_budget().submissions_per_day - 1, event="repository_dispatch"
        )
    )
    assert actions_usage.alarms(usage, _real_budget()) == ()


def test_the_submission_alarm_names_what_this_number_decides() -> None:
    """This rate is what says the public-submission queue
    has stopped being a precaution. The pointer belongs where the number
    is read, not only in a plan nobody has open at 6am."""
    usage = _summarise(
        _minute_runs(_real_budget().submissions_per_day, event="repository_dispatch")
    )
    fired = actions_usage.alarms(usage, _real_budget())
    assert "queue" in fired[0].text


def test_an_uncosted_run_is_its_own_loud_alarm() -> None:
    """A control that can only ever report 'fine' is not a control
    (D-25). Every figure is an undercount by an unknown amount when this
    fires, and saying so is the point."""
    payload = _run(run_id=1)
    payload["timing"] = "not a mapping"
    usage = _summarise([payload])
    kinds = {alarm.kind for alarm in actions_usage.alarms(usage, _real_budget())}
    assert actions_usage.UNREADABLE_ALARM in kinds


def test_a_truncated_collection_is_its_own_loud_alarm() -> None:
    """Reaching the cap takes a burst, so the cap being reached is a
    signal rather than a shrug."""
    usage = _summarise(_minute_runs(3), truncated=True)
    kinds = {alarm.kind for alarm in actions_usage.alarms(usage, _real_budget())}
    assert kinds == {actions_usage.TRUNCATED_ALARM}


def test_a_runner_this_arithmetic_cannot_price_is_its_own_loud_alarm() -> None:
    """macOS bills at ten times a Linux minute and Windows at two. This
    module adds every runner's minutes at one each, so a non-Linux runner
    makes it an undercount -- reported, never quietly mis-added."""
    usage = _summarise([_run(runner="MACOS")])
    kinds = {alarm.kind for alarm in actions_usage.alarms(usage, _real_budget())}
    assert actions_usage.RUNNER_ALARM in kinds


def test_a_quiet_window_composes_no_message_at_all() -> None:
    usage = _summarise(_minute_runs(2))
    assert actions_usage.alarms(usage, _real_budget()) == ()
    assert actions_usage.message(usage, ()) is None


def test_the_message_carries_the_caveat_that_this_is_not_the_bill() -> None:
    """The free allowance belongs to the organisation and is shared with
    every other private repository it owns. A reader must not be able to
    mistake a per-repository sum for an invoice."""
    usage = _summarise(_minute_runs(_rate_boundary()))
    body = actions_usage.message(usage, actions_usage.alarms(usage, _real_budget()))
    assert body is not None
    assert actions_usage.LOWER_BOUND_NOTE in body
    assert "data/actions-usage.yml" in body


def test_the_message_names_no_person() -> None:
    """No actor, no commit author, no branch: those fields are never read
    out of the payload, so there is no path by which one could appear."""
    payload = _run(run_id=1, jobs=(60_000,) * 400)
    payload["run"]["actor"] = {"login": "a-real-person"}
    payload["run"]["head_branch"] = "a-real-person/branch"
    usage = _summarise([payload])
    body = actions_usage.message(usage, actions_usage.alarms(usage, _real_budget()))
    assert body is not None
    assert "a-real-person" not in body


# ==================================================================== #
# The committed record
# ==================================================================== #


def test_the_record_replaces_todays_row_rather_than_duplicating_it() -> None:
    """A `workflow_dispatch` on a morning the schedule already fired must
    correct the day, not add a second row for it."""
    usage = _summarise(_minute_runs(2))
    first = actions_usage.record_to_data(usage, [])
    second = actions_usage.record_to_data(usage, first["history"])
    assert len(second["history"]) == 1


def test_the_record_keeps_its_history_bounded() -> None:
    previous = [
        {"day": f"2026-06-{day:02d}", "runs": 0, "minutes": 0} for day in range(1, 31)
    ] + [{"day": f"2026-07-{day:02d}", "runs": 0, "minutes": 0} for day in range(1, 32)]
    assert len(previous) > actions_usage.HISTORY_LENGTH
    data = actions_usage.record_to_data(_summarise(_minute_runs(1)), previous)
    assert len(data["history"]) == actions_usage.HISTORY_LENGTH
    assert data["history"][-1]["day"] == "2026-08-24"


def test_the_history_rows_key_the_day_as_day_and_not_as_on() -> None:
    """PyYAML implements YAML 1.1, whose bool resolver reads a bare `on`
    as `True` -- the same trap `conftest.py` documents for a workflow's
    own `on:` block. The writer quotes it; a volunteer hand-editing the
    file would not."""
    data = actions_usage.record_to_data(_summarise(_minute_runs(1)), [])
    assert set(data["history"][-1]) >= {"day"}
    assert "on" not in data["history"][-1]


def test_a_hand_mangled_history_costs_the_trend_and_never_the_alarm() -> None:
    """Deliberately the opposite tolerance from `budget_from_data`: losing
    two months of trend to a hand edit is a shame, refusing to check the
    budget over one would be the control failing over its own scrapbook."""
    assert actions_usage.history_from_data({"v": 1, "history": "nonsense"}) == []
    assert actions_usage.history_from_data(None) == []


@pytest.mark.parametrize(
    "data",
    [
        None,
        {"v": 2, "latest": {"observed_on": "2026-08-24"}},
        {"v": 1},
        {"v": 1, "latest": {"observed_on": 20260824}},
        {"v": 1, "latest": {"observed_on": "2026-13-99"}},
    ],
)
def test_observed_on_refuses_anything_not_the_exact_shape(data: Any) -> None:
    """A malformed record must not read as a healthy one: that is the one
    mistake that would turn this whole fix into a checkmark over a
    silence."""
    with pytest.raises(ValueError):
        actions_usage.observed_on_from_data(data)


def test_the_staleness_boundary() -> None:
    assert not actions_usage.is_stale(2, 2)
    assert actions_usage.is_stale(3, 2)
    assert not actions_usage.is_stale(-1, 2)


def test_the_committed_record_is_readable_by_its_own_reader() -> None:
    """`data/actions-usage.yml` ships committed, so a person can read what
    the runs cost by opening this repository -- no CI, no job log. If the
    file this repository actually holds ever stops parsing, the watchdog
    goes red on it, so it must parse here too."""
    loaded = safe_load(actions_usage.usage_path(_ROOT).read_text(encoding="utf-8"))
    assert isinstance(actions_usage.observed_on_from_data(loaded), date)


# ==================================================================== #
# cli.py: the three commands, end to end, offline
# ==================================================================== #


class _FixedDatetime:
    """A stand-in for the `datetime` class `cli.py` imports, whose `now()`
    always returns the same instant -- the same idiom
    `test_retention_liveness.py::_FixedDatetime` uses."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self, tz: Any = None) -> datetime:
        return self._fixed


def _set_today(monkeypatch: pytest.MonkeyPatch, today: date) -> None:
    monkeypatch.setattr(
        "convener_ops.cli.datetime",
        _FixedDatetime(datetime(today.year, today.month, today.day, 9, 0, tzinfo=UTC)),
    )


def _instance(tmp_path: Path, payloads: list[Any]) -> Path:
    """A temporary repository root holding the thresholds this repository
    really ships and a collected input file. Nothing is stubbed but the
    clock and the collector's own output."""
    import json

    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "actions-budget.yml").write_text(
        actions_usage.budget_path(_ROOT).read_text(encoding="utf-8"), encoding="utf-8"
    )
    source = tmp_path / "actions-usage-input.jsonl"
    source.write_text(
        "".join(f"{json.dumps(payload)}\n" for payload in payloads), encoding="utf-8"
    )
    return source


def test_record_actions_usage_writes_the_record_and_stays_green_when_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One half of the proof the brief asks for: data just below the line,
    watched staying quiet."""
    _instance(tmp_path, _minute_runs(_rate_boundary() - 1))
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))

    assert record_actions_usage() == 0
    captured = capsys.readouterr()
    assert "::error::" not in captured.err
    assert "budget_alert=false" in captured.out
    assert not (tmp_path / "budget-body.md").exists()

    loaded = safe_load(actions_usage.usage_path(tmp_path).read_text(encoding="utf-8"))
    assert loaded["latest"]["observed_on"] == "2026-08-24"
    assert loaded["latest"]["billed_minutes"] == _rate_boundary() - 1


def test_record_actions_usage_fires_loudly_when_the_rate_crosses_the_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half: one minute more, watched going off -- an
    `::error::` annotation, `budget_alert=true` for the workflow step that
    fails the job on it, and a body addressed to the board's own thread."""
    _instance(tmp_path, _minute_runs(_rate_boundary()))
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_NOTIFY_THREAD", "12")
    monkeypatch.setenv("CONVENER_NOTIFY_MENTION", "@example/editorial")
    _set_today(monkeypatch, date(2026, 8, 24))

    assert record_actions_usage() == 0
    captured = capsys.readouterr()
    assert "::error::[rate]" in captured.err
    assert "budget_alert=true" in captured.out

    body = (tmp_path / "budget-body.md").read_text(encoding="utf-8")
    assert body.startswith("@example/editorial")
    assert actions_usage.LOWER_BOUND_NOTE in body


def test_the_alarm_is_loud_even_with_no_channel_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unconfigured integration must never be able to turn a real
    finding into silence. No channel means no comment; it does not mean no
    alarm -- `budget_alert=true` still goes out, and the workflow's own
    last step fails the job on it."""
    _instance(tmp_path, _minute_runs(_rate_boundary()))
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("CONVENER_NOTIFY_THREAD", raising=False)
    monkeypatch.delenv("CONVENER_NOTIFY_MENTION", raising=False)
    _set_today(monkeypatch, date(2026, 8, 24))

    assert record_actions_usage() == 0
    captured = capsys.readouterr()
    assert "budget_alert=true" in captured.out
    assert "::error::" in captured.err
    assert not (tmp_path / "budget-body.md").exists()


def test_record_actions_usage_refuses_to_report_zero_when_nothing_was_collected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty file is a real answer -- nothing ran. A *missing* one means
    the collector step never wrote anything, and reporting that as
    '0 minutes, all healthy' is exactly the silence this feature exists to
    prevent."""
    _instance(tmp_path, [])
    (tmp_path / "actions-usage-input.jsonl").unlink()
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))

    assert record_actions_usage() == 1
    assert "::error::" in capsys.readouterr().err


def test_record_actions_usage_refuses_unreadable_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _instance(tmp_path, [])
    (tmp_path / "config" / "actions-budget.yml").write_text(
        "v: 1\nmonthly_minutes: what\n", encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))

    assert record_actions_usage() == 1
    assert "::error::" in capsys.readouterr().err


def test_record_actions_usage_is_idempotent_the_same_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors the workflow's own commit step, which stages nothing once
    the file already says this (`git diff --staged --quiet`), and which
    re-runs this command inside its retry loop after a hard reset."""
    _instance(tmp_path, _minute_runs(3))
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))

    assert record_actions_usage() == 0
    first = actions_usage.usage_path(tmp_path).read_text(encoding="utf-8")
    assert record_actions_usage() == 0
    assert actions_usage.usage_path(tmp_path).read_text(encoding="utf-8") == first


def test_actions_usage_window_derives_the_window_from_the_same_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The days the collector fetches and the days the rate divides by are
    the same number, or the projection is a wrong answer delivered
    confidently."""
    _instance(tmp_path, [])
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _set_today(monkeypatch, date(2026, 8, 24))

    assert actions_usage_window() == 0
    out = capsys.readouterr().out
    since = actions_usage.window_start(date(2026, 8, 24), _real_budget()).isoformat()
    assert f"since={since}" in out
    assert f"max_runs={_real_budget().max_runs}" in out


def test_actions_usage_window_refuses_unreadable_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))
    assert actions_usage_window() == 1
    assert "::error::" in capsys.readouterr().err


# -------------------------------------------------------------------- #
# check_actions_usage_liveness(): has the alarm itself stopped running?
# -------------------------------------------------------------------- #


def test_the_liveness_check_fires_when_the_measurement_has_gone_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An alarm hosted inside the daily job it watches cannot report its
    own silence -- and an exhausted budget is one of the things that stops
    that job. This is the command the second, independent schedule runs."""
    _instance(tmp_path, _minute_runs(1))
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 18))
    assert record_actions_usage() == 0

    _set_today(monkeypatch, date(2026, 8, 24))
    assert check_actions_usage_liveness() == 1
    err = capsys.readouterr().err
    assert "::error::" in err
    assert "2026-08-18" in err


def test_the_liveness_check_is_green_when_the_measurement_is_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _instance(tmp_path, _minute_runs(1))
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))
    assert record_actions_usage() == 0

    assert check_actions_usage_liveness() == 0
    captured = capsys.readouterr()
    assert "::error::" not in captured.err
    assert "healthy" in captured.out


def test_the_liveness_check_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _instance(tmp_path, _minute_runs(1))
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 20))
    assert record_actions_usage() == 0

    _set_today(monkeypatch, date(2026, 8, 20 + _real_budget().max_silent_days))
    assert check_actions_usage_liveness() == 0
    _set_today(monkeypatch, date(2026, 8, 21 + _real_budget().max_silent_days))
    assert check_actions_usage_liveness() == 1


def test_the_liveness_check_treats_a_missing_record_as_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not the ordinary D-13 'an integration that may not exist yet'
    state: it means the daily job has never once landed this record,
    which is the silence this command exists to report."""
    _instance(tmp_path, [])
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))
    assert check_actions_usage_liveness() == 1
    assert "::error::" in capsys.readouterr().err


def test_the_liveness_check_refuses_a_malformed_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _instance(tmp_path, [])
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    actions_usage.usage_path(tmp_path).write_text(
        "v: 1\nlatest: []\n", encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))
    assert check_actions_usage_liveness() == 1
    assert "::error::" in capsys.readouterr().err


def test_a_line_the_collector_left_unreadable_is_counted_as_uncosted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Blank lines are nothing; a line that is not JSON is a run whose
    cost could not be read, and it says so loudly rather than vanishing
    from the total."""
    source = _instance(tmp_path, _minute_runs(2))
    source.write_text(
        source.read_text(encoding="utf-8") + "\n{ this is not json\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))

    assert record_actions_usage() == 0
    captured = capsys.readouterr()
    assert "::error::[unreadable]" in captured.err
    assert "budget_alert=true" in captured.out
    loaded = safe_load(actions_usage.usage_path(tmp_path).read_text(encoding="utf-8"))
    assert loaded["latest"]["runs"] == 3
    assert loaded["latest"]["uncosted_runs"] == 1


def test_an_unreadable_previous_record_costs_the_trend_and_not_the_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Today's window is measured from today's API answer and depends on
    nothing in the old file. A hand-mangled record restarts the trend and
    warns; it does not stop the budget being checked."""
    _instance(tmp_path, _minute_runs(2))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    actions_usage.usage_path(tmp_path).write_text("v: 1\n  bad: [\n", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))

    assert record_actions_usage() == 0
    assert "::warning::" in capsys.readouterr().out
    loaded = safe_load(actions_usage.usage_path(tmp_path).read_text(encoding="utf-8"))
    assert len(loaded["history"]) == 1


def test_thresholds_that_are_not_valid_yaml_stop_both_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _instance(tmp_path, _minute_runs(1))
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))
    assert record_actions_usage() == 0

    (tmp_path / "config" / "actions-budget.yml").write_text(
        "v: 1\n  broken: [\n", encoding="utf-8"
    )
    capsys.readouterr()
    assert record_actions_usage() == 1
    assert check_actions_usage_liveness() == 1
    assert capsys.readouterr().err.count("::error::") == 2


def test_the_liveness_check_refuses_a_record_that_is_not_valid_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _instance(tmp_path, [])
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    actions_usage.usage_path(tmp_path).write_text("v: 1\n  bad: [\n", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 24))
    assert check_actions_usage_liveness() == 1
    assert "invalid YAML" in capsys.readouterr().err


# ==================================================================== #
# The two workflow files: what no offline command can see
# ==================================================================== #


def _loaded(path: Path) -> WorkflowYaml:
    loaded = safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _steps(path: Path, job: str) -> list[dict[str, Any]]:
    steps = _loaded(path)["jobs"][job]["steps"]
    assert isinstance(steps, list)
    return steps


def _runs(path: Path, job: str) -> str:
    return " ".join(
        step["run"] for step in _steps(path, job) if isinstance(step.get("run"), str)
    )


def test_measuring_the_cost_added_no_workflow_and_no_job() -> None:
    """The constraint that shapes this whole feature: a workflow or a job
    created to watch the cost would cost a billed job every day, which is
    self-defeating. Every command lives in a job that already ran."""
    hosting = {
        path.name
        for path in _WORKFLOWS.glob("*.yml")
        if "convener-record-actions-usage" in path.read_text(encoding="utf-8")
        or "convener-actions-usage-window" in path.read_text(encoding="utf-8")
        or "convener-check-actions-usage-liveness" in path.read_text(encoding="utf-8")
    }
    assert hosting == {"sweep-and-notify.yml", "retention-watchdog.yml"}
    assert set(_loaded(_SWEEP_PATH)["jobs"]) == {"immediate", "daily"}
    assert set(_loaded(_WATCHDOG_PATH)["jobs"]) == {"watchdog"}


def test_the_daily_job_measures_and_the_push_job_does_not() -> None:
    """`immediate` reacts to a human's push and needs `contents: read` and
    nothing else. Measuring there would hand it permissions it has no use
    for, and would bill the measurement on every push as well."""
    assert "convener-record-actions-usage" in _runs(_SWEEP_PATH, "daily")
    assert "convener-record-actions-usage" not in _runs(_SWEEP_PATH, "immediate")


def test_the_daily_job_reads_the_billed_timing_not_a_wall_clock() -> None:
    """GitHub bills per job, rounded up. Only `/timing` reports the
    per-job durations that rounding applies to."""
    script = _runs(_SWEEP_PATH, "daily")
    assert "/timing" in script
    assert "actions/runs" in script


def test_the_daily_job_needs_no_permission_beyond_what_it_already_had() -> None:
    """`actions: read` is what the two endpoints need, and `actions:
    write` -- already there for the publish-vitrine dispatch -- includes
    it. Least privilege here means adding nothing, not adding a line."""
    permissions = _loaded(_SWEEP_PATH)["jobs"]["daily"]["permissions"]
    assert permissions == {
        "contents": "write",
        "actions": "write",
        "issues": "write",
    }
    assert "actions" not in _loaded(_SWEEP_PATH)["jobs"]["immediate"]["permissions"]


def test_the_budget_alarm_fails_the_job_whether_or_not_a_channel_exists() -> None:
    """D-25, and the one decision deliberately kept in YAML: the failing
    step's `if:` reads the command's own output and nothing about a
    notification channel, so an unconfigured integration cannot turn a
    real finding into silence."""
    failing = [
        step
        for step in _steps(_SWEEP_PATH, "daily")
        if step.get("name") == "Fail if the budget is running out"
    ]
    assert len(failing) == 1
    condition = failing[0]["if"]
    assert "steps.usage.outputs.budget_alert == 'true'" in condition
    assert "hashFiles" not in condition
    assert "exit 1" in failing[0]["run"]


def test_the_budget_alarm_posts_on_its_own_file_not_the_digests() -> None:
    """One file for two messages composed in the same job means whichever
    is written last silently replaces the other."""
    posting = [
        step
        for step in _steps(_SWEEP_PATH, "daily")
        if step.get("name") == "Tell the board the budget is going"
    ]
    assert len(posting) == 1
    assert "budget-body.md" in posting[0]["run"]
    assert "notify-body.md" not in posting[0]["run"]


def test_the_budget_alarm_uses_the_channel_this_project_already_has() -> None:
    """D-07: a comment on a repository thread that mentions the board's
    team, which the platform then turns into email. No second address
    book, no mail provider, no subscription."""
    posting = " ".join(
        step["run"]
        for step in _steps(_SWEEP_PATH, "daily")
        if isinstance(step.get("run"), str) and "budget-body.md" in step["run"]
    )
    assert "gh issue comment" in posting


def test_the_measurement_secrets_are_declared_at_the_step_not_the_job() -> None:
    """The measuring code must not be able to see the board's channel
    except while it is composing a message for it -- the same rule the two
    Compose steps hold themselves to."""
    assert "env" not in _loaded(_SWEEP_PATH)["jobs"]["daily"] or set(
        _loaded(_SWEEP_PATH)["jobs"]["daily"]["env"]
    ) == {"TARGET_BRANCH"}


def test_the_measurement_re_derives_rather_than_rebases_on_a_rejected_push() -> None:
    """The same defence every other retry loop in this repository uses."""
    recording = [
        step
        for step in _steps(_SWEEP_PATH, "daily")
        if step.get("name") == "Record what those runs cost"
    ]
    assert len(recording) == 1
    script = recording[0]["run"]
    commands = [
        line for line in script.splitlines() if not line.strip().startswith("#")
    ]
    assert not any("git rebase" in line for line in commands)
    assert not any("git pull" in line for line in commands)
    assert 'git fetch origin "$TARGET_BRANCH"' in script
    assert 'git reset --hard "origin/$TARGET_BRANCH"' in script
    assert "git add data/actions-usage.yml" in script


def test_the_watchdog_also_asks_whether_the_alarm_itself_still_runs() -> None:
    """A second, independent schedule -- and a step, not a job: this job
    already runs daily, so the extra question is free."""
    assert "convener-check-actions-usage-liveness" in _runs(_WATCHDOG_PATH, "watchdog")
    assert _loaded(_WATCHDOG_PATH)["jobs"]["watchdog"]["permissions"] == {
        "contents": "read"
    }


def test_the_watchdogs_two_checks_do_not_hide_each_other() -> None:
    """A stale retention record and a dead budget alarm are two separate
    findings. The second must run even when the first has already gone
    red, or one silence would hide another."""
    step = next(
        step
        for step in _steps(_WATCHDOG_PATH, "watchdog")
        if isinstance(step.get("run"), str)
        and "convener-check-actions-usage-liveness" in step["run"]
    )
    assert "always()" in step["if"]


def test_the_watchdog_still_runs_later_in_the_day_than_what_it_watches() -> None:
    """`sweep-and-notify.yml`'s daily cron is 05:00 UTC; the watchdog's
    hour must be later, so a healthy day's record is already written by
    the time this checks it. Never a same-day race, the same property
    `test_retention_watchdog_workflow.py` pins against retention.yml."""
    watchdog_cron = _loaded(_WATCHDOG_PATH)[True]["schedule"][0]["cron"]
    sweep_cron = _loaded(_SWEEP_PATH)[True]["schedule"][0]["cron"]
    assert int(watchdog_cron.split()[1]) > int(sweep_cron.split()[1])
