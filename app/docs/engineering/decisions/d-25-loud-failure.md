# D-25 — A control that cannot fail loudly is not a control

**Status:** Accepted

## Context

The absence of a red result is not proof of success. Left unstated, that
sounds obvious; in practice it is a failure shape that recurs, in disguises
different enough that no single fix closes the class.

## Decision

No path in this system reads a command's failure as its answer.

## Why this needed to become a rule, not a habit

The same underlying shape has shown up repeatedly, wearing a different
costume each time: a workflow that reported success without having
transmitted the secret it existed to transmit; a public projection published
where nothing was actually reading it; a step whose failure was
indistinguishable from a negative answer, and which went on to record a
destruction that had never happened; an entirely undecryptable export
reported as "nobody attended", the one reading of that failure that is
certainly wrong; and a correction whose confirmation message never printed
because the process had already exited by the time it tried.

Verification and publication checks produced their own instances: a
performance budget set above anything the site could plausibly reach; an
accessibility rule that an automated tool classifies as a best-practice
suggestion rather than a standards failure, letting a broken heading
hierarchy pass; a leak-detection guard whose only signal was the very field
being stripped out, so it could never see anything else; a dependency audit
flag that exempted an entire dependency tree because the tree declared no
production dependencies at all; a dependency audit added to the one surface
that was already passing; a verification step that could have inspected one
page out of many and reported success regardless of the rest; two
client-mounted interactive pieces that a server-rendered-HTML check would
have found empty and still called valid; and — the most instructive
instance — a reviewed exceptions list for an accessibility checker, indexed
on the tool's generic *reason* rather than the specific element it had
measured, silently pre-approving any element that happened to share that
reason, **inside the very control written to prevent exactly that.**

A further, distinct instance: a workflow written with a YAML construct its
own execution platform cannot parse. It would therefore have failed to
parse at all rather than run — a control that cannot fail because it does
not exist. Alongside it: a leak-detection guard searching for an unfolded
string inside output that the relevant specification requires to be folded,
blind to a real address as a result; and a correctly written, correctly
tested check that nothing in the pipeline ever actually called.

## Consequences

A control captures the status of what it inspected **separately** from what
it concludes from that status. A deliberate skip announces itself — a step
that did nothing must never present as a step that succeeded. And tests
enforce this; it is not left as a drafting habit to remember.

**The counter-proof is now standard practice.** No check ships without
first being broken on purpose and watched to fail: a budget is burst
deliberately, a violation is injected deliberately, a mutation is applied
deliberately. Every instance listed above was found this way — none by
re-reading the code that was supposed to catch it.

## Rejected

Trusting a green result at face value, or trusting careful reading in place
of a negative test.

## Cost

Every control now carries its own negative test alongside the positive one
— roughly doubling what "adding a check" means, in exchange for a green
result that can actually be trusted to mean something.
