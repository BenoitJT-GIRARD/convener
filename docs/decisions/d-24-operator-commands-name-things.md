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

An early-erasure request accepts an address as a fallback: refusing to erase
someone's data because they lost their confirmation email would be worse
than the exposure. This exception is named wherever a reader might encounter
it, not only here.

## Rejected

Taking an address as the normal parameter for any operator command.

## Cost

An operator needs the certificate or pairing identifier in hand rather than
just "the person's address" — one extra lookup step, in exchange for never
leaving an address sitting in a CI run's page or logs.
