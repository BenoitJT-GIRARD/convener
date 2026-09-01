"""The commands that issue, re-issue, revoke and deliver a certificate.

`convener_ops.journey.certificate` decides what a certificate says and
`convener_ops.journey.signing` signs it; this opens the register, resolves
the attendee, and mails the document. `certificates.yml` is opened here
and nowhere else, which is what keeps the one file that survives the
retention sweep free of a name and an address.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from convener_ops.cli import step_output, store
from convener_ops.cli.journey.event import (
    conference_ids_from_env,
    env_flag_is_true,
    load_registrations,
)
from convener_ops.declaration.paths import (
    DATA_DIR,
    PUBLIC_DATA_DIR,
    repo_root,
)
from convener_ops.declaration.yaml_safe import safe_load as yaml_safe_load
from convener_ops.governance.rule import paris_today
from convener_ops.journey import (
    delivery,
    eventkeys,
    signing,
)
from convener_ops.journey.attendance import (
    EligibilityThreshold,
    MatchedAttendee,
    MatchEvent,
    eligible_attendees,
    match,
)
from convener_ops.journey.certificate import (
    EVENTS_DIR,
    STATE_REVOKED,
    CertificateEntry,
    CertificateEvent,
    certificates_path,
    duration_hours,
    fingerprint,
    full_name,
    is_valid_identifier,
    issue,
    public_register,
    register_from_data,
    register_to_data,
    reissue,
    revoke,
    sign_for,
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

#: certificates.yml holds no name and no address by construction -- see
#: tools/convener_ops/journey/certificate.py's module docstring for why this file
#: survives the retention sweep on registrations.enc, in the same
#: directory, untouched.
CERTIFICATES_HEADER = (
    "# Certificate register -- no name, no address; "
    "see tools/convener_ops/journey/certificate.py\n"
)


def _warn_if_title_truncated(event: CertificateEvent) -> None:
    """`CertificateEvent.__post_init__`
    truncates a title over `certificate._MAX_TITLE_LENGTH` silently --
    correct for the document and the signature (they must never
    disagree about which title they carry), but silent for the operator
    too, until now. Every one of the four commands that construct a
    `CertificateEvent` (`issue_certificates`, `reissue_certificate`,
    `deliver_certificates`, `deliver_certificate`) calls this right after,
    so a shortened title is always named once, on stderr, never
    swallowed -- the same "surfaced, not folded away" discipline this
    module already gives the revoked-refusal case."""
    if event.title_truncated:
        print(
            f"::warning::the title for event {event.event_id} was too "
            "long and has been truncated on the certificate -- see "
            "instance/data/speakers.yml's own title field for that event",
            file=sys.stderr,
        )


def issue_certificates() -> int:
    """`convener-issue-certificates`: match this event's attendance, work out
    who is eligible, and issue -- or reproduce -- a certificate
    for each of them.

    Reads `EVENT_ID` and `EVENT_PRIVATE_KEY` exactly as `match_attendance`
    does, for the same reason: this job re-derives the match from scratch
    rather than trusting a prior run's own answer, so a corrected
    registration or a corrected attendance export is picked up for free
    -- a corrected match recomputes without anybody re-registering.

    Also reads `CONVENER_FCC_CONFERENCE_ID`
    (`conference_ids_from_env`, shared with `reissue_certificate`), the
    same optional `workflow_dispatch` input `recording.yml` already gives
    `release_recording`. Without it, nothing ever populated
    `conference_ids`, so the FCC path (`CONVENER_MEETING_API_TOKEN` configured)
    could never issue a certificate at all: `PlatformFCC._conference_id`
    raised `EventNotFoundError` before any network call, and this function
    did not catch it. Both are closed together: the input is
    threaded through, and `EventNotFoundError` joins the exception tuple
    below alongside `AttendanceImportError` and `FCCRequestError`. A
    conference id is a provider identifier, not personal data -- so the
    "never an address" reasoning does not apply to it, the same conclusion
    `recording.yml`'s own header comment already reached. **The manual
    path (no `CONVENER_MEETING_API_TOKEN`) stays blocked regardless**: its own
    attendance export is `.gitignore`d and cannot exist in a CI checkout
    at all.

    Two secrets gate whether *anything* is issued this run, checked before
    any registration is even decrypted:

    - `signing.SECRET_NAME` (`CONVENER_SIGNING_KEY`) absent is the ordinary
      D-13 shape `declarations/integrations.yml`'s own `signing_key` row
      documents -- no certificate this run, nothing else affected.
    - `CONVENER_MATCHING_SALT` absent is *not* ordinary here, unlike its own
      row's documented behaviour for `matching_code`: see
      `certificate.py`'s module docstring for why a certificate
      fingerprint cannot be computed safely without it. Both absences
      produce the same outward shape -- a printed line, a clean exit,
      nothing written -- because both are D-13 states from the outside;
      only the *reason* differs, and it is named in the message so an
      operator reading the log knows which secret to set.

    Every other failure mirrors `match_attendance`'s own handling: a bad
    event id, a missing private key, a missing or malformed
    `registrations.enc`, or a platform that cannot answer are all reported
    on one line and exit 1. A missing or malformed `instance/data/config.yml`
    exits 1 too -- eligibility cannot be computed at all without
    `seminar_duration_minutes`, unlike `match_attendance`, which never
    needed the config file in the first place. `CONVENER_SIGNING_KEY` present
    but unusable (a mangled PEM, the ordinary way a pasted secret fails)
    is checked once, before any registration is decrypted, rather than
    left to surface as an unhandled `signing.SigningError` traceback from
    inside the loop below.

    A speaker record for `event_id` that is missing, or present but
    carries an empty title or an empty date, refuses the whole run (exit
    1) rather than signing a certificate that names no event and no date
    -- a certificate's content is not optional, and the register row a
    silently-empty certificate would leave behind is permanent.
    When `instance/data/speakers.yml` itself failed to parse, the
    message names that parse failure -- surfaced from `store.load`, never
    discarded -- instead of sending an operator to look for a speaker
    record that was never actually missing.

    Prints only counts, never a name or an address -- the same discipline
    `match_attendance` already holds itself to for the same reason.
    `instance/data/events/<id>/certificates.yml` is rewritten, as a whole file
    (never appended to a partial one), only when at least one certificate
    was freshly minted; reissuing every attendee already on record writes
    nothing and still exits 0.

    **A fingerprint whose only rows are revoked is refused, not
    resurrected.** `issue`'s own three-way lookup
    raises `ValueError` for that one attendee; this loop catches it,
    counts it separately (never crashing the whole run over it), and
    leaves the register untouched for that fingerprint. The correction
    path is `convener-reissue-certificate`, an operator's own deliberate act,
    never something this scheduled-and-re-run command performs itself.

    **Writes the freshly-issued identifiers to `$GITHUB_OUTPUT` as
    `issued_ids=<comma-joined>`.** Identifiers are
    public by design -- already printed on the document, already
    published in `certificates-public.json` -- so nothing personal
    travels. `issue-certificates.yml`'s delivery step
    (`deliver_certificates`, below) reads this to restrict an ordinary run
    to exactly what was minted just now, rather than re-mailing every past
    attendee on every dispatch.

    Each eligible attendee's `duration_seconds` is capped at
    `threshold.seminar_duration_minutes * 60` before it ever reaches
    `issue` -- see
    `certificate.duration_hours`'s own docstring for why this is the
    correct number, not a workaround, and why it is done here rather than
    inside `certificate.py`: this is the one place both the attendee's
    summed duration and the seminar's own scheduled length are already in
    hand.
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

    signing_key = os.environ.get(signing.SECRET_NAME, "")
    if not signing_key:
        print(f"{signing.SECRET_NAME} not configured -- no certificate issued this run")
        return 0
    try:
        signing.derive_public_pem(signing_key)
    except signing.SigningError as exc:
        print(f"{signing.SECRET_NAME}: {exc}", file=sys.stderr)
        return 1

    salt = os.environ.get("CONVENER_MATCHING_SALT") or ""
    if not salt:
        print(
            "CONVENER_MATCHING_SALT not configured -- no certificate issued this "
            "run (a certificate fingerprint cannot be computed safely "
            "without it)"
        )
        return 0

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

    speakers, speaker_errors = store.load(root / DATA_DIR / "speakers.yml")
    cfg, _errors = store.load(root / DATA_DIR / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    if not isinstance(cfg, dict):
        print(
            f"{(DATA_DIR / 'config.yml').as_posix()} is missing or invalid "
            "-- cannot compute eligibility",
            file=sys.stderr,
        )
        return 1

    platform = platform_from_env(
        os.environ,
        speaker_list,
        cfg,
        conference_ids_from_env(event_id),
        private_pem=private_pem,
    )
    try:
        rows = platform.get_attendance(event_id)
    except (AttendanceImportError, FCCRequestError, EventNotFoundError) as exc:
        # `EventNotFoundError` is in this tuple because,
        # with no `CONVENER_FCC_CONFERENCE_ID` configured for this event,
        # `PlatformFCC._conference_id` raises it and nothing here used to
        # catch it -- `issue_certificates`'s own docstring
        # already promised every failure is "reported on one line and
        # exit 1", and this was the one hole in that promise.
        print(str(exc), file=sys.stderr)
        return 1

    matched = match(rows, registrations, MatchEvent(event_id=event_id, salt=salt))
    threshold = EligibilityThreshold.from_config(cfg)
    eligible = eligible_attendees(matched, threshold)

    record: Mapping[str, Any] = {}
    with contextlib.suppress(EventNotFoundError):
        record = find_speaker(speaker_list, event_id)

    title = str(record.get("title", "") or "")
    event_date = str(record.get("date", "") or "")
    if not title or not event_date:
        if speaker_errors:
            print(
                f"{(DATA_DIR / 'speakers.yml').as_posix()}: "
                f"{'; '.join(speaker_errors)} -- refusing "
                "to sign a certificate naming no event and no date",
                file=sys.stderr,
            )
        else:
            print(
                f"no speaker record with both a title and a date matches "
                f"event {event_id} -- refusing to sign a certificate naming "
                "no event and no date",
                file=sys.stderr,
            )
        return 1

    loaded_register = _load_certificate_register(root, event_id)
    if loaded_register is None:
        return 1
    register_path, existing = loaded_register

    event = CertificateEvent(event_id=event_id, title=title, date=event_date)
    _warn_if_title_truncated(event)
    issued_on = paris_today(datetime.now(UTC))
    max_duration_seconds = threshold.seminar_duration_minutes * 60

    entries = list(existing)
    issued_count = 0
    already_count = 0
    refused_count = 0
    freshly_issued_ids: list[str] = []
    for attendee in eligible:
        capped_attendee = replace(
            attendee,
            duration_seconds=min(attendee.duration_seconds, max_duration_seconds),
        )
        # `result.token` is deliberately dropped: delivery recomputes it
        # byte-identically (PKCS1v15 determinism -- see certificate.py's
        # own module docstring, "idempotent without being deterministic").
        # This is the payoff of the idempotence design, not an oversight.
        try:
            result = issue(
                capped_attendee,
                event,
                signing_key,
                salt,
                tuple(entries),
                issued_on=issued_on,
            )
        except ValueError:
            # Every register row for this fingerprint
            # is revoked -- `issue`'s own three-way lookup refuses rather
            # than resurrecting it. A routine re-run must skip this one
            # attendee, never crash the whole run over it; the correction
            # path is `convener-reissue-certificate`, run by hand.
            refused_count += 1
            continue
        if result.already_registered:
            already_count += 1
        else:
            entries.append(result.entry)
            issued_count += 1
            freshly_issued_ids.append(result.entry.identifier)

    if issued_count:
        register_path.parent.mkdir(parents=True, exist_ok=True)
        register_path.write_text(
            CERTIFICATES_HEADER + store.dump(register_to_data(tuple(entries))),
            encoding="utf-8",
            newline="",
        )

    # Hand the freshly-issued identifiers (public by
    # design -- already printed on the document, already published in
    # certificates-public.json) to the delivery step through
    # `$GITHUB_OUTPUT`, so a re-dispatch after a corrected export mails
    # only the newly corrected certificates, not every past attendee
    # again. Written even when empty -- an empty `issued_ids=` is exactly
    # what tells `convener-deliver-certificates` this run minted nothing new,
    # so it should deliver nothing (see that function's own docstring).
    step_output.write(f"issued_ids={','.join(freshly_issued_ids)}\n")

    refused_note = (
        f", {refused_count} refused (revoked, use convener-reissue-certificate)"
    )
    print(
        f"certificates for event {event_id}: {issued_count} issued, "
        f"{already_count} already on record"
        f"{refused_note if refused_count else ''} ({len(eligible)} eligible; "
        f"{unreadable_registrations} registration(s) could not be read)"
    )
    return 0


def certificates_public_data() -> int:
    """`convener-certificates-public-data`: rebuild
    `instance/public-data/certificates-public.json` from every event's own
    `instance/data/events/<id>/certificates.yml`, following `public_data`'s own
    precedent for `events-public.json` (`certificate.public_register` is
    the pure projection this calls, the same split `public_data.to_public`
    draws for the speaker list).

    Reads every `certificates.yml` under `instance/data/events/*/` that exists --
    an event with none yet contributes nothing, not an error, the ordinary
    state for an event with no certificates issued -- and aggregates them
    into one flat list before projecting: identifiers are drawn from
    `secrets.token_hex`, so a collision between two events' identifiers is
    not a case this function has to guard against (see
    `certificate.py`'s own docstring for the entropy this relies on).
    Malformed content in one event's register is reported and stops the
    whole run rather than silently publishing a partial feed -- the same
    "a malformed committed file is not a normal state to paper over"
    choice `register_from_data` itself already makes.
    """
    root = repo_root()
    events_dir = root / EVENTS_DIR
    entries: list[Any] = []
    if events_dir.is_dir():
        for register_path in sorted(events_dir.glob("*/certificates.yml")):
            # Relative to `root`, not the whole
            # absolute path -- issue_certificates and reissue_certificate
            # already name a register this way, and the absolute form
            # carries CONVENER_REPO_ROOT into the log for no reason.
            relative = register_path.relative_to(root).as_posix()
            try:
                data = yaml_safe_load(register_path.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                print(f"{relative}: invalid YAML - {exc}", file=sys.stderr)
                return 1
            try:
                entries.extend(register_from_data(data))
            except ValueError as exc:
                print(f"{relative}: {exc}", file=sys.stderr)
                return 1

    rows = public_register(entries)
    out_dir = root / PUBLIC_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "certificates-public.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} certificates")
    return 0


def _load_certificate_register(
    root: Path, event_id: str
) -> tuple[Path, tuple[CertificateEntry, ...]] | None:
    """Load `event_id`'s register -- factored out so
    `issue_certificates`, `reissue_certificate` and `revoke_certificate`
    share one reading of `certificates.yml` rather than three copies that
    could drift. Returns `None` on any failure, having already printed the
    one-line reason to stderr; a caller returns `1` in that case. Returning
    `None` rather than a third element a caller has to `assert` away keeps
    every call site a plain `if loaded is None: return 1`, which mypy
    narrows on its own."""
    register_path = certificates_path(root, event_id)
    if register_path.exists():
        try:
            register_data = yaml_safe_load(register_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(
                f"{register_path.relative_to(root).as_posix()}: invalid YAML - {exc}",
                file=sys.stderr,
            )
            return None
    else:
        register_data = None
    try:
        existing = register_from_data(register_data)
    except ValueError as exc:
        print(f"{register_path.relative_to(root).as_posix()}: {exc}", file=sys.stderr)
        return None
    return register_path, existing


def _find_register_entry(
    existing: Sequence[CertificateEntry], event_id: str, certificate_id: str
) -> CertificateEntry | None:
    """`existing`'s own row for `(event_id, certificate_id)`, or `None` --
    factored out so `reissue_certificate` and
    `deliver_certificate` share one reading of "does this certificate id
    exist on record for this event", rather than the inline `next(...)`
    each once wrote for itself."""
    return next(
        (
            entry
            for entry in existing
            if entry.event_id == event_id and entry.identifier == certificate_id
        ),
        None,
    )


def _find_attendee_by_fingerprint(
    eligible: Sequence[MatchedAttendee],
    event_id: str,
    salt: str,
    target_fingerprint: str,
) -> MatchedAttendee | None:
    """The one currently-eligible attendee whose own fingerprint matches
    `target_fingerprint`, or `None` -- the reverse of
    `certificate.issue`'s own lookup: resolve a public certificate
    id to a person by fingerprint alone, never by accepting or holding an
    address. Factored out so `reissue_certificate` and
    `deliver_certificate` share this one resolution path rather than
    `deliver_certificate` writing a second copy of it -- see that
    function's own docstring."""
    return next(
        (
            attendee
            for attendee in eligible
            if fingerprint(event_id, attendee.registration.email, salt)
            == target_fingerprint
        ),
        None,
    )


def reissue_certificate() -> int:
    """`convener-reissue-certificate`: an operator's deliberate correction to
    one already-issued certificate -- mint a fresh identifier and a fresh
    signed token for the attendee named by `CERTIFICATE_ID`, never
    touching the row it replaces.

    Unlike `convener-issue-certificates`, this is never a scheduled job: an
    operator runs it by hand, once, for one certificate, after revoking
    the one it replaces (`convener-revoke-certificate`).
    See `certificate.reissue`'s own docstring for why this has to be a
    separate, explicit command rather than a change to
    `convener-issue-certificates`'s own idempotent lookup: that job must keep
    refusing to resurrect a revoked certificate on a routine re-run, which
    is only true as long as reissuing never happens inside its loop.

    Reads `EVENT_ID`, `EVENT_PRIVATE_KEY`, `CONVENER_SIGNING_KEY`,
    `CONVENER_MATCHING_SALT` and `CONVENER_FCC_CONFERENCE_ID` exactly as
    `convener-issue-certificates` does -- the same D-13 shapes, and the same
    `conference_ids_from_env` resolution --
    plus `CERTIFICATE_ID`, the certificate this run corrects.

    **`CERTIFICATE_ID` is shape-checked before it is ever echoed.**
    `certificate.is_valid_identifier` -- the exact 32
    lowercase hex characters `_new_identifier` always produces -- is
    checked immediately after this value is read, the same one-line
    discipline `eventkeys.secret_name` already gives `EVENT_ID`.
    `.strip()` alone only removes a *leading or trailing* newline; an id
    shaped `"abc\\n::add-mask::secret"` would otherwise put a GitHub
    Actions workflow command at the start of a log line the moment this
    function's own refusal or success message printed it back.

    **`CERTIFICATE_ID`, never an address.** A `workflow_dispatch`
    input is rendered on the run page and retained with the run for as
    long as the run's own history exists -- longer than the 14-day
    artefact this project uses everywhere it has to carry personal data
    at all, and exactly the exposure that argues against it. This
    command has an alternative `convener-resend-confirmation` never had: the
    certificate identifier is random, public by design, already printed
    on the document and already published in
    `certificates-public.json` -- so it names exactly one certificate
    without naming a person. The identifier resolves to a registration
    the same way `certificate.issue` does, run in reverse: this function
    reads the register row `CERTIFICATE_ID` names (`fingerprint`,
    private, never published) and then computes every currently eligible
    attendee's own fingerprint until one matches -- the one candidate
    `certificate.fingerprint`'s salted HMAC says is the same person,
    without ever reading or printing an address to find out. No address
    is typed into this command, held by it, or printed by it, at any
    point.

    Re-derives registrations and attendance from scratch, exactly as
    `convener-issue-certificates` does, so a correction to either -- a
    mis-typed name fixed in a re-submitted registration, a corrected
    attendance export -- is picked up automatically; the only differences
    from `convener-issue-certificates` are which one attendee this command
    acts on, and that it calls `certificate.reissue` instead of
    `certificate.issue`. Refuses (exit 1) when no register entry carries
    `CERTIFICATE_ID`, when no currently eligible attendee's fingerprint
    matches that entry's, or when `certificate.reissue` itself refuses --
    a still-issued row standing in the way -- surfacing that `ValueError`
    verbatim, since it already names the reason.
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

    signing_key = os.environ.get(signing.SECRET_NAME, "")
    if not signing_key:
        print(
            f"{signing.SECRET_NAME} not configured -- no certificate reissued this run"
        )
        return 0
    try:
        signing.derive_public_pem(signing_key)
    except signing.SigningError as exc:
        print(f"{signing.SECRET_NAME}: {exc}", file=sys.stderr)
        return 1

    salt = os.environ.get("CONVENER_MATCHING_SALT") or ""
    if not salt:
        print(
            "CONVENER_MATCHING_SALT not configured -- no certificate reissued "
            "this run (a certificate fingerprint cannot be computed "
            "safely without it)"
        )
        return 0

    certificate_id = os.environ.get("CERTIFICATE_ID", "").strip()
    if not certificate_id:
        print("no certificate id supplied", file=sys.stderr)
        return 1
    if not is_valid_identifier(certificate_id):
        # Never echo a malformed value back -- the
        # same "no valid event id supplied" idiom `eventkeys.secret_name`'s
        # own caller above already uses for the identical reason.
        print("not a valid certificate id supplied", file=sys.stderr)
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

    registrations, _unreadable_registrations = load_registrations(
        current.entries, private_pem
    )

    loaded_register = _load_certificate_register(root, event_id)
    if loaded_register is None:
        return 1
    register_path, existing = loaded_register

    target_entry = _find_register_entry(existing, event_id, certificate_id)
    if target_entry is None:
        print(
            f"no certificate {certificate_id} on record for event {event_id}",
            file=sys.stderr,
        )
        return 1

    speakers, speaker_errors = store.load(root / DATA_DIR / "speakers.yml")
    cfg, _errors = store.load(root / DATA_DIR / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    if not isinstance(cfg, dict):
        print(
            f"{(DATA_DIR / 'config.yml').as_posix()} is missing or invalid "
            "-- cannot compute eligibility",
            file=sys.stderr,
        )
        return 1

    platform = platform_from_env(
        os.environ,
        speaker_list,
        cfg,
        conference_ids_from_env(event_id),
        private_pem=private_pem,
    )
    try:
        rows = platform.get_attendance(event_id)
    except (AttendanceImportError, FCCRequestError, EventNotFoundError) as exc:
        # See `issue_certificates`'s own comment on the identical
        # `EventNotFoundError` addition.
        print(str(exc), file=sys.stderr)
        return 1

    matched = match(rows, registrations, MatchEvent(event_id=event_id, salt=salt))
    threshold = EligibilityThreshold.from_config(cfg)
    eligible = eligible_attendees(matched, threshold)

    # Resolve the certificate to a candidate by fingerprint, the
    # same derivation `certificate.issue` performs, run in reverse --
    # never by reading an address out of the register (it holds none) or
    # accepting one as input (see the docstring above). Shared with
    # `deliver_certificate` through `_find_attendee_by_fingerprint`
    # rather than written a second time.
    attendee = _find_attendee_by_fingerprint(
        eligible, event_id, salt, target_entry.fingerprint
    )
    if attendee is None:
        print(
            f"certificate {certificate_id} does not match any currently "
            f"eligible attendee for event {event_id} -- not enough "
            "attendance recorded to reissue it",
            file=sys.stderr,
        )
        return 1

    record: Mapping[str, Any] = {}
    with contextlib.suppress(EventNotFoundError):
        record = find_speaker(speaker_list, event_id)
    title = str(record.get("title", "") or "")
    event_date = str(record.get("date", "") or "")
    if not title or not event_date:
        if speaker_errors:
            print(
                f"{(DATA_DIR / 'speakers.yml').as_posix()}: "
                f"{'; '.join(speaker_errors)} -- refusing "
                "to sign a certificate naming no event and no date",
                file=sys.stderr,
            )
        else:
            print(
                f"no speaker record with both a title and a date matches "
                f"event {event_id} -- refusing to sign a certificate naming "
                "no event and no date",
                file=sys.stderr,
            )
        return 1

    event = CertificateEvent(event_id=event_id, title=title, date=event_date)
    _warn_if_title_truncated(event)
    capped_attendee = replace(
        attendee,
        duration_seconds=min(
            attendee.duration_seconds, threshold.seminar_duration_minutes * 60
        ),
    )
    issued_on = paris_today(datetime.now(UTC))
    try:
        result = reissue(
            capped_attendee, event, signing_key, salt, existing, issued_on=issued_on
        )
    except ValueError as exc:
        print(f"cannot reissue for event {event_id}: {exc}", file=sys.stderr)
        return 1

    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text(
        CERTIFICATES_HEADER + store.dump(register_to_data((*existing, result.entry))),
        encoding="utf-8",
        newline="",
    )
    print(
        f"certificate reissued for event {event_id}: {certificate_id} -> "
        f"{result.entry.identifier}"
    )
    return 0


def revoke_certificate() -> int:
    """`convener-revoke-certificate`: mark one already-issued certificate
    `STATE_REVOKED` in the register -- the operation
    this module always had a tested, correct pure function for
    (`certificate.revoke`) and, for a long time, no caller at all.

    A hand edit of the committed-clear register was once reasoned to be
    a legitimate way to flip one entry's `state`. It is not: it depends
    on a volunteer having a working checkout,
    finding the right file, editing the right row, and committing it
    correctly -- exactly the "a collaborator's goodwill or their post"
    dependency this whole project refuses to build on elsewhere -- and
    `revoke`'s own guard against naming an identifier that is not in the
    register is unreachable from a text editor, which is precisely where
    that mistake gets made.

    Reads `EVENT_ID` and `CERTIFICATE_ID` -- both public identifiers,
    never an address (see `reissue_certificate`'s own docstring for
    why an address is never accepted by any command in this module that a
    `workflow_dispatch` form could expose). `CERTIFICATE_ID` is
    shape-checked the same way `reissue_certificate` checks it
    -- see that function's own docstring for why. Needs no
    signing key and no matching salt: revocation touches the register alone
    (`certificate.py`'s own "revocation touches the register, never the
    signature" section) -- the token a revoked certificate's holder
    carries keeps verifying forever; only the register's own `state`
    column says it should no longer be trusted.
    """
    event_id = os.environ.get("EVENT_ID", "").strip()
    try:
        eventkeys.secret_name(event_id)
    except ValueError:
        print("no valid event id supplied", file=sys.stderr)
        return 1

    certificate_id = os.environ.get("CERTIFICATE_ID", "").strip()
    if not certificate_id:
        print("no certificate id supplied", file=sys.stderr)
        return 1
    if not is_valid_identifier(certificate_id):
        print("not a valid certificate id supplied", file=sys.stderr)
        return 1

    root = repo_root()
    loaded_register = _load_certificate_register(root, event_id)
    if loaded_register is None:
        return 1
    register_path, existing = loaded_register

    try:
        # `event_id` is passed alongside `certificate_id`:
        # `revoke` filters on both, the same "this
        # event's own certificate" `reissue` already required, rather than
        # matching an identifier alone across whatever `existing` happens
        # to hold.
        updated = revoke(existing, event_id, certificate_id)
    except ValueError as exc:
        print(f"cannot revoke for event {event_id}: {exc}", file=sys.stderr)
        return 1

    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text(
        CERTIFICATES_HEADER + store.dump(register_to_data(updated)),
        encoding="utf-8",
        newline="",
    )
    print(f"certificate {certificate_id} revoked for event {event_id}")
    return 0


def deliver_certificates() -> int:
    """`convener-deliver-certificates`: e-mail every currently eligible
    attendee's certificate for one event -- by e-mail alone, never as a
    document naming a person deposited in a repository -- the
    step `issue-certificates.yml` runs immediately after
    `convener-issue-certificates` itself, in the same job and the same
    checkout, so this function's own re-derivation of the register (via
    `_load_certificate_register`) reads exactly what that step just wrote.

    Re-derives registrations, attendance and eligibility from scratch,
    exactly as `issue_certificates` does -- the same discipline of
    recalculating without re-registering -- and then calls
    `certificate.issue` again for each eligible attendee. That second call
    never grows the register (`issue`'s own fingerprint-keyed lookup
    reuses the existing entry's `identifier`, `certificate.py`'s own
    module docstring,
    "idempotent without being deterministic") and reproduces the exact
    same signed token every time (`signing.sign` is deterministic) -- so
    running this command again, for a delivery that failed the first
    time, replays the identical document rather than minting a second
    certificate for the same person (`delivery.py`'s module docstring,
    "replayable, not regenerated").

    Never writes anything to disk: the rendered
    document lives only in memory for the length of one e-mail send
    (`delivery.render_certificate`, `delivery.deliver`) and is never
    written to a file, an artefact, or printed. A failed delivery is
    reported -- folded into the printed count, never named individually --
    and replayed by re-running this same command; see `delivery.py`'s own
    module docstring, "never written to disk", for why writing it
    anywhere would be the wrong pattern here regardless: what it would
    retain is a nominative, signed document, in an Actions surface,
    exactly what this project forbids -- the same "reported, not retained"
    rule `_send_confirmation` applies to an unsent registration
    confirmation too, once that message
    stopped being the one documented case a build artefact was the right
    place for it.

    Two secrets gate whether anything is delivered this run, checked
    before any registration is even decrypted -- the same two
    `issue_certificates` gates on, for the identical reasons (see that
    function's own docstring): `CONVENER_SIGNING_KEY` absent is ordinary D-13
    (nothing to sign a token with, so nothing delivered, a clean exit);
    `CONVENER_MATCHING_SALT` absent is not (a certificate fingerprint cannot be
    computed safely without it). Absent `email_transport` secrets are
    ordinary D-13 too, but at a different point: every attempt this run
    makes simply reports unsent (`delivery.deliver` returns
    `sent=False` with nothing configured), never a refusal before the
    loop -- an operator who has not yet configured outbound mail can still
    see exactly how many certificates *would* have gone out.

    Every other refusal mirrors `issue_certificates`'s own handling line
    for line: a bad event id, a missing private key, a missing or
    malformed `registrations.enc`, a missing or malformed
    `instance/data/config.yml`, a platform that cannot answer, or a speaker record
    with no title and no date all refuse the whole run (exit 1) before
    anything is delivered. **A missing certificate register also refuses
    :** with no `certificates.yml` on disk for this
    event, `issue`'s own "no row" branch would mint a fresh identifier
    that this function never persists (only `issue_certificates` writes
    the register) -- a certificate mailed once and never again reproducible.
    Unreachable from the shipped workflow, which only ever runs this step
    after `issue_certificates` has already written the file, but this
    command is dispatchable on its own, so the guard is not decorative.

    Once eligibility is computed, this command never fails the whole run
    again. Four outcomes, each counted separately and printed by name,
    never folded into one indistinguishable bucket:

    - **`issue` refuses:** every register row for this fingerprint
      is revoked. Counted as its own `refused_count`, not folded into
      "not sent" (it used to be, and an
      operator reading the printed line could not tell "correctly not
      sent, on purpose" from "the mail server is down" -- exactly the
      distinction `unsent_count`'s own D-13 framing below depends on
      meaning only one thing). A revoked certificate is never delivered,
      by any path, but this is not a renderer crash or a transport
      failure either, so it does not inflate those two counts.
    - **Rendering or composing the document raises:** counted separately
      from a transport failure (`render_failed_count`) -- `delivery.deliver`
      below never raises for an ordinary send failure, it *returns*
      `sent=False`, so anything caught here is this module's own code
      (the concrete, reachable case: `event.title` overflowing the QR --
      see `certificate.CertificateEvent`'s own `_MAX_TITLE_LENGTH` for
      why that specific crash can no longer happen, though a
      still-unanticipated one is handled identically).
      An operator seeing this count knows to look at the code or the data,
      never at the mail secrets.
    - **`delivery.deliver` returns `sent=False`:** no transport configured,
      or a configured one that raised and was already caught inside
      `delivery.deliver` itself. Counted as `unsent_count`, the ordinary
      D-13 shape.

    None of these three stops delivery to the rest of `eligible`; the
    exception's own text is never printed, only counted, and the message
    also lists the *identifiers* (never a name or an address) that did not
    go out -- an operator whose one bounce failed can
    then name it directly to `convener-deliver-certificate`, rather than
    reaching for the batch that caused the problem in the first place.

    **Restricted by default to what this run's own issuance step just
    minted.** `DELIVER_ONLY` -- a comma-joined set of
    identifiers, ordinarily `issue_certificates`'s own `issued_ids` output,
    forwarded by `issue-certificates.yml` -- skips every eligible attendee
    whose identifier is not in that set, counted separately
    (`skipped_count`, "not targeted this run"), never as unsent. Unset
    entirely (a manual, standalone run outside that workflow) or
    `RESEND_ALL=true` (an operator's own deliberate batch retry, never the
    default) both mean no restriction at all -- every eligible attendee is
    targeted, the behaviour this function had before `DELIVER_ONLY` existed.
    `DELIVER_ONLY` set to the empty string -- an issuance run that minted
    nothing new -- means every eligible attendee is skipped: the whole
    point of the hand-off is that a re-dispatch after nothing changed
    mails nobody again.

    Prints only counts and public identifiers, never a name or an
    address, on every path -- including an attendee who was already on
    record before this run started (a name printed on exactly that branch
    survived a
    full green suite once already, because the leak sweep that would have
    caught it only ever ran on the freshly-issued path)."""
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

    signing_key = os.environ.get(signing.SECRET_NAME, "")
    if not signing_key:
        print(
            f"{signing.SECRET_NAME} not configured -- no certificate delivered this run"
        )
        return 0
    try:
        signing.derive_public_pem(signing_key)
    except signing.SigningError as exc:
        print(f"{signing.SECRET_NAME}: {exc}", file=sys.stderr)
        return 1

    salt = os.environ.get("CONVENER_MATCHING_SALT") or ""
    if not salt:
        print(
            "CONVENER_MATCHING_SALT not configured -- no certificate delivered "
            "this run (a certificate fingerprint cannot be computed "
            "safely without it)"
        )
        return 0

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

    speakers, speaker_errors = store.load(root / DATA_DIR / "speakers.yml")
    cfg, _errors = store.load(root / DATA_DIR / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    if not isinstance(cfg, dict):
        print(
            f"{(DATA_DIR / 'config.yml').as_posix()} is missing or invalid "
            "-- cannot compute eligibility",
            file=sys.stderr,
        )
        return 1

    platform = platform_from_env(
        os.environ,
        speaker_list,
        cfg,
        conference_ids_from_env(event_id),
        private_pem=private_pem,
    )
    try:
        rows = platform.get_attendance(event_id)
    except (AttendanceImportError, FCCRequestError, EventNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    matched = match(rows, registrations, MatchEvent(event_id=event_id, salt=salt))
    threshold = EligibilityThreshold.from_config(cfg)
    eligible = eligible_attendees(matched, threshold)

    record: Mapping[str, Any] = {}
    with contextlib.suppress(EventNotFoundError):
        record = find_speaker(speaker_list, event_id)
    title = str(record.get("title", "") or "")
    event_date = str(record.get("date", "") or "")
    if not title or not event_date:
        if speaker_errors:
            print(
                f"{(DATA_DIR / 'speakers.yml').as_posix()}: "
                f"{'; '.join(speaker_errors)} -- refusing "
                "to sign a certificate naming no event and no date",
                file=sys.stderr,
            )
        else:
            print(
                f"no speaker record with both a title and a date matches "
                f"event {event_id} -- refusing to sign a certificate naming "
                "no event and no date",
                file=sys.stderr,
            )
        return 1

    loaded_register = _load_certificate_register(root, event_id)
    if loaded_register is None:
        return 1
    register_path, existing = loaded_register
    if not register_path.exists():
        # Nothing to reproduce from -- see this
        # function's own docstring for why minting here anyway would be
        # unsafe (an identifier written nowhere).
        print(f"no certificate register for event {event_id}", file=sys.stderr)
        return 1

    event = CertificateEvent(event_id=event_id, title=title, date=event_date)
    _warn_if_title_truncated(event)
    issued_on = paris_today(datetime.now(UTC))
    max_duration_seconds = threshold.seminar_duration_minutes * 60

    # Restrict to what this run's own issuance step
    # just minted, unless an operator has explicitly asked for everyone.
    # See this function's own docstring for the full contract.
    resend_all = env_flag_is_true("RESEND_ALL")
    deliver_only_raw = os.environ.get("DELIVER_ONLY")
    deliver_only: frozenset[str] | None
    if resend_all or deliver_only_raw is None:
        deliver_only = None
    else:
        deliver_only = frozenset(
            piece for piece in deliver_only_raw.split(",") if piece
        )

    sent_count = 0
    unsent_count = 0
    refused_count = 0
    render_failed_count = 0
    skipped_count = 0
    unsent_ids: list[str] = []
    for attendee in eligible:
        capped_attendee = replace(
            attendee,
            duration_seconds=min(attendee.duration_seconds, max_duration_seconds),
        )
        try:
            result = issue(
                capped_attendee, event, signing_key, salt, existing, issued_on=issued_on
            )
        except ValueError:
            # Every register row for this fingerprint is revoked --
            # never resurrect it here. Counted
            # separately from `unsent_count` -- a revoked certificate that
            # was correctly never delivered is not the same finding as a
            # transport failure, and an operator could not previously tell
            # "the mail server is down" from "this one is revoked, on
            # purpose" in the printed line.
            refused_count += 1
            continue

        if deliver_only is not None and result.entry.identifier not in deliver_only:
            skipped_count += 1
            continue

        try:
            document = delivery.render_certificate(
                name=full_name(capped_attendee),
                event_title=event.title,
                event_date=event.date,
                duration_hours=duration_hours(capped_attendee.duration_seconds),
                identifier=result.entry.identifier,
                token=result.token,
            )
            message = delivery.compose(
                capped_attendee.registration,
                event.title,
                result.entry.identifier,
                document,
            )
        except Exception:  # our own code, not the transport
            render_failed_count += 1
            unsent_ids.append(result.entry.identifier)
            continue

        send_result = delivery.deliver(message, os.environ)
        if send_result.sent:
            sent_count += 1
        else:
            unsent_count += 1
            unsent_ids.append(result.entry.identifier)

    print(
        f"certificates delivered for event {event_id}: {sent_count} sent, "
        f"{unsent_count} not sent, {refused_count} refused (revoked), "
        f"{render_failed_count} failed to render, {skipped_count} not "
        f"targeted this run ({len(eligible)} eligible; "
        f"{unreadable_registrations} registration(s) could not be read)"
    )
    if unsent_ids:
        # Identifiers are public by design -- never a
        # name or an address -- so an operator can copy one straight into
        # convener-deliver-certificate's own CERTIFICATE_ID input.
        print(f"not sent: {', '.join(sorted(unsent_ids))}")
    return 0


def deliver_certificate() -> int:
    """`convener-deliver-certificate`: (re)deliver one already-issued
    certificate, named by `CERTIFICATE_ID` -- the manual resend the risk
    of silent loss asks for (a certificate in a spam folder does not
    exist), for the one document this project never accepts an address to
    redeliver.

    Reuses `reissue_certificate`'s own `CERTIFICATE_ID` -> attendee
    resolution (`_find_register_entry`, `_find_attendee_by_fingerprint`)
    rather than writing a second lookup: `CERTIFICATE_ID` is a public,
    printed-on-the-document identifier, resolved to a register row and then
    to a currently-eligible attendee by fingerprint alone, run in reverse
    from `certificate.issue`'s own derivation -- never by reading or
    accepting an address (see `reissue_certificate`'s own docstring for the
    full reasoning this shares).

    **Signs `target_entry` directly, via `certificate.sign_for`, never
    `certificate.issue`.** `issue`
    re-resolves by *fingerprint*, taking the currently-issued row for that
    fingerprint -- almost always `target_entry` itself, but not after a
    revoke-and-reissue with no correction applied here: the register would
    then read `[old(revoked)]` or (mid-correction) still resolve to a row
    other than the one `CERTIFICATE_ID` named. This function used to
    resolve `target_entry` correctly and then discard it by
    calling `issue` anyway -- naming one certificate in its own log while
    delivering whatever `issue` happened to resolve. `sign_for` signs the
    exact row this function already holds; nothing here re-resolves
    anything by fingerprint at all.

    **Refuses a revoked `target_entry` outright.** Checked
    immediately after resolving it by `CERTIFICATE_ID`, before eligibility
    is even computed -- a revoked certificate is not delivered, ever, by
    any path; the correction is `convener-reissue-certificate`, run by hand.

    Every refusal before resolution mirrors `reissue_certificate`'s own
    handling: a bad event id, a missing private key, `CONVENER_SIGNING_KEY` or
    `CONVENER_MATCHING_SALT` absent (both ordinary D-13, nothing delivered, a
    clean exit -- for `CONVENER_MATCHING_SALT` the same stronger reason
    `certificate.py`'s module docstring gives), a missing or malformed
    `CERTIFICATE_ID`, missing or malformed `registrations.enc`, an unknown
    or revoked certificate id, a missing or malformed `instance/data/config.yml`, a
    platform that cannot answer, an id that matches no currently eligible
    attendee, or a speaker record with no title and no date -- all refuse
    (exit 1) before anything is rendered or sent.

    Once the attendee is resolved, this command always exits 0 and reports
    the outcome by message alone -- the same shape
    `resend_confirmation`/`_send_confirmation` already use for an ordinary
    confirmation resend: whether a delivery was actually sent is D-13's
    ordinary outward shape (a line, a clean exit), never a job failure,
    because the certificate itself is unaffected either way and a repeat
    run replays it identically (`delivery.py`'s own module docstring,
    "replayable, not regenerated" -- bounded, after the retention
    sweep, by whether this event's registrations still exist at all; see
    that same section for the boundary). Prints only the certificate id
    (already public) and the outcome -- never a name or an address."""
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

    signing_key = os.environ.get(signing.SECRET_NAME, "")
    if not signing_key:
        print(
            f"{signing.SECRET_NAME} not configured -- no certificate delivered this run"
        )
        return 0
    try:
        signing.derive_public_pem(signing_key)
    except signing.SigningError as exc:
        print(f"{signing.SECRET_NAME}: {exc}", file=sys.stderr)
        return 1

    salt = os.environ.get("CONVENER_MATCHING_SALT") or ""
    if not salt:
        print(
            "CONVENER_MATCHING_SALT not configured -- no certificate delivered "
            "this run (a certificate fingerprint cannot be computed "
            "safely without it)"
        )
        return 0

    certificate_id = os.environ.get("CERTIFICATE_ID", "").strip()
    if not certificate_id:
        print("no certificate id supplied", file=sys.stderr)
        return 1
    if not is_valid_identifier(certificate_id):
        print("not a valid certificate id supplied", file=sys.stderr)
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

    registrations, _unreadable_registrations = load_registrations(
        current.entries, private_pem
    )

    loaded_register = _load_certificate_register(root, event_id)
    if loaded_register is None:
        return 1
    _register_path, existing = loaded_register

    target_entry = _find_register_entry(existing, event_id, certificate_id)
    if target_entry is None:
        print(
            f"no certificate {certificate_id} on record for event {event_id}",
            file=sys.stderr,
        )
        return 1
    if target_entry.state == STATE_REVOKED:
        # A revoked certificate is not
        # delivered, ever, by any path -- refuse outright rather than
        # ever reaching a signer with it.
        print(
            f"certificate {certificate_id} is revoked for event {event_id} "
            "-- not delivered; use convener-reissue-certificate for a correction",
            file=sys.stderr,
        )
        return 1

    speakers, speaker_errors = store.load(root / DATA_DIR / "speakers.yml")
    cfg, _errors = store.load(root / DATA_DIR / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    if not isinstance(cfg, dict):
        print(
            f"{(DATA_DIR / 'config.yml').as_posix()} is missing or invalid "
            "-- cannot compute eligibility",
            file=sys.stderr,
        )
        return 1

    platform = platform_from_env(
        os.environ,
        speaker_list,
        cfg,
        conference_ids_from_env(event_id),
        private_pem=private_pem,
    )
    try:
        rows = platform.get_attendance(event_id)
    except (AttendanceImportError, FCCRequestError, EventNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    matched = match(rows, registrations, MatchEvent(event_id=event_id, salt=salt))
    threshold = EligibilityThreshold.from_config(cfg)
    eligible = eligible_attendees(matched, threshold)

    attendee = _find_attendee_by_fingerprint(
        eligible, event_id, salt, target_entry.fingerprint
    )
    if attendee is None:
        print(
            f"certificate {certificate_id} does not match any currently "
            f"eligible attendee for event {event_id} -- not enough "
            "attendance recorded to deliver it",
            file=sys.stderr,
        )
        return 1

    record: Mapping[str, Any] = {}
    with contextlib.suppress(EventNotFoundError):
        record = find_speaker(speaker_list, event_id)
    title = str(record.get("title", "") or "")
    event_date = str(record.get("date", "") or "")
    if not title or not event_date:
        if speaker_errors:
            print(
                f"{(DATA_DIR / 'speakers.yml').as_posix()}: "
                f"{'; '.join(speaker_errors)} -- refusing "
                "to sign a certificate naming no event and no date",
                file=sys.stderr,
            )
        else:
            print(
                f"no speaker record with both a title and a date matches "
                f"event {event_id} -- refusing to sign a certificate naming "
                "no event and no date",
                file=sys.stderr,
            )
        return 1

    event = CertificateEvent(event_id=event_id, title=title, date=event_date)
    _warn_if_title_truncated(event)
    capped_attendee = replace(
        attendee,
        duration_seconds=min(
            attendee.duration_seconds, threshold.seminar_duration_minutes * 60
        ),
    )
    try:
        # Sign `target_entry` -- the row
        # `CERTIFICATE_ID` actually named -- rather than calling `issue`,
        # which re-resolves by fingerprint and could hand back a
        # different row. That is a real defect this project has had: the
        # command named one certificate in its own log and delivered another.
        token = sign_for(target_entry, event, capped_attendee, signing_key)
        document = delivery.render_certificate(
            name=full_name(capped_attendee),
            event_title=event.title,
            event_date=event.date,
            duration_hours=duration_hours(capped_attendee.duration_seconds),
            identifier=target_entry.identifier,
            token=token,
        )
        message = delivery.compose(
            capped_attendee.registration,
            event.title,
            target_entry.identifier,
            document,
        )
        send_result = delivery.deliver(message, os.environ)
    except Exception:  # nobody is watching this job for a traceback
        print(
            f"certificate {certificate_id} could not be delivered for event "
            f"{event_id}, for a reason this job did not anticipate",
        )
        return 0

    if send_result.sent:
        print(f"certificate {certificate_id} delivered for event {event_id}")
    else:
        print(
            f"certificate {certificate_id} not delivered for event {event_id} "
            "-- no email transport configured or delivery failed; re-run "
            "this command to retry"
        )
    return 0
