"""The `lattice` family: pin what makes it a field, and what makes it fit.

The discipline `motifs/test_ribbon.py` states for the ribbon and
`motifs/test_bracket.py` repeats for the bracket: a path string held
against a stored literal would pass for a wrong drawing and fail for a
better one, so what is pinned here is what has to be provable. This family
is measured against no artwork -- it is the one drawing this product has
that is nobody's mark -- so what stands in for the artwork is the set of
measurements each of its four figures was fixed by, and every one of them
is checked here against the thing it was read off rather than against
itself.

The rule that no family but the ribbon draws a curve is not here. It
belongs to every family a charter may name, so `test_registry.py` holds it.
"""

from __future__ import annotations

import json
import re
from itertools import pairwise
from pathlib import Path
from typing import Final

import pytest

from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, brand_templates, formats, motifs
from convener_ops.publication.motifs import bracket
from convener_ops.publication.motifs.lattice import (
    _BOTTOM,
    _COLUMNS,
    _GUTTER_STEPS,
    _MARK_STEPS,
    _OFFSET_STEPS,
    _RIGHT_BOTTOM,
    _ROW_STEPS,
    _STEP,
    CLEARANCE_STROKE_WIDTHS,
    REACH,
    Point,
    _fmt,
    _row_tops,
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
#: Read off the charters rather than typed, because it is the figure
#: `_STEP` is bounded from below by: a charter committed at a heavier
#: stroke closes this field's own gaps, and this is what says so.
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


# ---------------------------------------------------------------------------
# The measurements the four figures were fixed by
# ---------------------------------------------------------------------------


def _charters() -> tuple[Path, ...]:
    """Every charter this repository holds: the two an instance owns, and
    every one the product ships. The same set `cli._template_charters`
    renders, read the same way rather than listed here."""
    return (
        brand.INSTANCE_PATH,
        Path("examples") / "the-example-collective" / brand.INSTANCE_PATH,
        *brand.shipped(ROOT),
    )


def test_the_heaviest_stroke_is_the_one_a_charter_here_actually_draws() -> None:
    """The bound `_STEP` is set against, read off the charters rather than
    asserted. A charter committed at a heavier weight moves this figure,
    and the field has to be re-measured against it rather than the figure
    being edited to agree."""
    weights = {
        rel.as_posix(): float(
            json.loads((ROOT / rel).read_text(encoding="utf-8"))["motif"]["width_ratio"]
        )
        for rel in _charters()
    }
    assert max(weights.values()) == HEAVIEST_RATIO, (
        f"the charters here draw at {weights}, and this family's own step "
        f"is measured against {HEAVIEST_RATIO}"
    )


def test_a_mark_is_one_step_long_and_a_column_one_step_from_the_next() -> None:
    """The field's one unit, carried onto a canvas. Every length across or
    down the page is a multiple of it, which is what gives the texture one
    grain rather than a horizontal decision and a vertical one."""
    width, height = 1200.0, 1200.0
    step = _STEP * _short_side(width, height)
    row = waypoints(width, height).left[:_COLUMNS]

    for (_x0, y0), (_x1, y1) in row:
        assert y1 - y0 == pytest.approx(_MARK_STEPS * step)
    for (before, _end), (after, _also) in pairwise(row):
        assert after[0] - before[0] == pytest.approx(step)


def test_alternate_rows_are_shifted_half_a_step_and_give_up_a_column() -> None:
    """The whole of what makes this a lattice rather than a set of columns
    -- and the reason a shifted row is one mark shorter: the panel reaches
    the same depth on every row rather than bulging on alternate ones."""
    step = _STEP * 1200.0
    left = waypoints(1200.0, 1200.0).left
    first = left[:_COLUMNS]
    second = left[_COLUMNS : _COLUMNS + _COLUMNS - 1]

    assert len(second) == _COLUMNS - 1
    assert second[0][0][0] - first[0][0][0] == pytest.approx(_OFFSET_STEPS * step)
    assert max(x for (x, _y), _end in first) == pytest.approx(
        max(x for (x, _y), _end in second) + _OFFSET_STEPS * step
    )


def test_rows_stand_two_steps_apart_down_the_page() -> None:
    step = _STEP * 1200.0
    tops = _row_tops(1200.0, 1200.0, _BOTTOM)
    assert len(tops) > 1
    for before, after in pairwise(tops):
        assert after - before == pytest.approx(_ROW_STEPS * step)


def test_the_field_stays_a_field_at_the_heaviest_charter_here() -> None:
    """What `_STEP` is bounded from below by. A mark one step long, painted
    at the heaviest weight any charter here carries with a round cap at
    each end, has to leave a gap to the next mark down its column -- and
    the figure chosen leaves a third of the mark's own length. Without
    this bound the field closes into a rule and stops being a texture.
    """
    gap = (_ROW_STEPS - _MARK_STEPS) * _STEP - HEAVIEST_RATIO
    assert gap > 0, (
        f"at {HEAVIEST_RATIO} of the shorter side a mark's painted ends "
        "meet the next mark's, and the column is a rule rather than a field"
    )
    assert gap == pytest.approx(_MARK_STEPS * _STEP / 3, abs=0.0005)


def test_the_field_asks_for_no_more_ground_than_the_bracket_already_does() -> None:
    """What `_COLUMNS` is bounded from above by: the deepest drawing this
    product already ships. A composition gives up no more room to a charter
    naming this family than to one naming the product's own mark -- and one
    column more would ask for more.
    """
    deepest = (1.0 + bracket._EDGE_STANDOFF + 1.0) * bracket._OUTER_HALF_WIDTH
    assert deepest > REACH
    assert deepest < (_GUTTER_STEPS + _COLUMNS) * _STEP, (
        "a further column would still fit inside the bracket's own reach, "
        f"so {_COLUMNS} is not the most this field may have"
    )


def test_the_field_keeps_one_gutter_from_the_left_the_right_and_the_top() -> None:
    """Half a step from every edge it meets, which is what makes the
    texture read as one thing rather than as three decisions."""
    for width, height in CANVASES:
        gutter = _GUTTER_STEPS * _STEP * _short_side(width, height)
        field = waypoints(width, height)
        assert min(x for mark in field.left for x, _y in mark) == pytest.approx(gutter)
        assert width - max(x for mark in field.right for x, _y in mark) == (
            pytest.approx(gutter)
        )
        assert min(y for mark in marks(width, height) for _x, y in mark) == (
            pytest.approx(gutter)
        )


def test_the_left_panel_stops_above_the_announcements_registration_slot() -> None:
    """One of the two pages `_BOTTOM` is read off. The announcement takes
    the free strip nearest the left edge for its slot, and a field standing
    off that edge leaves a strip a gutter wide there -- which
    `brand_templates._ANNOUNCEMENT_SLOT_FLOOR` refuses rather than drawing
    a slot nobody could drop a code into. So the field finishes above those
    rows and the slot gets the whole page.
    """
    side = formats.SQUARE
    lowest = max(y for mark in marks(side.width, side.height) for _x, y in mark)
    assert lowest < brand_templates._ANNOUNCEMENT_REGISTER_TOP

    corridor = motifs.free_spans(
        "lattice",
        side.width,
        side.height,
        ratio=HEAVIEST_RATIO,
        top=brand_templates._ANNOUNCEMENT_REGISTER_TOP,
        bottom=brand_templates._ANNOUNCEMENT_SLOT_TOP
        + brand_templates._ANNOUNCEMENT_SLOT_SIDE,
    )
    assert corridor == ((0.0, side.width),)


#: The row the announcement's `.content` band begins at, as a fraction of
#: the page, on the format where it begins earliest. The same measurement
#: `motifs/test_bracket.py` holds its own right arm to: 0.317 of the
#: square, 0.224 of the A4 print, and the banner's wide derivation has no
#: such band at all. That band is the one thing on the right of the page
#: that does not read a family's own margin -- it reads the clearance alone
#: (`visual._motif_content_right_margin`) -- so a drawing on that side has
#: to finish above it.
CONTENT_BEGINS: Final = 0.224


def test_the_right_panel_finishes_above_the_content_band() -> None:
    """What `_RIGHT_BOTTOM` is read off, and why this field is short on the
    right where it runs the page on the left. Held at every canvas, because
    the fraction is of the height and the rows are a grid in short sides:
    which row is the last one is a property of the aspect ratio.
    """
    assert _RIGHT_BOTTOM < CONTENT_BEGINS
    for width, height in CANVASES:
        lowest = max(y for mark in waypoints(width, height).right for _x, y in mark)
        assert lowest <= _RIGHT_BOTTOM * height
        assert lowest < CONTENT_BEGINS * height, (
            f"the right panel reaches row {lowest:.1f} of a "
            f"{width:.0f}x{height:.0f} page, into a band set against the "
            "clearance alone"
        )


def test_the_right_panel_is_the_opening_of_the_left_panels_own_grid() -> None:
    """One texture read to two depths, never two drawings: every row of the
    right panel sits on a row of the left."""
    for width, height in CANVASES:
        field = waypoints(width, height)
        left_rows = sorted({y for mark in field.left for _x, y in mark})
        right_rows = sorted({y for mark in field.right for _x, y in mark})
        assert right_rows == left_rows[: len(right_rows)]
        assert 0 < len(right_rows) < len(left_rows)


# ---------------------------------------------------------------------------
# The field adapts to aspect ratio rather than being stretched
# ---------------------------------------------------------------------------


def test_the_grain_is_unaffected_by_the_long_side() -> None:
    """Every length in the field tracks the shorter side, so a taller page
    gets more rows of the same texture rather than a stretched one."""
    square = waypoints(1200.0, 1200.0).left
    tall = waypoints(1200.0, 3508.0).left
    assert len(tall) > len(square)
    for square_mark, tall_mark in zip(square, tall, strict=False):
        assert square_mark == tall_mark


def test_the_field_scales_with_the_short_side() -> None:
    small = marks(1000.0, 1000.0)
    big = marks(2000.0, 2000.0)
    assert len(small) == len(big)
    for (small_start, small_end), (big_start, big_end) in zip(small, big, strict=True):
        for (sx, sy), (bx, by) in ((small_start, big_start), (small_end, big_end)):
            assert bx == pytest.approx(2 * sx)
            assert by == pytest.approx(2 * sy)


def test_the_right_panel_keeps_a_constant_offset_from_the_right_edge() -> None:
    wide = waypoints(2000.0, 1000.0).right
    narrow = waypoints(1400.0, 1000.0).right
    assert [2000.0 - x for mark in wide for x, _y in mark] == (
        [1400.0 - x for mark in narrow for x, _y in mark]
    )


# ---------------------------------------------------------------------------
# The drawing itself
# ---------------------------------------------------------------------------


def test_the_path_is_one_move_and_one_line_per_mark() -> None:
    for width, height in CANVASES:
        commands = [line.split()[0] for line in path(width, height).splitlines()]
        assert commands == ["M", "L"] * len(marks(width, height))


def test_the_path_is_drawn_through_exactly_the_marks() -> None:
    drawn = _points(path(1200.0, 630.0))
    every = [point for mark in marks(1200.0, 630.0) for point in mark]
    for (drawn_x, drawn_y), (x, y) in zip(drawn, every, strict=True):
        assert drawn_x == pytest.approx(x, abs=0.01)
        assert drawn_y == pytest.approx(y, abs=0.01)


def test_the_outline_is_the_marks_and_nothing_else() -> None:
    """Straight segments join the two points of each mark and reach past
    neither, so this family's outline is its marks -- which is what lets
    `path` and the corridor arithmetic describe one drawing in two
    notations without either being an approximation of the other."""
    for width, height in CANVASES:
        assert outline(width, height) == marks(width, height)


def test_every_mark_is_two_points_and_stands_inside_the_canvas() -> None:
    for width, height in CANVASES:
        for mark in marks(width, height):
            assert len(mark) == 2
            for x, y in mark:
                assert 0.0 <= x <= width
                assert 0.0 <= y <= height


def test_the_two_panels_stand_against_opposite_edges() -> None:
    field = waypoints(1200.0, 1200.0)
    assert max(x for mark in field.left for x, _y in mark) < 600.0
    assert min(x for mark in field.right for x, _y in mark) > 600.0


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
def test_no_canvas_leaves_either_panel_with_nothing_to_draw(
    width: float, height: float
) -> None:
    """A family that returned no geometry would report no corridor either,
    and every block on that page would be placed against a drawing that is
    not there. `_row_tops` says why no canvas can do that; these are the
    extremes of aspect ratio, both ways up, that say it is so.
    """
    field = waypoints(width, height)
    assert field.left
    assert field.right


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


def test_the_safe_area_clears_the_field_at_every_canvas() -> None:
    """The property the margins exist for: no painted part of the field --
    a mark's centreline, plus half the stroke around it -- reaches into the
    corridor a word is allowed to start in. Exact for this family, since a
    straight segment reaches past neither of its ends.
    """
    ratio = HEAVIEST_RATIO
    for width, height in CANVASES:
        stroke = ratio * min(width, height)
        left_margin, right_margin = motifs.safe_margins(
            "lattice", width, height, ratio=ratio
        )
        field = waypoints(width, height)
        for x, _y in (point for mark in field.left for point in mark):
            assert x + stroke / 2 <= left_margin
        for x, _y in (point for mark in field.right for point in mark):
            assert x - stroke / 2 >= width - right_margin


def test_the_safe_area_is_the_fields_own_reach_and_nothing_more() -> None:
    """A margin derived from a point the drawing does not reach is a control
    that cannot fail, and one wider than the drawing costs a composition
    width for nothing. Each margin sits exactly one clearance outside the
    deepest mark of its own panel, and that depth is `REACH`."""
    ratio = 0.0204
    for width, height in CANVASES:
        short = min(width, height)
        clearance = ratio * short * CLEARANCE_STROKE_WIDTHS
        left_margin, right_margin = motifs.safe_margins(
            "lattice", width, height, ratio=ratio
        )
        assert left_margin == pytest.approx(REACH * short + clearance)
        assert right_margin == pytest.approx(REACH * short + clearance)


def test_the_charter_draws_a_mark_three_times_its_own_width() -> None:
    """`assets/brand/lattice/brand.json::motif._width_ratio` says the weight is
    the one that makes a mark a mark rather than a dot: a mark is one step
    long, and the stroke is a third of that. Held to the arithmetic here,
    so the charter's own sentence and this module cannot drift apart.
    """
    named = brand.SHIPPED_DIR / "lattice" / brand.SHIPPED_FILE
    charter = brand.charter(ROOT, named)
    assert charter["motif"][brand.MOTIF_FAMILY] == "lattice"
    assert charter["motif"]["width_ratio"] * 3 == pytest.approx(_MARK_STEPS * _STEP)
