"""One-shot migration of `data/speakers.yml` from schema v4 to schema v5.

Schema v5 adds one field: `survey_enabled`, the post-event survey's
per-event switch. It is a fact about a speaker
record, not a `data/config.yml` setting, for the reasoning
`app/src/data/types.ts::Speaker.survey_enabled`'s own doc comment gives --
so every existing record, real data older than the field itself, has to
gain it before `app/src/data/validate.ts` and `tools/convener_ops/validate.py`
can both start requiring it.

What it does, and the whole of what it does: every speaker gains
`survey_enabled: false` when the key is absent, placed directly after
`forum_thread` -- the last of the event-mechanics fields (`zoom_link`,
`youtube_url`, `forum_thread`) the switch belongs beside.

`false`, never `true`: optional means absent by default, so
an existing event never silently gains an
open survey it never asked for. Turning the survey on for a real event is a
deliberate, later, per-event edit, not something this migration should ever
decide on an organiser's behalf.

The migration is **idempotent**: the field is added only when its key is
missing, so a second run is a no-op down to the byte -- the same guarantee
`migrate_v4.py` gives, and for the same reason: an accidental second run
must never overwrite a switch someone has since turned on.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python ../scripts/migrate_v5.py --dry-run   # print the diff
    uv run python ../scripts/migrate_v5.py             # write the file
"""

from __future__ import annotations

import argparse
import difflib
import sys
from collections.abc import Sequence
from typing import Any

from convener_ops.cli import dump_speakers
from convener_ops.paths import repo_root
from convener_ops.yaml_safe import safe_load

#: The new field, keyed by the field it is written after -- the position
#: `app/src/data/types.ts` and `app/src/data/validate.ts::readSpeaker` both
#: use: directly after `forum_thread`, the last of the event-mechanics
#: fields the switch belongs beside. The file is read by hand and reviewed
#: as a diff, so a new key sits beside the field it belongs with and the
#: diff reads as added lines -- the same discipline `migrate_v4.py`'s own
#: `TEXT_AFTER`/`LIST_AFTER`/`MAP_AFTER` follow.
BOOL_AFTER: dict[str, tuple[str, ...]] = {
    "forum_thread": ("survey_enabled",),
}

#: Every key this migration may add, with the value it adds. Nothing
#: outside this mapping is written.
NEW_FIELDS: dict[str, Any] = {
    "survey_enabled": False,
}


def migrate_speaker(speaker: dict[str, Any]) -> dict[str, Any]:
    """Migrate one speaker, preserving key order and every existing value.

    A field already present keeps exactly what it has, whatever it is --
    the same "never overwrite" discipline `migrate_v4.py::migrate_speaker`
    holds itself to, and the property that keeps a re-run from ever
    resetting a switch an organiser has since turned on.
    """
    migrated: dict[str, Any] = {}
    for key, value in speaker.items():
        migrated[key] = value
        for field in BOOL_AFTER.get(key, ()):
            if field not in speaker:
                migrated[field] = NEW_FIELDS[field]

    # The anchor above is the usual shape; a hand-written entry may lack
    # it, and the record still has to end up complete.
    for field in NEW_FIELDS:
        if field not in migrated:
            migrated[field] = NEW_FIELDS[field]
    return migrated


def migrate_speakers(speakers: Sequence[Any]) -> list[Any]:
    return [
        migrate_speaker(speaker) if isinstance(speaker, dict) else speaker
        for speaker in speakers
    ]


def _ascii(text: str) -> str:
    """Escape non-ASCII for a terminal -- identical to
    `migrate_v4.py::_ascii`; see that function's own docstring."""
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
        description="Migrate data/speakers.yml to schema v5."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the diff instead of writing the file",
    )
    args = parser.parse_args(argv)

    speakers_path = repo_root() / "data" / "speakers.yml"
    before = speakers_path.read_text(encoding="utf-8")
    after = dump_speakers(migrate_speakers(safe_load(before) or []))

    if before == after:
        print(f"{speakers_path.name}: already migrated, nothing to do")
        return 0
    if args.dry_run:
        print(_ascii(diff(before, after, "data/speakers.yml")), end="")
        print("dry run: nothing written")
        return 0
    speakers_path.write_text(after, encoding="utf-8", newline="")
    print(f"{speakers_path.name}: migrated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
