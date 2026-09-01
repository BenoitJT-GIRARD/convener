"""`convener_ops.cli.store`: the one reader every command's YAML goes
through, and the two answers it gives about a file it cannot use.

`load` returns `(value, errors)` rather than raising, because a command is
a workflow step: what an operator reads in the run log is the message, and
a stack trace is what a step prints when nobody wrote one.
"""

from __future__ import annotations

from pathlib import Path

from convener_ops.cli.store import load


def test_load_missing_file_reports_error(tmp_path: Path) -> None:
    value, errors = load(tmp_path / "missing.yml")
    assert value is None
    assert errors == ["missing.yml: file missing"]


def test_load_malformed_yaml_reports_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yml"
    bad.write_text("key: [unclosed\n", encoding="utf-8")

    value, errors = load(bad)

    assert value is None
    assert len(errors) == 1
    assert "invalid YAML" in errors[0]


def test_load_valid_yaml_returns_data_and_no_errors(tmp_path: Path) -> None:
    good = tmp_path / "good.yml"
    good.write_text("season: 2026\n", encoding="utf-8")

    value, errors = load(good)

    assert value == {"season": 2026}
    assert errors == []
