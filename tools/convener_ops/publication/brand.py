"""The charter: the system ships with the product, the values stay with the
instance, and the design ships whole rather than being demanded.

Three things used to read `instance/data/brand.json`, each with its own two-line
loader: `tools/scripts/generate_brand_css.py` for the two stylesheets,
the ribbon for the motif, `visual.py` for the colours. Three loaders were
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
ink the headlines, the motif and the wordmark are drawn in; `field` is
the saturated ground that fills the page; `band` is the full-width
horizontal bands laid across it. Three of them used to be `purple`,
`turquoise` and `cream`, after the hues of the first palette anybody
measured -- and the product's own charter holds a navy under `purple` and
a coral under `turquoise`. `SUPERSEDED_COLOURS` below still knows those
three spellings, so that a charter written before the rename is answered
by name and told which key became which, rather than raising a `KeyError`
inside a template.

**A default palette is the product's too**, `assets/brand/convener/brand.json`,
so that a duplicate looks finished at its first build rather than grey. It
is the product's own colours (`assets/brand/convener/README.md`), and it clears
the same AA floor under the same `--check`; a palette that does not is a
palette that does not build.

**The values are the instance's**, `instance/data/brand.json`, and
`declarations/boundary.yml` hands that whole directory to the instance. Nothing
about this instance's own colours moved: the file is what it was.

**A duplicate with nobody to draw for it names one instead of writing
one.** `assets/brand/` holds several charters now, and until `charter` there was
no way to build with any but the first: choosing the lattice meant copying
`assets/brand/lattice/brand.json` into `instance/data/`, which forks a product
file into a duplicate's tree on the commit that copies it -- every later
correction to that charter, a contrast remeasured or a token renamed,
arrives as a merge conflict on a file the duplicate now owns, which is the
opposite of what `assets/brand/` is for. So the choice is a name in
`instance/config.json` (`published.CHARTER_KEY`) and the file stays where
upstream maintains it. `source` below is where the three answers -- named,
written, neither -- are settled, and where naming both is refused.

**`motif` has a default too, and its absence used to be the decision.**
`motif` names the drawing (`family`), the colour it is stroked in, how
wide that stroke is drawn, and the colour of the wordmark's dots. It
carried no default at first, on the
reasoning that a mark somebody drew must not be lent to a duplicate that
forgot to configure one. The first half of that is right and is not
negotiable; the second does not follow from it, and what it produced was
a fresh clone whose build stopped, demanding a design file, before it had
ever drawn anything. So the line sits elsewhere now, and it is a line
about *what kind of value* it is rather than about which file it is in:
**identity has to be supplied -- an organisation's name, its published
address, the title of its series, none of which anything can guess -- and
design never does.** The product's own motif is in
`assets/brand/convener/brand.json` beside the palette it belongs with, and what
tells a reader an instance is not configured is `published.unconfigured`
on the public pages, which is the better guard of the two because it
lets somebody watch the product work while they configure it.

**What still refuses is a half-written one.** A `motif` an instance did
write and left incomplete is a mistake rather than a choice -- a drawing
with no colour of its own would be inked in whatever happened to surround
it -- so `motif()` names the file and the missing fields instead of
quietly filling them from somewhere else. Absence is answered;
incompleteness is refused. The same refusal covers the product's own
charter losing its `motif`, which is the product being broken rather than
an instance being unconfigured, and says so.

**And a `motif` written in the shape that had one drawing.** While
`ribbon.py` was the only mark there was, the section held `ribbon_stroke`
and `ribbon_width_ratio` and named no family at all -- two field names
that could only ever be true of that one drawing, and a section that
could not say which drawing it meant. `SUPERSEDED_MOTIF_FIELDS` still
knows those two spellings, and a section carrying no `family` is answered
the same way, so a charter written before the rename is told
which two fields to rename rather than meeting a `KeyError` inside a
template. A
`family` naming a drawing this product does not have is refused by
`publication/motifs/` itself, which lists the ones it does.

The arithmetic lives here, not in the generator
-------------------------------------------------
WCAG 2.1 relative luminance and contrast are needed on both sides: by
`generate_brand_css.py`, which refuses to write a stylesheet from a
palette that fails AA, and by `visual.py`, which is inside
this package and cannot import `tools/scripts/` (`tools/pyproject.toml`'s wheel
ships `convener_ops` alone). One implementation, imported by the script, rather
than the script owning it and the package doing without.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from ..declaration import published
from ..declaration.paths import DATA_DIR
from . import motifs

__all__ = [
    "AA_NORMAL_TEXT",
    "DEFAULT_PATH",
    "INSTANCE_PATH",
    "MOTIF_COMMON_FIELDS",
    "MOTIF_FAMILY",
    "MOTIF_FIELDS",
    "MOTIF_KEY",
    "SHIPPED_DIR",
    "SHIPPED_FILE",
    "SUPERSEDED_COLOURS",
    "SUPERSEDED_MOTIF_FIELDS",
    "AmbiguousCharterError",
    "MissingMotifError",
    "SupersededCharterError",
    "UnknownCharterError",
    "charter",
    "chosen",
    "colours",
    "contrast_problems",
    "contrast_ratio",
    "declared",
    "hex_to_rgb",
    "load",
    "motif",
    "motif_family",
    "motif_stroke",
    "motif_width_ratio",
    "names",
    "relative_luminance",
    "rgb_triplet",
    "rgba",
    "shipped",
    "source",
]

#: The instance's own values, relative to a repository root. Optional: a
#: duplicate that has not chosen its colours yet simply does not have this
#: file, and `declarations/boundary.yml` hands the directory it sits in to the
#: instance so that upstream never edits it.
INSTANCE_PATH: Final = DATA_DIR / "brand.json"

#: Where the charters this product ships live, one directory each. The
#: product's own is `assets/brand/convener/`, beside the mark it belongs to; the
#: rest are palettes a duplicate with nobody to draw for it may choose
#: instead of writing its own.
SHIPPED_DIR: Final = Path("assets") / "brand"

#: The file each of those directories holds.
SHIPPED_FILE: Final = "brand.json"

#: The product's own, shipped with the code and never edited by an
#: instance. Beside the mark it belongs to (`assets/brand/convener/`) rather than
#: in a directory of its own, so the product's default and the product's
#: mark are one identity instead of two.
DEFAULT_PATH: Final = SHIPPED_DIR / "convener" / SHIPPED_FILE

#: The design section. `assets/brand/convener/brand.json` carries one, so an
#: instance never has to; what it may not do is write half of one.
MOTIF_KEY: Final = "motif"

#: The field that names the drawing. Every other field in the section says
#: how that drawing is inked, and `publication/motifs/` is where a name
#: becomes one -- see that package for why a charter names a family rather
#: than a module importing one.
MOTIF_FAMILY: Final = "family"

#: What a `motif` carries whatever it draws: the drawing's own name, and
#: the colour of the dot the lock-up beside the wordmark closes on, which
#: belongs to that device rather than to the drawing.
MOTIF_COMMON_FIELDS: Final = (MOTIF_FAMILY, "logo_dots")

#: What a complete `motif` carries, per family. A flat tuple until the
#: motif became a choice: `ribbon_stroke` and `ribbon_width_ratio` could
#: only ever be true of one drawing, and a family that is not a stroked
#: line declares different fields, so the family says which ones it wants
#: and this reads them off the registry rather than holding a second list
#: that could disagree with it.
MOTIF_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    name: (*MOTIF_COMMON_FIELDS, *drawn.fields)
    for name, drawn in motifs.FAMILIES.items()
}

#: The two field names a `motif` carried while there was one drawing, and
#: what each became. Both name the ink rather than the drawing -- the
#: colour the motif is stroked in, and that stroke's weight as a fraction
#: of the composition's shorter side -- so both stay true of a drawing that
#: is not the ribbon, and neither keeps the ribbon's name.
SUPERSEDED_MOTIF_FIELDS: Final = {
    "ribbon_stroke": "stroke",
    "ribbon_width_ratio": "width_ratio",
}

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
#: The refusal below reads this table, so the rename it asks for and the
#: names it refuses can never disagree about which moved where.
SUPERSEDED_COLOURS: Final = {
    "purple": "dominant",
    "turquoise": "field",
    "cream": "band",
}


class SupersededCharterError(RuntimeError):
    """A charter still written in a shape this product has moved past.

    Two of them, and one sentence covers both: the keys are the system's,
    and every template reads a colour and a motif field by name, so a file
    under the old names answers none of the names anything asks for.
    Colours named after hues is the first; a `motif` under the ribbon's own
    field names, or naming no family at all, is the second. A duplicate
    that updates without renaming its own keys would otherwise meet a
    `KeyError` raised from inside a format string, which names neither the
    file to open nor the key to write.

    Carries the whole message rather than a code, for the reason
    `MissingMotifError` gives.
    """


class UnknownCharterError(RuntimeError):
    """An `instance/config.json::charter` naming a charter this product
    does not ship.

    Never a fall back to the product's own: a duplicate that misspelt
    `chevrons` and got the default would build, look finished, and be
    wearing a design nobody chose -- which is the defect
    `motifs.UnknownMotifFamilyError` exists to prevent one layer down, and
    this is the same refusal at the layer above it. Lists the charters
    that do exist, for the same reason: the thing a person needs at the
    moment a build stops is what they may write instead.

    Carries the whole message rather than a code, for the reason
    `MissingMotifError` gives.
    """


class AmbiguousCharterError(RuntimeError):
    """An instance that both named a charter and wrote one of its own.

    Two declarations of one notion, free to disagree, which is the defect
    this repository refuses everywhere else. Whichever of the two won, the
    other would be a value sitting in a committed file doing nothing --
    the state D-16's drift lived in for months. So neither wins and the
    build stops, naming both files and the one line to delete.

    The two routes are both legitimate on their own, and the message says
    so: a duplicate with nobody to draw for it names one of the product's
    charters, and a duplicate with a designer writes
    `instance/data/brand.json` and names none.
    """


class MissingMotifError(RuntimeError):
    """A `motif` that was written and left half-finished.

    Not "no `motif`": an absent one is answered by the product's own, and
    `motif` below says why. Not a superseded one either, which
    `SupersededCharterError` answers by name. This is the case nothing can
    answer -- a section somebody wrote, missing a field the family it names
    declares, which no default may quietly complete without inventing a
    value that appears in no file.

    Carries the whole message rather than a code: the thing a person needs
    at the moment a build stops is what is missing and where to put it,
    and a caller that had to compose that sentence itself would compose it
    differently in each of the three places this can surface.
    """


def shipped(root: Path) -> tuple[Path, ...]:
    """Every charter this product ships, root-relative, in name order.

    Read off `assets/brand/` rather than written down, for the reason
    `motifs.FAMILIES` gives about the directory beside it: a charter that
    has to be added to a list somewhere is a charter somebody forgets to
    add, and what it is forgotten by is the sweep that would have caught
    it. `cli.render_template_fixtures` renders every one of these against
    every family, and `generate_brand_css.py` recomputes every one of
    their contrasts, both with no entry to make anywhere.

    A directory under `assets/brand/` holding no `brand.json` is artwork rather
    than a charter and is passed over; `assets/brand/convener/` holds both.
    """
    found = sorted((root / SHIPPED_DIR).glob(f"*/{SHIPPED_FILE}"))
    return tuple(path.relative_to(root) for path in found)


def names(root: Path) -> str:
    """Every charter that exists, for a message that has to list them.

    Off `shipped` above, so a charter committed tomorrow is offered by
    every refusal on the commit that adds it.
    """
    return ", ".join(rel.parent.name for rel in shipped(root))


def declared(root: Path) -> str | None:
    """The name `instance/config.json` writes under `charter`, or `None`.

    Absence answered twice, and neither is a fall back. A declaration that
    carries no `charter` names none, which is `published.charter_from_data`
    saying so. A tree carrying *no declaration at all* names none either:
    a charter reader needs a charter, and `tests/publication/test_motif.py`
    builds a root holding one file and nothing else to prove a family
    dispatches. That second tolerance covers absence and stops there -- a
    `charter` somebody wrote is always answered, by `charter_from_data` if
    it is not a name and by `chosen` below if it is not one of ours -- and
    a tree missing this declaration is refused by every other reader of it
    (`published.load`, `load_identity`, `load_edition_prefix`), each for
    its own reason.
    """
    if not (root / published.INSTANCE_PATH).is_file():
        return None
    return published.load_charter(root)


def chosen(root: Path) -> Path | None:
    """The charter this instance's declaration names, root-relative, or
    `None` when it names none.

    The name comes from `instance/config.json` (`published.CHARTER_KEY`,
    which says why it is declared there); this is where it becomes a file.
    A name is only ever answered by matching it against `shipped` above,
    never by building a path out of it, so a declaration cannot address a
    file `assets/brand/` does not hold however it is spelt.
    """
    name = declared(root)
    if name is None:
        return None
    return _shipped_as(root, name)


def _shipped_as(root: Path, name: str) -> Path:
    """`assets/brand/<name>/brand.json`, or a refusal naming the charters there
    are -- `motifs.family`'s own shape, one layer up."""
    for rel in shipped(root):
        if rel.parent.name == name:
            return rel
    known = names(root)
    listed = (
        f"The charters it ships are: {known}."
        if known
        else f"It ships none at all, which is {SHIPPED_DIR.as_posix()}/ being "
        "broken rather than this declaration being wrong."
    )
    raise UnknownCharterError(
        f"{published.INSTANCE_PATH.as_posix()}: {published.CHARTER_KEY} names "
        f"{name!r}, which is not a charter this product ships. {listed} "
        f"Delete the key to be drawn with the product's own "
        f"({DEFAULT_PATH.as_posix()})."
    )


def source(root: Path) -> Path:
    """Which charter `load` will read, root-relative.

    Three answers, in the order this asks for them.

    1. **The declaration names one of the product's**, `charter` in
       `instance/config.json`: `assets/brand/<name>/brand.json`, read where
       upstream maintains it. A duplicate that wanted the lattice used to
       have to copy that file into `instance/data/`, which forks it: the
       copy stops tracking upstream on the commit that makes it, and every
       later correction to that charter arrives as a conflict on a file
       the duplicate now owns.
    2. **This instance wrote its own**, `instance/data/brand.json`: that
       file. A duplicate with a designer keeps the route it has always
       had, and nothing about this instance's own charter moved.
    3. **Neither**: the product's own, `DEFAULT_PATH`, which is the whole
       of `assets/brand/convener/brand.json::_why_a_default` and is not weakened
       by the key above. Design is never something a person has to supply
       before the thing will run.

    **Both is refused**, and the refusal is what makes the three above a
    rule. Either answer would leave the other declaration sitting in a
    committed file doing nothing, which is the shape this repository keeps
    meeting -- one notion, two homes, free to disagree. Refused ahead of
    an unknown name, because when both are wrong the key is what has to go
    either way.

    Separate from `load` so that a message can name the file the values
    actually came from: a contrast that no longer recomputes and a
    `motif` left half-written are both reported against the file somebody
    has to open.
    """
    name = declared(root)
    wrote_one = (root / INSTANCE_PATH).is_file()
    if name is None:
        return INSTANCE_PATH if wrote_one else DEFAULT_PATH
    if wrote_one:
        raise AmbiguousCharterError(
            f"{published.INSTANCE_PATH.as_posix()} names the {name!r} charter "
            f"and {INSTANCE_PATH.as_posix()} is a charter this instance wrote "
            "itself. One of the two is the design in force and nothing here "
            f"chooses between them. Delete the {published.CHARTER_KEY!r} key "
            f"to be drawn with the file, or delete "
            f"{INSTANCE_PATH.as_posix()} to be drawn with the charter that "
            "key names."
        )
    return _shipped_as(root, name)


def load(root: Path) -> dict[str, Any]:
    """The charter in force: the instance's values if it has any, the
    product's default otherwise.

    Whole file or whole file, never a merge of the two. Ownership in this
    repository is a property of a *file* (`declarations/boundary.yml`), and a
    half-merged charter would be a third set of values nobody chose --
    an instance that overrode two colours and inherited six would be
    measured against a palette that exists in no file.
    """
    return _checked(root, source(root))


def charter(root: Path, rel: Path) -> dict[str, Any]:
    """One named charter, parsed, with every superseded spelling refused.

    `load` above answers "which values is this build drawn from"; this
    answers "what does that file say", for the one caller that has to read
    a charter no build is drawn from -- `generate_brand_css.py`, which
    recomputes the contrasts of every palette this product ships and not
    only of the one in force. A palette a duplicate may choose has to
    clear AA before anybody chooses it.
    """
    return _checked(root, rel)


def _checked(root: Path, rel: Path) -> dict[str, Any]:
    """One charter file, parsed, with every superseded spelling refused.

    Both refusals run here rather than at each lookup: the alternative is
    one `KeyError` per template, each of them the first thing a duplicate
    sees after an upgrade and none of them naming the migration. `motif`
    reads the product's own charter through this too, so a default written
    in the old shape is answered the same way as an instance's.
    """
    charter = _read(root, rel)
    named = rel.as_posix()
    _refuse_superseded_names(charter, named=named)
    _refuse_superseded_motif(charter.get(MOTIF_KEY), named=named)
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
        "template reads a colour by that name. Rename the keys in the file; "
        "no value changes."
    )


def _refuse_superseded_motif(section: Any, *, named: str) -> None:
    """Stop on a `motif` written for the one drawing there used to be.

    Three shapes, and the first two ask for the same rename. A section
    still under `ribbon_stroke` and `ribbon_width_ratio` names the ink
    after the drawing, which is the defect the colour keys had one section
    higher up. A section naming no `family` cannot say which drawing it
    means, and guessing the ribbon is exactly the silent fall back the
    registry exists to refuse. A `family` this product cannot draw is the
    registry's own refusal, prefixed here with the file that wrote it.

    A section that is not an object at all is left to `motif`, which
    answers it as the half-written one it is.
    """
    if not isinstance(section, dict):
        return

    found = sorted(key for key in section if key in SUPERSEDED_MOTIF_FIELDS)
    if found:
        moved = ", ".join(
            f"{old} -> {new}" for old, new in SUPERSEDED_MOTIF_FIELDS.items()
        )
        raise SupersededCharterError(
            f"{named} names its {MOTIF_KEY} fields after the ribbon "
            f"({', '.join(found)}). The section names the drawing it wants "
            f"now ({MOTIF_FAMILY}), and the colour and weight it is stroked "
            f"in are the same two fields whatever that drawing is ({moved}). "
            "Rename the two keys in the file and add the family beside them; "
            "no value changes."
        )

    if MOTIF_FAMILY not in section:
        raise SupersededCharterError(
            f"{named} has a {MOTIF_KEY!r} section naming no {MOTIF_FAMILY!r}. "
            f"A charter says which drawing it wants by name ({motifs.names()}) "
            "now, and drawing whichever one this product happens to have "
            "would hand a duplicate a "
            "mark it never asked for. Add the family to the section; no "
            "value changes."
        )

    try:
        motifs.family(str(section[MOTIF_FAMILY]))
    except motifs.UnknownMotifFamilyError as unknown:
        raise motifs.UnknownMotifFamilyError(f"{named}: {unknown}") from unknown


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
    instance gets its own section or the product's, never one field of
    each.
    """
    named = source(root)
    section = _checked(root, named).get(MOTIF_KEY)
    if section is None and named != DEFAULT_PATH:
        named = DEFAULT_PATH
        section = _checked(root, DEFAULT_PATH).get(MOTIF_KEY)

    wanted = _fields_a_complete_motif_carries(section)
    if isinstance(section, dict):
        missing = [field for field in wanted if field not in section]
        if not missing:
            return dict(section)
    else:
        missing = list(MOTIF_COMMON_FIELDS)

    lacking = ", ".join(missing)
    if named == DEFAULT_PATH:
        raise MissingMotifError(
            f"{DEFAULT_PATH.as_posix()} is the product's own charter and does "
            f"not carry a complete {MOTIF_KEY!r}: missing {lacking}. Every "
            "duplicate that has written no mark of its own is drawn with that "
            "one, so this is the product being broken rather than an instance "
            f"being unconfigured. Restore it, or write a complete {MOTIF_KEY!r} "
            f"object carrying {_how_to_write_one(wanted)} in "
            f"{INSTANCE_PATH.as_posix()} to stand in for it."
        )
    raise MissingMotifError(
        f"{named.as_posix()} has a {MOTIF_KEY!r} section and it is not a "
        f"complete one: missing {lacking}. A drawing with no colour of its own "
        "would be inked in whatever happened to surround it, so half a "
        f"{MOTIF_KEY!r} is refused rather than completed. Either finish it -- "
        f"{_how_to_write_one(wanted)}, see assets/brand/convener/README.md for what "
        "each one is -- or delete the section outright and the product's own "
        f"({DEFAULT_PATH.as_posix()}) is drawn instead."
    )


def _fields_a_complete_motif_carries(section: Any) -> tuple[str, ...]:
    """What this `motif` has to carry, given the family it names.

    A section that names a family the registry knows is held to that
    family's own list. One that names none is past `_refuse_superseded_
    motif` only by not being an object at all, and the two fields every
    motif carries are all that can be said about it without inventing a
    family for it.
    """
    if isinstance(section, dict):
        name = section.get(MOTIF_FAMILY)
        if isinstance(name, str) and name in MOTIF_FIELDS:
            return MOTIF_FIELDS[name]
    return MOTIF_COMMON_FIELDS


def _how_to_write_one(wanted: tuple[str, ...]) -> str:
    """The fields to write, said so that it stays true when the family is
    not known yet: a section that names one is answered with that family's
    own list, and one that names none is answered with what every family
    would want beside the two every motif carries."""
    if wanted != MOTIF_COMMON_FIELDS:
        return ", ".join(wanted)
    declared = "; ".join(
        f"{name} needs {', '.join(drawn.fields)}"
        for name, drawn in sorted(motifs.FAMILIES.items())
    )
    return f"{', '.join(wanted)}, and what that family draws with ({declared})"


def motif_family(root: Path) -> str:
    """Which drawing the charter in force asks for.

    Hand this to `publication/motifs/` to get the geometry; nothing outside
    that package may import a family by name, which is the whole of what
    naming the family in the charter bought.
    """
    return str(motif(root)[MOTIF_FAMILY])


def motif_stroke(root: Path) -> str:
    """The one colour the motif is ever drawn in -- never hand-typed."""
    return str(motif(root)["stroke"])


def motif_width_ratio(root: Path) -> float:
    """Stroke width as a fraction of the canvas's shorter side.

    Each charter says where its own figure comes from, and the two do not
    come from the same place: this instance's was measured off the
    designer's poster (`instance/data/brand.json::motif._width_ratio`), and
    the product's is carried over from the proportion its own mark's inner
    arc is drawn at (`assets/brand/convener/brand.json`).
    """
    return float(motif(root)["width_ratio"])


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
