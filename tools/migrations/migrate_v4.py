"""One-shot migration of `instance/data/speakers.yml` from schema v3 to schema v4.

Schema v4 adds the six fields the checklists have always asked for and the
model never had, so they travelled by e-mail and were lost: a portrait, a
short biography, a handle, the questions the speaker wants the discussion
opened with, the slots that were put to the speaker, and the name against
each line of the journey.

What it does, and the whole of what it does:

1. every speaker gains `photo_url`, `bio`, `linkedin` and `seed_questions`
   as `''` when the key is absent;
2. every speaker gains `candidate_dates` as `[]` when the key is absent;
3. every speaker gains `checklist` as `{}` when the key is absent.

`checklist` arrives empty and stays empty until somebody puts a name against
a line. That is not an unfinished migration: a line with no owner is the
hosts', which is exactly what every line meant before this field existed, so
an empty checklist is the migration preserving today's behaviour rather than
declining to guess at one. Nothing here reads `assigned_to` to fill it --
that is the board member who owns the *lead*, a different notion at a
different grain, and deriving one from the other is a defect this project
has already paid for once.

What it deliberately does not do: it never overwrites a key that is already
there, and it never touches `publication.consent`. Asking the speakers for
their consent to publish is a human act, not a migration.

The five values are all empty. That is the point of the distinction the
validator draws with `in` rather than truthiness: an empty value is an
answer the record can hold, an absent key is a record nobody finished. This
migration turns the second into the first and invents nothing.

The migration is **idempotent**: every field is added only when its key is
missing, so a second run is a no-op down to the byte.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python migrations/migrate_v4.py --dry-run   # print the diff
    uv run python migrations/migrate_v4.py             # write the file
"""

from __future__ import annotations

import argparse
import difflib
import sys
from collections.abc import Sequence
from typing import Any

from convener_ops.cli.store import dump_speakers
from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.yaml_safe import safe_load

#: The new text fields, each keyed by the field it is written after. The
#: positions are those of `app/src/data/types.ts` and of the boundary
#: fixture the browser generates: the portrait, biography and handle belong
#: with the person, the seed questions with what the person will talk about.
#: The file is read by hand and reviewed as a diff, so a new key sits beside
#: the field it belongs with and the diff reads as added lines.
TEXT_AFTER: dict[str, tuple[str, ...]] = {
    "country": ("photo_url", "bio", "linkedin"),
    "abstract": ("seed_questions",),
}

#: `candidate_dates` is the date negotiation, so it sits with the edition it
#: is negotiating, just before the date that negotiation settles on.
LIST_AFTER: dict[str, tuple[str, ...]] = {
    "edition_code": ("candidate_dates",),
}

#: `checklist` says who owes each line of the runbook, so it sits directly
#: after `runbook_progress`, which says whether each line is done. The two
#: are read together on every screen that shows a journey.
MAP_AFTER: dict[str, tuple[str, ...]] = {
    "runbook_progress": ("checklist",),
}

#: Every key this migration may add, with the empty value it adds. Nothing
#: outside this mapping is written.
NEW_FIELDS: dict[str, Any] = {
    "photo_url": "",
    "bio": "",
    "linkedin": "",
    "seed_questions": "",
    "candidate_dates": [],
    "checklist": {},
}


def _empty(field: str) -> Any:
    value = NEW_FIELDS[field]
    # A fresh container per speaker: a shared mutable default would give all
    # 31 records the same object, and one later edit would appear in all of
    # them.
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def migrate_speaker(speaker: dict[str, Any]) -> dict[str, Any]:
    """Migrate one speaker, preserving key order and every existing value.

    A field already present keeps exactly what it has, whatever it is --
    including a value the validator would reject, which is a data question
    and not a migration's to answer.
    """
    migrated: dict[str, Any] = {}
    for key, value in speaker.items():
        migrated[key] = value
        for field in (
            *TEXT_AFTER.get(key, ()),
            *LIST_AFTER.get(key, ()),
            *MAP_AFTER.get(key, ()),
        ):
            if field not in speaker:
                migrated[field] = _empty(field)

    # The anchors above are the usual shape; a hand-written entry may lack
    # them, and the record still has to end up complete.
    for field in NEW_FIELDS:
        if field not in migrated:
            migrated[field] = _empty(field)
    return migrated


def migrate_speakers(speakers: Sequence[Any]) -> list[Any]:
    return [
        migrate_speaker(speaker) if isinstance(speaker, dict) else speaker
        for speaker in speakers
    ]


def _ascii(text: str) -> str:
    """Escape non-ASCII for a terminal.

    The operator's Windows console renders non-ASCII as mojibake, and this
    output is meant to be read carefully -- it is a diff of records about
    real people. `backslashreplace` keeps the information (an altered
    accented name still shows as a changed escape) instead of hiding it
    behind a replacement character.
    """
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
        description="Migrate instance/data/speakers.yml to schema v4."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the diff instead of writing the file",
    )
    args = parser.parse_args(argv)

    speakers_path = repo_root() / "instance" / "data" / "speakers.yml"
    before = speakers_path.read_text(encoding="utf-8")
    after = dump_speakers(migrate_speakers(safe_load(before) or []))

    if before == after:
        print(f"{speakers_path.name}: already migrated, nothing to do")
        return 0
    if args.dry_run:
        print(_ascii(diff(before, after, "instance/data/speakers.yml")), end="")
        print("dry run: nothing written")
        return 0
    speakers_path.write_text(after, encoding="utf-8", newline="")
    print(f"{speakers_path.name}: migrated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
