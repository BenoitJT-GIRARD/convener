"""Every drawing a charter may name, and the one place a name becomes one.

`motif.family` is the field a charter writes to say which drawing it wants;
this package is where that string is answered. One module per family, each
of them pure geometry -- a canvas size in, an SVG path and a pair of
margins out, no file read and no colour decided -- and one `Family` entry
here per module, so the set of names a charter may write and the set of
modules that can draw one are the same set by construction.

Why a registry rather than an import
-------------------------------------
`ribbon.py` was the motif: `visual.py` and `brand_templates.py` imported it
by name and drew it whatever the charter said, and `motif` carried
`ribbon_stroke` and `ribbon_width_ratio` -- field names that could only ever
be true of one drawing. A second charter wanting a different mark had
nowhere to say so. Naming the family in the charter and dispatching on it
here is what makes a second one possible without a second call site.

**An unknown family stops the build and names the ones that exist.** Falling
back to a drawing the charter did not ask for is the failure this whole
arrangement exists to prevent: a duplicate would ship somebody else's mark
and nothing would say so.

What is the family's and what is the motif's
----------------------------------------------
The *drawing* is the family's: the path, how deep into the canvas it
reaches, and how much clearance a block of text keeps from it. The *ink* is
the motif's, whatever family it names: `stroke` is the colour it is drawn
in and `width_ratio` its weight as a fraction of the composition's shorter
side. `stroke_width` below is that second pair's arithmetic, and it sits
here rather than in a family because every family this product ships is a
stroked drawing and none of them measures its weight differently.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Final, Protocol

from . import bracket, lattice, ribbon

__all__ = [
    "BRACKET",
    "FAMILIES",
    "LATTICE",
    "RIBBON",
    "CoveredCanvasError",
    "Family",
    "Point",
    "Span",
    "UnknownMotifFamilyError",
    "clearance",
    "family",
    "free_spans",
    "names",
    "outline",
    "path",
    "safe_margins",
    "stroke_width",
]


#: A point in the canvas's own units, and a range of x in them. A `Span`
#: is always `(start, end)` with `start <= end`.
Point = tuple[float, float]
Span = tuple[float, float]


class UnknownMotifFamilyError(RuntimeError):
    """A `motif.family` naming a drawing this product does not have.

    Carries the whole message rather than a code, for the reason
    `brand.MissingMotifError` gives, and lists the families that do exist:
    the thing a person needs at the moment a build stops is what they may
    write instead.
    """


class Drawing(Protocol):
    """The path a family draws on a canvas of the given size."""

    def __call__(self, width: float, height: float) -> str: ...


class Shape(Protocol):
    """The same drawing as a polyline, for the corridor arithmetic below.

    One tuple of points per continuous run of the drawing -- one for the
    ribbon, which is a single stroke; two for the bracket, one per
    bracket. A straight segment joins each consecutive pair, so a family
    that draws curves flattens them finely enough that the polyline's own
    reach is the curve's (`ribbon._FLATTEN_STEPS` measures how finely).

    Points outside the canvas are welcome and expected: a drawing that
    runs off an edge says so here, and the clipping below is the
    registry's job rather than each family's.
    """

    def __call__(
        self, width: float, height: float
    ) -> tuple[tuple[Point, ...], ...]: ...


@dataclass(frozen=True)
class Family:
    """One drawing, under the name a charter writes to ask for it."""

    #: The string `motif.family` holds.
    name: str
    #: What a `motif` naming this family has to carry beyond the fields
    #: every motif carries. Every family this product ships is a stroked
    #: drawing and declares the same two; one that is not would declare its
    #: own, which is why this is the family's to say and not a constant.
    fields: tuple[str, ...]
    #: The geometry, as an SVG path `d`.
    path: Drawing
    #: The same geometry as a polyline, which is what every corridor on
    #: this page is measured against. A family declares its drawing twice
    #: and in two notations, but never twice over: each module below
    #: derives both from one list of points, and its own tests hold them
    #: to each other.
    outline: Shape
    #: How much clearance a block of text keeps from this drawing's reach,
    #: in stroke widths. The family's own measurement -- see `ribbon.py`'s
    #: own constant for what the ribbon's two halves cover.
    clearance_stroke_widths: float


#: The ribbon: one continuous stroke, traced off one instance's own
#: announcement poster. A charter naming it is drawn with that instance's
#: mark, which is why the charters this repository ships publicly name the
#: family below instead.
RIBBON: Final = Family(
    name="ribbon",
    fields=("stroke", "width_ratio"),
    path=ribbon.path,
    outline=ribbon.outline,
    clearance_stroke_widths=ribbon.CLEARANCE_STROKE_WIDTHS,
)

#: The product's own mark in straight segments -- what `brand/convener/
#: brand.json` and `instances/example/` are drawn with, and what a
#: duplicate that has chosen no charter of its own gets.
BRACKET: Final = Family(
    name="bracket",
    fields=("stroke", "width_ratio"),
    path=bracket.path,
    outline=bracket.outline,
    clearance_stroke_widths=bracket.CLEARANCE_STROKE_WIDTHS,
)

#: A field of short marks, offset row to row -- a texture rather than a
#: mark, and the one drawing here that is nobody's artwork squared off. It
#: reaches less far into a page than the bracket does and says where every
#: figure it is built from comes from (`lattice.py`).
LATTICE: Final = Family(
    name="lattice",
    fields=("stroke", "width_ratio"),
    path=lattice.path,
    outline=lattice.outline,
    clearance_stroke_widths=lattice.CLEARANCE_STROKE_WIDTHS,
)

#: Every family, by the name a charter names it. Written out rather than
#: discovered by walking the directory: a name a charter may write is part
#: of the product's own contract, and `tests/publication/motifs/
#: test_registry.py` is what holds this table and the directory to each
#: other.
FAMILIES: Final[dict[str, Family]] = {
    RIBBON.name: RIBBON,
    BRACKET.name: BRACKET,
    LATTICE.name: LATTICE,
}


def names() -> str:
    """Every family that exists, for a message that has to list them."""
    return ", ".join(sorted(FAMILIES))


def family(name: str) -> Family:
    """The drawing a charter asked for, or a refusal naming the ones there
    are.

    Never a fall back to whichever family happens to be first: a build that
    quietly drew a mark the charter did not name would ship a duplicate
    wearing somebody else's identity, and nothing on the page would say so.
    """
    found = FAMILIES.get(name)
    if found is None:
        raise UnknownMotifFamilyError(
            f"{name!r} is not a motif family this product draws. The "
            f"families it has are: {names()}"
        )
    return found


def stroke_width(width: float, height: float, *, ratio: float) -> float:
    """The stroke width for a canvas of the given size, at the given ratio.

    Pure geometry, deliberately not a charter reader itself -- a caller
    fetches `ratio` once with `brand.motif_width_ratio(repo_root())` and
    threads it through, the same separation a family keeps between its own
    `path` and its `waypoints`. Tracks the *shorter* side on purpose: a wide
    banner and a tall print use the same ratio, so the stroke never balloons
    on the long axis the way a naive `width`-relative value would on a
    banner, or a `height`-relative one would on a print.
    """
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")
    return ratio * min(width, height)


def path(name: str, width: float, height: float) -> str:
    """The named family's drawing, as an SVG path `d`."""
    return family(name).path(width, height)


def outline(name: str, width: float, height: float) -> tuple[tuple[Point, ...], ...]:
    """The named family's drawing as a polyline, in the canvas's units."""
    return family(name).outline(width, height)


def clearance(name: str, width: float, height: float, *, ratio: float) -> float:
    """The room a block of text keeps beyond the named family's own reach,
    in the canvas's units."""
    return (
        stroke_width(width, height, ratio=ratio) * family(name).clearance_stroke_widths
    )


def _rows(
    height: float, top: float | None, bottom: float | None
) -> tuple[float, float]:
    """The band of rows a corridor is being asked about, defaulted to all
    of them and refused if it is upside down."""
    first = 0.0 if top is None else top
    last = height if bottom is None else bottom
    if last < first:
        raise ValueError(
            f"a band runs from its first row to its last: {first} is below {last}"
        )
    return first, last


def _crosses(
    start: Point, end: Point, first: float, last: float
) -> tuple[float, float] | None:
    """The x-range one straight segment occupies between two rows.

    `None` when the segment never enters the band at all. A segment lying
    flat inside it contributes both its ends; one crossing it contributes
    the two points where it enters and where it leaves, computed rather
    than stood in for by its own endpoints -- which is the whole reason a
    band is worth asking about. The ribbon's tail runs from x 280 down to
    x 210 over three hundred rows of the announcement, and answering "280"
    for every one of those rows would cost the page seventy units of
    ground the stroke is nowhere near.
    """
    (x0, y0), (x1, y1) = start, end
    if y0 == y1:
        return (min(x0, x1), max(x0, x1)) if first <= y0 <= last else None
    low, high = (y0, y1) if y0 < y1 else (y1, y0)
    if high < first or low > last:
        return None
    xs = [
        x0 + (x1 - x0) * (row - y0) / (y1 - y0)
        for row in (max(low, first), min(high, last))
    ]
    return min(xs), max(xs)


def _merge(spans: list[Span]) -> tuple[Span, ...]:
    """Overlapping and touching x-ranges joined into as few as say it."""
    merged: list[Span] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def covered(
    name: str,
    width: float,
    height: float,
    *,
    ratio: float,
    top: float | None = None,
    bottom: float | None = None,
) -> tuple[Span, ...]:
    """The ground the named family's drawing takes, over a band of rows.

    A tuple of x-ranges in the canvas's own units, each already widened by
    the family's own `clearance` on both sides and clipped to the canvas,
    left to right and never overlapping. `top` and `bottom` default to the
    whole canvas, which is what a caller wanting one corridor for a whole
    page passes.

    This is the one measurement on this page. `safe_margins` and
    `free_spans` below are both readings of it, `visual.py` and all three
    generated templates reach it through one of those two, and a family
    supplies the polyline it is taken from and nothing else.
    """
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")
    first, last = _rows(height, top, bottom)
    room = clearance(name, width, height, ratio=ratio)
    spans: list[Span] = []
    for run in outline(name, width, height):
        for start, end in pairwise(run):
            crossing = _crosses(start, end, first, last)
            if crossing is None:
                continue
            low = max(0.0, crossing[0] - room)
            high = min(width, crossing[1] + room)
            if low < high:
                spans.append((low, high))
    return _merge(spans)


def free_spans(
    name: str,
    width: float,
    height: float,
    *,
    ratio: float,
    top: float | None = None,
    bottom: float | None = None,
) -> tuple[Span, ...]:
    """Every strip of the canvas a word may occupy over a band of rows.

    The complement of `covered` inside the canvas, left to right. Usually
    one strip; two when the drawing runs down the middle of the band with
    ground either side of it, which is the announcement's own lower left
    -- the ribbon's tail crosses it diagonally, the "what to expect"
    column sits east of the stroke and the registration slot sits west of
    it, and no single margin measured from an edge can describe that.
    """
    free: list[Span] = []
    edge = 0.0
    for start, end in covered(name, width, height, ratio=ratio, top=top, bottom=bottom):
        if start > edge:
            free.append((edge, start))
        edge = max(edge, end)
    if edge < width:
        free.append((edge, width))
    return tuple(free)


class CoveredCanvasError(RuntimeError):
    """A drawing that leaves no ground across the middle of the canvas.

    Carries the whole message rather than a code, for the reason
    `UnknownMotifFamilyError` gives. It is a family's defect and not a
    caller's: every drawing this product ships stands in the margins, and
    one that paints across the middle of a band has no safe area to report
    there -- so it says so and stops, rather than handing back a margin no
    word could honour.
    """


def _size(number: float) -> str:
    """A length, for a message -- a whole number without a trailing zero."""
    return f"{number:g}"


def safe_margins(
    name: str,
    width: float,
    height: float,
    *,
    ratio: float,
    top: float | None = None,
    bottom: float | None = None,
) -> tuple[float, float]:
    """How far in from each side a word has to start to clear the named
    family's drawing, in the canvas's units.

    The strip of `free_spans` holding the middle of the canvas, read as
    two margins: how far its left edge sits from the canvas's left, and
    how far its right edge sits from the canvas's right. With no band
    given that is the whole page's corridor, which is what
    `visual._motif_safe_margins` turns into the `vw` its own CSS is
    written in and what `brand_templates.render_video_call_background`
    places a plate of text between. With a band given it is the corridor
    over those rows alone, which is what the two downloadable templates
    ask for, once per block of type.
    """
    for start, end in free_spans(
        name, width, height, ratio=ratio, top=top, bottom=bottom
    ):
        if start <= width / 2 <= end:
            return start, width - end
    first, last = _rows(height, top, bottom)
    raise CoveredCanvasError(
        f"the {name!r} motif leaves no ground across the middle of a "
        f"{_size(width)}x{_size(height)} canvas between rows {_size(first)} "
        f"and {_size(last)}: its drawing, plus the clearance a word keeps "
        "from it, covers the whole width there, so there is no safe area to "
        "report. A drawing this product ships stands in the margins of a "
        "page, not across it."
    )
