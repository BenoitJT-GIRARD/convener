"""Telling the people who registered that an edition is off.

A cancellation is the one act in this journey whose cost falls entirely on
people outside it. The record self-heals: `instance/keys/events/<id>.pub`
stops being minted for the moment the status leaves `scheduled`, the events
feed stops carrying the edition, and the event key is destroyed ninety days
after the date that was announced, cancelled or not. **The people do not.** A
participant who registered, received a confirmation naming a date, and was
promised a certificate is owed a message, and until this module existed there
was nothing that could send one.

**Why a ledger rather than a flag on the record.** The cockpit writes files
and dispatches nothing -- its token carries `contents` and no more -- so the
only trigger available is the push that carries the cancellation. A workflow
reacting to a push has to answer "which of these have not been told yet",
and the answer cannot live on the speaker record: a record rewritten by any
other hand would carry the answer with it, and a re-run would either send a
second message to everyone or none to anybody. `instance/data/cancellations.yml`
is that answer, in the same shape and for the same reason as
`instance/data/event-key-destructions.yml`: one line per event, written after
the fact, and the difference between the two lists is the work still to do.

**Pure, like the rest of the journey.** Nothing here reads a file, sends a
message or asks the clock. `pending` takes the records and the ledger;
`compose` takes one registration and the event. The I/O is
`cli/journey/cancellation.py`'s, and the decision to send is the workflow's.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any, Final

from convener_ops.declaration.paths import DATA_DIR
from convener_ops.journey.confirmation import Confirmation, EventDetails
from convener_ops.journey.registration import Registration

#: Where the ledger lives. Under `instance/data/`, which the boundary hands to
#: the instance whole, beside the destruction registry it is modelled on.
LEDGER_PATH: Final = DATA_DIR / "cancellations.yml"

#: The status a cancelled edition carries. Spelt once here rather than
#: compared inline in three places: `app/src/data/types.ts` is where the word
#: is decided, and a second spelling on this side is how the two come to
#: disagree about a record neither of them can see.
CANCELLED: Final = "cancelled"

#: The version this file's shape is at, the same declaration discipline every
#: other instance file follows.
LEDGER_VERSION: Final = 1


def pending(
    speakers: Iterable[Mapping[str, Any]], told: Mapping[str, date]
) -> tuple[str, ...]:
    """The cancelled editions nobody has written to yet, oldest id first.

    The difference between two lists, which is what makes a re-run safe: a
    workflow that had already sent finds nothing to do, and one that failed
    halfway finds exactly what it missed. Neither state is recoverable from a
    flag on a record that any other write would carry along with it.
    """
    waiting = [
        str(entry.get("id", "")).lower()
        for entry in speakers
        if entry.get("status") == CANCELLED
    ]
    return tuple(sorted({one for one in waiting if one and one not in told}))


def ledger_from_data(data: Any) -> dict[str, date]:
    """Parse the ledger. Refuses rather than repairs, like every declaration
    in this project: a ledger that cannot be read is worse than an absent one,
    because an absent one means "tell everybody" and an unreadable one means
    whatever the reader guessed."""
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise ValueError(f"{LEDGER_PATH.as_posix()} is not a mapping")
    rows = data.get("cancellations")
    if rows is None:
        return {}
    if not isinstance(rows, list):
        raise ValueError(
            f"{LEDGER_PATH.as_posix()}: cancellations is "
            f"{type(rows).__name__}, and it has to be a list"
        )
    told: dict[str, date] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(
                f"{LEDGER_PATH.as_posix()}: an entry is "
                f"{type(row).__name__} rather than a mapping"
            )
        event_id = row.get("event")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError(f"{LEDGER_PATH.as_posix()}: an entry names no event")
        day = row.get("told_on")
        # An ISO string, the way `eventkeys.registry_from_data` reads the
        # destruction registry and for the same reason: this file is dumped by
        # `store.dump`, which writes a date as a quoted string, so a reader
        # expecting a `date` object would refuse the file it had just written.
        if not isinstance(day, str):
            raise ValueError(
                f"{LEDGER_PATH.as_posix()}: {event_id} has told_on {day!r}, "
                "which is not a date written as YYYY-MM-DD"
            )
        try:
            told[event_id] = date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError(
                f"{LEDGER_PATH.as_posix()}: {event_id} has told_on {day!r}, "
                "which is not a date written as YYYY-MM-DD"
            ) from exc
    return told


def ledger_to_data(told: Mapping[str, date]) -> dict[str, Any]:
    """The ledger as it is written back, sorted so a diff reads as one line
    added rather than a file reordered."""
    return {
        "v": LEDGER_VERSION,
        "cancellations": [
            {"event": event_id, "told_on": told[event_id].isoformat()}
            for event_id in sorted(told)
        ],
    }


def compose(registration: Registration, event: EventDetails) -> Confirmation:
    """The message one registrant receives.

    Deterministic in both arguments, like `confirmation.compose`, so a re-run
    that reaches somebody twice reaches them with the identical message rather
    than a second, differently-worded one.

    **It says the one thing the reader needs in the first line.** Everything
    else -- why, what happens to their data, whether they need to do anything
    -- is below it. Somebody scanning a subject line and a first sentence on a
    phone must not have to read to the end to learn that they should not turn
    up.

    **It does not say why.** The reason is in the register, in a closed
    vocabulary, and none of its four values is anybody's business but the
    series': "the speaker withdrew" is a fact about a person who did not
    consent to it being mailed to two hundred strangers. What a registrant is
    owed is that it is off, that nothing is expected of them, and what becomes
    of what they gave.
    """
    what = f" for {event.title}" if event.title else ""
    when = f" on {event.date}" if event.date else ""

    subject = "Cancelled"
    if event.title:
        subject = f"{subject} — {event.title}"

    lines: list[str] = [
        f"Dear {registration.first_name},",
        "",
        f"The seminar you registered{what}{when} has been cancelled, and will "
        "not take place.",
        "",
        "There is nothing you need to do. Please ignore the joining details in "
        "your confirmation, and accept our apologies for the change.",
        "",
        "Your registration is closed. What you gave us stays encrypted and is "
        "destroyed on the schedule the confirmation described, on the date the "
        "seminar would have been held — a cancellation does not extend it.",
        "",
        "If this talk finds a new date it will be announced as a new seminar, "
        "and registering again will be a fresh decision rather than something "
        "we carried over on your behalf.",
    ]
    return Confirmation(to=registration.email, subject=subject, body="\n".join(lines))


def summary(event_id: str, sent: int, unsent: int, unreadable: int) -> str:
    """What a run says about one edition, whatever it found.

    Always printed, including "nobody had registered" -- the case this
    product's first cancellation will almost certainly be. A run that goes
    quiet when there is nobody to tell is indistinguishable from one that
    could not read the file, and only one of those is good news.
    """
    if sent == 0 and unsent == 0 and unreadable == 0:
        return f"{event_id}: nobody had registered, so there was nobody to tell"
    parts = [f"{event_id}: {sent} told"]
    if unsent:
        parts.append(f"{unsent} could not be sent")
    if unreadable:
        parts.append(f"{unreadable} entry(ies) could not be read")
    return "; ".join(parts)


def recorded(told: Mapping[str, date], event_id: str, today: date) -> dict[str, date]:
    """The ledger with `event_id` written into it, or unchanged if it is
    already there. Idempotent on purpose: a re-run records the first day, not
    the day of the re-run, because the first is when the people were told."""
    if event_id in told:
        return dict(told)
    return {**told, event_id: today}


def every_registrant(
    registrations: Sequence[Registration], event: EventDetails
) -> list[Confirmation]:
    """One message per registration, in the order they were taken."""
    return [compose(registration, event) for registration in registrations]
