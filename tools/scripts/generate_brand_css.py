"""Everything the charter derives: the design tokens and the two templates.

`instance/data/brand.json` measured the designer's own colours -- turquoise `#FECAC1`,
cream `#F4F0F1`, purple `#012765` -- and the contrast each pairing gives. Both
implementations that draw the identity were still a hand-typed copy of that
file: `site/src/style.css` and `app/src/design/tokens.css` each carried the
same values retyped, and the application had drifted to a reconstruction's
palette without anyone deciding that on purpose.
Purple on turquoise measured
4.44 there, below AA; the measured charter gives 7.93, AAA. One source of fact
and two hand-typed copies is exactly the shape that let that drift happen
silently. This script closes it: the custom properties are generated, and
`--check` makes the generation a fact about the repository rather than a
habit somebody might keep up.

A third file, `app/src/design/tokens.ts`, used to be generated here too. It
turned out to be dead -- nothing under `app/src` imports it --
and was retired instead: a generated file nobody reads still drifts, exactly
as a hand-typed one would, except it now looks maintained. If a real
consumer ever needs it again, it should be wired up and regenerated, not
resurrected as an unread copy.

What the charter is
--------------------
`instance/data/brand.json` is no longer *the* source of fact; it is *this
instance's*. `declarations/boundary.yml` hands `instance/data/` to the instance, so a
duplicate writes its own values there and never merges a conflict with
upstream over them. A duplicate that has not chosen colours yet has no such
file at all, and `convener_ops.publication.brand.load` reads the product's own charter,
`brand/convener/brand.json`, instead -- so a fresh duplicate builds a
finished-looking site rather than a grey one. Which of the two is in force
is `brand.py`'s answer and nobody else's; this script, `brand_templates.py`
and `visual.py` all ask it.

**`motif` has a default of its own too, since 2026-08-26.** It had none
until then, so that no duplicate could wear a mark somebody else drew --
right about the mark, wrong about the default, and what it produced was a
clone whose very first build refused until a designer had been found. The
product ships its own motif now (`brand/convener/brand.json`), and what
says an instance is not configured is `published.unconfigured` on the
public pages rather than a build that will not run. This command still
stops on a `motif` written and left half-finished, which is a mistake
nothing can complete.

**AA is checked here, not only in the test suite.** Every pairing the
charter records is recomputed from the two colours beside it at every run,
`--check` or not, and one that recomputes below 4.5 stops the build. That
is what makes shipping a default palette safe at all: this project was
already caught once by an *invented* palette that measured worse than the
one it replaced (D-16), and the parade is that a palette which cannot
clear AA cannot build.

What is generated and what stays hand-authored
-----------------------------------------------
Neither stylesheet is generated whole. `site/src/style.css` and
`app/src/design/tokens.css` hold real, hand-authored component CSS --
layout, buttons, prose rendering -- that no JSON file could sensibly derive,
and `instance/data/brand.json` itself only ever claimed the **colour tokens**, not the
rest of either file. So each stylesheet keeps one block of custom properties
between two marker comments, and this script owns only what is between them:
it reads the committed file, keeps everything outside the markers exactly as
it stood, and replaces what is between them with what `instance/data/brand.json`
currently derives.

Two colours the stylesheets need have no measurement to derive from at all:
`--danger` and `--info` name states (a rejected token, a soft banner) that
none of the designer's originals ever had reason to draw, so
`instance/data/brand.json` does not carry them and this script does not pretend it
does -- they are named constants below, clearly marked as the one exception,
rather than invented brand data.

What a marker guards, and what it cannot
-----------------------------------------
`--check` catches a value hand-edited inside the marked block without
`instance/data/brand.json` changing, and a `instance/data/brand.json` value
changed without regenerating -- the two mutations this module's own tests
prove against. It
cannot stop a colour from being hand-typed **outside** any marked block --
that is a different property, and `tools/tests/publication/test_brand.py` guards it
separately, by asking the committed files themselves whether one of
`instance/data/brand.json`'s values, or one of the reconstruction's, appears anywhere
outside the block this script owns.

The three downloadable files are generated whole
--------------------------------------------------
`docs/handbook/assets/announcement-template.svg`, `flyer-template.svg` and
`video-call-background.svg` are the files `docs/handbook/toolkit/visual-kit.md`
hands a volunteer. Nothing in them is hand-authored any more, so there are
no markers and no splice: they are written entire, from the charter and
from `instance/config.json`. All three were drawn by hand once. The two
templates had drifted onto the palette D-16 discarded -- including one
line set in the page's own ground colour, invisible in every poster ever
downloaded. The background was a PNG, which is worse than drifting: no
check in this repository could read a word of it, and it disagreed with
`instance/config.json` about the series' own strapline for as long as it
existed. See `convener_ops/publication/brand_templates.py` for the measurements, for
why the mark is what makes a duplicate's build refuse, and for why the
background is committed as vector with no raster beside it.

Contrast is recomputed, not read
---------------------------------
`instance/data/brand.json` also carries measured contrast ratios. This script exposes
the same WCAG 2.1 relative-luminance arithmetic the measurement used
(`relative_luminance`, `contrast_ratio`) so that `test_brand.py` can
recompute every stored ratio from the colours that produce it and fail the
moment the two disagree -- a plausible-sounding number that nobody rechecks
is exactly how the reconstruction's drift went unnoticed for months.

The name says `css` and it writes two SVGs as well. Renaming it would
rewrite the header comment of both committed stylesheets and the step that
runs it in `quality.yml`, to gain nothing a docstring cannot say: it is
the charter's generator, and this is what the charter derives.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python scripts/generate_brand_css.py            # write the files
    uv run python scripts/generate_brand_css.py --check    # assert only

As with the schema generator, there is no mode that prints a file, and
nothing this repository's Python writes to a terminal may be non-ASCII.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, brand_templates, cockpit, motifs
from convener_ops.publication.brand import rgb_triplet, rgba

#: The instance's own values, relative to the repository root. Not "the one
#: source of fact" any more: an instance that
#: has not chosen its colours has no such file, and `brand.load` reads the
#: product's own charter (`brand/convener/brand.json`) instead. Kept under
#: this name because every failure message and both generated stylesheets'
#: own headers point a reader at it -- it is where a duplicate writes its
#: values, whether or not it has yet.
BRAND_PATH: Final = brand.INSTANCE_PATH

SITE_CSS_PATH: Final = Path("site") / "src" / "style.css"
APP_TOKENS_CSS_PATH: Final = Path("app") / "src" / "design" / "tokens.css"
ANNOUNCEMENT_SVG_PATH: Final = brand_templates.ANNOUNCEMENT_PATH
FLYER_SVG_PATH: Final = brand_templates.FLYER_PATH
BACKGROUND_SVG_PATH: Final = brand_templates.BACKGROUND_PATH

#: How the script is invoked, quoted in every failure message. One string,
#: so the messages cannot come to name two different commands.
COMMAND: Final = "uv run python scripts/generate_brand_css.py"

#: Markers wrapping the generated block inside each stylesheet. Everything
#: outside them, in either file, is this script's to leave alone.
_BEGIN: Final = "/* BEGIN GENERATED TOKENS -- tools/scripts/generate_brand_css.py */"
_END: Final = (
    "/* END GENERATED TOKENS -- edit instance/data/brand.json, not this block */"
)

#: No original the designer drew ever needed a rejection colour or a soft
#: informational one, so `instance/data/brand.json` does not carry either -- these are
#: the one deliberate exception to "every colour comes from the brand file".
_DANGER: Final = "#9b2226"
_INFO: Final = "#4a6c75"

#: The translucency each `--select` needs. Not brand data -- an opacity
#: choice for a UI state -- so it lives here rather than in the JSON file.
_SITE_SELECT_ALPHA: Final = 0.35
_APP_SELECT_ALPHA: Final = 0.25


# --------------------------------------------------------------------------
# Reading the one source of fact
# --------------------------------------------------------------------------


def load_brand(root: Path) -> dict[str, Any]:
    """The charter in force -- the instance's values, or the product's own.

    One line, and it is `convener_ops.publication.brand`'s: this script, the
    ribbon and `visual.py` each used to carry their own two-line loader, which was
    harmless while `instance/data/brand.json` was the only file there was to load
    and stopped being harmless the moment it became optional.
    """
    return brand.load(root)


def _colours(charter: dict[str, Any]) -> dict[str, str]:
    """Every named colour, `colour` and `derived` merged."""
    return brand.colours(charter)


# --------------------------------------------------------------------------
# The generated block, splice into an otherwise hand-authored stylesheet
# --------------------------------------------------------------------------


def _splice(current: str, inner: str) -> str:
    """`current`, with the text between the markers replaced by `inner`.

    Raises rather than guessing when a marker is missing: silently leaving
    the file untouched would make `--check` compare `current` with itself
    and report a match on a file that no longer has anywhere to write to.
    """
    if _BEGIN not in current or _END not in current:
        raise ValueError(
            f"markers not found ({_BEGIN!r} / {_END!r}); the generated block"
            " cannot be located"
        )
    before, _, rest = current.partition(_BEGIN)
    _, _, after = rest.partition(_END)
    return f"{before}{_BEGIN}\n{inner}{_END}{after}"


#: `site/src/style.css`'s tokens. Names and values match the file as it
#: stood before this script existed, once the charter's
#: measured values had been restored by hand, plus `--white`/`--white-rgb`,
#: added here because
#: `#fff` was hand-typed more than a dozen times below the block for plain
#: white text and borders, and a value `instance/data/brand.json` carries cannot be
#: one this stylesheet retypes either. `--danger`/`--info` joined later:
#: the certificate-verification page needed them and got them
#: hand-typed outside this block instead, the same duplication `--white`
#: was added here to avoid -- so they generate from `_DANGER`/`_INFO` below,
#: same as `app/src/design/tokens.css`'s own two, rather than being retyped.
_SITE_ROOT_TEMPLATE: Final = """\
  /* Grounds: the field fills the page, the bands run across it, white
   * appears only inside photographic frames. */
  --paper:          {white};
  --surface:        {band};
  --surface-2:      {field};

  /* Text: warm, never slate -- the warmth is the single thing that most
   * distinguishes this identity from a palette assembled out of defaults. */
  --ink:            {ink};
  --ink-mute:       {ink_muted};
  --ink-faint:      {ink_faint};

  /* The plain field value is a GROUND and must never carry text.
   * field-text is the readable variant, for links and text accents. */
  --field:          {field};
  --field-text:     {field_text};
  --field-tint:     {field_tint};

  --dominant:       {dominant};
  --dominant-hover: {dominant_hover};
  --dominant-tint:  {dominant_tint};

  /* No instance/data/brand.json equivalent: no original the designer drew ever
   * needed a rejection colour or a soft informational one. Measured against
   * this file's own --surface (the band), the certificate-verification
   * panel's ground: see instance/data/brand.json's contrast._comment for
   * both numbers. */
  --danger:         {danger};
  --info:           {info};

  /* Rules and borders only -- never text. */
  --rule:           {rule};
  --rule-strong:    {rule_strong};
  --select:         {select};

  /* White as a foreground/border role, distinct in name from --paper (the
   * ground) though currently the same value: text and a border drawn on a
   * coloured background need "white" as a role of its own. */
  --white:          {white};
  --white-rgb:      {white_rgb};
"""


def render_site_root_block(charter: dict[str, Any]) -> str:
    """The generated inner text of `site/src/style.css`'s `:root` block."""
    colours = _colours(charter)
    return _SITE_ROOT_TEMPLATE.format(
        white=colours["white"],
        band=colours["band"],
        field=colours["field"],
        ink=colours["ink"],
        ink_muted=colours["ink_muted"],
        ink_faint=colours["ink_faint"],
        field_text=colours["field_text"],
        field_tint=colours["field_tint"],
        dominant=colours["dominant"],
        dominant_hover=colours["dominant_hover"],
        dominant_tint=colours["dominant_tint"],
        danger=_DANGER,
        info=_INFO,
        rule=colours["rule"],
        rule_strong=colours["rule_strong"],
        select=rgba(colours["field"], _SITE_SELECT_ALPHA),
        white_rgb=rgb_triplet(colours["white"]),
    )


def render_site_css(root: Path) -> str:
    """`site/src/style.css` in full: hand-authored, with its tokens generated."""
    current = (root / SITE_CSS_PATH).read_text(encoding="utf-8")
    return _splice(current, render_site_root_block(load_brand(root)))


#: `app/src/design/tokens.css`'s tokens, one line per key
#: `convener_ops.publication.cockpit.TOKEN_COLOURS` declares, and every
#: value read from the charter in force through it. That table is the one
#: home for "which charter colour is behind this custom property": the
#: same module measures every pairing the cockpit's chrome sets against
#: every charter under `brand/`, and a sweep reading one table while the
#: stylesheet was written from another would be measuring a cockpit
#: nobody builds.
#:
#: The names are the showcase's now. They were `--primary` and `--accent`
#: where `site/src/style.css` says `--field` and `--dominant`, which the
#: comment here used to call a Tailwind vocabulary as much as a CSS one
#: and leave at that. What settled it is the measurement: a charter's
#: field is a ground that may never carry text and may never carry white
#: text -- every `contrast._forbidden` under `brand/` says so in those
#: words -- and `primary` is the word an author reaches for when filling
#: a button. Twenty-five class lists in fifteen files did one of the two
#: things it invites: eighteen filled a control or a masthead with the
#: field and set white on it, seven set the field itself as type, and both
#: measure 1.61 to 1.71 against white. The rest of the
#: cockpit's names are left alone: no measurement bears on `--border`
#: against the showcase's `--rule`, and a rename nothing measures is
#: taste rather than a finding.
_APP_ROOT_TEMPLATE: Final = """\
  --paper:          {paper};
  --paper-soft:     {paper-soft};
  --surface:        {surface};
  --surface-mute:   {surface-mute};
  --ink:            {ink};
  --ink-muted:      {ink-muted};
  --ink-faint:      {ink-faint};
  --field:          {field};
  --field-text:     {field-text};
  --field-tint:     {field-tint};
  --dominant:       {dominant};
  --dominant-hover: {dominant-hover};
  --dominant-tint:  {dominant-tint};
  --border:         {border};
  --border-strong:  {border-strong};
  /* No instance/data/brand.json equivalent: no original the designer drew ever
   * needed a rejection colour or a soft informational one. */
  --danger:         {danger};
  --info:           {info};
  --select:         {select};
"""


def app_tokens(charter: dict[str, Any]) -> dict[str, str]:
    """Every cockpit token at this charter, including the two no charter
    carries. One call, so that the stylesheet this script writes and the
    pairings `cockpit.contrast_problems` measures are the same colours."""
    return cockpit.token_colours(charter, danger=_DANGER, info=_INFO)


def render_app_root_block(charter: dict[str, Any]) -> str:
    """The generated inner text of `app/src/design/tokens.css`'s `:root` block."""
    tokens = app_tokens(charter)
    return _APP_ROOT_TEMPLATE.format(
        **tokens,
        select=rgba(_colours(charter)["field"], _APP_SELECT_ALPHA),
    )


def render_app_tokens_css(root: Path) -> str:
    """`app/src/design/tokens.css` in full, tokens generated, rest untouched."""
    current = (root / APP_TOKENS_CSS_PATH).read_text(encoding="utf-8")
    return _splice(current, render_app_root_block(load_brand(root)))


# --------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Target:
    """One generated file: where it lives, and how to render it."""

    rel_path: Path
    render: Callable[[Path], str]


#: Everything the charter derives. The two stylesheets keep one block
#: between markers inside an otherwise hand-authored file; the two
#: templates are written whole, because nobody hand-authors anything in
#: them -- see `convener_ops/publication/brand_templates.py` for what they are and why
#: they had to stop being drawn.
_TARGETS: Final = (
    _Target(SITE_CSS_PATH, render_site_css),
    _Target(APP_TOKENS_CSS_PATH, render_app_tokens_css),
    _Target(ANNOUNCEMENT_SVG_PATH, brand_templates.render_announcement_template),
    _Target(FLYER_SVG_PATH, brand_templates.render_flyer_template),
    _Target(BACKGROUND_SVG_PATH, brand_templates.render_video_call_background),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the design tokens and the downloadable "
        "templates from the charter in force."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if a committed file is not what "
        "the charter derives",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    named = brand.source(root).as_posix()

    # A charter still written in a shape this product has moved past --
    # colours named after hues, a `motif` under the ribbon's own field
    # names or naming no family at all -- before anything is measured: it
    # answers none of the names the templates below ask for, so the one
    # useful thing to print is which file it is and which migration
    # rewrites it. A `family` naming a drawing that does not exist is the
    # same moment and the same one useful thing to print, and never a
    # fall back to whichever drawing this product happens to have.
    try:
        charter = brand.load(root)
        others = [
            (rel.as_posix(), brand.charter(root, rel))
            for rel in brand.shipped(root)
            if rel != brand.source(root)
        ]
    except (brand.SupersededCharterError, motifs.UnknownMotifFamilyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    # The palettes first, and unconditionally -- writing or checking. A
    # measurement that no longer recomputes, or one that recomputes below
    # AA, is not a file that needs regenerating: it is a palette that must
    # not build, whichever file it came from. The
    # `--check` is here precisely so that a default palette could ship at all
    # (see brand/convener/brand.json's own `_why_a_default`), and a check
    # that only compared files against a JSON document would have carried
    # none of that promise.
    #
    # Every charter under `brand/` is measured here and not only the one
    # in force, which is what a directory of palettes a duplicate may
    # *choose* costs: a charter nobody has chosen yet derives no file, so
    # nothing else in this run would ever open it, and it would ship
    # failing AA with every gate green. The list is read off the directory
    # (`brand.shipped`), so a charter added there is measured on the commit
    # that adds it.
    # What the cockpit's own chrome sets, read off `app/src` before any
    # palette is measured against it. Two refusals rather than a ratio --
    # a `text-`/`bg-` value that names neither a colour nor a known
    # non-colour word, and an `opacity-*` dimming type its own class list
    # does not name -- because both are pairings this sweep would
    # otherwise have measured something other than what the browser
    # paints. See `convener_ops/publication/cockpit.py` for why they are
    # findings rather than skips.
    chrome, refused = cockpit.scan(root)
    refused += cockpit.unresolved_foregrounds(chrome)
    if refused:
        for problem in refused:
            print(problem, file=sys.stderr)
        print(
            "A pairing this sweep cannot resolve is a pairing no charter "
            "is ever measured against. Name the ground and the type on the "
            "same element.",
            file=sys.stderr,
        )
        return 1

    failed = False
    for shown, values in [(named, charter), *others]:
        contrast = brand.contrast_problems(values, named=shown)
        # The palette's own twelve pairings, and then every pairing the
        # cockpit's chrome sets at this palette. The second is not a
        # property of the charter and could not be recorded in it: it is
        # what `app/src` does with the charter, and until it was measured
        # the sign-in screen filled its primary button with the field and
        # set white on it -- 1.61, the exact pairing every
        # `contrast._forbidden` under `brand/` names. `check-a11y.mjs`
        # could not see it: it sweeps the showcase's pages, and it renders
        # the one charter in force rather than the four a duplicate may
        # choose.
        contrast += cockpit.contrast_problems(
            chrome, values, named=shown, danger=_DANGER, info=_INFO
        )
        if not contrast:
            print(
                f"every measured contrast in {shown} recomputes and clears "
                f"AA, and so does every one of the {len(chrome)} pairings "
                "the cockpit's chrome sets at it"
            )
            continue
        failed = True
        for problem in contrast:
            print(problem, file=sys.stderr)
    if failed:
        print(
            "A palette that does not clear AA does not build. Fix the "
            "colours in the charter named above, or the ratio beside them.",
            file=sys.stderr,
        )
        return 1

    problems: list[str] = []
    for target in _TARGETS:
        path = root / target.rel_path
        try:
            rendered = target.render(root)
        except brand.MissingMotifError as exc:
            # Not "this file needs regenerating": nothing can regenerate
            # it. A `motif` left half-written names no colour to draw the
            # ribbon in, and neither the charter in force nor the
            # product's own can supply the missing half without inventing
            # a value that appears in no file.
            print(f"{target.rel_path.as_posix()}: {exc}", file=sys.stderr)
            return 1
        except (FileNotFoundError, ValueError) as exc:
            problems.append(f"{target.rel_path.as_posix()}: {exc}")
            continue

        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != rendered:
                problems.append(
                    f"{target.rel_path.as_posix()} is not what {named} derives."
                )
            continue

        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current == rendered:
            print(f"{target.rel_path.as_posix()} unchanged")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8", newline="")
            print(f"wrote {target.rel_path.as_posix()}")

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(
            f"Generated, not authored: run `{COMMAND}` from `tools/` and "
            "commit what it writes.",
            file=sys.stderr,
        )
        return 1

    if args.check:
        print(f"every generated file matches {named}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
