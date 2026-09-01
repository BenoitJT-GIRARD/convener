"""The `ribbon` family: one continuous meandering stroke, not four circles.

`instance/data/brand.json::motif._family` names the defect this module fixes: the
purple stroke that runs through the designer's own poster
(`instance/data/brand-sources/announcement-template_initial.png`,
gitignored -- it carries a real person's photograph) was stood in for by
three bare circles and arcs everywhere it appeared. A poster built from
circles does not
read as that mark, no matter how faithfully every other measurement passes.
This module drew the ribbon for the generated posters (`visual.py`) alone
until 2026-08-28; `brand_templates.py` sets it in the two downloadable
templates as well now, which is what it took to retire the last of those
circles.

What the reference actually shows
----------------------------------
Traced pixel by pixel against the 1200x1200 reference. The description
that came with it was a starting point to verify, not a given, and two of
its claims did not survive that check: the left curl does not cross its own
tail (it is a near circle open on one side, like the right one), and the
stroke measures 23-33px wide there, not the 0.0075-ratio 9px
`instance/data/brand.json` used to hold (see `motif._width_ratio`).

What does hold up: a single purple stroke, uniform width, round caps, no
fill, that enters and leaves the canvas rather than closing on itself. On the
left it runs almost the full height -- a curve down from the top edge, off
the left edge, back in lower down to trace one open loop, then a long curve
out through the bottom edge. On the right, one large loop sits near the top,
crossing the right edge twice as it turns, then a short tail exits lower
down through the same edge. Neither loop is a full circle and the two sides
are not mirror images of each other.

A pure function, not a fixed drawing
-------------------------------------
Every coordinate below is a fraction of either the canvas's shorter side
(`_short_side`, for anything that must stay round rather than stretch -- a
loop's radius, a stroke's width, how far a curl sits from its edge) or of
its width or height (for how far a point sits along the edge it belongs to,
or how far the S-curve has travelled down the page). Nothing is a literal
pixel count: this same function renders into a square poster, a wide
banner and a high-definition print, and a ribbon that only composes at one
aspect ratio is a ribbon that fails three tasks later. Each loop is a true
arc of a circle -- computed from where that circle crosses the edge it
grazes, not a handful of hand-placed points -- because a circle sampled
densely is what reads as a round curl instead of a kinked polygon.

The path stays one continuous cubic-Bezier subpath -- a single `M`, only `C`
after it, no `Z` -- exactly as the motif is described, even where the
visible stroke leaves the frame. The gaps where the designer's stroke runs off
one edge and back in, and the long invisible span between the left motif and
the right, are drawn as real cubic segments that happen to fall outside the
canvas rectangle; each helper that draws one proves in its own docstring
that every control point stays on the correct side of the boundary, so
nothing stray crosses the visible page at any aspect ratio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

Point = tuple[float, float]


def _short_side(width: float, height: float) -> float:
    """The dimension a round feature's size must track to stay round."""
    return min(width, height)


# ----------------------------------------------------------------------
# Circular arcs: each loop is a real arc of a circle, not hand-placed points
# ----------------------------------------------------------------------


def _edge_crossing_half_angle(offset: float, radius: float) -> float:
    """The half-angle (degrees) between a circle's two crossings of a line.

    A circle of the given `radius`, whose centre sits `offset` from a
    straight boundary along the axis perpendicular to it, crosses that
    boundary at `axis_angle - phi` and `axis_angle + phi` for the `phi` this
    returns -- the standard `cos(phi) = offset / radius` relation, real only
    when the centre is nearer the boundary than the radius reaches.
    """
    if not 0 <= offset < radius:
        raise ValueError("a circle only crosses the line when 0 <= offset < radius")
    return math.degrees(math.acos(offset / radius))


def _arc_points(
    centre: Point, radius: float, start_deg: float, end_deg: float, steps: int
) -> list[Point]:
    """`steps + 1` points evenly spaced by angle along a circular arc.

    Degrees follow the SVG plane (x right, y down): 0 points along +x, 90
    along +y. `start_deg` and `end_deg` may differ by more than 360 or run
    in either direction -- the sweep follows whatever `end_deg - start_deg`
    is, which is how a loop's own direction (clockwise or not) is chosen by
    its caller rather than by this function.
    """
    if steps < 1:
        raise ValueError("need at least one step to draw an arc")
    cx, cy = centre
    points = []
    for i in range(steps + 1):
        angle = math.radians(start_deg + (end_deg - start_deg) * i / steps)
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


#: Left loop, in short-side/height fractions: centre 0.058 short-sides in
#: from the left edge, 0.365 of the height down the page, radius 0.105
#: short-sides -- fitted so the circle's own extremes land close to the
#: reference's measured apexes (top ~(0.058, 0.290), right ~(0.133, 0.356),
#: bottom ~(0.058, 0.429), in the same units) while crossing x=0 twice, the
#: two points the reference shows the stroke actually touching the edge; the
#: radius reads a touch larger than that fit once rendered and compared
#: side by side against the reference -- looking at
#: it, not just measuring it, is the actual acceptance test here.
_LEFT_LOOP_CENTRE_X: Final = 0.058
_LEFT_LOOP_CENTRE_Y: Final = 0.365
_LEFT_LOOP_RADIUS: Final = 0.105

#: Right loop: centre 0.069 short-sides in from the right edge, radius
#: 0.103 short-sides. Its centre-y is not a separate fitted number -- it is
#: exactly the radius, which is what makes the circle's own topmost point
#: land on y=0 (see `waypoints`), matching the reference: this loop grazes
#: the top of the frame without ever crossing it, only the right edge.
_RIGHT_LOOP_CENTRE_X: Final = 0.069
_RIGHT_LOOP_RADIUS: Final = 0.103

#: Points sampled along each loop's visible arc. Dense enough that Catmull-
#: Rom through them reads as a round curl rather than a faceted polygon --
#: verified by rendering and comparing side by side, not by a formula,
#: since "looks round" is a visual property.
_ARC_STEPS: Final = 8

#: The left tail's own bulge: the one interior anchor a Catmull-Rom curve
#: threads between the loop's close point and the bottom exit. Fitted by
#: least squares against a scanline trace of the reference
#: (`announcement-template_initial.png`, 1200x1200): the purple stroke's own
#: centre x at every row from the loop's close (y~543) to the bottom edge
#: (y=1200), 4px steps, 165 rows. The fit does not sit at the traced
#: curve's own plateau (~(0.234, 0.821) in the same units) -- placing the
#: anchor there directly undershoots, because a Catmull-Rom curve overshoots
#: past an interior anchor on its way to the next one; fitting the anchor's
#: position against the whole traced row, not just its apex, is what lands
#: the resulting curve's own apex at (0.240, 0.792), close to the trace.
#: Residual: 9.4px RMS over the 165 rows, against a stroke ~29px wide at
#: this scale -- under a third of the stroke's own half-width, and not only
#: at the apex. This replaces an earlier (0.213, 0.875), which was
#: named directly as wrong: "the tail curvature is a generic smooth interpolation,
#: not a point-by-point trace" -- that anchor left the resulting curve's
#: apex about 100px short of the traced centreline through the middle of
#: the tail (worst row, y~807: 97px), most visible there and less so near
#: the two ends, which is exactly the "gentler bow, swings less far right"
#: a side-by-side render showed.
_LEFT_TAIL_BULGE_X: Final = 0.233
_LEFT_TAIL_BULGE_Y: Final = 0.747


@dataclass(frozen=True)
class Waypoints:
    """Every on-curve point of the ribbon, before it is joined into a path.

    A dataclass rather than a dict of mixed single points and arcs: exposed
    on purpose, not folded into `path`, because the properties that
    actually matter -- a loop's footprint tracking the shorter side, a
    point's distance from the edge it belongs to, a value that does *not*
    move when only the long side changes -- are trivial to pin against named
    fields and would need re-parsing an SVG path string otherwise.
    """

    left_top_entry: Point
    left_top_exit: Point
    #: The left loop's own arc, entry point first and close point last --
    #: `left_loop_arc[0]` and `left_loop_arc[-1]` *are* its entry and close.
    left_loop_arc: list[Point]
    left_tail_bulge: Point
    left_bottom_exit: Point
    #: The right loop's own arc, entry point first, exit point last.
    right_loop_arc: list[Point]
    right_loop_out: Point
    right_tail_start: Point
    right_tail_bulge: Point
    right_tail_exit: Point

    @property
    def left_loop_entry(self) -> Point:
        return self.left_loop_arc[0]

    @property
    def left_loop_close(self) -> Point:
        return self.left_loop_arc[-1]

    @property
    def right_loop_entry(self) -> Point:
        return self.right_loop_arc[0]

    @property
    def right_loop_exit(self) -> Point:
        return self.right_loop_arc[-1]


def waypoints(width: float, height: float) -> Waypoints:
    """Every on-curve point of the ribbon, before it is joined into a path."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")
    s = _short_side(width, height)

    def sx(fraction: float) -> float:
        """A size, or an offset from the left edge -- tracks the short side."""
        return fraction * s

    def rx(fraction: float) -> float:
        """An offset from the *right* edge -- tracks the short side."""
        return width - fraction * s

    def hy(fraction: float) -> float:
        """A position down the page -- tracks the full height."""
        return fraction * height

    # Left loop: a circle crossing x=0 twice. Its own axis toward the
    # boundary it grazes is 180 degrees (pointing at -x); the entry (upper,
    # smaller y) sits at axis+phi, the close (lower, larger y) at axis-phi,
    # and the visible arc sweeps the *long* way between them -- increasing
    # angle, through the top (270), the right extreme (0/360) and the
    # bottom (90) -- which is what makes it a loop rather than a short bite
    # out of the circle's edge.
    left_phi = _edge_crossing_half_angle(_LEFT_LOOP_CENTRE_X, _LEFT_LOOP_RADIUS)
    left_centre = (sx(_LEFT_LOOP_CENTRE_X), hy(_LEFT_LOOP_CENTRE_Y))
    left_radius = sx(_LEFT_LOOP_RADIUS)
    left_entry_deg = 180 + left_phi
    left_close_deg = 180 - left_phi + 360  # the long way round, not the short bite
    left_arc = _arc_points(
        left_centre, left_radius, left_entry_deg, left_close_deg, _ARC_STEPS
    )

    # Right loop: a circle crossing x=width twice, axis 0 degrees (+x). Its
    # centre-y equals its own radius, which puts the topmost point of the
    # circle exactly at y=0 -- grazing the top edge without crossing it, as
    # the reference shows. Entry (upper) at axis-phi, exit (lower, where the
    # short tail continues from) at axis+phi; the visible arc sweeps the
    # long way, *decreasing* angle this time, through the top (270 = -90),
    # the left extreme (180) and the bottom (90) -- the opposite rotation
    # from the left loop, because this loop turns the other way, not a
    # mirror image of it.
    right_phi = _edge_crossing_half_angle(_RIGHT_LOOP_CENTRE_X, _RIGHT_LOOP_RADIUS)
    right_radius = sx(_RIGHT_LOOP_RADIUS)
    right_centre = (rx(_RIGHT_LOOP_CENTRE_X), right_radius)
    right_entry_deg = -right_phi
    right_exit_deg = right_phi - 360  # the long way round, decreasing angle
    right_arc = _arc_points(
        right_centre, right_radius, right_entry_deg, right_exit_deg, _ARC_STEPS
    )

    return Waypoints(
        # Left: enters the top edge, runs almost the full height, leaves
        # through the bottom edge, with one open loop on the way down.
        left_top_entry=(sx(0.106), 0.0),
        left_top_exit=(0.0, hy(0.2125)),
        left_loop_arc=left_arc,
        left_tail_bulge=(sx(_LEFT_TAIL_BULGE_X), hy(_LEFT_TAIL_BULGE_Y)),
        left_bottom_exit=(sx(0.175), height),
        # Right: one large loop near the top, crossing the right edge twice
        # as it turns, then a short tail exiting lower down through the
        # same edge.
        right_loop_arc=right_arc,
        right_loop_out=(width + sx(0.018), right_arc[-1][1] + sx(0.02)),
        right_tail_start=(width, right_arc[-1][1] + sx(0.05)),
        right_tail_bulge=(rx(0.047), hy(0.392)),
        right_tail_exit=(width, hy(0.475)),
    )


def _catmull_rom(points: list[Point]) -> list[tuple[Point, Point, Point]]:
    """Cubic Bezier control points for a smooth open curve through `points`.

    Uniform Catmull-Rom to Bezier, the standard conversion: each interior
    point's tangent is set from its neighbours, and the two end points are
    padded by duplication so the curve does not need a tangent supplied from
    outside the sequence. Returns one `(c1, c2, end)` triple per segment --
    `points[0]` is the implicit start of the first one.
    """
    if len(points) < 2:
        raise ValueError("need at least two points to draw a curve")
    padded = [points[0], *points, points[-1]]
    segments: list[tuple[Point, Point, Point]] = []
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        segments.append((c1, c2, p2))
    return segments


def _fmt(number: float) -> str:
    """A coordinate, trimmed of the trailing zeros a fixed format leaves."""
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


#: One cubic segment, as the four points that define it: where it starts,
#: its two control points, and where it ends. `path` formats these into
#: `C` commands and `outline` flattens this same list into a polyline, so
#: the drawing a consumer inks and the drawing a corridor is measured
#: against cannot come to be two different curves.
Cubic = tuple[Point, Point, Point, Point]


def _cubic(segment: Cubic) -> str:
    """One segment as its `C` command -- the start point is where the
    previous command already left the pen, so it is not written again."""
    _start, c1, c2, end = segment
    return (
        f"C {_fmt(c1[0])} {_fmt(c1[1])} {_fmt(c2[0])} {_fmt(c2[1])} "
        f"{_fmt(end[0])} {_fmt(end[1])}"
    )


def _corner(start: Point, end: Point) -> Cubic:
    """A smooth quarter-turn between a vertical and a horizontal tangent.

    Used once, for the segment that crosses the top-left corner: the stroke
    enters the top edge travelling straight down and leaves the left edge
    travelling straight out, the same perpendicular-to-each-edge shape the
    reference poster's own top-left curve shows. Control 1 sits directly
    below `start`; control 2 sits directly out from `end`.
    """
    c1 = (start[0], start[1] + (end[1] - start[1]) * 0.5)
    c2 = (start[0] + (end[0] - start[0]) * 0.5, end[1])
    return (start, c1, c2, end)


def _edge_gap(start: Point, end: Point, *, bulge: float) -> Cubic:
    """The invisible span where the stroke runs off the left edge and back.

    Both `start` and `end` sit on the canvas boundary (`x == 0`); a straight
    join between them would render as a seam right on the edge, which the
    reference does not show -- there is real background between the two
    crossings. Bulging both control points to `x = -bulge` keeps every
    point of this segment at `x <= 0` (the hull of `{0, -bulge, -bulge, 0}`),
    touching the boundary only at the two given endpoints, so it never
    paints anything inside the canvas.
    """
    c1 = (-bulge, start[1] + (end[1] - start[1]) / 3.0)
    c2 = (-bulge, start[1] + (end[1] - start[1]) * 2.0 / 3.0)
    return (start, c1, c2, end)


def _connector(start: Point, end: Point, *, width: float, height: float) -> list[Cubic]:
    """The long invisible span from the left motif to the right one.

    Three segments, each provably outside the `[0, width] x [0, height]`
    canvas rectangle by the convex hull of its own four points -- a cubic
    Bezier never leaves that hull, so pinning every one of a segment's
    points to one side of a boundary line is sufficient on its own, with no
    sampling and no dependence on how the two aspect ratios involved compare:

    1. every y-coordinate is `>= height` (a run below the bottom edge, since
       `start` already sits on it);
    2. every x-coordinate equals `width + margin` exactly (a vertical run to
       the right of the right edge, at one constant coordinate so nothing
       about the segment's curvature can drift it back inside);
    3. every x-coordinate is between `width` and `width + margin` (a run
       approaching the right edge from outside it), reaching `end` -- which
       is why the right loop's own entry point sits exactly on `x = width`
       (see `waypoints`): this segment meets the canvas only there.

    `margin` is tied to the canvas's own extent (twice its longer side) so
    it clears both edges by construction at any aspect ratio, rather than a
    fixed pixel count that would need re-tuning per format.
    """
    margin = 2 * max(width, height)
    beyond = (width + margin, height + margin)

    seg1 = (start, (start[0], height + margin), beyond, beyond)
    seg2 = (
        beyond,
        (width + margin, height * 0.5),
        (width + margin, end[1]),
        (width + margin, end[1]),
    )
    seg3 = (
        (width + margin, end[1]),
        (width + margin * 0.7, end[1]),
        (width + margin * 0.3, end[1]),
        end,
    )
    return [seg1, seg2, seg3]


#: How far outside the left edge the invisible gap between the top segment
#: and the loop bulges. Only needs to clear half the stroke width by a
#: comfortable margin; tied to the short side so it scales with the ribbon
#: itself rather than sitting still while everything around it resizes.
_GAP_BULGE_FACTOR: Final = 0.25


def segments(width: float, height: float) -> list[Cubic]:
    """Every cubic of the ribbon, in the order the stroke draws them.

    One list, read twice: `path` formats it into `C` commands for whoever
    inks the drawing, and `outline` flattens it into the polyline the
    registry measures a corridor against. Two readers of one derivation,
    for the reason `Waypoints` is exposed rather than folded into `path` --
    except that here the reason is sharper, because the two readings have
    to agree about where the curve actually goes: a corridor measured off
    the waypoints alone would miss the small overshoot a Catmull-Rom curve
    makes past an interior anchor, and that overshoot is real paint.
    """
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")

    w = waypoints(width, height)
    s = _short_side(width, height)
    gap_bulge = _GAP_BULGE_FACTOR * s

    drawn: list[Cubic] = [
        _corner(w.left_top_entry, w.left_top_exit),
        _edge_gap(w.left_top_exit, w.left_loop_entry, bulge=gap_bulge),
    ]

    left_chain = [*w.left_loop_arc, w.left_tail_bulge, w.left_bottom_exit]
    start = w.left_loop_entry
    for c1, c2, end in _catmull_rom(left_chain):
        drawn.append((start, c1, c2, end))
        start = end

    drawn.extend(
        _connector(w.left_bottom_exit, w.right_loop_entry, width=width, height=height)
    )

    right_chain = [
        *w.right_loop_arc,
        w.right_loop_out,
        w.right_tail_start,
        w.right_tail_bulge,
        w.right_tail_exit,
    ]
    start = w.right_loop_entry
    for c1, c2, end in _catmull_rom(right_chain):
        drawn.append((start, c1, c2, end))
        start = end

    return drawn


def path(width: float, height: float) -> str:
    """This family's drawing for a canvas of the given size, as an SVG path `d`.

    One `M`, only `C` after it, no `Z`: a single continuous cubic-Bezier
    stroke, exactly as `instance/data/brand.json::motif._family` describes
    it, not four bare circles standing in for one. The charter's own
    `stroke` and `width_ratio` say what a consumer inks it with
    (`motifs.stroke_width`); this function only ever returns geometry.
    """
    drawn = segments(width, height)
    start = drawn[0][0]
    commands = [f"M {_fmt(start[0])} {_fmt(start[1])}"]
    commands.extend(_cubic(segment) for segment in drawn)
    return chr(10).join(commands)


#: How many straight steps each cubic is flattened into for `outline`.
#:
#: The number is a measurement, not a taste: the property that matters is
#: that the polyline's own deepest reach into the canvas agrees with the
#: curve's, and `tests/publication/motifs/test_ribbon.py` holds the two to
#: within a tenth of a unit on a 1200-unit canvas by halving the step and
#: showing the answer stops moving. Sixteen is where it has stopped --
#: the arcs are already sampled into eight chords apiece before this
#: (`_ARC_STEPS`), so no single cubic here spans much curvature.
_FLATTEN_STEPS: Final = 16


def _flatten(segment: Cubic) -> list[Point]:
    """One cubic as `_FLATTEN_STEPS + 1` points along it, start included."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = segment
    points = []
    for step in range(_FLATTEN_STEPS + 1):
        t = step / _FLATTEN_STEPS
        u = 1.0 - t
        a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        points.append(
            (a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3)
        )
    return points


def outline(width: float, height: float) -> tuple[tuple[Point, ...], ...]:
    """This family's drawing as a polyline, for the registry to measure.

    One polyline, because the ribbon is one continuous stroke: every cubic
    `segments` returns, flattened, end to end. The spans that run outside
    the canvas are in it exactly as they are in the path -- the registry
    clips to the canvas rather than each family deciding for itself what
    counts, which is what lets a family draw off the edge without also
    having to reason about corridors.
    """
    points: list[Point] = []
    for segment in segments(width, height):
        step = _flatten(segment)
        points.extend(step[1:] if points else step)
    return (tuple(points),)


#: How much clearance a block of text keeps from this drawing, in stroke
#: widths. Half of it is the stroke's own physical extent either side of
#: its centreline; the other half is a gutter, so a word set at the safe
#: area's own edge is not set against the drawing.
#:
#: It used to be half stroke and half *buffer* -- an allowance for the
#: small overshoot a Catmull-Rom curve makes past an interior anchor,
#: because the reach was read off `waypoints` and the curve goes a little
#: further than they do. `outline` above flattens the curve itself, so the
#: overshoot is measured rather than allowed for, and this figure buys a
#: gutter now instead of paying a debt. That is why the ribbon's own safe
#: margin moved by about eight units on a 1200-unit canvas when the two
#: swapped places. A family drawn some other way measures its own, which is
#: why the registry reads this off the family rather than holding one
#: figure for all of them.
CLEARANCE_STROKE_WIDTHS: Final = 1.0
