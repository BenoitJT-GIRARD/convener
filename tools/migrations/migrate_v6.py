"""One-shot migration of `instance/data/` from schema v5 to schema v6.

Schema v6 renames one configuration key and changes nothing else. The
counter that says which edition number to assign next was called
`vw_counter`: two letters taken from the name of the one series that
happened to be running this repository, written into the **product's**
own schema. Every duplicate of this repository was therefore forced to
carry another series' initials in its own `instance/data/config.yml`, in the
validator that reads it, in the model the browser narrows against, and in
the schema appendix every duplicate ships.

*(The old name is left spelled out above and in the code below, and it is
the one place in this repository where that is deliberate. A migration
record that cannot say what it renamed cannot be run by anybody who still
has the old key.)*

**It is renamed rather than frozen because nothing outside a repository
carries it.** The edition *prefix* was left alone for the opposite reason,
and the difference is the whole argument: a code like `MRG-05` is in a
published address, on every certificate issued for that event and in
`instance/keys/events/mrg-05.pub`, so renumbering it would break links nobody can
reach. This key is a name in one file, read by two validators; the number
it holds does not change, and neither does a single edition code.

`next_edition_number` says what it holds. The prefix that number is
written under stays where it is declared, `instance/config.json::
edition_prefix`, and this key never spelled it.

What it does, and the whole of what it does
--------------------------------------------
1. in each `config.yml` below, the line whose key is `vw_counter` becomes
   the same line under the name `next_edition_number` -- **in place**, so
   the diff reads as one renamed line rather than a key moved to the end,
   and so the paragraphs of YAML comments each of these files opens with
   survive. Nothing else in the file is touched, and the result is checked
   against the file it came from before it is written: same keys in the
   same order but for the rename, same values.
2. in each `speakers.yml` beside it, the header line's schema number is
   re-stamped from v5 to v6. Nothing in a speaker record changes; the
   header is the one place this repository writes the version of the
   unified schema down, and a file written after this migration that still
   announced v5 would be the only statement of that version, and wrong.

**Two trees, not one.** `instance/data/` is this instance's, and
`instances/example/instance/data/` is the product's own worked example -- the one
`tools/tests/test_second_instance.py` builds this whole repository as.
Migrating one and not the other would ship a product whose own example
fails its own validator at the next `convener-validate`.

**Idempotent.** Every step tests for the migrated shape first, so a second
run is a no-op down to the byte -- the same guarantee the three earlier
migrations give.

**Reversible**, and deliberately without a flag for it. The inverse of a
rename is the same rename with the two names swapped: one key name in one
line of each `config.yml`, plus one digit in each header. Nothing is
dropped and nothing is invented, so there is no information an undo would
have to reconstruct -- which is what an `--undo` switch is for, and why
there is not one here. `migrate_v3.py` deleted a key and could not have
said this.

**A file carrying both names is refused, never merged.** Only a hand edit
can produce one, the two numbers can disagree, and choosing between them
is a decision about which edition to number next -- not a migration's to
take (D-25).

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python migrations/migrate_v6.py --dry-run   # print the diff
    uv run python migrations/migrate_v6.py             # write the files
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.yaml_safe import safe_load

#: The key as schema v5 wrote it, and as this migration reads it. The one
#: place in the product this spelling survives, and it survives here for
#: the reason a migration exists at all: a file written before today still
#: says it.
OLD_KEY = "vw_counter"

#: The key as schema v6 writes it. Named after what it holds, not after
#: who wrote it: `app/src/data/types.ts::Config.next_edition_number` and
#: `tools/convener_ops/validate.py::CONFIG_REQUIRED` are the two readers that
#: require it, and `docs/reference/schema.md` derives its row from the
#: first of those.
NEW_KEY = "next_edition_number"

#: The one line to rewrite: the old key at the top level of the mapping,
#: which is where both readers require it and the only place either would
#: find it. Anchored at the start of a line with no indentation, so a
#: `vw_counter` nested inside some other block -- or written inside a
#: comment, or inside a value -- is left exactly where it is rather than
#: being rewritten by a bare string replacement.
_KEY_LINE = re.compile(rf"^{re.escape(OLD_KEY)}(?=:)", re.MULTILINE)

#: What schema v5 stamped on a speakers file, and what v6 stamps. This
#: migration has to write exactly what every later writer writes, or the
#: first sweep after it would produce a second diff; the two constants
#: that do the writing are `convener_ops.cli.SPEAKERS_HEADER` and
#: `app/src/data/yaml.ts::SPEAKERS_HEADER`, and
#: `tools/tests/test_migrate_v6.py` holds all three together rather than
#: this module importing one of them and leaving the other free to drift.
_V5_STAMP = "unified schema v5"
_V6_STAMP = "unified schema v6"

#: The two data directories this repository ships, each holding the same
#: two files. Relative to the repository root; see the module docstring
#: for why the example instance is migrated too.
DATA_DIRS = ("instance/data", "instances/example/instance/data")


class MigrationRefusedError(RuntimeError):
    """A file this migration will not rewrite, with the whole reason.

    The message rather than a code, for the reason
    `brand.MissingMotifError` gives: what a person needs at the moment a
    migration stops is which file holds what, not a symbol to look up.
    """


def _check_only_the_key_changed(before: Any, after: Any) -> None:
    """The post-condition, checked on the parsed mappings rather than on
    the text: the same keys in the same order but for the rename, and
    every value identical.

    A regular expression rewriting a data file has to prove it rewrote
    what it meant to. This is that proof, and it runs on every file every
    time rather than only in the tests.
    """
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise MigrationRefusedError("config.yml: top-level must be a mapping")
    expected = [NEW_KEY if key == OLD_KEY else key for key in before]
    if list(after) != expected:
        raise MigrationRefusedError(
            f"the rewrite changed the shape of the file: expected keys "
            f"{expected}, got {list(after)}"
        )
    for old_key, new_key in zip(before, expected, strict=True):
        if before[old_key] != after[new_key]:
            raise MigrationRefusedError(
                f"the rewrite changed the value of {old_key!r}: "
                f"{before[old_key]!r} became {after[new_key]!r}"
            )


def migrate_config_text(text: str) -> str:
    """Rename the counter in one `config.yml`, and change nothing else.

    Text in, text out: the comments a reader of these files depends on --
    the paragraph `instances/example/instance/data/config.yml` opens with, most of
    all -- do not survive a load-and-dump round trip, and a migration that
    reformatted a file to rename one key would bury the rename it exists
    to make reviewable.

    A file that already carries only the new name is returned unchanged,
    which is what makes a second run a no-op.
    """
    loaded = safe_load(text)
    if not isinstance(loaded, dict):
        raise MigrationRefusedError("config.yml: top-level must be a mapping")
    if OLD_KEY in loaded and NEW_KEY in loaded:
        raise MigrationRefusedError(
            f"this file carries both {OLD_KEY} ({loaded[OLD_KEY]!r}) and "
            f"{NEW_KEY} ({loaded[NEW_KEY]!r}); only a hand edit can write "
            f"both, and which edition to number next is not a migration's "
            f"decision -- delete the one that is wrong and run this again"
        )
    if OLD_KEY not in loaded:
        return text
    migrated = _KEY_LINE.sub(NEW_KEY, text)
    _check_only_the_key_changed(loaded, safe_load(migrated))
    return migrated


def migrate_speakers_text(text: str) -> str:
    """Re-stamp a speakers file's header line, and touch nothing else.

    Only the first line, and only the version in it: the example
    instance's own file opens with a sentence of its own that happens to
    carry the stamp, and that sentence is prose a rewrite of the whole
    file would flatten.
    """
    first, sep, rest = text.partition("\n")
    if not sep or _V5_STAMP not in first:
        return text
    return first.replace(_V5_STAMP, _V6_STAMP) + sep + rest


def _ascii(text: str) -> str:
    """Escape non-ASCII for a terminal -- identical to
    `migrate_v5.py::_ascii`; see that function's own docstring."""
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


def migrate_tree(directory: Path, name: str) -> list[tuple[Path, str, str]]:
    """One data directory's two files, as (path, before, after)."""
    config_path = directory / "config.yml"
    speakers_path = directory / "speakers.yml"
    config_before = config_path.read_text(encoding="utf-8")
    speakers_before = speakers_path.read_text(encoding="utf-8")
    try:
        config_after = migrate_config_text(config_before)
    except MigrationRefusedError as exc:
        raise MigrationRefusedError(f"{name}/config.yml: {exc}") from exc
    return [
        (config_path, config_before, config_after),
        (speakers_path, speakers_before, migrate_speakers_text(speakers_before)),
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate instance/data/ to schema v6.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the diff instead of writing the files",
    )
    args = parser.parse_args(argv)

    root = repo_root()

    # Every tree is read and rewritten in memory before a single byte is
    # written back. A migration that had already rewritten `instance/data/` when it
    # met a refusal in the example would leave the repository between two
    # schema versions, which is the one state neither validator can name.
    planned: list[tuple[str, Path, str, str]] = []
    for name in DATA_DIRS:
        try:
            for path, before, after in migrate_tree(root / name, name):
                planned.append((f"{name}/{path.name}", path, before, after))
        except MigrationRefusedError as exc:
            print(str(exc), file=sys.stderr)
            return 1

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
