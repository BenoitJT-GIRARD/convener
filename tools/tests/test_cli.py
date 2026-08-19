from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, tzinfo
from pathlib import Path

import pytest
import yaml
from conftest import board_member, config, speaker

from convener_ops.cli import _load, handle_proposal, sweep, validate


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
