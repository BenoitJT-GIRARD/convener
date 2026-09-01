"""`convener-render-visual-fixtures` -- the one disk-writing seam between
`visual.render_announcement`/`formats.FORMATS` (both pure) and the
pinned Node/Puppeteer render step, which reads what this command writes
rather than re-deriving a page's own markup a second time in JavaScript.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import instance_identity
import pytest

from convener_ops.cli import render_visual_fixtures
from convener_ops.declaration import published
from convener_ops.declaration.paths import repo_root
from convener_ops.journey.registration import signup_url
from convener_ops.publication import brand
from convener_ops.publication.formats import FORMATS
from convener_ops.publication.visual import FIXTURE_ANNOUNCEMENT

ROOT = repo_root()
EXAMPLE = ROOT / published.EXAMPLE_INSTANCE_ROOT


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


# ------------------------------------------------------------------ #
# Whose poster the committed reference images are
# ------------------------------------------------------------------ #


def test_the_fixture_is_rendered_as_the_example_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The three committed reference images are bytes, and no text sweep
    in this repository can read them -- `test_second_instance.py` says so
    by name. So the claim that they carry no real instance's identity has
    to be made here, on the pages they are rendered from, one value at a
    time and each read from the example's own files rather than typed.

    Every layer of the composition that carries an identity at all: the
    palette, the motif, the hero band, the wordmark band, and the address
    encoded in the registration QR."""
    out = tmp_path / "fixtures"
    _run(out, monkeypatch)
    page = (out / "print.html").read_text(encoding="utf-8")

    theirs = published.load_identity(EXAMPLE)
    assert theirs.strapline.upper() in page.upper()
    assert theirs.forum_host in page
    assert signup_url(FIXTURE_ANNOUNCEMENT.event_id, root=EXAMPLE) in page

    colours = brand.colours(brand.load(EXAMPLE))
    assert colours["dominant"] in page
    assert brand.motif(EXAMPLE)["stroke"] in page


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_no_value_of_the_instance_running_this_repository_reaches_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half, and the one that would actually catch a
    regression: the same five values, read from *this* repository's own
    declaration and charter, must be absent. Derived rather than written
    out, so the day this instance changes a colour or its forum the check
    still looks for the right string.

    Both halves are needed. The first alone would pass for a page that
    happened to carry both instances; this one alone would pass for a
    blank page."""
    out = tmp_path / "fixtures"
    _run(out, monkeypatch)
    page = (out / "print.html").read_text(encoding="utf-8")

    ours = published.load_identity(ROOT)
    assert ours.strapline.upper() not in page.upper()
    assert ours.forum_host not in page
    assert ours.organisation not in page
    assert signup_url(FIXTURE_ANNOUNCEMENT.event_id) not in page
    assert published.load(ROOT).host not in page

    assert brand.colours(brand.load(ROOT))["dominant"] not in page
    assert brand.motif(ROOT)["stroke"] not in page


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_the_two_charters_this_test_compares_are_actually_different() -> None:
    """Guards the pair above. If the example ever adopted this instance's
    palette or its forum, both tests would still pass and neither would
    mean anything -- the second would be asserting the absence of a string
    the first had just found."""
    assert (
        brand.colours(brand.load(EXAMPLE))["dominant"]
        != brand.colours(brand.load(ROOT))["dominant"]
    )
    assert published.load_identity(EXAMPLE).forum_host != (
        published.load_identity(ROOT).forum_host
    )
    assert published.load_identity(EXAMPLE).strapline != (
        published.load_identity(ROOT).strapline
    )


def test_the_fonts_still_come_from_the_product_and_not_the_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one thing that is deliberately *not* taken from the example:
    the self-hosted faces are the product's, served by it (D-17), and
    `examples/the-example-collective/` holds no copy of them precisely because a face is
    not an identity here. A render that started reading them from the
    example's tree would find nothing and fall back silently."""
    out = tmp_path / "fixtures"
    _run(out, monkeypatch)
    assert not (EXAMPLE / "fonts").exists()
    copied = {path.name for path in (out / "fonts").glob("*.woff2")}
    assert copied == {path.name for path in (ROOT / "fonts").glob("*.woff2")}
    assert copied
