"""What a command reads about the one event it was given.

The registrations it can actually decrypt, the platform identifiers the
workflow passed it, and whether that event's survey is switched on. Four
commands used to carry their own copy of the registration loop and each
silently dropped what it could not read; this is the one place it is
written, and the count of what failed comes back with it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from convener_ops.cli import store
from convener_ops.declaration.paths import (
    DATA_DIR,
)
from convener_ops.journey.platform import (
    EventNotFoundError,
    find_speaker,
)
from convener_ops.journey.registration import (
    Registration,
    to_registration,
)


def survey_enabled(root: Path, event_id: str) -> bool:
    """Whether `event_id`'s speaker record has the survey switch on --
    the switch is a field on the speaker record, a
    per-event fact beside the event's other per-event facts, not a
    `instance/data/config.yml` setting. `False` for every failure to determine it
    cleanly: a speaker file that will not load, no record for this event
    id, or `False` on the record itself all mean the same thing here --
    this event's survey is not open -- because a job that decrypts and
    stores an answer nobody asked for is the one outcome this check exists
    to prevent, and there is no direction it is safer to guess wrong in
    than "closed".
    """
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    if errors or not isinstance(speakers, list):
        return False
    try:
        record = find_speaker(speakers, event_id)
    except EventNotFoundError:
        return False
    return bool(record.get("survey_enabled") is True)


def load_registrations(
    entries: Sequence[Mapping[str, Any]], private_pem: str
) -> tuple[list[Registration], int]:
    """Every registration `private_pem` can actually read out of `entries`
    (`current.entries`, from a loaded `registrations.enc`), and how many
    could not be -- carried item 10: `match_attendance`, `issue_certificates`,
    `deliver_certificates` and `invite_survey` each carried their own copy
    of this loop, and each silently dropped an entry that failed to decrypt
    or did not parse as `to_registration` expects, reporting a count that
    never mentioned it. "Four divergent fixes would be worse than the
    defect" -- so this is the one place the loop is written, and the one
    place its silence was fixed.

    Not the same shape as `platform.decrypt_attendance_rows`'s own guard:
    that one refuses outright when *every* row in a non-empty file fails --
    the wrong-file case. This is the *partial* case that guard deliberately left
    open ("some rows failing is a damaged file -- tolerable"): one
    undecryptable entry among many good ones is not refused here either,
    for the same reason -- it would let one damaged entry take down a
    whole event's registrations, matching, and certification. What was
    missing was never the tolerance, only the honesty: the second element
    of the return value is that count, and every caller now reports it
    rather than letting it vanish into "0 matched" with no explanation.
    """
    registrations: list[Registration] = []
    unreadable = 0
    for entry in entries:
        registration = to_registration(json.dumps(entry), private_pem)
        if registration is not None:
            registrations.append(registration)
        else:
            unreadable += 1
    return registrations, unreadable


def conference_ids_from_env(event_id: str) -> dict[str, str]:
    """`conference_ids` for `platform_from_env`, folded from
    `CONVENER_FCC_CONFERENCE_ID` exactly the way `release_recording` already
    does: `issue_certificates` and
    `reissue_certificate` both need the identical resolution, so it is
    factored out here rather than retyped a third and fourth time.

    Neither `issue_certificates` nor `reissue_certificate` used to
    pass any `conference_ids` at all, so `PlatformFCC._conference_id`
    always raised `EventNotFoundError` the moment the FCC path was in play
    -- uncaught until `EventNotFoundError` joined
    both functions' own `except` tuples. An event with no FCC conference
    configured is the ordinary D-13 shape either way: this returns `{}`,
    the same "nothing to resolve" `release_recording` and
    `discard_recording` already treat identically.

    `release_recording` and `discard_recording`
    keep their own inline versions rather than being rewritten to call
    this -- deliberately left alone."""
    conference_id = os.environ.get("CONVENER_FCC_CONFERENCE_ID", "").strip()
    return {event_id: conference_id} if conference_id else {}


def env_flag_is_true(name: str) -> bool:
    """This project's own convention for a boolean `workflow_dispatch`
    input, named here rather than nowhere:
    the literal string `"true"`, matched case-insensitively after
    stripping surrounding whitespace -- never `bool(os.environ.get(...))`
    (a non-empty `"false"` string is still truthy in Python) and never a
    bare `== "true"` (a boolean `workflow_dispatch` input renders as the
    exact lowercase literal `"true"`/`"false"` today, but this project's
    own convention reads it case-insensitively anyway, the same way an
    operator typing a raw `gh workflow run -f resend_all=True` expects to
    work). `RESEND_ALL` was matched this way at two call sites
    (`invite_survey`, `deliver_certificates`) with the comparison
    retyped, identically, at each -- a third call site retyping it a
    third time, slightly differently, is exactly the drift this function
    exists to close off. `test_invite_survey_resend_all_only_recognises_
    the_literal_true` pins every value a `workflow_dispatch` boolean input
    or a raw API dispatch could actually send."""
    return os.environ.get(name, "").strip().lower() == "true"
