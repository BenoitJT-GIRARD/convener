# D-03 — Authentication: a GitHub App and the device flow

**Status:** Accepted

## Context

Signing in previously meant pasting a personal access token by hand — hostile
to non-technical volunteers, and one that needs re-copying every 90 days per
person. GitHub's OAuth endpoints send no CORS headers, so a browser
application cannot complete the device flow by calling them directly.

## Decision

Sign-in goes through a **GitHub App** using the **device flow**, relayed by a
stateless **Cloudflare Worker owned by the organisation**. The user clicks
"sign in with GitHub", is shown a short code, enters it at
`github.com/login/device`, and returns signed in — about thirty seconds, no
settings page.

The Worker's only job is forwarding the two OAuth requests that need CORS
headers added. It holds no state, no database, no business logic. Its source
lives in the repository and deploys from CI; the hosting account belongs to
the organisation.

## Rejected

Hardening the existing personal-token flow instead. It costs nothing to set
up and something forever: every volunteer's token still expires every 90
days. On a non-technical population, onboarding friction is what determines
whether the tool gets used at all.

## Cost

One more small service to operate and, in principle, redeploy if its hosting
account is ever lost — mitigated by living in the repository and deploying
from CI rather than by hand. In exchange, a session token now lasts hours
rather than 90 days, is revocable from the organisation's side, and is
scoped to the installation rather than to a whole personal account.
