"""`convener-render-poster-fixtures` -- the poster the cockpit generates,
at every charter, every family and every canvas.

The composition every duplicate publishes was the one nothing swept.
`render_visual_fixtures` renders it at one charter -- the example's -- and
compares the pixels, which is what a pinned reference image can do and the
reason `visuals.yml` must stay blind to a duplicate's own charter.
`render_template_fixtures` sweeps the cross product, of the three files a
volunteer *downloads*. The poster is neither, and
`visual._motif_content_right_margin` rested on that: it padded `.content`
-- the "what to expect" copy and the speaker's photographic plate -- with
the family's clearance alone, on an argument about where the ribbon's
right side happens to run.

The argument was wrong about the ribbon too. Rendered at this instance's
own charter, its own family and the square canvas its own forum gets, the
ribbon's right loop was painted 14.4 pixels across the speaker's plate,
and 29.8 across it on the print. Every gate was green, because no gate had
ever drawn that page.

What this module holds is the Python half: that the command writes the
whole cross product, and that the margin is the family's own reach over
that band rather than a constant. `tools/visuals/check-posters.mjs` is the
other half and the one that actually proves it, in the pinned engine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Final

import pytest

from convener_ops.cli.publication import _template_charters, render_poster_fixtures
from convener_ops.declaration import published
from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, composition, motifs, visual
from convener_ops.publication.formats import FORMATS
from convener_ops.publication.visual import FIXTURE_ANNOUNCEMENT

ROOT: Final = repo_root()


def _run(out: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["convener-render-poster-fixtures", str(out)])
    return render_poster_fixtures()


def _expected() -> set[str]:
    return {
        f"{label}-{family}-{fmt.name}"
        for label, _charter, _declaration in _template_charters(ROOT)
        for family in motifs.FAMILIES
        for fmt in FORMATS
    }


def test_writes_the_whole_cross_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every charter this repository holds, crossed with every family the
    registry draws, crossed with every canvas the composition renders.

    Read off `_template_charters`, `motifs.FAMILIES` and `formats.FORMATS`
    rather than counted here: a charter committed under `assets/brand/` and a
    family registered beside `ribbon.py` are both swept on the commit that
    adds them, with no entry to make anywhere.
    """
    out = tmp_path / "fixtures"
    assert _run(out, monkeypatch) == 0
    written = {path.stem for path in out.glob("*.html")}
    assert written == _expected()
    assert len(written) >= 30, (
        f"the sweep renders {len(written)} pages, which is fewer than this "
        "repository's charters times its families times its canvases -- a "
        "checker fed an empty sweep would pass for free"
    )


def test_the_manifest_says_which_charter_and_family_each_page_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The checker reports by name, and a name that did not say which
    charter and which family drew the page would leave a person with a
    failure they could not reproduce."""
    out = tmp_path / "fixtures"
    _run(out, monkeypatch)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert {entry["name"] for entry in manifest} == _expected()
    for entry in manifest:
        assert (
            entry["name"] == f"{entry['charter']}-{entry['family']}-{entry['format']}"
        )
        assert (out / entry["file"]).is_file()
        assert entry["width"] > 0 and entry["height"] > 0


def test_the_fixture_identity_reaches_every_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same fixed, versioned identity the reference images use -- an
    invented speaker, no photograph, no clock, no network -- so the same
    input always writes the same ninety pages."""
    out = tmp_path / "fixtures"
    _run(out, monkeypatch)
    for path in out.glob("*.html"):
        html = path.read_text(encoding="utf-8")
        assert FIXTURE_ANNOUNCEMENT.speaker_name in html
        assert FIXTURE_ANNOUNCEMENT.title in html


def test_each_page_is_drawn_with_the_family_its_name_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sweep that rendered the same drawing ninety times under ninety
    names would pass everything and measure one family."""
    out = tmp_path / "fixtures"
    _run(out, monkeypatch)
    for family in sorted(motifs.FAMILIES):
        drawn = motifs.path(family, 1200.0, 1200.0).splitlines()[0].strip()
        html = (out / f"convener-{family}-square.html").read_text(encoding="utf-8")
        assert drawn in html, f"the {family} page is not drawn with {family}"


def test_the_command_refuses_without_an_output_directory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["convener-render-poster-fixtures"])
    assert render_poster_fixtures() == 1
    assert "usage:" in capsys.readouterr().err


# --------------------------------------------------------------------------
# The margin the sweep exists for
# --------------------------------------------------------------------------


def _content_margin(root: Path, width: float, height: float) -> float:
    return visual._motif_content_right_margin(width, height, root) / 100.0 * width


@pytest.mark.parametrize("family", sorted(motifs.FAMILIES))
@pytest.mark.parametrize(
    "charter", _template_charters(ROOT), ids=lambda entry: entry[0]
)
def test_the_content_margin_is_the_familys_own_reach_over_that_band(
    tmp_path: Path, charter: tuple[str, Path, Path], family: str
) -> None:
    """What `.content` pays for is what the drawing does beside it.

    Not the clearance alone, which is what it was: that number is the same
    whatever the drawing, so a family reaching into those rows on the right
    was paid for by nobody. And not the full-height right margin either,
    which would cost the band width the drawing never reaches there.
    """
    from convener_ops.cli.publication import _template_fixture_root

    _label, path, declaration = charter
    root = _template_fixture_root(tmp_path, ROOT, path, declaration, family)
    ratio = brand.motif_width_ratio(root)
    width = height = 1200.0
    _left, reach = motifs.safe_margins(
        family,
        width,
        height,
        ratio=ratio,
        top=composition.CONTENT_TOP * height,
        bottom=height,
    )
    clearance = motifs.clearance(family, width, height, ratio=ratio)
    assert _content_margin(root, width, height) == pytest.approx(max(reach, clearance))


def test_the_ribbon_pays_for_its_right_loop_and_the_others_do_not(
    tmp_path: Path,
) -> None:
    """The measurement that made the old margin wrong, stated as a number.

    The ribbon reaches into `.content`'s own rows on the right; the four
    families beside it finish above the band and reach nothing there. So
    the ribbon's margin has to be wider than the clearance and theirs has
    to be exactly it -- which is also why nothing noticed for as long as
    the one charter anything rendered drew `bracket`.
    """
    from convener_ops.cli.publication import _template_fixture_root

    width = height = 1200.0
    margins = {}
    for family in sorted(motifs.FAMILIES):
        root = _template_fixture_root(
            tmp_path,
            ROOT,
            brand.source(ROOT),
            published.INSTANCE_PATH,
            family,
        )
        ratio = brand.motif_width_ratio(root)
        margins[family] = (
            _content_margin(root, width, height),
            motifs.clearance(family, width, height, ratio=ratio),
        )
    ribbon, ribbon_clearance = margins["ribbon"]
    assert ribbon > ribbon_clearance * 2
    for family, (margin, clearance) in margins.items():
        if family == "ribbon":
            continue
        assert margin == pytest.approx(clearance), (
            f"{family} finishes above `.content` and should pay the gutter alone"
        )
