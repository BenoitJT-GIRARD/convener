"""Which lane a registration takes, and the floor under the threshold.

Four groups, in this order:

1. **The arithmetic** -- the threshold's own closed shape, the Europe/Paris
   instant an event starts at, the cutoff that follows from the two, and
   the boundary on both sides of it.
2. **The floor.** The one property in this file that is not about a
   function but about the repository: the configured threshold has to sit
   above twice the drain's own period, and the period is *derived from the
   drain's cron*, never restated here. A maintainer who shortens the
   threshold, or lengthens the drain's cadence, finds out from a red test
   and not from a participant who never got into the room.
3. **The projection** -- `to_routing_data` and the console script that
   writes it, including that nothing about a speaker but an edition code
   and a date can ever reach the published file.
4. **The three files that have to agree with it** -- `.gitignore`,
   `deploy.yml`, and `services/signup-relay/src/index.js`. Three copies of
   a path or a version that disagreed would be a relay reading a file
   nothing writes, silently routing every registration to the immediate
   lane -- which is safe, and therefore invisible, which is the problem.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import config, speaker

from convener_ops.cli import registration_routing_public_data
from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.yaml_safe import safe_load
from convener_ops.governance import PARIS
from convener_ops.journey import registration_routing
from convener_ops.journey.registration_routing import (
    CronShapeError,
    drain_period_hours,
    event_start,
    floor_hours,
    lane,
    queue_until,
    threshold_from_data,
    to_routing_data,
)

_ROOT = repo_root()
_RELAY = (_ROOT / "services" / "signup-relay" / "src" / "index.js").read_text(
    encoding="utf-8"
)


def _write_data(tmp_path: Path, speakers: object, threshold: object) -> None:
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "speakers.yml").write_text(json.dumps(speakers), encoding="utf-8")
    (data_dir / "config.yml").write_text(json.dumps(config()), encoding="utf-8")
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "registration-lanes.yml").write_text(
        json.dumps(threshold), encoding="utf-8"
    )


# ------------------------------------------------------------------ #
# 1 - the arithmetic
# ------------------------------------------------------------------ #


def test_the_threshold_is_read_out_of_its_own_closed_shape() -> None:
    assert threshold_from_data({"v": 1, "queue_beyond_hours": 96}) == 96


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "96",
        {"queue_beyond_hours": 96},
        {"v": 2, "queue_beyond_hours": 96},
        {"v": 1},
        {"v": 1, "queue_beyond_hours": "96"},
        {"v": 1, "queue_beyond_hours": 96.5},
        {"v": 1, "queue_beyond_hours": 0},
        {"v": 1, "queue_beyond_hours": -1},
        # `True` is an `int` in Python, and a threshold of one hour read out
        # of a boolean is exactly the silent nonsense this shape check
        # exists to refuse.
        {"v": 1, "queue_beyond_hours": True},
    ],
)
def test_a_threshold_this_code_cannot_read_is_refused_never_defaulted(
    data: Any,
) -> None:
    with pytest.raises(ValueError):
        threshold_from_data(data)


def test_an_event_with_a_wall_clock_time_starts_at_that_paris_instant() -> None:
    record = speaker(date="2026-09-24", time="12:30")
    assert event_start(record) == datetime(2026, 9, 24, 12, 30, tzinfo=PARIS)


def test_an_event_with_no_time_starts_at_midnight_not_at_the_standing_start() -> None:
    """Midnight is the *earlier* of the two, and the earlier one is the safe
    guess: reading a start sooner than it really is can only move a
    registration into the immediate lane, which costs a run. Guessing
    12:30 and being wrong would move one the other way, which costs a
    participant their link."""
    assert event_start(speaker(date="2026-09-24", time="")) == datetime(
        2026, 9, 24, 0, 0, tzinfo=PARIS
    )


def test_a_time_nobody_can_parse_falls_back_rather_than_dropping_the_date() -> None:
    assert event_start(speaker(date="2026-09-24", time="half past")) == datetime(
        2026, 9, 24, 0, 0, tzinfo=PARIS
    )


@pytest.mark.parametrize(
    "record",
    [
        {"date": "", "time": "12:30"},
        {"date": "2026-13-40", "time": "12:30"},
        {"date": None, "time": ""},
        {},
    ],
)
def test_an_event_nobody_can_date_has_no_start_at_all(record: Any) -> None:
    assert event_start(record) is None


def test_the_cutoff_crosses_a_daylight_saving_boundary_by_the_real_offset() -> None:
    """An event at 12:30 on the Monday after the October change, with a
    threshold long enough to reach back over it. The cutoff is a real
    instant, so the *elapsed* hours are what the threshold says even though
    the wall clocks either side of it differ by an hour -- which is the
    whole reason this arithmetic is done here and not in a worker.

    This is the test that found the defect: `queue_until` first subtracted
    the threshold from the Paris-aware start directly, and Python's
    documented same-`tzinfo` shortcut made that wall-clock arithmetic, an
    hour off across the change. `(start - cutoff)` cannot see it -- the
    same shortcut applies to the check -- so the assertion below is on the
    UTC instants, which is the only comparison that can.
    """
    start = event_start(speaker(date="2026-10-27", time="12:30"))
    assert start is not None
    cutoff = queue_until(start, 96)
    assert (start.astimezone(UTC) - cutoff.astimezone(UTC)).total_seconds() == (
        96 * 3600
    )
    # 27 October is CET (+01:00); 96 hours earlier is 23 October, CEST
    # (+02:00), so the local wall clock reads one hour later than a naive
    # subtraction of four days would give.
    assert cutoff.astimezone(PARIS).strftime("%Y-%m-%d %H:%M") == "2026-10-23 13:30"


def test_the_boundary_is_closed_on_the_side_that_still_delivers_the_link() -> None:
    """Driven on both sides. A submission one second before the cutoff
    waits for the drain; one arriving *at* the cutoff, and everything after
    it, is dispatched at once."""
    cutoff = queue_until(datetime(2026, 9, 24, 12, 30, tzinfo=PARIS), 96)
    one_second = timedelta(seconds=1)
    assert lane(cutoff, cutoff - one_second) == "queue"
    assert lane(cutoff, cutoff) == "immediate"
    assert lane(cutoff, cutoff + one_second) == "immediate"


def test_no_cutoff_at_all_is_the_immediate_lane_never_the_queue() -> None:
    assert lane(None, datetime(2026, 1, 1, tzinfo=UTC)) == "immediate"


# ------------------------------------------------------------------ #
# 2 - the floor
# ------------------------------------------------------------------ #


def _drain_workflow() -> dict[str | bool, Any]:
    loaded = safe_load(
        (_ROOT / registration_routing.DRAIN_WORKFLOW_PATH).read_text(encoding="utf-8")
    )
    assert isinstance(loaded, dict)
    return loaded


def test_the_drains_period_is_read_out_of_the_workflow_that_runs_it() -> None:
    assert drain_period_hours(_drain_workflow()) == 24


@pytest.mark.parametrize(
    "workflow",
    [
        {},
        {True: "push"},
        {True: {"push": {"branches": ["main"]}}},
        {True: {"schedule": []}},
        {True: {"schedule": [{"cron": "0 5 * * *"}, {"cron": "0 17 * * *"}]}},
        {True: {"schedule": [{"cron": "*/30 * * * *"}]}},
        {True: {"schedule": [{"cron": "0 5 * * 1"}]}},
        {True: {"schedule": [{"cron": "0 5 1 * *"}]}},
        {True: {"schedule": [{"cron": 5}]}},
        {True: {"schedule": ["0 5 * * *"]}},
    ],
)
def test_a_schedule_this_module_cannot_read_is_refused_never_approximated(
    workflow: Any,
) -> None:
    """A floor that answered "probably 24 hours" about a cron it misread
    would be worse than no floor: it would be a green test standing over a
    threshold nobody had actually checked. Every shape here raises by
    name."""
    with pytest.raises(CronShapeError):
        drain_period_hours(workflow)


def test_the_floor_leaves_room_for_one_drain_that_never_runs() -> None:
    assert floor_hours(24) == 48
    assert floor_hours(6) == 12


def test_the_configured_threshold_sits_above_the_floor_the_drain_imposes() -> None:
    """**The property this whole task turns on, and it is not the number.**

    `instance/registration-lanes.yml` is meant to be edited. What must not be
    editable into existence is a threshold shorter than the drain can
    honour: at twelve hours against a once-daily drain, a far-lane
    registrant is told they are registered and then hears nothing until
    after the seminar.

    Both halves are derived, neither is retyped -- the threshold from the
    config file, the period from the cron in the workflow that actually
    drains the queue -- so this fails on a change to *either* of them and
    cannot quietly drift out of agreement with what the repository does.
    """
    configured = threshold_from_data(
        safe_load(
            (_ROOT / registration_routing.CONFIG_PATH).read_text(encoding="utf-8")
        )
    )
    floor = floor_hours(drain_period_hours(_drain_workflow()))
    assert configured >= floor, (
        f"instance/registration-lanes.yml queues a registration until "
        f"{configured}h before its event, but the drain that has to send "
        f"its confirmation only runs every "
        f"{drain_period_hours(_drain_workflow())}h and GitHub drops "
        f"scheduled runs -- anything under {floor}h can leave a registrant "
        "without the room link until after the event"
    )


def test_the_default_threshold_is_generous_rather_than_exactly_at_the_floor() -> None:
    """At the floor exactly, the worst case (submit at the threshold, one
    drain dropped) delivers the confirmation at the very instant the
    seminar starts. That is not a margin, it is a coincidence. The shipped
    default sits a further whole period above it so the message lands with
    time to be read and acted on."""
    configured = threshold_from_data(
        safe_load(
            (_ROOT / registration_routing.CONFIG_PATH).read_text(encoding="utf-8")
        )
    )
    period = drain_period_hours(_drain_workflow())
    assert configured >= floor_hours(period) + period


# ------------------------------------------------------------------ #
# 3 - the projection
# ------------------------------------------------------------------ #


def test_the_projection_publishes_one_utc_instant_per_datable_event() -> None:
    data = to_routing_data(
        [speaker(id="spk-001", edition_code="MRG-06", date="2026-09-24", time="12:30")],
        96,
    )
    assert data == {"v": 1, "queue_until": {"mrg-06": "2026-09-20T10:30:00Z"}}


def test_the_projection_carries_nothing_about_a_speaker_but_the_edition() -> None:
    """The leak check every projection in this repository is held to: a
    mutant emitting the record itself, or any field of it, fails here."""
    record = speaker(
        id="spk-001",
        edition_code="MRG-06",
        date="2026-09-24",
        time="12:30",
        name="Ada Lovelace",
        email="ada@example.org",
        affiliation="Example University",
        title="On analytical engines",
    )
    rendered = json.dumps(to_routing_data([record], 96))
    for leaked in ("Ada", "ada@example.org", "Example University", "analytical"):
        assert leaked not in rendered


@pytest.mark.parametrize(
    "overrides",
    [
        {"edition_code": ""},
        {"edition_code": None},
        {"date": ""},
        {"date": "not-a-date"},
    ],
)
def test_an_event_the_projection_cannot_key_or_date_is_simply_absent(
    overrides: Any,
) -> None:
    """Absent, never guessed at: the relay reads an event it does not find
    as "dispatch immediately", which is where an event nobody can date
    belongs."""
    record = speaker(edition_code="MRG-06", date="2026-09-24", time="12:30")
    record.update(overrides)
    assert to_routing_data([record], 96)["queue_until"] == {}


def test_the_projection_ignores_an_entry_that_is_not_a_record_at_all() -> None:
    assert to_routing_data(["not a record", None], 96)["queue_until"] == {}


def test_the_projection_is_sorted_so_a_rerun_writes_the_same_bytes() -> None:
    records = [
        speaker(id="spk-002", edition_code="MRG-07", date="2026-10-29", time="12:30"),
        speaker(id="spk-001", edition_code="MRG-06", date="2026-09-24", time="12:30"),
    ]
    assert list(to_routing_data(records, 96)["queue_until"]) == ["mrg-06", "mrg-07"]


def test_the_console_script_writes_what_the_projection_produced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_data(
        tmp_path,
        [
            speaker(
                id="spk-001", edition_code="MRG-06", date="2026-09-24", time="12:30"
            ),
            speaker(id="spk-002", edition_code="MRG-07", date="", time=""),
        ],
        {"v": 1, "queue_beyond_hours": 96},
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert registration_routing_public_data() == 0
    assert "wrote 1 event(s)" in capsys.readouterr().out
    written = json.loads(
        (tmp_path / registration_routing.ROUTING_PATH).read_text(encoding="utf-8")
    )
    assert written == {"v": 1, "queue_until": {"mrg-06": "2026-09-20T10:30:00Z"}}


def test_the_console_script_refuses_a_threshold_it_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Never a default. A threshold guessed at is a threshold that could
    put a last-minute registrant in a queue they cannot afford to wait
    in."""
    _write_data(
        tmp_path,
        [speaker(edition_code="MRG-06", date="2026-09-24", time="12:30")],
        {"v": 1, "queue_beyond_hours": "soon"},
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert registration_routing_public_data() == 1
    assert "queue_beyond_hours" in capsys.readouterr().out
    assert not (tmp_path / registration_routing.ROUTING_PATH).exists()


def test_the_console_script_reports_a_missing_file_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    (tmp_path / "instance" / "data").mkdir(parents=True)

    assert registration_routing_public_data() == 1
    assert "file missing" in capsys.readouterr().out
    assert not (tmp_path / "instance" / "public-data").exists()


# ------------------------------------------------------------------ #
# 4 - the files that have to agree
# ------------------------------------------------------------------ #


def test_gitignore_keeps_the_published_routing_file_tracked() -> None:
    """`instance/public-data/*` is ignored wholesale; this one file needs a named
    exception or `deploy.yml` has no tracked path to commit it to, and the
    relay reads a 404 for ever -- safe, silent, and permanently one billed
    run per registration."""
    ignore = (_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert f"!{registration_routing.ROUTING_PATH.as_posix()}" in ignore


def test_deploy_commits_the_routing_file_it_generates() -> None:
    deploy = (_ROOT / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )
    assert "uv run convener-registration-routing-public-data" in deploy
    assert f"git add {registration_routing.ROUTING_PATH.as_posix()}" in deploy


def test_the_relay_reads_the_path_and_the_version_this_module_writes() -> None:
    """The path is matched as the relay's own constant now, not as a
    concatenation. `CONTENTS_URL` was a module constant there, built off a
    repository written into that file; the repository arrives as a
    deploy-time binding, so the address is built at each call site and only
    the path itself is left to hold against this module's."""
    assert (
        f"const ROUTING_PATH = '{registration_routing.ROUTING_PATH.as_posix()}';"
        in _RELAY
    )
    assert "contentsUrl(repository, ROUTING_PATH)" in _RELAY
    assert (
        f"const ROUTING_FILE_VERSION = {registration_routing.ROUTING_FILE_VERSION};"
        in _RELAY
    )


def test_the_relay_reads_the_cutoff_key_the_projection_writes() -> None:
    """One key name, in two languages. A rename on either side would make
    every event look undated to the relay -- every registration dispatched,
    nothing red anywhere."""
    assert set(to_routing_data([], 96)) == {"v", "queue_until"}
    assert "data.queue_until" in _RELAY
