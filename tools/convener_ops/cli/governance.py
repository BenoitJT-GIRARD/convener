"""The commands that read what the board decided and say so out loud.

The validator run over the records, the register derived from the commits
that carry the decisions, the two notifications a volunteer who is not
looking at the app receives, and the alarm a secret-touching workflow run
raises. `convener_ops.governance` holds the rules; this module opens the
files and writes the messages.
"""

from __future__ import annotations

import json
import os
import re

# One fixed git invocation, in `_git_log` and nowhere else; see its docstring.
import subprocess  # nosec B404
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import yaml

from convener_ops.cli import step_output, store
from convener_ops.declaration import published
from convener_ops.declaration.paths import (
    DATA_DIR,
    REGISTER_PATH,
    repo_root,
)
from convener_ops.declaration.yaml_safe import safe_load as yaml_safe_load
from convener_ops.governance.dispatch_alert import alert_message
from convener_ops.governance.notify import (
    daily_digest,
    dispatch,
    immediate_events,
    render_events,
)
from convener_ops.governance.register import (
    LOG_FORMAT,
    entries_from_log,
    render_register,
)
from convener_ops.governance.validate import (
    board_target_report,
    validate_config,
    validate_speakers,
)


def validate() -> int:
    root = repo_root()
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    cfg, cfg_errors = store.load(root / DATA_DIR / "config.yml")
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
    behaviour `declarations/integrations.yml` promises for outbound email.
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
    after, errors = store.load(root / DATA_DIR / "speakers.yml")
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
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    cfg, cfg_errors = store.load(root / DATA_DIR / "config.yml")
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
        step_output.write("off_main=false\n")
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
    step_output.write("off_main=true\n")
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
