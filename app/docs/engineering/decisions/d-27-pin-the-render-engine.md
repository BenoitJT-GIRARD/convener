# D-27 — A comparison against a reference only means something if the engine that produced it is pinned

**Status:** Accepted

## Context

A check that compares rendered output against a versioned reference image
only has meaning if the engine producing that output cannot drift under it.
Without pinning, a silent engine update that turns the comparison red
teaches one reaction — "regenerate the reference" — and that is exactly the
reaction that will also fire the day the thing actually being checked has
changed. Pinning is not a belt next to a brace; it is what gives a red
result meaning at all: "what I am checking changed", never "the machine
changed".

## Decision

The rendering engine used for any reference-image comparison is pinned
through a locked dependency, not through a container built and maintained
for one job.

## Rejected

An unpinned render step using whatever engine happens to be installed, and a
purpose-built container image maintained solely for this one comparison —
this project had just finished observing what becomes of infrastructure
nobody exercises regularly.

## Cost

Measured before it was accepted: roughly 430 MB of browser download,
isolated into its own package so that no other workflow pays for it, and
gated by a path filter so the job only runs when it actually has something
to compare.

## Proof, in both directions

The check is broken deliberately and watched to go red, then rerun
unchanged and watched to return to green. A check that is red at random gets
ignored exactly as quickly as a check that is never red — the second half of
that proof matters as much as the first.
