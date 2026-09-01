"""The `chevrons` family: straight segments meeting at an angle, stacked.

A column of chevrons standing in each margin, every one of them two
segments meeting at a point below and every one the same size as the one
above it. It reads as a sequence advancing a step at a time, which is what
a series of talks is, and it is the fourth drawing this product has:
`ribbon.py` is one continuous curve traced off an instance's own poster,
`bracket.py` is the product's own arcs squared off, `lattice.py` is a
texture of short marks on a grid, and this is an angle repeated down a
page.

Straight segments, and the rule behind that
--------------------------------------------
A chevron is three points and two `L` commands. `tests/publication/motifs/
test_registry.py` refuses a curve command in every family but the ribbon,
because the ribbon is somebody's own mark and a second curve would read as
a variant of it rather than as a charter of its own.

One drawing, inked and measured
---------------------------------
`chevrons` below returns every point of both columns once. `path` writes
those points as `M`/`L` for whoever inks the drawing, and `outline` hands
the same points to the registry, which measures every corridor on a page
against them. What is painted and what is measured cannot become two
drawings, because a straight segment reaches past neither of its ends.

Nothing is a pixel
-------------------
A chevron's width, its depth and the distance one keeps from the next are
fractions of the canvas's shorter side, so the shape stays the shape at
every aspect ratio. The two figures that say where a column stops are
fractions of the height, because how far down a page a column runs is a
property of that page. The same function draws a 1200 square, a 1200x630
banner, an A4 print at 300 dpi, a 1920x1080 video-call frame and the
400-unit square the chrome sets in a masthead.

Where every number comes from
------------------------------
Five figures decide the columns, and each is fixed by something this
repository already measures:

- **`_TIP_HALF_ANGLE_DEGREES`, the angle the two segments meet at.** The
  product's own mark opens by 80 degrees: both arcs of
  `assets/brand/convener/convener-mark.svg` run from 40 to 320, and
  `bracket._OPENING_HALF_ANGLE_DEGREES` carries the half of that onto the
  brackets' returns. A chevron here is that same opening laid on its side,
  so the angle in this drawing is the angle in the product's artwork
  rather than one chosen beside it.
- **`_EDGE_GUTTER`, how far a chevron's arm-ends stand off the edge.** The
  heaviest stroke any charter this repository holds draws a motif at is
  0.03 of the shorter side (`examples/the-example-collective/`). At a gutter of exactly
  that, the paint at an arm's end stops half a stroke short of the edge at
  the heaviest charter and further at every other, so no column bleeds off
  the page it is drawn on.
- **`_SPAN`, how wide a chevron is.** Bounded from above by the ground a
  page can spare, and taken at that bound: the deepest drawing this
  product already ships is the bracket, whose left arm reaches 0.1403 of
  the shorter side (`bracket._OUTER_HALF_WIDTH` at its own stand-off).
  `_EDGE_GUTTER` plus `_SPAN` is that figure, so a composition gives up
  exactly the room a charter naming the product's own mark already asks
  for.
- **`_PITCH_RISES`, how far one chevron stands from the next.** In
  chevrons' own depths, and a whole number of them: at one the next
  chevron's arm-ends would begin on the tip above, so two is the smallest
  count that leaves ground between them. What that ground measures once
  the drawing is inked is the second half of the figure -- at two it is
  0.0657 of the shorter side against a stroke of 0.03 at the heaviest
  charter here, so a column stays a column of separate chevrons rather
  than closing into a zigzag.
- **`_BOTTOM` and `_RIGHT_BOTTOM`, the rows each column stops at.** Two
  bands of a page fix them, and both are stated at the constants
  themselves.

`tools/visuals/check-templates.mjs` is what measures the result, in a
browser, for every charter this repository holds crossed with every
family: at the stroke weights those charters carry, this drawing clears
every block of type in all three downloadable templates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from .. import composition

Point = tuple[float, float]

#: One chevron: the end of its upper arm, its tip, and the end of its
#: lower arm. A column is a great many of these and nothing else.
Chevron = tuple[Point, Point, Point]


def _short_side(width: float, height: float) -> float:
    """The dimension a chevron's own shape has to track to stay itself."""
    return min(width, height)


# ----------------------------------------------------------------------
# The chevron's own shape
# ----------------------------------------------------------------------

#: Half the angle the two segments meet at, in degrees, measured from the
#: axis the tip sits on. The module docstring has the artwork it is read
#: off, and `tests/publication/motifs/test_chevrons.py` holds it there.
_TIP_HALF_ANGLE_DEGREES: Final = 40.0

#: How far a chevron's arm-ends stand off the edge the column belongs to,
#: in short sides.
_EDGE_GUTTER: Final = 0.03

#: How wide one chevron is, in short sides: arm-end to arm-end, across the
#: page. With the gutter above it is the whole of what a column asks a
#: composition for.
_SPAN: Final = 0.1103

#: How far the tip hangs below the arm-ends, in short sides. Not a figure
#: anything chooses -- it is what the span and the angle come to, which is
#: what makes this drawing the product's own opening rather than a wedge
#: that resembles it.
_RISE: Final = (_SPAN / 2) / math.tan(math.radians(_TIP_HALF_ANGLE_DEGREES))

#: How far one chevron stands from the next, in rises.
_PITCH_RISES: Final = 2.0

#: The same distance in short sides, which is what the drawing is laid out
#: on.
_PITCH: Final = _PITCH_RISES * _RISE

#: The row the announcement's registration block begins at, as a fraction
#: of the 1200-unit square it is drawn on
#: (`brand_templates._ANNOUNCEMENT_REGISTER_TOP`, 870). That block takes
#: the free strip nearest the left edge over its own rows, and a column
#: standing a gutter off that edge would leave it a strip a gutter wide --
#: which `brand_templates._ANNOUNCEMENT_SLOT_FLOOR` refuses outright
#: rather than drawing a slot nobody could drop a code into. So the left
#: column finishes above those rows and the slot gets the whole page.
_REGISTER_TOP: Final = 0.725

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

#: The last row of the page the left column's tips may reach, in heights:
#: the register band, less the gutter every other edge of this drawing
#: keeps. The two figures are measured against different axes and are the
#: same length on the square both of them are read off.
_BOTTOM: Final = _REGISTER_TOP - _EDGE_GUTTER

#: The last row the right column's tips may reach, in heights: the content
#: band, less that same gutter. Every drawing this product ships is the
#: short one on the right, and this is why.
_RIGHT_BOTTOM: Final = _CONTENT_TOP - _EDGE_GUTTER

#: How far a column reaches into the page from the edge it stands against,
#: in short sides. Not a figure anything sets -- it is what the gutter and
#: the span come to, and it is what a composition pays for.
REACH: Final = _EDGE_GUTTER + _SPAN


@dataclass(frozen=True)
class Waypoints:
    """Every chevron of both columns, in the order each is drawn.

    Exposed rather than folded into `path`, for the reason `bracket.py`'s
    own `Waypoints` gives: how deep a column reaches, how far down the
    page it runs and what does not move when only the long side changes
    are trivial to pin against these two sequences and would need an SVG
    path string re-parsed otherwise. Here they are also the drawing
    itself, since straight segments join them.
    """

    #: The column standing against the left edge, running the page.
    left: tuple[Chevron, ...]
    #: The column standing against the right edge: the same chevrons at
    #: the same rows, and the opening of that sequence rather than all of
    #: it.
    right: tuple[Chevron, ...]


def _arm_tops(short: float, height: float, stop: float) -> tuple[float, ...]:
    """The row each chevron's arm-ends sit on, down the page, as far as
    `stop`.

    One sequence, read to two depths. The first chevron's arms sit a
    gutter below the top edge, every one after it a pitch further down,
    and the last is whichever one still has its tip above `stop`. The
    right column takes the opening of the left column's own sequence, so
    the two sides of a page are one drawing read twice.

    There is no canvas this returns nothing for. The first chevron's tip
    reaches `(_EDGE_GUTTER + _RISE)` of the *shorter* side, 0.0957 of it,
    and the earlier of the two floors is `_RIGHT_BOTTOM` of the *height*,
    0.194 of it. The shorter side is never longer than the height, so the
    first chevron always fits, at any aspect ratio either way up. A family
    that could return no geometry would report no corridor either, and
    every block on that page would then be placed against a drawing that
    is not there.
    """
    floor = stop * height
    rise = _RISE * short
    rows: list[float] = []
    top = _EDGE_GUTTER * short
    while top + rise <= floor:
        rows.append(top)
        top += _PITCH * short
    return tuple(rows)


def _column(short: float, rows: tuple[float, ...]) -> tuple[Chevron, ...]:
    """One column's chevrons, measured from the edge it stands against.

    The arms open toward the top of the page and the tip hangs below
    them, so a column reads down the page in the direction it is set.
    """
    gutter = _EDGE_GUTTER * short
    span = _SPAN * short
    rise = _RISE * short
    return tuple(
        (
            (gutter, top),
            (gutter + span / 2, top + rise),
            (gutter + span, top),
        )
        for top in rows
    )


def waypoints(width: float, height: float) -> Waypoints:
    """Every chevron of both columns on a canvas of the given size."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")
    short = _short_side(width, height)
    return Waypoints(
        left=_column(short, _arm_tops(short, height, _BOTTOM)),
        right=tuple(
            ((width - a[0], a[1]), (width - b[0], b[1]), (width - c[0], c[1]))
            for a, b, c in _column(short, _arm_tops(short, height, _RIGHT_BOTTOM))
        ),
    )


def marks(width: float, height: float) -> tuple[Chevron, ...]:
    """Every chevron, both columns, in the order they are drawn.

    One list, read twice: `path` writes it as `M`/`L` for whoever inks the
    drawing and `outline` hands it to the registry, which measures every
    corridor against it. Two readings of one derivation, for the reason
    `ribbon.segments` gives.
    """
    columns = waypoints(width, height)
    return (*columns.left, *columns.right)


def _fmt(number: float) -> str:
    """A coordinate, trimmed of the trailing zeros a fixed format leaves."""
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def path(width: float, height: float) -> str:
    """This family's drawing for a canvas of the given size, as an SVG path `d`.

    One subpath per chevron, each an `M` and two `L`s, and no curve
    command anywhere: the ribbon is the one drawing this product has that
    is a continuous curve, and it is the one traced off an instance's own
    poster. The charter's `stroke` and `width_ratio` say what a consumer
    inks this with (`motifs.stroke_width`); this function only ever
    returns geometry.
    """
    commands: list[str] = []
    for mark in marks(width, height):
        start, *rest = mark
        commands.append(f"M {_fmt(start[0])} {_fmt(start[1])}")
        commands.extend(f"L {_fmt(x)} {_fmt(y)}" for x, y in rest)
    return "\n".join(commands)


def outline(width: float, height: float) -> tuple[tuple[Point, ...], ...]:
    """This family's drawing as a polyline, for the registry to measure.

    One three-point run per chevron, because that is what a column is: a
    run of separate angles, none of them joined to another.
    `bracket.outline` hands back two runs and `ribbon.outline` one; the
    number is the drawing's, never the interface's.
    """
    return marks(width, height)


#: How much clearance a block of text keeps from this drawing, in stroke
#: widths, and the first figure in this package that is not 1.0.
#:
#: Half of it is a gutter, so that a word set at the safe area's own edge
#: is not set against the drawing. The other part is the stroke's own
#: reach across the page, and a slanted segment reaches further across
#: than an upright one does: paint extends half a stroke *perpendicular*
#: to a segment, which on an arm standing 50 degrees from the horizontal
#: is `0.5 / sin(50)` of a stroke measured along the axis a corridor is
#: measured on. The round cap at an arm's end reaches half a stroke in
#: every direction and so is inside that. The mitre at the tip runs down
#: the axis the two arms are symmetric about and reaches no further
#: across than the arms themselves.
#:
#: A family drawn some other way measures its own, which is why the
#: registry reads this off the family: `bracket.py` and `lattice.py` are
#: both 1.0 because every segment either of them draws is upright.
CLEARANCE_STROKE_WIDTHS: Final = (
    0.5 / math.sin(math.radians(90.0 - _TIP_HALF_ANGLE_DEGREES)) + 0.5
)
