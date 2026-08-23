# D-26 — Verify the shape that will actually be deployed, never a convenient local one

**Status:** Accepted

## Context

Serving a built site at the root of a local server is not a smaller version
of production — it is a different topology, whenever production serves the
same output from a subpath. A full suite of screenshot-based checks passed
entirely against a locally-rooted server on a site where every path was
written relative to the root, while the actual hosting serves it from a
named subpath. Every relative stylesheet, font and internal link — and both
interactive islands, registration and certificate verification, the two
reasons the surface exists — would have returned a 404 in the real
deployment. Two invisible calls underneath them would have failed the same
way: fetching an event's public key for encryption, and fetching the
certificate register for verification.

The repository already disagreed with itself on this point: one build
configuration baked in the real subpath and had a test pinning it, while the
interactive islands and the generated templates assumed the root. One part
of the system knew where it would live; the rest did not.

## Decision

Any visual or functional verification of a published surface runs **at the
address and topology it will actually be served under.** Serving the built
output at the root of a local server is not a verification — it is a
different artefact from the one that will exist in production.

## Rejected

Verifying against a locally convenient root path and treating a pass there
as representative.

## Cost

A local preview now requires reconstructing the real publish topology
rather than simply opening a build directory. In exchange, the check closes
the whole class rather than one instance of it: no emitted path may be
root-relative without the deployment prefix, that prefix is written once and
tied by a test to the same base addresses the certificate and registration
code already pin — since a build configuration in one language cannot
directly import a constant defined in the other
([D-14](d-14-language-boundary.md) applied to one more boundary) — and the
check also verifies its own inverse: served at the bare root, the site is
required to break.
