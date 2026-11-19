# D-13 — Every integration is optional, and absence is a normal state

**Status:** Accepted

## Context

External accounts (meeting platform, email sending, authentication relay,
video channel) cannot all be finalised on day one — some depend on
decisions and approvals outside the development process's control.
Development cannot be blocked waiting on them.

## Decision

The system is built and shipped **fully functional with zero external
accounts configured**. Connecting an account is always an addition of a
secret, never a code change.

**Rules that follow from this:**

1. **No hard-coded credential.** Every external dependency goes through a
   named, documented secret, read in one place.
2. **Every integration has three states** — absent, trial, production — and
   absent is a normal state, never an error.
3. **Degrade visibly, never break.** An unconfigured integration degrades
   the feature explicitly rather than failing:
   - no meeting-platform account → the manual adapter takes over, the event
     page shows that no link is set yet;
   - no email transport → messages are written to an inspectable log
     instead of being sent, and the interface shows they are pending;
   - no authentication relay → the system falls back to a documented
     personal-token flow.
4. **Everything is testable with no account at all.** Every external
   adapter has a test implementation driven by fixed data; the test suite
   never touches the network.
5. **Configuration state is visible.** One command and one CI job report
   which integrations are active, which are pending, and which secret is
   missing for each.
6. **One reference page per account**, in the operations documentation:
   what to create, the exact secret name to set, and how to confirm it
   works.

## Rejected

Waiting for every account to be finalised before building against it, or
building against a specific vendor's SDK directly rather than a documented
secret and a degraded-absent state.

## Cost

Every integration is written twice in effect — the real adapter and the
degraded/test behaviour for its absence — and the system carries visible
"not configured yet" states in production until an account is created. In
exchange, nothing about delivery timing for an external account can block
shipping working software.
