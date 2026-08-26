from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import re
import urllib.parse
from collections.abc import Sequence
from datetime import UTC, date, datetime, tzinfo
from email.message import EmailMessage
from functools import cache
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml
from conftest import board_member, config, speaker

from convener_ops import eventkeys
from convener_ops.attendance import MatchedAttendee
from convener_ops.certificate import CertificateEntry, CertificateEvent, IssueResult
from convener_ops.certificate import fingerprint as certificate_fingerprint
from convener_ops.certificate import issue as certificate_issue
from convener_ops.cli import (
    UNMATCHED_ATTENDANCE,
    _load,
    agenda_internal,
    certificates_public_data,
    deliver_certificate,
    deliver_certificates,
    discard_recording,
    encrypt_attendance_export,
    encrypt_identifier,
    handle_proposal,
    handle_registration,
    invite_survey,
    issue_certificates,
    match_attendance,
    public_data,
    record_survey_invitation,
    reissue_certificate,
    release_recording,
    resend_confirmation,
    resolve_registration_secret,
    revoke_certificate,
    send_confirmation,
    survey_status_public_data,
    sweep,
    validate,
)
from convener_ops.governance import paris_today
from convener_ops.paths import repo_root
from convener_ops.platform import (
    AttendanceRow,
    EventNotFoundError,
    decrypt_attendance_rows,
    encrypt_attendance_rows,
    load_attendance_export_file,
    parse_attendance_csv,
)
from convener_ops.platform_fcc import RETRIEVED_TICK, FCCRequestError, PlatformFCC
from convener_ops.registration import (
    Registration,
    RegistrationFile,
    dump_registration_file,
    load_registration_file,
    matching_code,
    to_registration,
    upsert,
)
from convener_ops.signing import derive_public_pem, generate, verify
from convener_ops.survey_invite import survey_url


def test_load_missing_file_reports_error(tmp_path: Path) -> None:
    value, errors = _load(tmp_path / "missing.yml")
    assert value is None
    assert errors == ["missing.yml: file missing"]


def test_load_malformed_yaml_reports_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yml"
    bad.write_text("key: [unclosed\n", encoding="utf-8")

    value, errors = _load(bad)

    assert value is None
    assert len(errors) == 1
    assert "invalid YAML" in errors[0]


def test_load_valid_yaml_returns_data_and_no_errors(tmp_path: Path) -> None:
    good = tmp_path / "good.yml"
    good.write_text("season: 2026\n", encoding="utf-8")

    value, errors = _load(good)

    assert value == {"season": 2026}
    assert errors == []


#: The real declaration, copied into every scratch root below rather than
#: re-typed. `convener-validate` reads `config/instance.json` for the prefix its
#: editions are numbered under, and a second hand-typed
#: declaration here would be a second answer to what this instance is --
#: the same choice `test_cli_render_visuals.py::_fake_root` already makes.
#: Read on demand, never while this module loads.
#: `config/boundary.yml` hands this path to the instance, and a derived
#: repository is entitled not to have it until the derivation lays an
#: example's own file there. At module scope the read took the whole
#: module down at collection, every test in it with a stack trace; from
#: here it fails the tests that are actually about the declaration, and
#: says which file is missing.
@cache
def _real_instance() -> str:
    return (repo_root() / "config" / "instance.json").read_text(encoding="utf-8")


def _write_data(tmp_path: Path, speakers: object, cfg: object) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "speakers.yml").write_text(yaml.safe_dump(speakers), encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "instance.json").write_text(_real_instance(), encoding="utf-8")


def test_validate_reports_ok_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_data(tmp_path, [speaker()], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert validate() == 0
    assert "Data OK - 1 speakers, config=ok" in capsys.readouterr().out


def test_validate_reports_errors_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_data(tmp_path, [speaker(status="bogus-status")], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert validate() == 1
    out = capsys.readouterr().out
    assert "Data validation FAILED" in out
    assert "invalid status 'bogus-status'" in out


def test_validate_reports_a_board_under_its_target_without_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The target is said out loud, and saying it changes no verdict.

    A board short of `board_min` is the state in which every act that would
    fix it has to stay available, so `convener-validate` reports and exits 0. The
    line is ASCII, like everything this package prints to a terminal.
    """
    cfg = config(
        board=[board_member(login="a"), board_member(login="b")],
        board_min=5,
    )
    _write_data(tmp_path, [speaker()], cfg)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert validate() == 0
    out = capsys.readouterr().out
    assert "Note: config.yml: board has 2 active members, below its target of 5" in out
    assert "Data OK" in out
    assert out.isascii()


def test_validate_handles_a_missing_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # config.yml can be absent -- a fresh checkout before it is ever
    # written, or a broken deploy -- and validate() must still run speakers
    # validation and report the load error, not crash resolving
    # cfg["board"] or calling validate_config(None).
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "speakers.yml").write_text(
        yaml.safe_dump([speaker()]), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert validate() == 1
    out = capsys.readouterr().out
    assert "config.yml: file missing" in out
    # validate_config(None) would itself report "top-level must be a
    # mapping" gracefully rather than raise -- so calling it unconditionally
    # (skipping `if cfg is not None:`) would not crash here, it would just
    # add a second, redundant message. This line is what tells the two
    # apart.
    assert "top-level must be a mapping" not in out


def test_validate_handles_a_missing_speakers_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert validate() == 1
    out = capsys.readouterr().out
    assert "speakers.yml: file missing" in out
    # validate_speakers(None) would itself report "top-level must be a
    # list" gracefully rather than raise -- so calling it unconditionally
    # (skipping `if speakers is not None:`) would not crash here, it would
    # just add a second, redundant message. This line is what tells the
    # two apart.
    assert "top-level must be a list" not in out


def test_validate_handles_a_config_with_no_board_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # board_logins seeds validate_speakers's login checks (assigned_to /
    # ballot voter). A config.yml with no "board" key at all -- a hand-edit
    # or an in-progress migration -- must fall back to an empty set rather
    # than raise iterating None. assigned_to="ada" makes that fallback
    # observable: with board_logins genuinely empty, "ada" cannot be in it,
    # so the speaker-side error names it -- proof the fallback ran, not
    # just that *some* error appeared.
    cfg = config()
    del cfg["board"]
    _write_data(tmp_path, [speaker(assigned_to="ada")], cfg)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert validate() == 1
    out = capsys.readouterr().out
    assert "Data validation FAILED" in out
    assert "assigned_to is not a board member ('ada')" in out


def test_sweep_reports_nothing_to_sweep_when_no_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_data(tmp_path, [speaker(status="lead")], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert sweep() == 0
    assert "Nothing to sweep." in capsys.readouterr().out


def test_sweep_rewrites_the_file_and_keeps_the_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    row = speaker(
        status="scheduled",
        edition_code="MRG-05",
        date="2000-01-01",
        time="09:00",
        host_1="H1",
        host_2="H2",
    )
    _write_data(tmp_path, [row], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert sweep() == 0
    out = capsys.readouterr().out
    assert "spk-001: scheduled -> delivered" in out

    text = (tmp_path / "data" / "speakers.yml").read_text(encoding="utf-8")
    assert text.startswith("# Speakers (unified schema v6")
    assert "status: delivered" in text


def test_sweep_reports_load_errors_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()

    assert sweep() == 1
    assert "file missing" in capsys.readouterr().out


def test_public_data_writes_the_allowlisted_feed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The entry point `convener-public-data` runs, wired end to end: a lead is
    # excluded (not a public status), a scheduled talk is included and
    # named by its edition_code (to_public's own id mapping, see
    # test_public_data.py) -- proving this writes to_public's *output*,
    # not merely that to_public itself works in isolation.
    speakers = [
        speaker(id="spk-001", status="lead"),
        speaker(
            id="spk-002",
            status="scheduled",
            edition_code="MRG-05",
            date="2026-01-08",
            host_1="H1",
            host_2="H2",
        ),
    ]
    _write_data(tmp_path, speakers, config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert public_data() == 0
    assert "wrote 1 events" in capsys.readouterr().out

    written = json.loads(
        (tmp_path / "public-data" / "events-public.json").read_text(encoding="utf-8")
    )
    assert [row["id"] for row in written] == ["MRG-05"]


def test_public_data_reports_load_errors_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()

    assert public_data() == 1
    assert "file missing" in capsys.readouterr().out
    assert not (tmp_path / "public-data").exists()


def test_survey_status_public_data_writes_only_the_enabled_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`convener-survey-status-public-data`, wired end to end: an event
    with the switch off is excluded, one with it on is
    named by its lower-cased edition code -- proving this writes
    `to_survey_status`'s own output, not merely that the function works in
    isolation."""
    speakers = [
        speaker(id="spk-001", edition_code="MRG-05", survey_enabled=False),
        speaker(id="spk-002", edition_code="MRG-06", survey_enabled=True),
    ]
    _write_data(tmp_path, speakers, config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert survey_status_public_data() == 0
    assert "wrote 1 event(s)" in capsys.readouterr().out

    written = json.loads(
        (tmp_path / "public-data" / "survey-status.json").read_text(encoding="utf-8")
    )
    assert written == ["mrg-06"]


def test_survey_status_public_data_reports_load_errors_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()

    assert survey_status_public_data() == 1
    assert "file missing" in capsys.readouterr().out
    assert not (tmp_path / "public-data").exists()


def test_agenda_internal_writes_pure_crlf_bytes_for_a_scheduled_edition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`convener-agenda-internal`, wired end to end: a
    `scheduled` speaker becomes one `VEVENT`, and the file this CLI
    command actually writes to disk carries the CRLF line endings RFC 5545
    requires -- `write_bytes`, not a text-mode write that this project's
    own Windows checkouts would corrupt (see `agenda_internal`'s own
    docstring)."""
    speakers = [
        speaker(
            id="spk-001", edition_code="MRG-07", status="scheduled", date="2026-09-10"
        )
    ]
    _write_data(tmp_path, speakers, config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert agenda_internal() == 0
    assert "wrote 1 entrie(s)" in capsys.readouterr().out

    written = (tmp_path / "public-data" / "agenda-internal.ics").read_bytes()
    assert b"BEGIN:VEVENT" in written
    assert b"mrg-07" in written
    assert b"\r\n" in written
    stripped = written.replace(b"\r\n", b"")
    assert b"\n" not in stripped, (
        "a bare LF survived the write -- CRLF was not preserved"
    )


def test_agenda_internal_reports_load_errors_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()

    assert agenda_internal() == 1
    assert "file missing" in capsys.readouterr().out
    assert not (tmp_path / "public-data").exists()


def test_handle_proposal_with_no_payload_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("PROPOSAL_PAYLOAD", raising=False)

    assert handle_proposal() == 1
    assert "no payload" in capsys.readouterr().err


def test_handle_proposal_writes_a_new_lead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_data(tmp_path, [speaker(id="spk-001")], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    payload = json.dumps({"fields": [{"label": "Name", "value": "Grace Hopper"}]})
    monkeypatch.setenv("PROPOSAL_PAYLOAD", payload)
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 0
    out = capsys.readouterr().out
    assert "created spk-002 from form proposal" in out

    text = (tmp_path / "data" / "speakers.yml").read_text(encoding="utf-8")
    assert "spk-002" in text
    assert "Grace Hopper" in text


class _FrozenClock:
    """`datetime` with `now` pinned to one instant, for the intake date."""

    #: 23:30 UTC on 11 January 2026 is 00:30 Paris on the 12th: the two zones
    #: name different calendar days at this instant.
    INSTANT = datetime(2026, 1, 11, 23, 30, tzinfo=UTC)

    @staticmethod
    def now(tz: tzinfo | None = None) -> datetime:
        return (
            _FrozenClock.INSTANT if tz is None else _FrozenClock.INSTANT.astimezone(tz)
        )


def test_handle_proposal_stamps_the_paris_day_not_the_utc_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # `opened_on` seeds the vote window, so an intake between 00:00 and 02:00
    # Paris must not be dated on the UTC day that is still yesterday.
    _write_data(tmp_path, [], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr("convener_ops.cli.datetime", _FrozenClock)
    payload = json.dumps({"fields": [{"label": "Name", "value": "Grace Hopper"}]})
    monkeypatch.setenv("PROPOSAL_PAYLOAD", payload)
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 0
    capsys.readouterr()

    written = yaml.safe_load((tmp_path / "data" / "speakers.yml").read_text("utf-8"))
    assert written[0]["selection"]["opened_on"] == "2026-01-12"


def test_handle_proposal_with_an_invalid_signature_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("PROPOSAL_PAYLOAD", '{"fields": []}')
    monkeypatch.setenv("PROPOSAL_SIGNATURE", "deadbeef")
    monkeypatch.setenv("TALLY_WEBHOOK_SECRET", "shh")

    assert handle_proposal() == 1
    assert "invalid signature" in capsys.readouterr().err


def test_handle_proposal_accepts_a_correctly_signed_tally_shaped_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The production path end to end: a secret is configured (so
    # verify_signature cannot short-circuit through the D-13 empty-secret
    # escape), the payload is Tally's own shape -- {"data": {"fields": [...]}}
    # -- which is what the workflow now passes through untouched (cli.py
    # reads payload["data"]["fields"], not the legacy payload["fields"]
    # fallback every other test here exercises), and the signature is the
    # real base64(HMAC-SHA256(secret, payload)) computed over that exact
    # string. Reverting candidate-form.yml to toJSON(...), or adding a
    # .strip() to the payload before verifying, would break this while every
    # other handle_proposal test in this file stayed green.
    _write_data(tmp_path, [speaker(id="spk-001")], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    secret = "s3cr3t"
    payload = json.dumps(
        {"data": {"fields": [{"label": "Name", "value": "Grace Hopper"}]}}
    )
    signature = base64.b64encode(
        hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    ).decode()
    monkeypatch.setenv("PROPOSAL_PAYLOAD", payload)
    monkeypatch.setenv("PROPOSAL_SIGNATURE", signature)
    monkeypatch.setenv("TALLY_WEBHOOK_SECRET", secret)

    assert handle_proposal() == 0
    out = capsys.readouterr().out
    assert "created spk-002 from form proposal" in out

    text = (tmp_path / "data" / "speakers.yml").read_text(encoding="utf-8")
    assert "spk-002" in text
    assert "Grace Hopper" in text


def test_handle_proposal_skips_a_duplicate_lead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_data(
        tmp_path,
        [speaker(id="spk-001", email="grace@example.org", status="lead")],
        config(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    payload = json.dumps(
        {
            "fields": [
                {"label": "Name", "value": "Grace Hopper"},
                {"label": "Email", "value": "grace@example.org"},
            ]
        }
    )
    monkeypatch.setenv("PROPOSAL_PAYLOAD", payload)
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 0
    assert "skipping: duplicate email" in capsys.readouterr().out


def test_handle_proposal_skips_an_empty_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_data(tmp_path, [speaker(id="spk-001")], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    payload = json.dumps({"fields": [{"label": "Name", "value": ""}]})
    monkeypatch.setenv("PROPOSAL_PAYLOAD", payload)
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 0
    assert "skipping: empty name" in capsys.readouterr().out


def test_handle_proposal_reports_load_errors_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()
    monkeypatch.setenv("PROPOSAL_PAYLOAD", '{"fields": []}')
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 1
    assert "file missing" in capsys.readouterr().out


def test_handle_proposal_with_a_non_json_payload_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Reachable in production: with no TALLY_WEBHOOK_SECRET configured,
    # verify_signature accepts any body (D-13), so a malformed one reaches
    # json.loads unguarded unless this raises a clean message instead of an
    # unhandled JSONDecodeError traceback.
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("PROPOSAL_PAYLOAD", "not json at all")
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 1
    assert "invalid JSON payload" in capsys.readouterr().err


def test_handle_proposal_with_a_json_array_payload_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Valid JSON, but not an object -- payload.get(...) would otherwise
    # raise AttributeError on a list.
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("PROPOSAL_PAYLOAD", "[1, 2, 3]")
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 1
    assert "invalid JSON payload" in capsys.readouterr().err


def test_handle_proposal_treats_a_non_list_fields_value_as_no_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Tally always sends "fields" as a list, but the signature only proves
    # who sent the body, not its shape (see handle_proposal's docstring). A
    # payload where "fields" is null (present but not a list, and not even
    # iterable) must degrade to "no fields" rather than raise TypeError
    # iterating it. A string would be iterable by accident and pass this
    # test even with the guard removed -- null does not.
    _write_data(tmp_path, [], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("PROPOSAL_PAYLOAD", json.dumps({"data": {"fields": None}}))
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 0
    assert "skipping: empty name" in capsys.readouterr().out


def test_handle_proposal_resolves_a_picker_shaped_gender_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A DROPDOWN answer's raw `value` is a list of option ids, not
    # text -- this is the end-to-end proof that handle_proposal resolves it
    # (via field_value) before to_lead ever sees it, using the exact shape
    # Tally's webhook sends, not a plain string standing in for one.
    _write_data(tmp_path, [speaker(id="spk-001")], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    payload = json.dumps(
        {
            "fields": [
                {"label": "Name", "value": "Grace Hopper"},
                {
                    "label": "Gender",
                    "value": ["opt-nb"],
                    "options": [
                        {"id": "opt-f", "text": "F"},
                        {"id": "opt-m", "text": "M"},
                        {"id": "opt-nb", "text": "NB"},
                        {"id": "opt-undisclosed", "text": "undisclosed"},
                    ],
                },
            ]
        }
    )
    monkeypatch.setenv("PROPOSAL_PAYLOAD", payload)
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 0

    written = yaml.safe_load((tmp_path / "data" / "speakers.yml").read_text("utf-8"))
    assert written[-1]["gender"] == "NB"


def test_handle_proposal_never_writes_a_stringified_list_for_an_unresolvable_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An id absent from `options` (a malformed or truncated payload) must
    # not resurrect the original bug: "['unknown-id']" landing in the
    # record instead of the field being recognised as unmapped and falling
    # back to "undisclosed" like any other unrecognised answer.
    _write_data(tmp_path, [speaker(id="spk-001")], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    payload = json.dumps(
        {
            "fields": [
                {"label": "Name", "value": "Grace Hopper"},
                {"label": "Gender", "value": ["unknown-id"], "options": []},
            ]
        }
    )
    monkeypatch.setenv("PROPOSAL_PAYLOAD", payload)
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 0

    text = (tmp_path / "data" / "speakers.yml").read_text(encoding="utf-8")
    assert "['unknown-id']" not in text
    written = yaml.safe_load(text)
    assert written[-1]["gender"] == "undisclosed"


# ------------------------------------------------------------------ #
# resolve_registration_secret() and handle_registration(): the two steps
# .github/workflows/registration.yml runs for one incoming registration.
#
# The job that decrypts a registration is the one place in this project a
# stranger's name and address ever exist as plaintext. These tests are the
# ones that hold that line: no name and no address may appear anywhere the
# job prints, on any path -- success, a fresh registration, a resend that
# updates one, or a failure -- and the same address must never produce a
# second record.
# ------------------------------------------------------------------ #


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


def _publish_event_key(tmp_path: Path, event_id: str = "mrg-042") -> tuple[str, str]:
    private_pem, public_pem = eventkeys.generate()
    keys_dir = tmp_path / "keys" / "events"
    keys_dir.mkdir(parents=True)
    (keys_dir / f"{event_id}.pub").write_text(public_pem, encoding="ascii")
    return private_pem, public_pem


#: Every string that would identify Ada personally, in the fields the
#: fixture above submits. Checked case-insensitively against whatever the
#: job printed -- never against the encrypted file, whose base64 content
#: can legitimately contain a short substring like "ada" by pure chance;
#: `eventkeys.py`'s own tests already cover the file's confidentiality
#: property directly, and a leak test on this job belongs on what the job
#: prints.
_LEAK_STRINGS = (
    "Ada",
    "Lovelace",
    "ada@example.org",
    "Analytical Engines Institute",
)


def _assert_no_leak(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    for secret in _LEAK_STRINGS:
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
    _, public_pem = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert handle_registration() == 1

    err = capsys.readouterr().err
    assert "no private key configured for event mrg-042" in err
    assert not (tmp_path / "data").exists()


def test_handle_registration_does_not_require_a_published_public_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The failure mode this replaces: re-encryption used to read
    `keys/events/<id>.pub` from disk and fail without it. `upsert` now
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
    assert not (tmp_path / "keys").exists()

    assert handle_registration() == 0
    assert (
        "recorded a registration for event mrg-042 (1 total)" in capsys.readouterr().out
    )


def test_handle_registration_rejects_an_undecryptable_payload_and_leaks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_a, _ = _publish_event_key(tmp_path)
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
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    private_pem, public_pem = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert handle_registration() == 0

    out = _assert_no_leak(capsys)
    assert "recorded a registration for event mrg-042 (1 total)" in out

    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
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
    private_pem, public_pem = _publish_event_key(tmp_path)
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

    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    file = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert len(file.entries) == 1
    recovered = to_registration(json.dumps(file.entries[0]), private_pem)
    assert recovered is not None
    assert recovered.institution == "Somewhere Else"


def test_handle_registration_rejects_a_malformed_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = _publish_event_key(tmp_path)
    events_dir = tmp_path / "data" / "events" / "mrg-042"
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
# `_LEAK_STRINGS` is a fixed tuple and the code is a different string on
# every run, so the tests that actually derive one (`CONVENER_MATCHING_SALT`
# set) check its absence from stdout/stderr directly, next to computing the
# same code fresh, rather than pretending a static list could name a value
# it cannot know in advance.
# ------------------------------------------------------------------ #


def _write_event(tmp_path: Path, **overrides: object) -> None:
    """`data/speakers.yml` and `data/config.yml`, with one record whose
    `edition_code` matches the `mrg-042` event id every fixture above
    already submits against."""
    record = speaker(
        edition_code="MRG-042",
        zoom_link="https://meet.example.org/permanent-room",
        title="On analytical engines",
        date="2026-09-01",
    )
    record.update(overrides)
    _write_data(tmp_path, [record], config())


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
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

    _handle_and_send(tmp_path, monkeypatch)

    code = matching_code("mrg-042", "ada@example.org", "shh")
    assert code is not None

    out = capsys.readouterr()
    combined = out.out + out.err
    assert code not in combined, "the matching code leaked into stdout/stderr"

    assert len(_RecordingSmtpClient.sent) == 1
    body = _RecordingSmtpClient.sent[0].get_content()
    assert code in body


def test_handle_registration_confirmation_names_what_changed_on_an_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = _publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("CONVENER_SMTP_PORT", "587")
    monkeypatch.setenv("CONVENER_SMTP_USER", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_SMTP_PASSWORD", "shh")
    monkeypatch.setenv("CONVENER_SMTP_FROM", "convener-registration@example.org")
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

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
    assert len(_RecordingSmtpClient.sent) == 2
    body = _RecordingSmtpClient.sent[1].get_content()
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
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

    _handle_and_send(tmp_path, monkeypatch)

    assert len(_RecordingSmtpClient.sent) == 1
    body = _RecordingSmtpClient.sent[0].get_content()
    assert "This confirms an update" not in body


def test_handle_registration_confirmation_degrades_with_no_speaker_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `data/speakers.yml` at all -- the state every registration test
    before this one already ran in. The registration must still be
    recorded and a confirmation still composed and sent, only without a
    room link."""
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

    _handle_and_send(tmp_path, monkeypatch)

    out = _assert_no_leak(capsys)
    assert "no speaker record matches event mrg-042" in out

    assert len(_RecordingSmtpClient.sent) == 1
    assert _RecordingSmtpClient.sent[0]["To"] == "ada@example.org"


def test_handle_registration_survives_an_unanticipated_confirmation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The property `_send_confirmation`'s docstring names directly: a
    registration already decrypted and written to `registrations.enc` must
    never be lost because composing or sending its confirmation broke in a
    way this job did not anticipate. Simulated by making `compose` itself
    raise -- something no branch above the broad `except` already guards
    against."""
    private_pem, public_pem = _publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    _clear_transport_env(monkeypatch)

    def _broken_compose(*args: object, **kwargs: object) -> object:
        raise RuntimeError("an unanticipated failure inside compose()")

    monkeypatch.setattr("convener_ops.cli.confirmation.compose", _broken_compose)

    _handle_and_send(tmp_path, monkeypatch)

    out = _assert_no_leak(capsys)
    assert "recorded a registration for event mrg-042 (1 total)" in out
    assert "could not be composed or sent" in out

    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    file = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert len(file.entries) == 1


class _RecordingSmtpClient:
    """A fake `smtplib.SMTP`, substituted so `handle_registration` can
    exercise a genuine "sent" outcome without opening a socket.

    `sent` holds `EmailMessage`, not `object`: this double stands in for
    `convener_ops.confirmation`'s own `smtplib.SMTP`, and that module builds an
    `EmailMessage` before every send. It is also what the tests below read
    back -- `get_content()` and header subscripting are `EmailMessage`'s
    own API, which the base `email.message.Message` does not carry."""

    sent: ClassVar[list[EmailMessage]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port

    def starttls(self) -> None:
        pass

    def login(self, user: str, password: str) -> None:
        pass

    def send_message(self, message: EmailMessage) -> None:
        _RecordingSmtpClient.sent.append(message)

    def __enter__(self) -> _RecordingSmtpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_handle_registration_sends_through_a_configured_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

    _handle_and_send(tmp_path, monkeypatch)

    out = _assert_no_leak(capsys)
    assert "confirmation for event mrg-042 sent" in out
    assert len(_RecordingSmtpClient.sent) == 1


def test_send_confirmation_with_no_payload_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("REGISTRATION_PAYLOAD", raising=False)
    assert send_confirmation() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_send_confirmation_fails_closed_without_a_configured_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, public_pem = _publish_event_key(tmp_path)
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert send_confirmation() == 1
    assert "no private key configured for event mrg-042" in capsys.readouterr().err


def test_send_confirmation_rejects_an_undecryptable_payload_and_leaks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_a, _ = _publish_event_key(tmp_path)
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
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    private_pem, public_pem = _publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("CONVENER_SMTP_PORT", "587")
    monkeypatch.setenv("CONVENER_SMTP_USER", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_SMTP_PASSWORD", "shh")
    monkeypatch.setenv("CONVENER_SMTP_FROM", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "shh")
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

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
    assert len(_RecordingSmtpClient.sent) == 1
    original = _RecordingSmtpClient.sent[0].get_content()
    assert code in original

    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv(
        "EMAIL_ENVELOPE", eventkeys.encrypt(public_pem, b"ada@example.org")
    )
    assert resend_confirmation() == 0

    assert len(_RecordingSmtpClient.sent) == 2
    resent = _RecordingSmtpClient.sent[1].get_content()
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
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv(
        "EMAIL_ENVELOPE", eventkeys.encrypt(public_pem, b"ada@example.org")
    )
    assert resend_confirmation() == 0

    assert len(_RecordingSmtpClient.sent) == 1
    resent = _RecordingSmtpClient.sent[0].get_content()
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
    private_pem, _public_pem = _publish_event_key(tmp_path)
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
    private_pem, public_pem = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EMAIL_ENVELOPE", eventkeys.encrypt(public_pem, b""))
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert resend_confirmation() == 1
    assert "encrypted identifier is empty" in capsys.readouterr().err


def test_resend_confirmation_with_nothing_recorded_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    private_pem, public_pem = _publish_event_key(tmp_path)
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
    private_pem, public_pem = _publish_event_key(tmp_path)
    events_dir = tmp_path / "data" / "events" / "mrg-042"
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


# ------------------------------------------------------------------ #
# match_attendance(): join the platform's attendance export
# against this event's registrations, through the eligibility cascade, and
# report the result. Like handle_registration above, this job holds
# decrypted registrations in memory; these tests check the same property
# the registration tests check -- no name and no address may appear
# anywhere this job prints, on any path -- plus one more: the
# host's short list of unresolved attendance goes to a file, never to
# stdout, and only when there is something in it to report.
# ------------------------------------------------------------------ #

_ATTENDANCE_CSV_HEADER = "display_name,email,joined_at,left_at,duration_seconds"


def _write_registrations(
    tmp_path: Path, event_id: str, private_pem: str, *registrations: Registration
) -> None:
    file = load_registration_file(None)
    for registration in registrations:
        file, _replaced = upsert(file, registration, private_pem=private_pem)
    path = tmp_path / "data" / "events" / event_id / "registrations.enc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_registration_file(file), encoding="utf-8")


def _write_attendance_csv(tmp_path: Path, event_id: str, *rows: str) -> None:
    path = tmp_path / "data" / "events" / event_id / "attendance-import.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join((_ATTENDANCE_CSV_HEADER, *rows)) + "\n", encoding="utf-8")


def _write_attendance_csv_encrypted(
    tmp_path: Path, event_id: str, public_pem: str, *rows: str
) -> None:
    """The committed shape:
    `data/events/<id>/attendance-import.csv.enc`, one independent
    `eventkeys` envelope per row -- built through the real
    `parse_attendance_csv` + `platform.encrypt_attendance_rows`, never a
    hand-rolled stand-in for either, the same discipline
    `_write_registrations` already holds for `registrations.enc`."""
    text = "\n".join((_ATTENDANCE_CSV_HEADER, *rows)) + "\n"
    parsed_rows, issues = parse_attendance_csv(text)
    assert issues == []
    path = tmp_path / "data" / "events" / event_id / "attendance-import.csv.enc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        encrypt_attendance_rows(public_pem, parsed_rows), encoding="utf-8", newline=""
    )


def test_encrypt_attendance_export_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)

    assert encrypt_attendance_export() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_encrypt_attendance_export_without_a_published_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert encrypt_attendance_export() == 1
    assert "no public key published" in capsys.readouterr().err


def test_encrypt_attendance_export_without_a_plaintext_csv_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert encrypt_attendance_export() == 1
    err = capsys.readouterr().err
    assert "no attendance export to encrypt" in err
    assert "data/events/mrg-042/attendance-import.csv" in err
    assert str(tmp_path) not in err


def test_encrypt_attendance_export_writes_a_decryptable_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole point: needs no `EVENT_PRIVATE_KEY` at all (never reads
    it), yet what it writes is exactly what `convener-match-attendance` can
    later decrypt with that key -- proven here by decrypting the file this
    command wrote and parsing it back into the original rows, not by
    trusting the envelope's shape alone."""
    private_pem, _public_pem = _publish_event_key(tmp_path)
    events_dir = tmp_path / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "attendance-import.csv").write_text(
        _ATTENDANCE_CSV_HEADER + "\n"
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
        "2026-08-20T19:30:00Z,5400\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert encrypt_attendance_export() == 0
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
    _publish_event_key(tmp_path)
    events_dir = tmp_path / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    plain_path = events_dir / "attendance-import.csv"
    plain_path.write_text(
        _ATTENDANCE_CSV_HEADER + "\nAda,ada@example.org,x,y,60\n", encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert encrypt_attendance_export() == 0
    assert "replacing" not in capsys.readouterr().out

    plain_path.write_text(
        _ATTENDANCE_CSV_HEADER + "\nGrace,grace@example.org,x,y,90\n", encoding="utf-8"
    )
    assert encrypt_attendance_export() == 0
    out = capsys.readouterr().out
    assert "replacing the already-committed" in out
    assert "attendance-import.csv.enc" in out


def test_encrypt_attendance_export_never_reads_the_private_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never touches `EVENT_PRIVATE_KEY` -- the whole reason this command
    can run on a host's own laptop with no CI job and no secret at all
    (the private half `n'est utilisee qu'en integration
    continue`). Asserted by monkeypatching `os.environ.get` and failing
    the moment this name is asked for through it, not merely by leaving
    it unset (which a bug reading it with `or ''` would pass silently).
    This guards the one way `convener_ops` actually reads
    an environment variable today (verified by grep -- nothing in the
    package reads one by subscript or through `os.getenv`); it would not
    by itself catch a future read added through either of those."""
    _publish_event_key(tmp_path)
    events_dir = tmp_path / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "attendance-import.csv").write_text(
        _ATTENDANCE_CSV_HEADER + "\nAda,ada@example.org,x,y,60\n", encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    import os as os_module

    real_get = os_module.environ.get

    def _guarded_get(key: str, default: str | None = None) -> str | None:
        assert key != "EVENT_PRIVATE_KEY", "must never read the event private key"
        return real_get(key, default)

    monkeypatch.setattr(os_module.environ, "get", _guarded_get)

    assert encrypt_attendance_export() == 0


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
    assert encrypt_identifier() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_encrypt_identifier_with_an_invalid_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "../escape")
    assert encrypt_identifier() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_encrypt_identifier_with_no_email_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("REGISTRATION_EMAIL", raising=False)
    assert encrypt_identifier() == 1
    assert "no e-mail address" in capsys.readouterr().err


def test_encrypt_identifier_without_a_published_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")

    assert encrypt_identifier() == 1
    assert "no public key published" in capsys.readouterr().err


def test_encrypt_identifier_never_reads_the_private_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same "no secret needed" proof
    `test_encrypt_attendance_export_never_reads_the_private_key` already
    gives its own sibling command -- encrypting under a public key is
    exactly the operation a stranger with no account, and this command
    with no secret, could already perform."""
    _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")

    import os as os_module

    real_get = os_module.environ.get

    def _guarded_get(key: str, default: str | None = None) -> str | None:
        assert key != "EVENT_PRIVATE_KEY", "must never read the event private key"
        return real_get(key, default)

    monkeypatch.setattr(os_module.environ, "get", _guarded_get)

    assert encrypt_identifier() == 0


def test_encrypt_identifier_prints_a_decryptable_envelope_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The round trip that actually matters: what this command prints is
    exactly what `resend_confirmation` and `erase_registration` can
    decrypt back into the same address -- and the address itself never
    appears in anything this command prints."""
    private_pem, _public_pem = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")

    assert encrypt_identifier() == 0
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
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert match_attendance() == 1
    assert "no registrations recorded" in capsys.readouterr().err


def test_match_attendance_rejects_a_malformed_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
    events_dir = tmp_path / "data" / "events" / "mrg-042"
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)

    class _FailingPlatform:
        def get_attendance(self, event_id: str) -> list[AttendanceRow]:
            raise FCCRequestError(f"GET /conferences/{event_id}/calls failed: timeout")

    monkeypatch.setattr(
        "convener_ops.cli.platform_from_env",
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)

    class _FailingPlatform:
        def get_attendance(self, event_id: str) -> list[AttendanceRow]:
            raise EventNotFoundError(
                f"no FCC conference is recorded for event {event_id!r}"
            )

    monkeypatch.setattr(
        "convener_ops.cli.platform_from_env",
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
    private_pem, _ = _publish_event_key(tmp_path)
    first_marie = Registration("Marie", "Martin", "marie.m1@example.org", "", False)
    second_marie = Registration("Marie", "Martin", "marie.m2@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, first_marie, second_marie)
    _write_attendance_csv(
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
    private_pem, _ = _publish_event_key(tmp_path)
    first_marie = Registration("Marie", "Martin", "marie.m1@example.org", "", False)
    second_marie = Registration("Marie", "Martin", "marie.m2@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, first_marie, second_marie)
    _write_attendance_csv(
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_attendance_csv(
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_attendance_csv(
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
        "convener_ops.cli.matching_code", lambda event_id, email, salt: None
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_attendance_csv(
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
    private_pem, public_pem = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_attendance_csv(
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    code = matching_code("mrg-042", ada.email, "s3cr3t-salt-value")
    assert code is not None
    _write_attendance_csv(
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_attendance_csv(
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_attendance_csv(
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file = load_registration_file(None)
    file, _replaced = upsert(file, ada, private_pem=private_pem)
    _other_private, other_public = eventkeys.generate()
    stray = json.loads(eventkeys.encrypt(other_public, b'{"not": "ours"}'))
    file = RegistrationFile(entries=(*file.entries, stray))
    path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_registration_file(file), encoding="utf-8")
    _write_attendance_csv(
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


# ------------------------------------------------------------------ #
# invite_survey() / record_survey_invitation(): e-mail the
# post-event survey link to every currently *matched* attendee of one
# event, and never a second time by default. Like
# match_attendance above, these tests check that no name or address ever
# reaches stdout, on any path including a refusal -- and that an unmatched
# or an unreachable attendee is never invited, that a closed survey
# refuses outright, and that a resend without resend_all invites nobody.
# ------------------------------------------------------------------ #


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
    `event_private_pem`. Mirrors `_prepare_event` (the certificate
    section's own twin) but never writes `config.yml` -- `invite_survey`
    computes no eligibility threshold, so it tolerates a missing one, the
    same way `match_attendance` already does."""
    private_pem, _ = _publish_event_key(tmp_path, event_id)
    if registrations:
        _write_registrations(tmp_path, event_id, private_pem, *registrations)
    if attendance_rows:
        _write_attendance_csv(tmp_path, event_id, *attendance_rows)
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
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
    for secret in _LEAK_STRINGS:
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
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

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

    assert len(_RecordingSmtpClient.sent) == 1
    email = _RecordingSmtpClient.sent[0]
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
    path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
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
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

    assert invite_survey() == 0
    out = capsys.readouterr().out
    assert "1 sent, 0 not sent" in out
    assert "1 registration(s) could not be read" in out
    assert len(_RecordingSmtpClient.sent) == 1


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
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

    assert invite_survey() == 0
    captured = capsys.readouterr()
    assert "2 sent, 0 not sent" in captured.out
    _assert_survey_leak_sweep(captured.out + captured.err)

    assert len(_RecordingSmtpClient.sent) == 2
    bodies = [message.get_content() for message in _RecordingSmtpClient.sent]
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
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)
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
    registry_path = tmp_path / "data" / "survey-invitations.yml"
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
    registry_path = tmp_path / "data" / "survey-invitations.yml"
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
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

    assert invite_survey() == 0
    if expect_resend:
        assert len(_RecordingSmtpClient.sent) == 1
    else:
        assert len(_RecordingSmtpClient.sent) == 0
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
    registry_path = tmp_path / "data" / "survey-invitations.yml"
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
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

    assert invite_survey() == 0
    captured = capsys.readouterr()
    assert "1 sent, 0 not sent" in captured.out
    _assert_survey_leak_sweep(captured.out + captured.err)
    assert len(_RecordingSmtpClient.sent) == 1


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
        "convener_ops.confirmation.smtplib.SMTP", _FlakySurveySmtpClient
    )

    assert invite_survey() == 0
    assert "1 sent, 0 not sent" in capsys.readouterr().out
    assert _FlakySurveySmtpClient.attempts == 2
    assert len(_FlakySurveySmtpClient.sent) == 1


def test_invite_survey_rejects_a_malformed_committed_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepare_survey_event(tmp_path)
    registry_path = tmp_path / "data" / "survey-invitations.yml"
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

    registry_path = tmp_path / "data" / "survey-invitations.yml"
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
    registry_path = tmp_path / "data" / "survey-invitations.yml"
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
    registry_path = tmp_path / "data" / "survey-invitations.yml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("not valid at all: [", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert record_survey_invitation() == 1
    assert "survey-invitations.yml" in capsys.readouterr().err


# ------------------------------------------------------------------ #
# issue_certificates() / certificates_public_data(): match,
# check eligibility, issue (or reproduce) a certificate per eligible
# attendee, and keep the register. Like match_attendance above, these
# tests check that no name or address ever reaches stdout or the
# certificate register file, plus the two guarantees this section exists
# for: no certificate is issued without both CONVENER_SIGNING_KEY and
# CONVENER_MATCHING_SALT configured, and reissuing an already-registered
# attendee never grows the register.
# ------------------------------------------------------------------ #


#: The name and address every certificate test in this section attends
#: with -- shared so `_assert_no_personal_data_leaked` below sweeps for
#: the same three strings everywhere it is called.
_ADA_PERSONAL_DATA = ("Ada", "Lovelace", "ada@example.org")


def _assert_no_personal_data_leaked(text: str) -> None:
    """The original sweep
    (`test_issue_certificates_issues_one_certificate_for_an_eligible_attendee`)
    only ever ran on the freshly-issued path. A name and an address
    printed on the `already_registered` branch alone -- the branch every
    retry and every scheduled re-run actually takes -- survived the full
    suite. Factored into one helper so every call site sweeps the same
    three strings the same way, and a new branch is one call away from
    being covered rather than one omission away from leaking."""
    for leaked in _ADA_PERSONAL_DATA:
        assert leaked not in text


def _certificates_register_path(tmp_path: Path, event_id: str = "mrg-042") -> Path:
    return tmp_path / "data" / "events" / event_id / "certificates.yml"


#: `CERTIFICATE_ID` is shape-checked
#: (`certificate.is_valid_identifier`) before `reissue_certificate` and
#: `revoke_certificate` do anything else with it, so every certificate id
#: a test hands either command through this env var must have
#: `_new_identifier`'s own shape -- 32 lowercase hex characters -- where
#: the old, human-readable "cert-under-test" would once have done just as
#: well. `_CERT_ID` is reused everywhere a test only needs
#: *some* valid id; `_CERT_ID_OTHER` is a second, distinct one for the few
#: tests that need two.
_CERT_ID = "1" * 32
_CERT_ID_OTHER = "2" * 32


def _write_certificate_register(
    tmp_path: Path,
    event_id: str = "mrg-042",
    *,
    identifier: str = _CERT_ID,
    fingerprint_value: str = "f" * 64,
    state: str = "issued",
    issued_on: str = "2026-08-20",
) -> None:
    """A hand-built one-row `certificates.yml`, for a test that needs
    `CERTIFICATE_ID` to resolve against *some* register row without caring
    which real attendee it names -- most of `reissue_certificate`'s and
    `revoke_certificate`'s own refusal paths never reach the point where
    the row's `fingerprint` is compared against anything, so a dummy value
    is honest here, not a shortcut. Tests that exercise the fingerprint
    match itself compute a real one with `certificate_fingerprint` instead
    (see `test_reissue_certificate_reissues_the_certificate_named_by_id`)."""
    path = _certificates_register_path(tmp_path, event_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "v": 1,
                "certificates": [
                    {
                        "identifier": identifier,
                        "event_id": event_id,
                        "issued_on": issued_on,
                        "fingerprint": fingerprint_value,
                        "state": state,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


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
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_SIGNING_KEY", raising=False)

    assert issue_certificates() == 0
    assert "CONVENER_SIGNING_KEY not configured" in capsys.readouterr().out
    assert not _certificates_register_path(tmp_path).exists()


def test_issue_certificates_with_an_unloadable_signing_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unlike the D-13 case above, a *present*
    but unusable `CONVENER_SIGNING_KEY` -- a secret pasted with a mangled PEM
    header, the ordinary way this fails in Actions -- used to reach
    `signing.sign` from inside the issuance loop and crash with an
    unhandled `signing.SigningError` traceback. Validated once, before
    anything is decrypted, so this is now a one-line refusal instead."""
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", "not-a-pem-at-all")
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert issue_certificates() == 1
    assert "CONVENER_SIGNING_KEY" in capsys.readouterr().err
    assert not _certificates_register_path(tmp_path).exists()


def test_issue_certificates_without_a_matching_salt_issues_nothing_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one deliberate exception to D-13 here: an absent
    CONVENER_MATCHING_SALT is not the ordinary state `config/integrations.yml`
    documents for `matching_code` -- a certificate fingerprint cannot be
    computed safely without it, so this run issues nothing rather than
    writing one unsafely. Same outward shape as the signing-key case
    above (a line, a clean exit, nothing written); the message names the
    real reason."""
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert issue_certificates() == 0
    assert "CONVENER_MATCHING_SALT not configured" in capsys.readouterr().out
    assert not _certificates_register_path(tmp_path).exists()


def test_issue_certificates_with_nothing_recorded_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
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
    private_pem, _ = _publish_event_key(tmp_path)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
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
    private_pem, _ = _publish_event_key(tmp_path)
    events_dir = tmp_path / "data" / "events" / "mrg-042"
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
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, registrations=(ada,)
    )

    class _FailingPlatform:
        def get_attendance(self, event_id: str) -> list[AttendanceRow]:
            raise FCCRequestError(f"GET /conferences/{event_id}/calls failed: timeout")

    monkeypatch.setattr(
        "convener_ops.cli.platform_from_env",
        lambda *args, **kwargs: _FailingPlatform(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")

    assert issue_certificates() == 1
    assert "failed" in capsys.readouterr().err.lower()


def _prepare_event(
    tmp_path: Path,
    *,
    event_id: str = "mrg-042",
    registrations: tuple[Registration, ...] = (),
    attendance_rows: tuple[str, ...] = (),
    threshold_share: float = 0.6666666666666666,
) -> tuple[str, str]:
    """Everything `issue_certificates` needs on disk for one event, short
    of the environment variables a test still sets for itself (which
    secrets are present is exactly what most of these tests vary). Returns
    `(event_private_pem, signing_private_pem)`, so a test can pass both
    straight to `monkeypatch.setenv`."""
    private_pem, _ = _publish_event_key(tmp_path, event_id)
    if registrations:
        # A single call carrying every registration -- `_write_registrations`
        # starts from an empty file on each call it is given (`upsert`ing
        # onto `load_registration_file(None)`), so calling it once per
        # registration, as an earlier version of this loop did, overwrote
        # the file with only the *last* one and silently dropped the rest.
        # Never exercised until a test needed more than one registrant.
        _write_registrations(tmp_path, event_id, private_pem, *registrations)
    if attendance_rows:
        _write_attendance_csv(tmp_path, event_id, *attendance_rows)
    # Not `_write_data` (used elsewhere in this file): that helper's own
    # `data_dir.mkdir()` has no `exist_ok`, and `_write_registrations` /
    # `_write_attendance_csv` above already created `data/events/<id>/`.
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "speakers.yml").write_text(
        yaml.safe_dump(
            [
                speaker(
                    edition_code=event_id.upper(),
                    title="On analytical engines",
                    date="2026-08-20",
                )
            ]
        ),
        encoding="utf-8",
    )
    (data_dir / "config.yml").write_text(
        yaml.safe_dump(config(eligibility_share=threshold_share)), encoding="utf-8"
    )
    signing_private_pem, _ = generate()
    return private_pem, signing_private_pem


def test_issue_certificates_issues_one_certificate_for_an_eligible_attendee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = _prepare_event(
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
    _assert_no_personal_data_leaked(captured.out + captured.err)

    register_text = _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    assert register_text.endswith("\n")
    register_data = yaml.safe_load(register_text)
    [entry] = register_data["certificates"]
    assert entry["event_id"] == "mrg-042"
    assert entry["state"] == "issued"
    assert entry["issued_on"] == paris_today(datetime.now(UTC)).isoformat()
    _assert_no_personal_data_leaked(register_text)


def test_issue_certificates_warns_when_the_event_title_is_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """There was a time when a title over
    `certificate._MAX_TITLE_LENGTH` was truncated on the signed,
    delivered certificate with nothing telling an operator it happened."""
    from convener_ops.certificate import _MAX_TITLE_LENGTH

    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    # Overwrite the speaker record `_prepare_event` already wrote, with an
    # over-long title -- everything else about the event stays identical.
    (tmp_path / "data" / "speakers.yml").write_text(
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
    _assert_no_personal_data_leaked(captured.out + captured.err)


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
# discipline `_FakeRecordingTransport` below uses for `release_recording`'s
# own tests, kept separate here rather than reused across ~1200 lines of
# this file for locality.
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

    monkeypatch.setattr("convener_ops.cli.platform_from_env", fake_platform_from_env)


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
    event_private_pem, signing_private_pem = _prepare_event(
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
    _assert_no_personal_data_leaked(captured.out + captured.err)


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
    event_private_pem, signing_private_pem = _prepare_event(
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
    assert not _certificates_register_path(tmp_path).exists()


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
    event_private_pem, signing_private_pem = _prepare_event(
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

    monkeypatch.setattr("convener_ops.cli.issue", _spy)
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
    event_private_pem, signing_private_pem = _prepare_event(
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
    (tmp_path / "data" / "events" / "mrg-042" / "registrations.enc").write_text(
        dump_registration_file(file), encoding="utf-8"
    )
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
    event_private_pem, signing_private_pem = _prepare_event(
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
    assert not _certificates_register_path(tmp_path).exists()
    _assert_no_personal_data_leaked(captured.out + captured.err)


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
    event_private_pem, signing_private_pem = _prepare_event(
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
    first_register = _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    capsys.readouterr()  # discard the first run's own output

    assert issue_certificates() == 0
    second_captured = capsys.readouterr()
    assert (
        "0 issued, 1 already on record (1 eligible;"
        " 0 registration(s) could not be read)" in second_captured.out
    )
    _assert_no_personal_data_leaked(second_captured.out + second_captured.err)
    second_register = _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    assert second_register == first_register


def test_issue_certificates_rejects_a_malformed_committed_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    register_path = _certificates_register_path(tmp_path)
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
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    register_path = _certificates_register_path(tmp_path)
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
    private_pem, _ = _publish_event_key(tmp_path)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
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
    assert not _certificates_register_path(tmp_path).exists()
    _assert_no_personal_data_leaked(captured.out + captured.err)


def test_issue_certificates_refuses_and_names_the_parse_failure_of_speakers_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A review's own reproduction: a
    `data/speakers.yml` that fails to *parse* used to be indistinguishable
    from an event genuinely absent from a well-formed file -- both landed
    on `EventNotFoundError` and the same "no speaker record matches"
    message, sending an operator looking for a missing record that was
    never actually missing. `_load`'s own errors are surfaced instead."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    private_pem, _ = _publish_event_key(tmp_path)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
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
    assert not _certificates_register_path(tmp_path).exists()
    _assert_no_personal_data_leaked(captured.out + captured.err)


def test_certificates_public_data_aggregates_every_events_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    events_dir = tmp_path / "data" / "events"
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
        (tmp_path / "public-data" / "certificates-public.json").read_text(
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
        (tmp_path / "public-data" / "certificates-public.json").read_text(
            encoding="utf-8"
        )
    )
    assert written == []


def test_certificates_public_data_rejects_a_malformed_register_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    events_dir = tmp_path / "data" / "events" / "mrg-042"
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
    events_dir = tmp_path / "data" / "events" / "mrg-042"
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
# CERTIFICATE_ID (`_write_certificate_register`'s dummy fingerprint is
# never compared against anything before the refusal fires); the tests
# that exercise the fingerprint match itself compute a real one with
# `certificate_fingerprint`, matching what `_prepare_event`'s own
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
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", "not-a-pem-at-all")

    assert reissue_certificate() == 1
    assert "CONVENER_SIGNING_KEY" in capsys.readouterr().err


def test_reissue_certificate_without_a_signing_key_reissues_nothing_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_SIGNING_KEY", raising=False)

    assert reissue_certificate() == 0
    assert "CONVENER_SIGNING_KEY not configured" in capsys.readouterr().out


def test_reissue_certificate_without_a_matching_salt_reissues_nothing_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
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
    private_pem, _ = _publish_event_key(tmp_path)
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
    private_pem, _ = _publish_event_key(tmp_path)
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
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert reissue_certificate() == 1
    assert "no registrations recorded" in capsys.readouterr().err


def test_reissue_certificate_rejects_a_malformed_committed_registrations_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
    events_dir = tmp_path / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "registrations.enc").write_text("not json at all", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

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
    event_private_pem, signing_private_pem = _prepare_event(
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
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 1
    captured = capsys.readouterr()
    assert "no certificate" in captured.err
    assert "on record" in captured.err
    _assert_no_personal_data_leaked(captured.out + captured.err)


def test_reissue_certificate_with_a_missing_config_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    private_pem, _ = _publish_event_key(tmp_path)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_certificate_register(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert reissue_certificate() == 1
    assert "config.yml" in capsys.readouterr().err


def test_reissue_certificate_catches_a_platform_request_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, registrations=(ada,)
    )
    _write_certificate_register(tmp_path)

    class _FailingPlatform:
        def get_attendance(self, event_id: str) -> list[AttendanceRow]:
            raise FCCRequestError(f"GET /conferences/{event_id}/calls failed: timeout")

    monkeypatch.setattr(
        "convener_ops.cli.platform_from_env",
        lambda *args, **kwargs: _FailingPlatform(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

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
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, registrations=(ada,)
    )
    _write_certificate_register(
        tmp_path,
        identifier=_CERT_ID,
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
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert reissue_certificate() == 0
    assert transport.get_calls == [f"/conferences/{conference_id}/calls"]
    captured = capsys.readouterr()
    assert "reissued" in captured.out
    _assert_no_personal_data_leaked(captured.out + captured.err)


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
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, registrations=(ada,)
    )
    _write_certificate_register(
        tmp_path,
        identifier=_CERT_ID,
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
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

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
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path,
        registrations=(ada,),
        # 30 of 90 scheduled minutes -- well under the two-thirds default.
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T18:30:00Z,1800",
        ),
    )
    _write_certificate_register(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 1
    captured = capsys.readouterr()
    assert "does not match any currently eligible attendee" in captured.err
    _assert_no_personal_data_leaked(captured.out + captured.err)


def test_reissue_certificate_rejects_a_malformed_committed_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    register_path = _certificates_register_path(tmp_path)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text("not yaml at all: [unclosed", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_reissue_certificate_rejects_a_register_of_the_wrong_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Valid YAML, but not this format -- exercises `register_from_data`'s
    own refusal, distinct from the malformed-YAML test above."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path,
        registrations=(ada,),
        attendance_rows=(
            "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
            "2026-08-20T19:30:00Z,5400",
        ),
    )
    register_path = _certificates_register_path(tmp_path)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text(
        yaml.safe_dump({"v": 999, "certificates": []}), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)
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
    private_pem, _ = _publish_event_key(tmp_path)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "speakers.yml").write_text(yaml.safe_dump([]), encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    salt = "s3cr3t-salt-value"
    _write_certificate_register(
        tmp_path,
        identifier=_CERT_ID,
        fingerprint_value=certificate_fingerprint("mrg-042", "ada@example.org", salt),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", salt)
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 1
    captured = capsys.readouterr()
    assert "no speaker record" in captured.err
    _assert_no_personal_data_leaked(captured.out + captured.err)


def test_reissue_certificate_refuses_and_names_the_parse_failure_of_speakers_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    private_pem, _ = _publish_event_key(tmp_path)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    _write_attendance_csv(
        tmp_path,
        "mrg-042",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "speakers.yml").write_text("- title: [unterminated", encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    salt = "s3cr3t-salt-value"
    _write_certificate_register(
        tmp_path,
        identifier=_CERT_ID,
        fingerprint_value=certificate_fingerprint("mrg-042", "ada@example.org", salt),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", salt)
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert reissue_certificate() == 1
    captured = capsys.readouterr()
    assert "speakers.yml" in captured.err
    assert "no speaker record" not in captured.err
    _assert_no_personal_data_leaked(captured.out + captured.err)


def test_reissue_certificate_refuses_when_the_standing_certificate_is_still_issued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guard reissue exists for: reissuing over a still-issued row would
    leave two valid, contradictory certificates standing at once. An
    operator must revoke first -- this run, with nothing revoked yet,
    refuses instead."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event_private_pem, signing_private_pem = _prepare_event(
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]

    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])
    assert reissue_certificate() == 1
    captured = capsys.readouterr()
    assert "revoke" in captured.err
    _assert_no_personal_data_leaked(captured.out + captured.err)


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
    event_private_pem, signing_private_pem = _prepare_event(
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"][0]

    monkeypatch.setenv("CERTIFICATE_ID", original["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()

    assert reissue_certificate() == 0
    captured = capsys.readouterr()
    assert "reissued" in captured.out
    assert original["identifier"] in captured.out
    _assert_no_personal_data_leaked(captured.out + captured.err)

    register_text = _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    _assert_no_personal_data_leaked(register_text)
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
    event_private_pem, signing_private_pem = _prepare_event(
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
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
    _assert_no_personal_data_leaked(captured.out + captured.err)

    after_text = _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    _assert_no_personal_data_leaked(after_text)
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
    event_private_pem, signing_private_pem = _prepare_event(
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()

    file = load_registration_file(
        (tmp_path / "data" / "events" / "mrg-042" / "registrations.enc").read_text(
            encoding="utf-8"
        )
    )
    _other_private, other_public = eventkeys.generate()
    stray = json.loads(eventkeys.encrypt(other_public, b'{"not": "ours"}'))
    file = RegistrationFile(entries=(*file.entries, stray))
    (tmp_path / "data" / "events" / "mrg-042" / "registrations.enc").write_text(
        dump_registration_file(file), encoding="utf-8"
    )

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
    register_path = _certificates_register_path(tmp_path)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text("not yaml at all: [unclosed", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert revoke_certificate() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_revoke_certificate_rejects_a_register_of_the_wrong_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    register_path = _certificates_register_path(tmp_path)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text(
        yaml.safe_dump({"v": 999, "certificates": []}), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert revoke_certificate() == 1
    assert "certificates.yml" in capsys.readouterr().err


def test_revoke_certificate_refuses_an_unknown_identifier_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`certificate.revoke`'s own guard, surfaced verbatim -- this is the
    guard the whole command turns on: unreachable from a text editor,
    reachable here. The one register row on file must come back
    unchanged."""
    _write_certificate_register(tmp_path, identifier=_CERT_ID)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID_OTHER)

    assert revoke_certificate() == 1
    captured = capsys.readouterr()
    assert "cannot revoke" in captured.err
    assert _CERT_ID_OTHER in captured.err
    register_text = _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    assert yaml.safe_load(register_text)["certificates"][0]["state"] == "issued"


def test_revoke_certificate_refuses_a_row_naming_a_different_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercised through the real CLI command, not
    only `certificate.revoke` directly (see `test_certificate.py`'s own
    unit-level pair): `data/events/mrg-042/certificates.yml` can still
    carry a row whose own `event_id` field names a different event --
    `register_from_data` does not itself refuse one -- and this event's
    own revoke command must not be able to touch it."""
    _write_certificate_register(tmp_path, event_id="mrg-042", identifier=_CERT_ID)
    foreign_path = _certificates_register_path(tmp_path, event_id="mrg-042")
    data = yaml.safe_load(foreign_path.read_text(encoding="utf-8"))
    data["certificates"][0]["event_id"] = "mrg-999"
    foreign_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

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
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID_OTHER)

    assert revoke_certificate() == 1
    capsys.readouterr()
    assert not _certificates_register_path(tmp_path).exists()


def test_revoke_certificate_revokes_the_named_certificate_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_certificate_register(tmp_path, identifier=_CERT_ID, state="issued")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert revoke_certificate() == 0
    captured = capsys.readouterr()
    assert _CERT_ID in captured.out
    assert "revoked" in captured.out

    register_text = _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    assert register_text.endswith("\n")
    [entry] = yaml.safe_load(register_text)["certificates"]
    assert entry["identifier"] == _CERT_ID
    assert entry["state"] == "revoked"


def test_revoke_certificate_only_revokes_the_named_identifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mutation this runs directly: a
    `convener-revoke-certificate` that revoked the wrong identifier, or flipped
    every row instead of one, would still pass a single-entry register
    test. Two rows, only one named -- the other must come back
    byte-for-byte the row it started as."""
    path = _certificates_register_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "v": 1,
                "certificates": [
                    {
                        "identifier": _CERT_ID,
                        "event_id": "mrg-042",
                        "issued_on": "2026-08-20",
                        "fingerprint": "a" * 64,
                        "state": "issued",
                    },
                    {
                        "identifier": _CERT_ID_OTHER,
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
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert revoke_certificate() == 0
    capsys.readouterr()

    certificates = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    by_identifier = {row["identifier"]: row for row in certificates}
    assert by_identifier[_CERT_ID]["state"] == "revoked"
    assert by_identifier[_CERT_ID_OTHER] == {
        "identifier": _CERT_ID_OTHER,
        "event_id": "mrg-042",
        "issued_on": "2026-08-20",
        "fingerprint": "b" * 64,
        "state": "issued",
    }


# ------------------------------------------------------------------ #
# deliver_certificates() / deliver_certificate(): the only step in this
# project that sends a nominative document anywhere (by e-mail, never as a
# named document deposited in a
# depot."). Like the certificate tests above, these check that no name or
# address ever reaches stdout or the certificate register -- and that the
# *rendered document* never reaches disk either, that a replay reproduces
# the identical document rather than regenerating one, and that the
# already-registered
# path leaks nothing, not only the freshly-issued one -- a real defect
# once found in certificate.py, guarded here in a second module.
# ------------------------------------------------------------------ #

#: The same fixture the earlier `issue_certificates` tests use, shared here
#: so the certificate register a `deliver_certificates` test reads is
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
    opening a socket. Kept separate from `_RecordingSmtpClient` above
    (confirmation's own fake) rather than shared, so a test in this
    section can never be satisfied by state a confirmation test left
    behind, or vice versa."""

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
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_SIGNING_KEY", raising=False)

    assert deliver_certificates() == 0
    assert "CONVENER_SIGNING_KEY not configured" in capsys.readouterr().out


def test_deliver_certificates_without_a_matching_salt_delivers_nothing_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
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
    private_pem, _ = _publish_event_key(tmp_path)
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
    event_private_pem, signing_private_pem = _prepare_event(
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
    assert not _certificates_register_path(tmp_path).exists()

    assert deliver_certificates() == 1
    captured = capsys.readouterr()
    assert "no certificate register for event mrg-042" in captured.err
    _assert_no_personal_data_leaked(captured.out + captured.err)
    assert not _certificates_register_path(tmp_path).exists()


def test_deliver_certificates_with_no_transport_configured_reports_all_unsent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
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
    _assert_no_personal_data_leaked(captured.out + captured.err)
    assert "not sent: " in captured.out


def test_deliver_certificates_delivers_to_an_eligible_attendee_and_leaks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
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
    _assert_no_personal_data_leaked(captured.out + captured.err)

    assert len(_RecordingCertificateSmtpClient.sent) == 1
    email = _RecordingCertificateSmtpClient.sent[0]
    assert email["To"] == "ada@example.org"
    document = _sent_attachment_html(email)
    assert "Ada Lovelace" in document
    _assert_no_personal_data_leaked(email["Subject"])


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
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    assert issue_certificates() == 0  # a second, routine re-run: 0 issued, 1 already
    capsys.readouterr()

    assert deliver_certificates() == 0
    captured = capsys.readouterr()
    _assert_no_personal_data_leaked(captured.out + captured.err)
    assert len(_RecordingCertificateSmtpClient.sent) == 1


def test_deliver_certificates_never_writes_anything_to_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No path this function takes may place a rendered certificate under
    the repository, committed or not."""
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
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
    """A failed remise must replay
    without regenerating -- the identifier, the payload and the signature
    must not change. Simulated here by calling `deliver_certificates`
    twice in a row (the same recovery path a real retry takes: re-running
    the command, or the whole workflow) and comparing the two attachments
    byte for byte."""
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
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
# `_prepare_event` / `_RecordingCertificateSmtpClient` fixtures every
# other delivery test in this file already uses.
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
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    [entry] = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()
    before_redelivery = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]

    # A routine re-run of convener-issue-certificates: must mint nothing new.
    assert issue_certificates() == 0
    issue_captured = capsys.readouterr()
    assert "1 refused" in issue_captured.out

    assert deliver_certificates() == 0
    deliver_captured = capsys.readouterr()
    _assert_no_personal_data_leaked(deliver_captured.out + deliver_captured.err)
    assert "0 sent, 0 not sent, 1 refused (revoked)" in deliver_captured.out
    assert len(_RecordingCertificateSmtpClient.sent) == 0

    after = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
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
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    [original] = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", original["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()
    assert reissue_certificate() == 0
    capsys.readouterr()
    certificates = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
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
    _assert_no_personal_data_leaked(captured.out + captured.err)
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
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    [entry] = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()

    assert deliver_certificate() == 1
    captured = capsys.readouterr()
    assert f"certificate {entry['identifier']} is revoked" in captured.err
    _assert_no_personal_data_leaked(captured.out + captured.err)
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
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    [original] = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", original["identifier"])
    assert revoke_certificate() == 0
    capsys.readouterr()
    assert reissue_certificate() == 0
    capsys.readouterr()
    certificates = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
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
    _assert_no_personal_data_leaked(captured.out + captured.err)

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
    event_private_pem, signing_private_pem = _prepare_event(
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert f"issued_ids={entry['identifier']}" in lines
    _assert_no_personal_data_leaked(output_path.read_text(encoding="utf-8"))


def test_issue_certificates_github_output_is_empty_when_nothing_is_freshly_issued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A routine re-run: everyone is already on record, so `issued_ids`
    must be the empty string -- the signal `deliver_certificates` reads as
    "deliver nobody this run"."""
    event_private_pem, signing_private_pem = _prepare_event(
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
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    certificates = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    assert len(certificates) == 2
    salt = "s3cr3t-salt-value"
    ada_fingerprint = certificate_fingerprint("mrg-042", "ada@example.org", salt)
    [ada_row] = [row for row in certificates if row["fingerprint"] == ada_fingerprint]

    monkeypatch.setenv("DELIVER_ONLY", ada_row["identifier"])
    assert deliver_certificates() == 0
    captured = capsys.readouterr()
    _assert_no_personal_data_leaked(captured.out + captured.err)
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
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
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
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )
    assert issue_certificates() == 0
    capsys.readouterr()
    certificates = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
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
    private_pem, _ = _publish_event_key(tmp_path)
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
    private_pem, _ = _publish_event_key(tmp_path)
    events_dir = tmp_path / "data" / "events" / "mrg-042"
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
    private_pem, _ = _publish_event_key(tmp_path)
    _write_registrations(tmp_path, "mrg-042", private_pem, _ADA)
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
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, registrations=(_ADA,)
    )

    class _FailingPlatform:
        def get_attendance(self, event_id: str) -> list[AttendanceRow]:
            raise FCCRequestError(f"GET /conferences/{event_id}/calls failed: timeout")

    monkeypatch.setattr(
        "convener_ops.cli.platform_from_env",
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
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    file = load_registration_file(None)
    file, _replaced = upsert(file, _ADA, private_pem=event_private_pem)
    _other_private, other_public = eventkeys.generate()
    stray = json.loads(eventkeys.encrypt(other_public, b'{"not": "ours"}'))
    file = RegistrationFile(entries=(*file.entries, stray))
    (tmp_path / "data" / "events" / "mrg-042" / "registrations.enc").write_text(
        dump_registration_file(file), encoding="utf-8"
    )
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
    private_pem, _ = _publish_event_key(tmp_path)
    _write_registrations(tmp_path, "mrg-042", private_pem, _ADA)
    _write_attendance_csv(tmp_path, "mrg-042", _ADA_ATTENDANCE_ROW)
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
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
    _assert_no_personal_data_leaked(captured.out + captured.err)


def test_deliver_certificates_rejects_a_malformed_committed_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    register_path = _certificates_register_path(tmp_path)
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
    event_private_pem, signing_private_pem = _prepare_event(
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

    monkeypatch.setattr("convener_ops.cli.delivery.render_certificate", _raise)

    assert deliver_certificates() == 0
    captured = capsys.readouterr()
    # A render crash is counted separately from
    # a transport failure -- see deliver_certificates's own docstring.
    assert (
        "0 sent, 0 not sent, 0 refused (revoked), 1"
        " failed to render, 0 not targeted this run "
        "(1 eligible; 0 registration(s) could not be read)" in captured.out
    )
    _assert_no_personal_data_leaked(captured.out + captured.err)
    assert "RuntimeError" not in captured.out
    assert "RuntimeError" not in captured.err


def test_deliver_certificates_refuses_and_names_the_parse_failure_of_speakers_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
    _write_registrations(tmp_path, "mrg-042", private_pem, _ADA)
    _write_attendance_csv(tmp_path, "mrg-042", _ADA_ATTENDANCE_ROW)
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
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
    _assert_no_personal_data_leaked(captured.out + captured.err)


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
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_SIGNING_KEY", raising=False)

    assert deliver_certificate() == 0
    assert "CONVENER_SIGNING_KEY not configured" in capsys.readouterr().out


def test_deliver_certificate_without_a_matching_salt_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
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
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert deliver_certificate() == 1
    assert "no registrations recorded" in capsys.readouterr().err


def test_deliver_certificate_refuses_when_the_certificate_id_is_not_on_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert deliver_certificate() == 1
    assert f"no certificate {_CERT_ID} on record" in capsys.readouterr().err


def test_deliver_certificate_refuses_when_the_certificate_id_matches_nobody_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    _write_certificate_register(tmp_path, fingerprint_value="not-adas-fingerprint")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert deliver_certificate() == 1
    assert "does not match any currently eligible attendee" in capsys.readouterr().err


def test_deliver_certificate_delivers_the_named_certificate_and_leaks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    captured = capsys.readouterr()
    register_text = _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    [entry] = yaml.safe_load(register_text)["certificates"]
    certificate_id = entry["identifier"]

    monkeypatch.setenv("CERTIFICATE_ID", certificate_id)
    assert deliver_certificate() == 0
    captured = capsys.readouterr()
    assert f"certificate {certificate_id} delivered for event mrg-042" in captured.out
    _assert_no_personal_data_leaked(captured.out + captured.err)

    assert len(_RecordingCertificateSmtpClient.sent) == 1
    email = _RecordingCertificateSmtpClient.sent[0]
    assert email["To"] == "ada@example.org"
    document = _sent_attachment_html(email)
    assert "Ada Lovelace" in document
    _assert_no_personal_data_leaked(email["Subject"])


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
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    certificates = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
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
    _assert_no_personal_data_leaked(captured.out + captured.err)

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
    event_private_pem, signing_private_pem = _prepare_event(
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])

    assert deliver_certificate() == 0
    captured = capsys.readouterr()
    assert "not delivered" in captured.out
    _assert_no_personal_data_leaked(captured.out + captured.err)


def test_deliver_certificate_replays_the_identical_document_on_a_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
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
        "convener_ops.delivery.smtplib.SMTP", _RecordingCertificateSmtpClient
    )

    assert issue_certificates() == 0
    capsys.readouterr()
    [entry] = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    assert [row["identifier"] for row in register_after] == [entry["identifier"]], (
        "a resend must never mint a second register row for the same certificate"
    )


def test_deliver_certificate_with_an_unloadable_signing_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", "not-a-pem-at-all")
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert deliver_certificate() == 1
    assert "CONVENER_SIGNING_KEY" in capsys.readouterr().err


def test_deliver_certificate_rejects_a_malformed_committed_registrations_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
    events_dir = tmp_path / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "registrations.enc").write_text("not json at all", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", generate()[0])
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert deliver_certificate() == 1
    assert "registrations.enc" in capsys.readouterr().err


def test_deliver_certificate_with_a_missing_config_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    _write_certificate_register(tmp_path)
    (tmp_path / "data" / "config.yml").unlink()
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert deliver_certificate() == 1
    assert "config.yml" in capsys.readouterr().err


def test_deliver_certificate_catches_a_platform_request_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, registrations=(_ADA,)
    )
    _write_certificate_register(tmp_path)

    class _FailingPlatform:
        def get_attendance(self, event_id: str) -> list[AttendanceRow]:
            raise FCCRequestError(f"GET /conferences/{event_id}/calls failed: timeout")

    monkeypatch.setattr(
        "convener_ops.cli.platform_from_env",
        lambda *args, **kwargs: _FailingPlatform(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

    assert deliver_certificate() == 1
    assert "failed" in capsys.readouterr().err.lower()


def test_deliver_certificate_refuses_when_no_speaker_record_supplies_a_title_and_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    (tmp_path / "data" / "speakers.yml").write_text(
        yaml.safe_dump([]), encoding="utf-8"
    )
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])

    assert deliver_certificate() == 1
    captured = capsys.readouterr()
    assert "no speaker record" in captured.err
    _assert_no_personal_data_leaked(captured.out + captured.err)


def test_deliver_certificate_rejects_a_malformed_committed_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
        tmp_path, registrations=(_ADA,), attendance_rows=(_ADA_ATTENDANCE_ROW,)
    )
    register_path = _certificates_register_path(tmp_path)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text("not yaml at all: [unclosed", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", event_private_pem)
    monkeypatch.setenv("CONVENER_SIGNING_KEY", signing_private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt-value")
    monkeypatch.setenv("CERTIFICATE_ID", _CERT_ID)

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
    event_private_pem, signing_private_pem = _prepare_event(
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])

    def _raise(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError("a reason this job did not anticipate")

    monkeypatch.setattr("convener_ops.cli.delivery.render_certificate", _raise)

    assert deliver_certificate() == 0
    captured = capsys.readouterr()
    assert "could not be delivered" in captured.out
    _assert_no_personal_data_leaked(captured.out + captured.err)
    assert "RuntimeError" not in captured.out
    assert "RuntimeError" not in captured.err


def test_deliver_certificate_skips_a_stray_entry_that_fails_to_decrypt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stray entry encrypted under an unrelated key pair must not stop a
    resend for the one registration that does decrypt -- the same handling
    `issue_certificates` and `reissue_certificate` already give a stray
    entry."""
    event_private_pem, signing_private_pem = _prepare_event(
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]

    file = load_registration_file(
        (tmp_path / "data" / "events" / "mrg-042" / "registrations.enc").read_text(
            encoding="utf-8"
        )
    )
    _other_private, other_public = eventkeys.generate()
    stray = json.loads(eventkeys.encrypt(other_public, b'{"not": "ours"}'))
    file = RegistrationFile(entries=(*file.entries, stray))
    (tmp_path / "data" / "events" / "mrg-042" / "registrations.enc").write_text(
        dump_registration_file(file), encoding="utf-8"
    )
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
    _assert_no_personal_data_leaked(captured.out + captured.err)


def test_deliver_certificate_refuses_and_names_the_parse_failure_of_speakers_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event_private_pem, signing_private_pem = _prepare_event(
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    (tmp_path / "data" / "speakers.yml").write_text(
        "- title: [unterminated", encoding="utf-8"
    )
    monkeypatch.setenv("CERTIFICATE_ID", entry["identifier"])

    assert deliver_certificate() == 1
    captured = capsys.readouterr()
    assert "speakers.yml" in captured.err
    assert "no speaker record" not in captured.err
    _assert_no_personal_data_leaked(captured.out + captured.err)


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
    event_private_pem, signing_private_pem = _prepare_event(
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
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    certificate_id = entry["identifier"]

    # Simulates the retention sweep: the registration -- and with it
    # the only address this certificate could ever be resent to -- is
    # gone. certificates.yml, in the same directory, is deliberately left
    # untouched (certificate.py's own module docstring, "the register
    # survives the data it was derived from").
    (tmp_path / "data" / "events" / "mrg-042" / "registrations.enc").unlink()

    monkeypatch.setenv("CERTIFICATE_ID", certificate_id)
    assert deliver_certificate() == 1
    captured = capsys.readouterr()
    assert "no registrations recorded" in captured.err
    _assert_no_personal_data_leaked(captured.out + captured.err)
    # The certificate itself is untouched -- still on record, still issued.
    still_there = yaml.safe_load(
        _certificates_register_path(tmp_path).read_text(encoding="utf-8")
    )["certificates"]
    assert still_there == [entry]


# ------------------------------------------------------------------ #
# release_recording(): retrieve, verify the retrieval, then
# delete. This ordering gets a test that fails if deletion
# is reachable without a verified retrieval, not a paragraph. Every test
# below that expects no deletion asserts directly on
# `transport.delete_calls`, never only on the return code -- a change
# that returns 1 but deletes anyway would still fail one of these.
#
# `_FakeRecordingTransport` is keyed by the exact path or URL it is asked
# for, never a positionless queue: a caller
# that resolves the wrong conference id touches a path this fake was
# never told about and fails loudly, rather than silently answering with
# data that happens to belong to a different conference. `_patch_platform`
# forwards whatever `conference_ids` `release_recording` actually built
# from `CONVENER_FCC_CONFERENCE_ID` -- never hardcodes it -- so a test that
# sets the wrong value genuinely exercises a different path.
# ------------------------------------------------------------------ #

_CONFERENCE_ID = "618515381"
_PATH = f"/conferences/{_CONFERENCE_ID}"
_RECORDING_URL = "https://cdn.example.org/rec/618515381"
_VIDEO_URL = _RECORDING_URL + ".video.mp4"


def _recording_payload(
    *, available: bool = True, file_size: int = 900_000_000
) -> dict[str, Any]:
    if not available:
        return {
            "recording_url": "",
            "file_size": 0,
            "is_recorded": False,
            "deleted": False,
        }
    return {
        "recording_url": _RECORDING_URL,
        "file_size": file_size,
        "is_recorded": True,
        "deleted": False,
    }


def _video_headers(*, content_length: int = 900_000_000) -> dict[str, str]:
    """A `head()` response shaped exactly like the provider's own
    converted recording, as measured against the real provider:
    `video/mp4`, `Accept-Ranges: bytes`."""
    return {
        "content_type": "video/mp4",
        "accept_ranges": "bytes",
        "content_length": str(content_length),
    }


class _FakeRecordingTransport:
    """Structurally an `FCCTransport` -- `get_json`/`delete`/`head` --
    keyed by the exact path or URL it is asked for. `get_results` maps a
    path to a list of payload-dicts or exceptions, consumed in call
    order, so the pre-delete and post-delete reads of the same path can
    answer differently. Records every call it receives, so a test can
    assert directly on what was, and was not, called -- never only on
    `release_recording`'s return code."""

    def __init__(
        self,
        get_results: dict[str, list[Any]],
        head_responses: dict[str, dict[str, str] | None] | None = None,
        delete_error: Exception | None = None,
    ) -> None:
        self._get_results = {path: list(queue) for path, queue in get_results.items()}
        self.head_responses = dict(head_responses or {})
        self.delete_error = delete_error
        self.get_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.head_calls: list[str] = []

    def get_json(self, path: str, token: str) -> Any:
        self.get_calls.append(path)
        queue = self._get_results.get(path)
        if not queue:
            raise AssertionError(f"unexpected GET {path}")
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def delete(self, path: str, token: str) -> None:
        self.delete_calls.append(path)
        if self.delete_error is not None:
            raise self.delete_error

    def head(self, url: str) -> dict[str, str] | None:
        self.head_calls.append(url)
        return self.head_responses.get(url)


def _write_speaker_for_recording(
    tmp_path: Path,
    event_id: str = "mrg-042",
    retrieved: bool = False,
    consent_granted: bool = False,
) -> None:
    """`retrieved=True` ticks `RETRIEVED_TICK` on `runbook_progress` --
    trace 1. Never sets `youtube_url`: that field is a
    publication signal, deliberately irrelevant to this guard.

    `consent_granted=True` sets
    `publication.consent: "granted"` and nothing else -- the one condition
    `cli.py::_consent_granted` requires before `release_recording` will
    even attempt the two-trace check. `outcome` is deliberately left
    blank even when `consent_granted=True`: the whole point is that
    `outcome` (the board's own, later archive gate) must not gate this
    function at all. Defaults to `False` (the ordinary state for a fresh
    talk whose speaker has not yet answered, and the only state
    `discard_recording`'s own tests need, since that function never reads
    `publication` at all)."""
    runbook_progress = {RETRIEVED_TICK: True} if retrieved else {}
    publication: dict[str, Any] = {
        "consent": "granted" if consent_granted else "",
        "approved_by": "",
        "approved_on": "",
        "objections": [],
        "outcome": "",
    }
    _write_data(
        tmp_path,
        [
            speaker(
                edition_code=event_id.upper(),
                runbook_progress=runbook_progress,
                publication=publication,
            )
        ],
        config(),
    )


def _set_fcc_env(
    monkeypatch: pytest.MonkeyPatch,
    event_id: str = "mrg-042",
    conference_id: str = _CONFERENCE_ID,
) -> None:
    monkeypatch.setenv("EVENT_ID", event_id)
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.setenv("CONVENER_FCC_CONFERENCE_ID", conference_id)


def _patch_platform(
    monkeypatch: pytest.MonkeyPatch, transport: _FakeRecordingTransport
) -> None:
    def fake_platform_from_env(
        env: Any,
        speakers: Any = (),
        config: Any = None,
        conference_ids: Any = None,
    ) -> PlatformFCC:
        return PlatformFCC(
            access_token="tok",
            speakers=speakers,
            config=config,
            conference_ids=dict(conference_ids or {}),
            transport=transport,
        )

    monkeypatch.setattr("convener_ops.cli.platform_from_env", fake_platform_from_env)


@pytest.mark.parametrize(
    ("label", "publication"),
    [
        ("granted", {"consent": "granted"}),
        ("refused", {"consent": "refused"}),
        ("pending", {"consent": "pending"}),
        ("blank", {"consent": ""}),
        ("unrecognised", {"consent": "yes please"}),
        ("missing_key", {}),
        ("missing_block", None),
        ("malformed_block", "not a mapping"),
    ],
)
def test_consent_granted_is_the_narrow_silence_is_never_a_yes_rule(
    label: str, publication: Any
) -> None:
    """`_consent_granted` is the one place this asymmetry is checked, so
    it is pinned directly rather than only through `release_recording`'s
    own behaviour: only the literal string `"granted"` is a yes; every
    other value, including one this project has never seen before, and a
    missing or malformed `publication` block entirely, is silence."""
    from convener_ops.cli import _consent_granted

    record: dict[str, Any] = {}
    if publication is not None:
        record["publication"] = publication

    assert _consent_granted(record) == (label == "granted")


def test_release_recording_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)

    assert release_recording() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_release_recording_with_an_invalid_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "../escape")

    assert release_recording() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_release_recording_with_an_unknown_event_id_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-999")

    assert release_recording() == 1
    assert "mrg-999" in capsys.readouterr().err


def test_release_recording_reports_a_malformed_speakers_file_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "speakers.yml").write_text("key: [unclosed\n", encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert release_recording() == 1
    assert "invalid YAML" in capsys.readouterr().out


def test_release_recording_refuses_when_consent_is_not_granted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Enforced, not only documented. A
    fresh talk (the default, unfixtured `publication` block -- consent
    blank, the ordinary state before a speaker has answered) is refused
    before any platform interaction at all -- not the two-trace check
    that ran here before, a different, earlier one."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", retrieved=True)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.setenv("CONVENER_FCC_CONFERENCE_ID", _CONFERENCE_ID)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    err = capsys.readouterr().err
    assert "publication consent is not granted" in err
    assert "discard_recording" in err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_release_recording_refuses_when_consent_is_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pins the asymmetry `_consent_granted`'s own docstring names --
    "not did they refuse but did they agree" -- for the one value most
    likely to be mistaken for a soft yes: a speaker who has been asked and
    has not yet answered must not release either."""
    _write_data(
        tmp_path,
        [
            speaker(
                edition_code="MRG-042",
                publication={
                    "consent": "pending",
                    "approved_by": "",
                    "approved_on": "",
                    "objections": [],
                    "outcome": "",
                },
                runbook_progress={RETRIEVED_TICK: True},
            )
        ],
        config(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert "publication consent is not granted" in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_refuses_when_consent_is_refused_even_with_a_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exact scenario, expected to refuse rather than
    succeed: a speaker who explicitly refused consent, with the host
    having retrieved the recording regardless. `release_recording` is the
    wrong route for this -- `discard_recording` is (see the dedicated
    test in that section)."""
    _write_data(
        tmp_path,
        [
            speaker(
                edition_code="MRG-042",
                youtube_url="",
                publication={
                    "consent": "refused",
                    "approved_by": "",
                    "approved_on": "",
                    "objections": [],
                    "outcome": "withheld",
                },
                runbook_progress={RETRIEVED_TICK: True},
            )
        ],
        config(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert "publication consent is not granted" in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_succeeds_when_consent_is_granted_regardless_of_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The concrete regression test for the correction: a
    speaker who agreed, on a talk `finalize-archive` has not yet run for
    (the ordinary state right after an event) -- exactly the scenario
    the wrong gate refused. Freeing the
    quota is not publishing, so this must succeed regardless of
    `outcome`."""
    _write_data(
        tmp_path,
        [
            speaker(
                edition_code="MRG-042",
                publication={
                    "consent": "granted",
                    "approved_by": "",
                    "approved_on": "",
                    "objections": [],
                    "outcome": "",
                },
                runbook_progress={RETRIEVED_TICK: True},
            )
        ],
        config(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]},
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 0
    assert transport.delete_calls == [_PATH]
    assert "retrieved, verified, and released" in capsys.readouterr().out


def test_release_recording_without_a_configured_account_is_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-13: no token is the ordinary state. ManualPlatform holds no
    recording storage of its own, so this is a harmless no-op, not a
    failure. `consent_granted=True` so this test still reaches that branch rather
    than the (new, earlier) publication gate."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", consent_granted=True)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert release_recording() == 0
    assert "nothing to release" in capsys.readouterr().out


def test_release_recording_is_a_noop_when_nothing_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", consent_granted=True)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport({_PATH: [_recording_payload(available=False)]})
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 0
    assert "nothing to release" in capsys.readouterr().out
    assert transport.delete_calls == []


def test_release_recording_treats_a_malformed_runbook_progress_as_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runbook_progress` loaded as `None`, or any non-mapping, must
    refuse rather than crash -- the same "empty means missing" reading
    `release_recording` gives a genuinely absent tick. Consent granted
    so this test still reaches the retrieval-tick check, not the (new,
    earlier) publication gate."""
    _write_data(
        tmp_path,
        [
            speaker(
                edition_code="MRG-042",
                runbook_progress=None,
                publication={
                    "consent": "granted",
                    "approved_by": "",
                    "approved_on": "",
                    "objections": [],
                    "outcome": "published",
                },
            )
        ],
        config(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert RETRIEVED_TICK in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_refuses_without_the_retrieved_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=False, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    err = capsys.readouterr().err
    assert RETRIEVED_TICK in err
    assert transport.delete_calls == []


def test_release_recording_ignores_youtube_url_and_still_requires_the_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`youtube_url` is a publication signal,
    not a retrieval one, and must not satisfy this guard by itself --
    even when it is set to something plausible. Consent granted so
    this test still reaches the retrieval-tick check."""
    _write_data(
        tmp_path,
        [
            speaker(
                edition_code="MRG-042",
                youtube_url="https://youtu.be/abc123",
                runbook_progress={},
                publication={
                    "consent": "granted",
                    "approved_by": "",
                    "approved_on": "",
                    "objections": [],
                    "outcome": "published",
                },
            )
        ],
        config(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert RETRIEVED_TICK in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_succeeds_once_consent_is_granted_and_both_traces_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The positive case the consent gate still has to permit: a talk
    whose speaker agreed (`consent: granted`) and whose retrieval is
    genuinely verified must still succeed -- the gate narrows who may use
    this route, it does not additionally weaken the two traces that
    already governed it."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]},
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 0
    assert transport.delete_calls == [_PATH]
    assert "retrieved, verified, and released" in capsys.readouterr().out


def test_release_recording_refuses_when_the_converted_video_is_not_reachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    # No head_responses entry: the fake answers `None` for every URL, the
    # same "not yet" `_UrllibTransport.head` gives on a 404.
    transport = _FakeRecordingTransport({_PATH: [_recording_payload()]})
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    err = capsys.readouterr().err
    assert "converted recording" in err
    assert transport.delete_calls == []


def test_release_recording_refuses_a_200_that_looks_like_an_error_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reviewer's probe: a 200 with
    `Content-Type: text/html` (a CDN's own error page, or a followed
    redirect to one) must not count as proof of conversion."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]},
        head_responses={_VIDEO_URL: {"content_type": "text/html; charset=utf-8"}},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert "converted recording" in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_does_not_delete_when_get_recording_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guard on a failed retrieval: it must never still delete."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [FCCRequestError("GET /conferences/618515381 failed: timeout")]}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert "failed" in capsys.readouterr().err.lower()
    assert transport.delete_calls == []


def test_release_recording_refuses_a_non_numeric_conference_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reviewer's probe, with the exact value they
    used (`THIS-IS-THE-WRONG-CONFERENCE`). With `_patch_platform` no
    longer hardcoding `conference_ids`, this reaches `PlatformFCC`'s own
    digit-only validation and is refused before any
    transport call -- never silently deletes whatever the fake happens to
    have registered under a different, hardcoded path."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch, conference_id="THIS-IS-THE-WRONG-CONFERENCE")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    err = capsys.readouterr().err
    assert "not a valid FCC conference id" in err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_release_recording_refuses_a_path_shaped_conference_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reviewer's probe: a hand-typed conference id
    shaped like a path-traversal payload must never reach `DELETE`."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch, conference_id="618/../999")
    transport = _FakeRecordingTransport(
        {}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    err = capsys.readouterr().err
    assert "not a valid FCC conference id" in err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_release_recording_returns_1_when_no_conference_id_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Closes the untested branch of `cli.py`'s
    `{event_id: conference_id} if conference_id else {}` conditional
    expression, invisible to `coverage --branch` as a branch (Important
    1) -- an absent `CONVENER_FCC_CONFERENCE_ID` must refuse cleanly, not
    silently resolve to whatever `conference_ids` happened to hold
    before."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.delenv("CONVENER_FCC_CONFERENCE_ID", raising=False)
    transport = _FakeRecordingTransport(
        {}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert "mrg-042" in capsys.readouterr().err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_release_recording_deletes_the_conference_named_by_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proves `CONVENER_FCC_CONFERENCE_ID` genuinely determines which
    conference is released -- a different, non-hardcoded id, registered
    under its own path in the fake, is the one that gets deleted."""
    other_id = "777777"
    other_path = f"/conferences/{other_id}"
    other_video_url = "https://cdn.example.org/rec/777777.video.mp4"
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch, conference_id=other_id)
    transport = _FakeRecordingTransport(
        {
            other_path: [
                {
                    "recording_url": "https://cdn.example.org/rec/777777",
                    "file_size": 900_000_000,
                    "is_recorded": True,
                    "deleted": False,
                },
                _recording_payload(available=False),
            ]
        },
        head_responses={other_video_url: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 0
    assert transport.delete_calls == [other_path]
    assert transport.get_calls == [other_path, other_path]


def test_release_recording_deletes_once_both_traces_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]},
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 0
    assert transport.delete_calls == [_PATH]
    assert "retrieved, verified, and released" in capsys.readouterr().out


def test_release_recording_reports_when_delete_recording_itself_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]},
        head_responses={_VIDEO_URL: _video_headers()},
        delete_error=FCCRequestError("DELETE /conferences/618515381 returned HTTP 500"),
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert transport.delete_calls == [_PATH]
    # No post-delete confirmation is attempted once the deletion itself
    # failed: only the one pre-delete read happened.
    assert transport.get_calls == [_PATH]
    assert "500" in capsys.readouterr().err


def test_release_recording_alerts_when_space_stays_occupied_after_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An alert, not silence, when the quota is still
    occupied after deletion -- checked *after*, since a saturated quota
    breaks the *next* session's recording."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload()]},  # still available
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert transport.delete_calls == [_PATH]
    err = capsys.readouterr().err
    assert "occupied" in err
    assert "::error::" in err


def test_release_recording_reports_when_the_post_delete_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {
            _PATH: [
                _recording_payload(),
                FCCRequestError("GET /conferences/618515381 failed: timeout"),
            ]
        },
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert transport.delete_calls == [_PATH]
    err = capsys.readouterr().err
    assert "deleted" in err
    assert "could not be confirmed" in err


# ------------------------------------------------------------------ #
# discard_recording(): the other route, for a
# recording that must never be retrieved (the discussion segment; a talk
# whose publication consent was withheld). Gated on an explicit typed
# operator confirmation, never on the retrieval traces -- every test
# below that expects a refusal asserts directly on `transport.delete_calls`
# and (where relevant) `transport.get_calls`, never only on the return
# code.
# ------------------------------------------------------------------ #


def test_discard_confirmation_names_the_action_and_the_event() -> None:
    from convener_ops.cli import _discard_confirmation

    assert _discard_confirmation("mrg-042") == "discard mrg-042"


def test_discard_recording_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)

    assert discard_recording() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_discard_recording_with_an_invalid_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "../escape")

    assert discard_recording() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_discard_recording_refuses_a_blank_confirmation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `CONVENER_REPO_ROOT` is set up at all -- the confirmation is checked
    before any data file is even opened, so a blank confirmation refuses
    cleanly with no other setup required."""
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("CONFIRM_DISCARD", raising=False)

    assert discard_recording() == 1
    err = capsys.readouterr().err
    assert "CONFIRM_DISCARD" in err
    assert "discard mrg-042" in err


def test_discard_recording_refuses_a_mismatched_confirmation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONFIRM_DISCARD", "yes please")

    assert discard_recording() == 1
    assert "CONFIRM_DISCARD" in capsys.readouterr().err


def test_discard_recording_refuses_a_confirmation_typed_for_another_event(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A copy-pasted confirmation from a different event's run must not
    silently discard the wrong one."""
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-999")

    assert discard_recording() == 1
    assert "CONFIRM_DISCARD" in capsys.readouterr().err


def test_discard_recording_with_an_unknown_event_id_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-999")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-999")

    assert discard_recording() == 1
    assert "mrg-999" in capsys.readouterr().err


def test_discard_recording_reports_a_malformed_speakers_file_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "speakers.yml").write_text("key: [unclosed\n", encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")

    assert discard_recording() == 1
    assert "invalid YAML" in capsys.readouterr().out


def test_discard_recording_without_a_configured_account_is_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert discard_recording() == 0
    assert "nothing to discard" in capsys.readouterr().out


def test_discard_recording_is_a_noop_when_nothing_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport({_PATH: [_recording_payload(available=False)]})
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 0
    assert "nothing to discard" in capsys.readouterr().out
    assert transport.delete_calls == []


def test_discard_recording_refuses_a_non_numeric_conference_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same probe `release_recording` was tested against: a hand-typed
    conference id must be refused before any transport call, on this route
    too."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch, conference_id="THIS-IS-THE-WRONG-CONFERENCE")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport({_PATH: [_recording_payload()]})
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    err = capsys.readouterr().err
    assert "not a valid FCC conference id" in err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_discard_recording_returns_1_when_no_conference_id_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Closes the branch of discard_recording's own `if conference_id: ...
    else: ...` resolution -- written as a statement, not the
    ternary a review found invisible to `coverage --branch`, so this
    branch is not merely closed in substance but actually visible to the
    coverage figure)."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    monkeypatch.delenv("CONVENER_FCC_CONFERENCE_ID", raising=False)
    transport = _FakeRecordingTransport({})
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert "mrg-042" in capsys.readouterr().err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_discard_recording_ignores_the_retrieval_tick_and_still_needs_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The second constraint on discarding, behaviourally: a ticked
    `RETRIEVED_TICK` must not let a missing or wrong confirmation through."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", retrieved=True)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.delenv("CONFIRM_DISCARD", raising=False)
    transport = _FakeRecordingTransport({_PATH: [_recording_payload()]})
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert transport.delete_calls == []


def test_discard_recording_deletes_once_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No retrieval tick at all -- the ordinary shape for the discussion
    segment or a consent-withheld talk -- and no converted video either;
    the typed confirmation alone is enough."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", retrieved=False)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]}
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 0
    assert transport.delete_calls == [_PATH]
    out = capsys.readouterr().out
    assert "discarded, never retrieved" in out


def test_discard_recording_warns_but_still_deletes_when_already_converted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If the converted video already answers -- someone clicked Download
    on a recording that should never have been converted -- discarding
    still proceeds (declining would only leave the quota occupied for a
    leak that already happened) but a warning names it."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]},
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 0
    assert transport.delete_calls == [_PATH]
    err = capsys.readouterr().err
    assert "::warning::" in err
    assert "already reachable" in err


def test_discard_recording_does_not_warn_when_never_converted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]}
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 0
    assert "::warning::" not in capsys.readouterr().err


def test_discard_recording_reports_when_delete_recording_itself_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]},
        delete_error=FCCRequestError("DELETE /conferences/618515381 returned HTTP 500"),
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert transport.delete_calls == [_PATH]
    assert transport.get_calls == [_PATH]
    assert "500" in capsys.readouterr().err


def test_discard_recording_alerts_when_space_stays_occupied_after_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload()]}
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert transport.delete_calls == [_PATH]
    err = capsys.readouterr().err
    assert "occupied" in err
    assert "::error::" in err


def test_discard_recording_reports_when_the_post_delete_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {
            _PATH: [
                _recording_payload(),
                FCCRequestError("GET /conferences/618515381 failed: timeout"),
            ]
        }
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert transport.delete_calls == [_PATH]
    err = capsys.readouterr().err
    assert "discarded" in err
    assert "could not be confirmed" in err


def test_discard_recording_refuses_a_self_consistent_typo_into_a_nonexistent_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The residual risk: an operator who fat-fingers the same
    wrong event id into both `event_id` and `confirm_discard` produces a
    self-consistent pair that sails past the confirmation check alone --
    but `find_speaker` still refuses it, because the typo does not name a
    real event. This is the half of "narrow it where it is cheap" that
    costs nothing extra: `find_speaker` is already called, unconditionally,
    before any platform is even constructed.

    `CONVENER_FCC_CONFERENCE_ID` used to be
    left unset here, so `conference_ids` resolved to `{}` and
    `PlatformFCC._conference_id` raised its *own* `EventNotFoundError` for
    'mrg-999' the moment `platform.get_recording` ran -- the identical
    message shape, from a different guard entirely. Removing the
    `find_speaker` call this test claims to pin left every assertion
    green: the same exception type, the same event id in the text, and
    `transport.get_calls == []` because the redundant failure happens
    inside `_conference_id`, before any transport call. Setting a
    validly-shaped `CONVENER_FCC_CONFERENCE_ID` for this exact (wrong) event id
    makes `_conference_id('mrg-999')` resolve cleanly, so the only thing
    left that can refuse the run at all is `find_speaker`'s own guard --
    removing it now lets the function reach `transport.get_json` against
    an empty `_FakeRecordingTransport`, which raises `AssertionError`
    instead of returning 1, failing this test loudly rather than quietly
    passing for the wrong reason."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-999")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-999")
    # Carried item 1: a validly-shaped conference id for the *wrong* event
    # id, so `PlatformFCC._conference_id` cannot coincidentally refuse this
    # run for a reason that has nothing to do with `find_speaker`.
    monkeypatch.setenv("CONVENER_FCC_CONFERENCE_ID", _CONFERENCE_ID)
    transport = _FakeRecordingTransport({})
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert "mrg-999" in capsys.readouterr().err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def _delete_recording_call_sites(package_dir: Path) -> list[str]:
    """Every `.py` file under `package_dir`, at any depth, that calls
    `delete_recording(` for real (excluding `def delete_recording(`
    declarations). `rglob`, not `glob`:
    `convener_ops` is flat today, but a non-recursive glob would silently stop
    looking the day it grows a subpackage -- reproduced against a
    synthetic one below."""
    return [
        str(path.relative_to(package_dir))
        for path in sorted(package_dir.rglob("*.py"))
        for _match in re.finditer(
            r"(?<!def )\bdelete_recording\(", path.read_text(encoding="utf-8")
        )
    ]


def test_delete_recording_has_exactly_two_call_sites_both_in_cli() -> None:
    """The rule, pinned rather than left to a docstring, covering
    both routes: the only calls to
    `Platform.delete_recording` anywhere in `convener_ops` are inside
    `release_recording` and `discard_recording`, both in `cli.py`. A third
    call site anywhere -- a shortcut some future change adds -- would
    bypass whichever guard exists to provide; this test reads every
    module's own source, at any depth, and refuses to let a third one
    exist silently, the same "read the module's own source" idiom
    `test_notify.py::test_the_notification_module_holds_no_transport`
    already uses in this codebase.

    Brittle in one direction only, and deliberately left that way:
    a docstring that happens to contain the literal
    text `delete_recording(` (with the open paren) would also match here
    and fail this test even though it calls nothing. That is the safe
    direction to be brittle in -- it can only ever demand a closer look,
    never hide a real call site."""
    import convener_ops

    package_dir = Path(convener_ops.__file__).parent
    assert _delete_recording_call_sites(package_dir) == ["cli.py", "cli.py"]


def test_release_recordings_delete_call_is_gated_on_missing_retrieval_evidence() -> (
    None
):
    """Structural, not merely behavioural: `release_recording`'s own call
    to `delete_recording` must textually follow the point where
    `missing_retrieval_evidence` is checked, so the gate cannot be
    reordered away from the call it exists to protect without this test
    noticing."""
    import inspect

    from convener_ops.cli import release_recording

    source = inspect.getsource(release_recording)
    evidence_at = source.index("missing_retrieval_evidence(")
    delete_at = source.index("platform.delete_recording(")
    assert evidence_at < delete_at


def test_discard_recordings_delete_call_is_gated_on_the_confirmation() -> None:
    """The same structural pin, for the other route: `discard_recording`'s
    call to `delete_recording` must textually follow the confirmation
    comparison, not merely happen to pass a test today."""
    import inspect

    from convener_ops.cli import discard_recording

    source = inspect.getsource(discard_recording)
    confirm_at = source.index("confirm_discard != expected")
    delete_at = source.index("platform.delete_recording(")
    assert confirm_at < delete_at


def _code_body_excluding_docstring(func: object) -> str:
    """`inspect.getsource(func)` with the leading docstring stripped --
    the two structural tests below search the *body* for a name, and both
    functions' own docstrings name, in prose, exactly what must be absent
    from the body, so a plain substring search over the whole source would
    trip on its own explanation."""
    import inspect

    source = inspect.getsource(func)  # type: ignore[arg-type]
    return source.split('"""', 2)[-1]


def test_discard_recording_never_reads_the_retrieval_tick_or_evidence() -> None:
    """The second constraint on discarding, pinned structurally: a ticked
    `RETRIEVED_TICK` must never be able to substitute for the typed
    confirmation, because `discard_recording`'s own code body never
    mentions `runbook_progress`, `RETRIEVED_TICK`, or
    `missing_retrieval_evidence` at all -- as a name, an attribute, or a
    string literal such as `record.get("runbook_progress")`."""
    from convener_ops.cli import discard_recording

    body = _code_body_excluding_docstring(discard_recording)
    assert "missing_retrieval_evidence" not in body
    assert "RETRIEVED_TICK" not in body
    assert "runbook_progress" not in body


def test_release_recording_never_reads_the_discard_confirmation() -> None:
    """The mirror of the test above: `CONFIRM_DISCARD` and
    `_discard_confirmation` must never appear in `release_recording`'s own
    code body, so a typed discard confirmation can never substitute for
    the two retrieval traces it actually requires."""
    from convener_ops.cli import release_recording

    body = _code_body_excluding_docstring(release_recording)
    assert "CONFIRM_DISCARD" not in body
    assert "_discard_confirmation" not in body


def test_the_call_site_scan_is_recursive(tmp_path: Path) -> None:
    """Reproduces exactly what a review found: a
    non-recursive `glob("*.py")` misses a call hidden one directory down.
    `convener_ops` is flat today (the test above proves it), so this is tested
    against a synthetic package instead of waiting for a real subpackage
    to exist."""
    (tmp_path / "cli.py").write_text("def f():\n    pass\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "evil.py").write_text(
        "def sneaky(platform, event_id):\n    platform.delete_recording(event_id)\n",
        encoding="utf-8",
    )

    assert _delete_recording_call_sites(tmp_path) == [str(Path("sub") / "evil.py")]
