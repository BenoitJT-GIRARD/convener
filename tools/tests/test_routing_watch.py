"""Nothing detects that the saving has quietly stopped.

A registration has two lanes, and the relay resolves every
failure to read `public-data/registration-routing.json` to the *immediate*
one -- correctly, because the confirmation carries the room link and the
matching code and there is no second channel for either. The consequence
this module covers is that the whole economy of the phase can therefore
disappear with nothing turning red: the queue stays empty, which looks
exactly like a quiet day.

Three layers, mirroring the split `test_queue_watch.py` already uses:

* `routing_watch.py`'s own pure functions -- the published file's shape,
  which events are still live, and what counts as a divergence;
* `cli.py`'s `check_registration_routing`, the command the daily job runs.
  This is the "prove it" half: drive a missing file, a complete one, a live
  event the file has never heard of, a file whose every event is in the
  past, and five consecutive healthy days;
* the workflow file, read as text and `safe_load`-parsed -- never parsed
  and executed, which here would mean a real run.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from convener_ops import registration_routing, routing_watch
from convener_ops.cli import check_registration_routing
from convener_ops.paths import repo_root
from convener_ops.yaml_safe import safe_load

_ROOT = repo_root()
_SWEEP_PATH = _ROOT / ".github" / "workflows" / "sweep-and-notify.yml"
_SWEEP = _SWEEP_PATH.read_text(encoding="utf-8")

#: A Tuesday morning, the hour the drain is scheduled for.
_NOW = datetime(2026, 8, 25, 5, 0, tzinfo=UTC)

#: `config/registration-lanes.yml`'s own value, restated here rather than
#: read, so a maintainer moving the real threshold cannot silently move
#: what these fixtures mean.
_THRESHOLD = 96

#: Far enough away that a registration arriving at `_NOW` waits for the
#: drain: the whole reason the projection exists.
_LIVE = {"id": "spk-101", "edition_code": "MRG-09", "date": "2026-09-20", "time": ""}

#: Inside the threshold. A registration for it is dispatched immediately
#: whatever the file says, so the file being wrong about it costs nothing.
_NEAR = {"id": "spk-102", "edition_code": "MRG-08", "date": "2026-08-27", "time": ""}

#: Delivered months ago. Nothing can be registered for it at all.
_PAST = {"id": "spk-103", "edition_code": "MRG-07", "date": "2026-01-10", "time": ""}


def _cutoffs(*records: dict[str, str]) -> dict[str, str]:
    """What `deploy.yml` would publish for `records` -- produced by the
    real publisher, never typed out, so these fixtures cannot drift from
    the file the relay actually reads."""
    data = registration_routing.to_routing_data(list(records), _THRESHOLD)
    cutoffs = data["queue_until"]
    assert isinstance(cutoffs, dict)
    return cutoffs


# ==================================================================== #
# 1 - routing_watch.py: the published file's shape
# ==================================================================== #


def test_a_well_formed_file_parses_to_its_cutoffs() -> None:
    published = _cutoffs(_LIVE, _PAST)
    data = {"v": registration_routing.ROUTING_FILE_VERSION, "queue_until": published}
    assert routing_watch.published_from_data(data) == published


@pytest.mark.parametrize(
    "data",
    [
        pytest.param([], id="not an object"),
        pytest.param({"queue_until": {}}, id="no version"),
        pytest.param({"v": 99, "queue_until": {}}, id="a version nobody knows"),
        pytest.param({"v": 1, "queue_until": []}, id="queue_until is not a mapping"),
        pytest.param({"v": 1, "queue_until": {"": "x"}}, id="an empty event key"),
        pytest.param({"v": 1, "queue_until": {"mrg-09": 7}}, id="a numeric cutoff"),
    ],
)
def test_every_shape_the_relay_refuses_is_refused_here_too(data: Any) -> None:
    """The relay applies exactly these checks and reads a failure of any of
    them as "no cutoff at all". A file this function salvaged would
    describe a repository that does not exist."""
    with pytest.raises(ValueError, match=re.escape("registration-routing.json")):
        routing_watch.published_from_data(data)


def test_this_module_reads_what_the_publisher_writes() -> None:
    """The one thing a shared constant would have bought, bought instead by
    driving the real writer: every instant `to_routing_data` emits parses
    here. If the two spellings ever part company, this goes red rather than
    every event silently looking not-live."""
    for value in _cutoffs(_LIVE, _NEAR, _PAST).values():
        assert routing_watch.parse_published(value) is not None


def test_a_cutoff_nobody_can_parse_is_no_cutoff_on_the_published_side() -> None:
    """`null` is what the relay makes of it, and `null` is the immediate
    lane -- a per-event loss, not a malformed file."""
    assert routing_watch.parse_published("the twelfth of never") is None


def test_a_cutoff_nobody_can_parse_on_this_side_is_an_error() -> None:
    """The asymmetry that keeps this control from buying itself silence: a
    value read leniently here would make every event look not-live."""
    with pytest.raises(ValueError, match="drifted apart"):
        routing_watch.parse_expected("the twelfth of never")


# ==================================================================== #
# 2 - routing_watch.py: what is still live, and what diverges
# ==================================================================== #


def test_only_an_event_a_registration_could_still_be_queued_for_is_live() -> None:
    """The scope that keeps a quiet season quiet and keeps every seminar's
    own last four days quiet."""
    expected = _cutoffs(_LIVE, _NEAR, _PAST)
    assert routing_watch.live_events(expected, expected, _NOW) == ("mrg-09",)


def test_an_event_only_the_published_file_still_queues_is_live() -> None:
    """The direction that is about a person rather than the bill: the file
    would put somebody in the queue for an event this repository can no
    longer place in time."""
    published = _cutoffs(_LIVE)
    assert routing_watch.live_events({}, published, _NOW) == ("mrg-09",)


def test_a_file_that_agrees_about_every_live_event_diverges_nowhere() -> None:
    expected = _cutoffs(_LIVE, _NEAR, _PAST)
    assert routing_watch.divergences(expected, expected, _NOW) == ()


def test_a_file_that_has_never_heard_of_a_live_event_diverges() -> None:
    expected = _cutoffs(_LIVE, _PAST)
    published = _cutoffs(_PAST)
    diverged = routing_watch.divergences(expected, published, _NOW)
    assert [item.event for item in diverged] == ["mrg-09"]
    assert diverged[0].published is None
    assert "absent from the published file" in routing_watch.describe(diverged[0])


def test_a_file_that_is_wrong_only_about_a_past_event_is_not_a_finding() -> None:
    """History is out of scope on purpose. An event both sides place in the
    past cannot receive a registration, so a disagreement about it costs
    nothing and saying so would be the noise that teaches people to skim."""
    expected = _cutoffs(_LIVE, _PAST)
    published = dict(expected)
    published["mrg-07"] = "2020-01-01T00:00:00Z"
    assert routing_watch.divergences(expected, published, _NOW) == ()


def test_a_file_that_is_wrong_about_an_event_inside_the_threshold_is_silent() -> None:
    """Without this, every seminar would raise an alarm for its own last
    four days -- when the immediate lane is the correct answer anyway."""
    expected = _cutoffs(_LIVE, _NEAR)
    published = dict(expected)
    published.pop("mrg-08")
    assert routing_watch.divergences(expected, published, _NOW) == ()


def test_a_live_event_published_with_the_wrong_cutoff_diverges() -> None:
    """The `config/registration-lanes.yml` case: `deploy.yml` ignores
    `config/**`, so a threshold edited there changes what this repository
    would publish and regenerates nothing."""
    expected = _cutoffs(_LIVE)
    published = registration_routing.to_routing_data([_LIVE], _THRESHOLD + 24)
    cutoffs = published["queue_until"]
    assert isinstance(cutoffs, dict)
    diverged = routing_watch.divergences(expected, cutoffs, _NOW)
    assert [item.event for item in diverged] == ["mrg-09"]
    assert "would publish" in routing_watch.describe(diverged[0])


def test_an_event_the_data_no_longer_dates_is_described_as_such() -> None:
    published = _cutoffs(_LIVE)
    diverged = routing_watch.divergences({}, published, _NOW)
    assert "no longer gives it a usable date" in routing_watch.describe(diverged[0])


# ==================================================================== #
# 3 - routing_watch.py: the findings and what they say
# ==================================================================== #


def test_a_projection_that_still_routes_says_nothing() -> None:
    assert routing_watch.findings(()) == ()
    assert routing_watch.message((), ()) is None


def test_an_unreadable_file_is_the_only_finding_it_raises() -> None:
    """Every divergence in that case is a consequence of it, and two
    findings describing one cause is how an operator learns to skim."""
    diverged = routing_watch.divergences(_cutoffs(_LIVE), {}, _NOW)
    fired = routing_watch.findings(diverged, "it is not there.")
    assert [finding.kind for finding in fired] == [routing_watch.UNPUBLISHED]
    assert "every one of them is affected" in fired[0].text


def test_an_unreadable_file_fires_even_in_a_quiet_season() -> None:
    """The one unconditional finding. It is not a statement about the
    season: the file will still be missing on the morning an announcement
    goes out."""
    fired = routing_watch.findings((), "it is not there.")
    assert [finding.kind for finding in fired] == [routing_watch.UNPUBLISHED]
    assert "still be true on the morning an announcement goes out" in fired[0].text
    body = routing_watch.message(fired, ())
    assert body is not None
    assert "Events affected" not in body


def test_the_two_per_event_findings_are_told_apart() -> None:
    """The fix is the same but the reader still has to know which of the
    two happened -- a file that never heard of an event is a deploy that
    never ran; a wrong cutoff is a deploy older than the data."""
    expected = _cutoffs(_LIVE)
    other = {"id": "spk-104", "edition_code": "MRG-10", "date": "2026-10-01", "time": ""}
    expected |= _cutoffs(other)
    published = {"mrg-10": "2020-01-01T00:00:00Z"}
    fired = routing_watch.findings(routing_watch.divergences(expected, published, _NOW))
    assert [finding.kind for finding in fired] == [
        routing_watch.UNNAMED,
        routing_watch.STALE,
    ]


def test_every_finding_says_what_to_do_about_it() -> None:
    """The half a reader cannot deduce: this alarm is about a deployment,
    and nothing in the daily job or in an operator's editor fixes it."""
    for fired in (
        routing_watch.findings((), "it is not there."),
        routing_watch.findings(routing_watch.divergences(_cutoffs(_LIVE), {}, _NOW)),
    ):
        assert fired
        for finding in fired:
            assert ".github/workflows/deploy.yml" in finding.text
            assert "Deploy app" in finding.text


def test_the_enumeration_is_bounded_but_the_count_is_not() -> None:
    """A comment body past what GitHub accepts is no message at all, which
    is the exact silence this module refuses."""
    many = [
        {"id": f"spk-2{n:02d}", "edition_code": f"VX-{n:02d}", "date": "2026-09-20"}
        for n in range(routing_watch.MOST_LISTED + 3)
    ]
    diverged = routing_watch.divergences(_cutoffs(*many), {}, _NOW)
    assert len(diverged) == routing_watch.MOST_LISTED + 3
    lines = routing_watch.annotation_lines(routing_watch.findings(diverged), diverged)
    assert lines[-1] == "::error::and 3 more event(s) routed on stale data"
    body = routing_watch.message(routing_watch.findings(diverged), diverged)
    assert body is not None and "  - and 3 more" in body


def test_the_message_says_nothing_is_lost() -> None:
    """This alarm guards money, never a person. Saying so is what stops it
    being read as the queue alarm one block up, which guards somebody's
    seat in a room."""
    diverged = routing_watch.divergences(_cutoffs(_LIVE), {}, _NOW)
    body = routing_watch.message(routing_watch.findings(diverged), diverged)
    assert body is not None
    assert "No registration is lost" in body
    assert "mrg-09" in body


def test_the_summary_counts_both_halves() -> None:
    assert routing_watch.summary(("mrg-09", "mrg-10"), ()) == (
        "2 event(s) can be registered for right now, 0 of them not routed "
        "the way this repository would"
    )


# ==================================================================== #
# 4 - cli.py: the proofs, driven
# ==================================================================== #


class _FixedDatetime:
    """A stand-in for the `datetime` class `cli.py` imports, whose `now()`
    always returns the same instant -- the same idiom
    `test_queue_watch.py::_FixedDatetime` uses."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self, tz: Any = None) -> datetime:
        return self._fixed


def _repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    speakers: list[dict[str, str]],
    published: dict[str, str] | str | None,
    now: datetime = _NOW,
) -> Path:
    """A repository root holding only what this command reads.

    `published` is the mapping to publish, a raw string to write verbatim,
    or `None` to leave the file out entirely.
    """
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "speakers.yml").write_text(
        json.dumps(speakers), encoding="utf-8"
    )
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "registration-lanes.yml").write_text(
        f"v: 1\nqueue_beyond_hours: {_THRESHOLD}\n", encoding="utf-8"
    )
    routing = tmp_path / registration_routing.ROUTING_PATH
    routing.parent.mkdir(parents=True, exist_ok=True)
    if published is None:
        routing.unlink(missing_ok=True)
    elif isinstance(published, str):
        routing.write_text(published, encoding="utf-8")
    else:
        routing.write_text(
            json.dumps(
                {
                    "v": registration_routing.ROUTING_FILE_VERSION,
                    "queue_until": published,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("CONVENER_NOTIFY_THREAD", raising=False)
    monkeypatch.delenv("CONVENER_NOTIFY_MENTION", raising=False)
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


def test_a_missing_projection_fires_and_names_the_deploy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proof 1. Nothing has ever published the file the relay reads, so
    every registration bills a run -- and nothing else in this repository
    would say so."""
    _repo(tmp_path, monkeypatch, speakers=[_LIVE], published=None)
    out = _github_output(tmp_path, monkeypatch)
    assert check_registration_routing() == 0
    assert _outputs(out)["routing_alert"] == "true"
    printed = capsys.readouterr().out
    assert "[unpublished]" in printed
    assert ".github/workflows/deploy.yml" in printed
    assert "mrg-09" in printed


def test_a_complete_projection_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proof 2. The healthy case, and the one that has to stay quiet: an
    alarm that cries wolf about a working repository costs more credibility
    than this failure costs minutes."""
    _repo(
        tmp_path,
        monkeypatch,
        speakers=[_LIVE, _NEAR, _PAST],
        published=_cutoffs(_LIVE, _NEAR, _PAST),
    )
    out = _github_output(tmp_path, monkeypatch)
    assert check_registration_routing() == 0
    assert _outputs(out)["routing_alert"] == "false"
    printed = capsys.readouterr().out
    assert "1 event(s) can be registered for right now, 0 of them" in printed
    assert "::error::" not in printed


def test_an_event_the_projection_never_heard_of_fires_and_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proof 3. The file is present, readable and current for everything it
    knows about -- and a new seminar was announced without a deploy ever
    regenerating it."""
    _repo(
        tmp_path,
        monkeypatch,
        speakers=[_LIVE, _PAST],
        published=_cutoffs(_PAST),
    )
    out = _github_output(tmp_path, monkeypatch)
    assert check_registration_routing() == 0
    assert _outputs(out)["routing_alert"] == "true"
    printed = capsys.readouterr().out
    assert "[unnamed]" in printed
    assert "mrg-09: absent from the published file" in printed


def test_a_projection_of_only_past_events_is_a_quiet_season(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proof 4, and the decision it settles: **not** an alarm. No event is
    open for registration, so no registration can be queued, so there is no
    saving to lose. An age check gets exactly this case backwards -- the
    file is as old as the last seminar and entirely correct."""
    _repo(tmp_path, monkeypatch, speakers=[_PAST], published=_cutoffs(_PAST))
    out = _github_output(tmp_path, monkeypatch)
    assert check_registration_routing() == 0
    assert _outputs(out)["routing_alert"] == "false"
    assert "0 event(s) can be registered for right now" in capsys.readouterr().out


def test_the_same_old_file_fires_the_moment_an_event_opens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half of proof 4, and the whole argument for measuring the
    ability to route rather than the age: the *same* published file, not a
    byte different, is healthy in one repository and a finding in the
    next."""
    _repo(tmp_path, monkeypatch, speakers=[_PAST, _LIVE], published=_cutoffs(_PAST))
    out = _github_output(tmp_path, monkeypatch)
    assert check_registration_routing() == 0
    assert _outputs(out)["routing_alert"] == "true"
    assert "mrg-09" in capsys.readouterr().out


def test_a_healthy_repository_stays_silent_day_after_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proof 5. Five consecutive drains over an unchanged repository, one
    of them the day the live event crosses into the immediate lane. Not one
    of them says anything: this control has no clock of its own to drift
    and no record to go stale."""
    published = _cutoffs(_LIVE, _NEAR, _PAST)
    out = _github_output(tmp_path, monkeypatch)
    for day in range(5):
        _repo(
            tmp_path,
            monkeypatch,
            speakers=[_LIVE, _NEAR, _PAST],
            published=published,
            now=_NOW + timedelta(days=day),
        )
        assert check_registration_routing() == 0
        assert _outputs(out)["routing_alert"] == "false"
    assert "::error::" not in capsys.readouterr().out


def test_a_file_the_relay_would_refuse_is_reported_as_unpublished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bytes that are not JSON, and a version the relay does not know, are
    the same outcome as an absent file -- `registrationCutoff` returns
    `null` for both -- so they are reported as the same finding."""
    for content in ("{not json", '{"v": 99, "queue_until": {}}'):
        _repo(tmp_path, monkeypatch, speakers=[_LIVE], published=content)
        out = _github_output(tmp_path, monkeypatch)
        assert check_registration_routing() == 0
        assert _outputs(out)["routing_alert"] == "true"
        assert "[unpublished]" in capsys.readouterr().out


def test_the_command_posts_through_the_channel_that_already_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-07: the board's thread and the team mention, no second address
    book -- and its own body file, because four messages are now composed
    in this one job."""
    root = _repo(tmp_path, monkeypatch, speakers=[_LIVE], published={})
    _github_output(tmp_path, monkeypatch)
    monkeypatch.setenv("CONVENER_NOTIFY_THREAD", "42")
    monkeypatch.setenv("CONVENER_NOTIFY_MENTION", "@example/board")
    assert check_registration_routing() == 0
    body = (root / "routing-body.md").read_text(encoding="utf-8")
    assert body.startswith("@example/board")
    assert "mrg-09" in body
    assert "Deploy app" in body
    assert "thread 42" in capsys.readouterr().out
    assert not (root / "queue-body.md").exists()
    assert not (root / "notify-body.md").exists()
    assert not (root / "budget-body.md").exists()


def test_an_unconfigured_channel_still_leaves_the_finding_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-13 is the ordinary state here. An unconfigured integration must
    never be able to turn a real finding into silence -- so no body file is
    written and `routing_alert` is still true, which is what the workflow's
    own last step reads."""
    root = _repo(tmp_path, monkeypatch, speakers=[_LIVE], published=None)
    out = _github_output(tmp_path, monkeypatch)
    assert check_registration_routing() == 0
    assert _outputs(out)["routing_alert"] == "true"
    assert not (root / "routing-body.md").exists()


def test_the_repository_s_own_unreadable_inputs_are_a_different_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing `data/speakers.yml` or a threshold nobody can read is a
    broken repository, not a stale deployment: exit 1, no `routing_alert`
    at all, and no message claiming the deploy is at fault."""
    root = _repo(tmp_path, monkeypatch, speakers=[_LIVE], published={})
    _github_output(tmp_path, monkeypatch)
    (root / "config" / "registration-lanes.yml").write_text("v: 9\n", encoding="utf-8")
    assert check_registration_routing() == 1
    assert "not a supported format version" in capsys.readouterr().err

    (root / "data" / "speakers.yml").unlink()
    assert check_registration_routing() == 1
    assert "file missing" in capsys.readouterr().err


# ==================================================================== #
# 5 - the workflow
# ==================================================================== #


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


def test_the_check_is_a_step_of_a_job_that_already_runs() -> None:
    """The whole economy of the phase, one more time: a workflow or a job
    created to watch the saving would itself cost a billed run every day,
    which is the cost it exists to protect."""
    mentions = {
        path.name
        for path in (_ROOT / ".github" / "workflows").glob("*.yml")
        if "convener-check-registration-routing" in path.read_text(encoding="utf-8")
    }
    assert mentions == {"sweep-and-notify.yml"}
    workflow = safe_load(_SWEEP)
    assert isinstance(workflow, dict)
    assert sorted(workflow["jobs"]) == ["daily", "immediate"]
    step = _daily_step("Check that registrations can still be queued")
    assert step["run"] == "uv run convener-check-registration-routing"


def test_the_check_runs_even_when_the_sweep_or_the_drain_failed() -> None:
    """It reads two committed files and a clock. A drain that could not
    finish is no reason to stop asking whether tomorrow's registrations
    will reach the queue at all."""
    step = _daily_step("Check that registrations can still be queued")
    assert step["if"] == "always() && steps.uv.outcome == 'success'"


def test_the_finding_uses_the_channel_that_already_exists_with_its_own_body() -> None:
    """D-07: the same thread, the same team mention. A fourth body
    filename, because several messages composed in one job sharing one
    filename means whichever is written last silently replaces the rest."""
    step = _daily_step("Tell the board registrations are no longer being queued")
    assert "routing-body.md" in step["run"]
    for other in ("notify-body.md", "queue-body.md", "budget-body.md"):
        assert other not in step["run"]
    assert step["env"]["THREAD"] == "${{ secrets.CONVENER_NOTIFY_THREAD }}"


def test_the_channel_is_never_visible_beyond_the_step_that_composes() -> None:
    """Step-level, never job-level -- the rule every other composing step
    in this job holds itself to."""
    workflow = safe_load(_SWEEP)
    assert isinstance(workflow, dict)
    assert "CONVENER_NOTIFY_THREAD" not in workflow["jobs"]["daily"].get("env", {})
    step = _daily_step("Check that registrations can still be queued")
    for name in ("CONVENER_NOTIFY_THREAD", "CONVENER_NOTIFY_MENTION"):
        assert step["env"][name] == "${{ secrets." + name + " }}"


def test_the_finding_turns_the_daily_job_red_on_its_own() -> None:
    """A log line is not a control (D-25): the red run has to happen
    whether or not a channel was configured to post to."""
    step = _daily_step("Fail if registrations can no longer be queued")
    assert (
        step["if"] == "always() && steps.routing-watch.outputs.routing_alert == 'true'"
    )
    assert "exit 1" in step["run"]
    assert "Deploy app" in step["run"]


def test_the_check_does_not_raise_the_daily_job_s_ceiling() -> None:
    """It is a pure function over two committed files -- no network, no
    push, no retry loop. The ceiling has already gone from 25 to 40
    minutes, which is a real cost; this
    task adds none of it."""
    workflow = safe_load(_SWEEP)
    assert isinstance(workflow, dict)
    assert workflow["jobs"]["daily"]["timeout-minutes"] == 40
