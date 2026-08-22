"""Anonymous's ribbon: one continuous meandering stroke, not four bare circles.

`data/brand.json::motif._ribbon` names the defect this module fixes: both
announcement SVGs already in this repository stand in four bare `<circle>`
elements for the purple stroke that runs through Anonymous's own poster
(`docs/assets/example_and_template_initial_assets/announcement-template_initial.png`,
gitignored -- it carries a real person's photograph, entry 9 of
`docs/superpowers/deferred-work.md`). A poster built from circles does not
read as hers, no matter how faithfully every other measurement passes.

What the reference actually shows
----------------------------------
Traced pixel by pixel against the 1200x1200 reference -- task 1's own brief
was a starting point to verify, not a given, and two of its claims did not
survive that check: the left curl does not cross its own tail (it is a near
circle open on one side, like the right one), and the stroke measures 23-33px
wide there, not the 0.0075-ratio 9px `data/brand.json` held before this task
(see `motif._ribbon_width_ratio`).

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
pixel count: task 4 renders this same function into a square poster, a wide
banner and a high-definition print, and a ribbon that only composes at one
aspect ratio is a ribbon that fails three tasks later. Each loop is a true
arc of a circle -- computed from where that circle crosses the edge it
grazes, not a handful of hand-placed points -- because a circle sampled
densely is what reads as a round curl instead of a kinked polygon.

The path stays one continuous cubic-Bezier subpath -- a single `M`, only `C`
after it, no `Z` -- exactly as the motif is described, even where the
visible stroke leaves the frame. The gaps where Anonymous's stroke runs off
one edge and back in, and the long invisible span between the left motif and
the right, are drawn as real cubic segments that happen to fall outside the
canvas rectangle; each helper that draws one proves in its own docstring
that every control point stays on the correct side of the boundary, so
nothing stray crosses the visible page at any aspect ratio.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: The one source of fact for the stroke's colour and width ratio.
BRAND_PATH: Final = Path("data") / "brand.json"

Point = tuple[float, float]


def _load_motif(root: Path) -> dict[str, Any]:
    """`data/brand.json::motif`, parsed. `root` matches
    `generate_brand_css.load_brand`'s own convention: threaded in from
    `repo_root()` at the call site rather than resolved here, so a test can
    point it at a fixture without touching the environment."""
    brand = json.loads((root / BRAND_PATH).read_text(encoding="utf-8"))
    return dict(brand["motif"])


def ribbon_stroke_colour(root: Path) -> str:
    """The one purple the ribbon is ever drawn in -- never hand-typed."""
    return str(_load_motif(root)["ribbon_stroke"])


def ribbon_width_ratio(root: Path) -> float:
    """Stroke width as a fraction of the canvas's shorter side.

    See `data/brand.json::motif._ribbon_width_ratio` for how this was
    measured against the reference poster.
    """
    return float(_load_motif(root)["ribbon_width_ratio"])


def ribbon_stroke_width(width: float, height: float, *, ratio: float) -> float:
    """The stroke width for a canvas of the given size, at the given ratio.

    Pure geometry, deliberately not a brand.json reader itself -- a caller
    fetches `ratio` once with `ribbon_width_ratio(repo_root())` and threads
    it through, the same separation `ribbon_path` keeps from `waypoints`.
    Tracks the *shorter* side on purpose: a wide banner and a tall print use
    the same ratio, so the stroke never balloons on the long axis the way a
    naive `width`-relative value would on a banner, or a `height`-relative
    one would on a print.
    """
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")
    return ratio * min(width, height)


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
#: side by side against the reference (see the task 1 report) -- looking at
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
#: verified by rendering, not by a formula, since "looks round" is a visual
#: property. See the task's own report for the side-by-side comparison.
_ARC_STEPS: Final = 8


@dataclass(frozen=True)
class Waypoints:
    """Every on-curve point of the ribbon, before it is joined into a path.

    A dataclass rather than a dict of mixed single points and arcs: exposed
    on purpose, not folded into `ribbon_path`, because the properties that
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
        left_tail_bulge=(sx(0.213), hy(0.875)),
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


def _cubic(c1: Point, c2: Point, end: Point) -> str:
    return (
        f"C {_fmt(c1[0])} {_fmt(c1[1])} {_fmt(c2[0])} {_fmt(c2[1])} "
        f"{_fmt(end[0])} {_fmt(end[1])}"
    )


def _corner(start: Point, end: Point) -> str:
    """A smooth quarter-turn between a vertical and a horizontal tangent.

    Used once, for the segment that crosses the top-left corner: the stroke
    enters the top edge travelling straight down and leaves the left edge
    travelling straight out, the same perpendicular-to-each-edge shape the
    reference poster's own top-left curve shows. Control 1 sits directly
    below `start`; control 2 sits directly out from `end`.
    """
    c1 = (start[0], start[1] + (end[1] - start[1]) * 0.5)
    c2 = (start[0] + (end[0] - start[0]) * 0.5, end[1])
    return _cubic(c1, c2, end)


def _edge_gap(start: Point, end: Point, *, bulge: float) -> str:
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
    return _cubic(c1, c2, end)


def _connector(start: Point, end: Point, *, width: float, height: float) -> str:
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

    seg1 = _cubic((start[0], height + margin), beyond, beyond)
    seg2 = _cubic(
        (width + margin, height * 0.5),
        (width + margin, end[1]),
        (width + margin, end[1]),
    )
    seg3 = _cubic(
        (width + margin * 0.7, end[1]),
        (width + margin * 0.3, end[1]),
        end,
    )
    return "\n".join((seg1, seg2, seg3))


#: How far outside the left edge the invisible gap between the top segment
#: and the loop bulges. Only needs to clear half the stroke width by a
#: comfortable margin; tied to the short side so it scales with the ribbon
#: itself rather than sitting still while everything around it resizes.
_GAP_BULGE_FACTOR: Final = 0.25


def ribbon_path(width: float, height: float) -> str:
    """Anonymous's ribbon for a canvas of the given size, as an SVG path `d`.

    One `M`, only `C` after it, no `Z`: a single continuous cubic-Bezier
    stroke, exactly as `data/brand.json::motif._ribbon` describes it, not
    four bare circles standing in for one. Pair with `ribbon_stroke_colour`
    and `ribbon_stroke_width` for the `stroke` and `stroke-width` a consumer
    draws it with; this function only ever returns geometry.
    """
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")

    w = waypoints(width, height)
    s = _short_side(width, height)
    gap_bulge = _GAP_BULGE_FACTOR * s

    commands: list[str] = [f"M {_fmt(w.left_top_entry[0])} {_fmt(w.left_top_entry[1])}"]
    commands.append(_corner(w.left_top_entry, w.left_top_exit))
    commands.append(_edge_gap(w.left_top_exit, w.left_loop_entry, bulge=gap_bulge))

    left_chain = [*w.left_loop_arc, w.left_tail_bulge, w.left_bottom_exit]
    for c1, c2, end in _catmull_rom(left_chain):
        commands.append(_cubic(c1, c2, end))

    commands.append(
        _connector(w.left_bottom_exit, w.right_loop_entry, width=width, height=height)
    )

    right_chain = [
        *w.right_loop_arc,
        w.right_loop_out,
        w.right_tail_start,
        w.right_tail_bulge,
        w.right_tail_exit,
    ]
    for c1, c2, end in _catmull_rom(right_chain):
        commands.append(_cubic(c1, c2, end))

    return "\n".join(commands)
