"""The commands that invite an event's attendees to the post-event survey.

One invitation per event, bounded by a registry that holds an event id and
a date and nothing else -- no name, no address, no count of how many.
`convener_ops.journey.survey_invite` decides whether an event is due; this
sends and records.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from convener_ops.cli import step_output, store
from convener_ops.cli.journey.event import (
    conference_ids_from_env,
    env_flag_is_true,
    load_registrations,
    survey_enabled,
)
from convener_ops.declaration.paths import (
    DATA_DIR,
    repo_root,
)
from convener_ops.declaration.yaml_safe import safe_load as yaml_safe_load
from convener_ops.governance.rule import paris_today
from convener_ops.journey import (
    confirmation,
    eventkeys,
    survey_invite,
)
from convener_ops.journey.attendance import (
    MatchEvent,
    match,
)
from convener_ops.journey.platform import (
    AttendanceImportError,
    EventNotFoundError,
    find_speaker,
)
from convener_ops.journey.platform_fcc import (
    FCCRequestError,
    platform_from_env,
)
from convener_ops.journey.registration import (
    load_registration_file,
)

#: The survey invitation registry holds only an event id and a
#: date -- see tools/convener_ops/journey/survey_invite.py's module docstring for
#: why this is the whole bound a resend is checked against.
SURVEY_INVITATIONS_HEADER = (
    "# Survey invitation registry -- no name, no address; "
    "see tools/convener_ops/journey/survey_invite.py\n"
)


def _load_invitation_registry(
    root: Path,
) -> tuple[survey_invite.InvitationRegistry, str | None]:
    """`(registry, None)` on success, `({}, message)` on a malformed
    committed file -- mirrors `_load_destruction_registry` exactly, for
    the same reason: a *missing* file is not an error (no event has ever
    been invited yet), and never raises, so `invite_survey` can print one
    line and return 1 the same way every other "closed shape" loader in
    this module already does."""
    registry_path = survey_invite.invitations_path(root)
    if not registry_path.exists():
        return {}, None
    try:
        data = yaml_safe_load(registry_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return {}, f"{survey_invite.INVITATIONS_PATH.as_posix()}: invalid YAML - {exc}"
    try:
        return survey_invite.registry_from_data(data), None
    except ValueError as exc:
        return {}, f"{survey_invite.INVITATIONS_PATH.as_posix()}: {exc}"


def invite_survey() -> int:
    """`convener-invite-survey`: e-mail the post-event survey link to every
    currently *matched* attendee of one event -- see
    `survey_invite.py`'s own module docstring for why matched
    and only matched, never a registrant, an unmatched attendee (no
    address to send to) or a telephone joiner (never had one).

    Checked in this order, cheapest and least sensitive first, and every
    refusal prints one line naming only the event id (already public) --
    never a name or an address, on any path, mirroring `issue_certificates`
    and `deliver_certificates`'s own discipline:

    1. the event id is a legal token at all;
    2. **the survey switch is on** (`survey_enabled`): an
       invitation to a closed survey would be a fourth hole in the same
       switch `handle_survey_response`, the signup relay and `SurveyForm.tsx`
       already enforce;
    3. **this event has not already been invited**
       (`instance/data/survey-invitations.yml`), unless `RESEND_ALL=true` -- the
       whole bound a resend has, checked before anything is decrypted so a routine
       re-dispatch after nothing changed touches no registration at all;
    4. the event's private key is configured;
    5. `registrations.enc` exists and parses;
    6. the attendance platform answers.

    Composes and sends through `confirmation.deliver` -- reused, not
    rebuilt, see `survey_invite.py`'s own module docstring for why -- and
    prints only counts: how many matched attendees were invited, how many
    sends failed, and, kept apart rather than folded into one number
    rather than folded into one number, how many this event's own attendance
    export named but never invited for each of the two different reasons
    eligibility distinguishes -- unmatched (an address was seen; no registration tied
    to it, so there is nothing on file to compose an invitation *from*,
    never mind send it to) and unreachable (a telephone joiner; no address
    was ever collected at all). `invite_survey` is the only *reachable*
    command that counts either population at all -- `unmatched-attendance.md`
    (`match-attendance.yml`, above) is the only place a host can act on the
    unmatched half, but nothing here reads that file back, so this line
    was the one place the unmatched/unreachable distinction could still be
    erased even after it was drawn.

    **Writes `record` to `$GITHUB_OUTPUT`** (`true` when at least one
    invitation actually sent this run, `false` otherwise) --
    `invite-survey.yml`'s own follow-up step reads this to decide whether
    `convener-record-survey-invitation` should run at all. Deliberately gated
    on *sent*, not *attempted*: a run that sent nothing (no matched
    attendee, or `email_transport` unconfigured) must not mark this event
    as invited, or a later run -- once the real cause is fixed -- would
    refuse itself outright for an invitation that, in fact, never went
    anywhere.

    **A single in-place retry, needing no identifier at all.**
    A delivery that fails is retried once, immediately,
    inside this same loop, before counting it as unsent -- see
    `survey_invite.py`'s own module docstring
    for why this -- not a per-person resend handle -- is the
    right place to spend effort on a transient failure: it needs nothing
    committed anywhere, so it costs nothing in proportionality or in
    `CONVENER_MATCHING_SALT`'s own ordinary absence, and it means a run of 40
    where message 3 hiccups once no longer has to be re-run wholesale
    (`resend_all`) to reach the other 39 a first attempt already reached.
    """
    event_id = os.environ.get("EVENT_ID", "").strip()
    try:
        eventkeys.secret_name(event_id)
    except ValueError:
        print("no valid event id supplied", file=sys.stderr)
        return 1

    root = repo_root()
    if not survey_enabled(root, event_id):
        print(
            f"the survey is not enabled for event {event_id} -- refusing to "
            "invite anyone",
            file=sys.stderr,
        )
        return 1

    registry, registry_error = _load_invitation_registry(root)
    if registry_error:
        print(registry_error, file=sys.stderr)
        return 1

    resend_all = env_flag_is_true("RESEND_ALL")
    if event_id in registry and not resend_all:
        print(
            f"event {event_id} was already invited on "
            f"{registry[event_id].isoformat()} -- no invitations sent this "
            "run (tick resend_all for a deliberate resend)"
        )
        step_output.write("record=false\n")
        return 0

    private_pem = os.environ.get("EVENT_PRIVATE_KEY", "")
    if not private_pem:
        print(f"no private key configured for event {event_id}", file=sys.stderr)
        return 1

    rel_path = DATA_DIR / "events" / event_id / "registrations.enc"
    enc_path = root / rel_path
    if not enc_path.exists():
        print(f"no registrations recorded for event {event_id}", file=sys.stderr)
        return 1
    try:
        current = load_registration_file(enc_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"{rel_path.as_posix()}: {exc}", file=sys.stderr)
        return 1

    registrations, unreadable_registrations = load_registrations(
        current.entries, private_pem
    )

    speakers, _errors = store.load(root / DATA_DIR / "speakers.yml")
    cfg, _errors = store.load(root / DATA_DIR / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    config_map = cfg if isinstance(cfg, dict) else None

    platform = platform_from_env(
        os.environ,
        speaker_list,
        config_map,
        conference_ids_from_env(event_id),
        private_pem=private_pem,
    )
    try:
        rows = platform.get_attendance(event_id)
    except (AttendanceImportError, FCCRequestError, EventNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    salt = os.environ.get("CONVENER_MATCHING_SALT")
    matched = match(rows, registrations, MatchEvent(event_id=event_id, salt=salt))

    record: Mapping[str, Any] = {}
    with contextlib.suppress(EventNotFoundError):
        record = find_speaker(speaker_list, event_id)
    event_title = str(record.get("title", "") or "")

    sent_count = 0
    unsent_count = 0
    for attendee in matched.matched:
        message = survey_invite.compose(attendee.registration, event_title, event_id)
        result = confirmation.deliver(message, os.environ)
        if not result.sent:
            # One immediate retry, in place --
            # see this function's own docstring and survey_invite.py's
            # module docstring for why this, not a per-person
            # resend handle, is the right answer to a transient failure.
            result = confirmation.deliver(message, os.environ)
        if result.sent:
            sent_count += 1
        else:
            unsent_count += 1

    # Kept apart rather than folded into one
    # "present but not invited" count -- see this function's own docstring
    # for why the two are not the same finding, and why this print line
    # was the one reachable place that still erased the difference.
    print(
        f"survey invitations for event {event_id}: {sent_count} sent, "
        f"{unsent_count} not sent ({len(matched.matched)} matched attendee(s); "
        f"{len(matched.unmatched)} unmatched -- present, but no registration "
        f"found for their address; {len(matched.unreachable)} unreachable -- "
        "joined by phone, no address ever collected; "
        f"{unreadable_registrations} registration(s) could not be read)"
    )
    step_output.write(f"record={'true' if sent_count else 'false'}\n")
    return 0


def record_survey_invitation() -> int:
    """`convener-record-survey-invitation`: the second, retried half of *Invite
    the post-event survey* -- see `invite_survey`'s own docstring for why
    sending and recording are two separate steps.

    Reads `EVENT_ID` and idempotently adds it to
    `instance/data/survey-invitations.yml` with today's Paris date -- `setdefault`,
    never overwritten, so calling this again for an event already on
    record (a git-push retry that re-runs this command after a rejected
    push resets the working tree, or an operator re-dispatching the whole
    workflow by hand) reproduces the identical file rather than moving the
    date forward. Never sends anything and never reads a private key: by
    the time this runs, `invite_survey` has already sent whatever it is
    going to send, and this command's only job is to write the one fact
    that a re-dispatch checks."""
    event_id = os.environ.get("EVENT_ID", "").strip()
    try:
        eventkeys.secret_name(event_id)
    except ValueError:
        print("no valid event id supplied", file=sys.stderr)
        return 1

    root = repo_root()
    registry, registry_error = _load_invitation_registry(root)
    if registry_error:
        print(registry_error, file=sys.stderr)
        return 1

    today = paris_today(datetime.now(UTC))
    registry.setdefault(event_id, today)

    registry_path = survey_invite.invitations_path(root)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        SURVEY_INVITATIONS_HEADER
        + store.dump(survey_invite.registry_to_data(registry)),
        encoding="utf-8",
        newline="",
    )
    print(f"recorded a survey invitation for event {event_id}")
    return 0
