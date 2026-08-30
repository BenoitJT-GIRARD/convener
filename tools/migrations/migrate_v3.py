"""One-shot migration of `instance/data/` from schema v2 to schema v3 (governance).

What it does:

1. `selection.votes_for: [login]` becomes a list of `yes` ballots, each
   carrying `decided_on` as its date when there is one and an empty string
   otherwise -- no date is invented;
2. `config.board_members: [login]` becomes `board: [{login, joined_on,
   status, unavailable_until}]` with `status: active` and `joined_on` empty
   (the joining dates are not recorded anywhere, so they stay unknown);
3. `config.vote_threshold` is deleted -- the threshold is computed from the
   eligible board, never stored;
4. every speaker gains `career_stage: undisclosed`;
5. every speaker gains a `publication` block, with `consent: pending` for a
   speaker whose status is `delivered` or `archived` and `''` otherwise;
6. every speaker gains `assigned_to: ''` -- `proposed_by` is
   the submitter, self-reported, and is never touched here.

The migration is **idempotent**: every step tests for the migrated shape
first and leaves it alone, so a second run is a no-op. That matters more
than it sounds -- an accidental re-run must not double anybody's ballots.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python migrations/migrate_v3.py --dry-run   # print the diff
    uv run python migrations/migrate_v3.py             # write the files
"""

from __future__ import annotations

import argparse
import difflib
import sys
from collections.abc import Iterable, Sequence
from typing import Any

from convener_ops.cli import dump_config, dump_speakers
from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.yaml_safe import safe_load

#: Statuses whose recording exists, so consent is something to go and ask
#: for rather than a field left blank.
PUBLISHABLE = frozenset({"delivered", "archived"})

#: Values for the schema-v3 configuration keys that did not exist in v2.
#: Every one of them is a governance rule this project had already settled:
#: board size 5..9, vote window 14 days, objection window 3
#: working days, balance window 24 months,
#: and the four SLA delays. `inactivity_months` is the one
#: value nothing else pins down; 6 months is what the test fixtures
#: already assume, and it is a configuration key precisely so the Board can
#: change it without code.
CONFIG_DEFAULTS: dict[str, Any] = {
    "nominations": [],
    "board_min": 5,
    "board_max": 9,
    "vote_window_days": 14,
    "objection_window_working_days": 3,
    "inactivity_months": 6,
    "balance_window_months": 24,
    "view_count_window_days": 30,
    "sla_days": {
        "invitation_follow_up": 30,
        "summary_after_delivery": 7,
        "recording_after_delivery": 14,
    },
}


def _publication(status: Any) -> dict[str, Any]:
    return {
        "consent": "pending" if status in PUBLISHABLE else "",
        "approved_by": "",
        "approved_on": "",
        "objections": [],
        "outcome": "",
    }


def _migrate_selection(selection: Any) -> Any:
    """Turn `votes_for` into ballots; leave an already-migrated one alone."""
    if not isinstance(selection, dict):
        return selection
    if "ballots" in selection:
        # Already migrated. Only fill in the two dates if a hand-edit lost
        # them -- never touch the ballots themselves.
        migrated = dict(selection)
        migrated.setdefault("opened_on", "")
        migrated.setdefault("decided_on", "")
        return migrated

    decided_on = selection.get("decided_on") or ""
    voters = selection.get("votes_for") or []
    ballots = [
        {
            "voter": voter,
            "value": "yes",
            "comment": "",
            "coi_reason": "",
            "date": decided_on,
        }
        for voter in voters
    ]
    return {
        "ballots": ballots,
        # No date is invented: a v2 file never recorded when a vote opened.
        "opened_on": selection.get("opened_on", ""),
        "decided_on": decided_on,
    }


def migrate_speaker(speaker: dict[str, Any]) -> dict[str, Any]:
    """Migrate one speaker, preserving key order and every existing value.

    New keys are inserted next to the field they belong with rather than
    appended, so the resulting file diff reads as added lines instead of a
    reshuffle.
    """
    migrated: dict[str, Any] = {}
    for key, value in speaker.items():
        if key == "selection":
            migrated["selection"] = _migrate_selection(value)
            if "publication" not in speaker:
                migrated["publication"] = _publication(speaker.get("status"))
            continue

        migrated[key] = value
        if key == "gender" and "career_stage" not in speaker:
            migrated["career_stage"] = "undisclosed"
        if key == "proposed_by" and "assigned_to" not in speaker:
            # assigned_to is the board member who owns the
            # lead, proposed_by is whoever suggested the speaker. They are
            # not the same person and are never merged.
            migrated["assigned_to"] = ""

    # Anchors above are the usual shape; a hand-written entry may lack them.
    if "career_stage" not in migrated:
        migrated["career_stage"] = "undisclosed"
    if "assigned_to" not in migrated:
        migrated["assigned_to"] = ""
    if "publication" not in migrated:
        migrated["publication"] = _publication(speaker.get("status"))
    return migrated


def migrate_speakers(speakers: Sequence[Any]) -> list[Any]:
    return [
        migrate_speaker(speaker) if isinstance(speaker, dict) else speaker
        for speaker in speakers
    ]


def ballot_voters(speakers: Sequence[Any]) -> list[str]:
    """Every login that cast a ballot, in order of first appearance."""
    voters: list[str] = []
    for speaker in speakers:
        selection = speaker.get("selection") if isinstance(speaker, dict) else None
        if not isinstance(selection, dict):
            continue
        raw = selection.get("ballots")
        if not isinstance(raw, list):
            continue
        for entry in raw:
            voter = entry.get("voter") if isinstance(entry, dict) else None
            if isinstance(voter, str) and voter and voter not in voters:
                voters.append(voter)
    return voters


def _board(logins: Iterable[str]) -> list[dict[str, Any]]:
    return [
        {
            "login": login,
            # Unknown: v2 recorded no joining date for anyone.
            "joined_on": "",
            "status": "active",
            "unavailable_until": "",
        }
        for login in logins
    ]


def migrate_config(
    config: dict[str, Any], voters: Sequence[str] = ()
) -> dict[str, Any]:
    """Migrate the configuration, preserving key order and every value kept.

    `voters` are the logins found on ballots in `speakers.yml`. They are
    added to the board after the declared members: the v2 file declared one
    member while four people had actually been voting, and a board that
    omits them would make every one of their ballots invalid. Nothing is
    merged -- if two entries turn out to be the same person, that is a
    decision for the Board, not for a migration.
    """
    migrated: dict[str, Any] = {}
    for key, value in config.items():
        if key == "vote_threshold":
            # Deleted, not moved: the threshold is computed from the
            # eligible board size (convener_ops.governance), never stored.
            continue
        if key == "board_members":
            declared = [login for login in value if isinstance(login, str)]
            extra = [voter for voter in voters if voter not in declared]
            migrated["board"] = _board([*declared, *extra])
            continue
        migrated[key] = value

    if "board" not in migrated:
        # Already migrated (or never had a board): leave it exactly as is.
        migrated["board"] = []
    for key, default in CONFIG_DEFAULTS.items():
        migrated.setdefault(key, default)
    return migrated


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
    parser = argparse.ArgumentParser(description="Migrate instance/data/ to schema v3.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the diff instead of writing the files",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    speakers_path = root / "instance" / "data" / "speakers.yml"
    config_path = root / "instance" / "data" / "config.yml"

    speakers_before = speakers_path.read_text(encoding="utf-8")
    config_before = config_path.read_text(encoding="utf-8")

    speakers = migrate_speakers(safe_load(speakers_before) or [])
    config = migrate_config(safe_load(config_before) or {}, ballot_voters(speakers))

    speakers_after = dump_speakers(speakers)
    config_after = dump_config(config)

    changed = False
    for path, before, after in (
        (speakers_path, speakers_before, speakers_after),
        (config_path, config_before, config_after),
    ):
        if before == after:
            print(f"{path.name}: already migrated, nothing to do")
            continue
        changed = True
        if args.dry_run:
            print(_ascii(diff(before, after, f"instance/data/{path.name}")), end="")
        else:
            path.write_text(after, encoding="utf-8", newline="")
            print(f"{path.name}: migrated")

    if changed and args.dry_run:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
