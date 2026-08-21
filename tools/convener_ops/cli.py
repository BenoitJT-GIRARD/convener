"""Command-line entry points. This is the only module that touches the disk."""

from __future__ import annotations

import contextlib
import json
import os
import re

# One fixed git invocation, in `_git_log` and nowhere else; see its docstring.
import subprocess  # nosec B404
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any, Final

import yaml

from convener_ops import confirmation, delivery, eventkeys, signing
from convener_ops.attendance import (
    EligibilityThreshold,
    MatchedAttendee,
    MatchEvent,
    eligible_attendees,
    match,
)
from convener_ops.certificate import (
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
from convener_ops.governance import PARIS, paris_today
from convener_ops.integrations import ABSENT, Integration, load_declaration, resolve_states
from convener_ops.notify import daily_digest, dispatch, immediate_events, render_events
from convener_ops.paths import repo_root
from convener_ops.platform import (
    AttendanceImportError,
    EventNotFoundError,
    Room,
    find_speaker,
)
from convener_ops.platform_fcc import (
    FCCRequestError,
    PlatformFCC,
    converted_recording_is_reachable,
    missing_retrieval_evidence,
    platform_from_env,
)
from convener_ops.proposal import field_value, skip_reason, to_lead, verify_signature
from convener_ops.public_data import to_public
from convener_ops.register import (
    LOG_FORMAT,
    REGISTER_PATH,
    entries_from_log,
    render_register,
)
from convener_ops.registration import (
    AmbiguousMatchingCodeError,
    Registration,
    dump_registration_file,
    erase,
    event_id_from_payload,
    find_by_email,
    find_by_matching_code,
    load_registration_file,
    matching_code,
    normalize_email,
    to_registration,
    upsert,
)
from convener_ops.sweep import expire_votes, sweep_inactive_members
from convener_ops.sweep import sweep as sweep_speakers
from convener_ops.validate import (
    board_target_report,
    validate_config,
    validate_speakers,
)
from convener_ops.yaml_safe import safe_load as yaml_safe_load

#: The header line each data file carries. `app/src/data/yaml.ts` holds the
#: same two strings: it is the browser's half of this file format, and the
#: YAML-boundary fixture is written by one side and read by the other.
SPEAKERS_HEADER = "# Speakers (unified schema v3 — see docs/reference/schema.md)\n"
CONFIG_HEADER = "# Repo-wide config for the Convener app\n"
#: certificates.yml holds no name and no address by construction -- see
#: tools/convener_ops/certificate.py's module docstring for why this file
#: survives task 15's retention sweep on registrations.enc, in the same
#: directory, untouched.
CERTIFICATES_HEADER = (
    "# Certificate register -- no name, no address; see tools/convener_ops/certificate.py\n"
)
#: The destruction registry (task 15) holds only an event id and a date --
#: see tools/convener_ops/eventkeys.py's module docstring, "the destruction
#: registry lives in one file".
DESTRUCTIONS_HEADER = (
    "# Event key destruction registry; see tools/convener_ops/eventkeys.py\n"
)


class _Dumper(yaml.SafeDumper):
    """SafeDumper that writes a multi-line string the way js-yaml does.

    PyYAML's default for a string containing a newline is a single-quoted
    scalar with the line breaks folded through blank lines; js-yaml writes a
    literal block (`|-`). Both read back identically, but they are different
    bytes for the same abstract, so a talk abstract typed into the browser
    form and later touched by the sweep would be rewritten wholesale by
    whichever side wrote last. `_represent_str` below makes this package
    write the block form too -- see `app/src/data/yaml.ts::DUMP` for the
    browser's half, and `tools/tests/fixtures/speakers-from-app.yml` for the
    fixture that holds the two together.
    """


#: Text that js-yaml quotes on write and PyYAML would leave bare.
#:
#: Both loaders read every one of these back as a string, so this is not a
#: correctness fix -- it is a formatting one, and the fixture is byte-level,
#: so it has to be made. The four families, all of them YAML 1.1 leftovers
#: js-yaml still defends against: a sexagesimal time whose first digit is a
#: zero (`09:05`; PyYAML's own int resolver requires 1-9 there, which is why
#: `12:30` needs nothing added), an exponent with no decimal point (`1e3`),
#: the one-letter booleans (`y`, `Y`, `n`, `N`), and a YAML 1.2 octal
#: (`0o17`). The exponent alternative deliberately excludes any form with a
#: decimal point: that is what a real float represents as, and quoting one
#: would turn a number into a string on the next read.
_QUOTE_LIKE_JS_YAML = re.compile(
    r"""^(?:[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+
        |[-+]?[0-9][0-9_]*[eE][-+]?[0-9]+
        |[yYnN]
        |[-+]?0o[0-7_]+)$""",
    re.X,
)

# Registered on the dumper only. The tag names what the scalar would be
# mistaken for; all that matters to the emitter is that it is not `str`, which
# is what makes it quote the value.
_Dumper.add_implicit_resolver(
    "tag:yaml.org,2002:int", _QUOTE_LIKE_JS_YAML, list("-+0123456789yYnN")
)


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _represent_str)


def _dump(data: Any) -> str:
    """The one YAML writer of this package.

    Every writer -- the sweep, the form handler, the v3 migration -- goes
    through it, so a file written by any of them keeps the same shape and
    stays readable by the browser.
    """
    return yaml.dump(
        data,
        Dumper=_Dumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    )


def dump_speakers(speakers: Any) -> str:
    return SPEAKERS_HEADER + _dump(speakers)


def dump_config(config: Any) -> str:
    return CONFIG_HEADER + _dump(config)


def _load(path: Path) -> tuple[Any, list[str]]:
    if not path.exists():
        return None, [f"{path.name}: file missing"]
    try:
        return yaml_safe_load(path.read_text(encoding="utf-8")), []
    except yaml.YAMLError as exc:
        return None, [f"{path.name}: invalid YAML - {exc}"]


def validate() -> int:
    root = repo_root()
    speakers, errors = _load(root / "data" / "speakers.yml")
    cfg, cfg_errors = _load(root / "data" / "config.yml")
    errors += cfg_errors

    board_logins: set[str] = set()
    if isinstance(cfg, dict):
        board = cfg.get("board")
        if isinstance(board, list):
            board_logins = {
                str(m["login"])
                for m in board
                if isinstance(m, dict) and isinstance(m.get("login"), str)
            }

    if speakers is not None:
        errors += validate_speakers(speakers, board_logins)
    if cfg is not None:
        errors += validate_config(cfg)

    # Before the verdict, and regardless of it: `board_min` is a target, so a
    # board short of it is news the meeting needs, not a fault to fix. It
    # neither adds to `errors` nor changes the exit code -- a target that
    # could fail a run would be a rule wearing a softer word.
    shortfall = board_target_report(cfg)
    if shortfall:
        print(f"Note: {shortfall}")

    if errors:
        print("Data validation FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1

    count = len(speakers or [])
    print(f"Data OK - {count} speakers, config=ok")
    return 0


_SYMBOL = {"production": "[ok]", "trial": "[trial]", "absent": "[--]"}


def render_check(integrations: list[Integration]) -> str:
    """The `convener-check-config` report.

    "An absent integration is a normal state" is true for every row but the
    ones that declare `absent_is_normal: false` (see `integrations.py`).
    Softening the footer to "...unless a row says otherwise" would charge
    the honest rows for the exceptional one's sake, so instead: an
    exceptional row that is currently absent is marked inline, where the
    reader is already looking, and the footer only admits the exception --
    naming which row -- when one is actually in that state. A row that
    merely *declares* itself exceptional but is `production` today changes
    nothing here, because there is nothing to warn about yet.
    """
    lines = ["Integration status", "=================="]
    exceptional_absences: list[str] = []
    for integration in integrations:
        marker = ""
        if integration.state == ABSENT and not integration.absent_is_normal:
            marker = "  (not a normal absence -- see below)"
            exceptional_absences.append(integration.label)
        lines.append(
            f"{_SYMBOL[integration.state]} {integration.label} - "
            f"{integration.state}{marker}"
        )
        if integration.missing:
            lines.append(f"      waiting on: {', '.join(integration.missing)}")
            lines.append(f"      meanwhile:  {integration.absent_behaviour.strip()}")
    counts = Counter(i.state for i in integrations)
    summary = ", ".join(
        f"{counts[state]} {state}"
        for state in ("production", "trial", "absent")
        if counts[state]
    )
    lines.append("")
    lines.append(f"Summary: {summary}")
    if exceptional_absences:
        lines.append(
            "An absent integration is a normal state, not a failure -- "
            f"except {', '.join(exceptional_absences)}, marked above."
        )
    else:
        lines.append("An absent integration is a normal state, not a failure.")
    return "\n".join(lines)


def check_config() -> int:
    declaration = repo_root() / "config" / "integrations.yml"
    integrations = resolve_states(load_declaration(declaration), env=os.environ)
    print(render_check(integrations))
    return 0


def _report_inactivity(
    cfg: dict[str, Any], speakers: list[dict[str, Any]], now: datetime
) -> None:
    """Print the board-inactivity proposals (G-09) and discard them.

    Detection is what the scheduled task operates; applying a proposal stays a
    human act on the Board screen. So the config `sweep_inactive_members`
    returns -- the file as it would read once a proposal were applied -- is
    bound to `_` and dropped right here, deliberately: it reaches no writer, and
    nothing downstream of this function can see it. A scheduled job has no
    author to record, and no automated path may write a terminal outcome about
    a person.

    Printing nothing is an ordinary outcome, not a failure. A member whose
    silence has no countable start -- no ballot on file, and no `joined_on`
    to date the silence from -- is one this rule has no evidence about, and
    it names nobody on a guess. It speaks once the file gives it a day to
    measure from, and stays quiet until then, however many members the file
    happens to carry.

    Each line's subject is the ballot record, never the person.
    """
    _, prompts = sweep_inactive_members(cfg, speakers, now)
    if not prompts:
        return
    print("")
    print("Board inactivity (G-09) - proposed, not applied; a human decides:")
    for prompt in prompts:
        print(f"  - {prompt}")


def sweep() -> int:
    root = repo_root()
    speakers_path = root / "data" / "speakers.yml"
    speakers, errors = _load(speakers_path)
    cfg, cfg_errors = _load(root / "data" / "config.yml")
    if errors or cfg_errors:
        for error in errors + cfg_errors:
            print(f"  - {error}")
        return 1

    now = datetime.now(UTC)
    swept, changes = sweep_speakers(speakers or [], cfg or {}, now)
    swept, vote_changes = expire_votes(swept, cfg or {}, now)
    changes += vote_changes
    if changes:
        speakers_path.write_text(dump_speakers(swept), encoding="utf-8", newline="")
        for change in changes:
            print(change)
    else:
        print("Nothing to sweep.")

    _report_inactivity(cfg or {}, swept, now)
    return 0


def public_data() -> int:
    root = repo_root()
    speakers, errors = _load(root / "data" / "speakers.yml")
    if errors:
        for error in errors:
            print(f"  - {error}")
        return 1

    rows = to_public(speakers or [])
    out_dir = root / "public-data"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "events-public.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} events")
    return 0


def handle_proposal() -> int:
    """Turn a signed Tally webhook into a lead, or refuse it.

    ``PROPOSAL_PAYLOAD`` is the raw body Tally signed -- not a wrapper
    around it -- so verifying the signature against it and then parsing it
    as JSON are both operating on exactly what Tally sent. The workflow
    (.github/workflows/candidate-form.yml) sets it from
    ``client_payload.body``, which the relay (services/form-relay) sends
    separately from ``client_payload.signature`` for exactly this reason: a
    signature cannot verify a payload that contains that signature.
    """
    payload_str = os.environ.get("PROPOSAL_PAYLOAD", "")
    signature = os.environ.get("PROPOSAL_SIGNATURE", "").strip()
    secret = os.environ.get("TALLY_WEBHOOK_SECRET", "").strip()

    if not payload_str:
        print("no payload", file=sys.stderr)
        return 1

    if not verify_signature(payload_str, signature, secret):
        print("invalid signature", file=sys.stderr)
        return 1

    # `payload_str` is signature-checked above, never schema-checked: a
    # signature only proves who sent the body, not that it parses as JSON
    # or that it is a JSON object rather than, say, an array. With no
    # secret configured, verify_signature accepts anything (D-13), which
    # makes this reachable in production, not just a defensive guess.
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        print("invalid JSON payload", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("invalid JSON payload", file=sys.stderr)
        return 1

    fields_list = (
        payload.get("data", {}).get("fields")
        if isinstance(payload.get("data"), dict)
        else payload.get("fields")
    )
    if not isinstance(fields_list, list):
        fields_list = []
    # field_value resolves a picker's chosen option id(s) against that
    # field's own `options` array (R-9) -- without it, a DROPDOWN/
    # MULTIPLE_CHOICE/CHECKBOXES/MULTI_SELECT answer's raw `value` is a list
    # of ids, never the text `to_lead` compares against `GENDERS`/
    # `CAREER_STAGES`, and every such answer would silently become
    # "undisclosed". This is the one place in the repository that flattens
    # a Tally field into `to_lead`'s `fields: dict[str, str]`.
    fields = {
        f.get("label", ""): field_value(f) for f in fields_list if isinstance(f, dict)
    }

    root = repo_root()
    speakers_path = root / "data" / "speakers.yml"
    speakers, errors = _load(speakers_path)
    cfg, cfg_errors = _load(root / "data" / "config.yml")
    if errors or cfg_errors:
        for error in errors + cfg_errors:
            print(f"  - {error}")
        return 1
    speakers = speakers or []

    # The Paris day, not the UTC one: this date seeds the vote window
    # (`selection.opened_on`), so a submission arriving between 00:00 and 02:00
    # Paris would otherwise open a window dated a day early and every deadline
    # derived from it would inherit the error.
    today = paris_today(datetime.now(UTC)).isoformat()
    lead = to_lead(fields, speakers, cfg or {}, today)
    if lead is None:
        print(f"skipping: {skip_reason(fields, speakers)}")
        return 0

    speakers.append(lead)
    speakers_path.write_text(dump_speakers(speakers), encoding="utf-8", newline="")
    print(f"created {lead['id']} from form proposal")
    return 0


#: Where an unsent confirmation is left for inspection: never printed, and
#: `.gitignore`d -- see `confirmation.py`'s module docstring for why a
#: message carrying an address and a matching code is written to a file
#: rather than to this job's own stdout, the way `NOTIFY_BODY` above is for
#: a message that carries neither. Overwritten on every attempt, the same
#: "one fixed name inside the run's own isolated workspace" idiom
#: `NOTIFY_BODY` already uses -- a fresh `actions/checkout` per run means
#: two runs never share a workspace to collide in.
UNSENT_CONFIRMATION: Final = "unsent-confirmation.eml"


def _write_github_output(line: str) -> None:
    """`line` (already `key=value\n`-shaped, one or more) to
    `$GITHUB_OUTPUT`, or printed when that path is unset -- a run outside
    Actions, the "inspectable instead of silent" idiom
    `resolve_registration_secret` originated. Shared with
    `handle_registration` now, so the fallback cannot drift between the
    two call sites."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(line)
    else:
        print(line, end="")


def _send_confirmation(
    event_id: str, registration: Registration, changed: Sequence[str]
) -> None:
    """Compose and attempt to deliver the confirmation for `registration`,
    then print exactly one line naming the event id (already public) and
    the outcome -- never the registration's own fields, and never the
    composed message. See `confirmation.py`'s module docstring for the
    reasoning; this function is only the disk-and-stdout half of it, kept
    in `cli.py` the way `_notify` keeps `notify.py`'s own file write.

    `changed` is the field labels the caller already worked out
    (`confirmation.changed_fields`) -- this function does not compute it,
    so `resend_confirmation` (always `changed=()`) and `send_confirmation`
    (a fresh or updated registration, this task's own step) share one code
    path with no branch of their own in here.

    Never lets a room lookup that fails (`confirmation.EventNotFoundError`
    -- no speaker record matches `event_id`) stop the confirmation from
    being composed and sent: the caller already holds the registration
    itself, and a missing speaker record must not lose the message too.
    The message that goes out in that case simply has no room link, which
    the print line below says plainly.

    Nothing in this function is allowed to raise past it: the whole body,
    not only the compose-deliver-write sequence, is wrapped in one broad
    `except Exception`. That catch is no longer a defence against `set -e`
    aborting a commit -- since review round 1 (Important 2), sending is a
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
        speakers, _errors = _load(root / "data" / "speakers.yml")
        cfg, _errors = _load(root / "data" / "config.yml")
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

        unsent_path = root / UNSENT_CONFIRMATION
        if result.sent:
            # A previous attempt in this same workspace may have left a
            # file behind (review round 1, Important 1): once a message
            # has genuinely gone out, nothing should remain that an
            # `if: always()` step would then upload as though it had not.
            unsent_path.unlink(missing_ok=True)
            print(f"confirmation for event {event_id} sent")
            return

        unsent_path.write_text(result.unsent_body or "", encoding="utf-8", newline="")
        print(
            f"confirmation for event {event_id} not sent -- no email "
            f"transport configured or delivery failed; composed message "
            f"left in {UNSENT_CONFIRMATION}"
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
    `_write_github_output`; printed to stdout instead when `$GITHUB_OUTPUT`
    is unset (a run outside Actions), the same "inspectable instead of
    silent" idiom `_notify` uses for its own absent channel.

    Neither line carries anything a stranger could not already read from
    the repository: `event_id` is public (`keys/events/<id>.pub` names it
    openly) and `secret_name` is a *name*, not a value.
    """
    payload = os.environ.get("REGISTRATION_PAYLOAD", "")
    event_id = event_id_from_payload(payload)
    if event_id is None:
        print("no valid event id in the registration payload", file=sys.stderr)
        return 1

    _write_github_output(
        f"event_id={event_id}\nsecret_name={eventkeys.secret_name(event_id)}\n"
    )
    return 0


def handle_registration() -> int:
    """`convener-handle-registration`: the second of the three steps
    `.github/workflows/registration.yml` runs -- decrypt one registration
    and store it re-encrypted in `data/events/<id>/registrations.enc`.

    The confirmation itself is sent by a *separate* step
    (`convener-send-confirmation`, gated `if: success()` so it runs at most once
    per job, only after this step's own push-retry loop has actually
    landed the record on the branch). Split this way on review (R-9 round
    1, Important 2): this step's workflow retries on a rejected push,
    re-running the whole step up to three times, and a step that both
    stored and sent would send one confirmation per attempt -- or, worse,
    send one for a registration a later, failed attempt then discarded.

    Reads `REGISTRATION_PAYLOAD` (the raw relayed body -- see
    `convener_ops.registration.to_registration` for why it is passed through
    whole) and `EVENT_PRIVATE_KEY` (the PEM the workflow selected using
    `resolve_registration_secret`'s own output). Never prints either of
    them, or anything decrypted from them: every message below names only
    the event id -- already public, the same identifier every workflow run
    and every `keys/events/<id>.pub` filename already carry in the clear
    -- and a count.

    An absent `EVENT_PRIVATE_KEY` is not D-13's normal state here, the same
    exception `eventkeys.py`'s module docstring names: this job exits in
    error rather than doing anything at all with the ciphertext it was
    handed, the same as a genuinely undecryptable one.

    Writes `changed=<comma-joined field labels>` to `$GITHUB_OUTPUT` -- the
    R-9 diff between the prior stored registration (read via
    `find_by_email`, before `upsert` overwrites it) and this one, for
    `send_confirmation` to read back and hand to `confirmation.compose`
    unchanged. Field labels are not personal data (that is the whole point
    of naming rather than quoting, R-9), so this is the one thing this
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
        print(
            f"registration for event {event_id} could not be decrypted", file=sys.stderr
        )
        return 1

    root = repo_root()
    rel_path = Path("data") / "events" / event_id / "registrations.enc"
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
    _write_github_output(f"changed={','.join(changed)}\n")
    return 0


def send_confirmation() -> int:
    """`convener-send-confirmation`: the third of the three steps
    `.github/workflows/registration.yml` runs -- and the only one gated
    `if: success()`, so it runs at most once per job, only once
    `convener-handle-registration`'s own push-retry loop has actually landed
    the record on the branch. See `handle_registration`'s own docstring
    for why sending was split into its own step (R-9 review round 1,
    Important 2).

    Reads `REGISTRATION_PAYLOAD` and `EVENT_PRIVATE_KEY` again -- the
    workflow already holds both for the step that ran before this one, so
    reading them again here needs no new secret -- and decrypts the
    registration a second time. Not wasted work an oversight left behind:
    the registration's plaintext lives only in one process's memory at a
    time (the phase 4 spec's whole design; `registration.py`'s own module
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
        print(
            f"registration for event {event_id} could not be decrypted", file=sys.stderr
        )
        return 1

    changed = tuple(
        field for field in os.environ.get("CHANGED_FIELDS", "").split(",") if field
    )
    _send_confirmation(event_id, registration, changed)
    return 0


def resend_confirmation() -> int:
    """`convener-resend-confirmation`: re-send the confirmation already on file
    for one address, without regenerating anything -- the manual resend the
    phase 4 spec's risk table asks for (S:9: "a certificate in the spam
    folder does not exist").

    Reads `EVENT_ID` and `REGISTRATION_EMAIL` -- both plain, operator-typed
    values, not the encrypted relay payload `handle_registration` reads:
    this is a human running a manual step (through a `workflow_dispatch`
    input), never a public endpoint, so there is nothing here for a
    stranger to reach. `EVENT_PRIVATE_KEY` is the same per-event secret
    `handle_registration` reads.

    `REGISTRATION_EMAIL` is retained by GitHub on the run page for as long
    as the run's history exists -- longer than the 14-day artefact
    `resend-confirmation.yml` uploads specifically so an address does not
    have to sit in a retained Actions surface (`config/integrations.yml`,
    `docs/reference/operations.md`). This is a deliberate, narrow
    exception, not an oversight: `registration.py`'s own module docstring
    explains why no other identifier for one registration is stored at
    all ("No stored identifier for whose entry is this"), so an address
    is the only handle a resend can name a registration by, and
    `workflow_dispatch` is restricted to collaborators with repository
    write access -- the same trust boundary as anyone who could already
    read the job log or a delivered artefact.

    Finds the one entry for `REGISTRATION_EMAIL` in `registrations.enc`
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

    email = os.environ.get("REGISTRATION_EMAIL", "").strip()
    if not email:
        print("no registration e-mail address supplied", file=sys.stderr)
        return 1

    private_pem = os.environ.get("EVENT_PRIVATE_KEY", "")
    if not private_pem:
        print(f"no private key configured for event {event_id}", file=sys.stderr)
        return 1

    root = repo_root()
    rel_path = Path("data") / "events" / event_id / "registrations.enc"
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
    """`convener-retention-sweep`: the job that makes spec S4's central promise
    true. Finds the id of every event whose retention window has elapsed
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

    **R-28: `CONVENER_RETENTION_TOKEN` absent fails this job outright, on
    every scheduled run, whether or not any event happens to be due for
    destruction today.** Every other secret in this codebase degrades to
    an ordinary D-13 absence -- a feature that does not run this time,
    reported and nothing more. This one does not: a retention job that
    exits green having destroyed nothing looks identical, from the
    Actions tab, to a retention job that genuinely had nothing to do --
    and the two must never be confused for a promise with legal weight.
    So this is checked, and fails, before anything else -- including
    before reading `data/speakers.yml`, so a malformed data file is never
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
            "destroyed nothing -- see docs/reference/operations.md, "
            "'Retention and early erasure'",
            file=sys.stderr,
        )
        return 1

    root = repo_root()
    speakers, errors = _load(root / "data" / "speakers.yml")
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
                # ::warning:: (Important 1): a skip nobody sees is exactly
                # the failure R-28 exists to prevent -- this function's own
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
        _write_github_output(
            f"destroyed_ids=\ndestroyed_secrets=\ndestroyed_on={today.isoformat()}\n"
        )
        return 0

    secret_names = [eventkeys.secret_name(event_id) for event_id in due]
    print(f"due for destruction: {', '.join(due)}")
    _write_github_output(
        f"destroyed_ids={','.join(due)}\n"
        f"destroyed_secrets={','.join(secret_names)}\n"
        f"destroyed_on={today.isoformat()}\n"
    )
    return 0


def record_destructions() -> int:
    """`convener-record-destructions`: write `data/event-key-destructions.yml`
    with every id in `DESTROYED_IDS` (comma-joined, `retention_sweep`'s
    own `$GITHUB_OUTPUT`, or a hand-run operator recovering from a wedged
    sweep -- see `docs/reference/operations.md`, 'Retention and early
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

    **Calls `eventkeys.destroy`, not a bare `dict.setdefault` (R-35,
    Important 3 and Minor 6).** Every id `retention_sweep` itself ever
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
    published `.pub` (R-35, Important 2).** `keys/events/<id>.pub` is the
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

    A missing or malformed `DESTROYED_ON`, or a `data/event-key-
    destructions.yml` that failed to parse, is reported and the run exits
    1 -- both mean this step cannot answer the one question it exists to
    answer (what day did this destruction happen), so it must not guess.
    An empty `DESTROYED_IDS` is not an error: `retention_sweep` writes it
    empty on an ordinary day nothing was due, and this step has nothing to
    record.

    **This function is all-or-nothing across `ids`, unlike the delete
    step above, which is per-event tolerant (R-34) -- a deliberate
    asymmetry, not an oversight.** If recording aborts partway, the
    secrets already confirmed gone are simply left unrecorded; the next
    sweep finds those events still due, re-deletes secrets that are
    already absent (which R-34 made safe), and records them then.
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
        DESTRUCTIONS_HEADER + _dump(eventkeys.registry_to_data(registry)),
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
    one entry an early erasure request names -- spec S4's "effacement
    avant echeance" ("reecriture du fichier chiffre sans l'enregistrement
    concerne, procedure documentee et testee").

    **Identifies the registration by `MATCHING_CODE` in preference to
    `REGISTRATION_EMAIL` (R-32).** The code is already in the
    participant's own confirmation e-mail (task 7) and is recomputed and
    compared against every stored entry
    (`registration.find_by_matching_code`), never reversed out of
    anything stored -- nothing here stores it. `REGISTRATION_EMAIL` is
    accepted as a fallback for a participant who no longer has that
    e-mail: the same **deliberate, documented exception**
    `resend_confirmation` above already makes for the identical reason
    (an address in a `workflow_dispatch` input is rendered and retained on
    the run page -- review round 1, Important 4 -- accepted anyway because
    refusing the request would be worse than the exposure). Both may be
    supplied; the code is tried first.

    **A code collision (Minor 8) is resolved by the address, if one was
    also given and it narrows the tie to exactly one entry** -- reading
    the evidence the requester supplied is not guessing, so this proceeds;
    with no address, or an address that does not narrow the tie, this
    refuses rather than pick one (`AmbiguousMatchingCodeError`, whose own
    docstring carries the full reasoning).

    **Checked before anything else touches disk: has this event's key
    already been destroyed?** `data/event-key-destructions.yml` is read
    first, and if it already names `event_id`, this prints the destruction
    date on record and returns 0 -- spec S4's "et c'est demontrable",
    proved from the committed registry rather than merely asserted, and
    the request is already satisfied (there is nothing left that could be
    erased). An event id that is not known to this repository at all (no
    `keys/events/<id>.pub`, and no destruction on record either) is
    refused instead -- that is not "already erased", it names nothing this
    repository ever registered.

    **Unless `EVENT_PRIVATE_KEY` is supplied anyway (Minor 4).** A key
    that still opens `registrations.enc` for an event this registry
    already calls destroyed contradicts the one thing this command exists
    to prove -- "there is nothing left" would then be an assertion, not a
    demonstration, exactly the distinction spec S4 draws. So that
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
    email = os.environ.get("REGISTRATION_EMAIL", "").strip()
    if not code and not email:
        print("no matching code or e-mail address supplied", file=sys.stderr)
        return 1

    private_pem = os.environ.get("EVENT_PRIVATE_KEY", "")
    if not private_pem:
        print(f"no private key configured for event {event_id}", file=sys.stderr)
        return 1

    rel_path = Path("data") / "events" / event_id / "registrations.enc"
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
            # address was also supplied (R-32) and it narrows the tied
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

    enc_path.write_text(dump_registration_file(updated), encoding="utf-8", newline="")
    print(f"erased a registration for event {event_id} ({len(updated.entries)} remain)")
    return 0


#: Where the host's short list of attendance to resolve by hand lands --
#: names and addresses a volunteer needs to read directly, so this file is
#: `.gitignore`d and never printed, the same way `UNSENT_CONFIRMATION`
#: already handles a composed message that carries the same kind of data.
#: Written only when there is something to report; unlinked otherwise, so a
#: stale file from an earlier run of this same job workspace is never
#: mistaken for this run's answer.
#:
#: WARNING for whoever wires this into a workflow next (task 17's own
#: enchaînement, most likely): `unsent-confirmation.eml`'s own upload step
#: (`.github/workflows/registration.yml`) is a short-retention *private*
#: build artefact, restricted to the run's own collaborators -- never a
#: public one. This file carries the same kind of data and must be
#: uploaded the identical way if it ever is; inheriting the artefact
#: *pattern* without also inheriting that access restriction would publish
#: names and addresses this whole module exists to keep out of anything a
#: stranger can read.
UNMATCHED_ATTENDANCE: Final = "unmatched-attendance.md"


def match_attendance() -> int:
    """`convener-match-attendance`: read the platform's attendance export for
    one event, join it against that event's stored registrations through
    `attendance.match` (spec S:5's cascade), and report the result.

    Reads `EVENT_ID` -- an operator-typed value, the same manual-trigger
    shape `resend_confirmation` already reads, since the platform's
    attendance export only exists once the session is over, on nobody's
    automatic schedule -- and `EVENT_PRIVATE_KEY`, the same per-event
    secret every other step in this file that touches
    `registrations.enc` reads. Every existing entry is decrypted once, in
    memory, into `Registration` objects; an entry that fails to decrypt
    under this key is skipped rather than treated as a match, the same
    handling `find_by_email` and `upsert` already give a stray
    undecryptable entry.

    `attendance.py` is pure and never prints; this function is the only
    place its answer is turned into output, and it draws the same line
    task 6 drew for a decrypted registration: only counts -- how many
    matched, unmatched and unreachable, and how many rows were read --
    ever reach stdout, never a name or an address. The host's actual short
    list goes to `UNMATCHED_ATTENDANCE` instead, never printed and never
    committed (see its own comment above).
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
    rel_path = Path("data") / "events" / event_id / "registrations.enc"
    enc_path = root / rel_path
    if not enc_path.exists():
        print(f"no registrations recorded for event {event_id}", file=sys.stderr)
        return 1
    try:
        current = load_registration_file(enc_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"{rel_path.as_posix()}: {exc}", file=sys.stderr)
        return 1

    registrations: list[Registration] = []
    for entry in current.entries:
        registration = to_registration(json.dumps(entry), private_pem)
        if registration is not None:
            registrations.append(registration)

    speakers, _errors = _load(root / "data" / "speakers.yml")
    cfg, _errors = _load(root / "data" / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    config_map = cfg if isinstance(cfg, dict) else None
    platform = platform_from_env(os.environ, speaker_list, config_map)

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
        # `EventNotFoundError` joined the tuple in fix round 3 (Critical B):
        # this function never populates `conference_ids` (out of this
        # round's own scope -- it has no workflow to receive a
        # `conference_id` input from at all), so `PlatformFCC._conference_id`
        # always raises it today when the FCC path is in play, and it was
        # not caught here -- the identical hole `issue_certificates` and
        # `reissue_certificate` had, closed the same way in all three
        # places.
        print(str(exc), file=sys.stderr)
        return 1

    salt = os.environ.get("CONVENER_MATCHING_SALT")
    result = match(rows, registrations, MatchEvent(event_id=event_id, salt=salt))

    print(
        f"attendance for event {event_id}: {len(result.matched)} matched, "
        f"{len(result.unmatched)} unmatched, {len(result.unreachable)} "
        f"unreachable ({len(rows)} row(s) read)"
    )

    unmatched_path = root / UNMATCHED_ATTENDANCE
    if result.unmatched or result.unreachable:
        lines = [f"# Attendance to resolve -- event {event_id}"]
        if result.unmatched:
            lines.append("")
            lines.append("## Unmatched -- the host can resolve these by hand")
            for unmatched in result.unmatched:
                minutes = unmatched.duration_seconds // 60
                line = (
                    f"- {unmatched.display_name} <{unmatched.email}> -- {minutes} min"
                )
                if unmatched.tied_with:
                    # A tie the cascade refused to guess between (spec S:5:
                    # "empêche de revendiquer la présence d'autrui") --
                    # named here rather than left as a bare "unmatched",
                    # since the host is resolving a specific ambiguity, not
                    # starting from nothing. See attendance.py's own
                    # "Ties are never resolved by guessing" section.
                    line += f" -- ties: {', '.join(unmatched.tied_with)}"
                lines.append(line)
        if result.unreachable:
            lines.append("")
            lines.append(
                "## Unreachable -- joined by phone, no address on file, "
                "cannot be matched"
            )
            for unreachable in result.unreachable:
                minutes = unreachable.duration_seconds // 60
                lines.append(f"- {unreachable.display_name} -- {minutes} min")
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


def _conference_ids_from_env(event_id: str) -> dict[str, str]:
    """`conference_ids` for `platform_from_env`, folded from
    `CONVENER_FCC_CONFERENCE_ID` exactly the way `release_recording` already
    does (task 10) -- Critical B, fix round 3: `issue_certificates` and
    `reissue_certificate` both need the identical resolution, so it is
    factored out here rather than retyped a third and fourth time, per
    this round's own ruling ("reuse that code path rather than writing a
    second one").

    Before this round, neither `issue_certificates` nor `reissue_certificate`
    passed any `conference_ids` at all, so `PlatformFCC._conference_id`
    always raised `EventNotFoundError` the moment the FCC path was in play
    -- uncaught until this same round also added `EventNotFoundError` to
    both functions' own `except` tuples. An event with no FCC conference
    configured is the ordinary D-13 shape either way: this returns `{}`,
    the same "nothing to resolve" `release_recording` and
    `discard_recording` already treat identically.

    `release_recording` and `discard_recording` (task 10, a closed round)
    keep their own inline versions rather than being rewritten to call
    this -- not reopened here."""
    conference_id = os.environ.get("CONVENER_FCC_CONFERENCE_ID", "").strip()
    return {event_id: conference_id} if conference_id else {}


def issue_certificates() -> int:
    """`convener-issue-certificates`: match this event's attendance, work out
    who is eligible (spec S:5), and issue -- or reproduce -- a certificate
    for each of them (spec S:7, task 12).

    Reads `EVENT_ID` and `EVENT_PRIVATE_KEY` exactly as `match_attendance`
    does, for the same reason: this job re-derives the match from scratch
    rather than trusting a prior run's own answer, so a corrected
    registration or a corrected attendance export is picked up for free
    (spec S:8: "un appariement corrigé se recalcule sans réinscrire").

    **Critical B, fix round 3.** Also reads `CONVENER_FCC_CONFERENCE_ID`
    (`_conference_ids_from_env`, shared with `reissue_certificate`), the
    same optional `workflow_dispatch` input `recording.yml` already gives
    `release_recording` (task 10) -- without it, nothing ever populated
    `conference_ids`, so the FCC path (`CONVENER_MEETING_API_TOKEN` configured)
    could never issue a certificate at all: `PlatformFCC._conference_id`
    raised `EventNotFoundError` before any network call, and this function
    did not catch it. Both are fixed together here: the input is now
    threaded through, and `EventNotFoundError` joins the exception tuple
    below alongside `AttendanceImportError` and `FCCRequestError`. A
    conference id is a provider identifier, not personal data -- none of
    R-22's "never an address" reasoning applies to it, the same conclusion
    `recording.yml`'s own header comment already reached. **The manual
    path (no `CONVENER_MEETING_API_TOKEN`) stays blocked regardless**: its own
    attendance export is `.gitignore`d and cannot exist in a CI checkout
    at all -- see `docs/superpowers/deferred-work.md` entry 10.

    Two secrets gate whether *anything* is issued this run, checked before
    any registration is even decrypted:

    - `signing.SECRET_NAME` (`CONVENER_SIGNING_KEY`) absent is the ordinary
      D-13 shape `config/integrations.yml`'s own `signing_key` row
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
    on one line and exit 1. A missing or malformed `data/config.yml`
    exits 1 too -- eligibility cannot be computed at all without
    `seminar_duration_minutes`, unlike `match_attendance`, which never
    needed the config file in the first place. `CONVENER_SIGNING_KEY` present
    but unusable (a mangled PEM, the ordinary way a pasted secret fails)
    is checked once, before any registration is decrypted, rather than
    left to surface as an unhandled `signing.SigningError` traceback from
    inside the loop below (Important 1, fix round 1).

    A speaker record for `event_id` that is missing, or present but
    carries an empty title or an empty date, refuses the whole run (exit
    1) rather than signing a certificate that names no event and no date
    -- spec S:7's content list is not optional, and the register row a
    silently-empty certificate would leave behind is permanent (Important
    2, fix round 1). When `data/speakers.yml` itself failed to parse, the
    message names that parse failure -- surfaced from `_load`, never
    discarded -- instead of sending an operator to look for a speaker
    record that was never actually missing.

    Prints only counts, never a name or an address -- the same discipline
    `match_attendance` already holds itself to for the same reason.
    `data/events/<id>/certificates.yml` is rewritten, as a whole file
    (never appended to a partial one), only when at least one certificate
    was freshly minted; reissuing every attendee already on record writes
    nothing and still exits 0.

    **A fingerprint whose only rows are revoked is refused, not resurrected
    (R-26, fix round 1, Critical 1).** `issue`'s own three-way lookup
    raises `ValueError` for that one attendee; this loop catches it,
    counts it separately (never crashing the whole run over it), and
    leaves the register untouched for that fingerprint. The correction
    path is `convener-reissue-certificate`, an operator's own deliberate act,
    never something this scheduled-and-re-run command performs itself.

    **Writes the freshly-issued identifiers to `$GITHUB_OUTPUT` as
    `issued_ids=<comma-joined>` (R-27, fix round 1).** Identifiers are
    public by design -- already printed on the document, already
    published in `certificates-public.json` -- so nothing personal
    travels. `issue-certificates.yml`'s delivery step
    (`deliver_certificates`, below) reads this to restrict an ordinary run
    to exactly what was minted just now, rather than re-mailing every past
    attendee on every dispatch.

    Each eligible attendee's `duration_seconds` is capped at
    `threshold.seminar_duration_minutes * 60` before it ever reaches
    `issue` (R-17, fix round 1, Critical 1) -- see
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
    rel_path = Path("data") / "events" / event_id / "registrations.enc"
    enc_path = root / rel_path
    if not enc_path.exists():
        print(f"no registrations recorded for event {event_id}", file=sys.stderr)
        return 1
    try:
        current = load_registration_file(enc_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"{rel_path.as_posix()}: {exc}", file=sys.stderr)
        return 1

    registrations: list[Registration] = []
    for entry in current.entries:
        registration = to_registration(json.dumps(entry), private_pem)
        if registration is not None:
            registrations.append(registration)

    speakers, speaker_errors = _load(root / "data" / "speakers.yml")
    cfg, _errors = _load(root / "data" / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    if not isinstance(cfg, dict):
        print(
            "data/config.yml is missing or invalid -- cannot compute eligibility",
            file=sys.stderr,
        )
        return 1

    platform = platform_from_env(
        os.environ, speaker_list, cfg, _conference_ids_from_env(event_id)
    )
    try:
        rows = platform.get_attendance(event_id)
    except (AttendanceImportError, FCCRequestError, EventNotFoundError) as exc:
        # `EventNotFoundError` joined this tuple in fix round 3 (Critical
        # B): with no `CONVENER_FCC_CONFERENCE_ID` configured for this event,
        # `PlatformFCC._conference_id` raises it, and before this round
        # nothing here caught it -- `issue_certificates`'s own docstring
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
                f"data/speakers.yml: {'; '.join(speaker_errors)} -- refusing "
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
        # `result.token` is deliberately dropped: task 14 recomputes it
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
            # R-26, fix round 1: every register row for this fingerprint
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
            CERTIFICATES_HEADER + _dump(register_to_data(tuple(entries))),
            encoding="utf-8",
            newline="",
        )

    # R-27, fix round 1: hand the freshly-issued identifiers (public by
    # design -- already printed on the document, already published in
    # certificates-public.json) to the delivery step through
    # `$GITHUB_OUTPUT`, so a re-dispatch after a corrected export mails
    # only the newly corrected certificates, not every past attendee
    # again. Written even when empty -- an empty `issued_ids=` is exactly
    # what tells `convener-deliver-certificates` this run minted nothing new,
    # so it should deliver nothing (see that function's own docstring).
    _write_github_output(f"issued_ids={','.join(freshly_issued_ids)}\n")

    refused_note = f", {refused_count} refused (revoked, use convener-reissue-certificate)"
    print(
        f"certificates for event {event_id}: {issued_count} issued, "
        f"{already_count} already on record"
        f"{refused_note if refused_count else ''} ({len(eligible)} eligible)"
    )
    return 0


def certificates_public_data() -> int:
    """`convener-certificates-public-data`: rebuild
    `public-data/certificates-public.json` from every event's own
    `data/events/<id>/certificates.yml`, following `public_data`'s own
    precedent for `events-public.json` (`certificate.public_register` is
    the pure projection this calls, the same split `public_data.to_public`
    draws for the speaker list).

    Reads every `certificates.yml` under `data/events/*/` that exists --
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
            # Minor 5 (fix round 1): relative to `root`, not the whole
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
    out_dir = root / "public-data"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "certificates-public.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} certificates")
    return 0


def _load_certificate_register(
    root: Path, event_id: str
) -> tuple[Path, tuple[CertificateEntry, ...]] | None:
    """Load `event_id`'s register -- factored out (fix round 2) so
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
    factored out (task 14) so `reissue_certificate` and
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
    `certificate.issue`'s own lookup (R-22): resolve a public certificate
    id to a person by fingerprint alone, never by accepting or holding an
    address. Factored out (task 14) so `reissue_certificate` and
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
    touching the row it replaces (R-18, fix round 1, Important 3).

    Unlike `convener-issue-certificates`, this is never a scheduled job: an
    operator runs it by hand, once, for one certificate, after revoking
    the one it replaces (`convener-revoke-certificate`, R-21, fix round 2).
    See `certificate.reissue`'s own docstring for why this has to be a
    separate, explicit command rather than a change to
    `convener-issue-certificates`'s own idempotent lookup: that job must keep
    refusing to resurrect a revoked certificate on a routine re-run, which
    is only true as long as reissuing never happens inside its loop.

    Reads `EVENT_ID`, `EVENT_PRIVATE_KEY`, `CONVENER_SIGNING_KEY`,
    `CONVENER_MATCHING_SALT` and `CONVENER_FCC_CONFERENCE_ID` exactly as
    `convener-issue-certificates` does -- the same D-13 shapes, and the same
    `_conference_ids_from_env` resolution (Critical B, fix round 3) --
    plus `CERTIFICATE_ID`, the certificate this run corrects (R-22, fix
    round 2).

    **`CERTIFICATE_ID` is shape-checked before it is ever echoed (minor 2,
    fix round 3).** `certificate.is_valid_identifier` -- the exact 32
    lowercase hex characters `_new_identifier` always produces -- is
    checked immediately after this value is read, the same one-line
    discipline `eventkeys.secret_name` already gives `EVENT_ID`.
    `.strip()` alone only removes a *leading or trailing* newline; an id
    shaped `"abc\\n::add-mask::secret"` would otherwise put a GitHub
    Actions workflow command at the start of a log line the moment this
    function's own refusal or success message printed it back.

    **`CERTIFICATE_ID`, never an address (R-22).** A `workflow_dispatch`
    input is rendered on the run page and retained with the run for as
    long as the run's own history exists -- longer than the 14-day
    artefact this project uses everywhere it has to carry personal data
    at all, and exactly the exposure task 7's own Important 4 named. This
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
        # Minor 2, fix round 3: never echo a malformed value back -- the
        # same "no valid event id supplied" idiom `eventkeys.secret_name`'s
        # own caller above already uses for the identical reason.
        print("not a valid certificate id supplied", file=sys.stderr)
        return 1

    root = repo_root()
    rel_path = Path("data") / "events" / event_id / "registrations.enc"
    enc_path = root / rel_path
    if not enc_path.exists():
        print(f"no registrations recorded for event {event_id}", file=sys.stderr)
        return 1
    try:
        current = load_registration_file(enc_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"{rel_path.as_posix()}: {exc}", file=sys.stderr)
        return 1

    registrations: list[Registration] = []
    for entry in current.entries:
        registration = to_registration(json.dumps(entry), private_pem)
        if registration is not None:
            registrations.append(registration)

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

    speakers, speaker_errors = _load(root / "data" / "speakers.yml")
    cfg, _errors = _load(root / "data" / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    if not isinstance(cfg, dict):
        print(
            "data/config.yml is missing or invalid -- cannot compute eligibility",
            file=sys.stderr,
        )
        return 1

    platform = platform_from_env(
        os.environ, speaker_list, cfg, _conference_ids_from_env(event_id)
    )
    try:
        rows = platform.get_attendance(event_id)
    except (AttendanceImportError, FCCRequestError, EventNotFoundError) as exc:
        # See `issue_certificates`'s own comment on the identical
        # `EventNotFoundError` addition (Critical B, fix round 3).
        print(str(exc), file=sys.stderr)
        return 1

    matched = match(rows, registrations, MatchEvent(event_id=event_id, salt=salt))
    threshold = EligibilityThreshold.from_config(cfg)
    eligible = eligible_attendees(matched, threshold)

    # R-22: resolve the certificate to a candidate by fingerprint, the
    # same derivation `certificate.issue` performs, run in reverse --
    # never by reading an address out of the register (it holds none) or
    # accepting one as input (see the docstring above). Shared with
    # `deliver_certificate` (task 14) through `_find_attendee_by_fingerprint`
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
                f"data/speakers.yml: {'; '.join(speaker_errors)} -- refusing "
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
        CERTIFICATES_HEADER + _dump(register_to_data((*existing, result.entry))),
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
    `STATE_REVOKED` in the register (R-21, fix round 2) -- the operation
    spec S:7 names by itself ("Révocation"), and the one this module
    always had a tested, correct pure function for (`certificate.revoke`)
    and, until this round, no caller at all.

    Round 1 reasoned that a hand edit of the committed-clear register was
    a legitimate way to flip one entry's `state` (`cli.py`'s own docstring
    at the time; see the fix round 1 report's Concern 2). R-21 does not
    accept that: it depends on a volunteer having a working checkout,
    finding the right file, editing the right row, and committing it
    correctly -- exactly the "a collaborator's goodwill or their post"
    dependency this whole project refuses to build on elsewhere -- and
    `revoke`'s own guard against naming an identifier that is not in the
    register is unreachable from a text editor, which is precisely where
    that mistake gets made.

    Reads `EVENT_ID` and `CERTIFICATE_ID` -- both public identifiers,
    never an address (R-22; see `reissue_certificate`'s own docstring for
    why an address is never accepted by any command in this module that a
    `workflow_dispatch` form could expose). `CERTIFICATE_ID` is
    shape-checked the same way `reissue_certificate` checks it (minor 2,
    fix round 3) -- see that function's own docstring for why. Needs no
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
        # `event_id` is passed alongside `certificate_id` since fix round
        # 3 (minor 1): `revoke` now filters on both, the same "this
        # event's own certificate" `reissue` already required, rather than
        # matching an identifier alone across whatever `existing` happens
        # to hold.
        updated = revoke(existing, event_id, certificate_id)
    except ValueError as exc:
        print(f"cannot revoke for event {event_id}: {exc}", file=sys.stderr)
        return 1

    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text(
        CERTIFICATES_HEADER + _dump(register_to_data(updated)),
        encoding="utf-8",
        newline="",
    )
    print(f"certificate {certificate_id} revoked for event {event_id}")
    return 0


def deliver_certificates() -> int:
    """`convener-deliver-certificates`: e-mail every currently eligible
    attendee's certificate for one event (spec S:7's "Remise": "Par
    courriel. Jamais de document nominatif depose dans un depot.") -- the
    step `issue-certificates.yml` runs immediately after
    `convener-issue-certificates` itself, in the same job and the same
    checkout, so this function's own re-derivation of the register (via
    `_load_certificate_register`) reads exactly what that step just wrote.

    Re-derives registrations, attendance and eligibility from scratch,
    exactly as `issue_certificates` does -- the same "recalcule sans
    reinscrire" discipline (spec S:8) -- and then calls `certificate.issue`
    again for each eligible attendee. That second call never grows the
    register (`issue`'s own fingerprint-keyed lookup reuses the existing
    entry's `identifier`, `certificate.py`'s own module docstring,
    "idempotent without being deterministic") and reproduces the exact
    same signed token every time (`signing.sign` is deterministic) -- so
    running this command again, for a delivery that failed the first
    time, replays the identical document rather than minting a second
    certificate for the same person (spec S:8's own guarantee, and
    `delivery.py`'s module docstring, "replayable, not regenerated").

    Never writes anything to disk (ruling 1, task 14): the rendered
    document lives only in memory for the length of one e-mail send
    (`delivery.render_certificate`, `delivery.deliver`) and is never
    written to a file, an artefact, or printed. A failed delivery is
    reported -- folded into the printed count, never named individually --
    and replayed by re-running this same command; see `delivery.py`'s own
    module docstring, "never written to disk", for why the pattern task 7
    uses for an unsent confirmation (`UNSENT_CONFIRMATION`, a 14-day
    build artefact) is the wrong one here: what it would retain is a
    nominative, signed document, in an Actions surface, exactly what spec
    S:7 forbids.

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
    `data/config.yml`, a platform that cannot answer, or a speaker record
    with no title and no date all refuse the whole run (exit 1) before
    anything is delivered. **A missing certificate register also refuses
    (Minor 1, fix round 1):** with no `certificates.yml` on disk for this
    event, `issue`'s own "no row" branch would mint a fresh identifier
    that this function never persists (only `issue_certificates` writes
    the register) -- a certificate mailed once and never again reproducible.
    Unreachable from the shipped workflow, which only ever runs this step
    after `issue_certificates` has already written the file, but this
    command is dispatchable on its own, so the guard is not decorative.

    Once eligibility is computed, this command never fails the whole run
    again. Three outcomes, each counted separately and printed by name,
    never folded into one indistinguishable bucket (Important 3, fix
    round 1):

    - **`issue` refuses (R-26):** every register row for this fingerprint
      is revoked. Counted with the ordinary "not sent" total -- a revoked
      certificate is never delivered, by any path, but this is not a
      renderer crash or a transport failure, so it does not inflate
      either of those.
    - **Rendering or composing the document raises:** counted separately
      from a transport failure (`render_failed_count`) -- `delivery.deliver`
      below never raises for an ordinary send failure, it *returns*
      `sent=False`, so anything caught here is this module's own code
      (the concrete, reachable case: `event.title` overflowing the QR --
      see `certificate.CertificateEvent`'s own `_MAX_TITLE_LENGTH`, which
      this round also added, for why that specific crash can no longer
      happen, though a still-unanticipated one is handled identically).
      An operator seeing this count knows to look at the code or the data,
      never at the mail secrets.
    - **`delivery.deliver` returns `sent=False`:** no transport configured,
      or a configured one that raised and was already caught inside
      `delivery.deliver` itself. Counted as `unsent_count`, the ordinary
      D-13 shape.

    None of these three stops delivery to the rest of `eligible`; the
    exception's own text is never printed, only counted, and the message
    also lists the *identifiers* (never a name or an address) that did not
    go out (R-27, fix round 1) -- an operator whose one bounce failed can
    then name it directly to `convener-deliver-certificate`, rather than
    reaching for the batch that caused the problem in the first place.

    **Restricted by default to what this run's own issuance step just
    minted (R-27, fix round 1).** `DELIVER_ONLY` -- a comma-joined set of
    identifiers, ordinarily `issue_certificates`'s own `issued_ids` output,
    forwarded by `issue-certificates.yml` -- skips every eligible attendee
    whose identifier is not in that set, counted separately
    (`skipped_count`, "not targeted this run"), never as unsent. Unset
    entirely (a manual, standalone run outside that workflow) or
    `RESEND_ALL=true` (an operator's own deliberate batch retry, never the
    default) both mean no restriction at all -- every eligible attendee is
    targeted, the behaviour this function always had before this round.
    `DELIVER_ONLY` set to the empty string -- an issuance run that minted
    nothing new -- means every eligible attendee is skipped: the whole
    point of the hand-off is that a re-dispatch after nothing changed
    mails nobody again.

    Prints only counts and public identifiers, never a name or an
    address, on every path -- including an attendee who was already on
    record before this run started (Important 10 in `certificate.py`'s
    own review history: a name printed on exactly that branch survived a
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
    rel_path = Path("data") / "events" / event_id / "registrations.enc"
    enc_path = root / rel_path
    if not enc_path.exists():
        print(f"no registrations recorded for event {event_id}", file=sys.stderr)
        return 1
    try:
        current = load_registration_file(enc_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"{rel_path.as_posix()}: {exc}", file=sys.stderr)
        return 1

    registrations: list[Registration] = []
    for entry in current.entries:
        registration = to_registration(json.dumps(entry), private_pem)
        if registration is not None:
            registrations.append(registration)

    speakers, speaker_errors = _load(root / "data" / "speakers.yml")
    cfg, _errors = _load(root / "data" / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    if not isinstance(cfg, dict):
        print(
            "data/config.yml is missing or invalid -- cannot compute eligibility",
            file=sys.stderr,
        )
        return 1

    platform = platform_from_env(
        os.environ, speaker_list, cfg, _conference_ids_from_env(event_id)
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
                f"data/speakers.yml: {'; '.join(speaker_errors)} -- refusing "
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
        # Minor 1, fix round 1: nothing to reproduce from -- see this
        # function's own docstring for why minting here anyway would be
        # unsafe (an identifier written nowhere).
        print(f"no certificate register for event {event_id}", file=sys.stderr)
        return 1

    event = CertificateEvent(event_id=event_id, title=title, date=event_date)
    issued_on = paris_today(datetime.now(UTC))
    max_duration_seconds = threshold.seminar_duration_minutes * 60

    # R-27, fix round 1: restrict to what this run's own issuance step
    # just minted, unless an operator has explicitly asked for everyone.
    # See this function's own docstring for the full contract.
    resend_all = os.environ.get("RESEND_ALL", "").strip().lower() == "true"
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
            # R-26: every register row for this fingerprint is revoked --
            # never resurrect it here.
            unsent_count += 1
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
        except Exception:  # Important 3: our own code, not the transport
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
        f"{unsent_count} not sent, {render_failed_count} failed to render, "
        f"{skipped_count} not targeted this run ({len(eligible)} eligible)"
    )
    if unsent_ids:
        # R-27, fix round 1: identifiers are public by design -- never a
        # name or an address -- so an operator can copy one straight into
        # convener-deliver-certificate's own CERTIFICATE_ID input.
        print(f"not sent: {', '.join(sorted(unsent_ids))}")
    return 0


def deliver_certificate() -> int:
    """`convener-deliver-certificate`: (re)deliver one already-issued
    certificate, named by `CERTIFICATE_ID` -- the manual resend `spec S:9`
    asks for ("un certificat dans les indesirables n'existe pas"), for the
    one document R-22 forbids ever accepting an address to redeliver.

    Reuses `reissue_certificate`'s own `CERTIFICATE_ID` -> attendee
    resolution (`_find_register_entry`, `_find_attendee_by_fingerprint`)
    rather than writing a second lookup: `CERTIFICATE_ID` is a public,
    printed-on-the-document identifier, resolved to a register row and then
    to a currently-eligible attendee by fingerprint alone, run in reverse
    from `certificate.issue`'s own derivation -- never by reading or
    accepting an address (see `reissue_certificate`'s own docstring for the
    full reasoning this shares).

    **Signs `target_entry` directly, via `certificate.sign_for`, never
    `certificate.issue` (R-26, fix round 1, Critical 1).** `issue`
    re-resolves by *fingerprint*, taking the currently-issued row for that
    fingerprint -- almost always `target_entry` itself, but not after a
    revoke-and-reissue with no correction applied here: the register would
    then read `[old(revoked)]` or (mid-correction) still resolve to a row
    other than the one `CERTIFICATE_ID` named. Before this round this
    function resolved `target_entry` correctly and then discarded it by
    calling `issue` anyway -- naming one certificate in its own log while
    delivering whatever `issue` happened to resolve. `sign_for` signs the
    exact row this function already holds; nothing here re-resolves
    anything by fingerprint at all.

    **Refuses a revoked `target_entry` outright (R-26).** Checked
    immediately after resolving it by `CERTIFICATE_ID`, before eligibility
    is even computed -- a revoked certificate is not delivered, ever, by
    any path; the correction is `convener-reissue-certificate`, run by hand.

    Every refusal before resolution mirrors `reissue_certificate`'s own
    handling: a bad event id, a missing private key, `CONVENER_SIGNING_KEY` or
    `CONVENER_MATCHING_SALT` absent (both ordinary D-13, nothing delivered, a
    clean exit -- for `CONVENER_MATCHING_SALT` the same stronger reason
    `certificate.py`'s module docstring gives), a missing or malformed
    `CERTIFICATE_ID`, missing or malformed `registrations.enc`, an unknown
    or revoked certificate id, a missing or malformed `data/config.yml`, a
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
    "replayable, not regenerated" -- bounded, after task 15's retention
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
    rel_path = Path("data") / "events" / event_id / "registrations.enc"
    enc_path = root / rel_path
    if not enc_path.exists():
        print(f"no registrations recorded for event {event_id}", file=sys.stderr)
        return 1
    try:
        current = load_registration_file(enc_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"{rel_path.as_posix()}: {exc}", file=sys.stderr)
        return 1

    registrations: list[Registration] = []
    for entry in current.entries:
        registration = to_registration(json.dumps(entry), private_pem)
        if registration is not None:
            registrations.append(registration)

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
        # R-26, fix round 1, Critical 1: a revoked certificate is not
        # delivered, ever, by any path -- refuse outright rather than
        # ever reaching a signer with it.
        print(
            f"certificate {certificate_id} is revoked for event {event_id} "
            "-- not delivered; use convener-reissue-certificate for a correction",
            file=sys.stderr,
        )
        return 1

    speakers, speaker_errors = _load(root / "data" / "speakers.yml")
    cfg, _errors = _load(root / "data" / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    if not isinstance(cfg, dict):
        print(
            "data/config.yml is missing or invalid -- cannot compute eligibility",
            file=sys.stderr,
        )
        return 1

    platform = platform_from_env(
        os.environ, speaker_list, cfg, _conference_ids_from_env(event_id)
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
                f"data/speakers.yml: {'; '.join(speaker_errors)} -- refusing "
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
    capped_attendee = replace(
        attendee,
        duration_seconds=min(
            attendee.duration_seconds, threshold.seminar_duration_minutes * 60
        ),
    )
    try:
        # R-26, fix round 1, Critical 1: sign `target_entry` -- the row
        # `CERTIFICATE_ID` actually named -- rather than calling `issue`,
        # which re-resolves by fingerprint and could hand back a
        # different row (the exact bug this round found: this command
        # named one certificate in its own log and delivered another).
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


def _consent_granted(record: Mapping[str, Any]) -> bool:
    """Whether this event's speaker explicitly agreed to publication --
    read directly, not through `public_data.recording_withheld`, because
    that function answers a different question and round 3 wiring it in
    here was wrong (caught on review, round 4). `recording_withheld` has
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
    `tools/tests/test_cli.py::test_delete_recording_has_exactly_two_call_sites_both_in_cli`).
    `delete_recording` exists because of the chosen platform's
    storage quota (spec Section 2/9: a 90-minute recording costs roughly
    1.6x the free tier's entire 1 GB allowance) -- freeing it after every
    event is a condition of operation, not an optimisation, and getting
    the order wrong loses a recording forever.

    The two-trace shape this enforces is not invented here: it reproduces
    a design ruling already recorded in
    `.superpowers/sdd/phase-4-prep-notes.md` ("2026-08-19 -- DESIGN RULING
    for the spec: who deletes the recording, and on what evidence"), and
    `platform_fcc.py`'s module docstring cites it in full; this function's
    job is carrying that ruling into a real, tested call order.

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
    enforces that rather than only documenting it (fix round 3; corrected
    in round 4).** A recording that must never become public -- the
    discussion segment (recorded on purpose, phase 3's own three-step
    discipline, but never published), or a talk whose publication consent
    was withheld -- must never take this path: trace 2 can only be
    satisfied by converting to MP4, and a converted file stays *publicly
    reachable at its own URL even after the conference is deleted*
    (verified empirically). Proving retrieval this way is exactly the
    exposure those two cases exist to prevent. So before either trace is
    even checked, this function refuses unless `_consent_granted` reads
    `publication.consent == "granted"` on the event's own speaker record.

    **Consent alone, not `public_data.recording_withheld`.** Round 3
    wired that function in here and it was wrong, caught on review:
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
    failure this whole task exists to prevent, for every fresh talk, every
    time. `discard_recording` below is the other route: no proof of
    retrieval is asked for or accepted, because none may ever exist. See
    its own docstring, and `platform_fcc.py`'s module docstring's "Which
    recordings take which route" section, for the full split. This
    function never downloads the recording itself, and calls nothing that
    could trigger a conversion on its own -- only the host's Download
    click does that, and only a consented recording headed for YouTube
    should ever receive one.

    The quota is checked *after* deletion, deliberately (spec Section 9:
    "alerte si l'espace reste occupe"), because a saturated quota breaks
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
    `docs/reference/operations.md`). `PlatformFCC._conference_id` validates
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
    speakers, errors = _load(root / "data" / "speakers.yml")
    cfg, cfg_errors = _load(root / "data" / "config.yml")
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

    # Enforced, not only documented (fix round 3; corrected round 4): the
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
    `tools/tests/test_cli.py::test_delete_recording_has_exactly_two_call_sites_both_in_cli`).

    **This is not `release_recording` with a shortcut.** The two
    operations have opposite preconditions on purpose, and neither can
    reach the other's call to `delete_recording`: `release_recording`
    requires proof the recording *was* retrieved; this function requires
    proof the operator is *choosing not to retrieve it at all*, because
    for the two cases it exists for -- the discussion segment (recorded
    on purpose, phase 3's own discipline, never published) and a talk
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
    reason `release_recording` does (spec Section 9) -- a saturated quota
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
    speakers, errors = _load(root / "data" / "speakers.yml")
    cfg, cfg_errors = _load(root / "data" / "config.yml")
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


#: Where a message that has somewhere to go is left for the workflow to post.
#:
#: The file's *existence* is the whole signal: it is written only when
#: `notify.dispatch` returned a `Dispatch`, which cannot happen without a
#: configured channel. `.github/workflows/notify.yml` posts what it finds here
#: and does nothing at all when it finds nothing -- so there is no
#: "notifications on/off" switch anywhere in the chain, only a message that
#: either has an address or was never composed with one. Git-ignored: it is a
#: run artefact, never a file anybody edits.
NOTIFY_BODY: Final = "notify-body.md"

#: The parent of HEAD, as a fixed `git show` argument. The fallback, used when
#: the run does not know where the branch actually moved from.
PREVIOUS_SPEAKERS: Final = "HEAD~1:data/speakers.yml"

#: An object name, and nothing else, may be interpolated into `git show`.
#: Anchored and hexadecimal, so no value of `BEFORE` can become an option or a
#: second argument -- the same discipline `PREVIOUS_SPEAKERS` keeps by being a
#: constant.
_OBJECT_NAME: Final = re.compile(r"[0-9a-f]{40}")


def previous_revision(env: Mapping[str, str]) -> str:
    """The revision of the speaker file to compare against.

    `HEAD~1` is only the previous *commit*, not the previous state of the
    branch. A push carrying three commits moved the branch by three, so
    comparing against the parent of HEAD describes the last one and silently
    drops the events of the other two. GitHub sends where the branch actually
    was as `github.event.before`, and `.github/workflows/notify.yml` passes it
    through as `BEFORE`; that is what this prefers.

    Falls back to `HEAD~1` when `BEFORE` is absent, malformed, or the all-zero
    name GitHub sends for the first push to a branch (`NO_PARENT`) -- there is
    no earlier state to read in that last case, and the caller turns a `git
    show` failure into "nothing to compare, so nothing to say".
    """
    before = env.get("BEFORE", "").strip()
    if _OBJECT_NAME.fullmatch(before) and before.strip("0"):
        return f"{before}:data/speakers.yml"
    return PREVIOUS_SPEAKERS


def _git_show(root: Path, revision: str) -> tuple[str, str]:
    """`data/speakers.yml` as of `revision`, or an explanation.

    A shallow clone, an initial commit, or a repository with no such revision
    all land in the error half, and the caller turns that into "nothing to
    compare, so nothing to say" -- never into a message.
    """
    # shell=False and `revision` is either a constant or an object name that
    # matched `_OBJECT_NAME`, so it can be neither an option nor a second
    # argument: B603 and B607 both describe a risk this call does not carry.
    result = subprocess.run(  # nosec B603 B607
        ["git", "show", revision],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        first = next(iter(result.stderr.strip().splitlines()), "")
        return "", first or "no parent commit"
    return result.stdout, ""


def _notify(message: str | None) -> int:
    """Print what was composed, and leave it for the workflow only if it has
    somewhere to go.

    Always exits 0. Nothing to say, no channel configured, and both at once are
    the same outcome here, and none of them is a failure: an absent integration
    is a normal state (D-13), and a quiet day is the point of the digest.

    The composed text is printed to the job log either way, so a repository
    with no channel yet still lets a volunteer read what *would* have been
    sent -- the same "written to an inspectable log instead of being sent"
    behaviour `config/integrations.yml` promises for outbound email.
    """
    if message is None:
        print("nothing to notify")
        return 0

    print(message)
    if "--dry-run" in sys.argv[1:]:
        print("")
        print("[dry run] nothing was written and nothing was addressed")
        return 0

    addressed = dispatch(message, os.environ)
    if addressed is None:
        print("")
        print("no notification channel is configured - nothing was addressed")
        return 0

    path = repo_root() / NOTIFY_BODY
    path.write_text(addressed.body, encoding="utf-8", newline="")
    print("")
    print(f"addressed to thread {addressed.channel.thread}; left in {NOTIFY_BODY}")
    return 0


def notify_immediate() -> int:
    """`convener-notify-immediate`: the three events spec section 7 interrupts for.

    Compares the working tree's speaker file against the state the branch was
    in before the push (`previous_revision`), so a push carrying several
    commits reports the events of all of them rather than only the last. With
    no earlier revision to read there is no change to describe, so this says
    nothing rather than treating the whole file as new -- which on a fresh
    clone would announce every lead in it at once.
    """
    root = repo_root()
    after, errors = _load(root / "data" / "speakers.yml")
    if errors:
        for error in errors:
            print(f"  - {error}")
        return 1

    text, error = _git_show(root, previous_revision(os.environ))
    if error:
        print(f"no previous revision to compare against ({error}); nothing to notify")
        return 0
    try:
        before = yaml_safe_load(text)
    except yaml.YAMLError as exc:
        print(f"previous speakers.yml is not readable ({exc}); nothing to notify")
        return 0

    return _notify(render_events(immediate_events(before or [], after or [])))


def notify_digest() -> int:
    """`convener-notify-digest`: one message for the day, or none at all.

    `--dry-run` composes and prints, and writes nothing.
    """
    root = repo_root()
    speakers, errors = _load(root / "data" / "speakers.yml")
    cfg, cfg_errors = _load(root / "data" / "config.yml")
    if errors or cfg_errors:
        for error in errors + cfg_errors:
            print(f"  - {error}")
        return 1

    return _notify(daily_digest(speakers or [], cfg or {}, datetime.now(UTC)))


def _git_log(root: Path) -> tuple[str, str]:
    """The whole history in `register.LOG_FORMAT`, oldest commit first.

    The one subprocess in this package, and it is why it lives in `cli`: the
    rest of `convener_ops` stays a pure library that a test can drive without a
    checkout. Fixed argv, no shell, no interpolated value -- there is nothing
    here for a commit message to escape into, because no commit message is
    passed in; only read out.
    """
    # Fixed argv, shell=False, nothing interpolated: B603 and B607 both
    # describe a risk this call does not carry.
    result = subprocess.run(  # nosec B603 B607
        ["git", "log", "--reverse", f"--format={LOG_FORMAT}"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return "", result.stderr.strip() or "git log failed"
    return result.stdout, ""


def register() -> int:
    """`convener-register`: rewrite the decision register from the commits.

    Rewrite, not append. The file is a function of the history and of nothing
    else, so the safe thing to do with whatever is on disk is to replace it --
    which is also what makes a hand-written row impossible to keep. `--dry-run`
    prints the same bytes and touches nothing.

    `--check` writes nothing either and exits 1 when the committed file is not
    what the history derives. Rewriting is what makes a hand edit impossible to
    *keep*; on its own it leaves the edit standing in the repository between a
    push and the next run, which is the window this mode closes. The comparison
    is meaningful because the rendering reads no clock, no `data/*.yml` and no
    environment: two runs over the same commits produce the same bytes, so a
    difference can only be a change made outside the history.
    """
    dry_run = "--dry-run" in sys.argv[1:]
    check = "--check" in sys.argv[1:]
    root = repo_root()
    log, error = _git_log(root)
    if error:
        print(f"cannot read the commit history: {error}", file=sys.stderr)
        return 1

    entries = entries_from_log(log)
    rendered = render_register(entries)
    if dry_run:
        sys.stdout.write(rendered)
        return 0

    path = root / REGISTER_PATH
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if check:
        if current != rendered:
            print(
                f"{REGISTER_PATH.as_posix()} is not what the commit history derives.",
                file=sys.stderr,
            )
            print(
                "It is derived, not authored: run `convener-register` and commit the"
                " file it writes.",
                file=sys.stderr,
            )
            return 1
        print(f"register matches the history - {len(entries)} decision(s)")
        return 0
    if current == rendered:
        print(f"register unchanged - {len(entries)} decision(s)")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8", newline="")
    print(f"wrote {REGISTER_PATH.as_posix()} - {len(entries)} decision(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    # Unreachable under both ways this module is ever run: pytest imports
    # it as convener_ops.cli, never as __main__, and every console script in
    # [project.scripts] (convener-validate and the rest) calls its target
    # function directly -- neither executes this module as a script. Only
    # `python convener_ops/cli.py` or `python -m convener_ops.cli` would, and this
    # project does not invoke it that way.
    sys.exit(validate())
