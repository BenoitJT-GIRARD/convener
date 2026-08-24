"""Evidence, inside this repository, that the submission queue still empties.

Phase 9, task 4. Tasks 2 and 3 made a public submission wait in a branch
instead of starting a run of its own, and every failure *inside* a drain is
already loud: a refusal is annotated, a deferral is annotated **and** turns
the daily job red (`submission_queue.annotation_lines`). What none of that
covers is the submission that entered the queue and was never handled at
all, because nothing looked. The submitter has their `204` from the relay
and believes they are registered; the repository has nothing red; the drain
may not even have run. For a survey response that is a lost answer. For a
registration it is a person who is told they are registered, never receives
the room link or the matching code, cannot join and can never be issued a
certificate -- and `registration_routing.py`'s own docstring is explicit
that there is no second channel for either.

The queue makes that possible in four ways the one-run-per-submission path
could not:

* the daily drain stops running -- GitHub disables a workflow's `schedule:`
  after 60 days without activity in the repository, and an exhausted
  Actions minute budget simply stops work (AF-2, 2026-08-23 security
  audit);
* the drain runs and fails on the same entry every time;
* entries defer past `submission_queue.MAX_EVENTS_PER_DRAIN` day after day,
  because more than that many distinct events have submissions waiting;
* an entry defers for ever because no key is configured for its event --
  task 2 deliberately keeps such an entry *in* the queue rather than
  dropping it, which is right, and which also means it waits indefinitely
  if nobody looks.

The signal, and why it is an age and not a count
--------------------------------------------------
**The oldest waiting entry's age**, never the number waiting. A hundred
entries that arrived this morning is a healthy queue on a good day; one
entry stuck for five days is a person who will never get into the room. A
count cannot tell those apart, and the threshold it would need is a
guess about how popular an announcement is -- a number this project has
no measurement for and could only ever set wrong (Q-5).

The age is measured from this repository's **own successive observations**,
not from the millisecond the entry id carries. That timestamp is written by
the relay, `submission_queue`'s docstring says in as many words that it is
not trusted and that no date is ever parsed out of an entry id, and the
direction of the risk here is what settles it: an entry claiming an instant
in the future would look permanently young, i.e. would silently never
alarm. An observation this repository committed itself cannot do that.

The cost of that choice is stated rather than hidden: `since` is the first
drain that *saw the entry still waiting*, so up to one drain period of real
waiting happened before the clock starts. Every age here is therefore a
lower bound on how long the submitter has actually waited, and the bounds
in `alarm_bounds` below are what pay for that lag.

Where the two halves live, and why they cannot be one
------------------------------------------------------
An entry that is *known* to be stuck can only be known by something that
read the queue -- which is the daily drain, which by definition is running.
So the daily job is where that alarm belongs, and it is also the only place
that already has the board's thread and team mention (D-07). It posts with
its own body file for the reason phase 8's budget alarm does: the digest
composed in the same job writes `notify-body.md`, and one file for two
messages means whichever is composed last silently replaces the other.

**The drain having stopped altogether cannot be detected from inside it.**
A control hosted in the job it watches reports nothing when that job is the
thing that went quiet -- the identical argument `retention-watchdog.yml`
records for `retention.yml` and, since phase 8, for `data/actions-usage.yml`.
So the second half is a record, `data/queue-watch.yml`, written by the daily
job every day whatever it found, and read on `retention-watchdog.yml`'s own
independent schedule some hours later. Going stale is the finding.

What that leaves uncovered, written down rather than implied
--------------------------------------------------------------
The same residue both existing watchdog checks state in their own headers,
and for the same reason: `retention-watchdog.yml` is itself a scheduled
GitHub Actions workflow. If the whole repository goes dark -- sixty days
inactive, or the month's minutes exhausted before its slot -- the watchdog
is disabled or starved at the same moment the drain is, and nothing running
inside GitHub Actions can report that at zero cost. What survives is
`data/queue-watch.yml` itself: a person who opens this repository, with no
run log and no CI at all, can read the date it names and the entries it
lists and draw the same conclusion by hand.

One overlap is worth naming rather than being quietly relied on.
`data/actions-usage.yml` is written by the *same* daily job, and phase 8's
own liveness check already goes red when it stops moving -- so "the daily
job died" is, today, detected twice. That is an accident of the two records
sharing a job, not a contract: this record is written by the queue steps
and that one by the steps after them, so a day when the queue steps stop
running and the rest of the job carries on is visible here and nowhere
else. The messages differ too, which is the point of a control: one says
the budget is no longer watched, this one says submissions are piling up
unhandled, and the fix is not the same.

Everything in this module is a pure function. `cli.py` supplies the queue's
current contents, the previous record and the clock; nothing here reads a
file, an environment variable or a clock, and nothing here goes near the
network.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from math import ceil
from pathlib import Path
from typing import Any, Final

from .registration_routing import MISSED_DRAINS_COVERED

#: Where the record lives, relative to a repository root -- the same "one
#: function names the path" discipline `retention_liveness.LAST_RUN_PATH`
#: and `submission_queue.LEDGER_PATH` already hold themselves to.
WATCH_PATH: Final = Path("data") / "queue-watch.yml"

#: `data/queue-watch.yml`'s own format version.
WATCH_FILE_VERSION: Final = 1

#: The maintainer-editable thresholds, relative to a repository root.
#: Beside `actions-budget.yml` and `registration-lanes.yml`, never in
#: `data/config.yml` -- see either of those files' own headers for why the
#: app's validator, which refuses by name any key it does not know, makes
#: the latter impossible.
CONFIG_PATH: Final = Path("config") / "queue-drain.yml"

#: `config/queue-drain.yml`'s own format version.
CONFIG_FILE_VERSION: Final = 1

#: How the record spells an instant. Seconds precision, always UTC, always
#: the same width -- the identical spelling
#: `registration_routing.to_routing_data` uses for the cutoffs it
#: publishes, so a reader who has seen one has seen both.
INSTANT_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"

#: An entry has been waiting longer than the configured threshold.
OVERDUE_ALARM: Final = "overdue"

#: How many stuck entries the annotations and the board message name one
#: by one before they say "and N more".
#:
#: A bound, not a preference. A burst against nine open events defers
#: every entry beyond the eighth, and an unbounded list would be an
#: annotation per entry and a comment body past what GitHub accepts -- a
#: message too large to post is no message at all, which is the exact
#: silence this module exists to refuse. The count is always exact; only
#: the enumeration is trimmed, and the committed record holds every line
#: of it.
MOST_LISTED: Final = 10

#: The previous record could not be read, so every age restarts from now.
#: Its own alarm because the consequence is an alarm *postponed*: an entry
#: that had been waiting four days looks brand new again, and silence that
#: was earned by a lost file is exactly the failure this module exists to
#: refuse.
RESTARTED_ALARM: Final = "restarted"


@dataclass(frozen=True)
class Thresholds:
    """`config/queue-drain.yml`, parsed. Two numbers, one per half of this
    module: how long an entry may be known to be waiting before the board
    is told, and how long the record itself may go without moving before
    the watchdog calls the drain dead."""

    alarm_after_hours: int
    max_silent_days: int


@dataclass(frozen=True)
class Waiting:
    """One entry still in the queue after a drain finished, and what is
    known about it.

    `entry` is the path inside the queue branch (`queue/<kind>/<id>.json`)
    and `reason` is a note the drain wrote (`submission_queue.Note.reason`)
    -- an entry name, an event id, a file path. Both are already public by
    construction, and neither ever carries anything decrypted or anything a
    submitter typed: this record is committed to the default branch, so
    nothing else could be allowed in it.
    """

    entry: str
    since: datetime
    reason: str = ""


@dataclass(frozen=True)
class Record:
    """`data/queue-watch.yml`, parsed: when the queue was last looked at,
    and what was still in it at that moment."""

    observed_at: datetime
    waiting: tuple[Waiting, ...] = ()


@dataclass(frozen=True)
class Alarm:
    """One reason to be loud, and the sentence that says it -- the same
    shape `actions_usage.Alarm` has, so `kind` can be pinned by a test
    without matching prose."""

    kind: str
    text: str


def flatten_reason(reason: str) -> str:
    """One `submission_queue.Note.reason`, made safe to put on a line of a
    tab-separated file and in one line of a committed record.

    Every run of whitespace becomes a single space. Not cosmetic: a
    deferral's reason can be a YAML parser's own error message
    (`drain`'s "a committed file this drain cannot parse" path builds it
    as `f"{path}: {exc}"`), and PyYAML's exceptions are several lines
    long. A newline in the middle of a record whose format is one entry
    per line means the next drain reads half a path as an entry name, and
    an entry name nothing matches is an alarm about a submission that does
    not exist -- or, worse, silence about one that does.
    """
    return " ".join(reason.split())


def watch_path(root: Path) -> Path:
    """`data/queue-watch.yml`, relative to `root`. Pure path computation:
    reads nothing, touches nothing."""
    return root / WATCH_PATH


def config_path(root: Path) -> Path:
    """`config/queue-drain.yml`, relative to `root`."""
    return root / CONFIG_PATH


def thresholds_from_data(data: Any) -> Thresholds:
    """Parse an already YAML-loaded `config/queue-drain.yml`.

    Raises `ValueError` on anything that is not this exact shape -- the
    same closed-shape discipline `registration_routing.threshold_from_data`
    holds itself to, and for the same sharpened reason: a threshold this
    function guessed at is an alarm that fires at a moment nobody chose. A
    file that is absent, malformed, or carrying a version this code does
    not know is not a default to fall back on; it is a `ValueError` the
    caller reports.
    """
    named = CONFIG_PATH.as_posix()
    if not isinstance(data, dict) or data.get("v") != CONFIG_FILE_VERSION:
        raise ValueError(f"{named} is not a supported format version")
    values: dict[str, int] = {}
    for key in ("alarm_after_hours", "max_silent_days"):
        value = data.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{named} holds no positive whole {key} value")
        values[key] = value
    return Thresholds(**values)


def alarm_bounds(period_hours: int, queue_beyond_hours: int) -> tuple[int, int]:
    """The lowest and the highest value `alarm_after_hours` may take,
    derived from the drain's own cadence and from the lane rule -- never a
    number typed twice.

    **The floor.** `MISSED_DRAINS_COVERED` times the drain's period, the
    same margin `registration_routing.floor_hours` reserves and for the
    same recorded reason: `sweep-and-notify.yml`'s own header says GitHub's
    scheduled runs "are routinely ten to twenty minutes late and are
    dropped outright under load", so a drain that has not happened yet is
    not evidence of anything being stuck. An alarm that fires before a
    healthy drain has had its chance is an alarm people learn to ignore,
    and this project has thirteen recorded instances of a control that
    failed to bite.

    **The ceiling, which is the half that is easy to forget.** A queued
    registration's event is at least `queue_beyond_hours` away when it is
    submitted (that is the whole of the lane rule). One period of that is
    spent before this module's clock even starts, because `since` is the
    first drain that *observed* the entry, not the moment it arrived; and
    one more has to be left after the alarm, or the operator is told about
    a registration at the moment its seminar begins. So the alarm must fire
    no later than `queue_beyond_hours` minus those two periods. An alarm
    later than that is not an alarm, it is a post-mortem.

    Returns `(floor, ceiling)`. The two can meet, and with this
    repository's current settings they do -- see
    `tools/tests/test_queue_watch.py`, which is where a configuration
    outside them goes red. They can also cross, which is a real finding
    rather than a broken test: it says the lane threshold has been cut so
    close to the drain's cadence that no alarm can both wait for a healthy
    drain and still leave anybody time to act.
    """
    margin = MISSED_DRAINS_COVERED * period_hours
    return margin, queue_beyond_hours - margin


def silence_floor_days(period_hours: int) -> int:
    """The lowest `max_silent_days` may be, in whole days: the same
    `MISSED_DRAINS_COVERED` periods the alarm's own floor allows for, in
    the unit the record's staleness is measured in.

    Rounded **up**, so a drain running more often than daily never lowers
    this below one day -- a record that must move every day would call a
    single dropped schedule a dead drain, which is the false alarm
    `retention_liveness.MAX_SILENT_DAYS` already declines to raise.
    """
    return max(1, ceil(MISSED_DRAINS_COVERED * period_hours / 24))


def _instant_from(raw: Any, what: str) -> datetime:
    """One `INSTANT_FORMAT` string, parsed, or a `ValueError` naming what
    it was supposed to be. Never a guess at another spelling: this file is
    written by one function in this repository, and a value in any other
    shape means something hand-edited it."""
    named = WATCH_PATH.as_posix()
    if not isinstance(raw, str):
        raise ValueError(f"{named} holds no usable {what}")
    try:
        return datetime.strptime(raw, INSTANT_FORMAT).replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(f"{named} holds an invalid {what}: {raw!r}") from exc


def record_from_data(data: Any) -> Record:
    """Parse an already YAML-loaded `data/queue-watch.yml`.

    Raises `ValueError` on anything that is not this exact format. A
    *missing* file is not this function's business -- it means no drain has
    ever written one, which the caller handles on its own.
    """
    named = WATCH_PATH.as_posix()
    if not isinstance(data, dict) or data.get("v") != WATCH_FILE_VERSION:
        raise ValueError(f"{named} is not a supported format version")
    observed_at = _instant_from(data.get("observed_at"), "observed_at instant")
    raw_waiting = data.get("waiting")
    if not isinstance(raw_waiting, list):
        raise ValueError(f"{named} holds no usable waiting list")
    waiting: list[Waiting] = []
    for item in raw_waiting:
        if not isinstance(item, dict):
            raise ValueError(f"{named} holds a waiting item that is not a mapping")
        entry = item.get("entry")
        if not isinstance(entry, str) or not entry:
            raise ValueError(f"{named} holds a waiting item with no entry path")
        reason = item.get("reason", "")
        if not isinstance(reason, str):
            raise ValueError(f"{named} holds a waiting item with an unusable reason")
        waiting.append(
            Waiting(
                entry=entry,
                since=_instant_from(item.get("since"), f"since instant for {entry}"),
                reason=reason,
            )
        )
    return Record(observed_at=observed_at, waiting=tuple(waiting))


def record_to_data(record: Record) -> dict[str, Any]:
    """The plain, YAML-safe structure `cli.py` hands to its own YAML writer
    -- the inverse of `record_from_data`.

    Ordered oldest first, then by entry name, so two drains that saw the
    same queue write the same bytes and produce no commit of their own
    beyond the moving `observed_at`.
    """
    return {
        "v": WATCH_FILE_VERSION,
        "observed_at": record.observed_at.astimezone(UTC).strftime(INSTANT_FORMAT),
        "waiting": [
            {
                "entry": item.entry,
                "since": item.since.astimezone(UTC).strftime(INSTANT_FORMAT),
                "reason": item.reason,
            }
            for item in sorted(record.waiting, key=lambda w: (w.since, w.entry))
        ],
    }


def next_record(
    previous: Record | None, still_waiting: Mapping[str, str], now: datetime
) -> Record:
    """The record this drain commits: everything still in the queue, each
    carrying the first instant this repository observed it waiting.

    `still_waiting` maps an entry path to the reason the last drain gave
    for it, or `""` where it gave none.

    Two rules, and each is a decision rather than a convenience:

    * **An entry the previous record did not name starts its clock now.**
      Including one that arrived while this very run was working -- a
      brand-new submission is not late, and dating it any earlier would
      alarm about a queue that is behaving.
    * **An entry the previous record named keeps its `since`.** That is
      what makes the age an age at all, and it is the one field a
      restarted history destroys (see `RESTARTED_ALARM`).

    The reason is refreshed to whatever the last drain said, *except* that
    a drain which said nothing does not erase what an earlier one did: a
    run that never reached the drain step records no reason for anything,
    and "no private key configured for event X" from yesterday is worth
    more to the operator than a blank today.

    Self-pruning, exactly as `submission_queue.next_ledger` is and for a
    stronger reason here: an entry no longer in the queue has been handled
    and cleared, entry ids are unique, and nothing can bring that name
    back -- so carrying it would be carrying an alarm about a submission
    that is done.
    """
    known = {item.entry: item for item in previous.waiting} if previous else {}
    waiting = []
    for entry in sorted(still_waiting):
        reason = still_waiting[entry]
        seen = known.get(entry)
        waiting.append(
            Waiting(
                entry=entry,
                since=seen.since if seen is not None else now,
                reason=reason or (seen.reason if seen is not None else ""),
            )
        )
    return Record(observed_at=now, waiting=tuple(waiting))


def hours_waiting(since: datetime, now: datetime) -> int:
    """How long an entry has been known to be waiting, in whole hours,
    **rounded up**.

    Rounded up rather than down, and that is not a detail. A drain observes
    an entry at whatever moment GitHub actually starts the job, and the
    same workflow's own header records that its scheduled runs are
    routinely ten to twenty minutes late. A late first observation followed
    by an early later one makes two full periods measure as 47 hours and 20
    minutes; floored, that is 47, one short of a 48-hour threshold, and the
    alarm is postponed by a whole further period -- silently, because of
    minutes of jitter. Rounding up spends the error in the direction that
    can only ever make the alarm early, never late, which is the only
    direction a control may err in.

    Never raises and never clamps: a record dated in the future -- a hand
    edit, a clock skew between two runners -- yields zero or a negative
    number, which `is_overdue` reads as healthy. This function measures
    elapsed time; it does not judge the record it was handed.
    """
    elapsed = now.astimezone(UTC) - since.astimezone(UTC)
    return ceil(elapsed.total_seconds() / 3600)


def is_overdue(elapsed_hours: int, alarm_after_hours: int) -> bool:
    """Whether `elapsed_hours` (see `hours_waiting`) has reached the
    configured threshold.

    `>=`, not `>`, and deliberately not the `>` that
    `retention_liveness.is_stale` uses. That function counts days against a
    tolerance for a *late* job; this one counts hours against a threshold
    that is already the longest a healthy queue can take (`alarm_bounds`).
    Reaching it is the failure, not the last healthy moment -- and because
    a drain only ever observes at whole multiples of its own period, `>`
    would push every alarm a full further period past the value the
    maintainer chose, which is a day of somebody's margin given away by an
    off-by-one nobody would see.
    """
    return elapsed_hours >= alarm_after_hours


def overdue(
    record: Record, now: datetime, alarm_after_hours: int
) -> tuple[Waiting, ...]:
    """Every entry in `record` that has reached the threshold, oldest
    first. Empty is a healthy queue."""
    return tuple(
        item
        for item in sorted(record.waiting, key=lambda w: (w.since, w.entry))
        if is_overdue(hours_waiting(item.since, now), alarm_after_hours)
    )


def days_since(observed_on: date, today: date) -> int:
    """`today - observed_on`, in whole days -- the twin of
    `actions_usage.days_since`, kept here so the watchdog's arithmetic and
    this module's record stay one thing."""
    return (today - observed_on).days


def is_stale(elapsed_days: int, max_silent_days: int) -> bool:
    """Whether the record itself has gone quiet, i.e. whether the drain has
    stopped running. Its own function so the boundary -- exactly
    `max_silent_days` is still healthy, one more is not -- is something a
    test can pin without building a fixture and two dates to reach it."""
    return elapsed_days > max_silent_days


def alarms(
    stuck: Sequence[Waiting], now: datetime, *, restarted: bool = False
) -> tuple[Alarm, ...]:
    """Every reason this observation should make a noise. Empty is quiet.

    Two kinds, and the second exists so that this control can be *wrong*
    and be noticed (D-25): entries that have waited past the threshold, and
    a previous record that could not be read at all -- which loses every
    age and would otherwise buy silence.
    """
    fired: list[Alarm] = []
    if stuck:
        oldest = stuck[0]
        fired.append(
            Alarm(
                OVERDUE_ALARM,
                f"{len(stuck)} public submission(s) have been waiting in the "
                "queue since before the last drain that could have handled "
                f"them. The oldest, {oldest.entry}, has been known to be "
                f"waiting for {hours_waiting(oldest.since, now)} hour(s)"
                + (f" -- {oldest.reason}" if oldest.reason else "")
                + ". Nothing has been lost: every entry named below is still "
                "in the queue and will be handled by the first drain that "
                "can reach it.",
            )
        )
    if restarted:
        fired.append(
            Alarm(
                RESTARTED_ALARM,
                f"{WATCH_PATH.as_posix()} could not be read, so how long "
                "each entry has been waiting is no longer known and every "
                "age below restarts from now. An entry that had been stuck "
                "for days looks new again, which is silence this control "
                "did not earn.",
            )
        )
    return tuple(fired)


def _listed(stuck: Sequence[Waiting]) -> tuple[tuple[Waiting, ...], int]:
    """The entries to name one by one, and how many are left over -- see
    `MOST_LISTED`."""
    return tuple(stuck[:MOST_LISTED]), max(0, len(stuck) - MOST_LISTED)


def annotation_lines(fired: Sequence[Alarm], stuck: Sequence[Waiting]) -> list[str]:
    """Every line the daily job prints for GitHub Actions to render on the
    run: one `::error::` per alarm, then one per stuck entry naming its own
    reason, because the fix differs by reason and a count does not say
    which one it is.

    `::error::` for both, not `::warning::`, and unlike
    `submission_queue.annotation_lines` there is no stranger-controlled
    half to keep out of the colour of the run: an entry can only reach this
    threshold by surviving drains that could not finish it, which is the
    operator's to fix in every case.

    Composed here rather than in `cli.py` so a test can read the exact text
    without capturing stdout.
    """
    lines = [f"::error::[{alarm.kind}] {alarm.text}" for alarm in fired]
    named, beyond = _listed(stuck)
    lines += [
        f"::error::{item.entry}: waiting, "
        + (item.reason or "no reason recorded by the last drain")
        for item in named
    ]
    if beyond:
        lines.append(f"::error::and {beyond} more entry(ies) past the threshold")
    return lines


def message(
    fired: Sequence[Alarm], stuck: Sequence[Waiting], now: datetime
) -> str | None:
    """The alert body, or `None` when nothing fired.

    Text only -- no address. `notify.dispatch` is what pairs this with a
    thread and a team mention, so an unconfigured repository composes
    nothing postable at all rather than a message addressed to nobody.

    Every identifier in it is a queue entry path or an event id, both
    already public by construction: this message goes to a repository
    thread, and nothing decrypted, nothing typed by a submitter and no
    address may ever reach one.
    """
    if not fired:
        return None
    lines = ["Workshop series - the submission queue is not emptying", ""]
    for alarm in fired:
        lines += [f"  - [{alarm.kind}] {alarm.text}", ""]
    if stuck:
        named, beyond = _listed(stuck)
        lines.append("Still waiting:")
        lines += [
            f"  - {item.entry}, {hours_waiting(item.since, now)} hour(s) -- "
            + (item.reason or "no reason recorded by the last drain")
            for item in named
        ]
        if beyond:
            lines.append(f"  - and {beyond} more, all of them in the record below")
        lines.append("")
    lines += [
        "A registration that waits does not get its room link or its "
        "matching code, and there is no other channel for either.",
        "",
        f"The full list is committed to {WATCH_PATH.as_posix()} in this "
        "repository -- no run log to open.",
    ]
    return "\n".join(lines)


def summary(record: Record, stuck: Sequence[Waiting]) -> str:
    """The one line the daily job prints. One line, deliberately: what a
    person is meant to read is the committed file; what a person is meant
    to be *told* is the alarm (`actions_usage.summary_line`'s own note)."""
    return (
        f"{len(record.waiting)} submission(s) still waiting in the queue, "
        f"{len(stuck)} of them past the alarm threshold"
    )
