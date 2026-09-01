"""The device that stands beside the organisation's own address.

Three surfaces set the same lock-up -- the announcement template, the
flyer (`brand_templates.py`) and the poster the cockpit generates
(`visual.py`) -- so the device is written once, here, rather than three
times.

What was here, on all three, and why it could not stay
-------------------------------------------------------
`brand_templates` drew five squares, two drop-shaped markers with a hole
through each, the arc joining them and the tail that became the rule under
the address: every coordinate measured pixel by pixel off
`announcement-template_initial.png`, this instance's own announcement
poster, which `.gitignore` keeps out of this repository because it carries
a real person's photograph. `visual.py` drew two squares on a diagonal and
two dots joined by a short lead, and called itself "a deliberately
simplified reading" of the same poster -- which is a reading of it.

Both were drawn **at every charter**. A duplicate choosing `assets/brand/lattice/`
downloaded two templates and generated every poster carrying a device
taken from one instance's artwork. It is the same provenance that keeps
`ribbon` named by no charter but this instance's own, and the same class as
every raster and screenshot this repository has had to stop shipping.

What replaces it follows the charter, and does not become the product's
own mark
-----------------------------------------------------------------------
Which is where this parts company with the reasoning that put
`assets/brand/convener/convener-mark.svg` in the cockpit's browser tab. That
reasoning turned on the cockpit *being* the product: a tab icon says which
software a volunteer is running, and the instance's identity arrives
afterwards, at run time. These three surfaces are the opposite. They are
the instance's own artefacts, published under the instance's name, and the
box below stands in the logotype position beside that organisation's own
address. The product's two arcs closing on a dot there would read as *that
organisation's* logo -- and `TRADEMARK.md` reserves exactly those arcs
from the licence and asks a fork to rename. Shipping them by default into
every duplicate's public poster is the one place this product must not put
its own mark.

So the box holds the charter's own drawing: the family it names, from
`publication/motifs/`, on a square canvas of the box's own size, stroked in
`motif.stroke` at `motif.width_ratio`. A charter has no logotype to give
and never will -- identity is the one thing this product refuses to invent
-- but it does have a drawing, and a drawing at the size of a mark is the
only device that can be supplied without lending somebody a mark. What a
duplicate with a logo of its own does is put it there instead; both
templates say so in their own markup.

**A nested `<svg>` and not a `<g>` with a transform.** A nested one
establishes a viewport of its own and clips to it. Every family this
product draws runs off the edges of whatever canvas it is given -- the
ribbon's own connector travels twice the canvas's longer side past two of
them -- so a `<g>` would paint the device straight across the address
beside it. The clipping is what makes the box a box.
"""

from __future__ import annotations

from typing import Final

from . import motifs

__all__ = ["BOX", "DOT", "device"]

#: The device's own canvas, in units of its own. Every caller scales the
#: box to whatever its composition wants and none of them restates a
#: coordinate.
BOX: Final = 100.0

#: The dot the device closes on, as three fractions of the box: centre x,
#: centre y, radius. The only numbers here read off any artwork, and the
#: artwork is the product's own -- `assets/brand/convener/convener-mark.svg` is a
#: circle of radius 47.68 at (424.89, 255.19) on a 512 viewBox, which
#: `assets/brand/convener/README.md` records as measured off the original raster
#: and rebuilt rather than traced.
#: `assets/brand/convener/brand.json::motif._logo_dots` already reads its
#: *colour* off that same circle -- "it is the colour of the dot in
#: convener-mark.svg" -- so the dot the charter has been colouring all
#: along is the dot that is now drawn.
#: `tests/publication/test_template_mark.py` reads the three numbers back
#: out of that file.
DOT: Final = (424.89 / 512, 255.19 / 512, 47.68 / 512)


def _num(value: float) -> str:
    """A coordinate, at two decimals, without a trailing `.0`."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def device(
    *,
    family: str,
    ratio: float,
    ink: str,
    dots: str,
    attributes: str,
    indent: str = "",
) -> str:
    """The whole `<svg>`, with `attributes` the caller's own placement.

    `attributes` is where a caller says where the box goes and how big it
    is -- `x`/`y`/`width`/`height` in the two templates, a class the
    stylesheet sizes in the generated poster. The `viewBox` is not the
    caller's: it is what clips the drawing to its box, and a caller free
    to write its own would be free to write one that does not.
    """
    stroke = motifs.stroke_width(BOX, BOX, ratio=ratio)
    joiner = "\n" + indent + " " * 15
    drawing = joiner.join(motifs.path(family, BOX, BOX).splitlines())
    cx, cy, r = (_num(value * BOX) for value in DOT)
    return (
        f"{indent}<svg {attributes}\n"
        f'{indent}     viewBox="0 0 {_num(BOX)} {_num(BOX)}"\n'
        f'{indent}     aria-hidden="true" focusable="false">\n'
        f'{indent}  <path d="{drawing}"\n'
        f'{indent}        fill="none" stroke="{ink}" stroke-width="{_num(stroke)}"\n'
        f'{indent}        stroke-linecap="round" stroke-linejoin="round"/>\n'
        f'{indent}  <circle cx="{cx}" cy="{cy}" r="{r}" fill="{dots}"/>\n'
        f"{indent}</svg>"
    )
