"""The announcement composition: a page, not a hand-drawn SVG (P-3).

`docs/assets/example_and_template_initial_assets/announcement-template_initial.png`
(gitignored -- entry 9 of `docs/superpowers/deferred-work.md`) is Anonymous's own
template. Reading it pixel by pixel, top to bottom: a cream band carrying the
wordmark; the series title in heavy purple caps on turquoise; a two-line
invitation to the discussion; a second cream band carrying the talk's own
title; a purple date line; a "WHAT TO EXPECT?" block; a white, tilted
photographic frame with the speaker's name along its lower edge; a
"REGISTER HERE" label over a QR code; and task 1's ribbon running over
everything, off every edge.

Why a page rather than an SVG template with placeholders
----------------------------------------------------------
An SVG template can hold a blank for a short string. It cannot *compose* a
title nobody has written yet, because SVG text does not wrap or reflow --
every one of this project's inherited `*_test_dev.svg` gabarits would clip
a title longer than whatever the person who drew it happened to type. HTML
and CSS, rendered to an image, get wrapping, `flex`, and text metrics for
free: the two-line invitation and the "WHAT TO EXPECT?" block are static,
but the talk's own title is not, and D-08 names the overflowing hand-made
poster as a real, lived failure -- see `render_announcement`'s own
docstring for how this module answers it (Python-computed font size, not a
browser-side "shrink to fit" script).

Where the identity comes from, and where it does not
--------------------------------------------------------
Every colour below is read out of `data/brand.json` by this module's own
`_load_colours`, never imported from `scripts/generate_brand_css.py`:
`convener_ops` ships as an installed package (`tools/pyproject.toml`'s own
`[tool.hatch.build.targets.wheel]` lists only this one package), and
`scripts/` sits outside it -- exactly the boundary `ribbon.py`'s own
`_load_motif` already respects (`ribbon.py`'s module docstring: "threaded
in from `repo_root()` at the call site rather than resolved here"). So
this reads the one shared source of fact directly, the same file the
site's and the app's own generators read, rather than importing either
generator across a boundary this project does not build tooling to cross.
The variable names below are deliberately the ones
`generate_brand_css.render_site_root_block` already writes into
`site/src/style.css` (`--purple`, `--surface`, `--turquoise-d`, ...) so
that a reader who knows the showcase's own tokens recognises this page's
CSS on sight -- not because the two are the same generated file (they are
not: two independent readers of one JSON source, which is what D-16 asks
for), but because a third name for the same colour would be one more thing
to keep in step by hand.

The ribbon itself is never redrawn here. `ribbon_path`, `ribbon_stroke_colour`
and `ribbon_stroke_width` (task 1's own module) are called with this
composition's exact canvas size and painted as the last element in the
document, so it always sits on top -- exactly what the reference shows:
the purple stroke crosses over the lower "WHAT TO EXPECT?" text near the
left edge in Anonymous's own poster, not behind it.

The variable parts, and how each is handled
------------------------------------------------
- **Title** -- `render_announcement`'s own `title` parameter. Wrapped, not
  truncated, sized in `vw` (of the canvas *width*, the axis it must not
  overflow) by `_scaled_font_size` (a pure function of its character
  count, computed here in Python rather than measured by a script in the
  rendered page -- see that function's own docstring for why
  a *measured* fit would undermine task 5's own pinned image comparison).
- **Date** -- `talk_date`, a real `datetime.date`, never a hand-typed
  string. `paris_standing_start` derives the real Europe/Paris UTC offset
  and abbreviation for this project's standing 12:30 local start time on
  that calendar day, exactly the computation this project already made
  once for the vitrine (`site/.eleventy.js::parisStandingStart`) after
  finding the reference poster's own defect: a hard-typed "12h30 (CET)",
  wrong for the three of this project's five fixture editions that fall in
  daylight-saving time. D-14 governs the relationship between the two
  implementations: a shared *fixture* (the same five editions, three of
  them in DST), not shared code -- an Eleventy config cannot import this
  package and this package does not build tooling to import a `.eleventy.js`
  either. `governance.PARIS`, not a second `ZoneInfo("Europe/Paris")`, is
  the one instance this module and the governance rule both anchor to.
- **Portrait** -- `portrait_data_uri`, `None` by default. `None` is not a
  degraded case to work around -- it is what most editions look like until
  a speaker's `photo_url` clears the consent gate (P-4,
  `public_data.PUBLISHABLE_ON_CONSENT`), and `_frame_html` below renders a
  composed placeholder for it, never a hole or a broken `<img>`. This
  module never fetches a URL and never reads `data/speakers.yml` itself --
  `photo_url` is, by the schema's own words, "a link, not an upload: the
  repository holds records, not media"
  (`docs/reference/schema.md`), so turning it into something this function
  can inline (a `data:` URI, most likely) is a job for whatever calls this
  module with real data, not for a pure renderer that this project also
  needs to keep off the network in its own test suite. What *is* this
  module's job, and what its own tests prove: passing the gated public
  projection through (`public_data.to_public`, which already empties
  `photo_url` unless the speaker's consent is granted and the record is
  published) is enough on its own to withhold the portrait -- there is no
  second check to bypass here, because there is nothing here that reads
  the raw record.
- **Speaker name and affiliation** -- `speaker_name`, `speaker_affiliation`,
  set along the tilted frame's own lower border like a caption written
  under a printed photograph, each independently sized by
  `_scaled_font_size`. The reference only ever shows a name here; carrying
  the affiliation onto the same caption, wrapping instead of an ellipsis,
  is this module's own extension for data the original was never asked to
  display (see `render_announcement`'s own docstring for the reasoning).
- **Registration code** -- task 3's. `_registration_slot_html` reserves a
  square footprint of a fixed, sensible size and marks it
  `data-registration-code-slot`, exactly as phase 5's task 5 reserved the
  registration form's own mount point before task 6 filled it.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Final

from .governance import PARIS
from .ribbon import (
    ribbon_path,
    ribbon_stroke_colour,
    ribbon_stroke_width,
    ribbon_width_ratio,
)

__all__ = [
    "Announcement",
    "date_line",
    "paris_standing_start",
    "render_announcement",
]

#: Same convention as `ribbon.BRAND_PATH`: relative to the repository root,
#: threaded in by the caller rather than resolved from this file's own
#: location.
BRAND_PATH: Final = Path("data") / "brand.json"

#: This project's one standing start time, Europe/Paris local. The
#: JavaScript twin of this exact constant is
#: `site/.eleventy.js::STANDING_START_LOCAL`.
STANDING_START_LOCAL: Final = time(12, 30)

#: Fixed English names, not `date.strftime('%A'/'%B')`: `strftime`'s day
#: and month names are locale-dependent, and this project has already found
#: one Python/JavaScript date-formatting mismatch it did not expect (D-20).
#: `tools/tests/test_site.py::_ENGLISH_WEEKDAYS`/`_ENGLISH_MONTHS` make the
#: identical choice for the identical reason -- a rendered page's own
#: wording must not depend on the locale of whatever machine renders it.
_WEEKDAYS: Final = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_MONTHS: Final = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def paris_standing_start(talk_date: date) -> tuple[str, str]:
    """The real Europe/Paris UTC offset and CET/CEST abbreviation for this
    project's standing 12:30 local start time, on `talk_date`.

    Mirrors `site/.eleventy.js::parisStandingStart` and
    `tools/tests/test_site.py::_expected_paris_start` -- three independent
    readings of the one fact the reference poster got wrong by hard-typing
    "(CET)": Europe/Paris observes `+01:00`/CET from late October to late
    March and `+02:00`/CEST the rest of the year, and three of this
    project's own five fixture editions
    (`site/src/_data/events.json`) fall in the second half. Unlike the
    JavaScript side, this needs no `Intl` locale juggling to avoid a
    'GMT+1'-shaped string: `zoneinfo`'s `tzname()` on an aware `datetime`
    reads the IANA database directly and returns exactly 'CET' or 'CEST'
    for this zone, unambiguous at 12:30 because Europe/Paris's own DST
    transitions always happen in the small hours.

    Returns `(offset, abbreviation)`, e.g. `("+01:00", "CET")` or
    `("+02:00", "CEST")`.
    """
    probe = datetime.combine(talk_date, STANDING_START_LOCAL, tzinfo=PARIS)
    offset = probe.utcoffset()
    if offset is None:
        raise ValueError(f"{talk_date} resolved no UTC offset in Europe/Paris")
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    abbreviation = probe.tzname()
    if not abbreviation:
        raise ValueError(
            f"{talk_date} resolved no timezone abbreviation in Europe/Paris"
        )
    return f"{sign}{hours:02d}:{minutes:02d}", abbreviation


def date_line(talk_date: date) -> str:
    """ "Thursday, 12 March 2026 at 12:30 CET" -- the corrected twin of the
    reference poster's own "Thursday, the DATE at 12h30 (CET)".

    Two corrections, both computed rather than assumed: the weekday name
    comes from `talk_date.weekday()`, not a fixed "Thursday" left over from
    whichever edition the original was drawn for, and the zone label comes
    from `paris_standing_start` rather than a hard-typed "(CET)". The
    "12h30 (CET)" spelling is not reproduced either -- this project's own
    vitrine already settled on "12:30 CET"/"12:30 CEST" with no parentheses
    (`site/.eleventy.js::parisStandingStart`'s own `label`), and stating
    the time two different ways on two surfaces of the same announcement
    would be its own small disagreement.
    """
    weekday = _WEEKDAYS[talk_date.weekday()]
    month = _MONTHS[talk_date.month - 1]
    _, abbreviation = paris_standing_start(talk_date)
    hh = STANDING_START_LOCAL.hour
    mm = STANDING_START_LOCAL.minute
    return (
        f"{weekday}, {talk_date.day} {month} {talk_date.year} at "
        f"{hh:02d}:{mm:02d} {abbreviation}"
    )


def _load_colours(root: Path) -> dict[str, str]:
    """Every named colour this composition uses, `colour` and `derived`
    merged -- the same two sections and the same "skip an underscore-led
    commentary key" rule `generate_brand_css._colours` applies, read
    independently rather than imported (see the module docstring)."""
    brand: dict[str, Any] = json.loads((root / BRAND_PATH).read_text(encoding="utf-8"))
    merged: dict[str, str] = {}
    for section in ("colour", "derived"):
        for key, value in brand[section].items():
            if not key.startswith("_"):
                merged[key] = str(value)
    return merged


#: The generated block's own variable names
#: (`generate_brand_css.render_site_root_block`), reused here so a reader
#: who knows the showcase's tokens recognises this page's CSS on sight --
#: see the module docstring for why this is a second reader of
#: `data/brand.json`, not an import of the generator.
def _root_css_block(colours: dict[str, str]) -> str:
    return f"""\
  --paper:        {colours["white"]};
  --surface:      {colours["cream"]};
  --surface-2:    {colours["turquoise"]};
  --ink:          {colours["ink"]};
  --ink-mute:     {colours["ink_muted"]};
  --ink-faint:    {colours["ink_faint"]};
  --turquoise:    {colours["turquoise"]};
  --turquoise-d:  {colours["turquoise_text"]};
  --turquoise-l:  {colours["turquoise_tint"]};
  --purple:       {colours["purple"]};
  --purple-d:     {colours["purple_hover"]};
  --purple-l:     {colours["purple_tint"]};
  --rule:         {colours["rule"]};
  --rule-strong:  {colours["rule_strong"]};
  --white:        {colours["white"]};
  --black:        {colours["black"]};
"""


#: Hand-typed, and correctly so: file paths and Unicode ranges are not
#: colours `data/brand.json` carries an opinion about, and this project
#: already has two other hand-authored copies of this exact block
#: (`site/src/style.css`, `app/src/design/tokens.css`) -- a third bespoke
#: surface reading the same self-hosted files (D-17) is the established
#: shape, not a new one. Only Latin and Latin Extended are self-hosted
#: (the same two subsets the showcase ships): a non-Latin title or name
#: falls through to this same `font-family` list's own system fallbacks
#: (`-apple-system`, `Segoe UI`, ...), which is a property of the render
#: host's own installed fonts, not of this module -- see
#: `render_announcement`'s own docstring for the non-Latin state this is
#: exercised against.
_FONT_FACE_CSS: Final = """\
  @font-face {
    font-family: 'Archivo';
    font-style: normal;
    font-weight: 100 900;
    font-display: block;
    src: url('fonts/archivo-latin-standard-normal.woff2') format('woff2');
    unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6,
      U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+2074, U+20AC,
      U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
  }
  @font-face {
    font-family: 'Archivo';
    font-style: normal;
    font-weight: 100 900;
    font-display: block;
    src: url('fonts/archivo-latin-ext-standard-normal.woff2') format('woff2');
    unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7,
      U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F,
      U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F,
      U+A720-A7FF;
  }
"""

#: `font-display: block` rather than the showcase's own `swap`: this page
#: is rendered exactly once, to a screenshot, by a renderer that already
#: waits for it to finish loading (task 5's own pinned engine) -- there is
#: no visitor for a swap to matter to, and `block` guarantees the glyphs
#: task 1's ribbon shares a canvas with are never captured mid-swap in a
#: fallback face.

_FONT_STACK: Final = (
    "'Archivo', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
)


# ---------------------------------------------------------------------------
# Text that composes instead of overflowing (D-08's own lived problem)
# ---------------------------------------------------------------------------


def _scaled_font_size(
    text: str, *, max_size: float, min_size: float, soft_limit: int, hard_limit: int
) -> float:
    """A font size, in whatever CSS unit the caller has in mind, that
    shrinks as `text` grows longer.

    Unit-agnostic on purpose: `_title_font_size` below pairs its result
    with `vw` (the talk-title band spans nearly the full canvas width, so
    what must not overflow is *width*), while `_name_font_size` and
    `_affiliation_font_size` pair theirs with `vmin` (the tilted frame
    they sit inside is itself sized in `vmin` -- see `render_announcement`'s
    own CSS -- so text meant to fit inside it has to shrink on the same
    axis the frame does, at any aspect ratio task 4 renders this page at,
    or the two would drift apart on anything but a square canvas).

    Computed here, in Python, rather than measured in the browser by a
    "shrink to fit" script -- deliberately, for two reasons. First, no new
    complexity: a real fit-to-box measurement needs the element's own
    rendered metrics, which means either a layout pass a plain CSS
    property cannot see (`ResizeObserver`, requestAnimationFrame polling)
    or a canvas text-measurement call -- either way, script this page does
    not otherwise need. Second, and more importantly: task 5's own image
    comparison is only a real control if identical input always renders
    identically (P-2's whole argument for pinning the engine at all) -- a
    size that depended on live browser font-metrics could legitimately
    differ by a pixel between two Chromium builds that still agree on
    every design decision, which is exactly the false-positive P-2 exists
    to rule out. A pure function of `len(text)` cannot do that: the same
    title always asks for the same size, on any machine, before a single
    pixel is painted.

    Below `soft_limit` characters, returns `max_size` unchanged: short text
    is not shrunk merely for being non-empty. Above `hard_limit`, floors at
    `min_size` -- a title longer than that is expected to wrap onto more
    lines rather than ask for an ever-smaller, eventually illegible face.
    Between the two, scales linearly.
    """
    length = len(text)
    if length <= soft_limit:
        return max_size
    if length >= hard_limit:
        return min_size
    fraction = (length - soft_limit) / (hard_limit - soft_limit)
    return max_size - fraction * (max_size - min_size)


#: Talk titles: academic and often long by nature (the real fixture
#: already carries one at 123 characters --
#: `site/src/_data/events.json`'s MRG-04). Paired with `vw` (see
#: `_scaled_font_size`'s own docstring): `soft_limit` is chosen above the
#: series' own median title length so an ordinary title is never shrunk at
#: all; `hard_limit` is chosen so a title at the real fixture's own longest
#: still lands comfortably above the floor, leaving headroom below it for
#: whatever a future edition types that is longer still.
_TITLE_FONT_MAX_MRG: Final = 4.6
_TITLE_FONT_MIN_MRG: Final = 2.1
_TITLE_SOFT_LIMIT: Final = 36
_TITLE_HARD_LIMIT: Final = 170

#: Speaker names: shorter-lived than a title, so both limits sit lower.
#: Paired with `vmin` -- the frame they caption is sized in `vmin`.
_NAME_FONT_MAX_VMIN: Final = 2.7
_NAME_FONT_MIN_VMIN: Final = 1.3
_NAME_SOFT_LIMIT: Final = 22
_NAME_HARD_LIMIT: Final = 64

#: Affiliations: routinely longer than a name for the same person (an
#: institute name, a department, a city), so both limits sit higher than
#: the name's own. Paired with `vmin`, for the same reason as the name.
_AFFILIATION_FONT_MAX_VMIN: Final = 1.7
_AFFILIATION_FONT_MIN_VMIN: Final = 0.95
_AFFILIATION_SOFT_LIMIT: Final = 28
_AFFILIATION_HARD_LIMIT: Final = 110


def _title_font_size(title: str) -> float:
    """A size in `vw` -- see `_scaled_font_size`'s own docstring for why
    the title is paired with `vw` where the name and affiliation are
    paired with `vmin`."""
    return _scaled_font_size(
        title,
        max_size=_TITLE_FONT_MAX_MRG,
        min_size=_TITLE_FONT_MIN_MRG,
        soft_limit=_TITLE_SOFT_LIMIT,
        hard_limit=_TITLE_HARD_LIMIT,
    )


def _name_font_size(name: str) -> float:
    """A size in `vmin` -- see `_scaled_font_size`'s own docstring."""
    return _scaled_font_size(
        name,
        max_size=_NAME_FONT_MAX_VMIN,
        min_size=_NAME_FONT_MIN_VMIN,
        soft_limit=_NAME_SOFT_LIMIT,
        hard_limit=_NAME_HARD_LIMIT,
    )


def _affiliation_font_size(affiliation: str) -> float:
    """A size in `vmin` -- see `_scaled_font_size`'s own docstring."""
    return _scaled_font_size(
        affiliation,
        max_size=_AFFILIATION_FONT_MAX_VMIN,
        min_size=_AFFILIATION_FONT_MIN_VMIN,
        soft_limit=_AFFILIATION_SOFT_LIMIT,
        hard_limit=_AFFILIATION_HARD_LIMIT,
    )


def _num(value: float) -> str:
    """A CSS/SVG number, trimmed of a pointless trailing `.0`."""
    return f"{value:g}"


# ---------------------------------------------------------------------------
# The fixed parts: wordmark, series title, invitation, "WHAT TO EXPECT?"
# ---------------------------------------------------------------------------

#: The squares-and-dots device to the wordmark's own left, in the
#: reference poster -- a deliberately simplified reading of it, not a
#: pixel trace the way task 1's ribbon is. Unlike the ribbon, this glyph
#: was never named as the part of the identity that had drifted (D-16
#: names the palette; the brief for this task names the ribbon
#: specifically as "the only part of the identity that was ever in
#: doubt"), so it is redrawn here as a plain evocation -- two turquoise
#: squares on a diagonal, two purple dots joined by a short curved
#: lead -- rather than measured stroke by stroke.
_WORDMARK_LOGO_SVG: Final = """\
<svg class="wordmark-logo" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
  <rect x="1" y="1" width="14" height="14" fill="var(--turquoise)"/>
  <rect x="17" y="17" width="14" height="14" fill="var(--turquoise)"/>
  <path d="M9 15 V22 Q9 26 13 26 H24" fill="none" stroke="var(--purple)"
        stroke-width="2.6" stroke-linecap="round"/>
  <path d="M24 26 V19 Q24 15 28 15 H33" fill="none" stroke="var(--purple)"
        stroke-width="2.6" stroke-linecap="round"/>
  <circle cx="9" cy="26" r="3.6" fill="var(--purple)"/>
  <circle cx="24" cy="26" r="3.6" fill="var(--purple)"/>
  <circle cx="9" cy="26" r="1.2" fill="var(--surface)"/>
  <circle cx="24" cy="26" r="1.2" fill="var(--surface)"/>
</svg>
"""

_WORDMARK_HTML: Final = f"""\
<div class="band band--wordmark">
  {_WORDMARK_LOGO_SVG}
  <p class="wordmark-text">www.<span class="accent">The</span>Behaviour<span
    class="accent2">Forum.org</span></p>
</div>
"""

_SERIES_HTML: Final = """\
<section class="hero">
  <h1>Read together</h1>
  <p>Join the discussion before and after the talk at<br>
  <strong>forum.example.test</strong></p>
</section>
"""

#: Fixed boilerplate (`render_announcement`'s own brief: "Fixed: ... the
#: `WHAT TO EXPECT?` block"). Read against the reference critically before
#: keeping it verbatim, as the task brief asks -- this text carries no
#: edition-specific fact (no date, no name, no hard-typed zone), so nothing
#: about it needed correcting the way the date line did.
_EXPECT_HTML: Final = """\
<div class="expect">
  <h2>What to expect?</h2>
  <p class="expect__row"><strong>Before:</strong> Ask your questions to the
    speaker at forum.example.test</p>
  <p class="expect__row"><strong>D-Day:</strong> Presentation followed by a
    discussion with the audience</p>
  <p class="expect__row"><strong>After:</strong> Continue the discussion and
    connect with peers at forum.example.test</p>
</div>
"""


def _registration_slot_html() -> str:
    """A reserved, correctly-sized square for task 3's registration code --
    the same "reserve the mount point before the next task fills it"
    pattern phase 5's task 5 used for the registration form. `aria-hidden`
    and empty on purpose: there is nothing to announce about a placeholder,
    and a real `<svg>` QR code takes this element's exact place (by class
    and by the `data-registration-code-slot` hook) once task 3 exists."""
    return (
        '<div class="registration-code-slot" data-registration-code-slot'
        ' aria-hidden="true"></div>'
    )


# ---------------------------------------------------------------------------
# The photographic frame: a portrait, or a composed placeholder -- never a
# hole, never a broken <img> (P-4)
# ---------------------------------------------------------------------------


def _frame_photo_html(portrait_data_uri: str | None, speaker_name: str) -> str:
    """The frame's own photo area.

    `portrait_data_uri` is `None` far more often than not -- see the module
    docstring's "Portrait" section for why that is a legitimate, common
    state (P-4) rather than something to work around, and why this
    function never reaches for a network request to fill it in itself. A
    `None` renders a composed placeholder (the speaker's own first
    initial, on the same turquoise tint the rest of this identity already
    uses for a soft fill) instead of an empty box or an `<img>` whose `src`
    would be missing or empty -- a browser renders a *broken-image* icon
    for exactly that second case, which is a worse failure than simply
    not drawing a photo, and precisely what this function is written to
    avoid producing under any input.
    """
    if portrait_data_uri:
        safe_alt = html.escape(
            f"Portrait of {speaker_name}" if speaker_name else "Portrait"
        )
        safe_src = html.escape(portrait_data_uri, quote=True)
        return f'<img src="{safe_src}" alt="{safe_alt}">'
    initial = speaker_name.strip()[:1].upper() or "?"
    safe_initial = html.escape(initial)
    return (
        '<div class="frame__placeholder" aria-hidden="true">'
        f"<span>{safe_initial}</span></div>"
    )


def _frame_html(
    *, portrait_data_uri: str | None, speaker_name: str, speaker_affiliation: str
) -> str:
    """The whole tilted, polaroid-like frame, name and affiliation set
    along its own lower border like a caption written under a printed
    photograph -- the reference only ever shows a name there; carrying the
    affiliation onto the same caption is this module's own extension, not
    a reproduction (see the module docstring). Both are independently
    sized by `_scaled_font_size` and allowed to wrap rather than being
    clipped -- the caption's own height is not fixed, so a long name and a
    long affiliation together grow the frame's own footprint instead of
    losing text to an ellipsis, matching this task's "the composition
    degrades; it does not break" brief.
    """
    safe_name = html.escape(speaker_name) if speaker_name else "Speaker name"
    photo = _frame_photo_html(portrait_data_uri, speaker_name)
    name_size = _num(_name_font_size(speaker_name or "Speaker name"))
    caption = [
        '<span class="frame__name" '
        f'style="font-size: {name_size}vmin">{safe_name}</span>'
    ]
    if speaker_affiliation:
        safe_affiliation = html.escape(speaker_affiliation)
        affiliation_size = _num(_affiliation_font_size(speaker_affiliation))
        caption.append(
            '<span class="frame__affiliation" '
            f'style="font-size: {affiliation_size}vmin">{safe_affiliation}</span>'
        )
    return (
        '<figure class="frame">'
        f'<div class="frame__photo">{photo}</div>'
        f'<figcaption class="frame__caption">{"".join(caption)}</figcaption>'
        "</figure>"
    )


def _ribbon_overlay_svg(width: float, height: float, root: Path) -> str:
    """The ribbon, painted last so it sits on top of everything else --
    exactly what the reference shows (task 1's own stroke crosses over the
    "WHAT TO EXPECT?" text near the left edge in Anonymous's own poster, not
    behind it). Colour and width both come from task 1's own reader
    functions, never hand-typed here."""
    d = ribbon_path(width, height)
    colour = ribbon_stroke_colour(root)
    stroke_width = ribbon_stroke_width(width, height, ratio=ribbon_width_ratio(root))
    return (
        f'<svg class="ribbon-overlay" viewBox="0 0 {_num(width)} {_num(height)}" '
        'aria-hidden="true" focusable="false">'
        f'<path d="{d}" fill="none" stroke="{colour}" '
        f'stroke-width="{_num(stroke_width)}" stroke-linecap="round"/>'
        "</svg>"
    )


# ---------------------------------------------------------------------------
# The composition itself
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Announcement:
    """Everything one edition's announcement composition needs to know.

    `portrait_data_uri` defaults to `None` -- the common, legitimate state
    (P-4) -- rather than requiring every caller to spell it out. Nothing
    else defaults: a title, a date, a name are what an announcement *is*.
    `speaker_affiliation` may be `""` (a speaker with none to show), which
    `_frame_html` handles by omitting the second caption line entirely
    rather than rendering an empty one.
    """

    title: str
    talk_date: date
    speaker_name: str
    speaker_affiliation: str
    portrait_data_uri: str | None = None


def render_announcement(
    announcement: Announcement, *, width: float, height: float, root: Path
) -> str:
    """The announcement composition, as a complete, self-contained HTML
    page -- see the module docstring for what is fixed, what varies, and
    why this is a page rather than an SVG template.

    Reads `data/brand.json` for colour, and task 1's `ribbon.py` for the
    motif; touches nothing else on disk and makes no network request of
    its own -- `portrait_data_uri`, if given, is inlined as-is (a `data:`
    URI is what a caller should normally pass, so the rendered page never
    needs one either).

    `width` and `height` are the canvas the ribbon and every `vw`/`vmin`
    -relative size in this page's own CSS are computed against -- task 4's
    three formats are this same function called with three different
    pairs, not three different templates.

    `title`, `speaker_name` and `speaker_affiliation` are HTML-escaped
    (`html.escape`) before reaching the page, the same way
    `delivery.render_certificate` escapes a participant's name and an
    event's title -- see that module's own docstring for why bidirectional
    overrides and a bare newline are deliberately left alone rather than
    stripped.
    """
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")

    colours = _load_colours(root)
    safe_title = html.escape(announcement.title) if announcement.title else "Talk title"
    title_size = _num(_title_font_size(announcement.title or "Talk title"))
    when = date_line(announcement.talk_date)
    doc_title = html.escape(
        f"Read together — {announcement.title}"
        if announcement.title
        else "Read together"
    )
    frame = _frame_html(
        portrait_data_uri=announcement.portrait_data_uri,
        speaker_name=announcement.speaker_name,
        speaker_affiliation=announcement.speaker_affiliation,
    )
    ribbon_svg = _ribbon_overlay_svg(width, height, root)
    registration_slot = _registration_slot_html()

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{doc_title}</title>
<style>
{_FONT_FACE_CSS}
  :root {{
{_root_css_block(colours)}  }}

  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    padding: 0;
    overflow: hidden;
    background: var(--surface-2);
  }}

  .poster {{
    position: relative;
    width: 100vw;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--surface-2);
    color: var(--ink);
    font-family: {_FONT_STACK};
  }}

  .band {{
    flex: 0 0 auto;
    background: var(--surface);
    padding: 1.8vmin 4vw;
  }}

  .band--wordmark {{
    display: flex;
    align-items: center;
    gap: 1.6vmin;
  }}
  .wordmark-logo {{ width: 7.2vmin; height: 7.2vmin; flex: 0 0 auto; }}
  .wordmark-text {{
    margin: 0;
    font-size: 3vw;
    font-weight: 800;
    color: var(--purple);
    border-bottom: 0.18vmin solid var(--purple);
    padding-bottom: 0.6vmin;
  }}
  .wordmark-text .accent {{ color: var(--turquoise-d); }}
  .wordmark-text .accent2 {{ color: var(--purple); }}

  .hero {{ flex: 0 0 auto; padding: 2.2vmin 4vw 1.6vmin; }}
  .hero h1 {{
    margin: 0;
    font-size: 4.7vw;
    line-height: 1.05;
    font-weight: 800;
    color: var(--purple);
    text-transform: uppercase;
  }}
  .hero p {{
    margin: 1.6vmin 0 0;
    font-size: 1.75vw;
    line-height: 1.4;
    color: var(--black);
  }}

  .band--talk-title p {{
    margin: 0;
    text-align: center;
    font-weight: 800;
    color: var(--purple);
    overflow-wrap: anywhere;
    line-height: 1.2;
  }}

  .date-line {{
    flex: 0 0 auto;
    margin: 1.8vmin 4vw 0.6vmin;
    text-align: center;
    font-size: 2.2vw;
    font-weight: 800;
    color: var(--purple);
  }}

  .content {{
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    align-items: flex-start;
    gap: 2vmin;
    padding: 1.6vmin 4vw 3.2vmin;
  }}

  .expect {{ flex: 1 1 56%; min-width: 0; padding-left: 22vmin; }}
  .expect h2 {{
    margin: 0 0 1.4vmin;
    font-size: 2vw;
    font-weight: 800;
    text-transform: uppercase;
    color: var(--black);
  }}
  .expect__row {{
    margin: 0 0 1.4vmin;
    font-size: 1.65vw;
    line-height: 1.35;
    color: var(--black);
  }}
  .expect__row strong {{
    color: var(--purple);
    text-transform: uppercase;
  }}

  .frame-wrap {{
    flex: 0 0 40%;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    padding-top: 1vmin;
  }}
  .frame {{
    transform: rotate(6deg);
    background: var(--white);
    width: 30vmin;
    padding: 1.6vmin 1.6vmin 1.2vmin;
    box-shadow: 0 0.6vmin 1.6vmin rgba(0, 0, 0, 0.28);
  }}
  .frame__photo {{
    width: 100%;
    aspect-ratio: 4 / 3;
    background: var(--turquoise-l);
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .frame__photo img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }}
  .frame__placeholder {{
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--purple);
  }}
  .frame__placeholder span {{ font-size: 9vmin; font-weight: 800; }}
  .frame__caption {{
    margin: 1vmin 0 0;
    text-align: center;
    color: var(--black);
  }}
  .frame__name {{ display: block; font-weight: 800; overflow-wrap: anywhere; }}
  .frame__affiliation {{
    display: block;
    font-weight: 400;
    margin-top: 0.4vmin;
    overflow-wrap: anywhere;
  }}

  .register {{
    position: absolute;
    left: 4vw;
    bottom: 3vmin;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1.2vmin;
  }}
  .register p {{
    margin: 0;
    font-weight: 800;
    font-size: 1.8vw;
    line-height: 1.15;
    color: var(--black);
    text-transform: uppercase;
  }}
  .registration-code-slot {{
    width: 16vmin;
    height: 16vmin;
    background: var(--white);
    border: 0.2vmin dashed var(--rule-strong);
  }}

  .ribbon-overlay {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }}
</style>
</head>
<body>
  <div class="poster">
    {_WORDMARK_HTML}
    {_SERIES_HTML}
    <div class="band band--talk-title">
      <p style="font-size: {title_size}vw">{safe_title}</p>
    </div>
    <p class="date-line">{when}</p>
    <div class="content">
      {_EXPECT_HTML}
      <div class="frame-wrap">{frame}</div>
    </div>
    <div class="register">
      <p>Register<br>here</p>
      {registration_slot}
    </div>
    {ribbon_svg}
  </div>
</body>
</html>
"""
