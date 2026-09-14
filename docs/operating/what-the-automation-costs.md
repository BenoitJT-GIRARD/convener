# What the automation costs

Every automated thing this product does runs on GitHub Actions, and an
instance's cockpit is a **private** repository — its records are personal
data, so it cannot be public (D-15). GitHub Free gives a private repository
**2000 Actions minutes a month**. Nothing here spends money, and nothing
here is allowed to start.

The budget is therefore a design constraint. This page is what was
measured, what it cost, and which prices are the right ones to keep
paying.

## How GitHub actually bills

Three facts, and the first two are the ones that mislead:

1. **Billing is per *job*, not per run.** A workflow with four jobs bills
   four times for one push.
2. **Every job rounds up to a whole minute.** A job that finishes in
   eleven seconds costs a minute. This sets a hard floor: a push that
   wakes six workflows costs at least six minutes however fast they are.
3. **A skipped job costs nothing.** A job whose `if:` is false, or whose
   workflow is filtered out by `paths:`, never gets a runner. This is the
   only lever that reaches zero.

A run's start-to-finish span, which is what the Actions tab shows, is wall
time including queueing. It is neither of the above, and it does not even
rank the workflows in the same order.

## What one session cost, measured

On 2026-09-13, one operator walked the runbook for two seminars on a live
instance: **53 commits in 47 minutes**, each of them a write to
`instance/data/speakers.yml`, each of them waking nine workflows.

**1175 billed minutes** — over half the month — in 400 runs and 472 jobs.
The account's allowance ran out mid-session, and every workflow on the
instance stopped: no publishing, no key minting, no notifications.

| workflow | jobs | billed | share |
|---|---:|---:|---:|
| Monitor secret-bearing workflow runs | 123 | 432 | 37% |
| Quality | 124 | 428 | 36% |
| Validate data | 32 | 51 | 4% |
| Security | 32 | 51 | 4% |
| Derive the decision register | 31 | 47 | 4% |
| Publish showcase | 30 | 45 | 4% |
| Sweep and notify the board | 29 | 44 | 4% |
| Visuals production | 30 | 32 | 3% |
| Deploy app | 30 | 32 | 3% |
| Tell the registrants | 10 | 12 | 1% |
| Mint event keys | 1 | 1 | — |

Two workflows were 73% of it, and neither had anything to do with the
change that woke it.

## What was wrong, and what fixed it

**The secret monitor (432).** It watches twenty secret-bearing workflows
and fires once per watched run. An ordinary push starts four of them, so
one runbook tick paid for four full Python toolchain installs — to compute
that the branch was `main` and write nothing. Its job guard now reads
`github.event.workflow_run.head_branch` straight from the event payload,
which is the same value the alert itself decides on, so on `main` no runner
starts at all.

**The code checks (479).** `quality.yml` and `security.yml` had no path
filter, so a data write re-ran lint, type-check, four package test suites
and a secret scan over source nothing had touched. They now carry
`paths-ignore:` for the instance's own data trees. The handful of tests
that genuinely read the shipped `instance/` tree are marked `shipped_data`
and run by `validate-data.yml` instead — which tests those are was
measured, not assumed.

**The publishers (92).** `publish-showcase.yml` and
`derive-decision-register.yml` had no concurrency block, so twenty-five
ticks bought twenty-five full publishes of a site that only ever ends up in
one state. They now cancel superseded runs, as `deploy.yml` always has.
That is worth tens of minutes; it was done mainly because two overlapping
runs racing to push a built site is a correctness defect, not a cost one.

## What is *not* being cut, and why

**`validate-data.yml` (51).** This is the one check a data write is for. It
is the whole safety net over the file the cockpit writes, and cutting it to
save minutes would be cutting the thing the minutes are for.

**`sweep-and-notify.yml` (44).** Its `immediate` job runs eleven seconds
and bills a minute, twenty-nine times. There is nothing to make cheaper:
the floor is the rounding. It cannot be cancelled either — it composes its
message from the diff against `github.event.before`, so each run holds a
window no other run holds and a cancelled one loses that notification for
good. It watches for the three things worth interrupting people for; 44
minutes is the right price.

**Anything that sends something.** `test_cancellation_safety.py` refuses
`cancel-in-progress: true` on any workflow that mails a registrant or posts
to the board. A cancelled publish is republished by the run that cancelled
it; a cancelled send is simply lost. If such a workflow is costing too
much, narrow what wakes it — never cancel it.

## The second lever: how many commits the work makes

Narrowing what a push wakes took the session from 1175 billed minutes to
roughly 240. What was left was floor rather than waste — six short jobs woken
per write, each billing its minimum whole minute — so the remaining lever was
never another path filter. It was **the number of writes**: fifty-three
commits for two seminars is one per checkbox.

The cockpit now holds a record's checklist edits and writes them together.
Only the checklist: a `checkbox` is a task and a `field` is a fact, nothing
reads either in the same breath, and both are the record catching up with
work already done. A `button-group` is a *transition* — it changes a status,
and a status change publishes an edition, mints a key, opens registration or
sends somebody a message — so it is never held, and it flushes whatever is
held before it writes.

**The worst of what this fixed was not the ticking.** The checklist's fields
fire on every keystroke, and each one wrote: **one commit per character
typed**. It had gone unnoticed because the first values a volunteer reaches
for — a GitHub login, a forum URL — get pasted, and a paste is one event. The
session measured above has exactly one `set host_1` in it for that reason.

## Where the floor is now

| | billed minutes |
|---|---:|
| the session as measured | 1175 |
| with what a push wakes narrowed | ~240 |
| with checklist edits written together | **~115** |

About **ten times less**, and roughly seventeen sessions of that shape in a
month rather than one and a half. For a volunteer who *types* a title and an
abstract rather than pasting them, the difference has no fixed factor at all:
two hundred characters was two hundred commits and is now part of one.

Both figures after the first are projections from the one session there is,
and the first run after an allowance resets is what confirms them.

The queue waits twenty minutes, and that number is deliberately too long to
catch ordinary work. Every other way it empties is somebody doing something —
leaving the record, starting a transition, switching to another tab, pressing
the control that says so. The timer is for a record left open on a screen
nobody is at. A net that caught the ordinary case would be splitting a
volunteer's work into commits at the rhythm of their pauses.

## If an instance runs out anyway

Included minutes reset at the start of the billing cycle, and nothing
restores them early without paying. What follows is what is and is not
actually stopped, because most of it is less than it first looks.

**Taking an update is not blocked.** A merge is git, and git costs no Actions
minutes — so the ordinary procedure in
[Taking an update](taking-an-update.md) works unchanged, including the
`sh gates.sh` it already asks for before the push. Those gates are every
check continuous integration runs and need no account and no secret, so the
verification simply happens on your machine instead of on a runner.

**Nothing accumulates while the workflows are stopped.** `Deploy app` and
`Publish showcase` build from `HEAD`: they publish a *state*, not a queue of
changes. One run after the allowance resets produces exactly what it would
have produced at the moment of the merge. That is the same property that lets
them cancel their own superseded runs.

**The showcase keeps being served.** A public repository has unlimited
Actions minutes, and an instance's published site — the event pages and the
cockpit application both — lives in one. Its own Pages build goes on working
throughout. What has stopped is the private repository that *produces* that
content, not the public one that serves it.

**One thing is genuinely lost: the public proposal form.** `form-relay` turns
the form's webhook into a `repository_dispatch` and holds nothing. The
dispatch is created successfully, the workflow behind it then fails to start,
and the person who submitted sees a confirmation for a proposal that was
never recorded. Close the form at its own source for the duration; a
submitter reading "closed" is told the truth, and a silent success is not.

**Registrations are not in that position.** The signup relay refuses an
edition whose key has not been published, with an honest error, so nothing is
accepted and quietly dropped.

Resist operating the instance by hand in the meantime. Every `convener-*`
command in `tools/` will run locally and do the right thing, which is exactly
what makes it tempting — but a publish done by hand skips the steps the
workflow wraps it in, and one of those refuses to publish a build carrying
the room address. Waiting costs a few weeks of staleness. The other way costs
the guarantee.
