"""Evidence, inside this repository, that the retention sweep still runs.

D-25 makes every control fail loudly
*inside* a run. It has nothing to say about a run that never starts --
`.github/workflows/retention.yml` is the job that destroys an event's
registration key on schedule (D-22), GitHub disables a workflow's
own `schedule:` trigger after 60 days without any activity in the
repository, and an exhausted Actions minute budget simply stops work either
way. Neither ever turns a badge red, because no run happens at all.

This module holds the pure half of the fix: a tiny, versioned record --
`instance/data/retention-last-run.yml`, one field, `last_run` -- and the arithmetic
that decides whether it is stale. `cli.py` is the only module that touches
disk (its own module docstring); the two console scripts built on this one
(`convener-record-retention-run` and `convener-check-retention-liveness`) live there.

The record is written unconditionally by `retention.yml` every day its
schedule fires, regardless of whether that day's actual sweep succeeded --
see that workflow's own "Record that the retention workflow ran today" step
for why conflating "it ran" with "it ran correctly" would hide a real,
ongoing failure behind a checkmark. `retention-watchdog.yml`, a second,
independent schedule, reads it and fails loudly once it has gone quiet for
longer than `MAX_SILENT_DAYS` -- see that workflow's own header comment for
what it does and does not catch, most importantly that it cannot detect the
one scenario it exists for if the *whole* repository, this watchdog
included, goes dark at once. What survives even that: a person who opens
this repository, no CI required, can read the date this file names.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Final

from ..declaration.paths import DATA_DIR

#: Where the record lives, relative to a repository root -- the same
#: "one function names the path" discipline `eventkeys.destructions_path`
#: already holds itself to.
LAST_RUN_PATH: Final = DATA_DIR / "retention-last-run.yml"

#: `instance/data/retention-last-run.yml`'s own format version -- the file-level
#: analogue of `eventkeys.DESTRUCTIONS_FILE_VERSION`.
LAST_RUN_FILE_VERSION: Final = 1

#: How many days of silence `is_stale` tolerates before calling it quiet.
#: `retention.yml` runs daily (06:11 UTC); `retention-watchdog.yml` checks
#: daily too, later the same day (12:00 UTC), so a healthy day's record is
#: always already written by the time it is checked -- under ordinary
#: operation `days_since` should read 0 on every check. One full day of
#: slack absorbs an occasional scheduling delay GitHub's own documentation
#: allows for a busy runner queue without a false alarm; two consecutive
#: missed days -- the whole point of a promise with legal weight -- is a
#: genuine signal, not a coincidence worth shrugging off.
MAX_SILENT_DAYS: Final = 2


def last_run_path(root: Path) -> Path:
    """`instance/data/retention-last-run.yml`, relative to `root`. Pure path
    computation: reads nothing, touches nothing."""
    return root / LAST_RUN_PATH


def record_to_data(today: date) -> dict[str, Any]:
    """The plain, YAML-safe structure `cli.py` hands to its own YAML
    writer -- the inverse of `last_run_from_data`."""
    return {"v": LAST_RUN_FILE_VERSION, "last_run": today.isoformat()}


def last_run_from_data(data: Any) -> date:
    """Parse an already YAML-loaded `instance/data/retention-last-run.yml`.

    Raises `ValueError` on anything that is not this exact, single-field
    format -- the same closed-shape discipline
    `eventkeys.registry_from_data` holds itself to. A *missing* file is a
    fact about the filesystem, not a shape this function ever sees; the
    caller (`cli.py::check_retention_liveness`) handles that case on its
    own, before this function is ever called.
    """
    if not isinstance(data, dict) or data.get("v") != LAST_RUN_FILE_VERSION:
        raise ValueError(
            f"{LAST_RUN_PATH.as_posix()} is not a supported format version"
        )
    raw = data.get("last_run")
    if not isinstance(raw, str):
        raise ValueError(f"{LAST_RUN_PATH.as_posix()} holds no usable last_run date")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"{LAST_RUN_PATH.as_posix()} holds an invalid last_run date"
        ) from exc


def days_since(last_run: date, today: date) -> int:
    """`today - last_run`, in whole days.

    Can be negative -- a hand-edited file, or a clock skew between the
    runner that wrote it and the one that reads it -- and `is_stale` below
    treats a negative value as healthy, never as extra-fresh evidence of
    anything: this function only measures elapsed time. It does not judge
    the record it was handed.
    """
    return (today - last_run).days


def is_stale(elapsed_days: int, max_silent_days: int = MAX_SILENT_DAYS) -> bool:
    """Whether `elapsed_days` (see `days_since`) counts as the retention
    schedule having gone quiet. A pure comparison, its own function so the
    boundary itself -- `elapsed_days == max_silent_days` is still healthy,
    `max_silent_days + 1` is not -- is something a test can pin directly,
    without also standing up a fixture file and two dates to reach it."""
    return elapsed_days > max_silent_days
