"""H2 (2026-08-23 security audit, AF-2): pins the two workflow files this
fix touches against the properties `test_retention_liveness.py`'s own CLI
tests cannot see, because they never read a `.yml` file at all.

Read as text and `safe_load`-parsed, the same idiom every workflow-pinning
module in this suite already uses -- never parsed and executed, which here
would mean a real scheduled run and a real push, exactly the network
access this suite must not take on.
"""

from __future__ import annotations

from convener_ops.paths import repo_root
from convener_ops.yaml_safe import safe_load

_ROOT = repo_root()
_WATCHDOG_PATH = _ROOT / ".github" / "workflows" / "retention-watchdog.yml"
_RETENTION_PATH = _ROOT / ".github" / "workflows" / "retention.yml"


def _watchdog() -> dict:
    loaded = safe_load(_WATCHDOG_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _retention() -> dict:
    loaded = safe_load(_RETENTION_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


# ==================================================================== #
# retention-watchdog.yml
# ==================================================================== #


def test_watchdog_is_scheduled_and_also_dispatchable_by_hand() -> None:
    # PyYAML's YAML-1.1 bool resolver reads a bare `on:` key as the
    # boolean `True`, not the string "on" -- the same gotcha
    # test_workflows.py's own text-assertion modules already work around
    # (see test_publish_vitrine_paths_trigger_includes_the_certificate_
    # register's own comment).
    triggers = _watchdog()[True]
    schedule = triggers.get("schedule")
    assert isinstance(schedule, list) and schedule
    assert "workflow_dispatch" in triggers


def test_watchdog_runs_after_retentions_own_cron_the_same_day() -> None:
    """Never a same-day race against the job it watches: retention.yml's
    own cron is '11 6 * * *' (06:11 UTC); the watchdog's hour must be
    later than 6 so a healthy day's record is already written by the time
    this checks it."""
    watchdog_cron = _watchdog()[True]["schedule"][0]["cron"]
    retention_cron = _retention()[True]["schedule"][0]["cron"]
    watchdog_hour = int(watchdog_cron.split()[1])
    retention_hour = int(retention_cron.split()[1])
    assert watchdog_hour > retention_hour, (
        f"watchdog cron {watchdog_cron!r} does not run later in the day "
        f"than retention.yml's own {retention_cron!r} -- a same-day race "
        "would report a healthy day as stale"
    )


def test_watchdog_declares_no_secret_beyond_github_token() -> None:
    """It must not: see this file's own header comment for why it can
    read only a committed fact and must reach no network beyond its own
    checkout. A secret here would also require adding this workflow to
    secret-workflow-monitor.yml's own watch list
    (test_the_secret_workflow_monitor_watches_every_secret_bearing_workflow
    in test_workflows.py already enforces that direction generically)."""
    text = _WATCHDOG_PATH.read_text(encoding="utf-8")
    assert "secrets." not in text


def test_watchdog_job_permissions_are_read_only() -> None:
    job = _watchdog()["jobs"]["watchdog"]
    assert job["permissions"] == {"contents": "read"}


def test_watchdog_runs_the_liveness_check_command() -> None:
    job = _watchdog()["jobs"]["watchdog"]
    runs = " ".join(
        step["run"] for step in job["steps"] if isinstance(step.get("run"), str)
    )
    assert "convener-check-retention-liveness" in runs


# ==================================================================== #
# retention.yml's own new step
# ==================================================================== #


def _retention_steps() -> list[dict]:
    steps = _retention()["jobs"]["retention"]["steps"]
    assert isinstance(steps, list)
    return steps


def _last_run_step() -> dict:
    for step in _retention_steps():
        if step.get("name") == "Record that the retention workflow ran today":
            return step
    raise AssertionError(
        "retention.yml has no 'Record that the retention workflow ran "
        "today' step -- renamed away from the name this test looks for"
    )


def test_retention_workflow_records_a_run_unconditionally() -> None:
    """The one property that makes this fix mean what it claims: this
    step must run whether or not every step above it succeeded, or a
    permanently broken CONVENER_RETENTION_TOKEN -- failing loudly every single
    day -- would never advance the record, silently turning a real,
    ongoing, already-loud failure into a *second*, misleading kind of
    silence at the watchdog layer."""
    assert _last_run_step().get("if") == "always()"


def test_retention_workflow_last_run_step_calls_the_record_command() -> None:
    script = _last_run_step()["run"]
    assert "convener-record-retention-run" in script


def test_retention_workflow_last_run_step_stages_the_liveness_file() -> None:
    script = _last_run_step()["run"]
    assert "git add data/retention-last-run.yml" in script


def test_retention_workflow_last_run_step_re_derives_rather_than_rebases() -> None:
    """The same defence every other retry loop in this file uses (see
    deploy.yml's and publish-vitrine.yml's own pins in test_workflows.py
    for the identical reasoning): a rejected push is handled by fetching
    the branch tip and hard-resetting, never `git pull --rebase` or
    `git rebase`."""
    script = _last_run_step()["run"]
    commands = [
        line for line in script.splitlines() if not line.strip().startswith("#")
    ]
    assert not any("git rebase" in line for line in commands)
    assert not any("git pull" in line for line in commands)
    assert 'git fetch origin "$TARGET_BRANCH"' in script
    assert 'git reset --hard "origin/$TARGET_BRANCH"' in script


def test_retention_workflow_last_run_step_is_the_final_step() -> None:
    """Deliberately last: it must observe whatever the destruction-
    recording step above already pushed this same run, not race it."""
    steps = _retention_steps()
    assert steps[-1] == _last_run_step()
