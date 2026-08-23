"""Detects, never prevents: a secret-bearing workflow run whose ref was not
`main`.

The security audit's C1/C2 fix wanted every job that reads a sensitive
secret scoped behind a GitHub `environment:` with a deployment branch
policy, so a `workflow_dispatch` against an attacker's own branch would be
refused the secret before any step ran -- real prevention. That control
requires GitHub Team or GitHub Pro on a private repository (verified against
GitHub's own documentation, not assumed); this repository is on GitHub Free,
and the project's own zero-cost constraint does not suspend for security.
`docs/superpowers/mise-en-ligne.md` Sec 4 records what that leaves open.

What is left, at zero cost, is **detection**: `.github/workflows/
secret-workflow-monitor.yml` watches every workflow this repository's own
tests confirm declares a secret beyond `GITHUB_TOKEN`, and fires on
`workflow_run` with `types: [requested]` -- within seconds of the run being
queued, not after it finishes. This module composes what that alert says.
It does not, and structurally cannot, stop the run it is reporting on: by
the time this code executes, the workflow it is describing has already been
requested, and nothing here calls the Actions API to cancel anything. A
loud, fast alert shortens the time before someone rotates whatever the run
could see from "nobody ever finds out" to "minutes" -- real, worthwhile
value, and not the same property as P-5, which asks whether the exfiltration
could happen at all. Never describe this module's output as though it were.

Shares its channel with `notify.py` rather than inventing a second address
book: `dispatch()` and `Channel` are imported from there unchanged, so a
board that has already configured `CONVENER_NOTIFY_THREAD` and
`CONVENER_NOTIFY_MENTION` for governance notices needs nothing new configured for
this alert to reach the same thread, and `resolve_channel`'s "both or
neither" rule (a malformed mention must never look like a mention) is not
reimplemented a second time to drift from the original.

**The `::error::` job failure is unconditional, the notification is not.**
`.github/workflows/secret-workflow-monitor.yml`'s own last step fails the
job whenever `alert_message` returns non-`None`, whether or not a
notification channel exists to also post to -- the same reasoning
`config/integrations.yml`'s "read-only default" gives everywhere else in
this repository: an unconfigured integration must never be able to turn a
real finding into silence.
"""

from __future__ import annotations

from typing import Final

#: The one ref every sensitive workflow in this repository is meant to run
#: against. Anything else -- another branch, an empty or missing value,
#: a tag -- is worth reporting; see `alert_message`'s own docstring for why
#: an unrecognised value is treated the same as a wrong one, never as `main`.
MAIN_BRANCH: Final = "main"


def alert_message(
    *,
    workflow_name: str,
    head_branch: str | None,
    run_event: str,
    run_url: str,
    actor: str,
) -> str | None:
    """The alert body for one `workflow_run` event, or `None` when there is
    nothing to report.

    `None` exactly when `head_branch == "main"` -- the run this whole system
    exists to allow. Every other value is reported, including an absent or
    empty branch name: GitHub omits `head_branch` for a run whose branch has
    since been deleted, and a run this module cannot positively confirm was
    on `main` must never read as though it were. Silence is the one outcome
    this function must get right; a false alarm costs a board member one
    read they can dismiss; a missed one costs the property the whole
    workflow exists to protect.
    """
    if head_branch == MAIN_BRANCH:
        return None
    branch_text = (
        head_branch if head_branch else "(branch unknown -- see the run itself)"
    )
    lines = [
        "Workshop series - a secret-bearing workflow ran off main",
        "",
        f"  - workflow: {workflow_name or '(unknown)'}",
        f"  - ref: {branch_text}",
        f"  - trigger: {run_event or '(unknown)'}",
        f"  - actor: {actor or '(unknown)'}",
        f"  - run: {run_url or '(unknown)'}",
        "",
        "This reports only that the run happened against that ref -- not that",
        "a secret was read, and not that anything left the run. If this was",
        "not an expected operator action, rotate whatever this workflow can",
        "see and read the run's own log before doing anything else.",
    ]
    return "\n".join(lines)
