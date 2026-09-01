"""The commands that carry a registration from the queue to a confirmation.

A registration arrives as ciphertext, waits in the queue branch, is
drained into the store, and is answered by a confirmation carrying the
matching code its holder will need later. The commands that erase one, or
name one without naming a person, are here too: `convener-encrypt-
identifier` exists so that an operator dispatching a workflow pastes
ciphertext into the form rather than somebody's address.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

from convener_ops.cli import step_output, store
from convener_ops.cli.journey.event import (
    survey_enabled,
)
from convener_ops.declaration.paths import (
    DATA_DIR,
    repo_root,
)
from convener_ops.declaration.yaml_safe import safe_load as yaml_safe_load
from convener_ops.journey import (
    confirmation,
    eventkeys,
    registration_routing,
    submission_queue,
)
from convener_ops.journey.platform import (
    Room,
)
from convener_ops.journey.platform_fcc import (
    platform_from_env,
)
from convener_ops.journey.registration import (
    Registration,
    dump_registration_file,
    event_id_from_payload,
    find_by_email,
    load_registration_file,
    matching_code,
    to_registration,
    upsert,
)
from convener_ops.maintenance import (
    queue_watch,
)

#: Which queue entries a drain has already applied, so a
#: drain that committed its result and was then interrupted before clearing
#: the queue does not apply them a second time. Committed in the *same*
#: commit as the data those entries produced, which is the whole of why it
#: works; see tools/convener_ops/journey/submission_queue.py's own module docstring.
QUEUE_LEDGER_HEADER = (
    "# Which queued submissions a drain has already applied; "
    "see tools/convener_ops/journey/submission_queue.py\n"
)


def registration_routing_public_data() -> int:
    """`convener-registration-routing-public-data`: rebuild
    `instance/public-data/registration-routing.json` from
    `instance/data/speakers.yml` and `instance/registration-lanes.yml` --
    `survey_status_public_data`'s own precedent above, for a third consumer
    and a third question.

    What it publishes is one already-resolved instant per event: the moment
    that event stops being far enough away for a registration to wait for
    the daily drain. `services/signup-relay` reads it through the Contents
    API, with the credential and the call shape it already uses for
    `instance/keys/events/<id>.pub` and
    `instance/public-data/survey-status.json`, and its whole share of the
    rule becomes one comparison against the clock. Every
    piece of arithmetic that has a project decision in it -- Europe/Paris,
    the standing start, the configured threshold -- happens here, in the
    language it already lives in.

    Deliberately its own file and its own command rather than a field folded
    into `survey-status.json`, for that file's own stated reason: the two
    answer different questions for different readers, and a consumer that
    checks membership in a list of ids must not have to know about a
    mapping of instants to do it.

    Returns 1, printing why, on a `instance/registration-lanes.yml` this code
    cannot read as the shape it knows. Never a default: a threshold guessed
    at is a threshold that could route a last-minute registrant into a queue
    they cannot afford to wait in, and a red build is the cheap version of
    finding that out.
    """
    root = repo_root()
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    config_data, config_errors = store.load(root / registration_routing.CONFIG_PATH)
    if errors or config_errors:
        for error in errors + config_errors:
            print(f"  - {error}")
        return 1
    try:
        threshold = registration_routing.threshold_from_data(config_data)
    except ValueError as exc:
        print(f"  - {exc}")
        return 1

    data = registration_routing.to_routing_data(speakers or [], threshold)
    out_path = root / registration_routing.ROUTING_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {len(data['queue_until'])} event(s) whose registrations may "
        f"wait for the drain more than {threshold}h before they start"
    )
    return 0


def _send_confirmation(
    event_id: str, registration: Registration, changed: Sequence[str]
) -> None:
    """Compose and attempt to deliver the confirmation for `registration`,
    then print exactly one line naming the event id (already public) and
    the outcome -- never the registration's own fields, and never the
    composed message. See `confirmation.py`'s module docstring for the
    reasoning.

    **Reported, not retained.** An unsent
    confirmation used to be written to a `.gitignore`d file and uploaded as
    a 14-day build artefact -- `docs/handbook/governance/traitement-donnees.md`'s
    own Recipients section named this an exception, but with
    `email_transport` unconfigured (this project's default state) it was
    the path *every* registration took, not an exception at all. Removed
    outright, the same way `delivery.py` already handles an unsent
    certificate (that module's own docstring, "never written to disk"):
    `confirmation.deliver` hands back only `SendResult.sent`, nothing else
    to write anywhere, and this function prints that a confirmation could
    not be sent and names the recovery -- `convener-resend-confirmation`
    reproduces the identical message from the *stored* registration, so
    nothing composed here is ever the only copy of anything.

    `changed` is the field labels the caller already worked out
    (`confirmation.changed_fields`) -- this function does not compute it,
    so `resend_confirmation` (always `changed=()`) and `send_confirmation`
    (a fresh or updated registration) share one code path with no branch of
    their own in here.

    Never lets a room lookup that fails (`confirmation.EventNotFoundError`
    -- no speaker record matches `event_id`) stop the confirmation from
    being composed and sent: the caller already holds the registration
    itself, and a missing speaker record must not lose the message too.
    The message that goes out in that case simply has no room link, which
    the print line below says plainly.

    Nothing in this function is allowed to raise past it: the whole body,
    not only the compose-and-deliver sequence, is wrapped in one broad
    `except Exception`. That catch is no longer a defence against `set -e`
    aborting a commit: sending is a
    separate, non-retried step from storing, so a failure here can no
    longer reach back and threaten a registration already on the branch by
    the time this runs. It stays for the same reason `notify.py`'s own
    functions are documented as never raising: both this function's
    callers -- `send_confirmation` (an unattended job step) and
    `resend_confirmation` (a volunteer's manual run) -- are contexts
    nobody is watching for a Python traceback, and this turns whatever
    goes wrong into the one sentence a reader actually needs, instead:
    that the confirmation failed for a reason this job did not anticipate,
    and that a resend, once the reason is understood, is how to recover.
    Every failure this function already anticipates -- no room, no
    transport, a transport that raises -- is handled above the broad catch
    and never reaches it; it exists for what nobody anticipated.
    """
    try:
        root = repo_root()
        speakers, _errors = store.load(root / DATA_DIR / "speakers.yml")
        cfg, _errors = store.load(root / DATA_DIR / "config.yml")
        speaker_list = speakers if isinstance(speakers, list) else []
        config_map = cfg if isinstance(cfg, dict) else None
        platform = platform_from_env(os.environ, speaker_list, config_map)

        try:
            event = confirmation.event_details(speaker_list, event_id, platform)
        except confirmation.EventNotFoundError:
            print(
                f"no speaker record matches event {event_id} -- confirmation "
                "composed with no room link"
            )
            event = confirmation.EventDetails(
                title="", date="", room=Room(join_url="", instructions="")
            )

        salt = os.environ.get("CONVENER_MATCHING_SALT")
        code = matching_code(event_id, registration.email, salt)
        message = confirmation.compose(registration, event, code, changed)
        result = confirmation.deliver(message, os.environ)

        if result.sent:
            print(f"confirmation for event {event_id} sent")
            return

        print(
            f"confirmation for event {event_id} not sent -- no email "
            f"transport configured or delivery failed; run "
            f"convener-resend-confirmation for this registrant once the reason "
            f"is understood"
        )
    except Exception:  # deliberately broad -- see the docstring above
        print(
            f"confirmation for event {event_id} could not be composed or "
            "sent, for a reason this job did not anticipate; the "
            "registration itself is already stored"
        )


def resolve_registration_secret() -> int:
    """`convener-registration-secret-name`: the first of the three steps
    `.github/workflows/registration.yml` runs for one incoming
    registration.

    GitHub Actions can only select a *secret* through an expression
    evaluated in the workflow file itself (`secrets[...]`), never from
    inside a running step -- there is no way to hand a step "the secret
    named by this string I just computed". So this step's only job is to
    read `event_id` out of the dispatch payload and hand back the *name*
    of the secret that holds that event's private key -- never the key
    itself, which this step never touches -- for the other two steps'
    `env:` blocks to look up by (`convener-handle-registration` and
    `convener-send-confirmation` both need it). Written to `$GITHUB_OUTPUT` via
    `step_output.write`; printed to stdout instead when `$GITHUB_OUTPUT`
    is unset (a run outside Actions), the same "inspectable instead of
    silent" idiom `_notify` uses for its own absent channel.

    Neither line carries anything a stranger could not already read from
    the repository: `event_id` is public (`instance/keys/events/<id>.pub` names it
    openly) and `secret_name` is a *name*, not a value.
    """
    payload = os.environ.get("REGISTRATION_PAYLOAD", "")
    event_id = event_id_from_payload(payload)
    if event_id is None:
        print("no valid event id in the registration payload", file=sys.stderr)
        return 1

    step_output.write(
        f"event_id={event_id}\nsecret_name={eventkeys.secret_name(event_id)}\n"
    )
    return 0


def handle_registration() -> int:
    """`convener-handle-registration`: the second of the three steps
    `.github/workflows/registration.yml` runs -- decrypt one registration
    and store it re-encrypted in `instance/data/events/<id>/registrations.enc`.

    The confirmation itself is sent by a *separate* step
    (`convener-send-confirmation`, gated `if: success()` so it runs at most once
    per job, only after this step's own push-retry loop has actually
    landed the record on the branch). Split this way on review: this
    step's workflow retries on a rejected push,
    re-running the whole step up to three times, and a step that both
    stored and sent would send one confirmation per attempt -- or, worse,
    send one for a registration a later, failed attempt then discarded.

    Reads `REGISTRATION_PAYLOAD` (the raw relayed body -- see
    `convener_ops.journey.registration.to_registration` for why it is passed through
    whole) and `EVENT_PRIVATE_KEY` (the PEM the workflow selected using
    `resolve_registration_secret`'s own output). Never prints either of
    them, or anything decrypted from them: every message below names only
    the event id -- already public, the same identifier every workflow run
    and every `instance/keys/events/<id>.pub` filename already carry in the clear
    -- and a count.

    An absent `EVENT_PRIVATE_KEY` is not D-13's normal state here, the same
    exception `eventkeys.py`'s module docstring names: this job exits in
    error rather than doing anything at all with the ciphertext it was
    handed, the same as a genuinely undecryptable one.

    Writes `changed=<comma-joined field labels>` to `$GITHUB_OUTPUT` -- the
    diff between the prior stored registration (read via
    `find_by_email`, before `upsert` overwrites it) and this one, for
    `send_confirmation` to read back and hand to `confirmation.compose`
    unchanged. Field labels are not personal data (that is the whole point
    of naming rather than quoting), so this is the one thing this
    function ever writes anywhere a stranger could, in principle, also
    read.
    """
    payload = os.environ.get("REGISTRATION_PAYLOAD", "")
    event_id = event_id_from_payload(payload)
    if event_id is None:
        print("no valid event id in the registration payload", file=sys.stderr)
        return 1

    private_pem = os.environ.get("EVENT_PRIVATE_KEY", "")
    if not private_pem:
        print(f"no private key configured for event {event_id}", file=sys.stderr)
        return 1

    registration = to_registration(payload, private_pem)
    if registration is None:
        # The survey twin's own fix, applied here: "could not be read",
        # not "could not be decrypted". to_registration's own uniform None
        # folds a missing
        # field, a wrong type, an empty required field or a field over
        # _MAX_FIELD_LENGTH into the same outcome as an undecryptable one --
        # correct for the untrusted-input reason its own docstring gives --
        # but this operator-facing line named only the narrowest,
        # sometimes-wrong cause. A participant whose institution tripped
        # the length cap deserves an honest "could not be read", not a
        # claim about decryption that did not happen to fail.
        print(f"registration for event {event_id} could not be read", file=sys.stderr)
        return 1

    root = repo_root()
    rel_path = DATA_DIR / "events" / event_id / "registrations.enc"
    enc_path = root / rel_path
    existing_text = enc_path.read_text(encoding="utf-8") if enc_path.exists() else None
    try:
        current = load_registration_file(existing_text)
    except ValueError as exc:
        print(f"{rel_path.as_posix()}: {exc}", file=sys.stderr)
        return 1

    old = find_by_email(current, registration.email, private_pem)
    updated, replaced = upsert(current, registration, private_pem=private_pem)
    enc_path.parent.mkdir(parents=True, exist_ok=True)
    enc_path.write_text(dump_registration_file(updated), encoding="utf-8", newline="")

    verb = "updated" if replaced else "recorded"
    print(f"{verb} a registration for event {event_id} ({len(updated.entries)} total)")

    changed = confirmation.changed_fields(old, registration) if old is not None else ()
    step_output.write(f"changed={','.join(changed)}\n")
    return 0


def send_confirmation() -> int:
    """`convener-send-confirmation`: the third of the three steps
    `.github/workflows/registration.yml` runs -- and the only one gated
    `if: success()`, so it runs at most once per job, only once
    `convener-handle-registration`'s own push-retry loop has actually landed
    the record on the branch. See `handle_registration`'s own docstring
    for why sending was split into its own step.

    Reads `REGISTRATION_PAYLOAD` and `EVENT_PRIVATE_KEY` again -- the
    workflow already holds both for the step that ran before this one, so
    reading them again here needs no new secret -- and decrypts the
    registration a second time. Not wasted work an oversight left behind:
    the registration's plaintext lives only in one process's memory at a
    time (this project's whole design; `registration.py`'s own module
    docstring), so a later step that needs it again has no way to ask for
    it except by decrypting it again from the same ciphertext, exactly as
    `resend_confirmation` already does for a manual resend.

    `CHANGED_FIELDS` is the comma-joined field labels
    `handle_registration` wrote to `$GITHUB_OUTPUT` as `changed=...`, read
    back here and split on the comma -- safe because none of
    `confirmation.FIELD_LABELS`'s values ever contains one. An empty
    string (a first registration, or an update that changed nothing this
    module tracks) splits to nothing, `changed=()`, the same empty tuple a
    resend always passes.
    """
    payload = os.environ.get("REGISTRATION_PAYLOAD", "")
    event_id = event_id_from_payload(payload)
    if event_id is None:
        print("no valid event id in the registration payload", file=sys.stderr)
        return 1

    private_pem = os.environ.get("EVENT_PRIVATE_KEY", "")
    if not private_pem:
        print(f"no private key configured for event {event_id}", file=sys.stderr)
        return 1

    registration = to_registration(payload, private_pem)
    if registration is None:
        # See handle_registration's own
        # identical comment above -- the same wrong claim, at the second
        # of the two call sites it was found at.
        print(f"registration for event {event_id} could not be read", file=sys.stderr)
        return 1

    changed = tuple(
        field for field in os.environ.get("CHANGED_FIELDS", "").split(",") if field
    )
    _send_confirmation(event_id, registration, changed)
    return 0


def resend_confirmation() -> int:
    """`convener-resend-confirmation`: re-send the confirmation already on file
    for one address, without regenerating anything -- the manual resend the
    risk of silent loss asks for: a confirmation in a spam folder does not
    exist.

    Reads `EVENT_ID` -- a plain, operator-typed value -- and
    `EMAIL_ENVELOPE`: not the address itself, but that address hybrid-
    encrypted under this event's own public key (`eventkeys.encrypt`,
    the identical wire format a browser already produces for a
    registration), the same shape `convener-encrypt-identifier` exists to
    produce on an operator's own machine. `EVENT_PRIVATE_KEY` is the same
    per-event secret `handle_registration` reads, and is what this
    function decrypts `EMAIL_ENVELOPE` with -- nothing here can recover an
    address from `EMAIL_ENVELOPE` alone.

    `EMAIL_ENVELOPE` used to be `REGISTRATION_EMAIL`,
    a bare address: GitHub renders and retains a `workflow_dispatch`
    input's own value on the run page for as long as the run's history
    exists, which manufactured a fresh, permanent, plaintext copy of the
    address every single resend -- the identical exposure
    `erase-registration.yml`'s own fallback carried. `registration.py`'s own
    module docstring still explains why no other identifier for one
    registration is stored at all ("No stored identifier for whose entry
    is this"), so an address is still the only handle a resend can name a
    registration by -- but D-24 requires it never sit on the run page in
    the clear, and ciphertext is what closes that without giving up the
    handle: only the CI job holding `EVENT_PRIVATE_KEY` can ever turn
    `EMAIL_ENVELOPE` back into the address it names.

    Finds the one entry for the decrypted address in `registrations.enc`
    (`registration.find_by_email`) and re-composes the message
    `_send_confirmation` would have composed for it, with `changed=()`: a
    resend repeats the current, stored registration -- it does not
    describe an update to it, even if the stored registration is itself
    the result of one.

    Nothing here is regenerated: `matching_code` is a pure function of the
    event id, the address and `CONVENER_MATCHING_SALT` (see its own docstring),
    so calling it again reproduces exactly the code the original
    confirmation carried, with nothing stored anywhere to look it up from
    instead. A resend that produced a *different* code would make the
    first message a lie about which code is current.
    """
    event_id = os.environ.get("EVENT_ID", "").strip()
    try:
        eventkeys.secret_name(event_id)
    except ValueError:
        print("no valid event id supplied", file=sys.stderr)
        return 1

    envelope = os.environ.get("EMAIL_ENVELOPE", "").strip()
    if not envelope:
        print("no encrypted identifier supplied", file=sys.stderr)
        return 1

    private_pem = os.environ.get("EVENT_PRIVATE_KEY", "")
    if not private_pem:
        print(f"no private key configured for event {event_id}", file=sys.stderr)
        return 1

    try:
        email = eventkeys.decrypt(private_pem, envelope).decode("utf-8").strip()
    except (eventkeys.DecryptionError, UnicodeDecodeError):
        # D-25: a supplied identifier this job cannot read must refuse
        # loudly, not silently fall through to "no registration found" --
        # the two causes (wrong identifier, undecryptable identifier) are
        # not the same fact and must not be reported as though they were.
        print(
            "the supplied encrypted identifier could not be decrypted", file=sys.stderr
        )
        return 1
    if not email:
        print("the supplied encrypted identifier is empty", file=sys.stderr)
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

    registration = find_by_email(current, email, private_pem)
    if registration is None:
        print(f"no registration found for event {event_id}", file=sys.stderr)
        return 1

    _send_confirmation(event_id, registration, ())
    return 0


def encrypt_identifier() -> int:
    """`convener-encrypt-identifier`: turn a registrant's own e-mail address
    into the ciphertext `resend-confirmation.yml`'s and
    `erase-registration.yml`'s own `encrypted_identifier` input both
    expect -- closing the class rather than the one instance.

    D-24: an operator command names a record, never a person. Both
    workflows' own declared exception lets a participant who lost their
    confirmation e-mail -- and, with it, their own matching code -- be
    resolved by address instead, but a raw address typed straight into a
    `workflow_dispatch` input is rendered and permanently retained on
    that run's own page, for anyone with repository read access, for as
    long as the run's history exists. This command closes that without
    giving up the fallback: it reuses `eventkeys.encrypt`, the identical
    hybrid construction a browser already performs client-side for a
    registration itself, so the value an operator pastes into the
    dispatch form is ciphertext -- decryptable only by whichever CI job
    later holds this event's own `EVENT_PRIVATE_KEY`, the same secret
    that already never leaves a job's own environment (`eventkeys.py`'s
    own module docstring).

    Runs entirely outside continuous integration, on an operator's own
    machine, against the event's already-published public key
    (`instance/keys/events/<id>.pub`) -- needs no secret at all: encrypting under
    a public key is exactly the operation a stranger with no account
    could already perform (the same reasoning
    `encrypt_attendance_export`'s own docstring gives for its identical
    "no secret needed" shape).

    Reads `EVENT_ID` and `REGISTRATION_EMAIL` -- both plain, operator-
    typed values on the operator's own terminal, never inside a CI job
    and never written to any file this command controls. Refuses (exit
    1) when the event id is not shaped like one, when no public key has
    been published for it yet, or when `REGISTRATION_EMAIL` is empty.
    Prints the resulting envelope -- `eventkeys.encrypt`'s own compact
    JSON, one line -- to stdout and nothing else, for the operator to
    copy into the workflow's own `encrypted_identifier` field.
    """
    event_id = os.environ.get("EVENT_ID", "").strip()
    try:
        eventkeys.secret_name(event_id)
    except ValueError:
        print("no valid event id supplied", file=sys.stderr)
        return 1

    email = os.environ.get("REGISTRATION_EMAIL", "").strip()
    if not email:
        print("no e-mail address supplied", file=sys.stderr)
        return 1

    public_path = eventkeys.public_key_path(event_id)
    if not public_path.exists():
        print(f"no public key published for event {event_id}", file=sys.stderr)
        return 1

    public_pem = public_path.read_text(encoding="utf-8")
    print(eventkeys.encrypt(public_pem, email.encode("utf-8")))
    return 0


#: Where the queue step leaves what it exported from `QUEUE_BRANCH` -- a
#: directory holding `queue/<kind>/<id>.json`, outside the checkout so a
#: queued entry can never be committed to the default branch by accident.
#: Set by the workflow; both commands below refuse to guess it.
QUEUE_DIR_ENV: Final = "CONVENER_QUEUE_DIR"


#: Where `drain_queue` writes the entry names the clearing step must remove
#: from `QUEUE_BRANCH`, one per line. A file rather than a step output
#: because a drain of two hundred entries would run past what an output can
#: hold, and because the clearing step must read exactly what the drain
#: acted on -- not recompute it.
QUEUE_CLEAR_ENV: Final = "CONVENER_QUEUE_CLEAR_FILE"


#: Where `drain_queue` writes the registrations whose confirmation still has
#: to go out -- one `<entry name><tab><comma-joined changed labels>` line per
#: registration -- and where `confirm_queued_registrations` reads them back
#: from, after the drain's commit has actually been pushed.
#:
#: A file for the same two reasons as `QUEUE_CLEAR_ENV`, and one more: the
#: only things on a line are a queue entry path and field *labels*
#: (`confirmation.FIELD_LABELS`, never a value), so nothing here is personal
#: data even though it crosses between two steps of a job whose log a
#: volunteer can read. That is the same property `registration.yml` relies on
#: when it passes `changed` between its own two steps as a step output.
QUEUE_CONFIRM_ENV: Final = "CONVENER_QUEUE_CONFIRM_FILE"


#: The separator on a line of that file. A tab, because a queue entry path
#: is `queue/<kind>/<id>.json` (no tabs by construction, `ENTRY_ID_RE`) and
#: `confirmation.FIELD_LABELS`' own values contain neither tabs nor commas.
_CONFIRM_FIELD_SEPARATOR: Final = "\t"


#: Where `drain_queue` writes the entries it could **not** finish and the
#: reason for each -- one `<entry name><tab><reason>` line -- and where
#: `record_queue_watch` reads them back from.
#:
#: A third cross-step file rather than a step output, for the first of
#: `QUEUE_CLEAR_ENV`'s two reasons: a drain that deferred two hundred
#: entries would run past what an output can hold. Nothing on a line but a
#: queue entry path, an event id and a repository path -- the same
#: already-public identifiers `submission_queue.Note` is documented to be
#: limited to, which is what lets this reach a committed record and a
#: comment on the board's thread.
QUEUE_DEFERRED_ENV: Final = "CONVENER_QUEUE_DEFERRED_FILE"


#: The separator on a line of the deferral file. A tab, for
#: `_CONFIRM_FIELD_SEPARATOR`'s own reason; named separately because the
#: two files carry different things, and one shared constant would make a
#: change to either silently reshape the other.
DEFERRED_FIELD_SEPARATOR: Final = "\t"


def _queue_entries(root: Path) -> dict[str, str]:
    """Every queue entry under `root`, keyed by its path inside
    `QUEUE_BRANCH` (`queue/<kind>/<id>.json`).

    Reads every file it finds, whatever its name or depth, rather than only
    the ones shaped like an entry: `submission_queue.read_entry` is what
    decides an entry is unusable, and it says so loudly. A reader that
    silently skipped an odd filename would turn a misplaced submission into
    a submission that never existed.
    """
    entries: dict[str, str] = {}
    if not root.is_dir():
        return entries
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            entries[path.relative_to(root).as_posix()] = path.read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeDecodeError):
            # Unreadable bytes are not a reason to lose the rest of the
            # queue. Recorded as an entry that cannot be read at all, which
            # `read_entry` refuses by name on the run.
            entries[path.relative_to(root).as_posix()] = ""
    return entries


def _queue_ledger(root: Path) -> tuple[frozenset[str], str | None]:
    """`(ledger, None)`, or `(empty, message)` on a committed file that will
    not parse -- never raises, the same shape `_load_destruction_registry`
    already has. A *missing* file means no drain has ever run, which is the
    empty ledger and not an error."""
    path = root / submission_queue.LEDGER_PATH
    if not path.exists():
        return frozenset(), None
    try:
        data = yaml_safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return (
            frozenset(),
            f"{submission_queue.LEDGER_PATH.as_posix()}: invalid YAML - {exc}",
        )
    try:
        return submission_queue.ledger_from_data(data), None
    except ValueError as exc:
        return frozenset(), f"{submission_queue.LEDGER_PATH.as_posix()}: {exc}"


@dataclass(frozen=True)
class _QueueSnapshot:
    """What both commands below read before they do anything: the queue as
    it was exported, the committed ledger, and the plan the two imply.
    `error` is a message when something is wrong enough that draining would
    be worse than not draining -- an unset queue directory, or a ledger that
    will not parse, which would otherwise be read as "nothing has ever been
    handled" and re-apply every entry an earlier drain already did."""

    plan: submission_queue.DrainPlan
    entries: dict[str, str]
    ledger: frozenset[str]
    error: str | None


def _queue_snapshot(root: Path) -> _QueueSnapshot:
    """Read the queue and the ledger, and plan against both."""
    queue_dir = os.environ.get(QUEUE_DIR_ENV, "")
    if not queue_dir:
        return _QueueSnapshot(
            submission_queue.DrainPlan(), {}, frozenset(), f"{QUEUE_DIR_ENV} is not set"
        )
    entries = _queue_entries(Path(queue_dir))
    ledger, error = _queue_ledger(root)
    if error is not None:
        return _QueueSnapshot(submission_queue.DrainPlan(), entries, ledger, error)
    plan = submission_queue.plan_drain(
        entries, ledger, lambda event_id: survey_enabled(root, event_id)
    )
    return _QueueSnapshot(plan, entries, ledger, None)


def plan_queue_drain() -> int:
    """`convener-plan-queue-drain`: name the secrets today's drain will need.

    Writes `pending`, and `event_1..N` / `secret_1..N` for
    `submission_queue.MAX_EVENTS_PER_DRAIN` slots, to `$GITHUB_OUTPUT`. An
    unused slot is the empty string on both, and `${{ secrets[''] }}`
    resolves to the empty string rather than failing -- which is how one
    fixed set of expressions serves a drain of one event and a drain of
    eight.

    Prints only counts and event ids. An event id is already public (it
    names a `instance/keys/events/<id>.pub` this repository publishes); nothing a
    submitter wrote can reach this command at all, because nothing here
    decrypts.
    """
    root = repo_root()
    snapshot = _queue_snapshot(root)
    if snapshot.error is not None:
        print(f"::error::{snapshot.error}", file=sys.stderr)
        return 1
    plan, entries = snapshot.plan, snapshot.entries

    # `pending` is "is there anything at all to do", not "is there anything
    # to handle". Three states beyond a fresh submission need the drain
    # step to run: entries an earlier drain handled but could not clear
    # (they have to be cleared now), entries it will refuse (same), and an
    # empty queue with a non-empty ledger (the ledger has to be pruned, or
    # it grows for ever). Only a queue *and* a ledger that are both empty
    # mean a drain would do nothing at all -- and then nothing runs, and no
    # commit is made.
    pending = bool(entries) or bool(snapshot.ledger)
    lines = [f"pending={'true' if pending else 'false'}\n"]
    names = submission_queue.secret_names(plan)
    for slot, secret in enumerate(names, start=1):
        event_id = plan.event_ids[slot - 1] if slot <= len(plan.event_ids) else ""
        lines.append(f"event_{slot}={event_id}\nsecret_{slot}={secret}\n")
    step_output.write("".join(lines))

    print(
        f"{len(entries)} entrie(s) in the queue: {len(plan.handle)} to handle "
        f"across {len(plan.event_ids)} event(s), {len(plan.refused)} to refuse, "
        f"{len(plan.deferred)} left waiting, {len(plan.already_handled)} already "
        "handled by an earlier drain"
    )
    return 0


def drain_queue() -> int:
    """`convener-drain-queue`: handle everything the queue holds, in one pass.

    Reads the same snapshot `plan_queue_drain` read, pairs each slot's event
    id with the key the workflow selected for it, and writes the result --
    every event's `survey-responses.enc` **and** `instance/data/queue-ledger.yml` --
    so the caller can commit the lot as one commit. The two must land
    together or not at all: the ledger is what makes a replayed drain a
    no-op, and a ledger committed without its data (or data without its
    ledger) is exactly a lost or a doubled submission.

    Writes nothing to the queue itself. The clearing step reads
    `$CONVENER_QUEUE_CLEAR_FILE` **after** the commit has been pushed, which is
    the whole ordering that makes an interruption safe -- see
    `submission_queue`'s own module docstring.

    Returns 0 even when entries were refused or deferred: a drain that
    failed here would leave the good submissions uncommitted for the sake of
    a bad one. Both are reported as annotations, and the workflow's own
    reporting step is what turns a refusal red.
    """
    root = repo_root()
    snapshot = _queue_snapshot(root)
    if snapshot.error is not None:
        print(f"::error::{snapshot.error}", file=sys.stderr)
        return 1
    plan, entries = snapshot.plan, snapshot.entries

    # Paired by slot, not by name: the workflow put event id *i* and the
    # secret it selected for event *i* in the same numbered pair, and this
    # is the one place the two halves meet again. `plan_queue_drain` and
    # this command compute the identical plan from the identical snapshot,
    # so slot `i` names the same event in both.
    keys: dict[str, str] = {}
    for slot, event_id in enumerate(plan.event_ids, start=1):
        named = os.environ.get(f"CONVENER_QUEUE_EVENT_{slot}", event_id)
        if named != event_id:
            # Belt and braces: if the two steps ever disagreed about which
            # event holds slot `i`, the key in that slot belongs to another
            # event and would decrypt nothing. Left empty, so every entry
            # for this event is deferred and reported rather than refused.
            print(
                f"::warning::slot {slot} names event {named} but this drain "
                f"planned {event_id} -- leaving it for the next drain",
            )
            continue
        keys[event_id] = os.environ.get(f"CONVENER_QUEUE_KEY_{slot}", "")

    existing: dict[str, str | None] = {}
    for event_id in plan.event_ids:
        for rel in (
            submission_queue.responses_path(event_id),
            submission_queue.registrations_path(event_id),
        ):
            path = root / rel
            existing[rel] = path.read_text(encoding="utf-8") if path.exists() else None

    outcome = submission_queue.drain(plan, keys, existing, snapshot.ledger, entries)

    for rel, text in sorted(outcome.files.items()):
        path = root / Path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")

    ledger_path = root / submission_queue.LEDGER_PATH
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        QUEUE_LEDGER_HEADER
        + store.dump(submission_queue.ledger_to_data(outcome.ledger)),
        encoding="utf-8",
        newline="",
    )

    clear_file = os.environ.get(QUEUE_CLEAR_ENV, "")
    if clear_file:
        # `newline=""`, the same discipline every other writer in this
        # module holds, and here it is load-bearing rather than tidy: the
        # clearing step reads this file line by line in `sh`, and a line
        # ending Python had translated would make every path it read end
        # in a carriage return. `git rm --ignore-unmatch` matches no such
        # path, stages nothing, and the step reports the queue as already
        # clear -- a queue that never empties, reported as success.
        # Found by driving the real workflow shell, not by reading it.
        Path(clear_file).write_text(
            "".join(f"{name}\n" for name in outcome.clear),
            encoding="utf-8",
            newline="",
        )

    confirm_file = os.environ.get(QUEUE_CONFIRM_ENV, "")
    if confirm_file:
        # `newline=""` for the identical, load-bearing reason the clear file
        # above carries it: the confirming step reads this back line by
        # line, and a line ending Python had translated would make every
        # entry path it read end in a carriage return -- an entry nothing
        # in the exported queue matches, i.e. a confirmation silently never
        # sent, reported as success.
        Path(confirm_file).write_text(
            "".join(
                f"{item.name}{_CONFIRM_FIELD_SEPARATOR}{','.join(item.changed)}\n"
                for item in outcome.confirm
            ),
            encoding="utf-8",
            newline="",
        )

    deferred_file = os.environ.get(QUEUE_DEFERRED_ENV, "")
    if deferred_file:
        # The drain is the only thing in the run that
        # knows *why* an entry is still waiting -- a key nobody
        # configured, a committed file nobody can parse, more open events
        # than there are secret slots -- and the fix differs by reason, so
        # the record that outlives this run has to carry it rather than
        # only the fact of waiting.
        #
        # `newline=""`, and `flatten_reason` on every line, for the same
        # load-bearing reason the two files above carry theirs: this is
        # read back line by line, and a deferral whose reason is a YAML
        # parser's own several-line message would otherwise put a fragment
        # of an error where the next line's entry path belongs.
        Path(deferred_file).write_text(
            "".join(
                f"{note.name}{DEFERRED_FIELD_SEPARATOR}"
                f"{queue_watch.flatten_reason(note.reason)}\n"
                for note in outcome.deferred
            ),
            encoding="utf-8",
            newline="",
        )

    for line in submission_queue.annotation_lines(outcome):
        print(line)
    print(submission_queue.summary(outcome))
    step_output.write(
        f"handled={outcome.handled}\nrefused={len(outcome.refused)}\n"
        f"deferred={len(outcome.deferred)}\n"
        f"confirm={len(outcome.confirm)}\n"
    )
    return 0


def confirm_queued_registrations() -> int:
    """`convener-confirm-queued-registrations`: send the confirmation for every
    registration `convener-drain-queue` stored, and only then let it be cleared.

    The third of the queue's steps, and the one whose *position* is the
    whole of its correctness. It runs **after** the drain's commit has been
    pushed, so no confirmation can ever go out for a registration a rejected
    push then discarded -- the identical ordering `registration.yml` spells
    out for the immediate lane -- and **before** the clearing step, so an
    entry is only ever removed from the queue once its confirmation has
    actually been attempted. A run that stopped between the two would leave
    the entry in the queue, and the next drain would find it in the ledger
    *and* still waiting, which is exactly how it recognises "stored, not yet
    confirmed" (`submission_queue.DrainPlan.confirm_only`).

    "Attempted", not "delivered", and the difference is deliberate: with no
    SMTP transport configured -- this project's ordinary D-13 state -- no
    confirmation is ever delivered at all, and a clear that waited for
    delivery would mean a queue that never empties and an alarm every single
    day. `_send_confirmation` already reports a message it could not send
    and names `convener-resend-confirmation` as the recovery, and that is the
    same recovery here.

    Reads the queue the drain read (`CONVENER_QUEUE_DIR`), the list the drain
    wrote (`CONVENER_QUEUE_CONFIRM_FILE`), and the same numbered
    `CONVENER_QUEUE_EVENT_<n>` / `CONVENER_QUEUE_KEY_<n>` pairs -- decrypting the
    payload a second time from the same ciphertext, because a registration's
    plaintext lives in one process's memory at a time and there is no other
    way to ask for it again (`send_confirmation`'s own docstring makes the
    identical point about the identical second decrypt).

    Appends what it confirmed to `CONVENER_QUEUE_CLEAR_FILE`, so the clearing
    step removes exactly the entries that are now completely done, alongside
    the survey responses and refusals the drain already put there.
    """
    queue_dir = os.environ.get(QUEUE_DIR_ENV, "")
    if not queue_dir:
        print(f"::error::{QUEUE_DIR_ENV} is not set", file=sys.stderr)
        return 1
    confirm_file = os.environ.get(QUEUE_CONFIRM_ENV, "")
    if not confirm_file:
        print(f"::error::{QUEUE_CONFIRM_ENV} is not set", file=sys.stderr)
        return 1
    pending = Path(confirm_file)
    if not pending.exists():
        print("the drain stored no registration that still needs a confirmation")
        return 0

    entries = _queue_entries(Path(queue_dir))
    keys: dict[str, str] = {}
    for slot in range(1, submission_queue.MAX_EVENTS_PER_DRAIN + 1):
        event_id = os.environ.get(f"CONVENER_QUEUE_EVENT_{slot}", "")
        if event_id:
            keys[event_id] = os.environ.get(f"CONVENER_QUEUE_KEY_{slot}", "")

    confirmed: list[str] = []
    for line in pending.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, _, raw_changed = line.partition(_CONFIRM_FIELD_SEPARATOR)
        payload = entries.get(name)
        if payload is None:
            # The queue no longer holds it, so an earlier run already
            # cleared it, which -- by this step's own ordering -- means its
            # confirmation already went out. Nothing to do, and nothing
            # wrong: never a second message for one submission.
            print(f"::warning::{name}: no longer in the queue, nothing sent")
            continue
        read = submission_queue.read_entry(name, payload)
        if isinstance(read, submission_queue.Note):
            print(f"::warning::{name}: {read.reason}")
            confirmed.append(name)
            continue
        private_pem = keys.get(read.event_id, "")
        if not private_pem:
            # Left in the queue and *not* confirmed: the next drain finds
            # it in the ledger and still waiting, and tries again. Loud,
            # because a key nobody configured is the operator's to fix.
            print(
                f"::error::{name}: no private key configured for event "
                f"{read.event_id} -- its confirmation is still waiting"
            )
            continue
        registration = to_registration(read.payload, private_pem)
        if registration is None:
            # Stored it was not (the drain refuses exactly the same
            # envelope), so there is nothing this can confirm. Cleared
            # rather than left to block the queue for ever.
            print(
                f"::warning::{name}: a queued registration for event "
                f"{read.event_id} could not be read, nothing sent"
            )
            confirmed.append(name)
            continue
        changed = tuple(field for field in raw_changed.split(",") if field)
        _send_confirmation(read.event_id, registration, changed)
        confirmed.append(name)

    if confirmed:
        clear_file = os.environ.get(QUEUE_CLEAR_ENV, "")
        if not clear_file:
            print(f"::error::{QUEUE_CLEAR_ENV} is not set", file=sys.stderr)
            return 1
        with Path(clear_file).open("a", encoding="utf-8", newline="") as handle:
            for name in confirmed:
                handle.write(f"{name}\n")

    print(f"{len(confirmed)} queued registration(s) confirmed and ready to clear")
    return 0
