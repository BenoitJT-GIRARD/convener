"""The two templates a collaborator downloads, derived rather than drawn.

`docs/assets/announcement-template.svg` and `flyer-template.svg` are the
files `docs/toolkit/visual-kit.md` links to: a volunteer downloads one,
opens it in Inkscape or a text editor, fills in the event and exports an
image. They were drawn by hand, and they had drifted -- entry 1 of
`docs/superpowers/deferred-work.md` measured it on 2026-08-24. They carried
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

Why the mark is what makes this refuse
----------------------------------------
Both files draw the wordmark and the decorative loops, and both take their
colour and their stroke weight from `motif` -- the one section of the
charter with no product default (`brand.py`). That is deliberate placement
rather than a coincidence of layout: these are the files that leave the
repository, so they are exactly where another organisation's mark would
leak. A duplicate that has configured no `motif` cannot build them at all,
and is told what is missing and where to put it.

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

What is still drawn by hand, and why
--------------------------------------
The loops are still the four bare circles and arcs the original file had,
now at the charter's own stroke weight and colour.
`data/brand.json::motif._ribbon` is right that they are not the ribbon --
one continuous meandering stroke is, and `ribbon.py` draws it for the
generated posters (`visual.py`). Putting the real ribbon *here* is not a
colour change: `visual._ribbon_safe_margins` derives a corridor of 25.7 and
19.6 units per hundred of the canvas, so on a 1200-unit square the stroke
owns the left 308 and the right 235, and both these layouts put type,
photograph and QR slot inside it. Using it means re-laying-out two posters,
which is a poster's task and not the charter's.
"""

from __future__ import annotations

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
    so that "no motif" is one message however many files are being
    written.
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

    <!-- Decorative loops, bled off three edges. Their colour and their
         stroke weight are the charter's own motif, so neither can drift
         from it. Each one is placed clear of every word on the page: the
         weight the charter measures is nearly twice what these were drawn
         at, and a heavy stroke behind dark type is unreadable type. Move
         or delete them freely; they carry no text. -->
    <g fill="none" stroke="{ribbon_stroke}" stroke-width="{loop_stroke}">
      <circle cx="1165" cy="55" r="95"/>
      <path d="M120 40 C 20 130, 20 250, 120 330 C 220 410, 220 530, 120 610"/>
      <circle cx="70" cy="700" r="120"/>
    </g>

    <!-- Wordmark. The mark is three squares and a link, drawn rather than
         embedded: an SVG that references an external logo file is an SVG
         that travels broken. -->
    <g transform="translate(168 52)">
      <rect x="0" y="6" width="26" height="26" fill="{logo_dots}"/>
      <rect x="34" y="0" width="26" height="26" fill="{logo_dots}"/>
      <rect x="6" y="42" width="26" height="26" fill="{logo_dots}"/>
      <rect x="44" y="36" width="26" height="26" fill="{logo_dots}"/>
      <path d="M18 18 C 46 12, 62 26, 58 48" fill="none"
            stroke="{ribbon_stroke}" stroke-width="5"/>
      <circle cx="16" cy="20" r="7" fill="none"
              stroke="{ribbon_stroke}" stroke-width="5"/>
      <circle cx="58" cy="46" r="7" fill="none"
              stroke="{ribbon_stroke}" stroke-width="5"/>
    </g>
    <text x="268" y="112" font-size="58" font-weight="500"
          fill="{purple}">{forum_host}</text>
    <rect x="268" y="130" width="690" height="4" fill="{purple}"/>

    <text x="600" y="262" text-anchor="middle" font-size="66"
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
    <text font-size="29" fill="{black}">
      <tspan x="280" y="796" font-weight="800"
             fill="{purple}">BEFORE: </tspan><tspan>Ask your</tspan>
      <tspan x="280" y="832">questions to the speaker</tspan>
      <tspan x="280" y="868">at {forum_host}</tspan>
      <tspan x="280" y="944" font-weight="800"
             fill="{purple}">D-DAY: </tspan><tspan>Presentation</tspan>
      <tspan x="280" y="980">followed by a discussion</tspan>
      <tspan x="280" y="1016">with the audience</tspan>
      <tspan x="280" y="1092" font-weight="800"
             fill="{purple}">AFTER: </tspan><tspan>Continue the</tspan>
      <tspan x="280" y="1128">discussion and connect</tspan>
      <tspan x="280" y="1164">with peers</tspan>
    </text>

    <!-- REGISTRATION QR. Generate it from the registration link with any
         offline generator, or in the app; then drop it over this square. -->
    <text x="40" y="928" font-size="32" font-weight="800"
          fill="{black}">REGISTER</text>
    <text x="40" y="966" font-size="32" font-weight="800"
          fill="{black}">HERE</text>
    <rect x="40" y="990" width="200" height="200" fill="{white}"/>
    <rect x="60" y="1010" width="160" height="160" fill="none"
          stroke="{rule_strong}" stroke-width="3" stroke-dasharray="10 8"/>
    <text x="140" y="1098" text-anchor="middle" font-size="22"
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

    <!-- Decorative loops, bled off the edges, in the charter's own motif
         colour and at its own stroke weight, each placed clear of every
         word on the page. They carry no text: move or delete them. -->
    <g fill="none" stroke="{ribbon_stroke}" stroke-width="{loop_stroke}">
      <path d="M210 300 C 60 420, 60 640, 210 760 C 360 880, 360 1100, 210 1220"/>
      <circle cx="2060" cy="470" r="180"/>
      <circle cx="60" cy="2500" r="170"/>
    </g>

    <!-- Wordmark: three squares and a link, drawn rather than embedded. -->
    <g transform="translate(250 92)">
      <rect x="0" y="10" width="44" height="44" fill="{logo_dots}"/>
      <rect x="58" y="0" width="44" height="44" fill="{logo_dots}"/>
      <rect x="10" y="72" width="44" height="44" fill="{logo_dots}"/>
      <rect x="76" y="62" width="44" height="44" fill="{logo_dots}"/>
      <path d="M30 30 C 78 20, 106 44, 100 82" fill="none"
            stroke="{ribbon_stroke}" stroke-width="9"/>
      <circle cx="27" cy="33" r="12" fill="none"
              stroke="{ribbon_stroke}" stroke-width="9"/>
      <circle cx="100" cy="80" r="12" fill="none"
              stroke="{ribbon_stroke}" stroke-width="9"/>
    </g>
    <text x="420" y="196" font-size="98" font-weight="500"
          fill="{purple}">{forum_host}</text>
    <rect x="420" y="228" width="1180" height="7" fill="{purple}"/>

    <text x="1050" y="430" text-anchor="middle" font-size="106"
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
    <text x="1050" y="1290" text-anchor="middle" font-size="76"
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
    <text x="1050" y="2900" text-anchor="middle" font-size="40"
          font-weight="700" fill="{purple}">{speaker_edition_code}</text>
  </g>

  <g id="fixed-what-to-expect">
    <text x="230" y="1470" font-size="62" font-weight="800"
          fill="{black}">WHAT TO EXPECT?</text>
    <text font-size="50" fill="{black}">
      <tspan x="300" y="1590" font-weight="800"
             fill="{purple}">BEFORE: </tspan><tspan>Ask your</tspan>
      <tspan x="300" y="1652">questions to the speaker</tspan>
      <tspan x="300" y="1714">at {forum_host}</tspan>
      <tspan x="300" y="1846" font-weight="800"
             fill="{purple}">D-DAY: </tspan><tspan>Presentation</tspan>
      <tspan x="300" y="1908">followed by a discussion</tspan>
      <tspan x="300" y="1970">with the audience</tspan>
      <tspan x="300" y="2102" font-weight="800"
             fill="{purple}">AFTER: </tspan><tspan>Continue the</tspan>
      <tspan x="300" y="2164">discussion and connect</tspan>
      <tspan x="300" y="2226">with peers</tspan>
    </text>

    <!-- REGISTRATION QR. Generate it from the registration link with any
         offline generator, then drop it over this square. -->
    <text x="300" y="2360" font-size="56" font-weight="800"
          fill="{black}">REGISTER HERE</text>
    <rect x="300" y="2400" width="360" height="340" fill="{white}"/>
    <rect x="330" y="2430" width="300" height="280" fill="none"
          stroke="{rule_strong}" stroke-width="5" stroke-dasharray="18 14"/>
    <text x="480" y="2595" text-anchor="middle" font-size="40"
          fill="{ink_muted}">QR code</text>
    <text x="1050" y="2830" text-anchor="middle" font-size="46"
          fill="{black}">Free · online · everyone welcome — register
      at {forum_host}</text>
  </g>
</svg>
"""


def _loop_stroke(width: float, height: float, ratio: float) -> str:
    """The decorative loops' stroke weight, from the charter's own ratio.

    `ribbon.ribbon_stroke_width` and not a literal: the weight the loops
    were drawn at (17 units on a 1200 square, 0.014 of the shorter side)
    was nobody's measurement, and `motif._ribbon_width_ratio` records one
    taken against the reference poster.
    """
    return _num(ribbon.ribbon_stroke_width(width, height, ratio=ratio))


def render_announcement_template(root: Path) -> str:
    """`docs/assets/announcement-template.svg` in full."""
    values = _values(root)
    width, height = formats.SQUARE.width, formats.SQUARE.height
    return _ANNOUNCEMENT.format(
        **values,
        w=_num(width),
        h=_num(height),
        generated_note=_GENERATED_NOTE,
        loop_stroke=_loop_stroke(width, height, float(values["ribbon_ratio"])),
    )


def render_flyer_template(root: Path) -> str:
    """`docs/assets/flyer-template.svg` in full."""
    values = _values(root)
    paper_w, paper_h = formats.PRINT_PAPER_MM
    width, height = paper_w * _UNITS_PER_MM, paper_h * _UNITS_PER_MM
    return _FLYER.format(
        **values,
        w=_num(width),
        h=_num(height),
        paper_w=_num(paper_w),
        paper_h=_num(paper_h),
        generated_note=_GENERATED_NOTE,
        loop_stroke=_loop_stroke(width, height, float(values["ribbon_ratio"])),
    )
