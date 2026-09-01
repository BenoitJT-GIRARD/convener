"""`convener-validate` (`convener_ops.cli.governance`): the command that
reads this instance's records and says whether they hold together.

The return code is the whole of what continuous integration reads, so
every test here asserts on it as well as on what was printed -- a
validator that reports a fault and exits 0 is a gate that is not one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from conftest import board_member, config, speaker
from helpers.command_line import (
    write_data,
)

from convener_ops.cli.governance import validate


def test_validate_reports_ok_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_data(tmp_path, [speaker()], config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert validate() == 0
    assert "Data OK - 1 speakers, config=ok" in capsys.readouterr().out


def test_validate_reports_errors_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_data(tmp_path, [speaker(status="bogus-status")], config())
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
    write_data(tmp_path, [speaker()], cfg)
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
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True)
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
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True)
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
    write_data(tmp_path, [speaker(assigned_to="ada")], cfg)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert validate() == 1
    out = capsys.readouterr().out
    assert "Data validation FAILED" in out
    assert "assigned_to is not a board member ('ada')" in out
