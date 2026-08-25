"""The charter: the system ships with the product, the values stay with the
instance, and the mark refuses rather than substituting.

Three things used to read `data/brand.json`, each with its own two-line
loader: `scripts/generate_brand_css.py` for the two stylesheets,
`ribbon.py` for the motif, `visual.py` for the colours. Three loaders were
harmless while there was exactly one file to load. They stopped being
harmless the moment the file became optional: a duplicate that ships no
`data/brand.json` would have had one reader fall back to the product's own
palette and two others raise `FileNotFoundError`, which is the same defect
this repository keeps meeting -- one notion, several homes, free to
disagree. So the fallback is decided here, once, and the three read it.

What is the product's and what is the instance's
-------------------------------------------------
**The system is the product's.** The token names, the written roles ("the
turquoise is a ground, never a text colour on white"), the obligation that
every measured pairing clears AA, and the `--check` that stops a
stylesheet drifting away from the values -- that is the part with the
engineering in it, and it ships with the code.

**A default palette is the product's too**, `brand/convener/brand.json`,
so that a duplicate looks finished at its first build rather than grey. It
is the product's own colours (`brand/convener/README.md`), and it clears
the same AA floor under the same `--check`; a palette that does not is a
palette that does not build.

**The values are the instance's**, `data/brand.json`, and
`config/boundary.yml` hands that whole directory to the instance. Nothing
about this instance's own colours moved: the file is what it was.

**`motif` has no default at all.** `motif` is the ribbon's stroke and the
logo's dots -- what somebody drew and what people recognise. A default
mark would be worn by every duplicate that forgot to configure one, which
is the definition of a leak rather than of a default: *a default that
leaks when you forget it is not a default, it is a trap.* So `motif` is
absent from `brand/convener/brand.json`, and `motif()` below raises
`MissingMotifError` rather than substituting. Everything that draws the mark
stops, and says what is missing and where to put it (S-4).

The arithmetic lives here, not in the generator
-------------------------------------------------
WCAG 2.1 relative luminance and contrast are needed on both sides: by
`generate_brand_css.py`, which refuses to write a stylesheet from a
palette that fails AA, and by `visual.py`/`ribbon.py`, which are inside
this package and cannot import `scripts/` (`tools/pyproject.toml`'s wheel
ships `convener_ops` alone). One implementation, imported by the script, rather
than the script owning it and the package doing without.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

__all__ = [
    "AA_NORMAL_TEXT",
    "DEFAULT_PATH",
    "INSTANCE_PATH",
    "MOTIF_FIELDS",
    "MOTIF_KEY",
    "MissingMotifError",
    "colours",
    "contrast_problems",
    "contrast_ratio",
    "hex_to_rgb",
    "load",
    "motif",
    "relative_luminance",
    "rgb_triplet",
    "rgba",
    "source",
]

#: The instance's own values, relative to a repository root. Optional: a
#: duplicate that has not chosen its colours yet simply does not have this
#: file, and `config/boundary.yml` hands the directory it sits in to the
#: instance so that upstream never edits it.
INSTANCE_PATH: Final = Path("data") / "brand.json"

#: The product's own, shipped with the code and never edited by an
#: instance. Beside the mark it belongs to (`brand/convener/`) rather than
#: in a directory of its own, so the product's default and the product's
#: mark are one identity instead of two.
DEFAULT_PATH: Final = Path("brand") / "convener" / "brand.json"

#: The section that has no default, and the fields it has to carry.
MOTIF_KEY: Final = "motif"
MOTIF_FIELDS: Final = ("ribbon_stroke", "ribbon_width_ratio", "logo_dots")

#: WCAG 2.1's floor for normal text. AAA is 7; nothing here is held to
#: AAA, because the charter records pairings that are legitimately AA.
AA_NORMAL_TEXT: Final = 4.5

#: The two sections that hold colours. Everything else in the file is
#: commentary, measurement or typography.
_COLOUR_SECTIONS: Final = ("colour", "derived")


class MissingMotifError(RuntimeError):
    """No `motif` section, and there is no default for one.

    Carries the whole message rather than a code: the thing a person needs
    at the moment a build stops is what is missing and where to put it,
    and a caller that had to compose that sentence itself would compose it
    differently in each of the three places this can surface.
    """


def source(root: Path) -> Path:
    """Which of the two files `load` will read, root-relative.

    Separate from `load` so that a message can name the file the values
    actually came from -- "no `motif` in `data/brand.json`" and "no
    `motif`, and you have not written a `data/brand.json` at all" are
    different problems with different fixes.
    """
    return INSTANCE_PATH if (root / INSTANCE_PATH).is_file() else DEFAULT_PATH


def load(root: Path) -> dict[str, Any]:
    """The charter in force: the instance's values if it has any, the
    product's default otherwise.

    Whole file or whole file, never a merge of the two. Ownership in this
    repository is a property of a *file* (`config/boundary.yml`), and a
    half-merged charter would be a third set of values nobody chose --
    an instance that overrode two colours and inherited six would be
    measured against a palette that exists in no file.
    """
    return dict(json.loads((root / source(root)).read_text(encoding="utf-8")))


def colours(brand: dict[str, Any]) -> dict[str, str]:
    """Every named colour, `colour` and `derived` merged.

    Keys starting with `_` are commentary (`_roles`, `_comment`, ...), not
    colours, and are skipped in both sections.
    """
    merged: dict[str, str] = {}
    for section in _COLOUR_SECTIONS:
        for key, value in brand[section].items():
            if not key.startswith("_"):
                merged[key] = str(value)
    return merged


def motif(root: Path) -> dict[str, Any]:
    """`motif`, or a refusal naming what is missing and where to put it.

    The one section of the charter with no product default. A duplicate
    that has configured nothing must not wear another organisation's
    ribbon and dots, so everything that draws them stops here rather than
    reaching for a substitute.
    """
    brand = load(root)
    named = source(root).as_posix()
    section = brand.get(MOTIF_KEY)
    if isinstance(section, dict):
        missing = [field for field in MOTIF_FIELDS if field not in section]
        if not missing:
            return dict(section)
        lacking = ", ".join(missing)
    else:
        lacking = ", ".join(MOTIF_FIELDS)

    where = (
        f"{named} has no complete {MOTIF_KEY!r} section"
        if named == INSTANCE_PATH.as_posix()
        else f"there is no {INSTANCE_PATH.as_posix()}, and the product's own "
        f"charter ({named}) deliberately carries no {MOTIF_KEY!r} section"
    )
    raise MissingMotifError(
        f"{where}: missing {lacking}. The ribbon's stroke and the logo's dots "
        "are a signature, not a colour, so the product ships no default for "
        "them -- a duplicate that configures nothing must not wear another "
        f"organisation's mark. Add a {MOTIF_KEY!r} object carrying "
        f"{', '.join(MOTIF_FIELDS)} to {INSTANCE_PATH.as_posix()} "
        "(see brand/convener/README.md for what each one is)."
    )


# --------------------------------------------------------------------------
# Colour arithmetic, shared by the generator, the visuals and the tests
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


def contrast_problems(brand: dict[str, Any], *, named: str) -> list[str]:
    """Every way the charter's own `contrast` table is not the truth.

    Two failures, and they are different failures. A ratio that does not
    recompute from the two colours beside it is a *measurement* nobody
    rechecked -- exactly how D-16's drift survived for months, on the
    strength of a plausible-sounding number. A ratio that recomputes
    correctly and sits below 4.5 is a *palette* that fails AA, which is
    the state the spec forbids a default from ever reaching: "a palette
    that does not clear AA must not build".

    Both are checked at the command rather than only in the test suite,
    because the palette a duplicate builds with is not one this
    repository's tests ever see.
    """
    named_colours = colours(brand)
    problems: list[str] = []
    for name, stored in brand["contrast"].items():
        if name.startswith("_"):
            continue
        fg, _, bg = name.rpartition("_on_")
        if fg not in named_colours or bg not in named_colours:
            problems.append(f"{named}: contrast.{name} names no such colour")
            continue
        computed = round(contrast_ratio(named_colours[fg], named_colours[bg]), 2)
        if computed != stored:
            problems.append(
                f"{named}: contrast.{name} claims {stored}, "
                f"{named_colours[fg]} on {named_colours[bg]} computes to {computed}"
            )
        elif computed < AA_NORMAL_TEXT:
            problems.append(
                f"{named}: contrast.{name} is {computed}, below the "
                f"{AA_NORMAL_TEXT} WCAG AA needs for normal text"
            )
    return problems
