from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from convener_ops.integrations import load_declaration, resolve_states

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
