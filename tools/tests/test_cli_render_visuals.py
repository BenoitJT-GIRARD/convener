"""`convener-render-visuals` -- the disk-writing seam for *production*
visuals: real, scheduled editions from `data/speakers.yml`, run through the
same public gate every other public artefact in this project already goes
through (`public_data.to_public`), rendered on the same pure
composition. `render_visual_fixtures` always renders the one
fixed, fictional identity a regression check needs; this is its opposite
number, exercised here against real data shapes instead.
"""

from __future__ import annotations

import json
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import speaker

from convener_ops.cli import _scheduled_announcements, render_visuals
from convener_ops.formats import FORMATS
from convener_ops.paths import repo_root
from convener_ops.public_data import to_public
from convener_ops.visual import render_announcement

_REAL_ROOT = repo_root()


#: Read on demand, never while this module loads.
#: Both are paths `config/boundary.yml` hands to the instance, and a
#: derived repository is entitled not to have them until the derivation
#: lays an example's own files there. At module scope the read took this
#: whole module down at collection; from here it fails the tests that
#: actually build a root, and says which file is missing.
@cache
def _real_brand() -> str:
    return (_REAL_ROOT / "data" / "brand.json").read_text(encoding="utf-8")


#: The composition reads the instance's own declaration
#: too, for the wordmark, the strapline and the forum the "what to expect"
#: rows name. Copied from the real repository for the same reason
#: `data/brand.json` above is -- a second, hand-typed identity here would
#: be a second answer to "what does this instance call itself", free to
#: drift from the file every other reader in this project reads.
@cache
def _real_instance() -> str:
    return (_REAL_ROOT / "config" / "instance.json").read_text(encoding="utf-8")


def _scheduled(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": "scheduled",
        "edition_code": "MRG-07",
        "date": "2026-05-14",
        "host_1": "H1",
        "host_2": "H2",
    }
    base.update(overrides)
    return speaker(**base)


def _fake_root(tmp_path: Path, speakers: list[dict[str, Any]]) -> Path:
    """A repository root a test can point `convener_ops.cli.repo_root` at:
    real `data/brand.json` and real `config/instance.json` (both small,
    stable and non-personal -- copied rather than re-typed, the same
    choice `test_visual.py`'s own `ROOT = repo_root()` makes by reading
    them from the real repository directly),
    a placeholder `fonts/` (only the *presence* of a `.woff2` is ever
    checked, never its bytes -- `render_visual_fixtures`'s own tests make
    the identical choice), and the `speakers` given, serialised through
    real `yaml.safe_dump` so a hand-typed `date: 2026-05-14` cannot
    accidentally reach the file unquoted.
    """
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "speakers.yml").write_text(
        yaml.safe_dump(speakers, sort_keys=False), encoding="utf-8"
    )
    (tmp_path / "data" / "brand.json").write_text(_real_brand(), encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "instance.json").write_text(
        _real_instance(), encoding="utf-8"
    )
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "placeholder.woff2").write_bytes(b"not a real font, presence only")
    return tmp_path


def _run(out: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["convener-render-visuals", str(out)])
    return render_visuals()


def _use_fake_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, speakers: list[dict[str, Any]]
) -> Path:
    fake_root = _fake_root(tmp_path, speakers)
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: fake_root)
    return fake_root


# ---------------------------------------------------------------------------
# _scheduled_announcements -- pure, no disk
# ---------------------------------------------------------------------------


def test_only_scheduled_rows_become_announcements() -> None:
    rows = to_public(
        [
            speaker(id="a", status="lead"),
            _scheduled(id="b", edition_code="MRG-01", date="2026-02-02"),
            speaker(
                id="c",
                status="archived",
                edition_code="MRG-02",
                date="2025-01-01",
                host_1="H1",
                host_2="H2",
            ),
        ]
    )
    announcements = _scheduled_announcements(rows)
    assert [a.event_id for a in announcements] == ["mrg-01"]


def test_event_id_is_lower_cased_from_the_edition_code() -> None:
    rows = to_public([_scheduled(edition_code="MRG-42", date="2026-03-03")])
    [announcement] = _scheduled_announcements(rows)
    assert announcement.event_id == "mrg-42"


def test_title_name_and_affiliation_are_carried_through() -> None:
    rows = to_public(
        [
            _scheduled(
                title="A long talk title",
                name="Grace Hopper",
                affiliation="US Navy",
                date="2026-04-01",
            )
        ]
    )
    [announcement] = _scheduled_announcements(rows)
    assert announcement.title == "A long talk title"
    assert announcement.speaker_name == "Grace Hopper"
    assert announcement.speaker_affiliation == "US Navy"


def test_talk_date_is_a_real_date_not_a_string() -> None:
    from datetime import date

    rows = to_public([_scheduled(date="2026-07-09")])
    [announcement] = _scheduled_announcements(rows)
    assert announcement.talk_date == date(2026, 7, 9)


def test_an_unparseable_date_on_a_scheduled_row_raises_rather_than_skipping() -> None:
    rows = to_public([_scheduled(date="not-a-date")])
    with pytest.raises(ValueError, match="not-a-date"):
        _scheduled_announcements(rows)


def test_a_scheduled_row_without_consent_never_carries_a_portrait() -> None:
    rows = to_public([_scheduled(photo_url="https://example.org/portrait.jpg")])
    [announcement] = _scheduled_announcements(rows)
    assert announcement.portrait_data_uri is None


def test_a_consented_photo_url_is_still_not_embedded_but_is_reported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The structurally near-unreachable edge case this function's own
    docstring names: consent granted and the publication gate opened by
    hand on a row that is still `status: scheduled`. Even then, the gate's
    own direction -- never a way *around* it -- holds by construction:
    nothing here fetches `photo_url` over the network, so the rendered
    page still gets no portrait. The gap is visible, not silent (D-25)."""
    rows = to_public(
        [
            _scheduled(
                photo_url="https://example.org/portrait.jpg",
                publication={
                    "consent": "granted",
                    "approved_by": "Board",
                    "approved_on": "2026-01-01",
                    "objections": [],
                    "outcome": "published",
                },
            )
        ]
    )
    [announcement] = _scheduled_announcements(rows)
    assert announcement.portrait_data_uri is None
    assert "::notice::" in capsys.readouterr().err


def test_an_end_to_end_withheld_portrait_renders_the_no_portrait_variant() -> None:
    """The consent gate, proved end to end through the real production path: a real
    speaker record carrying a `photo_url` but no recorded consent, run
    through `to_public` and `_scheduled_announcements`, renders a page
    with no `<img>` at all -- never a broken one, never the URL leaked
    into the markup."""
    rows = to_public([_scheduled(photo_url="https://example.org/portrait.jpg")])
    [announcement] = _scheduled_announcements(rows)
    html = render_announcement(announcement, width=1200, height=1200, root=_REAL_ROOT)
    assert "example.org/portrait" not in html
    assert "<img" not in html


# ---------------------------------------------------------------------------
# render_visuals -- the disk-writing seam
# ---------------------------------------------------------------------------


def test_writes_one_page_per_edition_per_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_fake_root(tmp_path, monkeypatch, [_scheduled()])
    out = tmp_path / "out"
    exit_code = _run(out, monkeypatch)
    assert exit_code == 0
    for fmt in FORMATS:
        html = (out / f"mrg-07-{fmt.name}.html").read_text(encoding="utf-8")
        assert "<!doctype html>" in html
        assert "Ada Lovelace" in html


def test_manifest_carries_event_id_alongside_the_fixture_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_fake_root(tmp_path, monkeypatch, [_scheduled()])
    out = tmp_path / "out"
    _run(out, monkeypatch)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == [
        {
            "event_id": "mrg-07",
            "name": fmt.name,
            "width": fmt.width,
            "height": fmt.height,
            "file": f"mrg-07-{fmt.name}.html",
        }
        for fmt in FORMATS
    ]


def test_non_scheduled_editions_are_never_rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_fake_root(
        tmp_path,
        monkeypatch,
        [
            speaker(id="a", status="lead"),
            speaker(
                id="b",
                status="delivered",
                edition_code="MRG-08",
                date="2025-01-01",
                host_1="H1",
                host_2="H2",
            ),
            _scheduled(edition_code="MRG-09", date="2026-06-01"),
        ],
    )
    out = tmp_path / "out"
    _run(out, monkeypatch)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert {entry["event_id"] for entry in manifest} == {"mrg-09"}


def test_multiple_scheduled_editions_all_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_fake_root(
        tmp_path,
        monkeypatch,
        [
            _scheduled(edition_code="MRG-01", date="2026-01-08"),
            _scheduled(edition_code="MRG-02", date="2026-02-09"),
        ],
    )
    out = tmp_path / "out"
    _run(out, monkeypatch)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert {entry["event_id"] for entry in manifest} == {"mrg-01", "mrg-02"}
    assert len(manifest) == 2 * len(FORMATS)


def test_zero_scheduled_editions_writes_an_empty_manifest_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-13: nothing scheduled is a normal state, printed plainly, not a
    failure -- and not indistinguishable from one either (D-25): the
    message names exactly why nothing was rendered."""
    _use_fake_root(tmp_path, monkeypatch, [speaker(id="a", status="lead")])
    out = tmp_path / "out"
    exit_code = _run(out, monkeypatch)
    assert exit_code == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == []
    assert "nothing to render" in capsys.readouterr().out
    assert not list(out.glob("*.html"))


def test_fonts_are_copied_alongside_when_something_was_rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_fake_root(tmp_path, monkeypatch, [_scheduled()])
    out = tmp_path / "out"
    _run(out, monkeypatch)
    assert (out / "fonts" / "placeholder.woff2").exists()


def test_fonts_are_not_copied_when_nothing_was_scheduled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_fake_root(tmp_path, monkeypatch, [speaker(id="a", status="lead")])
    out = tmp_path / "out"
    _run(out, monkeypatch)
    assert not (out / "fonts").exists()


def test_a_stale_page_from_an_earlier_run_does_not_survive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same "regenerate the whole target, never accumulate into it"
    discipline `render_visual_fixtures`'s own `test_a_stale_fonts_
    directory_from_an_earlier_run_does_not_survive` already pins for
    `fonts/`, applied here to a whole edition: one no longer scheduled
    must not leave its own page sitting next to a manifest that no longer
    lists it."""
    fake_root = _use_fake_root(
        tmp_path, monkeypatch, [_scheduled(edition_code="MRG-01", date="2026-01-08")]
    )
    out = tmp_path / "out"
    _run(out, monkeypatch)
    assert (out / "mrg-01-square.html").exists()

    (fake_root / "data" / "speakers.yml").write_text(
        yaml.safe_dump(
            [_scheduled(edition_code="MRG-02", date="2026-02-09")], sort_keys=False
        ),
        encoding="utf-8",
    )
    _run(out, monkeypatch)
    assert not (out / "mrg-01-square.html").exists()
    assert (out / "mrg-02-square.html").exists()


def test_invalid_yaml_fails_loudly_and_leaves_the_target_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "speakers.yml").write_text("not: [valid", encoding="utf-8")
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: tmp_path)
    out = tmp_path / "out"
    exit_code = _run(out, monkeypatch)
    assert exit_code == 1
    assert "::error::" in capsys.readouterr().err
    assert not out.exists()


def test_a_bad_date_on_a_scheduled_row_fails_the_whole_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-25: a broken record must not silently render the *other*,
    well-formed editions and say nothing about the one it skipped -- the
    whole command fails, naming the record that disagreed with
    `convener-validate`'s own rule that a scheduled edition has a real date."""
    _use_fake_root(tmp_path, monkeypatch, [_scheduled(date="not-a-date")])
    out = tmp_path / "out"
    exit_code = _run(out, monkeypatch)
    assert exit_code == 1
    assert "::error::" in capsys.readouterr().err
    assert not out.exists()


def test_a_print_qr_that_would_be_unscannable_fails_the_whole_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`formats.qr_module_size_mm` is a real,
    tested function that nothing in the actual pipeline called against a
    real edition before this guard. An `edition_code` long enough to bump
    `registration_code_modules`'s own QR version drops the print poster's
    module size below `formats.SCANNABLE_QR_MODULE_MM`; this must fail the
    whole command (D-25) rather than ship an unscannable poster.

    Deliberately bypasses `validate_speakers`'s own four-digit bound
    (this fixture never calls `convener-validate`) to prove the render-time
    guard is load-bearing on its own, not merely a backstop for a check
    some other, unrelated command already ran."""
    long_edition = "MRG-" + "9" * 120
    _use_fake_root(
        tmp_path,
        monkeypatch,
        [_scheduled(edition_code=long_edition, date="2026-01-08")],
    )
    out = tmp_path / "out"
    exit_code = _run(out, monkeypatch)
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "::error::" in err
    assert "scannable" in err
    assert not out.exists()


def test_wrong_argument_count_fails_with_a_usage_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["convener-render-visuals"])
    exit_code = render_visuals()
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "usage" in err.lower()
    assert not (tmp_path / "manifest.json").exists()
