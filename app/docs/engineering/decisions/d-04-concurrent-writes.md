# D-04 — Concurrent writes are handled explicitly

**Status:** Accepted

## Context

More than one person can have the same record open at once, and a scheduled
job can also write to it. A write that ignores this loses data silently: two
people editing the same speaker, or a background sweep writing while someone
has the page open, can each overwrite the other's change.

## Decision

Every write handles a version conflict (an HTTP `409`) explicitly: reload,
reapply the change, retry. No write is ever triggered merely by loading a
page.

## Rejected

Sending a known file version and ignoring a rejection — the shape the system
previously had, where two simultaneous sessions were enough to produce a
lost write or a hard error, and where a routine background sweep wrote
during an ordinary page load.

## Cost

Every mutating action carries retry logic instead of a bare write, and a
user occasionally sees a brief "reapplying your change" pause instead of an
instant save. That is the price of a system with no server to serialise
writes for it.
