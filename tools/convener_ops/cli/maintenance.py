"""The commands the scheduled jobs run when nobody is watching.

The state sweep, the Actions budget window and its record, and the
evidence that the retention run, the queue drain and the registration
routing are each still happening at all. Every module of
`convener_ops.maintenance` is a pure function of what it is handed; this
is where the disk and the clock come in.

Two names are imported from `convener_ops.cli.journey.registration` rather
than declared here, and the direction is deliberate: the drain writes the
deferral file and this reads it back, so the file's own name belongs to
the writer.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import yaml

from convener_ops.cli import step_output, store
from convener_ops.cli.journey.registration import (
    DEFERRED_FIELD_SEPARATOR,
    QUEUE_DEFERRED_ENV,
)
from convener_ops.declaration.paths import (
    DATA_DIR,
    repo_root,
)
from convener_ops.declaration.yaml_safe import safe_load as yaml_safe_load
from convener_ops.governance.notify import (
    dispatch,
)
from convener_ops.governance.rule import paris_today
from convener_ops.journey import (
    registration_routing,
)
from convener_ops.maintenance import (
    actions_usage,
    credential_expiry,
    queue_watch,
    retention_liveness,
    routing_watch,
)
from convener_ops.maintenance.sweep import expire_votes, sweep_inactive_members
from convener_ops.maintenance.sweep import sweep as sweep_speakers

#: Evidence that retention.yml's own
#: schedule still fires, independent of whether that day's sweep found
#: anything due; see tools/convener_ops/maintenance/retention_liveness.py's own module
#: docstring.
RETENTION_LAST_RUN_HEADER = (
    "# Evidence the retention sweep still runs; "
    "see tools/convener_ops/maintenance/retention_liveness.py\n"
)


#: What the last window of runs actually billed, and the
#: only place in this repository where a *measured* minute exists rather
#: than a `timeout-minutes` ceiling. Committed on purpose: legible by
#: opening this repository, with no run log to scroll and no CI required.
#: The second line is the caveat that must travel with every number in the
#: file; see tools/convener_ops/maintenance/actions_usage.py's own module docstring.
ACTIONS_USAGE_HEADER = (
    "# What this repository's own Actions runs really billed; "
    "see tools/convener_ops/maintenance/actions_usage.py\n"
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


def _report_inactivity(
    cfg: dict[str, Any], speakers: list[dict[str, Any]], now: datetime
) -> None:
    """Print the board-inactivity proposals (G-14) and discard them.

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
    print("Board inactivity (G-14) - proposed, not applied; a human decides:")
    for prompt in prompts:
        print(f"  - {prompt}")


def sweep() -> int:
    root = repo_root()
    speakers_path = root / DATA_DIR / "speakers.yml"
    speakers, errors = store.load(speakers_path)
    cfg, cfg_errors = store.load(root / DATA_DIR / "config.yml")
    if errors or cfg_errors:
        for error in errors + cfg_errors:
            print(f"  - {error}")
        return 1

    now = datetime.now(UTC)
    swept, changes = sweep_speakers(speakers or [], cfg or {}, now)
    swept, vote_changes = expire_votes(swept, cfg or {}, now)
    changes += vote_changes
    if changes:
        speakers_path.write_text(
            # Under the header the file already had. This writer is the one
            # that deleted sixty-seven lines of it, on a schedule, in a commit
            # about elapsed events -- see `store.under_its_own_header`.
            store.speakers_under_own_header(
                speakers_path.read_text(encoding="utf-8"), swept
            ),
            encoding="utf-8",
            newline="",
        )
        for change in changes:
            print(change)
    else:
        print("Nothing to sweep.")

    _report_inactivity(cfg or {}, swept, now)
    return 0


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
#: Actions cannot report on. See tools/convener_ops/maintenance/queue_watch.py's own
#: module docstring.
QUEUE_WATCH_HEADER = (
    "# What the public submission queue still holds, and since when; "
    "see tools/convener_ops/maintenance/queue_watch.py\n"
)


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
        entry, _, reason = line.partition(DEFERRED_FIELD_SEPARATOR)
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
        QUEUE_WATCH_HEADER + store.dump(queue_watch.record_to_data(record)),
        encoding="utf-8",
        newline="",
    )

    stuck = queue_watch.overdue(record, now, thresholds.alarm_after_hours)
    fired = queue_watch.alarms(stuck, now, restarted=restarted)
    print(queue_watch.summary(record, stuck))
    if not fired:
        step_output.write("queue_alert=false\n")
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
    step_output.write("queue_alert=true\n")
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
            "was removed); see tools/convener_ops/maintenance/queue_watch.py",
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

#: A fifth body file, for the reason there is a fourth: several messages
#: composed in one job sharing one filename means whichever is written last
#: silently replaces the rest.
RENEWALS_BODY: Final = "renewals-body.md"


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
    `tools/convener_ops/maintenance/routing_watch.py` for why that comparison rather
    than the file's age, and for why a file naming only past events is a quiet
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
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    config_data, config_errors = store.load(root / registration_routing.CONFIG_PATH)
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
        step_output.write("routing_alert=false\n")
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
    step_output.write("routing_alert=true\n")
    return 0


def check_credential_expiry() -> int:
    """`convener-check-credential-expiry`: is a credential about to stop
    working?

    The watchdog for the failure the other four cannot see. They each
    recompute a signal from something this repository holds; an expiry can
    only be *declared*, because GitHub reports a fine-grained token's expiry
    to its owner alone and a credential held at a third party is further out
    of reach still. `instance/data/credential-renewals.yml` is that
    declaration and
    `tools/convener_ops/maintenance/credential_expiry.py` carries the
    argument for it.

    Prints what it read even when nothing is due, so that a run's log
    distinguishes "nothing is due" from "nothing was looked at" -- only one
    of which is good news, and an undeclared date looks exactly like a
    healthy one from here.

    Returns 0 even when a finding fires, the same split the three alarms
    above use: the workflow's own last step is what turns the job red, so an
    unconfigured channel can never turn a real finding into silence. Returns
    1 only for a declaration this repository owns and cannot read.
    """
    root = repo_root()
    try:
        renewals = credential_expiry.load(root)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    today = paris_today(datetime.now(UTC))
    fired = credential_expiry.due(renewals, today)
    print(credential_expiry.summary(renewals, fired, today))
    if not fired:
        step_output.write("renewal_alert=false\n")
        return 0

    for line in credential_expiry.annotation_lines(fired):
        # Each line names a credential that is about to stop working, which
        # is this watchdog's entire purpose -- the *name* of one, never its
        # value. `py/clear-text-logging-sensitive-data` classifies by the
        # name of the field a value came from, and the field is
        # `Renewal.secret_name`: accurate, and carrying the word the
        # heuristic looks for. Renaming it further to avoid a regular
        # expression would serve the scanner at the reader's expense.
        #
        # What makes this safe is not this comment. `credential_expiry`
        # refuses anything not shaped like a repository secret's name, so a
        # credential pasted where a name belongs never reaches this line --
        # and the refusal that catches it deliberately repeats nothing,
        # because this is where it would be repeated to.
        #
        # A `# codeql[py/clear-text-logging-sensitive-data]` marker was
        # tried here and is not worth trying again: code scanning ignored
        # it, and the alert merely moved down the file with the line, which
        # closed it at the old position and opened it at the new one. That
        # is easy to read as a fix and is not one. The alert is dismissed
        # on the record above instead, and only this repository ever raises
        # it: `security.yml` runs CodeQL on a repository that is not
        # private, and every duplicate's cockpit is private by design
        # (D-15).
        print(line)
    addressed = dispatch(credential_expiry.message(fired, today), os.environ)
    if addressed is not None:
        (root / RENEWALS_BODY).write_text(addressed.body, encoding="utf-8", newline="")
        print(
            f"addressed to thread {addressed.channel.thread}; left in {RENEWALS_BODY}"
        )
    else:
        print(
            "no notification channel is configured -- this finding reaches "
            "nowhere but this run's own red status"
        )
    step_output.write("renewal_alert=true\n")
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
    `tools/convener_ops/maintenance/retention_liveness.py`'s own module docstring for
    why conflating the two into one signal would be worse than answering
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
        RETENTION_LAST_RUN_HEADER
        + store.dump(retention_liveness.record_to_data(today)),
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
    step_output.write(f"since={since.isoformat()}\nmax_runs={budget.max_runs}\n")
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
        ACTIONS_USAGE_HEADER
        + store.dump(actions_usage.record_to_data(usage, previous)),
        encoding="utf-8",
        newline="",
    )
    print(actions_usage.summary_line(usage))

    fired = actions_usage.alarms(usage, budget)
    if not fired:
        step_output.write("budget_alert=false\n")
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
    step_output.write("budget_alert=true\n")
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
            "removed); see tools/convener_ops/maintenance/actions_usage.py",
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
