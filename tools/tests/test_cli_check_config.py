from __future__ import annotations

from pathlib import Path

import pytest

from convener_ops.cli import check_config, render_check
from convener_ops.integrations import Integration


def _absent() -> Integration:
    return Integration(
        name="email_transport",
        label="Outbound email",
        secrets=["CONVENER_SMTP_HOST"],
        absent_behaviour="Messages are written to a log instead of being sent.",
        state="absent",
        missing=["CONVENER_SMTP_HOST"],
    )


def _live() -> Integration:
    return Integration(
        name="auth_proxy",
        label="Authentication relay",
        secrets=["CONVENER_AUTH_PROXY_URL"],
        absent_behaviour="Sign-in falls back to a personal access token.",
        state="production",
        missing=[],
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


def test_check_config_exits_zero_with_all_integrations_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_root = tmp_path
    (fake_root / "config").mkdir()
    (fake_root / "config" / "integrations.yml").write_text(
        """
integrations:
  - name: auth_proxy
    label: Authentication relay
    secrets: [CONVENER_AUTH_PROXY_URL]
    absent_behaviour: Sign-in falls back to a personal access token.
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: fake_root)
    monkeypatch.delenv("CONVENER_AUTH_PROXY_URL", raising=False)

    exit_code = check_config()

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Authentication relay" in out
    assert "absent" in out
    assert "FAIL" not in out
    assert "ERROR" not in out
