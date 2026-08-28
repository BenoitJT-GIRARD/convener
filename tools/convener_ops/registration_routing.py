"""Which of the two lanes a registration takes, and the floor under it.

The survey response goes into `submission_queue`'s own
queue, and a registration used to be left alone: a survey response
sends nothing back to anybody, so the slowest cadence costs the person who
submitted it nothing at all, while **a registration's confirmation e-mail
is not a receipt, it is the entry ticket.** It carries the room link and
the matching code the participant has to put in their display name for
their attendance to be recognised -- and therefore for their certificate to
exist -- and `confirmation.py`'s own template says the room link "only ever
reaches a participant here... this e-mail is the one channel it goes out
on". A fixed delay is out: somebody registering on the morning of the
seminar must still get their link.

Two lanes, and the distance to the event is the only thing that decides
-------------------------------------------------------------------------
* **Far from the event** -- the relay writes the envelope to the queue
  branch and starts nothing. The drain that already runs once a day
  (`.github/workflows/sweep-and-notify.yml`) stores it and sends the
  confirmation. **Zero additional runs**, and this is where the bulk of an
  announcement's registrations live.
* **Close to the event** -- the relay sends the `repository_dispatch` it
  always sent, `registration.yml` runs unchanged, and the confirmation
  goes out within the minute. Same cost as before this phase, same latency.

There is deliberately no third, hourly lane in between. It would need a
*scheduled job of its own*, i.e. a billed run every hour whether or not
anybody registered -- far more than the runs it would save, on a repository
whose whole constraint is that the bill stays at zero.

The floor, which is the part that is not a matter of taste
-----------------------------------------------------------
The threshold is configuration (`config/registration-lanes.yml`), and a
maintainer is meant to move it. What a maintainer must *not* be able to do
is move it somewhere that silently loses people: set it to twelve hours
against a once-daily drain and a far-lane registrant is told they are
registered and then never hears again until after the seminar.

So the floor is derived here, from the drain's own cron, and
`tools/tests/test_registration_routing.py` fails if the configured value
drops below it. `MISSED_DRAINS_COVERED` is why the floor is *twice* the
drain's period rather than once: `sweep-and-notify.yml`'s own header
comment records that GitHub's scheduled runs "are routinely ten to twenty
minutes late and are dropped outright under load", so the next drain to
actually run can be two periods away, and the confirmation still has to
land before the event.

`drain_period_hours` refuses to evaluate a cron shape it does not
positively understand rather than guessing at one -- the same discipline
the workflow sweep adopted for GitHub's branch filters, and for
the same reason: a floor that answered "probably 24 hours" about a cron it
misread would be worse than no floor at all. A maintainer who changes the
drain's cadence to a shape this cannot read gets a red test naming the
shape, not a wrong number.

How the answer reaches the relay
----------------------------------
`services/signup-relay` cannot read `data/speakers.yml` (it is YAML, and
that worker has no parser for it) and must not be trusted to re-derive
Europe/Paris start times from a date and an optional wall-clock string.
So the whole of the arithmetic happens here, and what is published is one
already-resolved instant per event: **the moment that event stops being
far away**. `to_routing_data` writes it to
`public-data/registration-routing.json`, `deploy.yml` commits it, and the
worker's entire share of the rule becomes `Date.now() < cutoff`.

That file is a projection, exactly like `public-data/survey-status.json`
beside it, read by the relay through the Contents API with the credential
and the call shape it already uses for `keys/events/<id>.pub`. It is
regenerated whenever `data/speakers.yml` moves, which is precisely when an
event's date can have changed. A *threshold* edited in `config/` lands one
run later -- see that file's own header for the one-line answer to that.

Unknown is not "far"
----------------------
Every failure to determine an event's cutoff cleanly -- no record, no
date, a date nobody can parse, a routing file the relay could not read at
all -- resolves to **the immediate lane**, never the queue. This is the
opposite direction from `cli._survey_enabled`, which guesses "closed" on
every ambiguity, and the asymmetry is the point: there, the risk being
guarded against is storing an answer nobody asked for, so silence must
mean no; here, the risk is a participant who never receives the link that
is their only way into the room, so silence must mean send it now. The
cost of guessing wrong in this direction is one billed run.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any, Final

from .governance import PARIS
from .paths import PUBLIC_DATA_DIR

#: The maintainer-editable threshold, relative to a repository root. Beside
#: `actions-budget.yml` and `integrations.yml`, never in `data/config.yml`
#: -- see that file's own header for why the app's validator makes the
#: latter impossible.
CONFIG_PATH: Final = Path("config") / "registration-lanes.yml"

#: `config/registration-lanes.yml`'s own format version.
CONFIG_FILE_VERSION: Final = 1

#: The projection the relay reads, relative to a repository root.
#: `.gitignore` carries a named exception for it, the same shape
#: `!public-data/survey-status.json` already has, because
#: `deploy.yml` needs a tracked path to commit it to.
ROUTING_PATH: Final = PUBLIC_DATA_DIR / "registration-routing.json"

#: `public-data/registration-routing.json`'s own format version. Read by
#: `services/signup-relay/src/index.js`, which refuses any other value
#: rather than guessing at a shape it does not know.
ROUTING_FILE_VERSION: Final = 1

#: The workflow whose schedule *is* the drain's cadence. Named here so the
#: floor is derived from the real file rather than from a number somebody
#: retyped -- the two cannot drift if only one of them exists.
DRAIN_WORKFLOW_PATH: Final = Path(".github") / "workflows" / "sweep-and-notify.yml"

#: How many drains in a row the floor assumes may not happen. Two, not one:
#: `sweep-and-notify.yml`'s own header records that GitHub drops scheduled
#: runs under load, so the next drain that actually runs can be a whole
#: extra period away. One is what a floor of "the period itself" would
#: assume, and it is the assumption that loses somebody their seat.
MISSED_DRAINS_COVERED: Final = 2

#: `on:` parses to the boolean `True` under PyYAML's YAML-1.1 resolver, not
#: to the string `"on"`. Named rather than written as a bare subscript, the
#: same way `tools/tests/conftest.py` names it.
_ON_KEY_UNDER_YAML_1_1: Final = True

#: The one cron shape this module will evaluate: a fixed minute and a fixed
#: hour, every day. `sweep-and-notify.yml` is `0 5 * * *`. Anything else --
#: a step, a list, a day-of-week restriction -- is refused by name, never
#: approximated.
_DAILY_CRON_RE: Final = re.compile(r"^\s*(\d+)\s+(\d+)\s+\*\s+\*\s+\*\s*$")

_HOURS_PER_DAY: Final = 24

#: The start of day this module assumes for an event whose record carries
#: no usable wall-clock time. Midnight Europe/Paris, deliberately not
#: `visual.STANDING_START_LOCAL`'s 12:30 -- see `event_start` for why the
#: earlier of the two is the safe guess.
_CONSERVATIVE_START: Final = time(0, 0)


class CronShapeError(ValueError):
    """A schedule this module will not put a number on.

    Its own class rather than a bare `ValueError` so the test that derives
    the floor can say *which* half failed: a cron nobody here can read is a
    finding about the workflow, not about the configured threshold.
    """


def threshold_from_data(data: Any) -> int:
    """Parse an already YAML-loaded `config/registration-lanes.yml`.

    Raises `ValueError` on anything that is not this exact shape -- the
    same closed-shape discipline `submission_queue.ledger_from_data` holds
    itself to, and for a sharper reason here than tidiness: a threshold
    this function guessed at is a threshold that routes a last-minute
    registrant into a queue they cannot afford to wait in. A file that is
    absent, malformed, or carrying a version this code does not know is not
    a default to fall back on; it is a `ValueError` the caller reports.
    """
    if not isinstance(data, dict) or data.get("v") != CONFIG_FILE_VERSION:
        raise ValueError(f"{CONFIG_PATH.as_posix()} is not a supported format version")
    hours = data.get("queue_beyond_hours")
    if not isinstance(hours, int) or isinstance(hours, bool) or hours <= 0:
        raise ValueError(
            f"{CONFIG_PATH.as_posix()} holds no positive whole queue_beyond_hours value"
        )
    return hours


def drain_period_hours(workflow: Mapping[str | bool, Any]) -> int:
    """The guaranteed cadence of the drain, in hours, read out of an
    already-loaded `sweep-and-notify.yml`.

    Only `schedule:` counts. That workflow also declares `push:` and
    `workflow_dispatch:`, and both can start the daily job -- but neither
    is a *cadence*: nothing promises anybody pushes, or dispatches, on any
    particular day, and a floor built on either would be a floor built on
    somebody's habits.

    Raises `CronShapeError`, naming what it saw, for every schedule this
    module cannot put an exact number on: no `schedule:` block, more than
    one `cron:` entry (their combined worst-case gap is not a thing this
    function will guess at), or a cron that is not the fixed
    minute/fixed hour/every day shape. Refusing is the whole point -- see
    the module docstring.
    """
    triggers = workflow.get(_ON_KEY_UNDER_YAML_1_1)
    if not isinstance(triggers, dict):
        raise CronShapeError(
            f"{DRAIN_WORKFLOW_PATH.as_posix()} declares no `on:` mapping, so "
            "it has no schedule to derive the drain's period from"
        )
    schedule = triggers.get("schedule")
    if not isinstance(schedule, list) or not schedule:
        raise CronShapeError(
            f"{DRAIN_WORKFLOW_PATH.as_posix()} declares no `schedule:` entry, "
            "so nothing guarantees the drain runs at all"
        )
    if len(schedule) != 1:
        raise CronShapeError(
            f"{DRAIN_WORKFLOW_PATH.as_posix()} declares {len(schedule)} cron "
            "entries; the worst-case gap between several schedules is not "
            "something this module will guess at"
        )
    entry = schedule[0]
    cron = entry.get("cron") if isinstance(entry, dict) else None
    if not isinstance(cron, str) or not _DAILY_CRON_RE.match(cron):
        raise CronShapeError(
            f"{DRAIN_WORKFLOW_PATH.as_posix()} schedules {cron!r}, which is "
            "not the fixed-minute, fixed-hour, every-day shape this module "
            "knows how to put a period on"
        )
    return _HOURS_PER_DAY


def floor_hours(period_hours: int) -> int:
    """The lowest threshold that is still safe against the drain that
    exists -- `MISSED_DRAINS_COVERED` times its period. See the module
    docstring for why the multiplier is two and not one."""
    return period_hours * MISSED_DRAINS_COVERED


def event_start(record: Mapping[str, Any]) -> datetime | None:
    """The Europe/Paris instant an event begins, or `None` when this record
    does not say.

    `time` is optional on a speaker record and routinely empty
    (`sweep._has_ended` already has to cope with exactly that). Where it is
    absent this falls back to **midnight**, not to the project's standing
    12:30 start: midnight is the more conservative of the two, because a
    start read *earlier* than the real one only ever moves a registration
    into the immediate lane, which costs a run and never a participant.
    Guessing 12:30 and being wrong would move one the other way.

    Never raises. A record with no date, a date nobody can parse, or a time
    that is not `HH:MM` all resolve to `None`, which the caller reads as
    "no cutoff for this event" -- and an event with no cutoff is dispatched
    immediately, never queued.
    """
    raw_date = record.get("date")
    if not isinstance(raw_date, str) or not raw_date:
        return None
    try:
        day = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return None

    raw_time = record.get("time")
    if isinstance(raw_time, str) and raw_time:
        try:
            clock = datetime.strptime(raw_time, "%H:%M").time()
        except ValueError:
            # A time nobody can parse is not a reason to lose the date:
            # fall back to the same conservative midnight an absent time
            # gets, rather than dropping the event out of the file
            # entirely -- both are "we are not sure", and the safe answer
            # to that is the earlier instant, not no answer.
            clock = _CONSERVATIVE_START
    else:
        clock = _CONSERVATIVE_START

    return datetime.combine(day, clock, tzinfo=PARIS)


def queue_until(start: datetime, threshold_hours: int) -> datetime:
    """The instant `start`'s event stops being far away: submit before it
    and the registration waits for the drain, submit at it or after and it
    is dispatched immediately.

    A boundary, and a closed one on the queue's side only: a registration
    landing exactly here takes the *immediate* lane, because the whole
    reason this instant exists is that everything from here on is too
    close to wait, and an off-by-one at a boundary must fall on the side
    that still delivers the link.

    **Converted to UTC before the subtraction, and that is not a
    formatting detail.** Python's `datetime` subtraction takes a documented
    shortcut when both operands carry the same `tzinfo` object: it ignores
    the zone and works on the wall clocks. Subtracting four days from a
    Europe/Paris instant that sits on the far side of a daylight-saving
    change therefore lands an hour away from the instant it should -- and
    an hour of a participant's margin, silently, in whichever direction the
    change went. Working in UTC makes the arithmetic elapsed time, which is
    what "so many hours before the event" means. Found by driving the
    October boundary, not by reading this line.
    """
    return start.astimezone(UTC) - timedelta(hours=threshold_hours)


def to_routing_data(speakers: Sequence[object], threshold_hours: int) -> dict[str, Any]:
    """`public-data/registration-routing.json`'s whole content: one
    already-resolved UTC instant per event that has a usable date.

    A projection of exactly two fields, `edition_code` and `date` (plus
    `time` where it is set) -- no name, no address, no title, nothing about
    a speaker at all. There is no allowlist to maintain here because there
    is nothing else this function could emit, the same property
    `public_data.to_survey_status` has for its own single field.

    Keyed on the lower-cased `edition_code`, the rule
    `platform.find_speaker` owns and `SignupForm.tsx` and the relay both
    already use -- never on `id`, which is the record's own internal key
    and means nothing to a submitter. A record with no usable
    `edition_code`, or no usable date, is simply absent: the relay reads an
    absent event as "dispatch immediately", which is where an event nobody
    can date belongs.

    `Sequence[object]`, not a sequence of mappings, for
    `to_survey_status`'s own stated reason: the caller hands over whatever
    `data/speakers.yml` parsed to, and a hand-edited list whose entries are
    not mappings is what the `isinstance` guard below is actually for.
    """
    cutoffs: dict[str, str] = {}
    for entry in speakers:
        if not isinstance(entry, dict):
            continue
        edition_code = entry.get("edition_code")
        if not isinstance(edition_code, str) or not edition_code:
            continue
        start = event_start(entry)
        if start is None:
            continue
        cutoff = queue_until(start, threshold_hours)
        cutoffs[edition_code.lower()] = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "v": ROUTING_FILE_VERSION,
        "queue_until": dict(sorted(cutoffs.items())),
    }


def lane(cutoff: datetime | None, submitted_at: datetime) -> str:
    """`"queue"` or `"immediate"` for one submission -- the Python twin of
    `services/signup-relay/src/index.js::registrationLane`, and the one
    place the rule is written on this side.

    Nothing in production calls this: the decision is the relay's, because
    only the relay knows the instant a submission arrived. It exists so the
    boundary the worker implements can be driven from fixtures here, in the
    language the rest of this rule already lives in, rather than being
    described twice and checked once.
    """
    if cutoff is None:
        return "immediate"
    return "queue" if submitted_at < cutoff else "immediate"
