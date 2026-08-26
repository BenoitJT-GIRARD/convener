"""Nothing detects `retention.yml` no longer running.

D-25 makes every control fail loudly *inside* a run; it says nothing about
a run that never starts, and `retention.yml` is exactly the job whose
silence has legal weight (D-22) -- it is what makes an event's
registrations permanently unreadable once the retention window elapses.

Two layers, mirroring `test_retention.py`'s own split:

* `retention_liveness.py`'s own pure functions -- the record's shape and
  the staleness arithmetic, including the boundary a real watchdog run
  would actually hit.
* `cli.py`'s `record_retention_run` and `check_retention_liveness` -- the
  two commands `retention.yml` and `retention-watchdog.yml` actually run.
  The second half is the "prove it": simulate the silence and show the
  watchdog firing, then show it silent when retention is healthy.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from convener_ops import retention_liveness
from convener_ops.cli import check_retention_liveness, record_retention_run

# ==================================================================== #
# retention_liveness.py: the pure record shape and staleness arithmetic
# ==================================================================== #


def test_record_to_data_and_last_run_from_data_round_trip() -> None:
    today = date(2026, 8, 23)
    data = retention_liveness.record_to_data(today)
    assert data == {"v": 1, "last_run": "2026-08-23"}
    assert retention_liveness.last_run_from_data(data) == today


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "not a dict",
        {"v": 2, "last_run": "2026-08-23"},
        {"v": 1},
        {"v": 1, "last_run": 20260823},
        {"v": 1, "last_run": "not a date"},
        {"v": 1, "last_run": "2026-13-99"},
    ],
)
def test_last_run_from_data_refuses_anything_not_the_exact_shape(data: Any) -> None:
    """The same closed-shape discipline `eventkeys.registry_from_data`
    holds itself to (its own docstring): a malformed committed file is
    reported, never guessed at."""
    with pytest.raises(ValueError):
        retention_liveness.last_run_from_data(data)


def test_days_since_is_zero_on_the_same_day() -> None:
    d = date(2026, 8, 23)
    assert retention_liveness.days_since(d, d) == 0


def test_days_since_counts_whole_elapsed_days() -> None:
    assert retention_liveness.days_since(date(2026, 8, 20), date(2026, 8, 23)) == 3


def test_days_since_can_be_negative_for_a_record_dated_in_the_future() -> None:
    """A hand-edited file or a clock skew between two runners -- `is_stale`
    treats this as healthy, never as extra-fresh evidence of anything."""
    assert retention_liveness.days_since(date(2026, 8, 25), date(2026, 8, 23)) == -2


def test_is_stale_boundary_exactly_at_max_silent_days_is_still_healthy() -> None:
    assert retention_liveness.is_stale(retention_liveness.MAX_SILENT_DAYS) is False


def test_is_stale_boundary_one_day_past_max_silent_days_is_stale() -> None:
    assert retention_liveness.is_stale(retention_liveness.MAX_SILENT_DAYS + 1) is True


def test_is_stale_treats_a_negative_elapsed_count_as_healthy() -> None:
    assert retention_liveness.is_stale(-1) is False


def test_is_stale_zero_days_is_healthy() -> None:
    assert retention_liveness.is_stale(0) is False


# ==================================================================== #
# cli.py: record_retention_run(), check_retention_liveness()
# ==================================================================== #


class _FixedDatetime:
    """A stand-in for the `datetime` class `cli.py` imports, whose `now()`
    always returns the same instant -- the same idiom
    `test_retention.py::_FixedDatetime` uses to pin `retention_sweep`'s
    own clock, reproduced here rather than imported across test modules."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self, tz: Any = None) -> datetime:
        return self._fixed


def _set_today(monkeypatch: pytest.MonkeyPatch, today: date) -> None:
    monkeypatch.setattr(
        "convener_ops.cli.datetime",
        _FixedDatetime(datetime(today.year, today.month, today.day, 9, 0, tzinfo=UTC)),
    )


def test_record_retention_run_writes_todays_paris_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 23))

    assert record_retention_run() == 0
    assert "2026-08-23" in capsys.readouterr().out

    path = retention_liveness.last_run_path(tmp_path)
    assert path.exists()
    from convener_ops.yaml_safe import safe_load

    loaded = safe_load(path.read_text(encoding="utf-8"))
    assert retention_liveness.last_run_from_data(loaded) == date(2026, 8, 23)


def test_record_retention_run_is_idempotent_the_same_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors `retention.yml`'s own commit step, which stages nothing --
    and therefore commits nothing -- once today's date is already what
    the file names (`git diff --staged --quiet`); re-running the command
    itself must produce byte-identical output for that guard to work."""
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 23))

    assert record_retention_run() == 0
    path = retention_liveness.last_run_path(tmp_path)
    first = path.read_text(encoding="utf-8")

    assert record_retention_run() == 0
    assert path.read_text(encoding="utf-8") == first


def test_record_retention_run_advances_the_date_on_a_later_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 23))
    assert record_retention_run() == 0

    _set_today(monkeypatch, date(2026, 8, 24))
    assert record_retention_run() == 0

    path = retention_liveness.last_run_path(tmp_path)
    from convener_ops.yaml_safe import safe_load

    loaded = safe_load(path.read_text(encoding="utf-8"))
    assert retention_liveness.last_run_from_data(loaded) == date(2026, 8, 24)


# -------------------------------------------------------------------- #
# check_retention_liveness(): the "prove it" pair -- the watchdog firing
# on real silence, and staying silent on real health.
# -------------------------------------------------------------------- #


def test_check_retention_liveness_fails_loudly_when_retention_has_gone_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Simulated silence: the record last advanced 5 days ago, well past
    `MAX_SILENT_DAYS`. This is the exact command
    `retention-watchdog.yml` runs -- a red run here is the fix's whole
    point."""
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 18))
    assert record_retention_run() == 0

    _set_today(monkeypatch, date(2026, 8, 23))
    assert check_retention_liveness() == 1
    err = capsys.readouterr().err
    assert "::error::" in err
    assert "2026-08-18" in err
    assert "5 day" in err


def test_check_retention_liveness_is_silent_and_green_when_retention_is_healthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half of the same proof: a record from today passes clean,
    with no `::error::` annotation at all."""
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 23))
    assert record_retention_run() == 0

    assert check_retention_liveness() == 0
    captured = capsys.readouterr()
    assert "::error::" not in captured.err
    assert "healthy" in captured.out


def test_check_retention_liveness_boundary_exactly_max_silent_days_still_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 21))
    assert record_retention_run() == 0

    # MAX_SILENT_DAYS later, exactly -- still healthy (is_stale's own
    # boundary test, exercised through the real command this time).
    _set_today(monkeypatch, date(2026, 8, 21 + retention_liveness.MAX_SILENT_DAYS))
    assert check_retention_liveness() == 0


def test_check_retention_liveness_boundary_one_day_past_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 21))
    assert record_retention_run() == 0

    _set_today(monkeypatch, date(2026, 8, 21 + retention_liveness.MAX_SILENT_DAYS + 1))
    assert check_retention_liveness() == 1


def test_check_retention_liveness_fails_when_the_record_has_never_been_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `record_retention_run` call at all -- the bootstrap state before
    this fix's own seed commit, or a repository where the file was
    somehow removed. Not the ordinary D-13 "an integration that may not
    exist yet" -- it is exactly the silence this command exists to
    report."""
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 23))

    assert check_retention_liveness() == 1
    assert "::error::" in capsys.readouterr().err


def test_check_retention_liveness_refuses_a_malformed_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 23))
    path = retention_liveness.last_run_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not: [valid, yaml", encoding="utf-8")

    assert check_retention_liveness() == 1
    assert "::error::" in capsys.readouterr().err


def test_check_retention_liveness_refuses_a_record_of_the_wrong_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_today(monkeypatch, date(2026, 8, 23))
    path = retention_liveness.last_run_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("last_run: 2026-08-23\n", encoding="utf-8")  # no "v"

    assert check_retention_liveness() == 1
    assert "::error::" in capsys.readouterr().err
