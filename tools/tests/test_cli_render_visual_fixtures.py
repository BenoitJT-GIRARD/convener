"""`convener-render-visual-fixtures` -- the one disk-writing seam between
`visual.render_announcement`/`formats.FORMATS` (both pure) and task 5's own
pinned Node/Puppeteer render step, which reads what this command writes
rather than re-deriving a page's own markup a second time in JavaScript.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from convener_ops.cli import render_visual_fixtures
from convener_ops.formats import FORMATS
from convener_ops.visual import FIXTURE_ANNOUNCEMENT


def _run(out: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["convener-render-visual-fixtures", str(out)])
    return render_visual_fixtures()


def test_writes_one_html_page_per_named_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "fixtures"
    exit_code = _run(out, monkeypatch)
    assert exit_code == 0
    for fmt in FORMATS:
        html = (out / f"{fmt.name}.html").read_text(encoding="utf-8")
        assert "<!doctype html>" in html
        # The fixture's own identity actually reached the page -- proof
        # this called render_announcement with FIXTURE_ANNOUNCEMENT, not a
        # blank or a different Announcement.
        assert FIXTURE_ANNOUNCEMENT.speaker_name in html
        assert FIXTURE_ANNOUNCEMENT.title in html


def test_manifest_names_are_derived_from_formats_not_hand_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "fixtures"
    _run(out, monkeypatch)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    expected = [
        {
            "name": fmt.name,
            "width": fmt.width,
            "height": fmt.height,
            "file": f"{fmt.name}.html",
        }
        for fmt in FORMATS
    ]
    assert manifest == expected


def test_fonts_are_copied_alongside_so_a_relative_url_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "fixtures"
    _run(out, monkeypatch)
    fonts = out / "fonts"
    assert fonts.is_dir()
    woff2_files = list(fonts.glob("*.woff2"))
    assert woff2_files, (
        "no font file was copied -- a relative url('fonts/...') would 404"
    )


def test_a_stale_fonts_directory_from_an_earlier_run_does_not_survive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second run must leave `fonts/` exactly as the repository's own
    `fonts/` stands today, never a merge of an old copy and a new one --
    the same "regenerate the whole target, never accumulate into it"
    discipline `register()` already applies to the decision register."""
    out = tmp_path / "fixtures"
    out.mkdir()
    stale = out / "fonts"
    stale.mkdir()
    (stale / "leftover-from-a-previous-run.woff2").write_bytes(b"not a real font")

    _run(out, monkeypatch)

    assert not (out / "fonts" / "leftover-from-a-previous-run.woff2").exists()


def test_wrong_argument_count_fails_with_a_usage_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["convener-render-visual-fixtures"])
    exit_code = render_visual_fixtures()
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "usage" in err.lower()
    assert not (tmp_path / "manifest.json").exists()
