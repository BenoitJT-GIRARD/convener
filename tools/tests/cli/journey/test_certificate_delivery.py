"""deliver_certificates() / deliver_certificate(): the only step in this
project that sends a nominative document anywhere (by e-mail, never as
a named document deposited in a repository). Like the tests of the same
command module's issuing half (`test_certificate.py`), these check that no
name or address ever reaches stdout or the
certificate register -- and that the *rendered document* never reaches
disk either, that a replay reproduces
the identical document rather than regenerating one, and that the
already-registered
path leaks nothing, not only the freshly-issued one -- a real defect
once found in certificate.py, guarded here in a second module.
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml
from conftest import config
from helpers.command_line import (
    CERT_ID,
    assert_no_personal_data_leaked,
    certificates_register_path,
    prepare_event,
    publish_event_key,
    write_attendance_csv,
    write_certificate_register,
    write_registrations,
)

from convener_ops.cli.journey.certificate import (
    deliver_certificate,
    deliver_certificates,
    issue_certificates,
    reissue_certificate,
    revoke_certificate,
)
from convener_ops.journey import eventkeys
from convener_ops.journey.certificate import fingerprint as certificate_fingerprint
from convener_ops.journey.platform import (
    AttendanceRow,
)
from convener_ops.journey.platform_fcc import (
    FCCRequestError,
)
from convener_ops.journey.registration import (
    Registration,
    RegistrationFile,
    dump_registration_file,
    load_registration_file,
    upsert,
)
from convener_ops.journey.signing import derive_public_pem, generate, verify

#: The same fixture `test_certificate.py`'s `issue_certificates` tests
#: use, so the certificate register a `deliver_certificates` test reads is
#: genuinely the one `issue_certificates` would have written moments
#: before it, in the real workflow.
_ADA = Registration("Ada", "Lovelace", "ada@example.org", "", False)
_ADA_ATTENDANCE_ROW = (
    "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400"
)

_SMTP_ENV: dict[str, str] = {
    "CONVENER_SMTP_HOST": "smtp.example.org",
    "CONVENER_SMTP_PORT": "587",
    "CONVENER_SMTP_USER": "convener-certificates@example.org",
    "CONVENER_SMTP_PASSWORD": "shh",
    "CONVENER_SMTP_FROM": "convener-certificates@example.org",
}


class _RecordingCertificateSmtpClient:
    """A fake `smtplib.SMTP`, substituted so `deliver_certificates` and
    `deliver_certificate` can exercise a genuine "sent" outcome without
    opening a socket. Kept separate from
    `helpers.command_line.RecordingSmtpClient` (confirmation's own fake)
    rather than shared, so a test here can never be satisfied by state a
    confirmation test left behind, or vice versa."""

    sent: ClassVar[list[Any]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        pass

    def starttls(self) -> None:
        pass

    def login(self, user: str, password: str) -> None:
        pass

    def send_message(self, message: Any) -> None:
        _RecordingCertificateSmtpClient.sent.append(message)

    def __enter__(self) -> _RecordingCertificateSmtpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _sent_attachment_html(message: Any) -> str:
    [attachment] = list(message.iter_attachments())
    content = attachment.get_content()
    assert isinstance(content, str)
    return content


def test_deliver_certificates_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)
    assert deliver_certificates() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_deliver_certificates_without_a_configured_event_key_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)
    assert deliver_certificates() == 1
    assert "no private key configured" in capsys.readouterr().err


def test_deliver_certificates_without_a_signing_key_delivers_nothing_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_SIGNING_KEY", raising=False)

    assert deliver_certificates() == 0
    assert "CONVENER_SIGNING_KEY not configured" in capsys.readouterr().out


def test_deliver_certificates_without_a_matching_salt_delivers_nothing_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert deliver_certificates() == 0
    assert "CONVENER_MATCHING_SALT not configured" in capsys.readouterr().out


def test_deliver_certificates_with_nothing_recorded_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert deliver_certificates() == 1
    assert "no registrations recorded" in capsys.readouterr().err


def test_deliver_certificates_with_no_certificate_register_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no `certificates.yml` on disk for this
    event -- reachable when this command is dispatched standalone, before
    `convener-issue-certificates` has ever run for the event -- `issue`'s own
    "no row" branch would mint a fresh identifier that this function never
    persists (only `issue_certificates` writes the register), so a second
    run would mail a *different* identifier for the same person. Refused
    before anything is rendered or sent."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    assert not certificates_register_path(tmp_path).exists()

    assert deliver_certificates() == 1
    captured = capsys.readouterr()
    assert "no certificate register for event mrg-042" in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)
    assert not certificates_register_path(tmp_path).exists()


def test_deliver_certificates_with_no_transport_configured_reports_all_unsent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    for key in _SMTP_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    # A register must exist on disk -- the real
    # workflow always issues before it delivers, in the same job.
    assert issue_certificates() == 0
    capsys.readouterr()

    assert deliver_certificates() == 0
    captured = capsys.readouterr()
    assert (
        "0 sent, 1 not sent, 0 refused (revoked), 0"
        " failed to render, 0 not targeted this run "
        "(1 eligible; 0 registration(s) could not be read)" in captured.out
    )
    assert_no_personal_data_leaked(captured.out + captured.err)
    assert "not sent: " in captured.out


def test_deliver_certificates_delivers_to_an_eligible_attendee_and_leaks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    # Issuing first, exactly as the real workflow does (a delivery step
    # after issuance, in the same job): certificates.yml must already
    # carry Ada's entry for `deliver_certificates` to find.
    assert issue_certificates() == 0
    capsys.readouterr()

    assert deliver_certificates() == 0
    captured = capsys.readouterr()
    assert (
        "1 sent, 0 not sent, 0 refused (revoked), 0"
        " failed to render, 0 not targeted this run "
        "(1 eligible; 0 registration(s) could not be read)" in captured.out
    )
    assert_no_personal_data_leaked(captured.out + captured.err)

    assert len(_RecordingCertificateSmtpClient.sent) == 1
    email = _RecordingCertificateSmtpClient.sent[0]
    assert email["To"] == "ada@example.org"
    document = _sent_attachment_html(email)
    assert "Ada Lovelace" in document
    assert_no_personal_data_leaked(email["Subject"])


def test_deliver_certificates_already_registered_path_leaks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same shape, applied here: a name printed only
    on the branch where the attendee was *already* on the register, not
    the freshly-issued one, survived a full green suite once already
    because the sweep that would have caught it only ever ran on the
    first-run path. This test issues first (so the register already holds
    Ada's entry before delivery ever runs), which is exactly the branch a
    sweep covering only a fresh issue-and-deliver run would miss."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    assert issue_certificates() == 0  # a second, routine re-run: 0 issued, 1 already
    capsys.readouterr()

    assert deliver_certificates() == 0
    captured = capsys.readouterr()
    assert_no_personal_data_leaked(captured.out + captured.err)
    assert len(_RecordingCertificateSmtpClient.sent) == 1


def test_deliver_certificates_never_writes_anything_to_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No path this function takes may place a rendered certificate under
    the repository, committed or not."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )
    assert issue_certificates() == 0
    capsys.readouterr()

    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())

    assert deliver_certificates() == 0
    capsys.readouterr()

    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    assert before == after, (
        f"deliver_certificates() changed the file set under the repository "
        f"root: {set(after) - set(before)} appeared, "
        f"{set(before) - set(after)} disappeared -- a rendered certificate "
        "must never be written to disk"
    )
    # Belt and braces: search every file's own bytes for the tell-tale
    # marker, in case a future edit overwrote an *existing* file rather
    # than creating a new one, which the file-set check above could not see.
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert "Certificate of attendance" not in path.read_text(
                encoding="utf-8", errors="ignore"
            )


def test_deliver_certificates_replays_the_identical_document_on_a_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed delivery must replay
    without regenerating -- the identifier, the payload and the signature
    must not change. Simulated here by calling `deliver_certificates`
    twice in a row (the same recovery path a real retry takes: re-running
    the command, or the whole workflow) and comparing the two attachments
    byte for byte."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )
    assert issue_certificates() == 0
    capsys.readouterr()

    assert deliver_certificates() == 0
    capsys.readouterr()
    first_document = _sent_attachment_html(_RecordingCertificateSmtpClient.sent[0])

    _RecordingCertificateSmtpClient.sent = []
    assert deliver_certificates() == 0
    capsys.readouterr()
    second_document = _sent_attachment_html(_RecordingCertificateSmtpClient.sent[0])

    assert first_document == second_document, (
        "a second delivery run produced a different document -- the "
        "identifier, payload or signature changed between runs, which "
        "means this replayed a certificate rather than reproducing it"
    )


# ------------------------------------------------------------------ #
# A revoked certificate must never be delivered, and
# after a reissue it is the *only* one that could be. `certificate.issue`
# resolved by fingerprint alone and ignored `state`, so a revoke-and-
# reissue left the register `[old(revoked), new(issued)]` and `issue`
# handed back the revoked one -- the bulk command mailed it, and the
# singular command named the new one in its own log while delivering the
# old one. Reproduced here through the real CLI commands, the same
# `prepare_event` / `_RecordingCertificateSmtpClient` fixtures every
# other delivery test here already uses.
# ------------------------------------------------------------------ #


def test_deliver_certificates_never_delivers_a_revoked_certificate_with_no_reissue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The revocation guarantee, for the bulk command: issue, revoke, no
    reissue -- a routine re-run of `convener-issue-certificates` (and the
    delivery step immediately after it) must mint and deliver nothing for
    this attendee, not resurrect the revoked document. Also the CLI-level
    counterpart of the lookup mutation: reverting the three-way lookup
    to two-way (skip revoked rows and mint) would deliver a *fresh*
    certificate here instead of refusing -- this test's `sent == 0` and
    unchanged register both catch that too."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    [entry] = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()
    before_redelivery = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]

    # A routine re-run of convener-issue-certificates: must mint nothing new.
    assert issue_certificates() == 0
    issue_captured = capsys.readouterr()
    assert "1 refused" in issue_captured.out

    assert deliver_certificates() == 0
    deliver_captured = capsys.readouterr()
    assert_no_personal_data_leaked(deliver_captured.out + deliver_captured.err)
    assert "0 sent, 0 not sent, 1 refused (revoked)" in deliver_captured.out
    assert len(_RecordingCertificateSmtpClient.sent) == 0

    after = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    assert after == before_redelivery, (
        "a routine re-run after a revocation with no reissue must not "
        "change the register at all"
    )


def test_deliver_certificates_delivers_the_reissued_certificate_not_the_revoked_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reproduction (b): after issue, revoke, reissue, the
    bulk command must deliver the *new*, issued identifier -- and never
    the old, revoked one that used to come first in file order."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    [original] = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", original["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()
    assert reissue_certificate() == 0
    capsys.readouterr()
    certificates = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    by_identifier = {row["identifier"]: row for row in certificates}
    assert by_identifier[original["identifier"]]["state"] == "revoked"
    [new_identifier] = [
        identifier
        for identifier in by_identifier
        if identifier != original["identifier"]
    ]

    assert deliver_certificates() == 0
    captured = capsys.readouterr()
    assert_no_personal_data_leaked(captured.out + captured.err)
    assert "1 sent" in captured.out

    assert len(_RecordingCertificateSmtpClient.sent) == 1
    document = _sent_attachment_html(_RecordingCertificateSmtpClient.sent[0])
    [delivered_id] = re.findall(r"<dd>([0-9a-f]{32})</dd>", document)
    assert delivered_id == new_identifier
    assert delivered_id != original["identifier"]


def test_deliver_certificate_refuses_a_revoked_certificate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same guarantee for the singular command: a revoked certificate
    must never be delivered, by any path."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    [entry] = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()

    assert deliver_certificate() == 1
    captured = capsys.readouterr()
    assert f"certificate {entry['identifier']} is revoked" in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)
    assert len(_RecordingCertificateSmtpClient.sent) == 0


def test_deliver_certificate_delivers_the_reissued_certificate_not_the_revoked_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The singular resend must name and
    deliver the same certificate -- the row `CERTIFICATE_ID` actually
    named, never a different one `issue`'s fingerprint lookup happens to
    resolve. The mutation this catches: make `deliver_certificate` sign
    something other than the row it resolved -- this test's own identifier
    check, pulled out of the attachment itself, is what catches that."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    [original] = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", original["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()
    assert reissue_certificate() == 0
    capsys.readouterr()
    certificates = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    by_identifier = {row["identifier"]: row for row in certificates}
    [new_identifier] = [
        identifier
        for identifier in by_identifier
        if identifier != original["identifier"]
    ]

    monkeypatch.setenv("CERTIFICATE_ID", new_identifier)
    assert deliver_certificate() == 0
    captured = capsys.readouterr()
    assert f"certificate {new_identifier} delivered for event mrg-042" in captured.out
    assert_no_personal_data_leaked(captured.out + captured.err)

    assert len(_RecordingCertificateSmtpClient.sent) == 1
    document = _sent_attachment_html(_RecordingCertificateSmtpClient.sent[0])
    [delivered_id] = re.findall(r"<dd>([0-9a-f]{32})</dd>", document)
    assert delivered_id == new_identifier
    assert delivered_id != original["identifier"]


# ------------------------------------------------------------------ #
# The issue step hands its own freshly-issued
# identifiers to the delivery step through $GITHUB_OUTPUT, and the
# delivery step restricts itself to exactly that set by default -- so a
# re-dispatch mails only what genuinely changed, never every past
# attendee again.
# ------------------------------------------------------------------ #

_GRACE = Registration("Grace", "Hopper", "grace@example.org", "", False)
_GRACE_ATTENDANCE_ROW = (
    "Grace Hopper,grace@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400"
)


def test_issue_certificates_writes_freshly_issued_identifiers_to_github_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(_ADA,),
        attendance_rows=(_ADA_ATTENDANCE_ROW,),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    output_path = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    assert issue_certificates() == 0
    capsys.readouterr()

    [entry] = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert f"issued_ids={entry['identifier']}" in lines
    assert_no_personal_data_leaked(output_path.read_text(encoding="utf-8"))


def test_issue_certificates_github_output_is_empty_when_nothing_is_freshly_issued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A routine re-run: everyone is already on record, so `issued_ids`
    must be the empty string -- the signal `deliver_certificates` reads as
    "deliver nobody this run"."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(_ADA,),
        attendance_rows=(_ADA_ATTENDANCE_ROW,),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    assert issue_certificates() == 0
    capsys.readouterr()

    output_path = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    assert issue_certificates() == 0
    capsys.readouterr()

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert "issued_ids=" in lines


def test_deliver_certificates_with_deliver_only_targets_just_those_identifiers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mutation this catches: make the delivery step ignore the
    identifiers the issue step handed it and deliver everyone -- removing
    the `DELIVER_ONLY` filter check in `deliver_certificates` would send
    Grace's certificate too, which the `sent == [ada]` assertion below
    would then fail."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(_ADA, _GRACE),
        attendance_rows=(_ADA_ATTENDANCE_ROW, _GRACE_ATTENDANCE_ROW),
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    certificates = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    assert len(certificates) == 2
    salt = "s3cr3t-salt-value"
    ada_fingerprint = certificate_fingerprint("mrg-042", "ada@example.org", salt)
    [ada_row] = [row for row in certificates if row["fingerprint"] == ada_fingerprint]

    monkeypatch.setenv("DELIVER_ONLY", ada_row["identifier"])
    assert deliver_certificates() == 0
    captured = capsys.readouterr()
    assert_no_personal_data_leaked(captured.out + captured.err)
    assert (
        "1 sent, 0 not sent, 0 refused (revoked), 0"
        " failed to render, 1 not targeted this run "
        "(2 eligible; 0 registration(s) could not be read)" in captured.out
    )

    assert len(_RecordingCertificateSmtpClient.sent) == 1
    assert _RecordingCertificateSmtpClient.sent[0]["To"] == "ada@example.org"


def test_deliver_certificates_with_deliver_only_empty_targets_nobody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exact shape a routine re-dispatch takes after nothing changed:
    `issue_certificates` writes `issued_ids=` (empty), and the delivery
    step must then deliver to nobody, not fall back to "everyone"."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )
    assert issue_certificates() == 0
    capsys.readouterr()

    monkeypatch.setenv("DELIVER_ONLY", "")
    assert deliver_certificates() == 0
    captured = capsys.readouterr()
    assert (
        "0 sent, 0 not sent, 0 refused (revoked), 0"
        " failed to render, 1 not targeted this run "
        "(1 eligible; 0 registration(s) could not be read)" in captured.out
    )
    assert len(_RecordingCertificateSmtpClient.sent) == 0


def test_deliver_certificates_resend_all_ignores_deliver_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`RESEND_ALL=true` is the deliberate batch retry -- it must deliver
    to everyone eligible, even with a `DELIVER_ONLY` naming only one of
    them (the exact env pairing `issue-certificates.yml` sends when an
    operator ticks `resend_all`, since the step still reads the issuance
    step's own output)."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(_ADA, _GRACE),
        attendance_rows=(_ADA_ATTENDANCE_ROW, _GRACE_ATTENDANCE_ROW),
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )
    assert issue_certificates() == 0
    capsys.readouterr()
    certificates = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    salt = "s3cr3t-salt-value"
    ada_fingerprint = certificate_fingerprint("mrg-042", "ada@example.org", salt)
    [ada_row] = [row for row in certificates if row["fingerprint"] == ada_fingerprint]

    monkeypatch.setenv("DELIVER_ONLY", ada_row["identifier"])
    monkeypatch.setenv("RESEND_ALL", "true")
    assert deliver_certificates() == 0
    captured = capsys.readouterr()
    assert (
        "2 sent, 0 not sent, 0 refused (revoked), 0"
        " failed to render, 0 not targeted this run "
        "(2 eligible; 0 registration(s) could not be read)" in captured.out
    )
    assert len(_RecordingCertificateSmtpClient.sent) == 2


def test_deliver_certificates_with_an_unloadable_signing_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", "not-a-pem-at-all")
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert deliver_certificates() == 1
    assert "CONVENER_SIGNING_KEY" in capsys.readouterr().err


def test_deliver_certificates_rejects_a_malformed_committed_registrations_file(
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

    assert deliver_certificates() == 1
    assert "registrations.enc" in capsys.readouterr().err


def test_deliver_certificates_with_a_missing_config_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    write_registrations(tmp_path, "mrg-042", private_pem, _ADA)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert deliver_certificates() == 1
    assert "config.yml" in capsys.readouterr().err


def test_deliver_certificates_catches_a_platform_request_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,)
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

    assert deliver_certificates() == 1
    assert "failed" in capsys.readouterr().err.lower()


def test_deliver_certificates_skips_an_entry_that_fails_to_decrypt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    file = load_registration_file(None)
    file, _replaced = upsert(file, _ADA, private_pem=event_private_pem)
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
    for key in _SMTP_ENV:
        monkeypatch.delenv(key, raising=False)
    # A register must exist on disk. issue_certificates
    # skips the same stray, undecryptable entry the same way, so this is
    # still exercising the property this test is named for -- the stray
    # entry never stops Ada's own certificate from being processed.
    assert issue_certificates() == 0
    capsys.readouterr()

    assert deliver_certificates() == 0
    assert (
        "0 sent, 1 not sent, 0 refused (revoked), 0"
        " failed to render, 0 not targeted this run "
        "(1 eligible; 1 registration(s) could not be read)" in capsys.readouterr().out
    )


def test_deliver_certificates_refuses_when_no_speaker_record_supplies_a_title_and_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    write_registrations(tmp_path, "mrg-042", private_pem, _ADA)
    write_attendance_csv(tmp_path, "mrg-042", _ADA_ATTENDANCE_ROW)
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "speakers.yml").write_text(yaml.safe_dump([]), encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert deliver_certificates() == 1
    captured = capsys.readouterr()
    assert "no speaker record" in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_deliver_certificates_rejects_a_malformed_committed_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
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

    assert deliver_certificates() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_deliver_certificates_continues_past_a_render_failure_for_one_attendee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The per-attendee `except Exception` branch: nothing this module
    anticipates can actually raise once the two upfront secrets are valid,
    but the same "nobody is watching this job for a traceback" reasoning
    `_send_confirmation` documents for itself applies here too -- exercised
    directly by forcing `delivery.render_certificate` to raise."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    # A register must exist on disk, and issuing
    # first never calls delivery.render_certificate, so patching it below
    # cannot interfere.
    assert issue_certificates() == 0
    capsys.readouterr()

    def _raise(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError("a reason this job did not anticipate")

    monkeypatch.setattr(
        "convener_ops.cli.journey.certificate.delivery.render_certificate", _raise
    )

    assert deliver_certificates() == 0
    captured = capsys.readouterr()
    # A render crash is counted separately from
    # a transport failure -- see deliver_certificates's own docstring.
    assert (
        "0 sent, 0 not sent, 0 refused (revoked), 1"
        " failed to render, 0 not targeted this run "
        "(1 eligible; 0 registration(s) could not be read)" in captured.out
    )
    assert_no_personal_data_leaked(captured.out + captured.err)
    assert "RuntimeError" not in captured.out
    assert "RuntimeError" not in captured.err


def test_deliver_certificates_refuses_and_names_the_parse_failure_of_speakers_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    write_registrations(tmp_path, "mrg-042", private_pem, _ADA)
    write_attendance_csv(tmp_path, "mrg-042", _ADA_ATTENDANCE_ROW)
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "speakers.yml").write_text("- title: [unterminated", encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert deliver_certificates() == 1
    captured = capsys.readouterr()
    assert "speakers.yml" in captured.err
    assert "no speaker record" not in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_deliver_certificate_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)
    assert deliver_certificate() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_deliver_certificate_without_a_configured_event_key_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)
    assert deliver_certificate() == 1
    assert "no private key configured" in capsys.readouterr().err


def test_deliver_certificate_without_a_signing_key_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_SIGNING_KEY", raising=False)

    assert deliver_certificate() == 0
    assert "CONVENER_SIGNING_KEY not configured" in capsys.readouterr().out


def test_deliver_certificate_without_a_matching_salt_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert deliver_certificate() == 0
    assert "CONVENER_MATCHING_SALT not configured" in capsys.readouterr().out


def test_deliver_certificate_without_a_certificate_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", "irrelevant")
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CERTIFICATE_ID", raising=False)

    assert deliver_certificate() == 1
    assert "no certificate id supplied" in capsys.readouterr().err


def test_deliver_certificate_refuses_a_malformed_certificate_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", "irrelevant")
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", "not-32-hex-chars")

    assert deliver_certificate() == 1
    assert "not a valid certificate id supplied" in capsys.readouterr().err


def test_deliver_certificate_with_nothing_recorded_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert deliver_certificate() == 1
    assert "no registrations recorded" in capsys.readouterr().err


def test_deliver_certificate_refuses_when_the_certificate_id_is_not_on_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert deliver_certificate() == 1
    assert f"no certificate {CERT_ID} on record" in capsys.readouterr().err


def test_deliver_certificate_refuses_when_the_certificate_id_matches_nobody_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    write_certificate_register(tmp_path, fingerprint_value="not-adas-fingerprint")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert deliver_certificate() == 1
    assert "does not match any currently eligible attendee" in capsys.readouterr().err


def test_deliver_certificate_delivers_the_named_certificate_and_leaks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    captured = capsys.readouterr()
    register_text = certificates_register_path(tmp_path).read_text(encoding="utf-8")
    [entry] = yaml.safe_load(register_text)["certificates"]
    certificate_id = entry["identifier"]

    monkeypatch.setenv("CERTIFICATE_ID", certificate_id)
    assert deliver_certificate() == 0
    captured = capsys.readouterr()
    assert f"certificate {certificate_id} delivered for event mrg-042" in captured.out
    assert_no_personal_data_leaked(captured.out + captured.err)

    assert len(_RecordingCertificateSmtpClient.sent) == 1
    email = _RecordingCertificateSmtpClient.sent[0]
    assert email["To"] == "ada@example.org"
    document = _sent_attachment_html(email)
    assert "Ada Lovelace" in document
    assert_no_personal_data_leaked(email["Subject"])


def test_deliver_certificate_signs_the_row_it_resolved_not_a_different_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The signing mutation, pinned so it cannot be satisfied by
    coincidence: two eligible attendees, two issued certificates, resend
    the *second* one by its own `CERTIFICATE_ID`. A version of
    `deliver_certificate` that signed some other row it holds a reference
    to -- the first entry in the register, say, rather than the one it
    actually resolved -- would attach Ada's document while the log still
    names Grace's certificate. Unlike a version that merely re-resolved by
    fingerprint (which, after the fix to `issue`'s lookup, would
    coincidentally land on the correct row anyway), this test cannot be
    satisfied by coincidence: the wrong row here belongs to a different
    person outright."""
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path,
        registrations=(_ADA, grace),
        attendance_rows=(
            _ADA_ATTENDANCE_ROW,
            "Grace Hopper,grace@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    certificates = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    assert len(certificates) == 2
    salt = "s3cr3t-salt-value"
    grace_fingerprint = certificate_fingerprint("mrg-042", "grace@example.org", salt)
    [grace_row] = [
        row for row in certificates if row["fingerprint"] == grace_fingerprint
    ]

    monkeypatch.setenv("CERTIFICATE_ID", grace_row["identifier"])
    assert deliver_certificate() == 0
    captured = capsys.readouterr()
    assert (
        f"certificate {grace_row['identifier']} delivered for event mrg-042"
        in captured.out
    )
    assert_no_personal_data_leaked(captured.out + captured.err)

    assert len(_RecordingCertificateSmtpClient.sent) == 1
    email = _RecordingCertificateSmtpClient.sent[0]
    assert email["To"] == "grace@example.org"
    document = _sent_attachment_html(email)
    assert "Grace Hopper" in document
    assert "Ada Lovelace" not in document
    [delivered_id] = re.findall(r"<dd>([0-9a-f]{32})</dd>", document)
    assert delivered_id == grace_row["identifier"]

    # The identifier and name printed as inert text are not what a
    # mutation like "sign existing[0] instead of target_entry" would
    # actually break -- render_certificate's own `identifier=` and
    # `name=` parameters are passed straight through from the resolved
    # attendee, untouched by which entry gets signed. What *would* break
    # is the token's own signed payload, so this decodes it directly:
    # `signing.verify` must report Grace's own identifier and name, never
    # Ada's -- the property this test's own docstring is about.
    [token] = re.findall(r'href="[^"]*\?token=([^"]+)"', document)
    token = urllib.parse.unquote(html.unescape(token))
    public_pem = derive_public_pem(signing_private_pem)
    outcome = verify(token, [public_pem])
    assert outcome.valid
    assert outcome.payload is not None
    assert outcome.payload["identifier"] == grace_row["identifier"]
    assert outcome.payload["name"] == "Grace Hopper"


def test_deliver_certificate_with_no_transport_configured_reports_not_delivered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    for key in _SMTP_ENV:
        monkeypatch.delenv(key, raising=False)

    assert issue_certificates() == 0
    capsys.readouterr()
    [entry] = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])

    assert deliver_certificate() == 0
    captured = capsys.readouterr()
    assert "not delivered" in captured.out
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_deliver_certificate_replays_the_identical_document_on_a_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    _RecordingCertificateSmtpClient.sent = []
    monkeypatch.setattr(
        "convener_ops.journey.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    [entry] = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])

    assert deliver_certificate() == 0
    capsys.readouterr()
    first_document = _sent_attachment_html(_RecordingCertificateSmtpClient.sent[0])

    _RecordingCertificateSmtpClient.sent = []
    assert deliver_certificate() == 0
    capsys.readouterr()
    second_document = _sent_attachment_html(_RecordingCertificateSmtpClient.sent[0])

    assert first_document == second_document

    register_after = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    assert [row["identifier"] for row in register_after] == [entry["identifier"]], (
        "a resend must never mint a second register row for the same certificate"
    )


def test_deliver_certificate_with_an_unloadable_signing_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", "not-a-pem-at-all")
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert deliver_certificate() == 1
    assert "CONVENER_SIGNING_KEY" in capsys.readouterr().err


def test_deliver_certificate_rejects_a_malformed_committed_registrations_file(
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

    assert deliver_certificate() == 1
    assert "registrations.enc" in capsys.readouterr().err


def test_deliver_certificate_with_a_missing_config_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    write_certificate_register(tmp_path)
    (tmp_path / "instance" / "data" / "config.yml").unlink()
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", CERT_ID)

    assert deliver_certificate() == 1
    assert "config.yml" in capsys.readouterr().err


def test_deliver_certificate_catches_a_platform_request_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,)
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

    assert deliver_certificate() == 1
    assert "failed" in capsys.readouterr().err.lower()


def test_deliver_certificate_refuses_when_no_speaker_record_supplies_a_title_and_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
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
    (tmp_path / "instance" / "data" / "speakers.yml").write_text(
        yaml.safe_dump([]), encoding="utf-8"
    )
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])

    assert deliver_certificate() == 1
    captured = capsys.readouterr()
    assert "no speaker record" in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_deliver_certificate_rejects_a_malformed_committed_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
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

    assert deliver_certificate() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_deliver_certificate_survives_an_unanticipated_delivery_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same `except Exception` reasoning as the batch command's own
    test above, exercised for the single-certificate resend: a delivery
    that fails for a reason this job did not anticipate is reported, never
    a crash, and this command still exits 0 -- the same D-13 shape
    `resend_confirmation` already gives an ordinary confirmation resend."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
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

    def _raise(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError("a reason this job did not anticipate")

    monkeypatch.setattr(
        "convener_ops.cli.journey.certificate.delivery.render_certificate", _raise
    )

    assert deliver_certificate() == 0
    captured = capsys.readouterr()
    assert "could not be delivered" in captured.out
    assert_no_personal_data_leaked(captured.out + captured.err)
    assert "RuntimeError" not in captured.out
    assert "RuntimeError" not in captured.err


def test_deliver_certificate_skips_a_stray_entry_that_fails_to_decrypt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stray entry encrypted under an unrelated key pair must not stop a
    resend for the one registration that does decrypt -- the same handling
    `issue_certificates` and `reissue_certificate` already give a stray
    entry."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
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
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])

    assert deliver_certificate() == 0
    captured = capsys.readouterr()
    # The stray entry must not stop resolution reaching Ada's own
    # certificate -- whether the send itself succeeds is a separate
    # concern (no CONVENER_SMTP_* configured here), covered by the delivery
    # tests above; what this test pins is that the certificate id
    # resolved to the one attendee that does decrypt.
    assert entry["identifier"] in captured.out
    assert "does not match any currently eligible" not in captured.err
    assert f"no certificate {entry['identifier']} on record" not in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_deliver_certificate_refuses_and_names_the_parse_failure_of_speakers_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
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
    (tmp_path / "instance" / "data" / "speakers.yml").write_text(
        "- title: [unterminated", encoding="utf-8"
    )
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])

    assert deliver_certificate() == 1
    captured = capsys.readouterr()
    assert "speakers.yml" in captured.err
    assert "no speaker record" not in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)


def test_deliver_certificate_after_the_registration_is_gone_refuses_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The boundary: replayability is bounded by retention.
    Once `registrations.enc` is gone -- the retention sweep, 90 days
    after the event -- there is no address left to resolve a certificate
    id against, even though `certificates.yml` (never touched by that
    sweep) still names it. This must refuse cleanly, the same D-13 shape
    every other missing-registrations refusal already has, never a crash
    and never a message claiming the certificate itself is invalid --
    it isn't; it simply can no longer be delivered by us."""
    event_private_pem, signing_private_pem = prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
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
    certificate_id = entry["identifier"]

    # Simulates the retention sweep: the registration -- and with it
    # the only address this certificate could ever be resent to -- is
    # gone. certificates.yml, in the same directory, is deliberately left
    # untouched (certificate.py's own module docstring, "the register
    # survives the data it was derived from").
    (
        tmp_path / "instance" / "data" / "events" / "mrg-042" / "registrations.enc"
    ).unlink()

    monkeypatch.setenv("CERTIFICATE_ID", certificate_id)
    assert deliver_certificate() == 1
    captured = capsys.readouterr()
    assert "no registrations recorded" in captured.err
    assert_no_personal_data_leaked(captured.out + captured.err)
    # The certificate itself is untouched -- still on record, still issued.
    still_there = yaml.safe_load(
        certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    assert still_there == [entry]
