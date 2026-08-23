# D-24 — An operator command names a thing, never a person

**Status:** Accepted

## Context

An input to a manually triggered CI job is displayed on that job's own page,
exposed in its logs, and kept alongside the run — for longer than the
short-lived artefact retention this project otherwise holds itself to
elsewhere.

## Decision

Operator commands take a **certificate identifier** or a **pairing code**,
never an address. A certificate identifier is random, public by design, and
names exactly one certificate.

## The exception, and it is a declared one

An early-erasure request (and its identical twin, a resend) accepts an
address as a fallback: refusing to act on someone's data because they
lost their confirmation email would be worse than the exposure. **That
fallback address never sits on a run page in the clear.** It is
encrypted under the event's own public key before it ever becomes a
`workflow_dispatch` input — the operator, or the participant, produces
the ciphertext locally, with no secret, and only the CI job holding the
event's private key can ever read it back out. The exception is not "an
address is exposed, and we accept that"; it is "the fallback still names
an address, but only ciphertext ever reaches a surface GitHub renders or
retains." This exception is named wherever a reader might encounter it,
not only here.

## Rejected

Taking an address as the normal parameter for any operator command.

## Cost

An operator needs the certificate or pairing identifier in hand rather than
just "the person's address" — one extra lookup step, in exchange for never
leaving an address sitting in a CI run's page or logs. Where the address
fallback is used at all, one further step: running `convener-encrypt-identifier`
locally to turn it into ciphertext before it ever reaches the dispatch
form, in exchange for the same guarantee holding even there.
