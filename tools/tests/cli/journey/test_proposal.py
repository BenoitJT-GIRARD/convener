"""`convener-handle-proposal` (`convener_ops.cli.journey.proposal`): the step
`.github/workflows/proposal.yml` runs for one incoming talk proposal.

A proposal arrives signed, from a form nobody here controls, and lands as
a row in this instance's own records. So the tests are about what the
command refuses as much as what it writes: an unsigned body, a body that
is not JSON, a shape the form could produce and the parser has never seen,
and the same person submitting twice.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, tzinfo
from pathlib import Path

import pytest
import yaml
from conftest import config, speaker
from helpers.command_line import (
    write_data,
)

from convener_ops.cli.journey.proposal import handle_proposal


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
    write_data(tmp_path, [speaker(id="spk-001")], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    payload = json.dumps({"fields": [{"label": "Name", "value": "Grace Hopper"}]})
    monkeypatch.setenv("PROPOSAL_PAYLOAD", payload)
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 0
    out = capsys.readouterr().out
    assert "created spk-002 from form proposal" in out

    text = (tmp_path / "instance" / "data" / "speakers.yml").read_text(encoding="utf-8")
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
    write_data(tmp_path, [], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr("convener_ops.cli.journey.proposal.datetime", _FrozenClock)
    payload = json.dumps({"fields": [{"label": "Name", "value": "Grace Hopper"}]})
    monkeypatch.setenv("PROPOSAL_PAYLOAD", payload)
    monkeypatch.delenv("PROPOSAL_SIGNATURE", raising=False)
    monkeypatch.delenv("TALLY_WEBHOOK_SECRET", raising=False)

    assert handle_proposal() == 0
    capsys.readouterr()

    written = yaml.safe_load(
        (tmp_path / "instance" / "data" / "speakers.yml").read_text("utf-8")
    )
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
    # -- which is what the workflow now passes through untouched (cli/
    # reads payload["data"]["fields"], not the legacy payload["fields"]
    # fallback every other test here exercises), and the signature is the
    # real base64(HMAC-SHA256(secret, payload)) computed over that exact
    # string. Reverting candidate-form.yml to toJSON(...), or adding a
    # .strip() to the payload before verifying, would break this while every
    # other handle_proposal test here stayed green.
    write_data(tmp_path, [speaker(id="spk-001")], config())
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

    text = (tmp_path / "instance" / "data" / "speakers.yml").read_text(encoding="utf-8")
    assert "spk-002" in text
    assert "Grace Hopper" in text


def test_handle_proposal_skips_a_duplicate_lead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_data(
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
    write_data(tmp_path, [speaker(id="spk-001")], config())
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
    (tmp_path / "instance" / "data").mkdir(parents=True)
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
    write_data(tmp_path, [], config())
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
    write_data(tmp_path, [speaker(id="spk-001")], config())
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

    written = yaml.safe_load(
        (tmp_path / "instance" / "data" / "speakers.yml").read_text("utf-8")
    )
    assert written[-1]["gender"] == "NB"


def test_handle_proposal_never_writes_a_stringified_list_for_an_unresolvable_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An id absent from `options` (a malformed or truncated payload) must
    # not resurrect the original bug: "['unknown-id']" landing in the
    # record instead of the field being recognised as unmapped and falling
    # back to "undisclosed" like any other unrecognised answer.
    write_data(tmp_path, [speaker(id="spk-001")], config())
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

    text = (tmp_path / "instance" / "data" / "speakers.yml").read_text(encoding="utf-8")
    assert "['unknown-id']" not in text
    written = yaml.safe_load(text)
    assert written[-1]["gender"] == "undisclosed"
