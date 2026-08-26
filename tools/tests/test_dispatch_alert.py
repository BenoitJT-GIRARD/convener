"""Detection, never prevention -- see `convener_ops.dispatch_alert`'s own module
docstring. The tests here split the same way the code does: `alert_message`
is a pure function, tested directly; `cli.alert_secret_workflow_run` is the
thin wrapper the workflow actually calls, tested through its exit code, its
`$GITHUB_OUTPUT` write and whether it leaves `notify-body.md` behind -- the
same three things `.github/workflows/secret-workflow-monitor.yml`'s own
later steps read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from convener_ops import cli
from convener_ops.dispatch_alert import MAIN_BRANCH, alert_message
from convener_ops.notify import MENTION_ENV, THREAD_ENV


@pytest.fixture(autouse=True)
def _no_ambient_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test inherits a channel from the machine it runs on."""
    monkeypatch.delenv(THREAD_ENV, raising=False)
    monkeypatch.delenv(MENTION_ENV, raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)


# --------------------------------------------------------------------- #
# alert_message -- pure function
# --------------------------------------------------------------------- #


def test_a_run_on_main_produces_no_message() -> None:
    assert MAIN_BRANCH == "main"
    assert (
        alert_message(
            workflow_name="Issue certificates",
            head_branch="main",
            run_event="workflow_dispatch",
            run_url="https://example.invalid/runs/1",
            actor="someone",
        )
        is None
    )


def test_a_run_off_main_names_the_workflow_branch_event_actor_and_url() -> None:
    message = alert_message(
        workflow_name="Issue certificates",
        head_branch="chore/cleanup",
        run_event="workflow_dispatch",
        run_url="https://example.invalid/runs/1",
        actor="someone",
    )
    assert message is not None
    assert "Issue certificates" in message
    assert "chore/cleanup" in message
    assert "workflow_dispatch" in message
    assert "someone" in message
    assert "https://example.invalid/runs/1" in message


def test_a_missing_branch_is_reported_not_treated_as_main() -> None:
    """GitHub omits `head_branch` for a run whose branch has since been
    deleted. An absent value must never read as `main` by default -- that
    would make the one case this module cannot positively clear the safer-
    looking answer, backwards from what a security alert should ever do."""
    message = alert_message(
        workflow_name="Issue certificates",
        head_branch=None,
        run_event="workflow_dispatch",
        run_url="https://example.invalid/runs/1",
        actor="someone",
    )
    assert message is not None
    assert "unknown" in message.lower()


def test_an_empty_branch_string_is_also_reported() -> None:
    message = alert_message(
        workflow_name="Issue certificates",
        head_branch="",
        run_event="workflow_dispatch",
        run_url="https://example.invalid/runs/1",
        actor="someone",
    )
    assert message is not None


def test_missing_optional_fields_fall_back_rather_than_raising() -> None:
    message = alert_message(
        workflow_name="",
        head_branch="chore/cleanup",
        run_event="",
        run_url="",
        actor="",
    )
    assert message is not None
    assert "(unknown)" in message


def test_the_message_says_what_it_does_not_confirm() -> None:
    """The one sentence this alert must never omit: it reports a ref, not a
    confirmed leak. Someone reading this on a phone at 11pm must not read
    it as "a secret was definitely just exfiltrated"."""
    message = alert_message(
        workflow_name="Issue certificates",
        head_branch="chore/cleanup",
        run_event="workflow_dispatch",
        run_url="https://example.invalid/runs/1",
        actor="someone",
    )
    assert message is not None
    assert "not that a secret was read" in message or "not that" in message


# --------------------------------------------------------------------- #
# cli.alert_secret_workflow_run -- the thin wrapper the workflow calls
# --------------------------------------------------------------------- #


def _set_run_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    workflow_name: str = "Issue certificates",
    head_branch: str = "main",
    run_event: str = "workflow_dispatch",
    run_url: str = "https://example.invalid/runs/1",
    actor: str = "someone",
) -> None:
    monkeypatch.setenv("WORKFLOW_NAME", workflow_name)
    monkeypatch.setenv("HEAD_BRANCH", head_branch)
    monkeypatch.setenv("RUN_EVENT", run_event)
    monkeypatch.setenv("RUN_URL", run_url)
    monkeypatch.setenv("RUN_ACTOR", actor)


def test_cli_on_main_exits_zero_writes_off_main_false_and_no_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: tmp_path)
    _set_run_env(monkeypatch, head_branch="main")
    output_file = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

    assert cli.alert_secret_workflow_run() == 0

    assert "nothing to report" in capsys.readouterr().out
    assert output_file.read_text(encoding="utf-8") == "off_main=false\n"
    assert not (tmp_path / cli.NOTIFY_BODY).exists()


def test_cli_off_main_no_channel_writes_off_main_true_and_no_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: tmp_path)
    _set_run_env(monkeypatch, head_branch="chore/cleanup")
    output_file = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

    assert cli.alert_secret_workflow_run() == 0

    out = capsys.readouterr().out
    assert "chore/cleanup" in out
    assert "no notification channel is configured" in out
    assert output_file.read_text(encoding="utf-8") == "off_main=true\n"
    assert not (tmp_path / cli.NOTIFY_BODY).exists()


def test_cli_off_main_with_channel_writes_the_body_and_off_main_true(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: tmp_path)
    _set_run_env(monkeypatch, head_branch="chore/cleanup")
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@example/editorial")
    output_file = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

    assert cli.alert_secret_workflow_run() == 0

    body = (tmp_path / cli.NOTIFY_BODY).read_text(encoding="utf-8")
    assert body.startswith("@example/editorial")
    assert "chore/cleanup" in body
    assert output_file.read_text(encoding="utf-8") == "off_main=true\n"
    assert "addressed to thread 42" in capsys.readouterr().out


def test_cli_without_github_output_prints_the_line_instead(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Outside Actions, `$GITHUB_OUTPUT` is unset -- `_write_github_output`'s
    own fallback prints the `key=value` line instead of raising, the same
    "inspectable instead of silent" idiom every other CLI output write in
    this package already uses."""
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: tmp_path)
    _set_run_env(monkeypatch, head_branch="chore/cleanup")

    assert cli.alert_secret_workflow_run() == 0

    assert "off_main=true" in capsys.readouterr().out


def test_cli_never_fails_the_process_itself(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The workflow's own last step decides whether the job fails, by
    reading `off_main` -- this command's own exit code must stay 0 in
    every case, on or off main, channel or no channel, so that step is
    the only place D-25's loud failure actually happens."""
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: tmp_path)
    for branch in ("main", "chore/cleanup", ""):
        _set_run_env(monkeypatch, head_branch=branch)
        assert cli.alert_secret_workflow_run() == 0
