"""One-shot migration of every `brand.json` in this repository: `motif`
names the drawing it wants, and the two fields that named the ribbon are
renamed to what they actually hold.

`motif` carried three fields -- `ribbon_stroke`, `ribbon_width_ratio` and
`logo_dots` -- and `convener_ops/publication/ribbon.py` drew one hard-coded
drawing, so the section could not say which mark it meant. Two of those
three names were the ribbon's:

    ribbon_stroke        -> stroke        the colour the motif is drawn in
    ribbon_width_ratio   -> width_ratio   that stroke's weight, as a
                                          fraction of the composition's
                                          shorter side

Neither is a property of the ribbon. Every family this product draws is a
stroked drawing inked from those same two values, so a charter whose motif
is a lattice would have been writing `ribbon_stroke` -- the exact defect
the colour keys had one section higher up, where `purple` held a navy.

`logo_dots` keeps its name. It is the colour of the four filled squares in
the wordmark, which belongs to the wordmark and not to the drawing beside
it.

What the section gains
-----------------------
`family`, written first, holding `ribbon`. It is the field that says which
drawing the charter wants, and `convener_ops/publication/motifs/` is where
that name is answered. Every charter written before this migration drew the
one drawing there was, so `ribbon` is what each of them meant -- this
invents nothing.

The commentary follows its own field
-------------------------------------
`_ribbon_stroke` and `_ribbon_width_ratio` are the paragraphs written
beside those two fields, and a commentary key naming a field that no longer
exists is the same defect one line down; they become `_stroke` and
`_width_ratio`. `_ribbon` describes the drawing itself -- "one continuous
meandering stroke" -- which is what `family` now names, so it becomes
`_family`. `_logo_dots` is untouched, because its own field is.

Three charters, not one
------------------------
`brand/convener/brand.json` is the product's own, the palette and mark a
duplicate builds with before it has chosen anything. `instance/data/
brand.json` is this instance's. `instances/example/instance/data/brand.json`
is the worked example `tools/tests/test_second_instance.py` builds the whole
repository as. All three answer the same names, because the *system* is the
product's and every template reads a motif field by name.

`instance/data/brand.json` is optional -- a duplicate that has chosen no
design has no such file -- so a charter that is not there is reported and
skipped rather than treated as an error.

**No value changes, and no prose.** Only key names, in place, plus the one
line that writes the family down, so the diff reads as a renamed line
rather than a section rewritten. The parade is that every rendered artefact
is the same byte for byte afterwards. The commentary these files carry is
left exactly as it stands: a migration that rewrote English would bury the
rename it exists to make reviewable, and the prose in an instance's charter
is that instance's.

**Idempotent.** The rewrite is driven by which keys are still under the old
names and by whether the section names a family at all, so a charter
already carrying the new shape is left alone down to the byte and says so.
A migration that refused its own second run could not be replayed inside an
upgrade script.

**A charter carrying both names for one field is refused, never merged.**
Only a hand edit can produce one, the two values can disagree, and choosing
between them is a decision about what to draw with -- not a migration's to
take.

**Reversible**, and deliberately without a flag for it. The inverse is the
same rewrite with the pairs swapped and the `family` line deleted. Nothing
else is dropped and nothing is invented, so there is no information an undo
would have to reconstruct.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python migrations/migrate_motif_family.py --dry-run
    uv run python migrations/migrate_motif_family.py
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, motifs

#: The section this migration touches, and the field it gains. Read from
#: the reader that has to refuse a charter still under the old shape,
#: rather than written again here.
SECTION: Final = brand.MOTIF_KEY
FAMILY: Final = brand.MOTIF_FAMILY

#: The family every charter written before this migration meant: there was
#: one drawing, and `motifs.RIBBON` is it.
DRAWN: Final = motifs.RIBBON.name

#: The two fields that moved, old to new -- read from the same refusal, so
#: that the migration and the refusal can never disagree about which name
#: became which.
FIELDS: Final = brand.SUPERSEDED_MOTIF_FIELDS

#: The commentary key that describes the drawing rather than one of its
#: fields, and the field that names the drawing now.
DESCRIPTION: Final = {f"_{DRAWN}": f"_{FAMILY}"}

#: Every key this migration renames: the two fields, the paragraph written
#: beside each of them, and the one that describes the drawing itself.
RENAMES: Final = {
    **FIELDS,
    **{f"_{old}": f"_{new}" for old, new in FIELDS.items()},
    **DESCRIPTION,
}

#: The three charters this repository ships. `brand/convener/brand.json` is
#: the product's own and is always there; the other two are an instance's,
#: and the first of them is optional by design.
CHARTERS: Final = (
    brand.DEFAULT_PATH,
    brand.INSTANCE_PATH,
    Path("instances") / "example" / brand.INSTANCE_PATH,
)


class MigrationRefusedError(RuntimeError):
    """A charter this migration will not rewrite, with the whole reason.

    The message rather than a code, for the reason
    `brand.MissingMotifError` gives: what a person needs at the moment a
    migration stops is which file holds what, not a symbol to look up.
    """


def rename(name: str) -> str:
    """One key under its new name, or unchanged.

    An exact table rather than the prefix arithmetic
    `migrate_charter_colour_names.py` uses: a colour name is a word other
    keys are built on (`purple_hover`, `white_on_purple`), and these three
    are not -- `ribbon_stroke` becomes `stroke` and not `family_stroke`,
    which is what a prefix rewrite would have made of it.
    """
    return RENAMES.get(name, name)


#: One key at the start of a line, at any indentation: a charter writes
#: every key that way, and no value can be mistaken for one. The prose in
#: these files says `ribbon` many times over -- inside string values, which
#: never begin a line -- and none of it is rewritten.
_KEY_LINE: Final = re.compile(
    r'^(?P<indent>[ \t]*)"(?P<key>[^"]+)"(?=\s*:)', re.MULTILINE
)

#: The line that opens the section, and the indentation of whatever follows
#: it -- which is the indentation the new field is written at, read off the
#: file rather than assumed, so a charter indented differently still comes
#: out looking like itself.
_SECTION_OPEN: Final = re.compile(
    rf'(?P<open>^[ \t]*"{re.escape(SECTION)}"[ \t]*:[ \t]*\{{[ \t]*\n)'
    r"(?P<inner>[ \t]*)",
    re.MULTILINE,
)


def _section_of(charter: dict[str, Any], *, where: str) -> dict[str, Any]:
    """The `motif` object, or a refusal naming the file."""
    body = charter.get(SECTION)
    if not isinstance(body, dict):
        raise MigrationRefusedError(
            f"{where} has no {SECTION!r} object; this is not a charter"
        )
    return body


def _renamed_keys(mapping: dict[str, Any], *, where: str) -> dict[str, str]:
    """Every key in the section that changes, old name to new.

    Refuses a section carrying a key under both names: the two can hold
    different values, and which one the mark is drawn with is not a
    decision a migration may take.
    """
    changed = {key: rename(key) for key in mapping if rename(key) != key}
    for old, new in changed.items():
        if new in mapping:
            raise MigrationRefusedError(
                f"{where} carries both {old} ({mapping[old]!r}) and "
                f"{new} ({mapping[new]!r}); only a hand edit can write both, "
                f"and which one to draw with is not a migration's "
                f"decision -- delete the one that is wrong and run this again"
            )
    return changed


def _check_only_the_motif_changed(
    before: dict[str, Any], after: dict[str, Any], *, where: str
) -> None:
    """The post-condition, checked on the parsed charters rather than on
    the text: every section in the same order, nothing outside `motif`
    touched, every key inside it under the name `rename` gives it, every
    value identical, and `family` holding the one drawing there was.

    A regular expression rewriting a data file has to prove it rewrote what
    it meant to. This is that proof, and it runs on every file every time
    rather than only in the tests.
    """
    if list(after) != list(before):
        raise MigrationRefusedError(
            f"{where}: the rewrite changed the sections of the file: "
            f"expected {list(before)}, got {list(after)}"
        )
    for name, body in before.items():
        if name != SECTION and after[name] != body:
            raise MigrationRefusedError(
                f"{where}: the rewrite changed {name!r}, which is not the "
                f"{SECTION!r} section"
            )

    was = _section_of(before, where=where)
    now = _section_of(after, where=where)
    expected = {rename(key): value for key, value in was.items()}
    if FAMILY not in was:
        expected = {FAMILY: DRAWN, **expected}
    if list(now) != list(expected):
        raise MigrationRefusedError(
            f"{where}: the rewrite changed the keys of {SECTION!r}: "
            f"expected {list(expected)}, got {list(now)}"
        )
    if now != expected:
        raise MigrationRefusedError(
            f"{where}: the rewrite changed a value in {SECTION!r}"
        )


def migrate_charter_text(text: str, *, where: str) -> str:
    """One `brand.json`, with its `motif` naming the drawing it wants.

    Text in, text out: these files carry paragraphs of commentary and blank
    lines between the groups of colours, and neither survives a
    load-and-dump round trip. A charter already carrying the new shape is
    returned unchanged, which is what makes a second run a no-op.
    """
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise MigrationRefusedError(f"{where}: top-level must be an object")

    section = _section_of(loaded, where=where)
    changed = _renamed_keys(section, where=f"{where}: {SECTION}")
    needs_family = FAMILY not in section
    if not changed and not needs_family:
        return text

    def one_line(match: re.Match[str]) -> str:
        key = match.group("key")
        return f'{match.group("indent")}"{changed.get(key, key)}"'

    migrated = _KEY_LINE.sub(one_line, text, count=0)
    if needs_family:
        migrated = _write_the_family_down(migrated, where=where)
    _check_only_the_motif_changed(loaded, json.loads(migrated), where=where)
    return migrated


def _write_the_family_down(text: str, *, where: str) -> str:
    """`family` as the section's first field, at the indentation the file
    already writes its own fields at."""

    def opened(match: re.Match[str]) -> str:
        inner = match.group("inner")
        return f'{match.group("open")}{inner}"{FAMILY}": "{DRAWN}",\n{inner}'

    migrated, count = _SECTION_OPEN.subn(opened, text, count=1)
    if count != 1:
        raise MigrationRefusedError(
            f"{where}: {SECTION!r} does not open on a line of its own, so "
            f"there is nowhere to write {FAMILY!r} without reformatting the "
            "file; add the field by hand and run this again"
        )
    return migrated


def _ascii(text: str) -> str:
    """Escape non-ASCII for a terminal -- identical to
    `migrate_v6.py::_ascii`; see that function's own docstring."""
    return text.encode("ascii", "backslashreplace").decode("ascii")


def diff(before: str, after: str, name: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Give the charter's motif the name of the drawing it wants."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the diff instead of writing the files",
    )
    args = parser.parse_args(argv)

    root = repo_root()

    # Every charter is read and rewritten in memory before a single byte is
    # written back. A migration that had already rewritten one file when it
    # met a refusal in another would leave the repository holding charters
    # under two shapes, which is the one state no reader can draw from.
    planned: list[tuple[str, Path, str, str]] = []
    for rel in CHARTERS:
        path = root / rel
        shown = rel.as_posix()
        if not path.is_file():
            print(f"{shown}: no charter here, nothing to migrate")
            continue
        before = path.read_text(encoding="utf-8")
        try:
            after = migrate_charter_text(before, where=shown)
        except MigrationRefusedError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        planned.append((shown, path, before, after))

    changed = False
    for shown, path, before, after in planned:
        if before == after:
            print(f"{shown}: already migrated, nothing to do")
            continue
        changed = True
        if args.dry_run:
            print(_ascii(diff(before, after, shown)), end="")
        else:
            path.write_text(after, encoding="utf-8", newline="")
            print(f"{shown}: migrated")

    if changed and args.dry_run:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
