"""The `chevrons` family: pin what makes it an angle, and what makes it fit.

The discipline `motifs/test_ribbon.py` states for the ribbon and
`motifs/test_bracket.py` repeats for the bracket: a path string held
against a stored literal would pass for a wrong drawing and fail for a
better one, so what is pinned here is what has to be provable. This family
is measured against no artwork of its own -- the one figure it takes from
the product's mark is the angle -- so what stands in for the artwork is
the set of measurements each of its figures was fixed by, and every one of
them is checked here against the thing it was read off rather than against
itself.

The rule that no family but the ribbon draws a curve is not here. It
belongs to every family a charter may name, so `test_registry.py` holds it.
"""

from __future__ import annotations

import json
import math
import re
from itertools import pairwise
from pathlib import Path
from typing import Final

import pytest

from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, brand_templates, formats, motifs
from convener_ops.publication.motifs import bracket
from convener_ops.publication.motifs.chevrons import (
    _BOTTOM,
    _CONTENT_TOP,
    _EDGE_GUTTER,
    _PITCH,
    _PITCH_RISES,
    _REGISTER_TOP,
    _RIGHT_BOTTOM,
    _RISE,
    _SPAN,
    _TIP_HALF_ANGLE_DEGREES,
    CLEARANCE_STROKE_WIDTHS,
    REACH,
    Point,
    _arm_tops,
    _fmt,
    _short_side,
    marks,
    outline,
    path,
    waypoints,
)

ROOT: Final = repo_root()

#: Every canvas this product actually draws a motif on: the three named
#: publication formats, and the video-call background's own frame.
CANVASES: Final[tuple[tuple[float, float], ...]] = (
    *((named.width, named.height) for named in formats.FORMATS),
    (brand_templates.BACKGROUND_WIDTH, brand_templates.BACKGROUND_HEIGHT),
)

#: The heaviest weight any charter this repository holds draws a motif at.
#: Read off the charters below rather than trusted, because it is the
#: figure both `_EDGE_GUTTER` and `_PITCH_RISES` are bounded by: a charter
#: committed at a heavier stroke bleeds this drawing off its own edge and
#: closes the ground between one chevron and the next.
HEAVIEST_RATIO: Final = 0.03


def _points(text: str) -> list[Point]:
    """Every `(x, y)` pair in an SVG path fragment.

    Valid because this family only ever emits `M x y` and `L x y` -- every
    number belongs to a coordinate pair, never a lone flag or radius the
    way an `A` command would need.
    """
    numbers = [float(match) for match in re.findall(r"-?\d+\.?\d*", text)]
    assert len(numbers) % 2 == 0, "an odd count means a non-coordinate number leaked in"
    return list(zip(numbers[0::2], numbers[1::2], strict=True))


def _charters() -> tuple[Path, ...]:
    """Every charter this repository holds: the two an instance owns, and
    every one the product ships. The same set `cli._template_charters`
    renders, read the same way rather than listed here."""
    return (
        brand.INSTANCE_PATH,
        Path("examples") / "the-example-collective" / brand.INSTANCE_PATH,
        *brand.shipped(ROOT),
    )


# ---------------------------------------------------------------------------
# The measurements each figure was fixed by
# ---------------------------------------------------------------------------


def test_the_heaviest_stroke_is_the_one_a_charter_here_actually_draws() -> None:
    """The bound two of this family's figures are set against, read off the
    charters rather than asserted. A charter committed at a heavier weight
    moves this figure, and the drawing has to be re-measured against it
    rather than the figure being edited to agree."""
    weights = {
        rel.as_posix(): float(
            json.loads((ROOT / rel).read_text(encoding="utf-8"))["motif"]["width_ratio"]
        )
        for rel in _charters()
    }
    assert max(weights.values()) == HEAVIEST_RATIO, (
        f"the charters here draw at {weights}, and this family's own gutter "
        f"and pitch are measured against {HEAVIEST_RATIO}"
    )


def test_the_tip_opens_at_the_angle_the_products_own_mark_opens_at() -> None:
    """Where the shape itself comes from. Both arcs of
    `brand/convener/convener-mark.svg` run from 40 degrees to 320, and the
    bracket carries the half of that opening onto its returns; a chevron is
    that same opening laid on its side. Held to the bracket's own constant,
    so the two drawings cannot come to disagree about the mark."""
    assert _TIP_HALF_ANGLE_DEGREES == bracket._OPENING_HALF_ANGLE_DEGREES


def test_the_column_asks_for_exactly_the_ground_the_bracket_already_takes() -> None:
    """What `_SPAN` is fixed by: the deepest drawing this product already
    ships. A composition gives up the same room to a charter naming this
    family as to one naming the product's own mark, and not a unit more."""
    deepest = (1.0 + bracket._EDGE_STANDOFF + 1.0) * bracket._OUTER_HALF_WIDTH
    reach = REACH
    assert reach == pytest.approx(deepest)
    assert reach == pytest.approx(_EDGE_GUTTER + _SPAN)


def test_the_gutter_keeps_the_paint_of_an_arm_off_the_edge() -> None:
    """What `_EDGE_GUTTER` is fixed by. An arm's end carries a round cap
    reaching half a stroke in every direction, so at the heaviest charter
    here the paint stops half that gutter short of the edge, and further
    at every other charter."""
    assert _EDGE_GUTTER == HEAVIEST_RATIO
    assert _EDGE_GUTTER - HEAVIEST_RATIO / 2 > 0


def test_the_rise_is_what_the_span_and_the_angle_come_to() -> None:
    """`_RISE` is no figure of its own: half a span, over the tangent of
    the opening's half-angle. Checked on a canvas rather than on the
    constants alone, so a drawing that stopped using it would fail here."""
    width, height = 1200.0, 1200.0
    short = _short_side(width, height)
    (arm_x, arm_y), (tip_x, tip_y), _end = waypoints(width, height).left[0]
    across = tip_x - arm_x
    down = tip_y - arm_y
    assert across == pytest.approx(_SPAN * short / 2)
    assert math.degrees(math.atan2(across, down)) == pytest.approx(
        _TIP_HALF_ANGLE_DEGREES
    )
    assert down == pytest.approx(_RISE * short)


def test_two_rises_is_the_smallest_pitch_that_leaves_ground_at_all() -> None:
    """The first half of what `_PITCH_RISES` is bounded by, and the reason
    it is a whole number: at one rise the next chevron's arm-ends would
    begin on the tip above."""
    assert _PITCH_RISES == 2.0
    assert (_PITCH_RISES - 1.0) * _RISE > 0
    assert (1.0 - 1.0) * _RISE == 0


def test_the_chevrons_stay_apart_at_the_heaviest_charter_here() -> None:
    """The second half, and the one that needs a measurement: the ground
    between one chevron's tip and the next chevron's arms, once the drawing
    is inked at the heaviest weight any charter here carries. Without this
    bound the column closes into a zigzag and stops being a sequence."""
    gap = (_PITCH_RISES - 1.0) * _RISE - HEAVIEST_RATIO
    assert gap > 0, (
        f"at {HEAVIEST_RATIO} of the shorter side the paint below one tip "
        "meets the arms of the chevron under it, and the column is a zigzag "
        "rather than a sequence"
    )
    pitch = _PITCH
    assert pitch == pytest.approx(_PITCH_RISES * _RISE)


def test_the_column_keeps_one_gutter_from_the_left_the_right_and_the_top() -> None:
    """The same distance from every edge it meets, which is what makes the
    two columns read as one drawing rather than as three decisions."""
    for width, height in CANVASES:
        gutter = _EDGE_GUTTER * _short_side(width, height)
        columns = waypoints(width, height)
        assert min(x for mark in columns.left for x, _y in mark) == pytest.approx(
            gutter
        )
        assert width - max(x for mark in columns.right for x, _y in mark) == (
            pytest.approx(gutter)
        )
        assert min(y for mark in marks(width, height) for _x, y in mark) == (
            pytest.approx(gutter)
        )


def test_the_left_column_stops_above_the_announcements_registration_slot() -> None:
    """What `_BOTTOM` is read off. The announcement takes the free strip
    nearest the left edge for its registration slot, and a column standing
    off that edge would leave it a strip a gutter wide -- which
    `brand_templates._ANNOUNCEMENT_SLOT_FLOOR` refuses rather than drawing
    a slot nobody could drop a code into. So the column finishes above
    those rows and the slot gets the whole page."""
    register_top = _REGISTER_TOP
    bottom = _BOTTOM
    assert register_top == pytest.approx(
        brand_templates._ANNOUNCEMENT_REGISTER_TOP / formats.SQUARE.height
    )
    assert bottom == pytest.approx(_REGISTER_TOP - _EDGE_GUTTER)

    side = formats.SQUARE
    lowest = max(y for mark in marks(side.width, side.height) for _x, y in mark)
    assert lowest < brand_templates._ANNOUNCEMENT_REGISTER_TOP

    corridor = motifs.free_spans(
        "chevrons",
        side.width,
        side.height,
        ratio=HEAVIEST_RATIO,
        top=brand_templates._ANNOUNCEMENT_REGISTER_TOP,
        bottom=brand_templates._ANNOUNCEMENT_SLOT_TOP
        + brand_templates._ANNOUNCEMENT_SLOT_SIDE,
    )
    assert corridor == ((0.0, side.width),)


def test_the_right_column_finishes_above_the_content_band() -> None:
    """What `_RIGHT_BOTTOM` is read off, and why this drawing is short on
    the right where it runs the page on the left. `.content` -- the "what
    to expect" copy and the speaker's frame beside it -- is the one band on
    that side of a generated poster set against the clearance alone
    (`visual._motif_content_right_margin`); measured in the pinned engine
    it begins at 0.317 of a square and 0.224 of an A4 print, which is the
    same figure `motifs/test_bracket.py` holds its own right arm to. Held
    at every canvas, because which chevron is the last one is a property of
    the aspect ratio."""
    right_bottom = _RIGHT_BOTTOM
    assert _CONTENT_TOP == 0.224
    assert right_bottom == pytest.approx(_CONTENT_TOP - _EDGE_GUTTER)
    for width, height in CANVASES:
        lowest = max(y for mark in waypoints(width, height).right for _x, y in mark)
        assert lowest <= _RIGHT_BOTTOM * height
        assert lowest < _CONTENT_TOP * height, (
            f"the right column reaches row {lowest:.1f} of a "
            f"{width:.0f}x{height:.0f} page, into a band set against the "
            "clearance alone"
        )


def test_the_right_column_is_the_opening_of_the_left_columns_own_sequence() -> None:
    """One drawing read to two depths, never two: every chevron of the
    right column sits on a row of the left."""
    for width, height in CANVASES:
        columns = waypoints(width, height)
        left_rows = sorted({y for mark in columns.left for _x, y in mark})
        right_rows = sorted({y for mark in columns.right for _x, y in mark})
        assert right_rows == left_rows[: len(right_rows)]
        assert 0 < len(right_rows) < len(left_rows)


def test_the_chevrons_stand_a_pitch_apart_down_the_page() -> None:
    tops = _arm_tops(1200.0, 1200.0, _BOTTOM)
    assert len(tops) > 1
    for before, after in pairwise(tops):
        assert after - before == pytest.approx(_PITCH * 1200.0)


# ---------------------------------------------------------------------------
# The drawing adapts to aspect ratio rather than being stretched
# ---------------------------------------------------------------------------


def test_the_shape_is_unaffected_by_the_long_side() -> None:
    """Every length in a chevron tracks the shorter side, so a taller page
    gets more chevrons of the same shape rather than stretched ones."""
    square = waypoints(1200.0, 1200.0).left
    tall = waypoints(1200.0, 3508.0).left
    assert len(tall) > len(square)
    for square_mark, tall_mark in zip(square, tall, strict=False):
        assert square_mark == tall_mark


def test_the_column_scales_with_the_short_side() -> None:
    small = marks(1000.0, 1000.0)
    big = marks(2000.0, 2000.0)
    assert len(small) == len(big)
    for small_mark, big_mark in zip(small, big, strict=True):
        for (sx, sy), (bx, by) in zip(small_mark, big_mark, strict=True):
            assert bx == pytest.approx(2 * sx)
            assert by == pytest.approx(2 * sy)


def test_the_right_column_keeps_a_constant_offset_from_the_right_edge() -> None:
    wide = waypoints(2000.0, 1000.0).right
    narrow = waypoints(1400.0, 1000.0).right
    assert [2000.0 - x for mark in wide for x, _y in mark] == (
        [1400.0 - x for mark in narrow for x, _y in mark]
    )


# ---------------------------------------------------------------------------
# The drawing itself
# ---------------------------------------------------------------------------


def test_the_path_is_one_move_and_two_lines_per_chevron() -> None:
    for width, height in CANVASES:
        commands = [line.split()[0] for line in path(width, height).splitlines()]
        assert commands == ["M", "L", "L"] * len(marks(width, height))


def test_the_path_is_drawn_through_exactly_the_chevrons() -> None:
    drawn = _points(path(1200.0, 630.0))
    every = [point for mark in marks(1200.0, 630.0) for point in mark]
    for (drawn_x, drawn_y), (x, y) in zip(drawn, every, strict=True):
        assert drawn_x == pytest.approx(x, abs=0.01)
        assert drawn_y == pytest.approx(y, abs=0.01)


def test_the_outline_is_the_chevrons_and_nothing_else() -> None:
    """Straight segments join the three points of each chevron and reach
    past neither end, so this family's outline is its chevrons -- which is
    what lets `path` and the corridor arithmetic describe one drawing in
    two notations without either being an approximation of the other."""
    for width, height in CANVASES:
        assert outline(width, height) == marks(width, height)


def test_every_chevron_is_three_points_and_stands_inside_the_canvas() -> None:
    for width, height in CANVASES:
        for mark in marks(width, height):
            assert len(mark) == 3
            for x, y in mark:
                assert 0.0 <= x <= width
                assert 0.0 <= y <= height


def test_the_two_columns_stand_against_opposite_edges() -> None:
    columns = waypoints(1200.0, 1200.0)
    assert max(x for mark in columns.left for x, _y in mark) < 600.0
    assert min(x for mark in columns.right for x, _y in mark) > 600.0


def test_a_chevrons_tip_hangs_below_its_own_arms() -> None:
    """The direction the drawing reads in: the arms open toward the top of
    the page and the point is under them."""
    for mark in marks(1200.0, 1200.0):
        (_arm_x, arm_y), (_tip_x, tip_y), (_end_x, end_y) = mark
        assert arm_y == end_y
        assert tip_y > arm_y


def test_waypoints_rejects_a_non_positive_canvas() -> None:
    for width, height in ((0.0, 100.0), (100.0, -1.0)):
        with pytest.raises(ValueError, match="positive"):
            waypoints(width, height)


def test_path_rejects_a_non_positive_canvas() -> None:
    with pytest.raises(ValueError, match="positive"):
        path(-1.0, 100.0)


def test_the_outline_rejects_a_non_positive_canvas() -> None:
    with pytest.raises(ValueError, match="positive"):
        outline(100.0, 0.0)


@pytest.mark.parametrize(
    ("width", "height"),
    [(4000.0, 100.0), (100.0, 4000.0), (1.0, 1.0), (7.0, 3.0), (3.0, 7.0)],
)
def test_no_canvas_leaves_either_column_with_nothing_to_draw(
    width: float, height: float
) -> None:
    """A family that returned no geometry would report no corridor either,
    and every block on that page would be placed against a drawing that is
    not there. `_arm_tops` says why no canvas can do that; these are the
    extremes of aspect ratio, both ways up, that say it is so."""
    columns = waypoints(width, height)
    assert columns.left
    assert columns.right


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


def test_the_clearance_is_a_slanted_segments_own_reach_plus_a_gutter() -> None:
    """This family's clearance is the first in the package that is not one
    stroke width, and the arithmetic is what makes it so: paint reaches
    half a stroke perpendicular to a segment, and an arm standing 50
    degrees off the horizontal therefore reaches `0.5 / sin(50)` of a
    stroke along the axis a corridor is measured on."""
    arm_angle = 90.0 - _TIP_HALF_ANGLE_DEGREES
    clearance = CLEARANCE_STROKE_WIDTHS
    assert clearance == pytest.approx(0.5 / math.sin(math.radians(arm_angle)) + 0.5)
    assert motifs.BRACKET.clearance_stroke_widths < clearance
    assert motifs.LATTICE.clearance_stroke_widths < clearance


def test_a_word_keeps_half_a_stroke_from_the_paint_at_every_row() -> None:
    """What that figure buys, measured rather than asserted: at every row
    the drawing crosses, the painted edge of the arm nearest the middle of
    the page stays at least half a stroke from where a word may start. A
    family declaring one stroke width here would keep a third of that.
    """
    ratio = HEAVIEST_RATIO
    width, height = 1200.0, 1200.0
    stroke = ratio * _short_side(width, height)
    across = stroke / 2 / math.sin(math.radians(90.0 - _TIP_HALF_ANGLE_DEGREES))
    for (_arm_x, _arm_y), (tip_x, tip_y), (end_x, end_y) in waypoints(
        width, height
    ).left:
        for step in range(21):
            row = end_y + (tip_y - end_y) * step / 20
            centre = end_x + (tip_x - end_x) * (row - end_y) / (tip_y - end_y)
            left, _right = motifs.safe_margins(
                "chevrons", width, height, ratio=ratio, top=row, bottom=row
            )
            assert left - (centre + across) >= stroke / 2 - 1e-9


def test_the_safe_area_clears_the_columns_at_every_canvas() -> None:
    """The property the margins exist for: no part of the drawing reaches
    into the corridor a word is allowed to start in."""
    ratio = HEAVIEST_RATIO
    for width, height in CANVASES:
        stroke = ratio * min(width, height)
        left_margin, right_margin = motifs.safe_margins(
            "chevrons", width, height, ratio=ratio
        )
        columns = waypoints(width, height)
        for x, _y in (point for mark in columns.left for point in mark):
            assert x + stroke / 2 <= left_margin
        for x, _y in (point for mark in columns.right for point in mark):
            assert x - stroke / 2 >= width - right_margin


def test_the_safe_area_is_the_columns_own_reach_and_nothing_more() -> None:
    """A margin derived from a point the drawing does not reach is a
    control that cannot fail, and one wider than the drawing costs a
    composition width for nothing. Each margin sits exactly one clearance
    outside the deepest point of its own column, and that depth is
    `REACH`."""
    ratio = 0.0204
    for width, height in CANVASES:
        short = min(width, height)
        clearance = ratio * short * CLEARANCE_STROKE_WIDTHS
        left_margin, right_margin = motifs.safe_margins(
            "chevrons", width, height, ratio=ratio
        )
        assert left_margin == pytest.approx(REACH * short + clearance)
        assert right_margin == pytest.approx(REACH * short + clearance)


def test_the_charter_draws_an_arm_four_times_its_own_width() -> None:
    """`brand/chevrons/brand.json::motif._width_ratio` says the weight is
    the one that keeps a chevron an angle rather than a wedge: an arm is
    half a span across and a rise down, and the stroke is a quarter of
    that length. Held to the arithmetic here, so the charter's own sentence
    and this module cannot drift apart."""
    named = brand.SHIPPED_DIR / "chevrons" / brand.SHIPPED_FILE
    charter = brand.charter(ROOT, named)
    arm = math.hypot(_SPAN / 2, _RISE)
    assert charter["motif"][brand.MOTIF_FAMILY] == "chevrons"
    assert charter["motif"]["width_ratio"] * 4 == pytest.approx(arm, abs=1e-5)
