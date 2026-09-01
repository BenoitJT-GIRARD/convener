"""The commands that join an attendance export to the registrations, and
the two that end a recording's life.

The export is encrypted before it is committed, matched against the
event's own registrations by `convener_ops.journey.attendance`'s cascade,
and reported without ever printing an address. `release_recording` and
`discard_recording` are the only two call sites of
`Platform.delete_recording` anywhere in this package, and
`tools/tests/cli/test_cli.py` refuses a third.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import Any, Final

from convener_ops.cli import store
from convener_ops.cli.journey.event import (
    conference_ids_from_env,
    load_registrations,
)
from convener_ops.declaration.paths import (
    DATA_DIR,
    repo_root,
)
from convener_ops.journey import (
    eventkeys,
)
from convener_ops.journey.attendance import (
    MatchEvent,
    match,
)
from convener_ops.journey.platform import (
    AttendanceImportError,
    EventNotFoundError,
    encrypt_attendance_rows,
    find_speaker,
    parse_attendance_csv,
)
from convener_ops.journey.platform_fcc import (
    FCCRequestError,
    PlatformFCC,
    converted_recording_is_reachable,
    missing_retrieval_evidence,
    platform_from_env,
)
from convener_ops.journey.registration import (
    load_registration_file,
    matching_code,
)

#: Where the host's short list of attendance to resolve by hand lands.
#: Written only when there is something to report; unlinked otherwise, so
#: a stale file from an earlier run of this same job workspace is never
#: mistaken for this run's answer. `.gitignore`d: never committed.
#:
#: This file used to carry
#: display names and addresses in the clear -- a 14-day build artefact
#: readable by anyone with repository read access, a wider set than those
#: holding the event's own decryption key, and entirely outside the
#: encryption/erasure/key-destruction lifecycle every other piece of
#: personal data in this project is held to. The `.gitignore`
#: comment that used to guard it said "never printed" -- true, but that
#: never covered "never uploaded", which is the surface that actually
#: leaked. `match_attendance` below no longer writes a name or an address
#: here at all: an unmatched connection is named by a record identifier
#: (`registration.matching_code`, salted, the same shape a registrant's
#: own confirmation code already uses) when `CONVENER_MATCHING_SALT` is
#: configured, or by its position in this run's own list otherwise --
#: D-24, applied to a report the same way it already applies to an
#: operator command. An unreachable connection (never host-resolvable
#: regardless -- see `attendance.py`'s own "boundary, not weakness"
#: framing) collapses to one count-and-duration summary line, naming
#: nobody. This file is still uploaded as a short-retention, access-
#: controlled build artefact (defence in depth), but its own safety no
#: longer depends on that restriction.
UNMATCHED_ATTENDANCE: Final = "unmatched-attendance.md"


def encrypt_attendance_export() -> int:
    """`convener-encrypt-attendance-export`: turn a host's raw, never-committed
    `instance/data/events/<id>/attendance-import.csv` into a committable,
    encrypted `instance/data/events/<id>/attendance-import.csv.enc` -- see
    `platform.py`'s module docstring, "one independent envelope per row",
    for the file's own per-row shape.

    Runs entirely outside continuous integration, on a host's own
    machine, against the plaintext export they just downloaded off the
    meeting platform -- the manual implementation's whole point. Needs no
    secret at all: `instance/keys/events/<id>.pub` is already published, public
    data (`eventkeys.py`'s own module docstring, "the public half is a
    file, not a secret"), and encrypting under a public key is exactly
    the operation a stranger with no account could already perform.
    `EVENT_PRIVATE_KEY` never enters this function, and must not: the
    matching private half stays exactly where it belongs, in a
    CI job's own environment, never on the machine this command runs on.

    Reads `EVENT_ID` -- the same operator-typed, manual-trigger shape
    `resend_confirmation` and `match_attendance` already read -- and the
    plaintext CSV at `instance/data/events/<id>/attendance-import.csv`. Refuses
    (exit 1) when the event id is not shaped like one, when no public key
    has been published for it yet (`instance/keys/events/<id>.pub` absent -- an
    operator has to create the event's key pair, per
    `docs/operating/operations.md`'s "Event registration keys" section,
    before anyone can register for it at all, so this is never the first
    command run against a fresh event), when there is no plaintext export
    to encrypt at the expected path, or when the CSV itself is malformed
    (a missing or duplicated required column -- `parse_attendance_csv`'s
    own whole-file failures, surfaced here on the host's own screen
    rather than reaching a CI job log at all, which is the strongest
    answer to that finding there is).

    Parses the plaintext locally and prints one line per malformed row,
    the same as `ManualPlatform.get_attendance` already does for the
    never-encrypted path -- a host sees exactly what would be dropped
    before anything is committed, not after. Writes the encrypted file --
    one independent envelope per valid row, two-space indent, one
    trailing newline, the same shape `registrations.enc` already uses --
    and prints where it landed and what to do next: commit it, then run
    `convener-match-attendance` (or `convener-issue-certificates`, which re-derives
    the same join internally) from a CI job holding this event's private
    key. Never reads, prints, or otherwise touches any row's own fields
    beyond the malformed-row count above -- see
    `platform.encrypt_attendance_rows` for the real work this function
    wraps.
    """
    event_id = os.environ.get("EVENT_ID", "").strip()
    try:
        eventkeys.secret_name(event_id)
    except ValueError:
        print("no valid event id supplied", file=sys.stderr)
        return 1

    root = repo_root()
    public_path = eventkeys.public_key_path(event_id)
    if not public_path.exists():
        print(f"no public key published for event {event_id}", file=sys.stderr)
        return 1

    plain_path = root / DATA_DIR / "events" / event_id / "attendance-import.csv"
    if not plain_path.exists():
        relative = DATA_DIR / "events" / event_id / "attendance-import.csv"
        print(
            f"no attendance export to encrypt for event {event_id}: expected "
            f"{relative.as_posix()}",
            file=sys.stderr,
        )
        return 1

    #: Not "utf-8" -- the same BOM tolerance `ManualPlatform.get_attendance`
    #: already gives the never-encrypted path; a host's own export tool is
    #: exactly as likely to write one here.
    plain_text = plain_path.read_text(encoding="utf-8-sig")
    try:
        rows, issues = parse_attendance_csv(plain_text)
    except AttendanceImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for parse_issue in issues:
        print(
            f"attendance-import.csv line {parse_issue.line_number}: "
            f"{parse_issue.reason}"
        )

    public_pem = public_path.read_text(encoding="utf-8")
    envelope_file = encrypt_attendance_rows(public_pem, rows)

    enc_path = plain_path.parent / f"{plain_path.name}.enc"
    rel_enc = DATA_DIR / "events" / event_id / enc_path.name
    # This has no date or content to compare against
    # -- it always encrypts whatever the local plaintext currently says --
    # so a stray or stale local export would otherwise replace a good
    # committed file with a worse one and the only signal would be an
    # unreadable blob's own git diff. Naming that this is a replacement,
    # not a first write, costs one line and is the whole fix.
    if enc_path.exists():
        print(f"replacing the already-committed {rel_enc.as_posix()}")
    enc_path.write_text(envelope_file, encoding="utf-8", newline="")
    print(
        f"encrypted attendance export written to {rel_enc.as_posix()} "
        f"({len(rows)} row(s)) -- commit it, then run convener-match-attendance "
        "or convener-issue-certificates from a job holding this event's private key"
    )
    return 0


def _salted_record_id(event_id: str, email: str, salt: str) -> str:
    """`registration.matching_code`, guaranteed non-`None` here: `salt` is
    checked truthy by every caller before this is reached, and
    `matching_code` only ever returns `None` for a falsy salt. Raised
    explicitly rather than asserted -- an `assert` is stripped under
    `python -O`, and D-25 requires this failure mode to survive that --
    rather than silently falling back to the address it would otherwise
    have to print instead, the one leak this is meant to rule out."""
    record_id = matching_code(event_id, email, salt)
    if record_id is None:
        raise RuntimeError(
            "matching_code returned None for a truthy salt -- refusing "
            "to fall back to the address this function exists to keep "
            "out of the report"
        )
    return record_id


def match_attendance() -> int:
    """`convener-match-attendance`: read the platform's attendance export for
    one event, join it against that event's stored registrations through
    `attendance.match`'s cascade, and report the result.

    Reads `EVENT_ID` -- an operator-typed value, the same manual-trigger
    shape `resend_confirmation` already reads, since the platform's
    attendance export only exists once the session is over, on nobody's
    automatic schedule -- and `EVENT_PRIVATE_KEY`, the same per-event
    secret every other step in this file that touches
    `registrations.enc` reads. Every existing entry is decrypted once, in
    memory, into `Registration` objects via `load_registrations`; an
    entry that fails to decrypt under this key is skipped rather than
    treated as a match, the same tolerance `find_by_email` and `upsert`
    already give a stray undecryptable entry -- but no longer silently:
    carried item 10, this fix wave, made every one of the four commands
    that share this loop report how many entries it skipped, rather than
    a count that never mentioned them.

    `attendance.py` is pure and never prints; this function is the only
    place its answer is turned into output, and it draws the same line
    this project draws for a decrypted registration: only counts -- how many
    matched, unmatched and unreachable, and how many rows were read --
    ever reach stdout, never a name or an address. The host's actual short
    list goes to `UNMATCHED_ATTENDANCE` instead, never printed and never
    committed (see its own comment above).

    **`UNMATCHED_ATTENDANCE` itself no longer carries a
    name or an address either.** An unmatched connection is named by its
    own salted record identifier (`_salted_record_id`, the identical
    `matching_code` shape a registrant's own confirmation code already
    uses) when `CONVENER_MATCHING_SALT` is configured, or by its position in
    this run's own list when it is not -- D-24 applied to a report the
    same way it already applies to every operator command. A tie the
    cascade refused to guess between is still named, by each tied
    candidate's own record identifier, never its address. An unreachable
    connection collapses to one count-and-duration line: `attendance.py`'s
    own module docstring already calls this outcome "not a host-resolvable
    case", so there was never a name for a host to act on there in the
    first place.

    **`CONVENER_MATCHING_SALT` and `CONVENER_FCC_CONFERENCE_ID`:**
    the same optional matching-salt and per-event conference id
    `issue_certificates` and `invite_survey` already read, via the
    identical `conference_ids_from_env` resolution -- match-attendance.yml
    gives this command the same `EVENT_ID`/`conference_id` input shape
    those two workflows already use, rather than a shape of its own.
    """
    event_id = os.environ.get("EVENT_ID", "").strip()
    try:
        eventkeys.secret_name(event_id)
    except ValueError:
        print("no valid event id supplied", file=sys.stderr)
        return 1

    private_pem = os.environ.get("EVENT_PRIVATE_KEY", "")
    if not private_pem:
        print(f"no private key configured for event {event_id}", file=sys.stderr)
        return 1

    root = repo_root()
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
        # This has a workflow of its own
        # (match-attendance.yml), with the same `conference_id` input
        # `issue_certificates` and `invite_survey` already take -- so the
        # resolution those two already share is shared here too, rather
        # than leaving this the one caller still missing it.
        conference_ids_from_env(event_id),
        private_pem=private_pem,
    )

    try:
        rows = platform.get_attendance(event_id)
    except (AttendanceImportError, FCCRequestError, EventNotFoundError) as exc:
        # Both are "the platform did not answer", from this caller's own
        # point of view -- the manual path's missing-file/malformed-header
        # failure, or the chosen platform's own network/API failure
        # (`platform_fcc.py`'s own docstring: named generically for
        # exactly this, so a caller does not have to know which
        # implementation it is holding to handle "no data" uniformly).
        # Catching only the first would leave a real API outage as an
        # uncaught traceback instead of the same clean one-line failure
        # every other error path in this function already gives.
        # `EventNotFoundError` is in the tuple
        # for the FCC path raising it whenever conference_ids resolves
        # nothing for event_id -- still reachable even now that
        # conference_ids is populated: an operator can still leave
        # `conference_id` blank.
        print(str(exc), file=sys.stderr)
        return 1

    salt = os.environ.get("CONVENER_MATCHING_SALT")
    result = match(rows, registrations, MatchEvent(event_id=event_id, salt=salt))

    print(
        f"attendance for event {event_id}: {len(result.matched)} matched, "
        f"{len(result.unmatched)} unmatched, {len(result.unreachable)} "
        f"unreachable ({len(rows)} row(s) read; {unreadable_registrations} "
        "registration(s) could not be read)"
    )

    unmatched_path = root / UNMATCHED_ATTENDANCE
    if result.unmatched or result.unreachable:
        lines = [f"# Attendance to resolve -- event {event_id}"]
        if result.unmatched:
            lines.append("")
            lines.append("## Unmatched -- the host can resolve these by hand")
            for index, unmatched in enumerate(result.unmatched, start=1):
                minutes = unmatched.duration_seconds // 60
                # Named by record, never by person (D-24).
                # `unmatched.email` and `.display_name` are the platform's
                # own observed values for this connection -- never printed
                # here. `_salted_record_id` needs the same salt every
                # registrant's own matching code already needs; with none
                # configured, this run's own position is the only stable
                # handle left, and that is said plainly rather than left
                # to look like a missing feature.
                if salt:
                    record_id = _salted_record_id(event_id, unmatched.email, salt)
                    label = f"record {record_id}"
                else:
                    label = (
                        f"connection {index} (no record identifier -- "
                        "CONVENER_MATCHING_SALT not configured)"
                    )
                line = f"- {label} -- {minutes} min"
                if unmatched.tied_with:
                    # A tie the cascade refused to guess between -- the
                    # rule against anyone being credited with somebody
                    # else's attendance --
                    # named here rather than left as a bare "unmatched",
                    # since the host is resolving a specific ambiguity, not
                    # starting from nothing. See attendance.py's own
                    # "Ties are never resolved by guessing" section. Each
                    # tied candidate is a real registrant, so it is named
                    # by its own record identifier too, never its address.
                    if salt:
                        tied_ids = [
                            _salted_record_id(event_id, address, salt)
                            for address in unmatched.tied_with
                        ]
                        line += f" -- ties: {', '.join(tied_ids)}"
                    else:
                        line += (
                            f" -- {len(unmatched.tied_with)} registrant(s) "
                            "tied (no record identifier -- "
                            "CONVENER_MATCHING_SALT not configured)"
                        )
                lines.append(line)
        if result.unreachable:
            # `attendance.py`'s own module docstring already
            # calls this outcome "not a host-resolvable case" -- no cascade
            # level past the code could ever reach a telephone joiner, so a
            # per-row name here was never actionable, only a name. One
            # count-and-duration summary line says everything a host can
            # act on: nobody, and how much total time.
            lines.append("")
            lines.append("## Unreachable -- no address on file, not resolvable by hand")
            unreachable_minutes = (
                sum(entry.duration_seconds for entry in result.unreachable) // 60
            )
            lines.append(
                f"- {len(result.unreachable)} connection(s), "
                f"{unreachable_minutes} min total"
            )
        # One explicit trailing newline, appended once, here -- not left to
        # depend on a section happening to end its own list with a blank
        # entry, which is the same "content plus one trailing newline"
        # idiom `dump_registration_file` already uses for a committed file.
        unmatched_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
        print(
            f"{len(result.unmatched)} unmatched and {len(result.unreachable)} "
            f"unreachable attendee(s) written to {UNMATCHED_ATTENDANCE} for the "
            "host to review"
        )
    else:
        unmatched_path.unlink(missing_ok=True)

    return 0


def _consent_granted(record: Mapping[str, Any]) -> bool:
    """Whether this event's speaker explicitly agreed to publication --
    read directly, not through `public_data.recording_withheld`, because
    that function answers a different question and wiring it in
    here was wrong, caught on review. `recording_withheld` has
    no reusable, decomposed "consent alone" reader -- it is built on the
    private `_gate_closed`, which combines consent with the board's own
    archive gate and is not exported -- so this reads the field directly
    rather than restating `recording_withheld`'s comparison inside a
    second copy of it.

    Keeps `recording_withheld`'s own documented asymmetry, because it
    applies here too: **"not did they refuse but did they agree"**
    (`public_data.py::recording_withheld`'s docstring). `pending`, `""`, a
    missing or malformed `publication` block, and any value this project
    does not recognise are all silence, and silence is never a
    permission -- so a not-yet-answered consent must not release a
    recording, the same as a refused one."""
    publication = record.get("publication")
    if not isinstance(publication, dict):
        return False
    return publication.get("consent") == "granted"


def release_recording() -> int:
    """`convener-release-recording`: retrieve, verify the retrieval, then
    delete -- one of exactly two places in this whole package allowed to
    call `Platform.delete_recording`, the other being `discard_recording`
    below (pinned by
    `tools/tests/cli/test_cli.py::test_delete_recording_has_exactly_two_call_sites_both_in_cli`).
    `delete_recording` exists because of the chosen platform's
    storage quota: a 90-minute recording costs roughly
    1.6x the free tier's entire 1 GB allowance, so freeing it after every
    event is a condition of operation, not an optimisation, and getting
    the order wrong loses a recording forever.

    The two-trace shape this enforces is a settled design ruling about
    who deletes the recording and on what evidence;
    `platform_fcc.py`'s module docstring carries it in full, and this
    function's job is turning it into a real, tested call order.

    The order is not negotiable, and it is not a comment above a function
    call -- it is the only order this function's own control flow can
    produce: `platform.get_recording` is called, then
    `missing_retrieval_evidence` is checked and must come back empty, and
    only then is `platform.delete_recording` reached. Every early return
    above that call -- a bad or unknown event id, a malformed conference
    id, a data file that will not load, no meeting-platform account
    configured, nothing currently recorded, or evidence still missing --
    exits before it, never after.

    "Verified" means two independent, host-driven traces
    (`missing_retrieval_evidence`'s own docstring gives the full
    reasoning): the `RETRIEVED_TICK` step on the event's own
    `runbook_progress`, and a successful `HEAD` confirming the provider's
    own converted copy is reachable, checked against `video/mp4` and
    `Accept-Ranges: bytes`, not merely a 2xx status. **Not `youtube_url`**
    -- an earlier version of this function used it, and review found that
    wrong: `youtube_url` is a publication signal (`app/src/state/phases.ts`'s
    own `delivered/youtube-url` item, gated separately from
    `publication.outcome`), so a recording that is legitimately never
    published would never have satisfied it despite being genuinely
    retrieved, and the quota it occupies would never have been freed.

    **This function is only for a recording headed to YouTube, and it now
    enforces that rather than only documenting it.**
    A recording that must never become public -- the
    discussion segment (recorded on purpose, under the hosting runbook's
    three-step discipline, but never published), or a talk whose publication consent
    was withheld -- must never take this path: trace 2 can only be
    satisfied by converting to MP4, and a converted file stays *publicly
    reachable at its own URL even after the conference is deleted*
    (verified empirically). Proving retrieval this way is exactly the
    exposure those two cases exist to prevent. So before either trace is
    even checked, this function refuses unless `_consent_granted` reads
    `publication.consent == "granted"` on the event's own speaker record.

    **Consent alone, not `public_data.recording_withheld`.** That
    function was wired in here once and it was wrong, caught on review:
    `recording_withheld` answers a *different* question -- "must this
    recording stay out of the public feed" -- and requires the board's
    own archive gate too (`publication.outcome == "published"`, written
    only by `finalize-archive`, which runs on its own, later timeline:
    board approval, then an objection window). Freeing the platform's
    quota is not publishing. The question this function actually needs
    answered is only whether *converting* the recording was legitimate,
    and converting is legitimate exactly when the speaker agreed to
    publication -- nothing about whether the board has since finished
    approving it for the public feed. Gating on the full publication gate
    would hold the quota hostage to a board timeline the quota has no
    relationship with, recreating the exact "refuses forever, quota fills"
    failure this command exists to prevent, for every fresh talk, every
    time. `discard_recording` below is the other route: no proof of
    retrieval is asked for or accepted, because none may ever exist. See
    its own docstring, and `platform_fcc.py`'s module docstring's "Which
    recordings take which route" section, for the full split. This
    function never downloads the recording itself, and calls nothing that
    could trigger a conversion on its own -- only the host's Download
    click does that, and only a consented recording headed for YouTube
    should ever receive one.

    The quota is checked *after* deletion, deliberately -- an alarm if
    the space stays occupied -- because a saturated quota breaks
    the *next* session's recording -- discovered on the far side of a
    month otherwise. `platform.get_recording` is called a second time
    once `delete_recording` returns; if it still reports the recording
    `available`, this prints a `::error::`-prefixed line (surfaced by
    GitHub Actions in the run's own summary, not merely a stray line in a
    log nobody reads) and returns 1 -- a signal, not silence.

    `CONVENER_FCC_CONFERENCE_ID` is `platform_fcc.py`'s open seam
    (`conference_ids`, "the one thing this module does not attempt" to
    resolve on its own) filled in the simplest available way: typed once,
    by the human running `.github/workflows/recording.yml`'s
    `workflow_dispatch`, for the one event that run is about -- never a
    persisted mapping, never resolved from an unverified listing
    endpoint, and never scheduled or unattended for that same reason
    (`platform_fcc.py`'s module docstring says so plainly, as does
    `docs/operating/operations.md`). `PlatformFCC._conference_id` validates
    its shape (digits only) before it can reach a URL; a malformed value
    surfaces here as a plain `ValueError`, caught the same way as every
    other "the platform did not answer" case in this function.
    """
    event_id = os.environ.get("EVENT_ID", "").strip()
    try:
        eventkeys.secret_name(event_id)
    except ValueError:
        print("no valid event id supplied", file=sys.stderr)
        return 1

    root = repo_root()
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    cfg, cfg_errors = store.load(root / DATA_DIR / "config.yml")
    if errors or cfg_errors:
        for error in errors + cfg_errors:
            print(f"  - {error}")
        return 1
    speaker_list = speakers if isinstance(speakers, list) else []
    config_map = cfg if isinstance(cfg, dict) else None

    try:
        record = find_speaker(speaker_list, event_id)
    except EventNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    runbook_progress = record.get("runbook_progress")
    if not isinstance(runbook_progress, dict):
        runbook_progress = {}

    # Enforced, not only documented: the
    # question here is only whether converting the recording was
    # legitimate, which turns on consent alone -- not
    # `public_data.recording_withheld`, which also waits on the board's
    # own archive gate and would hold this quota hostage to that timeline.
    # See `_consent_granted`'s own docstring, and this function's own
    # docstring's "Consent alone" section, for the full reasoning.
    if not _consent_granted(record):
        print(
            f"publication consent is not granted for event {event_id} "
            "(publication.consent must be 'granted') -- release_recording "
            "refuses; if this recording is never going to be published, "
            "use discard_recording instead",
            file=sys.stderr,
        )
        return 1

    conference_id = os.environ.get("CONVENER_FCC_CONFERENCE_ID", "").strip()
    conference_ids = {event_id: conference_id} if conference_id else {}
    platform = platform_from_env(os.environ, speaker_list, config_map, conference_ids)

    if not isinstance(platform, PlatformFCC):
        # D-13: no account configured is the ordinary state. The manual
        # implementation holds no recording storage of its own
        # (`ManualPlatform.delete_recording`'s own docstring), so there is
        # nothing here to retrieve, verify or free.
        print(
            f"no meeting-platform account is configured for event {event_id} "
            "-- the manual implementation holds no recording storage of "
            "its own, so there is nothing to release"
        )
        return 0

    try:
        recording = platform.get_recording(event_id)
    except (EventNotFoundError, FCCRequestError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not recording.available:
        print(
            f"no recording is currently held for event {event_id} -- nothing to release"
        )
        return 0

    problems = missing_retrieval_evidence(platform, recording, runbook_progress)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(
            f"recording for event {event_id} was NOT deleted -- retrieval "
            "is not yet confirmed",
            file=sys.stderr,
        )
        return 1

    try:
        platform.delete_recording(event_id)
    except (EventNotFoundError, FCCRequestError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        after = platform.get_recording(event_id)
    except (EventNotFoundError, FCCRequestError, ValueError) as exc:
        print(
            f"recording for event {event_id} was deleted, but the freed "
            f"space could not be confirmed: {exc}",
            file=sys.stderr,
        )
        return 1

    if after.available:
        print(
            f"::error::space for event {event_id} is still occupied after "
            "deletion -- the next session's recording may fail",
            file=sys.stderr,
        )
        return 1

    print(
        f"recording for event {event_id} retrieved, verified, and released "
        f"({recording.size} bytes freed)"
    )
    return 0


def _discard_confirmation(event_id: str) -> str:
    """The exact text `CONFIRM_DISCARD` must equal for `discard_recording`
    to proceed. A single deliberate sentence rather than a boolean flag or
    a repeated id alone -- "discard mrg-042" names both the irreversible
    action and its target in one typed phrase, the same "type the name to
    confirm" idea a repository-deletion UI uses, adapted so the text
    itself states intent rather than only identity."""
    return f"discard {event_id}"


def discard_recording() -> int:
    """`convener-discard-recording`: delete a recording that is never meant to
    be retrieved -- one of exactly two places in this whole package
    allowed to call `Platform.delete_recording`, the other being
    `release_recording` above (pinned by
    `tools/tests/cli/test_cli.py::test_delete_recording_has_exactly_two_call_sites_both_in_cli`).

    **This is not `release_recording` with a shortcut.** The two
    operations have opposite preconditions on purpose, and neither can
    reach the other's call to `delete_recording`: `release_recording`
    requires proof the recording *was* retrieved; this function requires
    proof the operator is *choosing not to retrieve it at all*, because
    for the two cases it exists for -- the discussion segment (recorded
    on purpose, under the hosting runbook's discipline, never published) and a talk
    whose publication consent was withheld -- no such proof may ever be
    manufactured. Converting to MP4 is the only way `release_recording`'s
    trace 2 can be satisfied, and a converted file stays publicly
    reachable at its own URL forever, even after the conference is
    deleted (verified empirically) -- exactly what must never happen to
    either case this function exists for. See `platform_fcc.py`'s module
    docstring's "Which recordings take which route" section for where
    this split is decided, not merely implemented.

    **The guard is an explicit, typed operator affirmation, never the
    retrieval traces.** `missing_retrieval_evidence`, `RETRIEVED_TICK` and
    `runbook_progress` are not read anywhere in this function -- not
    checked, not accepted as a substitute, not consulted at all, so a
    ticked `RETRIEVED_TICK` can never make this function decide there is
    nothing to affirm. What it asks for instead: `CONFIRM_DISCARD` must
    equal `_discard_confirmation(event_id)` exactly -- "discard
    mrg-042", say, typed by hand into
    `.github/workflows/discard-recording.yml`'s `workflow_dispatch` form,
    the same "type the name to confirm" discipline a repository-deletion
    UI uses for its own irreversible action. A blank, a mismatch, or a
    copy-paste of the wrong event's confirmation all refuse, before this
    function touches the platform at all.

    If the provider's converted video already answers (checked the same
    way `release_recording` does, `converted_recording_is_reachable`),
    this prints a `::warning::` -- not a refusal: whatever exposure
    already happened cannot be undone by declining to delete, and leaving
    the recording in place afterwards would only leave the quota occupied
    too. Discarding still proceeds, because freeing the quota is still
    the right next action regardless of an earlier mistake; a human still
    needs to see that mistake named, which the warning is for.

    The quota is checked *after* deletion, the same way and for the same
    reason `release_recording` does -- a saturated quota
    breaks the *next* session's recording.
    """
    event_id = os.environ.get("EVENT_ID", "").strip()
    try:
        eventkeys.secret_name(event_id)
    except ValueError:
        print("no valid event id supplied", file=sys.stderr)
        return 1

    confirm_discard = os.environ.get("CONFIRM_DISCARD", "").strip()
    expected = _discard_confirmation(event_id)
    if confirm_discard != expected:
        print(
            f'CONFIRM_DISCARD must be exactly "{expected}" -- nothing was discarded',
            file=sys.stderr,
        )
        return 1

    root = repo_root()
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    cfg, cfg_errors = store.load(root / DATA_DIR / "config.yml")
    if errors or cfg_errors:
        for error in errors + cfg_errors:
            print(f"  - {error}")
        return 1
    speaker_list = speakers if isinstance(speakers, list) else []
    config_map = cfg if isinstance(cfg, dict) else None

    try:
        find_speaker(speaker_list, event_id)
    except EventNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    conference_id = os.environ.get("CONVENER_FCC_CONFERENCE_ID", "").strip()
    # An `if`/`else` statement, not the `{...} if c else {}` conditional
    # expression `release_recording` uses for the identical resolution:
    # review found that shape invisible to `coverage --branch` (a single
    # line, so both outcomes execute on it), and asked that no second one
    # of the same shape be added rather than that the first be changed.
    # `noqa: SIM108` -- ruff's own suggestion is exactly the shape being
    # deliberately avoided here.
    if conference_id:  # noqa: SIM108
        conference_ids = {event_id: conference_id}
    else:
        conference_ids = {}
    platform = platform_from_env(os.environ, speaker_list, config_map, conference_ids)

    if not isinstance(platform, PlatformFCC):
        print(
            f"no meeting-platform account is configured for event {event_id} "
            "-- the manual implementation holds no recording storage of "
            "its own, so there is nothing to discard"
        )
        return 0

    try:
        recording = platform.get_recording(event_id)
    except (EventNotFoundError, FCCRequestError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not recording.available:
        print(
            f"no recording is currently held for event {event_id} -- nothing to discard"
        )
        return 0

    if converted_recording_is_reachable(recording, platform.transport):
        print(
            f"::warning::the converted recording for event {event_id} is "
            "already reachable at the provider -- if it was never meant "
            "to be converted, it may already be publicly exposed, which "
            "discarding it now cannot undo; freeing the quota anyway",
            file=sys.stderr,
        )

    try:
        platform.delete_recording(event_id)
    except (EventNotFoundError, FCCRequestError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        after = platform.get_recording(event_id)
    except (EventNotFoundError, FCCRequestError, ValueError) as exc:
        print(
            f"recording for event {event_id} was discarded, but the freed "
            f"space could not be confirmed: {exc}",
            file=sys.stderr,
        )
        return 1

    if after.available:
        print(
            f"::error::space for event {event_id} is still occupied after "
            "discarding -- the next session's recording may fail",
            file=sys.stderr,
        )
        return 1

    print(
        f"recording for event {event_id} discarded, never retrieved "
        f"({recording.size} bytes freed)"
    )
    return 0
