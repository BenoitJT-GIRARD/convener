"""The `lattice` family: a field of short marks, offset row to row.

The third drawing this product has, and the first that is not a mark at
all. `ribbon.py` is one continuous stroke crossing the page, traced off one
instance's own poster; `bracket.py` is two shapes standing in the margins,
the product's own arcs squared off. This is a *texture*: many small
identical marks on one grid whose alternate rows are shifted half a step
across, standing in the margins either side of the page -- down the whole
of the left one, and across the top of the right one. It reads as
regularity and recurrence, which is what a series is -- the same room, the
same hour, every fortnight -- and a series is what this product runs.

Straight segments, and why that is not a style
------------------------------------------------
Every mark is two points and one `L`. `tests/publication/motifs/
test_registry.py` refuses a curve command in every family but the ribbon,
and the reason is not tidiness: the ribbon is a continuous curve because it
is somebody's own mark, traced pixel by pixel, so a second drawing built
out of curves would read as a variant of that mark rather than as a charter
of its own.

One drawing, inked and measured
---------------------------------
`marks` below returns every point of the field once. `path` writes those
points as `M`/`L` for whoever inks the drawing and `outline` hands the same
points to the registry, which is what every corridor on a page is measured
against. A drawing that is inked and a drawing that is measured must not be
able to become two different drawings -- the discipline `ribbon.segments`
states, and the one this family gets for nothing, because a straight
segment reaches past neither of its ends.

Nothing is a pixel
-------------------
The field has one unit, `_STEP`, and it is a fraction of the canvas's
shorter side; every length across and down the page is a multiple of it.
The only figure measured against an axis of the canvas is the one that says
where the field stops, and it is a fraction of the height, because running
down whatever page it is given is what a field does. So the same function
draws a 1200 square, a 1200x630 banner, an A4 page at ten units a
millimetre, a 1920x1080 video-call frame and the 400-unit square the chrome
sets in a masthead, and the texture has the same grain on all five.

Where every number comes from
------------------------------
Nothing here is a shape somebody liked. Four figures decide the field, and
each is fixed by a measurement this repository already holds:

- **`_STEP`, the field's own unit.** Bounded from below by the heaviest
  stroke a charter here may draw -- 0.03 of the shorter side, the ceiling
  `tests/publication/motifs/test_lattice.py::HEAVIEST_RATIO` holds every
  `motif.width_ratio` under -- because a mark one step long, painted at
  that weight with a round cap at each end, would close the gap to the
  next mark down its column and the field would become a rule. At 0.045
  that gap is a third of the mark's own length, so the field stays a field
  at every charter this repository holds, the heaviest of which draws at
  0.024.
- **`_COLUMNS`, how many columns stand in each panel.** Bounded from above
  by the ground a page can spare: the deepest drawing this product already
  ships is the bracket, whose left arm reaches 0.1403 of the shorter side
  (`bracket._OUTER_HALF_WIDTH` at its own stand-off). Three columns reach
  0.1125 and four would reach 0.1575, so three is the most columns that ask
  a composition for no more room than a charter naming the bracket already
  gives up.
- **`_GUTTER_STEPS`, the field's own margin.** Half a step, from the left
  edge, the right edge and the top edge alike: the field keeps the same
  distance from every edge it meets, so the texture reads as one thing
  rather than as three decisions.
- **`_BOTTOM`, the row the left panel stops at.** The bottom is the one
  edge the field does not keep its own gutter from, and two pages fix the
  figure. The announcement template sets its registration slot in whatever
  ground the drawing leaves over rows 870 to 1140 of its 1200-unit square
  (`brand_templates._ANNOUNCEMENT_REGISTER_TOP`), taking the free strip
  nearest the left edge -- and a field standing half a step off that edge
  leaves a strip nine units wide there, which
  `brand_templates._ANNOUNCEMENT_SLOT_FLOOR` refuses outright rather than
  drawing a slot nobody could drop a code into. The video-call background
  sets the code a participant scans at a fixed distance from its own bottom
  right corner (`_CODE_RIGHT_GAP`, `_CODE_BOTTOM_GAP`, `_CODE_SIDE`), and
  nothing about that corner moves with a drawing. At 0.68 the last row's
  ink ends at row 729 of the announcement, 141 above its register band, and
  at row 656 of the background, 108 above the code's own label.
- **`_RIGHT_BOTTOM`, the row the right panel stops at, higher up the page
  than the left.** Not a gesture: `.content` -- the "what to expect" copy
  and the speaker's frame beside it -- is the one band a generated poster
  sets against the clearance alone rather than against a family's own
  reach, because no drawing this product ships reaches those rows on that
  side (`visual._motif_content_right_margin`). Measured in the pinned
  engine, that band begins at 0.317 of a square and 0.224 of an A4 print,
  and the banner has none of it. So the right panel finishes above the
  earlier of the two, exactly as the bracket's own right arm does -- that
  one ends at 0.209. At 0.20 the last row on this side ends 0.024 of the
  page above the band, which is more than the whole clearance it is padded
  by at the heaviest charter here (0.03 of the shorter side is 0.021 of an
  A4's height).

`tools/visuals/check-templates.mjs` is what measures the result, in a
browser, for every charter this repository holds crossed with every family:
at the four stroke weights those charters carry, this drawing clears every
block of type in all three downloadable templates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

Point = tuple[float, float]

#: One mark: where it starts and where it ends. A field is a great many of
#: these and nothing else.
Mark = tuple[Point, Point]


def _short_side(width: float, height: float) -> float:
    """The dimension the field's own grain has to track to stay itself."""
    return min(width, height)


# ----------------------------------------------------------------------
# The field's one unit, and every length as a multiple of it
# ----------------------------------------------------------------------

#: The step, in short sides: how far one column stands from the next. Every
#: other length across or down the page is a multiple of this, so the
#: texture has one grain rather than a horizontal decision and a vertical
#: one. The module docstring has the two measurements that fix it.
_STEP: Final = 0.045

#: How long a mark is, in steps. One: a mark is exactly as long as its
#: column stands from the next, so the field is as dense down a column as
#: it is across.
_MARK_STEPS: Final = 1.0

#: How far one row stands from the next, in steps. Two, which is the mark
#: and a gap of its own length -- before the stroke is painted. What that
#: gap actually measures once the drawing is inked is what fixes `_STEP`.
_ROW_STEPS: Final = 2.0

#: How far a row is shifted from the one above it, in steps. Half, which is
#: the whole of what makes this a lattice rather than a set of columns.
_OFFSET_STEPS: Final = 0.5

#: How far the field stands off each edge it meets, in steps. Half, and the
#: same on the left, the right and the top.
_GUTTER_STEPS: Final = 0.5

#: How many columns stand in each panel.
_COLUMNS: Final = 3

#: The last row of the page the left panel's ink may reach, in heights.
#: The bottom is the one edge the field does not keep its own gutter from,
#: and these two are the only figures here measured against an axis of the
#: canvas rather than against the step.
_BOTTOM: Final = 0.68

#: The last row the right panel's ink may reach, in heights. Higher up the
#: page than the left, and the module docstring says which band on that
#: side of a generated poster is why. Every drawing this product ships is
#: the short one on the right, for that same reason.
_RIGHT_BOTTOM: Final = 0.20

#: How far the field reaches into the page from either edge, in short
#: sides: its gutter, plus the columns beyond the first. Not a figure
#: anything sets -- it is what the two constants above come to, and it is
#: what a composition pays for.
REACH: Final = (_GUTTER_STEPS + _COLUMNS - 1) * _STEP


@dataclass(frozen=True)
class Waypoints:
    """Every mark of the field, panel by panel.

    Exposed rather than folded into `path`, for the reason `bracket.py`'s
    own `Waypoints` gives: how deep the field reaches, how far down the
    page it runs and what does not move when only the long side changes are
    trivial to pin against these two sequences and would need an SVG path
    string re-parsed otherwise. Here they are also the drawing itself,
    since straight segments join them.
    """

    #: The panel standing against the left edge, running the page.
    left: tuple[Mark, ...]
    #: The panel standing against the right edge: the same grid, mirrored,
    #: and the opening rows of it rather than all of them.
    right: tuple[Mark, ...]


def _row_tops(short: float, height: float, stop: float) -> tuple[float, ...]:
    """Where each row's marks begin, down the page, as far as `stop`.

    One grid, read to two depths. The first row's ink starts at the field's
    own gutter below the top edge; every row after it is `_ROW_STEPS`
    further down; the last is whichever one still ends above `stop`. The
    right panel's rows are the opening of the left panel's own sequence
    rather than a second grid, so the two sides of a page are one texture
    read twice and never two drawings.

    There is no canvas this returns nothing for, and it is worth saying why
    rather than guarding against it: the first row's ink ends at
    `(_GUTTER_STEPS + _MARK_STEPS) * _STEP` of the *shorter* side, 0.0675
    of it, and the earlier of the two floors is `_RIGHT_BOTTOM` of the
    *height*, 0.20 of it. The shorter side is never longer than the height,
    so the first row always fits, at any aspect ratio either way up. A
    family that could return no geometry would report no corridor either,
    and every block on that page would then be placed against a drawing
    that is not there.
    """
    step = _STEP * short
    length = _MARK_STEPS * step
    floor = stop * height
    rows: list[float] = []
    top = _GUTTER_STEPS * step
    while top + length <= floor:
        rows.append(top)
        top += _ROW_STEPS * step
    return tuple(rows)


def _panel(short: float, rows: tuple[float, ...]) -> tuple[Mark, ...]:
    """One panel's marks, measured from the edge it stands against.

    Every row is drawn from the same grid of columns; an odd row is shifted
    half a step across and gives up its last column, so the panel reaches
    exactly `REACH` on every row rather than bulging on alternate ones.
    """
    step = _STEP * short
    length = _MARK_STEPS * step
    gutter = _GUTTER_STEPS * step
    offset = _OFFSET_STEPS * step
    made: list[Mark] = []
    for index, top in enumerate(rows):
        shifted = index % 2 == 1
        columns = _COLUMNS - 1 if shifted else _COLUMNS
        first = gutter + (offset if shifted else 0.0)
        for column in range(columns):
            x = first + column * step
            made.append(((x, top), (x, top + length)))
    return tuple(made)


def waypoints(width: float, height: float) -> Waypoints:
    """Every mark of the field on a canvas of the given size."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")
    short = _short_side(width, height)
    return Waypoints(
        left=_panel(short, _row_tops(short, height, _BOTTOM)),
        right=tuple(
            ((width - x0, y0), (width - x1, y1))
            for (x0, y0), (x1, y1) in _panel(
                short, _row_tops(short, height, _RIGHT_BOTTOM)
            )
        ),
    )


def marks(width: float, height: float) -> tuple[Mark, ...]:
    """Every mark of the field, both panels, in the order they are drawn.

    One list, read twice: `path` writes it as `M`/`L` for whoever inks the
    drawing and `outline` hands it to the registry, which measures every
    corridor against it. Two readings of one derivation, for the reason
    `ribbon.segments` gives.
    """
    field = waypoints(width, height)
    return (*field.left, *field.right)


def _fmt(number: float) -> str:
    """A coordinate, trimmed of the trailing zeros a fixed format leaves."""
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def path(width: float, height: float) -> str:
    """This family's drawing for a canvas of the given size, as an SVG path `d`.

    One subpath per mark, each an `M` and a single `L`, and no curve command
    anywhere: the ribbon is the one drawing this product has that is a
    continuous curve, and it is the one traced off an instance's own poster.
    The charter's `stroke` and `width_ratio` say what a consumer inks this
    with (`motifs.stroke_width`); this function only ever returns geometry.
    """
    commands: list[str] = []
    for (x0, y0), (x1, y1) in marks(width, height):
        commands.append(f"M {_fmt(x0)} {_fmt(y0)}")
        commands.append(f"L {_fmt(x1)} {_fmt(y1)}")
    return "\n".join(commands)


def outline(width: float, height: float) -> tuple[tuple[Point, ...], ...]:
    """This family's drawing as a polyline, for the registry to measure.

    One two-point run per mark, because that is what the field is: a great
    many separate strokes, none of them joined to another. `bracket.outline`
    hands back two runs and `ribbon.outline` one; the number is the
    drawing's, never the interface's.
    """
    return marks(width, height)


#: How much clearance a block of text keeps from this drawing, in stroke
#: widths. Half of it is the stroke's own physical extent either side of a
#: mark's centreline, which for a straight segment is the whole of what it
#: paints beyond its own points -- a round cap reaches half a stroke past
#: each end and half a stroke either side of it, and no mark here has a
#: corner at all. The other half is a gutter, so a word set at the safe
#: area's own edge is not set against the field. A family drawn some other
#: way measures its own, which is why the registry reads this off the
#: family.
CLEARANCE_STROKE_WIDTHS: Final = 1.0
