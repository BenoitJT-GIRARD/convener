"""The `bracket` family: the product's own mark, drawn in straight segments.

`assets/brand/convener/convener-mark.svg` is the product's own artwork -- two arcs
and a circle, with the radii, the stroke widths and the opening between the
arcs' ends read off the original and rebuilt (`assets/brand/convener/README.md`,
"How the mark and the wordmark were made"). That geometry is the product's
own, which is what a charter this repository ships publicly may be drawn
with. `ribbon.py` beside this module is the other case, and its own
docstring says so: that shape is traced pixel by pixel off one instance's
announcement poster, so a charter naming it wears that instance's mark.

What this draws
----------------
One bracket standing against each vertical edge, its opening facing the
middle of the page. A bracket is one of the mark's arcs with the circle it
is struck on replaced by the box that circle sits in: a spine, an arm
turning in at each end of it, and a return on each arm that stops where the
arc's own end stops. Six points, five straight segments, `M` and `L` and
nothing else. `tests/publication/motifs/test_registry.py` holds every
family but the ribbon to that, at every canvas this product draws on.

Where each number comes from
-----------------------------
Off `convener-mark.svg` itself, in the units of its own 512 viewBox.

- **The opening.** Both arcs run from 40 degrees to 320, leaving a gap of
  80 facing the dot; measured off the file's own two `A` commands the
  half-angle is 39.9996 on the outer arc and 40.0016 on the inner. A ray
  at that angle from the centre leaves the box the circle sits in at
  `tan(40)` of the box's half-width above the middle of the side it
  crosses, and that is where a bracket's return stops. (`README.md`
  records the figure read off the original raster as 81 degrees. What the
  shipped file draws is 80.)
- **The two sizes.** The mark's inner arc is struck on a radius of 131.72
  against the outer's 205.66, so the inner is 0.6405 of the outer. The
  bracket against the left edge is the outer arc; the one against the
  right edge is the inner, at that fraction of it in both directions.
- **The stroke's weight** belongs to the motif rather than to a family
  (`motifs.stroke_width`), and `assets/brand/convener/brand.json::motif.
  _width_ratio` says where the product's own figure comes from: the mark
  draws its outer arc 68.69 wide on a radius of 205.66, 0.334 of it,
  carried onto `_OUTER_HALF_WIDTH` below. The outer arc's proportion
  rather than the inner's, because a bracket standing in a page's margin
  is the mark's own shape at the mark's own weight, where the ribbon
  crossing the page is a line and takes the thinner of the two.

The dot is not drawn here. `motif.logo_dots` is where the mark's coral
circle already goes -- the one filled circle `lockup.device` closes the
lock-up on, in both downloadable templates and in the poster the cockpit
generates -- and the charter's own `_logo_dots` says so.

Nothing is a pixel count
-------------------------
Every coordinate below is a fraction of either the canvas's shorter side
(a bracket's own width, its opening, and how far it stands off its edge)
or of the canvas's height (how far its spine runs down the page). This
same function is asked for a 1200 square, a 1200x630 banner, an A4 page at
300 dpi and a 1920x1080 video-call frame, and a drawing fitted to one of
them in pixels composes at one of them. The mark's own proportions track
the shorter side because stretching one of them puts a different shape on
a wider page; the spine tracks the height because running down whatever
page it is given is the whole of its job.

Where it may stand
-------------------
Every surface this product draws asks the registry where its words may go
-- the generated posters (`visual.py`), the video-call background and,
since the two downloadable templates stopped hand-placing their type,
those as well (`brand_templates.py`). So the placement constants below
are no longer a fit to one committed layout: a block of type that this
drawing reaches is moved by the layout, not accommodated by the drawing.
What they still are is a fit to the *reference poster's own proportions*
-- how deep a mark stands in a margin, how far down a page it runs -- and
`tests/publication/motifs/test_bracket.py` holds them to the mark they
are taken from rather than to a page they happen to clear.

`tools/visuals/check-templates.mjs` is what measures the result, in a
browser, for every charter this repository holds: at the three stroke
weights those charters carry, this drawing clears every block of the
announcement by at least 18 units on its 1200 canvas and every block of
the flyer by at least 47 on its 2100 one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

Point = tuple[float, float]


def _short_side(width: float, height: float) -> float:
    """The dimension a measured proportion has to track to stay itself."""
    return min(width, height)


# ----------------------------------------------------------------------
# The mark's own measurements
# ----------------------------------------------------------------------

#: The two radii the mark's arcs are struck on, in the units of its own
#: 512 viewBox (`convener-mark.svg`: `A 205.66` and `A 131.72`).
_MARK_OUTER_RADIUS: Final = 205.66
_MARK_INNER_RADIUS: Final = 131.72

#: What the outer arc's stroke is as a fraction of the radius it is struck
#: on, 0.334 (`convener-mark.svg`: `stroke-width="68.69"` on that arc).
#: `assets/brand/convener/brand.json::motif.width_ratio` is this carried onto
#: `_OUTER_HALF_WIDTH`, and `tests/publication/test_brand.py` holds the
#: charter's own figure to the arithmetic.
_MARK_OUTER_STROKE: Final = 68.69
MARK_OUTER_STROKE_OF_RADIUS: Final = _MARK_OUTER_STROKE / _MARK_OUTER_RADIUS

#: Half the mark's opening, in degrees: both arcs end this far either side
#: of the axis the dot sits on.
_OPENING_HALF_ANGLE_DEGREES: Final = 40.0

#: What the inner arc is as a fraction of the outer, 0.6405. The right
#: bracket is the left one at this size.
_INNER_OVER_OUTER: Final = _MARK_INNER_RADIUS / _MARK_OUTER_RADIUS

#: Where a bracket's return stops, as a fraction of that bracket's own
#: half-width, measured from the middle of its open side.
_RETURN_OF_HALF_WIDTH: Final = math.tan(math.radians(_OPENING_HALF_ANGLE_DEGREES))


# ----------------------------------------------------------------------
# Where the two brackets sit on a page
# ----------------------------------------------------------------------

#: The left bracket's half-width, in short sides. It decides how far the
#: motif reaches into the page -- 2.3 of it, with the stand-off below --
#: and it is what `assets/brand/convener/brand.json::motif.width_ratio` carries
#: the mark's own outer-arc proportion onto: 0.334 of 0.061 is 0.0204.
#:
#: The figure itself was a fit to the ground the two downloadable
#: templates left free while they still hand-placed their type -- measured
#: in a browser against both committed files, a drawing reaching past
#: roughly 0.16 of the shorter side crossed the announcement's date line
#: and the flyer's. Those templates read a family's own corridor now, so
#: the constraint that produced this number is gone and the number stays:
#: it is a mark standing a twelfth of the page deep in a margin, which is
#: the proportion the product's own artwork has, and there is no longer a
#: layout it has to be small enough for.
_OUTER_HALF_WIDTH: Final = 0.061

#: The left bracket's top arm and half-height, in heights: its spine runs
#: from 0.17 of the page to 0.458. The top clears the band both
#: downloadable templates set their wordmark in -- the lock-up's own
#: device and the rule under it -- which is a property of those compositions'
#: own top band and not of any drawing. The height is set from the other
#: end: the
#: right bracket is this one at `_INNER_OVER_OUTER`, and what that one has
#: to fit inside is stated at `_INNER_TOP`.
_OUTER_TOP: Final = 0.17
_OUTER_HALF_HEIGHT: Final = 0.144

#: How far a bracket's spine stands off the edge it belongs to, as a
#: fraction of that bracket's own half-width. Read off the bracket rather
#: than off the canvas, so the smaller of the two stands off by the same
#: share of itself and the pair keeps its proportions.
_EDGE_STANDOFF: Final = 0.30

#: Where the right bracket's top arm sits, in heights. It hangs from the
#: top of the page, and with `_OUTER_HALF_HEIGHT` above it is what keeps
#: the whole of this bracket clear of the one band on that side of the
#: page that does not read a family's own right margin: `.content`, which
#: holds the speaker's photographic frame and reads the clearance alone
#: (`visual._motif_content_right_margin`). Measured in a browser on all
#: three named formats, `.content` begins at 0.317 of the square, 0.224 of
#: the A4 print, and does not exist on the banner; the frame inside it
#: begins at 0.334 and 0.231. This bracket ends at 0.209 of the page,
#: above the earliest of them at every format, and
#: `tests/publication/motifs/test_bracket.py` holds it there.
_INNER_TOP: Final = 0.025


@dataclass(frozen=True)
class Waypoints:
    """Every point of both brackets, in the order each one is drawn.

    Exposed rather than folded into `path`, for the reason `ribbon.py`'s
    own `Waypoints` gives: the properties worth pinning -- how deep a
    bracket reaches, how far down the page it goes, what does not move
    when only the long side changes -- are trivial to pin against these
    two sequences and would need an SVG path string re-parsed otherwise.
    Here they are also the drawing itself, since straight segments join
    them: nothing this family paints lies outside the points below.
    """

    #: The outer arc's bracket, against the left edge, opening rightwards.
    left: tuple[Point, ...]
    #: The inner arc's bracket, against the right edge, opening leftwards.
    right: tuple[Point, ...]


def _bracket(
    centre: Point, half_width: float, half_height: float, *, facing: float
) -> tuple[Point, ...]:
    """One bracket, given the middle of the box it fits in.

    `facing` is `1.0` for an opening toward larger x and `-1.0` for one
    toward smaller x; the spine sits on the other side. The six points run
    from the upper return, round the spine, to the lower one, so a bracket
    is drawn in a single stroke.
    """
    centre_x, centre_y = centre
    open_x = centre_x + facing * half_width
    spine_x = centre_x - facing * half_width
    return_y = _RETURN_OF_HALF_WIDTH * half_width
    return (
        (open_x, centre_y - return_y),
        (open_x, centre_y - half_height),
        (spine_x, centre_y - half_height),
        (spine_x, centre_y + half_height),
        (open_x, centre_y + half_height),
        (open_x, centre_y + return_y),
    )


def waypoints(width: float, height: float) -> Waypoints:
    """Every point of both brackets on a canvas of the given size."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")
    short = _short_side(width, height)
    outer_half_width = _OUTER_HALF_WIDTH * short
    outer_half_height = _OUTER_HALF_HEIGHT * height
    inner_half_width = outer_half_width * _INNER_OVER_OUTER
    inner_half_height = outer_half_height * _INNER_OVER_OUTER
    return Waypoints(
        left=_bracket(
            (
                (1.0 + _EDGE_STANDOFF) * outer_half_width,
                _OUTER_TOP * height + outer_half_height,
            ),
            outer_half_width,
            outer_half_height,
            facing=1.0,
        ),
        right=_bracket(
            (
                width - (1.0 + _EDGE_STANDOFF) * inner_half_width,
                _INNER_TOP * height + inner_half_height,
            ),
            inner_half_width,
            inner_half_height,
            facing=-1.0,
        ),
    )


def _fmt(number: float) -> str:
    """A coordinate, trimmed of the trailing zeros a fixed format leaves."""
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def path(width: float, height: float) -> str:
    """This family's drawing for a canvas of the given size, as an SVG path `d`.

    Two subpaths, one `M` and five `L` each, and no curve command anywhere:
    the ribbon is the drawing this product has that is one continuous
    curve, and it is the one traced off an instance's own poster. The
    charter's `stroke` and `width_ratio` say what a consumer inks this
    with (`motifs.stroke_width`); this function only ever returns geometry.
    """
    marks = waypoints(width, height)
    commands: list[str] = []
    for bracket in (marks.left, marks.right):
        start, *rest = bracket
        commands.append(f"M {_fmt(start[0])} {_fmt(start[1])}")
        commands.extend(f"L {_fmt(x)} {_fmt(y)}" for x, y in rest)
    return "\n".join(commands)


def outline(width: float, height: float) -> tuple[tuple[Point, ...], ...]:
    """This family's drawing as a polyline, for the registry to measure.

    Two polylines, one per bracket, and for this family they are the
    drawing itself rather than an approximation of it: straight segments
    join the points `waypoints` returns and reach past none of them, so
    `path` above and this function describe the same six-point run twice
    in two notations. `ribbon.outline` has to flatten a curve to say the
    same thing.
    """
    marks = waypoints(width, height)
    return (marks.left, marks.right)


#: How much clearance a block of text keeps from this drawing, in stroke
#: widths. Half of it is the stroke's own physical extent either side of
#: its centreline: straight segments join the points `waypoints` returns
#: and reach past none of them, and at this drawing's only corner angle --
#: a right angle, between an arm and a spine or a return -- a mitre and a
#: round join both put the outline half a stroke width past the corner on
#: each axis. The other half is a gutter, so a word set at the safe area's
#: own edge is not set against the drawing. A family drawn some other way
#: measures its own, which is why the registry reads this off the family.
CLEARANCE_STROKE_WIDTHS: Final = 1.0
