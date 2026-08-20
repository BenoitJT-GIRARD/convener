"""Compose and deliver the registration confirmation -- the only channel a
participant is ever sent down (phase 4 spec S:3, S:9), and, per the ruling
below, the only channel that can ever let a real participant notice that
their registration was silently overwritten.

What the message must carry (spec S:3)
---------------------------------------
The room link, the matching code together with the exact instruction to put
it in the display name used when joining, the data-protection notice, and
the means to exercise data-protection rights. The second item is
load-bearing: task 8's whole attendance-matching cascade (spec S:5) rests on
a participant typing this code where instructed, so it is built from
`MATCHING_INSTRUCTION` below rather than restated by hand at each call site
-- one sentence, quoted by `test_confirmation.py` against both this module's
own output and the documentation copy
(`docs/toolkit/emails/registration-confirmed.md`), so the two cannot quietly
say different things.

`matching_code` (`registration.py`) returns `None` when `CONVENER_MATCHING_SALT`
is unset, and `config/integrations.yml`'s own `matching_salt` row calls that
an *ordinary* D-13 absence, with spec S:5's cascade (exact address, then
normalised name) as the documented fallback. `compose` below does not
refuse to send without a code for that reason; it sends a message that
names the fallback instead.

An update is sent down the same channel, not only a first registration (R-9)
------------------------------------------------------------------------------
Registrations deduplicate by address (`registration.py::upsert`), and the
entry point that reaches this job is deliberately without a shared secret --
a browser cannot hold one. So anyone who knows an event id and a
participant's address can overwrite that participant's name, institution or
announce-list preference, and a certificate is generated from exactly that
stored data. The review that found this ruled it *mandated* behaviour, not a
defect -- the relay's openness is deliberate, a decision task 5 already made
-- and named this confirmation as the only channel a genuine participant is
ever sent down that could let them notice an overwrite that was not theirs.

A channel nobody is ever sent down is not a channel. So `compose` takes
`changed`: the field *labels* that differ from the registration this one
replaced (`registration.changed_fields`), never old or new values -- naming
a field is enough to let the real owner recognise "that was not me", and
quoting a value they did not write back to them would be worse, not better.
When `changed` is non-empty the message says which fields changed and asks
the reader to write in if it was not them; when it is empty (a first
registration, or a resend) it says nothing about a change, because there
was not one. A manual resend (`convener-resend-confirmation`, `cli.py`) always
composes with `changed=()`: it repeats the current, stored message rather
than describing an update, so it must never claim one.

The transport, and the one place D-13's "inspectable log" does not mean
stdout
-------------------------------------------------------------------------
`config/integrations.yml`'s `email_transport` row promises: without its five
secrets, a message is "written to an inspectable log instead of being sent".
`notify.py` meets that promise, for board notifications, by printing
straight to the job's own stdout -- safe there because that module holds no
field that could ever be a name or an address (see its own docstring's "What
may leave the repository" section). This module's whole purpose is the
opposite: every message it composes carries a participant's address and
their matching code.

Printing either to stdout would write them into GitHub's own captured
Actions log -- persisted for the organisation to read, indefinitely for
practical purposes, and never something this project puts personal data
into on purpose (the same hard rule `registration.py` exists to uphold for
the committed file, applied here to a *log* rather than to git history).

So `deliver` below never prints anything, on any path. When no transport is
configured -- or when the real one raises -- it hands the *whole* composed
text back to the caller as `SendResult.unsent_body`, and does nothing else
with it: writing it anywhere is `cli.py`'s job, to a single fixed,
`.gitignore`d file inside the job's own ephemeral workspace, never to
stdout and never committed. `.github/workflows/registration.yml`
additionally uploads that file as a short-retention, access-controlled
build artifact when it exists, which is what keeps "inspectable" true in
the sense that matters -- a volunteer with the same access as the job log
already has can still read the message -- without the address or the code
ever entering the log stream itself, which is copy-pasteable, greppable by
anyone who can read Actions logs, and effectively permanent in a way a
short-retention artifact is not.

`deliver` catches only `smtplib.SMTPException` and `OSError` -- a real
network or protocol failure, never a caller mistake such as a bad argument
type, which should still raise. It deliberately does not inspect or forward
the caught exception's own text anywhere: `smtplib` routinely echoes the
*recipient address* into an `SMTPRecipientsRefused` message, and forwarding
that string to a caller that might print it would reopen the exact leak
this module exists to close.
"""

from __future__ import annotations

import smtplib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Final, Protocol

from .platform import EventNotFoundError, Platform, Room, find_speaker
from .registration import Registration

__all__ = [
    "FIELD_LABELS",
    "MATCHING_INSTRUCTION",
    "Confirmation",
    "EmailTransport",
    "EventDetails",
    "EventNotFoundError",
    "SendResult",
    "SmtpConfig",
    "changed_fields",
    "compose",
    "deliver",
    "event_details",
    "smtp_config_from_env",
]

# ------------------------------------------------------------------ #
# What changed, named rather than quoted (R-9)
# ------------------------------------------------------------------ #

#: `Registration` field name -> the label an update notice names it by, in
#: the order fields are listed in when more than one changed. `email` is
#: included even though it is the field `upsert` matches *by* -- the match
#: is on `normalize_email`, so the literal stored string (case, whitespace)
#: can still differ between the two registrations `changed_fields` compares.
FIELD_LABELS: Final[dict[str, str]] = {
    "first_name": "first name",
    "surname": "surname",
    "email": "e-mail address",
    "institution": "institution",
    "membership_opt_in": "announce-list subscription",
}


def changed_fields(old: Registration, new: Registration) -> tuple[str, ...]:
    """The labels of every field that differs between `old` and `new`, in
    `FIELD_LABELS`'s own order -- never the values themselves (see the
    module docstring's R-9 section for why). `old` and `new` are assumed to
    be the same registrant (`upsert` already matched them by normalised
    address before either reaches here); this does not check that itself,
    the same "the caller already established the precondition" contract
    `registration.upsert` documents for its own comparison loop.
    """
    return tuple(
        label
        for name, label in FIELD_LABELS.items()
        if getattr(old, name) != getattr(new, name)
    )


def _join_labels(labels: Sequence[str]) -> str:
    """ "a" / "a and b" / "a, b and c" -- an ordinary English list, no Oxford
    comma before the final "and" (house style: see `docs/toolkit/emails/`
    for the convention this mirrors)."""
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


#: The sentence an update notice warns with, naming what to do -- reply,
#: not "contact us" in the abstract, since a reply is the one channel this
#: message itself already proves is reachable. Quoted by
#: `test_confirmation.py` against the docs copy, the same way
#: `MATCHING_INSTRUCTION` is.
UPDATE_WARNING: Final = (
    "If that was not you, someone else may have used your e-mail address. "
    "Please reply to this message straight away and we will look into it"
)


# ------------------------------------------------------------------ #
# What the event contributes: title and date from the speaker record,
# the room from the Platform interface (D-05) rather than read directly --
# so this module never has to know which implementation answered.
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class EventDetails:
    """What the confirmation needs to know about the event itself, beyond
    the registration. `title` and `date` come straight off the matching
    speaker record -- the same fields `docs/toolkit/emails/*.md` already
    read as `{{ speaker.title }}` and `{{ speaker.date }}` -- because they
    are ordinary record fields with no `Platform` abstraction wrapping
    them. The room link and join instructions come through
    `Platform.get_room` instead, so a manual event and an API-backed one
    read identically here."""

    title: str
    date: str
    room: Room


def event_details(
    speakers: Sequence[Mapping[str, Any]], event_id: str, platform: Platform
) -> EventDetails:
    """Raises `EventNotFoundError` (naming `event_id`), exactly when
    `find_speaker` or `Platform.get_room` would -- no speaker record has
    this id. Deciding what a registration for an event with no matching
    record should still send is the caller's call (`cli.py`), not this
    function's: it does not guess at a blank `EventDetails` itself."""
    record = find_speaker(speakers, event_id)
    title = str(record.get("title", "") or "")
    date = str(record.get("date", "") or "")
    return EventDetails(title=title, date=date, room=platform.get_room(event_id))


# ------------------------------------------------------------------ #
# Composing the message
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class Confirmation:
    """One composed message, ready to deliver or to log. Holds exactly
    what an outbound e-mail needs -- never anything about *why* it was
    composed (an event id, a "replaced" flag): those belong to the caller
    that built it, not to the message itself."""

    to: str
    subject: str
    body: str


#: The load-bearing sentence (spec S:3, S:5): the exact instruction that
#: turns a participant's free-typed display name into a deterministic
#: match. A named constant, not inlined in `compose`, so
#: `test_confirmation.py` can pin the same words against
#: `docs/toolkit/emails/registration-confirmed.md` without a second,
#: hand-copied sentence living in the test file too.
MATCHING_INSTRUCTION: Final = (
    "Put this exact code into the display name you type when you join, and nowhere else"
)

#: What the message says instead, when no code could be generated
#: (`CONVENER_MATCHING_SALT` unset -- an ordinary D-13 absence, see the module
#: docstring). Names the fallback spec S:5 documents, so a participant is
#: never told nothing about how they will be recognised.
_NO_CODE_FALLBACK: Final = (
    "We could not generate a matching code for this event, so we will "
    "match your attendance by the e-mail address and the name on this "
    "registration instead."
)

_DATA_PROTECTION = (
    "Data protection. We hold your name, e-mail address and institution "
    "only for this event, encrypted under a key that exists only for it; "
    "the key is destroyed 90 days after the event, after which the data "
    "is permanently unreadable. It is never published, and it is only "
    "ever decrypted automatically, to record your registration and to "
    "issue your certificate."
)

_RIGHTS_NOTICE = (
    "To see, correct, withdraw or erase your data before then, or for "
    "any other question, reply to this message."
)


def compose(
    registration: Registration,
    event: EventDetails,
    matching_code: str | None,
    changed: Sequence[str] = (),
) -> Confirmation:
    """The confirmation for one registration. Deterministic in every input:
    the same four arguments always produce the same `Confirmation`, which is
    what lets a manual resend (`deliver`, called again with `changed=()`)
    reproduce the first message exactly rather than a message that merely
    carries the same code.

    `matching_code` is `str | None`, not computed here: `compose` stays a
    pure function of its arguments, and `registration.matching_code` is
    already the one place that derivation happens (see its own docstring).
    """
    subject = "Your registration is confirmed"
    if event.title:
        subject = f"{subject} — {event.title}"

    what = f" for {event.title}" if event.title else ""
    when = f" on {event.date}" if event.date else ""

    lines: list[str] = [
        f"Dear {registration.first_name},",
        "",
        f"Your registration{what}{when} is confirmed.",
        "",
    ]

    if event.room.join_url:
        lines.append(f"Join here: {event.room.join_url}")
    else:
        lines.append(
            "The room link for this event has not been set yet -- we will "
            "send it as soon as it is, to this same address."
        )
    if event.room.instructions:
        lines.append(event.room.instructions)
    lines.append("")

    if matching_code:
        lines.append(f"{MATCHING_INSTRUCTION}: {matching_code}")
        lines.append(
            "We compare that name against our attendance record after the "
            "seminar to issue your certificate, so a display name that "
            "does not carry this code means we may not be able to find "
            "you in the room."
        )
    else:
        lines.append(_NO_CODE_FALLBACK)
    lines.append("")

    if changed:
        lines.append(
            "This confirms an update to an earlier registration for this "
            f"event: we changed the {_join_labels(list(changed))}. "
            f"{UPDATE_WARNING}."
        )
        lines.append("")

    lines.append(_DATA_PROTECTION)
    lines.append(_RIGHTS_NOTICE)
    lines.append("")
    lines.append("Best regards,")
    lines.append("The Example Collective team")

    return Confirmation(
        to=registration.email, subject=subject, body="\n".join(lines) + "\n"
    )


# ------------------------------------------------------------------ #
# The transport (D-13) -- see the module docstring for what "an
# inspectable log" has to mean once a message carries personal data.
# ------------------------------------------------------------------ #

#: The five `email_transport` secrets (`config/integrations.yml`), read the
#: same "all five or none" way `notify.resolve_channel` reads its own two
#: and `platform_fcc.platform_from_env` reads its one: a partly-set
#: integration is not a working one.
_HOST_ENV: Final = "CONVENER_SMTP_HOST"
_PORT_ENV: Final = "CONVENER_SMTP_PORT"
_USER_ENV: Final = "CONVENER_SMTP_USER"
_PASSWORD_ENV: Final = "CONVENER_SMTP_PASSWORD"
_FROM_ENV: Final = "CONVENER_SMTP_FROM"

#: SMTP's own implicit-TLS port (RFC 8314). Any other configured port uses
#: STARTTLS instead. `CONVENER_SMTP_PORT` exists specifically so this adapter is
#: not locked to one provider's convention -- raccordement spec S:7: Gmail
#: wants 587 with STARTTLS, other providers want 465 implicit TLS, and
#: hard-coding either would silently exclude the other.
_IMPLICIT_TLS_PORT: Final = 465

#: Bounds `int(CONVENER_SMTP_PORT)` to a value `socket.connect` could ever use.
_MAX_PORT: Final = 65535


@dataclass(frozen=True)
class SmtpConfig:
    """The five secrets, resolved and validated. Never constructed with a
    blank field -- see `smtp_config_from_env`, the only place this is
    built."""

    host: str
    port: int
    user: str
    password: str
    sender: str


def smtp_config_from_env(env: Mapping[str, str]) -> SmtpConfig | None:
    """D-13, applied in full: `None` when any of the five secrets is
    absent, blank, or when `CONVENER_SMTP_PORT` is not a usable port number --
    never a half-built config a caller could try to connect with. Mirrors
    `platform_fcc.platform_from_env`'s "given the environment as a plain
    mapping, decide once" shape."""
    host = (env.get(_HOST_ENV) or "").strip()
    port_raw = (env.get(_PORT_ENV) or "").strip()
    user = (env.get(_USER_ENV) or "").strip()
    password = (env.get(_PASSWORD_ENV) or "").strip()
    sender = (env.get(_FROM_ENV) or "").strip()
    if not host or not port_raw or not user or not password or not sender:
        return None
    try:
        port = int(port_raw)
    except ValueError:
        return None
    if not (0 < port <= _MAX_PORT):
        return None
    return SmtpConfig(host=host, port=port, user=user, password=password, sender=sender)


class EmailTransport(Protocol):
    """What `deliver` needs from something that can actually send mail: one
    authenticated message, over one already-resolved `SmtpConfig`. The real
    implementation (`_SmtpTransport`) wraps `smtplib`; every test in
    `test_confirmation.py` substitutes a fake, which is what keeps this
    whole suite off the network."""

    def send(self, config: SmtpConfig, message: Confirmation) -> None: ...


@dataclass(frozen=True)
class _SmtpTransport:
    """The only piece of this module that touches the network. Never
    constructed by a test -- `deliver`'s `transport` parameter exists so a
    test never has to. Stdlib `smtplib` only, no new dependency."""

    timeout: float = 30.0

    def send(self, config: SmtpConfig, message: Confirmation) -> None:
        email = EmailMessage()
        email["Subject"] = message.subject
        email["From"] = config.sender
        email["To"] = message.to
        email.set_content(message.body)
        if config.port == _IMPLICIT_TLS_PORT:
            with smtplib.SMTP_SSL(
                config.host, config.port, timeout=self.timeout
            ) as client:
                client.login(config.user, config.password)
                client.send_message(email)
        else:
            with smtplib.SMTP(config.host, config.port, timeout=self.timeout) as client:
                client.starttls()
                client.login(config.user, config.password)
                client.send_message(email)


@dataclass(frozen=True)
class SendResult:
    """The outcome of trying to deliver one `Confirmation`.

    `unsent_body` is set exactly when `sent` is `False`, and holds the
    *whole* composed message, address and code included -- this module
    never prints it. Writing it anywhere at all is the caller's decision;
    see the module docstring's transport section for what `cli.py` does
    with it."""

    sent: bool
    unsent_body: str | None


def _rendered(message: Confirmation) -> str:
    """The plain-text form `cli.py` writes to its own log file when a
    message could not be delivered -- readable, and pasteable straight into
    a mail client for a manual send if it ever comes to that."""
    return f"To: {message.to}\nSubject: {message.subject}\n\n{message.body}"


def deliver(
    message: Confirmation,
    env: Mapping[str, str],
    *,
    transport: EmailTransport | None = None,
) -> SendResult:
    """Send `message`, or hand it back unsent -- see the module docstring
    for why "unsent" never means "printed" here. Two causes collapse to the
    same `SendResult`, deliberately, the same way `notify.dispatch`
    collapses "nothing to say" and "no channel configured": no transport
    configured, and a configured transport that raised
    `smtplib.SMTPException` or `OSError` while sending. Both are D-13's
    ordinary absence from this caller's point of view -- the registration
    itself was already recorded before this function is ever called, so
    neither cause should fail the job that called it.
    """
    config = smtp_config_from_env(env)
    if config is None:
        return SendResult(sent=False, unsent_body=_rendered(message))
    active_transport = transport if transport is not None else _SmtpTransport()
    try:
        active_transport.send(config, message)
    except (smtplib.SMTPException, OSError):
        return SendResult(sent=False, unsent_body=_rendered(message))
    return SendResult(sent=True, unsent_body=None)
