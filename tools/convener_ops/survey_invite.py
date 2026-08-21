"""Compose the post-event survey invitation, and keep the one record that
stops a re-dispatch from sending it twice -- phase 4 spec S:6's other half
of "meme entree que l'inscription": `tools/convener_ops/survey.py` is the
storage side (task 16a); this module is the *sending* side (task 16b),
"envoye apres coup aux seules personnes reconnues presentes".

Who gets invited, and why the other two do not (ruling 1)
------------------------------------------------------------
`attendance.match` (task 8) sorts every person a session's own attendance
export names into exactly three outcomes -- see that module's own "Three
outcomes, not two" section. Only `MatchedAttendee` is invited here:

- A **matched** attendee is a stored `Registration` the cascade tied to a
  room presence -- "reconnue presente" in the plainest possible sense: a
  person we can name, and can prove was in the room.
- An **unmatched** attendee (`UnmatchedAttendee`) was in the room but the
  cascade could not tie the address it saw to any registration on file.
  Not invited, and not only because spec S:6 says "reconnues presentes":
  this module has no address to send to either. `UnmatchedAttendee`
  carries the *room's* display name and address, never a
  `Registration` -- inventing an invitation from that would mean composing
  a message that names nobody's own stored consent to be written to at
  all, for a channel spec S:3 restricts to a registration in the first
  place.
- An **unreachable** attendee (`UnreachableAttendee`) joined by telephone.
  `attendance.py`'s own module docstring calls this a boundary, not a
  matching weakness: "no matching cascade this project can build ... will
  ever reach them by address ... for want of both." There has never been
  an address on file for this person, from any source, so there is
  nothing to exclude by policy here -- it was already excluded by fact,
  before this module was ever written.

So the fact this module invites *matched* attendees, not *eligible* ones
(`attendance.eligible_attendees`, the certificate-issuing threshold task 12
computes), is deliberate too: eligibility is a share of the seminar's own
scheduled duration, a bar spec S:5 sets for a signed attestation of
learning-adjacent presence; "reconnue presente" (S:6) asks only whether we
recognised the person in the room at all. Someone present for five minutes
is not eligible for a certificate, but they were, in fact, recognised
present, and the spec's own words for who receives a survey invitation are
narrower than "eligible" only in one direction -- they never say "eligible
attendee". Requiring the certificate threshold here would refuse an
invitation to someone the spec's own sentence plainly includes.

No personal data in the subject or the headers, and the same link for
everyone (ruling 2)
-----------------------------------------------------------------------------
The message names no certificate, no identifier, no matching code, and no
per-recipient token: `survey_url` returns exactly one string, `event_id`
and nothing else, the same address for every matched attendee of the same
event. A per-person token would be an identifier -- the one thing
`survey.py`'s own module docstring spends its whole "Why no identity
travels with a response" section refusing to let a stored answer carry --
and minting one just to hand it to the invitation, only for the survey page
to then discard it before encrypting anything, would smuggle the very
distinguishing mark the storage design exists to keep out, one hop
upstream of where it is checked. The subject line names the event, never
the recipient -- `event_title` is not personal data, the same reasoning
`confirmation.compose` and `delivery.compose` already rely on for their own
subject lines.

The body itself *does* open "Dear <first name>," as those two messages
also do: this is an ordinary, personally-addressed e-mail, sent to the
recipient's own address, out of the same registration record their
confirmation and their certificate already used it from. Nothing about
this invitation is anonymous, and nothing here claims it is -- only the
*survey response* the link leads to is designed to carry no identity; see
`survey.py`'s module docstring and `docs/reference/operations.md`'s
"Anonymous against a stranger; pseudonymous by metadata against the
organiser" section for the qualified claim this module must never
contradict by saying less carefully. This module does not repeat that
claim at all: the survey page itself (`SurveyForm.tsx`) is the one place a
participant reads it, in full, before answering anything, and a second,
shorter paraphrase in an e-mail could only say it less precisely, never
more.

A resend must not re-invite everybody, and what is honestly not solved
(ruling 3)
-----------------------------------------------------------------------------
`certificate.py`'s own identifiers let R-27 (task 14's own fix) restrict a
resend to exactly what one run minted, and report exactly which identifier
failed, because an identifier is a certificate's own public name, never a
person's. This module has no such name to give anything: a survey
invitation is not a register entry, and inventing one -- even a public,
content-free one, "invitation #7 for event mrg-042" -- would still be a
handle that let whoever holds `data/events/<id>/survey_responses.enc` and
the invitation log line up "the seventh person invited" against "the
response that arrived nine minutes after invitation seven went out",
exactly the metadata-pairing `operations.md`'s pseudonymity section already
names as the one channel padding cannot close. So this module does not
build a per-person restriction at all, and says so rather than pretending
otherwise:

**The bound is per event, not per person.** `data/survey-invitations.yml`
(`registry_from_data`/`registry_to_data`, below) records only that event
*X* was invited, and on what day -- no name, no address, no count of how
many. `cli.py::invite_survey` refuses outright, before composing anything,
once an event already carries an entry here, unless an operator ticks the
workflow's own `resend_all` -- which then re-invites *every* currently
matched attendee, including everyone the first run already reached.
Duplicate, not targeted: this module cannot single out the one recipient
whose message actually bounced, because nothing it holds says which one
that was. That is the honest cost of carrying no identifier -- accepted
here for the same reason `survey.py`'s own module docstring accepts no
per-response erasure: building the handle that would make a precise retry
possible is the same handle that would make a stored answer traceable, and
this feature does not need precision badly enough to buy it at that price.

**What an operator actually does about one bounce**: nothing automated.
The invitation carries no attachment and no cryptographic attestation --
unlike a certificate, a duplicate is a mild inconvenience, not a second
copy of a nominative document loose in the world -- so the deliberate,
supported recovery is `resend_all`, accepting that everyone who already
received it gets a second, identical copy. An operator who happens to know
the one address that bounced (because the room roster or the delivery
error named it to them directly, never because this module printed it) has
no purpose-built command to hand a single message to either; writing to
that person by hand, pasting `survey_url(event_id)`, is the whole
recovery, the same way a volunteer already writes to a participant by hand
for anything this codebase does not automate.

Nothing nominative reaches a job log, on every path (ruling 4)
-------------------------------------------------------------------
Mirrors `delivery.py` and `confirmation.py` exactly, for the identical
reason: `compose` below returns a `confirmation.Confirmation`, and
`cli.py::invite_survey` -- the only caller -- prints counts and event ids
only, never a name, an address, or a rendered message, on the success path
or on any refusal path (survey disabled, already invited, no registrations
on file, a platform that cannot answer). `confirmation.deliver` is reused
unmodified rather than rebuilt: its own `smtplib.SMTPException, OSError`
catch already never inspects or forwards the exception's own text, for the
same `SMTPRecipientsRefused`-echoes-the-address reason both sibling
modules' docstrings already give at length.

Reusing `confirmation.Confirmation` and `confirmation.deliver`, not a
third SMTP transport
------------------------------------------------------------------------
An invitation is `to`, `subject`, `body` -- exactly `Confirmation`'s own
three fields, nothing more (no attachment, unlike `delivery.Delivery`,
which needs a fourth and fifth field for the certificate document and its
filename). Composing a `confirmation.Confirmation` here and handing it to
`confirmation.deliver` reuses the one already-tested, leak-safe transport
this project has, rather than standing up a second copy of the same
`smtplib` wiring `delivery.py` already had to justify duplicating (that
module's own reason -- a signed document must never be written to disk,
even transiently -- does not apply to a plain link, so there is no reason
here to pay that duplication's cost a second time).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote

from . import confirmation
from .registration import Registration

__all__ = [
    "INVITATIONS_FILE_VERSION",
    "INVITATIONS_PATH",
    "NOTICE",
    "SURVEY_BASE",
    "InvitationRegistry",
    "compose",
    "invitations_path",
    "registry_from_data",
    "registry_to_data",
    "survey_url",
]

#: Mirrors `certificate.VERIFICATION_BASE` exactly: a `HashRouter` fragment
#: (`app/src/App.tsx`'s own `path="/survey/:eventId"` route), so the event
#: id sits after `#` and is never sent to a server on load, and so GitHub
#: Pages -- which serves no server-side routing -- never has to answer a
#: bare path. Unlike `verification_url`, there is no token to protect from
#: `Referer` here (ruling 2: this module mints no per-person token at
#: all), so the fragment placement is a consistency choice with the
#: certificate's own address, not a second privacy property this module
#: relies on. `test_survey_invite.py` pins this against `App.tsx`'s own
#: route literal (D-14), the same "read from both sides" discipline
#: `certificate.py`'s own shared fixture uses for its address.
SURVEY_BASE: Final = "https://example-instance.github.io/example-showcase/app/#/survey/"


def survey_url(event_id: str) -> str:
    """The one link every matched attendee of `event_id` receives -- see
    the module docstring's "ruling 2" section for why this is a single,
    person-independent address rather than anything computed from a
    registration."""
    return f"{SURVEY_BASE}{quote(event_id, safe='')}"


#: The one sentence every invitation carries about who receives it -- the
#: "notice" ruling 2 asks for, restated here as a named constant rather
#: than typed inline so `test_survey_invite.py` can pin it against
#: `docs/toolkit/emails/survey-invitation.md`'s own copy, the same
#: discipline `confirmation.MATCHING_INSTRUCTION` already holds itself to.
#: Deliberately silent on anonymity or padding or metadata: see the module
#: docstring's own paragraph on why a second, shorter paraphrase of
#: `SurveyForm.tsx`'s full notice could only say it less precisely.
NOTICE: Final = (
    "This short, optional survey is only sent to people we have recorded "
    "as present at this event."
)


def compose(
    registration: Registration, event_title: str, event_id: str
) -> confirmation.Confirmation:
    """The invitation for one matched attendee. Deterministic in every
    argument, the same property `confirmation.compose` and `delivery.compose`
    both have, for the same reason: replaying it (a batch `resend_all`, or a
    hand-written follow-up) reproduces the identical message rather than one
    that merely carries the same link.

    Returns a plain `confirmation.Confirmation` -- see the module
    docstring's own section on why this module mints no dedicated type or
    transport of its own."""
    subject = "Tell us what you thought"
    if event_title:
        subject = f"{subject} — {event_title}"

    what = f" {event_title}" if event_title else " the event"
    lines = [
        f"Dear {registration.first_name},",
        "",
        f"Thank you for attending{what}. We would like to hear what you thought.",
        "",
        NOTICE,
        "",
        f"Answer the survey here: {survey_url(event_id)}",
        "",
        "It takes about two minutes.",
        "",
        "Best regards,",
        "The Example Collective team",
    ]
    return confirmation.Confirmation(
        to=registration.email, subject=subject, body="\n".join(lines) + "\n"
    )


# ------------------------------------------------------------------ #
# The per-event invitation registry -- see the module docstring's
# "ruling 3" section for why this is the whole bound, and why it is
# keyed on the event, never on a person.
# ------------------------------------------------------------------ #

#: Where the registry lives, relative to a repository root -- mirrors
#: `eventkeys.DESTRUCTIONS_PATH`'s own role for
#: `data/event-key-destructions.yml`: a single file, an event id and a
#: date, nothing that could ever be personal data.
INVITATIONS_PATH: Final = Path("data") / "survey-invitations.yml"

#: `data/survey-invitations.yml`'s own format version -- the file-level
#: analogue of `eventkeys.DESTRUCTIONS_FILE_VERSION`.
INVITATIONS_FILE_VERSION: Final = 1

#: One registry entry's exact field set. See `registry_from_data`.
_INVITATION_FIELDS: Final = frozenset({"event_id", "invited_on"})

#: `event_id -> the day it was first invited`. A plain alias, not a
#: `NewType`: every caller already knows this is the invitation registry
#: from context, the same restraint `eventkeys.py` shows for its own
#: `dict[str, date]`.
InvitationRegistry = dict[str, date]


def invitations_path(root: Path) -> Path:
    """`data/survey-invitations.yml`, relative to `root`. Pure path
    computation -- `cli.py` is still the only module that ever opens the
    path this returns."""
    return root / INVITATIONS_PATH


def registry_from_data(data: Any) -> InvitationRegistry:
    """Parse an already YAML-loaded `data/survey-invitations.yml`, or start
    empty when `data` is `None` -- no event has ever been invited yet, the
    ordinary state before the first dispatch of *Invite the post-event
    survey*.

    Raises `ValueError` on anything committed that is not this exact
    format -- the same "closed shape" discipline
    `eventkeys.registry_from_data` and `registration.load_registration_file`
    already hold themselves to, and for the identical reason: a malformed
    committed file is never a normal state to paper over silently. Also
    refuses a duplicate `event_id`, for the same reason
    `eventkeys.registry_from_data` does: two rows for one event would leave
    idempotence (the day of the *first* invitation) unable to say which
    row is authoritative.
    """
    if data is None:
        return {}
    if not isinstance(data, dict) or data.get("v") != INVITATIONS_FILE_VERSION:
        raise ValueError(
            "data/survey-invitations.yml is not a supported format version"
        )
    raw_entries = data.get("invitations")
    if not isinstance(raw_entries, list):
        raise ValueError("data/survey-invitations.yml is malformed")

    registry: InvitationRegistry = {}
    for raw in raw_entries:
        if not isinstance(raw, dict) or set(raw) != _INVITATION_FIELDS:
            raise ValueError(
                "data/survey-invitations.yml holds an entry that is not "
                "exactly an event id and an invitation date"
            )
        event_id, invited_on_raw = raw["event_id"], raw["invited_on"]
        if not isinstance(event_id, str) or not isinstance(invited_on_raw, str):
            raise ValueError(
                "data/survey-invitations.yml holds a field of the wrong type"
            )
        if event_id in registry:
            raise ValueError(
                "data/survey-invitations.yml holds event id "
                f"{event_id!r} more than once"
            )
        try:
            registry[event_id] = date.fromisoformat(invited_on_raw)
        except ValueError as exc:
            raise ValueError(
                "data/survey-invitations.yml holds an invalid invited_on "
                f"date for event {event_id!r}"
            ) from exc
    return registry


def registry_to_data(registry: Mapping[str, date]) -> dict[str, Any]:
    """The inverse of `registry_from_data`: a plain, YAML-safe structure
    `cli.py` hands to its own YAML writer. Sorted by event id, the same
    diff-friendly ordering `eventkeys.registry_to_data` already uses."""
    return {
        "v": INVITATIONS_FILE_VERSION,
        "invitations": [
            {"event_id": event_id, "invited_on": registry[event_id].isoformat()}
            for event_id in sorted(registry)
        ],
    }
