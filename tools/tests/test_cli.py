from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import ClassVar

import pytest
import yaml
from conftest import board_member, config, speaker

from convener_ops import eventkeys
from convener_ops.cli import (
    UNSENT_CONFIRMATION,
    _load,
    handle_proposal,
    handle_registration,
    public_data,
    resend_confirmation,
    resolve_registration_secret,
    sweep,
    validate,
)
from convener_ops.registration import load_registration_file, matching_code, to_registration


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
# handle_registration()'s confirmation step (task 7), and
# resend_confirmation(): the manual resend spec S:9 asks for.
#
# Every test below that expects the confirmation to be *unsent* checks the
# file it was left in, never stdout -- `_assert_no_leak` (above) is applied
# to every one of them, now also covering the matching code, which the
# original registration tests could not leak because nothing computed one.
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

    assert handle_registration() == 0

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

    assert handle_registration() == 0

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
    assert handle_registration() == 0

    monkeypatch.setenv(
        "REGISTRATION_PAYLOAD",
        _registration_payload("mrg-042", public_pem, institution="Somewhere Else"),
    )
    assert handle_registration() == 0

    _assert_no_leak(capsys)
    unsent = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
    assert "institution" in unsent
    assert "This confirms an update" in unsent
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

    assert handle_registration() == 0

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

    assert handle_registration() == 0

    out = _assert_no_leak(capsys)
    assert "no speaker record matches event mrg-042" in out

    unsent = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
    assert "ada@example.org" in unsent


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

    assert handle_registration() == 0

    out = _assert_no_leak(capsys)
    assert "confirmation for event mrg-042 sent" in out
    assert not (tmp_path / UNSENT_CONFIRMATION).exists()
    assert len(_RecordingSmtpClient.sent) == 1


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
    assert handle_registration() == 0
    original = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
    (tmp_path / UNSENT_CONFIRMATION).unlink()

    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    assert resend_confirmation() == 0

    resent = (tmp_path / UNSENT_CONFIRMATION).read_text(encoding="utf-8")
    code = matching_code("mrg-042", "ada@example.org", "shh")
    assert code is not None
    assert code in original
    assert code in resent
    assert original == resent

    _assert_no_leak(capsys)


def test_resend_confirmation_does_not_claim_an_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A resend repeats the current, stored registration -- even one that
    is itself the result of an earlier update must not be described as
    changing again on every resend."""
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
    (tmp_path / UNSENT_CONFIRMATION).unlink()

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
    (tmp_path / UNSENT_CONFIRMATION).unlink()

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
