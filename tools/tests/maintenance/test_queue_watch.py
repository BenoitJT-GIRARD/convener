"""Nothing detects a submission that entered the queue and
was never handled.

Every failure *inside* a drain is already loud (`test_submission_queue.py`).
This module covers the one that is not: a submission nobody looked at. The
submitter had their answer from the relay and believes they are registered;
the repository has nothing red; the drain may not even have run.

Three layers, mirroring the split `test_retention_liveness.py` and
`test_actions_usage.py` already use:

* `queue_watch.py`'s own pure functions -- the record's shape, the carrying
  forward of an entry's age, the two boundaries a real run actually hits,
  and the bounds the configured threshold has to sit inside;
* `cli.py`'s `record_queue_watch` and `check_queue_liveness` -- the two
  commands the daily job and the watchdog actually run. This is the "prove
  it" half: drive a stuck queue and watch the alarm fire, drive the same
  queue an hour under the threshold and watch it stay silent, drive a
  healthy queue filling and draining, drive the missing-key case and read
  the message, and drive the drain having stopped altogether;
* the two workflow files, read as text and `safe_load`-parsed -- never
  parsed and executed, which here would mean a real push.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import workflow_triggers

from convener_ops.cli import check_queue_liveness, record_queue_watch
from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.yaml_safe import safe_load
from convener_ops.journey import registration_routing
from convener_ops.maintenance import queue_watch

_ROOT = repo_root()
_SWEEP_PATH = _ROOT / ".github" / "workflows" / "sweep-and-notify.yml"
_WATCHDOG_PATH = _ROOT / ".github" / "workflows" / "retention-watchdog.yml"
_SWEEP = _SWEEP_PATH.read_text(encoding="utf-8")
_WATCHDOG = _WATCHDOG_PATH.read_text(encoding="utf-8")

_NOW = datetime(2026, 8, 24, 5, 0, tzinfo=UTC)
_ENTRY = "queue/registration/m1-11111111-2222-3333-4444-555555555555.json"
_OTHER = "queue/survey/m2-66666666-7777-8888-9999-aaaaaaaaaaaa.json"


def _hours(count: float) -> datetime:
    """The instant `count` hours before `_NOW`."""
    return _NOW - timedelta(hours=count)


# ==================================================================== #
# 1 - queue_watch.py: the record's shape
# ==================================================================== #


def test_record_round_trips_through_its_own_data_form() -> None:
    record = queue_watch.Record(
        observed_at=_NOW,
        waiting=(queue_watch.Waiting(_ENTRY, _hours(48), "no key"),),
    )
    data = queue_watch.record_to_data(record)
    assert data == {
        "v": 1,
        "observed_at": "2026-08-24T05:00:00Z",
        "waiting": [
            {
                "entry": _ENTRY,
                "since": "2026-08-22T05:00:00Z",
                "reason": "no key",
            }
        ],
    }
    assert queue_watch.record_from_data(data) == record


def test_record_to_data_orders_oldest_first_so_two_drains_write_one_file() -> None:
    """Deterministic bytes, the same property `submission_queue.
    ledger_to_data` holds: a record that reordered itself would commit on
    every drain and drown the one commit that means something."""
    record = queue_watch.Record(
        observed_at=_NOW,
        waiting=(
            queue_watch.Waiting(_OTHER, _hours(1)),
            queue_watch.Waiting(_ENTRY, _hours(50)),
        ),
    )
    entries = [item["entry"] for item in queue_watch.record_to_data(record)["waiting"]]
    assert entries == [_ENTRY, _OTHER]


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "not a dict",
        {"v": 2, "observed_at": "2026-08-24T05:00:00Z", "waiting": []},
        {"v": 1, "waiting": []},
        {"v": 1, "observed_at": 20260824, "waiting": []},
        {"v": 1, "observed_at": "2026-08-24", "waiting": []},
        {"v": 1, "observed_at": "2026-08-24T05:00:00Z"},
        {"v": 1, "observed_at": "2026-08-24T05:00:00Z", "waiting": "no"},
        {"v": 1, "observed_at": "2026-08-24T05:00:00Z", "waiting": ["no"]},
        {"v": 1, "observed_at": "2026-08-24T05:00:00Z", "waiting": [{"since": "x"}]},
        {
            "v": 1,
            "observed_at": "2026-08-24T05:00:00Z",
            "waiting": [{"entry": "a", "since": "nope"}],
        },
        {
            "v": 1,
            "observed_at": "2026-08-24T05:00:00Z",
            "waiting": [{"entry": "a", "since": "2026-08-24T05:00:00Z", "reason": 7}],
        },
    ],
)
def test_record_from_data_refuses_anything_not_the_exact_shape(data: Any) -> None:
    """A record this function guessed at is an age it invented, and an age
    it invented is either an alarm nobody earned or silence nobody did."""
    with pytest.raises(ValueError):
        queue_watch.record_from_data(data)


@pytest.mark.parametrize(
    "data",
    [
        None,
        {"v": 2, "alarm_after_hours": 48, "max_silent_days": 2},
        {"v": 1, "max_silent_days": 2},
        {"v": 1, "alarm_after_hours": 48},
        {"v": 1, "alarm_after_hours": 0, "max_silent_days": 2},
        {"v": 1, "alarm_after_hours": -1, "max_silent_days": 2},
        {"v": 1, "alarm_after_hours": True, "max_silent_days": 2},
        {"v": 1, "alarm_after_hours": 48.0, "max_silent_days": 2},
        {"v": 1, "alarm_after_hours": 48, "max_silent_days": 0},
    ],
)
def test_thresholds_from_data_refuses_anything_not_the_exact_shape(data: Any) -> None:
    with pytest.raises(ValueError):
        queue_watch.thresholds_from_data(data)


def test_flatten_reason_puts_a_multi_line_parser_error_on_one_line() -> None:
    """A deferral's reason can be a YAML parser's own several-line message.
    A newline in a file whose format is one entry per line makes the next
    read take half an error message for an entry path."""
    assert queue_watch.flatten_reason("line one\n  line two\t\tend") == (
        "line one line two end"
    )


# ==================================================================== #
# 2 - queue_watch.py: the age, and where it comes from
# ==================================================================== #


def test_next_record_starts_the_clock_for_an_entry_nobody_had_seen() -> None:
    record = queue_watch.next_record(None, {_ENTRY: "no key"}, _NOW)
    assert record.observed_at == _NOW
    assert record.waiting == (queue_watch.Waiting(_ENTRY, _NOW, "no key"),)


def test_next_record_carries_forward_the_instant_an_entry_was_first_seen() -> None:
    """The whole of why an age is an age. Lose this and every entry looks
    new on every drain, which is permanent silence."""
    previous = queue_watch.Record(
        observed_at=_hours(24), waiting=(queue_watch.Waiting(_ENTRY, _hours(72)),)
    )
    record = queue_watch.next_record(previous, {_ENTRY: ""}, _NOW)
    assert record.waiting[0].since == _hours(72)


def test_next_record_forgets_an_entry_that_is_no_longer_in_the_queue() -> None:
    """Self-pruning, exactly as `submission_queue.next_ledger` is: an entry
    that has been cleared is done, entry ids are unique, and carrying it
    would be carrying an alarm about a submission that is finished."""
    previous = queue_watch.Record(
        observed_at=_hours(24),
        waiting=(
            queue_watch.Waiting(_ENTRY, _hours(72)),
            queue_watch.Waiting(_OTHER, _hours(72)),
        ),
    )
    record = queue_watch.next_record(previous, {_OTHER: ""}, _NOW)
    assert [item.entry for item in record.waiting] == [_OTHER]


def test_next_record_keeps_an_older_reason_when_this_run_recorded_none() -> None:
    """A run that never reached the drain step records no reason for
    anything, and "no private key configured for event X" from yesterday is
    worth more to the operator than a blank today."""
    previous = queue_watch.Record(
        observed_at=_hours(24),
        waiting=(queue_watch.Waiting(_ENTRY, _hours(72), "no private key"),),
    )
    record = queue_watch.next_record(previous, {_ENTRY: ""}, _NOW)
    assert record.waiting[0].reason == "no private key"


def test_next_record_prefers_this_run_s_reason_when_it_has_one() -> None:
    previous = queue_watch.Record(
        observed_at=_hours(24),
        waiting=(queue_watch.Waiting(_ENTRY, _hours(72), "no private key"),),
    )
    record = queue_watch.next_record(previous, {_ENTRY: "eight events waiting"}, _NOW)
    assert record.waiting[0].reason == "eight events waiting"


def test_hours_waiting_rounds_up_so_schedule_jitter_cannot_postpone_it() -> None:
    """Two drain periods measured across GitHub's own ten-to-twenty-minute
    lateness is 47h20m, and floored that is 47 -- one hour short of a
    48-hour threshold, and the alarm silently waits a whole further day.
    Rounding up spends the error in the only direction a control may err."""
    assert queue_watch.hours_waiting(_hours(47 + 20 / 60), _NOW) == 48


def test_hours_waiting_is_exact_on_a_whole_hour() -> None:
    assert queue_watch.hours_waiting(_hours(48), _NOW) == 48


def test_hours_waiting_of_a_record_dated_in_the_future_is_not_positive() -> None:
    """A hand edit or a clock skew between two runners. `is_overdue` reads
    it as healthy; this function only ever measures elapsed time."""
    assert queue_watch.hours_waiting(_NOW + timedelta(hours=5), _NOW) <= 0


def test_is_overdue_fires_exactly_at_the_threshold() -> None:
    """`>=`, not `>`. A drain only ever observes at whole multiples of its
    own period, so `>` would push every alarm a full further period past
    the value the maintainer chose."""
    assert queue_watch.is_overdue(48, 48) is True


def test_is_overdue_is_silent_one_hour_under_the_threshold() -> None:
    assert queue_watch.is_overdue(47, 48) is False


def test_overdue_returns_the_oldest_first() -> None:
    record = queue_watch.Record(
        observed_at=_NOW,
        waiting=(
            queue_watch.Waiting(_OTHER, _hours(50)),
            queue_watch.Waiting(_ENTRY, _hours(99)),
        ),
    )
    stuck = queue_watch.overdue(record, _NOW, 48)
    assert [item.entry for item in stuck] == [_ENTRY, _OTHER]


def test_is_stale_boundary_exactly_at_max_silent_days_is_still_healthy() -> None:
    assert queue_watch.is_stale(2, 2) is False


def test_is_stale_boundary_one_day_past_is_stale() -> None:
    assert queue_watch.is_stale(3, 2) is True


# ==================================================================== #
# 3 - the threshold is configuration, and it is bounded by the drain
# ==================================================================== #


def _drain_period_hours() -> int:
    workflow = safe_load(_SWEEP.replace("\r\n", "\n"))
    assert isinstance(workflow, dict)
    return registration_routing.drain_period_hours(workflow)


def _configured() -> queue_watch.Thresholds:
    return queue_watch.thresholds_from_data(
        safe_load(queue_watch.config_path(_ROOT).read_text(encoding="utf-8"))
    )


def test_the_threshold_lives_beside_the_other_declarations() -> None:
    """Never `instance/data/config.yml`: the app's validator refuses by
    name any key it does not know and would delete it at the next Board
    edit, which has happened. It sits at the top of `instance/`, beside
    the other two thresholds, which is what `deploy.yml` ignores."""
    assert queue_watch.CONFIG_PATH.parent.as_posix() == "instance"
    assert queue_watch.config_path(_ROOT).is_file()
    assert (_ROOT / "instance" / "actions-budget.yml").is_file()
    assert (_ROOT / "instance" / "registration-lanes.yml").is_file()


def test_the_configured_alarm_sits_inside_the_bounds_the_drain_sets() -> None:
    """The threshold does not float free: both ends of it are derived from
    the drain's own cron (`registration_routing.drain_period_hours`, task
    3's, reused rather than restated) and from the lane threshold.

    Below the floor it fires before a healthy drain has had its chance, and
    an alarm people learn to ignore is not a control. Above the ceiling it
    tells the operator about a stuck registration as its seminar begins,
    which is a post-mortem.
    """
    period = _drain_period_hours()
    lane = registration_routing.threshold_from_data(
        safe_load(
            (_ROOT / registration_routing.CONFIG_PATH).read_text(encoding="utf-8")
        )
    )
    floor, ceiling = queue_watch.alarm_bounds(period, lane)
    assert floor <= ceiling, (
        f"instance/registration-lanes.yml's queue_beyond_hours ({lane}) is cut "
        f"so close to the drain's {period}-hour period that no alarm can "
        "both wait for a healthy drain and still leave anybody time to act "
        f"(floor {floor}, ceiling {ceiling}) -- the lane threshold is what "
        "has to move, not this one"
    )
    configured = _configured().alarm_after_hours
    assert floor <= configured <= ceiling, (
        f"instance/queue-drain.yml's alarm_after_hours ({configured}) is "
        f"outside the {floor}..{ceiling} hours the drain's own cadence and "
        "the registration lane leave for it"
    )


def test_the_configured_silence_tolerance_covers_the_drains_own_period() -> None:
    period = _drain_period_hours()
    assert _configured().max_silent_days >= queue_watch.silence_floor_days(period)


def test_alarm_bounds_cross_when_the_lane_is_cut_to_its_own_floor() -> None:
    """Driven rather than asserted about the live files: at a lane
    threshold equal to its own floor there is no legal alarm at all, and
    that is a real finding about the pair of settings, not a broken test."""
    floor, ceiling = queue_watch.alarm_bounds(24, registration_routing.floor_hours(24))
    assert floor > ceiling


def test_silence_floor_is_never_below_a_day_however_often_the_drain_runs() -> None:
    """A record that had to move every hour would call one dropped schedule
    a dead drain -- the false alarm `retention_liveness.MAX_SILENT_DAYS`
    already declines to raise."""
    assert queue_watch.silence_floor_days(1) == 1


# ==================================================================== #
# 4 - the message, and what may never be in it
# ==================================================================== #


def test_no_alarm_composes_no_message() -> None:
    assert queue_watch.message((), (), _NOW) is None


def test_the_message_names_what_is_stuck_and_for_how_long() -> None:
    stuck = (queue_watch.Waiting(_ENTRY, _hours(72), "no private key for abc-04"),)
    body = queue_watch.message(queue_watch.alarms(stuck, _NOW), stuck, _NOW)
    assert body is not None
    assert _ENTRY in body
    assert "72 hour(s)" in body
    assert "no private key for abc-04" in body


def test_the_message_and_the_annotations_are_bounded() -> None:
    """An unbounded list is a comment body past what GitHub accepts, i.e.
    no message at all -- the exact silence this control exists to refuse.
    The count stays exact; only the enumeration is trimmed."""
    stuck = tuple(
        queue_watch.Waiting(f"queue/survey/e{n}.json", _hours(99))
        for n in range(queue_watch.MOST_LISTED + 5)
    )
    fired = queue_watch.alarms(stuck, _NOW)
    body = queue_watch.message(fired, stuck, _NOW)
    assert body is not None
    assert f"{len(stuck)} public submission(s)" in body
    assert "and 5 more" in body
    lines = queue_watch.annotation_lines(fired, stuck)
    named = [line for line in lines if line.startswith("::error::queue/survey/e")]
    assert len(named) == queue_watch.MOST_LISTED
    assert any("and 5 more" in line for line in lines)


def test_a_lost_history_is_its_own_alarm_and_not_a_quiet_restart() -> None:
    """Losing the record loses every age, which buys silence for whatever
    was already stuck. A control that can only ever report "fine" is not a
    control (D-25)."""
    fired = queue_watch.alarms((), _NOW, restarted=True)
    assert [alarm.kind for alarm in fired] == [queue_watch.RESTARTED_ALARM]
    body = queue_watch.message(fired, (), _NOW)
    assert body is not None and "restarts from now" in body


# ==================================================================== #
# 5 - cli.py: the five proofs, driven
# ==================================================================== #


class _FixedDatetime:
    """A stand-in for the `datetime` class `cli.py` imports, whose `now()`
    always returns the same instant -- the same idiom
    `test_retention_liveness.py::_FixedDatetime` uses."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self, tz: Any = None) -> datetime:
        return self._fixed


def _repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, now: datetime) -> Path:
    """A repository root holding only what these two commands read."""
    (tmp_path / "instance" / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "instance" / "data" / "config.yml").write_text(
        "season: 2026\n", encoding="utf-8"
    )
    (tmp_path / "instance").mkdir(parents=True, exist_ok=True)
    (tmp_path / "instance" / "queue-drain.yml").write_text(
        "v: 1\nalarm_after_hours: 48\nmax_silent_days: 2\n", encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("CONVENER_NOTIFY_THREAD", raising=False)
    monkeypatch.delenv("CONVENER_NOTIFY_MENTION", raising=False)
    monkeypatch.setattr("convener_ops.cli.datetime", _FixedDatetime(now))
    return tmp_path


def _drive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    now: datetime,
    waiting: dict[str, str],
) -> Path:
    """One run of the daily job's recording step: the workflow's listing of
    the queue branch, and the drain's own deferral reasons."""
    listing = tmp_path / "queue-waiting.txt"
    listing.write_text("".join(f"{name}\n" for name in waiting), encoding="utf-8")
    deferred = tmp_path / "queue-deferred.txt"
    deferred.write_text(
        "".join(f"{name}\t{reason}\n" for name, reason in waiting.items() if reason),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONVENER_QUEUE_WAITING_FILE", str(listing))
    monkeypatch.setenv("CONVENER_QUEUE_DEFERRED_FILE", str(deferred))
    monkeypatch.setattr("convener_ops.cli.datetime", _FixedDatetime(now))
    return tmp_path


def _outputs(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        values[key] = value
    return values


def _github_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return out


def test_an_entry_older_than_the_threshold_fires(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proof 1. Two runs 49 hours apart over the same unmoving queue: the
    first starts the clock and is silent, the second is past the threshold
    and says what is stuck and for how long."""
    root = _repo(tmp_path, monkeypatch, _hours(49))
    out = _github_output(tmp_path, monkeypatch)
    _drive(root, monkeypatch, now=_hours(49), waiting={_ENTRY: "no private key"})
    assert record_queue_watch() == 0
    assert _outputs(out)["queue_alert"] == "false"

    _drive(root, monkeypatch, now=_NOW, waiting={_ENTRY: "no private key"})
    assert record_queue_watch() == 0
    assert _outputs(out)["queue_alert"] == "true"
    printed = capsys.readouterr().out
    assert _ENTRY in printed
    assert "49 hour(s)" in printed


def test_the_same_queue_one_hour_under_the_threshold_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proof 2. Identical to the run above but 47 hours apart."""
    root = _repo(tmp_path, monkeypatch, _hours(47))
    out = _github_output(tmp_path, monkeypatch)
    _drive(root, monkeypatch, now=_hours(47), waiting={_ENTRY: "no private key"})
    assert record_queue_watch() == 0

    _drive(root, monkeypatch, now=_NOW, waiting={_ENTRY: "no private key"})
    assert record_queue_watch() == 0
    assert _outputs(out)["queue_alert"] == "false"
    assert "::error::" not in capsys.readouterr().out
    assert not (root / "queue-body.md").exists()


def test_a_queue_filling_and_draining_normally_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proof 3. A week of drains, each one clearing what the last found and
    each one finding new arrivals. The alarm never fires and the record
    never grows."""
    root = _repo(tmp_path, monkeypatch, _NOW)
    out = _github_output(tmp_path, monkeypatch)
    for day in range(7):
        moment = _NOW + timedelta(days=day)
        _drive(
            root,
            monkeypatch,
            now=moment,
            waiting={f"queue/survey/day{day}.json": ""},
        )
        assert record_queue_watch() == 0
        assert _outputs(out)["queue_alert"] == "false"
    record = queue_watch.record_from_data(
        safe_load(queue_watch.watch_path(root).read_text(encoding="utf-8"))
    )
    assert [item.entry for item in record.waiting] == ["queue/survey/day6.json"]


def test_an_entry_stuck_for_a_missing_event_key_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proof 4. The fix for a missing key is not the fix for a full cap, so
    the message has to carry the drain's own reason and not only a count."""
    reason = "no private key configured for event abc-04"
    root = _repo(tmp_path, monkeypatch, _hours(72))
    out = _github_output(tmp_path, monkeypatch)
    _drive(root, monkeypatch, now=_hours(72), waiting={_ENTRY: reason})
    assert record_queue_watch() == 0
    _drive(root, monkeypatch, now=_NOW, waiting={_ENTRY: reason})
    monkeypatch.setenv("CONVENER_NOTIFY_THREAD", "42")
    monkeypatch.setenv("CONVENER_NOTIFY_MENTION", "@example/board")
    assert record_queue_watch() == 0
    assert _outputs(out)["queue_alert"] == "true"
    assert reason in capsys.readouterr().out
    body = (root / "queue-body.md").read_text(encoding="utf-8")
    assert reason in body
    assert "@example/board" in body


def test_the_drain_having_stopped_running_fires(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proof 5, and the case the whole task exists for. The daily job stops
    running, so nothing rewrites the record -- and the check that notices
    lives on `retention-watchdog.yml`'s own separate schedule, because a
    control hosted inside the job that stopped reports nothing."""
    root = _repo(tmp_path, monkeypatch, _NOW)
    _github_output(tmp_path, monkeypatch)
    _drive(root, monkeypatch, now=_NOW, waiting={})
    assert record_queue_watch() == 0

    monkeypatch.setattr(
        "convener_ops.cli.datetime", _FixedDatetime(_NOW + timedelta(days=2))
    )
    assert check_queue_liveness() == 0
    monkeypatch.setattr(
        "convener_ops.cli.datetime", _FixedDatetime(_NOW + timedelta(days=3))
    )
    assert check_queue_liveness() == 1
    assert "no longer being drained" in capsys.readouterr().err


def test_the_liveness_check_reports_a_record_that_was_never_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing file is an error, not a shrug -- the same call
    `check_retention_liveness` makes: it means the daily job has never once
    landed this record."""
    _repo(tmp_path, monkeypatch, _NOW)
    assert check_queue_liveness() == 1
    assert "does not exist" in capsys.readouterr().err


@pytest.mark.parametrize("content", ["v: 1\n  bad: [", "v: 9\n"])
def test_the_liveness_check_refuses_a_record_it_cannot_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    content: str,
) -> None:
    root = _repo(tmp_path, monkeypatch, _NOW)
    queue_watch.watch_path(root).write_text(content, encoding="utf-8")
    assert check_queue_liveness() == 1
    assert "::error::" in capsys.readouterr().err


def test_both_commands_refuse_a_configuration_they_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A threshold with a fallback in code is a constant with extra steps
    -- the identical call `_actions_budget` makes."""
    root = _repo(tmp_path, monkeypatch, _NOW)
    queue_watch.config_path(root).unlink()
    _drive(root, monkeypatch, now=_NOW, waiting={})
    assert record_queue_watch() == 1
    assert check_queue_liveness() == 1


def test_a_listing_that_was_never_taken_is_not_read_as_an_empty_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The lesson retention.yml carries one file over: a question that
    could not be answered is not the answer "nothing", and reading it as
    one is how a control reports that everything is fine while it is not."""
    root = _repo(tmp_path, monkeypatch, _NOW)
    monkeypatch.setenv("CONVENER_QUEUE_WAITING_FILE", str(root / "never-written.txt"))
    assert record_queue_watch() == 1
    assert "not the same as the queue being empty" in capsys.readouterr().err
    monkeypatch.delenv("CONVENER_QUEUE_WAITING_FILE")
    assert record_queue_watch() == 1


def test_a_record_that_cannot_be_read_is_rewritten_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both halves matter. Reported, because a lost history buys silence
    for whatever was already stuck; rewritten anyway, because a record
    frozen by a malformed file would make the watchdog call the drain dead
    when the drain is fine."""
    root = _repo(tmp_path, monkeypatch, _NOW)
    out = _github_output(tmp_path, monkeypatch)
    queue_watch.watch_path(root).write_text("v: 1\n  nope: [", encoding="utf-8")
    _drive(root, monkeypatch, now=_NOW, waiting={_ENTRY: ""})
    assert record_queue_watch() == 0
    assert _outputs(out)["queue_alert"] == "true"
    record = queue_watch.record_from_data(
        safe_load(queue_watch.watch_path(root).read_text(encoding="utf-8"))
    )
    assert record.observed_at == _NOW


def test_an_unconfigured_channel_still_leaves_the_finding_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-13 is the ordinary state here. An unconfigured integration must
    never be able to turn a real finding into silence -- so no body file is
    written and `queue_alert` is still true, which is what the workflow's
    own last step reads."""
    root = _repo(tmp_path, monkeypatch, _hours(72))
    out = _github_output(tmp_path, monkeypatch)
    _drive(root, monkeypatch, now=_hours(72), waiting={_ENTRY: "no key"})
    assert record_queue_watch() == 0
    _drive(root, monkeypatch, now=_NOW, waiting={_ENTRY: "no key"})
    assert record_queue_watch() == 0
    assert _outputs(out)["queue_alert"] == "true"
    assert not (root / "queue-body.md").exists()


# ==================================================================== #
# 6 - the two workflows
# ==================================================================== #


def test_the_recording_step_is_a_step_of_a_job_that_already_runs() -> None:
    """The whole economy of the phase. A workflow or a job created to watch
    the queue would cost a billed run every single day, which is the cost
    this feature exists to remove."""
    assert "uv run convener-record-queue-watch" in _SWEEP
    jobs = safe_load(_SWEEP)
    assert isinstance(jobs, dict)
    assert sorted(jobs["jobs"]) == ["daily", "immediate"]


def test_the_recording_step_runs_even_when_the_drain_failed() -> None:
    """The morning the drain fails is exactly the morning this record has
    to move, or the watchdog reports the *drain* as dead when what actually
    happened is that it ran and could not finish."""
    step = _daily_step("Record what the queue still holds")
    assert step["if"] == "always() && steps.queue-fetch.outcome == 'success'"


def _daily_steps() -> list[dict[str, Any]]:
    workflow = safe_load(_SWEEP)
    assert isinstance(workflow, dict)
    steps = workflow["jobs"]["daily"]["steps"]
    assert isinstance(steps, list)
    return steps


def _daily_step(name: str) -> dict[str, Any]:
    for step in _daily_steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"the daily job has no {name!r} step")


def test_the_record_is_written_after_the_queue_has_been_cleared() -> None:
    """What is still waiting is a fact about the branch tip once every
    other queue step has finished, never something inferred from what they
    intended."""
    order = [step.get("name") for step in _daily_steps()]
    assert order.index("Clear what the drain handled") < order.index(
        "Record what the queue still holds"
    )


def test_the_alarm_uses_the_channel_that_already_exists_with_its_own_body() -> None:
    """D-07: the same thread, the same team mention. A third body filename,
    because several messages composed in one job sharing one filename means
    whichever is written last silently replaces the rest."""
    step = _daily_step("Tell the board the queue is not emptying")
    assert "queue-body.md" in step["run"]
    assert "notify-body.md" not in step["run"]
    assert "budget-body.md" not in step["run"]
    assert step["env"]["THREAD"] == "${{ secrets.CONVENER_NOTIFY_THREAD }}"


def test_an_overdue_entry_turns_the_daily_job_red_on_its_own() -> None:
    """A log line is not a control (D-25): the red run has to happen
    whether or not a channel was configured to post to.

    This does not hand a stranger the colour of the job, which is what
    `submission_queue.annotation_lines` is careful about: a submission
    somebody sends today is handled by tomorrow's drain and never appears
    here, and reaching this threshold takes drains that could not finish
    it, every cause of which is the operator's.
    """
    step = _daily_step("Fail if a submission has been waiting too long")
    assert step["if"] == "always() && steps.queue-watch.outputs.queue_alert == 'true'"
    assert "exit 1" in step["run"]


def test_the_liveness_check_lives_outside_the_job_it_watches() -> None:
    """The point of the whole task. A control hosted in the daily job
    cannot report the daily job going quiet, which is the most likely and
    the most serious way a submission is never handled."""
    assert "convener-check-queue-liveness" in _WATCHDOG
    assert "convener-check-queue-liveness" not in _SWEEP


def test_the_watchdog_stays_read_only_and_secret_free() -> None:
    """Adding this check must not widen what that workflow can do: it reads
    one committed file and calls nothing. The posting happens in the daily
    job, which already holds the channel."""
    workflow = safe_load(_WATCHDOG)
    assert isinstance(workflow, dict)
    assert workflow["jobs"]["watchdog"]["permissions"] == {"contents": "read"}
    assert "secrets." not in _WATCHDOG


def test_the_watchdog_runs_later_in_the_day_than_the_drain_it_watches() -> None:
    """Never a same-day race: a healthy day's record must already be
    written by the time this reads it."""
    drain_hour = int(
        workflow_triggers(safe_load(_SWEEP))["schedule"][0]["cron"].split()[1]
    )
    watch_hour = int(
        workflow_triggers(safe_load(_WATCHDOG))["schedule"][0]["cron"].split()[1]
    )
    assert watch_hour > drain_hour


def test_the_watchdog_names_no_branch_the_daily_job_alone_may_touch() -> None:
    """`test_submission_queue.py`'s own guard says exactly one workflow may
    mention the queue branch. This check reads a committed record on the
    default branch and never goes near that branch, so the guard still
    means what it means rather than having been renamed around."""
    from convener_ops.journey import submission_queue

    assert submission_queue.QUEUE_BRANCH not in _WATCHDOG
    assert "convener-check-queue-liveness" in _WATCHDOG
