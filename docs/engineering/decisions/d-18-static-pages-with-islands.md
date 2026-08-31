# D-18 — Static public pages, interactivity in islands

**Status:** Accepted

## Context

Serving the showcase from inside the cockpit application fails on
discoverability: a client-routed application returns the same title and
description to every crawler, so every page produces the same, wrong social
share preview. Separately, the public registration form used to live inside
the *operators'* own application bundle — a visitor who wanted to register
was downloading the whole cockpit to do it, which is bad for load
performance and questionable for a public-facing surface regardless.

## Decision

Public pages — home, event, archives, verification — are statically
generated. Interactive pieces are mounted on them as isolated **islands**:
the registration form on an event's own page, certificate verification on
its own page. Encryption logic lives once, shared, and is never
reimplemented per island.

## Rejected

Serving the showcase and its interactive pieces from inside the operators'
application.

## Cost

The showcase's layout follows the original design's full-bleed, banded
composition rather than the lighter, accent-only layout it previously had —
a real layout change, not a colour swap.
