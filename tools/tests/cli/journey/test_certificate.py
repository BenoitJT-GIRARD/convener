"""issue_certificates() / certificates_public_data(): match,
check eligibility, issue (or reproduce) a certificate per eligible
attendee, and keep the register. Like `match_attendance`
(`test_attendance.py`), these tests check that no name or address ever
reaches stdout or the
certificate register file, plus the two guarantees this section exists
for: no certificate is issued without both CONVENER_SIGNING_KEY and
CONVENER_MATCHING_SALT configured, and reissuing an already-registered
attendee never grows the register.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import config, speaker
from helpers.command_line import (
    CERT_ID,
    CERT_ID_OTHER,
    assert_no_personal_data_leaked,
    certificates_register_path,
    prepare_event,
    publish_event_key,
    write_attendance_csv,
    write_certificate_register,
    write_registrations,
)

from convener_ops.cli.journey.certificate import (
    certificates_public_data,
    issue_certificates,
    reissue_certificate,
    revoke_certificate,
)
from convener_ops.governance.rule import paris_today
from convener_ops.journey import eventkeys
from convener_ops.journey.attendance import MatchedAttendee
from convener_ops.journey.certificate import (
    CertificateEntry,
    CertificateEvent,
    IssueResult,
)
from convener_ops.journey.certificate import fingerprint as certificate_fingerprint
from convener_ops.journey.certificate import issue as certificate_issue
from convener_ops.journey.platform import (
    AttendanceRow,
)
from convener_ops.journey.platform_fcc import (
    FCCRequestError,
    PlatformFCC,
)
from convener_ops.journey.registration import (
    Registration,
    RegistrationFile,
    dump_registration_file,
    load_registration_file,
    upsert,
)
from convener_ops.journey.signing import generate


def test_issue_certificates_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)

    assert issue_certificates() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_issue_certificates_without_a_configured_event_key_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert issue_certificates() == 1
    assert "no private key configured" in capsys.readouterr().err


def test_issue_certificates_without_a_signing_key_issues_nothing_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-13's ordinary shape: no CONVENER_SIGNING_KEY, no certificate, a clean
    exit -- and, because this check runs before registrations.enc is even
    opened, no registration data is touched at all."""
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_SIGNING_KEY", raising=False)

    assert issue_certificates() == 0
    assert "CONVENER_SIGNING_KEY not configured" in capsys.readouterr().out
    assert not certificates_register_path(tmp_path).exists()


def test_issue_certificates_with_an_unloadable_signing_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unlike the D-13 case above, a *present*
    but unusable `CONVENER_SIGNING_KEY` -- a secret pasted with a mangled PEM
    header, the ordinary way this fails in Actions -- used to reach
    `signing.sign` from inside the issuance loop and crash with an
    unhandled `signing.SigningError` traceback. Validated once, before
    anything is decrypted, so this is now a one-line refusal instead."""
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", "not-a-pem-at-all")
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert issue_certificates() == 1
    assert "CONVENER_SIGNING_KEY" in capsys.readouterr().err
    assert not certificates_register_path(tmp_path).exists()


def test_issue_certificates_without_a_matching_salt_issues_nothing_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one deliberate exception to D-13 here: an absent
    CONVENER_MATCHING_SALT is not the ordinary state `declarations/integrations.yml`
    documents for `matching_code` -- a certificate fingerprint cannot be
    computed safely without it, so this run issues nothing rather than
    writing one unsafely. Same outward shape as the signing-key case
    above (a line, a clean exit, nothing written); the message names the
    real reason."""
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert issue_certificates() == 0
    assert "CONVENER_MATCHING_SALT not configured" in capsys.readouterr().out
    assert not certificates_register_path(tmp_path).exists()


def test_issue_certificates_with_nothing_recorded_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert issue_certificates() == 1
    assert "no registrations recorded" in capsys.readouterr().err


def test_issue_certificates_with_a_missing_config_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert issue_certificates() == 1
    assert "config.yml" in capsys.readouterr().err


def test_issue_certificates_rejects_a_malformed_committed_registrations_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    events_dir = tmp_path / "instance" / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "registrations.enc").write_text("not json at all", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert issue_certificates() == 1
    assert "registrations.enc" in capsys.readouterr().err


def test_issue_certificates_catches_a_platform_request_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mirrors `match_attendance`'s own handling of the same exception,
    raised by whichever `Platform` implementation is in play."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(ada,)
    )

    class _FailingPlatform:
        def get_attendance(self, event_id: str) -> list[AttendanceRow]:
            raise FCCRequestError(f"GET /conferences/{event_id}/calls failed: timeout")

    monkeypatch.setattr(
        "convener_ops.cli.journey.certificate.platform_from_env",
        lambda *args, **kwargs: _FailingPlatform(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert issue_certificates() == 1
    assert "failed" in capsys.readouterr().err.lower()


def test_issue_certificates_issues_one_certificate_for_an_eligible_attendee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert issue_certificates() == 0
    captured = capsys.readouterr()
    assert (
        "1 issued, 0 already on record (1 eligible;"
        " 0 registration(s) could not be read)" in captured.out
    )
    assert_no_personal_data_leaked(captured.out + captured.err)

    register_text = certificates_register_path(tmp_path).read_text(encoding="utf-8")
    assert register_text.endswith("\n")
    register_data = yaml.safe_load(register_text)
    [entry] = register_data["certificates"]
    assert entry["event_id"] == "mrg-042"
    assert entry["state"] == "issued"
    assert entry["issued_on"] == paris_today(datetime.now(UTC)).isoformat()
    assert_no_personal_data_leaked(register_text)


def test_issue_certificates_warns_when_the_event_title_is_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """There was a time when a title over
    `certificate._MAX_TITLE_LENGTH` was truncated on the signed,
    delivered certificate with nothing telling an operator it happened."""
    from convener_ops.journey.certificate import _MAX_TITLE_LENGTH

    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    # Overwrite the speaker record `prepare_event` already wrote, with an
    # over-long title -- everything else about the event stays identical.
    (tmp_path / "instance" / "data" / "speakers.yml").write_text(
        yaml.safe_dump(
            [
                speaker(
                    edition_code="MRG-042",
                    title="x" * (_MAX_TITLE_LENGTH + 50),
                    date="2026-08-20",
                )
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert issue_certificates() == 0
    captured = capsys.readouterr()
    assert "::warning::" in captured.err
    assert "mrg-042" in captured.err
    assert "truncated" in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)


# ------------------------------------------------------------------ #
# Nothing populated `conference_ids` for a long time,
# so the FCC path (`CONVENER_MEETING_API_TOKEN` configured) always
# raised `EventNotFoundError` before it ever reached the network -- a gap
# 10's own review found exactly this value stubbed out of every test and
# invisible to branch coverage for `release_recording`; the identical gap
# existed here, unnoticed, until somebody actually ran the wired job
# rather than only reading it. `_FakeFCCTransport` is a minimal
# `FCCTransport`-shaped fake for the one method `get_attendance` calls
# (`get_json`), keyed by the exact path it is asked for -- the same
# discipline `test_attendance_recording.py`'s own `_FakeRecordingTransport`
# uses for `release_recording`, kept separate from it rather than shared,
# so that neither command's tests can be satisfied by the other's fake.
# ------------------------------------------------------------------ #


class _FakeFCCTransport:
    def __init__(self, path: str, calls: list[dict[str, Any]]) -> None:
        self._path = path
        self._calls = calls
        self.get_calls: list[str] = []

    def get_json(self, path: str, token: str) -> Any:
        self.get_calls.append(path)
        if path != self._path:
            raise AssertionError(f"unexpected GET {path}")
        return self._calls


def _fcc_call(
    *,
    display_name: str = "Ada Lovelace",
    email: str = "ada@example.org",
    start: datetime = datetime(2026, 8, 20, 18, 0, 0, tzinfo=UTC),
    duration_seconds: int = 5400,
) -> dict[str, Any]:
    return {
        "custom_name": display_name,
        "email": email,
        "service_types": ["voip"],
        "time_created_utc": int(start.timestamp()),
        "time_disconnected_utc": int(start.timestamp()) + duration_seconds,
        "audio_duration": duration_seconds,
        "is_host": False,
    }


def _patch_fcc_platform(
    monkeypatch: pytest.MonkeyPatch, transport: _FakeFCCTransport
) -> None:
    def fake_platform_from_env(
        env: Any,
        speakers: Any = (),
        config: Any = None,
        conference_ids: Any = None,
        *,
        private_pem: str | None = None,
    ) -> PlatformFCC:
        return PlatformFCC(
            access_token="tok",
            speakers=speakers,
            config=config,
            conference_ids=dict(conference_ids or {}),
            transport=transport,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(
        "convener_ops.cli.journey.certificate.platform_from_env", fake_platform_from_env
    )


def test_issue_certificates_uses_the_conference_id_named_by_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proves `CONVENER_FCC_CONFERENCE_ID` genuinely reaches `conference_ids`:
    the fake transport only answers under one specific, non-hardcoded
    path. A version of `issue_certificates` that ignores the input (builds
    `{}` regardless, or hardcodes a different conference id) reaches the
    wrong path -- `PlatformFCC._conference_id` then raises
    `EventNotFoundError` for `event_id`, and this test fails on the return
    code and the empty register alike, never silently passing."""
    conference_id = "618515381"
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(ada,)
    )
    transport = _FakeFCCTransport(f"/conferences/{conference_id}/calls", [_fcc_call()])
    _patch_fcc_platform(monkeypatch, transport)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.setenv("CONVENER_FCC_CONFERENCE_ID", conference_id)

    assert issue_certificates() == 0
    assert transport.get_calls == [f"/conferences/{conference_id}/calls"]
    captured = capsys.readouterr()
    assert (
        "1 issued, 0 already on record (1 eligible;"
        " 0 registration(s) could not be read)" in captured.out
    )
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_issue_certificates_reports_cleanly_when_no_conference_id_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`EventNotFoundError` used not to be
    in `issue_certificates`'s own `except` tuple, so this exact
    situation -- a token configured, no conference id for this event --
    crashed with an unhandled traceback instead of the one-line refusal
    `issue_certificates`'s own docstring already promised every other
    failure. Asserted on the message, not only the return code, so a fix
    that merely swallows the traceback without naming the reason would
    still fail this test."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(ada,)
    )
    transport = _FakeFCCTransport("/conferences/000000/calls", [])
    _patch_fcc_platform(monkeypatch, transport)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.delenv("CONVENER_FCC_CONFERENCE_ID", raising=False)

    assert issue_certificates() == 1
    assert "no FCC conference is recorded for event 'mrg-042'" in (
        capsys.readouterr().err
    )
    assert transport.get_calls == []
    assert not certificates_register_path(tmp_path).exists()


def test_issue_certificates_clamps_a_double_counted_duration_at_the_seminar_length(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two attendance rows for one person --
    a reconnection and a genuinely simultaneous second device look
    identical to `attendance.match`, and both sum -- must never sign more
    credit than the seminar's own scheduled length: 90 minutes, `config()`'s
    default, against 180 minutes of summed attendance here.

    The register never carries a duration and the signed token is
    deliberately never printed or returned by `issue_certificates` (see
    `certificate.py`'s own module docstring, "idempotent without being
    deterministic"), so the only way to observe what was actually signed
    is to intercept the call to `certificate.issue` itself -- `_spy`
    below delegates to the real function so `issue_certificates`'s own
    behaviour (register writes, counts) is otherwise unaffected."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    captured_durations: list[int] = []

    def _spy(
        attendee: MatchedAttendee,
        event: CertificateEvent,
        private_pem: str,
        salt: str,
        existing: Sequence[CertificateEntry],
        *,
        issued_on: date,
    ) -> IssueResult:
        captured_durations.append(attendee.duration_seconds)
        return certificate_issue(
            attendee, event, private_pem, salt, existing, issued_on=issued_on
        )

    monkeypatch.setattr("convener_ops.cli.journey.certificate.issue", _spy)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert issue_certificates() == 0
    # 10800s summed (double the 90-minute session) capped to 5400s -- the
    # seminar's own scheduled length, not a fraction chosen after the fact.
    assert captured_durations == [90 * 60]


def test_issue_certificates_skips_an_entry_that_fails_to_decrypt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stray entry encrypted under an unrelated key pair -- well-formed
    envelope shape, undecryptable with this event's own key. Skipped, not
    treated as a match, the same handling `match_attendance` already gives
    a stray undecryptable entry -- but, carried item 10, no longer
    silently: the printed line now says so."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    file = load_registration_file(None)
    file, _replaced = upsert(file, ada, private_pem=event_private_pem)
    _other_private, other_public = eventkeys.generate()
    stray = json.loads(eventkeys.encrypt(other_public, b'{"not": "ours"}'))
    file = RegistrationFile(entries=(*file.entries, stray))
    (
        tmp_path / "instance" / "data" / "events" / "mrg-042" / "registrations.enc"
    ).write_text(dump_registration_file(file), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert issue_certificates() == 0
    out = capsys.readouterr().out
    assert "1 issued, 0 already on record (1 eligible" in out
    assert "1 registration(s) could not be read" in out


def test_issue_certificates_skips_an_attendee_below_the_eligibility_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        # 30 of 90 scheduled minutes -- well under the two-thirds default.
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T18:30:00Z,1800",
        ),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert issue_certificates() == 0
    captured = capsys.readouterr()
    assert (
        "0 issued, 0 already on record (0 eligible;"
        " 0 registration(s) could not be read)" in captured.out
    )
    assert not certificates_register_path(tmp_path).exists()
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_issue_certificates_run_twice_does_not_grow_the_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A corrected match recalculating without re-registering, exercised
    through the real
    CLI wiring: running the job a second time over the exact same event
    reproduces the same one register entry, reported as already on
    record, never a second row.

    Also a regression this project has had: this is the branch
    every retry, every re-run and every scheduled re-execution actually
    takes -- the normal state, not the exceptional one -- and a name and
    an address printed only here survived the full suite until this sweep
    was added on the second run's own output."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert issue_certificates() == 0
    first_register = certificates_register_path(tmp_path).read_text(encoding="utf-8")
    capsys.readouterr()  # discard the first run's own output

    assert issue_certificates() == 0
    second_captured = capsys.readouterr()
    assert (
        "0 issued, 1 already on record (1 eligible;"
        " 0 registration(s) could not be read)" in second_captured.out
    )
    assert_no_personal_data_leaked(second_captured.out + second_captured.err)
    second_register = certificates_register_path(tmp_path).read_text(encoding="utf-8")
    assert second_register == first_register


def test_issue_certificates_rejects_a_malformed_committed_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    register_path = certificates_register_path(tmp_path)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text("not yaml at all: [unclosed", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert issue_certificates() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_issue_certificates_rejects_a_register_of_the_wrong_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Valid YAML, but not this format -- distinct from the previous test,
    which never gets past the YAML parse at all. This one exercises
    `register_from_data`'s own refusal."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    register_path = certificates_register_path(tmp_path)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text(
        yaml.safe_dump({"v": 999, "certificates": []}), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert issue_certificates() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_issue_certificates_refuses_when_no_speaker_record_supplies_a_title_and_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The original choice here
    mirrored `_send_confirmation`'s "never let a missing room lookup stop
    the thing that matters" -- but that reasoning does not carry.
    `_send_confirmation` degrades a room link in an e-mail that can be
    resent; this would sign `event: ""` and `date: ""` into a permanent,
    third-party-facing document, with the empty register row reused (and
    the empty document kept valid) on every future re-run. Refuse
    instead, before anything is signed or written."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    private_pem, _ = publish_event_key(tmp_path)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "speakers.yml").write_text(yaml.safe_dump([]), encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    signing_private_pem, _ = generate()
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert issue_certificates() == 1
    captured = capsys.readouterr()
    assert "no speaker record" in captured.err
    assert "mrg-042" in captured.err
    assert not certificates_register_path(tmp_path).exists()
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_issue_certificates_refuses_and_names_the_parse_failure_of_speakers_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A review's own reproduction: a
    `instance/data/speakers.yml` that fails to *parse* used to be indistinguishable
    from an event genuinely absent from a well-formed file -- both landed
    on `EventNotFoundError` and the same "no speaker record matches"
    message, sending an operator looking for a missing record that was
    never actually missing. `_load`'s own errors are surfaced instead."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    private_pem, _ = publish_event_key(tmp_path)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "speakers.yml").write_text("- title: [unterminated", encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    signing_private_pem, _ = generate()
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert issue_certificates() == 1
    captured = capsys.readouterr()
    assert "speakers.yml" in captured.err
    assert "no speaker record" not in captured.err
    assert not certificates_register_path(tmp_path).exists()
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_certificates_public_data_aggregates_every_events_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    events_dir = tmp_path / "instance" / "data" / "events"
    (events_dir / "mrg-042").mkdir(parents=True)
    (events_dir / "mrg-042" / "certificates.yml").write_text(
        yaml.safe_dump(
            {
                "v": 1,
                "certificates": [
                    {
                        "identifier": "aaa",
                        "event_id": "mrg-042",
                        "issued_on": "2026-08-20",
                        "fingerprint": "f" * 64,
                        "state": "issued",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (events_dir / "mrg-043").mkdir(parents=True)
    (events_dir / "mrg-043" / "certificates.yml").write_text(
        yaml.safe_dump(
            {
                "v": 1,
                "certificates": [
                    {
                        "identifier": "bbb",
                        "event_id": "mrg-043",
                        "issued_on": "2026-09-01",
                        "fingerprint": "e" * 64,
                        "state": "revoked",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert certificates_public_data() == 0
    assert "wrote 2 certificates" in capsys.readouterr().out

    written = json.loads(
        (tmp_path / "instance" / "public-data" / "certificates-public.json").read_text(
            encoding="utf-8"
        )
    )
    assert written == [
        {"identifier": "aaa", "state": "issued"},
        {"identifier": "bbb", "state": "revoked"},
    ]
    for row in written:
        assert set(row) == {"identifier", "state"}


def test_certificates_public_data_with_no_events_directory_writes_an_empty_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert certificates_public_data() == 0
    written = json.loads(
        (tmp_path / "instance" / "public-data" / "certificates-public.json").read_text(
            encoding="utf-8"
        )
    )
    assert written == []


def test_certificates_public_data_rejects_a_malformed_register_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    events_dir = tmp_path / "instance" / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "certificates.yml").write_text(
        "not yaml: [unclosed", encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert certificates_public_data() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_certificates_public_data_rejects_a_register_of_the_wrong_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Valid YAML, but not this format -- exercises `register_from_data`'s
    own refusal, distinct from the previous test's YAML-parse failure."""
    events_dir = tmp_path / "instance" / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "certificates.yml").write_text(
        yaml.safe_dump({"v": 999, "certificates": []}), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert certificates_public_data() == 1
    assert "certificates.yml" in capsys.readouterr().err


# ------------------------------------------------------------------ #
# reissue_certificate() / revoke_certificate(): two operator actions, run
# by hand for one certificate, identified by CERTIFICATE_ID and never an
# address. `reissue_certificate` resolves CERTIFICATE_ID to a
# registration by computing each currently eligible attendee's own
# fingerprint and matching it against the register row's -- the same
# derivation `certificate.issue` performs, run in reverse -- so most
# refusal paths below need only *some* register row to exist under
# CERTIFICATE_ID (`write_certificate_register`'s dummy fingerprint is
# never compared against anything before the refusal fires); the tests
# that exercise the fingerprint match itself compute a real one with
# `certificate_fingerprint`, matching what `prepare_event`'s own
# registration would produce.
# ------------------------------------------------------------------ #


def test_reissue_certificate_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)

    assert reissue_certificate() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_reissue_certificate_without_a_configured_event_key_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert reissue_certificate() == 1
    assert "no private key configured" in capsys.readouterr().err


def test_reissue_certificate_with_an_unloadable_signing_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same guard applies equally here: a present but unusable
    `CONVENER_SIGNING_KEY` must refuse cleanly, never crash with a traceback."""
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", "not-a-pem-at-all")

    assert reissue_certificate() == 1
    assert "CONVENER_SIGNING_KEY" in capsys.readouterr().err


def test_reissue_certificate_without_a_signing_key_reissues_nothing_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_SIGNING_KEY", raising=False)

    assert reissue_certificate() == 0
    assert "CONVENER_SIGNING_KEY not configured" in capsys.readouterr().out


def test_reissue_certificate_without_a_matching_salt_reissues_nothing_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert reissue_certificate() == 0
    assert "CONVENER_MATCHING_SALT not configured" in capsys.readouterr().out


def test_reissue_certificate_without_a_certificate_id_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CERTIFICATE_ID", raising=False)

    assert reissue_certificate() == 1
    assert "no certificate id supplied" in capsys.readouterr().err


def test_reissue_certificate_refuses_a_malformed_certificate_id_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`is_valid_identifier` refuses anything that
    is not exactly 32 lowercase hex characters -- checked before this
    value is ever echoed into a log line. The refusal message never
    repeats the malformed value back (the same "no valid event id
    supplied" idiom `eventkeys.secret_name`'s own caller already uses),
    which also proves an embedded newline could not have reached a log
    line through this path."""
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", "cert-under-test")

    assert reissue_certificate() == 1
    captured = capsys.readouterr()
    assert "not a valid certificate id" in captured.err
    assert "cert-under-test" not in captured.err


def test_reissue_certificate_with_nothing_recorded_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert reissue_certificate() == 1
    assert "no registrations recorded" in capsys.readouterr().err


def test_reissue_certificate_rejects_a_malformed_committed_registrations_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    events_dir = tmp_path / "instance" / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "registrations.enc").write_text("not json at all", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert reissue_certificate() == 1
    assert "registrations.enc" in capsys.readouterr().err


def test_reissue_certificate_refuses_when_the_certificate_id_is_not_on_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The replacement for the old email-not-registered refusal: with
    no register at all (or one that never named this id), there is
    nothing to resolve a fingerprint against, so this refuses before ever
    computing eligibility."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 1
    captured = capsys.readouterr()
    assert "no certificate" in captured.err
    assert "on record" in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_reissue_certificate_with_a_missing_config_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    private_pem, _ = publish_event_key(tmp_path)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    write_certificate_register(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert reissue_certificate() == 1
    assert "config.yml" in capsys.readouterr().err


def test_reissue_certificate_catches_a_platform_request_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(ada,)
    )
    write_certificate_register(tmp_path)

    class _FailingPlatform:
        def get_attendance(self, event_id: str) -> list[AttendanceRow]:
            raise FCCRequestError(f"GET /conferences/{event_id}/calls failed: timeout")

    monkeypatch.setattr(
        "convener_ops.cli.journey.certificate.platform_from_env",
        lambda *args, **kwargs: _FailingPlatform(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert reissue_certificate() == 1
    assert "failed" in capsys.readouterr().err.lower()


def test_reissue_certificate_uses_the_conference_id_named_by_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reissue-side twin of `issue_certificates`'s own equivalent test
    -- see that test's own docstring for the
    full reasoning. `reissue_certificate` shares `_conference_ids_from_env`
    with `issue_certificates`, so this proves the shared helper is
    genuinely wired into both callers, not only one."""
    conference_id = "618515381"
    salt = "s3cr3t-salt-value"
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(ada,)
    )
    write_certificate_register(
        tmp_path,
        identifier=CERT_ID,
        fingerprint_value=certificate_fingerprint("mrg-042", "ada@example.org", salt),
        state="revoked",
    )
    transport = _FakeFCCTransport(f"/conferences/{conference_id}/calls", [_fcc_call()])
    _patch_fcc_platform(monkeypatch, transport)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", salt)
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.setenv("CONVENER_FCC_CONFERENCE_ID", conference_id)
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert reissue_certificate() == 0
    assert transport.get_calls == [f"/conferences/{conference_id}/calls"]
    captured = capsys.readouterr()
    assert "reissued" in captured.out
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_reissue_certificate_reports_cleanly_when_no_conference_id_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reissue-side twin of
    `issue_certificates`'s own equivalent test -- see that test's own
    docstring. This exact situation -- a token
    configured, no conference id for this event -- crashed with an
    unhandled traceback instead of refusing cleanly."""
    salt = "s3cr3t-salt-value"
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(ada,)
    )
    write_certificate_register(
        tmp_path,
        identifier=CERT_ID,
        fingerprint_value=certificate_fingerprint("mrg-042", "ada@example.org", salt),
        state="revoked",
    )
    transport = _FakeFCCTransport("/conferences/000000/calls", [])
    _patch_fcc_platform(monkeypatch, transport)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", salt)
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.delenv("CONVENER_FCC_CONFERENCE_ID", raising=False)
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert reissue_certificate() == 1
    assert "no FCC conference is recorded for event 'mrg-042'" in (
        capsys.readouterr().err
    )
    assert transport.get_calls == []


def test_reissue_certificate_refuses_when_the_certificate_id_matches_nobody_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The replacement for the old "not currently eligible" refusal: a
    register row exists (any row -- its own fingerprint is never compared
    against anything before `eligible` turns out empty), but nobody
    currently eligible for this event can match it."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        # 30 of 90 scheduled minutes -- well under the two-thirds default.
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T18:30:00Z,1800",
        ),
    )
    write_certificate_register(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 1
    captured = capsys.readouterr()
    assert "does not match any currently eligible attendee" in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_reissue_certificate_rejects_a_malformed_committed_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    register_path = certificates_register_path(tmp_path)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text("not yaml at all: [unclosed", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_reissue_certificate_rejects_a_register_of_the_wrong_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Valid YAML, but not this format -- exercises `register_from_data`'s
    own refusal, distinct from the malformed-YAML test above."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    register_path = certificates_register_path(tmp_path)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text(
        yaml.safe_dump({"v": 999, "certificates": []}), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_reissue_certificate_refuses_when_no_speaker_record_supplies_a_title_and_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same guard applies here: reissuing must never sign a corrected
    certificate that names no event and no date, any more than a first
    issuance may. This is the first test in this block where the register
    row's own fingerprint has to be real: reaching this refusal requires
    the fingerprint match to have already succeeded and found Ada."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    private_pem, _ = publish_event_key(tmp_path)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "speakers.yml").write_text(yaml.safe_dump([]), encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    salt = "s3cr3t-salt-value"
    write_certificate_register(
        tmp_path,
        identifier=CERT_ID,
        fingerprint_value=certificate_fingerprint("mrg-042", "ada@example.org", salt),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", salt)
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 1
    captured = capsys.readouterr()
    assert "no speaker record" in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_reissue_certificate_refuses_and_names_the_parse_failure_of_speakers_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    private_pem, _ = publish_event_key(tmp_path)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "speakers.yml").write_text("- title: [unterminated", encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    salt = "s3cr3t-salt-value"
    write_certificate_register(
        tmp_path,
        identifier=CERT_ID,
        fingerprint_value=certificate_fingerprint("mrg-042", "ada@example.org", salt),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", salt)
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 1
    captured = capsys.readouterr()
    assert "speakers.yml" in captured.err
    assert "no speaker record" not in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_reissue_certificate_refuses_when_the_standing_certificate_is_still_issued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guard reissue exists for: reissuing over a still-issued row would
    leave two valid, contradictory certificates standing at once. An
    operator must revoke first -- this run, with nothing revoked yet,
    refuses instead."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    assert issue_certificates() == 0
    capsys.readouterr()
    [entry] = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]

    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])
    assert reissue_certificate() == 1
    captured = capsys.readouterr()
    assert "revoke" in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_reissue_certificate_mints_a_new_identifier_while_the_old_row_stays_revoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The end-to-end correction these commands exist
    for: issue, revoke (`convener-revoke-certificate` -- no more hand edit),
    then reissue by `CERTIFICATE_ID` (no address anywhere). The register
    must end up with exactly two rows for this one person: the original,
    still `revoked`, under its original identifier, and a fresh, `issued`
    row under a genuinely new one."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    assert issue_certificates() == 0
    capsys.readouterr()
    original = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"][0]

    monkeypatch.setenv("CERTIFICATE_ID", original["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()

    assert reissue_certificate() == 0
    captured = capsys.readouterr()
    assert "reissued" in captured.out
    assert original["identifier"] in captured.out
    assert_no_personal_data_leaked(captured.out + captured.err)

    register_text = certificates_register_path(tmp_path).read_text(encoding="utf-8")
    assert_no_personal_data_leaked(register_text)
    certificates = yaml.safe_load(register_text)["certificates"]
    assert len(certificates) == 2
    by_identifier = {row["identifier"]: row for row in certificates}
    assert by_identifier[original["identifier"]]["state"] == "revoked"
    [new_identifier] = [
        identifier
        for identifier in by_identifier
        if identifier != original["identifier"]
    ]
    assert by_identifier[new_identifier]["state"] == "issued"
    assert by_identifier[new_identifier]["fingerprint"] == original["fingerprint"]


def test_reissue_certificate_resolves_to_the_matching_registration_not_another_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guarantee, pinned directly: two eligible attendees, two
    issued certificates, one revoked and reissued by its own
    `CERTIFICATE_ID`. The correction must land on the person that id
    actually names, resolved by fingerprint -- never on whichever eligible
    attendee happens to be matched first, and never touching the other
    row.

    Deliberately revokes and reissues the *second* person seen in the
    attendance rows (Grace), not the first (Ada): a resolution bug that
    fell back to `eligible[0]` regardless of the register row's own
    fingerprint would silently resolve to Ada instead, whose own row is
    still `issued` -- `certificate.reissue`'s "already issued" guard would
    then make this call return `1`, not `0`, so a mutant this coarse is
    caught by the return code alone; a subtler bug that happened to pick
    the right *count* of candidates but the wrong *identity* is what the
    row-by-row assertions below are for."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada, grace),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
            "Grace Hopper,grace@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    assert issue_certificates() == 0
    capsys.readouterr()
    before = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    assert len(before) == 2
    salt = "s3cr3t-salt-value"
    ada_fingerprint = certificate_fingerprint("mrg-042", "ada@example.org", salt)
    [ada_row] = [row for row in before if row["fingerprint"] == ada_fingerprint]
    [grace_row] = [row for row in before if row["fingerprint"] != ada_fingerprint]

    monkeypatch.setenv("CERTIFICATE_ID", grace_row["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()

    assert reissue_certificate() == 0
    captured = capsys.readouterr()
    assert_no_personal_data_leaked(captured.out + captured.err)

    after_text = certificates_register_path(tmp_path).read_text(encoding="utf-8")
    assert_no_personal_data_leaked(after_text)
    after = yaml.safe_load(after_text)["certificates"]
    assert len(after) == 3

    # Ada's own row must be byte-for-byte untouched: still issued, still
    # under her original identifier and fingerprint.
    [still_ada] = [row for row in after if row["identifier"] == ada_row["identifier"]]
    assert still_ada == ada_row

    # Grace's original row stays revoked under its own identifier, and the
    # one new row carries *her* fingerprint, never Ada's.
    grace_fingerprint = grace_row["fingerprint"]
    [still_grace_original] = [
        row for row in after if row["identifier"] == grace_row["identifier"]
    ]
    assert still_grace_original["state"] == "revoked"
    assert still_grace_original["fingerprint"] == grace_fingerprint
    [new_row] = [
        row
        for row in after
        if row["identifier"] not in (ada_row["identifier"], grace_row["identifier"])
    ]
    assert new_row["state"] == "issued"
    assert new_row["fingerprint"] == grace_fingerprint


def test_reissue_certificate_skips_a_stray_entry_that_fails_to_decrypt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stray entry encrypted under an unrelated key pair -- well-formed
    envelope shape, undecryptable with this event's own key -- must not
    stop a correction for the one registration that does decrypt, the
    same handling `issue_certificates` already gives a stray entry."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    assert issue_certificates() == 0
    capsys.readouterr()
    [entry] = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()

    file = load_registration_file(
        (
            tmp_path / "instance" / "data" / "events" / "mrg-042" / "registrations.enc"
        ).read_text(encoding="utf-8")
    )
    _other_private, other_public = eventkeys.generate()
    stray = json.loads(eventkeys.encrypt(other_public, b'{"not": "ours"}'))
    file = RegistrationFile(entries=(*file.entries, stray))
    (
        tmp_path / "instance" / "data" / "events" / "mrg-042" / "registrations.enc"
    ).write_text(dump_registration_file(file), encoding="utf-8")

    assert reissue_certificate() == 0
    assert "reissued" in capsys.readouterr().out


# ------------------------------------------------------------------ #
# revoke_certificate(): revocation, given a real caller for the first
# time.
# `certificate.revoke` needed no signing key and no matching salt -- see
# its own docstring, "revocation touches the register, never the
# signature" -- and neither does this command: only EVENT_ID and
# CERTIFICATE_ID, both public identifiers, never an address.
# ------------------------------------------------------------------ #


def test_revoke_certificate_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)

    assert revoke_certificate() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_revoke_certificate_without_a_certificate_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("CERTIFICATE_ID", raising=False)

    assert revoke_certificate() == 1
    assert "no certificate id supplied" in capsys.readouterr().err


def test_revoke_certificate_refuses_a_malformed_certificate_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same shape check `reissue_certificate`
    applies, checked before this value could ever be echoed into a log
    line -- see that test's own docstring for the full reasoning."""
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", "cert-under-test")

    assert revoke_certificate() == 1
    captured = capsys.readouterr()
    assert "not a valid certificate id" in captured.err
    assert "cert-under-test" not in captured.err


def test_revoke_certificate_rejects_a_malformed_committed_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    register_path = certificates_register_path(tmp_path)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text("not yaml at all: [unclosed", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert revoke_certificate() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_revoke_certificate_rejects_a_register_of_the_wrong_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    register_path = certificates_register_path(tmp_path)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text(
        yaml.safe_dump({"v": 999, "certificates": []}), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert revoke_certificate() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_revoke_certificate_refuses_an_unknown_identifier_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`certificate.revoke`'s own guard, surfaced verbatim -- this is the
    guard the whole command turns on: unreachable from a text editor,
    reachable here. The one register row on file must come back
    unchanged."""
    write_certificate_register(tmp_path, identifier=CERT_ID)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID_OTHER)

    assert revoke_certificate() == 1
    captured = capsys.readouterr()
    assert "cannot revoke" in captured.err
    assert CERT_ID_OTHER in captured.err
    register_text = certificates_register_path(tmp_path).read_text(encoding="utf-8")
    assert yaml.safe_load(register_text)["certificates"][0]["state"] == "issued"


def test_revoke_certificate_refuses_a_row_naming_a_different_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercised through the real CLI command, not
    only `certificate.revoke` directly (see `test_certificate.py`'s own
    unit-level pair): `instance/data/events/mrg-042/certificates.yml` can still
    carry a row whose own `event_id` field names a different event --
    `register_from_data` does not itself refuse one -- and this event's
    own revoke command must not be able to touch it."""
    write_certificate_register(tmp_path, event_id="mrg-042", identifier=CERT_ID)
    foreign_path = certificates_register_path(tmp_path, event_id="mrg-042")
    data = yaml.safe_load(foreign_path.read_text(encoding="utf-8"))
    data["certificates"][0]["event_id"] = "mrg-999"
    foreign_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert revoke_certificate() == 1
    captured = capsys.readouterr()
    assert "cannot revoke" in captured.err
    register_text = foreign_path.read_text(encoding="utf-8")
    assert yaml.safe_load(register_text)["certificates"][0]["state"] == "issued"


def test_revoke_certificate_writes_no_file_when_it_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID_OTHER)

    assert revoke_certificate() == 1
    capsys.readouterr()
    assert not certificates_register_path(tmp_path).exists()


def test_revoke_certificate_revokes_the_named_certificate_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_certificate_register(tmp_path, identifier=CERT_ID, state="issued")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert revoke_certificate() == 0
    captured = capsys.readouterr()
    assert CERT_ID in captured.out
    assert "revoked" in captured.out

    register_text = certificates_register_path(tmp_path).read_text(encoding="utf-8")
    assert register_text.endswith("\n")
    [entry] = yaml.safe_load(register_text)["certificates"]
    assert entry["identifier"] == CERT_ID
    assert entry["state"] == "revoked"


def test_revoke_certificate_only_revokes_the_named_identifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mutation this runs directly: a
    `convener-revoke-certificate` that revoked the wrong identifier, or flipped
    every row instead of one, would still pass a single-entry register
    test. Two rows, only one named -- the other must come back
    byte-for-byte the row it started as."""
    path = certificates_register_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "v": 1,
                "certificates": [
                    {
                        "identifier": CERT_ID,
                        "event_id": "mrg-042",
                        "issued_on": "2026-08-20",
                        "fingerprint": "a" * 64,
                        "state": "issued",
                    },
                    {
                        "identifier": CERT_ID_OTHER,
                        "event_id": "mrg-042",
                        "issued_on": "2026-08-20",
                        "fingerprint": "b" * 64,
                        "state": "issued",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert revoke_certificate() == 0
    capsys.readouterr()

    certificates = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    by_identifier = {row["identifier"]: row for row in certificates}
    assert by_identifier[CERT_ID]["state"] == "revoked"
    assert by_identifier[CERT_ID_OTHER] == {
        "identifier": CERT_ID_OTHER,
        "event_id": "mrg-042",
        "issued_on": "2026-08-20",
        "fingerprint": "b" * 64,
        "state": "issued",
    }
