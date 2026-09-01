"""resolve_registration_secret() and handle_registration(): the two steps
.github/workflows/registration.yml runs for one incoming registration.

The job that decrypts a registration is the one place in this project a
stranger's name and address ever exist as plaintext. These tests are the
ones that hold that line: no name and no address may appear anywhere the
job prints, on any path -- success, a fresh registration, a resend that
updates one, or a failure -- and the same address must never produce a
second record.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import config, speaker
from helpers.command_line import (
    LEAK_STRINGS,
    RecordingSmtpClient,
    publish_event_key,
    write_data,
)

from convener_ops.cli.journey.registration import (
    handle_registration,
    resend_confirmation,
    resolve_registration_secret,
    send_confirmation,
)
from convener_ops.journey import eventkeys
from convener_ops.journey.registration import (
    load_registration_file,
    matching_code,
    to_registration,
)


def _registration_fields(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "first_name": "Ada",
        "surname": "Lovelace",
        "email": "ada@example.org",
        "institution": "Analytical Engines Institute",
        "membership_opt_in": True,
    }
    base.update(overrides)
    return base


def _registration_payload(event_id: str, public_pem: str, **overrides: object) -> str:
    """The whole body `services/signup-relay/src/index.js` forwards:
    `{event_id, v, encrypted_key, iv, ciphertext}`."""
    plaintext = json.dumps(_registration_fields(**overrides)).encode("utf-8")
    envelope = json.loads(eventkeys.encrypt(public_pem, plaintext))
    return json.dumps({"event_id": event_id, **envelope})


def _assert_no_leak(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    for secret in LEAK_STRINGS:
        assert secret.lower() not in combined, f"{secret!r} leaked into job output"
    return captured.out


def test_resolve_registration_secret_with_no_payload_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("REGISTRATION_PAYLOAD", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert resolve_registration_secret() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_resolve_registration_secret_rejects_an_invalid_event_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("REGISTRATION_PAYLOAD", json.dumps({"event_id": "../escape"}))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert resolve_registration_secret() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_resolve_registration_secret_writes_to_github_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, public_pem = eventkeys.generate()
    output_file = tmp_path / "gh_output"
    output_file.write_text("", encoding="utf-8")
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

    assert resolve_registration_secret() == 0

    text = output_file.read_text(encoding="utf-8")
    assert "event_id=mrg-042\n" in text
    assert "secret_name=CONVENER_EVENT_KEY_MRG_042\n" in text


def test_resolve_registration_secret_prints_when_github_output_is_unset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A local run outside Actions -- the same "inspectable instead of
    silent" idiom `_notify` uses for its own absent channel."""
    _, public_pem = eventkeys.generate()
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert resolve_registration_secret() == 0

    out = capsys.readouterr().out
    assert "event_id=mrg-042" in out
    assert "secret_name=CONVENER_EVENT_KEY_MRG_042" in out


def test_handle_registration_with_no_payload_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("REGISTRATION_PAYLOAD", raising=False)

    assert handle_registration() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_handle_registration_fails_closed_without_a_configured_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-13 does not apply here -- `eventkeys.py`'s own exception: an
    absent private key must not fall back to writing anything, encrypted
    or not."""
    _, public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert handle_registration() == 1

    err = capsys.readouterr().err
    assert "no private key configured for event mrg-042" in err
    assert not (tmp_path / "instance" / "data").exists()


def test_handle_registration_does_not_require_a_published_public_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The failure mode this replaces: re-encryption used to read
    `instance/keys/events/<id>.pub` from disk and fail without it. `upsert` now
    derives the matching public half from `private_pem` itself
    (`eventkeys.derive_public_pem`), so this job succeeds even when no
    `.pub` file exists anywhere in the checkout -- removing both the
    failure mode and the possibility of re-encrypting under a stale or
    swapped published key."""
    private_pem, public_pem = eventkeys.generate()
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    assert not (tmp_path / "instance" / "keys").exists()

    assert handle_registration() == 0
    assert (
        "recorded a registration for event mrg-042 (1 total)" in capsys.readouterr().out
    )


def test_handle_registration_rejects_an_undecryptable_payload_and_leaks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_a, _ = publish_event_key(tmp_path)
    _, public_b = eventkeys.generate()
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    # Encrypted under a *different* event's public key: a real registrant
    # would never do this, but the relay's own shape check cannot rule it
    # out, so this job must refuse it, not garble it.
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_b)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_a)

    assert handle_registration() == 1

    out = _assert_no_leak(capsys)
    assert out == ""


def test_handle_registration_refuses_a_field_over_the_length_cap_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The survey twin's own fix applied to
    registration -- a 201-character institution
    decrypts cleanly and is refused by the length cap alone, so the
    message must say "could not be read", never blame decryption for a
    failure that did not happen."""
    private_pem, public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD",
        _registration_payload("mrg-042", public_pem, institution="A" * 201),
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert handle_registration() == 1
    err = capsys.readouterr().err
    assert "registration for event mrg-042 could not be read" in err
    assert "decrypt" not in err.lower()


def test_handle_registration_writes_the_record_and_prints_no_name_or_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The test this whole section exists for: a job that decrypts a registration
    and then prints even one of its fields would pass every other test in
    this file and still leak personal data into a public Actions log."""
    private_pem, public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert handle_registration() == 0

    out = _assert_no_leak(capsys)
    assert "recorded a registration for event mrg-042 (1 total)" in out

    enc_path = (
        tmp_path / "instance" / "data" / "events" / "mrg-042" / "registrations.enc"
    )
    assert enc_path.exists()
    file = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert len(file.entries) == 1
    # Exactly ciphertext -- see test_registration.py's own
    # test_upsert_writes_entries_that_are_exactly_ciphertext for the
    # mutant this specific assertion is written to catch.
    assert set(file.entries[0]) == eventkeys.ENVELOPE_FIELDS
    recovered = to_registration(json.dumps(file.entries[0]), private_pem)
    assert recovered is not None
    assert recovered.email == "ada@example.org"


def test_handle_registration_a_resend_updates_the_one_record_and_still_leaks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Step 3 end to end, through the same entry point the workflow calls
    twice for two submissions: same address, same event -> the second
    updates the first rather than adding a second row."""
    private_pem, public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    assert handle_registration() == 0

    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD",
        _registration_payload("mrg-042", public_pem, institution="Somewhere Else"),
    )
    assert handle_registration() == 0

    out = _assert_no_leak(capsys)
    assert "recorded a registration for event mrg-042 (1 total)" in out
    assert "updated a registration for event mrg-042 (1 total)" in out

    enc_path = (
        tmp_path / "instance" / "data" / "events" / "mrg-042" / "registrations.enc"
    )
    file = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert len(file.entries) == 1
    recovered = to_registration(json.dumps(file.entries[0]), private_pem)
    assert recovered is not None
    assert recovered.institution == "Somewhere Else"


def test_handle_registration_rejects_a_malformed_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = publish_event_key(tmp_path)
    events_dir = tmp_path / "instance" / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "registrations.enc").write_text("not json at all", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert handle_registration() == 1
    assert "registrations.enc" in capsys.readouterr().err


# ------------------------------------------------------------------ #
# handle_registration()'s two-step confirmation flow: sending was moved
# out of the push-retry loop, into its
# own step -- `send_confirmation`, `convener-send-confirmation` -- that
# `.github/workflows/registration.yml` now runs only `if: success()`), and
# resend_confirmation(): the manual resend a lost message asks for.
#
# `_handle_and_send` below runs the same two calls that workflow now makes
# -- `convener-handle-registration` writes what changed to `$GITHUB_OUTPUT`,
# `convener-send-confirmation` reads it back and sends -- through a real
# `GITHUB_OUTPUT` file, the same mechanics production uses, not a shortcut
# available only inside a test process.
#
# Every test below that expects the confirmation to be *unsent* checks the
# file it was left in, never stdout -- `_assert_no_leak` (above) is applied
# to every one of them. It does not cover the matching code itself:
# `LEAK_STRINGS` is a fixed tuple and the code is a different string on
# every run, so the tests that actually derive one (`CONVENER_MATCHING_SALT`
# set) check its absence from stdout/stderr directly, next to computing the
# same code fresh, rather than pretending a static list could name a value
# it cannot know in advance.
# ------------------------------------------------------------------ #


def _write_event(tmp_path: Path, **overrides: object) -> None:
    """`instance/data/speakers.yml` and `instance/data/config.yml`, with one
    record whose `edition_code` matches the `mrg-042` event id every fixture above
    already submits against."""
    record = speaker(
        edition_code="MRG-042",
        zoom_link="https://meet.example.org/permanent-room",
        title="On analytical engines",
        date="2026-09-01",
    )
    record.update(overrides)
    write_data(tmp_path, [record], config())


def _clear_transport_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "CONVENER_SMTP_HOST",
        "CONVENER_SMTP_PORT",
        "CONVENER_SMTP_USER",
        "CONVENER_SMTP_PASSWORD",
        "CONVENER_SMTP_FROM",
        "CONVENER_MATCHING_SALT",
    ):
        monkeypatch.delenv(name, raising=False)


def _handle_and_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The two calls `registration.yml` now makes for one submission:
    `handle_registration` (store, and report what changed via a real
    `$GITHUB_OUTPUT` file) then `send_confirmation` (read `changed` back
    and compose/deliver) -- exactly the split a review asked for,
    so `handle_registration() == 0` alone is no longer
    enough to exercise sending. Reuses one output file across repeated
    calls in the same test (an update sequence calls this twice), which is
    safe because `handle_registration` always re-derives `changed` fresh
    and GitHub Actions itself resolves a repeated output key to the last
    write, exactly like a real, repeated step would.
    """
    output_file = tmp_path / "gh_output"
    if not output_file.exists():
        output_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    assert handle_registration() == 0
    changed = ""
    for line in output_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("changed="):
            changed = line[len("changed=") :]
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("CHANGED_FIELDS", changed)
    assert send_confirmation() == 0


def test_handle_registration_writes_changed_to_github_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first registration reports no change; an update reports the
    field that differs -- both through a real `$GITHUB_OUTPUT` file, the
    channel `send_confirmation` actually reads in production."""
    private_pem, public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    output_file = tmp_path / "gh_output"
    output_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    assert handle_registration() == 0
    assert "changed=\n" in output_file.read_text(encoding="utf-8")

    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD",
        _registration_payload("mrg-042", public_pem, institution="Somewhere Else"),
    )
    assert handle_registration() == 0
    assert "changed=institution\n" in output_file.read_text(encoding="utf-8")


def test_handle_registration_prints_changed_when_github_output_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert handle_registration() == 0

    assert "changed=" in capsys.readouterr().out


def test_handle_registration_reports_and_never_writes_an_unsent_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unsent confirmation is reported, not
    retained -- no `.gitignore`d file, no build artefact, only a printed
    line naming the recovery (`convener-resend-confirmation`)."""
    private_pem, public_pem = publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    _clear_transport_env(monkeypatch)

    _handle_and_send(tmp_path, monkeypatch)

    out = _assert_no_leak(capsys)
    assert "confirmation for event mrg-042 not sent" in out
    assert "convener-resend-confirmation" in out
    assert not (tmp_path / "unsent-confirmation.eml").exists()


def test_handle_registration_confirmation_carries_the_code_when_salted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The property the confirmation exists for: the matching code reaches
    the message, and never reaches stdout. Inspected on the *sent* message
    -- an unsent confirmation is reported rather
    than retained, so there is no file to read it back from."""
    private_pem, public_pem = publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("CONVENER_SMTP_PORT", "587")
    monkeypatch.setenv("CONVENER_SMTP_USER", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_SMTP_PASSWORD", "shh")
    monkeypatch.setenv("CONVENER_SMTP_FROM", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "shh")
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    _handle_and_send(tmp_path, monkeypatch)

    code = matching_code("mrg-042", "ada@example.org", "shh")
    assert code is not None

    out = capsys.readouterr()
    combined = out.out + out.err
    assert code not in combined, "the matching code leaked into stdout/stderr"

    assert len(RecordingSmtpClient.sent) == 1
    body = RecordingSmtpClient.sent[0].get_content()
    assert code in body


def test_handle_registration_confirmation_names_what_changed_on_an_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("CONVENER_SMTP_PORT", "587")
    monkeypatch.setenv("CONVENER_SMTP_USER", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_SMTP_PASSWORD", "shh")
    monkeypatch.setenv("CONVENER_SMTP_FROM", "convener-registration@example.org")
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    _handle_and_send(tmp_path, monkeypatch)

    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD",
        _registration_payload("mrg-042", public_pem, institution="Somewhere Else"),
    )
    _handle_and_send(tmp_path, monkeypatch)

    _assert_no_leak(capsys)
    assert len(RecordingSmtpClient.sent) == 2
    body = RecordingSmtpClient.sent[1].get_content()
    # The whole sentence, not a bare "institution" substring:
    # that word also appears in the data-protection
    # paragraph of every message ever composed, so a check for it alone
    # would still pass a mutant naming the wrong changed field.
    assert (
        "This confirms an update to an earlier registration for this "
        "event: we changed the institution."
    ) in body
    # Named, never quoted: neither the old nor the new value appears.
    assert "Analytical Engines Institute" not in body
    assert "Somewhere Else" not in body


def test_handle_registration_confirmation_says_nothing_about_an_update_the_first_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("CONVENER_SMTP_PORT", "587")
    monkeypatch.setenv("CONVENER_SMTP_USER", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_SMTP_PASSWORD", "shh")
    monkeypatch.setenv("CONVENER_SMTP_FROM", "convener-registration@example.org")
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    _handle_and_send(tmp_path, monkeypatch)

    assert len(RecordingSmtpClient.sent) == 1
    body = RecordingSmtpClient.sent[0].get_content()
    assert "This confirms an update" not in body


def test_handle_registration_confirmation_degrades_with_no_speaker_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `instance/data/speakers.yml` at all -- the state every registration test
    before this one already ran in. The registration must still be
    recorded and a confirmation still composed and sent, only without a
    room link."""
    private_pem, public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("CONVENER_SMTP_PORT", "587")
    monkeypatch.setenv("CONVENER_SMTP_USER", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_SMTP_PASSWORD", "shh")
    monkeypatch.setenv("CONVENER_SMTP_FROM", "convener-registration@example.org")
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    _handle_and_send(tmp_path, monkeypatch)

    out = _assert_no_leak(capsys)
    assert "no speaker record matches event mrg-042" in out

    assert len(RecordingSmtpClient.sent) == 1
    assert RecordingSmtpClient.sent[0]["To"] == "ada@example.org"


def test_handle_registration_survives_an_unanticipated_confirmation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The property `_send_confirmation`'s docstring names directly: a
    registration already decrypted and written to `registrations.enc` must
    never be lost because composing or sending its confirmation broke in a
    way this job did not anticipate. Simulated by making `compose` itself
    raise -- something no branch above the broad `except` already guards
    against."""
    private_pem, public_pem = publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    _clear_transport_env(monkeypatch)

    def _broken_compose(*args: object, **kwargs: object) -> object:
        raise RuntimeError("an unanticipated failure inside compose()")

    monkeypatch.setattr(
        "convener_ops.cli.journey.registration.confirmation.compose", _broken_compose
    )

    _handle_and_send(tmp_path, monkeypatch)

    out = _assert_no_leak(capsys)
    assert "recorded a registration for event mrg-042 (1 total)" in out
    assert "could not be composed or sent" in out

    enc_path = (
        tmp_path / "instance" / "data" / "events" / "mrg-042" / "registrations.enc"
    )
    file = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert len(file.entries) == 1


def test_handle_registration_sends_through_a_configured_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("CONVENER_SMTP_PORT", "587")
    monkeypatch.setenv("CONVENER_SMTP_USER", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_SMTP_PASSWORD", "shh")
    monkeypatch.setenv("CONVENER_SMTP_FROM", "convener-registration@example.org")
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    _handle_and_send(tmp_path, monkeypatch)

    out = _assert_no_leak(capsys)
    assert "confirmation for event mrg-042 sent" in out
    assert len(RecordingSmtpClient.sent) == 1


def test_send_confirmation_with_no_payload_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("REGISTRATION_PAYLOAD", raising=False)
    assert send_confirmation() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_send_confirmation_fails_closed_without_a_configured_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert send_confirmation() == 1
    assert "no private key configured for event mrg-042" in capsys.readouterr().err


def test_send_confirmation_rejects_an_undecryptable_payload_and_leaks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_a, _ = publish_event_key(tmp_path)
    _, public_b = eventkeys.generate()
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_b)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_a)

    assert send_confirmation() == 1

    out = _assert_no_leak(capsys)
    assert out == ""


def test_send_confirmation_refuses_a_field_over_the_length_cap_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Same fix as `test_handle_registration_
    refuses_a_field_over_the_length_cap_honestly`, at the second of the
    two call sites the wrong wording was found at."""
    private_pem, public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD",
        _registration_payload("mrg-042", public_pem, institution="A" * 201),
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert send_confirmation() == 1
    err = capsys.readouterr().err
    assert "registration for event mrg-042 could not be read" in err
    assert "decrypt" not in err.lower()


# --- resend_confirmation() -------------------------------------------- #


def test_resend_confirmation_reproduces_the_original_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The property a manual resend depends on directly: it must
    reproduce the *same* code the original confirmation carried, or the
    first message becomes a lie about which code is current. Inspected on
    the *sent* messages -- an unsent confirmation
    is reported rather than retained, so there is no file to compare."""
    private_pem, public_pem = publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("CONVENER_SMTP_PORT", "587")
    monkeypatch.setenv("CONVENER_SMTP_USER", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_SMTP_PASSWORD", "shh")
    monkeypatch.setenv("CONVENER_SMTP_FROM", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "shh")
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    _handle_and_send(tmp_path, monkeypatch)

    code = matching_code("mrg-042", "ada@example.org", "shh")
    assert code is not None
    original_captured = capsys.readouterr()
    assert code not in (original_captured.out + original_captured.err), (
        "the matching code leaked into stdout/stderr on the original send"
    )
    assert len(RecordingSmtpClient.sent) == 1
    original = RecordingSmtpClient.sent[0].get_content()
    assert code in original

    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv(
        "EMAIL_ENVELOPE", eventkeys.encrypt(public_pem, b"ada@example.org")
    )
    assert resend_confirmation() == 0

    assert len(RecordingSmtpClient.sent) == 2
    resent = RecordingSmtpClient.sent[1].get_content()
    assert code in resent
    assert original == resent

    out = _assert_no_leak(capsys)
    assert code not in out, "the matching code leaked into stdout/stderr on resend"


def test_resend_confirmation_does_not_claim_an_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A resend repeats the current, stored registration -- even one that
    is itself the result of an earlier update must not be described as
    changing again on every resend. Setup only needs the two registrations
    *stored*, not sent, so it calls `handle_registration` bare -- the
    confirmation-sending half is what this test is actually checking, via
    `resend_confirmation` below."""
    private_pem, public_pem = publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    _clear_transport_env(monkeypatch)

    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    assert handle_registration() == 0
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD",
        _registration_payload("mrg-042", public_pem, institution="Somewhere Else"),
    )
    assert handle_registration() == 0

    monkeypatch.setenv("CONVENER_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("CONVENER_SMTP_PORT", "587")
    monkeypatch.setenv("CONVENER_SMTP_USER", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_SMTP_PASSWORD", "shh")
    monkeypatch.setenv("CONVENER_SMTP_FROM", "convener-registration@example.org")
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv(
        "EMAIL_ENVELOPE", eventkeys.encrypt(public_pem, b"ada@example.org")
    )
    assert resend_confirmation() == 0

    assert len(RecordingSmtpClient.sent) == 1
    resent = RecordingSmtpClient.sent[0].get_content()
    assert "This confirms an update" not in resent

    _assert_no_leak(capsys)


def test_resend_confirmation_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)
    assert resend_confirmation() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_resend_confirmation_with_an_invalid_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "../escape")
    assert resend_confirmation() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_resend_confirmation_with_no_email_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EMAIL_ENVELOPE", raising=False)
    assert resend_confirmation() == 1
    assert "no encrypted identifier supplied" in capsys.readouterr().err


def test_resend_confirmation_without_a_configured_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    # Never decrypted -- the missing-key refusal fires before
    # EMAIL_ENVELOPE is read at all.
    monkeypatch.setenv("EMAIL_ENVELOPE", "irrelevant")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert resend_confirmation() == 1
    assert "no private key configured for event mrg-042" in capsys.readouterr().err


def test_resend_confirmation_refuses_an_undecryptable_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-25: an EMAIL_ENVELOPE this job cannot decrypt
    (a stale plaintext address typed in by habit, a corrupted paste, or
    ciphertext meant for a different event) must refuse loudly and
    specifically, never fall through to a generic "no registration
    found" that would misreport why nothing happened."""
    private_pem, _public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EMAIL_ENVELOPE", "ada@example.org")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert resend_confirmation() == 1
    assert "could not be decrypted" in capsys.readouterr().err


def test_resend_confirmation_refuses_an_envelope_decrypting_to_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A well-formed envelope that decrypts to an empty string is not the
    same fact as none being supplied at all, and must say so."""
    private_pem, public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EMAIL_ENVELOPE", eventkeys.encrypt(public_pem, b""))
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert resend_confirmation() == 1
    assert "encrypted identifier is empty" in capsys.readouterr().err


def test_resend_confirmation_with_nothing_recorded_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv(
        "EMAIL_ENVELOPE", eventkeys.encrypt(public_pem, b"ada@example.org")
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert resend_confirmation() == 1
    assert "no registrations recorded for event mrg-042" in capsys.readouterr().err


def test_resend_confirmation_for_an_unknown_address_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    _clear_transport_env(monkeypatch)
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    assert handle_registration() == 0

    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv(
        "EMAIL_ENVELOPE", eventkeys.encrypt(public_pem, b"grace@example.org")
    )

    assert resend_confirmation() == 1
    assert "no registration found for event mrg-042" in capsys.readouterr().err


def test_resend_confirmation_rejects_a_malformed_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = publish_event_key(tmp_path)
    events_dir = tmp_path / "instance" / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "registrations.enc").write_text("not json at all", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv(
        "EMAIL_ENVELOPE", eventkeys.encrypt(public_pem, b"ada@example.org")
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert resend_confirmation() == 1
    assert "registrations.enc" in capsys.readouterr().err
