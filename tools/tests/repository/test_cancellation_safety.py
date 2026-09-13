"""When a superseded run may be cancelled, and when cancelling one loses something.

`concurrency.cancel-in-progress: true` is the cheapest minute-saving in
GitHub Actions and the easiest to misapply, because whether it is safe is
not a property of the workflow's cost — it is a property of what the
workflow *produces*.

**A workflow that publishes a state may be cancelled.** Whatever it is part
way through producing, a run started since is producing a newer version of
the same thing; the superseded run has nothing left to say. `deploy.yml`
has always said so, and says why in
`test_deploy_workflow_cancels_stale_runs_of_itself`: two overlapping runs
race to push a build, and the loser's rebase can replay cleanly and let the
older one silently overwrite the newer. `publish-showcase.yml` is the same
shape and had no concurrency block at all.

The minutes are the second reason and the smaller one. Measured on the
instance this product was derived for, on 2026-09-13, in billed minutes --
per job, rounded up, which is how GitHub charges -- `deploy.yml` cost 32
across 30 jobs with cancellation on, `publish-showcase.yml` 45 across 30
without it, and `derive-decision-register.yml` 47 across 31. These are
short jobs and every job bills at least a whole minute, so cancellation is
worth tens of minutes here. The hundreds were elsewhere: `quality.yml` at
428 and the secret monitor at 432, both of them waking for work they had
nothing to do about.

**A workflow that sends something may not.** `sweep-and-notify.yml`'s
`immediate` job composes a message from the diff between
`github.event.before` and the push that woke it: each run holds a window no
other run holds, so a cancelled run does not lose a race, it loses that
window's notification permanently. The same is true of every workflow that
mails a registrant or a speaker — a cancellation between "sent" and
"recorded" is the defect `cancel-edition.yml` was already split in two to
avoid.

Both halves happen to hold today. This module is here because the pressure
that would break the second one is exactly the work that established the
first: somebody reading the minutes, seeing a workflow run thirty times,
and reaching for the one-line fix that worked next door.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.yaml_safe import safe_load

WORKFLOWS = repo_root() / ".github" / "workflows"

#: How a workflow says, in its own YAML, that it puts something in front of
#: a person. Text rather than structure on purpose: a send can be a `run:`
#: line, a step's `env:`, or a command name, and what they have in common is
#: the vocabulary, not the shape. A marker matching too widely costs a
#: workflow its cancellation and nothing else; one matching too narrowly
#: costs somebody their message.
SEND_MARKERS = (
    "gh issue comment",  # the board thread, which GitHub turns into email
    "convener-tell",  # telling the registrants of a cancelled edition
    "convener-send",
    "convener-resend",
    "convener-invite",
    "convener-deliver",
    "convener-issue-certificates",
    "SMTP",
    "BREVO",
)

#: The workflows whose whole output is the latest state of something
#: published. Named rather than inferred: "publishes a state" is a claim
#: about what a workflow means, and the day one of these starts sending a
#: message as well, the list is where a reader will look.
PUBLISHERS = ("deploy.yml", "publish-showcase.yml", "derive-decision-register.yml")


def _workflows() -> list[tuple[Path, str, Any]]:
    out = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        out.append((path, text, safe_load(text)))
    return out


def _sends(text: str) -> bool:
    return any(marker in text for marker in SEND_MARKERS)


def _cancels(data: Any) -> bool:
    concurrency = data.get("concurrency")
    if not isinstance(concurrency, dict):
        return False
    return concurrency.get("cancel-in-progress") is True


def test_the_reader_knows_a_sender_when_it_sees_one() -> None:
    """Positive control. A marker list that matched nothing would make the
    rule below pass over an empty set, which is the one way this module
    could be quietly useless."""
    by_name = {path.name: text for path, text, _ in _workflows()}

    assert _sends(by_name["sweep-and-notify.yml"]), (
        "sweep-and-notify.yml posts to the board thread and must read as a "
        "sender -- it is the workflow this whole rule was written for"
    )
    assert _sends(by_name["cancel-edition.yml"]), (
        "cancel-edition.yml tells the registrants of a cancelled edition "
        "and must read as a sender"
    )
    assert not _sends(by_name["publish-showcase.yml"]), (
        "publish-showcase.yml reads as a sender, so the marker list has "
        "grown wide enough to cover a publisher -- the rule would then "
        "forbid the very cancellation it is paired with"
    )
    assert not _sends(by_name["deploy.yml"]), "deploy.yml sends nothing"


def test_no_workflow_that_sends_something_cancels_a_run_in_progress() -> None:
    """The rule that protects a message.

    A cancelled publish is republished by the run that cancelled it. A
    cancelled send is not re-sent by anything: the run that superseded it
    is composing a *different* message, from a different window, and the
    one that was interrupted is simply gone.
    """
    offenders = [
        path.name
        for path, text, data in _workflows()
        if _sends(text) and _cancels(data)
    ]
    assert not offenders, (
        "these workflows put something in front of a person and cancel a "
        f"run in progress: {sorted(offenders)}. A superseded send is not "
        "retried by the run that superseded it -- it is lost. If the "
        "minutes are the problem, narrow what wakes the workflow; never "
        "cancel it."
    )


def test_every_publisher_yields_to_the_run_that_supersedes_it() -> None:
    """The other half, and the saving itself.

    Each of these produces the latest state of one published thing, so a
    superseded run has nothing left to say. Left without a concurrency
    block, a volunteer ticking twenty-five runbook boxes pays for
    twenty-five full publishes of a site that only ever ends up in one
    state.
    """
    by_name = {path.name: data for path, _, data in _workflows()}
    for name in PUBLISHERS:
        assert _cancels(by_name[name]), (
            f"{name} publishes the latest state of something but does not "
            "cancel superseded runs -- so two of them can race to publish, "
            "and the loser's rebase can replay cleanly with the older "
            "result overwriting the newer. That is the case deploy.yml has "
            "always cancelled for, and the two files that lacked it billed "
            "92 minutes across 61 jobs against deploy.yml's 32 across 30."
        )


def test_a_publisher_groups_on_a_constant_so_it_cannot_drift() -> None:
    """`${{ github.ref }}` reads like "one run per branch" and is the same
    constant here, since every trigger these files carry resolves to the
    default branch. Written as a constant it cannot quietly become
    per-something-else later and stop cancelling anything at all."""
    by_name = {path.name: data for path, _, data in _workflows()}
    for name in PUBLISHERS:
        group = by_name[name]["concurrency"]["group"]
        assert "${{" not in group or "github.workflow" in group, (
            f"{name}'s concurrency group is {group!r} -- an expression that "
            "varies per run would put every run in its own group, which "
            "cancels nothing while looking exactly like this rule being "
            "followed"
        )
