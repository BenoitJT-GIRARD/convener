"""The `steps` family: pin what makes it a line, and what makes it fit.

The discipline `motifs/test_ribbon.py` states for the ribbon and
`motifs/test_bracket.py` repeats for the bracket: a path string held
against a stored literal would pass for a wrong drawing and fail for a
better one, so what is pinned here is what has to be provable. This family
is measured against no artwork -- it is nobody's mark -- so what stands in
for the artwork is the set of measurements each of its figures was fixed
by, and every one of them is checked here against the thing it was read
off rather than against itself.

The rule that no family but the ribbon draws a curve is not here. It
belongs to every family a charter may name, so `test_registry.py` holds it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Final

import pytest

from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, brand_templates, formats, motifs
from convener_ops.publication.motifs import bracket
from convener_ops.publication.motifs.steps import (
    _CONTENT_TOP,
    _NEAR,
    _OVERHANG,
    _RIGHT_LEVELS,
    _RISERS,
    _STEP,
    CLEARANCE_STROKE_WIDTHS,
    REACH,
    _fmt,
    _ledge_x,
    _short_side,
    line,
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
#: Read off the charters below rather than trusted, because it is what
#: `_OVERHANG` has to clear: the joining span carries half a stroke, and a
#: span nearer the page than that puts paint on a page it is not drawn on.
HEAVIEST_RATIO: Final = 0.03


def _charters() -> tuple[Path, ...]:
    """Every charter this repository holds: the two an instance owns, and
    every one the product ships. The same set `cli._template_charters`
    renders, read the same way rather than listed here."""
    return (
        brand.INSTANCE_PATH,
        Path("examples") / "the-example-collective" / brand.INSTANCE_PATH,
        *brand.shipped(ROOT),
    )


def _segments(width: float, height: float) -> list[tuple[tuple[float, float], ...]]:
    """Every straight segment of the stroke, in the order it is drawn."""
    return [pair for pair in pairwise(line(width, height))]


# ---------------------------------------------------------------------------
# The measurements each figure was fixed by
# ---------------------------------------------------------------------------


def test_the_heaviest_stroke_is_the_one_a_charter_here_actually_draws() -> None:
    """The bound `_OVERHANG` is set against, read off the charters rather
    than asserted. A charter committed at a heavier weight moves this
    figure, and the drawing has to be re-measured against it rather than
    the figure being edited to agree."""
    weights = {
        rel.as_posix(): float(
            json.loads((ROOT / rel).read_text(encoding="utf-8"))["motif"]["width_ratio"]
        )
        for rel in _charters()
    }
    assert max(weights.values()) == HEAVIEST_RATIO, (
        f"the charters here draw at {weights}, and this family's own "
        f"overhang is measured against {HEAVIEST_RATIO}"
    )


#: How much of the announcement a drawing crossing its registration rows
#: may take: the "what to expect" column's own indent, less the gutter
#: the slot keeps from the strip it sits in and the slot's own design
#: side. Read off the page rather than typed, because it is what
#: `_RISERS` is measured against.
SLOT_ROOM: Final = (
    brand_templates._ANNOUNCEMENT_COLUMN.indent
    - brand_templates._ANNOUNCEMENT_GUTTER
    - brand_templates._ANNOUNCEMENT_SLOT_SIDE
)


def test_sixteen_levels_is_the_fewest_the_announcement_leaves_room_for() -> None:
    """What `_RISERS` is fixed by, and it is not the ground a margin can
    spare. This drawing crosses the rows the announcement sets its
    registration slot in, and that slot stands on the far side of it with
    the "what to expect" column beyond. A ledge and its clearance
    therefore have `SLOT_ROOM` of that page, and sixteen levels is the
    fewest -- the deepest ledge -- that fit at the heaviest charter here.
    """
    side = formats.SQUARE
    room = HEAVIEST_RATIO * side.width * CLEARANCE_STROKE_WIDTHS
    assert _RISERS == 16
    assert side.width / _RISERS + room < SLOT_ROOM
    assert side.width / (_RISERS - 1) + room >= SLOT_ROOM, (
        f"{_RISERS - 1} levels would lay a ledge "
        f"{side.width / (_RISERS - 1):.1f} units deep on that page and the "
        f"slot would still clear the column, so {_RISERS} is not the fewest "
        "this drawing may have"
    )


def test_the_brackets_own_ground_is_the_looser_of_the_two_bounds() -> None:
    """The bound every other family here is measured against, checked so
    that a page which stopped asking for the slot would not leave this
    drawing unbounded: a ledge still reaches less far than the product's
    own mark does."""
    deepest = (1.0 + bracket._EDGE_STANDOFF + 1.0) * bracket._OUTER_HALF_WIDTH
    assert deepest > REACH


def test_a_ledge_and_a_riser_are_one_unit_read_against_two_axes() -> None:
    """`_STEP` is the drawing's only unit: a ledge is that fraction of the
    shorter side and a riser that fraction of the height. On the square the
    announcement is drawn on the two are the same length."""
    step = _STEP
    assert step == pytest.approx(1.0 / _RISERS)
    for width, height in CANVASES:
        short = _short_side(width, height)
        flight = waypoints(width, height).left
        rows = sorted({y for _x, y in flight if y >= 0})
        assert rows[0] == pytest.approx(_STEP * height)
        depths = sorted({x for x, _y in flight})
        assert depths[0] == pytest.approx(_NEAR)
        assert depths[-1] == pytest.approx(_STEP * short)
        assert len(depths) == 2
    side = formats.SQUARE
    assert _STEP * side.width == pytest.approx(_STEP * side.height)


def test_the_flight_crosses_the_page_from_the_top_edge_to_the_bottom() -> None:
    """What makes this a line across a page rather than a mark in a
    margin: the left flight enters through the top edge and leaves through
    the bottom one, in `_RISERS` levels exactly."""
    for width, height in CANVASES:
        flight = waypoints(width, height).left
        assert flight[0][1] < 0.0
        assert flight[-1][1] == pytest.approx(height)
        risers = [
            pair
            for pair in pairwise(flight)
            if pair[0][0] == pytest.approx(pair[1][0]) and pair[0][1] != pair[1][1]
        ]
        assert len(risers) == _RISERS


def test_the_near_end_of_every_ledge_sits_on_the_page_edge() -> None:
    """What `_NEAR` is fixed by, stated: the announcement's registration
    slot takes the free strip nearest the left edge over rows it shares
    with this drawing, and a line standing off that edge leaves the slot
    that gap to sit in."""
    assert _NEAR == 0.0
    for width, height in CANVASES:
        flights = waypoints(width, height)
        assert min(x for x, _y in flights.left) == pytest.approx(0.0)
        assert max(x for x, _y in flights.right) == pytest.approx(width)


def test_the_registration_slot_gets_the_whole_page_east_of_the_drawing() -> None:
    """The result on the page the figure was read off. The strip nearest
    the left edge over the register's own rows begins where the drawing
    ends, so the slot is drawn at its own design size rather than at
    whatever a gutter allows."""
    side = formats.SQUARE
    corridor = motifs.free_spans(
        "steps",
        side.width,
        side.height,
        ratio=HEAVIEST_RATIO,
        top=brand_templates._ANNOUNCEMENT_REGISTER_TOP,
        bottom=brand_templates._ANNOUNCEMENT_SLOT_TOP
        + brand_templates._ANNOUNCEMENT_SLOT_SIDE,
    )
    assert len(corridor) == 1
    assert corridor[0][1] == side.width

    canvas = brand_templates._Canvas(
        family="steps", width=side.width, height=side.height, ratio=HEAVIEST_RATIO
    )
    drawn = brand_templates._register_values(canvas)
    assert float(drawn["slot_side"]) == pytest.approx(
        brand_templates._ANNOUNCEMENT_SLOT_SIDE
    )
    edge = float(drawn["slot_x"]) + float(drawn["slot_side"])
    assert edge < brand_templates._ANNOUNCEMENT_COLUMN.indent, (
        f"the slot runs to {edge:.1f} and the column beside it begins at "
        f"{brand_templates._ANNOUNCEMENT_COLUMN.indent}, so the two are set "
        "on top of each other -- which nothing in this repository measures"
    )


def test_a_flight_standing_off_that_edge_is_refused_outright(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the figure, and the reason it is a bound rather
    than a preference: the same drawing moved one ledge inboard leaves the
    announcement a strip too narrow to drop a code into, and the page says
    so instead of drawing a stamp."""
    side = formats.SQUARE
    inboard = _STEP * side.width

    def shifted(
        width: float, height: float
    ) -> tuple[tuple[tuple[float, float], ...], ...]:
        return tuple(
            tuple((x + inboard, y) for x, y in run) for run in outline(width, height)
        )

    monkeypatch.setitem(
        motifs.FAMILIES,
        "steps-inboard",
        replace(motifs.STEPS, name="steps-inboard", outline=shifted),
    )
    canvas = brand_templates._Canvas(
        family="steps-inboard",
        width=side.width,
        height=side.height,
        ratio=HEAVIEST_RATIO,
    )
    with pytest.raises(ValueError, match="registration slot"):
        brand_templates._register_values(canvas)


def test_the_joining_span_stands_clear_of_the_page_it_crosses() -> None:
    """What `_OVERHANG` is fixed by. The span joining the two flights is
    never painted on the page, so it has to stand further off the top edge
    than the paint it carries -- half the heaviest stroke any charter here
    draws."""
    overhang = _OVERHANG
    assert overhang == pytest.approx(_STEP)
    for width, height in CANVASES:
        assert overhang * height > HEAVIEST_RATIO * _short_side(width, height) / 2
        flights = waypoints(width, height)
        span = (flights.right[-1], flights.left[0])
        assert span[0][1] == pytest.approx(span[1][1])
        assert span[0][1] == pytest.approx(-overhang * height)


def test_the_right_flight_finishes_above_the_content_band() -> None:
    """What `_RIGHT_LEVELS` is read off, and why this drawing is short on
    the right where it crosses the page on the left. `.content` -- the
    "what to expect" copy and the speaker's frame beside it -- is the one
    band on that side of a generated poster set against the clearance
    alone (`visual._motif_content_right_margin`); measured in the pinned
    engine it begins at 0.317 of a square and 0.224 of an A4 print, which
    is the same figure `motifs/test_bracket.py` holds its own right arm
    to."""
    assert _CONTENT_TOP == 0.224
    assert _RIGHT_LEVELS == 3
    assert _RIGHT_LEVELS * _STEP < _CONTENT_TOP
    assert (_RIGHT_LEVELS + 1) * _STEP > _CONTENT_TOP
    for width, height in CANVASES:
        lowest = max(y for _x, y in waypoints(width, height).right)
        assert lowest < _CONTENT_TOP * height, (
            f"the right flight reaches row {lowest:.1f} of a "
            f"{width:.0f}x{height:.0f} page, into a band set against the "
            "clearance alone"
        )


def test_the_right_flight_is_the_opening_of_the_left_flights_own_levels() -> None:
    """One drawing read to two depths, never two: mirrored across the
    page, the right flight is the first levels of the left one."""
    for width, height in CANVASES:
        flights = waypoints(width, height)
        mirrored = [(width - x, y) for x, y in reversed(flights.right)]
        assert mirrored == list(flights.left[: len(mirrored)])
        assert 0 < len(mirrored) < len(flights.left)


# ---------------------------------------------------------------------------
# The drawing adapts to aspect ratio rather than being stretched
# ---------------------------------------------------------------------------


def test_a_ledge_keeps_its_depth_when_only_the_long_side_changes() -> None:
    square = waypoints(1200.0, 1200.0).left
    tall = waypoints(1200.0, 3508.0).left
    assert len({x for x, _y in square}) == len({x for x, _y in tall})
    assert sorted({x for x, _y in square}) == sorted({x for x, _y in tall})


def test_the_flight_always_crosses_the_page_in_the_same_count_of_levels() -> None:
    for width, height in CANVASES:
        rows = sorted({y for _x, y in waypoints(width, height).left if y >= 0})
        assert len(rows) == _RISERS
        assert rows[-1] == pytest.approx(height)


def test_the_drawing_scales_with_the_canvas() -> None:
    small = line(1000.0, 1000.0)
    big = line(2000.0, 2000.0)
    assert len(small) == len(big)
    for (sx, sy), (bx, by) in zip(small, big, strict=True):
        assert bx == pytest.approx(2 * sx)
        assert by == pytest.approx(2 * sy)


# ---------------------------------------------------------------------------
# The drawing itself
# ---------------------------------------------------------------------------


def test_every_corner_is_a_right_angle() -> None:
    """The whole of what "orthogonal" means here, measured: every segment
    is upright or flat, and no two consecutive ones are both."""
    for width, height in CANVASES:
        for (x0, y0), (x1, y1) in _segments(width, height):
            assert x0 == pytest.approx(x1) or y0 == pytest.approx(y1)
        for before, after in pairwise(_segments(width, height)):
            upright = before[0][0] == pytest.approx(before[1][0])
            next_upright = after[0][0] == pytest.approx(after[1][0])
            assert upright != next_upright


def test_the_path_is_one_move_and_a_line_for_every_point_after_it() -> None:
    for width, height in CANVASES:
        commands = [text.split()[0] for text in path(width, height).splitlines()]
        assert commands[0] == "M"
        assert set(commands[1:]) == {"L"}
        assert len(commands) == len(line(width, height))


def test_the_outline_is_one_run_and_it_is_the_line() -> None:
    """A line, not a field: `lattice.outline` hands back one run per mark
    and `bracket.outline` two, and this drawing is a single stroke that
    happens to leave the page and come back."""
    for width, height in CANVASES:
        drawn = outline(width, height)
        assert len(drawn) == 1
        assert drawn[0] == line(width, height)


def test_the_line_leaves_the_page_only_over_the_top_edge() -> None:
    """Every point that is not on the page is above it, which is what
    makes the joining span invisible rather than a stroke somebody has to
    account for."""
    for width, height in CANVASES:
        for x, y in line(width, height):
            assert 0.0 <= x <= width
            assert y <= height
            if y < 0.0:
                assert y == pytest.approx(-_OVERHANG * height)


def test_the_two_flights_stand_against_opposite_edges() -> None:
    flights = waypoints(1200.0, 1200.0)
    assert max(x for x, _y in flights.left) < 600.0
    assert min(x for x, _y in flights.right) > 600.0


def test_a_riser_alternates_between_the_two_depths() -> None:
    assert _ledge_x(1, 150.0) == 150.0
    assert _ledge_x(2, 150.0) == _NEAR
    assert _ledge_x(3, 150.0) == 150.0


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
def test_no_canvas_leaves_either_flight_with_nothing_to_draw(
    width: float, height: float
) -> None:
    """A family that returned no geometry would report no corridor either,
    and every block on that page would be placed against a drawing that is
    not there. Both flights are a whole number of levels of the page
    itself, so there is no canvas that empties either; these are the
    extremes of aspect ratio, both ways up, that say it is so."""
    flights = waypoints(width, height)
    assert flights.left
    assert flights.right


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


def test_the_safe_area_clears_the_line_at_every_canvas() -> None:
    """The property the margins exist for: no painted part of the line
    reaches into the corridor a word is allowed to start in. Exact for
    this family, since a straight segment reaches past neither of its ends
    and every corner is square."""
    ratio = HEAVIEST_RATIO
    for width, height in CANVASES:
        stroke = ratio * _short_side(width, height)
        left_margin, right_margin = motifs.safe_margins(
            "steps", width, height, ratio=ratio
        )
        flights = waypoints(width, height)
        for x, _y in flights.left:
            assert x + stroke / 2 <= left_margin
        for x, _y in flights.right:
            assert x - stroke / 2 >= width - right_margin


def test_the_safe_area_is_the_lines_own_reach_and_nothing_more() -> None:
    """A margin derived from a point the drawing does not reach is a
    control that cannot fail, and one wider than the drawing costs a
    composition width for nothing. Each margin sits exactly one clearance
    outside the deepest point of its own flight, and that depth is
    `REACH`."""
    ratio = 0.0204
    for width, height in CANVASES:
        short = _short_side(width, height)
        clearance = ratio * short * CLEARANCE_STROKE_WIDTHS
        left_margin, right_margin = motifs.safe_margins(
            "steps", width, height, ratio=ratio
        )
        assert left_margin == pytest.approx(REACH * short + clearance)
        assert right_margin == pytest.approx(REACH * short + clearance)


def test_the_charter_draws_a_ledge_five_times_its_own_width() -> None:
    """`assets/brand/steps/brand.json::motif._width_ratio` says the weight is the
    one that keeps a ledge a ledge rather than a block: a ledge is one step
    deep, and the stroke is a fifth of that. Held to the arithmetic here,
    so the charter's own sentence and this module cannot drift apart."""
    named = brand.SHIPPED_DIR / "steps" / brand.SHIPPED_FILE
    charter = brand.charter(ROOT, named)
    assert charter["motif"][brand.MOTIF_FAMILY] == "steps"
    assert charter["motif"]["width_ratio"] * 5 == pytest.approx(_STEP)
