"""The design tokens, derived from `data/brand.json` -- the one source of fact.

`data/brand.json` measured Anonymous's own colours -- turquoise `#FECAC1`, cream
`#F4F0F1`, purple `#012765` -- and the contrast each pairing gives. Every
implementation that draws the identity was still a hand-typed copy of that
file: `site/src/style.css`, `app/src/design/tokens.css` and
`app/src/design/tokens.ts` each carried the same values retyped, and one of
the three -- the application -- had drifted to a reconstruction's palette
without anyone deciding that on purpose (`docs/superpowers/deferred-work.md`,
entry 1). Purple on turquoise measured 4.44 there, below AA; Anonymous's own
value gives 7.93, AAA. One source of fact and three hand-typed copies is
exactly the shape that let that drift happen silently. This script closes it:
the custom properties are generated, and `--check` makes the generation a
fact about the repository rather than a habit somebody might keep up.

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
currently derives. `app/src/design/tokens.ts` holds no hand-authored component
styles at all -- it is pure data -- so it is generated whole, the same
discipline `generate_schema_doc.py` already applies to the handbook's schema
appendix.

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

Contrast is recomputed, not read
---------------------------------
`data/brand.json` also carries measured contrast ratios. This script exposes
the same WCAG 2.1 relative-luminance arithmetic the measurement used
(`relative_luminance`, `contrast_ratio`) so that `test_brand.py` can
recompute every stored ratio from the colours that produce it and fail the
moment the two disagree -- a plausible-sounding number that nobody rechecks
is exactly how the reconstruction's drift went unnoticed for months.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python ../scripts/generate_brand_css.py            # write the files
    uv run python ../scripts/generate_brand_css.py --check    # assert only

As with the schema generator, there is no mode that prints a file, and
nothing this repository's Python writes to a terminal may be non-ASCII.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from convener_ops.paths import repo_root

#: The one source of fact, relative to the repository root.
BRAND_PATH: Final = Path("data") / "brand.json"

SITE_CSS_PATH: Final = Path("site") / "src" / "style.css"
APP_TOKENS_CSS_PATH: Final = Path("app") / "src" / "design" / "tokens.css"
APP_TOKENS_TS_PATH: Final = Path("app") / "src" / "design" / "tokens.ts"

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
    """`data/brand.json`, parsed."""
    return dict(json.loads((root / BRAND_PATH).read_text(encoding="utf-8")))


def _colours(brand: dict[str, Any]) -> dict[str, str]:
    """Every named colour, `colour` and `derived` merged.

    Keys starting with `_` are commentary (`_roles`, `_comment`, ...), not
    colours, and are skipped in both sections.
    """
    merged: dict[str, str] = {}
    for section in ("colour", "derived"):
        for key, value in brand[section].items():
            if not key.startswith("_"):
                merged[key] = value
    return merged


# --------------------------------------------------------------------------
# Colour arithmetic, shared by the generator and by the contrast test
# --------------------------------------------------------------------------


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """A `#rrggbb` string as three 0-255 integers."""
    v = value.lstrip("#")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


def rgba(value: str, alpha: float) -> str:
    """A hex colour as a CSS `rgba(...)` literal at the given alpha."""
    r, g, b = hex_to_rgb(value)
    return f"rgba({r}, {g}, {b}, {alpha})"


def rgb_triplet(value: str) -> str:
    """`r, g, b`, for a custom property an `rgba()` call can reuse."""
    r, g, b = hex_to_rgb(value)
    return f"{r}, {g}, {b}"


def _channel_linear(value: int) -> float:
    """One sRGB channel (0-255), linearised per WCAG 2.1."""
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(value: str) -> float:
    """WCAG 2.1 relative luminance of a `#rrggbb` colour."""
    r, g, b = hex_to_rgb(value)
    return (
        0.2126 * _channel_linear(r)
        + 0.7152 * _channel_linear(g)
        + 0.0722 * _channel_linear(b)
    )


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2.1 contrast ratio between two `#rrggbb` colours, always >= 1."""
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


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
#: one this stylesheet retypes either.
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


def render_site_root_block(brand: dict[str, Any]) -> str:
    """The generated inner text of `site/src/style.css`'s `:root` block."""
    colours = _colours(brand)
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
        rule=colours["rule"],
        rule_strong=colours["rule_strong"],
        select=rgba(colours["turquoise"], _SITE_SELECT_ALPHA),
        white_rgb=rgb_triplet(colours["white"]),
    )


def render_site_css(root: Path) -> str:
    """`site/src/style.css` in full: hand-authored, with its tokens generated."""
    brand = load_brand(root)
    current = (root / SITE_CSS_PATH).read_text(encoding="utf-8")
    return _splice(current, render_site_root_block(brand))


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
  --danger:        {danger};
  --info:          {info};
  --select:        {select};
"""


def render_app_root_block(brand: dict[str, Any]) -> str:
    """The generated inner text of `app/src/design/tokens.css`'s `:root` block."""
    colours = _colours(brand)
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
    brand = load_brand(root)
    current = (root / APP_TOKENS_CSS_PATH).read_text(encoding="utf-8")
    return _splice(current, render_app_root_block(brand))


#: `app/src/design/tokens.ts` holds no hand-authored component styles, so it
#: is generated whole, the way `generate_schema_doc.py` generates
#: `docs/reference/schema.md` whole. `fonts` is written out rather than
#: read from `data/brand.json`'s `typography` block: nothing there had
#: drifted (the reconstruction only ever touched colour), and the two
#: literal font stacks below are the narrative half of this file, in the
#: same sense the prose around `generate_schema_doc.py`'s tables is -- fixed
#: structure, not a fact this script derives.
_TOKENS_TS_TEMPLATE: Final = """\
// Generated by scripts/generate_brand_css.py from data/brand.json.
// Do not edit by hand: run `{command}` from `tools/` and commit what it
// writes.
export const colors = {{
  paper: '{white}', surface: '{white}',
  ink: '{ink}', inkMuted: '{ink_muted}',
  primary: '{turquoise}', primaryHover: '{turquoise_text}',
  accent: '{purple}', border: '{rule}',
  danger: '{danger}', info: '{info}',
}} as const;

export const fonts = {{
  display: '"Archivo", system-ui, sans-serif',
  body: '"Archivo", system-ui, sans-serif',
  mono: '"JetBrains Mono", monospace',
}} as const;
"""


def render_app_tokens_ts(root: Path) -> str:
    """`app/src/design/tokens.ts` in full."""
    brand = load_brand(root)
    colours = _colours(brand)
    return _TOKENS_TS_TEMPLATE.format(
        command=COMMAND,
        white=colours["white"],
        ink=colours["ink"],
        ink_muted=colours["ink_muted"],
        turquoise=colours["turquoise"],
        turquoise_text=colours["turquoise_text"],
        purple=colours["purple"],
        rule=colours["rule"],
        danger=_DANGER,
        info=_INFO,
    )


# --------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Target:
    """One generated file: where it lives, and how to render it."""

    rel_path: Path
    render: Callable[[Path], str]


_TARGETS: Final = (
    _Target(SITE_CSS_PATH, render_site_css),
    _Target(APP_TOKENS_CSS_PATH, render_app_tokens_css),
    _Target(APP_TOKENS_TS_PATH, render_app_tokens_ts),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=("Generate CSS/TypeScript design tokens from data/brand.json.")
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if a committed file is not what "
        "data/brand.json derives",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    problems: list[str] = []
    for target in _TARGETS:
        path = root / target.rel_path
        try:
            rendered = target.render(root)
        except (FileNotFoundError, ValueError) as exc:
            problems.append(f"{target.rel_path.as_posix()}: {exc}")
            continue

        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != rendered:
                problems.append(
                    f"{target.rel_path.as_posix()} is not what "
                    f"{BRAND_PATH.as_posix()} derives."
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
        print(f"every generated file matches {BRAND_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
