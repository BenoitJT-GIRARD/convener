"""Command-line entry points. This is the only module that touches the disk."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil

# One fixed git invocation, in `_git_log` and nowhere else; see its docstring.
import subprocess  # nosec B404
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any, Final

import yaml

from convener_ops import (
    actions_usage,
    agenda,
    announce,
    confirmation,
    delivery,
    eventkeys,
    formats,
    published,
    queue_watch,
    registration_routing,
    retention_liveness,
    routing_watch,
    signing,
    submission_queue,
    survey_invite,
    visual,
)
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
from convener_ops.dispatch_alert import alert_message
from convener_ops.governance import PARIS, paris_today
from convener_ops.integrations import (
    ABSENT,
    Integration,
    load_declaration,
    resolve_states,
)
from convener_ops.notify import daily_digest, dispatch, immediate_events, render_events
from convener_ops.paths import DATA_DIR, PUBLIC_DATA_DIR, REGISTER_PATH, repo_root
from convener_ops.platform import (
    ENCRYPTED_ATTENDANCE_FILENAME,
    AttendanceImportError,
    EventNotFoundError,
    Room,
    dump_attendance_export_file,
    encrypt_attendance_rows,
    erase_attendance_rows,
    find_speaker,
    load_attendance_export_file,
    parse_attendance_csv,
)
from convener_ops.platform_fcc import (
    FCCRequestError,
    PlatformFCC,
    converted_recording_is_reachable,
    missing_retrieval_evidence,
    platform_from_env,
)
from convener_ops.proposal import field_value, skip_reason, to_lead, verify_signature
from convener_ops.public_data import to_public, to_survey_status
from convener_ops.register import (
    LOG_FORMAT,
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
SPEAKERS_HEADER = "# Speakers (unified schema v6 — see docs/reference/schema.md)\n"
CONFIG_HEADER = "# Repo-wide config for the convener app\n"
#: certificates.yml holds no name and no address by construction -- see
#: tools/convener_ops/certificate.py's module docstring for why this file
#: survives the retention sweep on registrations.enc, in the same
#: directory, untouched.
CERTIFICATES_HEADER = (
    "# Certificate register -- no name, no address; "
    "see tools/convener_ops/certificate.py\n"
)
#: The destruction registry holds only an event id and a date --
#: see tools/convener_ops/eventkeys.py's module docstring, "the destruction
#: registry lives in one file".
DESTRUCTIONS_HEADER = (
    "# Event key destruction registry; see tools/convener_ops/eventkeys.py\n"
)
#: The survey invitation registry holds only an event id and a
#: date -- see tools/convener_ops/survey_invite.py's module docstring for
#: why this is the whole bound a resend is checked against.
SURVEY_INVITATIONS_HEADER = (
    "# Survey invitation registry -- no name, no address; "
    "see tools/convener_ops/survey_invite.py\n"
)
#: Evidence that retention.yml's own
#: schedule still fires, independent of whether that day's sweep found
#: anything due; see tools/convener_ops/retention_liveness.py's own module
#: docstring.
RETENTION_LAST_RUN_HEADER = (
    "# Evidence the retention sweep still runs; "
    "see tools/convener_ops/retention_liveness.py\n"
)
#: Which queue entries a drain has already applied, so a
#: drain that committed its result and was then interrupted before clearing
#: the queue does not apply them a second time. Committed in the *same*
#: commit as the data those entries produced, which is the whole of why it
#: works; see tools/convener_ops/submission_queue.py's own module docstring.
QUEUE_LEDGER_HEADER = (
    "# Which queued submissions a drain has already applied; "
    "see tools/convener_ops/submission_queue.py\n"
)
#: What the last window of runs actually billed, and the
#: only place in this repository where a *measured* minute exists rather
#: than a `timeout-minutes` ceiling. Committed on purpose: legible by
#: opening this repository, with no run log to scroll and no CI required.
#: The second line is the caveat that must travel with every number in the
#: file; see tools/convener_ops/actions_usage.py's own module docstring.
ACTIONS_USAGE_HEADER = (
    "# What this repository's own Actions runs really billed; "
    "see tools/convener_ops/actions_usage.py\n"
    "# A LOWER BOUND, never the bill: the free minutes belong to the "
    "organisation and are shared.\n"
)

#: Where the collector step leaves what it read from the Actions API, one
#: JSON object per line. The whole of this project's network access for
#: this feature lives in that step, in `gh`; everything downstream of this
#: file is a pure function a test drives from a fixture. A run artefact,
#: git-ignored, never edited.
ACTIONS_USAGE_INPUT: Final = "actions-usage-input.jsonl"

#: Where a budget alarm that has somewhere to go is left for the workflow
#: to post, exactly as `NOTIFY_BODY` works for the digest.
#:
#: Deliberately **not** `NOTIFY_BODY`: the daily digest already writes that
#: file in the same job, and one file for two messages would mean the alarm
#: silently overwriting the digest, or the digest silently overwriting the
#: alarm, depending on step order. Same channel, same thread, same team
#: mention -- a second address book is what is forbidden (D-07), not a
#: second message.
BUDGET_BODY: Final = "budget-body.md"


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
    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    cfg, cfg_errors = _load(root / DATA_DIR / "config.yml")
    errors += cfg_errors

    # The prefix this instance numbers its editions under,
    # read before anything is checked against it. Reported as one more
    # error rather than raised: `convener-validate` is the command a duplicate
    # runs first and its whole contract is to print what is wrong with
    # this repository and exit 1, so answering the one defect it exists to
    # name with a traceback -- and hiding every other error behind it --
    # would be the wrong shape twice over.
    editions: published.EditionPrefix | None = None
    try:
        editions = published.load_edition_prefix(root)
    except ValueError as exc:
        # Already names the file and the key it is about.
        errors.append(str(exc))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{published.INSTANCE_PATH.as_posix()}: {exc}")

    board_logins: set[str] = set()
    if isinstance(cfg, dict):
        board = cfg.get("board")
        if isinstance(board, list):
            board_logins = {
                str(m["login"])
                for m in board
                if isinstance(m, dict) and isinstance(m.get("login"), str)
            }

    if speakers is not None and editions is not None:
        errors += validate_speakers(speakers, board_logins, editions=editions)
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
    speakers_path = root / DATA_DIR / "speakers.yml"
    speakers, errors = _load(speakers_path)
    cfg, cfg_errors = _load(root / DATA_DIR / "config.yml")
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
    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    if errors:
        for error in errors:
            print(f"  - {error}")
        return 1

    rows = to_public(speakers or [])
    out_dir = root / PUBLIC_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "events-public.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} events")
    return 0


def survey_status_public_data() -> int:
    """`convener-survey-status-public-data`: rebuild
    `instance/public-data/survey-status.json` from `instance/data/speakers.yml`'s own
    `survey_enabled` field -- `public_data`'s own
    precedent (above), for a different consumer and a different field: an
    operational fact, not the programme feed `to_public` projects through
    the consent gate.

    Deliberately its own file, its own command, its own step in
    `deploy.yml` -- not folded into `public_data()`'s own
    `events-public.json` -- because the two answer different questions for
    different readers: `events-public.json` is the programme a visitor
    reads, gated on consent; `survey-status.json` is a closed list of ids
    `SurveyForm.tsx` checks membership against before it ever renders a
    question, and it must never require the consent gate to have opened
    for an event that has not even happened yet.
    """
    root = repo_root()
    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    if errors:
        for error in errors:
            print(f"  - {error}")
        return 1

    ids = to_survey_status(speakers or [])
    out_dir = root / PUBLIC_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "survey-status.json").write_text(
        json.dumps(ids, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(ids)} event(s) with the survey open")
    return 0


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
    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    config_data, config_errors = _load(root / registration_routing.CONFIG_PATH)
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


def agenda_internal() -> int:
    """`convener-agenda-internal`: rebuild
    `instance/public-data/agenda-internal.ics` from
    `instance/data/speakers.yml` and `instance/data/config.yml` --
    `public_data`'s own precedent (above), for a feed that must never reach
    either published bundle: unlike `events-public.json`, nothing in this
    build's own copy scripts ever names this file, and `.gitattributes`
    marks it binary so a checkin never rewrites its own CRLF line endings to
    this repository's own default `eol=lf`. See `agenda.py`'s module
    docstring for the feed in full, and `.github/workflows/deploy.yml`'s own
    "Commit internal agenda" step for where the committed copy comes from.
    """
    root = repo_root()
    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    cfg, cfg_errors = _load(root / DATA_DIR / "config.yml")
    if errors or cfg_errors:
        for error in errors + cfg_errors:
            print(f"  - {error}")
        return 1

    calendar = agenda.build_internal_calendar(speakers or [], cfg or {})
    out_dir = root / PUBLIC_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    # Binary, not text mode: this string already carries real CRLF line
    # endings RFC 5545 requires, and a text-mode write on this project's own
    # Windows checkouts would translate each embedded "\n" to the platform
    # line ending on top of the "\r" already there, corrupting every line to
    # "\r\r\n" (`tools/convener_ops`'s own YAML writers hit the identical trap and
    # guard against it with `newline=""`; binary mode is the same guarantee
    # by a different route).
    (out_dir / "agenda-internal.ics").write_bytes(calendar.encode("utf-8"))
    print(f"wrote {calendar.count('BEGIN:VEVENT')} entrie(s)")
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
    # field's own `options` array -- without it, a DROPDOWN/
    # MULTIPLE_CHOICE/CHECKBOXES/MULTI_SELECT answer's raw `value` is a list
    # of ids, never the text `to_lead` compares against `GENDERS`/
    # `CAREER_STAGES`, and every such answer would silently become
    # "undisclosed". This is the one place in the repository that flattens
    # a Tally field into `to_lead`'s `fields: dict[str, str]`.
    fields = {
        f.get("label", ""): field_value(f) for f in fields_list if isinstance(f, dict)
    }

    root = repo_root()
    speakers_path = root / DATA_DIR / "speakers.yml"
    speakers, errors = _load(speakers_path)
    cfg, cfg_errors = _load(root / DATA_DIR / "config.yml")
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
    reasoning.

    **Reported, not retained.** An unsent
    confirmation used to be written to a `.gitignore`d file and uploaded as
    a 14-day build artefact -- `docs/governance/traitement-donnees.md`'s
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
        speakers, _errors = _load(root / DATA_DIR / "speakers.yml")
        cfg, _errors = _load(root / DATA_DIR / "config.yml")
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
    `_write_github_output`; printed to stdout instead when `$GITHUB_OUTPUT`
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

    _write_github_output(
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
    `convener_ops.registration.to_registration` for why it is passed through
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
    _write_github_output(f"changed={','.join(changed)}\n")
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


# ------------------------------------------------------------------ #
# The post-event survey: the same intake as registration, the same
# encrypted storage, the same key destruction.
#
# Two console scripts used to live here
# -- `resolve_survey_secret` and `handle_survey_response`, the two steps of
# `.github/workflows/survey.yml` -- along with that workflow itself. A
# survey response no longer arrives as a `repository_dispatch` that starts
# a run of its own; the relay writes it to the queue branch and the daily
# drain below handles every waiting response at once. What remains here is
# the one thing the drain still needs from this module: whether an event's
# survey switch is on.
# ------------------------------------------------------------------ #


def _survey_enabled(root: Path, event_id: str) -> bool:
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
    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    if errors or not isinstance(speakers, list):
        return False
    try:
        record = find_speaker(speakers, event_id)
    except EventNotFoundError:
        return False
    return bool(record.get("survey_enabled") is True)


# ------------------------------------------------------------------ #
# The submission queue. Two steps of
# `.github/workflows/sweep-and-notify.yml`'s own daily job, never a
# workflow or a job of their own -- one of either would cost a billed run
# every day, which is what this feature exists to stop.
#
# The split between them is the GitHub Actions constraint every other
# event-key job in this repository already meets: a secret can only be
# selected by an expression in the workflow file, from a *previous* step's
# output, never by a name a running step computed. `plan_queue_drain`
# names the secrets; the workflow selects them; `drain_queue` spends them.
# Both read the same snapshot of the queue and both call the same pure
# `submission_queue.plan_drain`, so they agree by construction rather than
# by handing state to one another.
# ------------------------------------------------------------------ #

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

#: Where the workflow leaves the queue branch's contents *after* the drain,
#: the confirmations and the clearing have all finished -- one entry path
#: per line, `git ls-tree` against the branch tip.
#:
#: Read rather than inferred, and that is the whole reliability of this
#: record: what is still waiting is a fact about the branch, not something
#: to be reconstructed from what three earlier steps intended. A drain that
#: failed to push, a clearing step that could not commit, and a submission
#: the relay wrote while this very run was working are all simply *there*,
#: with no case analysis left to get wrong.
QUEUE_WAITING_ENV: Final = "CONVENER_QUEUE_WAITING_FILE"

#: The separator on a line of the deferral file. A tab, for
#: `_CONFIRM_FIELD_SEPARATOR`'s own reason; named separately because the
#: two files carry different things, and one shared constant would make a
#: change to either silently reshape the other.
_DEFERRED_FIELD_SEPARATOR: Final = "\t"

#: Where a queue alarm that has somewhere to go is left for the workflow to
#: post. A *third* body filename in one job, and deliberately neither
#: `NOTIFY_BODY` nor `BUDGET_BODY`: the digest and the budget alarm are
#: composed in the same job, and one filename for several messages means
#: whichever is written last silently replaces the rest. Same channel, same
#: thread, same team mention -- a second address book is what D-07 forbids,
#: never a second message.
QUEUE_BODY: Final = "queue-body.md"

#: What the public submission queue still held the last
#: time a drain looked at it, and since when. Committed on purpose, like
#: every other record this repository keeps about itself: legible by
#: opening the repository, with no run log to scroll and no CI required,
#: which is exactly what survives the scenario a watchdog inside GitHub
#: Actions cannot report on. See tools/convener_ops/queue_watch.py's own module
#: docstring.
QUEUE_WATCH_HEADER = (
    "# What the public submission queue still holds, and since when; "
    "see tools/convener_ops/queue_watch.py\n"
)


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
        entries, ledger, lambda event_id: _survey_enabled(root, event_id)
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
    _write_github_output("".join(lines))

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
        QUEUE_LEDGER_HEADER + _dump(submission_queue.ledger_to_data(outcome.ledger)),
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
                f"{note.name}{_DEFERRED_FIELD_SEPARATOR}"
                f"{queue_watch.flatten_reason(note.reason)}\n"
                for note in outcome.deferred
            ),
            encoding="utf-8",
            newline="",
        )

    for line in submission_queue.annotation_lines(outcome):
        print(line)
    print(submission_queue.summary(outcome))
    _write_github_output(
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


# ------------------------------------------------------------------ #
# Whether the queue is emptying at all
# ------------------------------------------------------------------ #


def _queue_thresholds(root: Path) -> queue_watch.Thresholds:
    """`instance/queue-drain.yml`, parsed or refused.

    Raises `ValueError` carrying a message already shaped for an
    `::error::` annotation. Both commands below fail on it rather than
    fall back to a built-in default, the identical call `_actions_budget`
    makes and for the identical reason: a threshold with a fallback in
    code is a constant with extra steps, and this is the one file that
    decides when an unhandled submission stops being a backlog.
    """
    path = queue_watch.config_path(root)
    named = queue_watch.CONFIG_PATH.as_posix()
    if not path.exists():
        raise ValueError(f"{named} does not exist -- nothing declares the thresholds")
    try:
        data = yaml_safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{named}: invalid YAML - {exc}") from exc
    return queue_watch.thresholds_from_data(data)


def _previous_queue_watch(root: Path) -> tuple[queue_watch.Record | None, bool]:
    """`(record, restarted)`: the committed observation this run builds on,
    and whether it had to be thrown away.

    A **missing** file is `(None, False)`: no drain has ever written one,
    which is the ordinary state of a repository before its first drain and
    not a finding. A file that will not parse is `(None, True)` -- the
    ages it carried are gone, which buys silence for anything that was
    already stuck, so it is reported as its own alarm rather than
    swallowed (`queue_watch.RESTARTED_ALARM`). Never raises: the record
    must still be rewritten either way, or a malformed file would freeze
    the record for ever and the watchdog would then report the *drain* as
    dead when the drain is fine.
    """
    path = queue_watch.watch_path(root)
    named = queue_watch.WATCH_PATH.as_posix()
    if not path.exists():
        return None, False
    try:
        data = yaml_safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"::error::{named}: invalid YAML - {exc}", file=sys.stderr)
        return None, True
    try:
        return queue_watch.record_from_data(data), False
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return None, True


def _queue_deferral_reasons() -> dict[str, str]:
    """What the drain said about each entry it could not finish, read back
    from `$CONVENER_QUEUE_DEFERRED_FILE`.

    An absent or unset file is the empty mapping, not an error: a run whose
    drain step never happened -- nothing was pending, or the step failed
    before it wrote anything -- still has to record what the queue holds.
    Every entry then simply has no reason attached, which
    `queue_watch.next_record` reads as "keep whatever an earlier drain
    said".
    """
    named = os.environ.get(QUEUE_DEFERRED_ENV, "")
    if not named:
        return {}
    path = Path(named)
    if not path.exists():
        return {}
    reasons: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry, _, reason = line.partition(_DEFERRED_FIELD_SEPARATOR)
        reasons[entry] = reason
    return reasons


def record_queue_watch() -> int:
    """`convener-record-queue-watch`: write down what the queue still holds, and
    be loud about anything that has been in it too long.

    The last of the daily job's queue steps, and the one that runs whatever
    the four before it did. It reads the queue branch's contents *after*
    the drain, the confirmations and the clearing have finished -- a fact
    about the branch, listed by the workflow, never inferred from what
    those steps intended -- pairs each remaining entry with the reason the
    drain gave for it, and carries forward the instant each was first seen
    waiting.

    Two outcomes, and they are deliberately different things:

    * `instance/data/queue-watch.yml` is rewritten every single run, whatever it
      found. Its *freshness* is the evidence the drain still runs at all,
      which `convener-check-queue-liveness` reads from
      `retention-watchdog.yml`'s own independent schedule -- a control
      hosted inside the job it watches cannot report that job going quiet.
    * `queue_alert` on `$GITHUB_OUTPUT`, and a body file to post, when an
      entry has waited past `instance/queue-drain.yml`'s threshold. That half
      *can* live here, because an entry can only be known to be stuck by
      something that read the queue, and this is the only place that has
      both the queue and the board's channel (D-07).

    Returns 0 even when the alarm fires: the workflow's own last step is
    what turns the job red, the same split the budget alarm uses so
    that an unconfigured channel can never turn a real finding into
    silence.
    """
    root = repo_root()
    try:
        thresholds = _queue_thresholds(root)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    listing = os.environ.get(QUEUE_WAITING_ENV, "")
    if not listing:
        print(f"::error::{QUEUE_WAITING_ENV} is not set", file=sys.stderr)
        return 1
    path = Path(listing)
    if not path.exists():
        # Never read as "the queue is empty". A listing that was not taken
        # is not the answer "nothing waiting", and reading it as one is how
        # a control reports that everything is fine while it is not (the
        # same lesson retention.yml carries one file over).
        print(
            f"::error::{listing} does not exist -- the queue was never "
            "listed, which is not the same as the queue being empty",
            file=sys.stderr,
        )
        return 1
    names = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    reasons = _queue_deferral_reasons()
    still_waiting = {name: reasons.get(name, "") for name in names if name}

    previous, restarted = _previous_queue_watch(root)
    now = datetime.now(UTC)
    record = queue_watch.next_record(previous, still_waiting, now)
    watch_file = queue_watch.watch_path(root)
    watch_file.parent.mkdir(parents=True, exist_ok=True)
    watch_file.write_text(
        QUEUE_WATCH_HEADER + _dump(queue_watch.record_to_data(record)),
        encoding="utf-8",
        newline="",
    )

    stuck = queue_watch.overdue(record, now, thresholds.alarm_after_hours)
    fired = queue_watch.alarms(stuck, now, restarted=restarted)
    print(queue_watch.summary(record, stuck))
    if not fired:
        _write_github_output("queue_alert=false\n")
        return 0

    for line in queue_watch.annotation_lines(fired, stuck):
        print(line)
    addressed = dispatch(queue_watch.message(fired, stuck, now), os.environ)
    if addressed is not None:
        (root / QUEUE_BODY).write_text(addressed.body, encoding="utf-8", newline="")
        print(f"addressed to thread {addressed.channel.thread}; left in {QUEUE_BODY}")
    else:
        print(
            "no notification channel is configured -- this alarm reaches "
            f"nowhere but this run's own red status and "
            f"{queue_watch.WATCH_PATH.as_posix()}"
        )
    _write_github_output("queue_alert=true\n")
    return 0


def check_queue_liveness() -> int:
    """`convener-check-queue-liveness`: has the drain itself stopped running?

    The half of this control that cannot live in the daily job. An alarm
    hosted inside the job it watches reports nothing when that job is the
    thing that went quiet -- and a stopped drain is the most likely and the
    most serious of the four ways a submission can sit in the queue for
    ever. So `retention-watchdog.yml`, a second, independent schedule that
    already exists and already asks this exact question about
    `retention.yml` and `instance/data/actions-usage.yml`, asks it about
    `instance/data/queue-watch.yml` too, in the same job, at no extra billed job.

    Reads the record's freshness and nothing else. It deliberately does
    *not* re-report the entries that are past the threshold: an entry can
    only be known to be stuck by a drain that ran, so the daily job has
    already said so with the board's channel in hand, and a second red run
    saying the same thing on the same day is how an operator learns to
    ignore both.

    A missing file is an error, not a shrug -- the same call
    `check_retention_liveness` and `check_actions_usage_liveness` make, for
    the same reason: it means the daily job has never once landed this
    record, which is the silence this command exists to report.

    See `.github/workflows/retention-watchdog.yml`'s own header comment for
    what a watchdog living inside the scheduler it watches can and cannot
    catch. The answer is the same here, and so is the residue: the
    committed file itself, readable by a person with no CI running at all.
    """
    root = repo_root()
    try:
        thresholds = _queue_thresholds(root)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    path = queue_watch.watch_path(root)
    named = queue_watch.WATCH_PATH.as_posix()
    if not path.exists():
        print(
            f"::error::{named} does not exist -- the daily job has never "
            "recorded what the public submission queue holds (or the file "
            "was removed); see tools/convener_ops/queue_watch.py",
            file=sys.stderr,
        )
        return 1
    try:
        data = yaml_safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"::error::{named}: invalid YAML - {exc}", file=sys.stderr)
        return 1
    try:
        record = queue_watch.record_from_data(data)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    today = paris_today(datetime.now(UTC))
    observed_on = paris_today(record.observed_at)
    elapsed = queue_watch.days_since(observed_on, today)
    if queue_watch.is_stale(elapsed, thresholds.max_silent_days):
        print(
            f"::error::{named} last moved on {observed_on.isoformat()}, "
            f"{elapsed} day(s) ago -- the public submission queue is no "
            "longer being drained, so anything waiting in it is waiting "
            "indefinitely and nothing else would say so",
            file=sys.stderr,
        )
        return 1
    print(
        f"{named} last moved on {observed_on.isoformat()}, {elapsed} day(s) "
        f"ago, with {len(record.waiting)} submission(s) waiting -- healthy"
    )
    return 0


#: Where `check_registration_routing` leaves the body it
#: composed, for the workflow step that posts it. Neither `NOTIFY_BODY`,
#: nor `BUDGET_BODY`, nor `QUEUE_BODY`: four messages are now composed in
#: the one daily job, and one filename for several of them means whichever
#: is written last silently replaces the rest. Same channel, same thread,
#: same team mention -- a second address book is what D-07 forbids, never a
#: second message.
ROUTING_BODY: Final = "routing-body.md"


def _published_routing(root: Path) -> tuple[dict[str, str], str | None]:
    """`(cutoffs, None)` for a projection the relay can read, or
    `({}, why)` for one it cannot.

    Never raises, and never falls back to a default: an empty mapping here
    always travels with the reason beside it, so the caller cannot mistake
    "the file says no event is queueable" for "there is no file". That
    distinction is the whole of `routing_watch.UNPUBLISHED`.

    A **missing** file is a finding rather than the ordinary pre-first-run
    state its neighbours treat it as. `instance/data/queue-watch.yml` absent means
    no drain has run yet; this file absent means the relay's every read
    404s, which is exactly the silent fallback to the immediate lane this
    command exists to report -- and it stays true on the morning an
    announcement goes out.
    """
    named = registration_routing.ROUTING_PATH.as_posix()
    routing_file = root / registration_routing.ROUTING_PATH
    if not routing_file.exists():
        return {}, (
            f"{named} does not exist in this repository, so every read the "
            "relay makes of it is a 404."
        )
    try:
        data = json.loads(routing_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"{named} could not be read as JSON ({exc})."
    try:
        return routing_watch.published_from_data(data), None
    except ValueError as exc:
        return {}, f"{exc}, so the relay refuses it and reads no cutoff at all."


def check_registration_routing() -> int:
    """`convener-check-registration-routing`: can a registration still reach the
    queue at all?

    The last of the queue's controls, and the one that guards the *saving*
    rather than a submission. Every failure the relay meets while reading
    `instance/public-data/registration-routing.json` resolves to the immediate lane,
    deliberately and correctly -- and therefore invisibly. If that file goes
    missing or falls behind the data, every registration bills a run again,
    the queue is simply empty, and an empty queue looks like a quiet day.

    This recomputes the projection from `instance/data/speakers.yml` and
    `instance/registration-lanes.yml` with the same function `deploy.yml`
    runs, and compares it with the committed file over the events a
    registration arriving now could still be queued for. See
    `tools/convener_ops/routing_watch.py` for why that comparison rather than
    the file's age, and for why a file naming only past events is a quiet
    season instead of an alarm.

    Returns 0 even when a finding fires, the same split the budget alarm
    and the queue alarm use: the workflow's own last step is
    what turns the job red, so an unconfigured channel can never turn a
    real finding into silence. Returns 1 only for the inputs *this*
    repository owns and cannot read -- a missing or malformed
    `instance/data/speakers.yml` or `instance/registration-lanes.yml` -- which is a
    broken repository rather than a stale deployment.
    """
    root = repo_root()
    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    config_data, config_errors = _load(root / registration_routing.CONFIG_PATH)
    if errors or config_errors:
        for error in errors + config_errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1
    try:
        threshold = registration_routing.threshold_from_data(config_data)
        expected = registration_routing.to_routing_data(speakers or [], threshold)
        published, unreadable = _published_routing(root)
        now = datetime.now(UTC)
        cutoffs = expected["queue_until"]
        live = routing_watch.live_events(cutoffs, published, now)
        diverged = routing_watch.divergences(cutoffs, published, now)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    fired = routing_watch.findings(diverged, unreadable)
    print(routing_watch.summary(live, diverged))
    if not fired:
        _write_github_output("routing_alert=false\n")
        return 0

    for line in routing_watch.annotation_lines(fired, diverged):
        print(line)
    addressed = dispatch(routing_watch.message(fired, diverged), os.environ)
    if addressed is not None:
        (root / ROUTING_BODY).write_text(addressed.body, encoding="utf-8", newline="")
        print(f"addressed to thread {addressed.channel.thread}; left in {ROUTING_BODY}")
    else:
        print(
            "no notification channel is configured -- this finding reaches "
            "nowhere but this run's own red status"
        )
    _write_github_output("routing_alert=true\n")
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
            "destroyed nothing -- see docs/reference/operations.md, "
            "'Retention and early erasure'",
            file=sys.stderr,
        )
        return 1

    root = repo_root()
    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
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


def record_retention_run() -> int:
    """`convener-record-retention-run`: record that today's `retention.yml` run
    happened at all.

    Writes `instance/data/retention-last-run.yml` with today's Paris date
    (`governance.paris_today`), unconditionally. `retention.yml`'s own
    "Record that the retention workflow ran today" step calls this last,
    with `if: always()`, deliberately independent of whether the sweep
    above it actually found anything, deleted a secret, or even ran to
    completion -- this function answers only "did the schedule fire and
    the job start", never "did it finish correctly". See
    `tools/convener_ops/retention_liveness.py`'s own module docstring for why
    conflating the two into one signal would be worse than answering
    neither: a broken token failing loudly every day is already visible
    on the Actions tab and in GitHub's own failure e-mail; recording that
    as "healthy" here would bury it behind a checkmark instead.

    Always succeeds -- there is no failure mode of its own to report; a
    write failure (a read-only filesystem, a full disk) surfaces as an
    unhandled exception, which is correct: this function does not attempt
    to reason about a failure mode it cannot name.
    """
    root = repo_root()
    today = paris_today(datetime.now(UTC))
    path = retention_liveness.last_run_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        RETENTION_LAST_RUN_HEADER + _dump(retention_liveness.record_to_data(today)),
        encoding="utf-8",
        newline="",
    )
    print(f"recorded a retention run for {today.isoformat()}")
    return 0


def check_retention_liveness() -> int:
    """`convener-check-retention-liveness`: `retention-watchdog.yml`'s own
    command.

    Reads `instance/data/retention-last-run.yml` (written by `record_retention_run`
    above) and fails, loudly, once it has gone more than
    `retention_liveness.MAX_SILENT_DAYS` days without moving. A missing
    file is not the ordinary D-13 "an integration that may not exist yet"
    state some other absent-secret checks in this module treat kindly --
    it means retention.yml's own "Record that the retention workflow ran
    today" step has never once landed a commit in this repository, which
    is exactly the silence this command exists to report, so it is
    reported the same way a stale date is: an error, not a shrug. A
    malformed file (hand-edited, a partial write) is reported and refused
    the same way `_load_destruction_registry` refuses one, rather than
    guessed at.

    Prints `::error::` on the failing path, the format GitHub Actions
    renders as an annotation on the run -- see
    `.github/workflows/retention-watchdog.yml`'s own header comment for
    what a red run here does and does not mean.
    """
    root = repo_root()
    path = retention_liveness.last_run_path(root)
    if not path.exists():
        print(
            "::error::instance/data/retention-last-run.yml does not exist -- "
            "retention.yml has never recorded a run in this repository "
            "(or the file was removed) -- see this command's own "
            "docstring and retention-watchdog.yml's own header comment",
            file=sys.stderr,
        )
        return 1
    try:
        data = yaml_safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(
            f"::error::instance/data/retention-last-run.yml: invalid YAML - {exc}",
            file=sys.stderr,
        )
        return 1
    try:
        last_run = retention_liveness.last_run_from_data(data)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    today = paris_today(datetime.now(UTC))
    elapsed = retention_liveness.days_since(last_run, today)
    if retention_liveness.is_stale(elapsed):
        print(
            f"::error::retention.yml last recorded a run on "
            f"{last_run.isoformat()}, {elapsed} day(s) ago -- see "
            "retention-watchdog.yml's own header comment for what that "
            "does and does not mean",
            file=sys.stderr,
        )
        return 1
    print(
        f"retention.yml last recorded a run on {last_run.isoformat()}, "
        f"{elapsed} day(s) ago -- healthy"
    )
    return 0


# ------------------------------------------------------------------ #
# What the runs really cost
# ------------------------------------------------------------------ #


def _actions_budget(root: Path) -> actions_usage.Budget:
    """`instance/actions-budget.yml`, parsed or refused.

    Raises `ValueError` carrying a message already shaped for an
    `::error::` annotation. All three commands below fail on it rather
    than fall back to a built-in default: a threshold with a fallback in
    code is a constant with extra steps, and this is the one file that
    decides when the alarm goes off, so a value it cannot read must stop
    the check rather than be quietly substituted.
    """
    path = actions_usage.budget_path(root)
    named = actions_usage.BUDGET_PATH.as_posix()
    if not path.exists():
        raise ValueError(f"{named} does not exist -- nothing declares the thresholds")
    try:
        data = yaml_safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{named}: invalid YAML - {exc}") from exc
    return actions_usage.budget_from_data(data)


def actions_usage_window() -> int:
    """`convener-actions-usage-window`: the first day the collector should ask
    the Actions API for, and the cap on how many runs it may cost.

    Writes `since=` and `max_runs=` to `$GITHUB_OUTPUT` for the `gh` step
    that follows. The window lives here, derived from the same
    configuration the arithmetic divides by, so the days the collector
    fetches and the days the rate is computed over can never be two
    different numbers -- the class of mistake that turns a projection into
    a wrong answer delivered confidently.

    `governance.paris_today`, never an implicit today.
    """
    root = repo_root()
    try:
        budget = _actions_budget(root)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    today = paris_today(datetime.now(UTC))
    since = actions_usage.window_start(today, budget)
    _write_github_output(f"since={since.isoformat()}\nmax_runs={budget.max_runs}\n")
    print(
        f"window: {since.isoformat()} to {today.isoformat()} "
        f"({budget.window_days} days), at most {budget.max_runs} runs"
    )
    return 0


def record_actions_usage() -> int:
    """`convener-record-actions-usage`: what the last window really billed, and
    the alarm when the rate says the budget will not hold.

    Reads what the collector step left behind -- one JSON object per line,
    each pairing a run with its `/timing` answer -- and writes
    `instance/data/actions-usage.yml`: a committed file, so the measurement is
    legible by opening this repository rather than by scrolling a job log
    nobody opens. One line goes to the log, not thirty.

    **Always exits 0 when it could measure at all**, and the same
    reasoning as `alert_secret_workflow_run` above: whether to fail the
    job is not decided in here. This writes `budget_alert=true`/`false` to
    `$GITHUB_OUTPUT` and the workflow's own last step fails the job on
    `true`, unconditionally, whether or not a channel was configured for
    the notification -- so D-25's loud failure is visible by reading the
    YAML that makes it happen, and this command can still be exercised and
    asserted against with no workflow runner at all.

    It exits 1 for the two things that are *not* an observation: unreadable
    thresholds, and a collector that left nothing behind. Reporting
    "0 minutes" for a step that never ran would be the exact shape of
    silence this whole feature exists to prevent.
    """
    root = repo_root()
    try:
        budget = _actions_budget(root)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    source = root / os.environ.get("CONVENER_ACTIONS_USAGE_INPUT", ACTIONS_USAGE_INPUT)
    if not source.exists():
        print(
            f"::error::{source.name} does not exist -- the collector step left "
            "nothing to measure, so this run observed nothing at all (an "
            "empty file is a real answer; a missing one is not)",
            file=sys.stderr,
        )
        return 1

    payloads: list[Any] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payloads.append(json.loads(stripped))
        except json.JSONDecodeError:
            # A line that cannot be parsed is a run this cannot cost, not a
            # run that cost nothing -- `summarise` counts `None` as exactly
            # that, and `alarms` is loud about it.
            payloads.append(None)

    truncated = os.environ.get("CONVENER_ACTIONS_USAGE_TRUNCATED", "").strip() == "true"
    today = paris_today(datetime.now(UTC))
    usage = actions_usage.summarise(
        payloads, observed_on=today, budget=budget, truncated=truncated
    )

    path = actions_usage.usage_path(root)
    previous: list[dict[str, Any]] = []
    if path.exists():
        try:
            previous = actions_usage.history_from_data(
                yaml_safe_load(path.read_text(encoding="utf-8"))
            )
        except yaml.YAMLError:
            print(
                "::warning::instance/data/actions-usage.yml is not readable YAML -- "
                "today's measurement replaces it and the trend restarts here"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        ACTIONS_USAGE_HEADER + _dump(actions_usage.record_to_data(usage, previous)),
        encoding="utf-8",
        newline="",
    )
    print(actions_usage.summary_line(usage))

    fired = actions_usage.alarms(usage, budget)
    if not fired:
        _write_github_output("budget_alert=false\n")
        return 0

    for alarm in fired:
        print(f"::error::[{alarm.kind}] {alarm.text}", file=sys.stderr)
    addressed = dispatch(actions_usage.message(usage, fired), os.environ)
    if addressed is not None:
        (root / BUDGET_BODY).write_text(addressed.body, encoding="utf-8", newline="")
        print(f"addressed to thread {addressed.channel.thread}; left in {BUDGET_BODY}")
    else:
        print(
            "no notification channel is configured -- this alarm reaches "
            "nowhere but this run's own red status and instance/data/actions-usage.yml"
        )
    _write_github_output("budget_alert=true\n")
    return 0


def check_actions_usage_liveness() -> int:
    """`convener-check-actions-usage-liveness`: has the budget alarm itself
    stopped running?

    An alarm hosted inside the daily job it watches over cannot report its
    own silence, and an exhausted budget is precisely what stops that job.
    So `retention-watchdog.yml` -- a second, independent schedule that
    already exists and already asks this exact question about
    `retention.yml` -- asks it about `instance/data/actions-usage.yml` too, in the
    same job, at no extra billed job. See that workflow's own header
    comment for what a watchdog living inside the scheduler it watches can
    and cannot catch; the answer is the same here, and the residue is the
    same: the committed file itself, readable by a person with no CI
    running at all.

    A missing file is an error, not a shrug -- the same call
    `check_retention_liveness` makes above, for the same reason: it means
    the daily job has never once landed this record, which is the silence
    this command exists to report.
    """
    root = repo_root()
    try:
        budget = _actions_budget(root)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    path = actions_usage.usage_path(root)
    named = actions_usage.USAGE_PATH.as_posix()
    if not path.exists():
        print(
            f"::error::{named} does not exist -- the daily job has never "
            "recorded what this repository's runs cost (or the file was "
            "removed); see tools/convener_ops/actions_usage.py",
            file=sys.stderr,
        )
        return 1
    try:
        data = yaml_safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"::error::{named}: invalid YAML - {exc}", file=sys.stderr)
        return 1
    try:
        observed_on = actions_usage.observed_on_from_data(data)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    today = paris_today(datetime.now(UTC))
    elapsed = actions_usage.days_since(observed_on, today)
    if actions_usage.is_stale(elapsed, budget.max_silent_days):
        print(
            f"::error::{named} last moved on {observed_on.isoformat()}, "
            f"{elapsed} day(s) ago -- the Actions budget is no longer being "
            "watched, so nothing would report the budget running out",
            file=sys.stderr,
        )
        return 1
    print(
        f"{named} last moved on {observed_on.isoformat()}, "
        f"{elapsed} day(s) ago -- healthy"
    )
    return 0


def record_destructions() -> int:
    """`convener-record-destructions`: write `instance/data/event-key-destructions.yml`
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
    `docs/reference/operations.md`'s "Event registration keys" section,
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


def _load_registrations(
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
    memory, into `Registration` objects via `_load_registrations`; an
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
    identical `_conference_ids_from_env` resolution -- match-attendance.yml
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

    registrations, unreadable_registrations = _load_registrations(
        current.entries, private_pem
    )

    speakers, _errors = _load(root / DATA_DIR / "speakers.yml")
    cfg, _errors = _load(root / DATA_DIR / "config.yml")
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
        _conference_ids_from_env(event_id),
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


def _conference_ids_from_env(event_id: str) -> dict[str, str]:
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


def _env_flag_is_true(name: str) -> bool:
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


# ------------------------------------------------------------------ #
# Inviting the post-event survey: sent afterwards, only to people
# recognised as present. Two commands, the
# same split registration.yml already draws between storing and sending:
# `invite_survey` composes and sends
# -- once, never retried, so a rejected push downstream can never turn
# into a second copy of the same message -- and `record_survey_invitation`
# writes the one, person-free fact that stops a re-dispatch from doing it
# again, inside a commit-and-push retry loop exactly like every other
# writer in this file uses. See `survey_invite.py`'s own module docstring
# for the reasoning this split rests on: there is no
# identifier here the way `certificate.py`'s own register gives one, so
# the whole bound is "this event was invited", never "these people were".
# ------------------------------------------------------------------ #


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
    2. **the survey switch is on** (`_survey_enabled`): an
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
    if not _survey_enabled(root, event_id):
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

    resend_all = _env_flag_is_true("RESEND_ALL")
    if event_id in registry and not resend_all:
        print(
            f"event {event_id} was already invited on "
            f"{registry[event_id].isoformat()} -- no invitations sent this "
            "run (tick resend_all for a deliberate resend)"
        )
        _write_github_output("record=false\n")
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

    registrations, unreadable_registrations = _load_registrations(
        current.entries, private_pem
    )

    speakers, _errors = _load(root / DATA_DIR / "speakers.yml")
    cfg, _errors = _load(root / DATA_DIR / "config.yml")
    speaker_list = speakers if isinstance(speakers, list) else []
    config_map = cfg if isinstance(cfg, dict) else None

    platform = platform_from_env(
        os.environ,
        speaker_list,
        config_map,
        _conference_ids_from_env(event_id),
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
    _write_github_output(f"record={'true' if sent_count else 'false'}\n")
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
        SURVEY_INVITATIONS_HEADER + _dump(survey_invite.registry_to_data(registry)),
        encoding="utf-8",
        newline="",
    )
    print(f"recorded a survey invitation for event {event_id}")
    return 0


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
    (`_conference_ids_from_env`, shared with `reissue_certificate`), the
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
    message names that parse failure -- surfaced from `_load`, never
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

    registrations, unreadable_registrations = _load_registrations(
        current.entries, private_pem
    )

    speakers, speaker_errors = _load(root / DATA_DIR / "speakers.yml")
    cfg, _errors = _load(root / DATA_DIR / "config.yml")
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
        _conference_ids_from_env(event_id),
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
            CERTIFICATES_HEADER + _dump(register_to_data(tuple(entries))),
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
    _write_github_output(f"issued_ids={','.join(freshly_issued_ids)}\n")

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
    `_conference_ids_from_env` resolution --
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

    registrations, _unreadable_registrations = _load_registrations(
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

    speakers, speaker_errors = _load(root / DATA_DIR / "speakers.yml")
    cfg, _errors = _load(root / DATA_DIR / "config.yml")
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
        _conference_ids_from_env(event_id),
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
        CERTIFICATES_HEADER + _dump(register_to_data(updated)),
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

    registrations, unreadable_registrations = _load_registrations(
        current.entries, private_pem
    )

    speakers, speaker_errors = _load(root / DATA_DIR / "speakers.yml")
    cfg, _errors = _load(root / DATA_DIR / "config.yml")
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
        _conference_ids_from_env(event_id),
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
    resend_all = _env_flag_is_true("RESEND_ALL")
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

    registrations, _unreadable_registrations = _load_registrations(
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

    speakers, speaker_errors = _load(root / DATA_DIR / "speakers.yml")
    cfg, _errors = _load(root / DATA_DIR / "config.yml")
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
        _conference_ids_from_env(event_id),
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
    `tools/tests/test_cli.py::test_delete_recording_has_exactly_two_call_sites_both_in_cli`).
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
    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    cfg, cfg_errors = _load(root / DATA_DIR / "config.yml")
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
    `tools/tests/test_cli.py::test_delete_recording_has_exactly_two_call_sites_both_in_cli`).

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
    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    cfg, cfg_errors = _load(root / DATA_DIR / "config.yml")
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
#: configured channel. `.github/workflows/sweep-and-notify.yml` posts what it finds here
#: and does nothing at all when it finds nothing -- so there is no
#: "notifications on/off" switch anywhere in the chain, only a message that
#: either has an address or was never composed with one. Git-ignored: it is a
#: run artefact, never a file anybody edits.
NOTIFY_BODY: Final = "notify-body.md"

#: The parent of HEAD, as a fixed `git show` argument. The fallback, used when
#: the run does not know where the branch actually moved from.
PREVIOUS_SPEAKERS: Final = "HEAD~1:instance/data/speakers.yml"

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
    was as `github.event.before`, and `.github/workflows/sweep-and-notify.yml`
    passes it
    through as `BEFORE`; that is what this prefers.

    Falls back to `HEAD~1` when `BEFORE` is absent, malformed, or the all-zero
    name GitHub sends for the first push to a branch (`NO_PARENT`) -- there is
    no earlier state to read in that last case, and the caller turns a `git
    show` failure into "nothing to compare, so nothing to say".
    """
    before = env.get("BEFORE", "").strip()
    if _OBJECT_NAME.fullmatch(before) and before.strip("0"):
        return f"{before}:instance/data/speakers.yml"
    return PREVIOUS_SPEAKERS


def _git_show(root: Path, revision: str) -> tuple[str, str]:
    """`instance/data/speakers.yml` as of `revision`, or an explanation.

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
    """`convener-notify-immediate`: the three events worth interrupting for.

    Compares the working tree's speaker file against the state the branch was
    in before the push (`previous_revision`), so a push carrying several
    commits reports the events of all of them rather than only the last. With
    no earlier revision to read there is no change to describe, so this says
    nothing rather than treating the whole file as new -- which on a fresh
    clone would announce every lead in it at once.
    """
    root = repo_root()
    after, errors = _load(root / DATA_DIR / "speakers.yml")
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
    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    cfg, cfg_errors = _load(root / DATA_DIR / "config.yml")
    if errors or cfg_errors:
        for error in errors + cfg_errors:
            print(f"  - {error}")
        return 1

    return _notify(daily_digest(speakers or [], cfg or {}, datetime.now(UTC)))


def alert_secret_workflow_run() -> int:
    """`convener-alert-secret-workflow-run`: composes the off-`main` alert for one
    `workflow_run` event and addresses it, if a channel is configured.

    Reads the triggering run's own facts from the environment --
    `.github/workflows/secret-workflow-monitor.yml`'s own "Evaluate" step
    sets them from `github.event.workflow_run.*` before calling this.

    **Always exits 0.** Unlike `_notify`, whether to fail the job is not
    decided in here: this command writes `off_main=true`/`off_main=false` to
    `$GITHUB_OUTPUT`, and the workflow's own last step -- not this one --
    fails the job when it reads `true`, unconditionally, whether or not a
    channel was configured for the notification below. Keeping that one
    decision in the workflow file rather than in an exit code means D-25's
    loud failure is visible by reading the fifteen lines of YAML that make
    it happen, not by tracing a library call's return value back through a
    subprocess boundary -- and it means this command itself can be
    exercised and asserted against without a workflow runner at all.
    """
    message = alert_message(
        workflow_name=os.environ.get("WORKFLOW_NAME", ""),
        head_branch=os.environ.get("HEAD_BRANCH") or None,
        run_event=os.environ.get("RUN_EVENT", ""),
        run_url=os.environ.get("RUN_URL", ""),
        actor=os.environ.get("RUN_ACTOR", ""),
    )
    if message is None:
        name = os.environ.get("WORKFLOW_NAME", "(unknown)")
        print(f"{name} ran on main -- nothing to report")
        _write_github_output("off_main=false\n")
        return 0

    print(message)
    addressed = dispatch(message, os.environ)
    if addressed is not None:
        path = repo_root() / NOTIFY_BODY
        path.write_text(addressed.body, encoding="utf-8", newline="")
        print("")
        print(f"addressed to thread {addressed.channel.thread}; left in {NOTIFY_BODY}")
    else:
        print("")
        print(
            "no notification channel is configured -- this alert reaches "
            "nowhere but this run's own log"
        )
    _write_github_output("off_main=true\n")
    return 0


def _git_log(root: Path) -> tuple[str, str]:
    """The whole history in `register.LOG_FORMAT`, oldest commit first.

    One of the two places this package shells out, and it is why this one
    lives in `cli`: the rest of `convener_ops` stays a pure library that a test
    can drive without a checkout. (The other is
    `derivation_guard._git`, which reads a repository's whole *history*
    rather than a working tree -- there is no pure function to hand that
    to.) Fixed argv, no shell, no interpolated value -- there is nothing
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
    is meaningful because the rendering reads no clock, no `instance/data/*.yml` and no
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


def render_visual_fixtures() -> int:
    """`convener-render-visual-fixtures OUTPUT_DIR`: writes the pinned
    render step its input -- one self-contained HTML page per named format
    (`formats.FORMATS`), a `manifest.json` naming each one's format name and
    pixel size, and a copy of the repository's self-hosted `fonts/` beside
    them so a relative `url('fonts/...')` resolves once served.

    The one disk-writing seam between the two halves of that pipeline.
    `visual.render_announcement` and `formats.FORMATS` stay pure -- neither
    touches disk or knows this project builds a Node/Puppeteer step on top
    of what they return -- and the pinned renderer (`visuals/`, a separate
    npm package so only its own CI job ever pays for the Chrome-for-Testing
    download that isolation buys) never re-derives a page's own markup a second
    time in JavaScript: it reads exactly the bytes this command wrote.

    `manifest.json` is the shared *fixture* the two languages agree on
    (D-14's own shape, applied to a boundary this project has not crossed
    before): the pinned renderer reads a format's name and pixel size from
    it rather than a second, hand-typed `{width: 1200, height: 1200}` in
    JavaScript that `formats.py` could silently drift away from.

    Always renders `visual.FIXTURE_ANNOUNCEMENT` -- the one fixed, versioned
    identity the committed reference images are measured against
    (see that constant's own docstring for why it is Ada Lovelace and no
    photograph, never a real, living speaker's name or face). Nothing about
    this command reads `instance/data/speakers.yml`, the clock, or the network: the
    same input always produces the same three pages, which is the entire
    point of a pinned regression fixture.

    **And it renders as the example instance, never as this one.**
    `render_announcement` takes a `root` to read the charter and
    the declaration from; this command used to hand it `repo_root()`, so
    the three committed reference images were a frozen photograph of
    whichever instance ran the repository -- its palette, its ribbon, its
    strapline, its wordmark -- sitting in `visuals/`, which is the
    product's. Two things follow from handing it `instances/example/`
    instead, and both are the point rather than a side effect:

    - **the images carry no real instance's identity.** They pin what
      `visual.py` *renders* -- the geometry, the glyph shapes, the QR
      modules, the ribbon's stroke against its ground -- and an invented
      charter pins all of that exactly as well as a real one. The
      designer of this instance's charter declined to have it ship with
      the product; this is the byte-level half of honouring that.
    - **the check stops failing for every duplicate.** `visuals.yml` fires
      on the charter's own path, so before this change a duplicate that
      chose its own colours rendered them against images of somebody
      else's and went red on its first push, with nothing wrong.

    The fonts still come from `root / "fonts"`: they are the product's,
    self-hosted and served by it (D-17), and `instances/example/` holds no
    copy of them precisely because a face is not an identity here.
    """
    if len(sys.argv) != 2:
        print("usage: convener-render-visual-fixtures OUTPUT_DIR", file=sys.stderr)
        return 1
    root = repo_root()
    # The charter and the declaration the fixture is rendered from -- the
    # example instance's, never this repository's own. See the docstring.
    charter = root / published.EXAMPLE_INSTANCE_ROOT
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, Any]] = []
    for fmt in formats.FORMATS:
        html = visual.render_announcement(
            visual.FIXTURE_ANNOUNCEMENT,
            width=fmt.width,
            height=fmt.height,
            root=charter,
        )
        filename = f"{fmt.name}.html"
        (out / filename).write_text(html, encoding="utf-8")
        manifest.append(
            {
                "name": fmt.name,
                "width": fmt.width,
                "height": fmt.height,
                "file": filename,
            }
        )

    fonts_dest = out / "fonts"
    if fonts_dest.exists():
        shutil.rmtree(fonts_dest)
    shutil.copytree(root / "fonts", fonts_dest)

    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(manifest)} visual fixture(s) to {out}")
    return 0


def _scheduled_announcements(rows: list[dict[str, Any]]) -> list[visual.Announcement]:
    """`public_data.to_public`'s own output, turned into the
    `visual.Announcement`s the production render needs -- never a
    second, looser read of the raw speaker record.

    Filtered to `status == "scheduled"`: an edition still being announced,
    the one state "a date locked" (the trigger's own language) describes.
    Routing through `to_public` first is what withholds a portrait under
    the consent gate with no second check written here -- see `visual.py`'s own module
    docstring, "Portrait", for why passing the gated projection through is
    "enough on its own".

    `photo_url` never becomes `portrait_data_uri` here, even on the rare
    row where `to_public` leaves it non-empty. Today that is close to
    unreachable for a *scheduled* row: `public_data.
    personal_disclosure_withheld`'s own docstring records that its gate is
    written to open only once a talk is archived and published, which is
    after the point an announcement is useful -- so a real, ordinarily
    written record never reaches this branch. But nothing stops a
    hand-edited file from setting `publication.outcome: published` on a
    still-`scheduled` row, and `docs/reference/schema.md` calls
    `photo_url` "a link, not an upload": turning it into something
    `render_announcement` can inline would mean this command reaching onto
    the network for a URL a data file names, which it does not do. A row
    that does carry a consented one prints a visible notice instead of
    silently doing nothing about it (D-25) -- the alternative
    is a gap that looks identical to the common, legitimate case of
    "nothing to embed".
    """
    announcements: list[visual.Announcement] = []
    for row in rows:
        if row.get("status") != "scheduled":
            continue
        event_id = str(row.get("id", "")).lower()
        raw_date = str(row.get("date") or "")
        try:
            talk_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValueError(
                f"{row.get('id')!r}: scheduled but its date {raw_date!r} is "
                "not a valid YYYY-MM-DD -- instance/data/speakers.yml disagrees "
                "with its own validator"
            ) from exc
        if row.get("photo_url"):
            print(
                f"::notice::{event_id} has a consented photo_url but the "
                "production renderer does not embed a portrait yet -- "
                "rendering the no-portrait variant "
                "(see _scheduled_announcements's own docstring)",
                file=sys.stderr,
            )
        announcements.append(
            visual.Announcement(
                title=str(row.get("title", "")),
                talk_date=talk_date,
                speaker_name=str(row.get("speaker_name", "")),
                speaker_affiliation=str(row.get("speaker_affiliation", "")),
                event_id=event_id,
                portrait_data_uri=None,
            )
        )
    return announcements


def render_visuals() -> int:
    """`convener-render-visuals OUTPUT_DIR`: the disk-writing seam for
    *production* visuals -- real, scheduled editions read from
    `instance/data/speakers.yml`, through the same public gate every other public
    artefact in this project already goes through (`public_data.
    to_public`), never a second, looser read of the raw record.

    The opposite number of `render_visual_fixtures` above: that command
    always renders the one fixed, fictional identity a regression check
    needs and never touches `instance/data/speakers.yml` at all; this one renders
    *only* real, scheduled editions and touches nothing else. Zero
    scheduled editions is a normal, expected state (D-13) -- printed
    plainly, exit 0, an empty `manifest.json` -- not a failure; a
    malformed date on a record that claims to be scheduled is not, and
    fails loudly instead (D-25): `instance/data/speakers.yml` disagreeing with its
    own validator is a data defect this command must never render around
    quietly.

    Same discipline for `formats.qr_module_size_mm`: computed and checked
    here, against every real scheduled edition's own `event_id`, before
    anything is written -- `formats.py`'s own docstring proves the
    function correct but never calls it against real data, and
    `validate.validate_speakers` bounds `edition_code`'s length but only
    in the separate `convener-validate` command, which nothing requires this
    one to run first. An edition whose id is long enough to bump
    `registration_code_modules` past the point where a printed A4 poster's
    QR module drops below `formats.SCANNABLE_QR_MODULE_MM` fails loudly
    (D-25) instead of shipping a poster nobody can scan.

    This is also the "manual command" the trigger requires, independently
    of any workflow: `uv run --project tools convener-render-visuals
    OUTPUT_DIR` renders the current, real state of `instance/data/speakers.yml` on
    demand, from a plain checkout, no CI needed.

    Only touches the target directory once a valid state has actually been
    computed (mirrors `publish-vitrine.yml`'s own "a build that cannot
    replace what it would remove must never be allowed to begin removing
    it"), and then regenerates it whole rather than accumulating into it
    (the same discipline `render_visual_fixtures`'s own `fonts/` handling
    and `register()` already apply): an edition no longer scheduled must
    not leave a stale page sitting next to a manifest that no longer lists
    it.
    """
    if len(sys.argv) != 2:
        print("usage: convener-render-visuals OUTPUT_DIR", file=sys.stderr)
        return 1
    root = repo_root()
    out = Path(sys.argv[1])

    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1

    try:
        announcements = _scheduled_announcements(to_public(speakers or []))
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    for announcement in announcements:
        module_mm = formats.qr_module_size_mm(formats.PRINT, announcement.event_id)
        if module_mm < formats.SCANNABLE_QR_MODULE_MM:
            print(
                f"::error::{announcement.event_id}: print QR module would be "
                f"{module_mm:.3f}mm, below the {formats.SCANNABLE_QR_MODULE_MM}mm "
                "scannable floor -- edition_code is too long for a printed "
                "A4 poster to stay scannable",
                file=sys.stderr,
            )
            return 1

    out.mkdir(parents=True, exist_ok=True)
    for stale_html in out.glob("*.html"):
        stale_html.unlink()
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()
    fonts_dest = out / "fonts"
    if fonts_dest.exists():
        shutil.rmtree(fonts_dest)

    manifest: list[dict[str, Any]] = []
    if not announcements:
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(
            "no scheduled edition in instance/data/speakers.yml -- nothing to "
            "render (normal until a date is locked)"
        )
        return 0

    for announcement in announcements:
        for fmt in formats.FORMATS:
            html = visual.render_announcement(
                announcement, width=fmt.width, height=fmt.height, root=root
            )
            filename = f"{announcement.event_id}-{fmt.name}.html"
            (out / filename).write_text(html, encoding="utf-8")
            manifest.append(
                {
                    "event_id": announcement.event_id,
                    "name": fmt.name,
                    "width": fmt.width,
                    "height": fmt.height,
                    "file": filename,
                }
            )

    shutil.copytree(root / "fonts", fonts_dest)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {len(manifest)} production visual page(s) for "
        f"{len(announcements)} scheduled edition(s) to {out}"
    )
    return 0


def render_announcements() -> int:
    """`convener-render-announcements OUTPUT_DIR`: the disk-writing
    seam for the ready-to-publish texts (D-09) -- the forum announcement,
    the professional-network post, the mailing-list message, and the
    recording announcement, one Markdown file each, one subdirectory per
    edition (`OUTPUT_DIR/<event id>/<channel>.md`).

    The app (`app/`, D-15's "cockpit") already offers an authenticated
    operator the same four texts, filled in live from the record they have
    open, through `app/src/content/render.ts`'s gated `{{ public.… }}`
    vocabulary (`app/src/state/consent.ts::toPublicFields`). This command
    is the second, independent route to the identical four texts that
    needs no browser and no authenticated session -- `uv run --project
    tools convener-render-announcements OUTPUT_DIR` renders the current, real
    state of `instance/data/speakers.yml` on demand, from a plain checkout, exactly
    the same "manual command, independent of any workflow" property
    `render_visuals`'s own docstring states for the visuals.

    This command has a real
    consumer -- `.github/workflows/visuals-production.yml` runs it
    alongside `convener-render-visuals` and uploads both into the identical
    `announcement-visuals` artefact, one subdirectory per edition, so an
    operator downloads the poster and the words for the same talk
    together rather than hunting two separate places for them. The
    per-edition subdirectory (rather than a flat `<event id>-
    <channel>.txt` naming) is what makes that placement work without a
    merge step: `render-production.mjs` already writes each edition's
    images to `OUTPUT_DIR/<event id>/<format>.png` in that same artefact
    directory, so this command's own `<event id>/<channel>.md` lands
    alongside them, never colliding on a filename. `.md`, not `.txt`: the
    text this command now writes is a page's worth of Markdown (headings,
    emphasis, a volunteer's own working notes), not plain prose, because
    it is now `docs/toolkit/*.md` itself, rendered (`announce.py`'s own
    module docstring) -- the extension names what the file actually is.

    Routed through `public_data.to_public` before either rendering module
    ever sees a row (`announce.py`'s own module docstring) -- never a
    second, looser read of the raw record. A `scheduled` row gets its
    three promotional texts; an `archived` row gets a recording
    announcement only when `announce.recording_announcement` finds a
    `youtube_url` to announce, which is the ordinary, common state (D-13)
    until the speaker agrees and the board's own gate opens.

    Zero renderable editions is a normal state, printed plainly, exit 0 --
    the same "empty is normal" discipline `render_visuals` already
    applies. A malformed date on a record that claims to be scheduled or
    archived is not, and fails loudly instead (D-25).
    """
    if len(sys.argv) != 2:
        print("usage: convener-render-announcements OUTPUT_DIR", file=sys.stderr)
        return 1
    root = repo_root()
    out = Path(sys.argv[1])

    speakers, errors = _load(root / DATA_DIR / "speakers.yml")
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1

    rows = to_public(speakers or [])

    out.mkdir(parents=True, exist_ok=True)
    for stale_text in out.glob("*/*.md"):
        stale_text.unlink()
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()

    manifest: list[dict[str, Any]] = []
    try:
        for row in rows:
            event_id = str(row.get("id", "")).lower()
            if not event_id:
                continue
            status = row.get("status")
            texts: dict[str, str] = {}
            if status == "scheduled":
                texts["forum"] = announce.forum_announcement(row, root=root)
                texts["network"] = announce.network_post(row, root=root)
                texts["mailing-list"] = announce.mailing_list_message(row, root=root)
            elif status == "archived":
                recording = announce.recording_announcement(row, root=root)
                if recording is not None:
                    texts["recording"] = recording
            for channel, text in texts.items():
                event_dir = out / event_id
                event_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{channel}.md"
                (event_dir / filename).write_text(text, encoding="utf-8")
                manifest.append(
                    {
                        "event_id": event_id,
                        "channel": channel,
                        "file": f"{event_id}/{filename}",
                    }
                )
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if not manifest:
        print(
            "no scheduled or announceable archived edition in "
            "instance/data/speakers.yml -- nothing to render (normal until a date "
            "is locked or a recording is published)"
        )
        return 0
    print(f"wrote {len(manifest)} announcement text(s) to {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    # Unreachable under both ways this module is ever run: pytest imports
    # it as convener_ops.cli, never as __main__, and every console script in
    # [project.scripts] (convener-validate and the rest) calls its target
    # function directly -- neither executes this module as a script. Only
    # `python convener_ops/cli.py` or `python -m convener_ops.cli` would, and this
    # project does not invoke it that way.
    sys.exit(validate())
