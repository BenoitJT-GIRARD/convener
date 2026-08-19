from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from convener_ops.integrations import load_declaration, resolve_states
from convener_ops.paths import repo_root

DECLARATION = """
integrations:
  - name: auth_proxy
    label: Authentication relay
    secrets: [CONVENER_AUTH_PROXY_URL, CONVENER_GITHUB_APP_CLIENT_ID]
    absent_behaviour: Sign-in falls back to a personal access token.
  - name: meeting_provider
    label: Meeting platform
    secrets: [CONVENER_MEETING_API_TOKEN]
    absent_behaviour: The manual adapter is used; no room link is published.
"""


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "integrations.yml"
    path.write_text(DECLARATION, encoding="utf-8")
    return path


def test_declaration_is_loaded(tmp_path: Path) -> None:
    integrations = load_declaration(_write(tmp_path))
    assert [i.name for i in integrations] == ["auth_proxy", "meeting_provider"]
    assert integrations[0].secrets == [
        "CONVENER_AUTH_PROXY_URL",
        "CONVENER_GITHUB_APP_CLIENT_ID",
    ]


def test_absent_when_no_secret_is_set(tmp_path: Path) -> None:
    resolved = resolve_states(load_declaration(_write(tmp_path)), env={})
    assert all(i.state == "absent" for i in resolved)


def test_absent_when_only_some_secrets_are_set(tmp_path: Path) -> None:
    env = {"CONVENER_AUTH_PROXY_URL": "https://relay.example"}
    resolved = resolve_states(load_declaration(_write(tmp_path)), env=env)
    by_name = {i.name: i for i in resolved}
    assert by_name["auth_proxy"].state == "absent"
    assert by_name["auth_proxy"].missing == ["CONVENER_GITHUB_APP_CLIENT_ID"]


def test_production_when_all_secrets_are_set(tmp_path: Path) -> None:
    env = {
        "CONVENER_AUTH_PROXY_URL": "https://relay.example",
        "CONVENER_GITHUB_APP_CLIENT_ID": "Iv1.abc",
    }
    resolved = resolve_states(load_declaration(_write(tmp_path)), env=env)
    by_name = {i.name: i for i in resolved}
    assert by_name["auth_proxy"].state == "production"
    assert by_name["auth_proxy"].missing == []


def test_trial_when_marked_as_such(tmp_path: Path) -> None:
    env = {
        "CONVENER_AUTH_PROXY_URL": "https://relay.example",
        "CONVENER_GITHUB_APP_CLIENT_ID": "Iv1.abc",
        "CONVENER_AUTH_PROXY_TRIAL": "1",
    }
    resolved = resolve_states(load_declaration(_write(tmp_path)), env=env)
    assert {i.name: i.state for i in resolved}["auth_proxy"] == "trial"


def test_empty_string_counts_as_unset(tmp_path: Path) -> None:
    env = {"CONVENER_AUTH_PROXY_URL": "  ", "CONVENER_GITHUB_APP_CLIENT_ID": ""}
    resolved = resolve_states(load_declaration(_write(tmp_path)), env=env)
    assert {i.name: i.state for i in resolved}["auth_proxy"] == "absent"


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "integrations.yml"
    path.write_text("integrations: [unterminated", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_declaration(path)


# ------------------------------------------------------------------ #
# The real declaration
# ------------------------------------------------------------------ #


def test_email_transport_declares_the_smtp_port() -> None:
    """Gmail requires port 587 with STARTTLS; other providers require 465
    with implicit TLS. Hardcoding either would silently exclude the other, so
    the port is a secret like the rest of the transport rather than a
    constant -- and an absent one must be reported exactly like an absent
    host, user, password or from-address, not specially."""
    declaration = load_declaration(repo_root() / "config" / "integrations.yml")
    email = next(i for i in declaration if i.name == "email_transport")
    assert set(email.secrets) == {
        "CONVENER_SMTP_HOST",
        "CONVENER_SMTP_PORT",
        "CONVENER_SMTP_USER",
        "CONVENER_SMTP_PASSWORD",
        "CONVENER_SMTP_FROM",
    }


def test_email_transport_is_absent_when_only_the_port_is_missing() -> None:
    """The port is resolved through the same generic `secrets` list as its
    four siblings -- nothing in `resolve_states` singles it out -- so an
    environment with everything except the port is `absent`, exactly as an
    environment missing the host would be."""
    declaration = load_declaration(repo_root() / "config" / "integrations.yml")
    env = {
        "CONVENER_SMTP_HOST": "smtp.example.org",
        "CONVENER_SMTP_USER": "board",
        "CONVENER_SMTP_PASSWORD": "secret",
        "CONVENER_SMTP_FROM": "board@example.org",
    }
    resolved = {i.name: i for i in resolve_states(declaration, env=env)}
    email = resolved["email_transport"]
    assert email.state == "absent"
    assert email.missing == ["CONVENER_SMTP_PORT"]
