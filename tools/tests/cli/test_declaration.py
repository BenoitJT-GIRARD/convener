from __future__ import annotations

from pathlib import Path

import pytest

from convener_ops.cli.declaration import check_config, render_check
from convener_ops.declaration.integrations import Integration


def _absent() -> Integration:
    return Integration(
        name="email_transport",
        label="Outbound email",
        secrets=["CONVENER_SMTP_HOST"],
        purpose="Sends the messages a scheduled job addresses to a participant.",
        absent_behaviour="Messages are written to a log instead of being sent.",
        state="absent",
        missing=["CONVENER_SMTP_HOST"],
    )


def _live() -> Integration:
    return Integration(
        name="auth_proxy",
        label="Authentication relay",
        secrets=["CONVENER_AUTH_PROXY_URL"],
        purpose="Signs a volunteer in with a short code.",
        absent_behaviour="Sign-in falls back to a personal access token.",
        state="production",
        missing=[],
    )


def _exceptional_absent() -> Integration:
    return Integration(
        name="event_keys",
        label="Event registration encryption",
        secrets=["CONVENER_EVENT_KEY_<ID>"],
        purpose="Decrypts one event's registrations.",
        absent_behaviour="The job that would decrypt registrations exits in error.",
        absent_is_normal=False,
        state="absent",
        missing=["CONVENER_EVENT_KEY_<ID>"],
    )


def test_absent_integration_shows_the_missing_secret() -> None:
    out = render_check([_absent()])
    assert "Outbound email" in out
    assert "absent" in out
    assert "CONVENER_SMTP_HOST" in out
    assert "written to a log" in out


def test_absent_integration_is_not_reported_as_a_failure() -> None:
    out = render_check([_absent()])
    assert "FAIL" not in out
    assert "ERROR" not in out


def test_live_integration_does_not_list_missing_secrets() -> None:
    out = render_check([_live()])
    assert "production" in out
    assert "CONVENER_AUTH_PROXY_URL" not in out


def test_summary_counts_every_state() -> None:
    out = render_check([_absent(), _live()])
    assert "1 production" in out
    assert "1 absent" in out


def test_footer_is_unchanged_when_every_absent_row_is_normal() -> None:
    out = render_check([_absent(), _live()])
    assert "An absent integration is a normal state, not a failure." in out
    assert "except" not in out


def test_a_row_that_declares_itself_exceptional_but_is_live_changes_nothing() -> None:
    """`absent_is_normal: false` only matters while the row actually is
    absent -- a row that is currently `production` has nothing to warn
    about, so it gets no inline marker and does not touch the footer."""
    live_exception = Integration(
        name="event_keys",
        label="Event registration encryption",
        secrets=["CONVENER_EVENT_KEY_<ID>"],
        purpose="Decrypts one event's registrations.",
        absent_behaviour="unused",
        absent_is_normal=False,
        state="production",
        missing=[],
    )
    out = render_check([live_exception])
    assert "not a normal absence" not in out
    assert "An absent integration is a normal state, not a failure." in out
    assert "except" not in out


def test_an_exceptional_absence_is_marked_inline_and_named_in_the_footer() -> None:
    out = render_check([_absent(), _exceptional_absent()])

    assert "Event registration encryption - absent  (not a normal absence" in out
    assert (
        "An absent integration is a normal state, not a failure -- "
        "except Event registration encryption, marked above." in out
    )
    # The five ordinary rows are not charged for the sixth: their own
    # section of the output carries no exception marker.
    assert "Outbound email - absent  (not a normal" not in out


def test_check_config_exits_zero_with_all_integrations_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_root = tmp_path
    (fake_root / "declarations").mkdir()
    (fake_root / "declarations" / "integrations.yml").write_text(
        """
integrations:
  - name: auth_proxy
    label: Authentication relay
    secrets: [CONVENER_AUTH_PROXY_URL]
    purpose: Signs a volunteer in with a short code.
    absent_behaviour: Sign-in falls back to a personal access token.
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("convener_ops.cli.declaration.repo_root", lambda: fake_root)
    monkeypatch.delenv("CONVENER_AUTH_PROXY_URL", raising=False)

    exit_code = check_config()

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Authentication relay" in out
    assert "absent" in out
    assert "FAIL" not in out
    assert "ERROR" not in out
