"""The three files a collaborator downloads, derived rather than drawn.

`docs/handbook/assets/announcement-template.svg` and `flyer-template.svg` are the
files `docs/handbook/toolkit/visual-kit.md` links to: a volunteer downloads one,
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
- `#3FB1C2` on `#F4F1E6` -- the wordmark's second colour on the band
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
refuses if one of them falls under AA. Half of that claim is read back
out of the markup and half is still a reviewer's, which is why each entry
says where it is; the paragraph on the wordmark's casing below says which
half is which. What it buys is that the check holds for *any* palette,
including one a duplicate writes tomorrow.

The ribbon these files draw is the ribbon
-------------------------------------------
Both files drew three bare circles and arcs in place of the motif until
2026-08-28, which is what `instance/data/brand.json::motif._ribbon` had always
said they were: a stroke ending in a closed ring reads as a line with a
circle stuck on it, not as one continuous ribbon running off the edges.
`motifs/ribbon.py` had the real curve all along -- traced against the designer's
own poster, the same 1200-unit reference these two layouts come from --
and drew it for the generated posters (`visual.py`) and nowhere else. It
draws it here now, at the same colour and the same weight the charter
already gave the loops, so nothing about the stroke itself changed.

What that cost was a re-layout, which is why it had been deferred and is
the whole of the work: the ribbon owns ground on both sides that these
two compositions were using. Every block moved below is moved because the
stroke passes through where it stood, and the distance each moved is the
stroke's own reach over that block's rows -- read off `motifs.path`
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

The wordmark's second word takes `field_text` and not the field itself,
which is what the reference sets it in. `colour._roles` in every charter
forbids the field as text on white or on a band by name -- `contrast.
_forbidden` does not: it names the field on *white* and stops there, so
the pairing the reference actually sets is refused by the role and not by
the table beneath it.

The two figures this paragraph used to carry were one charter's, recorded
when there was one. Re-measured at all six this repository holds -- the
four under `assets/brand/`, this instance's and the example's -- the reference's
own pairing (`field` on `band`) measures **1.40 to 1.43**, and the
treatment shipped instead (`field_text` on the same band) measures
**4.58 to 5.49**. Neither end moves the decision: the raw treatment is
about a third of what AA asks at every charter, and the readable one
clears it at every charter -- though `assets/brand/steps/` clears it by 0.08,
which is the margin to watch when a charter's `field_text` is next
re-derived.

**The question is settled by a control, not only by a rule.** The entry
in `_LEGIBILITY` below naming this pairing is measured at build time, so
declaring the raw treatment there fails `_values` at every one of the six
charters and writes no template at all. So restoring the reference's
treatment costs a change to what the charter says about its own colours,
at six files, and a build that refuses until they all say it. That is
what a maintainer has to weigh, and it is not a decision a generator gets
to take on its own.

What the arithmetic could not see was the markup. `_LEGIBILITY` is a list
kept true by hand, and setting the accent to `field` without moving the
entry beside it passed every gate here -- `generate_brand_css.py --check`
and 2132 tests -- because nothing read a rendered `fill` back. That half
is now read:
`test_brand.py::test_the_only_colours_either_template_inks_type_in_are_the_measured_ones`
walks both generated files, carries `fill` down the tree the way SVG
inherits it, and holds the set of colours a run of type is actually set
in equal to the set of inks this list measures. An ink the markup adds
without an entry fails it, and an entry no type is set in any more fails
it as a measurement of nothing.

One half of the claim is still a reviewer's, and it is the ground rather
than the ink: `where` says which surface each run sits on, and reading
that back needs the rendered geometry -- which element paints behind
which -- rather than an attribute. `tools/visuals/check-templates.mjs`
already walks both files in a browser at every charter, which is where a
control for it would go and why one is not attempted here.

The third file, and why it is vector where it used to be a bitmap
-------------------------------------------------------------------
`docs/handbook/assets/video-call-background.svg` is what a host puts behind them
during a session. It was a hand-drawn PNG until 2026-08-28, and it was the
last hand-made file in `docs/handbook/assets/` -- which made it the one thing
`convener_ops.derivation.derivation_guard` could not read: that guard sweeps every
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
  what `convener_ops.derivation.repository` re-runs when it builds a duplicate's
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
collides with the motif, that no line overflows the plate. The first is
answered by construction (`motifs.safe_margins` places the plate inside
the corridor the stroke leaves, at every stroke weight the charter might
declare); the second by fitting each line's size to the plate it is set in
rather than typing three sizes and hoping (`_fitted_font_size`).

All three answer it that way now, and one of them did not
--------------------------------------------------------
The paragraph above was true of the background and of nothing else. The
announcement and the flyer hand-placed every block of type: each x was a
number fitted, by eye, to where *one* drawing happened to run, and the
drawing they were fitted to was the ribbon. Nothing said so, and nothing
could fail when it stopped being true -- so when a second family arrived,
it was the family that was fitted to the layout rather than the layout
that read the family, and the layout's own numbers stayed exactly as
wrong as they had always been. Rendered and measured for the first time
(`tools/visuals/check-templates.mjs`), that cost two things nobody knew
about: the example instance's flyer drew its motif **11.9 units through
its own tagline**, and this instance's flyer cleared its headline by
**1.6 units** on a 2100-unit page.

Every horizontal coordinate in both files comes from `motifs` now, over
the rows the block it places actually occupies -- see "Where a block of
type may stand" below for the rule and for what stays a literal. The
vertical ones do not: a baseline, a band's own depth, the proportion of
the page a photograph takes are the composition's, and they would not
change if the charter named a different drawing. That is the test, and it
is the only one: a number that would have to move for another family is
the drawing's and is derived; a number that would not is the design's and
stays written down.

What it costs a volunteer is one export, and that cost is named on the
page rather than hidden: `docs/handbook/toolkit/visual-kit.md` already asks for
exactly that export from the other two files, and this is the one of the
three that needs no editing first.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ..declaration import published
from . import brand, formats, lockup, motifs, registration_code, typeface

__all__ = [
    "ANNOUNCEMENT_PATH",
    "BACKGROUND_HEIGHT",
    "BACKGROUND_PATH",
    "BACKGROUND_WIDTH",
    "FLYER_PATH",
    "UNITS_PER_MM",
    "render_announcement_template",
    "render_flyer_template",
    "render_video_call_background",
]

#: Where each generated template lives, relative to a repository root.
#: `docs/handbook/toolkit/visual-kit.md` links to both by these paths, and
#: `app/src/content/registry.ts::PUBLIC_ASSETS` publishes them.
ASSETS_DIR: Final = Path("docs") / "handbook" / "assets"
ANNOUNCEMENT_PATH: Final = ASSETS_DIR / "announcement-template.svg"
FLYER_PATH: Final = ASSETS_DIR / "flyer-template.svg"
BACKGROUND_PATH: Final = ASSETS_DIR / "video-call-background.svg"

#: The flyer's user-unit grid: ten units per millimetre of A4, so a
#: coordinate reads as a tenth of a millimetre and the physical size comes
#: from `formats.PRINT_PAPER_MM` rather than from 210 and 297 typed again.
UNITS_PER_MM: Final = 10

#: The class every element the composition *places* carries, and the whole
#: of the contract `tools/visuals/check-templates.mjs` reads it under: a
#: block is a rectangle or a device this file sets against the drawing's
#: corridor, and no two blocks may run into each other. Type carries it
#: implicitly -- every `<text>` line is a block -- so what is marked here
#: is the three that are not type: the white plate a photograph goes on,
#: the registration slot, and the wordmark's own device.
#:
#: The grounds and the bands are deliberately *not* blocks. A band is the
#: composition's own ground and type sits inside it on purpose, which is
#: the same reason the sweep exempts a pair where one block wholly
#: contains the other: "QR code" inside the slot is the design, and the
#: column crossing the slot's edge is not.
BLOCK: Final = "block"

#: The placeholders both files carry into the volunteer's editor, spelled
#: exactly as `app/src/content/render.ts::substitute` resolves them -- an
#: invented one would send somebody looking for a field that does not
#: exist (`app/tests/content/visual-kit.test.tsx` holds this).
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
    _Pairing("the wordmark's address, in the top band", "dominant", "band"),
    _Pairing(
        "the wordmark's second word, in the top band",
        "field_text",
        "band",
    ),
    _Pairing("the series' name, on the field", "dominant", "field"),
    _Pairing("the invitation lines, on the field", "black", "field"),
    _Pairing("the talk's title, in the band", "dominant", "band"),
    _Pairing("the date line, on the field", "dominant", "field"),
    _Pairing("the 'what to expect' heading and rows, on the field", "black", "field"),
    _Pairing("the before/during/after labels, on the field", "dominant", "field"),
    _Pairing("the caption inside the photographic frame", "ink_muted", "field_tint"),
    _Pairing("the speaker's name and affiliation, on the frame", "ink", "white"),
    _Pairing("the label in the QR slot", "ink_muted", "white"),
    _Pairing("the flyer's edition code, in the foot band", "dominant", "band"),
    _Pairing("the flyer's closing line, in the foot band", "black", "band"),
    _Pairing("the background's three lines, on its white plate", "black", "white"),
    _Pairing("the background's code label, on the field", "black", "field"),
)


def _num(value: float) -> str:
    """A coordinate, without a trailing `.0` on a whole number."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text else "0"


# --------------------------------------------------------------------------
# Where a block of type may stand
# --------------------------------------------------------------------------
#
# Every horizontal coordinate in the two compositions below comes from one
# of the four functions in this section, and each of them asks the family
# in force where its drawing actually is over that block's own rows. What
# stays a literal is the *design*: which rows a block sits on, how far in
# from the page's edge the composition sets it when nothing is in the way,
# how large it is, the axis it centres on. What is derived is the one thing
# a hand-placed number cannot survive -- a change of family.
#
# The rule, stated once because every block below follows it: a block sits
# at its own design indent, or at the corridor's own edge when the drawing
# reaches past that indent, whichever is further from the drawing. So a
# family that reaches nowhere near a block leaves the composition exactly
# as it was designed, and a family that reaches into it pushes it aside
# rather than being fitted around it.


#: How far the ink of a line of type reaches above and below its own
#: baseline, as a fraction of the font size. Measured in the pinned engine
#: across every line these three files set, in the face the charter names:
#: the deepest ascender ran to 0.902 of the size above the baseline and the
#: deepest descender to 0.234 below it. Rounded up, because these two turn
#: a baseline into the band of rows a corridor is asked about, and a band
#: read a shade too tall asks for a shade more room than the glyphs need.
_INK_ABOVE_BASELINE_EM: Final = 0.95
_INK_BELOW_BASELINE_EM: Final = 0.25


@dataclass(frozen=True)
class _Canvas:
    """One page, and the drawing the charter in force puts on it.

    Carries the family's name and the charter's own stroke ratio so that
    the layout below asks `motifs` a question per block rather than
    threading four arguments through every call. It reads no file: the two
    renderers load the charter once and hand it here, the same separation
    `motifs.stroke_width` keeps.
    """

    family: str
    width: float
    height: float
    ratio: float

    def rows(self, baseline: float, size: float) -> tuple[float, float]:
        """The band of rows a line set at `size` on `baseline` occupies."""
        return (
            baseline - _INK_ABOVE_BASELINE_EM * size,
            baseline + _INK_BELOW_BASELINE_EM * size,
        )

    def corridor(self, top: float, bottom: float) -> tuple[float, float]:
        """The first and last x a word may use, over those rows.

        `motifs.safe_margins` in the units the page is drawn in rather than
        as two margins, because every coordinate below is an x.
        """
        left, right = motifs.safe_margins(
            self.family,
            self.width,
            self.height,
            ratio=self.ratio,
            top=top,
            bottom=bottom,
        )
        return left, self.width - right

    def free(self, top: float, bottom: float) -> tuple[motifs.Span, ...]:
        """Every strip of the page a word may occupy, over those rows."""
        return motifs.free_spans(
            self.family,
            self.width,
            self.height,
            ratio=self.ratio,
            top=top,
            bottom=bottom,
        )


def _starts_at(canvas: _Canvas, *, indent: float, top: float, bottom: float) -> float:
    """Where a block set from the left begins: its own design indent, or
    the corridor's own left edge when the drawing reaches past it."""
    first, _last = canvas.corridor(top, bottom)
    return max(indent, first)


def _ends_at(canvas: _Canvas, *, inset: float, top: float, bottom: float) -> float:
    """Where a block set to the right ends: the page's own design inset,
    or the corridor's own right edge when the drawing reaches past it."""
    _first, last = canvas.corridor(top, bottom)
    return min(canvas.width - inset, last)


def _fitted(
    text: str,
    *,
    size: float,
    weight: int,
    available: float,
    letter_spacing: float = 0.0,
) -> float:
    """`size`, unless the line would then run wider than `available`, in
    which case the largest size that fits.

    The design's own size is what a page is set at; the corridor is what it
    may not exceed. So a family that leaves a block alone leaves its size
    alone too, and only a family that crowds it makes it smaller -- the
    same rule the placement above follows, applied to the one property a
    placement cannot fix for a line set on a fixed axis.

    `typeface.width` is the estimate, for the reason that module gives.
    """
    if not text:
        return size
    room = available - len(text) * letter_spacing
    if room <= 0:
        raise ValueError(
            f"no room to set {text!r} at all: {_num(available)} units of "
            "corridor cannot even hold its letter spacing"
        )
    ems = typeface.width(text, size=1.0, weight=weight)
    return min(size, room / ems)


def _at_most(*, size: float, ems: float, available: float) -> float:
    """`size`, or the size at which a line `ems` wide fits `available`.

    The same rule `_fitted` applies, for a line whose width has already
    been worked out -- one set in more than a single weight, which
    `typeface.width` measures a run at a time.
    """
    if ems <= 0:
        return size
    return min(size, available / ems)


def _centred(
    canvas: _Canvas,
    text: str,
    *,
    axis: float,
    baseline: float,
    size: float,
    weight: int,
    letter_spacing: float = 0.0,
    limit: float | None = None,
) -> float:
    """The size a line centred on `axis` is set at, so that it stays inside
    the corridor its own rows leave.

    The axis is the page's own, a design decision and a literal: a
    composition has one vertical axis, and letting each centred line find
    the middle of its own corridor would make the stack wander from row to
    row. So the corridor decides the size rather than the position, and the
    line stays where the design put it. `limit` bounds the half-width
    further, for a line the composition itself keeps clear of something --
    the flyer's foot band is the one case.

    The rows are taken at the *design* size, before any shrinking. That is
    deliberate rather than approximate: a line set smaller occupies fewer
    rows, and fewer rows can only leave a corridor at least as wide, so the
    answer stays true for the size it produces.
    """
    first, last = canvas.corridor(*canvas.rows(baseline, size))
    half = min(axis - first, last - axis)
    if limit is not None:
        half = min(half, limit)
    return _fitted(
        text,
        size=size,
        weight=weight,
        available=2 * half,
        letter_spacing=letter_spacing,
    )


# --------------------------------------------------------------------------
# The mark, and the wordmark beside it
# --------------------------------------------------------------------------


def _mark(
    x: float,
    y: float,
    size: float,
    *,
    family: str,
    ratio: float,
    dots: str,
    ink: str,
) -> str:
    """The lock-up's device, placed on this page.

    Everything the device *is* lives in `publication/lockup.py` -- what
    was drawn here before, whose artwork it was traced off, and why what
    replaces it follows the charter rather than becoming the product's own
    mark. This adds the one thing that is the page's: where the box goes
    and how many of the page's own units it occupies, so that both files
    ask for it at the size their own composition wants and neither
    restates any geometry.
    """
    return lockup.device(
        family=family,
        ratio=ratio,
        ink=ink,
        dots=dots,
        attributes=(
            f'class="{BLOCK}" x="{_num(x)}" y="{_num(y)}" '
            f'width="{_num(size)}" height="{_num(size)}"'
        ),
        indent=" " * 4,
    )


def _motif_path(family: str, width: float, height: float) -> str:
    """The charter's motif for a canvas, indented to sit in the markup.

    `motifs.path` returns one command a line, which is how a hundred
    cubics stay readable; a `d` attribute pasted in flush left inside an
    indented document is not, and these two files are opened in a text
    editor on purpose.
    """
    joiner = "\n" + " " * 15
    return joiner.join(motifs.path(family, width, height).splitlines())


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
    runs = _wordmark_runs(identity)
    return {
        **_SPEAKER,
        **colours,
        "block": BLOCK,
        # The address exactly as the wordmark sets it, without the tones it
        # is set in: `_wordmark_values` sizes that line to the room it has,
        # and a size is a property of the string and not of its colours.
        "wordmark_text": "".join(text for text, _accent in runs),
        "wordmark": _wordmark(
            runs,
            ink=colours["dominant"],
            accent=colours["field_text"],
        ),
        "motif_family": str(motif[brand.MOTIF_FAMILY]),
        "motif_stroke": str(motif["stroke"]),
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
        "motif_ratio": str(motif["width_ratio"]),
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
    <rect width="{w}" height="{h}" fill="{field}"/>
    <rect y="0" width="{w}" height="168" fill="{band}"/>
    <rect y="400" width="{w}" height="146" fill="{band}"/>

    <!-- The motif: the drawing the charter names, in the charter's own
         motif colour and at its own weight so neither can drift from it,
         painted before the words rather than over them. It carries no text
         and every word on this page is placed clear of it. Move or delete
         it freely; if you move a word instead, keep it out of the stroke,
         because a heavy line behind dark type is unreadable type. -->
    <g id="motif" fill="none" stroke="{motif_stroke}"
       stroke-width="{stroke_weight}"
       stroke-linecap="round" stroke-linejoin="round">
      <path d="{motif}"/>
    </g>

    <!-- Wordmark. The device is the charter's own drawing again, at the
         size of a mark and clipped to its box, drawn rather than embedded:
         an SVG that references an external logo file is an SVG that
         travels broken. The dot is the one the mark closes on. The rule
         underlines the two together. Nothing here is anybody's logo: put
         your own in its place if you have one. -->
{mark}
    <text x="{wordmark_x}" y="112" font-size="{wordmark_size}"
          font-weight="500">{wordmark}</text>
    <rect x="{rule_x}" y="{rule_y}" width="{rule_w}" height="{rule_h}"
          fill="{dominant}"/>

    <text x="{axis}" y="272" text-anchor="middle" font-size="{series_size}"
          font-weight="900" letter-spacing="1"
          fill="{dominant}">{series_caps}</text>
    <text x="{axis}" y="330" text-anchor="middle" font-size="{invitation_size}"
          fill="{black}">{invitation}</text>
    <text x="{axis}" y="372" text-anchor="middle" font-size="{address_size}"
          font-weight="700" fill="{black}">{forum_host}</text>
  </g>

  <g id="variable">
    <!-- TALK TITLE. Two lines, split by hand — SVG does not wrap text. A
         very long title: drop the font-size and use three lines. -->
    <text text-anchor="middle" font-size="{title_size}" font-weight="700"
          fill="{dominant}">
      <tspan x="{axis}" y="458">{speaker_title}</tspan>
      <tspan x="{axis}" y="512"></tspan>
    </text>

    <!-- DATE AND TIME. Written out the way it is said aloud; the app holds
         {speaker_date} as 2026-11-12 and {speaker_time} as 12:30 (CET). -->
    <text x="{axis}" y="600" text-anchor="middle" font-size="{date_size}"
          font-weight="700"
          fill="{dominant}">{speaker_date} at {speaker_time} (CET)</text>

    <!-- SPEAKER PHOTO. Replace this frame with the photo: in Inkscape,
         File &gt; Import, then send the image behind this white frame. Keep
         the tilt. No photo yet? Leave the frame; it reads as unfinished. -->
    <g transform="rotate(4 {frame_pivot_x} 900)">
      <rect class="{block}" x="{frame_x}" y="690" width="420" height="470"
            fill="{white}"/>
      <rect x="{frame_photo_x}" y="712" width="376" height="376"
            fill="{field_tint}"/>
      <text x="{frame_caption_x}" y="912" text-anchor="middle" font-size="26"
            fill="{ink_muted}">speaker photo</text>
      <text x="{frame_end_x}" y="1128" text-anchor="end" font-size="30"
            font-weight="800" fill="{ink}">{speaker_name}</text>
      <text x="{frame_end_x}" y="1152" text-anchor="end" font-size="19"
            fill="{ink}">{speaker_affiliation}</text>
    </g>
  </g>

  <g id="fixed-what-to-expect">
    <text x="{heading_x}" y="730" font-size="{heading_size}" font-weight="800"
          fill="{black}">WHAT TO EXPECT?</text>
    <text font-size="{column_size}" fill="{black}">
      <tspan x="{column_x}" y="796" font-weight="800"
             fill="{dominant}">BEFORE: </tspan><tspan>Ask your</tspan>
      <tspan x="{column_x}" y="832">questions to the speaker</tspan>
      <tspan x="{column_x}" y="868">at {forum_host}</tspan>
      <tspan x="{column_x}" y="944" font-weight="800"
             fill="{dominant}">D-DAY: </tspan><tspan>Presentation</tspan>
      <tspan x="{column_x}" y="980">followed by a discussion</tspan>
      <tspan x="{column_x}" y="1016">with the audience</tspan>
      <tspan x="{column_x}" y="1092" font-weight="800"
             fill="{dominant}">AFTER: </tspan><tspan>Continue the</tspan>
      <tspan x="{column_x}" y="1128">discussion and connect</tspan>
      <tspan x="{column_x}" y="1164">with peers</tspan>
    </text>

    <!-- REGISTRATION QR. Generate it from the registration link with any
         offline generator, or in the app; then drop it over this square.
         It is the one block on this page that stands on the far side of
         the motif rather than inside the corridor with the words: it
         takes whatever ground the drawing leaves between it and the left
         edge, over its own rows, and is as wide as that ground allows. -->
    <text x="{slot_x}" y="898" font-size="{register_size}" font-weight="800"
          fill="{black}">REGISTER</text>
    <text x="{slot_x}" y="936" font-size="{register_size}" font-weight="800"
          fill="{black}">HERE</text>
    <rect class="{block}" x="{slot_x}" y="960" width="{slot_side}" height="{slot_side}"
          fill="{white}"/>
    <rect x="{slot_dash_x}" y="{slot_dash_y}" width="{slot_dash_side}"
          height="{slot_dash_side}" fill="none"
          stroke="{rule_strong}" stroke-width="3" stroke-dasharray="10 8"/>
    <text x="{slot_mid_x}" y="1058" text-anchor="middle"
          font-size="{slot_label_size}" fill="{ink_muted}">QR code</text>
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
    <rect width="{w}" height="{h}" fill="{field}"/>
    <rect y="0" width="{w}" height="290" fill="{band}"/>
    <rect y="700" width="{w}" height="470" fill="{band}"/>
    <rect y="2760" width="{w}" height="210" fill="{band}"/>

    <!-- The motif: the drawing the charter names, in the charter's own
         motif colour and at its own weight, painted before the words
         rather than over them. It carries no text and every word here is
         placed clear of it. Move or delete it freely; if you move a word
         instead, keep it out of the stroke. -->
    <g id="motif" fill="none" stroke="{motif_stroke}"
       stroke-width="{stroke_weight}"
       stroke-linecap="round" stroke-linejoin="round">
      <path d="{motif}"/>
    </g>

    <!-- Wordmark: the charter's own drawing at the size of a mark,
         clipped to its box, with the dot the mark closes on. Nothing here
         is anybody's logo: put your own in its place if you have one. -->
{mark}
    <text x="{wordmark_x}" y="188" font-size="{wordmark_size}"
          font-weight="500">{wordmark}</text>
    <rect x="{rule_x}" y="{rule_y}" width="{rule_w}" height="{rule_h}"
          fill="{dominant}"/>

    <text x="{axis}" y="430" text-anchor="middle" font-size="{series_size}"
          font-weight="900" letter-spacing="2"
          fill="{dominant}">{series_caps}</text>
    <text x="{axis}" y="530" text-anchor="middle" font-size="{tagline_size}"
          fill="{black}">{tagline}</text>
    <text x="{axis}" y="600" text-anchor="middle" font-size="{invitation_size}"
          font-weight="700"
          fill="{black}">{invitation}</text>
  </g>

  <g id="variable">
    <!-- TALK TITLE. Up to three lines, split by hand — SVG does not wrap
         text. A short title: use one line and raise the font-size. -->
    <text text-anchor="middle" font-size="{title_size}" font-weight="700"
          fill="{dominant}">
      <tspan x="{axis}" y="840">{speaker_title}</tspan>
      <tspan x="{axis}" y="940"></tspan>
      <tspan x="{axis}" y="1040"></tspan>
    </text>

    <!-- DATE AND TIME. The app holds {speaker_date} as 2026-11-12 and
         {speaker_time} as 12:30; write them out the way they are said. -->
    <text x="{axis}" y="1290" text-anchor="middle" font-size="{date_size}"
          font-weight="700"
          fill="{dominant}">{speaker_date} at {speaker_time} (CET)</text>

    <!-- SPEAKER PHOTO. Replace this frame with the photo: in Inkscape,
         File &gt; Import, then send the image behind this white frame. Keep
         the tilt. No photo yet? Leave the frame; it reads as unfinished. -->
    <g transform="rotate(4 {frame_pivot_x} 1900)">
      <rect class="{block}" x="{frame_x}" y="1440" width="700" height="810"
            fill="{white}"/>
      <rect x="{frame_photo_x}" y="1478" width="624" height="624"
            fill="{field_tint}"/>
      <text x="{frame_caption_x}" y="1800" text-anchor="middle" font-size="44"
            fill="{ink_muted}">speaker photo</text>
      <text x="{frame_end_x}" y="2180" text-anchor="end" font-size="56"
            font-weight="800" fill="{ink}">{speaker_name}</text>
      <text x="{frame_end_x}" y="2226" text-anchor="end" font-size="34"
            fill="{ink}">{speaker_affiliation}</text>
    </g>

    <!-- EDITION CODE. The series number this event carries in the data. -->
    <text x="{axis}" y="2812" text-anchor="middle" font-size="{edition_size}"
          font-weight="700" fill="{dominant}">{speaker_edition_code}</text>
  </g>

  <g id="fixed-what-to-expect">
    <text x="{heading_x}" y="1470" font-size="{heading_size}" font-weight="800"
          fill="{black}">WHAT TO EXPECT?</text>
    <text font-size="{column_size}" fill="{black}">
      <tspan x="{column_x}" y="1590" font-weight="800"
             fill="{dominant}">BEFORE: </tspan><tspan>Ask your</tspan>
      <tspan x="{column_x}" y="1652">questions to the speaker</tspan>
      <tspan x="{column_x}" y="1714">at {forum_host}</tspan>
      <tspan x="{column_x}" y="1846" font-weight="800"
             fill="{dominant}">D-DAY: </tspan><tspan>Presentation</tspan>
      <tspan x="{column_x}" y="1908">followed by a discussion</tspan>
      <tspan x="{column_x}" y="1970">with the audience</tspan>
      <tspan x="{column_x}" y="2102" font-weight="800"
             fill="{dominant}">AFTER: </tspan><tspan>Continue the</tspan>
      <tspan x="{column_x}" y="2164">discussion and connect</tspan>
      <tspan x="{column_x}" y="2226">with peers</tspan>
    </text>

    <!-- REGISTRATION QR. Generate it from the registration link with any
         offline generator, then drop it over this square. Unlike the
         announcement's, this slot stands inside the same corridor as the
         words above it: on a page this tall the drawing is nowhere near
         this corner, and the slot keeps the column's own indent. -->
    <text x="{slot_x}" y="2360" font-size="{register_size}" font-weight="800"
          fill="{black}">REGISTER HERE</text>
    <rect class="{block}" x="{slot_x}" y="2400" width="{slot_w}" height="340"
          fill="{white}"/>
    <rect x="{slot_dash_x}" y="2430" width="{slot_dash_w}" height="280"
          fill="none"
          stroke="{rule_strong}" stroke-width="5" stroke-dasharray="18 14"/>
    <text x="{slot_mid_x}" y="2595" text-anchor="middle"
          font-size="{slot_label_size}" fill="{ink_muted}">QR code</text>
    <text x="{foot_axis}" y="2872" text-anchor="middle"
          font-size="{foot_size}" fill="{black}">{foot_top}</text>
    <text x="{foot_axis}" y="2928" text-anchor="middle"
          font-size="{foot_size}" fill="{black}">{foot_bottom}</text>
  </g>
</svg>
"""


def _stroke_weight(width: float, height: float, ratio: float) -> str:
    """The motif's stroke weight, from the charter's own ratio.

    `motifs.stroke_width` and not a literal: the weight the loops that
    stood in for the ribbon were drawn at (17 units on a 1200 square,
    0.014 of the shorter side) was nobody's measurement, and
    `motif._width_ratio` records one taken against the reference poster.
    """
    return _num(motifs.stroke_width(width, height, ratio=ratio))


@dataclass(frozen=True)
class _Wordmark:
    """The mark, the address beside it, and the rule that runs on east.

    `indent`, `top` and `size` place the mark's own hundred-unit box: the
    first is the design's own indent, and where the mark actually lands is
    that or the corridor's own edge, whichever is further in. `gap` is the
    air between the mark and the address, `baseline` and `text_size` set
    the address, and `rule_weight` is how heavy the rule is drawn.

    How far east the rule runs is not here, because it is not the mark's:
    it stops at the page's own inset or where the drawing comes down,
    whichever is nearer. It used to be a literal -- 964 on the square --
    and that number was the ribbon's right curl measured by hand, which is
    exactly the class of coordinate this file no longer keeps.
    """

    indent: float
    top: float
    size: float
    gap: float
    baseline: float
    text_size: float
    rule_weight: float


#: The square sets the mark at the size the reference poster sets it at: a
#: hundred units of twelve hundred, its top edge at 57 and its own indent
#: at 165. The flyer sets it at the same fraction of its own width, which
#: is what keeps the two reading as one series at two sizes.
_ANNOUNCEMENT_WORDMARK: Final = _Wordmark(165.0, 57.0, 100.0, 17.0, 112.0, 50.0, 4.0)
_FLYER_WORDMARK: Final = _Wordmark(280.0, 92.0, 175.0, 30.0, 188.0, 88.0, 7.0)

#: The weight each wordmark's address is set at, and the weight the two
#: `font-weight="800"` labels and headings are. Named because
#: `typeface.width` is charged per weight and a number typed twice, once
#: in the markup and once in the call that sizes it, is a number that can
#: drift.
_WORDMARK_WEIGHT: Final = 500
_HEADING_WEIGHT: Final = 800
_DISPLAY_WEIGHT: Final = 900
_BODY_WEIGHT: Final = 400
_STRONG_WEIGHT: Final = 700


def _wordmark_values(
    canvas: _Canvas, mark: _Wordmark, values: dict[str, str], *, inset: float
) -> dict[str, str]:
    """The mark, the address, and the rule that continues the mark's own
    tail east -- all three placed against the corridor their own rows leave.
    """
    rows = (mark.top, mark.top + mark.size)
    mark_x = _starts_at(canvas, indent=mark.indent, top=rows[0], bottom=rows[1])
    text_x = mark_x + mark.size + mark.gap
    text_rows = canvas.rows(mark.baseline, mark.text_size)
    _first, text_last = canvas.corridor(*text_rows)
    address = values["wordmark_text"]
    # The rule hangs from the box's own bottom edge and starts at its own
    # left one, so it underlines the whole lock-up -- the device and the
    # address together. It used to begin at (25, 83) inside the box, where
    # the traced device's tail turned east and became it; that coordinate
    # was a reading of somebody's poster and it went with the drawing.
    rule_x = mark_x
    rule_y = rows[1]
    rule_end = _ends_at(
        canvas, inset=inset, top=rule_y, bottom=rule_y + mark.rule_weight
    )
    return {
        "mark": _mark(
            mark_x,
            mark.top,
            mark.size,
            family=values["motif_family"],
            ratio=float(values["motif_ratio"]),
            dots=values["logo_dots"],
            ink=values["motif_stroke"],
        ),
        "wordmark_x": _num(text_x),
        "wordmark_size": _num(
            _fitted(
                address,
                size=mark.text_size,
                weight=_WORDMARK_WEIGHT,
                available=text_last - text_x,
            )
        ),
        "rule_x": _num(rule_x),
        "rule_y": _num(rule_y),
        "rule_w": _num(rule_end - rule_x),
        "rule_h": _num(mark.rule_weight),
    }


@dataclass(frozen=True)
class _Frame:
    """The tilted white plate a volunteer drops the speaker's photo into.

    Every field is a design decision and stays one: the plate's own size,
    the tilt, where the photo sits inside it and where the two lines of
    credit are set against its lower right. The one thing derived is how
    far east the whole assembly may stand, and it moves as one piece --
    `x` is where the design puts it, and a drawing that reaches into those
    rows slides it west rather than being fitted around it.
    """

    x: float
    y: float
    width: float
    height: float
    tilt: float
    pivot: motifs.Point
    photo_inset: float
    caption_offset: float
    end_offset: float


def _tilted(frame: _Frame, shift: float) -> tuple[motifs.Point, ...]:
    """The plate's four corners once it is tilted and moved by `shift`."""
    angle = math.radians(frame.tilt)
    pivot_x, pivot_y = frame.pivot[0] + shift, frame.pivot[1]
    corners = (
        (frame.x + shift, frame.y),
        (frame.x + shift + frame.width, frame.y),
        (frame.x + shift + frame.width, frame.y + frame.height),
        (frame.x + shift, frame.y + frame.height),
    )
    return tuple(
        (
            pivot_x + (x - pivot_x) * math.cos(angle) - (y - pivot_y) * math.sin(angle),
            pivot_y + (x - pivot_x) * math.sin(angle) + (y - pivot_y) * math.cos(angle),
        )
        for x, y in corners
    )


def _frame_values(canvas: _Canvas, frame: _Frame, *, inset: float) -> dict[str, str]:
    """The plate, moved west if the drawing reaches into its own rows."""
    corners = _tilted(frame, 0.0)
    rows = (min(y for _x, y in corners), max(y for _x, y in corners))
    limit = _ends_at(canvas, inset=inset, top=rows[0], bottom=rows[1])
    shift = min(0.0, limit - max(x for x, _y in corners))
    return {
        "frame_x": _num(frame.x + shift),
        "frame_photo_x": _num(frame.x + shift + frame.photo_inset),
        "frame_caption_x": _num(frame.x + shift + frame.caption_offset),
        "frame_end_x": _num(frame.x + shift + frame.end_offset),
        "frame_pivot_x": _num(frame.pivot[0] + shift),
    }


def _frame_west(canvas: _Canvas, frame: _Frame, *, inset: float) -> float:
    """The plate's own westmost point, which is what the column beside it
    may not run into."""
    corners = _tilted(frame, 0.0)
    rows = (min(y for _x, y in corners), max(y for _x, y in corners))
    limit = _ends_at(canvas, inset=inset, top=rows[0], bottom=rows[1])
    shift = min(0.0, limit - max(x for x, _y in corners))
    return min(x for x, _y in _tilted(frame, shift))


@dataclass(frozen=True)
class _Column:
    """The "what to expect" heading and the rows indented under it.

    `heading_indent` and `indent` are the design's own two indents, `top`
    and `bottom` the rows the whole block occupies, and `gap` the air the
    composition keeps between the column and whatever stands east of it.
    """

    heading_indent: float
    heading_baseline: float
    heading_size: float
    indent: float
    top: float
    bottom: float
    size: float
    gap: float


def _column_values(
    canvas: _Canvas, column: _Column, *, east: float, lines: tuple[_Line, ...]
) -> dict[str, str]:
    """The column, indented past the drawing and sized to the air it has."""
    heading_rows = canvas.rows(column.heading_baseline, column.heading_size)
    heading_x = _starts_at(
        canvas,
        indent=column.heading_indent,
        top=heading_rows[0],
        bottom=heading_rows[1],
    )
    column_x = _starts_at(
        canvas, indent=column.indent, top=column.top, bottom=column.bottom
    )
    _first, heading_last = canvas.corridor(*heading_rows)
    _first, column_last = canvas.corridor(column.top, column.bottom)
    return {
        "heading_x": _num(heading_x),
        "heading_size": _num(
            _fitted(
                _HEADING,
                size=column.heading_size,
                weight=_HEADING_WEIGHT,
                available=min(heading_last, east) - column.gap - heading_x,
            )
        ),
        "column_x": _num(column_x),
        "column_size": _num(
            _at_most(
                size=column.size,
                ems=max(_ems(line) for line in lines),
                available=min(column_last, east) - column.gap - column_x,
            )
        ),
    }


#: The heading both columns carry. Product prose, in English, like
#: "REGISTER HERE" below it -- not an instance's words, and so not
#: something a declaration could supply. Named because it is measured.
_HEADING: Final = "WHAT TO EXPECT?"

#: The line the square sets under its series name, and the one the flyer
#: sets under its tagline. Both name the forum, which is a declared value,
#: which is why the second is composed rather than typed into the markup.
_ANNOUNCEMENT_INVITATION: Final = "Join the discussion before and after the talk at"

#: What the flyer's foot band says. The first line is product prose; the
#: second names the forum.
_FLYER_FOOT_TOP: Final = "Free \u00b7 online \u00b7 everyone welcome"


#: One line of the column, as the runs it is actually set in: a line that
#: opens with a bold label and continues in the body weight is two runs,
#: and charging the whole of it at either weight would be measuring a line
#: this file does not set.
_Line = tuple[tuple[str, int], ...]


def _ems(line: _Line) -> float:
    """How wide one line is, in ems of the size it will be set at."""
    return sum(typeface.width(text, size=1.0, weight=weight) for text, weight in line)


def _column_lines(forum_host: str) -> tuple[_Line, ...]:
    """Every line the "what to expect" column sets, longest one included.

    Written out here rather than parsed back out of the markup: the size
    the column is set at is decided by whichever of these needs the most
    room, and the one that does is the one naming the forum, whose length
    is the instance's. `tests/publication/test_brand.py` holds this list
    and the markup to each other.
    """
    return (
        (("BEFORE: ", _HEADING_WEIGHT), ("Ask your", _BODY_WEIGHT)),
        (("questions to the speaker", _BODY_WEIGHT),),
        ((f"at {forum_host}", _BODY_WEIGHT),),
        (("D-DAY: ", _HEADING_WEIGHT), ("Presentation", _BODY_WEIGHT)),
        (("followed by a discussion", _BODY_WEIGHT),),
        (("with the audience", _BODY_WEIGHT),),
        (("AFTER: ", _HEADING_WEIGHT), ("Continue the", _BODY_WEIGHT)),
        (("discussion and connect", _BODY_WEIGHT),),
        (("with peers", _BODY_WEIGHT),),
    )


# --------------------------------------------------------------------------
# The square announcement
# --------------------------------------------------------------------------

#: The page's own vertical axis, its own inset from the right edge, and the
#: gutter the registration block keeps from whatever edge it ends up
#: against. All three are the composition's, not the drawing's.
_ANNOUNCEMENT_AXIS: Final = 600.0
_ANNOUNCEMENT_INSET: Final = 80.0
_ANNOUNCEMENT_GUTTER: Final = 24.0

_ANNOUNCEMENT_FRAME: Final = _Frame(
    x=700.0,
    y=690.0,
    width=420.0,
    height=470.0,
    tilt=4.0,
    pivot=(900.0, 900.0),
    photo_inset=22.0,
    caption_offset=210.0,
    end_offset=398.0,
)

_ANNOUNCEMENT_COLUMN: Final = _Column(
    heading_indent=240.0,
    heading_baseline=730.0,
    heading_size=34.0,
    indent=320.0,
    top=770.0,
    bottom=1175.0,
    size=27.0,
    gap=24.0,
)

#: The registration block: the two label baselines, the size they are set
#: at, the slot's own top edge and design side, how far the dashed
#: placeholder sits inside it, and where its caption is set. The slot is
#: the one block on this page that stands on the far side of the drawing,
#: so it is the one that reads `free_spans` rather than a corridor.
_ANNOUNCEMENT_REGISTER_TOP: Final = 870.0
_ANNOUNCEMENT_REGISTER_SIZE: Final = 32.0
_ANNOUNCEMENT_SLOT_TOP: Final = 960.0
_ANNOUNCEMENT_SLOT_SIDE: Final = 180.0
_ANNOUNCEMENT_SLOT_DASH: Final = 0.1
_ANNOUNCEMENT_SLOT_LABEL_SIZE: Final = 22.0

#: The smallest slot this page will draw. Below it the placeholder stops
#: being something a volunteer can drop a code into, and a build that
#: quietly drew a stamp-sized one would be shipping a poster nobody can
#: register from -- so it stops instead and says which family left no room.
_ANNOUNCEMENT_SLOT_FLOOR: Final = 120.0


def _register_values(canvas: _Canvas) -> dict[str, str]:
    """The registration slot, in whatever ground the drawing leaves it.

    It takes the free strip nearest the left edge over its own rows --
    which for a drawing that runs down the middle of this page's lower
    left is the notch between the stroke and the edge, and for one that is
    nowhere near is the whole page. Either way the slot keeps the page's
    own gutter from the strip's own left edge and is as wide as the strip
    allows, up to its design size.
    """
    bottom = _ANNOUNCEMENT_SLOT_TOP + _ANNOUNCEMENT_SLOT_SIDE
    strip = canvas.free(_ANNOUNCEMENT_REGISTER_TOP, bottom)[0]
    slot_x = strip[0] + _ANNOUNCEMENT_GUTTER
    side = min(_ANNOUNCEMENT_SLOT_SIDE, strip[1] - slot_x)
    if side < _ANNOUNCEMENT_SLOT_FLOOR:
        raise ValueError(
            f"the {canvas.family!r} motif leaves {_num(max(side, 0.0))} units "
            f"for the announcement's registration slot between rows "
            f"{_num(_ANNOUNCEMENT_REGISTER_TOP)} and {_num(bottom)}, and a "
            f"slot under {_num(_ANNOUNCEMENT_SLOT_FLOOR)} is not a "
            "placeholder anybody can drop a code into"
        )
    dash = _ANNOUNCEMENT_SLOT_DASH * side
    return {
        "slot_x": _num(slot_x),
        "slot_side": _num(side),
        "slot_mid_x": _num(slot_x + side / 2),
        "slot_dash_x": _num(slot_x + dash),
        "slot_dash_y": _num(_ANNOUNCEMENT_SLOT_TOP + dash),
        "slot_dash_side": _num(side - 2 * dash),
        "register_size": _num(
            _fitted(
                "REGISTER",
                size=_ANNOUNCEMENT_REGISTER_SIZE,
                weight=_HEADING_WEIGHT,
                available=strip[1] - slot_x,
            )
        ),
        "slot_label_size": _num(
            _fitted(
                "QR code",
                size=_ANNOUNCEMENT_SLOT_LABEL_SIZE,
                weight=_BODY_WEIGHT,
                available=side,
            )
        ),
    }


def render_announcement_template(root: Path) -> str:
    """`docs/handbook/assets/announcement-template.svg` in full."""
    values = _values(root)
    width, height = formats.SQUARE.width, formats.SQUARE.height
    canvas = _Canvas(
        values["motif_family"], width, height, float(values["motif_ratio"])
    )
    axis = _ANNOUNCEMENT_AXIS
    frame_west = _frame_west(canvas, _ANNOUNCEMENT_FRAME, inset=_ANNOUNCEMENT_INSET)
    return _ANNOUNCEMENT.format(
        **values,
        **_wordmark_values(
            canvas, _ANNOUNCEMENT_WORDMARK, values, inset=_ANNOUNCEMENT_INSET
        ),
        **_frame_values(canvas, _ANNOUNCEMENT_FRAME, inset=_ANNOUNCEMENT_INSET),
        **_column_values(
            canvas,
            _ANNOUNCEMENT_COLUMN,
            east=frame_west,
            lines=_column_lines(values["forum_host"]),
        ),
        **_register_values(canvas),
        w=_num(width),
        h=_num(height),
        axis=_num(axis),
        generated_note=_GENERATED_NOTE,
        stroke_weight=_stroke_weight(width, height, float(values["motif_ratio"])),
        motif=_motif_path(values["motif_family"], width, height),
        invitation=_ANNOUNCEMENT_INVITATION,
        series_size=_num(
            _centred(
                canvas,
                values["series_caps"],
                axis=axis,
                baseline=272.0,
                size=50.0,
                weight=_DISPLAY_WEIGHT,
                letter_spacing=1.0,
            )
        ),
        invitation_size=_num(
            _centred(
                canvas,
                _ANNOUNCEMENT_INVITATION,
                axis=axis,
                baseline=330.0,
                size=31.0,
                weight=_BODY_WEIGHT,
            )
        ),
        address_size=_num(
            _centred(
                canvas,
                values["forum_host"],
                axis=axis,
                baseline=372.0,
                size=31.0,
                weight=_STRONG_WEIGHT,
            )
        ),
        title_size=_num(
            _centred(
                canvas,
                values["speaker_title"],
                axis=axis,
                baseline=458.0,
                size=44.0,
                weight=_STRONG_WEIGHT,
            )
        ),
        date_size=_num(
            _centred(
                canvas,
                f"{values['speaker_date']} at {values['speaker_time']} (CET)",
                axis=axis,
                baseline=600.0,
                size=40.0,
                weight=_STRONG_WEIGHT,
            )
        ),
    )


# --------------------------------------------------------------------------
# The A4 flyer
# --------------------------------------------------------------------------

_FLYER_AXIS: Final = 1050.0
_FLYER_INSET: Final = 150.0

#: The foot band's own axis, which is not the page's: the band is read as
#: a line under the registration slot beside it rather than as part of the
#: centred stack above, and it sits east of the page's middle for that
#: reason. A design decision, and one no family moves.
_FLYER_FOOT_AXIS: Final = 1180.0

_FLYER_FRAME: Final = _Frame(
    x=1250.0,
    y=1440.0,
    width=700.0,
    height=810.0,
    tilt=4.0,
    pivot=(1520.0, 1900.0),
    photo_inset=38.0,
    caption_offset=350.0,
    end_offset=662.0,
)

_FLYER_COLUMN: Final = _Column(
    heading_indent=480.0,
    heading_baseline=1470.0,
    heading_size=62.0,
    indent=560.0,
    top=1540.0,
    bottom=2240.0,
    size=50.0,
    gap=40.0,
)

#: The flyer's own registration block. Unlike the square's it stands
#: inside the same corridor as the words above it -- on a page this tall
#: no drawing this product has comes near that corner -- so it is placed
#: like any other left-set block, from its own design indent.
_FLYER_SLOT_INDENT: Final = 600.0
_FLYER_SLOT_TOP: Final = 2400.0
_FLYER_SLOT_LABEL_BASELINE: Final = 2360.0
_FLYER_SLOT_WIDTH: Final = 360.0
_FLYER_SLOT_HEIGHT: Final = 340.0
_FLYER_SLOT_DASH: Final = 30.0
_FLYER_REGISTER_SIZE: Final = 56.0
_FLYER_SLOT_LABEL_SIZE: Final = 40.0


def render_flyer_template(root: Path) -> str:
    """`docs/handbook/assets/flyer-template.svg` in full."""
    values = _values(root)
    paper_w, paper_h = formats.PRINT_PAPER_MM
    width, height = paper_w * UNITS_PER_MM, paper_h * UNITS_PER_MM
    canvas = _Canvas(
        values["motif_family"], width, height, float(values["motif_ratio"])
    )
    axis = _FLYER_AXIS
    frame_west = _frame_west(canvas, _FLYER_FRAME, inset=_FLYER_INSET)
    invitation = f"Join the discussion at {values['forum_host']}"
    foot_bottom = f"Register at {values['forum_host']}"
    slot_x = _starts_at(
        canvas,
        indent=_FLYER_SLOT_INDENT,
        top=_FLYER_SLOT_LABEL_BASELINE - _INK_ABOVE_BASELINE_EM * _FLYER_REGISTER_SIZE,
        bottom=_FLYER_SLOT_TOP + _FLYER_SLOT_HEIGHT,
    )
    return _FLYER.format(
        **values,
        **_wordmark_values(canvas, _FLYER_WORDMARK, values, inset=_FLYER_INSET),
        **_frame_values(canvas, _FLYER_FRAME, inset=_FLYER_INSET),
        **_column_values(
            canvas,
            _FLYER_COLUMN,
            east=frame_west,
            lines=_column_lines(values["forum_host"]),
        ),
        w=_num(width),
        h=_num(height),
        paper_w=_num(paper_w),
        paper_h=_num(paper_h),
        axis=_num(axis),
        generated_note=_GENERATED_NOTE,
        stroke_weight=_stroke_weight(width, height, float(values["motif_ratio"])),
        motif=_motif_path(values["motif_family"], width, height),
        invitation=invitation,
        series_size=_num(
            _centred(
                canvas,
                values["series_caps"],
                axis=axis,
                baseline=430.0,
                size=86.0,
                weight=_DISPLAY_WEIGHT,
                letter_spacing=2.0,
            )
        ),
        tagline_size=_num(
            _centred(
                canvas,
                values["tagline"],
                axis=axis,
                baseline=530.0,
                size=50.0,
                weight=_BODY_WEIGHT,
            )
        ),
        invitation_size=_num(
            _centred(
                canvas,
                invitation,
                axis=axis,
                baseline=600.0,
                size=50.0,
                weight=_STRONG_WEIGHT,
            )
        ),
        title_size=_num(
            _centred(
                canvas,
                values["speaker_title"],
                axis=axis,
                baseline=840.0,
                size=80.0,
                weight=_STRONG_WEIGHT,
            )
        ),
        date_size=_num(
            _centred(
                canvas,
                f"{values['speaker_date']} at {values['speaker_time']} (CET)",
                axis=axis,
                baseline=1290.0,
                size=72.0,
                weight=_STRONG_WEIGHT,
            )
        ),
        edition_size=_num(
            _centred(
                canvas,
                values["speaker_edition_code"],
                axis=axis,
                baseline=2812.0,
                size=40.0,
                weight=_STRONG_WEIGHT,
            )
        ),
        slot_x=_num(slot_x),
        slot_w=_num(_FLYER_SLOT_WIDTH),
        slot_mid_x=_num(slot_x + _FLYER_SLOT_WIDTH / 2),
        slot_dash_x=_num(slot_x + _FLYER_SLOT_DASH),
        slot_dash_w=_num(_FLYER_SLOT_WIDTH - 2 * _FLYER_SLOT_DASH),
        register_size=_num(
            _fitted(
                "REGISTER HERE",
                size=_FLYER_REGISTER_SIZE,
                weight=_HEADING_WEIGHT,
                available=_ends_at(
                    canvas,
                    inset=_FLYER_INSET,
                    top=_FLYER_SLOT_LABEL_BASELINE
                    - _INK_ABOVE_BASELINE_EM * _FLYER_REGISTER_SIZE,
                    bottom=_FLYER_SLOT_LABEL_BASELINE
                    + _INK_BELOW_BASELINE_EM * _FLYER_REGISTER_SIZE,
                )
                - slot_x,
            )
        ),
        slot_label_size=_num(
            _fitted(
                "QR code",
                size=_FLYER_SLOT_LABEL_SIZE,
                weight=_BODY_WEIGHT,
                available=_FLYER_SLOT_WIDTH,
            )
        ),
        foot_axis=_num(_FLYER_FOOT_AXIS),
        foot_top=_FLYER_FOOT_TOP,
        foot_bottom=foot_bottom,
        foot_size=_num(
            min(
                _centred(
                    canvas,
                    _FLYER_FOOT_TOP,
                    axis=_FLYER_FOOT_AXIS,
                    baseline=2872.0,
                    size=46.0,
                    weight=_BODY_WEIGHT,
                ),
                _centred(
                    canvas,
                    foot_bottom,
                    axis=_FLYER_FOOT_AXIS,
                    baseline=2928.0,
                    size=46.0,
                    weight=_BODY_WEIGHT,
                ),
            )
        ),
    )


# --------------------------------------------------------------------------
# The video-call background
# --------------------------------------------------------------------------

#: The canvas. 1920x1080 is the size every video-call application scales
#: its virtual background to, and the size the hand-drawn file this
#: replaces was drawn at -- the designer's own vector original
#: (`host-background_initial.pdf`, gitignored local reference material) is
#: the same composition exported at 1440x810, the same 16:9 frame.
BACKGROUND_WIDTH: Final = 1920.0
BACKGROUND_HEIGHT: Final = 1080.0

#: The plate's own vertical geometry, in canvas units, read straight off
#: the original at this size: it runs from 24 to 376, drawn with a 3-unit
#: rule. Horizontal geometry is deliberately *not* here, because it is not
#: a measurement worth keeping -- `motifs.safe_margins` derives it, and
#: what it derives for this canvas (277.56) lands within half a unit of
#: where the designer put the plate's own left edge, which is the check on
#: both.
_PLATE_TOP: Final = 24.0
_PLATE_BOTTOM: Final = 376.0
_PLATE_RULE: Final = 3.0
_PLATE_PADDING: Final = 28.0

#: Each line's baseline, the capital height it is set at and the weight it
#: is set in, the first two measured off the original: the name at 76 units
#: of cap height, the strapline at 45, the address at 25. The weight is
#: here because `typeface.width` is charged per weight and the markup below
#: sets one on each of the three -- a number typed in two places is a
#: number that can drift.
_PLATE_LINES: Final = (
    (152.0, 76.0, 900),
    (241.0, 45.0, 800),
    (311.0, 25.0, 700),
)

#: Cap height as a fraction of the font size, for the heavy grotesques
#: this charter names and for every fallback in `_FALLBACK`. Used one way
#: only -- to turn a measured capital height back into the `font-size` that
#: produces it.
_CAP_HEIGHT_EM: Final = 0.72

#: The code's own box and where it sits: 202 units square, 86 in from the
#: right edge and 24 up from the bottom, all measured off the original. Its
#: label sits above it, the two baselines 53 and 24 units above the box.
#: Nothing here is derived from the ribbon, and that is not an omission:
#: the ribbon's right-hand curl leaves this canvas at 0.475 of its
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


def _fitted_font_size(
    text: str, *, cap_height: float, weight: int, available: float
) -> float:
    """A font size that sets `text` at `cap_height` unless it would then
    run wider than `available`, in which case as large as fits.

    A pure function of the string, deliberately:
    `visual._scaled_font_size`'s own argument applies unchanged -- the same
    declaration asks for the same size on any machine, before a glyph is
    drawn, where a browser measurement could differ between two builds
    that agree on every design decision.

    What it is a function *of* is what changed. It used to be the string's
    own length times one average advance, and that average was measured on
    two lines and wrong for the rest: it under-charged this plate's own
    name line by 22 units on one of the two charters this repository ships,
    which is 22 units of the padding the design asked for, spent without
    anything saying so. `typeface.width` charges each character what the
    face actually gives it, at the weight the line is set in.
    """
    by_height = cap_height / _CAP_HEIGHT_EM
    if not text:
        return by_height
    return _fitted(text, size=by_height, weight=weight, available=available)


_BACKGROUND: Final = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"
     viewBox="0 0 {w} {h}" font-family="{font_family}">
  <title>{series_title} — video-call background</title>
  <desc>Video-call background, {w}x{h}. Unlike the other two files in this
  kit it holds nothing an event changes, so there is nothing to fill in:
  export it to PNG or JPEG and add it as a virtual background in whatever
  the session runs on.</desc>

{generated_note}
  <rect width="{w}" height="{h}" fill="{field}"/>

  <!-- The motif: the drawing the charter names, in the charter's own
       motif colour and at its own weight. The plate below sits inside the
       corridor the drawing leaves free, so no word is ever drawn across
       it. -->
  <g id="motif" fill="none" stroke="{motif_stroke}"
     stroke-width="{stroke_weight}"
     stroke-linecap="round" stroke-linejoin="round">
    <path d="{motif}"/>
  </g>

  <!-- The plate: who this is, what the series is for, and where to find
       it. All three lines are declared values set in capitals, and each is
       sized to fit this plate rather than at a fixed size, so a longer
       name shrinks instead of running off the edge. -->
  <rect class="{block}" x="{plate_x}" y="{plate_y}" width="{plate_w}"
        height="{plate_h}"
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
  <rect class="{block}" x="{code_x}" y="{code_y}" width="{code_side}"
        height="{code_side}"
        fill="{white}"/>
  <svg x="{code_x}" y="{code_y}" width="{code_side}"
       height="{code_side}">{code}</svg>
</svg>
"""


def render_video_call_background(root: Path) -> str:
    """`docs/handbook/assets/video-call-background.svg` in full."""
    values = _values(root)
    width, height = BACKGROUND_WIDTH, BACKGROUND_HEIGHT
    ratio = float(values["motif_ratio"])
    left, right = motifs.safe_margins(
        values["motif_family"], width, height, ratio=ratio
    )

    plate_x = left + _PLATE_RULE / 2
    plate_w = (width - right - _PLATE_RULE / 2) - plate_x
    available = plate_w - 2 * _PLATE_PADDING
    lines = (
        values["organisation_caps"],
        values["strapline_caps"],
        values["address_caps"],
    )
    sizes = [
        _fitted_font_size(text, cap_height=cap, weight=weight, available=available)
        for text, (_baseline, cap, weight) in zip(lines, _PLATE_LINES, strict=True)
    ]

    code_x = width - _CODE_RIGHT_GAP - _CODE_SIDE
    code_y = height - _CODE_BOTTOM_GAP - _CODE_SIDE

    return _BACKGROUND.format(
        **values,
        w=_num(width),
        h=_num(height),
        generated_note=_GENERATED_NOTE,
        stroke_weight=_stroke_weight(width, height, ratio),
        motif=_motif_path(values["motif_family"], width, height),
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
        label_size=_num(
            _fitted_font_size(
                max(_CODE_LABEL, key=len),
                cap_height=_CODE_LABEL_CAP,
                weight=_HEADING_WEIGHT,
                available=_CODE_SIDE,
            )
        ),
        label_top_y=_num(code_y - _CODE_LABEL_BASELINES[0]),
        label_bottom_y=_num(code_y - _CODE_LABEL_BASELINES[1]),
        label_top=_CODE_LABEL[0],
        label_bottom=_CODE_LABEL[1],
        code=registration_code.forum_code_svg(dark=values["black"], root=root),
    )
