# D-09 — LinkedIn publication stays manual

**Status:** Accepted

## Context

LinkedIn's posting API requires an application review and a page
administrator's own token — a lot of integration cost for a channel that
already works without it.

## Decision

The application generates ready-to-paste post text. Publishing itself stays
a manual action.

## Rejected

Automated posting through LinkedIn's API.

## Cost

None beyond the manual step itself — someone still has to paste and publish.
That step already happens reliably without automation, so nothing is lost
by not building it.
