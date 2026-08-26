"""The whole registration-to-certificate chain, and the one property that
matters most -- partial failures are the norm, not the exception -- each
step replayable on its own, without the step before it having just run.

    registration -> confirmation -> event -> attendance retrieval
      -> matching -> eligibility -> issuance -> delivery
      -> register write -> recording retrieval and deletion
      -> (+90 days) key destruction

Every test below builds the *intermediate state* a step needs by writing
the files that step reads directly -- through the same pure functions
`registration.py`, `certificate.py` and `eventkeys.py` already export, the
same way every other module's own tests in this package build a fixture --
and then calls exactly one real, unmocked command from `convener_ops.cli`. No
test here ever calls a second `cli.py` entry point to "warm up" the state
another test drives: a step that secretly required its predecessor to have
run *in this same process* -- a stray module-level cache, an env var one
command sets and another reads back -- would have nothing here to read,
and every one of these tests would fail loudly rather than passing by
accident.

The order above is a narrative, not a transaction
--------------------------------------------------
Four of these eleven steps are not separate commands at all. `matching`,
`eligibility`, `issuance` and `register write` are one call to
`convener-issue-certificates`: the register is written *at
issuance*, never after delivery -- idempotence requires it
(`convener-deliver-certificates` re-derives and
re-signs but never grows the register; see `certificate.issue`'s own
"idempotent without being deterministic" section). So there is one test
below for issuance (covering all four steps at once) and a separate one
for `delivery`, in the order they actually run, not four separate tests
pretending a paragraph of prose is a call graph.

The manual implementation, closed end to end
----------------------------------------------
The whole chain has to be executable end to end with the manual
implementation and no external account. That used to be undemonstrable for
the one step that reads a meeting platform's export:
`ManualPlatform.get_attendance` read a plaintext CSV `.gitignore` refuses
to commit (personal data), so the manual path could run neither in CI (the
file is never there) nor locally (the event's private key must never be
there). That gap was recorded rather than glossed over.
`platform.py` now offers a second, committed source --
`attendance-import.csv.enc`, encrypted under the event's own public key by
`convener-encrypt-attendance-export`, needing no secret to produce -- and
`test_match_attendance_replays_from_committed_registrations_and_export_alone`
and `test_issue_certificates_replays_from_committed_registrations_and_export_alone`
below drive the real commands against nothing but that committed,
encrypted fixture and a private key, proving the manual chain actually
completes end to end -- not "by hand against a real drop", a real,
automated proof, run on every green build.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from conftest import config, speaker

from convener_ops import eventkeys, signing
from convener_ops.attendance import MatchedAttendee
from convener_ops.certificate import (
    CertificateEntry,
    CertificateEvent,
    register_to_data,
)
from convener_ops.certificate import (
    issue as certificate_issue,
)
from convener_ops.certificate import (
    revoke as certificate_revoke,
)
from convener_ops.cli import (
    CERTIFICATES_HEADER,
    UNMATCHED_ATTENDANCE,
    deliver_certificate,
    deliver_certificates,
    discard_recording,
    encrypt_attendance_export,
    erase_registration,
    issue_certificates,
    match_attendance,
    record_destructions,
    reissue_certificate,
    release_recording,
    resend_confirmation,
    retention_sweep,
    revoke_certificate,
)
from convener_ops.governance import paris_today
from convener_ops.platform import (
    decrypt_attendance_rows,
    encrypt_attendance_rows,
    load_attendance_export_file,
)
from convener_ops.platform import parse_attendance_csv as _parse_attendance_csv
from convener_ops.registration import Registration, dump_registration_file
from convener_ops.registration import load_registration_file as _load_registration_file
from convener_ops.registration import upsert as _upsert_registration

_ATTENDANCE_CSV_HEADER = "display_name,email,joined_at,left_at,duration_seconds"


def _publish_event_key(tmp_path: Path, event_id: str = "mrg-042") -> tuple[str, str]:
    """`keys/events/<id>.pub`, committed -- the one file this whole chain
    treats as public, never a secret. Returns `(private_pem, public_pem)`
    for a test's own env var and its own encryption calls."""
    private_pem, public_pem = eventkeys.generate()
    keys_dir = tmp_path / "keys" / "events"
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / f"{event_id}.pub").write_text(public_pem, encoding="ascii")
    return private_pem, public_pem


def _write_registrations_directly(
    tmp_path: Path, event_id: str, private_pem: str, *registrations: Registration
) -> None:
    """`data/events/<id>/registrations.enc`, built through `upsert` alone
    -- never through `convener-handle-registration`. This is the "a register
    with one entry" intermediate state."""
    file = _load_registration_file(None)
    for registration in registrations:
        file, _replaced = _upsert_registration(
            file, registration, private_pem=private_pem
        )
    path = tmp_path / "data" / "events" / event_id / "registrations.enc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_registration_file(file), encoding="utf-8", newline="")


def _write_encrypted_attendance_directly(
    tmp_path: Path, event_id: str, public_pem: str, *rows: str
) -> None:
    """`data/events/<id>/attendance-import.csv.enc`, built through
    `parse_attendance_csv` + `platform.encrypt_attendance_rows` alone --
    never through `convener-encrypt-attendance-export` itself, so a test of a
    *later* step (matching, issuance) can never accidentally depend on
    that earlier command having just run in this same process. The
    dedicated `convener-encrypt-attendance-export` command gets its own test
    below, replayed from nothing but a plaintext drop. One independent
    envelope per row, not one for the whole file."""
    text = "\n".join((_ATTENDANCE_CSV_HEADER, *rows)) + "\n"
    parsed_rows, issues = _parse_attendance_csv(text)
    assert issues == []
    path = tmp_path / "data" / "events" / event_id / "attendance-import.csv.enc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        encrypt_attendance_rows(public_pem, parsed_rows), encoding="utf-8", newline=""
    )


def _write_speakers_and_config(
    tmp_path: Path,
    event_id: str = "mrg-042",
    *,
    event_date: str = "2026-08-20",
    runbook_progress: dict[str, object] | None = None,
    publication_consent: str = "",
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    record = speaker(
        edition_code=event_id.upper(),
        title="On analytical engines",
        date=event_date,
        runbook_progress=runbook_progress or {},
    )
    record["publication"]["consent"] = publication_consent
    (data_dir / "speakers.yml").write_text(
        yaml.safe_dump([record], sort_keys=False), encoding="utf-8"
    )
    (data_dir / "config.yml").write_text(
        yaml.safe_dump(config(), sort_keys=False), encoding="utf-8"
    )


def _write_certificates_register_directly(
    tmp_path: Path, event_id: str, entries: Sequence[CertificateEntry]
) -> None:
    path = tmp_path / "data" / "events" / event_id / "certificates.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        CERTIFICATES_HEADER
        + yaml.safe_dump(register_to_data(entries), sort_keys=False),
        encoding="utf-8",
        newline="",
    )


# ------------------------------------------------------------------ #
# confirmation -- replays from a committed registration alone, never
# from having just called convener-handle-registration.
# ------------------------------------------------------------------ #


def test_confirmation_resend_replays_from_a_committed_registration_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_pem, public_pem = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations_directly(tmp_path, "mrg-042", private_pem, ada)

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv(
        "EMAIL_ENVELOPE", eventkeys.encrypt(public_pem, b"ada@example.org")
    )

    assert resend_confirmation() == 0


# ------------------------------------------------------------------ #
# attendance retrieval -- the manual export, encrypted.
# Replays from a plaintext drop alone -- no registration, no other
# command, ever needs to have run first.
# ------------------------------------------------------------------ #


def test_encrypt_attendance_export_replays_from_a_plaintext_drop_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Needs nothing about registrations, matching, or certificates -- only
    the event's own published public key (not a secret) and a plaintext
    CSV a host dropped by hand. Proves the host's own half of the chain
    needs no account and no prior step -- and that what it commits is
    genuinely encrypted, not the plaintext under a new name: decrypted
    here with the private half this command never touched, the same key
    a later CI job would use for real."""
    private_pem, _public_pem = _publish_event_key(tmp_path)
    event_dir = tmp_path / "data" / "events" / "mrg-042"
    event_dir.mkdir(parents=True)
    plain_text = (
        _ATTENDANCE_CSV_HEADER + "\n"
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
        "2026-08-20T19:30:00Z,5400\n"
    )
    (event_dir / "attendance-import.csv").write_text(
        plain_text, encoding="utf-8", newline=""
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert encrypt_attendance_export() == 0
    envelope_text = (event_dir / "attendance-import.csv.enc").read_text(
        encoding="utf-8"
    )
    assert envelope_text != plain_text
    file = load_attendance_export_file(envelope_text)
    assert len(file.entries) == 1
    [row] = decrypt_attendance_rows(file, private_pem)
    assert row.display_name == "Ada Lovelace"
    assert row.email == "ada@example.org"


# ------------------------------------------------------------------ #
# attendance retrieval -- matching. Replays from a committed
# registration and a committed encrypted export alone.
# ------------------------------------------------------------------ #


def test_match_attendance_replays_from_committed_registrations_and_export_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations_directly(tmp_path, "mrg-042", private_pem, ada)
    _write_encrypted_attendance_directly(
        tmp_path,
        "mrg-042",
        public_pem,
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert match_attendance() == 0
    printed = capsys.readouterr().out.lower()
    assert "1 matched, 0 unmatched, 0 unreachable" in printed
    assert not (tmp_path / UNMATCHED_ATTENDANCE).exists()


# ------------------------------------------------------------------ #
# matching + eligibility + issuance + register write --
# one command, convener-issue-certificates (see the module docstring's "the
# order above is a narrative" section for why these four steps share
# one test). Replays from committed registrations and a committed,
# encrypted attendance export alone -- the central proof.
# ------------------------------------------------------------------ #


def test_issue_certificates_replays_from_committed_registrations_and_export_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations_directly(tmp_path, "mrg-042", private_pem, ada)
    _write_encrypted_attendance_directly(
        tmp_path,
        "mrg-042",
        public_pem,
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    _write_speakers_and_config(tmp_path)
    signing_private_pem, _ = signing.generate()

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert issue_certificates() == 0
    out = capsys.readouterr().out
    assert "1 issued, 0 already on record" in out

    register_path = tmp_path / "data" / "events" / "mrg-042" / "certificates.yml"
    register_data = yaml.safe_load(register_path.read_text(encoding="utf-8"))
    [entry] = register_data["certificates"]
    assert entry["state"] == "issued"


# ------------------------------------------------------------------ #
# issuance -- correction path. reissue_certificate replays from a
# revoked register entry alone, never from having called
# convener-issue-certificates or convener-revoke-certificate in this process.
# ------------------------------------------------------------------ #


def test_reissue_certificate_replays_from_a_revoked_register_entry_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations_directly(tmp_path, "mrg-042", private_pem, ada)
    _write_encrypted_attendance_directly(
        tmp_path,
        "mrg-042",
        public_pem,
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    _write_speakers_and_config(tmp_path)
    signing_private_pem, _ = signing.generate()
    salt = "s3cr3t-salt-value"

    # The "an already-revoked certificate" intermediate state -- built
    # through the pure `certificate.issue` / `certificate.revoke`
    # functions, never through `convener-issue-certificates` /
    # `convener-revoke-certificate`.
    attendee = MatchedAttendee(registration=ada, duration_seconds=5400)
    event = CertificateEvent(
        event_id="mrg-042", title="On analytical engines", date="2026-08-20"
    )
    first = certificate_issue(
        attendee, event, signing_private_pem, salt, (), issued_on=date(2026, 8, 20)
    )
    revoked = certificate_revoke((first.entry,), "mrg-042", first.entry.identifier)
    _write_certificates_register_directly(tmp_path, "mrg-042", revoked)

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", salt)
    monkeypatch.setenv("CERTIFICATE_ID", first.entry.identifier)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 0
    assert "reissued" in capsys.readouterr().out


# ------------------------------------------------------------------ #
# revocation -- replays from an issued register entry alone. Needs
# neither a signing key nor a matching salt: revocation touches only
# the register (certificate.py's own "revocation touches the register,
# never the signature").
# ------------------------------------------------------------------ #


def test_revoke_certificate_replays_from_an_issued_register_entry_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    signing_private_pem, _ = signing.generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    attendee = MatchedAttendee(registration=ada, duration_seconds=5400)
    event = CertificateEvent(
        event_id="mrg-042", title="On analytical engines", date="2026-08-20"
    )
    first = certificate_issue(
        attendee,
        event,
        signing_private_pem,
        "s3cr3t-salt-value",
        (),
        issued_on=date(2026, 8, 20),
    )
    _write_certificates_register_directly(tmp_path, "mrg-042", (first.entry,))

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", first.entry.identifier)

    assert revoke_certificate() == 0
    assert "revoked" in capsys.readouterr().out

    register_data = yaml.safe_load(
        (tmp_path / "data" / "events" / "mrg-042" / "certificates.yml").read_text(
            encoding="utf-8"
        )
    )
    [row] = register_data["certificates"]
    assert row["state"] == "revoked"


# ------------------------------------------------------------------ #
# delivery -- replays from an issued, undelivered register entry alone.
# A failed delivery is replayed, never regenerated -- this is that
# replay, from a register `issue_certificates` never wrote in this
# process.
# ------------------------------------------------------------------ #


def test_deliver_certificate_replays_from_an_issued_undelivered_entry_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations_directly(tmp_path, "mrg-042", private_pem, ada)
    _write_encrypted_attendance_directly(
        tmp_path,
        "mrg-042",
        public_pem,
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    _write_speakers_and_config(tmp_path)
    signing_private_pem, _ = signing.generate()
    salt = "s3cr3t-salt-value"

    attendee = MatchedAttendee(registration=ada, duration_seconds=5400)
    event = CertificateEvent(
        event_id="mrg-042", title="On analytical engines", date="2026-08-20"
    )
    first = certificate_issue(
        attendee, event, signing_private_pem, salt, (), issued_on=date(2026, 8, 20)
    )
    _write_certificates_register_directly(tmp_path, "mrg-042", (first.entry,))

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", salt)
    monkeypatch.setenv("CERTIFICATE_ID", first.entry.identifier)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    for smtp_var in (
        "CONVENER_SMTP_HOST",
        "CONVENER_SMTP_PORT",
        "CONVENER_SMTP_USER",
        "CONVENER_SMTP_PASSWORD",
        "CONVENER_SMTP_FROM",
    ):
        monkeypatch.delenv(smtp_var, raising=False)

    register_path = tmp_path / "data" / "events" / "mrg-042" / "certificates.yml"
    before = yaml.safe_load(register_path.read_text(encoding="utf-8"))

    # `deliver_certificate` returns 0 on every
    # outcome once the attendee is resolved -- delivered, not delivered,
    # and (via cli.py's own broad `except Exception`) blown up entirely.
    # The exit code alone proved nothing here; inserting `raise
    # RuntimeError` immediately before `sign_for` used to leave this test
    # green. Asserting the printed outcome and that nothing was
    # regenerated is what actually demonstrates the replay without
    # regeneration this module docstring cites this test for.
    assert deliver_certificate() == 0
    out = capsys.readouterr().out
    assert f"certificate {first.entry.identifier} not delivered for event mrg-042" in out

    after = yaml.safe_load(register_path.read_text(encoding="utf-8"))
    assert {row["identifier"] for row in after["certificates"]} == {
        row["identifier"] for row in before["certificates"]
    }


def test_deliver_certificates_batch_replays_from_multiple_issued_entries_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    _write_registrations_directly(tmp_path, "mrg-042", private_pem, ada, grace)
    _write_encrypted_attendance_directly(
        tmp_path,
        "mrg-042",
        public_pem,
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
        "Grace Hopper,grace@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    _write_speakers_and_config(tmp_path)
    signing_private_pem, _ = signing.generate()
    salt = "s3cr3t-salt-value"

    event = CertificateEvent(
        event_id="mrg-042", title="On analytical engines", date="2026-08-20"
    )
    ada_result = certificate_issue(
        MatchedAttendee(registration=ada, duration_seconds=5400),
        event,
        signing_private_pem,
        salt,
        (),
        issued_on=date(2026, 8, 20),
    )
    grace_result = certificate_issue(
        MatchedAttendee(registration=grace, duration_seconds=5400),
        event,
        signing_private_pem,
        salt,
        (ada_result.entry,),
        issued_on=date(2026, 8, 20),
    )
    _write_certificates_register_directly(
        tmp_path, "mrg-042", (ada_result.entry, grace_result.entry)
    )

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", salt)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("DELIVER_ONLY", raising=False)
    monkeypatch.delenv("RESEND_ALL", raising=False)
    for smtp_var in (
        "CONVENER_SMTP_HOST",
        "CONVENER_SMTP_PORT",
        "CONVENER_SMTP_USER",
        "CONVENER_SMTP_PASSWORD",
        "CONVENER_SMTP_FROM",
    ):
        monkeypatch.delenv(smtp_var, raising=False)

    register_path = tmp_path / "data" / "events" / "mrg-042" / "certificates.yml"
    before = yaml.safe_load(register_path.read_text(encoding="utf-8"))

    # Making the delivery loop `continue`
    # immediately -- nobody delivered at all -- used to leave this test
    # green too. Asserting the printed counts and that the register's own
    # identifier set is unchanged is what actually demonstrates "sans
    # regenerer" for the batch path.
    assert deliver_certificates() == 0
    out = capsys.readouterr().out
    assert "0 sent, 2 not sent" in out
    assert "(2 eligible; 0 registration(s) could not be read)" in out

    after = yaml.safe_load(register_path.read_text(encoding="utf-8"))
    assert {row["identifier"] for row in after["certificates"]} == {
        row["identifier"] for row in before["certificates"]
    }


# ------------------------------------------------------------------ #
# recording retrieval and deletion -- the manual chain's
# own answer, replayed from a speaker record alone: nothing to release,
# nothing to discard, because ManualPlatform holds no recording storage
# at all (D-13's ordinary state, and the manual implementation's own
# boundary -- this step is a real no-op there, not an unreachable one).
# ------------------------------------------------------------------ #


def test_release_recording_replays_from_a_consenting_speaker_record_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speakers_and_config(
        tmp_path,
        runbook_progress={"delivered/recording-retrieved": True},
        publication_consent="granted",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert release_recording() == 0
    assert "nothing to release" in capsys.readouterr().out


def test_discard_recording_replays_from_a_speaker_record_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speakers_and_config(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert discard_recording() == 0
    assert "nothing to discard" in capsys.readouterr().out


# ------------------------------------------------------------------ #
# (+90 days) key destruction -- retention_sweep replays from a
# published key and a due event alone; record_destructions replays
# from DESTROYED_IDS/DESTROYED_ON alone, the "operator recovering a
# wedged sweep" case its own docstring names -- never from having read
# retention_sweep's own $GITHUB_OUTPUT in this process.
# ------------------------------------------------------------------ #


def test_retention_sweep_replays_from_a_published_key_and_a_due_event_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    long_past = (paris_today(datetime.now(UTC)) - timedelta(days=91)).isoformat()
    _publish_event_key(tmp_path, "mrg-042")
    _write_speakers_and_config(tmp_path, event_date=long_past)

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "fine-grained-pat")

    assert retention_sweep() == 0
    assert "mrg-042" in capsys.readouterr().out


def test_record_destructions_replays_from_env_alone_recovering_a_wedged_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exact scenario `record_destructions`'s own docstring names: "a
    hand-run operator recovering from a wedged sweep" -- `DESTROYED_IDS`
    and `DESTROYED_ON` typed in directly, never read back from
    `retention_sweep`'s own `$GITHUB_OUTPUT` in this same process (which
    this test never calls at all)."""
    _publish_event_key(tmp_path, "mrg-042")

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DESTROYED_IDS", "mrg-042")
    monkeypatch.setenv("DESTROYED_ON", "2026-08-20")

    assert record_destructions() == 0
    assert "mrg-042" in capsys.readouterr().out
    assert not (tmp_path / "keys" / "events" / "mrg-042.pub").exists()

    registry = yaml.safe_load(
        (tmp_path / "data" / "event-key-destructions.yml").read_text(encoding="utf-8")
    )
    [entry] = registry["destructions"]
    assert entry == {"event_id": "mrg-042", "destroyed_on": "2026-08-20"}


# ------------------------------------------------------------------ #
# effacement anticipe -- erase_registration replays from a committed
# register alone.
# ------------------------------------------------------------------ #


def test_erase_registration_replays_from_a_committed_register_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations_directly(tmp_path, "mrg-042", private_pem, ada)

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv(
        "EMAIL_ENVELOPE", eventkeys.encrypt(public_pem, b"ada@example.org")
    )
    monkeypatch.delenv("MATCHING_CODE", raising=False)

    assert erase_registration() == 0
    assert "erased a registration" in capsys.readouterr().out

    remaining = _load_registration_file(
        (tmp_path / "data" / "events" / "mrg-042" / "registrations.enc").read_text(
            encoding="utf-8"
        )
    )
    assert remaining.entries == ()
