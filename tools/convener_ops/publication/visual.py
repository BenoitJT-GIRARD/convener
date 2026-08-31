"""The announcement composition: a page, not a hand-drawn SVG.

`docs/handbook/assets/example_and_template_initial_assets/announcement-template_initial.png`
(gitignored -- it carries a real person's photograph) is the designer's
own template. Reading it pixel by pixel, top to bottom: a band carrying the
wordmark; the series title in heavy dominant caps on the field; a two-line
invitation to the discussion; a second band carrying the talk's own
title; a date line in the dominant; a "WHAT TO EXPECT?" block; a white, tilted
photographic frame with the speaker's name along its lower edge; a
"REGISTER HERE" label over a QR code; and the ribbon running over
everything, off every edge.

Why a page rather than an SVG template with placeholders
----------------------------------------------------------
An SVG template can hold a blank for a short string. It cannot *compose* a
title nobody has written yet, because SVG text does not wrap or reflow --
every one of this project's inherited `*_test_dev.svg` templates would clip
a title longer than whatever the person who drew it happened to type. HTML
and CSS, rendered to an image, get wrapping, `flex`, and text metrics for
free: the two-line invitation and the "WHAT TO EXPECT?" block are static,
but the talk's own title is not, and D-08 names the overflowing hand-made
poster as a real, lived failure -- see `render_announcement`'s own
docstring for how this module answers it (Python-computed font size, not a
browser-side "shrink to fit" script).

Where the identity comes from, and where it does not
--------------------------------------------------------
Every colour below is read out of `instance/data/brand.json` by this module's own
`_load_colours`, never imported from `tools/scripts/generate_brand_css.py`:
`convener_ops` ships as an installed package (`tools/pyproject.toml`'s own
`[tool.hatch.build.targets.wheel]` lists only this one package), and
`tools/scripts/` sits outside it -- exactly the boundary `brand.py`'s own
`motif` already respects (`motifs/__init__.py`'s `stroke_width`: "threaded
in from `repo_root()` at the call site rather than resolved here"). So
this reads the one shared source of fact directly, the same file the
site's and the app's own generators read, rather than importing either
generator across a boundary this project does not build tooling to cross.
The variable names below are deliberately the ones
`generate_brand_css.render_site_root_block` already writes into
`site/src/style.css` (`--dominant`, `--surface`, `--field-text`, ...) so
that a reader who knows the showcase's own tokens recognises this page's
CSS on sight -- not because the two are the same generated file (they are
not: two independent readers of one JSON source, which is what D-16 asks
for), but because a third name for the same colour would be one more thing
to keep in step by hand.

Every *name* below comes from `instance/config.json`, through
`published.load_identity` -- the same reader `announce.py` and the two
generated SVG templates already use, never a fourth. Three of this page's
fixed parts used to be this instance's own prose: the wordmark
band, the hero band's strapline, and two of the three "what to expect"
rows. A poster is the artefact a duplicate prints and pins to a wall, so
each of the three was this instance's name arriving in another
organisation's building.

The wordmark: derived plainly, not refused and not reconstructed
------------------------------------------------------------------
The band sets `identity.forum_host` -- one colour, lower case, exactly as
`identity.forum` declares it. It used to set
`www.<span class="accent">The</span>Behaviour<span
class="accent2">Forum.org</span>`, and three options were weighed against
the code rather than in the abstract:

- **Derive the treatment.** There is nothing to derive from. Splitting a
  host into an accented part and an unaccented one is a decision about
  one name -- here, accenting the English definite article inside a
  domain -- and no rule over an arbitrary `forum_host` reproduces it.
  Re-casing is the same: the band used to set the host in camel case,
  which is a typographic reading of a name, and DNS holds no capitals to
  read one back out of.
- **Refuse to render.** This project refuses what has no safe default,
  applied to a *value* that might be missing. Nothing is missing
  here: `identity.forum` is required, is refused while it still carries a
  placeholder, and is parsed before `forum_host` exists at all
  (`published.identity_from_data`). What has no safe default is a
  flourish, not a fact -- and a poster that refuses to render costs a
  collaborator the whole artefact, where a build that refuses to publish
  costs a maintainer one message. D-13's own shape applies: the
  unconfigured extra degrades visibly instead of stopping everything.
- **Render it plainly.** Taken, and it is not a new decision so much as
  the one this project already made: `brand_templates.py` writes exactly
  this wordmark into `docs/handbook/assets/announcement-template.svg` and
  `flyer-template.svg` -- the two files a collaborator downloads -- as
  `<text ... fill="{dominant}">{forum_host}</text>`, plain and lower case,
  derived from this same declaration. Two renderings of one poster
  disagreeing about their own wordmark is precisely the second source
  this project keeps deleting. `instance/data/brand.json`'s own `_roles` agrees
  independently: "dominant: Headlines, ribbon, wordmark. The dominant
  colour, **not an accent**."

What is actually lost is one word: `.accent2` resolved to `var(--dominant)`,
which is the colour `.wordmark-text` already inherits, so the "two-tone"
treatment rendered as a single `The` in the same colour as the rest of the
line -- not two colours meeting. The device to its left (`_WORDMARK_LOGO_SVG`)
is untouched: it is drawn from the charter's own `--dominant` and
`--field` -- not from `motif`, which only the two downloadable
templates read for their wordmark -- and it carries no name.

The motif itself is never drawn here. `motifs.path` and
`motifs.stroke_width`, with the family and the ink `brand.py` reads out of
the charter, are called with this composition's exact canvas size and
painted as the last element in the document, so it always sits on top --
exactly what the reference shows:
the stroke crosses over the lower "WHAT TO EXPECT?" text near the
left edge in the designer's own poster, not behind it.

Why a safe area, and why derived rather than hand-typed
---------------------------------------------------------
The ribbon still runs off every edge and still passes behind the bands --
it keeps its full gesture, exactly as above. What it must never do is pass
*through* the words this page sets: the reference's own content sits inside
margins the ribbon lives outside of on both sides, nothing it sets ever
crosses the stroke. `_motif_safe_margins` computes the same two margins
for this composition by asking the family the charter names -- for the
ribbon, the loop centres, the left tail's own fitted bulge, the points
where the stroke crosses each edge -- and taking the deepest on-curve
reach into the canvas on each side,
plus the stroke's own width as clearance (half of it for the stroke's own
physical extent either side of its centreline, the other half as a
documented buffer for the small overshoot a Catmull-Rom curve makes past an
interior anchor on its way to the next one -- `motifs/ribbon.py`'s own
`_LEFT_TAIL_BULGE_X` comment measures this at ~8px on a 1200px canvas
against a ~29px stroke there, comfortably inside one full stroke width).
Every band and the hero section and the date line all read the same two
margins (`--safe-l`/`--safe-r`, `vw`-relative custom properties on
`.poster`) for their own horizontal padding, rather than each guessing its
own clearance the way `.expect`'s own hand-typed `padding-left: 22vmin`
used to (a number that, worked out independently here, turns out close to
what `_motif_safe_margins` derives for a square canvas -- a useful sanity
check, not a coincidence worth relying on for the next aspect ratio).
Deriving the margins from the family's own waypoints rather than typing two numbers
is what makes them survive a change of aspect ratio: `waypoints`
already expresses every loop and bulge as a fraction of the canvas's own
short side, width or height (see that module's own docstring), so a margin
computed from it adapts the same way the ribbon itself does, at any
`width`/`height` this function is called with.

`.content` is the one exception, and reads a third variable,
`--safe-r-content`, for its own right padding instead of `--safe-r` --
`_motif_content_right_margin`'s own docstring explains why: the right
motif never reaches anywhere near as far down the page as `.content`
itself sits, so the full corridor's own right margin is not a number
`.content` needs to clear a threat with, only width it would otherwise
lose for nothing. `.content`'s own left padding still reads `--safe-l`
unchanged -- the left tail's own fitted bulge sits deep inside `.content`'s
own vertical range, not above it the way the right motif's reach is. The
register band (below `.content` -- see "Why the code can never be
clipped" below for why it is a band of its own, not nested inside
`.content` any more) reads `--safe-l` and `--safe-r-content` directly,
the same two margins `.content` itself reads, rather than inheriting
either through nesting the way it once did.

That nesting -- `.register` used to sit inside `.content`'s own
`.expect-col`, below the "what to expect" copy -- is also what fixed a
different, independent bug found in the same render:
`.register` used to be positioned `absolute`, pinned a fixed distance from
the *viewport's* own bottom regardless of how tall the content above it
grew -- exactly the kind of fixed assumption a page whose text can wrap to
more lines must not make. Moving it into normal flow fixed that overlap.
It introduced a second, subtler one in its place, which is why the band
is no longer nested at all -- see below.

Why the code can never be clipped, and why that took more than a QR image
---------------------------------------------------------------------------
`.content` is the one flexible element in the page's own
column of bands, `flex: 1 1 auto; min-height: 0`, absorbing whatever
height the rigid bands above it (`wordmark`, `hero`, the talk-title band,
the date line -- all `flex: 0 0 auto`) left over. That is fine exactly as
long as `.content`'s own children fit inside whatever height it is handed.
They do not always: a long, heavily-wrapped title (a non-Latin script
often wraps to more lines than the same character count would in Latin,
at the same font size -- there are fewer places to break a long word)
grows the talk-title band enough that `.content` is squeezed below what
its own children need, and a flex container squeezed below its children's
natural height does not clip them -- with no `overflow` property of its
own, it lets them spill past its own box edge, into `.poster`'s own hard
`overflow: hidden` clip at the canvas edge. With the register block
sitting last inside that squeezed column, it was the one that spilled off
the bottom of the poster -- a `REGISTER HERE` label whose own code cannot
be scanned is worse than no label at all.

The fix is structural, not a tuned number that happens to hold today for
six rendered states and might not tomorrow: `.register` is now its own
band, a direct child of `.poster`, sibling to `.content` rather than
nested inside it -- `flex: 0 0 auto`, exactly like the wordmark band, the
hero section and the date line. Flexbox never shrinks a `flex: 0 0 auto`
item below its own natural size; the only way to reclaim height when the
page runs long is to take it from an item that is allowed to give some up,
and `.content` (now holding only the "what to expect" copy and the photo)
is that item -- `min-height: 0; overflow: hidden`, with a flex-shrink
factor (20) large enough that ordinary content growth is absorbed there
alone, invisibly, for every state this module's own tests render.
`.band--talk-title` keeps its own flex-shrink too (1,
twenty times less eager than `.content`'s), not because an everyday title
is expected to need it -- `.content` shrinks first, and the six rendered
states never drive it below what its own children need -- but because
nothing bounds how long a title can be (unlike a speaker's name or
institution, `registration._MAX_FIELD_LENGTH`'s own kind of limit),
so a title long enough to exhaust `.content` down to nothing still has
somewhere left to give before the registration code does. Only once both
have given up everything they have could the register band itself be at
risk, and even then it is title text that clips, never the code.
`tests/publication/test_visual.py::test_the_register_band_is_never_squeezed_by_flexible_content`
pins the properties this rests on -- the same kind of property test
`test_the_safe_area_clears_every_ribbon_waypoint` already uses for the
ribbon rather than a rendered pixel -- and its own docstring records what
reverting each property does to the suite.

The variable parts, and how each is handled
------------------------------------------------
- **Title** -- `render_announcement`'s own `title` parameter. Wrapped, not
  truncated, sized in `vw` (of the canvas *width*, the axis it must not
  overflow) by `_scaled_font_size` (a pure function of its character
  count, computed here in Python rather than measured by a script in the
  rendered page -- see that function's own docstring for why
  a *measured* fit would undermine the pinned image comparison).
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
  a speaker's `photo_url` clears the consent gate
  (`public_data.PUBLISHABLE_ON_CONSENT`), and `_frame_html` below renders a
  composed placeholder for it, never a hole or a broken `<img>`. This
  module never fetches a URL and never reads `instance/data/speakers.yml` itself --
  `photo_url` is, by the schema's own words, "a link, not an upload: the
  repository holds records, not media"
  (`docs/operating/schema.md`), so turning it into something this function
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
- **Registration code** -- `announcement.event_id`. `_registration_slot_html`
  renders a QR code encoding `registration.signup_url(event_id)` (D-19)
  into the fixed-size slot reserved for it
  (`registration_code.registration_code_svg`; see that module's own
  docstring for the encoder, and for why its signature -- an id, never a
  URL -- makes a room link structurally unreachable here). The wrapping
  element keeps `data-registration-code-slot`, the hook that
  marked it, now around real content rather than an empty placeholder.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Final

from ..declaration.published import load_identity
from ..governance.rule import PARIS
from . import brand, motifs
from .registration_code import registration_code_svg

__all__ = [
    "FIXTURE_ANNOUNCEMENT",
    "REGISTRATION_SLOT_PADDING_VMIN",
    "REGISTRATION_SLOT_VMIN",
    "WIDE_ASPECT_THRESHOLD",
    "Announcement",
    "date_line",
    "is_wide",
    "paris_standing_start",
    "render_announcement",
]

#: Same convention as `brand.INSTANCE_PATH`: relative to the repository root,
#: threaded in by the caller rather than resolved from this file's own
#: location. Which file is actually read is `brand.py`'s answer, not this
#: module's -- an instance that has written no values of its own builds
#: with the product's charter instead.
BRAND_PATH: Final = brand.INSTANCE_PATH

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
    merged -- read through `convener_ops.publication.brand`, which is the one thing that
    decides *which* charter is in force (the instance's own values, or the
    product's default when a duplicate has not written any).

    Still not an import of `tools/scripts/generate_brand_css.py`, which is the
    boundary the module docstring above is about: that script lives
    outside the installed package. `brand.py` is inside it, and it exists
    precisely so that this module and that script cannot answer "which
    file holds the colours" differently.
    """
    return brand.colours(brand.load(root))


#: The generated block's own variable names
#: (`generate_brand_css.render_site_root_block`), reused here so a reader
#: who knows the showcase's tokens recognises this page's CSS on sight --
#: see the module docstring for why this is a second reader of
#: `instance/data/brand.json`, not an import of the generator.
def _root_css_block(colours: dict[str, str]) -> str:
    return f"""\
  --paper:          {colours["white"]};
  --surface:        {colours["band"]};
  --surface-2:      {colours["field"]};
  --ink:            {colours["ink"]};
  --ink-mute:       {colours["ink_muted"]};
  --ink-faint:      {colours["ink_faint"]};
  --field:          {colours["field"]};
  --field-text:     {colours["field_text"]};
  --field-tint:     {colours["field_tint"]};
  --dominant:       {colours["dominant"]};
  --dominant-hover: {colours["dominant_hover"]};
  --dominant-tint:  {colours["dominant_tint"]};
  --rule:           {colours["rule"]};
  --rule-strong:    {colours["rule_strong"]};
  --white:          {colours["white"]};
  --black:          {colours["black"]};
"""


#: Hand-typed, and correctly so: file paths and Unicode ranges are not
#: colours `instance/data/brand.json` carries an opinion about, and this project
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
#: waits for it to finish loading (the pinned engine) -- there is
#: no visitor for a swap to matter to, and `block` guarantees the glyphs
#: the motif shares a canvas with are never captured mid-swap in a
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
    axis the frame does, at any aspect ratio this page is rendered at,
    or the two would drift apart on anything but a square canvas).

    Computed here, in Python, rather than measured in the browser by a
    "shrink to fit" script -- deliberately, for two reasons. First, no new
    complexity: a real fit-to-box measurement needs the element's own
    rendered metrics, which means either a layout pass a plain CSS
    property cannot see (`ResizeObserver`, requestAnimationFrame polling)
    or a canvas text-measurement call -- either way, script this page does
    not otherwise need. Second, and more importantly: the pinned image
    comparison is only a real control if identical input always renders
    identically (the whole argument for pinning the engine at all) -- a
    size that depended on live browser font-metrics could legitimately
    differ by a pixel between two Chromium builds that still agree on
    every design decision, which is exactly the false positive pinning
    exists to rule out. A pure function of `len(text)` cannot do that: the same
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
#: pixel trace the way the ribbon is. Unlike the ribbon, this glyph
#: was never named as the part of the identity that had drifted (D-16
#: names the palette; the correction named the ribbon
#: specifically as "the only part of the identity that was ever in
#: doubt"), so it is redrawn here as a plain evocation -- two squares in
#: the field's colour on a diagonal, two dots in the dominant joined by a
#: short curved lead -- rather than measured stroke by stroke.
_WORDMARK_LOGO_SVG: Final = """\
<svg class="wordmark-logo" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
  <rect x="1" y="1" width="14" height="14" fill="var(--field)"/>
  <rect x="17" y="17" width="14" height="14" fill="var(--field)"/>
  <path d="M9 15 V22 Q9 26 13 26 H24" fill="none" stroke="var(--dominant)"
        stroke-width="2.6" stroke-linecap="round"/>
  <path d="M24 26 V19 Q24 15 28 15 H33" fill="none" stroke="var(--dominant)"
        stroke-width="2.6" stroke-linecap="round"/>
  <circle cx="9" cy="26" r="3.6" fill="var(--dominant)"/>
  <circle cx="24" cy="26" r="3.6" fill="var(--dominant)"/>
  <circle cx="9" cy="26" r="1.2" fill="var(--surface)"/>
  <circle cx="24" cy="26" r="1.2" fill="var(--surface)"/>
</svg>
"""


def _wordmark_html(forum_host: str) -> str:
    """The top band: the device, then the forum's own address.

    Plain, one colour, and lower case -- see the module docstring's "The
    wordmark: derived plainly, not refused and not reconstructed" for the
    argument, and `brand_templates.py` for the two downloadable templates
    that already set this exact wordmark exactly this way.
    """
    return f"""\
<div class="band band--wordmark">
  {_WORDMARK_LOGO_SVG}
  <p class="wordmark-text">{html.escape(forum_host)}</p>
</div>
"""


def _series_html(strapline: str, forum_host: str) -> str:
    """The hero band: the series' own strapline, and where to discuss it.

    `strapline` is `instance/config.json`'s own key, not a
    motto typed here: until it existed, a duplicate's posters announced
    *this* series' motto above *its* talks. `published.Identity`'s own
    docstring records why it is not `tagline` -- that one is a sentence,
    and a sentence set at `4vw` in heavy capitals wraps to three lines
    and walks the composition into the motif.
    """
    return f"""\
<section class="hero">
  <h1>{html.escape(strapline)}</h1>
  <p>Join the discussion before and after the talk at<br>
  <strong>{html.escape(forum_host)}</strong></p>
</section>
"""


def _expect_html(forum_host: str) -> str:
    """The `WHAT TO EXPECT?` block, fixed on every poster, with the one
    thing in it that is not the product's read from the declaration.

    The three rows carry no edition-specific fact -- no date, no name, no
    hard-typed zone -- so none of them needed correcting the way the date
    line did. Two of them named a forum, though, and named it in a
    *third* spelling: the bare registrable domain, where the wordmark
    band above set `www.` and camel case. One host, written once, spelled
    the way `identity.forum` declares it.
    """
    host = html.escape(forum_host)
    return f"""\
<div class="expect">
  <h2>What to expect?</h2>
  <p class="expect__row"><strong>Before:</strong> Ask your questions to the
    speaker at {host}</p>
  <p class="expect__row"><strong>D-Day:</strong> Presentation followed by a
    discussion with the audience</p>
  <p class="expect__row"><strong>After:</strong> Continue the discussion and
    connect with peers at {host}</p>
</div>
"""


def _registration_slot_html(event_id: str, *, dark: str, root: Path) -> str:
    """The registration QR code, filling the fixed-size slot reserved for
    it (the same `data-registration-code-slot` hook, the
    same "reserve the mount point before the thing that fills it exists"
    pattern the registration form used). `registration_code_svg`
    encodes `registration.signup_url(event_id)` and nothing else -- see that
    function's own docstring for why its signature (an id, never a URL)
    makes a room link structurally unreachable through this call.

    No longer `aria-hidden`: the placeholder had nothing to announce;
    this element now carries the one machine-readable way to reach the
    event's own registration page, so it is left to whatever assistive
    reading the surrounding `<svg>`'s own `<title>` (the plain URL,
    `registration_code_svg`'s own `title=` argument to segno) already
    provides."""
    # The same `root` the charter came from: the encoded address and the
    # colours around it are one instance's, or the poster contradicts
    # itself in a layer no text sweep can read.
    qr_svg = registration_code_svg(event_id, dark=dark, root=root)
    return (
        '<div class="registration-code-slot" data-registration-code-slot>'
        f"{qr_svg}</div>"
    )


# ---------------------------------------------------------------------------
# The photographic frame: a portrait, or a composed placeholder -- never a
# hole, never a broken <img>
# ---------------------------------------------------------------------------


def _frame_photo_html(portrait_data_uri: str | None, speaker_name: str) -> str:
    """The frame's own photo area.

    `portrait_data_uri` is `None` far more often than not -- see the module
    docstring's "Portrait" section for why that is a legitimate, common
    state rather than something to work around, and why this
    function never reaches for a network request to fill it in itself. A
    `None` renders a composed placeholder (the speaker's own first
    initial, on the same field tint the rest of this identity already
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
    losing text to an ellipsis: the composition degrades, it does not
    break.
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


#: Clearance beyond the motif's own deepest on-curve reach, expressed as a
#: multiple of its own stroke width -- see the module docstring's
#: "Why a safe area, and why derived rather than hand-typed" for the two
#: halves this covers (the stroke's own physical extent either side of its
#: centreline, and a documented buffer for Catmull-Rom overshoot).
def _motif_safe_margins(width: float, height: float, root: Path) -> tuple[float, float]:
    """The left and right text safe-area margins, in `vw` (of the canvas
    *width* -- the axis every margin below is subtracted from).

    `motifs.safe_margins` is the arithmetic and this is the unit
    conversion: the two numbers are "how far into the canvas does this
    side's motif reach", plus the clearance the family it names keeps, read
    off that family's own on-curve points rather than sampled from the
    rendered drawing -- see `motifs.safe_margins`, and the module docstring
    here for what the margins are for.
    """
    left, right = motifs.safe_margins(
        brand.motif_family(root),
        width,
        height,
        ratio=brand.motif_width_ratio(root),
    )
    return left / width * 100.0, right / width * 100.0


def _motif_content_right_margin(width: float, height: float, root: Path) -> float:
    """The right-hand safe-area margin for `.content` alone, in `vw` --
    narrower than `_motif_safe_margins`'s own right margin, and the one
    margin in this composition that is not a drawing's own reach.

    What it rests on, measured rather than assumed. `.content` is this
    composition's last band before the register band, and in the pinned
    engine it begins at 0.317 of a square canvas and 0.224 of an A4 print
    -- higher up the page than `0.475`, the fraction the ribbon's own
    `right_tail_exit` sits at (`motifs/ribbon.py::waypoints`). So that
    band and the right motif do share rows, and what keeps the ribbon off
    the words is its shape row by row: its right side runs along the
    canvas edge over most of that range and comes closest at
    `right_tail_bulge`, 0.047 short sides in at 0.392 of the height, where
    the photo frame beside it still clears the stroke -- a few units of
    field between the two on the rendered square. A family drawn some
    other way clears the band by finishing above it instead:
    `motifs/bracket.py::_INNER_TOP` states the rows it fits in and
    `tests/publication/motifs/test_bracket.py` holds it there.

    Reusing `_motif_safe_margins`'s own full-height right margin here
    would cost `.content` -- the "what to expect" copy and the photo frame
    beside it -- width the right motif was never going to reach: this
    fix's own first attempt did exactly that, and it was that copy
    re-wrapping into the "register" label beneath it, not the ribbon, that
    gave the mistake away. `.content`'s own *left* margin still uses
    `_motif_safe_margins`'s full corridor unchanged (see
    `render_announcement`) -- the left tail's own fitted bulge sits at
    `0.747` of the page, well inside `.content`'s own vertical range.
    """
    clearance = motifs.clearance(
        brand.motif_family(root), width, height, ratio=brand.motif_width_ratio(root)
    )
    return clearance / width * 100.0


def _motif_overlay_svg(width: float, height: float, root: Path) -> str:
    """The motif, painted last so it sits on top of everything else --
    exactly what the reference shows (the stroke crosses over the
    "WHAT TO EXPECT?" text near the left edge in the designer's own poster,
    not behind it). The drawing comes from the family the charter names and
    its colour and width from the charter's own fields, never hand-typed
    here."""
    d = motifs.path(brand.motif_family(root), width, height)
    colour = brand.motif_stroke(root)
    stroke_width = motifs.stroke_width(
        width, height, ratio=brand.motif_width_ratio(root)
    )
    return (
        f'<svg class="ribbon-overlay" viewBox="0 0 {_num(width)} {_num(height)}" '
        'aria-hidden="true" focusable="false">'
        f'<path d="{d}" fill="none" stroke="{colour}" '
        f'stroke-width="{_num(stroke_width)}" stroke-linecap="round"/>'
        "</svg>"
    )


# ---------------------------------------------------------------------------
# The wide derivation: a banner is not a squashed poster
# ---------------------------------------------------------------------------
#
# `formats.SQUARE` and `formats.PRINT` both render the composition above
# unchanged -- a taller canvas only ever gives every band *more* room. Only
# `formats.BANNER` (1200x630) is short enough that the square's full
# vertical rhythm (wordmark, hero, talk title, date, "what to expect" plus
# photo, register) cannot all fit without clipping, overlapping, or
# shrinking text below a legible size -- three outcomes that are equally
# unacceptable. Something has to give; two things do, chosen for
# being the *least* essential to a share-preview thumbnail glimpsed in a
# feed, never studied the way a poster on an institute wall is:
#
# - `_series_html` (the strapline in capitals, plus the two-line
#   invitation) restates, at length, exactly what the wordmark band
#   immediately above it already names -- the one line of brand identity a
#   share preview needs, not a second, larger repetition of it.
# - `_expect_html` (the three "before/D-Day/after" rows) explains a process
#   to someone who has decided to attend and is reading for a minute, not
#   someone deciding whether to click through a link preview.
#
# Both are dropped entirely -- not hidden with CSS while still present in
# the document, so nothing about them can be mistaken for a fallback that
# almost renders. What remains is rearranged into two columns rather than
# stacked, because a banner's own width is the resource the square does not
# have and the wide shape is what makes a two-column layout make sense: the
# talk title, the date and the registration code down the left, the
# speaker's frame on the right -- see the `.poster--wide` rule for the
# mechanism, and `render_announcement`'s own docstring for why the register
# band's row can never be the one that gives.
#
# `is_wide` is a plain function of the two numbers `render_announcement`
# already receives, not a CSS media query the browser evaluates at its own
# viewport: every one of this project's three named formats is rendered
# once, to one screenshot, at one already-known size (the pinned
# engine, never resized after the fact), so there is nothing for a media
# query to answer that this function does not already know when it builds
# the page -- and a plain Python conditional is what every other
# size-dependent choice in this module already is (`_scaled_font_size`,
# `_motif_safe_margins`), not a second mechanism next to them.
WIDE_ASPECT_THRESHOLD: Final = 1.5


def is_wide(width: float, height: float) -> bool:
    """Whether a canvas this shape renders the banner derivation rather
    than the square/print one.

    Comfortably below the banner's own 1200x630 (1.905) and comfortably
    above both the square's 1:1 and the print poster's own portrait A4
    ratio (~0.71) -- see `formats.py` for the three named sizes this
    threshold has to tell apart, and the section above for what "wide"
    changes about the composition.
    """
    if width <= 0 or height <= 0:
        raise ValueError("width and height must both be positive")
    return width / height >= WIDE_ASPECT_THRESHOLD


#: The registration slot's own footprint and inner padding, in vmin --
#: named constants rather than literals inside the CSS block below, because
#: `formats.qr_module_size_mm` needs these same two numbers to work out the
#: registration QR's physical module size at print resolution (the
#: printed channel: a poster actually pinned to a wall, where "physical
#: module size" is a real, measurable thing, not a figure of speech). A
#: hand-copied second reading of "12.5" and "0.5" over there could silently
#: drift from what this page actually renders; one is threaded through
#: instead.
REGISTRATION_SLOT_VMIN: Final = 12.5
REGISTRATION_SLOT_PADDING_VMIN: Final = 0.5


# ---------------------------------------------------------------------------
# The composition itself
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Announcement:
    """Everything one edition's announcement composition needs to know.

    `event_id` is the one thing the registration code encodes -- always an
    id, per D-19 (`edition_code`, lower-cased), never a URL and never a
    whole event or speaker record: see `_registration_slot_html` and
    `registration_code.registration_code_svg` for why that signature is
    what keeps a room link structurally unreachable here, not merely
    absent by convention.

    `portrait_data_uri` defaults to `None` -- the common, legitimate state
    -- rather than requiring every caller to spell it out. Nothing
    else defaults: a title, a date, a name, an event id are what an
    announcement *is*. `speaker_affiliation` may be `""` (a speaker with
    none to show), which `_frame_html` handles by omitting the second
    caption line entirely rather than rendering an empty one.
    """

    title: str
    talk_date: date
    speaker_name: str
    speaker_affiliation: str
    event_id: str
    portrait_data_uri: str | None = None


#: The one canonical announcement the versioned reference images
#: render -- reusing `tools/tests/publication/test_visual.py::_announcement`'s own
#: default identity rather than inventing a second "canonical" one (two
#: fixture identities claiming to be *the* announcement is exactly the
#: unforced drift D-14 warns against). Ada Lovelace has been dead for over
#: a century and a half: a name safe to commit to a versioned image where
#: a real, living speaker's would not be -- no real person's name or face
#: may enter one. `portrait_data_uri` stays at
#: its default, `None` -- no photograph is ever committed either, and the
#: gate applies here exactly as it does to a real edition: a reference image is
#: not an exemption from the consent gate, it is one more thing the gate
#: must hold for.
FIXTURE_ANNOUNCEMENT: Final = Announcement(
    title="On analytical engines",
    talk_date=date(2026, 3, 12),
    speaker_name="Ada Lovelace",
    speaker_affiliation="Analytical Engines Institute",
    event_id="mrg-9",
)


def render_announcement(
    announcement: Announcement, *, width: float, height: float, root: Path
) -> str:
    """The announcement composition, as a complete, self-contained HTML
    page -- see the module docstring for what is fixed, what varies, and
    why this is a page rather than an SVG template.

    Reads `instance/data/brand.json` for colour, and `motifs/` for the
    motif; touches nothing else on disk and makes no network request of
    its own -- `portrait_data_uri`, if given, is inlined as-is (a `data:`
    URI is what a caller should normally pass, so the rendered page never
    needs one either).

    `width` and `height` are the canvas the ribbon and every `vw`/`vmin`
    -relative size in this page's own CSS are computed against -- the
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
    identity = load_identity(root)
    safe_title = html.escape(announcement.title) if announcement.title else "Talk title"
    title_size = _num(_title_font_size(announcement.title or "Talk title"))
    when = date_line(announcement.talk_date)
    doc_title = html.escape(
        f"{identity.strapline} — {announcement.title}"
        if announcement.title
        else identity.strapline
    )
    wide = is_wide(width, height)
    frame = _frame_html(
        portrait_data_uri=announcement.portrait_data_uri,
        speaker_name=announcement.speaker_name,
        # Dropped on the banner alone, never hidden with CSS.
        # `_AFFILIATION_FONT_MAX_VMIN` is 1.7vmin; at the banner's own
        # 630px-tall canvas (`vmin` reads the *shorter* side, and height is
        # shorter than width on every wide render) that is ~10.7px before a
        # share-preview surface then scales the whole 1200x630 image down
        # further to display it -- illegible, not merely small. The title
        # and the date already carry what a glanced-at preview needs; an
        # affiliation nobody can read earns its place even less than the
        # series hero or the "what to expect" copy this same derivation
        # already drops for exactly that reason (see "The wide derivation"
        # section below). `_frame_html` already has the mechanism this
        # reuses: an empty string omits the caption's second line entirely,
        # the same path a speaker with no affiliation to show takes on
        # every format, so this needs no new branch of its own. The name
        # alone survives at 2.7vmin (~17px) -- still small, but legible,
        # and it is *who*, the one fact the affiliation's absence does not
        # cost the reader.
        speaker_affiliation=("" if wide else announcement.speaker_affiliation),
    )
    motif_svg = _motif_overlay_svg(width, height, root)
    registration_slot = _registration_slot_html(
        announcement.event_id, dark=colours["black"], root=root
    )
    safe_left_vw, safe_right_vw = _motif_safe_margins(width, height, root)
    safe_content_right_vw = _motif_content_right_margin(width, height, root)

    poster_class = "poster poster--wide" if wide else "poster"
    title_band = f"""\
    <div class="band band--talk-title">
      <p style="font-size: {title_size}vw">{safe_title}</p>
    </div>"""
    register_band = f"""\
    <div class="register">
      <p>Register<br>here</p>
      {registration_slot}
    </div>"""
    wordmark = _wordmark_html(identity.forum_host)
    if wide:
        # See the module's own "The wide derivation" section: the series
        # hero and the "what to expect" copy are dropped outright, not
        # merely hidden, and the frame stands alone rather than sharing
        # `.content` with the copy that no longer exists. Title and date
        # are wrapped together in `.wide-heading` -- see the `.poster--wide
        # > .wide-heading` rule's own comment for why one flex column,
        # centred as a pair, reads better than two separate grid rows that
        # `.frame-wrap`'s own spanning height can pull apart.
        #
        # `title_band` (shared with the square and print
        # branch below, unchanged) is wrapped in one extra element here,
        # `.wide-title-row` -- wide-only, never emitted outside this
        # branch. `.band--talk-title__backdrop`, the first child, is what
        # actually paints the band full-width -- see
        # `.poster--wide .wide-title-row`'s own CSS comment for the full
        # mechanism and why it lives on a sibling rather than on
        # `.band--talk-title` itself.
        body = f"""\
    {wordmark}
    <div class="wide-heading">
      <div class="wide-title-row">
        <div class="band--talk-title__backdrop" aria-hidden="true"></div>
{title_band}
      </div>
    <p class="date-line">{when}</p>
    </div>
    <div class="frame-wrap">{frame}</div>
{register_band}
    {motif_svg}"""
    else:
        body = f"""\
    {wordmark}
    {_series_html(identity.strapline, identity.forum_host)}
{title_band}
    <p class="date-line">{when}</p>
    <div class="content">
      <div class="expect-col">
        {_expect_html(identity.forum_host)}
      </div>
      <div class="frame-wrap">{frame}</div>
    </div>
{register_band}
    {motif_svg}"""

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
    --safe-l: {_num(safe_left_vw)}vw;
    --safe-r: {_num(safe_right_vw)}vw;
    --safe-r-content: {_num(safe_content_right_vw)}vw;
  }}

  .band {{
    flex: 0 0 auto;
    background: var(--surface);
    padding: 1.3vmin var(--safe-r) 1.3vmin var(--safe-l);
  }}

  .band--wordmark {{
    display: flex;
    align-items: center;
    gap: 1.6vmin;
  }}
  .wordmark-logo {{ width: 5.6vmin; height: 5.6vmin; flex: 0 0 auto; }}
  .wordmark-text {{
    margin: 0;
    font-size: 2.6vw;
    font-weight: 800;
    color: var(--dominant);
    border-bottom: 0.18vmin solid var(--dominant);
    padding-bottom: 0.4vmin;
  }}

  .hero {{ flex: 0 0 auto; padding: 1.4vmin var(--safe-r) 1vmin var(--safe-l); }}
  .hero h1 {{
    margin: 0;
    font-size: 4vw;
    line-height: 1.05;
    font-weight: 800;
    color: var(--dominant);
    text-transform: uppercase;
    text-align: center;
  }}
  .hero p {{
    margin: 1vmin 0 0;
    font-size: 1.55vw;
    line-height: 1.35;
    color: var(--black);
  }}

  .band--talk-title {{
    flex: 0 1 auto;
    min-height: 0;
    overflow: hidden;
  }}
  .band--talk-title p {{
    margin: 0;
    text-align: center;
    font-weight: 800;
    color: var(--dominant);
    overflow-wrap: anywhere;
    line-height: 1.2;
  }}

  .date-line {{
    flex: 0 0 auto;
    margin: 1vmin var(--safe-r) 0.4vmin var(--safe-l);
    text-align: center;
    font-size: 2vw;
    font-weight: 800;
    color: var(--dominant);
  }}

  .content {{
    flex: 1 20 auto;
    min-height: 0;
    overflow: hidden;
    display: flex;
    align-items: flex-start;
    gap: 2vmin;
    padding: 1vmin var(--safe-r-content) 1vmin var(--safe-l);
  }}

  .expect-col {{
    flex: 1 1 56%;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }}
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
    color: var(--dominant);
    text-transform: uppercase;
  }}

  .frame-wrap {{
    flex: 0 0 40%;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    padding-top: 0.6vmin;
  }}
  .frame {{
    transform: rotate(6deg);
    background: var(--white);
    width: 25vmin;
    padding: 1.3vmin 1.3vmin 1vmin;
    box-shadow: 0 0.6vmin 1.6vmin rgba(0, 0, 0, 0.28);
  }}
  .frame__photo {{
    width: 100%;
    aspect-ratio: 4 / 3;
    background: var(--field-tint);
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
    color: var(--dominant);
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
    flex: 0 0 auto;
    padding: 0 var(--safe-r-content) 1.2vmin var(--safe-l);
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 1.4vmin;
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
    flex: 0 0 auto;
    width: {_num(REGISTRATION_SLOT_VMIN)}vmin;
    height: {_num(REGISTRATION_SLOT_VMIN)}vmin;
    padding: {_num(REGISTRATION_SLOT_PADDING_VMIN)}vmin;
    background: var(--white);
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .registration-code-slot svg {{
    display: block;
    width: 100%;
    height: 100%;
  }}

  .ribbon-overlay {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }}

  /* The wide (banner) derivation -- see the module's own "The wide
     derivation" section for why this exists and what it drops. Dead
     weight when `wide` is false: no element ever carries
     `poster--wide` on a square or print render, so nothing below ever
     matches.

     The grid's own two columns (`heading`'s "1fr" beside
     `frame`'s own "auto" width) are exactly the shape `.band--talk-title`
     needs to *not* have -- a band confined to one column reads as a
     truncated accident, not the "bands run full width" rule
     `instance/data/brand.json`'s own `layout._bands` states outright. See
     `.poster--wide .wide-title-row`'s own comment below for the fix. */
  .poster--wide {{
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-rows: auto minmax(0, 1fr) auto;
    grid-template-areas:
      "wordmark wordmark"
      "heading  frame"
      "register frame";
    column-gap: 2vmin;
    row-gap: 0.6vmin;
  }}
  .poster--wide > .band--wordmark {{ grid-area: wordmark; }}
  /* Title and date are wrapped in one flex column (`.wide-heading`,
     `render_announcement`'s own markup) rather than placed as two
     separate grid rows: `frame`'s own natural height, spanning both this
     area and `register`'s, can exceed what the title and date need
     together, and a single row that size just leaves the two of them
     stranded apart -- one flex column centred as a unit collects any
     slack above and below the *pair* instead, which reads as deliberate
     spacing rather than a gap. */
  .poster--wide > .wide-heading {{
    grid-area: heading;
    align-self: center;
    display: flex;
    flex-direction: column;
    gap: 0.8vmin;
    min-height: 0;
  }}
  /* `.wide-title-row` (wide-only markup, wrapping the shared
     `title_band` -- see `render_announcement`'s own wide branch) is what
     lets the band's own *background* run the full canvas width while
     its *text* stays exactly where it was, clear of the frame's own
     column -- two different boxes doing two different jobs, rather than
     one box trying to be both.

     `.band--talk-title` itself keeps its unconditional `flex: 0 1 auto;
     min-height: 0; overflow: hidden` (shared with the square and print
     formats -- the vertical "shrink and clip rather than spill" backstop
     the composition already relies on) unchanged; giving `.wide-title-row` the
     same `display: flex; flex-direction: column` re-establishes it one
     level further out, so `.band--talk-title` is still a real flex child
     that can be forced to shrink -- and still clips its own overflow when
     it is -- exactly as before this fix. `.wide-title-row`'s own width is
     never set explicitly, so it stretches to `.wide-heading`'s own
     (column-confined) width by the same flex default that sized
     `.band--talk-title` directly before this fix -- the *text* never
     moves.

     `.band--talk-title__backdrop` is the one element that actually
     breaks out: `position: absolute` removes it from the flow entirely
     (unlike the plain `width: 100vw` tried first and
     reverted -- that fed back into the grid's own "1fr" column-sizing,
     and, worse, widened the *text's* own box too, running it straight
     under the frame -- checked by rendering, not assumed). `top: 0; left:
     0` anchor it to `.wide-title-row`'s own padding box, whose top-left
     corner already sits flush with the canvas's own left edge (column 1
     starts at the grid's own edge, no leading gap) -- so `width: 100vw`
     alone extends it to the canvas's own right edge with no left offset
     needed, and it never reaches `.poster`'s own `overflow: hidden`
     (both are exactly 100vw). `height: 100%` matches `.wide-title-row`'s
     own height exactly, whether that is `.band--talk-title`'s natural
     height or a squeezed one -- `.wide-title-row` has no content of its
     own besides `.band--talk-title`, so the two always match.

     Paint order: an absolutely positioned box with `z-index: auto` paints
     *after* its stacking context's own ordinary in-flow content --
     backwards from what "behind the text" needs -- which is exactly why
     `.wide-title-row` itself gets `position: relative; z-index: 0`,
     giving the backdrop's own `z-index: -1` a *local* stacking context to
     be negative *within*, ahead of `.band--talk-title`'s own text rather
     than beneath some unrelated ancestor's background. `.frame-wrap`
     (below, later in this page's own DOM order, outside this stacking
     context entirely) still paints over whatever part of the backdrop
     its own column overlaps -- white border and drop shadow on top of
     the band, read as layered rather than colliding, exactly like the
     wordmark band above it (whose "wordmark wordmark" grid area already
     spans both columns) and like this same band on the square and print
     formats (there, a plain flex child stretched to `.poster`'s own full
     width by default -- no backdrop needed, because nothing beside it
     ever shares its row). */
  .poster--wide .wide-title-row {{
    position: relative;
    z-index: 0;
    display: flex;
    flex-direction: column;
    flex: 0 1 auto;
    min-height: 0;
  }}
  .poster--wide .wide-title-row .band--talk-title__backdrop {{
    position: absolute;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100%;
    z-index: -1;
    background: var(--surface);
  }}
  .poster--wide .wide-heading .date-line {{ margin: 0 var(--safe-r) 0 var(--safe-l); }}
  .poster--wide > .frame-wrap {{
    grid-area: frame;
    align-self: center;
    justify-self: end;
    padding: 0 var(--safe-r-content) 0 0;
  }}
  .poster--wide > .register {{ grid-area: register; }}
</style>
</head>
<body>
  <div class="{poster_class}">
{body}
  </div>
</body>
</html>
"""
