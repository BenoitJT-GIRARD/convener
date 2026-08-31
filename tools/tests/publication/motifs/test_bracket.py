"""The `bracket` family: pin what makes it the mark, and what makes it
straight.

The discipline `motifs/test_ribbon.py` states for the ribbon: a path string
held against a stored literal would pass for a wrong drawing and fail for a
better one, so what is pinned here is what has to be provable. The mark's
own two measurements carried onto a canvas -- the opening between its arcs'
ends, and what its inner arc is as a fraction of its outer. A shape that
adapts to aspect ratio rather than stretching. And a safe area that clears
the drawing at every canvas this product draws on, which for this family is
exact: straight segments join the points `waypoints` returns and reach past
none of them.

The rule that no family but the ribbon draws a curve is not here. It belongs
to every family a charter may name, so `test_registry.py` holds it.
"""

from __future__ import annotations

import math
import re
from typing import Final

import pytest

from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand_templates, formats
from convener_ops.publication.motifs.bracket import (
    _INNER_OVER_OUTER,
    _MARK_INNER_RADIUS,
    _MARK_OUTER_RADIUS,
    _OPENING_HALF_ANGLE_DEGREES,
    CLEARANCE_STROKE_WIDTHS,
    Point,
    _fmt,
    _short_side,
    margins,
    path,
    waypoints,
)

#: Every canvas this product actually draws a motif on: the three named
#: publication formats, and the video-call background's own frame.
CANVASES: Final[tuple[tuple[float, float], ...]] = (
    *((named.width, named.height) for named in formats.FORMATS),
    (brand_templates._BACKGROUND_WIDTH, brand_templates._BACKGROUND_HEIGHT),
)

#: The artwork every measurement in the family is read off.
MARK = repo_root() / "brand" / "convener" / "convener-mark.svg"


def _points(text: str) -> list[Point]:
    """Every `(x, y)` pair in an SVG path fragment.

    Valid because this family only ever emits `M x y` and `L x y` -- every
    number belongs to a coordinate pair, never a lone flag or radius the
    way an `A` (arc) command would need.
    """
    numbers = [float(match) for match in re.findall(r"-?\d+\.?\d*", text)]
    assert len(numbers) % 2 == 0, "an odd count means a non-coordinate number leaked in"
    return list(zip(numbers[0::2], numbers[1::2], strict=True))


# ---------------------------------------------------------------------------
# The mark's own measurements, carried onto a canvas
# ---------------------------------------------------------------------------


def test_the_two_radii_are_the_ones_the_shipped_mark_is_struck_on() -> None:
    """Read back out of `convener-mark.svg`, so a constant edited here
    without the artwork moving fails rather than drifting quietly."""
    mark = MARK.read_text(encoding="utf-8")
    assert f"A {_MARK_OUTER_RADIUS} " in mark
    assert f"A {_MARK_INNER_RADIUS} " in mark


def test_the_half_angle_is_the_one_the_marks_own_arcs_end_at() -> None:
    """The constant, against the artwork rather than against itself.

    Each arc in `convener-mark.svg` is drawn `M x y1 A r r 0 1 1 x y2`:
    both ends sit at the same x, so the centre is level with their midpoint
    and `r` fixes how far along x it sits. The angle either end makes with
    the axis the dot sits on follows, and it is the figure this module
    holds. Recovering the angle from the drawing alone would move with a
    wrong constant instead of failing on it.
    """
    mark = MARK.read_text(encoding="utf-8")
    arcs = re.findall(
        r'd="M [\d.]+ ([\d.]+) A ([\d.]+) [\d.]+ 0 1 1 [\d.]+ ([\d.]+)"', mark
    )
    assert len(arcs) == 2, f"{MARK.name} draws two arcs, and this read {len(arcs)}"

    for first_y, radius_text, second_y in arcs:
        half_span = abs(float(first_y) - float(second_y)) / 2
        radius = float(radius_text)
        along_axis = math.sqrt(radius**2 - half_span**2)
        measured = math.degrees(math.atan2(half_span, along_axis))
        assert measured == pytest.approx(_OPENING_HALF_ANGLE_DEGREES, abs=0.01)


def test_the_opening_is_the_one_the_marks_arcs_leave() -> None:
    """Each bracket's returns stop where a ray at the mark's own half-angle
    leaves the box its arc's circle sits in, which is what carries the
    measurement above onto a canvas."""
    marks = waypoints(1200.0, 1200.0)
    for points in (marks.left, marks.right):
        half_width = abs(points[0][0] - points[2][0]) / 2
        middle = (points[1][1] + points[4][1]) / 2
        for corner in (points[0], points[5]):
            recovered = math.degrees(math.atan2(abs(corner[1] - middle), half_width))
            assert recovered == pytest.approx(_OPENING_HALF_ANGLE_DEGREES)


def test_the_right_bracket_is_the_inner_arc_of_the_left_one() -> None:
    """0.6405 in both directions: the mark's inner radius over its outer. A
    right bracket sized on its own would read as a second drawing rather
    than as the same mark's other arc."""
    assert pytest.approx(_MARK_INNER_RADIUS / _MARK_OUTER_RADIUS) == _INNER_OVER_OUTER

    marks = waypoints(1200.0, 900.0)
    left_width = abs(marks.left[0][0] - marks.left[2][0])
    right_width = abs(marks.right[0][0] - marks.right[2][0])
    left_spine = marks.left[3][1] - marks.left[2][1]
    right_spine = marks.right[3][1] - marks.right[2][1]

    assert right_width / left_width == pytest.approx(_INNER_OVER_OUTER)
    assert right_spine / left_spine == pytest.approx(_INNER_OVER_OUTER)


# ---------------------------------------------------------------------------
# The shape adapts to aspect ratio rather than being stretched
# ---------------------------------------------------------------------------


def test_the_left_bracket_is_unaffected_by_the_long_side() -> None:
    """Its width and its stand-off track the shorter side, so a taller page
    moves nothing across the page, only down it."""
    square = waypoints(1200.0, 1200.0).left
    tall = waypoints(1200.0, 3508.0).left
    assert [x for x, _y in square] == [x for x, _y in tall]


def test_the_right_bracket_keeps_a_constant_offset_from_the_right_edge() -> None:
    wide = waypoints(2000.0, 1000.0).right
    narrow = waypoints(1400.0, 1000.0).right
    assert [2000.0 - x for x, _y in wide] == [1400.0 - x for x, _y in narrow]


def test_a_brackets_footprint_scales_with_the_short_side() -> None:
    small = waypoints(1000.0, 1000.0).left
    big = waypoints(2000.0, 2000.0).left
    for (small_x, small_y), (big_x, big_y) in zip(small, big, strict=True):
        assert big_x == pytest.approx(2 * small_x)
        assert big_y == pytest.approx(2 * small_y)


def test_the_spine_runs_down_the_page_rather_than_across_it() -> None:
    """The one measurement that reads `height`: a banner's spine is shorter
    than a square's on the same width, in the same proportion."""
    square = waypoints(1200.0, 1200.0).left
    banner = waypoints(1200.0, 630.0).left
    square_spine = square[3][1] - square[2][1]
    banner_spine = banner[3][1] - banner[2][1]
    assert banner_spine / square_spine == pytest.approx(630.0 / 1200.0)


# ---------------------------------------------------------------------------
# The drawing itself
# ---------------------------------------------------------------------------


def test_the_path_is_two_subpaths_of_five_straight_segments() -> None:
    commands = [line.split()[0] for line in path(1200.0, 1200.0).splitlines()]
    assert commands == ["M", "L", "L", "L", "L", "L"] * 2


def test_the_path_is_drawn_through_exactly_the_waypoints() -> None:
    marks = waypoints(1200.0, 630.0)
    drawn = _points(path(1200.0, 630.0))
    for (drawn_x, drawn_y), (x, y) in zip(
        drawn, (*marks.left, *marks.right), strict=True
    ):
        assert drawn_x == pytest.approx(x, abs=0.005)
        assert drawn_y == pytest.approx(y, abs=0.005)


def test_the_drawing_never_leaves_the_canvas() -> None:
    """The ribbon enters and leaves the frame; this one stands inside it on
    both sides, at every canvas."""
    for width, height in CANVASES:
        marks = waypoints(width, height)
        for x, y in (*marks.left, *marks.right):
            assert 0.0 <= x <= width
            assert 0.0 <= y <= height


def test_the_two_brackets_open_toward_each_other() -> None:
    """A bracket opening outward would frame the margins."""
    marks = waypoints(1200.0, 1200.0)
    assert marks.left[0][0] > marks.left[2][0]
    assert marks.right[0][0] < marks.right[2][0]


def test_waypoints_rejects_a_non_positive_canvas() -> None:
    for width, height in ((0.0, 100.0), (100.0, -1.0)):
        with pytest.raises(ValueError, match="positive"):
            waypoints(width, height)


def test_path_rejects_a_non_positive_canvas() -> None:
    with pytest.raises(ValueError, match="positive"):
        path(-1.0, 100.0)


def test_margins_reject_a_non_positive_canvas() -> None:
    with pytest.raises(ValueError, match="positive"):
        margins(100.0, 0.0, clearance=1.0)


def test_short_side_is_the_minimum_of_the_two() -> None:
    assert _short_side(3.0, 7.0) == 3.0
    assert _short_side(7.0, 3.0) == 3.0


def test_fmt_trims_trailing_zeros_and_never_prints_an_empty_coordinate() -> None:
    assert _fmt(12.5) == "12.5"
    assert _fmt(12.0) == "12"
    assert _fmt(0.0) == "0"
    assert _fmt(-0.001) == "0"


# ---------------------------------------------------------------------------
# The safe area clears the drawing, at every canvas
# ---------------------------------------------------------------------------


def test_the_safe_area_clears_the_drawing_at_every_canvas() -> None:
    """The property the margins exist for: no painted part of either
    bracket -- its centreline, plus half the stroke either side -- reaches
    into the corridor a word is allowed to start in.

    Exact for this family. Straight segments join the points below and
    reach past none of them, and at the drawing's only corner angle a mitre
    and a round join both put the outline half a stroke width past the
    corner on each axis.
    """
    ratio = 0.0204
    for width, height in CANVASES:
        stroke = ratio * min(width, height)
        clearance = stroke * CLEARANCE_STROKE_WIDTHS
        left_margin, right_margin = margins(width, height, clearance=clearance)
        marks = waypoints(width, height)
        for x, _y in marks.left:
            assert x + stroke / 2 <= left_margin
        for x, _y in marks.right:
            assert x - stroke / 2 >= width - right_margin


def test_the_safe_area_is_the_drawings_own_reach_and_nothing_more() -> None:
    """A margin derived from a point the drawing does not reach is a control
    that cannot fail, and one wider than the drawing costs the composition
    width for nothing. Each margin sits exactly one clearance outside the
    deepest point of its own bracket."""
    clearance = 25.0
    for width, height in CANVASES:
        left_margin, right_margin = margins(width, height, clearance=clearance)
        marks = waypoints(width, height)
        assert left_margin == pytest.approx(max(x for x, _y in marks.left) + clearance)
        assert right_margin == pytest.approx(
            width - min(x for x, _y in marks.right) + clearance
        )


#: The row the announcement's `.content` band begins at, as a fraction of
#: the page, on the format where it begins earliest. Measured in the
#: pinned engine on the rendered fixture: 0.317 of the square, 0.224 of
#: the A4 print, and the banner's wide derivation has no such band at all.
#: That band is the one thing on the right of the page that does not read
#: a family's own margin -- it reads the clearance alone
#: (`visual._motif_content_right_margin`) -- so a drawing on that side has
#: to finish above it.
CONTENT_BEGINS: Final = 0.224


def test_the_right_bracket_finishes_above_the_content_band() -> None:
    """The property `_INNER_TOP` and `_OUTER_HALF_HEIGHT` are set by. It
    holds as a fraction, so it holds at every canvas; checked at each of
    them anyway, because the two constants are read against different
    axes and only a canvas puts them together."""
    for width, height in CANVASES:
        lowest = max(y for _x, y in waypoints(width, height).right)
        assert lowest <= CONTENT_BEGINS * height, (
            f"the right bracket reaches {lowest / height:.4f} of a "
            f"{width:.0f}x{height:.0f} page, into the band that reads the "
            "clearance alone as its right margin"
        )
