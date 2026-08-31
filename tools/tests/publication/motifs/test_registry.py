"""The registry: every drawing in the directory is a family a charter can
name, and a name that is not one stops the build.

Two rules, and the second is the whole reason the first one is measured
rather than reviewed. A family module nobody registered is a drawing no
charter can ask for, which reads at a glance as a family that exists; and a
`motif.family` naming something the registry does not hold must never be
answered by drawing whichever family happens to be first, because a
duplicate would then ship a mark it never asked for with nothing on the
page to say so.

A third rule sits at the foot of this file and is about the drawings
themselves: one family is a continuous curve, and it is the one traced off
an instance's own poster.
"""

from __future__ import annotations

import re
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Final

import pytest

from convener_ops.publication import brand_templates, formats, motifs

#: The directory the registry is a table of.
DIRECTORY = Path(motifs.__file__).parent


def family_modules() -> list[str]:
    """Every module in the directory that is not the registry itself, read
    off the directory rather than listed here: adding a family puts it
    under the rule below on the commit that adds it."""
    return sorted(
        path.stem for path in DIRECTORY.glob("*.py") if path.stem != "__init__"
    )


def test_the_walk_finds_the_family_modules() -> None:
    """A read that found nothing would make the rule below pass over an
    empty directory -- the shape six sweeps in this repository had already
    silently narrowed into."""
    assert family_modules(), (
        f"{DIRECTORY} holds no family module at all, so the rule below "
        "compares two empty lists and proves nothing"
    )


def test_the_registry_reaches_every_family_in_the_directory() -> None:
    """The rule, on the real directory.

    Matched by the module each family's own `path` was defined in, not by
    the name it was registered under: a `Family` entry pointing at a module
    that is not the one it is named for would otherwise pass.
    """
    registered = sorted(
        drawn.path.__module__.rsplit(".", 1)[-1] for drawn in motifs.FAMILIES.values()
    )

    assert registered == family_modules(), (
        f"{DIRECTORY.name} holds {family_modules()} and the registry names "
        f"{registered}. A module nobody registered draws nothing any charter "
        "can ask for, and a family registered twice hides one of them"
    )


def test_every_family_declares_the_fields_a_charter_writes_for_it() -> None:
    """A family that declared none would make `brand.MOTIF_FIELDS` ask a
    charter for nothing but the two fields every motif carries, and a
    half-written section would then build."""
    silent = [name for name, drawn in motifs.FAMILIES.items() if not drawn.fields]

    assert silent == [], (
        f"{silent} declare no fields of their own. A family says which "
        "fields a charter naming it has to write, and `brand.py` holds the "
        "charter to that list"
    )


def test_a_family_is_looked_up_by_the_name_a_charter_writes() -> None:
    assert motifs.family("ribbon") is motifs.RIBBON
    assert motifs.RIBBON.name == "ribbon"


def test_an_unknown_family_is_refused_and_the_known_ones_are_named() -> None:
    """The refusal, and what it has to say: never a fall back to whichever
    drawing exists."""
    with pytest.raises(motifs.UnknownMotifFamilyError) as raised:
        motifs.family("lattice")

    message = str(raised.value)
    assert "'lattice'" in message
    for name in motifs.FAMILIES:
        assert name in message, (
            f"{name} exists and the refusal does not offer it, so a person "
            "reading it cannot tell what they may write instead"
        )


def test_every_entry_point_refuses_an_unknown_family() -> None:
    """Not only the lookup: each of the three things a caller actually
    asks for goes through it, so none of them can grow a fall back of its
    own."""
    for call in (
        lambda: motifs.path("lattice", 1200, 1200),
        lambda: motifs.safe_margins("lattice", 1200, 1200, ratio=0.02),
        lambda: motifs.clearance("lattice", 1200, 1200, ratio=0.02),
    ):
        with pytest.raises(motifs.UnknownMotifFamilyError):
            call()


# ---------------------------------------------------------------------------
# The stroke's own weight: the motif's, not any one family's
# ---------------------------------------------------------------------------


def test_stroke_width_tracks_the_shorter_side_not_the_longer_one() -> None:
    # Same short side (1000), wildly different long side: the width must
    # not move. A `max` in place of `min` inside `stroke_width` breaks
    # exactly this -- confirmed by mutating it and watching this test
    # fail, not assumed.
    square = motifs.stroke_width(1000, 1000, ratio=0.02)
    tall = motifs.stroke_width(1000, 5000, ratio=0.02)
    wide = motifs.stroke_width(5000, 1000, ratio=0.02)
    assert square == tall == wide == pytest.approx(20.0)


def test_stroke_width_scales_with_the_short_side_when_it_changes() -> None:
    small = motifs.stroke_width(1000, 1000, ratio=0.02)
    big = motifs.stroke_width(2000, 2000, ratio=0.02)
    assert big == pytest.approx(2 * small)


def test_stroke_width_rejects_a_non_positive_canvas() -> None:
    with pytest.raises(ValueError, match="positive"):
        motifs.stroke_width(0, 100, ratio=0.02)
    with pytest.raises(ValueError, match="positive"):
        motifs.stroke_width(100, -1, ratio=0.02)


def test_the_clearance_a_family_keeps_is_read_off_that_family() -> None:
    """`clearance` is the family's own figure times the stroke this canvas
    draws it at, never a constant held here: a drawing that is not a
    Catmull-Rom curve measures its own overshoot."""
    ratio = 0.02
    for name, drawn in motifs.FAMILIES.items():
        assert motifs.clearance(name, 1200, 1200, ratio=ratio) == pytest.approx(
            motifs.stroke_width(1200, 1200, ratio=ratio) * drawn.clearance_stroke_widths
        )


def test_safe_margins_leave_the_drawing_outside_and_waste_nothing() -> None:
    """The registry is the only thing that turns a ratio into a clearance,
    so a family never reads a charter to answer where a word may start --
    and what it widens is the family's own outline.

    Two halves, because either alone is trivially satisfiable: no point of
    the drawing lies in the corridor at all (a margin that let one in
    would be no margin), and the corridor is not one unit wider than it
    has to be (a margin derived from a point the drawing never reaches
    would be a control that cannot fail, and would cost a composition
    width for nothing).
    """
    ratio = 0.02
    for name in motifs.FAMILIES:
        room = motifs.clearance(name, 1200, 900, ratio=ratio)
        left, right = motifs.safe_margins(name, 1200, 900, ratio=ratio)
        inside = [
            x
            for run in motifs.outline(name, 1200, 900)
            for x, y in run
            if 0 <= x <= 1200 and 0 <= y <= 900
        ]
        assert not any(left < x < 1200 - right for x in inside)
        assert min(abs(x - (left - room)) for x in inside) < 0.5
        assert min(abs(x - (1200 - right + room)) for x in inside) < 0.5


def test_a_band_never_claims_more_ground_than_the_whole_canvas_does() -> None:
    """The corridor over any band of rows is at least as wide as the
    corridor over the whole page: a drawing cannot reach further into a
    slice of itself than into all of itself. The property that makes it
    safe for a block to ask about its own rows rather than the page."""
    ratio = 0.024
    for name in motifs.FAMILIES:
        whole = motifs.safe_margins(name, 1200, 1200, ratio=ratio)
        for top in range(0, 1200, 100):
            band = motifs.safe_margins(
                name, 1200, 1200, ratio=ratio, top=top, bottom=top + 100
            )
            assert band[0] <= whole[0] + 1e-9
            assert band[1] <= whole[1] + 1e-9


def test_covered_and_free_spans_partition_the_canvas() -> None:
    """Every strip of the page is either ground a word may use or ground
    the drawing has taken, and no unit is both."""
    ratio = 0.024
    for name in motifs.FAMILIES:
        taken = motifs.covered(name, 1200, 1200, ratio=ratio, top=200, bottom=600)
        free = motifs.free_spans(name, 1200, 1200, ratio=ratio, top=200, bottom=600)
        edges = sorted([*taken, *free])
        assert edges[0][0] == 0.0
        assert edges[-1][1] == 1200.0
        for (_start, end), (next_start, _next_end) in pairwise(edges):
            assert end == pytest.approx(next_start)


def test_a_band_the_drawing_never_enters_leaves_the_whole_page_free() -> None:
    """A row band with no part of the drawing in it reports no margins at
    all, which is what lets a block keep its own design indent rather than
    being pushed aside by a stroke that is nowhere near it."""
    for name in motifs.FAMILIES:
        empty = motifs.covered(name, 1200, 1200, ratio=0.024, top=599.9, bottom=600.0)
        if empty:
            continue
        assert motifs.safe_margins(
            name, 1200, 1200, ratio=0.024, top=599.9, bottom=600.0
        ) == (0.0, 0.0)


def test_a_band_that_runs_backwards_is_refused() -> None:
    with pytest.raises(ValueError, match="runs from its first row"):
        motifs.safe_margins("ribbon", 1200, 1200, ratio=0.024, top=800, bottom=200)


def test_a_drawing_across_the_middle_of_a_band_refuses_to_report_a_margin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A family painting right across the page leaves no safe area, and
    says so rather than handing back a margin no word could honour."""
    monkeypatch.setitem(
        motifs.FAMILIES,
        "wall",
        replace(
            motifs.BRACKET,
            name="wall",
            outline=lambda w, h: (((0.0, h / 2), (w, h / 2)),),
        ),
    )
    with pytest.raises(motifs.CoveredCanvasError, match="no ground across the middle"):
        motifs.safe_margins("wall", 1200, 1200, ratio=0.024)


# ---------------------------------------------------------------------------
# One family is a continuous curve, and it is the one traced off a poster
# ---------------------------------------------------------------------------

#: Every SVG path command that draws a curve: cubic and smooth cubic,
#: quadratic and smooth quadratic, and elliptical arc, in both cases.
CURVE_COMMANDS: Final = frozenset("CSQTAcsqta")

#: What a drawing made of straight segments may use instead: a move, a
#: line, and the close that ends a subpath.
STRAIGHT_COMMANDS: Final = frozenset("MLZmlz")

#: The one family that is a continuous curve, and the reason the rule
#: below has an exception at all. `ribbon.py` is traced pixel by pixel off
#: one instance's own announcement poster, and being a single unbroken
#: meandering stroke is the property of that trace -- so a second drawing
#: built as a curve would read as a variant of somebody else's mark rather
#: than as a charter of its own. Every other family is drawn from the
#: product's own artwork, and none of them may be one.
THE_TRACED_FAMILY: Final = motifs.RIBBON.name

#: Every canvas this product actually draws a motif on: the three named
#: publication formats, and the video-call background's own frame. The
#: rule below is checked at each of them, because a drawing's own
#: commands are a function of the canvas it is asked for.
CANVASES: Final[tuple[tuple[float, float], ...]] = (
    *((named.width, named.height) for named in formats.FORMATS),
    (brand_templates.BACKGROUND_WIDTH, brand_templates.BACKGROUND_HEIGHT),
)


def commands(drawn: str) -> list[str]:
    """Every path command letter in an SVG path `d`, in order."""
    return re.findall(r"[A-Za-z]", drawn)


def test_no_family_but_the_traced_one_draws_a_curve() -> None:
    """The rule, at every canvas and on every family the registry holds.

    A path whose only commands are `M` and `L` contains no curve: that is
    what makes this checkable rather than a sentence in a plan. The
    families this repository ships publicly are drawn from the product's
    own artwork, and a curve is the one shape they may not take.
    """
    for name in sorted(motifs.FAMILIES):
        if name == THE_TRACED_FAMILY:
            continue
        for width, height in CANVASES:
            drawn = commands(motifs.path(name, width, height))
            curves = sorted(set(drawn) & CURVE_COMMANDS)
            assert curves == [], (
                f"{name} draws {curves} on a {width:.0f}x{height:.0f} canvas. "
                f"{THE_TRACED_FAMILY} is the only family that may be a curve, "
                "because it is the only one traced off an instance's own mark"
            )
            unknown = sorted(set(drawn) - STRAIGHT_COMMANDS)
            assert unknown == [], (
                f"{name} draws {unknown} on a {width:.0f}x{height:.0f} canvas, "
                f"which is neither a move nor a line. Only "
                f"{sorted(STRAIGHT_COMMANDS)} say a segment is straight"
            )


def test_the_traced_family_does_draw_a_curve() -> None:
    """The anchor under the rule above: with no family drawing a curve at
    all, that rule would pass over a directory of empty paths and prove
    nothing."""
    for width, height in CANVASES:
        drawn = set(commands(motifs.path(THE_TRACED_FAMILY, width, height)))
        assert drawn & CURVE_COMMANDS, (
            f"{THE_TRACED_FAMILY} is the family the rule above excepts, and "
            f"it draws {sorted(drawn)} on a {width:.0f}x{height:.0f} canvas"
        )
