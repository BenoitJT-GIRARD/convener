"""invite_survey() / record_survey_invitation(): e-mail the
post-event survey link to every currently *matched* attendee of one
event, and never a second time by default. Like
`match_attendance` (`test_attendance.py`), these tests check that no name
or address ever
reaches stdout, on any path including a refusal -- and that an unmatched
or an unreachable attendee is never invited, that a closed survey
refuses outright, and that a resend without resend_all invites nobody.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest
import yaml
from conftest import speaker
from helpers.command_line import (
    LEAK_STRINGS,
    RecordingSmtpClient,
    publish_event_key,
    write_attendance_csv,
    write_registrations,
)

from convener_ops.cli.journey.survey import (
    invite_survey,
    record_survey_invitation,
)
from convener_ops.governance.rule import paris_today
from convener_ops.journey import eventkeys
from convener_ops.journey.registration import (
    Registration,
    RegistrationFile,
    dump_registration_file,
    load_registration_file,
)
from convener_ops.journey.survey_invite import survey_url


def _prepare_survey_event(
    tmp_path: Path,
    *,
    event_id: str = "mrg-042",
    registrations: tuple[Registration, ...] = (),
    attendance_rows: tuple[str, ...] = (),
    survey_enabled: bool = True,
) -> str:
    """Everything `invite_survey` needs on disk for one event, short of the
    environment variables a test still sets for itself. Returns
    `event_private_pem`. Mirrors `prepare_event` (the certificate
    section's own twin) but never writes `config.yml` -- `invite_survey`
    computes no eligibility threshold, so it tolerates a missing one, the
    same way `match_attendance` already does."""
    private_pem, _ = publish_event_key(tmp_path, event_id)
    if registrations:
        write_registrations(tmp_path, event_id, private_pem, *registrations)
    if attendance_rows:
        write_attendance_csv(tmp_path, event_id, *attendance_rows)
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "speakers.yml").write_text(
        yaml.safe_dump(
            [
                speaker(
                    edition_code=event_id.upper(),
                    title="On analytical engines",
                    date="2026-08-20",
                    survey_enabled=survey_enabled,
                )
            ]
        ),
        encoding="utf-8",
    )
    return private_pem


_ADA_REG = Registration("Ada", "Lovelace", "ada@example.org", "", False)

_SURVEY_SMTP_ENV: dict[str, str] = {
    "CONVENER_SMTP_HOST": "smtp.example.org",
    "CONVENER_SMTP_PORT": "587",
    "CONVENER_SMTP_USER": "convener-survey@example.org",
    "CONVENER_SMTP_PASSWORD": "shh",
    "CONVENER_SMTP_FROM": "convener-survey@example.org",
}


def _assert_survey_leak_sweep(captured_text: str) -> None:
    """The sweep every `invite_survey` test in
    this section now runs, on every path including a refusal -- took the
    already-captured text as a plain string, never `capsys` itself, the
    exact fix the harness bug needs: a helper that re-reads `capsys.readouterr()` after
    the caller already drained it observes nothing and passes vacuously.
    Asserting the text is non-empty first is what makes that failure mode
    itself fail loudly here, rather than pass silently forever."""
    assert captured_text.strip(), (
        "expected some output to sweep for a leak, got none -- a sweep "
        "with nothing to check proves nothing"
    )
    combined = captured_text.lower()
    for secret in LEAK_STRINGS:
        assert secret.lower() not in combined, f"{secret!r} leaked into job output"


class _FlakySurveySmtpClient:
    """A fake `smtplib.SMTP` whose *first* send
    attempt across the whole test fails with a transient `OSError`, and
    every attempt after that succeeds -- proves `invite_survey` retries a
    failed delivery once, in place, before counting it as unsent."""

    attempts: ClassVar[int] = 0
    sent: ClassVar[list[object]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        pass

    def starttls(self) -> None:
        pass

    def login(self, user: str, password: str) -> None:
        pass

    def send_message(self, message: object) -> None:
        _FlakySurveySmtpClient.attempts += 1
        if _FlakySurveySmtpClient.attempts == 1:
            raise OSError("transient failure")
        _FlakySurveySmtpClient.sent.append(message)

    def __enter__(self) -> _FlakySurveySmtpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_invite_survey_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)
    assert invite_survey() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_invite_survey_with_an_invalid_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "../escape")
    assert invite_survey() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_invite_survey_refuses_when_the_switch_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Inviting people to a closed survey would be a fourth
    hole beside the three `_survey_enabled` already guards."""
    _prepare_survey_event(tmp_path, survey_enabled=False)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert invite_survey() == 1
    captured = capsys.readouterr()
    assert "the survey is not enabled for event mrg-042" in captured.err
    _assert_survey_leak_sweep(captured.out + captured.err)


def test_invite_survey_with_no_speaker_record_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert invite_survey() == 1
    captured = capsys.readouterr()
    assert "the survey is not enabled for event mrg-042" in captured.err
    _assert_survey_leak_sweep(captured.out + captured.err)


def test_invite_survey_without_a_configured_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepare_survey_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert invite_survey() == 1
    captured = capsys.readouterr()
    assert "no private key configured" in captured.err
    _assert_survey_leak_sweep(captured.out + captured.err)


def test_invite_survey_with_nothing_recorded_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem = _prepare_survey_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert invite_survey() == 1
    captured = capsys.readouterr()
    assert "no registrations recorded" in captured.err
    _assert_survey_leak_sweep(captured.out + captured.err)


def test_invite_survey_catches_a_platform_request_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `except` in `invite_survey` re-prints
    whatever `platform.py`/`platform_fcc.py` composed -- text this module
    does not control. Mutating that line to append every decrypted
    address survived the full suite
    before this sweep existed; it does not now."""
    private_pem = _prepare_survey_event(tmp_path, registrations=(_ADA_REG,))
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    # No attendance-import.csv on disk at all -- ManualPlatform's own
    # missing-file failure, the same one match_attendance already catches.

    assert invite_survey() == 1
    captured = capsys.readouterr()
    assert "no attendance export" in captured.err
    _assert_survey_leak_sweep(captured.out + captured.err)


def test_invite_survey_only_invites_the_matched_attendee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mutant behind "only the matched attendee": an attendance export
    naming a matched
    attendee, an unmatched one (an address the cascade cannot tie to any
    registration) and an unreachable one (a telephone joiner, no address
    at all) -- only the first is ever composed or sent, and never invited,
    the message counts the other two separately,
    not folded into one "not invited" figure that would misdescribe the
    unmatched half as having no address on file at all."""
    private_pem = _prepare_survey_event(
        tmp_path,
        registrations=(_ADA_REG,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
            "Grace Hopper,grace@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,3600",
            "Some Caller,,2026-08-20T18:00:00Z,2026-08-20T19:00:00Z,1800",
        ),
    )
    for key, value in _SURVEY_SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    assert invite_survey() == 0
    captured = capsys.readouterr()
    assert (
        "1 sent, 0 not sent (1 matched attendee(s); 1 unmatched -- present, "
        "but no registration found for their address; 1 unreachable -- "
        "joined by phone, no address ever collected; 0 registration(s) could "
        "not be read)" in captured.out
    )
    out = captured.out + captured.err
    _assert_survey_leak_sweep(out)
    for stray in ("grace", "hopper", "grace@example.org", "some caller"):
        assert stray not in out.lower(), f"{stray!r} leaked into job output"
    assert out.isascii(), "this command's own output is ASCII by construction"

    assert len(RecordingSmtpClient.sent) == 1
    email = RecordingSmtpClient.sent[0]
    assert email["To"] == "ada@example.org"


def test_invite_survey_skips_an_entry_that_fails_to_decrypt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stray entry encrypted under an unrelated key pair -- well-formed
    envelope shape, but undecryptable with this event's own key. Skipped,
    not treated as a match, the same handling `match_attendance` and
    `issue_certificates` already give a stray undecryptable entry --
    carried item 10, the fourth of the four commands that share
    `_load_registrations`: it must not go unreported here either."""
    private_pem = _prepare_survey_event(
        tmp_path,
        registrations=(_ADA_REG,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    path = tmp_path / "instance" / "data" / "events" / "mrg-042" / "registrations.enc"
    file = load_registration_file(path.read_text(encoding="utf-8"))
    _other_private, other_public = eventkeys.generate()
    stray = json.loads(eventkeys.encrypt(other_public, b'{"not": "ours"}'))
    file = RegistrationFile(entries=(*file.entries, stray))
    path.write_text(dump_registration_file(file), encoding="utf-8")
    for key, value in _SURVEY_SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    assert invite_survey() == 0
    out = capsys.readouterr().out
    assert "1 sent, 0 not sent" in out
    assert "1 registration(s) could not be read" in out
    assert len(RecordingSmtpClient.sent) == 1


def test_invite_survey_composes_the_same_link_for_every_matched_attendee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    private_pem = _prepare_survey_event(
        tmp_path,
        registrations=(_ADA_REG, grace),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
            "Grace Hopper,grace@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    for key, value in _SURVEY_SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    assert invite_survey() == 0
    captured = capsys.readouterr()
    assert "2 sent, 0 not sent" in captured.out
    _assert_survey_leak_sweep(captured.out + captured.err)

    assert len(RecordingSmtpClient.sent) == 2
    bodies = [message.get_content() for message in RecordingSmtpClient.sent]
    links = {re.search(r"https://\S+", body).group(0) for body in bodies}  # type: ignore[union-attr]
    assert links == {survey_url("mrg-042")}


def test_invite_survey_with_no_transport_configured_reports_all_unsent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem = _prepare_survey_event(
        tmp_path,
        registrations=(_ADA_REG,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    for key in _SURVEY_SMTP_ENV:
        monkeypatch.delenv(key, raising=False)

    assert invite_survey() == 0
    captured = capsys.readouterr()
    assert "0 sent, 1 not sent" in captured.out
    _assert_survey_leak_sweep(captured.out + captured.err)

    output_path = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    output_path.write_text("", encoding="utf-8")
    assert invite_survey() == 0
    assert "record=false" in output_path.read_text(encoding="utf-8")


def test_invite_survey_writes_record_true_to_github_output_when_something_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem = _prepare_survey_event(
        tmp_path,
        registrations=(_ADA_REG,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    for key, value in _SURVEY_SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )
    output_path = tmp_path / "gh_output"
    output_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    assert invite_survey() == 0
    captured = capsys.readouterr()
    assert "record=true" in output_path.read_text(encoding="utf-8")
    _assert_survey_leak_sweep(captured.out + captured.err)


def test_invite_survey_refuses_a_second_time_without_resend_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mutant behind "invited once": once this event is on record as
    invited, a
    routine re-dispatch sends nothing further -- and touches no
    registration at all, so it cannot leak anything either. It also
    asserts `record=false` was actually written -- mutating that
    line to `record=true` survived the full suite until this assertion
    existed, harmless only because the recorder is itself idempotent."""
    _prepare_survey_event(tmp_path)
    registry_path = tmp_path / "instance" / "data" / "survey-invitations.yml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        "v: 1\ninvitations:\n- event_id: mrg-042\n  invited_on: '2026-08-01'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("RESEND_ALL", raising=False)
    output_path = tmp_path / "gh_output"
    output_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    assert invite_survey() == 0
    captured = capsys.readouterr()
    assert "already invited on 2026-08-01" in captured.out
    assert "no invitations sent this run" in captured.out
    _assert_survey_leak_sweep(captured.out + captured.err)
    assert "record=false" in output_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("resend_all_value", "expect_resend"),
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("false", False),
        ("False", False),
        ("", False),
        ("1", False),
        ("yes", False),
    ],
)
def test_invite_survey_resend_all_only_recognises_the_literal_true(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    resend_all_value: str,
    expect_resend: bool,
) -> None:
    """`RESEND_ALL: ${{ inputs.resend_all }}` is
    the literal string `"false"` when an operator leaves the workflow's own
    checkbox unticked -- untested for a long time, every existing
    test either deleted the variable or set it to `"true"`. Mutating the
    comparison from `== "true"` to `!= ""` survived the full suite and made
    every dispatch a full resend; this parametrisation exercises every
    value the workflow (`"true"`/`"false"`, exactly what a boolean
    `workflow_dispatch` input renders as) or a raw API dispatch could
    actually send, and pins that only `"true"`, case-insensitively, forces
    a resend."""
    private_pem = _prepare_survey_event(
        tmp_path,
        registrations=(_ADA_REG,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    registry_path = tmp_path / "instance" / "data" / "survey-invitations.yml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        "v: 1\ninvitations:\n- event_id: mrg-042\n  invited_on: '2026-08-01'\n",
        encoding="utf-8",
    )
    for key, value in _SURVEY_SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("RESEND_ALL", resend_all_value)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    assert invite_survey() == 0
    if expect_resend:
        assert len(RecordingSmtpClient.sent) == 1
    else:
        assert len(RecordingSmtpClient.sent) == 0
        assert "already invited" in capsys.readouterr().out


def test_invite_survey_resend_all_invites_the_matched_attendee_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem = _prepare_survey_event(
        tmp_path,
        registrations=(_ADA_REG,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    registry_path = tmp_path / "instance" / "data" / "survey-invitations.yml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        "v: 1\ninvitations:\n- event_id: mrg-042\n  invited_on: '2026-08-01'\n",
        encoding="utf-8",
    )
    for key, value in _SURVEY_SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("RESEND_ALL", "true")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    RecordingSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", RecordingSmtpClient
    )

    assert invite_survey() == 0
    captured = capsys.readouterr()
    assert "1 sent, 0 not sent" in captured.out
    _assert_survey_leak_sweep(captured.out + captured.err)
    assert len(RecordingSmtpClient.sent) == 1


def test_invite_survey_retries_a_failed_delivery_once_before_giving_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A transient failure on the first attempt
    must not force a whole-batch `resend_all` -- `invite_survey` retries
    once, in place, and this attendee's second attempt succeeds."""
    private_pem = _prepare_survey_event(
        tmp_path,
        registrations=(_ADA_REG,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    for key, value in _SURVEY_SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    _FlakySurveySmtpClient.attempts = 0
    _FlakySurveySmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.confirmation.smtplib.SMTP", _FlakySurveySmtpClient
    )

    assert invite_survey() == 0
    assert "1 sent, 0 not sent" in capsys.readouterr().out
    assert _FlakySurveySmtpClient.attempts == 2
    assert len(_FlakySurveySmtpClient.sent) == 1


def test_invite_survey_rejects_a_malformed_committed_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepare_survey_event(tmp_path)
    registry_path = tmp_path / "instance" / "data" / "survey-invitations.yml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("not valid at all: [", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert invite_survey() == 1
    captured = capsys.readouterr()
    assert "survey-invitations.yml" in captured.err
    _assert_survey_leak_sweep(captured.out + captured.err)


def test_record_survey_invitation_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)
    assert record_survey_invitation() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_record_survey_invitation_writes_a_fresh_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert record_survey_invitation() == 0

    registry_path = tmp_path / "instance" / "data" / "survey-invitations.yml"
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert data == {
        "v": 1,
        "invitations": [
            {
                "event_id": "mrg-042",
                "invited_on": paris_today(datetime.now(UTC)).isoformat(),
            }
        ],
    }


def test_record_survey_invitation_is_idempotent_and_keeps_the_first_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "instance" / "data" / "survey-invitations.yml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        "v: 1\ninvitations:\n- event_id: mrg-042\n  invited_on: '2026-08-01'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert record_survey_invitation() == 0

    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert data["invitations"] == [{"event_id": "mrg-042", "invited_on": "2026-08-01"}]


def test_record_survey_invitation_rejects_a_malformed_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_path = tmp_path / "instance" / "data" / "survey-invitations.yml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("not valid at all: [", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert record_survey_invitation() == 1
    assert "survey-invitations.yml" in capsys.readouterr().err
