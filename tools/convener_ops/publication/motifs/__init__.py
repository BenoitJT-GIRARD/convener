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
from typing import Final, Protocol

from . import ribbon

__all__ = [
    "FAMILIES",
    "RIBBON",
    "Family",
    "UnknownMotifFamilyError",
    "clearance",
    "family",
    "names",
    "path",
    "safe_margins",
    "stroke_width",
]


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


class Margins(Protocol):
    """How far in from the left and the right a word has to start.

    `clearance` is the room a text block keeps beyond the drawing's own
    deepest reach, already in the canvas's units -- the registry computes it
    from the family's own `clearance_stroke_widths` and the charter's
    `width_ratio`, so a family never reads a charter to answer this.
    """

    def __call__(
        self, width: float, height: float, *, clearance: float
    ) -> tuple[float, float]: ...


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
    #: The text safe area, in the canvas's own units.
    margins: Margins
    #: How much clearance a block of text keeps from this drawing's reach,
    #: in stroke widths. The family's own measurement -- see `ribbon.py`'s
    #: own constant for what the ribbon's two halves cover.
    clearance_stroke_widths: float


#: The charter's ribbon, and until now the only drawing there was.
RIBBON: Final = Family(
    name="ribbon",
    fields=("stroke", "width_ratio"),
    path=ribbon.path,
    margins=ribbon.margins,
    clearance_stroke_widths=ribbon.CLEARANCE_STROKE_WIDTHS,
)

#: Every family, by the name a charter names it. Written out rather than
#: discovered by walking the directory: a name a charter may write is part
#: of the product's own contract, and `tests/publication/motifs/
#: test_registry.py` is what holds this table and the directory to each
#: other.
FAMILIES: Final[dict[str, Family]] = {RIBBON.name: RIBBON}


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


def clearance(name: str, width: float, height: float, *, ratio: float) -> float:
    """The room a block of text keeps beyond the named family's own reach,
    in the canvas's units."""
    return (
        stroke_width(width, height, ratio=ratio) * family(name).clearance_stroke_widths
    )


def safe_margins(
    name: str, width: float, height: float, *, ratio: float
) -> tuple[float, float]:
    """How far in from each side a word has to start to clear the named
    family's drawing, in the canvas's units.

    Two readers, one arithmetic: `visual._motif_safe_margins` turns these
    into the `vw` its own CSS is written in, and
    `brand_templates.render_video_call_background` places a plate of text
    between them.
    """
    return family(name).margins(
        width, height, clearance=clearance(name, width, height, ratio=ratio)
    )
