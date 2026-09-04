"""What reaches a volunteer who is not looking at the app (G-09, D-07).

Everything else this repository does writes to a file a volunteer can read,
review and revert. A message that has been sent cannot be unsent, so this
module is built the other way round from the rest: **sending nothing is the
resting state**, and it is that way structurally rather than by default value.

How "no channel, no message" is made unreachable rather than guarded
----------------------------------------------------------------------
There is no `notifications_enabled` flag here, and no `if not enabled: return`.
Instead the *address* is the thing that can be absent:

* `Channel` holds the two things a message needs in order to reach anyone --
  the thread it is posted on and the team it mentions. It is only ever built
  by `resolve_channel`, which returns `None` unless both are declared in the
  environment (deferred configuration, D-13: connecting an account is adding a
  secret, never a code change).
* `Dispatch` -- the only value in this package that is postable text -- carries
  a `Channel`, and its body is *rendered from* that channel's mention. So a
  postable body is not constructible without an address. There is no
  "unaddressed message" for a caller to send anyway, because that value has no
  representation.
* `dispatch()` returns `Dispatch | None`, and `None` is the ordinary answer on
  a normally-configured-but-quiet day as well as on an unconfigured one. The
  two look identical downstream, which is what keeps the absent case from
  being an error path that someone later "fixes".

And this package cannot send in any case: it holds **no transport at all**.
No `smtplib`, no `urllib`, no `http`, no `socket`, no `subprocess` -- see
`tests/governance/test_notify.py::test_the_notification_module_holds_no_transport`,
which reads this file's own source. Composing text and delivering it are separated
by a process boundary: `.github/workflows/sweep-and-notify.yml` is what posts,
using the
platform's own issue thread, and the platform is what turns that into email
(D-07: no external service, no subscription, ever).

What may leave the repository
-----------------------------
`instance/data/speakers.yml` holds real names, institutional email addresses,
affiliations and countries of external researchers. **None of them appears in
anything this module renders.** A message names a record by its `id`
(`spk-014`), quotes stored ISO days, and uses the fixed step labels below --
and nothing else. That is not a filter applied to the output; there is no code
path here that reads `name`, `email`, `affiliation`, `country`, `title`,
`proposed_by`, `assigned_to`, `host_1`, `host_2` or a board `login`, so those
values have no way in. `tests/governance/test_notify.py` pins it by running every entry
point over records whose every such field is filled with a distinctive string
and asserting none of them reaches the text.

The wording is about the record, never the person
-------------------------------------------------
Same rule as `sweep.py`'s inactivity lines (which describe the ballot record)
and `commit_format.py`'s decision grammar (which has no free prose slot for a
verdict about a member). The subject of every sentence here is a piece of work
or a record. `commit_format.judgemental_terms` is run over the whole rendered
digest by a test, so the vocabulary of blame is checked with the same list the
commit grammar answers to rather than a second one written here.

Nothing here decides anything: no writer, no `mutate`, no terminal outcome
about anybody. `sweep.py` remains the only automated hand on the pipeline, and
parking a lead there is not a rejection either.

The overdue sentences are `app/src/state/sla.ts`'s, not a second set
--------------------------------------------------------------------
The overdue list belongs in the daily digest, and the screens already
have that wording. Two implementations of one sentence is the
cross-language divergence this repository has been bitten by four times, so
the Python half below is an explicit twin of `app/src/state/sla.ts` and the two
are pinned together by `tools/tests/fixtures/governance-cases.json`'s
`lateness_cases`, read by `tools/tests/governance/test_governance_fixture.py` and by
`app/tests/state/governance-fixture.test.ts`. A change to either wording that is not
mirrored fails in both languages.

Like the rest of `convener_ops`, this module is tolerant of malformed input and
never raises: it runs unattended in a scheduled job, where an exception is a
silent no-op overnight rather than a red screen someone can react to. The safe
degradation is always *fewer* lines, never a guessed one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final

from convener_ops.governance.rule import paris_today, vote_window_days

# ------------------------------------------------------------------ #
# Lateness -- the twin of `app/src/state/sla.ts`
#
# Calendar days, not working days: `config.sla_days` says its unit in neither
# direction, and these windows have always been written as plain days beside
# others that do spell out working days. `governance.add_working_days` is
# deliberately not used here, and that absence is the decision, not an
# omission. Converting between the two units would move a real deadline by
# real days.
# ------------------------------------------------------------------ #

#: The four steps the series sets a turnaround time for.
#:
#: Three of them are read off `config.sla_days`. The fourth, `lead_decision`,
#: is read off `config.vote_window_days`: the day the board's decision
#: becomes late is the day `sweep.expire_votes` parks the lead, and those were
#: two separate numbers in `config.yml` until this stopped being possible.
#: `sla_days.lead_decision` no longer exists, so the digest cannot call a lead
#: on time on the morning the job parks it.
SLA_STEPS: Final[tuple[str, ...]] = (
    "lead_decision",
    "invitation_follow_up",
    "summary_after_delivery",
    "recording_after_delivery",
)

#: How each step is named in a message. All four are noun phrases for a piece
#: of work: none is a role, and none can be read as an actor -- "Board
#: decision" is the decision, not the board. Identical to `STEP_LABELS` in
#: `app/src/state/sla.ts`.
STEP_LABELS: Final[dict[str, str]] = {
    "lead_decision": "Board decision",
    "invitation_follow_up": "Invitation follow-up",
    "summary_after_delivery": "Forum summary",
    "recording_after_delivery": "Recording",
}

#: The runbook item that records the forum summary as posted.
SUMMARY_ITEM: Final = "delivered/forum-summary"


@dataclass(frozen=True)
class Deadline:
    """A step's due day and the recorded day its clock started."""

    step: str
    due: str
    since: str


@dataclass(frozen=True)
class Overdue(Deadline):
    """A deadline that has passed. `days` is always at least 1.

    The count exists on this type only -- there is no `Deadline.days` for a
    step that is on time, so `0 days overdue` is not constructible from
    anything this module returns. Same shape as `Lateness`'s `overdue` arm in
    `app/src/state/sla.ts`.
    """

    days: int


#: An ISO calendar day, the only date form stored in the two data files.
#: `date.fromisoformat` alone is too generous -- it also accepts `20260818`
#: and week dates, neither of which this repository ever writes -- so the
#: shape is checked before it is parsed, as `rule.py` does.
_DATE_RE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _iso(value: Any) -> date | None:
    """`value` as a calendar day, or `None` when it is not an ISO day."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _target(config: Any, step: str) -> int | None:
    """How many days `step` is allowed, or `None` when the config does not say.

    `lead_decision` is not looked up in `sla_days`: it is
    `governance.vote_window_days`, the one definition `sweep.expire_votes`
    parks on, fallback and all. So an unusable config gives this step the
    spec's fourteen days rather than no deadline -- which is not a guess but
    the number the sweep will really apply that morning, and the digest naming
    a different day than the job acts on is the failure this exists to
    prevent.
    """
    if step == "lead_decision":
        return vote_window_days(config)
    sla = config.get("sla_days") if isinstance(config, Mapping) else None
    if not isinstance(sla, Mapping):
        return None
    raw = sla.get(step)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return raw


def _maybe(step: str, since: Any, config: Any) -> Deadline | None:
    """The deadline for `step`, or `None` when it cannot be computed.

    A deadline that cannot be computed is *absent*, never guessed. Seven of the
    31 records in `instance/data/speakers.yml` carry no `selection.opened_on` at all;
    inventing an anchor for them would manufacture a number a volunteer would
    then read as if the record held it.
    """
    days = _target(config, step)
    start = _iso(since)
    if days is None or start is None:
        return None
    return Deadline(
        step=STEP_LABELS[step],
        due=(start + timedelta(days=days)).isoformat(),
        since=str(since),
    )


def _publication_refused(speaker: Mapping[str, Any]) -> bool:
    """Whether somebody who could refuse publication has refused it.

    The twin of `app/src/state/governance.ts::publicationRefused`, and pinned
    to it by `lateness_cases` in
    `tools/tests/fixtures/governance-cases.json` -- it is read by `due_date`
    below, which is itself the twin of `sla.ts::dueDate`, so a change on one
    side that missed the other would put a deadline in the daily digest that
    the screens no longer show, or the reverse.

    Two refusals and only two: the speaker's own `refused`, and the board's
    resolution to `withhold`. A `pending` consent and an objection window
    still running are *waits* -- somebody can still say yes -- so they are
    not refusals, and the clock they carry is exactly the nudge to go and
    ask.

    Deliberately not `public_data.recording_withheld`, which answers a
    different question ("must this stay offline?") and answers it in the
    affirmative: an unanswered consent is withheld there and is not a
    refusal here.
    """
    publication = speaker.get("publication")
    publication = publication if isinstance(publication, Mapping) else {}
    return (
        publication.get("consent") == "refused"
        or publication.get("outcome") == "withheld"
    )


def due_date(speaker: Any, config: Any) -> Deadline | None:
    """The step this record is currently waiting on, and the day it was due.

    Anchors, mirroring `sla.ts::dueDate` exactly:

    * **Board decision** from `selection.opened_on`, the day the board was
      actually asked.
    * **Invitation follow-up** from `selection.decided_on`. No invitation-sent
      day exists in the schema; this proxy is on or before the real sending
      day, so a nudge can only ever come early -- the prudent direction.
    * **Forum summary** and **Recording** from `date`, and only while the
      artefact is still missing. Once either is in, its deadline stops
      existing rather than becoming a satisfied one. The recording's also
      stops when somebody has refused publication: `youtube_url` then stays
      empty by definition, and a deadline nothing can ever close is worse
      than no deadline.

    A delivered record can be waiting on both wrap-up steps; the earlier due
    day wins, so a record has exactly one deadline at a time.
    """
    if not isinstance(speaker, Mapping):
        return None
    selection = speaker.get("selection")
    selection = selection if isinstance(selection, Mapping) else {}
    status = speaker.get("status")

    if status == "lead":
        return _maybe("lead_decision", selection.get("opened_on"), config)

    if status == "invited":
        return _maybe("invitation_follow_up", selection.get("decided_on"), config)

    if status == "delivered":
        open_steps: list[Deadline] = []
        runbook = speaker.get("runbook_progress")
        runbook = runbook if isinstance(runbook, Mapping) else {}
        if not runbook.get(SUMMARY_ITEM):
            summary = _maybe("summary_after_delivery", speaker.get("date"), config)
            if summary is not None:
                open_steps.append(summary)
        if not speaker.get("youtube_url") and not _publication_refused(speaker):
            recording = _maybe("recording_after_delivery", speaker.get("date"), config)
            if recording is not None:
                open_steps.append(recording)
        if not open_steps:
            return None
        return min(open_steps, key=lambda d: d.due)

    return None


def overdue(speaker: Any, config: Any, today: str) -> Overdue | None:
    """How far past its deadline this record's current step is, or `None`.

    `None` both when no deadline applies and when the deadline has not passed
    -- including on the due day itself, which is still within the target. The
    day count therefore only ever exists on a step that really is late.
    """
    deadline = due_date(speaker, config)
    day = _iso(today)
    if deadline is None or day is None:
        return None
    due = _iso(deadline.due)
    # Deliberately uncovered: `_maybe` is the only place a Deadline is ever
    # built, and it always stamps `due` from `(start + timedelta(...)).
    # isoformat()` -- always a valid ISO day, never a value `_iso` refuses.
    # No public input can make `due_date` return a Deadline this branch
    # would catch. Kept, not deleted, so the type (`Deadline.due: str`)
    # does not have to be trusted blindly if a second constructor is ever
    # added.
    if due is None:
        return None
    days = (day - due).days
    if days <= 0:
        return None
    return Overdue(
        step=deadline.step, due=deadline.due, since=deadline.since, days=days
    )


def overdue_text(late: Overdue) -> str:
    """The sentence a volunteer reads for a step that is late.

    "Board decision is 3 days overdue" -- about the step, not a code and not a
    judgement. There is no grammatical position in it for a person, so no
    caller can put one there. Byte-identical to `sla.ts::overdueText`; the
    shared fixture is what keeps it so.
    """
    count = "1 day" if late.days == 1 else f"{late.days} days"
    return f"{late.step} is {count} overdue"


def waiting_since(late: Overdue) -> str:
    """The second half of the display: the day this step has been waiting
    since, as the stored ISO day. Twin of `sla.ts::waitingSince`."""
    return f"waiting since {late.since}"


# ------------------------------------------------------------------ #
# Immediate events
# ------------------------------------------------------------------ #

#: A lead arrived through the public form.
NEW_LEAD: Final = "new-lead"

#: A vote reached its threshold, so the lead is approved.
THRESHOLD_REACHED: Final = "threshold-reached"

#: An objection was lodged against publishing a recording.
OBJECTION_FILED: Final = "objection-filed"

#: The complete set. The immediate channel is reserved for what
#: calls for a quick reaction, and everything else waits for the digest --
#: because too much noise means the notifications get ignored, which is worse
#: than not having them. Adding a fourth kind is a spec change, not a tweak.
EVENT_KINDS: Final[tuple[str, ...]] = (NEW_LEAD, THRESHOLD_REACHED, OBJECTION_FILED)


@dataclass(frozen=True)
class Event:
    """One thing worth interrupting someone for.

    `record` is a speaker `id` and `text` is the sentence about it. Neither
    field can hold a person: `record` is copied from `id`, and `text` is built
    from `record` plus a fixed phrase chosen by `kind`.
    """

    kind: str
    record: str
    text: str


_EVENT_PHRASE: Final[dict[str, str]] = {
    NEW_LEAD: "a new lead arrived from the public form",
    THRESHOLD_REACHED: "the vote reached its threshold and the lead is approved",
    OBJECTION_FILED: "an objection is standing on the publication",
}


def _event(kind: str, record: str) -> Event:
    return Event(kind=kind, record=record, text=f"{record}: {_EVENT_PHRASE[kind]}")


def _selection_day(entry: Mapping[str, Any], key: str) -> str:
    selection = entry.get("selection")
    if not isinstance(selection, Mapping):
        return ""
    value = selection.get(key)
    return value if isinstance(value, str) else ""


def _record_id(entry: Any) -> str:
    if not isinstance(entry, Mapping):
        return ""
    value = entry.get("id")
    return value if isinstance(value, str) else ""


def _standing_objections(entry: Any) -> list[tuple[str, str, str]]:
    """Publication objections that are still open, as comparable tuples.

    An objection with no `resolved_on` stands, which is a stored fact rather
    than something inferred from dates -- so a hand-written objection that
    omits the key reads as standing, the safe direction.

    The tuple carries `date` and a marker for the reason's *presence*, never
    the reason's text: an objection's reason is free prose a member wrote and
    has no business being emailed out of the repository. Two objections that
    differ only in wording therefore compare equal, which at worst means one
    notification instead of two -- again the quiet direction.
    """
    # Deliberately uncovered: `_standing_objections` is called only from
    # `immediate_events`, twice, and both callers already guarantee a
    # Mapping -- `entry` there passed the loop's own isinstance check, and
    # `old` is `prior.get(rid)`, where `prior` only ever stores values for
    # which `_record_id` returned a truthy id, which itself requires a
    # Mapping. No call in this module can reach the branch below with
    # anything else. Kept as a guard against a future caller that does not
    # hold that invariant, since `entry: Any` invites exactly one.
    if not isinstance(entry, Mapping):
        return []
    publication = entry.get("publication")
    if not isinstance(publication, Mapping):
        return []
    objections = publication.get("objections")
    if not isinstance(objections, Sequence) or isinstance(objections, str | bytes):
        return []
    standing: list[tuple[str, str, str]] = []
    for raw in objections:
        if not isinstance(raw, Mapping) or raw.get("resolved_on"):
            continue
        member = raw.get("member")
        day = raw.get("date")
        standing.append(
            (
                member if isinstance(member, str) else "",
                day if isinstance(day, str) else "",
                "reasoned" if raw.get("reason") else "bare",
            )
        )
    return standing


def immediate_events(before: Any, after: Any) -> list[Event]:
    """The three things worth interrupting people for, and nothing else.

    * a new lead received through the public form;
    * a vote reaching its threshold, which approves the lead;
    * an objection lodged against a publication.

    Every other difference between the two files -- a ballot that does not
    reach the threshold, a runbook tick, a field edited, a status moving
    anywhere but `lead -> approved` -- produces no event. That closed list is
    the point: the immediate channel is worth having only while it stays rare.

    `before` and `after` are the speaker lists either side of a change. A
    record that vanishes produces nothing: a disappearance is not one of the
    three, and it is emphatically not something an automated path should
    announce about anybody.
    """
    prior: dict[str, Any] = {}
    if isinstance(before, Sequence) and not isinstance(before, str | bytes):
        for entry in before:
            rid = _record_id(entry)
            # Deliberately uncovered: `if rid:` False (a malformed `before`
            # entry with no usable id) skips this assignment, but nothing
            # would go wrong if it ran anyway -- `prior[""] = entry` is
            # valid Python, and the only reader, `prior.get(rid)` below, is
            # always called with a *non-empty* rid (the `after` loop's own
            # filter, a few lines down, guarantees that). So this branch's
            # two arms are behaviourally identical: no test could tell them
            # apart without asserting on `prior`'s internal shape, which
            # would be a test of implementation, not of behaviour.
            if rid:
                prior[rid] = entry
    if not isinstance(after, Sequence) or isinstance(after, str | bytes):
        return []

    events: list[Event] = []
    for entry in after:
        rid = _record_id(entry)
        if not rid or not isinstance(entry, Mapping):
            continue
        old = prior.get(rid)

        if old is None:
            if entry.get("status") == "lead" and entry.get("source") == "form":
                events.append(_event(NEW_LEAD, rid))
            # A record that appears in any other shape was not received from
            # the form; it is a hand-added row or a rename, and neither is one
            # of the three.
            continue

        if (
            old.get("status") == "lead"
            and entry.get("status") == "approved"
            and _selection_day(entry, "decided_on")
            and not _selection_day(old, "decided_on")
        ):
            # The recorded decision, not merely the new status. `ballot-cast`
            # is the only writer of `approved` that also stamps `decided_on`
            # (`app/src/state/transitions.ts`); an administrative override
            # moves the status and leaves the selection untouched, and the
            # sentence below -- "the vote reached its threshold" -- would then
            # be a false statement about a governance decision, sent to the
            # board, on the channel reserved for what calls for a quick
            # reaction. An override is a deliberate act by a named person and
            # the register records it; it is not news of a vote.
            events.append(_event(THRESHOLD_REACHED, rid))

        was = _standing_objections(old)
        now = _standing_objections(entry)
        for objection in now:
            if objection in was:
                was.remove(objection)
            else:
                events.append(_event(OBJECTION_FILED, rid))
    return events


# ------------------------------------------------------------------ #
# The daily digest
# ------------------------------------------------------------------ #

# The digest is composed only of facts the record itself dates -- there is no
# diff here, and no clock beyond the day being rendered for, so running it
# twice for the same day gives the same text.


def _publication_day(entry: Mapping[str, Any], key: str) -> str:
    publication = entry.get("publication")
    if not isinstance(publication, Mapping):
        return ""
    value = publication.get(key)
    return value if isinstance(value, str) else ""


def _parked_on(entry: Mapping[str, Any], config: Any) -> str:
    """The day this record's vote window ran out, if that is why it is parked.

    The one automatic transition that leaves no date of its own.
    `sweep.expire_votes` writes `status: parked` and nothing else, and this
    module takes no previous file to diff against -- so the day is *derived*
    from the two things the record does hold, `selection.opened_on` and the
    configured window, using `governance.vote_window_days`, the same single
    definition the sweep parks on. The sweep bites on the first day after the
    window closes (the closing day is still a day the board may vote), so
    that is the day named here.

    `''` for anything else: a lead the board parked by hand carries no
    `opened_on`-derived day that means anything, so this returns a day only
    for a record that is parked, has an opened window, and reached no
    decision. What it costs is that a sweep which does not run on its
    scheduled morning parks a day late while this still names the day the
    window closed; `daily_digest`'s docstring says so rather than leaving the
    reader to find out.
    """
    if entry.get("status") != "parked":
        return ""
    if _selection_day(entry, "decided_on"):
        return ""
    opened = _iso(_selection_day(entry, "opened_on"))
    if opened is None:
        return ""
    return (opened + timedelta(days=vote_window_days(config) + 1)).isoformat()


def _happened_today(speakers: Sequence[Any], config: Any, today: str) -> list[str]:
    """Everything the repository records as having happened on `today`.

    Derived from stored days rather than from a diff, deliberately: the digest
    takes no "yesterday's file" argument, so it cannot report something that
    left no date behind, and it cannot invent one either. What that costs is
    stated in `daily_digest`'s docstring.
    """
    lines: list[str] = []
    for entry in speakers:
        rid = _record_id(entry)
        if not rid or not isinstance(entry, Mapping):
            continue
        if _selection_day(entry, "opened_on") == today:
            lines.append(f"{rid}: the vote window opened")
        if _selection_day(entry, "decided_on") == today:
            lines.append(f"{rid}: the board decision was recorded")
        if _parked_on(entry, config) == today:
            lines.append(f"{rid}: the vote window closed and the lead was parked")
        if entry.get("status") == "delivered" and entry.get("date") == today:
            lines.append(f"{rid}: the talk is recorded as delivered")
        if _publication_day(entry, "approved_on") == today:
            lines.append(f"{rid}: the publication was approved")
        publication = entry.get("publication")
        objections = (
            publication.get("objections") if isinstance(publication, Mapping) else None
        )
        if isinstance(objections, Sequence) and not isinstance(objections, str | bytes):
            for raw in objections:
                if not isinstance(raw, Mapping):
                    continue
                if raw.get("resolved_on") == today:
                    lines.append(f"{rid}: an objection on the publication was closed")
                elif raw.get("date") == today and not raw.get("resolved_on"):
                    lines.append(f"{rid}: an objection was lodged on the publication")

    nominations = config.get("nominations") if isinstance(config, Mapping) else None
    if isinstance(nominations, Sequence) and not isinstance(nominations, str | bytes):
        for index, raw in enumerate(nominations, start=1):
            if not isinstance(raw, Mapping):
                continue
            # A nomination has no id of its own, and its `candidate` is a
            # person, so the record is named by its position in the list --
            # enough for a reader to find it on the Board screen, and the only
            # form of it that names nobody.
            label = f"nomination {index}"
            if raw.get("opened_on") == today:
                lines.append(f"{label}: a nomination window opened")
            objections = raw.get("objections")
            if isinstance(objections, Sequence) and not isinstance(
                objections, str | bytes
            ):
                for objection in objections:
                    if (
                        isinstance(objection, Mapping)
                        and objection.get("date") == today
                    ):
                        lines.append(f"{label}: an objection was lodged")
    return lines


def _overdue_lines(speakers: Sequence[Any], config: Any, today: str) -> list[str]:
    """The overdue list, in `sla.ts`'s exact words.

    Both sentences appear verbatim, joined by a comma, behind the record's id.
    The wording is not restated here: `overdue_text` and `waiting_since` are
    the twin of the screens' and are pinned to them by the shared fixture.
    Longest-waiting first, which is `byUrgency`'s order for the overdue arm.
    """
    late: list[tuple[str, Overdue]] = []
    for entry in speakers:
        rid = _record_id(entry)
        if not rid:
            continue
        item = overdue(entry, config, today)
        if item is not None:
            late.append((rid, item))
    late.sort(key=lambda pair: (pair[1].due, pair[0]))
    return [f"{rid}: {overdue_text(i)}, {waiting_since(i)}" for rid, i in late]


def daily_digest(speakers: Any, config: Any, now: datetime) -> str | None:
    """One message for a day, or `None` when the day has nothing in it.

    `None` when nothing is dated today **and** nothing is overdue. That is the
    property the whole channel rests on: a digest that arrives every morning
    saying nothing gets filtered into a folder within a fortnight, and once it
    is filtered the day something *does* happen is filtered with it. Silence is
    therefore a feature, and it is the most important test in this module.

    `now` is an instant; the day is taken in Paris (`governance.paris_today`),
    never off a UTC clock, so a run between 00:00 and 02:00 Paris does not
    report yesterday.

    **The one automatic transition, and how it is dated.** There is
    exactly one -- `expire_votes`
    parking a lead whose window ran out -- and it writes `status: parked` and
    no day. `_parked_on` derives that day from `selection.opened_on` and
    `governance.vote_window_days`, the same single definition the sweep parks
    on, so the digest cannot describe a window the job did not apply. It does
    assume the sweep ran on its scheduled morning: a job that misses a day
    parks a day late while this still names the day the window closed. That is
    a wrong day, not a wrong record, and it is stated here rather than hidden.

    **What this cannot report, and why nothing is invented to cover it.**
    Locked dates and settled nominations belong here too. Neither leaves a
    day behind in the schema -- there is no `scheduled_on`, and a nomination's
    outcome is stored without the day it was reached -- and this function takes
    no previous file to diff against. Reporting them would mean either guessing
    a day or duplicating `board.ts::NOMINATION_WINDOW_DAYS` into a second
    language, and a second copy of a window length is exactly the divergence
    this repository keeps having to back out of. So they are absent, and the
    schema change that would fix it is left to be made properly rather than
    worked around here.
    """
    if not isinstance(speakers, Sequence) or isinstance(speakers, str | bytes):
        speakers = []
    today = paris_today(now).isoformat()

    happened = _happened_today(speakers, config, today)
    late = _overdue_lines(speakers, config, today)
    if not happened and not late:
        return None

    lines = [f"Workshop series digest - {today}", ""]
    if happened:
        lines.append("Recorded today")
        lines += [f"  - {line}" for line in happened]
        lines.append("")
    if late:
        lines.append("Waiting longer than planned")
        lines += [f"  - {line}" for line in late]
        lines.append("")
    lines.append("Every line names a record. This message decides nothing.")
    return "\n".join(lines)


# ------------------------------------------------------------------ #
# The channel
# ------------------------------------------------------------------ #

#: The repository thread every message is posted on. An issue number.
THREAD_ENV: Final = "CONVENER_NOTIFY_THREAD"

#: The team handle a message mentions, so the platform emails the editorial
#: team. A team, never a person: nothing here may depend on one volunteer's
#: account still existing.
MENTION_ENV: Final = "CONVENER_NOTIFY_MENTION"

#: The shape of a GitHub team handle: `@org/team`. Anchored so a substring
#: cannot pass -- both the organisation and the team segment must be made of
#: handle characters (letters, digits, hyphens, underscores or dots), the
#: `@` and the `/` are mandatory, and neither segment may be empty.
#:
#: This is deliberately narrower than "any handle" -- it rejects `@person`
#: (no `/`, so no team) just as firmly as it rejects a bare `org/team` with
#: no leading `@`. The project's binding constraint is that nothing may
#: depend on the goodwill or the continued presence of one collaborator; a
#: personal mention notifies exactly one human and reintroduces that
#: dependency, so `resolve_channel` below refuses anything that does not
#: name an organisation and a team.
_TEAM_MENTION_RE: Final = re.compile(
    r"^@[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$"
)


@dataclass(frozen=True)
class Channel:
    """Where a message goes and who it mentions.

    Both halves are needed for a message to reach anybody, and neither has a
    safe default: a thread with no mention posts silently into a page nobody
    is watching, and a mention with no thread has nowhere to be written. So
    this type is only ever built by `resolve_channel`, and a partly-configured
    environment yields no `Channel` at all rather than a half-usable one.
    """

    thread: str
    mention: str


def resolve_channel(env: Mapping[str, str]) -> Channel | None:
    """The configured channel, or `None`.

    Deferred configuration (D-13): the system ships fully working with no
    account of any kind, and connecting one is adding a secret rather than
    changing code. `declarations/integrations.yml` declares these two under
    `board_notifications`, so `convener-check-config` reports the channel's state
    alongside every other integration and an absent one reads as the normal
    state it is.

    `mention` must be a team handle (`@org/team`, see `_TEAM_MENTION_RE`), not
    merely a non-empty string. A value missing its leading `@` -- or naming a
    person rather than an organisation and a team -- would still render at
    the head of a posted, readable, plausible comment, and would notify
    nobody: the one failure mode here that leaves no trace. A malformed
    mention is therefore treated exactly like an absent one: this returns
    `None`, so no `Channel` -- and downstream, no `Dispatch` -- is ever
    constructed from it. Widening this to also accept a personal handle would
    reintroduce the dependency on one volunteer's account that the team
    requirement exists to remove; do not "fix" it back open.
    """
    thread = env.get(THREAD_ENV, "").strip()
    mention = env.get(MENTION_ENV, "").strip()
    if not thread or not mention or not _TEAM_MENTION_RE.match(mention):
        return None
    return Channel(thread=thread, mention=mention)


@dataclass(frozen=True)
class Dispatch:
    """A message with somewhere to go: the only postable value in this package.

    It carries its `Channel`, and `body` is rendered from that channel's
    mention, so there is no way to hold postable text without also holding an
    address. That is what makes "unconfigured" unable to send rather than
    merely told not to: the value a sender would need does not exist.
    """

    channel: Channel
    body: str


def dispatch(message: str | None, env: Mapping[str, str]) -> Dispatch | None:
    """Pair a message with its channel, or return `None`.

    `None` on three counts that are deliberately indistinguishable downstream:
    nothing to say, no channel configured, or both. A quiet day and an
    unconfigured repository behave identically, which is what stops the absent
    case from turning into an error path somebody later "fixes" by inventing a
    default address.
    """
    if not message:
        return None
    channel = resolve_channel(env)
    if channel is None:
        return None
    return Dispatch(channel=channel, body=f"{channel.mention}\n\n{message}\n")


def render_events(events: Sequence[Event]) -> str | None:
    """The immediate events as one message, or `None` when there are none."""
    if not events:
        return None
    lines = ["Workshop series - needs a look", ""]
    lines += [f"  - {event.text}" for event in events]
    lines.append("")
    lines.append("Every line names a record. This message decides nothing.")
    return "\n".join(lines)
