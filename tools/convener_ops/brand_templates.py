"""The two templates a collaborator downloads, derived rather than drawn.

`docs/assets/announcement-template.svg` and `flyer-template.svg` are the
files `docs/toolkit/visual-kit.md` links to: a volunteer downloads one,
opens it in Inkscape or a text editor, fills in the event and exports an
image. They were drawn by hand, and they had drifted -- measured, not
suspected. They carried
the palette D-16 discarded on accessibility grounds (`#3D2D7C` for
`#012765`, `#3FB1C2` for `#fecac1`, `#F4F1E6` for `#f4f0f1`) plus four
greys from no charter at all, and `generate_brand_css.py --check` could
not see any of it: it knew only the two stylesheets it generates.

**That mattered more than an internal drift, because these are the files
that travel outward.** The palette leaving the project under an
organisation's name was the wrong one. Three of its pairings were not
merely off-charter but unreadable, measured with this repository's own
arithmetic:

- `#3D2D7C` on `#3FB1C2` -- the headline on the page's ground -- **4.44**,
  which is the exact number D-16 was decided over, still shipping;
- `#3FB1C2` on `#F4F1E6` -- the wordmark's second colour on the cream band
  -- **2.24**;
- `#3FB1C2` on `#3FB1C2` -- the forum's address in the "what to expect"
  block, set in the page's own ground colour -- **1.00**. Invisible. It had
  been invisible in every downloaded poster since the file was drawn.

Regenerating them by hand would have fixed those three numbers and left
nothing to stop a fourth. So they are generated here instead, from
`data/brand.json` (or the product's own charter, when an instance has not
written one) and `config/instance.json`, and `--check` holds them exactly
as it holds the two stylesheets.

Which mark these leave the repository wearing
-----------------------------------------------
Both files draw the wordmark and the ribbon, and both take their
colour and their stroke weight from `motif`. These are the files that
travel outward, so they are exactly where another organisation's mark
would leak -- which is why, until 2026-08-26, `motif` had no product
default and this module could not render at all without one. It has one
now, and the leak is closed at a better place: a duplicate that has
configured nothing renders these two files in the *product's* mark, and
`published.unconfigured` says on every public page that the instance is
not configured yet. A build that refuses cannot say that, because it
never gets as far as a page. What still stops here is a `motif` somebody
wrote and left incomplete (`brand.py`).

Every pairing is checked, not only the ones the charter names
--------------------------------------------------------------
`data/brand.json`'s `contrast` table records the pairings the *composition*
creates. These two files create a few more of their own -- a caption on a
photographic frame, a label beside a QR slot -- and it was precisely an
uninspected pairing that let the 1.00 above survive. So `_LEGIBILITY`
below names every ink-on-ground this module actually draws, and rendering
refuses if one of them falls under AA. It is a claim a reviewer has to
keep true against the markup, which is why each entry says where it is;
what it buys is that the check holds for *any* palette, including one a
duplicate writes tomorrow.

The ribbon these files draw is the ribbon
-------------------------------------------
Both files drew three bare circles and arcs in place of the motif until
2026-08-28, which is what `data/brand.json::motif._ribbon` had always
said they were: a stroke ending in a closed ring reads as a line with a
circle stuck on it, not as one continuous ribbon running off the edges.
`ribbon.py` had the real curve all along -- traced against the designer's
own poster, the same 1200-unit reference these two layouts come from --
and drew it for the generated posters (`visual.py`) and nowhere else. It
draws it here now, at the same colour and the same weight the charter
already gave the loops, so nothing about the stroke itself changed.

What that cost was a re-layout, which is why it had been deferred and is
the whole of the work: the ribbon owns ground on both sides that these
two compositions were using. Every block moved below is moved because the
stroke passes through where it stood, and the distance each moved is the
stroke's own reach over that block's rows -- read off `ribbon.ribbon_path`
at the size the file is drawn, not guessed. The reference poster places
its own type the same way: its "what to expect" column starts at 312 of
1200 and its registration slot ends at 215, both just clear of the stroke
beside them, neither clear of the ribbon's deepest reach anywhere else on
the page.

Two places keep the composition rather than the reference
-----------------------------------------------------------
The series' name is set smaller than it was (50 against 66 on the square),
because the right curl crosses the rows it occupies. That is a return
rather than a loss: at 66 it measured 1064 units wide on a 1200 canvas,
where the reference's own headline measures 868.

The wordmark's second word takes `turquoise_text` and not the field's own
turquoise, which is what the reference sets it in. `colour._roles` in the
charter forbids that colour as text on white or cream by name, and on the
cream band the reference's pairing measures 1.42 -- against the 4.5 WCAG
AA asks. `turquoise_text` is the charter's own readable variant of it,
5.41 on the same band, and it carries the two-tone split the reference
draws without creating the one pairing the charter refuses. Restoring the
field's turquoise there would be a change to the charter's own rules, and
that is not a decision a generator gets to take on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from . import brand, formats, published, ribbon

__all__ = [
    "ANNOUNCEMENT_PATH",
    "FLYER_PATH",
    "render_announcement_template",
    "render_flyer_template",
]

#: Where each generated template lives, relative to a repository root.
#: `docs/toolkit/visual-kit.md` links to both by these paths, and
#: `app/src/content/registry.ts::PUBLIC_ASSETS` publishes them.
ANNOUNCEMENT_PATH: Final = Path("docs") / "assets" / "announcement-template.svg"
FLYER_PATH: Final = Path("docs") / "assets" / "flyer-template.svg"

#: The flyer's user-unit grid: ten units per millimetre of A4, so a
#: coordinate reads as a tenth of a millimetre and the physical size comes
#: from `formats.PRINT_PAPER_MM` rather than from 210 and 297 typed again.
_UNITS_PER_MM: Final = 10

#: The placeholders both files carry into the volunteer's editor, spelled
#: exactly as `app/src/content/render.ts::substitute` resolves them -- an
#: invented one would send somebody looking for a field that does not
#: exist (`app/tests/visual-kit.test.tsx` holds this).
_SPEAKER: Final = {
    f"speaker_{field}": f"{{{{speaker.{field}}}}}"
    for field in ("title", "date", "time", "name", "affiliation", "edition_code")
}

#: The font stack both files set on their root element. The faces the
#: charter names, then the fallbacks any machine has -- an SVG that
#: reaches out to a font server is the shared-account dependency again,
#: one HTTP request further away.
_FALLBACK: Final = ("'Segoe UI'", "Arial", "Helvetica", "sans-serif")


@dataclass(frozen=True)
class _Pairing:
    """One ink, the ground it sits on, and where in the markup that is."""

    where: str
    ink: str
    ground: str


#: Every ink-on-ground the two files below actually draw. Text only:
#: `rule_strong` outlines the QR slot and `logo_dots` fills the wordmark's
#: squares, and neither is text -- WCAG exempts a logotype from the
#: non-text contrast rule outright, and a dashed placeholder border is
#: decoration around content that replaces it.
_LEGIBILITY: Final = (
    _Pairing("the wordmark's address, in the top cream band", "purple", "cream"),
    _Pairing(
        "the wordmark's second word, in the top cream band",
        "turquoise_text",
        "cream",
    ),
    _Pairing("the series' name, on the field", "purple", "turquoise"),
    _Pairing("the invitation lines, on the field", "black", "turquoise"),
    _Pairing("the talk's title, in the cream band", "purple", "cream"),
    _Pairing("the date line, on the field", "purple", "turquoise"),
    _Pairing(
        "the 'what to expect' heading and rows, on the field", "black", "turquoise"
    ),
    _Pairing("the before/during/after labels, on the field", "purple", "turquoise"),
    _Pairing(
        "the caption inside the photographic frame", "ink_muted", "turquoise_tint"
    ),
    _Pairing("the speaker's name and affiliation, on the frame", "ink", "white"),
    _Pairing("the label in the QR slot", "ink_muted", "white"),
    _Pairing("the flyer's edition code, in the foot band", "purple", "cream"),
    _Pairing("the flyer's closing line, in the foot band", "black", "cream"),
)


def _num(value: float) -> str:
    """A coordinate, without a trailing `.0` on a whole number."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text else "0"


# --------------------------------------------------------------------------
# The mark, and the wordmark beside it
# --------------------------------------------------------------------------

#: The mark, drawn in a box of its own hundred units so that one set of
#: numbers serves both files at whatever size each sets it. Every
#: coordinate is measured off
#: `announcement-template_initial.png` (1200x1200), where the mark occupies
#: x 165..265 and y 57..157 -- so a hundred units there is a hundred pixels,
#: and the figures below can be read straight back off the reference.
#:
#: **Five squares and not four, on a grid and not scattered.** They sit at
#: the corners and the centre of a three-by-three grid of 34-unit cells,
#: each square 32 units with the two-unit gap that grid leaves: x 0, 34, 68
#: and y 0, 34, 68 in this box, filled at (0,0), (68,0), (34,34), (0,68) and
#: (68,68). What stood here before was four squares of 26 at four offsets
#: that fell on no grid at all, which is most of why the device did not read
#: as the reference's.
#:
#: **The two markers are filled drops with a hole, not open rings.** Each is
#: 18 wide and 22 tall with a 5-unit hole on its own axis, and they point
#: opposite ways -- the left one down the way its tail leaves, the right one
#: up the way the connector arrives. Traced row by row off the same
#: reference: the left one is widest 6 rows below its point and tapers over
#: the 16 below that, the right one is the same shape turned over.
#:
#: **The rule under the wordmark is this drawing's own tail**, which is why
#: `_MARK_TAIL_END` is a coordinate rather than a comment: the stroke leaves
#: the left marker, turns east and becomes the rule that runs under the
#: address. Each file continues it as a rectangle from exactly that point,
#: because how far east it runs is a property of that page's own width and
#: not of the mark.
_MARK_BOX: Final = 100.0

#: Where the tail lands, in the mark's own hundred-unit box: the rule each
#: file draws begins here, at this height, and runs east.
_MARK_TAIL_END: Final = (25.0, 83.0)

#: The mark's own line weight, in the same box. Thin on purpose -- the
#: reference draws the connector and the rule at 3 to 4 pixels where the
#: mark is 100 across -- and it scales with the group, so the flyer's
#: larger mark carries a proportionally heavier line without a second
#: number.
_MARK_STROKE: Final = 3.5

_MARK_SQUARES: Final = ((0, 0), (68, 0), (34, 34), (0, 68), (68, 68))
_MARK_SQUARE: Final = 32

#: The left marker: a drop pointing down, and the 5-unit hole through it.
_MARK_PIN_LEFT: Final = (
    "M 15.5 39 C 21 39.5 24.5 42 24.5 45.5 C 24.5 52 20.5 57.5 15.5 61 "
    "C 10.5 57.5 6.5 52 6.5 45.5 C 6.5 42 10 39.5 15.5 39 Z "
    "M 18 49 A 2.5 2.5 0 1 1 13 49 A 2.5 2.5 0 1 1 18 49 Z"
)

#: The right marker: the same drop turned over, pointing up.
_MARK_PIN_RIGHT: Final = (
    "M 83.5 60 C 89 59.5 92.5 57 92.5 53.5 C 92.5 47 88.5 41 83.5 38 "
    "C 78.5 41 74.5 47 74.5 53.5 C 74.5 57 78 59.5 83.5 60 Z "
    "M 86 49 A 2.5 2.5 0 1 1 81 49 A 2.5 2.5 0 1 1 86 49 Z"
)

#: The line joining the two markers, and the tail leaving the left one for
#: the rule -- one stroked path each, drawn under the filled markers.
_MARK_CONNECTOR: Final = "M 48 15 L 73 15 C 79 15 83.5 20 83.5 29 L 83.5 38"
_MARK_TAIL: Final = "M 15.5 61 L 15.5 73 C 15.5 79 19 83 25 83"


def _mark(x: float, y: float, size: float, *, dots: str, ink: str) -> str:
    """The mark, set with its own box's top-left corner at `x`, `y`.

    `size` is how many of the page's units the hundred-unit box occupies,
    so both files ask for the mark at the size their own composition wants
    and neither restates its geometry.
    """
    scale = size / _MARK_BOX
    # No `scale(1)` on a mark drawn at its measured size: an identity
    # transform in a file somebody opens to edit is a thing to work out
    # the meaning of before deciding it means nothing.
    resize = "" if scale == 1 else f" scale({_num(scale)})"
    squares = "\n".join(
        f'      <rect x="{sx}" y="{sy}" width="{_MARK_SQUARE}" '
        f'height="{_MARK_SQUARE}" fill="{dots}"/>'
        for sx, sy in _MARK_SQUARES
    )
    pins = "\n".join(
        f'        <path d="{pin}"/>' for pin in (_MARK_PIN_LEFT, _MARK_PIN_RIGHT)
    )
    return (
        f'    <g transform="translate({_num(x)} {_num(y)}){resize}">\n'
        f"{squares}\n"
        f'      <g fill="none" stroke="{ink}" stroke-width="{_MARK_STROKE}"\n'
        f'         stroke-linecap="round">\n'
        f'        <path d="{_MARK_CONNECTOR}"/>\n'
        f'        <path d="{_MARK_TAIL}"/>\n'
        f"      </g>\n"
        f'      <g fill="{ink}" fill-rule="evenodd">\n'
        f"{pins}\n"
        f"      </g>\n"
        f"    </g>"
    )


def _ribbon(width: float, height: float) -> str:
    """The charter's ribbon for a canvas, indented to sit in the markup.

    `ribbon.ribbon_path` returns one command a line, which is how a
    hundred cubics stay readable; a `d` attribute pasted in flush left
    inside an indented document is not, and these two files are opened in
    a text editor on purpose.
    """
    joiner = "\n" + " " * 15
    return joiner.join(ribbon.ribbon_path(width, height).splitlines())


def _mark_tail_x(x: float, size: float) -> float:
    """Where the mark's tail lands, so a file's rule can start there."""
    return x + _MARK_TAIL_END[0] * size / _MARK_BOX


def _mark_tail_y(y: float, size: float) -> float:
    """The height the mark's tail lands at, which is the rule's own."""
    return y + _MARK_TAIL_END[1] * size / _MARK_BOX


#: Which of the organisation's own words takes the second tone. The
#: reference sets the address in two colours, and the word that changes is
#: the second of the three its own name runs together: the first and the
#: third in the dominant ink, with the prefix and the suffix the address
#: carries, and the middle one in the accent. Alternating from the first
#: word is the rule that produces that, and it produces something sensible
#: for a name of any number of words rather than only for one of three.
_WORDMARK_CAMEL: Final = re.compile(r"[A-Z][^A-Z]*|[^A-Z]+")


def _wordmark_runs(identity: published.Identity) -> tuple[tuple[str, bool], ...]:
    """The address as the organisation spells its own name, in its runs.

    Each pair is a run of the address and whether it takes the accent
    tone. The address itself is `forum_host` and is never retyped; what
    this adds is the *casing*, which the host has none of -- a domain name
    is lower case by definition, and the reference's wordmark is not: it
    runs the organisation's own words together with a capital on each,
    exactly as `identity.organisation` spells the same name. So the
    organisation is found inside the host, case-insensitively, and its own
    spelling is put back in place of the host's.

    A duplicate whose organisation does not appear in its forum's host --
    a name and an address that simply differ -- gets the host unchanged,
    in one tone. That is the honest answer there: nothing in the
    declaration says how such a name should be broken up, and inventing a
    split would put a stranger's wordmark in two colours at a boundary
    nobody chose.
    """
    host = identity.forum_host
    organisation = identity.organisation
    start = host.lower().find(organisation.lower())
    if start < 0:
        return ((host, False),)
    words = [word for word in _WORDMARK_CAMEL.findall(organisation) if word]
    if len(words) < 2:
        return ((host, False),)
    runs = [(word, index % 2 == 1) for index, word in enumerate(words)]
    runs[0] = (host[:start] + runs[0][0], runs[0][1])
    tail = host[start + len(organisation) :]
    runs[-1] = (runs[-1][0] + tail, runs[-1][1])
    return tuple(runs)


def _wordmark(runs: tuple[tuple[str, bool], ...], *, ink: str, accent: str) -> str:
    """The wordmark's runs as `tspan`s, ready to sit inside one `text`."""
    return "".join(
        f'<tspan fill="{accent if is_accent else ink}">{text}</tspan>'
        for text, is_accent in runs
    )


def _font_family(charter: dict[str, Any]) -> str:
    """The `font-family` attribute, the charter's display face first."""
    return ", ".join((str(charter["typography"]["display"]), *_FALLBACK))


def _legibility_problems(colours: dict[str, str], *, named: str) -> list[str]:
    """Every pairing these templates draw that falls below AA."""
    problems: list[str] = []
    for pairing in _LEGIBILITY:
        ratio = round(
            brand.contrast_ratio(colours[pairing.ink], colours[pairing.ground]), 2
        )
        if ratio < brand.AA_NORMAL_TEXT:
            problems.append(
                f"{named}: {pairing.where} sets {pairing.ink} on {pairing.ground}, "
                f"which measures {ratio} -- below the {brand.AA_NORMAL_TEXT} "
                "WCAG AA needs for normal text"
            )
    return problems


def _values(root: Path) -> dict[str, str]:
    """Everything both templates substitute: colours, motif, identity.

    Loads the charter once and refuses here rather than in each renderer,
    so that a half-written motif is one message however many files are
    being written.
    """
    charter = brand.load(root)
    colours = brand.colours(charter)
    problems = _legibility_problems(colours, named=brand.source(root).as_posix())
    if problems:
        raise ValueError("; ".join(problems))
    identity = published.load_identity(root)
    motif = brand.motif(root)
    return {
        **_SPEAKER,
        **colours,
        "wordmark": _wordmark(
            _wordmark_runs(identity),
            ink=colours["purple"],
            accent=colours["turquoise_text"],
        ),
        "ribbon_stroke": str(motif["ribbon_stroke"]),
        "logo_dots": str(motif["logo_dots"]),
        "font_family": _font_family(charter),
        "series_title": f"{identity.short_name} {identity.series}",
        "series_caps": identity.series.upper(),
        "tagline": identity.tagline,
        "forum_host": identity.forum_host,
        "ribbon_ratio": str(motif["ribbon_width_ratio"]),
    }


#: The note both files carry at the top. There is no double hyphen
#: anywhere in it, and that is not a style choice: XML forbids the
#: sequence inside a comment, so this project's usual `--` for an em dash,
#: and even the name of the `--check` flag, make the whole document
#: unparseable. Found by rendering one in a browser, which refused it
#: outright rather than drawing anything; `test_brand.py` parses both
#: files as XML now, so the next one is a failing test instead.
_GENERATED_NOTE: Final = """\
  <!-- Generated, not drawn: scripts/generate_brand_css.py writes this file
  from data/brand.json (the colours and the motif) and config/instance.json
  (the names). Change one of those, run that command, and commit what it
  writes; an edit made here is overwritten, and the check fails until it
  is. Once you have downloaded a copy it is yours, of course: edit that as
  freely as you like. -->"""


_ANNOUNCEMENT: Final = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"
     viewBox="0 0 {w} {h}" font-family="{font_family}">
  <title>{series_title} — announcement image</title>
  <desc>Square announcement image, {w}x{h}, for the forum and LinkedIn. Edit
  the text in any SVG editor (Inkscape, Figma, Illustrator, a browser plus a
  text editor). Everything inside id="variable" changes for each event;
  everything inside id="fixed" is the series identity and stays put.</desc>

{generated_note}
  <g id="fixed">
    <rect width="{w}" height="{h}" fill="{turquoise}"/>
    <rect y="0" width="{w}" height="168" fill="{cream}"/>
    <rect y="400" width="{w}" height="146" fill="{cream}"/>

    <!-- The ribbon: one continuous stroke, running off three edges and
         turning back on itself, in the charter's own motif colour and at
         its own weight so neither can drift from it. It carries no text
         and every word on this page is placed clear of it. Move or delete
         it freely; if you move a word instead, keep it out of the stroke,
         because a heavy line behind dark type is unreadable type. -->
    <g fill="none" stroke="{ribbon_stroke}" stroke-width="{stroke_weight}"
       stroke-linecap="round" stroke-linejoin="round">
      <path d="{ribbon}"/>
    </g>

    <!-- Wordmark. The mark is five squares, two markers and the line
         joining them, drawn rather than embedded: an SVG that references
         an external logo file is an SVG that travels broken. The rule
         under the address is the same line, continuing east. -->
{mark}
    <text x="282" y="112" font-size="50"
          font-weight="500">{wordmark}</text>
    <rect x="{rule_x}" y="{rule_y}" width="{rule_w}" height="{rule_h}"
          fill="{purple}"/>

    <text x="600" y="272" text-anchor="middle" font-size="50"
          font-weight="900" letter-spacing="1"
          fill="{purple}">{series_caps}</text>
    <text x="600" y="330" text-anchor="middle" font-size="31"
          fill="{black}">Join the discussion before and after the talk at</text>
    <text x="600" y="372" text-anchor="middle" font-size="31"
          font-weight="700" fill="{black}">{forum_host}</text>
  </g>

  <g id="variable">
    <!-- TALK TITLE. Two lines, split by hand — SVG does not wrap text. A
         very long title: drop the font-size to 40 and use three lines. -->
    <text text-anchor="middle" font-size="44" font-weight="700"
          fill="{purple}">
      <tspan x="600" y="458">{speaker_title}</tspan>
      <tspan x="600" y="512"></tspan>
    </text>

    <!-- DATE AND TIME. Written out the way it is said aloud; the app holds
         {speaker_date} as 2026-11-12 and {speaker_time} as 12:30 (CET). -->
    <text x="600" y="600" text-anchor="middle" font-size="40"
          font-weight="700"
          fill="{purple}">{speaker_date} at {speaker_time} (CET)</text>

    <!-- SPEAKER PHOTO. Replace this frame with the photo: in Inkscape,
         File &gt; Import, then send the image behind this white frame. Keep
         the tilt. No photo yet? Leave the frame; it reads as unfinished. -->
    <g transform="rotate(4 900 900)">
      <rect x="700" y="690" width="420" height="470" fill="{white}"/>
      <rect x="722" y="712" width="376" height="376" fill="{turquoise_tint}"/>
      <text x="910" y="912" text-anchor="middle" font-size="26"
            fill="{ink_muted}">speaker photo</text>
      <text x="1098" y="1128" text-anchor="end" font-size="30"
            font-weight="800" fill="{ink}">{speaker_name}</text>
      <text x="1098" y="1152" text-anchor="end" font-size="19"
            fill="{ink}">{speaker_affiliation}</text>
    </g>
  </g>

  <g id="fixed-what-to-expect">
    <text x="240" y="730" font-size="34" font-weight="800"
          fill="{black}">WHAT TO EXPECT?</text>
    <text font-size="27" fill="{black}">
      <tspan x="320" y="796" font-weight="800"
             fill="{purple}">BEFORE: </tspan><tspan>Ask your</tspan>
      <tspan x="320" y="832">questions to the speaker</tspan>
      <tspan x="320" y="868">at {forum_host}</tspan>
      <tspan x="320" y="944" font-weight="800"
             fill="{purple}">D-DAY: </tspan><tspan>Presentation</tspan>
      <tspan x="320" y="980">followed by a discussion</tspan>
      <tspan x="320" y="1016">with the audience</tspan>
      <tspan x="320" y="1092" font-weight="800"
             fill="{purple}">AFTER: </tspan><tspan>Continue the</tspan>
      <tspan x="320" y="1128">discussion and connect</tspan>
      <tspan x="320" y="1164">with peers</tspan>
    </text>

    <!-- REGISTRATION QR. Generate it from the registration link with any
         offline generator, or in the app; then drop it over this square.
         It sits where the ribbon's tail leaves it room, which is why the
         slot is 180 and not the width of the margin beside it. -->
    <text x="24" y="898" font-size="32" font-weight="800"
          fill="{black}">REGISTER</text>
    <text x="24" y="936" font-size="32" font-weight="800"
          fill="{black}">HERE</text>
    <rect x="24" y="960" width="180" height="180" fill="{white}"/>
    <rect x="42" y="978" width="144" height="144" fill="none"
          stroke="{rule_strong}" stroke-width="3" stroke-dasharray="10 8"/>
    <text x="114" y="1058" text-anchor="middle" font-size="22"
          fill="{ink_muted}">QR code</text>
  </g>
</svg>
"""


_FLYER: Final = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{paper_w}mm" height="{paper_h}mm"
     viewBox="0 0 {w} {h}" font-family="{font_family}">
  <title>{series_title} — event flyer</title>
  <desc>A4 portrait flyer ({paper_w}x{paper_h} mm) for printing and for
  attaching to an email. Edit the text in any SVG editor (Inkscape, Figma,
  Illustrator, a browser plus a text editor), then export to PDF or PNG at
  300 dpi. Everything inside id="variable" changes for each event;
  everything inside id="fixed" is the series identity and stays put.</desc>

{generated_note}
  <g id="fixed">
    <rect width="{w}" height="{h}" fill="{turquoise}"/>
    <rect y="0" width="{w}" height="290" fill="{cream}"/>
    <rect y="700" width="{w}" height="470" fill="{cream}"/>
    <rect y="2760" width="{w}" height="210" fill="{cream}"/>

    <!-- The ribbon: one continuous stroke, running off the edges and
         turning back on itself, in the charter's own motif colour and at
         its own weight. It carries no text and every word on this page is
         placed clear of it. Move or delete it freely; if you move a word
         instead, keep it out of the stroke. -->
    <g fill="none" stroke="{ribbon_stroke}" stroke-width="{stroke_weight}"
       stroke-linecap="round" stroke-linejoin="round">
      <path d="{ribbon}"/>
    </g>

    <!-- Wordmark: five squares, two markers and the line joining them,
         drawn rather than embedded. The rule is that line, continuing. -->
{mark}
    <text x="485" y="188" font-size="88"
          font-weight="500">{wordmark}</text>
    <rect x="{rule_x}" y="{rule_y}" width="{rule_w}" height="{rule_h}"
          fill="{purple}"/>

    <text x="1050" y="430" text-anchor="middle" font-size="86"
          font-weight="900" letter-spacing="2"
          fill="{purple}">{series_caps}</text>
    <text x="1050" y="530" text-anchor="middle" font-size="50"
          fill="{black}">{tagline}</text>
    <text x="1050" y="600" text-anchor="middle" font-size="50"
          font-weight="700"
          fill="{black}">Join the discussion at {forum_host}</text>
  </g>

  <g id="variable">
    <!-- TALK TITLE. Up to three lines, split by hand — SVG does not wrap
         text. A short title: use one line and raise the font-size to 96. -->
    <text text-anchor="middle" font-size="80" font-weight="700"
          fill="{purple}">
      <tspan x="1050" y="840">{speaker_title}</tspan>
      <tspan x="1050" y="940"></tspan>
      <tspan x="1050" y="1040"></tspan>
    </text>

    <!-- DATE AND TIME. The app holds {speaker_date} as 2026-11-12 and
         {speaker_time} as 12:30; write them out the way they are said. -->
    <text x="1050" y="1290" text-anchor="middle" font-size="72"
          font-weight="700"
          fill="{purple}">{speaker_date} at {speaker_time} (CET)</text>

    <!-- SPEAKER PHOTO. Replace this frame with the photo: in Inkscape,
         File &gt; Import, then send the image behind this white frame. Keep
         the tilt. No photo yet? Leave the frame; it reads as unfinished. -->
    <g transform="rotate(4 1520 1900)">
      <rect x="1250" y="1440" width="700" height="810" fill="{white}"/>
      <rect x="1288" y="1478" width="624" height="624"
            fill="{turquoise_tint}"/>
      <text x="1600" y="1800" text-anchor="middle" font-size="44"
            fill="{ink_muted}">speaker photo</text>
      <text x="1912" y="2180" text-anchor="end" font-size="56"
            font-weight="800" fill="{ink}">{speaker_name}</text>
      <text x="1912" y="2226" text-anchor="end" font-size="34"
            fill="{ink}">{speaker_affiliation}</text>
    </g>

    <!-- EDITION CODE. The series number this event carries in the data. -->
    <text x="1050" y="2812" text-anchor="middle" font-size="40"
          font-weight="700" fill="{purple}">{speaker_edition_code}</text>
  </g>

  <g id="fixed-what-to-expect">
    <text x="480" y="1470" font-size="62" font-weight="800"
          fill="{black}">WHAT TO EXPECT?</text>
    <text font-size="50" fill="{black}">
      <tspan x="560" y="1590" font-weight="800"
             fill="{purple}">BEFORE: </tspan><tspan>Ask your</tspan>
      <tspan x="560" y="1652">questions to the speaker</tspan>
      <tspan x="560" y="1714">at {forum_host}</tspan>
      <tspan x="560" y="1846" font-weight="800"
             fill="{purple}">D-DAY: </tspan><tspan>Presentation</tspan>
      <tspan x="560" y="1908">followed by a discussion</tspan>
      <tspan x="560" y="1970">with the audience</tspan>
      <tspan x="560" y="2102" font-weight="800"
             fill="{purple}">AFTER: </tspan><tspan>Continue the</tspan>
      <tspan x="560" y="2164">discussion and connect</tspan>
      <tspan x="560" y="2226">with peers</tspan>
    </text>

    <!-- REGISTRATION QR. Generate it from the registration link with any
         offline generator, then drop it over this square. It sits east of
         the ribbon's tail, which crosses the foot of this page. -->
    <text x="600" y="2360" font-size="56" font-weight="800"
          fill="{black}">REGISTER HERE</text>
    <rect x="600" y="2400" width="360" height="340" fill="{white}"/>
    <rect x="630" y="2430" width="300" height="280" fill="none"
          stroke="{rule_strong}" stroke-width="5" stroke-dasharray="18 14"/>
    <text x="780" y="2595" text-anchor="middle" font-size="40"
          fill="{ink_muted}">QR code</text>
    <text x="1180" y="2872" text-anchor="middle" font-size="46"
          fill="{black}">Free · online · everyone welcome</text>
    <text x="1180" y="2928" text-anchor="middle" font-size="46"
          fill="{black}">Register at {forum_host}</text>
  </g>
</svg>
"""


def _stroke_weight(width: float, height: float, ratio: float) -> str:
    """The ribbon's stroke weight, from the charter's own ratio.

    `ribbon.ribbon_stroke_width` and not a literal: the weight the loops
    that stood in for the ribbon were drawn at (17 units on a 1200 square,
    0.014 of the shorter side) was nobody's measurement, and
    `motif._ribbon_width_ratio` records one taken against the reference
    poster.
    """
    return _num(ribbon.ribbon_stroke_width(width, height, ratio=ratio))


@dataclass(frozen=True)
class _Wordmark:
    """Where one file sets the mark, and how far east its rule runs.

    `x`, `y` and `size` place the mark's own hundred-unit box; `rule_end`
    is the only number here a page decides rather than the mark, and it is
    where the right curl comes down: the rule stops short of the stroke
    instead of running into it, which is the one thing the reference does
    that this does not (its own rule and its own curl touch).
    """

    x: float
    y: float
    size: float
    rule_end: float
    rule_weight: float


#: The square sets the mark at the size the reference poster sets it at:
#: a hundred units of twelve hundred, its top-left corner at 165, 57. The
#: flyer sets it at the same fraction of its own width, which is what keeps
#: the two reading as one series at two sizes, and further east than the
#: square does because the ribbon runs deeper into an A4 page's own margin.
_ANNOUNCEMENT_WORDMARK: Final = _Wordmark(165.0, 57.0, 100.0, 964.0, 4.0)
_FLYER_WORDMARK: Final = _Wordmark(280.0, 92.0, 175.0, 1690.0, 7.0)


def _wordmark_values(mark: _Wordmark, values: dict[str, str]) -> dict[str, str]:
    """The mark, and the rule that continues its own tail east."""
    tail_x = _mark_tail_x(mark.x, mark.size)
    tail_y = _mark_tail_y(mark.y, mark.size)
    return {
        "mark": _mark(
            mark.x,
            mark.y,
            mark.size,
            dots=values["logo_dots"],
            ink=values["ribbon_stroke"],
        ),
        "rule_x": _num(tail_x),
        "rule_y": _num(tail_y - mark.rule_weight / 2),
        "rule_w": _num(mark.rule_end - tail_x),
        "rule_h": _num(mark.rule_weight),
    }


def render_announcement_template(root: Path) -> str:
    """`docs/assets/announcement-template.svg` in full."""
    values = _values(root)
    width, height = formats.SQUARE.width, formats.SQUARE.height
    return _ANNOUNCEMENT.format(
        **values,
        **_wordmark_values(_ANNOUNCEMENT_WORDMARK, values),
        w=_num(width),
        h=_num(height),
        generated_note=_GENERATED_NOTE,
        stroke_weight=_stroke_weight(width, height, float(values["ribbon_ratio"])),
        ribbon=_ribbon(width, height),
    )


def render_flyer_template(root: Path) -> str:
    """`docs/assets/flyer-template.svg` in full."""
    values = _values(root)
    paper_w, paper_h = formats.PRINT_PAPER_MM
    width, height = paper_w * _UNITS_PER_MM, paper_h * _UNITS_PER_MM
    return _FLYER.format(
        **values,
        **_wordmark_values(_FLYER_WORDMARK, values),
        w=_num(width),
        h=_num(height),
        paper_w=_num(paper_w),
        paper_h=_num(paper_h),
        generated_note=_GENERATED_NOTE,
        stroke_weight=_stroke_weight(width, height, float(values["ribbon_ratio"])),
        ribbon=_ribbon(width, height),
    )
