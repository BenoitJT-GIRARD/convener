# Operations

Everything the system needs from the outside world. Each integration is
optional: without it the feature degrades visibly and nothing breaks.

Run `cd tools && uv run convener-check-config` at any time to see what is
configured and what is still waiting.

## Before anything else

1. Create an email address owned by the organisation — never a personal one.
2. Create the shared password vault (`secrets.kdbx`, committed to this
   repository) and share the master password out of band with two or three
   Board members.
3. Create every account below with that address, and store its credentials
   in the vault.

A service account tied to one person's mailbox defeats the whole point:
anyone with organisation access must be able to pick this up. Do the vault
first.

## Authentication relay

**Without it:** sign-in falls back to a personal access token. The app stays
fully usable; onboarding is simply slower.

**To create:**
1. Register a GitHub App in the organisation. Permissions: *Contents: read &
   write*, *Issues: read & write*, on `workshop-series` only. Enable device
   flow.
2. Create a Cloudflare account with the organisation address; deploy the
   worker from `services/auth-proxy/` (`npx wrangler deploy` from that
   folder — see its README).

**Secrets to set:**
- Repository secret `CLOUDFLARE_API_TOKEN` (used by *Deploy auth relay* to
  deploy the worker).
- Repository **variables** `VITE_AUTH_PROXY_URL` and
  `VITE_GITHUB_APP_CLIENT_ID` (Settings → Secrets and variables → Actions →
  Variables). Both are public by construction — a relay URL and an OAuth
  client id ship inside the bundle — so they belong in Variables, not
  Secrets.

Whether the worker also needs a client secret depends on whether the GitHub
application is registered as a GitHub App or an OAuth App — confirm before
first deployment (recorded as an open question in
`services/auth-proxy/README.md`).

These variables are read only at build time (Vite requires the `VITE_`
prefix to expose a variable to the browser bundle at all). Setting or
changing them has no effect until the application is rebuilt — push to
`main` or run the *Deploy app* workflow manually.

**To verify:** sign out, reload; the screen should offer a short code rather
than a token field.

## GitHub Pages

**Without it:** nothing else is affected here — this is how the app itself
is published, not an optional integration.

**To create:** Settings → Pages → Source = *GitHub Actions*.

If the repository is private and the current GitHub plan does not offer
private Pages, either make the repository public or fall back to another
static host (for example Netlify or Cloudflare Pages) pointed at the
`app/dist` build output.

**To verify:** push to `main`; the *Deploy app* workflow ends green and the
site answers.

## Meeting platform

**Without it:** the manual adapter is used — links are typed by hand and
attendance is imported from a file. No room link is published
automatically.

**To create:** requires production API credentials from the meeting
provider, granted after a manual request (see phase 4).

**Secret to set:** `CONVENER_MEETING_API_TOKEN`.

**To verify:** run `cd tools && uv run convener-check-config`; *Meeting platform*
moves from `absent` to `production`.

## Outbound email

**Without it:** messages are written to an inspectable log instead of being
sent, and the interface says so. Nothing is silently dropped.

**To create:** see phase 4.

**Secrets to set:** `CONVENER_SMTP_HOST`, `CONVENER_SMTP_USER`, `CONVENER_SMTP_PASSWORD`,
`CONVENER_SMTP_FROM`.

**To verify:** run `cd tools && uv run convener-check-config`; *Outbound email*
moves from `absent` to `production`.

## Video channel

**Without it:** recording URLs are entered by hand after publishing. No
upload is attempted.

**To create:** create the video channel (for example a YouTube channel)
with the organisation address, and record its id.

**Secret to set:** `CONVENER_VIDEO_CHANNEL_ID`.

**To verify:** run `cd tools && uv run convener-check-config`; *Video channel*
moves from `absent` to `production`.
