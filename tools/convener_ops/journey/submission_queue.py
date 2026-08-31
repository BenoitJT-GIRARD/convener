"""The queue a public submission waits in, and the arithmetic that drains it.

Every survey response and every
registration a stranger submitted used to become one `repository_dispatch`, and one
billed GitHub Actions run, of its own -- the one line item in this project's
budget whose volume is decided by people the project has never met, and the
one that grows when the series succeeds. The submission
now waits in this repository instead, and one drain a day handles everything
waiting in a single commit.

The survey response moved first, since it sends nothing back to anybody.
The registration followed, but only the ones it is safe to keep waiting: the
confirmation e-mail is the participant's entry ticket, not a receipt, so
`registration_routing.py` routes a registration whose event is still days
away here and leaves everything closer to it on the immediate,
`repository_dispatch` path it always took. That module owns the rule; this
one only ever sees what it already sent.

Everything in this module is a pure function. `convener_ops.cli` supplies the
queue's contents, the repository's current state and the event keys; nothing
here reads a file, an environment variable or a clock, and nothing here goes
near the network -- which is what lets the whole behaviour, replay included,
be driven from fixtures.

Where the queue lives, and why it is a branch
-----------------------------------------------
`QUEUE_BRANCH`, a branch of this repository that no workflow watches --
never a path on the default branch. That half of the question is closed
rather than open: `register.yml`, `quality.yml` and `security.yml` start on
*any* commit to the default branch with no path filter at all, and
`deploy.yml` filters with `paths-ignore`, so a queue file committed to the
default branch would start at least five runs per submission -- the exact
inverse of this module's purpose. The relay writes with its own token, not
with a job's `GITHUB_TOKEN`, so GitHub's recursion guard does not apply to
anything it pushes; the only thing that makes a branch free is that no
trigger reaches it, and that is held by `tools/tests/test_workflows.py`'s
own directory-wide sweep rather than by anybody's care.

**The precondition that sweep cannot enforce, restated here because this is
the file a reader arrives at: no pull request may ever be opened from
`QUEUE_BRANCH`.** Six workflows trigger on `pull_request`; four filter on
paths a `queue/**` file does not match, but `quality.yml` and `security.yml`
do not filter at all, so an open pull request whose head is this branch would
start two of them -- six billed jobs -- on every submission, six times what
the queue replaced.
Whether such a pull request exists is repository state, not file content, so
no offline test can see it. What *is* held offline is the consequence one
step further on: `tools/tests/journey/test_submission_queue.py` fails if a queue
file ever appears in a checkout of the default branch, so merging one is red
rather than silent.

The entry, and what it carries
--------------------------------
One file per submission, at `queue/<kind>/<entry id>.json`, holding the
relay's request body byte for byte -- the hybrid envelope
`app/src/survey/encrypt.ts` or `app/src/signup/encrypt.ts` produced, so the
queue carries ciphertext and an event id, and nothing else. That matters for
retention: D-22 destroys the *key*, not the records, so a residual entry in
this branch's history becomes unreadable at exactly the moment
`instance/data/events/<id>/survey-responses.enc` and `registrations.enc` do, by the
same one operation. A queue whose entries were plaintext would have no such
property, which is why `KINDS` is a closed set and not an open door -- and
why the proposal, whose relay receives Tally's body in the clear, is still
not in it.

The entry id is `<milliseconds, base36>-<uuid>`. The timestamp is what
gives a drain a total order over what it found -- two submissions handled in
one drain must land in the same order they would have landed in two drains
-- and the uuid is what makes an id unique even when two submissions share a
millisecond. Neither is trusted: `ENTRY_ID_RE` is a shape check, the drain
never reads a date out of an entry id, and an id is only ever compared
against other ids.

Nothing may be lost, and what that costs
------------------------------------------
The drain writes its result to the default branch first and clears the queue
second, never the other way round, so every interruption leaves each
submission either fully handled or still waiting. The cost of that ordering
is that a drain interrupted between the two would handle the same entries
twice on its next run -- for the survey, two identical responses recorded
from one submission, which `survey.add_response` cannot detect on its own
(it is append-only and holds no identity to deduplicate on, deliberately;
see its own module docstring).

`instance/data/queue-ledger.yml` closes that. It is written in the *same commit* as
the data, so "this entry has been handled" and "here is what handling it
produced" become one atomic fact, and a replayed drain reads the ledger and
does nothing. It does not grow without bound: an id is forgotten by the
first drain that observes the entry is no longer in the queue, so the ledger
holds only what could still be replayed -- see `next_ledger`.

An entry is cleared when it is *completely* done, and for a registration
that is one step later than for a survey response
--------------------------------------------------------------------------
Storing a survey response is the whole of handling it. Storing a
registration is not: the confirmation carrying the room link and the
matching code still has to go out, and it can only go out **after** the
record has actually landed on the default branch -- the identical ordering
`registration.yml` spells out for the immediate lane, and for the identical
reason (a confirmation sent for a registration a failed push then discarded
is worse than a late one).

So a stored registration goes into the ledger, which is what stops a replay
recording it twice, but it is deliberately **left in the queue**
(`DrainOutcome.confirm`, absent from `DrainOutcome.clear`). The step that
sends its confirmation is what adds it to the clear list. A drain
interrupted between the two therefore finds it next time as
`DrainPlan.confirm_only`: in the ledger *and* still in the queue, which
means stored but not confirmed, so it is confirmed and not re-stored.

**That is at-least-once, and the choice is deliberate.** No record of
"the e-mail went out" can be written before the e-mail goes out, so an
interruption in that one window makes the next drain send a second, identical
confirmation -- same deterministic matching code, same room link, because
`registration.matching_code` is a pure function of the event, the address and
the salt. A duplicate confirmation is a confusing message. A missing one is a
participant who cannot get into the room and can never be issued a
certificate. The two are not comparable, and this errs at the cheaper one.

Loud, never quiet
-------------------
Three outcomes are not "handled", and none of them is silent (D-25):

* a **refusal** -- an entry that is not a submission this queue can ever
  handle (not JSON, no usable event id, a kind nothing serves, a survey the
  organiser never opened, ciphertext that does not decrypt). It is cleared,
  because leaving it would block the queue for ever, and it is reported by
  id and reason on the run.
* a **deferral** -- an entry this drain could not handle *yet*: no key
  configured for its event, a committed responses file that will not parse,
  or more distinct events waiting than `MAX_EVENTS_PER_DRAIN`. It stays in
  the queue, untouched, for the next drain, and it is reported too. Never
  cleared: a submission the operator can still rescue must not be thrown
  away because today's run could not reach it.
* an entry the ledger already holds, which is cleared and not re-applied
  -- unless it is a registration still waiting in the queue, which means
  stored but not yet confirmed (see the section above): that one is
  confirmed, then cleared.

The cap, and why there is one
-------------------------------
A submission can only be decrypted with its own event's private key, and a
GitHub Actions job can only reach a secret through an expression written in
the workflow file itself -- never through a name a running step computed. A
drain covering N events therefore needs N such expressions written out, so N
has to be a constant. `MAX_EVENTS_PER_DRAIN` is that constant,
`tools/tests/journey/test_submission_queue.py` pins the workflow to exactly that many
slots, and an event past the cap is deferred, never dropped.

A slot is per *event*, not per kind -- one key opens both files -- so the two
kinds never double the demand for them, and a busy event needs one slot
however much it holds. What they do compete for is which events get the
slots when more than `MAX_EVENTS_PER_DRAIN` of them are waiting at once, and
`plan_drain` settles that by putting **every event with a registration
waiting ahead of every event with only survey responses**, oldest waiting
entry breaking the tie inside each group. The two do not lose the same thing
by waiting: a deferred survey response costs its submitter nothing, while a
deferred registration spends one of the two drain periods
`registration_routing.floor_hours` reserves for exactly one missed drain.
Neither is ever dropped, both are reported, and a deferral of either turns
the daily job red.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from ..declaration.paths import DATA_DIR
from . import confirmation, eventkeys, survey
from .registration import (
    dump_registration_file,
    event_id_from_payload,
    find_by_email,
    load_registration_file,
    to_registration,
    upsert,
)

#: The branch the relay writes to and the drain empties. Named once, here,
#: and read from this constant by `tools/tests/journey/test_submission_queue.py`,
#: `.github/workflows/sweep-and-notify.yml` and
#: `services/signup-relay/src/index.js` -- three copies of a branch name
#: that disagreed would be a queue nothing drains, with nothing red.
QUEUE_BRANCH: Final = "submission-queue"

#: The directory every entry lives under, inside `QUEUE_BRANCH`. One
#: directory, so a checkout of the default branch can be swept for it (see
#: the module docstring's note on the pull-request precondition).
QUEUE_DIR: Final = "queue"

#: The kinds of submission this queue carries. A closed set, not a
#: convention: the drain refuses an entry under any other directory rather
#: than guessing what to do with it, and adding a kind means adding the code
#: that handles it in the same change.
#:
#: Registration joined once the distance-to-event lane
#: rule (`registration_routing.py`) existed to keep a last-minute registrant
#: out of the queue: the confirmation e-mail carries the room link and the
#: matching code, and there is no second channel for either, so only a
#: registration whose event is still days away may ever wait for a drain.
#: The proposal is absent for a different reason, recorded in
#: `docs/operating/operations.md`: `services/form-relay` receives Tally's
#: webhook body in the clear, so queuing it would put a stranger's name and
#: address into this repository's history in plain text, outside the key
#: destruction D-22 relies on.
SURVEY_KIND: Final = "survey"
REGISTRATION_KIND: Final = "registration"
KINDS: Final = frozenset({SURVEY_KIND, REGISTRATION_KIND})

#: The shape of an entry id -- see the module docstring. Deliberately a
#: shape check and nothing more: no date is ever parsed out of it, and an
#: id is only ever compared against another id.
ENTRY_ID_RE: Final = re.compile(
    r"^[0-9a-z]{1,16}-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$"
)

#: Where the ledger lives, relative to a repository root -- the same "one
#: function names the path" discipline `retention_liveness.LAST_RUN_PATH`
#: already holds itself to.
LEDGER_PATH: Final = DATA_DIR / "queue-ledger.yml"

#: `instance/data/queue-ledger.yml`'s own format version.
LEDGER_FILE_VERSION: Final = 1

#: How many distinct events one drain can decrypt for -- see the module
#: docstring's own section. Not a performance number: it is how many
#: `${{ secrets[...] }}` expressions the workflow spells out, and a test
#: fails if the two ever disagree.
MAX_EVENTS_PER_DRAIN: Final = 8


def entry_path(kind: str, entry_id: str) -> str:
    """`queue/<kind>/<entry id>.json`, the path one entry occupies inside
    `QUEUE_BRANCH`. Pure string arithmetic, and the one place that spelling
    exists on the Python side."""
    return f"{QUEUE_DIR}/{kind}/{entry_id}.json"


def responses_path(event_id: str) -> str:
    """`instance/data/events/<id>/survey-responses.enc`, as a repository-relative
    POSIX path -- the file `survey.py` owns the format of and the drain
    rewrites. A string, not a `Path`, because it is a key in
    `DrainOutcome.files` and has to compare equal across platforms."""
    return f"{(DATA_DIR / 'events').as_posix()}/{event_id}/survey-responses.enc"


def registrations_path(event_id: str) -> str:
    """`instance/data/events/<id>/registrations.enc`, the twin of `responses_path`
    above for the other kind this queue carries -- the same file
    `.github/workflows/registration.yml` writes for a registration that
    took the immediate lane, written here by the same
    `registration.upsert` for one that took the slow one. A string for the
    same reason: it is a key in `DrainOutcome.files`."""
    return f"{(DATA_DIR / 'events').as_posix()}/{event_id}/registrations.enc"


@dataclass(frozen=True)
class Entry:
    """One well-formed queue entry, once its name and its content have both
    been read. `payload` is the relay's request body byte for byte -- never
    re-serialised, because what `survey.to_survey_response` decrypts has to
    be exactly what the browser encrypted."""

    name: str
    kind: str
    entry_id: str
    event_id: str
    payload: str


@dataclass(frozen=True)
class Note:
    """One entry that was not handled, and why. `reason` never carries
    anything decrypted or anything a submitter typed: an entry name and an
    event id are the only two identifiers here, and both are already public
    by construction."""

    name: str
    reason: str


@dataclass(frozen=True)
class PendingConfirmation:
    """One stored registration whose confirmation has not gone out yet.

    The drain produces these; the *step after the push* acts on them, and
    only then is the entry cleared from the queue. `changed` is the
    diff `confirmation.compose` renders as "you changed these fields",
    field labels only and never a value -- the identical thing
    `registration.yml` passes between its own two steps as
    `CHANGED_FIELDS`, for the same reason and with the same safety: a
    label is not personal data.
    """

    name: str
    event_id: str
    changed: tuple[str, ...] = ()


@dataclass(frozen=True)
class DrainPlan:
    """What one drain intends to do with what it found.

    Computed twice per run, from the same snapshot of the queue, by two
    steps of the same job: once to name the secrets the drain will need,
    and once by the drain itself. It is a pure function of its inputs, so
    the two agree by construction rather than by passing state between
    steps.
    """

    #: Entries to handle, in the order they must be applied.
    handle: tuple[Entry, ...] = ()
    #: The distinct event ids `handle` covers, in slot order.
    event_ids: tuple[str, ...] = ()
    #: Entries this drain will never handle: cleared, and reported.
    refused: tuple[Note, ...] = ()
    #: Entries left in the queue for the next drain, and reported.
    deferred: tuple[Note, ...] = ()
    #: Entry names the ledger already holds: cleared, not re-applied.
    already_handled: tuple[str, ...] = ()
    #: Registrations the ledger already holds that are **still in the
    #: queue** -- stored by a drain that was interrupted before it could
    #: send their confirmation and clear them. Not re-applied (the ledger
    #: says they are stored, and the ledger lands in the same commit as
    #: the data, so "stored" cannot be wrong), but not cleared either:
    #: they are confirmed, then cleared. See the module docstring's own
    #: "an entry is cleared when it is completely done".
    confirm_only: tuple[Entry, ...] = ()


@dataclass(frozen=True)
class DrainOutcome:
    """What one drain actually did, once the event keys were in hand.

    `files` and `ledger` are what the caller writes to the default branch,
    in one commit; `clear` is what it removes from `QUEUE_BRANCH`
    afterwards, never before -- see the module docstring for why that order
    is the whole of "nothing may be lost".
    """

    files: Mapping[str, str]
    ledger: tuple[str, ...]
    clear: tuple[str, ...]
    refused: tuple[Note, ...] = ()
    deferred: tuple[Note, ...] = ()
    handled: int = 0
    #: The registrations whose confirmation still has to go out, and which
    #: are therefore **absent from `clear`**: the step that sends them is
    #: what adds them to it, after the commit above has been pushed.
    confirm: tuple[PendingConfirmation, ...] = ()


def ledger_to_data(handled: Iterable[str]) -> dict[str, Any]:
    """The plain, YAML-safe structure `cli.py` hands to its own YAML writer
    -- the inverse of `ledger_from_data`. Sorted, so a drain that handled
    the same entries in a different order still writes the same bytes and
    produces no commit of its own."""
    return {"v": LEDGER_FILE_VERSION, "handled": sorted(set(handled))}


def ledger_from_data(data: Any) -> frozenset[str]:
    """Parse an already YAML-loaded `instance/data/queue-ledger.yml`.

    Raises `ValueError` on anything that is not this exact format -- the
    same closed-shape discipline `retention_liveness.last_run_from_data`
    holds itself to, and for a sharper reason here: a ledger this function
    guessed at is a ledger that could report an entry as handled when it
    was not, or as unhandled when it was, and both of those are a lost or a
    doubled submission. A *missing* file is not this function's business;
    it means no drain has ever run, which the caller handles as the empty
    ledger.
    """
    if not isinstance(data, dict) or data.get("v") != LEDGER_FILE_VERSION:
        raise ValueError(f"{LEDGER_PATH.as_posix()} is not a supported format version")
    handled = data.get("handled")
    if not isinstance(handled, list) or not all(isinstance(h, str) for h in handled):
        raise ValueError(f"{LEDGER_PATH.as_posix()} holds no usable handled list")
    return frozenset(handled)


def next_ledger(
    ledger: frozenset[str], present: Iterable[str], newly_handled: Iterable[str]
) -> tuple[str, ...]:
    """The ledger the drain commits: what it has just acted on, plus what it
    was already carrying and can still see in the queue.

    The pruning half is what stops this file growing for ever, and it is
    sound rather than merely tidy. An id the ledger holds that is no longer
    in the queue has been cleared by an earlier drain, and an entry id is
    unique (a uuid), so nothing can ever bring that name back -- there is
    nothing left for the ledger to protect against. An id still in the queue
    is exactly the case the ledger exists for: a drain that committed its
    result and was then interrupted before clearing.

    Note the asymmetry with `DrainPlan.deferred`: a deferred entry is in the
    queue and *not* in `newly_handled`, so it does not enter the ledger and
    the next drain handles it normally.
    """
    still_present = frozenset(present)
    return tuple(sorted((ledger & still_present) | frozenset(newly_handled)))


def read_entry(name: str, text: str) -> Entry | Note:
    """One queue file, read into an `Entry` or a `Note` saying why not.

    `name` is the path inside `QUEUE_BRANCH` (`queue/<kind>/<id>.json`).
    Every failure is untrusted input -- the relay validated the envelope's
    shape, but this function must hold even if it did not -- so nothing here
    raises, and no reason ever quotes the file's content.
    """
    parts = name.split("/")
    if len(parts) != 3 or parts[0] != QUEUE_DIR or not parts[2].endswith(".json"):
        return Note(name, "not a queue entry path")
    kind, entry_id = parts[1], parts[2][: -len(".json")]
    if kind not in KINDS:
        return Note(name, f"no drain serves the {kind!r} kind")
    if not ENTRY_ID_RE.match(entry_id):
        return Note(name, "the entry id is not shaped like one")

    event_id = event_id_from_payload(text)
    if event_id is None:
        return Note(name, "no valid event id in the queued payload")
    return Entry(
        name=name, kind=kind, entry_id=entry_id, event_id=event_id, payload=text
    )


def plan_drain(
    entries: Mapping[str, str],
    ledger: frozenset[str],
    survey_open: Callable[[str], bool],
    *,
    max_events: int = MAX_EVENTS_PER_DRAIN,
) -> DrainPlan:
    """What to do with `entries`, the whole of what the queue held when the
    drain started.

    `survey_open` answers, for one event id, whether that event's survey
    switch is on -- `cli.py::_survey_enabled` reading `instance/data/speakers.yml`.
    Asked here rather than inside the drain so that an entry for a closed
    survey never costs one of the `max_events` slots, which are the scarce
    thing. Asked of survey entries only: there is no equivalent switch on
    the registration side, and the relay's own known-event check is what
    stands there instead.

    Deterministic in every respect: entries are ordered by name (which
    begins with the millisecond the relay wrote them), and events by
    whether a registration is waiting for them and then by their oldest
    waiting entry, so a busy event can never starve a quiet one out of a
    slot. Two drains over the same queue produce the same plan. See the
    module docstring's own "the cap" section for why registrations come
    first when the slots run short.
    """
    refused: list[Note] = []
    deferred: list[Note] = []
    already: list[str] = []
    by_event: dict[str, list[Entry]] = {}
    confirm_by_event: dict[str, list[Entry]] = {}
    oldest: dict[str, str] = {}
    with_registration: set[str] = set()

    def _seen(entry: Entry) -> None:
        # Keyed on the *entry id*, not on the whole path. The path begins
        # `queue/<kind>/`, so ordering paths orders by kind before time --
        # which would make every event holding a registration look older
        # than every event holding only survey responses, and turn the
        # explicit precedence below into an accident of two directory
        # names. Found by mutating that precedence away and watching its
        # own test still pass.
        oldest.setdefault(entry.event_id, entry.entry_id)
        if entry.kind == REGISTRATION_KIND:
            with_registration.add(entry.event_id)

    for name in sorted(entries):
        read = read_entry(name, entries[name])
        if name in ledger:
            if isinstance(read, Entry) and read.kind == REGISTRATION_KIND:
                # Stored, but the drain that stored it never got to send
                # its confirmation -- it is still in the queue, and the
                # queue is what records that. Costs a slot, because the
                # message can only be composed from the plaintext, which
                # only this event's own key opens.
                confirm_by_event.setdefault(read.event_id, []).append(read)
                _seen(read)
            else:
                already.append(name)
            continue
        if isinstance(read, Note):
            refused.append(read)
            continue
        if read.kind == SURVEY_KIND and not survey_open(read.event_id):
            # The same refusal `cli.handle_survey_response` already makes
            # one response at a time, and for the same reason: the relay's
            # own check proves only that `instance/keys/events/<id>.pub` exists, so
            # anyone who knows a live event id could otherwise get an
            # answer stored for an event whose organiser never opened a
            # survey. Refused rather than deferred -- it will not become
            # true by waiting, and an entry that waits for ever blocks the
            # queue.
            refused.append(
                Note(read.name, f"the survey is not open for event {read.event_id}")
            )
            continue
        by_event.setdefault(read.event_id, []).append(read)
        _seen(read)

    # Registration-bearing events take the scarce slots first, then the
    # oldest waiting entry breaks every remaining tie. The two kinds now
    # compete for the same `max_events`, and they do not lose the same
    # thing by waiting: a deferred survey response costs the person who
    # submitted it nothing at all (nothing is ever sent back to them),
    # while a deferred registration spends one of the two drain periods
    # `registration_routing.floor_hours` sets aside for exactly one missed
    # drain. Whichever is deferred is still in the queue, still reported,
    # and still turns the job red -- the ordering decides which one has to
    # spend its margin, never whether anything is lost.
    #
    # Nothing starves behind this. Within each group the oldest waiting
    # entry still wins, so a survey-only event can only be held back by
    # *distinct* events that have registrations waiting, and only while
    # more than `max_events` of them do at once.
    ordered = sorted(
        set(by_event) | set(confirm_by_event),
        key=lambda event_id: (event_id not in with_registration, oldest[event_id]),
    )
    chosen = ordered[:max_events]
    for event_id in ordered[max_events:]:
        for entry in by_event.get(event_id, []) + confirm_by_event.get(event_id, []):
            deferred.append(
                Note(
                    entry.name,
                    f"more than {max_events} events are waiting; event "
                    f"{event_id} keeps its place for the next drain",
                )
            )

    handle = tuple(entry for event_id in chosen for entry in by_event.get(event_id, []))
    confirm_only = tuple(
        entry for event_id in chosen for entry in confirm_by_event.get(event_id, [])
    )
    return DrainPlan(
        handle=handle,
        event_ids=tuple(chosen),
        refused=tuple(refused),
        deferred=tuple(deferred),
        already_handled=tuple(already),
        confirm_only=confirm_only,
    )


def secret_names(plan: DrainPlan, *, slots: int = MAX_EVENTS_PER_DRAIN) -> list[str]:
    """One secret name per slot, `''` for a slot this drain does not need.

    Exactly `slots` long, always: the workflow spells out that many
    `${{ secrets[...] }}` expressions, and an expression whose name is the
    empty string resolves to the empty string rather than failing, which is
    what lets the same job serve a drain of one event and a drain of eight.
    """
    names = [eventkeys.secret_name(event_id) for event_id in plan.event_ids[:slots]]
    return names + [""] * (slots - len(names))


def drain(
    plan: DrainPlan,
    keys: Mapping[str, str],
    existing: Mapping[str, str | None],
    ledger: frozenset[str],
    present: Iterable[str],
) -> DrainOutcome:
    """Apply `plan`, and say exactly what to write and what to clear.

    `keys` maps an event id to that event's private key PEM; an event
    missing from it, or holding an empty string, is **deferred, never
    refused** -- an unconfigured secret is the operator's problem, and
    clearing a submission because of it would destroy a response nobody
    could get back. `existing` maps a repository-relative path to that
    file's current text, or `None` where the event has no responses yet.

    Pure but not deterministic in its *output bytes*: `survey.add_response`
    encrypts each response afresh under a random AES key, so re-running this
    on the same input produces different ciphertext. That is the wire format
    working as designed, and it is why a replayed drain is made safe by the
    ledger rather than by comparing files.
    """
    files: dict[str, str] = {}
    refused = list(plan.refused)
    deferred = list(plan.deferred)
    newly_handled: list[str] = []
    awaiting: list[PendingConfirmation] = []
    handled = 0

    for event_id in plan.event_ids:
        entries = [entry for entry in plan.handle if entry.event_id == event_id]
        to_confirm = [
            entry for entry in plan.confirm_only if entry.event_id == event_id
        ]
        private_pem = keys.get(event_id) or ""
        if not private_pem:
            for entry in entries + to_confirm:
                deferred.append(
                    Note(entry.name, f"no private key configured for event {event_id}")
                )
            continue

        surveys = [entry for entry in entries if entry.kind == SURVEY_KIND]
        registrations = [entry for entry in entries if entry.kind == REGISTRATION_KIND]

        if surveys:
            path = responses_path(event_id)
            try:
                current = survey.load_response_file(existing.get(path))
            except ValueError as exc:
                # A committed file this drain cannot parse: every entry for
                # that event waits rather than being written into a file
                # whose shape nobody understands. Deferred, not refused, for
                # the same reason a missing key is -- the operator can still
                # fix the file.
                for entry in surveys:
                    deferred.append(Note(entry.name, f"{path}: {exc}"))
            else:
                for entry in surveys:
                    response = survey.to_survey_response(entry.payload, private_pem)
                    if response is None:
                        # "could not be read", never "could not be
                        # decrypted": `to_survey_response` folds a too-long
                        # answer into the same uniform `None` as an
                        # undecryptable envelope, and this line must not
                        # claim a cause it did not observe.
                        refused.append(
                            Note(
                                entry.name,
                                f"a queued response for event {event_id} "
                                "could not be read",
                            )
                        )
                        newly_handled.append(entry.name)
                        continue
                    current = survey.add_response(
                        current, response, private_pem=private_pem
                    )
                    newly_handled.append(entry.name)
                    handled += 1
                files[path] = survey.dump_response_file(current)

        if registrations:
            path = registrations_path(event_id)
            try:
                stored = load_registration_file(existing.get(path))
            except ValueError as exc:
                for entry in registrations:
                    deferred.append(Note(entry.name, f"{path}: {exc}"))
            else:
                touched = False
                for entry in registrations:
                    signup = to_registration(entry.payload, private_pem)
                    if signup is None:
                        refused.append(
                            Note(
                                entry.name,
                                f"a queued registration for event {event_id} "
                                "could not be read",
                            )
                        )
                        newly_handled.append(entry.name)
                        continue
                    # Read before `upsert` overwrites it, exactly as
                    # `cli.handle_registration` does for the immediate lane:
                    # the diff is against the *prior* stored entry, and
                    # after the upsert there is no prior entry left to read.
                    # Applying entries in name order -- which is submission
                    # order -- is what makes a registration and its own
                    # update in one drain produce what two drains would.
                    old = find_by_email(stored, signup.email, private_pem)
                    stored, _replaced = upsert(stored, signup, private_pem=private_pem)
                    touched = True
                    awaiting.append(
                        PendingConfirmation(
                            name=entry.name,
                            event_id=event_id,
                            changed=(
                                confirmation.changed_fields(old, signup)
                                if old is not None
                                else ()
                            ),
                        )
                    )
                    # In the ledger, so a replay never stores it twice --
                    # and deliberately *not* in `clear`: the entry stays in
                    # the queue until its confirmation has actually been
                    # attempted. See the module docstring.
                    newly_handled.append(entry.name)
                    handled += 1
                if touched:
                    files[path] = dump_registration_file(stored)

        # Stored by an earlier, interrupted drain. Nothing is re-applied --
        # the ledger and the data landed in one commit, so "stored" is not
        # in doubt -- but the confirmation still has to go out, with no
        # `changed` diff: the prior entry it would have been computed
        # against was overwritten by the drain that stored this one, and
        # `resend_confirmation` already settles what to do about that
        # (repeat the current registration, never describe an update).
        for entry in to_confirm:
            awaiting.append(PendingConfirmation(name=entry.name, event_id=event_id))

    newly_handled.extend(note.name for note in plan.refused)
    pending = {item.name for item in awaiting}
    clear = tuple(sorted((set(newly_handled) | set(plan.already_handled)) - pending))
    return DrainOutcome(
        files=files,
        ledger=next_ledger(ledger, present, newly_handled),
        clear=clear,
        refused=tuple(refused),
        deferred=tuple(deferred),
        handled=handled,
        confirm=tuple(awaiting),
    )


def annotation_lines(outcome: DrainOutcome) -> list[str]:
    """Every line the drain prints for GitHub Actions to render on the run.

    **A deferral is the `::error::` and a refusal the `::warning::`, which is
    the opposite of the intuitive assignment and is the whole point.** The
    workflow turns a deferral red, so what may turn this job red has to be
    something only the operator can cause: a key nobody configured, a
    committed file nobody can parse, more open events than there are slots.
    A refusal is caused by whoever submitted -- an envelope that will not
    decrypt, a survey closed between the submission and the drain -- and a
    stranger who could turn the daily job red at will would be able to
    train the operator to ignore it, which costs more than the finding is
    worth. Refusals are annotated, counted, and never silent; they simply
    do not get to decide the colour of the run.

    Composed here rather than in `cli.py` so a test can read the exact text
    without capturing stdout.
    """
    lines = [
        f"::error::{note.name}: {note.reason}"
        for note in sorted(outcome.deferred, key=lambda note: note.name)
    ]
    lines += [
        f"::warning::{note.name}: {note.reason}"
        for note in sorted(outcome.refused, key=lambda note: note.name)
    ]
    return lines


def queue_files_in(paths: Sequence[str]) -> list[str]:
    """Every path in `paths` that is a queue entry -- the sweep
    `tools/tests/journey/test_submission_queue.py` runs over a checkout of the
    default branch, where the answer must always be empty.

    It exists because the one precondition the workflow sweep cannot
    enforce -- no pull request from `QUEUE_BRANCH` -- becomes visible one
    step later, as queue files arriving on the default branch. This turns
    that from a silent five-runs-per-submission regression into a red test
    on the pull request that would cause it.
    """
    prefix = f"{QUEUE_DIR}/"
    return [path for path in paths if path.startswith(prefix)]


def summary(outcome: DrainOutcome) -> str:
    """One line naming what the drain did, with no identifier in it that is
    not already public -- counts only."""
    return (
        f"drained {outcome.handled} submission(s) across "
        f"{len(outcome.files)} event(s); {len(outcome.refused)} refused, "
        f"{len(outcome.deferred)} left waiting, "
        f"{len(outcome.confirm)} awaiting a confirmation"
    )
