"""The example instance's records, as old today as they were written to be.

`examples/the-example-collective/instance/data/` is a fixture with dates in
it, and a fixture with dates in it goes stale on its own. Read on the day
they were written, the records show a board with a vote open, a session five
weeks out and a wrap-up nobody is late on; read eleven months later they show
the same records with every deadline behind them, and the demonstration's
inbox prints "Forum summary is 281 days overdue" about a talk nobody gave.
That is not a defect in the inbox -- the inbox is right -- and it is not a
defect in the reader either: `app/src/data/demo.ts` reads the example rather
than inventing, deliberately. It is a defect in the days.

What this does, and the whole of it
-----------------------------------
Every ISO day in the text moves by the same whole number of weeks, so that
the fixture's own present lands on the week the demonstration is being
watched in.

    shift = floor((today - ANCHOR) / 7) * 7 days

**Weeks rather than days**, because a session is on a Thursday evening and
`agenda.py` composes the calendar entry from the day it finds: shifting by
whole weeks keeps every weekday it was written with, and shifting by days
would move a monthly Thursday series onto a Tuesday. What follows from that
is that the fixture's own present is between zero and six days behind the
real one, never ahead, so a record written as "due in seven days" is never
read as overdue.

**Text rather than records.** The rule is one regular expression over the
file, not a walk of the schema, and that is the point: a field added to the
model next year carries its date through this without anybody remembering to
name it here, and nothing here can reformat a file or drop the comment at the
top of it. The comment moves too, which is right rather than a side effect --
the shifted document says which day it is written for, and it is a different
day from the one the tracked file is written for.

Two implementations, one fixture
--------------------------------
`app/scripts/example-dates.mjs` is the same rule in the language the cockpit's
build speaks, because the demonstration's own records are compiled into that
bundle (`app/scripts/example-instance.mjs`) and no Python runs where that
happens. `tools/tests/fixtures/example-dates.json` is what stops the two
drifting: both sides read the same anchor and the same worked cases out of it
and must answer identically, the way `edition-prefix.json` already binds the
two readers of the declaration (D-14).

The day it is read against, and the one place it is ever overridden
-------------------------------------------------------------------
The real day, from the clock, everywhere but one: `CONVENER_EXAMPLE_TODAY`.
`tools/scripts/render_readme_shots.py` sets it to the day it also pins the
browser's clock to, so that the pictures in `README.md` are one moment in
the example instance's life and stay byte-identical between two runs on
different days. Nothing else sets it, and nothing about a real instance passes
through here at all: a repository's own `instance/data/` is never read by this
module, only the example the product ships.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from collections.abc import Mapping
from typing import Final

#: The day `examples/the-example-collective/instance/data/` is written for.
#: Every date in those files is placed against it, and the header of
#: `speakers.yml` says so in words. Mirrored by `ANCHOR` in
#: `app/scripts/example-dates.mjs` and pinned to it by
#: `tools/tests/fixtures/example-dates.json`.
ANCHOR: Final = "2026-09-03"

#: The one environment variable that replaces the clock here. See the module
#: docstring for its single caller.
TODAY_ENV: Final = "CONVENER_EXAMPLE_TODAY"

#: An ISO day, bounded on both sides so that a longer run of digits is not
#: half-matched. Deliberately the whole of what this module recognises as a
#: date: `18:00` is not one, `MRG-5` is not one, and a four-digit year on its
#: own is not one either.
ISO_DAY: Final = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


def today(environ: Mapping[str, str] | None = None) -> str:
    """The day the example's records are read against.

    `CONVENER_EXAMPLE_TODAY` when it is set to an ISO day, and the real day
    otherwise. An unusable value is refused rather than ignored: a renderer
    that meant to pin the clock and misspelled the day would otherwise take a
    picture of a moving fixture and report success (D-25).
    """
    source = os.environ if environ is None else environ
    pinned = source.get(TODAY_ENV, "")
    if not pinned:
        return dt.date.today().isoformat()
    if _parse(pinned) is None:
        raise ValueError(
            f"{TODAY_ENV} is {pinned!r}, which is not a YYYY-MM-DD day -- "
            "it is read to pin the example instance's own records to one "
            "moment, and a value nothing can parse would leave them moving"
        )
    return pinned


def shift_days(day: str) -> int:
    """Whole days -- always a multiple of seven -- from the anchor to the week
    `day` falls in. Negative when `day` is before the anchor, which is the
    ordinary case for a pinned renderer."""
    now = _parse(day)
    if now is None:
        raise ValueError(f"{day!r} is not a YYYY-MM-DD day")
    anchor = _parse(ANCHOR)
    assert anchor is not None, "ANCHOR is not a day"
    return ((now - anchor).days // 7) * 7


def shifted(text: str, day: str) -> str:
    """`text` with every ISO day in it moved into the week of `day`.

    A date the calendar does not have is left exactly as it was found: this
    replaces text, and text it cannot read is text it has nothing to say
    about. The validator is what refuses such a value, by name, and it must
    go on seeing the value somebody actually typed.
    """
    days = shift_days(day)
    if days == 0:
        return text
    delta = dt.timedelta(days=days)

    def move(match: re.Match[str]) -> str:
        found = _parse(match.group(0))
        return match.group(0) if found is None else (found + delta).isoformat()

    return ISO_DAY.sub(move, text)


def _parse(day: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(day)
    except ValueError:
        return None
