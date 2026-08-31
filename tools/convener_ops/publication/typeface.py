"""How wide a line of type will be, before a glyph is drawn.

SVG does not wrap and cannot measure. A file this repository generates is
written once, in Python, and opened later in a text editor, in Inkscape or
in a browser -- so anything that has to *fit* (a name inside a plate, a
headline inside the corridor a motif leaves) has to be sized here, from the
string itself, with no rasteriser in the room. That is the same argument
`visual._scaled_font_size` already makes for a talk's title: the same
declaration must produce the same file on every machine, where a browser
measurement taken at build time could differ between two builds that agree
on every design decision.

What this replaces, and why one number was not enough
------------------------------------------------------
`brand_templates` used to carry a single figure -- one average advance per
character, `0.68` of the font size -- measured on the video-call
background's own two lines and described as "rounded *up*, so a line of
narrower letters is shrunk slightly sooner than it needs to be rather than
one unit too late". Measured against every line those files actually set,
in the face the charter names, that claim is false in both directions:

- `MONTHLY READING GROUP` runs at **0.735** of the font size per character
  and `THE EXAMPLE COLLECTIVE` at **0.706**. Both are wider than the estimate
  that was meant to bound them, which is why the background's own name line
  overruns its plate's 28-unit padding on both charters this repository
  ships -- by 22 units on one and 3 on the other. Nothing had overflowed
  the plate itself yet. Nothing was stopping it.
- `Join the discussion before and after the talk at` runs at **0.427**.
  Bounding that line with 0.68 would shrink it to two thirds of its
  designed size for no reason at all.

A single average cannot be both, so this module measures the two things
that actually differ: which character it is, and how heavy it is set.

Where the numbers come from
-----------------------------
Measured off `fonts/archivo-latin-standard-normal.woff2`, this repository's
own copy of the face `instance/data/brand.json` names, in the pinned engine
(`tools/visuals/`, D-27): every printable ASCII character at each of the
five weights these files set. Two of those weights are kept -- the lightest
(400) and the heaviest (900) -- because the spread between them is 23% on
lower-case and every weight in between falls inside it. Each figure is
rounded **up** to the nearest fiftieth of an em, which is a fifth of a unit
at the size a poster's own body copy is set: the rounding is what keeps two
tables to fifty lines instead of a hundred and forty, and it rounds the way
that shrinks a line rather than the way that overflows one.

`tools/visuals/check-templates.mjs` re-measures the whole table against the
committed font file on every run and refuses a drift, so the table cannot
quietly stop describing the face beside it -- which is the failure a
hand-copied measurement invites, and the reason this is not simply a
comment saying where the numbers came from.

What this does not claim
--------------------------
**It is not a text layout engine.** It sums advances and adds letter
spacing; it does not kern, and kerning in this face only ever pulls a pair
closer, so the sum is at worst a shade wide. That is the safe direction: an
estimate over the truth sets a line slightly smaller than it had to be,
where one under the truth puts it through the edge of a plate.

**It describes one face.** The two templates name the charter's display
face first and then the fallbacks any machine has
(`brand_templates._FALLBACK`), and a volunteer whose machine has no Archivo
gets one of those instead. No check here can measure a face this repository
does not ship. What it can do is size the file for the face the charter
declares and self-hosts (D-17) -- the one every rendering this project
performs actually uses.
"""

from __future__ import annotations

import unicodedata
from typing import Final

__all__ = ["HEAVY", "LIGHT", "WIDEST_ADVANCE_EM", "advance_em", "width"]

#: The two weights the tables below are measured at. A line set at either
#: is charged its own table; one set between them is charged whichever of
#: the two is wider for each character, because two tables cannot describe
#: five weights and the point of an estimate here is to bound the line.
LIGHT: Final = 400
HEAVY: Final = 900

#: Every printable ASCII character's advance at `LIGHT`, as a fraction of
#: the font size, grouped by the value they share.
_LIGHT_EM: Final = (
    (1.02, "@"),
    (0.96, "%"),
    (0.94, "W"),
    (0.86, "Mm"),
    (0.80, "GOQ"),
    (0.74, "CDHNRUw"),
    (0.70, "&AB"),
    (0.68, "EKPSX"),
    (0.66, "VY"),
    (0.64, "+<=>Z^~"),
    (0.62, "FT"),
    (0.60, "#"),
    (0.58, "0235689?bdhnopqu"),
    (0.56, "47Jaeg"),
    (0.54, "1L"),
    (0.52, "$cksvxy"),
    (0.50, "_z"),
    (0.42, "*"),
    (0.38, '"'),
    (0.36, "(){}"),
    (0.34, "-r"),
    (0.30, "/:;[]t" + chr(92)),
    (0.28, "!,.If"),
    (0.26, "|"),
    (0.24, "ijl"),
    (0.22, " '"),
    (0.20, "`"),
)

#: The same characters at `HEAVY`. Fewer distinct widths, because the
#: heaviest instance of this face pushes most letters onto one of a handful
#: of advances.
_HEAVY_EM: Final = (
    (1.02, "@"),
    (1.00, "%Wm"),
    (0.98, "M"),
    (0.96, "w"),
    (0.90, "&"),
    (0.84, "GHKNOQU"),
    (0.78, "ABCDRVXY"),
    (0.74, "EPSTZ"),
    (0.68, "0123456789FJLabcdeghknopqux"),
    (0.66, "#+<=>^~"),
    (0.62, "$?svy"),
    (0.56, "_z"),
    (0.50, '"'),
    (0.46, "rt"),
    (0.42, "*"),
    (0.40, "()[]f{}"),
    (0.38, "I"),
    (0.34, "!,-.:;"),
    (0.32, "/ijl" + chr(92)),
    (0.30, "`|"),
    (0.28, "'"),
    (0.18, " "),
)


def _table(measured: tuple[tuple[float, str], ...]) -> dict[str, float]:
    return {character: em for em, characters in measured for character in characters}


_TABLES: Final = {LIGHT: _table(_LIGHT_EM), HEAVY: _table(_HEAVY_EM)}

#: What a character no table names is charged. The widest one they do, so
#: an unmeasured glyph is never charged less than a measured one -- a line
#: of them is set smaller than it needed to be, which is the direction that
#: keeps words out of the drawing.
WIDEST_ADVANCE_EM: Final = max(
    em for table in _TABLES.values() for em in table.values()
)


def _base(character: str) -> str:
    """A character with its combining marks dropped.

    An accented letter is charged as the letter it is built on, which is
    exact for this face: an acute over a capital A does not make the A
    wider.
    """
    stripped = "".join(
        part
        for part in unicodedata.normalize("NFD", character)
        if not unicodedata.combining(part)
    )
    return stripped if len(stripped) == 1 else character


def advance_em(character: str, *, weight: int) -> float:
    """One character's advance at one weight, as a fraction of the size.

    At `LIGHT` or `HEAVY` that is the measurement. Between them it is
    whichever of the two is wider -- which is not always the heavier one: a
    space is wider at 400 than at 900 in this face, so charging every
    in-between weight the heavy table alone would undercharge every space
    on the page.
    """
    tables: tuple[dict[str, float], ...]
    if weight <= LIGHT:
        tables = (_TABLES[LIGHT],)
    elif weight >= HEAVY:
        tables = (_TABLES[HEAVY],)
    else:
        tables = (_TABLES[LIGHT], _TABLES[HEAVY])
    base = _base(character)
    found = [table[base] for table in tables if base in table]
    return max(found) if found else WIDEST_ADVANCE_EM


def width(text: str, *, size: float, weight: int, letter_spacing: float = 0.0) -> float:
    """How wide `text` will be, set at `size` and `weight` in this face.

    In the same units the size is given in. `letter_spacing` is the SVG
    attribute of that name, in those units, added once per character
    exactly as a renderer adds it -- the last one included, which is what
    SVG's own `letter-spacing` does.
    """
    if size <= 0:
        raise ValueError("a font size is a positive length")
    return sum(
        advance_em(character, weight=weight) * size + letter_spacing
        for character in text
    )
