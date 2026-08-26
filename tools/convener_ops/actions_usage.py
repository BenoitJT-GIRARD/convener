"""What a run really cost, and how fast the budget is actually going.

Every minute figure this project has ever written down is a
`timeout-minutes` ceiling. Nothing in this repository has ever run on
GitHub, so the gap between those ceilings and a real duration is unknown
and plausibly a factor of five to ten. This
module is the half of closing that gap that can be computed offline: the
arithmetic that turns what the Actions API reports into a billed figure, a
rate, and the reasons an alarm should go off.

Two questions, deliberately kept apart
--------------------------------------
**What did it cost.** `summarise` reduces a window of runs to billed
minutes, split by the event that started each one. That is written to
`data/actions-usage.yml`, a committed file: legible by opening this
repository, with no CI running and no log to scroll -- the same shape
`data/retention-last-run.yml` already has, and for the same reason (see
`retention_liveness.py`'s own module docstring).

**Is the budget about to run out.** `alarms` answers that, and the answer
is loud or it is nothing: an exhausted Actions budget does not fail
noisily, it simply stops work, and `retention.yml` -- a promise with legal
weight -- is one of the things it stops.
A counter nobody reads is not a control (D-25).

Why a rate over a rolling window, and never a monthly total
-----------------------------------------------------------
A monthly counter announces on the 28th that nothing is left. What has to
be visible is the day an announcement brings three hundred registrations
in two hours -- the one place this budget can break suddenly instead of
drifting. So the measurement is a **window of the last `window_days`
days**, projected to a month, and the submission half is additionally
watched **per day**, on its busiest day rather than its average.

The finest grain available at zero cost is one day: the host that runs this
(`.github/workflows/sweep-and-notify.yml`'s daily job) runs once a day, so
a burst inside a day is seen the following morning, not while it happens.
That is a real limit, stated rather than papered over.

What these numbers are **not**
------------------------------
**They are a lower bound on the bill, never the bill.** The 2,000 free
minutes belong to the *organisation* that owns this repository and are
shared with every other private repository it owns. This module can only
see this repository's own runs -- the endpoint that reports the
organisation's actual consumption needs an `admin:org` credential nobody
has created, and requiring one would make this control unable to run at
all. Every rendering below says so in as many words, so that a reader
cannot mistake a per-repository sum for an invoice.

**They omit the minute multipliers.** GitHub bills a macOS runner at ten
times a Linux one and Windows at two. Everything this repository runs is
`ubuntu-latest`, so the multiplier is 1 and the sum below is in real billed
minutes; the moment a workflow moves to another runner OS, this arithmetic
becomes an undercount. `summarise` therefore keeps the per-OS split it was
given rather than flattening it, and `alarms` reports a non-Linux runner as
a finding instead of quietly mis-adding it.

Like the rest of `convener_ops` this module is pure: it reads no file, makes no
network call, and knows nothing about GitHub beyond the shape of two JSON
payloads it is handed. `cli.py` is the only module that touches disk, and
the API calls themselves live in a workflow step, in `gh` -- no test in
this repository ever reaches the network.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil
from pathlib import Path
from typing import Any, Final

#: Where a maintainer edits the thresholds. Deliberately **not**
#: `data/config.yml`: that file is the app's own governance config, read
#: and rewritten by the browser through a closed shape
#: (`app/src/data/validate.ts::readConfig` refuses any key it does not
#: know, and `tools/tests/test_yaml_boundary.py` pins the two writers
#: byte-for-byte), so a key the app has no use for could not be added
#: there without a cross-language change to four files. `config/` is where
#: this repository already keeps declarations that tooling reads and the
#: app never does -- `config/integrations.yml` is the precedent.
BUDGET_PATH: Final = Path("config") / "actions-budget.yml"

#: Where the measurement is written: a committed file, not a log line.
USAGE_PATH: Final = Path("data") / "actions-usage.yml"

#: `data/actions-usage.yml`'s own format version -- the same file-level
#: guard `retention_liveness.LAST_RUN_FILE_VERSION` carries.
USAGE_FILE_VERSION: Final = 1

#: GitHub bills **per job, rounded up to the whole minute**. A job that
#: does twenty seconds of useful work bills a full minute; eight such jobs
#: bill eight. That rounding is why `billed_minutes` is applied to each
#: job's own duration and never to a run's total.
BILLED_MINUTE_MS: Final = 60_000

#: Days in an average month, for projecting a window's rate. The same 30.4
#: the declared ceilings were computed with, so the two are
#: directly comparable.
DAYS_PER_MONTH: Final = 30.4

#: How many daily observations `data/actions-usage.yml` keeps. Sixty is two
#: months: long enough to read a trend off the file itself rather than off
#: `git log`, short enough that the file stays a page a person will read.
HISTORY_LENGTH: Final = 60

#: The event GitHub reports for a cron run. This half of the budget is
#: fixed and cannot surprise anybody.
SCHEDULED_EVENT: Final = "schedule"

#: The event GitHub reports for a public submission arriving through a
#: relay -- `registration.yml` and `candidate-form.yml` trigger on
#: `repository_dispatch`. **This is the only item in the whole budget whose
#: volume is decided by strangers, and the only one that grows when the
#: series succeeds.**
#:
#: The survey is off this line entirely: a survey
#: response is written to the submission queue and handled by a step of a
#: job that already runs, so it produces no run of its own and appears in
#: no measurement here. What that means for a reading of
#: `data/actions-usage.yml` spanning the change is that the count drops
#: without the traffic dropping.
SUBMISSION_EVENT: Final = "repository_dispatch"

#: The runner OS whose billed minute is worth one minute. Everything this
#: repository declares is `ubuntu-latest`; see the module docstring for why
#: anything else makes the sum below an undercount rather than a number to
#: quietly multiply.
LINUX_RUNNER: Final = "UBUNTU"

#: A `created_at` as the Actions API writes it. Only the leading day is
#: read; the rest is not parsed, because nothing here needs an hour.
_CREATED_AT_RE: Final = re.compile(r"^(\d{4}-\d{2}-\d{2})T")

#: Alarm kinds. Strings rather than an enum so a test can pin *which* alarm
#: fired without matching its prose, and so the same names can appear in
#: `data/actions-usage.yml` unchanged.
RATE_ALARM: Final = "rate"
SUBMISSIONS_ALARM: Final = "submissions"
UNREADABLE_ALARM: Final = "unreadable"
TRUNCATED_ALARM: Final = "truncated"
RUNNER_ALARM: Final = "runner"

#: The sentence every rendering carries. One place, so the caveat cannot
#: drift between the committed file and the posted message.
LOWER_BOUND_NOTE: Final = (
    "These minutes are this repository's own runs only. The free monthly "
    "allowance belongs to the organisation and is shared with every other "
    "private repository it owns, so this is a lower bound on the bill, "
    "never the bill itself."
)


def budget_path(root: Path) -> Path:
    """`config/actions-budget.yml`, relative to `root`. Pure path
    computation: reads nothing."""
    return root / BUDGET_PATH


def usage_path(root: Path) -> Path:
    """`data/actions-usage.yml`, relative to `root`. Pure path
    computation: reads nothing."""
    return root / USAGE_PATH


# ------------------------------------------------------------------ #
# The thresholds -- configuration, never constants in this file
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class Budget:
    """The numbers a maintainer may want to change, as declared in
    `config/actions-budget.yml`.

    None of them has a default here, and that is the point: a threshold
    with a fallback in Python is a constant with extra steps, and the
    instance/code boundary is mechanical. A malformed or
    partial file is refused by `budget_from_data`, never quietly completed.
    """

    monthly_minutes: int
    window_days: int
    warn_at_share: float
    submissions_per_day: int
    max_runs: int
    max_silent_days: int


def _whole(data: Mapping[str, Any], key: str, *, minimum: int) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(
            f"config/actions-budget.yml: {key} must be a whole number "
            f"of at least {minimum}, got {value!r}"
        )
    return value


def budget_from_data(data: Any) -> Budget:
    """Parse an already YAML-loaded `config/actions-budget.yml`.

    Raises `ValueError` on anything that is not this exact shape -- the
    same closed-shape discipline `retention_liveness.last_run_from_data`
    holds itself to. A hand-edited threshold file that says something
    nobody meant must stop the check rather than run it against a guess:
    this is the file that decides when the alarm goes off, so a value it
    cannot read is the one thing it must never silently substitute for.
    """
    if not isinstance(data, dict) or data.get("v") != USAGE_FILE_VERSION:
        raise ValueError("config/actions-budget.yml is not a supported format version")
    share = data.get("warn_at_share")
    if not isinstance(share, int | float) or isinstance(share, bool):
        raise ValueError(
            f"config/actions-budget.yml: warn_at_share must be a number "
            f"in ]0, 1], got {share!r}"
        )
    if not 0 < float(share) <= 1:
        raise ValueError(
            f"config/actions-budget.yml: warn_at_share must be in ]0, 1], got {share!r}"
        )
    return Budget(
        monthly_minutes=_whole(data, "monthly_minutes", minimum=1),
        window_days=_whole(data, "window_days", minimum=1),
        warn_at_share=float(share),
        submissions_per_day=_whole(data, "submissions_per_day", minimum=1),
        max_runs=_whole(data, "max_runs", minimum=1),
        max_silent_days=_whole(data, "max_silent_days", minimum=0),
    )


def window_start(observed_on: date, budget: Budget) -> date:
    """The first day the collector should ask the API for.

    `window_days` days back from `observed_on`, inclusive of today: a
    seven-day window covers today and the six days before it. Kept here
    rather than in the workflow so the window the collector fetches and the
    window the arithmetic divides by can never be two different numbers.
    """
    return observed_on - timedelta(days=budget.window_days - 1)


# ------------------------------------------------------------------ #
# One run, as the two API payloads describe it
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class Run:
    """One workflow run, reduced to what the arithmetic needs.

    `billed_minutes` is `None` when the timing endpoint could not be read
    for this run. That is deliberately not zero: a question that could not
    be answered is not the answer "nothing" -- this repository has already
    paid for reading one as the other once (`retention.yml`'s own
    comment on `gh secret list`), and reading an unreadable run as free is
    exactly the direction that understates a bill.

    No actor, no commit author, no branch: nothing here identifies a
    person, and nothing downstream can, because those fields are never
    read out of the payload in the first place.
    """

    run_id: int
    workflow: str
    event: str
    day: str
    billed_minutes: int | None
    jobs: int
    runner_oses: tuple[str, ...]


def billed_minutes(duration_ms: Any) -> int:
    """One job's duration in milliseconds, as GitHub bills it: whole
    minutes, rounded **up**.

    A job that never got a runner (an `if:` GitHub skipped) reports no
    duration and bills nothing, so zero maps to zero -- but any positive
    duration, however short, is a whole minute. Anything that is not a
    usable number is treated as zero here and reported by the caller as
    unreadable; this function does not judge its input, it only converts.
    """
    if not isinstance(duration_ms, int | float) or isinstance(duration_ms, bool):
        return 0
    if duration_ms <= 0:
        return 0
    return ceil(duration_ms / BILLED_MINUTE_MS)


def _day_of(created_at: Any) -> str | None:
    if not isinstance(created_at, str):
        return None
    match = _CREATED_AT_RE.match(created_at)
    return match.group(1) if match else None


def run_from_payload(payload: Any) -> Run | None:
    """One `{"run": ..., "timing": ...}` object as the collector writes it.

    `None` when the run half is unusable -- no id, or no readable
    `created_at` -- which the caller counts as a run it could not account
    for. A readable run whose `timing` half is absent or malformed comes
    back as a `Run` with `billed_minutes=None`: it still counts towards the
    submission rate, because *that a submission happened* is legible from
    the run alone.

    The day is the UTC day the API reports, not a Paris day. The two differ
    by at most two hours at the boundary, which cannot move a rate; the
    observation date on the record itself is Paris (`governance.paris_
    today`), and the two are labelled rather than silently mixed.
    """
    if not isinstance(payload, Mapping):
        return None
    run = payload.get("run")
    if not isinstance(run, Mapping):
        return None
    run_id = run.get("id")
    if not isinstance(run_id, int) or isinstance(run_id, bool):
        return None
    day = _day_of(run.get("created_at"))
    if day is None:
        return None
    name = run.get("name")
    event = run.get("event")

    timing = payload.get("timing")
    if not isinstance(timing, Mapping):
        return Run(
            run_id=run_id,
            workflow=name if isinstance(name, str) and name else "(unnamed)",
            event=event if isinstance(event, str) and event else "(unknown)",
            day=day,
            billed_minutes=None,
            jobs=0,
            runner_oses=(),
        )
    billable = timing.get("billable")
    if not isinstance(billable, Mapping):
        # An empty `billable` is what GitHub returns for a run that billed
        # nothing at all -- every job skipped by an `if:`. That is a real,
        # ordinary answer (`sweep-and-notify.yml`'s own two jobs exclude
        # each other exactly that way), so it is zero, not unreadable.
        billable = {}
    total = 0
    jobs = 0
    oses: list[str] = []
    for runner_os, entry in sorted(billable.items()):
        if not isinstance(entry, Mapping):
            continue
        oses.append(str(runner_os))
        job_runs = entry.get("job_runs")
        if isinstance(job_runs, Sequence) and not isinstance(job_runs, str | bytes):
            for job in job_runs:
                if isinstance(job, Mapping):
                    total += billed_minutes(job.get("duration_ms"))
                    jobs += 1
            continue
        # No per-job breakdown: fall back to the OS total, which rounds
        # once instead of once per job and therefore **understates** a
        # multi-job run. Named here so nobody reads the resulting figure
        # as exact.
        total += billed_minutes(entry.get("total_ms"))
        count = entry.get("jobs")
        jobs += count if isinstance(count, int) and not isinstance(count, bool) else 0
    return Run(
        run_id=run_id,
        workflow=name if isinstance(name, str) and name else "(unnamed)",
        event=event if isinstance(event, str) and event else "(unknown)",
        day=day,
        billed_minutes=total,
        jobs=jobs,
        runner_oses=tuple(oses),
    )


# ------------------------------------------------------------------ #
# The window
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class Usage:
    """One day's observation of a rolling window.

    Both halves are carried separately because they behave differently:
    `scheduled_minutes` is the part of the budget that does not move, and
    `submission_minutes` plus `development_minutes` are the part that does.
    An alarm that watched only the first would be watching the half that
    cannot surprise anyone.
    """

    observed_on: str
    since: str
    window_days: int
    runs: int
    unreadable: int
    truncated: bool
    billed_minutes: int
    scheduled_minutes: int
    submission_minutes: int
    development_minutes: int
    by_event: tuple[tuple[str, int], ...]
    by_workflow: tuple[tuple[str, int], ...]
    submissions_by_day: tuple[tuple[str, int], ...]
    busiest_submission_day: str
    busiest_submissions: int
    projected_monthly_minutes: int
    foreign_runner_oses: tuple[str, ...]


def _totalled(pairs: Sequence[tuple[str, int]]) -> tuple[tuple[str, int], ...]:
    """`pairs` summed by key, heaviest first, ties broken by name so the
    committed file's diff shows a real change and never a reordering."""
    totals: dict[str, int] = {}
    for key, minutes in pairs:
        totals[key] = totals.get(key, 0) + minutes
    return tuple(sorted(totals.items(), key=lambda item: (-item[1], item[0])))


def summarise(
    payloads: Sequence[Any],
    *,
    observed_on: date,
    budget: Budget,
    truncated: bool = False,
) -> Usage:
    """Reduce a window of collected runs to one day's observation.

    `truncated` says the collector stopped at `budget.max_runs` before it
    ran out of runs, so everything below is an undercount -- carried
    through rather than dropped, and raised as its own alarm by `alarms`.

    Runs outside the window are kept, not filtered: the collector already
    asked the API for the window, and silently discarding a run the API
    chose to return would hide a disagreement between the two rather than
    show it. The projection divides by `window_days` regardless, so an
    extra boundary run makes the rate marginally *higher*, which is the
    safe direction for a control.
    """
    runs = 0
    unreadable = 0
    scheduled = 0
    submissions_minutes = 0
    development = 0
    event_pairs: list[tuple[str, int]] = []
    workflow_pairs: list[tuple[str, int]] = []
    submissions_per_day: dict[str, int] = {}
    foreign: set[str] = set()

    for payload in payloads:
        runs += 1
        run = run_from_payload(payload)
        if run is None:
            unreadable += 1
            continue
        foreign.update(os_ for os_ in run.runner_oses if os_ != LINUX_RUNNER)
        if run.event == SUBMISSION_EVENT:
            submissions_per_day[run.day] = submissions_per_day.get(run.day, 0) + 1
        if run.billed_minutes is None:
            unreadable += 1
            continue
        minutes = run.billed_minutes
        event_pairs.append((run.event, minutes))
        workflow_pairs.append((run.workflow, minutes))
        if run.event == SCHEDULED_EVENT:
            scheduled += minutes
        elif run.event == SUBMISSION_EVENT:
            submissions_minutes += minutes
        else:
            development += minutes

    total = scheduled + submissions_minutes + development
    by_day = tuple(sorted(submissions_per_day.items()))
    busiest_day, busiest = "", 0
    for day, count in by_day:
        if count > busiest:
            busiest_day, busiest = day, count

    return Usage(
        observed_on=observed_on.isoformat(),
        since=window_start(observed_on, budget).isoformat(),
        window_days=budget.window_days,
        runs=runs,
        unreadable=unreadable,
        truncated=truncated,
        billed_minutes=total,
        scheduled_minutes=scheduled,
        submission_minutes=submissions_minutes,
        development_minutes=development,
        by_event=_totalled(event_pairs),
        by_workflow=_totalled(workflow_pairs),
        submissions_by_day=by_day,
        busiest_submission_day=busiest_day,
        busiest_submissions=busiest,
        projected_monthly_minutes=round(total / budget.window_days * DAYS_PER_MONTH),
        foreign_runner_oses=tuple(sorted(foreign)),
    )


# ------------------------------------------------------------------ #
# The alarm
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class Alarm:
    """One reason to be loud, and the sentence that says it.

    `kind` is one of the module's `*_ALARM` constants, so a test can pin
    which alarm fired without matching prose and the workflow can name it
    in an annotation.
    """

    kind: str
    text: str


def warn_at(budget: Budget) -> int:
    """The projected monthly figure at or above which the rate alarm
    fires. Its own function so the boundary itself -- exactly at the
    threshold fires, one below does not -- is something a test can pin
    without also building a window of runs to reach it."""
    return ceil(budget.monthly_minutes * budget.warn_at_share)


def alarms(usage: Usage, budget: Budget) -> tuple[Alarm, ...]:
    """Every reason this observation should make a noise. Empty is quiet.

    Five kinds, and three of them exist so that this control can be
    *wrong* and be noticed (D-25): a rate that has crossed the line, a
    submission burst, runs whose cost could not be read, a collection that
    stopped early, and a runner OS whose minutes are billed at a multiple
    this arithmetic does not apply. A control that can only ever report
    "fine" is not a control.
    """
    fired: list[Alarm] = []
    threshold = warn_at(budget)
    if usage.projected_monthly_minutes >= threshold:
        fired.append(
            Alarm(
                RATE_ALARM,
                f"At the last {usage.window_days} days' rate "
                f"({usage.billed_minutes} billed minutes since {usage.since}), "
                f"this repository alone would use about "
                f"{usage.projected_monthly_minutes} minutes a month, at or "
                f"over the {threshold}-minute warning line "
                f"({budget.warn_at_share:g} of the {budget.monthly_minutes} "
                f"free monthly minutes). Scheduled {usage.scheduled_minutes}, "
                f"public submissions {usage.submission_minutes}, pushes and "
                f"pull requests {usage.development_minutes}.",
            )
        )
    if usage.busiest_submissions >= budget.submissions_per_day:
        fired.append(
            Alarm(
                SUBMISSIONS_ALARM,
                f"{usage.busiest_submissions} public submissions arrived on "
                f"{usage.busiest_submission_day}, at or over the "
                f"{budget.submissions_per_day} a day this repository is sized "
                "for. Submissions are the only item here whose volume is "
                "decided by strangers and the only one that grows when the "
                "series succeeds: one run each, today. This is the number "
                "that says the public-submission queue has stopped "
                "being a precaution and become the thing standing between an "
                "announcement and an exhausted budget.",
            )
        )
    if usage.unreadable:
        fired.append(
            Alarm(
                UNREADABLE_ALARM,
                f"{usage.unreadable} of {usage.runs} runs could not be "
                "costed: the timing endpoint answered with nothing usable. "
                "Every figure above is therefore an undercount by an unknown "
                "amount. A question that could not be answered is not the "
                "answer 'nothing'.",
            )
        )
    if usage.truncated:
        fired.append(
            Alarm(
                TRUNCATED_ALARM,
                f"The collection stopped at {budget.max_runs} runs before it "
                "ran out of runs to read, so the window holds more than this. "
                "Reaching that cap is itself a signal: it takes a burst.",
            )
        )
    if usage.foreign_runner_oses:
        fired.append(
            Alarm(
                RUNNER_ALARM,
                "Runs billed on "
                f"{', '.join(usage.foreign_runner_oses)} as well as Linux. "
                "GitHub bills macOS at ten times a Linux minute and Windows "
                "at two; the totals above add every runner's minutes at one "
                "each, so they understate the bill.",
            )
        )
    return tuple(fired)


def message(usage: Usage, fired: Sequence[Alarm]) -> str | None:
    """The alert body, or `None` when nothing fired.

    Text only -- no address. `notify.dispatch` is what pairs this with a
    thread and a team mention, so an unconfigured repository composes
    nothing postable at all rather than a message addressed to nobody (see
    `notify.py`'s own module docstring for why that is structural here).
    """
    if not fired:
        return None
    lines = [
        "Workshop series - the Actions budget is going faster than it can hold",
        "",
    ]
    for alarm in fired:
        lines += [f"  - [{alarm.kind}] {alarm.text}", ""]
    lines += [
        f"Window: {usage.since} to {usage.observed_on}, {usage.runs} runs, "
        f"{usage.billed_minutes} billed minutes.",
        "",
        LOWER_BOUND_NOTE,
        "",
        "The full breakdown is committed to data/actions-usage.yml in this "
        "repository -- no run log to open.",
    ]
    return "\n".join(lines)


def summary_line(usage: Usage) -> str:
    """The one line the daily job prints. One line, deliberately: the
    audit found `sweep`'s inactivity report already printing thirty times
    a month into a log nobody opens, and a second such report would be a
    second thing nobody reads. What a person is meant to read is the
    committed file; what a person is meant to be *told* is the alarm."""
    return (
        f"{usage.billed_minutes} billed minutes over {usage.window_days} days "
        f"({usage.runs} runs, {usage.unreadable} uncosted) -- about "
        f"{usage.projected_monthly_minutes} a month, this repository only"
    )


# ------------------------------------------------------------------ #
# The committed record
# ------------------------------------------------------------------ #


def _observation(usage: Usage) -> dict[str, Any]:
    """One row of the trend: the numbers a reader compares day to day.

    The day's key is `day`, not the shorter `on` an earlier draft used:
    PyYAML implements YAML 1.1, whose bool resolver reads a bare `on` as
    `True` -- the same trap `tools/tests/conftest.py` documents for a
    workflow's own `on:` block. The writer here quotes it, so the file
    round-trips either way; a volunteer hand-editing the file would not.
    """
    return {
        "day": usage.observed_on,
        "runs": usage.runs,
        "minutes": usage.billed_minutes,
        "projected_monthly": usage.projected_monthly_minutes,
        "busiest_submissions": usage.busiest_submissions,
    }


def history_from_data(data: Any) -> list[dict[str, Any]]:
    """The trend rows already in `data/actions-usage.yml`, or none.

    Tolerant on purpose, unlike `budget_from_data`: a record that cannot be
    read costs the trend, never the alarm -- today's window is measured
    from today's API answer and does not depend on any of this. Losing two
    months of history to a hand edit is a shame; refusing to check the
    budget because of one would be the control failing over its own
    scrapbook.
    """
    if not isinstance(data, Mapping):
        return []
    rows = data.get("history")
    if not isinstance(rows, Sequence) or isinstance(rows, str | bytes):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def observed_on_from_data(data: Any) -> date:
    """The day `data/actions-usage.yml` was last written.

    Raises `ValueError` on anything that is not this exact format -- the
    liveness check built on this must not read a malformed record as a
    healthy one, which is the single mistake that would turn this whole
    fix into a checkmark over a silence.
    """
    if not isinstance(data, Mapping) or data.get("v") != USAGE_FILE_VERSION:
        raise ValueError("data/actions-usage.yml is not a supported format version")
    latest = data.get("latest")
    raw = latest.get("observed_on") if isinstance(latest, Mapping) else None
    if not isinstance(raw, str):
        raise ValueError("data/actions-usage.yml holds no usable observed_on date")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            "data/actions-usage.yml holds an invalid observed_on date"
        ) from exc


def days_since(observed_on: date, today: date) -> int:
    """`today - observed_on`, in whole days. Can be negative -- a hand
    edit, or clock skew between the runner that wrote it and the one
    reading it -- and `is_stale` treats that as healthy rather than as
    extra-fresh evidence of anything."""
    return (today - observed_on).days


def is_stale(elapsed_days: int, max_silent_days: int) -> bool:
    """Whether the measurement has gone quiet. A pure comparison, its own
    function so the boundary -- `elapsed == max_silent_days` is still
    healthy, one more is not -- is pinnable directly. The same shape
    `retention_liveness.is_stale` has, and deliberately so: the two answer
    the same question about two different daily jobs."""
    return elapsed_days > max_silent_days


def record_to_data(
    usage: Usage, previous: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """The plain, YAML-safe structure `cli.py` hands to its own writer.

    `latest` is today's window in full; `history` is the trend, newest
    last, with today's row replacing an earlier one for the same day so
    that a re-run -- a `workflow_dispatch` on a morning the schedule
    already fired -- corrects the day rather than duplicating it. Bounded
    at `HISTORY_LENGTH` so the file stays a page a person reads.
    """
    rows = [dict(row) for row in previous if row.get("day") != usage.observed_on]
    rows.append(_observation(usage))
    return {
        "v": USAGE_FILE_VERSION,
        "latest": {
            "observed_on": usage.observed_on,
            "since": usage.since,
            "window_days": usage.window_days,
            "runs": usage.runs,
            "uncosted_runs": usage.unreadable,
            "truncated": usage.truncated,
            "billed_minutes": usage.billed_minutes,
            "scheduled_minutes": usage.scheduled_minutes,
            "submission_minutes": usage.submission_minutes,
            "development_minutes": usage.development_minutes,
            "projected_monthly_minutes": usage.projected_monthly_minutes,
            "busiest_submission_day": usage.busiest_submission_day,
            "busiest_submissions": usage.busiest_submissions,
            "by_event": [{"event": name, "minutes": m} for name, m in usage.by_event],
            "by_workflow": [
                {"workflow": name, "minutes": m} for name, m in usage.by_workflow
            ],
            "submissions_by_day": [
                {"day": day, "submissions": n} for day, n in usage.submissions_by_day
            ],
        },
        "history": rows[-HISTORY_LENGTH:],
    }
