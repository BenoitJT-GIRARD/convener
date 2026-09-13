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

## Where the floor is now

A session of the same shape should now bill roughly 240 minutes rather than
1175 — about five times less, and eight such sessions in a month rather
than one and a half.

What is left is mostly floor rather than waste: six short jobs woken per
tick, each billing its minimum whole minute. The next real lever is not
another workflow filter, it is **the number of commits**. Fifty-three
commits for two seminars is one per checkbox, and every one of them is a
push. Anything that batched a volunteer's ticks into fewer commits would
divide the remaining cost directly — that change has not been made, because
it trades against losing a volunteer's work if a batch is dropped, and that
trade has not been thought through yet.

## If an instance runs out anyway

Included minutes reset at the start of the billing cycle, and nothing
restores them early without paying. Until then the cockpit's automation is
stopped, and the instance is operated by hand through the `convener-*`
commands in `tools/`. A public repository has unlimited Actions minutes, so
an instance's **showcase** keeps building throughout — only the private
cockpit stops.
