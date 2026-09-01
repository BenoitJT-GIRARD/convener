"""The commands that destroy what this repository may no longer hold.

Ninety days after an event, the sweep deletes that event's private key and
records the destruction: the ciphertext stays in git forever and nothing
can ever read it again. `erase_registration` is the narrower, earlier
operation -- one person's own envelope, on their own request -- and it is
here because it reads the same registry the sweep writes.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

import yaml

from convener_ops.cli import step_output, store
from convener_ops.declaration.paths import (
    DATA_DIR,
    repo_root,
)
from convener_ops.declaration.yaml_safe import safe_load as yaml_safe_load
from convener_ops.governance.rule import PARIS, paris_today
from convener_ops.journey import (
    eventkeys,
)
from convener_ops.journey.platform import (
    ENCRYPTED_ATTENDANCE_FILENAME,
    EventNotFoundError,
    dump_attendance_export_file,
    erase_attendance_rows,
    find_speaker,
    load_attendance_export_file,
)
from convener_ops.journey.registration import (
    AmbiguousMatchingCodeError,
    Registration,
    dump_registration_file,
    erase,
    find_by_email,
    find_by_matching_code,
    load_registration_file,
    normalize_email,
)

#: The destruction registry holds only an event id and a date --
#: see tools/convener_ops/journey/eventkeys.py's module docstring, "the destruction
#: registry lives in one file".
DESTRUCTIONS_HEADER = (
    "# Event key destruction registry; see tools/convener_ops/journey/eventkeys.py\n"
)


def _load_destruction_registry(root: Path) -> tuple[dict[str, date], str | None]:
    """`(registry, None)` on success, `({}, message)` on a malformed
    committed file -- never raises, so both `retention_sweep` and
    `erase_registration` can print one line and return 1 the same way
    every other "closed shape" loader in this module already does. A
    *missing* file is not an error: no event has ever been destroyed yet,
    the ordinary state before the first retention sweep finds anything
    due (`eventkeys.registry_from_data(None)`)."""
    registry_path = eventkeys.destructions_path(root)
    if not registry_path.exists():
        return {}, None
    try:
        data = yaml_safe_load(registry_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return {}, f"{eventkeys.DESTRUCTIONS_PATH.as_posix()}: invalid YAML - {exc}"
    try:
        return eventkeys.registry_from_data(data), None
    except ValueError as exc:
        return {}, f"{eventkeys.DESTRUCTIONS_PATH.as_posix()}: {exc}"


def retention_sweep() -> int:
    """`convener-retention-sweep`: the job that makes this project's central
    retention promise true. Finds the id of every event whose window has elapsed
    (`eventkeys.is_due_for_destruction`: event date + 90 days, measured
    against `paris_today`) and whose key is not already on record as
    destroyed.

    **Computes only -- it does not write the registry and does not delete
    anything.** Writes `$GITHUB_OUTPUT`: `destroyed_ids` (comma-joined
    event ids), `destroyed_secrets` (the matching `CONVENER_EVENT_KEY_<ID>`
    names, `eventkeys.secret_name`), and `destroyed_on` (today's Paris
    date, ISO -- every event this run finds due shares one day). Three
    later, separate steps in `.github/workflows/retention.yml` read these:
    deleting the named secrets (`gh secret delete`), recording the
    destructions (`record_destructions`, below), and committing that
    record -- split out precisely so a *push* that has to retry after a
    rejected fast-forward re-runs only the pure, idempotent recording
    step, never `gh secret delete` a second time against a secret an
    earlier attempt already removed.

    **`CONVENER_RETENTION_TOKEN` absent fails this job outright, on
    every scheduled run, whether or not any event happens to be due for
    destruction today.** Every other secret in this codebase degrades to
    an ordinary D-13 absence -- a feature that does not run this time,
    reported and nothing more. This one does not: a retention job that
    exits green having destroyed nothing looks identical, from the
    Actions tab, to a retention job that genuinely had nothing to do --
    and the two must never be confused for a promise with legal weight.
    So this is checked, and fails, before anything else -- including
    before reading `instance/data/speakers.yml`, so a malformed data file is never
    what an operator sees first when the real problem is a missing
    credential. This function does not itself call the GitHub API with
    the token -- `retention.yml`'s own `gh secret delete` step does -- but
    its *presence* is checked here regardless, so the job fails at the
    first step rather than after computing a set of secrets nothing can
    then delete.

    A speaker record that cannot be found, or carries no usable `date`,
    for an event whose public key is still published is reported (one
    line, the event id only -- already public) and skipped rather than
    failing the whole run: one mis-recorded event must not block every
    other event's own, unrelated retention deadline from being honoured.
    """
    token = os.environ.get("CONVENER_RETENTION_TOKEN", "")
    if not token:
        print(
            "CONVENER_RETENTION_TOKEN is not configured -- destroying an event "
            "key requires a fine-grained personal access token, scoped to "
            "this repository, with the 'Secrets' permission set to "
            "read and write and nothing else (the default GITHUB_TOKEN "
            "cannot delete a repository secret). Without it this job "
            "cannot carry out the destruction the retention window "
            "promises, so it fails rather than exiting clean having "
            "destroyed nothing -- see docs/operating/operations.md, "
            "'Retention and early erasure'",
            file=sys.stderr,
        )
        return 1

    root = repo_root()
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    if errors:
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    speaker_list = speakers if isinstance(speakers, list) else []

    registry, registry_error = _load_destruction_registry(root)
    if registry_error:
        print(registry_error, file=sys.stderr)
        return 1

    today = paris_today(datetime.now(UTC))

    keys_dir = root / eventkeys.KEYS_DIR
    due: list[str] = []
    if keys_dir.is_dir():
        for pub_path in sorted(keys_dir.glob("*.pub")):
            event_id = pub_path.stem
            if event_id in registry:
                continue
            try:
                speaker_record = find_speaker(speaker_list, event_id)
            except EventNotFoundError:
                # ::warning::, because a skip nobody sees is exactly
                # the failure this guard exists to prevent -- the function's own
                # docstring argues a retention job that exits green having
                # destroyed nothing must never look, from the Actions tab,
                # like a job that genuinely had nothing to do; a plain
                # stderr line on an otherwise-green run is that same
                # confusion, for the far more likely cause (an
                # `edition_code` cleared, a speaker record deleted, a
                # mismatched `.pub` filename), not just a missing PAT.
                print(
                    f"::warning::no speaker record for event {event_id} -- "
                    "its retention deadline cannot be determined; skipped "
                    "this run",
                    file=sys.stderr,
                )
                continue
            try:
                event_date = date.fromisoformat(
                    str(speaker_record.get("date", "") or "")
                )
            except ValueError:
                print(
                    f"::warning::event {event_id} has no usable date -- its "
                    "retention deadline cannot be determined; skipped "
                    "this run",
                    file=sys.stderr,
                )
                continue
            if eventkeys.is_due_for_destruction(event_date, today):
                due.append(event_id)

    if not due:
        print("nothing due for destruction today")
        step_output.write(
            f"destroyed_ids=\ndestroyed_secrets=\ndestroyed_on={today.isoformat()}\n"
        )
        return 0

    secret_names = [eventkeys.secret_name(event_id) for event_id in due]
    print(f"due for destruction: {', '.join(due)}")
    step_output.write(
        f"destroyed_ids={','.join(due)}\n"
        f"destroyed_secrets={','.join(secret_names)}\n"
        f"destroyed_on={today.isoformat()}\n"
    )
    return 0


def record_destructions() -> int:
    """`convener-record-destructions`: write `instance/data/event-key-destructions.yml`
    with every id in `DESTROYED_IDS` (comma-joined, `retention_sweep`'s
    own `$GITHUB_OUTPUT`, or a hand-run operator recovering from a wedged
    sweep -- see `docs/operating/operations.md`, 'Retention and early
    erasure') recorded as destroyed on `DESTROYED_ON` (an ISO date; every
    event one sweep finds due shares one Paris day) -- factored out of
    `retention_sweep` itself so `retention.yml`'s commit-and-push retry
    loop can re-run *this* step alone after a rejected push resets the
    working tree, without ever repeating `gh secret delete` for a secret
    an earlier attempt already removed. Calling it twice for the same ids
    -- on the same day or a later one, as a genuine retry would -- writes
    the identical file: an id already in the registry keeps its existing
    date, never overwritten by whatever day the retry happens to run on
    (`eventkeys.destroy`'s own idempotence).

    **Calls `eventkeys.destroy`, not a bare `dict.setdefault`.**
    Every id `retention_sweep` itself ever
    produces already names a published key by construction, but this
    function is also `convener-record-destructions`, a console script an
    operator can and does run by hand after a wedged sweep -- reading a
    plain `DESTROYED_IDS` environment variable with no such guarantee.
    `destroy`'s own `key_was_published` guard
    (`public_key_path(event_id).exists()`) is exactly the missing
    validation: it refuses a typo'd or never-published id instead of
    writing a registry entry every reader then refuses. Its `ValueError`
    -- also raised for an id that is not even a legal token, the same
    `_validate_event_id` every other write path already goes through --
    is caught here and turned into an ordinary exit 1.

    **Only after every id above is durably written does this delete the
    published `.pub`.** `instance/keys/events/<id>.pub` is the
    signup relay's only "this event is open" gate
    (`services/signup-relay/src/index.js`); leaving it published after
    destruction lets a destroyed event keep accepting registrations that
    can never be decrypted or erased again. The order is load-bearing, not
    incidental: deleting the `.pub` *before* calling `destroy` would make
    its `key_was_published` guard see a key that looks never-published and
    refuse the destruction -- on every retry, forever, for exactly the ids
    this step exists to record. Deleting it *after* the registry write
    succeeds means a retry (the `.pub` already gone, the registry entry
    already there) takes the idempotent `destroy` branch and never
    consults `key_was_published` again -- safe either way, but the
    ordering below does not rely on that, it is correct on its own terms.
    `missing_ok=True` because an operator recovering by hand may be
    re-running this against a `.pub` an earlier, partial attempt already
    removed.

    A missing or malformed `DESTROYED_ON`, or a `instance/data/event-key-
    destructions.yml` that failed to parse, is reported and the run exits
    1 -- both mean this step cannot answer the one question it exists to
    answer (what day did this destruction happen), so it must not guess.
    An empty `DESTROYED_IDS` is not an error: `retention_sweep` writes it
    empty on an ordinary day nothing was due, and this step has nothing to
    record.

    **This function is all-or-nothing across `ids`, unlike the delete
    step above, which is per-event tolerant -- a deliberate
    asymmetry, not an oversight.** If recording aborts partway, the
    secrets already confirmed gone are simply left unrecorded; the next
    sweep finds those events still due, re-deletes secrets that are
    already absent (which the tolerance above makes safe), and records them then.
    """
    ids = [
        event_id
        for event_id in os.environ.get("DESTROYED_IDS", "").split(",")
        if event_id
    ]
    if not ids:
        print("no destroyed event ids to record")
        return 0

    destroyed_on_raw = os.environ.get("DESTROYED_ON", "").strip()
    try:
        destroyed_on = date.fromisoformat(destroyed_on_raw)
    except ValueError:
        print(
            f"DESTROYED_ON is not a valid date: {destroyed_on_raw!r}", file=sys.stderr
        )
        return 1

    root = repo_root()
    registry, registry_error = _load_destruction_registry(root)
    if registry_error:
        print(registry_error, file=sys.stderr)
        return 1

    # `destroy` is pure and wants a `datetime`, not the `date` this step
    # was handed; round-tripping through midnight Paris time gives back
    # exactly `destroyed_on` when `destroy` computes `paris_today` from it
    # for an id not already on record.
    now = datetime.combine(destroyed_on, time(), tzinfo=PARIS)
    for event_id in ids:
        try:
            key_was_published = eventkeys.public_key_path(event_id).exists()
            record = eventkeys.destroy(
                event_id, now, key_was_published=key_was_published, registry=registry
            )
        except ValueError as exc:
            print(
                f"cannot record the destruction of {event_id!r}: {exc}", file=sys.stderr
            )
            return 1
        registry[event_id] = record.destroyed_on

    registry_path = eventkeys.destructions_path(root)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        DESTRUCTIONS_HEADER + store.dump(eventkeys.registry_to_data(registry)),
        encoding="utf-8",
        newline="",
    )

    # See the docstring above: this comes last, deliberately, after the
    # registry write has already succeeded for every id.
    for event_id in ids:
        eventkeys.public_key_path(event_id).unlink(missing_ok=True)

    print(f"recorded {len(ids)} destruction(s): {', '.join(ids)}")
    return 0


def erase_registration() -> int:
    """`convener-erase-registration`: rewrite `registrations.enc` without the
    one entry an early erasure request names: the encrypted file is
    rewritten without that record, by a procedure that is documented and
    tested.

    **Identifies the registration by `MATCHING_CODE` in preference to
    `EMAIL_ENVELOPE`.** The code is already in the participant's
    own confirmation e-mail and is recomputed and compared
    against every stored entry (`registration.find_by_matching_code`),
    never reversed out of anything stored -- nothing here stores it.
    `EMAIL_ENVELOPE` is accepted as a fallback for a participant who no
    longer has that e-mail: the same **deliberate, documented exception**
    `resend_confirmation` above already makes for the identical reason.

    `EMAIL_ENVELOPE` used to be `REGISTRATION_EMAIL`,
    a bare address rendered and retained on the run page for as long as
    the run's history exists -- the erasure command manufacturing a
    fresh, permanent, plaintext copy of the exact address it exists to
    erase, which is the sharpest way D-24 can be broken. `EMAIL_ENVELOPE`
    is that same address hybrid-encrypted under this event's own public
    key instead (`eventkeys.encrypt`, produced on an operator's own
    machine by `convener-encrypt-identifier`, needing no secret); this
    function decrypts it with `EVENT_PRIVATE_KEY` -- already required
    below for the erasure itself -- and the plaintext never exists
    anywhere but this job's own memory. Both `MATCHING_CODE` and
    `EMAIL_ENVELOPE` may be supplied; the code is tried first.

    **A code collision is resolved by the address, if one was
    also given and it narrows the tie to exactly one entry** -- reading
    the evidence the requester supplied is not guessing, so this proceeds;
    with no address, or an address that does not narrow the tie, this
    refuses rather than pick one (`AmbiguousMatchingCodeError`, whose own
    docstring carries the full reasoning).

    **Checked before anything else touches disk: has this event's key
    already been destroyed?** `instance/data/event-key-destructions.yml` is read
    first, and if it already names `event_id`, this prints the destruction
    date on record and returns 0 -- demonstrable, not merely asserted:
    proved from the committed registry, and
    the request is already satisfied (there is nothing left that could be
    erased). An event id that is not known to this repository at all (no
    `instance/keys/events/<id>.pub`, and no destruction on record either) is
    refused instead -- that is not "already erased", it names nothing this
    repository ever registered.

    **Unless `EVENT_PRIVATE_KEY` is supplied anyway.** A key
    that still opens `registrations.enc` for an event this registry
    already calls destroyed contradicts the one thing this command exists
    to prove -- "there is nothing left" would then be an assertion, not a
    demonstration, and this command exists to demonstrate. So that
    contradiction refuses loudly (exit 1) rather than confirming "nothing
    to erase" over it; a caller with nothing to prove wrong simply omits
    `EVENT_PRIVATE_KEY`, the ordinary case.
    """
    event_id = os.environ.get("EVENT_ID", "").strip()
    try:
        eventkeys.secret_name(event_id)
    except ValueError:
        print("no valid event id supplied", file=sys.stderr)
        return 1

    root = repo_root()
    registry, error = _load_destruction_registry(root)
    if error:
        print(error, file=sys.stderr)
        return 1

    destroyed_on = registry.get(event_id)
    if destroyed_on is not None:
        if os.environ.get("EVENT_PRIVATE_KEY", ""):
            print(
                f"event {event_id} is on record as destroyed on "
                f"{destroyed_on.isoformat()}, but a private key was "
                "supplied for it -- refusing rather than trusting a "
                "registry a working key contradicts",
                file=sys.stderr,
            )
            return 1
        print(
            f"nothing to erase for event {event_id}: its key was destroyed "
            f"on {destroyed_on.isoformat()}, and every registration for "
            "this event has been permanently unreadable since"
        )
        return 0

    if not eventkeys.public_key_path(event_id).exists():
        print(f"event {event_id} is not known to this repository", file=sys.stderr)
        return 1

    code = os.environ.get("MATCHING_CODE", "").strip()
    envelope = os.environ.get("EMAIL_ENVELOPE", "").strip()
    if not code and not envelope:
        print("no matching code or encrypted identifier supplied", file=sys.stderr)
        return 1

    private_pem = os.environ.get("EVENT_PRIVATE_KEY", "")
    if not private_pem:
        print(f"no private key configured for event {event_id}", file=sys.stderr)
        return 1

    email = ""
    if envelope:
        try:
            email = eventkeys.decrypt(private_pem, envelope).decode("utf-8").strip()
        except (eventkeys.DecryptionError, UnicodeDecodeError):
            # D-25: refuse loudly rather than silently treating an
            # undecryptable envelope the same as "no address supplied" --
            # those are different facts, and folding them together would
            # let a mistyped or stale envelope look like a plain refusal
            # to identify anyone.
            print(
                "the supplied encrypted identifier could not be decrypted",
                file=sys.stderr,
            )
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

    target: Registration | None = None
    if code:
        salt = os.environ.get("CONVENER_MATCHING_SALT")
        try:
            target = find_by_matching_code(current, event_id, code, salt, private_pem)
        except AmbiguousMatchingCodeError as exc:
            # A collision on the code alone must refuse -- but if an
            # address was also supplied and it narrows the tied
            # entries to exactly one, that is evidence in hand, not a
            # guess: using it is the right side of the same rule that
            # refuses when there is nothing else to go on.
            resolved: Registration | None = None
            if email:
                wanted_email = normalize_email(email)
                narrowed = [
                    candidate
                    for candidate in exc.tied
                    if normalize_email(candidate.email) == wanted_email
                ]
                if len(narrowed) == 1:
                    resolved = narrowed[0]
            if resolved is None:
                print(str(exc), file=sys.stderr)
                return 1
            target = resolved
    if target is None and email:
        target = find_by_email(current, email, private_pem)
    if target is None:
        print(f"no registration found for event {event_id}", file=sys.stderr)
        return 1

    updated, removed = erase(current, target.email, private_pem)
    if not removed:
        print(f"no registration found for event {event_id}", file=sys.stderr)
        return 1

    # This early erasure request has to
    # remove the same person's rows from the committed attendance export
    # too, or "erased" is no longer true -- an early erasure exists
    # precisely to beat the +90-day key destruction, and before this fix
    # the export's own copy would have survived it untouched. Read
    # (before either file is written) so a malformed attendance file
    # refuses the whole request rather than reporting success over a
    # write it could not actually make -- the same "say it only once it
    # is true" discipline this fix exists to restore.
    attendance_path = (
        root / DATA_DIR / "events" / event_id / ENCRYPTED_ATTENDANCE_FILENAME
    )
    attendance_rows_removed = 0
    updated_attendance_file = None
    if attendance_path.exists():
        try:
            attendance_file = load_attendance_export_file(
                attendance_path.read_text(encoding="utf-8")
            )
        except ValueError as exc:
            print(
                f"{attendance_path.relative_to(root).as_posix()}: {exc}",
                file=sys.stderr,
            )
            return 1
        updated_attendance_file, attendance_rows_removed = erase_attendance_rows(
            attendance_file, target.email, private_pem
        )

    enc_path.write_text(dump_registration_file(updated), encoding="utf-8", newline="")
    if attendance_rows_removed and updated_attendance_file is not None:
        attendance_path.write_text(
            dump_attendance_export_file(updated_attendance_file),
            encoding="utf-8",
            newline="",
        )

    attendance_note = (
        f"; {attendance_rows_removed} attendance row(s) also removed"
        if attendance_rows_removed
        else ""
    )
    print(
        f"erased a registration for event {event_id} ({len(updated.entries)} "
        f"remain){attendance_note}"
    )
    return 0
