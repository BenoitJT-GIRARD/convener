"""Everything the charter derives: the design tokens and the two templates.

`data/brand.json` measured Anonymous's own colours -- turquoise `#FECAC1`, cream
`#F4F0F1`, purple `#012765` -- and the contrast each pairing gives. Both
implementations that draw the identity were still a hand-typed copy of that
file: `site/src/style.css` and `app/src/design/tokens.css` each carried the
same values retyped, and the application had drifted to a reconstruction's
palette without anyone deciding that on purpose
(`docs/superpowers/deferred-work.md`, entry 1). Purple on turquoise measured
4.44 there, below AA; Anonymous's own value gives 7.93, AAA. One source of fact
and two hand-typed copies is exactly the shape that let that drift happen
silently. This script closes it: the custom properties are generated, and
`--check` makes the generation a fact about the repository rather than a
habit somebody might keep up.

A third file, `app/src/design/tokens.ts`, used to be generated here too. Fix
round 1 of this task found it dead -- nothing under `app/src` imports it --
and retired it instead: a generated file nobody reads still drifts, exactly
as a hand-typed one would, except it now looks maintained. If a real
consumer ever needs it again, it should be wired up and regenerated, not
resurrected as an unread copy.

What the charter is, after phase 10
-------------------------------------
`data/brand.json` is no longer *the* source of fact; it is *this
instance's*. `config/boundary.yml` hands `data/` to the instance, so a
duplicate writes its own values there and never merges a conflict with
upstream over them. A duplicate that has not chosen colours yet has no such
file at all, and `convener_ops.brand.load` reads the product's own charter,
`brand/convener/brand.json`, instead -- so a fresh duplicate builds a
finished-looking site rather than a grey one. Which of the two is in force
is `brand.py`'s answer and nobody else's; this script, `ribbon.py` and
`visual.py` all ask it.

**`motif` is the exception, and it has no default at all.** The ribbon's
stroke and the logo's dots are a signature. `brand.motif` refuses rather
than substituting, and this command stops with that refusal rather than
writing a template wearing another organisation's mark.

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
and `data/brand.json` itself only ever claimed the **colour tokens**, not the
rest of either file. So each stylesheet keeps one block of custom properties
between two marker comments, and this script owns only what is between them:
it reads the committed file, keeps everything outside the markers exactly as
it stood, and replaces what is between them with what `data/brand.json`
currently derives.

Two colours the stylesheets need have no measurement to derive from at all:
`--danger` and `--info` name states (a rejected token, a soft banner) that
none of Anonymous's originals ever had reason to draw, so `data/brand.json` does
not carry them and this script does not pretend it does -- they are named
constants below, clearly marked as the one exception, rather than invented
brand data.

What a marker guards, and what it cannot
-----------------------------------------
`--check` catches a value hand-edited inside the marked block without
`data/brand.json` changing, and a `data/brand.json` value changed without
regenerating -- the two mutations this module's own tests prove against. It
cannot stop a colour from being hand-typed **outside** any marked block --
that is a different property, and `tools/tests/test_brand.py` guards it
separately, by asking the committed files themselves whether one of
`data/brand.json`'s values, or one of the reconstruction's, appears anywhere
outside the block this script owns.

The two downloadable templates are generated whole
----------------------------------------------------
`docs/assets/announcement-template.svg` and `flyer-template.svg` are the
files `docs/toolkit/visual-kit.md` hands a volunteer. Nothing in them is
hand-authored any more, so there are no markers and no splice: they are
written entire, from the charter and from `config/instance.json`. They
were drawn by hand until phase 10 task 4 and had drifted onto the palette
D-16 discarded -- including one line set in the page's own ground colour,
invisible in every poster ever downloaded. See
`convener_ops/brand_templates.py` for the measurements and for why the mark is
what makes a duplicate's build refuse.

Contrast is recomputed, not read
---------------------------------
`data/brand.json` also carries measured contrast ratios. This script exposes
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

    uv run python ../scripts/generate_brand_css.py            # write the files
    uv run python ../scripts/generate_brand_css.py --check    # assert only

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

from convener_ops import brand, brand_templates
from convener_ops.brand import rgb_triplet, rgba
from convener_ops.paths import repo_root

#: The instance's own values, relative to the repository root. Not "the one
#: source of fact" any more, and that is phase 10's doing: an instance that
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

#: How the script is invoked, quoted in every failure message. One string,
#: so the messages cannot come to name two different commands.
COMMAND: Final = "uv run python ../scripts/generate_brand_css.py"

#: Markers wrapping the generated block inside each stylesheet. Everything
#: outside them, in either file, is this script's to leave alone.
_BEGIN: Final = "/* BEGIN GENERATED TOKENS -- scripts/generate_brand_css.py */"
_END: Final = "/* END GENERATED TOKENS -- edit data/brand.json, not this block */"

#: No original Anonymous drew ever needed a rejection colour or a soft
#: informational one, so `data/brand.json` does not carry either -- these are
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

    One line, and it is `convener_ops.brand`'s: this script, `ribbon.py` and
    `visual.py` each used to carry their own two-line loader, which was
    harmless while `data/brand.json` was the only file there was to load
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
#: stood before this script existed -- task 2 already restored Anonymous's own
#: values by hand -- plus `--white`/`--white-rgb`, added here because
#: `#fff` was hand-typed more than a dozen times below the block for plain
#: white text and borders, and a value `data/brand.json` carries cannot be
#: one this stylesheet retypes either. `--danger`/`--info` joined in a later
#: fix round: the certificate-verification page needed them and got them
#: hand-typed outside this block instead, the same duplication `--white`
#: was added here to avoid -- so they generate from `_DANGER`/`_INFO` below,
#: same as `app/src/design/tokens.css`'s own two, rather than being retyped.
_SITE_ROOT_TEMPLATE: Final = """\
  /* Grounds: turquoise is the field, cream runs across it in bands, white
   * appears only inside photographic frames. */
  --paper:        {white};
  --surface:      {cream};
  --surface-2:    {turquoise};

  /* Text: warm, never slate -- the warmth is the single thing that most
   * distinguishes this identity from a generic purple-and-teal one. */
  --ink:          {ink};
  --ink-mute:     {ink_muted};
  --ink-faint:    {ink_faint};

  /* The plain turquoise value is a GROUND and must never carry text.
   * turquoise-d is the readable variant, for links and text accents. */
  --turquoise:    {turquoise};
  --turquoise-d:  {turquoise_text};
  --turquoise-l:  {turquoise_tint};

  --purple:       {purple};
  --purple-d:     {purple_hover};
  --purple-l:     {purple_tint};

  /* No data/brand.json equivalent: no original Anonymous drew ever needed a
   * rejection colour or a soft informational one. Measured against this
   * file's own --surface (cream), the certificate-verification panel's
   * ground: see data/brand.json's contrast._comment for both numbers. */
  --danger:       {danger};
  --info:         {info};

  /* Rules and borders only -- never text. */
  --rule:         {rule};
  --rule-strong:  {rule_strong};
  --select:       {select};

  /* White as a foreground/border role, distinct in name from --paper (the
   * ground) though currently the same value: text and a border drawn on a
   * coloured background need "white" as a role of its own. */
  --white:        {white};
  --white-rgb:    {white_rgb};
"""


def render_site_root_block(charter: dict[str, Any]) -> str:
    """The generated inner text of `site/src/style.css`'s `:root` block."""
    colours = _colours(charter)
    return _SITE_ROOT_TEMPLATE.format(
        white=colours["white"],
        cream=colours["cream"],
        turquoise=colours["turquoise"],
        ink=colours["ink"],
        ink_muted=colours["ink_muted"],
        ink_faint=colours["ink_faint"],
        turquoise_text=colours["turquoise_text"],
        turquoise_tint=colours["turquoise_tint"],
        purple=colours["purple"],
        purple_hover=colours["purple_hover"],
        purple_tint=colours["purple_tint"],
        danger=_DANGER,
        info=_INFO,
        rule=colours["rule"],
        rule_strong=colours["rule_strong"],
        select=rgba(colours["turquoise"], _SITE_SELECT_ALPHA),
        white_rgb=rgb_triplet(colours["white"]),
    )


def render_site_css(root: Path) -> str:
    """`site/src/style.css` in full: hand-authored, with its tokens generated."""
    current = (root / SITE_CSS_PATH).read_text(encoding="utf-8")
    return _splice(current, render_site_root_block(load_brand(root)))


#: `app/src/design/tokens.css`'s tokens. Same variable *names* the file
#: already declared -- `tailwind.config.ts` reads them by name, and renaming
#: would be a second change wearing this one's clothes -- but every value
#: corrected from the reconstruction's palette to `data/brand.json`'s.
_APP_ROOT_TEMPLATE: Final = """\
  --paper:         {white};
  --paper-soft:    {cream};
  --surface:       {white};
  --surface-mute:  {turquoise_tint};
  --ink:           {ink};
  --ink-muted:     {ink_muted};
  --ink-faint:     {ink_faint};
  --primary:       {turquoise};
  --primary-hover: {turquoise_text};
  --primary-soft:  {turquoise_tint};
  --accent:        {purple};
  --accent-hover:  {purple_hover};
  --accent-soft:   {purple_tint};
  --border:        {rule};
  --border-strong: {rule_strong};
  /* No data/brand.json equivalent: no original Anonymous drew ever needed a
   * rejection colour or a soft informational one. */
  --danger:        {danger};
  --info:          {info};
  --select:        {select};
"""


def render_app_root_block(charter: dict[str, Any]) -> str:
    """The generated inner text of `app/src/design/tokens.css`'s `:root` block."""
    colours = _colours(charter)
    return _APP_ROOT_TEMPLATE.format(
        white=colours["white"],
        cream=colours["cream"],
        turquoise_tint=colours["turquoise_tint"],
        ink=colours["ink"],
        ink_muted=colours["ink_muted"],
        ink_faint=colours["ink_faint"],
        turquoise=colours["turquoise"],
        turquoise_text=colours["turquoise_text"],
        purple=colours["purple"],
        purple_hover=colours["purple_hover"],
        purple_tint=colours["purple_tint"],
        rule=colours["rule"],
        rule_strong=colours["rule_strong"],
        danger=_DANGER,
        info=_INFO,
        select=rgba(colours["turquoise"], _APP_SELECT_ALPHA),
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
#: them -- see `convener_ops/brand_templates.py` for what they are and why they
#: had to stop being drawn.
_TARGETS: Final = (
    _Target(SITE_CSS_PATH, render_site_css),
    _Target(APP_TOKENS_CSS_PATH, render_app_tokens_css),
    _Target(ANNOUNCEMENT_SVG_PATH, brand_templates.render_announcement_template),
    _Target(FLYER_SVG_PATH, brand_templates.render_flyer_template),
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

    # The palette first, and unconditionally -- writing or checking. A
    # measurement that no longer recomputes, or one that recomputes below
    # AA, is not a file that needs regenerating: it is a palette that must
    # not build, whichever of the two files it came from. Phase 7 put the
    # `--check` here precisely so that a default palette could ship at all
    # (see brand/convener/brand.json's own `_why_a_default`), and a check
    # that only compared files against a JSON document would have carried
    # none of that promise.
    contrast = brand.contrast_problems(brand.load(root), named=named)
    if contrast:
        for problem in contrast:
            print(problem, file=sys.stderr)
        print(
            "A palette that does not clear AA does not build. Fix the "
            f"colours in {named}, or the ratio beside them.",
            file=sys.stderr,
        )
        return 1
    print(f"every measured contrast in {named} recomputes and clears AA")

    problems: list[str] = []
    for target in _TARGETS:
        path = root / target.rel_path
        try:
            rendered = target.render(root)
        except brand.MissingMotifError as exc:
            # Not "this file needs regenerating": nothing can regenerate
            # it. The build stops here rather than reaching for a mark
            # that belongs to somebody else (S-4).
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
