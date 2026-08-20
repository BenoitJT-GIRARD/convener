from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml
from conftest import board_member, config, speaker

from convener_ops import eventkeys
from convener_ops.cli import (
    UNMATCHED_ATTENDANCE,
    UNSENT_CONFIRMATION,
    _load,
    discard_recording,
    handle_proposal,
    handle_registration,
    match_attendance,
    public_data,
    release_recording,
    resend_confirmation,
    resolve_registration_secret,
    send_confirmation,
    sweep,
    validate,
)
from convener_ops.platform import AttendanceRow
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


def _write_data(tmp_path: Path, speakers: object, cfg: object) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "speakers.yml").write_text(yaml.safe_dump(speakers), encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(cfg), encoding="utf-8")


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
    assert text.startswith("# Speakers (unified schema v3")
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
    # R-9: a DROPDOWN answer's raw `value` is a list of option ids, not
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
# ones the task exists for: no name and no address may appear anywhere the
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
#: prints, exactly what the task asks for.
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


def test_handle_registration_writes_the_record_and_prints_no_name_or_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The test the task exists for: a job that decrypts a registration
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
# handle_registration()'s two-step confirmation flow (task 7 review round
# 1's Important 2: sending was moved out of the push-retry loop, into its
# own step -- `send_confirmation`, `convener-send-confirmation` -- that
# `.github/workflows/registration.yml` now runs only `if: success()`), and
# resend_confirmation(): the manual resend spec S:9 asks for.
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
    and compose/deliver) -- exactly the split Important 2 of the task 7
    review asked for, so `handle_registration() == 0` alone is no longer
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


def test_handle_registration_leaves_an_unsent_confirmation_with_no_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
    assert UNSENT_CONFIRMATION in out

    unsent = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
    assert "ada@example.org" in unsent
    assert "https://meet.example.org/permanent-room" in unsent
    assert "On analytical engines" in unsent


def test_handle_registration_confirmation_carries_the_code_when_salted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The property task 7 exists for: the matching code reaches the
    message, and never reaches stdout -- only the file does."""
    private_pem, public_pem = _publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    _clear_transport_env(monkeypatch)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "shh")

    _handle_and_send(tmp_path, monkeypatch)

    code = matching_code("mrg-042", "ada@example.org", "shh")
    assert code is not None

    out = capsys.readouterr()
    combined = out.out + out.err
    assert code not in combined, "the matching code leaked into stdout/stderr"

    unsent = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
    assert code in unsent


def test_handle_registration_confirmation_names_what_changed_on_an_update(
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
    _handle_and_send(tmp_path, monkeypatch)

    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD",
        _registration_payload("mrg-042", public_pem, institution="Somewhere Else"),
    )
    _handle_and_send(tmp_path, monkeypatch)

    _assert_no_leak(capsys)
    unsent = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
    # The whole sentence, not a bare "institution" substring (review round
    # 1, Important 6): that word also appears in the data-protection
    # paragraph of every message ever composed, so a check for it alone
    # would still pass a mutant naming the wrong changed field.
    assert (
        "This confirms an update to an earlier registration for this "
        "event: we changed the institution."
    ) in unsent
    # Named, never quoted (R-9): neither the old nor the new value appears.
    assert "Analytical Engines Institute" not in unsent
    assert "Somewhere Else" not in unsent


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
    _clear_transport_env(monkeypatch)

    _handle_and_send(tmp_path, monkeypatch)

    unsent = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
    assert "This confirms an update" not in unsent


def test_handle_registration_confirmation_degrades_with_no_speaker_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `data/speakers.yml` at all -- the state every registration test
    before this one already ran in. The registration must still be
    recorded and a confirmation still composed, only without a room link."""
    private_pem, public_pem = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    _clear_transport_env(monkeypatch)

    _handle_and_send(tmp_path, monkeypatch)

    out = _assert_no_leak(capsys)
    assert "no speaker record matches event mrg-042" in out

    unsent = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
    assert "ada@example.org" in unsent


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
    assert not (tmp_path / UNSENT_CONFIRMATION).exists()

    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    file = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert len(file.entries) == 1


class _RecordingSmtpClient:
    """A fake `smtplib.SMTP`, substituted so `handle_registration` can
    exercise a genuine "sent" outcome without opening a socket."""

    sent: ClassVar[list[object]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port

    def starttls(self) -> None:
        pass

    def login(self, user: str, password: str) -> None:
        pass

    def send_message(self, message: object) -> None:
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
    assert not (tmp_path / UNSENT_CONFIRMATION).exists()
    assert len(_RecordingSmtpClient.sent) == 1


def test_send_confirmation_unlinks_a_stale_unsent_file_once_it_sends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review round 1, Important 1: a file an earlier, failed attempt left
    behind must not survive a later, successful send -- an
    `if: always()` upload step would otherwise preserve a stale address
    and code as though the message had not gone out."""
    private_pem, public_pem = _publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    (tmp_path / UNSENT_CONFIRMATION).write_text(
        "a stale, previous attempt", encoding="utf-8"
    )

    monkeypatch.setenv("CONVENER_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("CONVENER_SMTP_PORT", "587")
    monkeypatch.setenv("CONVENER_SMTP_USER", "convener-registration@example.org")
    monkeypatch.setenv("CONVENER_SMTP_PASSWORD", "shh")
    monkeypatch.setenv("CONVENER_SMTP_FROM", "convener-registration@example.org")
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)
    monkeypatch.setenv("CHANGED_FIELDS", "")
    _RecordingSmtpClient.sent = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _RecordingSmtpClient)

    assert send_confirmation() == 0

    _assert_no_leak(capsys)
    assert not (tmp_path / UNSENT_CONFIRMATION).exists()


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


# --- resend_confirmation() -------------------------------------------- #


def test_resend_confirmation_reproduces_the_original_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The property S:9's manual resend depends on directly: it must
    reproduce the *same* code the original confirmation carried, or the
    first message becomes a lie about which code is current."""
    private_pem, public_pem = _publish_event_key(tmp_path)
    _write_event(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    _clear_transport_env(monkeypatch)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "shh")

    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD", _registration_payload("mrg-042", public_pem)
    )
    _handle_and_send(tmp_path, monkeypatch)
    original = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
    (tmp_path / UNSENT_CONFIRMATION).unlink()

    code = matching_code("mrg-042", "ada@example.org", "shh")
    assert code is not None
    original_captured = capsys.readouterr()
    assert code not in (original_captured.out + original_captured.err), (
        "the matching code leaked into stdout/stderr on the original send"
    )

    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    assert resend_confirmation() == 0

    resent = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
    assert code in original
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

    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    assert resend_confirmation() == 0

    resent = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
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
    monkeypatch.delenv("REGISTRATION_EMAIL", raising=False)
    assert resend_confirmation() == 1
    assert "no registration e-mail" in capsys.readouterr().err


def test_resend_confirmation_without_a_configured_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert resend_confirmation() == 1
    assert "no private key configured for event mrg-042" in capsys.readouterr().err


def test_resend_confirmation_with_nothing_recorded_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
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
    monkeypatch.setenv("REGISTRATION_EMAIL", "grace@example.org")

    assert resend_confirmation() == 1
    assert "no registration found for event mrg-042" in capsys.readouterr().err
    assert not (tmp_path / UNSENT_CONFIRMATION).exists()


def test_resend_confirmation_rejects_a_malformed_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path)
    events_dir = tmp_path / "data" / "events" / "mrg-042"
    events_dir.mkdir(parents=True)
    (events_dir / "registrations.enc").write_text("not json at all", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert resend_confirmation() == 1
    assert "registrations.enc" in capsys.readouterr().err


# ------------------------------------------------------------------ #
# match_attendance(): task 8 -- join the platform's attendance export
# against this event's registrations (spec S:5's cascade) and report the
# result. Like handle_registration above, this job holds decrypted
# registrations in memory; these tests check the same property task 6's
# tests check there -- no name and no address may appear anywhere this
# job prints, on any path -- plus the one new thing task 8 adds: the
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


def test_match_attendance_names_tied_candidates_in_the_host_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tie the cascade refused to guess between is not left as a bare
    "unmatched" in the host's own file -- both candidates' addresses are
    named, so the host is resolving a specific ambiguity."""
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
    assert "marie.m1@example.org" in host_list
    assert "marie.m2@example.org" in host_list
    assert host_list.endswith("\n")
    assert not host_list.endswith("\n\n")


def test_match_attendance_prints_only_counts_and_writes_the_host_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ada joins by the link with her own address (matched, level 2 --
    no salt configured); Grace's connection carries an address that
    matches nobody (unmatched); a third connection has no address at all
    (unreachable). Neither Ada's nor Grace's name or address may appear
    in anything this job prints -- only in the host's file, which is the
    one place they are allowed to, because that is the whole point of
    handing it to a human."""
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
    for leaked in ("ada", "lovelace", "grace", "hopper", "555 0100"):
        assert leaked not in printed, f"{leaked!r} leaked into job output"

    host_list = (tmp_path / UNMATCHED_ATTENDANCE).read_text(encoding="utf-8")
    assert "Grace Hopper" in host_list
    assert "grace@example.org" in host_list
    assert "+1 555 0100" in host_list
    assert "Ada" not in host_list
    assert "ada@example.org" not in host_list


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
    already give a stray undecryptable entry."""
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
    assert "1 matched, 0 unmatched, 0 unreachable" in capsys.readouterr().out


# ------------------------------------------------------------------ #
# release_recording(): task 10 -- retrieve, verify the retrieval, then
# delete. R-7's ruling: this ordering gets a test that fails if deletion
# is reachable without a verified retrieval, not a paragraph. Every test
# below that expects no deletion asserts directly on
# `transport.delete_calls`, never only on the return code -- a change
# that returns 1 but deletes anyway would still fail one of these.
#
# `_FakeRecordingTransport` is keyed by the exact path or URL it is asked
# for, never a positionless queue (fix round 1, Important 1): a caller
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
    converted recording, per phase-4-prep-notes.md's 2026-08-19
    measurement: `video/mp4`, `Accept-Ranges: bytes`."""
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
    cleared: bool = False,
) -> None:
    """`retrieved=True` ticks `RETRIEVED_TICK` on `runbook_progress` --
    trace 1, since fix round 1. Never sets `youtube_url`: that field is a
    publication signal, deliberately irrelevant to this guard now (see
    Important 4).

    `cleared=True` (fix round 3) sets `publication.consent: "granted"`
    and `publication.outcome: "published"` -- the two conditions
    `public_data.recording_withheld` requires together before
    `release_recording` will even attempt the two-trace check. Defaults
    to `False` (the ordinary state for a fresh, unarchived talk, and the
    only state `discard_recording`'s own tests need, since that function
    never reads `publication` at all)."""
    runbook_progress = {RETRIEVED_TICK: True} if retrieved else {}
    publication = (
        {
            "consent": "granted",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "published",
        }
        if cleared
        else {
            "consent": "",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "",
        }
    )
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


def test_release_recording_refuses_when_publication_is_not_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fix round 3: enforced, not only documented. A fresh talk (the
    default, unfixtured `publication` block -- consent and outcome both
    blank, the ordinary state before `finalize-archive` has ever run) is
    refused before any platform interaction at all -- not the two-trace
    check that ran here before, a different, earlier one."""
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
    assert "publication is not cleared" in err
    assert "discard_recording" in err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_release_recording_refuses_when_consent_is_refused_even_with_a_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exact Important 4 scenario, now expected to refuse rather than
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
    assert "publication is not cleared" in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_refuses_when_consent_is_granted_but_outcome_is_not_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proves both halves of the predicate are required, not only
    consent: a speaker who agreed, on a talk `finalize-archive` has not
    yet run for (the ordinary state right after an event), still
    refuses."""
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
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert "publication is not cleared" in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_without_a_configured_account_is_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-13: no token is the ordinary state. ManualPlatform holds no
    recording storage of its own, so this is a harmless no-op, not a
    failure. `cleared=True` so this test still reaches that branch rather
    than the (new, earlier) publication gate."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", cleared=True)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert release_recording() == 0
    assert "nothing to release" in capsys.readouterr().out


def test_release_recording_is_a_noop_when_nothing_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", cleared=True)
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
    `release_recording` gives a genuinely absent tick. Publication cleared
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
        tmp_path, event_id="mrg-042", retrieved=False, cleared=True
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
    """Important 4, fix round 1: `youtube_url` is a publication signal,
    not a retrieval one, and must not satisfy this guard by itself --
    even when it is set to something plausible. Publication cleared so
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


def test_release_recording_succeeds_once_publication_is_cleared_and_both_traces_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The positive case fix round 3 still has to permit: a talk whose
    publication gate genuinely opened (`consent: granted`,
    `outcome: published`) and whose retrieval is genuinely verified must
    still succeed -- the new gate narrows who may use this route, it does
    not additionally weaken the two traces that already governed it."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
    """Reviewer probe, round 1, Important 3: a 200 with
    `Content-Type: text/html` (a CDN's own error page, or a followed
    redirect to one) must not count as proof of conversion."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
    """The mutation-B guard this task's own brief asks for: a failed
    retrieval must never still delete."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
    """Reviewer probe, round 1, Important 1: the exact value the reviewer
    used (`THIS-IS-THE-WRONG-CONFERENCE`). With `_patch_platform` no
    longer hardcoding `conference_ids`, this reaches `PlatformFCC`'s own
    digit-only validation (Important 2's fix) and is refused before any
    transport call -- never silently deletes whatever the fake happens to
    have registered under a different, hardcoded path."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
    """Reviewer probe, round 1, Important 2: a hand-typed conference id
    shaped like a path-traversal payload must never reach `DELETE`."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
    """Spec Section 9: an alert, not silence, when the quota is still
    occupied after deletion -- checked *after*, since a saturated quota
    breaks the *next* session's recording."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
        tmp_path, event_id="mrg-042", retrieved=True, cleared=True
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
# discard_recording(): task 10 fix round 2 -- the other route, for a
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
    else: ...` resolution (fix round 2 -- written as a statement, not the
    ternary review round 1 found invisible to `coverage --branch`, so this
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
    """The review's own second constraint, behaviourally: a ticked
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
    """The residual the review named: an operator who fat-fingers the same
    wrong event id into both `event_id` and `confirm_discard` produces a
    self-consistent pair that sails past the confirmation check alone --
    but `find_speaker` still refuses it, because the typo does not name a
    real event. This is the half of "narrow it where it is cheap" that
    costs nothing extra: `find_speaker` is already called, unconditionally,
    before any platform is even constructed."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-999")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-999")
    transport = _FakeRecordingTransport({})
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert "mrg-999" in capsys.readouterr().err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def _delete_recording_call_sites(package_dir: Path) -> list[str]:
    """Every `.py` file under `package_dir`, at any depth, that calls
    `delete_recording(` for real (excluding `def delete_recording(`
    declarations). `rglob`, not `glob` (fix round 1, Important 5):
    `convener_ops` is flat today, but a non-recursive glob would silently stop
    looking the day it grows a subpackage -- reproduced against a
    synthetic one below, the same way the review that found this built
    one."""
    return [
        str(path.relative_to(package_dir))
        for path in sorted(package_dir.rglob("*.py"))
        for _match in re.finditer(
            r"(?<!def )\bdelete_recording\(", path.read_text(encoding="utf-8")
        )
    ]


def test_delete_recording_has_exactly_two_call_sites_both_in_cli() -> None:
    """R-7's ruling, pinned rather than left to a docstring, now covering
    both routes fix round 2 added: the only calls to
    `Platform.delete_recording` anywhere in `convener_ops` are inside
    `release_recording` and `discard_recording`, both in `cli.py`. A third
    call site anywhere -- a shortcut some future change adds -- would
    bypass whichever guard exists to provide; this test reads every
    module's own source, at any depth, and refuses to let a third one
    exist silently, the same "read the module's own source" idiom
    `test_notify.py::test_the_notification_module_holds_no_transport`
    already uses in this codebase.

    Brittle in one direction only, and deliberately left that way (fix
    round 1, minor 4): a docstring that happens to contain the literal
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
    """The review's own second constraint, pinned structurally: a ticked
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
    """Reproduces exactly what fix round 1's review found: a
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
