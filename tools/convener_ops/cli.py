"""Command-line entry points. This is the only module that touches the disk."""

from __future__ import annotations

import json
import os
import re

# One fixed git invocation, in `_git_log` and nowhere else; see its docstring.
import subprocess  # nosec B404
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import yaml

from convener_ops import confirmation, eventkeys, signing
from convener_ops.attendance import (
    EligibilityThreshold,
    MatchEvent,
    eligible_attendees,
    match,
)
from convener_ops.certificate import (
    CertificateEvent,
    issue,
    public_register,
    register_from_data,
    register_to_data,
)
from convener_ops.governance import paris_today
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
    Registration,
    dump_registration_file,
    event_id_from_payload,
    find_by_email,
    load_registration_file,
    matching_code,
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
    except (AttendanceImportError, FCCRequestError) as exc:
        # Both are "the platform did not answer", from this caller's own
        # point of view -- the manual path's missing-file/malformed-header
        # failure, or the chosen platform's own network/API failure
        # (`platform_fcc.py`'s own docstring: named generically for
        # exactly this, so a caller does not have to know which
        # implementation it is holding to handle "no data" uniformly).
        # Catching only the first would leave a real API outage as an
        # uncaught traceback instead of the same clean one-line failure
        # every other error path in this function already gives.
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


def issue_certificates() -> int:
    """`convener-issue-certificates`: match this event's attendance, work out
    who is eligible (spec S:5), and issue -- or reproduce -- a certificate
    for each of them (spec S:7, task 12).

    Reads `EVENT_ID` and `EVENT_PRIVATE_KEY` exactly as `match_attendance`
    does, for the same reason: this job re-derives the match from scratch
    rather than trusting a prior run's own answer, so a corrected
    registration or a corrected attendance export is picked up for free
    (spec S:8: "un appariement corrigé se recalcule sans réinscrire").

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
    needed the config file in the first place. A missing speaker record
    for `event_id` is not fatal: certificates are still issued, with an
    empty event title and date, and a line says so -- the same "never let
    a missing room lookup stop the thing that matters" choice
    `_send_confirmation` already makes for the confirmation e-mail.

    Prints only counts, never a name or an address -- the same discipline
    `match_attendance` already holds itself to for the same reason.
    `data/events/<id>/certificates.yml` is rewritten, as a whole file
    (never appended to a partial one), only when at least one certificate
    was freshly minted; reissuing every attendee already on record writes
    nothing and still exits 0.
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

    speakers, _errors = _load(root / "data" / "speakers.yml")
    cfg, _errors = _load(root / "data" / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    if not isinstance(cfg, dict):
        print(
            "data/config.yml is missing or invalid -- cannot compute eligibility",
            file=sys.stderr,
        )
        return 1

    platform = platform_from_env(os.environ, speaker_list, cfg)
    try:
        rows = platform.get_attendance(event_id)
    except (AttendanceImportError, FCCRequestError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    matched = match(rows, registrations, MatchEvent(event_id=event_id, salt=salt))
    threshold = EligibilityThreshold.from_config(cfg)
    eligible = eligible_attendees(matched, threshold)

    record: Mapping[str, Any]
    try:
        record = find_speaker(speaker_list, event_id)
    except EventNotFoundError:
        print(
            f"no speaker record matches event {event_id} -- certificates "
            "issued with no title or date"
        )
        record = {}

    register_path = root / "data" / "events" / event_id / "certificates.yml"
    if register_path.exists():
        try:
            register_data = yaml_safe_load(register_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(f"{register_path.name}: invalid YAML - {exc}", file=sys.stderr)
            return 1
    else:
        register_data = None
    try:
        existing = register_from_data(register_data)
    except ValueError as exc:
        print(f"{register_path.name}: {exc}", file=sys.stderr)
        return 1

    event = CertificateEvent(
        event_id=event_id,
        title=str(record.get("title", "") or ""),
        date=str(record.get("date", "") or ""),
    )
    issued_on = paris_today(datetime.now(UTC))

    entries = list(existing)
    issued_count = 0
    already_count = 0
    for attendee in eligible:
        result = issue(
            attendee,
            event,
            signing_key,
            salt,
            tuple(entries),
            issued_on=issued_on,
        )
        if result.already_registered:
            already_count += 1
        else:
            entries.append(result.entry)
            issued_count += 1

    if issued_count:
        register_path.parent.mkdir(parents=True, exist_ok=True)
        register_path.write_text(
            CERTIFICATES_HEADER + _dump(register_to_data(tuple(entries))),
            encoding="utf-8",
            newline="",
        )

    print(
        f"certificates for event {event_id}: {issued_count} issued, "
        f"{already_count} already on record ({len(eligible)} eligible)"
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
    events_dir = root / "data" / "events"
    entries: list[Any] = []
    if events_dir.is_dir():
        for register_path in sorted(events_dir.glob("*/certificates.yml")):
            try:
                data = yaml_safe_load(register_path.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                print(f"{register_path}: invalid YAML - {exc}", file=sys.stderr)
                return 1
            try:
                entries.extend(register_from_data(data))
            except ValueError as exc:
                print(f"{register_path}: {exc}", file=sys.stderr)
                return 1

    rows = public_register(entries)
    out_dir = root / "public-data"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "certificates-public.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} certificates")
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
