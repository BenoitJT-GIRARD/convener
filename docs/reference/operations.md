# Operations

Everything the *application code* needs from the outside world. Each
integration is optional: without it the feature degrades visibly and
nothing breaks -- with one exception, *Event registration keys* below,
which fails closed rather than degrading, because what it protects is
personal data rather than a feature.

Run `cd tools && uv run convener-check-config` at any time to see what is
configured and what is still waiting. That declaration
(`config/integrations.yml`) covers only what `tools/convener_ops` and `app/src`
themselves read at runtime — three further secrets exist to gate CI
workflow behaviour and are documented in their own section below instead,
since `convener-check-config` running on a laptop would otherwise report them
as permanently missing.

## Before anything else

1. Create an email address owned by the organisation — never a personal one.
2. Create the shared password vault (`secrets.kdbx`) in the organisation's
   existing shared Drive, or in a password manager the Board already uses —
   never committed to this repository — and share the master password out
   of band with two or three Board members.
3. Create every account below with that address, and store its credentials
   in the vault.

A service account tied to one person's mailbox defeats the whole point:
anyone with organisation access must be able to pick this up. Do the vault
first.

This repository must stay private: `data/speakers.yml` holds personal data
(names and institutional email addresses of external academics).

## Authentication relay

**Without it:** sign-in falls back to a personal access token. The app stays
fully usable; onboarding is simply slower.

**To create:**
1. Register a GitHub App in the organisation. Permissions: *Contents: read &
   write* and nothing else, on `example-cockpit` only. Enable device flow. The
   app never touches issues -- the board notifications are posted by the
   workflow's own token, not by this app -- so granting it *Issues* would be
   a permission nobody uses on a repository holding personal data.
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

The worker needs no client secret. Its device-flow login does not require
one, and the app does not attempt to refresh access tokens — refreshing
would require a client secret, and putting one into a relay we deliberately
built stateless and secret-free is a worse trade than re-running the
30-second device flow each session. Users re-authenticate once per session
instead.

These variables are read only at build time (Vite requires the `VITE_`
prefix to expose a variable to the browser bundle at all). Setting or
changing them has no effect until the application is rebuilt — push to
`main` or run the *Deploy app* workflow manually.

**To verify:** sign out, reload; the screen should offer a short code rather
than a token field.

## Form relay

**Without it:** the public Tally form has nowhere to send a submission. No
proposal is turned into a lead, and *Handle proposal*
(`.github/workflows/candidate-form.yml`) is never triggered.

This is a second Cloudflare Worker, `services/form-relay/`, deliberately
separate from the authentication relay above. That relay is stateless and
secret-free by design, which is what lets anyone in the organisation
redeploy it with one command (see its README). The form relay cannot make
that claim — turning a Tally webhook into a `repository_dispatch` requires
a GitHub token — so it holds one, and is kept in its own Worker rather than
folded into the auth relay, so the secret-free property of the other one
still holds.

**To create:**
1. Build the public form: `TALLY_API_KEY=tly-xxxx uv run python
   ../scripts/create_tally_form.py` from `tools/`. It is created as a
   `DRAFT`, deliberately — open it in Tally's dashboard and confirm the
   hint text actually renders under *Gender* and *Career stage* before
   publishing it. That text is placed on each dropdown's first option, a
   location `scripts/create_tally_form.py`'s own docstring notes is
   inferred from Tally's schema rather than confirmed against a worked
   example, so the script cannot verify for itself that Tally renders it
   as a hint rather than treating it as something else (Tally's OpenAPI
   spec suggests that field may instead be reserved for an "Other"
   sub-field on some block types) — if it does not render, the two
   dropdowns still resolve correctly, but a respondent sees a bare token
   with no explanation. Publish by hand once satisfied; a later run of
   the script never touches `status`, so this is a one-time check.
2. Deploy the worker from `services/form-relay/` (`npx wrangler deploy`
   from that folder — see its README) to the same Cloudflare account used
   for the authentication relay above.
3. Configure Tally's webhook to `POST` to the worker's URL with no path
   suffix (the worker's only route is its root) — any other path 404s and
   the submission is silently lost — and set the same signing secret in
   Tally that is set below as `TALLY_WEBHOOK_SECRET`.

**Secrets to set:**
- Wrangler secret `TALLY_WEBHOOK_SECRET` on the worker — set with
  `npx wrangler secret put TALLY_WEBHOOK_SECRET` from
  `services/form-relay/`. The same value must also be set as the
  repository secret `TALLY_WEBHOOK_SECRET` (see *CI-only secrets* below):
  Tally signs with it, the worker verifies it, and
  `tools/convener_ops/proposal.py` verifies it again on the GitHub Actions side
  — one secret, read in three places.
- Wrangler secret `CONVENER_DISPATCH_TOKEN` on the worker — set with
  `npx wrangler secret put CONVENER_DISPATCH_TOKEN` from
  `services/form-relay/`. A GitHub token scoped to *Contents: read & write*
  on `example-cockpit` only, sufficient to send it a `repository_dispatch`.
- Repository secret `CLOUDFLARE_API_TOKEN` — the same one already set for
  *Deploy auth relay* above; *Deploy form relay* reads it too, since both
  workers deploy to the same Cloudflare account.

Neither Wrangler secret belongs in `wrangler.toml` — both are set with
`npx wrangler secret put`, never committed.

**To verify:** submit the Tally form; a new lead should appear in
`data/speakers.yml` shortly after, committed by *Handle proposal*.

## Signup relay

**Without it:** the registration page has nowhere to send an encrypted
registration. `SignupForm.tsx` still fetches an event's public key and
still encrypts in the browser — nothing about that depends on this worker —
but with `VITE_SIGNUP_RELAY_URL` unset it says so and sends nothing: an
ordinary D-13 absence, not an error, and never a fallback to sending
anything unencrypted.

This is a third Cloudflare Worker, `services/signup-relay/`, separate from
both the authentication relay and the form relay above, for two different
reasons rather than one. Like the form relay, turning a submission into a
`repository_dispatch` needs a GitHub token, so it cannot be the stateless,
secret-free authentication relay. Unlike the form relay, there is no
shared secret its caller could sign with — a static registration page
cannot hold one — so its endpoint is open by construction where the form
relay's is not; see `services/signup-relay/README.md` for the abuse
protection chosen for that (a per-event burst limiter and a per-event
cumulative ceiling, in two separate Cloudflare bindings) and the reasoning
recorded alongside it, including the Workers KV and Workers Rate Limiting
free-tier evidence checked while choosing it.

Unlike the other two, this worker cannot read what it forwards at all —
the body is ciphertext the browser encrypted under the target event's
public key (`tools/convener_ops/eventkeys.py`), and this worker holds no
private key. Its validation is a shape check, not a content check: see
its README for exactly what that does and does not verify.

It also answers cross-origin requests: the registration page and this
worker are served from different origins, so it follows the same CORS
pattern `services/auth-proxy/` already established (see its README's
"Cross-origin requests" section) rather than a second one.

**To create:**
1. Deploy the worker from `services/signup-relay/`: `npm install`, then
   `npx wrangler kv namespace create SIGNUP_RELAY_KV` once and paste the
   printed id into that folder's `wrangler.toml`, then `npx wrangler
   deploy` — see its README — to the same Cloudflare account used for the
   other two workers. `SIGNUP_RATE_LIMITER`, the burst limiter, needs no
   equivalent creation step and ships already configured in
   `wrangler.toml`.
2. Set repository **variable** `VITE_SIGNUP_RELAY_URL` (Settings → Secrets
   and variables → Actions → Variables) to the deployed worker's URL. Public
   by construction, like `VITE_AUTH_PROXY_URL` above — a relay URL ships
   inside the bundle — so it belongs in Variables, not Secrets. Like those,
   it is read only at build time (forwarded into the build by
   `.github/workflows/deploy.yml`'s own `Build` step); setting or changing
   it has no effect until the application is rebuilt.

**Secrets to set:**
- Wrangler secret `CONVENER_DISPATCH_TOKEN` on the worker — set with
  `npx wrangler secret put CONVENER_DISPATCH_TOKEN` from
  `services/signup-relay/`. A GitHub token scoped to *Contents: read &
  write* on `example-cockpit` only — the same scope the form relay's own
  `CONVENER_DISPATCH_TOKEN` uses, since this worker both reads
  `keys/events/<id>.pub` to confirm an event is known and sends the
  `repository_dispatch` itself. Create a **separate** token from the form
  relay's rather than reusing it: this worker spends two GitHub API calls
  per registration against the same 5,000/hour budget the form relay also
  draws on, and one shared token would couple the two workers' quotas
  together — see the README's "Secrets" section for the failure mode that
  creates.
- Repository secret `CLOUDFLARE_API_TOKEN` — the same one already set for
  *Deploy auth relay* and *Deploy form relay* above; *Deploy signup relay*
  reads it too, since all three workers deploy to the same Cloudflare
  account.

`SIGNUP_RELAY_KV` and `SIGNUP_RATE_LIMITER` are not secrets — see the
README's "Secrets" section for what each needs and why only the former
needs a creation step; both are set directly in
`services/signup-relay/wrangler.toml` rather than as Wrangler secrets.
`deploy-signup-relay.yml`'s own gate skips the deploy, rather than letting
`wrangler deploy` fail, while the KV namespace id is still the placeholder
`wrangler.toml` ships with.

**To verify:** with `VITE_SIGNUP_RELAY_URL` set and the app rebuilt, submit
the registration form for an event with a published key; the worker
answers `204` and the `registration-submitted` dispatch it sends triggers
the workflow that handles it (see phase 4).

## Publishing the application (GitHub Pages)

**Without it:** nothing else is affected here — this is how the app itself
is published, not an optional integration.

**To create:** nothing, on this repository — Pages is not enabled here.
`example-cockpit` stays private (see *Before anything else* above), and GitHub
Pages will not serve a private repository without a paid plan, which the
project's no-cost constraint rules out. This page was right to name a
fallback for that case (Netlify, Cloudflare Pages, pointed at `app/dist`);
the fallback was never needed, because a route already sat closer to hand.

Pages is instead enabled on the separate, public
`example-instance/example-showcase` repository: Settings → Pages → Source =
*Deploy from a branch*, branch `main`, folder `/ (root)`. The *Deploy app*
workflow (`.github/workflows/deploy.yml`) builds the app here and pushes
`app/dist` into `example-showcase`, under `app/` — the same pattern *Publish
vitrine data* (`.github/workflows/publish-vitrine.yml`) already uses to
push the public events feed under `src/_data/`. The site is at
`https://example-instance.github.io/example-showcase/app/`.

This route, and not a third-party static host, because it adds no account.
A paid plan was already ruled out by the no-cost constraint; a third-party
host such as Netlify or Cloudflare Pages would still need its own account,
which is one more account somebody has to own, and the project's
constraints already forbid resting on any one collaborator's goodwill or
position. `example-showcase` costs nothing new to add: it already exists, under
the same organisation, to serve the public events feed.

**Also needs correcting, outside this repository:** the GitHub App's homepage URL
(the organisation's Settings → Developer settings → GitHub Apps → the app
registered above under *Authentication relay*) still reads
`.../example-cockpit/`. Point it at the address above instead. This is a
setting, not code — no test, no CI job and no type will ever notice it
drifting, so this paragraph is the only mechanism that gets it corrected.

**To verify:** push to `main`; the *Deploy app* workflow ends green and the
site answers at the address above.

## Meeting platform

**Without it:** the manual adapter (`tools/convener_ops/platform.py::ManualPlatform`)
is used — links are typed by hand and attendance is imported from a file. No
room link is published automatically. This is D-13's ordinary state, not a
degraded one, and it stays fully usable indefinitely: nothing in this project
requires the meeting provider's own API to ever be configured.

**With it:** `tools/convener_ops/platform_fcc.py::PlatformFCC` is used instead,
selected automatically by `platform_from_env` from whether the secret below
is set. Real per-person attendance is read from the provider's own
`GET /api/v4/conferences/{id}/calls` — one row per connection, address,
join and leave time, duration — and the session recording is reported and
deleted through the same API rather than tracked by hand. **This endpoint is
not published in the provider's own API reference.** It has answered
consistently against a real account and a real token, more than once, but
nothing contractual guarantees it keeps answering. If it ever stops, nothing
breaks: `platform_from_env` falls back to the manual adapter the moment the
secret is unset, exactly as it does today.

**To create:** requires production API credentials from the meeting
provider, granted after a manual request (see phase 4). The value to set is
a bearer **access token**, not a client id and secret — this project does
not exchange credentials for one itself.

**Secret to set:** `CONVENER_MEETING_API_TOKEN`.

**To verify:** run `cd tools && uv run convener-check-config`; *Meeting platform*
moves from `absent` to `production`.

**Renewing the token — a step of the event's journey, not a secret set
once.** The access token is short-lived (31 days on one grant observed, 14
on another) against a series that runs roughly monthly, so renewal cannot be
a one-time setup step. The provider's refresh token would solve that, but it
**rotates on every use** — exchanging it issues a new refresh token and
invalidates the old one, so it cannot be stored once as a secret the way an
access token is; whatever holds it must be rewritten by hand on every
renewal. The design that survives that constraint is human-in-the-loop
rather than automated:

1. The refresh token lives only in the shared vault (`secrets.kdbx`), never
   in this repository.
2. Roughly once a month, alongside the other T-7 preparations already on an
   event's runbook (beside a line like "Waiting room and co-host rights set
   up"), a volunteer completes a short browser consent step with the
   provider and pastes the new access token into `CONVENER_MEETING_API_TOKEN`.
3. If nobody has, before the current token's remaining life runs low, a
   **notice is posted to the board thread** — the same channel
   `convener-notify-immediate` already posts through — rather than the
   integration failing silently on the day of a seminar.

Skipping the step costs one event's manual attendance import through the
fallback above, never a cancelled seminar and never a security incident. The
journey line and the board notice that drive this are wired up in a later
phase-4 task; this section documents the procedure a volunteer or that later
task follows, and `tools/convener_ops/platform_fcc.py`'s module docstring
documents the same reasoning from the code's side.

## Outbound email

**Without it:** messages are written to an inspectable log instead of being
sent, and the interface says so. Nothing is silently dropped.

**To create:** see phase 4.

**Secrets to set:** `CONVENER_SMTP_HOST`, `CONVENER_SMTP_PORT`, `CONVENER_SMTP_USER`,
`CONVENER_SMTP_PASSWORD`, `CONVENER_SMTP_FROM`.

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

## Board notifications

**Without it:** nothing is sent. The digest and the immediate events are
still composed and printed to the *Notify the board* job log, where any
volunteer can read exactly what would have gone out, but they are addressed
to nobody and no comment is posted.

This is structural rather than a setting. A message needs both a thread to
be posted on and a team to mention; without both, no addressed message is
built at all, so the workflow's posting step finds nothing to post. There is
no notifications on/off switch anywhere in the chain, and a quiet day and an
unconfigured repository behave identically.

**To create:** no external service and no account — GitHub itself is the
delivery mechanism.

1. Open an issue in this repository to serve as the standing notification
   thread (for example *Board notifications*), and note its number.
2. Create an organisation team for the editorial board (for example
   `@example-instance/editorial`) and add the Board members to it. A team,
   never a person: the channel must keep working when any one volunteer
   stops reading.
3. Ask each member to watch the thread, so GitHub emails them its comments.

**Secrets to set:** `CONVENER_NOTIFY_THREAD` (the issue number) and
`CONVENER_NOTIFY_MENTION` (the team handle, `@org/team`).

**What travels:** record identifiers (`spk-014`), stored calendar days,
`nomination N` labels and the four fixed step names. No speaker name, email
address, affiliation, country, talk title or board login is ever included —
`tools/convener_ops/notify.py` reads none of those fields.

**To verify:** run `cd tools && uv run convener-check-config`; *Board
notifications* moves from `absent` to `production`. Run
`uv run convener-notify-digest --dry-run` to read the day's message without
sending anything.

## Event registration keys

**Without it:** there is no fallback, and this row means something
different from every other one on this page. A registration page cannot
encrypt without the event's *public* half, and a job cannot decrypt without
its *private* half — and unlike an absent SMTP host or an absent meeting
token, there is no degraded mode a missing key falls back to. The job that
would decrypt an event's registrations exits in error instead, rather than
writing personal data to disk unencrypted for want of a key. See
`tools/convener_ops/eventkeys.py` for the full reasoning, including why this is
the one place in this codebase where an absent integration (D-13) is not
treated as a normal state.

**To create:** for each event that will take registrations, generate a
fresh key pair (`convener_ops.eventkeys.generate()`) — never reuse one event's
pair for another, since a per-event key that read another event's data
would not be a per-event key at all.

1. Commit the public half as `keys/events/<event id>.pub`. This is not a
   secret: it is what lets the static registration page encrypt in the
   browser without asking a server for anything first.
2. Store the private half as the repository secret named by
   `convener_ops.eventkeys.secret_name(event_id)` -- **not** simply the event id
   uppercased: GitHub Actions secret names may only contain letters, digits
   and underscore, but an event id may legally contain `.` and `-` (the
   tests' own canonical id, `mrg-042`, does), so `secret_name` folds both to
   `_` before uppercasing. Never commit the private half, never write it to
   a file outside a CI job's environment, and never let it appear in a job
   log.

**Secrets to set:** `CONVENER_EVENT_KEY_<EVENT ID>`, one per event, set only for
as long as that event's registrations need decrypting.

**To verify:** run `cd tools && uv run convener-check-config`; *Event
registration encryption* is always reported `absent` here, on every
machine, because the declared name is a pattern (`CONVENER_EVENT_KEY_<ID>`) and
not a literal secret — the real per-event check happens inside the job that
decrypts that event's registrations, not in this general-purpose report.
The row is marked `(not a normal absence -- see below)` and the report's
closing line names it explicitly, because — unlike the other five rows —
this absence is not a harmless fallback (`absent_is_normal: false` in
`config/integrations.yml`).

**Destroying a key:** at the end of an event's retention window (see the
phase 4 spec, §4), remove `CONVENER_EVENT_KEY_<EVENT ID>` from the repository's
secrets. The encrypted registrations already committed under
`data/events/<event id>/` stay in git, with no history rewrite, and become
permanently unreadable the moment the secret is gone — nothing else needs
to happen to the repository itself. Record the destruction
(`convener_ops.eventkeys.destroy`) so the register can tell "destroyed on purpose" apart
from "this event never had a key" two years from now — the two look
identical from the repository alone, and only the register carries the
difference. A scheduled retention workflow (see phase 4) is meant to wire
this up so removing the secret and recording the destruction happen
together; done by hand, it is these two steps, always together, in that
order.

## Handling a registration

**Without it:** the signup relay (see *Signup relay* above) has nowhere to
send the `registration-submitted` dispatch it produces; the encrypted
envelope it forwards is simply never turned into a stored registration.
There is no D-13 fallback here for the same reason there is none for the
event key itself — this is the one place the ciphertext a participant sent
is ever read.

*Handle registration* (`.github/workflows/registration.yml`) runs on that
dispatch and does exactly two things: it decrypts, and it re-encrypts —
`tools/convener_ops/registration.py`'s module docstring explains why the stored
file (`data/events/<event id>/registrations.enc`) holds one independent
hybrid envelope per registration rather than one for the whole event, and
what that costs and buys. The plaintext never touches disk, a log, or
standard output at any point; a test
(`tools/tests/test_registration.py`, `tools/tests/test_cli.py`) pins that
directly by asserting no submitted name or address appears anywhere the
job prints, on both the success and the failure paths.

The job runs in two steps because of a GitHub Actions constraint, not a
design preference: a workflow can only select *which* repository secret a
step reads through an expression evaluated in the workflow file itself
(`secrets[...]`), and that expression cannot be computed from inside the
step whose `env:` it appears in. So the first step
(`convener-registration-secret-name`) reads only the event id out of the
dispatch payload and hands back the *name* of that event's key secret
(`convener_ops.eventkeys.secret_name`) as a step output — never the key itself
— for the second step's `env:` to look up by
(`secrets[steps.resolve.outputs.secret_name]`). An event with no such
secret set resolves to an empty string, exactly like a literal
`secrets.SOME_NAME` reference to a secret that does not exist, and the
second step treats that the same way `tools/convener_ops/eventkeys.py` says an
absent event key must be treated: the job exits in error rather than doing
anything with the ciphertext it was handed.

Two registrations landing at the same moment are the ordinary case here,
not an edge case — every submission dispatches its own workflow run, with
no batching. The workflow declares `concurrency: { group:
registration-handler, queue: max }` so that runs queue and execute one at
a time rather than racing to decrypt, update and push against the same
file; without `queue: max`, GitHub Actions' own default (`queue: single`)
keeps only the most recently queued run in a group and silently cancels
any others still waiting behind whichever run is in progress, which would
drop a registration outright rather than merely delay it.

**To verify:** submit the registration form for an event with a published
key (see *Signup relay* above); *Handle registration* runs, and
`data/events/<event id>/registrations.enc` gains one entry. Submitting
again with the same address updates that same entry rather than adding a
second one.

## Registration matching salt

**Without it:** `tools/convener_ops/registration.py::matching_code` returns
nothing — no matching code is derived, printed anywhere, or included in
the confirmation email a registration triggers (see task 7). Attendance
matching falls back to the address-and-name cascade the phase 4 spec
describes (§5) instead of the typed code. This is an ordinary D-13
absence: nothing here fails closed, because that cascade is a documented,
working fallback, not personal data landing somewhere it should not — see
`config/integrations.yml`'s own comment on why this row exists at all
despite that.

**Why a secret, and not a constant:** the matching code has to prove that
whoever typed it into a meeting platform's display name actually holds our
confirmation email for that address. A code anyone could derive from an
address alone — the way it would be if the salt were a literal string in
the source — proves nothing at all; it would be exactly as guessable by
someone who never registered as by the person who did.

**To create:** generate a long random string once (for example `openssl
rand -base64 32`) and set it as the repository secret below. It is not
per-event — one value salts every event's matching codes — and it must
never change once registrations exist under it: changing it would silently
change every already-issued code, so a resend of the confirmation email
(which recomputes the code rather than storing it) would no longer match
what the participant was already told.

**Secrets to set:** `CONVENER_MATCHING_SALT`.

**To verify:** run `cd tools && uv run convener-check-config`; *Registration
matching salt* moves from `absent` to `production`.

## CI-only secrets

These gate GitHub Actions workflow behaviour rather than anything the
application itself reads, so they never appear in `convener-check-config` (see
the note at the top of this document) — but a successor inheriting this
repository still needs to know they exist and where they live.

- **`TALLY_WEBHOOK_SECRET`** — verifies that a `proposal-submitted`
  `repository_dispatch` reaching *Handle proposal*
  (`.github/workflows/candidate-form.yml`) really came from the public
  Tally form and not a forged request. Without this repository secret set,
  that Actions-side check is skipped and any dispatch is accepted (D-13:
  an absent integration is a normal state, not an error) — the Worker's
  own copy of the same secret has no such fallback and refuses every
  request outright without it, because the Worker is the one thing
  standing between this whole chain and the public internet, while the
  Actions side only ever sees what the Worker already let through. Set as
  a repository secret; its value is the signing secret Tally shows when
  the webhook is configured. The same value is also set as a Wrangler
  secret on `services/form-relay/` (see *Form relay* above), which checks
  this signature first, before it ever sends the dispatch this workflow
  reads.
- **`VITRINE_DEPLOY_TOKEN`** — a fine-grained personal access token,
  scoped to the separate `example-instance/example-showcase` repository
  (contents: read & write only), that both *Publish vitrine data*
  (`.github/workflows/publish-vitrine.yml`) and *Deploy app*
  (`.github/workflows/deploy.yml`) use to push into it — the public events
  feed under `src/_data/`, and, since the app is now published through
  this same repository (see *Publishing the application (GitHub Pages)*
  above), the built application under `app/`. It is no longer only the
  events feed at stake: without it,
  *Deploy app* still logs a message and exits cleanly rather than failing
  loudly, but nothing is pushed anywhere and there is no fallback
  publishing route, so there is no site at all. Set as a repository secret
  on `example-cockpit`.
- **`CLOUDFLARE_API_TOKEN`** — already introduced above under
  *Authentication relay*: used by *Deploy auth relay* to deploy the
  worker in `services/auth-proxy/`, by *Deploy form relay* to deploy
  `services/form-relay/`, and by *Deploy signup relay* to deploy
  `services/signup-relay/` — all three to the same account. Listed again
  here because it is the same kind of CI-only, cross-account credential as
  the other two.

## Inactivity (G-09)

A Board member who has cast no ballot for `inactivity_months` stops counting
toward the vote threshold. Nothing about this happens on its own.

The window is **twelve months** (decision G-09), set in `data/config.yml`.
The series runs roughly monthly, so six months of silence is an ordinary
heavy year, a sabbatical or a period of leave; twelve is long enough that a
proposal cannot be triggered by accident, which matters because every line
the rule prints names a real volunteer.

`tools/convener_ops/sweep.py::sweep_inactive_members` computes the proposal — the
config as it would read, and one line per member naming the date of their
last ballot — and **no command applies it**.

Detection is the half the scheduled task operates. Every `convener-sweep` run ends
by printing whatever the rule has to propose, after the `scheduled →
delivered` and vote-window lines and whether or not those changed anything
(each proposal is one line; it is wrapped here to fit the page):

```
Board inactivity (G-09) - proposed, not applied; a human decides:
  - <login>: no ballot since <date>; proposed inactive so the threshold stops
    counting the seat - the seat is kept, the annual meeting decides, and one
    word in config.yml undoes it
```

Nothing is printed when the rule has nothing to propose, which is the live
case today (see the first of the three points below). The proposed config the
rule returns is discarded on the spot: `convener-sweep` writes `data/speakers.yml`
and never `data/config.yml`, and what it writes is byte-for-byte the same
whether or not there were proposals to print. A scheduled job with nobody's
name on it must not be able to change a volunteer's standing overnight — the
same reason a vote window that runs out parks a lead rather than declining it.
Applying the proposal is a human act on the Board screen, or a hand edit to
`data/config.yml`, and the annual meeting is what settles the question.

`inactive` is not a departure and not a judgement. The entry stays in the
file with its `login` and `joined_on` intact; the seat is kept; the only
effect is that the member leaves the denominator `N`, so a Board that has
really been four for a year stops needing four voices to agree. Coming back
is the same one word changed back to `active`, and a member re-seated
through a nomination is reactivated in place rather than added twice.

Three things the rule will not do:

- name anyone whose record cannot say when the silence began. Every
  `joined_on` in `data/config.yml` is empty today, so on the live data the
  proposal is empty — by design, not by accident. Step 3 of the September
  list below is what ends that, and until it is done this rule cannot say
  anything at all.
- name a member who declared an absence covering today, or one carrying a
  nomination the Board has not settled. Either of those is a live question
  already.
- take the Board below three members able to vote (decision G-03). Members
  it holds back for that reason still appear in the output, so the meeting
  reads the same list either way. The floor is three, never `board_min`: a
  rule that removes members must not be free to take the Board past the
  point where it can decide anything, including the decision to let those
  members go, and `board_min` is a target rather than a rule (see
  *The Board's target size* below).

## The Board's target size

`board_min` is a **target**, not a rule. No code refuses anything because the
Board is short of it: a nomination may be opened
(`app/src/state/board.ts::nominationBlocker`), a candidate may be seated
(`resolveNominations`), a vote may be decided, and the inactivity rule uses
its own floor of three. The reason is that every act a Board below its target
could be refused is an act that would bring it back up — refusing them would
lock the shortfall in.

`board_max` is the opposite: it is enforced at the moment of seating, a
candidate who does not fit becomes `waiting`, and a file above the ceiling is
one the app could not have written, so `convener-validate` rejects it.

A target nobody states is a decoration, so it is reported in two places, and
in both directions rather than only on bad news:

- the Board screen, under the composition table — *4 active members, below
  the board's target of 5* — or *5 active members. The board aims for 5 and
  seats at most 9.*
- `convener-validate`, as a `Note:` line printed alongside its verdict. It does
  not add to the errors and does not change the exit code; a target that
  could fail a run would be a rule wearing a softer word.

## The one-shot scripts

`scripts/migrate_v3.py` and `scripts/open_vote_window.py` have both already
run, and their effects are committed. They are kept, separately, and neither
is deleted nor merged into the other.

Kept, because each is the record of what was done to the data on a day
nobody will remember. Both are pure functions with a `main()` that reads,
transforms and writes, both are idempotent, and each has a test file that
pins, field by field, what it touched and — more usefully — what it left
alone: `tools/tests/test_migrate_v3.py` and
`tools/tests/test_open_vote_window.py`. Deleting the scripts would leave the
two commits that changed every record in `data/speakers.yml` with no
statement of what they changed.

Separate, because they are two decisions taken for two reasons. The
migration moved every record to schema v3; the backfill stamped
`selection.opened_on` on the leads so the board had a window to vote in.
Merging them would fuse two acts into one file, and with them the two
"nothing else was touched" proofs, which are per-act or they prove nothing.
It would also make re-running the migration re-apply a backfill that was
never part of it. This repository's argument throughout is that the history
is the record; merging two executed records is rewriting one of them.

Neither should be run again. If a third one-shot is ever needed, it is a
third script with a third test, not an edit to either of these.

## Reading the register (decision commits)

There is no database. The commit history is where a decision's author and
date survive, so the app writes a fixed line for every act the Board takes:

```
data: <act> <record> by <login>
data: <act> <record> by <login> (<qualifier>)
```

for example `data: record a ballot on spk-007 by ada (recused)`,
`data: reopen the vote on spk-012 by grace`, or
`data: settle the nomination of erin by ada`. The acts are a closed
list (`tools/convener_ops/commit_format.py`, mirrored in
`app/src/state/decisions.ts`), each naming a record rather than a person,
and the qualifier is closed per act. So the register can be read back with
`git log --format=%s -- data/` and filtered on one act, and no line in it
can say anything about a volunteer beyond which record they touched.

Ordinary commits -- code, docs, the nightly sweep, the public form -- are
not decisions and follow no such shape. The `Commit messages` step of the
`python` CI job checks only the commits under review, and only those that
open with one of the acts above; it also refuses an attribution trailer in
any message.

## After the September collaborators' meeting

Three changes to the governance data are deliberately deferred until the
collaborators' meeting in September. They are a deferred configuration in
the sense of decision D-13 — the state below is normal and expected, not a
defect to be rediscovered and not something to fix piecemeal beforehand.
All three touch `data/config.yml`, the first two `data/speakers.yml` as
well, and they are easiest done together, in one commit, with
`cd tools && uv run convener-validate` run before it is pushed.

**What this costs until then:** the Board is declared as five members while
only four people sit on it (see step 2), so the threshold — two thirds of
the eligible board, rounded up — is four, and only four people ever vote.
A lead therefore needs every available voice to be approved: effective
unanimity. This is a known, accepted, temporary state.

### 1. Replace the Board identifiers with real GitHub logins

`data/config.yml` currently lists the Board as `Anonymous`, `Anonymous`,
`Anonymous`, `Anonymous` and `Anonymous`. Only `Anonymous` is a GitHub login; the
other four are first names. Role detection matches the signed-in GitHub
account against these values, so today it recognises nobody but that one
account — every other member is treated as a visitor.

Collect each member's GitHub login at the meeting, then rewrite both files
in step:

1. `data/config.yml` — every `board[].login`.
2. `data/speakers.yml` — every `selection.ballots[].voter`, using exactly
   the same mapping. The ballots carry the same first-name identifiers, and
   a vote is tallied only from ballots whose voter is on the Board
   (`tools/convener_ops/governance.py`), so a Board renamed on its own would
   silently discard every vote cast so far.

Nothing else in `data/speakers.yml` holds a Board identifier today:
`assigned_to` and `publication.approved_by` are empty everywhere, and
`host_1` and `host_2` hold people's display names, which are not logins and
must not be rewritten. Check that this is still true before starting.

`convener-validate` reports any voter you miss as `ballot from a non-member`.

### 2. Merge the duplicate member and lower `board_min`

`Anonymous` and `Anonymous` are the same person, recorded twice. Delete one of
the two entries, keeping that person's real GitHub login. The Board then
goes from five members to four, and the threshold from four to three.

`board_min` is `5` in `data/config.yml` and should become `3` in the same
change — not because anything breaks otherwise, but because it is the
Board's stated target and the Board is choosing a new one. Nothing fails if
you forget: `convener-validate` prints `board has 4 active members, below its
target of 5 (board_min)` and still exits `0`. The count is of *active*
members: an entry marked `inactive` stays in the file, keeps its `login` and
`joined_on`, and does not occupy a seat. Three is also the floor set by
decision G-03 — a vote is suspended rather than decided below three eligible
members — so a target below three would be a target the Board could meet
and still not be able to decide anything.

Rewrite the ballots of whichever identifier disappears to the surviving
one. If any lead ends up with two ballots from the merged person, keep one:
one person casts one voice, and a repeated voter is a validation error.
No lead carries ballots from both identifiers at the time of writing —
`Anonymous` has never voted — but confirm it rather than assume it.

### 3. Fill in `joined_on` for every Board member

Every `board[].joined_on` in `data/config.yml` is the empty string. The
field is what the inactivity rule measures silence from: with no start
date there is no window to count, so the rule proposes nobody and will go
on proposing nobody for as long as the field stays empty. It is not a rule
that has been switched off — it runs nightly, reads every member, and
declines to name anyone, which reads exactly like a Board where everybody
has voted recently.

Ask each member at the meeting when they joined and record it as
`YYYY-MM-DD`. An approximate month is better than an empty field, because
the window the rule counts is twelve months long and a proposal is only
ever a prompt for the annual meeting to consider — nothing is applied
automatically. Do not fill these in from guesswork beforehand: a date
nobody confirmed would start a silence the member never had.

Once the dates are in, run `cd tools && uv run convener-sweep` and read what it
prints under `Board inactivity (G-09)`. Nothing there is applied; it is the
list the meeting discusses.
