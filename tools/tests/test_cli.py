from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from conftest import config, speaker

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
    assert text.startswith("# Speakers (unified schema v2")
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


def test_handle_proposal_with_an_invalid_signature_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("PROPOSAL_PAYLOAD", '{"fields": []}')
    monkeypatch.setenv("PROPOSAL_SIGNATURE", "deadbeef")
    monkeypatch.setenv("TALLY_WEBHOOK_SECRET", "shh")

    assert handle_proposal() == 1
    assert "invalid signature" in capsys.readouterr().err


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
