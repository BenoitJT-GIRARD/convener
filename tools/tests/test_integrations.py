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


def test_absent_is_normal_defaults_to_true_when_not_declared(tmp_path: Path) -> None:
    integrations = load_declaration(_write(tmp_path))
    assert all(i.absent_is_normal for i in integrations)


def test_absent_is_normal_false_is_read_from_the_declaration(tmp_path: Path) -> None:
    path = tmp_path / "integrations.yml"
    path.write_text(
        """
integrations:
  - name: event_keys
    label: Event registration encryption
    secrets: [CONVENER_EVENT_KEY_<ID>]
    absent_is_normal: false
    absent_behaviour: The job that would decrypt registrations exits in error.
""",
        encoding="utf-8",
    )
    integrations = load_declaration(path)
    assert integrations[0].absent_is_normal is False


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


def test_exactly_these_three_rows_declare_themselves_an_exception() -> None:
    """Pinned as data, not left to a reader noticing prose: two years from
    now, a new integration copied from a neighbouring row inherits
    `absent_is_normal: true` by default (see `Integration`), so this only
    breaks if someone deliberately declares a fourth exception -- which is
    exactly when this test should make them explain why.

    Two, not one: certificate_fingerprint
    was split out of matching_salt because the two consumers of
    CONVENER_MATCHING_SALT disagree about whether their own absence is ordinary
    -- a single row could only carry one `absent_is_normal` value, so it
    necessarily lied about whichever consumer disagreed with it.

    Three: retention_token joins the two above for
    the strongest reason in this project -- a retention job that exits 0
    having destroyed nothing must never look, from the Actions tab,
    identical to a run that genuinely had nothing to do. See
    `tools/convener_ops/cli.py::retention_sweep`'s own docstring."""
    declaration = load_declaration(repo_root() / "config" / "integrations.yml")
    exceptions = [i.name for i in declaration if not i.absent_is_normal]
    assert exceptions == ["event_keys", "retention_token", "certificate_fingerprint"]


#: How this file's own opening paragraph spells a count. Only the range a
#: ten-row declaration can reach; a count past it fails by KeyError, which
#: is the right failure -- a declaration with eleven exceptions needs the
#: sentence rewritten, not a longer table.
_COUNT_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


def _opening_paragraph(text: str) -> str:
    """The declaration's first comment paragraph -- every `#` line before
    the first bare `#`. That paragraph is the sentence this test is about;
    the ones after it discuss individual rows by name, including rows whose
    absence *is* ordinary, so sweeping the whole header would be sweeping
    the wrong thing."""
    lines: list[str] = []
    for line in text.splitlines():
        if line.strip() in ("#", ""):
            break
        assert line.startswith("#"), "the declaration does not open with a comment"
        lines.append(line.lstrip("#").strip())
    return " ".join(lines)


def test_this_declarations_own_header_names_every_exception() -> None:
    """The half of the row above that nothing was reading.

    `absent_is_normal` is pinned as data. The sentence
    at the top of `config/integrations.yml` that *describes* it was not,
    and it said "with one exception, event_keys" for two phases after the
    second and third rows were added -- through a task that corrected the
    identical sentence in `integrations.py`'s docstring and left this one,
    the more authoritative of the two and the one the cockpit's settings
    screen reads and ships into the demonstration.

    Nothing here transcribes the answer: the names and the count both come
    out of the declaration this paragraph is the header of, so a fourth
    exception fails this test by name rather than making the sentence
    quietly wrong again.
    """
    path = repo_root() / "config" / "integrations.yml"
    declaration = load_declaration(path)
    opening = _opening_paragraph(path.read_text(encoding="utf-8"))

    exceptions = [i.name for i in declaration if not i.absent_is_normal]
    ordinary = [i.name for i in declaration if i.absent_is_normal]
    assert exceptions and ordinary, "a declaration with only one kind of row"

    assert f"{_COUNT_WORDS[len(exceptions)]} exception" in opening, (
        f"the header does not count the {len(exceptions)} rows that declare "
        f"`absent_is_normal: false`: {opening!r}"
    )
    for name in exceptions:
        assert name in opening, f"the header does not name the exception {name}"
    for name in ordinary:
        assert name not in opening, (
            f"the header names {name} among the exceptions, but that row's "
            "absence is an ordinary state"
        )


def _first_paragraph(text: str) -> str:
    """A Markdown page's first paragraph after its title -- every line up
    to the first blank one. The paragraphs after it discuss individual
    integrations, including ones whose absence *is* ordinary, so sweeping
    the whole page would be sweeping the wrong thing."""
    paragraphs = text.split("\n\n")
    return " ".join(paragraphs[1].split()) if len(paragraphs) > 1 else ""


def test_the_handbook_page_names_every_exception_the_declaration_holds() -> None:
    """The fourth copy of the same sentence.

    `config/integrations.yml`'s own header and
    `tools/convener_ops/integrations.py`'s docstring and comment were
    corrected from one exception to three when the second and third rows
    declared themselves; `docs/reference/operations.md` opens by making
    the same claim and was not, because nothing read it. It is read here,
    against the declaration rather than against a list written out again:
    a fourth row declaring `absent_is_normal: false` fails this test by
    name, and so does a row that stops being one.

    The rows are named by their `label`, which is what
    `convener-check-config` prints, so a reader who meets the sentence and
    then runs the report sees the same three words. The page's own section
    headings are not the labels -- *Retention and early erasure* holds the
    retention credential -- and binding to those would have made this test
    a check on a heading rather than on the claim.
    """
    declaration = load_declaration(repo_root() / "config" / "integrations.yml")
    page = (repo_root() / "docs" / "reference" / "operations.md").read_text(
        encoding="utf-8"
    )
    opening = _first_paragraph(page)

    exceptions = [i.label for i in declaration if not i.absent_is_normal]
    ordinary = [i.label for i in declaration if i.absent_is_normal]
    assert exceptions and ordinary, "a declaration with only one kind of row"

    assert f"{_COUNT_WORDS[len(exceptions)]} exception" in opening, (
        f"the page does not count the {len(exceptions)} integrations that "
        f"declare `absent_is_normal: false`: {opening!r}"
    )
    for label in exceptions:
        assert label in opening, f"the page does not name the exception {label!r}"
    for label in ordinary:
        assert label not in opening, (
            f"the page names {label!r} among the exceptions, but that "
            "integration's absence is an ordinary state"
        )


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
