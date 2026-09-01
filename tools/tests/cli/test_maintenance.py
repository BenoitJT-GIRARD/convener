"""`convener-sweep` (`convener_ops.cli.maintenance`): the scheduled job that
moves a record on when its own date has passed.

It rewrites the instance's own records in place, so what it leaves behind
is checked here as well as what it says: a sweep that reports a change and
writes none, or writes one and loses the file's header, both exit 0.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import config, speaker
from helpers.command_line import (
    write_data,
)

from convener_ops.cli.maintenance import sweep


def test_sweep_reports_nothing_to_sweep_when_no_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_data(tmp_path, [speaker(status="lead")], config())
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
    write_data(tmp_path, [row], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert sweep() == 0
    out = capsys.readouterr().out
    assert "spk-001: scheduled -> delivered" in out

    text = (tmp_path / "instance" / "data" / "speakers.yml").read_text(encoding="utf-8")
    assert text.startswith("# Speakers (unified schema v6")
    assert "status: delivered" in text


def test_sweep_reports_load_errors_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    (tmp_path / "instance" / "data").mkdir(parents=True)

    assert sweep() == 1
    assert "file missing" in capsys.readouterr().out
