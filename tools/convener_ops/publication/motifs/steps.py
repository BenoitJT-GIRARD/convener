"""The `steps` family: one orthogonal line, laid across a page as levels.

A single stroke of right angles. It enters the page through the top edge
on the right, turns out to the right edge, leaves the page again over the
top, crosses back above it, comes down on the left and descends to the
bottom edge as a run of ledges at two depths joined by right-angled
risers. It reads as strata, and a series of talks is a stack of them.

It is a *line* rather than a field, which is what separates it from
`lattice.py` beside it: `outline` hands back one run where the lattice
hands back thirty-six and the bracket two. `ribbon.py` is the other line
this product has, and this one takes the ribbon's own habit of leaving the
canvas and coming back -- the span joining the right of the drawing to the
left runs above the page and is never painted on it, exactly as the
ribbon's own does.

Straight segments, and the rule behind that
--------------------------------------------
Every corner here is a right angle and every command is an `M` or an `L`.
`tests/publication/motifs/test_registry.py` refuses a curve command in
every family but the ribbon, because the ribbon is somebody's own mark and
a second curve would read as a variant of it rather than as a charter of
its own.

One drawing, inked and measured
---------------------------------
`line` below returns every point of the stroke once, in the order it is
drawn. `path` writes those points as `M`/`L` for whoever inks the drawing,
and `outline` hands the same points to the registry, which measures every
corridor on a page against them. Points above the top edge are part of the
line and are handed over as such: the registry clips what it measures to
the canvas, which is what lets a family run off a page without also having
to reason about corridors.

Nothing is a pixel
-------------------
The drawing has one unit, `_STEP`. A ledge is that fraction of the shorter
side and a riser that fraction of the height, so a ledge keeps its depth
whatever the page is shaped like and the flight always crosses the page in
the same number of levels. The same function draws a 1200 square, a
1200x630 banner, an A4 print at 300 dpi, a 1920x1080 video-call frame and
the 400-unit square the chrome sets in a masthead.

Where every number comes from
------------------------------
Four figures decide the line, and each is fixed by something this
repository already measures:

- **`_RISERS`, how many levels the flight crosses the page in.** Bounded
  from below by the one block on the announcement that stands on the far
  side of this drawing. That page sets its registration slot in the free
  strip nearest the left edge over rows 870 to 1140, 180 units wide with
  the page's own 24-unit gutter before it, and sets the "what to expect"
  column at an indent of 320 beside it
  (`brand_templates._ANNOUNCEMENT_COLUMN`). A drawing crossing those rows
  therefore has 320 less 24 less 180, that is 116 units of a 1200-unit
  page, for its own ledge and the clearance around it -- and the
  clearance is 36 at the heaviest charter this repository holds. Sixteen
  levels lay a ledge of 75 and fit; fifteen lay one of 80 and fourteen
  one of 85.7, and both put the slot into the column. Sixteen is
  therefore the fewest, and the fewest is the deepest ledge this page has
  room for. The bracket's own reach, 0.1403 of the shorter side, is the
  bound every other family here is measured against and it is the looser
  of the two.

  **The two figures are measured now, and one of them was wrong.** This
  paragraph used to end "nothing in this repository measures a slot
  against a column, which is why the figure is written down here", and
  said fifteen levels landed the slot *exactly* on the column's own
  indent. `tools/visuals/check-templates.mjs` sweeps every placed block
  against every other now, over the same ninety renderings, and reports
  fourteen at 6.7 units into the column and fifteen at 1.0 -- not zero,
  because the bold `A` of `AFTER: ` inks about a unit west of the pen
  position 320 that the arithmetic places it at. A side bearing is not
  something arithmetic over indents can see, which is why the figure is
  no longer only written down.
- **`_STEP`, the drawing's one unit.** Not a figure of its own: it is one
  level, `1 / _RISERS`, read against the shorter side for a ledge and
  against the height for a riser. On the 1200-unit square the
  announcement is drawn on the two are the same length, which is what
  makes the flight read as a stair rather than as a comb.
- **`_NEAR`, where the near end of every ledge sits.** On the page's own
  edge, and it is the one figure here that could not have been anything
  else. The announcement sets its registration slot in the free strip
  nearest the left edge over rows 870 to 1140
  (`brand_templates._ANNOUNCEMENT_REGISTER_TOP`), and this line crosses
  those rows. A line standing any distance off that edge leaves the slot
  that distance to sit in, and
  `brand_templates._ANNOUNCEMENT_SLOT_FLOOR` refuses anything under 120
  units of it. Standing a slot's width off the edge would cost more
  ground than the bracket's whole arm; standing on the edge leaves the
  slot the whole page east of the drawing, at every stroke weight a
  charter may name. So the risers on that side sit on the boundary and
  paint half a stroke off it, the way the ribbon's own left loop crosses
  x=0 twice.
- **`_OVERHANG`, how far above the top edge the joining span runs.** One
  riser, which is the drawing's own unit again. What it has to clear is
  the paint it carries: at the heaviest stroke a charter here may draw the
  ratio is 0.03 of the shorter side, so half of it is 0.015 of the shorter
  side, and one riser of the height is never shorter than that at any
  canvas this product renders. A span nearer than that would put paint on
  a page it is not drawn on.
  `brand.HEAVIEST_STROKE` is the ceiling and holds every charter under
  it, refused where a charter is read; the heaviest committed draws at
  0.024.

`_CONTENT_TOP` below is the fifth figure and it is not the line's: it is
where a generated poster's `.content` band begins, and it decides how many
levels the right of the drawing may have.

`tools/visuals/check-templates.mjs` is what measures the result, in a
browser, for every charter this repository holds crossed with every
family: at the stroke weights those charters carry, this drawing clears
every block of type in all three downloadable templates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .. import composition

Point = tuple[float, float]


def _short_side(width: float, height: float) -> float:
    """The dimension a ledge's own depth has to track to stay itself."""
    return min(width, height)


# ----------------------------------------------------------------------
# The flight's own unit, and every length as a multiple of it
# ----------------------------------------------------------------------

#: How many levels the flight crosses the page in. The module docstring
#: has the measurement that fixes it -- and it is the announcement's own
#: registration slot rather than the ground a margin can spare.
_RISERS: Final = 16

#: One level. A ledge is this fraction of the shorter side and a riser
#: this fraction of the height, so the drawing has one unit rather than a
#: horizontal decision and a vertical one.
_STEP: Final = 1.0 / _RISERS

#: Where the near end of every ledge sits, in short sides: on the edge the
#: flight stands against. The module docstring has the page that fixes it.
_NEAR: Final = 0.0

#: How far above the top edge the span joining the two sides of the
#: drawing runs, in heights. One riser.
_OVERHANG: Final = _STEP

#: The row `.content` begins at -- the "what to expect" copy and the
#: speaker's photographic plate beside it -- from the one home the figure
#: has. It was written out here, and identically in one other family, on
#: the strength of `visual._motif_content_right_margin` padding that band
#: with the clearance alone rather than with a family's own reach: a
#: drawing that stayed above the band was a drawing that could not be
#: painted across the plate. That margin asks the family now
#: (`composition.CONTENT_TOP` carries the measurement and what reads it),
#: so what this figure decides here is the drawing's own balance rather
#: than the composition's safety.
_CONTENT_TOP: Final = composition.CONTENT_TOP

#: How many levels the right of the drawing has: every one that finishes
#: above that band. A whole number rather than a fraction of a page,
#: because both figures are fractions of the height and their ratio is the
#: same at every canvas. Every drawing this product ships is the short one
#: on the right, and this is why.
_RIGHT_LEVELS: Final = int(_CONTENT_TOP / _STEP)

#: How far the line reaches into the page from either edge, in short
#: sides: one ledge. Not a figure anything sets -- it is what a level
#: comes to, and it is what a composition pays for.
REACH: Final = _STEP - _NEAR


@dataclass(frozen=True)
class Waypoints:
    """The two flights of the line, in the order the stroke is drawn.

    Exposed rather than folded into `path`, for the reason `ribbon.py`'s
    own `Waypoints` gives: how deep the line reaches, how far down the
    page it runs and what does not move when only the long side changes
    are trivial to pin against these two sequences and would need an SVG
    path string re-parsed otherwise. Here they are also the drawing
    itself, since straight segments join them.

    They are two fields of one stroke rather than two drawings: the
    segment joining `right[-1]` to `left[0]` is the span that runs above
    the page, and `line` below is the pair read as the single run it is.
    """

    #: The flight against the right edge, its far end first, leaving the
    #: page over the top.
    right: tuple[Point, ...]
    #: The flight against the left edge, entering over the top and running
    #: to the bottom edge.
    left: tuple[Point, ...]


def _ledge_x(level: int, ledge: float) -> float:
    """Which of the two depths a riser stands at.

    The first riser stands at the ledge's own depth and every riser after
    it alternates, which is what lays the levels either side of the ground
    between them.
    """
    return ledge if level % 2 == 1 else _NEAR


def _flight(
    short: float,
    height: float,
    *,
    levels: int,
    closing_tread: bool,
) -> tuple[Point, ...]:
    """One flight, from above the top edge downwards.

    `levels` risers, each followed by the tread that carries the line to
    the next one. `closing_tread` says whether the last riser is followed
    by one: the flight that runs the page is not, because it leaves
    through the bottom edge, and the flight that stops early is, because
    it leaves through the side.
    """
    ledge = _STEP * short
    rise = _STEP * height
    points: list[Point] = [(_ledge_x(1, ledge), -_OVERHANG * height)]
    for level in range(1, levels + 1):
        points.append((_ledge_x(level, ledge), level * rise))
        if level < levels or closing_tread:
            points.append((_ledge_x(level + 1, ledge), level * rise))
    return tuple(points)


def waypoints(width: float, height: float) -> Waypoints:
    """Both flights of the line on a canvas of the given size."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")
    short = _short_side(width, height)
    opening = _flight(short, height, levels=_RIGHT_LEVELS, closing_tread=True)
    return Waypoints(
        right=tuple((width - x, y) for x, y in reversed(opening)),
        left=_flight(short, height, levels=_RISERS, closing_tread=False),
    )


def line(width: float, height: float) -> tuple[Point, ...]:
    """Every point of the stroke, in the order it is drawn.

    One list, read twice: `path` writes it as `M`/`L` for whoever inks the
    drawing and `outline` hands it to the registry, which measures every
    corridor against it. Two readings of one derivation, for the reason
    `ribbon.segments` gives.
    """
    flights = waypoints(width, height)
    return (*flights.right, *flights.left)


def _fmt(number: float) -> str:
    """A coordinate, trimmed of the trailing zeros a fixed format leaves."""
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def path(width: float, height: float) -> str:
    """This family's drawing for a canvas of the given size, as an SVG path `d`.

    One subpath: a single `M`, an `L` for every point after it, and no
    curve command anywhere -- the ribbon is the one drawing this product
    has that is a continuous curve, and it is the one traced off an
    instance's own poster. The charter's `stroke` and `width_ratio` say
    what a consumer inks this with (`motifs.stroke_width`); this function
    only ever returns geometry.
    """
    start, *rest = line(width, height)
    commands = [f"M {_fmt(start[0])} {_fmt(start[1])}"]
    commands.extend(f"L {_fmt(x)} {_fmt(y)}" for x, y in rest)
    return "\n".join(commands)


def outline(width: float, height: float) -> tuple[tuple[Point, ...], ...]:
    """This family's drawing as a polyline, for the registry to measure.

    One run, because that is what the drawing is: a single stroke that
    happens to leave the page and come back. `bracket.outline` hands back
    two and `lattice.outline` one per mark; the number is the drawing's,
    never the interface's.
    """
    return (line(width, height),)


#: How much clearance a block of text keeps from this drawing, in stroke
#: widths. Half of it is the stroke's own physical extent either side of
#: its centreline: every segment here is upright or flat, and at this
#: drawing's only corner angle -- a right angle, between a riser and a
#: tread -- a mitre and a round join both put the outline half a stroke
#: width past the corner on each axis. The other half is a gutter, so a
#: word set at the safe area's own edge is not set against the drawing. A
#: family drawn some other way measures its own, which is why the registry
#: reads this off the family: `chevrons.py` keeps more, because it is the
#: one family here that draws a slanted segment.
CLEARANCE_STROKE_WIDTHS: Final = 1.0
