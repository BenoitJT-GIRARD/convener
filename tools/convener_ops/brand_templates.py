"""The three files a collaborator downloads, derived rather than drawn.

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
`instance/data/brand.json` (or the product's own charter, when an instance has not
written one) and `instance/config.json`, and `--check` holds them exactly
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
`instance/data/brand.json`'s `contrast` table records the pairings the *composition*
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
2026-08-28, which is what `instance/data/brand.json::motif._ribbon` had always
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

The third file, and why it is vector where it used to be a bitmap
-------------------------------------------------------------------
`docs/assets/video-call-background.svg` is what a host puts behind them
during a session. It was a hand-drawn PNG until 2026-08-28, and it was the
last hand-made file in `docs/assets/` -- which made it the one thing
`convener_ops.derivation_guard` could not read: that guard sweeps every
blob of every ref for the values this instance declares about itself, and
a wordmark inside an image is invisible to it. The file it could not read
carried this organisation's name, an address, a strapline written down
nowhere else (`THE PLACE TO DISCUSS ANIMAL BEHAVIOUR`, against
`identity.strapline`'s own `Read together`) and a QR code
pointing at a single 2024 forum thread for one past edition -- none of it
visible to any check, all of it irreversible once pushed. It is derived
here now, from the same two files the other two templates come from, and
every string on it is a declared string.

**It is an SVG, and it is not accompanied by a rendered PNG**, which is
the part that took a decision rather than a translation. A video-call
application takes a raster, so a background *is* eventually a PNG -- but a
rasterisation is not reproducible: font hinting and anti-aliasing differ
between machines, and a committed PNG held byte-for-byte would be a check
that goes red on somebody else's laptop for a reason that is not a defect.
The alternatives were weighed against what this repository already does:

- **Commit the PNG and hold it to a tolerance**, the way
  `tools/visuals/render-and-compare.mjs` holds `tools/visuals/references/*.png` (24
  levels per channel, 0.1% of pixels). That comparison is honest for what
  it is for, and it needs a browser -- so it could never run inside
  `tools/scripts/generate_brand_css.py --check`, which is pure Python and is
  what `convener_ops.derivation` re-runs when it builds a duplicate's
  repository. A duplicate would inherit *this* instance's background, in a
  file no guard can read. That is the defect, not a smaller version of it.
- **Commit the PNG and hold it byte-for-byte**, the way
  `visuals-production.yml` holds `site/src/banners/`. Same objection, plus
  a check that fails for the wrong reason -- which this project treats as
  worse than no check.
- **Commit the SVG alone.** Taken. Every string, every colour and the
  code's own target are text in the committed file, so the byte-exact
  check `--check` already applies to the other two templates applies here
  unchanged, the guard can read all of it, and the derivation regenerates
  it for whoever derives this repository.

What that check proves is worth stating exactly, because it is not
"the background looks right": it proves that the committed file is what
these declarations derive, character for character -- the names, the
address, the palette, the motif's own weight, and the string inside the
code. What it does not prove is anything about a rendering: that no glyph
collides with the ribbon, that no line overflows the plate. The first is
answered by construction (`ribbon.safe_margins` places the plate inside
the corridor the stroke leaves, at every stroke weight the charter might
declare); the second by fitting each line's size to the plate it is set in
rather than typing three sizes and hoping (`_fitted_font_size`).

What it costs a volunteer is one export, and that cost is named on the
page rather than hidden: `docs/toolkit/visual-kit.md` already asks for
exactly that export from the other two files, and this is the one of the
three that needs no editing first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from . import brand, formats, registration_code, ribbon
from .declaration import published

__all__ = [
    "ANNOUNCEMENT_PATH",
    "BACKGROUND_PATH",
    "FLYER_PATH",
    "render_announcement_template",
    "render_flyer_template",
    "render_video_call_background",
]

#: Where each generated template lives, relative to a repository root.
#: `docs/toolkit/visual-kit.md` links to both by these paths, and
#: `app/src/content/registry.ts::PUBLIC_ASSETS` publishes them.
ANNOUNCEMENT_PATH: Final = Path("docs") / "assets" / "announcement-template.svg"
FLYER_PATH: Final = Path("docs") / "assets" / "flyer-template.svg"
BACKGROUND_PATH: Final = Path("docs") / "assets" / "video-call-background.svg"

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
    _Pairing("the background's three lines, on its white plate", "black", "white"),
    _Pairing("the background's code label, on the field", "black", "turquoise"),
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


def _display_words(name: str) -> str:
    """An organisation's name with its own words separated by spaces.

    An organisation that runs its own words together -- `ReadingRoomTrust`
    -- is one token in the declaration and three words on a page set in
    capitals: upper-casing it whole gives `READINGROOMTRUST`, the name
    spelled correctly and read wrongly. The boundaries are not invented:
    `_WORDMARK_CAMEL` is the same reading `_wordmark_runs` already takes of
    the same field, so the two treatments of one name cannot come to
    disagree about where it breaks. A name already written with spaces
    (`The Example Collective`) comes back unchanged.
    """
    words = [word.strip() for word in _WORDMARK_CAMEL.findall(name)]
    return " ".join(word for word in words if word)


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
        # The background sets all three of these in capitals, which is a
        # display treatment and not a re-spelling: no word boundary is
        # invented, unlike the camel case `visual.py` refused to derive
        # for a host. `series_caps` above is the same treatment on the
        # same kind of line.
        "organisation_caps": _display_words(identity.organisation).upper(),
        "strapline_caps": identity.strapline.upper(),
        "address_caps": identity.forum_host.upper(),
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
  <!-- Generated, not drawn: tools/scripts/generate_brand_css.py writes this file
  from instance/data/brand.json (the colours and the motif) and instance/config.json
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


# --------------------------------------------------------------------------
# The video-call background
# --------------------------------------------------------------------------

#: The canvas. 1920x1080 is the size every video-call application scales
#: its virtual background to, and the size the hand-drawn file this
#: replaces was drawn at -- the designer's own vector original
#: (`host-background_initial.pdf`, gitignored local reference material) is
#: the same composition exported at 1440x810, the same 16:9 frame.
_BACKGROUND_WIDTH: Final = 1920.0
_BACKGROUND_HEIGHT: Final = 1080.0

#: The plate's own vertical geometry, in canvas units, read straight off
#: the original at this size: it runs from 24 to 376, drawn with a 3-unit
#: rule. Horizontal geometry is deliberately *not* here, because it is not
#: a measurement worth keeping -- `ribbon.safe_margins` derives it, and
#: what it derives for this canvas (277.56) lands within half a unit of
#: where the designer put the plate's own left edge, which is the check on
#: both.
_PLATE_TOP: Final = 24.0
_PLATE_BOTTOM: Final = 376.0
_PLATE_RULE: Final = 3.0
_PLATE_PADDING: Final = 28.0

#: Each line's baseline and the capital height it is set at, in canvas
#: units, measured off the original: the name at 76 units of cap height,
#: the strapline at 45, the address at 25.
_PLATE_LINES: Final = ((152.0, 76.0), (241.0, 45.0), (311.0, 25.0))

#: Cap height as a fraction of the font size, for the heavy grotesques
#: this charter names and for every fallback in `_FALLBACK`. Used one way
#: only -- to turn a measured capital height back into the `font-size` that
#: produces it.
_CAP_HEIGHT_EM: Final = 0.72

#: The average advance of one capital, as a fraction of the font size, for
#: fitting a line to the plate it is set in. Measured on the original's own
#: two lines whose glyph mix is what these three actually are -- a name
#: (1346 units across 19 characters at 105.6) and a domain (587 across 25
#: at 34.7) -- which give 0.671 and 0.677; rounded *up*, so a line of
#: narrower letters is shrunk slightly sooner than it needs to be rather
#: than one unit too late. SVG does not wrap and cannot measure, so this is
#: what stands between a long organisation's name and the overflowing
#: poster D-08 names -- the same job `visual._scaled_font_size` does for a
#: talk title, done against a real box instead of against a soft limit.
_ADVANCE_EM: Final = 0.68

#: The code's own box and where it sits: 202 units square, 86 in from the
#: right edge and 24 up from the bottom, all measured off the original. Its
#: label sits above it, the two baselines 53 and 24 units above the box.
#: Nothing here is derived from the ribbon, and that is not an omission:
#: `ribbon.waypoints`'s right-hand motif leaves this canvas at 0.475 of its
#: own height, so no part of the stroke shares a row with this block --
#: `test_brand.py` samples the rendered curve and holds that.
_CODE_SIDE: Final = 202.0
_CODE_RIGHT_GAP: Final = 86.0
_CODE_BOTTOM_GAP: Final = 24.0
_CODE_LABEL_BASELINES: Final = (53.0, 24.0)
_CODE_LABEL_CAP: Final = 20.0

#: What the label says. Product prose, in English, like the templates' own
#: "WHAT TO EXPECT?" and "REGISTER HERE" -- not an instance's words, and so
#: not something a declaration could supply. It says what scanning the code
#: does, which is only sayable because the code has one target
#: (`registration_code.forum_code_target`). The file this replaces said
#: "SCAN & REGISTER NOW:" over a code that resolved to one 2024 forum
#: thread for one past edition; the wording is corrected here together with
#: the target, not separately from it.
_CODE_LABEL: Final = ("SCAN TO JOIN", "THE DISCUSSION")


def _fitted_font_size(text: str, *, cap_height: float, available: float) -> float:
    """A font size that sets `text` at `cap_height` unless it would then
    run wider than `available`, in which case as large as fits.

    A pure function of the string's length, deliberately:
    `visual._scaled_font_size`'s own argument applies unchanged -- the same
    declaration asks for the same size on any machine, before a glyph is
    drawn, where a browser measurement could differ between two builds
    that agree on every design decision.
    """
    by_height = cap_height / _CAP_HEIGHT_EM
    if not text:
        return by_height
    by_width = available / (len(text) * _ADVANCE_EM)
    return min(by_height, by_width)


_BACKGROUND: Final = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"
     viewBox="0 0 {w} {h}" font-family="{font_family}">
  <title>{series_title} — video-call background</title>
  <desc>Video-call background, {w}x{h}. Unlike the other two files in this
  kit it holds nothing an event changes, so there is nothing to fill in:
  export it to PNG or JPEG and add it as a virtual background in whatever
  the session runs on.</desc>

{generated_note}
  <rect width="{w}" height="{h}" fill="{turquoise}"/>

  <!-- The ribbon: one continuous stroke, running off the edges and
       turning back on itself, in the charter's own motif colour and at its
       own weight. The plate below sits inside the corridor the stroke
       leaves free, so no word is ever drawn across it. -->
  <g fill="none" stroke="{ribbon_stroke}" stroke-width="{stroke_weight}"
     stroke-linecap="round" stroke-linejoin="round">
    <path d="{ribbon}"/>
  </g>

  <!-- The plate: who this is, what the series is for, and where to find
       it. All three lines are declared values set in capitals, and each is
       sized to fit this plate rather than at a fixed size, so a longer
       name shrinks instead of running off the edge. -->
  <rect x="{plate_x}" y="{plate_y}" width="{plate_w}" height="{plate_h}"
        fill="{white}" stroke="{black}" stroke-width="{plate_rule}"/>
  <g text-anchor="middle" fill="{black}">
    <text x="{plate_mid}" y="{name_y}" font-size="{name_size}"
          font-weight="900">{organisation_caps}</text>
    <text x="{plate_mid}" y="{strapline_y}" font-size="{strapline_size}"
          font-weight="800">{strapline_caps}</text>
    <text x="{plate_mid}" y="{address_y}" font-size="{address_size}"
          font-weight="700">{address_caps}</text>
  </g>

  <!-- The code, and what it does. It is drawn, not left as a slot to
       fill: it encodes one declared address and nothing an event changes,
       so there is nothing here for a volunteer to generate. That address
       is in the title element below, in the clear, so what a code points
       at can be read without scanning it. -->
  <g text-anchor="middle" fill="{black}" font-size="{label_size}"
     font-weight="800">
    <text x="{code_mid}" y="{label_top_y}">{label_top}</text>
    <text x="{code_mid}" y="{label_bottom_y}">{label_bottom}</text>
  </g>
  <rect x="{code_x}" y="{code_y}" width="{code_side}" height="{code_side}"
        fill="{white}"/>
  <svg x="{code_x}" y="{code_y}" width="{code_side}"
       height="{code_side}">{code}</svg>
</svg>
"""


def render_video_call_background(root: Path) -> str:
    """`docs/assets/video-call-background.svg` in full."""
    values = _values(root)
    width, height = _BACKGROUND_WIDTH, _BACKGROUND_HEIGHT
    ratio = float(values["ribbon_ratio"])
    left, right = ribbon.safe_margins(width, height, ratio=ratio)

    plate_x = left + _PLATE_RULE / 2
    plate_w = (width - right - _PLATE_RULE / 2) - plate_x
    available = plate_w - 2 * _PLATE_PADDING
    lines = (
        values["organisation_caps"],
        values["strapline_caps"],
        values["address_caps"],
    )
    sizes = [
        _fitted_font_size(text, cap_height=cap, available=available)
        for text, (_baseline, cap) in zip(lines, _PLATE_LINES, strict=True)
    ]

    code_x = width - _CODE_RIGHT_GAP - _CODE_SIDE
    code_y = height - _CODE_BOTTOM_GAP - _CODE_SIDE

    return _BACKGROUND.format(
        **values,
        w=_num(width),
        h=_num(height),
        generated_note=_GENERATED_NOTE,
        stroke_weight=_stroke_weight(width, height, ratio),
        ribbon=_ribbon(width, height),
        plate_x=_num(plate_x),
        plate_y=_num(_PLATE_TOP + _PLATE_RULE / 2),
        plate_w=_num(plate_w),
        plate_h=_num(_PLATE_BOTTOM - _PLATE_TOP - _PLATE_RULE),
        plate_rule=_num(_PLATE_RULE),
        plate_mid=_num(plate_x + plate_w / 2),
        name_y=_num(_PLATE_LINES[0][0]),
        name_size=_num(sizes[0]),
        strapline_y=_num(_PLATE_LINES[1][0]),
        strapline_size=_num(sizes[1]),
        address_y=_num(_PLATE_LINES[2][0]),
        address_size=_num(sizes[2]),
        code_x=_num(code_x),
        code_y=_num(code_y),
        code_side=_num(_CODE_SIDE),
        code_mid=_num(code_x + _CODE_SIDE / 2),
        label_size=_num(_CODE_LABEL_CAP / _CAP_HEIGHT_EM),
        label_top_y=_num(code_y - _CODE_LABEL_BASELINES[0]),
        label_bottom_y=_num(code_y - _CODE_LABEL_BASELINES[1]),
        label_top=_CODE_LABEL[0],
        label_bottom=_CODE_LABEL[1],
        code=registration_code.forum_code_svg(dark=values["black"], root=root),
    )
