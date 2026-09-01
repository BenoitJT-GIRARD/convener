"""One-shot migration of every `brand.json` in this repository: the three
colour keys that named hues are renamed to the positions they hold.

The charter declares eight colours, and three of them were named after
what they happened to be in the first palette anybody measured: `purple`,
`turquoise`, `cream`. They are read by name -- by
`tools/scripts/generate_brand_css.py`, by
`convener_ops/publication/visual.py` and by
`convener_ops/publication/brand_templates.py` -- so every later palette
inherited the names whatever colours it chose. In the product's own
charter `colour.purple` holds `#012765`, a navy, and `colour.turquoise`
holds `#febcb1`, a coral. `assets/brand/convener/brand.json` said so itself, in
a `_names` field that existed to tell a reader the keys named positions
and not hues.

A field explaining that a name is wrong is a name that is wrong. This
renames them:

    purple    -> dominant   the ink the headlines, the ribbon and the
                            wordmark are drawn in
    turquoise -> field      the saturated ground that fills the page
    cream     -> band       the full-width horizontal bands across it

Those three nouns are the charter's own: `colour._roles` already called
the first "the dominant colour, not an accent", `layout` already called
the second the field and the third the bands.

`ink`, `ink_muted`, `rule`, `white` and `black` keep their names. The
first three name a use rather than a hue. The last two do name hues, and
hold them: `white` is `#ffffff` and `black` is `#000000` in all three
charters, so neither name can mislead anybody.

What follows from the three
----------------------------
Every key built on a colour name follows it, in the same rewrite:

- the roles written beside them, `colour._roles`, keyed by colour name;
- `derived`: `turquoise_text`, `turquoise_tint`, `purple_hover`,
  `purple_tint`, and the commentary key `_purple_hover`;
- `contrast`: all twelve pairings, each named `<ink>_on_<ground>` and
  split back into its two colours by
  `convener_ops.publication.brand.contrast_problems` at every run.

`ink_faint`, `rule_strong` and the whole of `motif`, `typography` and
`layout` are untouched.

Three charters, not one
------------------------
`assets/brand/convener/brand.json` is the product's own, the palette a duplicate
builds with before it has chosen anything. `instance/data/brand.json` is
this instance's. `examples/the-example-collective/instance/data/brand.json` is the
worked example `tools/tests/repository/test_second_instance.py` builds the whole
repository as. All three answer the same names, because the *system* is
the product's and every template reads a colour by name; migrating one
and not the others would ship a product whose own example no longer
builds.

`instance/data/brand.json` is optional -- a duplicate that has chosen no
colours has no such file -- so a charter that is not there is reported
and skipped rather than treated as an error.

**No value changes, and no prose.** Only key names, in place, so the diff
reads as a renamed line rather than a section rewritten; the parade is
that every one of the twelve contrast figures is the same number
afterwards, and `generate_brand_css.py --check` recomputes all of them.
The commentary these files carry is left exactly as it stands: a
migration that rewrote English would bury the rename it exists to make
reviewable, and the prose in an instance's charter is that instance's.

**Idempotent.** The rewrite is driven by which keys are still under the
old names, so a charter already carrying the new ones is left alone down
to the byte and says so.

**A charter carrying both names in one section is refused, never
merged.** Only a hand edit can produce one, the two values can disagree,
and choosing between them is a decision about what colour to draw with --
not a migration's to take.

**Reversible**, and deliberately without a flag for it. The inverse is
the same rewrite with the three pairs swapped. Nothing is dropped and
nothing is invented, so there is no information an undo would have to
reconstruct.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python migrations/migrate_charter_colour_names.py --dry-run
    uv run python migrations/migrate_charter_colour_names.py
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
from convener_ops.publication import brand

#: The three names that moved, old to new. Read from the reader that has
#: to refuse a charter still under the old ones, rather than written
#: again here: a migration and a refusal that disagreed about which name
#: became which would send a person round in a circle.
POSITIONS: Final = brand.SUPERSEDED_COLOURS

#: The sections whose keys are colour names, and therefore the only ones
#: this migration may touch. `colour._roles` is keyed by colour name too
#: and is reached through `colour`.
SECTIONS: Final = ("colour", "derived", "contrast")

#: The nested map inside `colour` that writes down what each colour is
#: for, one entry per colour key.
ROLES_KEY: Final = "_roles"

#: The three charters this repository ships. `assets/brand/convener/brand.json`
#: is the product's own and is always there; the other two are an
#: instance's, and the first of them is optional by design.
CHARTERS: Final = (
    brand.DEFAULT_PATH,
    brand.INSTANCE_PATH,
    Path("examples") / "the-example-collective" / brand.INSTANCE_PATH,
)


class MigrationRefusedError(RuntimeError):
    """A charter this migration will not rewrite, with the whole reason.

    The message rather than a code, for the reason
    `brand.MissingMotifError` gives: what a person needs at the moment a
    migration stops is which file holds what, not a symbol to look up.
    """


def rename(name: str) -> str:
    """One key under its new name, or unchanged.

    Four shapes, and every key in a charter is one of them: a bare colour
    name (`purple`); a name built on one (`turquoise_text`,
    `purple_hover`); a contrast pairing naming two of them
    (`white_on_purple`); and a commentary key, which is any of those
    three behind a leading underscore (`_purple_hover`, `_roles`).
    """
    if name.startswith("_"):
        return "_" + rename(name[1:])
    ink, on, ground = name.rpartition("_on_")
    if on:
        return f"{rename(ink)}_on_{rename(ground)}"
    base, sep, rest = name.partition("_")
    return f"{POSITIONS.get(base, base)}{sep}{rest}"


#: One key at the start of a line, at any indentation: a charter writes
#: every key that way, and no value can be mistaken for one. The prose in
#: these files says `purple` and `turquoise` many times over -- inside
#: string values, which never begin a line -- and none of it is rewritten.
_KEY_LINE: Final = re.compile(
    r'^(?P<indent>[ \t]*)"(?P<key>[^"]+)"(?=\s*:)', re.MULTILINE
)


def _renamed_keys(mapping: dict[str, Any], *, where: str) -> dict[str, str]:
    """Every key in one section that changes, old name to new.

    Refuses a section carrying a key under both names: the two can hold
    different colours, and which one the palette is drawn in is not a
    decision a migration may take.
    """
    changed = {key: rename(key) for key in mapping if rename(key) != key}
    for old, new in changed.items():
        if new in mapping:
            raise MigrationRefusedError(
                f"{where} carries both {old} ({mapping[old]!r}) and "
                f"{new} ({mapping[new]!r}); only a hand edit can write both, "
                f"and which colour to draw with is not a migration's "
                f"decision -- delete the one that is wrong and run this again"
            )
    return changed


def _sections(
    charter: dict[str, Any], *, where: str
) -> list[tuple[str, dict[str, Any]]]:
    """The sections to rewrite, named for a message: the three keyed by
    colour name, plus the roles map inside `colour`."""
    found: list[tuple[str, dict[str, Any]]] = []
    for section in SECTIONS:
        body = charter.get(section)
        if not isinstance(body, dict):
            raise MigrationRefusedError(
                f"{where} has no {section!r} object; this is not a charter"
            )
        found.append((f"{where}: {section}", body))
        if section == "colour" and isinstance(body.get(ROLES_KEY), dict):
            found.append((f"{where}: colour.{ROLES_KEY}", body[ROLES_KEY]))
    return found


def _check_only_the_names_changed(
    before: dict[str, Any], after: dict[str, Any], *, where: str
) -> None:
    """The post-condition, checked on the parsed charters rather than on
    the text: every section in the same order, every key under the name
    `rename` gives it, and every value identical.

    A regular expression rewriting a data file has to prove it rewrote
    what it meant to. This is that proof, and it runs on every file every
    time rather than only in the tests.
    """
    if list(after) != list(before):
        raise MigrationRefusedError(
            f"{where}: the rewrite changed the sections of the file: "
            f"expected {list(before)}, got {list(after)}"
        )
    for section, body in before.items():
        if not isinstance(body, dict) or section not in SECTIONS:
            if after[section] != body:
                raise MigrationRefusedError(
                    f"{where}: the rewrite changed {section!r}, which holds no "
                    "colour name"
                )
            continue
        expected = {rename(key): value for key, value in body.items()}
        if section == "colour" and isinstance(body.get(ROLES_KEY), dict):
            expected[ROLES_KEY] = {
                rename(key): value for key, value in body[ROLES_KEY].items()
            }
        if list(after[section]) != list(expected):
            raise MigrationRefusedError(
                f"{where}: the rewrite changed the keys of {section!r}: "
                f"expected {list(expected)}, got {list(after[section])}"
            )
        if after[section] != expected:
            raise MigrationRefusedError(
                f"{where}: the rewrite changed a value in {section!r}"
            )


def migrate_charter_text(text: str, *, where: str) -> str:
    """One `brand.json`, with its colour keys under their positions.

    Text in, text out: these files carry paragraphs of commentary and
    blank lines between the groups of colours, and neither survives a
    load-and-dump round trip. A charter already carrying the new names is
    returned unchanged, which is what makes a second run a no-op.
    """
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise MigrationRefusedError(f"{where}: top-level must be an object")

    changed: dict[str, str] = {}
    for section_name, body in _sections(loaded, where=where):
        changed.update(_renamed_keys(body, where=section_name))
    if not changed:
        return text

    def one_line(match: re.Match[str]) -> str:
        key = match.group("key")
        return f'{match.group("indent")}"{changed.get(key, key)}"'

    migrated = _KEY_LINE.sub(one_line, text, count=0)
    _check_only_the_names_changed(loaded, json.loads(migrated), where=where)
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
        description="Rename the charter's colour keys to the positions they hold."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the diff instead of writing the files",
    )
    args = parser.parse_args(argv)

    root = repo_root()

    # Every charter is read and rewritten in memory before a single byte
    # is written back. A migration that had already rewritten one file
    # when it met a refusal in another would leave the repository holding
    # charters under two sets of names, which is the one state no reader
    # can draw from.
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
