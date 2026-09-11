"""match_attendance(): join the platform's attendance export
against this event's registrations, through the eligibility cascade, and
report the result. Like `handle_registration`
(`test_registration.py`), this job holds
decrypted registrations in memory; these tests check the same property
the registration tests check -- no name and no address may appear
anywhere this job prints, on any path -- plus one more: the
host's short list of unresolved attendance goes to a file, never to
stdout, and only when there is something in it to report.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers.command_line import (
    ATTENDANCE_CSV_HEADER,
    publish_event_key,
    write_attendance_csv,
    write_registrations,
)

from convener_ops.cli.journey.attendance import (
    UNMATCHED_ATTENDANCE,
    encrypt_attendance_export,
    match_attendance,
)
from convener_ops.cli.journey.registration import (
    encrypt_identifier,
)
from convener_ops.journey import eventkeys
from convener_ops.journey.platform import (
    AttendanceRow,
    EventNotFoundError,
    decrypt_attendance_rows,
    encrypt_attendance_rows,
    load_attendance_export_file,
    parse_attendance_csv,
)
from convener_ops.journey.platform_fcc import (
    FCCRequestError,
)
from convener_ops.journey.registration import (
    Registration,
    RegistrationFile,
    dump_registration_file,
    load_registration_file,
    matching_code,
    upsert,
)


def _write_attendance_csv_encrypted(
    tmp_path: Path, event_id: str, public_pem: str, *rows: str
) -> None:
    """The committed shape:
    `instance/data/events/<id>/attendance-import.csv.enc`, one independent
    `eventkeys` envelope per row -- built through the real
    `parse_attendance_csv` + `platform.encrypt_attendance_rows`, never a
    hand-rolled stand-in for either, the same discipline
    `write_registrations` already holds for `registrations.enc`."""
    text = "\n".join((ATTENDANCE_CSV_HEADER, *rows)) + "\n"
    parsed_rows, issues = parse_attendance_csv(text)
    assert issues == []
    path = (
        tmp_path
        / "instance"
        / "data"
        / "events"
        / event_id
        / "attendance-import.csv.enc"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        encrypt_attendance_rows(public_pem, parsed_rows), encoding="utf-8", newline=""
    )


def test_encrypt_attendance_export_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)

    assert encrypt_attendance_export([]) == 1
    assert "no valid event id" in capsys.readouterr().err


def test_encrypt_attendance_export_without_a_published_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert encrypt_attendance_export([]) == 1
    assert "no public key published" in capsys.readouterr().err


def test_encrypt_attendance_export_without_a_plaintext_csv_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert encrypt_attendance_export([]) == 1
    err = capsys.readouterr().err
    assert "no attendance export to encrypt" in err
    assert "instance/data/events/mrg-042/attendance-import.csv" in err
    assert str(tmp_path) not in err


def test_encrypt_attendance_export_writes_a_decryptable_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole point: needs no `EVENT_PRIVATE_KEY` at all (never reads
    it), yet what it writes is exactly what `convener-match-attendance` can
    later decrypt with that key -- proven here by decrypting the file this
    command wrote and parsing it back into the original rows, not by
    trusting the envelope's shape alone."""
    private_pem, _public_pem = publish_event_key(tmp_path)
    events_dir = tmp_path / "instance" / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "attendance-import.csv").write_text(
        ATTENDANCE_CSV_HEADER + "\n"
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
        "2026-08-20T19:30:00Z,5400\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert encrypt_attendance_export([]) == 0
    out = capsys.readouterr().out
    assert "attendance-import.csv.enc" in out
    assert "convener-match-attendance" in out

    enc_path = events_dir / "attendance-import.csv.enc"
    assert enc_path.exists()
    envelope_text = enc_path.read_text(encoding="utf-8")
    assert envelope_text.endswith("\n")
    assert not envelope_text.endswith("\n\n")

    file = load_attendance_export_file(envelope_text)
    assert len(file.entries) == 1
    rows = decrypt_attendance_rows(file, private_pem)
    assert [row.display_name for row in rows] == ["Ada Lovelace"]


def test_encrypt_attendance_export_warns_when_replacing_an_already_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """This command has no date or content to
    compare against -- it always encrypts whatever the local plaintext
    currently says -- so a stray or stale local export would otherwise
    replace a good committed file with a worse one with no visible
    signal. A first run names no replacement; a second run over a
    changed plaintext does."""
    publish_event_key(tmp_path)
    events_dir = tmp_path / "instance" / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    plain_path = events_dir / "attendance-import.csv"
    plain_path.write_text(
        ATTENDANCE_CSV_HEADER + "\nAda,ada@example.org,x,y,60\n", encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert encrypt_attendance_export([]) == 0
    assert "replacing" not in capsys.readouterr().out

    plain_path.write_text(
        ATTENDANCE_CSV_HEADER + "\nGrace,grace@example.org,x,y,90\n", encoding="utf-8"
    )
    assert encrypt_attendance_export([]) == 0
    out = capsys.readouterr().out
    assert "replacing the already-committed" in out
    assert "attendance-import.csv.enc" in out


def test_encrypt_attendance_export_never_reads_the_private_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never touches `EVENT_PRIVATE_KEY` -- the whole reason this command
    can run on a host's own laptop with no CI job and no secret at all
    (the private half is used in continuous integration and nowhere
    else). Asserted by monkeypatching `os.environ.get` and failing
    the moment this name is asked for through it, not merely by leaving
    it unset (which a bug reading it with `or ''` would pass silently).
    This guards the one way `convener_ops` actually reads
    an environment variable today (verified by grep -- nothing in the
    package reads one by subscript or through `os.getenv`); it would not
    by itself catch a future read added through either of those."""
    publish_event_key(tmp_path)
    events_dir = tmp_path / "instance" / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "attendance-import.csv").write_text(
        ATTENDANCE_CSV_HEADER + "\nAda,ada@example.org,x,y,60\n", encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    import os as os_module

    real_get = os_module.environ.get

    def _guarded_get(key: str, default: str | None = None) -> str | None:
        assert key != "EVENT_PRIVATE_KEY", "must never read the event private key"
        return real_get(key, default)

    monkeypatch.setattr(os_module.environ, "get", _guarded_get)

    assert encrypt_attendance_export([]) == 0


def test_encrypt_attendance_export_takes_the_event_as_an_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The option exists because the environment spelling cannot be
    typed on every shell this product is opened on: `EVENT_ID=<id>
    command` is a shape Windows PowerShell 5.1 has no form of at all, and
    no rewording of the page closes that. With `EVENT_ID` deliberately
    unset, the command still runs.
    """
    private_pem, _public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("EVENT_ID", raising=False)
    write_attendance_csv(tmp_path, "mrg-042", "Ada,ada@example.org,x,y,60")

    assert encrypt_attendance_export(["--event", "mrg-042"]) == 0
    assert "attendance-import.csv.enc" in capsys.readouterr().out

    written = (
        tmp_path
        / "instance"
        / "data"
        / "events"
        / "mrg-042"
        / "attendance-import.csv.enc"
    )
    file = load_attendance_export_file(written.read_text(encoding="utf-8"))
    assert [row.email for row in decrypt_attendance_rows(file, private_pem)] == [
        "ada@example.org"
    ]


def test_encrypt_attendance_export_prefers_the_option_to_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The precedence, measured rather than described: an operator who
    names an event on the command line means that event, whatever a
    standing `env:` says. See `cli/given.py` for the argument."""
    publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-999")
    write_attendance_csv(tmp_path, "mrg-042", "Ada,ada@example.org,x,y,60")

    assert encrypt_attendance_export(["--event", "mrg-042"]) == 0

    events = tmp_path / "instance" / "data" / "events"
    assert (events / "mrg-042" / "attendance-import.csv.enc").is_file()
    assert not (events / "mrg-999").exists()


# --- encrypt_identifier() ---------------------------------------------- #
#
# The local, no-secret command that lets an operator turn
# a registrant's own address into the ciphertext erase-registration.yml's
# and resend-confirmation.yml's own `encrypted_identifier` input expect,
# so neither workflow ever has to accept the address itself.


def test_encrypt_identifier_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)
    assert encrypt_identifier([]) == 1
    assert "no valid event id" in capsys.readouterr().err


def test_encrypt_identifier_with_an_invalid_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "../escape")
    assert encrypt_identifier([]) == 1
    assert "no valid event id" in capsys.readouterr().err


def test_encrypt_identifier_with_no_email_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("REGISTRATION_EMAIL", raising=False)
    assert encrypt_identifier([]) == 1
    assert "no e-mail address" in capsys.readouterr().err


def test_encrypt_identifier_without_a_published_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")

    assert encrypt_identifier([]) == 1
    assert "no public key published" in capsys.readouterr().err


def test_encrypt_identifier_never_reads_the_private_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same "no secret needed" proof
    `test_encrypt_attendance_export_never_reads_the_private_key` already
    gives its own sibling command -- encrypting under a public key is
    exactly the operation a stranger with no account, and this command
    with no secret, could already perform."""
    publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")

    import os as os_module

    real_get = os_module.environ.get

    def _guarded_get(key: str, default: str | None = None) -> str | None:
        assert key != "EVENT_PRIVATE_KEY", "must never read the event private key"
        return real_get(key, default)

    monkeypatch.setattr(os_module.environ, "get", _guarded_get)

    assert encrypt_identifier([]) == 0


def test_encrypt_identifier_takes_both_values_as_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both halves of the prefix this command used to require, as
    options -- with neither environment variable set, which is the state
    an operator on a shell with no such prefix is always in."""
    private_pem, _public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("EVENT_ID", raising=False)
    monkeypatch.delenv("REGISTRATION_EMAIL", raising=False)

    assert (
        encrypt_identifier(
            ["--event", "mrg-042", "--email", "ada@example.org"],
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "ada@example.org" not in out
    assert (
        eventkeys.decrypt(private_pem, out.strip()).decode("utf-8") == "ada@example.org"
    )


def test_encrypt_identifier_prefers_the_options_to_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The precedence again, on the command that reads two values: the
    option wins, the environment is the fallback."""
    private_pem, _public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "grace@example.org")

    assert encrypt_identifier(["--email", "ada@example.org"]) == 0
    out = capsys.readouterr().out
    assert (
        eventkeys.decrypt(private_pem, out.strip()).decode("utf-8") == "ada@example.org"
    )


def test_encrypt_identifier_prints_a_decryptable_envelope_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The round trip that actually matters: what this command prints is
    exactly what `resend_confirmation` and `erase_registration` can
    decrypt back into the same address -- and the address itself never
    appears in anything this command prints."""
    private_pem, _public_pem = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")

    assert encrypt_identifier([]) == 0
    out = capsys.readouterr().out
    lines = out.strip("\n").splitlines()
    assert len(lines) == 1
    assert "ada@example.org" not in out

    recovered = eventkeys.decrypt(private_pem, lines[0])
    assert recovered == b"ada@example.org"


def test_match_attendance_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)

    assert match_attendance() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_match_attendance_with_an_invalid_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "../escape")

    assert match_attendance() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_match_attendance_without_a_configured_key_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert match_attendance() == 1
    assert "no private key configured" in capsys.readouterr().err


def test_match_attendance_with_nothing_recorded_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert match_attendance() == 1
    assert "no registrations recorded" in capsys.readouterr().err


def test_match_attendance_rejects_a_malformed_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    events_dir = tmp_path / "instance" / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "registrations.enc").write_text("not json at all", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert match_attendance() == 1
    assert "registrations.enc" in capsys.readouterr().err


def test_match_attendance_reports_a_missing_attendance_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert match_attendance() == 1
    assert "no attendance export" in capsys.readouterr().err


def test_match_attendance_catches_a_platform_request_failure_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`get_attendance` can fail two different ways depending on which
    `Platform` implementation answers it: `AttendanceImportError` from the
    manual path (covered above), or `FCCRequestError` from the chosen
    platform's own network/API failure. Both must be caught the same
    clean way -- a real API outage must not escape as an uncaught
    traceback. No network touched: `platform_from_env` itself is
    substituted, the same seam other tests in this module already use for
    a dependency `match_attendance` does not construct a fake for on its
    own."""
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)

    class _FailingPlatform:
        def get_attendance(self, event_id: str) -> list[AttendanceRow]:
            raise FCCRequestError(f"GET /conferences/{event_id}/calls failed: timeout")

    monkeypatch.setattr(
        "convener_ops.cli.journey.attendance.platform_from_env",
        lambda *args, **kwargs: _FailingPlatform(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert match_attendance() == 1
    assert "failed" in capsys.readouterr().err.lower()


def test_match_attendance_catches_an_unresolved_conference_id_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`match_attendance` never populates
    `conference_ids` (it has no workflow to receive a `conference_id`
    input from at all), so the FCC path
    always raises `EventNotFoundError` today when it is in play, and this
    function did not catch it -- the identical hole `issue_certificates`
    and `reissue_certificate` had, closed the same way in all three
    places. Asserted on the message, not only the return code, so a fix
    that merely swallows the traceback would still fail this test."""
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)

    class _FailingPlatform:
        def get_attendance(self, event_id: str) -> list[AttendanceRow]:
            raise EventNotFoundError(
                f"no FCC conference is recorded for event {event_id!r}"
            )

    monkeypatch.setattr(
        "convener_ops.cli.journey.attendance.platform_from_env",
        lambda *args, **kwargs: _FailingPlatform(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert match_attendance() == 1
    assert "no FCC conference is recorded for event 'mrg-042'" in (
        capsys.readouterr().err
    )


def test_match_attendance_names_tied_candidates_by_record_id_in_the_host_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tie the cascade refused to guess between is not left as a bare
    "unmatched" in the host's own file -- both candidates are named, so
    the host is resolving a specific ambiguity. Named by
    each candidate's own salted record identifier now, never its
    address (D-24) -- the record identifier is the whole point of a tie
    being worth naming at all, not the address it used to be."""
    private_pem, _ = publish_event_key(tmp_path)
    first_marie = Registration("Marie", "Martin", "marie.m1@example.org", "", False)
    second_marie = Registration("Marie", "Martin", "marie.m2@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, first_marie, second_marie)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Marie Martin,someone-else@example.org,"
        "2026-08-20T18:00:00Z,2026-08-20T18:30:00Z,1800",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert match_attendance() == 0

    host_list = (tmp_path / UNMATCHED_ATTENDANCE).read_text(encoding="utf-8")
    first_code = matching_code("mrg-042", "marie.m1@example.org", "s3cr3t-salt-value")
    second_code = matching_code("mrg-042", "marie.m2@example.org", "s3cr3t-salt-value")
    assert first_code is not None
    assert second_code is not None
    assert first_code in host_list
    assert second_code in host_list
    assert "marie.m1@example.org" not in host_list
    assert "marie.m2@example.org" not in host_list
    assert "someone-else@example.org" not in host_list
    assert host_list.endswith("\n")
    assert not host_list.endswith("\n\n")


def test_match_attendance_tied_candidates_without_a_salt_show_no_addresses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The identical tie, with no salt configured: no record identifier
    can be computed for either candidate, so the host list says exactly
    that, and both addresses stay absent -- not the fallback the pre-fix
    code took of printing the address instead."""
    private_pem, _ = publish_event_key(tmp_path)
    first_marie = Registration("Marie", "Martin", "marie.m1@example.org", "", False)
    second_marie = Registration("Marie", "Martin", "marie.m2@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, first_marie, second_marie)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Marie Martin,someone-else@example.org,"
        "2026-08-20T18:00:00Z,2026-08-20T18:30:00Z,1800",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert match_attendance() == 0

    host_list = (tmp_path / UNMATCHED_ATTENDANCE).read_text(encoding="utf-8")
    assert "2 registrant(s) tied" in host_list
    assert "CONVENER_MATCHING_SALT not configured" in host_list
    assert "marie.m1@example.org" not in host_list
    assert "marie.m2@example.org" not in host_list
    assert "someone-else@example.org" not in host_list


def test_match_attendance_unmatched_entry_shows_a_record_id_not_the_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordinary, non-tied unmatched case, salted: the host list names
    the connection by its own salted record identifier, computed from the
    address the platform observed -- never the address itself."""
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Grace Hopper,grace@example.org,2026-08-20T18:00:00Z,2026-08-20T18:30:00Z,1800",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert match_attendance() == 0

    host_list = (tmp_path / UNMATCHED_ATTENDANCE).read_text(encoding="utf-8")
    code = matching_code("mrg-042", "grace@example.org", "s3cr3t-salt-value")
    assert code is not None
    assert code in host_list
    assert "grace@example.org" not in host_list
    assert "Grace" not in host_list
    assert "Hopper" not in host_list


def test_match_attendance_refuses_rather_than_leak_if_a_record_id_cannot_be_computed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_salted_record_id`'s own defensive branch: with a truthy salt,
    `matching_code` can never actually return `None` -- but if it ever
    did, falling back to the address would be exactly the leak this
    exists to close. Forced with a monkeypatch, the same technique
    `test_find_by_matching_code_refuses_a_collision_instead_of_returning_
    the_first` already uses to exercise an otherwise-unreachable branch:
    this must raise loudly, never print the address instead."""
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Grace Hopper,grace@example.org,2026-08-20T18:00:00Z,2026-08-20T18:30:00Z,1800",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setattr(
        "convener_ops.cli.journey.attendance.matching_code",
        lambda event_id, email, salt: None,
    )

    with pytest.raises(RuntimeError, match="matching_code returned None"):
        match_attendance()

    assert not (tmp_path / UNMATCHED_ATTENDANCE).exists()


def test_match_attendance_host_list_never_contains_a_raw_name_or_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The closing proof: an artefact or a
    log line must never carry a plaintext address (or name, or phone
    number) out of the envelope, regardless of whether CONVENER_MATCHING_SALT
    is configured. Ada joins by the link with her own address (matched,
    level 2 -- no salt configured); Grace's connection carries an address
    that matches nobody (unmatched); a third connection has no address at
    all (unreachable, a phone number as its own display name). Before this
    fix, `host_list` carried Grace's name and address and the caller's own
    phone number verbatim -- this pins that it no longer does, on either
    surface this job can write to: stdout/stderr, and the host's own
    file."""
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
        "Grace Hopper,grace@example.org,2026-08-20T18:00:00Z,2026-08-20T18:30:00Z,1800",
        "+1 555 0100,,2026-08-20T18:00:00Z,2026-08-20T18:10:00Z,600",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert match_attendance() == 0

    captured = capsys.readouterr()
    printed = (captured.out + captured.err).lower()
    assert "1 matched, 1 unmatched, 1 unreachable" in printed
    assert "3 row(s) read" in printed

    host_list = (tmp_path / UNMATCHED_ATTENDANCE).read_text(encoding="utf-8")
    leaked_strings = ("ada", "lovelace", "grace", "hopper", "555 0100")
    for leaked in leaked_strings:
        assert leaked not in printed, f"{leaked!r} leaked into job output"
        assert leaked not in host_list.lower(), (
            f"{leaked!r} leaked into {UNMATCHED_ATTENDANCE}"
        )
    assert "grace@example.org" not in host_list
    assert "ada@example.org" not in host_list

    # What the host does get instead: an unmatched entry naming a record,
    # never a person, and an unreachable connection collapsed to a count
    # -- both actionable without naming anybody: give a host what they
    # need to act, without naming people.
    assert "connection 1 (no record identifier" in host_list
    assert "30 min" in host_list  # Grace's own 1800-second connection
    assert "## Unreachable" in host_list
    assert "1 connection(s), 10 min total" in host_list


def test_match_attendance_reads_the_committed_encrypted_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end through this one command: no `CONVENER_MEETING_API_TOKEN`,
    no plaintext CSV anywhere on disk -- only the committed encrypted
    export a host would have produced with `convener-encrypt-attendance-export`
    and the same `EVENT_PRIVATE_KEY` every other command in this event's
    chain already reads. This is the manual implementation's own path,
    proven to actually decrypt and match, not merely accepted as present."""
    private_pem, public_pem = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_attendance_csv_encrypted(
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


def test_match_attendance_unlinks_a_stale_host_list_when_all_matched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    stale = tmp_path / UNMATCHED_ATTENDANCE
    stale.write_text("leftover from an earlier run", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert match_attendance() == 0
    assert not stale.exists()


def test_match_attendance_uses_the_matching_code_when_salted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An end-to-end check that CONVENER_MATCHING_SALT actually reaches the
    cascade: with a code embedded, a connection whose own address matches
    nobody is still matched -- level 1 overriding level 2, exercised
    through the real CLI wiring rather than only through attendance.match
    directly."""
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    code = matching_code("mrg-042", ada.email, "s3cr3t-salt-value")
    assert code is not None
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        f"Ada Lovelace {code},not-ada@example.org,"
        "2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert match_attendance() == 0
    assert not (tmp_path / UNMATCHED_ATTENDANCE).exists()


def test_match_attendance_host_list_with_only_unmatched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No unreachable entry this time -- the host list's second section
    is skipped, not printed as an empty heading."""
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Someone Else,someone@example.org,"
        "2026-08-20T18:00:00Z,2026-08-20T18:30:00Z,1800",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert match_attendance() == 0

    host_list = (tmp_path / UNMATCHED_ATTENDANCE).read_text(encoding="utf-8")
    assert "Unmatched" in host_list
    assert "Unreachable" not in host_list


def test_match_attendance_host_list_with_only_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No unmatched entry this time -- the host list's first section is
    skipped, not printed as an empty heading."""
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    write_registrations(tmp_path, "mrg-042", private_pem, ada)
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "+1 555 0100,,2026-08-20T18:00:00Z,2026-08-20T18:10:00Z,600",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert match_attendance() == 0

    host_list = (tmp_path / UNMATCHED_ATTENDANCE).read_text(encoding="utf-8")
    assert "Unreachable" in host_list
    assert "Unmatched" not in host_list


def test_match_attendance_skips_an_entry_that_fails_to_decrypt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stray entry encrypted under an unrelated key pair -- well-formed
    envelope shape, but undecryptable with this event's own key. Skipped,
    not treated as a match, the same handling find_by_email and upsert
    already give a stray undecryptable entry -- but, carried item 10, no
    longer silently: the printed line now says so."""
    private_pem, _ = publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file = load_registration_file(None)
    file, _replaced = upsert(file, ada, private_pem=private_pem)
    _other_private, other_public = eventkeys.generate()
    stray = json.loads(eventkeys.encrypt(other_public, b'{"not": "ours"}'))
    file = RegistrationFile(entries=(*file.entries, stray))
    path = tmp_path / "instance" / "data" / "events" / "mrg-042" / "registrations.enc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_registration_file(file), encoding="utf-8")
    write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert match_attendance() == 0
    out = capsys.readouterr().out
    assert "1 matched, 0 unmatched, 0 unreachable" in out
    assert "1 registration(s) could not be read" in out
