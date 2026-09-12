"""One-shot: open the vote window on the leads that never had one.

Why this exists
---------------
Every record migrated from schema v2 carries `selection.opened_on: ''`,
because the v2 file never recorded when a vote opened and the migration
invents no date. `sweep.expire_votes` skips --
silently, so an unattended overnight job never dies on bad data -- any lead
whose `opened_on` does not parse, so those leads can never expire and
nothing anywhere reports it. Intake was fixed separately
(`convener_ops.journey.proposal.to_lead` stamps the intake date); this script deals with
the backlog that predates the fix.

Dating the backlog is a policy choice, not a technical one, and the project
owner made it: the window opens today, `DEFAULT_ON` below.

What it touches
---------------
Exactly one field, `selection.opened_on`, and only on a record that is
still awaiting the Board. That means `status: lead` and nothing else: it is
the only status for which the Board is asked to vote (`sweep.expire_votes`
looks at no other, `app/src/state/inbox.ts` raises a vote row for no other,
and `ActionButtons` offers a ballot for no other). Every other status in
`validate.STATUSES` is excluded because its vote is over -- `approved`,
`invited`, `confirmed`, `scheduled`, `delivered`, `archived` all passed the
vote, `decline-board` and `decline-speaker` ended it, and `parked` is where
an expired window already put a lead. Opening a window retroactively on any
of them would either restart a concluded vote or, for a `lead` that already
has a `decided_on`, expose a settled decision to expiry.

The file it rewrites holds real people's names and e-mail addresses, so the
transformation is pure and tested before it is ever pointed at `instance/data/`, and
`--dry-run` prints the diff for a human to read first.

Idempotent: a record that already has an `opened_on` is left exactly as it
is, so a second run is a no-op and a re-run can never move a deadline.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run --frozen python scripts/open_vote_window.py --dry-run   # print the diff
    uv run --frozen python scripts/open_vote_window.py             # write the file
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

#: The date the project owner chose for the whole backlog. Not `date.today()`:
#: the value is a decision, and a decision belongs in the file that records
#: it, not in the clock of whoever happens to run the script.
DEFAULT_ON = "2026-08-18"

#: The statuses that mean "still awaiting the Board". See the module
#: docstring for why this is exactly one status.
AWAITING = frozenset({"lead"})


def needs_window(speaker: Any) -> bool:
    """Whether this record is a lead still waiting for a vote to be opened.

    Four conditions, each of which excludes a record that must not be
    stamped: it must be a mapping, it must be awaiting the Board, it must
    not already have a window (that would move an existing deadline), and
    its vote must not already be decided (a `decided_on` means the question
    was answered, whatever the status still says).
    """
    if not isinstance(speaker, dict) or speaker.get("status") not in AWAITING:
        return False
    selection = speaker.get("selection")
    if not isinstance(selection, dict):
        return False
    return not selection.get("opened_on") and not selection.get("decided_on")


def open_window(speaker: Any, on: str) -> Any:
    """Return the record with `selection.opened_on` set, or unchanged.

    Key order is preserved on both levels, so the file diff reads as one
    changed line per record instead of a reshuffle.
    """
    if not needs_window(speaker):
        return speaker
    stamped = dict(speaker)
    selection = dict(speaker["selection"])
    selection["opened_on"] = on
    stamped["selection"] = selection
    return stamped


def open_windows(speakers: Sequence[Any], on: str) -> list[Any]:
    return [open_window(speaker, on) for speaker in speakers]


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
        description="Open the vote window on leads that never had one."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the diff instead of writing the file",
    )
    parser.add_argument(
        "--on",
        default=DEFAULT_ON,
        help=f"the date to stamp, YYYY-MM-DD (default: {DEFAULT_ON})",
    )
    args = parser.parse_args(argv)

    speakers_path = repo_root() / "instance" / "data" / "speakers.yml"
    before = speakers_path.read_text(encoding="utf-8")

    speakers = safe_load(before) or []
    stamped = sum(1 for speaker in speakers if needs_window(speaker))
    after = dump_speakers(open_windows(speakers, args.on))

    if before == after:
        print("speakers.yml: every awaiting lead already has a vote window")
        return 0

    if args.dry_run:
        print(_ascii(diff(before, after, "instance/data/speakers.yml")), end="")
        print(f"dry run: nothing written ({stamped} leads would be stamped)")
        return 0

    speakers_path.write_text(after, encoding="utf-8", newline="")
    print(f"speakers.yml: vote window opened on {stamped} leads ({args.on})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
