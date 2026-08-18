from __future__ import annotations

from pathlib import Path

import pytest

from convener_ops.paths import repo_root


def test_repo_root_honours_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    assert repo_root() == tmp_path.resolve()


def test_repo_root_walks_upward_to_find_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CONVENER_REPO_ROOT", raising=False)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "config.yml").write_text("season: 2026\n", encoding="utf-8")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)

    assert repo_root(nested) == tmp_path.resolve()


def test_repo_root_raises_when_no_marker_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CONVENER_REPO_ROOT", raising=False)
    nested = tmp_path / "x" / "y"
    nested.mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        repo_root(nested)
