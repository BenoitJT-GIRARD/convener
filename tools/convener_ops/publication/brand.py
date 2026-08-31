"""The charter: the system ships with the product, the values stay with the
instance, and the design ships whole rather than being demanded.

Three things used to read `instance/data/brand.json`, each with its own two-line
loader: `tools/scripts/generate_brand_css.py` for the two stylesheets,
`ribbon.py` for the motif, `visual.py` for the colours. Three loaders were
harmless while there was exactly one file to load. They stopped being
harmless the moment the file became optional: a duplicate that ships no
`instance/data/brand.json` would have had one reader fall back to the product's own
palette and two others raise `FileNotFoundError`, which is the same defect
this repository keeps meeting -- one notion, several homes, free to
disagree. So the fallback is decided here, once, and the three read it.

What is the product's and what is the instance's
-------------------------------------------------
**The system is the product's.** The token names, the written roles ("the
field is a ground, never a text colour on white"), the obligation that
every measured pairing clears AA, and the `--check` that stops a
stylesheet drifting away from the values -- that is the part with the
engineering in it, and it ships with the code.

**The token names are positions in the composition.** `dominant` is the
ink the headlines, the ribbon and the wordmark are drawn in; `field` is
the saturated ground that fills the page; `band` is the full-width
horizontal bands laid across it. Three of them used to be `purple`,
`turquoise` and `cream`, after the hues of the first palette anybody
measured -- and the product's own charter holds a navy under `purple` and
a coral under `turquoise`. `SUPERSEDED_COLOURS` below still knows those
three spellings, so that a charter written before the rename is answered
by name and pointed at the migration rather than raising a `KeyError`
inside a template.

**A default palette is the product's too**, `brand/convener/brand.json`,
so that a duplicate looks finished at its first build rather than grey. It
is the product's own colours (`brand/convener/README.md`), and it clears
the same AA floor under the same `--check`; a palette that does not is a
palette that does not build.

**The values are the instance's**, `instance/data/brand.json`, and
`config/boundary.yml` hands that whole directory to the instance. Nothing
about this instance's own colours moved: the file is what it was.

**`motif` has a default too, and its absence used to be the decision.**
`motif` is the ribbon's stroke, how wide that stroke is drawn, and the
colour of the wordmark's dots. It carried no default at first, on the
reasoning that a mark somebody drew must not be lent to a duplicate that
forgot to configure one. The first half of that is right and is not
negotiable; the second does not follow from it, and what it produced was
a fresh clone whose build stopped, demanding a design file, before it had
ever drawn anything. So the line sits elsewhere now, and it is a line
about *what kind of value* it is rather than about which file it is in:
**identity has to be supplied -- an organisation's name, its published
address, the title of its series, none of which anything can guess -- and
design never does.** The product's own motif is in
`brand/convener/brand.json` beside the palette it belongs with, and what
tells a reader an instance is not configured is `published.unconfigured`
on the public pages, which is the better guard of the two because it
lets somebody watch the product work while they configure it.

**What still refuses is a half-written one.** A `motif` an instance did
write and left incomplete is a mistake rather than a choice -- a ribbon
with no colour of its own would be drawn in whatever ink happened to
surround it -- so `motif()` names the file and the missing fields instead
of quietly filling them from somewhere else. Absence is answered;
incompleteness is refused. The same refusal covers the product's own
charter losing its `motif`, which is the product being broken rather than
an instance being unconfigured, and says so.

The arithmetic lives here, not in the generator
-------------------------------------------------
WCAG 2.1 relative luminance and contrast are needed on both sides: by
`generate_brand_css.py`, which refuses to write a stylesheet from a
palette that fails AA, and by `visual.py`/`ribbon.py`, which are inside
this package and cannot import `tools/scripts/` (`tools/pyproject.toml`'s wheel
ships `convener_ops` alone). One implementation, imported by the script, rather
than the script owning it and the package doing without.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from ..declaration.paths import DATA_DIR

__all__ = [
    "AA_NORMAL_TEXT",
    "COLOUR_MIGRATION",
    "DEFAULT_PATH",
    "INSTANCE_PATH",
    "MOTIF_FIELDS",
    "MOTIF_KEY",
    "SUPERSEDED_COLOURS",
    "MissingMotifError",
    "SupersededCharterError",
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
INSTANCE_PATH: Final = DATA_DIR / "brand.json"

#: The product's own, shipped with the code and never edited by an
#: instance. Beside the mark it belongs to (`brand/convener/`) rather than
#: in a directory of its own, so the product's default and the product's
#: mark are one identity instead of two.
DEFAULT_PATH: Final = Path("brand") / "convener" / "brand.json"

#: The design section, and the three fields it has to carry wherever it
#: is written. `brand/convener/brand.json` carries one, so an instance
#: never has to; what it may not do is write half of one.
MOTIF_KEY: Final = "motif"
MOTIF_FIELDS: Final = ("ribbon_stroke", "ribbon_width_ratio", "logo_dots")

#: WCAG 2.1's floor for normal text. AAA is 7; nothing here is held to
#: AAA, because the charter records pairings that are legitimately AA.
AA_NORMAL_TEXT: Final = 4.5

#: The two sections that hold colours. Everything else in the file is
#: commentary, measurement or typography.
_COLOUR_SECTIONS: Final = ("colour", "derived")

#: The three colour names a charter carried before the keys named
#: positions, and the position each became. Every reader looks a colour up
#: by name, so a charter still under the old names is a charter nothing
#: here can draw from; this is what lets `load` say that in one sentence.
#: `tools/migrations/migrate_charter_colour_names.py` renames from this
#: same table, so the migration and the refusal can never disagree about
#: which names moved where.
SUPERSEDED_COLOURS: Final = {
    "purple": "dominant",
    "turquoise": "field",
    "cream": "band",
}

#: The command that renames them, quoted in the refusal, as it is run from
#: `tools/`.
COLOUR_MIGRATION: Final = "uv run python migrations/migrate_charter_colour_names.py"


class SupersededCharterError(RuntimeError):
    """A charter whose colours are still named after hues.

    The keys are the system's, and every template reads a colour by name,
    so a file under the old names answers none of the names anything asks
    for. A duplicate that upgrades without running the migration would
    otherwise meet a `KeyError` raised from inside a format string, which
    names neither the file to open nor the command to run.

    Carries the whole message rather than a code, for the reason
    `MissingMotifError` gives.
    """


class MissingMotifError(RuntimeError):
    """A `motif` that was written and left half-finished.

    Not "no `motif`": an absent one is answered by the product's own, and
    `motif` below says why. This is the case nothing can answer -- a
    section somebody wrote, missing a field, which no default may quietly
    complete without inventing a value that appears in no file.

    Carries the whole message rather than a code: the thing a person needs
    at the moment a build stops is what is missing and where to put it,
    and a caller that had to compose that sentence itself would compose it
    differently in each of the three places this can surface.
    """


def source(root: Path) -> Path:
    """Which of the two files `load` will read, root-relative.

    Separate from `load` so that a message can name the file the values
    actually came from: a contrast that no longer recomputes and a
    `motif` left half-written are both reported against the file somebody
    has to open, and which file that is depends on whether this instance
    wrote one at all.
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
    named = source(root)
    charter = _read(root, named)
    _refuse_superseded_names(charter, named=named.as_posix())
    return charter


def _refuse_superseded_names(charter: dict[str, Any], *, named: str) -> None:
    """Stop on a charter whose colours still name hues, and say what to run.

    Checked at the load rather than at each lookup: the alternative is one
    `KeyError` per template, each of them the first thing a duplicate sees
    after an upgrade and none of them naming the migration.
    """
    section = charter.get("colour")
    if not isinstance(section, dict):
        return
    found = sorted(
        key
        for key in section
        for old in SUPERSEDED_COLOURS
        if key == old or key.startswith(f"{old}_")
    )
    if not found:
        return
    moved = ", ".join(f"{old} -> {new}" for old, new in SUPERSEDED_COLOURS.items())
    raise SupersededCharterError(
        f"{named} names its colours after hues ({', '.join(found)}). The "
        f"charter names positions in the composition now ({moved}), and every "
        "template reads a colour by that name. Run "
        f"`{COLOUR_MIGRATION}` from `tools/` to rename them; no value changes."
    )


def _read(root: Path, rel: Path) -> dict[str, Any]:
    """One charter file, parsed. Named so that `motif` can ask for the
    product's own by path when the charter in force does not answer."""
    return dict(json.loads((root / rel).read_text(encoding="utf-8")))


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
    """`motif`, from the charter in force or from the product's own.

    Three answers, and the middle one is the correction of 2026-08-26.

    1. The charter in force carries a complete `motif`: that one, whole.
    2. It carries none at all: the product's own, `DEFAULT_PATH`. An
       instance that has chosen no mark is not a build that must stop --
       it is a build that draws the product's, while
       `published.unconfigured` says on every public page that this
       instance is not configured yet. Design is never something a person
       has to supply before the thing will run; identity is, and that is
       where the refusals in this repository belong.
    3. It carries a `motif` that is not a complete one: refuse, naming
       the file and the fields. Half a section is neither a choice nor an
       absence, and completing it from the default would hand back a
       motif that exists in no file -- the same thing `load` refuses to
       do with colours.

    Case 2 reads the product's charter by path rather than merging it into
    the charter in force, so this stays whole-section-or-whole-section: an
    instance gets its own three values or the product's three, never one
    of each.
    """
    named = source(root)
    section = load(root).get(MOTIF_KEY)
    if section is None and named != DEFAULT_PATH:
        named = DEFAULT_PATH
        section = _read(root, DEFAULT_PATH).get(MOTIF_KEY)

    if isinstance(section, dict):
        missing = [field for field in MOTIF_FIELDS if field not in section]
        if not missing:
            return dict(section)
    else:
        missing = list(MOTIF_FIELDS)

    lacking = ", ".join(missing)
    if named == DEFAULT_PATH:
        raise MissingMotifError(
            f"{DEFAULT_PATH.as_posix()} is the product's own charter and does "
            f"not carry a complete {MOTIF_KEY!r}: missing {lacking}. Every "
            "duplicate that has written no mark of its own is drawn with that "
            "one, so this is the product being broken rather than an instance "
            f"being unconfigured. Restore it, or write a complete {MOTIF_KEY!r} "
            f"object carrying {', '.join(MOTIF_FIELDS)} in "
            f"{INSTANCE_PATH.as_posix()} to stand in for it."
        )
    raise MissingMotifError(
        f"{named.as_posix()} has a {MOTIF_KEY!r} section and it is not a "
        f"complete one: missing {lacking}. A ribbon with no colour of its own "
        "would be drawn in whatever ink happened to surround it, so half a "
        f"{MOTIF_KEY!r} is refused rather than completed. Either finish it -- "
        f"{', '.join(MOTIF_FIELDS)}, see brand/convener/README.md for what "
        "each one is -- or delete the section outright and the product's own "
        f"({DEFAULT_PATH.as_posix()}) is drawn instead."
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
    the state a default must never reach: a palette that does not clear AA
    must not build.

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
