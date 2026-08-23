"""Anonymous's ribbon: pin the properties that make it hers, not the bytes.

A path string that happens to equal a stored literal would pass for a wrong
ribbon and fail for a better one -- see `ribbon.py`'s own docstring for the
defect this replaces (four bare `<circle>` elements) and what the reference
poster actually shows. What is pinned here instead is what task 1's own
brief asked to be provable: one continuous stroke rather than disjoint
pieces, a stroke that leaves the frame, a width that tracks the shorter
side, and a shape that adapts to aspect ratio rather than stretching. Each
of the four has its own test, named so a mutation report can point at it.
"""

from __future__ import annotations

import re

import pytest

from convener_ops.paths import repo_root
from convener_ops.ribbon import (
    Point,
    Waypoints,
    _arc_points,
    _catmull_rom,
    _connector,
    _edge_crossing_half_angle,
    _edge_gap,
    _fmt,
    _short_side,
    ribbon_path,
    ribbon_stroke_colour,
    ribbon_stroke_width,
    ribbon_width_ratio,
    waypoints,
)

ROOT = repo_root()


def _numbers(text: str) -> list[float]:
    """Every number in an SVG path fragment, in the order it appears."""
    return [float(match) for match in re.findall(r"-?\d+\.?\d*", text)]


def _points(text: str) -> list[Point]:
    """Every `(x, y)` pair in an SVG path fragment.

    Valid because this module only ever emits `M x y` and
    `C x1 y1 x2 y2 x y` -- every number belongs to a coordinate pair, never
    a lone flag or radius the way an `A` (arc) command would need.
    """
    numbers = _numbers(text)
    assert len(numbers) % 2 == 0, "an odd count means a non-coordinate number leaked in"
    return list(zip(numbers[0::2], numbers[1::2], strict=True))


# ---------------------------------------------------------------------------
# data/brand.json wiring -- the colour and ratio are read, never hand-typed
# ---------------------------------------------------------------------------


def test_ribbon_stroke_colour_reads_brand_json() -> None:
    assert ribbon_stroke_colour(ROOT) == "#012765"


def test_ribbon_width_ratio_reads_brand_json() -> None:
    # See data/brand.json::motif._ribbon_width_ratio for how this was
    # measured against the reference poster (task 1's correction from the
    # 0.0075 the field held before, which draws a stroke a third as thick).
    assert ribbon_width_ratio(ROOT) == 0.024


# ---------------------------------------------------------------------------
# Property 1: stroke width tracks the shorter side
# ---------------------------------------------------------------------------


def test_stroke_width_tracks_the_shorter_side_not_the_longer_one() -> None:
    # Same short side (1000), wildly different long side: the width must
    # not move. A `max` in place of `min` inside `ribbon_stroke_width`
    # breaks exactly this -- confirmed by mutating it and watching this
    # test fail (see the task 1 report).
    square = ribbon_stroke_width(1000, 1000, ratio=0.02)
    tall = ribbon_stroke_width(1000, 5000, ratio=0.02)
    wide = ribbon_stroke_width(5000, 1000, ratio=0.02)
    assert square == tall == wide == pytest.approx(20.0)


def test_stroke_width_scales_with_the_short_side_when_it_changes() -> None:
    small = ribbon_stroke_width(1000, 1000, ratio=0.02)
    big = ribbon_stroke_width(2000, 2000, ratio=0.02)
    assert big == pytest.approx(2 * small)


def test_stroke_width_rejects_a_non_positive_canvas() -> None:
    with pytest.raises(ValueError, match="positive"):
        ribbon_stroke_width(0, 100, ratio=0.02)
    with pytest.raises(ValueError, match="positive"):
        ribbon_stroke_width(100, -1, ratio=0.02)


# ---------------------------------------------------------------------------
# Property 2: the shape adapts to aspect ratio rather than being stretched
# ---------------------------------------------------------------------------


def test_left_motif_is_unaffected_by_the_long_side() -> None:
    # The left motif is anchored to the left edge and the top-to-bottom
    # travel of the page; nothing about it should read `width` at all once
    # `height` (here, also the short side) is fixed. Changing `sx()` inside
    # `waypoints` to divide by `width` instead of the short side breaks
    # exactly this -- confirmed by mutating it and watching this test fail.
    square = waypoints(1000, 1000)
    banner = waypoints(6000, 1000)
    assert square.left_top_entry == banner.left_top_entry
    assert square.left_top_exit == banner.left_top_exit
    assert square.left_loop_arc == banner.left_loop_arc
    assert square.left_tail_bulge == banner.left_tail_bulge
    assert square.left_bottom_exit == banner.left_bottom_exit


def test_right_motif_keeps_a_constant_offset_from_the_right_edge() -> None:
    # The right motif is anchored to the right edge instead, so its own
    # x-coordinates *do* move when width changes -- but only by exactly the
    # change in width; its offset *from* that edge must not move.
    square = waypoints(1000, 1000)
    banner = waypoints(6000, 1000)
    for near, far in zip(square.right_loop_arc, banner.right_loop_arc, strict=True):
        assert near[0] - 1000 == pytest.approx(far[0] - 6000)
        assert near[1] == pytest.approx(far[1])
    assert square.right_tail_exit[1] == pytest.approx(banner.right_tail_exit[1])


def test_loop_footprint_scales_with_the_short_side() -> None:
    # The complementary half of the previous two: when the short side
    # itself changes (here, a square doubling in both dimensions), the
    # loop's own size must scale with it -- proving the radius is a
    # fraction of the short side, not a fixed pixel count that would leave
    # the loop the same size on a poster twice as large. Replacing
    # `sx(_LEFT_LOOP_RADIUS)` with a literal pixel count inside `waypoints`
    # breaks exactly this -- confirmed by mutating it and watching this
    # test fail.
    small = waypoints(1000, 1000)
    big = waypoints(2000, 2000)

    def span(points: list[Point]) -> float:
        xs = [p[0] for p in points]
        return max(xs) - min(xs)

    assert span(big.left_loop_arc) == pytest.approx(2 * span(small.left_loop_arc))
    assert span(big.right_loop_arc) == pytest.approx(2 * span(small.right_loop_arc))


def test_waypoints_rejects_a_non_positive_canvas() -> None:
    with pytest.raises(ValueError, match="positive"):
        waypoints(0, 100)
    with pytest.raises(ValueError, match="positive"):
        waypoints(100, 0)


def test_short_side_is_the_minimum_of_the_two() -> None:
    assert _short_side(300, 700) == 300
    assert _short_side(700, 300) == 300
    assert _short_side(500, 500) == 500


# ---------------------------------------------------------------------------
# Property 3: the stroke leaves the frame -- it is not a closed shape
# inside the canvas, the defect the four bare circles stood in for
# ---------------------------------------------------------------------------


def test_left_loop_touches_the_left_edge_at_entry_and_close() -> None:
    w = waypoints(900, 1200)
    assert w.left_loop_entry[0] == pytest.approx(0.0, abs=1e-9)
    assert w.left_loop_close[0] == pytest.approx(0.0, abs=1e-9)
    # Entry and close are two different points, not the same one twice --
    # otherwise this would be a closed loop sitting inside the canvas,
    # exactly the shape a bare circle already draws.
    assert w.left_loop_entry[1] != pytest.approx(w.left_loop_close[1])


def test_right_loop_touches_the_right_edge_at_entry_and_exit() -> None:
    w = waypoints(900, 1200)
    assert w.right_loop_entry[0] == pytest.approx(900.0)
    assert w.right_loop_exit[0] == pytest.approx(900.0)
    assert w.right_loop_entry[1] != pytest.approx(w.right_loop_exit[1])


def test_right_loop_pokes_past_the_right_edge_as_it_turns() -> None:
    # Matches the reference: the loop does not just graze the edge, it
    # genuinely crosses it before turning back in to start the tail.
    # Flipping the `+` to a `-` in `right_loop_out`'s own formula inside
    # `waypoints` breaks exactly this -- confirmed by mutating it and
    # watching this test fail.
    w = waypoints(900, 1200)
    assert w.right_loop_out[0] > 900.0


def test_edge_gap_stays_outside_the_canvas_except_at_its_two_ends() -> None:
    # The gap between the top-left segment and the loop's own entry: real
    # background shows through here in the reference, which is why this is
    # drawn as a bulge to negative x rather than a straight seam on the
    # edge. Every point this segment passes through must stay at x <= 0.
    start: Point = (0.0, 100.0)
    end: Point = (0.0, 250.0)
    fragment = _edge_gap(start, end, bulge=40.0)
    xs = [p[0] for p in _points(fragment)]
    assert all(x <= 0.0 for x in xs)
    assert min(xs) < 0.0, "a bulge that never goes negative would render as a seam"


def test_connector_never_crosses_back_into_the_canvas_rectangle() -> None:
    # The long invisible span between the two motifs must clear the
    # `[0, width] x [0, height]` rectangle at every point except the exact
    # end it arrives at -- proven per segment in `_connector`'s own
    # docstring. Checked here at three aspect ratios (square, wide banner,
    # tall print) because the margin is computed from `max(width, height)`
    # and a mistake there could easily be safe at one ratio and not another.
    for width, height in [(1000, 1000), (3000, 800), (900, 2600)]:
        start: Point = (width * 0.2, height)
        end: Point = (width, height * 0.1)
        fragment = _connector(start, end, width=width, height=height)
        points = _points(fragment)
        # Every point is outside the rectangle, or sits on `end` itself
        # (the one point this segment is allowed to touch the canvas).
        for x, y in points:
            outside = x <= 0 or x >= width or y <= 0 or y >= height
            assert outside or (x, y) == pytest.approx(end)


def test_ribbon_path_leaves_the_canvas_rectangle() -> None:
    width, height = 900, 1200
    points = _points(ribbon_path(width, height))
    xs = [p[0] for p in points]
    assert min(xs) < 0, "the left gap should bulge past the left edge"
    assert max(xs) > width, "the right loop should turn past the right edge"


# ---------------------------------------------------------------------------
# Property 4: one continuous stroke, not disjoint pieces
# ---------------------------------------------------------------------------


def test_ribbon_path_is_a_single_continuous_subpath() -> None:
    # Exactly one `M` (a single starting point) and no `Z` (nothing closes
    # into a shape) -- the structural difference between "one continuous
    # meandering stroke" and "four bare circles". Splicing a second `M`
    # into the middle of `ribbon_path` (simulating a disjoint second piece)
    # breaks exactly this -- confirmed by mutating it and watching this
    # test fail (see the task 1 report).
    d = ribbon_path(900, 1200)
    commands = d.split("\n")
    moves = [line for line in commands if line.startswith("M")]
    closes = [line for line in commands if line.strip().upper().startswith("Z")]
    assert len(moves) == 1
    assert closes == []


def test_ribbon_path_has_only_cubic_segments_after_the_move() -> None:
    d = ribbon_path(900, 1200)
    commands = d.split("\n")
    assert commands[0].startswith("M")
    assert all(line.startswith("C") for line in commands[1:])
    # A real ribbon, not a two-segment stub: both loops, both tails and the
    # long connector between them all contribute cubic segments.
    assert len(commands) > 15


def test_ribbon_path_starts_where_waypoints_says_it_does() -> None:
    # Not a pin on the full string -- a pin on the one relationship that
    # must hold between the two public entry points this module offers.
    width, height = 900, 1200
    d = ribbon_path(width, height)
    first_line = d.split("\n", 1)[0]
    x, y = _numbers(first_line)
    assert (x, y) == pytest.approx(waypoints(width, height).left_top_entry, abs=0.01)


def test_ribbon_path_rejects_a_non_positive_canvas() -> None:
    with pytest.raises(ValueError, match="positive"):
        ribbon_path(0, 100)


# ---------------------------------------------------------------------------
# The small pure helpers underneath, each proved directly
# ---------------------------------------------------------------------------


def test_edge_crossing_half_angle_matches_the_geometry() -> None:
    # A circle of radius 1 centred 0.5 from the boundary crosses it at
    # +/-60 degrees from the axis pointing at that boundary: cos(60) = 0.5.
    assert _edge_crossing_half_angle(0.5, 1.0) == pytest.approx(60.0)
    assert _edge_crossing_half_angle(0.0, 1.0) == pytest.approx(90.0)


def test_edge_crossing_half_angle_rejects_a_circle_that_never_crosses() -> None:
    with pytest.raises(ValueError, match="crosses"):
        _edge_crossing_half_angle(1.0, 1.0)  # tangent, not a real crossing
    with pytest.raises(ValueError, match="crosses"):
        _edge_crossing_half_angle(2.0, 1.0)  # centre further than the radius reaches
    with pytest.raises(ValueError, match="crosses"):
        _edge_crossing_half_angle(-1.0, 1.0)


def test_arc_points_samples_the_requested_endpoints() -> None:
    points = _arc_points((0.0, 0.0), 10.0, 0.0, 90.0, 4)
    assert points[0] == pytest.approx((10.0, 0.0))
    assert points[-1] == pytest.approx((0.0, 10.0))
    assert len(points) == 5


def test_arc_points_rejects_too_few_steps() -> None:
    with pytest.raises(ValueError, match="step"):
        _arc_points((0.0, 0.0), 10.0, 0.0, 90.0, 0)


def test_catmull_rom_keeps_a_straight_line_straight() -> None:
    # Collinear points are the sharpest check available: any tangent
    # miscalculation shows up as a control point off the line.
    line = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)]
    for c1, c2, end in _catmull_rom(line):
        assert c1[1] == pytest.approx(0.0)
        assert c2[1] == pytest.approx(0.0)
        assert end[1] == pytest.approx(0.0)


def test_catmull_rom_rejects_a_single_point() -> None:
    with pytest.raises(ValueError, match="two points"):
        _catmull_rom([(0.0, 0.0)])


def test_fmt_trims_trailing_zeros() -> None:
    assert _fmt(1.20) == "1.2"
    assert _fmt(1.0) == "1"
    assert _fmt(0.5) == "0.5"


def test_fmt_never_prints_negative_zero() -> None:
    # -0.001 rounds to "-0.00" at two decimal places; a literal "-0" in an
    # SVG path is harmless to a renderer but is a wart no coordinate here
    # should ever produce.
    assert _fmt(-0.001) == "0"


def test_waypoints_is_a_plain_dataclass_with_the_documented_shape() -> None:
    # Guards the public shape `ribbon_path` and any future consumer (task
    # 2's composition) both rely on -- a field renamed or retyped here
    # would not otherwise fail loudly.
    w = waypoints(400, 400)
    assert isinstance(w, Waypoints)
    assert w.left_loop_arc[0] == w.left_loop_entry
    assert w.left_loop_arc[-1] == w.left_loop_close
    assert w.right_loop_arc[0] == w.right_loop_entry
    assert w.right_loop_arc[-1] == w.right_loop_exit
