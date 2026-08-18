"""Command-line entry points. This is the only module that touches the disk."""

from __future__ import annotations

import json
import os
import re

# One fixed git invocation, in `_git_log` and nowhere else; see its docstring.
import subprocess  # nosec B404
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import yaml

from convener_ops.governance import paris_today
from convener_ops.integrations import Integration, load_declaration, resolve_states
from convener_ops.notify import daily_digest, dispatch, immediate_events, render_events
from convener_ops.paths import repo_root
from convener_ops.proposal import skip_reason, to_lead, verify_signature
from convener_ops.public_data import to_public
from convener_ops.register import (
    LOG_FORMAT,
    REGISTER_PATH,
    entries_from_log,
    render_register,
)
from convener_ops.sweep import expire_votes, sweep_inactive_members
from convener_ops.sweep import sweep as sweep_speakers
from convener_ops.validate import validate_config, validate_speakers
from convener_ops.yaml_safe import safe_load as yaml_safe_load

#: The header line each data file carries. `app/src/data/yaml.ts` holds the
#: same two strings: it is the browser's half of this file format, and the
#: YAML-boundary fixture is written by one side and read by the other.
SPEAKERS_HEADER = "# Speakers (unified schema v3 — see docs/reference/schema.md)\n"
CONFIG_HEADER = "# Repo-wide config for the Convener app\n"


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
    lines = ["Integration status", "=================="]
    for integration in integrations:
        lines.append(
            f"{_SYMBOL[integration.state]} {integration.label} - {integration.state}"
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

    On the live data this prints nothing today: every `joined_on` in
    `data/config.yml` is empty pending the September merge, so no silence has a
    countable start. That is the rule declining to speak without evidence, not
    a failure.

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
    payload_str = os.environ.get("PROPOSAL_PAYLOAD", "")
    signature = os.environ.get("PROPOSAL_SIGNATURE", "").strip()
    secret = os.environ.get("TALLY_WEBHOOK_SECRET", "").strip()

    if not payload_str:
        print("no payload", file=sys.stderr)
        return 1

    if not verify_signature(payload_str, signature, secret):
        print("invalid signature", file=sys.stderr)
        return 1

    payload = json.loads(payload_str)
    fields_list = (
        payload.get("data", {}).get("fields")
        if isinstance(payload.get("data"), dict)
        else payload.get("fields")
    )
    if not isinstance(fields_list, list):
        fields_list = []
    fields = {
        f.get("label", ""): f.get("value", "")
        for f in fields_list
        if isinstance(f, dict)
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

#: The previous revision of the speaker file, as a fixed `git show` argument.
#: Held as a constant rather than assembled from a ref and a path so that
#: `_git_show` interpolates nothing at all -- the same discipline as `_git_log`.
PREVIOUS_SPEAKERS: Final = "HEAD~1:data/speakers.yml"


def _git_show(root: Path) -> tuple[str, str]:
    """`data/speakers.yml` as of the previous commit, or an explanation.

    A shallow clone, an initial commit, or a repository with no parent for
    HEAD all land in the error half, and the caller turns that into "nothing
    to compare, so nothing to say" -- never into a message.
    """
    # Fixed argv, shell=False, nothing interpolated: B603 and B607 both
    # describe a risk this call does not carry.
    result = subprocess.run(  # nosec B603 B607
        ["git", "show", PREVIOUS_SPEAKERS],
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

    Compares the working tree's speaker file against the previous commit's.
    With no previous commit to read there is no change to describe, so this
    says nothing rather than treating the whole file as new -- which on a fresh
    clone would announce every lead in it at once.
    """
    root = repo_root()
    after, errors = _load(root / "data" / "speakers.yml")
    if errors:
        for error in errors:
            print(f"  - {error}")
        return 1

    text, error = _git_show(root)
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
    """
    dry_run = "--dry-run" in sys.argv[1:]
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
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if current == rendered:
        print(f"register unchanged - {len(entries)} decision(s)")
        return 0
    path.write_text(rendered, encoding="utf-8", newline="")
    print(f"wrote {REGISTER_PATH.as_posix()} - {len(entries)} decision(s)")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
