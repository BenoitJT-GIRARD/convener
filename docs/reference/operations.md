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
4. Write the published form's own address into `config/instance.json` as
   `identity.proposal_form`. This is the half a reader sees: the showcase's
   `/propose/` page links it, and it is the only way a visitor reaches the
   form the three steps above just built. Until it is written, that page
   says the form is not open yet and offers the contact address instead —
   a placeholder (`REPLACE`) is read as *not configured*, never published
   as a link (`published.py::Identity.proposal_form_url`).

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

It also answers `POST /survey`, the post-event survey's own
intake — the same worker, not a fourth one; see its
README's "A second route, not a second worker" section for why, and for the
separate KV counter and rate-limiter key that route gets so a flooded
survey cannot spend, or be blocked by, a registration's own budget. Nothing
here needs a second deployment, a second variable or a second secret: it is
the same `VITE_SIGNUP_RELAY_URL`, with `/survey` appended by
`SurveyForm.tsx` itself.

**`/survey` also checks the survey switch
itself.** It first fetched `SURVEY_STATUS_URL`, a plain deployed
example-showcase page; that gave way to a read of this
repository's own `public-data/survey-status.json` through the GitHub
Contents API — the same `CONVENER_DISPATCH_TOKEN` credential and the same call
shape the relay already spends one read of for `keys/events/<id>.pub` —
because the deployed URL pointed at a site that had never actually been
built, and made the relay's own answer lag the handler's by a build cycle
it had no reason to inherit on top of the handler's own. There is no
`wrangler.toml` var for this any more: the repository and the token cover
both reads.

`public-data/survey-status.json` is still built by
`convener-survey-status-public-data` (`deploy.yml`'s own "Build survey status"
step, alongside "Build public data") and still baked into the app's own
built output by `app/scripts/copy-survey-status.mjs` for the *page* to
fetch (a static page has no token and cannot read the Contents API any
other way) — but it is also committed back to this
repository by `deploy.yml`'s own "Commit survey status" step, which is
what makes the relay's own Contents-API read possible at all. This is one
of three layers now (the page, the relay, and the CI handler each check
independently, the relay now reading this repository's own committed
copy rather than a deployed one); see *Draining the submission queue*
below, and `tools/convener_ops/submission_queue.py`'s own module docstring, for
why one alone was not enough.

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
the registration form for an event with a published key; the worker answers
`204`. **What happens next depends on how far away the seminar is**, and both
outcomes are correct:

- **More than `queue_beyond_hours` away** (`config/registration-lanes.yml`): the
  worker writes the encrypted envelope to the `submission-queue` branch and
  starts nothing. The confirmation goes out on the next daily drain, from the
  scheduled *Sweep and notify the board* run. Seeing no workflow run at all is
  the expected result here, not a failure.
- **Closer than that**: the `registration-submitted` dispatch goes out exactly
  as it always did, and *Handle registration* runs within the minute.

The threshold is held above a floor derived from the drain's own cron, so a
queued registration always has its room link before the seminar starts even if a
scheduled run is dropped. Anything the worker cannot resolve — an unreadable
routing file, an unknown event, a network failure — **dispatches immediately**
rather than queuing: the confirmation is the only channel the room link and the
matching code ever travel on, so doubt resolves towards sending it now.

**If the board says "registrations are no longer being queued".** That
fallback is right for the participant and invisible by construction: nothing
is lost, nobody waits, the queue simply stays empty — which looks exactly
like a quiet day while every registration bills a run again. The daily
*Sweep and notify the board* run therefore recomputes what
`public-data/registration-routing.json` should hold, from `data/speakers.yml`
and `config/registration-lanes.yml`, and compares it with the committed file
over the events a registration arriving today could still be queued for. A
file that is missing, unreadable, carrying an unknown version, or wrong about
one of those events turns the job red and posts to the board's thread naming
the events affected.

**The fix is always the same, and it is a deployment rather than an
edit:** that file is regenerated and committed by *Deploy app*, which
ignores `config/**` and is not started by the pushes this repository's own
jobs make — so nothing heals it on its own. Run *Deploy app* from the
Actions tab (`workflow_dispatch`) and the next daily run goes quiet. Two
consequences worth knowing before you go looking for a data problem: editing
`config/registration-lanes.yml` changes every cutoff and starts nothing, and
a file untouched for a month is perfectly healthy as long as it still names
every event that is open for registration — the alarm is about what the file
can still route, never about its age. A season with no upcoming event is
silent, because there is nothing to route.

## Publishing the showcase and the application (GitHub Pages)

**Without it:** nothing else is affected here — this is how both public
surfaces are published, not an optional integration.

**To create:** nothing, on this repository — Pages is not enabled here.
`example-cockpit` stays private (see *Before anything else* above), and GitHub
Pages will not serve a private repository without a paid plan, which the
project's no-cost constraint rules out.

Pages is instead enabled on the separate, public repository the built
site is pushed into — `config/instance.json`'s `published_url` says which
one, and nothing names it a second time
(`published.Published.publish_repository` derives it, and both publishing
workflows read that): Settings → Pages → Source =
*Deploy from a branch*, branch `main`, folder `/ (root)`. `example-showcase`
used to hold the showcase's own Eleventy templates directly, and
that repository's own `build.yml` published them to a `gh-pages` branch —
one this *Source* setting above was never configured to serve (see *Not
currently reachable*, below, for what that broke). Those
templates live in this repository now, under `site/` (D-15: private source,
public artefact), so `example-showcase` is now **purely generated** — every
byte there is reproducible from this repository, nothing hand-edited —
and retired `example-showcase`'s own `build.yml` along with them: two workflows
*here* now own the whole of `example-showcase`'s root between them, each
touching only its own disjoint subtree. *Publish vitrine*
(`.github/workflows/publish-vitrine.yml`) builds `site/` and pushes the
result to that root, `.nojekyll` included (`site/src/.nojekyll`, carried
through the build as a passthrough copy) — the file that stops GitHub
Pages falling back to rendering the repository's own `README.md` instead
of the real `index.html` now sitting there. *Deploy app*
(`.github/workflows/deploy.yml`) builds `app/` and pushes it into that
same root, under `app/`, unchanged from before. Neither workflow reads
what the other last wrote; each simply refuses to touch it.

Once published, the four public addresses are:

```
https://<owner>.github.io/<repository>/               the showcase
https://<owner>.github.io/<repository>/events/<id>/   one page per event
https://<owner>.github.io/<repository>/app/           the cockpit
https://<owner>.github.io/<repository>/verify/        certificate verification
```

`<owner>` and `<repository>` are not a placeholder anybody fills in by
hand: they are the two halves of `config/instance.json`'s own
`published_url`, which is where this project says once what address it is
published at.

Every path either build emits carries that prefix baked in at build time
— `site/.eleventy.js` reads it through `site/scripts/published.cjs` for
the showcase, `app/vite.config.ts`'s own
`base` for the application — bound by `tools/tests/test_site.py` to the
same two addresses `tools/convener_ops/registration.py::SIGNUP_BASE` and
`tools/convener_ops/certificate.py::VERIFICATION_BASE` already pin, so the
four cannot silently drift apart (D-14, applied to this one more
boundary). **A build served from a bare `localhost` root is not a preview
of this — it is a different topology** (D-26): the same test suite that
binds the four addresses together also asserts that a root-relative path
breaks at a bare root on purpose, which is why *Local preview*
(`site/README.md`) is a convenience for editing content, never a
rehearsal for how a page actually resolves once published.

This route, and not a third-party static host, because it adds no account.
A paid plan was already ruled out by the no-cost constraint; a third-party
host such as Netlify or Cloudflare Pages would still need its own account,
which is one more account somebody has to own, and the project's
constraints already forbid resting on any one collaborator's goodwill or
position. `example-showcase` costs nothing new to add: it already exists, under
the same organisation.

**Also needs correcting, outside this repository:** the GitHub App's homepage URL
(the organisation's Settings → Developer settings → GitHub Apps → the app
registered above under *Authentication relay*) still reads
`.../example-cockpit/`. Point it at the address above instead. This is a
setting, not code — no test, no CI job and no type will ever notice it
drifting, so this paragraph is the only mechanism that gets it corrected.

**To verify:** push to `main`; both *Publish vitrine* and *Deploy app* end
green, and the showcase and the cockpit answer at the addresses above.

**Not currently reachable.** No remote is connected to this repository
yet — nothing has ever been pushed to GitHub, so every gate on this page has been verified by reproducing its
command locally, never by a real deployment, and the honest current state
is that none of the four addresses above answers anything today. Two
things are worth keeping separate once a push does happen:

- `VITRINE_DEPLOY_TOKEN` unset is D-13's ordinary "absent is normal"
  state: both *Publish vitrine* and *Deploy app* log a message and exit
  cleanly at their first push step, rather than failing loudly, and simply
  push nothing.
- Independently of that, a review found a second, real
  problem, live at the time it was checked: a `curl -I` against the
  showcase's address returned `200`, but from GitHub Pages' own Jekyll
  rendering of `example-showcase`'s `README.md` (`<meta name="generator"
  content="Jekyll v3.10.0">`) — no `index.html` had ever reached that
  repository's root — and the application and the showcase's own
  stylesheet both `404`d. That was the two-`build.yml` conflict this
  section used to describe: `example-showcase`'s own build published to
  `gh-pages`, a branch the *Source* setting above does not serve. Moving
  the templates removes the cause rather than working around it, exactly as described
  above — but that removal has not yet been checked against a real
  deployment, so treat it as the most likely first thing to verify once
  this repository is finally connected to GitHub, not as settled.

## Content-Security-Policy and the security headers GitHub Pages cannot serve

**Without it:** nothing else is affected here either — this section
documents a fixed property of the hosting above, not an integration with
a state to degrade out of.

**The boundary, written down once so nobody meets it as a surprise.**
GitHub Pages serves every response with no headers of its own beyond the
bare minimum HTTP needs: no `X-Content-Type-Options`, no
`Permissions-Policy`, no HTTP Strict Transport Security, no
`Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy`/
`Cross-Origin-Resource-Policy`. None of the five is missing by omission —
there is no server on this project's side to configure, and Pages offers
no mechanism to add one. Adding one is not a task on a list; it is a
change of hosting provider, which the project's zero-cost, no-account
constraint rules out for the same reason the previous section already
ruled out a third-party static host.

The one thing this project *can* still ship is a Content-Security-Policy
carried by a `<meta http-equiv>` tag in each page's own `<head>` — the one
mechanism available with no server behind it. Exactly three directives
that would otherwise belong in the same policy do not survive that
delivery mechanism, by the CSP specification itself and not by an
oversight here — four tokens, since the reporting one is spelled two
ways:

- `frame-ancestors` is **ignored outright** when set by `<meta>` — nothing
  in this project can stop the showcase or the cockpit being framed by
  another site. This is the one clickjacking control the header form
  would have given and the `<meta>` form cannot.
- `sandbox` and `report-uri`/`report-to` are likewise specified to be
  ignored by a `<meta>`-delivered policy.

Naming any of the four above in the `<meta>` tag would not be a smaller
version of the real control — it would read as protection while doing
nothing, which is worse than the honest gap this section states instead.
`tools/tests/test_site.py::
test_content_security_policy_never_carries_a_directive_meta_delivery_ignores`
and `app/tests/csp.test.ts`'s own `'never carries a directive a <meta>
delivery ignores'` both fail the build the moment one of those four tokens
reaches either policy, so this stays true by construction, not only by
this paragraph.

**What does work by `<meta>` is everything else.** Those three are the
whole of the exception the specification names; `default-src`, `img-src`,
`style-src`, `font-src` and `base-uri` are delivered by a `<meta>` tag
exactly as `script-src` is. This section used to say instead that
“what does work by `<meta>`” *is* `script-src`, `connect-src`,
`object-src` and `form-action`, which read as the reason those four were
the whole of both policies — and it was not a reason. Neither policy had
a `default-src` or an `img-src`, so an image, a frame, a font, a
stylesheet, a media file or a worker was admitted from **any origin at
all**, on the public showcase and in the cockpit alike. That is closed;
what each policy now names, and what each name is justified by, is
written beside the directive in the two files themselves.

Two independent policies, one per document, built from what that document
actually loads rather than one policy loose enough to cover both:

- `site/src/_data/csp.js` — every page Eleventy builds (the showcase, and
  the registration, certificate-verification and post-event survey
  islands mounted on three of its pages — the last of them moved here from
  the cockpit). `default-src 'none'` with `script-src`,
  `style-src`, `img-src` and `font-src` all `'self'` — one stylesheet,
  three self-hosted woff2 faces and three island bundles are the whole of
  what these pages load — plus `base-uri 'none'`, `object-src 'none'`,
  `form-action 'self'`, and `connect-src 'self'` plus the signup relay's
  own origin (`VITE_SIGNUP_RELAY_URL`, the same repository variable
  *Signup relay* above already forwards into the application build —
  read here rather than hand-typed a second time) when one is
  configured.
- `app/scripts/csp.mjs` (injected into `app/index.html` by
  `app/vite.config.ts`'s own `cspHtmlPlugin`) — the operators' cockpit,
  gated on sign-in, and nothing else. The last
  public route this bundle carried (`/survey/:eventId`, the post-event
  survey) onto the island above, and `connect-src` dropped the signup
  relay's own origin as a direct consequence: nothing left in this
  bundle posts to it. `default-src 'none'` with `script-src`,
  `style-src`, `img-src` and `font-src` all `'self'` — one module
  script, one stylesheet, three woff2 faces and one SVG favicon are the
  whole of what this document loads — plus `base-uri 'none'`,
  `object-src 'none'`, `form-action 'self'`, and
  `connect-src 'self' https://api.github.com` plus the auth relay's own
  origin (`VITE_AUTH_PROXY_URL`), admitted only once its own variable is
  configured.

The two differ because the documents genuinely differ, not by oversight:
the showcase's pages never call the GitHub API or the authentication
relay, and the cockpit's own device sign-in and Contents-API calls have
no business in a policy served to an anonymous visitor of the showcase.

**The cockpit's development server carries a third, and it is deliberately
not the one that ships.** Vite runs `transformIndexHtml` for the
development server as well as for a build, so `npm run dev` was being
served the policy above — and `script-src 'self'` refuses
`@vitejs/plugin-react`'s React Refresh preamble, which is an *inline*
script the plugin writes into every served document. The cockpit's
development server therefore rendered a blank page from the day the policy
landed until somebody found it; the published
artefact was never affected, which is exactly why nobody met it. The
obvious remedy — not injecting the policy in development at all — was
rejected: it takes the policy out of the one environment where a
violation is actually read, so a developer would watch a third-party
image load in development and have it refused in production, where
nobody has a console open. `app/scripts/csp.mjs::devCspMetaContent`
derives a development-only policy from the shipped one instead, adding
`'unsafe-inline'` to `script-src` and `style-src` and nothing else — an
external script, a third-party image, a third-party font and a
connection to an origin the policy does not name are all still refused,
in front of the person who introduced them. `app/tests/csp.test.ts` holds both halves against the
real, committed configuration: the development document's own policy
admits the scripts that document actually contains, and the built
document carries neither an inline script nor an `'unsafe-inline'`.

**To verify:** build both `site/` and `app/`, serve the result under the
path prefix `config/instance.json` declares (D-26 — a bare `localhost`
root hides the path-prefix
class of defect this project has already paid for once), and read a real
browser's console on every page. `site/scripts/check-a11y.mjs` already
does the first two steps for every page this project publishes, in a
real, JavaScript-executing Chrome; a clean console on that same run is
this policy's own proof that legitimate content still loads under it. A
`javascript:` URI submitted through the public proposal intake
is exactly the kind of thing `script-src 'self'` refuses.

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
provider, granted after a manual request. The value to set is
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
journey line and the board notice that drive this are not wired up yet;
this section documents the procedure a volunteer, or whatever eventually
wires it, follows, and `tools/convener_ops/platform_fcc.py`'s module docstring
documents the same reasoning from the code's side.

**Two routes free the recording quota, never one.** The provider's free
tier is 1 GB; a 90-minute recording alone is roughly 1,645 MB, so freeing
the space after every event is a condition of operation, not an
optimisation. The hosting runbook's recording discipline —
recording started for the talk, stopped before the discussion, started
again for the discussion — means an event routinely produces **two**
recordings that both cost quota, and only one of them may ever be
converted to MP4. That is why there are two commands, not one, with
opposite guards, both structural rather than a convention a caller has to
remember:

**`convener-release-recording`** — for a talk headed to YouTube, only.
(`tools/convener_ops/cli.py::release_recording`, run through
`.github/workflows/recording.yml`.) Retrieves, verifies the retrieval,
then deletes, in that order. Before either trace is even checked, it
first refuses unless the speaker's own consent is on record:
`publication.consent` must be `"granted"` on the event's own speaker
record (`tools/convener_ops/cli.py::_consent_granted`) — **not**
`publication.outcome`, which the board's own, later `finalize-archive`
step writes and which governs a different question entirely (whether the
talk is *linked in the public feed*, not whether our copy may leave the
provider). An earlier version of this gate required both, modelled on
`tools/convener_ops/public_data.py::recording_withheld`; that was wrong,
because it held the quota hostage to the board's own timeline and refused
every fresh talk regardless of consent. `pending`, an unanswered field,
and any value this project does not recognise are all silence, and
silence is never a permission — a talk whose consent has not yet been
answered is refused the same as one that was declined; read the refusal
message and the record's own `publication.consent` value before deciding
whether to wait for an answer or to use `convener-discard-recording` instead.

The two-trace shape checked once consent is granted is a design ruling
— *who deletes the recording, and on what evidence* — carried into code
rather than restated anywhere it could drift from the code: it refuses to
delete unless both

1. the `delivered/recording-retrieved` step is ticked on the event's own
   `runbook_progress` — this has its own cockpit checkbox
   ("Recording retrieved and archived somewhere durable", first line of
   the Delivered — wrap-up journey, `app/src/state/phases.ts`); a
   volunteer without the app to hand can still set it directly on
   `data/speakers.yml`'s `runbook_progress` map, the same raw-YAML edit
   `youtube_url` itself already tolerates when set by hand. Ticked once
   the host has downloaded the recording and archived it somewhere
   durable, independent of whether it will ever be published — **not**
   `youtube_url`, which records where a *published*
   recording lives, is legitimately empty for one that never will be, and
   is read nowhere in this guard; and
2. the provider's own converted copy answers with `video/mp4` and
   `Accept-Ranges: bytes` — proof the host's Download click in
   FreeConferenceCall's own web interface already happened. Nothing in
   this codebase ever triggers that conversion itself; only the host's
   own click does.

**`convener-discard-recording`** — for the discussion segment, always, and for
a talk whose publication consent was withheld. (`tools/convener_ops/cli.py::discard_recording`,
run through `.github/workflows/discard-recording.yml`.) Neither of these
may ever be converted: the only way to satisfy trace 2 above is a
conversion, and a converted file stays *publicly reachable at its own URL
even after the conference itself is deleted* (verified empirically) —
never acceptable for content nobody agreed to publish. So this command
asks for no proof of retrieval at all, because for these two cases none
may ever exist without doing the exact harm the command exists to avoid.
Its guard is a **typed operator affirmation** instead: the
`confirm_discard` input must read exactly `discard <event_id>` (e.g.
`discard mrg-042`), the same "type the name to confirm" discipline a
repository-deletion page uses for its own irreversible action. It never
reads the retrieval tick above, and never accepts it as a substitute — a
ticked `delivered/recording-retrieved` cannot make this command decide
there is nothing to affirm. **Known limit:** typing the same wrong event
id into both `event_id` and `confirm_discard` satisfies the confirmation
on its own terms — a non-existent event is still caught (`convener_ops`'s own
existence and "has a recording" checks run regardless), but a typo that
happens to name a *different, real* recorded event is not. Read the event
id back before submitting.

**To run either:** trigger the matching workflow's `workflow_dispatch`,
supplying the event id and the FreeConferenceCall conference id (visible
in the conference's own URL inside FreeConferenceCall's web interface —
a numeric id, e.g. `618515381`); `discard-recording.yml` additionally
asks for the typed confirmation above. Running the wrong one for a
recording is not reversible: check which route an event's recording
needs *before* triggering either.

**Why both stay manual, per-event triggers, never a schedule.** Nothing
ties an event id to its FreeConferenceCall conference id anywhere in the
provider's documented or undocumented API in a way this project has been
able to verify (this project refused to build a resolver on the unverified
conference-listing endpoint, and that refusal was upheld on review). Until a verified way to
make that resolution exists, a human supplies the conference id by hand,
once, when running either workflow — so releasing or discarding a
recording remains a runbook step, not something this project promises to
do unattended. This does not fully close the "the quota problem is a
forgetting problem" risk the design ruling above names; it is a known,
disclosed limit, not an oversight.

## Outbound email

**Without it:** the registration confirmation is composed all the
same, and reported unsent — the job prints one line naming the event and
saying a confirmation could not be sent, never the composed message
itself. Nothing is silently dropped: the registration is already stored by
the time this step runs, so nothing here is the only copy of anything a
manual resend (below) cannot reproduce. **Reported, not retained.**
An earlier version of this row described the composed
message being written to a local file and uploaded as a 14-day, access-
controlled build artefact — that pattern is gone: `docs/governance/
traitement-donnees.md`'s own Recipients section named it a documented
exception to "a registration's plaintext exists only inside the job that
read it, for the length of that job's run", but with outbound email
unconfigured (this project's default state) it was the path every
registration took, not an exception. See
`tools/convener_ops/confirmation.py`'s module docstring for the full reasoning.

**To create:** an organisation mailbox reachable over SMTP (D-07's
arbitration: no external transactional-email service, no subscription).
Gmail and most providers want port `587` with STARTTLS; some want `465`
with implicit TLS instead — `tools/convener_ops/confirmation.py` picks between
the two from `CONVENER_SMTP_PORT` itself, so either works without a code change.

**Secrets to set:** `CONVENER_SMTP_HOST`, `CONVENER_SMTP_PORT`, `CONVENER_SMTP_USER`,
`CONVENER_SMTP_PASSWORD`, `CONVENER_SMTP_FROM`.

**To verify:** run `cd tools && uv run convener-check-config`; *Outbound email*
moves from `absent` to `production`.

**Manual resend:** the `Resend a registration confirmation` workflow
(`.github/workflows/resend-confirmation.yml`, `workflow_dispatch`) re-sends
the confirmation already on file for one event and address, without
regenerating anything — the matching code is a pure function of the event,
the address and `CONVENER_MATCHING_SALT`, so it is always exactly the code the
first message carried. Use it when a confirmation is reported missing;
the reasoning is that a certificate in the spam folder does not exist.

One exception to the no-personal-data-in-a-retained-surface rule above: an
address is still the only identifier for one registration
(`tools/convener_ops/registration.py`'s own module docstring), so a resend still
names one by address. **It never does so in the clear.**
`workflow_dispatch`'s own `encrypted_identifier` input carries that address
hybrid-encrypted under the event's own published public key, not the
address itself — produce it with:

```
cd tools && EVENT_ID=mrg-042 REGISTRATION_EMAIL=person@example.org \
  uv run convener-encrypt-identifier
```

which needs no secret (`keys/events/<id>.pub` is public data, not a
secret) and prints one line of ciphertext to paste into the workflow's own
form. GitHub still renders and retains a `workflow_dispatch` input's own
value on the run page for as long as the run's history exists, but what it
retains is now unreadable without this event's `EVENT_PRIVATE_KEY` — a
security-review fix closing what used to be a documented,
deliberate exception resting only on `workflow_dispatch` being restricted
to collaborators with repository write access.

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
still composed and printed to the *Sweep and notify the board* job log,
where any
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
2. Create an organisation team for the editorial board and add the Board
   members to it. Name it `editorial-board`: that slug is the one
   `app/src/auth/role.ts` asks GitHub about when it decides who signs in
   as a Board member, so a team under any other name leaves every member
   falling back to `data/config.yml` alone. The organisation is your own
   (`config/instance.json`'s `identity.repository`), so the handle reads
   `@<your-organisation>/editorial-board`. A team,
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

1. Store the private half as the repository secret named by
   `convener_ops.eventkeys.secret_name(event_id)` -- **not** simply the event id
   uppercased: GitHub Actions secret names may only contain letters, digits
   and underscore, but an event id may legally contain `.` and `-` (the
   tests' own canonical id, `mrg-042`, does), so `secret_name` folds both to
   `_` before uppercasing. Never commit the private half, never write it to
   a file outside a CI job's environment, and never let it appear in a job
   log.
2. Commit the public half as `keys/events/<event id>.pub`. This is not a
   secret: it is what lets the static registration page encrypt in the
   browser without asking a server for anything first.

**This order is load-bearing, not incidental.** Committing the public half
is what the signup relay checks before it will dispatch a submission at
all -- its "is this a known event" check (*Signup relay* above) -- and the
*private* half is what *Handle registration*'s job needs to ever read a
submission again. Publish the public half before the private secret
exists, and every registration accepted in that window is told "sent",
genuinely encrypted, and can never be decrypted again — the job that
would read it fails closed forever, not just until someone notices.
Setting the private secret first closes that window: the relay has
nothing to accept until step 2 opens it.

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

**Destroying a key:** at the end of an event's retention window,
remove `CONVENER_EVENT_KEY_<EVENT ID>` from the repository's
secrets. The encrypted registrations already committed under
`data/events/<event id>/` stay in git, with no history rewrite, and become
permanently unreadable the moment the secret is gone — nothing else needs
to happen to the repository itself. Record the destruction by running
`cd tools && DESTROYED_IDS=<event id> DESTROYED_ON=<YYYY-MM-DD> uv run
convener-record-destructions` so the register can tell "destroyed on purpose"
apart from "this event never had a key" two years from now — the two look
identical from the repository alone, and only the register carries the
difference. That same command also removes `keys/events/<event id>.pub`
once the registry write succeeds, so a destroyed event stops accepting new
registrations too — do not delete the `.pub` by hand first, or
`convener-record-destructions`' own guard (it refuses to record a destruction
for an id whose key was never published) will refuse the very destruction
it is meant to record. This happens automatically now — see *Retention and
early erasure*, below, for the scheduled workflow that removes the secret
and records the destruction together; done by hand instead, it is these
two steps, always together, in that order: remove the secret, then run
`convener-record-destructions`.

## Retention and early erasure

The retention sweep's own job, and this project's central promise — a key
destroyed 90 days after its event, making that event's registrations
permanently unreadable — carried out automatically, on a schedule, and
proved by a test (`tools/tests/test_retention.py`,
`test_after_the_key_is_destroyed_the_ciphertext_is_unreadable_forever`).

**This same destruction also covers
`data/events/<id>/survey-responses.enc`, the post-event survey's own
storage (§6) — with no change to this job at all.** `CONVENER_EVENT_KEY_<ID>`
is the one key both files are encrypted under; deleting the secret makes
both permanently unreadable in the same one operation. There is no second
retention path to remember, because none was built: the survey deliberately
did not create a second thing to destroy.

**`.github/workflows/retention.yml`** runs daily and on demand
(`workflow_dispatch`, no inputs). Each run: computes which events'
90-day windows have elapsed (`convener_ops.eventkeys.is_due_for_destruction`,
measured against `convener_ops.governance.paris_today` — never a raw clock
read); deletes each one's `CONVENER_EVENT_KEY_<EVENT ID>` secret (`gh secret
delete`, converging on the secret being *absent* regardless of that
command's own exit code — a secret already gone from a previous, partial
run is success, not failure); and records every destruction it actually
carried out (`convener-record-destructions`, reading `DESTROYED_IDS` and
`DESTROYED_ON`) in `data/event-key-destructions.yml`, the registry
`convener_ops.eventkeys.key_status` reads to tell "destroyed on purpose" apart
from "this event never had a key". That same step also removes the
event's `keys/events/<id>.pub` once the registry write succeeds, so a
destroyed event stops accepting new registrations too — the signup relay
has no other way to know an event has closed. Once that commit actually
pushes, the same step dispatches `deploy.yml`:
the commit itself lands with `GITHUB_TOKEN`, which never starts
a new workflow run on its own, so without this the deployed app bundle —
built from `copy-event-keys.mjs`'s own copy of `keys/events/` — would
keep serving a destroyed event's public key until some unrelated push to
`main` happened to rebuild it, the same suppression trap the certificate
workflows already dispatch around. `publish-vitrine.yml` is dispatched
alongside it for consistency with those workflows, though it watches
neither path this job changes and runs as a no-op. One event failing to
delete does not stop the run from still recording and closing every
other event due the same day; the job still ends red if anything failed.
A day nothing is due is an ordinary, green run that changes nothing. A
speaker record this job cannot find, or cannot read a date from, is
skipped rather than failing the run (one bad record must not block every
other event's own deadline) but is reported with an `::warning::`
annotation in the run's own summary, not merely on stderr, precisely so
that skip does not look identical to a genuinely quiet day.

**GitHub disables `schedule:` triggers in a repository with no activity
for 60 days.** That is a platform behaviour, not specific to this job,
but it matters most here: a job whose entire purpose is *not being
remembered* is exactly the one an operator will not notice has stopped
running. There is no automated way around this at zero cost; the mitigation
is procedural — if in doubt, open this workflow's own Actions history and
check its last run date, and use `workflow_dispatch` to run it by hand,
the same manual catch-up any other scheduled job in this project uses.

**`CONVENER_RETENTION_TOKEN` — the one credential this whole job depends on,
and its absence is deliberately not an ordinary D-13 state.**
Deleting a repository secret needs a credential `GITHUB_TOKEN` does not
carry, no matter what `permissions:` a workflow grants it — so this is a
**fine-grained personal access token, scoped to this repository, with
the "Secrets" repository permission set to Read and write, and nothing
else** (the same "one narrow scope, nothing more" shape
`VITRINE_DEPLOY_TOKEN` already uses for a different repository — see *CI-only
secrets*, below — except this one *is* declared in
`config/integrations.yml`, because its absence is not ordinary noise:
`convener-check-config` reports it, exactly like `CONVENER_EVENT_KEY_<ID>`, marked
"not a normal absence"). Free — a personal access token costs nothing —
so the zero-cost constraint holds.

**Without it, `convener-retention-sweep` fails the job outright, on every
scheduled run, whether or not any event is actually due for destruction
that day.** This is deliberate, and the strongest exception to D-13 in
this project: every other missing integration degrades to "a feature is
quietly unavailable"; this one does not, because a retention job that
exits green having destroyed nothing looks, from the Actions tab,
identical to one that genuinely had nothing to do — and the two must
never be confused for a promise with legal weight. A red job every day
until the token is set is the correct pressure. **To create one:** on
GitHub, Settings → Developer settings → Personal access tokens →
Fine-grained tokens → generate one scoped only to this repository, with
only the Secrets permission, set to read and write; paste the value into
this repository's own `CONVENER_RETENTION_TOKEN` secret.

**Early erasure**, the other right (erasure before the retention
deadline): a participant's own registration removed from
`registrations.enc` before
the retention window ends, without touching any other registrant's own
entry (`convener_ops.registration.erase`). Run
**`.github/workflows/erase-registration.yml`** by hand
(`workflow_dispatch`) with the event id and, **preferred**, the matching
code from the participant's own confirmation e-mail (`convener_ops.registration
.find_by_matching_code` recomputes and compares it — nothing on our side
ever stores it). The e-mail address is accepted as a **documented,
deliberate fallback** for someone who no longer has that e-mail —
the same exception *Outbound email*'s own "Manual resend" section above
already makes for `convener-resend-confirmation`'s `encrypted_identifier`
input. As with that input, `erase-registration.yml`'s own
`encrypted_identifier` field never carries the address itself: encrypt it
first with `convener-encrypt-identifier` (see "Manual resend" above for the
exact command), and paste the resulting ciphertext. `workflow_dispatch`
is still restricted to collaborators with repository write access, but
this fallback's safety no longer depends on that boundary — a security
review fix that closes what this exception used to
accept as an open, permanent, plaintext copy of the address it exists to
erase.

**Once an event's key is destroyed, there is nothing left to erase, and
this is provable rather than merely asserted.**
`convener-erase-registration` checks `data/event-key-destructions.yml` first —
before asking for a private key at all — and, if the event is already on
record as destroyed, prints the destruction date and exits cleanly: the
request is already satisfied. If `EVENT_PRIVATE_KEY` is supplied anyway
for an event on record as destroyed, this refuses loudly instead: a key
that still opens `registrations.enc` contradicts the registry, and that
contradiction must never pass silently in the one command whose whole job
is to prove there is nothing left.

**There is no equivalent early-erasure command for one person's own survey
responses, and this is a recorded gap, not an oversight.** A survey
response (`tools/convener_ops/survey.py`) carries no name and no address — see
that module's own docstring, "Why no identity travels with a response" —
so nothing stored there can be matched back to a specific participant the
way `convener-erase-registration` matches a registration by matching code or
address. The only lever an operator has for "erase this event's survey
answers before the retention deadline" is the same lever that erases its
registrations: destroying `CONVENER_EVENT_KEY_<ID>` early, which erases both
files together, not one response on its own.

**Dropping one response by hand is possible, without erasing the rest —
`survey.py`'s own module docstring names the property, this is the
procedure.** `data/events/<id>/survey-responses.enc` holds one JSON object
per response under its top-level `"responses"` array
(`tools/convener_ops/survey.py::ResponseFile`), each entry an independent
hybrid-encrypted envelope with its own AES key and nonce — removing one
array element and committing the result touches nothing else in the file,
byte for byte, the same guarantee `convener-erase-registration` relies
on for `registrations.enc`. There is no CLI command for this today (fair
warning: a response cannot be *identified* by anything short of decrypting
it, since none carries a name, address or matching code), so it is a
by-hand edit: open the file, decrypt each entry with the event's
`CONVENER_EVENT_KEY_<ID>` to find the one in question, delete that one JSON
object from the array, and commit. Do this only for a request an operator
can otherwise be confident about — there is no automated verification step
standing between a hand edit and the committed file the way there is for
`convener-erase-registration`.

**Anonymous against a stranger; pseudonymous by metadata against the
organiser — stated honestly, not fixed further, because fixing it further
would cost more than the risk.** A stored entry is
exactly `{v, encrypted_key, iv, ciphertext}`; the decrypted plaintext is
exactly `{overall_rating, recommend, feedback}`, padded to a fixed size
before encryption so the ciphertext's length no longer reveals how much a
participant wrote. Against a stranger without the event's private key,
that is complete: there is nothing else on the entry to read. Against the
organiser — who holds the key, and is the only party for whom anonymity is
a promise rather than a mathematical certainty — one channel remains
outside the encryption on purpose: arrival time. This used to be
sharp — `.github/workflows/survey.yml` committed once per response, at the
wall-clock minute it arrived, so array position N in
`survey-responses.enc` was paired with a timestamp permanently in the git
history, and "the one who answered at 19:04" was a workable handle for
whoever also held the attendance list.

**The submission queue blunted it as a side effect of something else.** The daily drain
(*Draining the submission queue*, below) writes every response that
arrived since the last drain in *one* commit, so what the history now
pairs with array position N is the drain's own run, not the participant's
own minute — every response in a day's batch shares one timestamp. The
channel is narrowed to "which day", not closed: the queue branch's own
commits, while an entry is waiting, still carry the minute it was written,
and anyone with access to that branch's history can read them. This was
not the reason for the change and should not be relied on as a control;
it is recorded because a later reader comparing this paragraph to the git
history would otherwise find it wrong. Whoever next writes anything that
treats these responses as anonymous to
the organiser specifically, should read this paragraph first.

## Certificate signing key

**Do not confuse this with *Event registration keys* above.** That key
*encrypts* a registration so only we can read it; this one *signs* a
certificate so a stranger can confirm it came from us — attesting, not
concealing. The two also run opposite lifecycles: an event key is destroyed
at the end of retention; this one is never destroyed, because a certificate
must still verify however long after it was issued someone checks it. See
`tools/convener_ops/signing.py`'s module docstring for the full reasoning behind
both differences, and for why the padding scheme, key size and wire format
were each chosen the way they were.

**Without it:** no certificate is issued. The job that would sign one
(`tools/convener_ops/certificate.py`) cannot, and stops there —
nothing partially written, nothing sensitive exposed. Unlike *Event
registration keys*, this is an ordinary D-13 absence: there is no
confidentiality risk a missing signing key could expose, only a feature
(certificates) that does not run this time.

**To create:** a human operator runs `convener_ops.signing.generate()`
themselves, interactively, on their own machine — a Python shell is
enough (`cd tools && uv run python`, then `from convener_ops.signing import
generate; private_pem, public_pem = generate()`). **Not an automated
step, and not something to delegate to an agent or a CI job:** this mints
the one key that every future certificate depends on, and it is minted
exactly once, deliberately, by someone who then holds the only copy of
its private half until it is pasted into GitHub Secrets and never printed
or saved again. There is exactly one of these in service at a time —
unlike an event key, this is not per-event.

1. Commit the public half as `keys/signing/<YYYY-MM-DD>.pub`, dated the day
   it was generated (`convener_ops.signing.public_key_path`). This is not a
   secret: it is what lets a public verification page confirm a
   certificate offline, with no request to us at all. `keys/signing/`
   holds a `README.md` describing this layout even when the directory is
   otherwise empty — an empty directory there is the normal state before
   the first key is ever generated, not a sign of anything missing.
2. Store the private half as the repository secret `CONVENER_SIGNING_KEY`, by
   pasting it directly from the terminal into the GitHub Secrets UI.
   **Never write it to a file, anywhere, at any point** — not a temporary
   one, not a `.gitignore`'d one, not a CI job's workspace. Once it is
   pasted in and the operator has confirmed the paste, close the terminal
   that generated it; nothing else should retain a copy. Never commit it,
   and never let it appear in a job log.

**This order is load-bearing, the same way it is for an event key:**
publish the public half before the private secret exists. Setting the
secret first would let a job sign a certificate under a key nobody can yet
verify against — the opposite failure of the event-key case (there, the
danger is accepting a registration nothing can ever decrypt), but the same
shaped bug, and the same fix: publish, then enable signing.

**Rotating a key:** generating a new pair and publishing its public half
(steps 1 and 2 above) does not, by itself, retire the old one — the old
private half stays `CONVENER_SIGNING_KEY`'s value until it is deliberately
replaced. Once it is, the certificates already signed under it keep
verifying: `convener_ops.signing.verify` is handed every published
`keys/signing/*.pub`, not only the one currently in service, and tries each
in turn (see the module docstring's "how a verifier chooses" section for
the recommended, but not required, newest-first order). **Never remove a
`.pub` file from `keys/signing/`** — doing so is exactly what would make an
already-issued certificate stop verifying, the one outcome §7 of the phase
4 spec exists to prevent. Do not generate two signing keys on the same
calendar day: the filename collides (see the module docstring).

**Secrets to set:** `CONVENER_SIGNING_KEY`.

**To verify:** run `cd tools && uv run convener-check-config`; *Certificate
signing key* moves from `absent` to `production`.

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
anything with the ciphertext it was handed. That second step also decrypts,
stores *and* commits — one step, not two, because the commit has to sit
inside the same retry loop as the decrypt (below), and a step boundary
cannot sit inside a loop.

Two registrations landing at the same moment are the ordinary case here,
not an edge case — every submission dispatches its own workflow run, with
no batching. The workflow declares `concurrency: { group:
registration-<event id>, queue: max }`, one group *per event*, so that
runs for the same event queue and execute one at a time rather than racing
to decrypt, update and push against the same file; without `queue: max`,
GitHub Actions' own default (`queue: single`) keeps only the most recently
queued run in a group and cancels any others still waiting behind
whichever run is in progress, which would drop a registration outright
rather than merely delay it. `queue: max` itself still caps a group at 100
pending runs and cancels anything past that — at the signup relay's own
per-event burst limit (30/minute) and roughly a minute per run, a sustained
blast against one event can approach that ceiling within several minutes;
scoping the group per event at least keeps that from starving every other
event's queue as well.

Serialising the runs is necessary but not sufficient on its own —
`actions/checkout` with no `ref:` reads the exact commit
`repository_dispatch` pinned at the moment the event was created
(`github.sha`), not the branch's current tip, so a run queued *because*
`queue: max` is working still starts from a tree that predates whatever the
run ahead of it in the same queue just pushed. The workflow checks out
`github.event.repository.default_branch` explicitly instead, so a queued
run always reads what the run before it actually wrote.

That leaves the case `queue: max` cannot remove on its own: two different
events' runs (different concurrency groups, so nothing serialises them)
racing to push, or a run for the same event slipping in from outside the
queue (a manual retry, for instance). A rejected push does **not** retry
with `git pull --rebase`: rebasing a JSON array whose closing lines both
commits rewrote reliably conflicts, and a conflicted rebase leaves the tree
mid-merge with nothing committed — the registration is gone, not merely
delayed. Instead the job fetches the branch tip, hard-resets to it,
**re-runs the handler**, and recommits: `convener_ops.registration.upsert` is
idempotent on the same address, so replaying it against the tree the other
push just produced reproduces this registration's own entry (under a fresh
AES key and nonce — encryption is never literally deterministic — but the
same logical content) beside whatever the other push added, rather than
asking git to merge two edits to one array by hand. Bounded at three
attempts, the same as `candidate-form.yml`'s own retry loop.

**To verify:** submit the registration form for an event with a published
key (see *Signup relay* above); *Handle registration* runs, and
`data/events/<event id>/registrations.enc` gains one entry. Submitting
again with the same address updates that same entry rather than adding a
second one. Submitting for two different addresses to the same event in
quick succession — the case the retry loop exists for — leaves both.

## Draining the submission queue

**Without it:** the signup relay's `/survey` route (see *Signup relay*
above) writes each encrypted envelope to the queue branch and nothing ever
picks it up. Responses accumulate on a branch nobody looks at, the
submitters were all told `204`, and no badge anywhere turns red. The
queue watchdog exists for exactly that silence.

**Where the queue is.** A branch of this repository called
`submission-queue`, one file per submission at
`queue/survey/<entry id>.json` holding the relay's request body byte for
byte. `tools/convener_ops/submission_queue.py` names the branch, and
`.github/workflows/sweep-and-notify.yml` and
`services/signup-relay/src/index.js` mirror that name; a test fails if
they drift apart.

A **branch**, never a path on `main`: `register.yml`, `quality.yml` and
`security.yml` start on any commit to the default branch with no path
filter at all, and `deploy.yml` filters with `paths-ignore`, so a queue
file on `main` would bill at least five runs per submission — the exact
inverse of the point. The relay writes with its own token rather than a
job's `GITHUB_TOKEN`, so GitHub's recursion guard does not save it; what
does is that nothing triggers on a push to a branch other than `main`,
which `tools/tests/test_workflows.py` holds over the whole workflow
directory.

> **Never open a pull request from `submission-queue`.** Six workflows
> trigger on `pull_request`, but four of them filter on paths a `queue/**`
> file does not match; `quality.yml` and `security.yml` do not filter at
> all. One open pull request whose head is that branch would therefore
> start **two workflows — six billed jobs — on every single submission**,
> six times what the queue replaced. No offline test can see whether such a pull request
> exists. What is held instead is the consequence one step later:
> `tools/tests/test_submission_queue.py` fails if a queue file ever
> reaches a checkout of the default branch, so merging one is red rather
> than silent.

**What drains it.** Four steps at the bottom of *Sweep and notify the
board*'s own `daily` job — never a workflow or a job of their own, which
would cost a billed run every day and defeat the purpose. They fetch the
queue branch into the runner's temporary directory (never into the
checkout), plan, drain, and clear:

1. the **plan** step names the event key secrets the drain will need. It is
   separate because of a GitHub Actions constraint every event-key job here
   already meets: a secret can only be selected by an expression in the
   workflow file, reading a previous step's output.
2. the **drain** step decrypts, checks each event's survey switch,
   validates and re-encrypts every waiting response into
   `data/events/<event id>/survey-responses.enc`
   (`tools/convener_ops/survey.py`) — one independent envelope per response,
   appended, never matched to an existing entry, because nothing about a
   response identifies who submitted it (see `survey.py`, "Why no identity
   travels with a response"). It commits **the responses and
   `data/queue-ledger.yml` together, in one commit**, and pushes.
3. the **clear** step removes what was handled from the queue branch,
   **only after that push succeeded**.
4. the last step turns the job red if anything is still waiting.

**That order is the whole of "nothing is lost".** An interruption between
the commit and the clear leaves entries in the queue that
`data/queue-ledger.yml` already records as handled, so tomorrow's drain
clears them without applying them twice. The reverse order would lose a
submission outright and no ledger could recover it.

**`data/queue-ledger.yml`** holds the entry names a drain has applied, and
nothing else — an entry name is a timestamp and a uuid, never anything a
participant wrote. It does not grow without bound: an id is forgotten by
the first drain that sees the entry is no longer in the queue.

**Eight events per drain, and why there is a number at all.** A response
can only be decrypted with its own event's key, and each key needs an
expression written out in the workflow file, so the count of events one
drain can cover is however many of those lines exist —
`submission_queue.MAX_EVENTS_PER_DRAIN`, currently 8, pinned to the YAML
by a test. A ninth event with responses waiting is **deferred**: its
entries stay in the queue, the job goes red, and the next drain takes
them. Nothing is dropped. If this ever bites, raise the constant and add
the matching pair of lines in the same change.

**Red is for the operator, never for a stranger.** A *deferral* — a key
nobody configured, a committed responses file nobody can parse, more open
events than slots — fails the job, because every one of those is
something only the operator can fix and every one leaves a submission
waiting indefinitely. A *refusal* — an envelope that will not decrypt, a
survey closed between the submission and the drain — is annotated and
counted but does not decide the colour of the run: anyone who can reach
the relay could otherwise keep this job red at will and train you to
ignore it.

**Why the proposal form is not on this queue.** It receives Tally's
webhook body, and that body is *plaintext*: a name, an address, an
institution, an abstract. Queuing it would write a stranger's personal
data into this repository's history in the clear, where D-22's key
destruction — which is what makes every other stored submission
unreadable — has no purchase at all, and it would keep a copy of
proposals the Board declined and deleted from `data/speakers.yml`.
`.github/workflows/candidate-form.yml` therefore still handles one
proposal per run. Changing that is a decision about personal data, not a
refactor.

**The survey switch is checked before anything is decrypted or written —
and this is the third of three checks, not the
only one.** `services/signup-relay`'s own known-event check once
proved only that an event's public key existed, never that its organiser
turned the survey on, and neither `SurveyForm.tsx` nor the relay had any
way to know the switch existed at all (`survey_enabled` is `NEVER_PUBLISHED`
on both languages' own consent classification, so a static page had no
file to read it from). The consequence was concrete, not theoretical: every
one of the 31 live records shipped with the switch off, so *every*
submission this pipeline could receive followed the one path that did
check — the participant was thanked, the relay answered `204`, and the
answer was discarded here, silently, with nobody told. Now the page checks
first (never offering the form), the relay checks second (refusing the
queue write, see *Signup relay* above), and the drain still checks a third
time, reading the event's speaker record
(`survey_enabled`, `data/speakers.yml`) itself, because it is the only one
of the three reading the authoritative file rather than a possibly
momentarily stale, published copy of it. There is no D-13 fallback here at
any of the three layers: a switch that is off is the ordinary state for
most events, but a *response arriving* for one is not something this job
may quietly discard by writing nothing and exiting clean — an unexplained
green run that stored nothing would be indistinguishable from an ordinary
day, and this is a case worth an operator's attention. It is
one of the drain's *refusals*: annotated on the run by entry id and
reason, cleared from the queue (it will not become true by waiting, and an
entry that waits for ever is a queue that never empties), and deliberately
not a red job — see *Draining the submission queue* above for why a
stranger must not get to decide the colour of that run.

There is no step sending a confirmation, unlike registration's own
workflow: nothing is returned to a participant for answering a survey.
That is precisely why the survey could be moved to the slowest cadence
with no trade-off at all, and why registration could not.

**To verify:** with an event's `survey_enabled` set to `true` in
`data/speakers.yml` — the "Post-event survey" checkbox in the cockpit
(`AdminOverride.tsx`) — submit the survey form
(`/survey/<event id>/` on the vitrine, its own island). **Nothing runs at
that moment, and that is the change:** a file
appears under `queue/survey/` on the `submission-queue` branch. Run *Sweep
and notify the board* by hand (`workflow_dispatch`) rather than waiting
for 05:00 UTC, and `data/events/<event id>/survey-responses.enc` gains one
entry while the queue file disappears. Submitting again adds a second,
independent entry — this is by design, not a defect; see `survey.py`'s own
docstring. With `survey_enabled` left `false` (the default for every
event), the submission is refused by the relay before it
is ever queued, and no file is written at all.

**Toggling that checkbox is not immediately live for a participant:**
`data/speakers.yml` is the authoritative record
the drain reads, but `SurveyForm.tsx` and the signup
relay both read `survey-status.json` instead (see *Signup relay* above),
which only reflects a new checkbox state once *Deploy app* next builds and
commits it. A board member who ticks the box expecting the survey page to
open immediately will see it stay closed until that build finishes — the
handler itself would already refuse the response either way, so this is a
UX lag, not a security gap, but it is worth saying to whoever flips the
switch expecting it to take effect at once.

## Registration matching salt

**Without it:** `tools/convener_ops/registration.py::matching_code` returns
nothing — no matching code is derived, printed anywhere, or included in
the confirmation email a registration triggers. Attendance
matching falls back to the address-and-name cascade instead of the typed
code. This is an ordinary D-13
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

This same secret has a second consumer: `tools/convener_ops/
certificate.py::fingerprint`, the certificate register's own salted trace
of an address. That is a second reason never to rotate it once any event's
register exists, not merely the first — rotating it would also change
every past attendee's fingerprint, so `convener-issue-certificates`' own
idempotent lookup would stop finding any of them and mint each a second
certificate on its next run. See `certificate.py`'s own module docstring,
"the fingerprint is reversible, given the salt", for the reasoning in
full, including what to do instead if this secret ever leaks.

**Secrets to set:** `CONVENER_MATCHING_SALT`.

**To verify:** run `cd tools && uv run convener-check-config`; *Registration
matching salt* moves from `absent` to `production`.

## Encrypting the manual attendance export

For an event using the manual implementation (no `CONVENER_MEETING_API_TOKEN`
configured), the host's own attendance export never reaches continuous
integration in the clear -- personal data must not, and `.gitignore` keeps
`data/events/<event id>/attendance-import.csv` out of every checkout on
purpose. `convener-encrypt-attendance-export`
(`tools/convener_ops/cli.py::encrypt_attendance_export`) is the step that
closes that gap:

1. Download the attendance export from the meeting platform, saving it
   locally as `data/events/<event id>/attendance-import.csv` (never
   committed).
2. Run, on your own machine, no CI job and no secret needed: `cd tools &&
   EVENT_ID=<event id> uv run convener-encrypt-attendance-export`. This reads
   only the event's already-published public key
   (`keys/events/<event id>.pub`) and the plaintext file above, and writes
   `data/events/<event id>/attendance-import.csv.enc` -- one independent
   `eventkeys` envelope per attendance row (the same
   per-record shape `registrations.enc` and `survey-responses.enc` already
   use, not one envelope for the whole file), safe to commit: the public
   key that produced it cannot decrypt any of it back. Running this again
   against a changed local export overwrites the committed file with
   whatever the plaintext currently says -- printing "replacing the
   already-committed ..." when it does, since there is no date or content
   comparison behind that write, so re-run it deliberately, not out of
   habit.
3. Commit and push `attendance-import.csv.enc`. `convener-match-attendance` and
   `convener-issue-certificates`, run in CI, decrypt it with
   `EVENT_PRIVATE_KEY` -- the same secret they already read to decrypt
   `registrations.enc` -- the moment it is checked out.

Never runs against the private key, and cannot: `EVENT_PRIVATE_KEY` is not
among the environment variables this command reads at all. If both the
encrypted and the plaintext export happen to sit on disk at once (a stray
leftover from local testing), the encrypted one is read and the plaintext
one is ignored.

**This is a journey step, not only a command.** It has
a line on the event's own runbook -- "Attendance export encrypted
and committed" (`app/src/state/phases.ts`, `delivered/attendance-export-
encrypted`), right beside "Recording retrieved and archived somewhere
durable" -- and a matching checklist line in
[Phase 4 -- After the webinar](../workflow/4-after.md), so an operator
meets this step without needing to already know this command exists.
Issuing certificates re-reads whatever is committed here, so nothing
downstream can proceed until this step is done.

## Matching attendance

`convener-match-attendance` (`tools/convener_ops/cli.py::match_attendance`) reads one
event's stored registrations and its attendance export -- the platform's own
API, or, with no `CONVENER_MEETING_API_TOKEN` configured, the manual
implementation's attendance export -- and joins them through the
matching cascade (matching code, then address, then normalised
name). It is the diagnostic step an operator runs before issuing
certificates for an event: it reports only counts on stdout (matched,
unmatched, unreachable, rows read) and writes the host's short list of
ties and unmatched attendees to `unmatched-attendance.md`, at the
repository root -- `.gitignore`'d and never committed. `convener-issue-
certificates` (below) re-runs the same join internally and never reads
this file; it exists for a human to resolve an ambiguity by hand before
certificates are minted, not as an input to anything automated.

**`unmatched-attendance.md` names records, not people.**
An unmatched connection is listed by a salted record
identifier -- `registration.matching_code`, the identical shape a
registrant's own confirmation code already uses -- when
`CONVENER_MATCHING_SALT` is configured, or by its position in the list
otherwise; a tie the cascade refused to guess between is listed by each
candidate's own record identifier, never its address. An unreachable
connection (a telephone joiner: never host-resolvable regardless -- the
matching cascade's own boundary) collapses to one count-and-duration line, naming
nobody. This used to carry display names and addresses in the clear; the
fix is in `cli.py::UNMATCHED_ATTENDANCE`'s own comment.

Like every other command in this section, it needs `EVENT_PRIVATE_KEY` to
decrypt `registrations.enc` -- and per *Event registration keys* above, that
key "must never... be written to a file outside a CI job's environment", so
this command is not meant to be run against a real event from a laptop.
**Its own workflow makes it reachable** (`.github/workflows/
match-attendance.yml`) -- the same `workflow_dispatch`
shape `convener-issue-certificates`, `convener-reissue-certificate` and
`convener-revoke-certificate` below already use, with the same `event_id` and
optional `conference_id` inputs `convener-issue-certificates` and
`convener-invite-survey` take. Before this workflow existed, two other
workflows' own header comments told an operator to "run
`convener-match-attendance` by hand first" -- an instruction nobody could ever
actually follow, since the private key it needs never touches a laptop by
design; both headers now name this workflow instead.

`unmatched-attendance.md` -- the only artefact naming what could not be
matched, and the only place acceptance criterion 9's unmatched/unreachable
distinction ever reaches a human -- is uploaded by this workflow's own
last step as a short-retention (14 days), access-controlled build
artefact. That restriction is defence in depth now, not the reason the
file is safe: the file itself carries no name and no address any more
(see above).

**The manual implementation can be run against real attendance in CI**,
closing a gap this page used to record. Before that, with
no `CONVENER_MEETING_API_TOKEN`, the manual implementation looked only for
`data/events/<event id>/attendance-import.csv`, which `.gitignore` keeps
out of every checkout -- there was nowhere to run this command *from* that
could hold that file, and the resulting contradiction with acceptance
criterion 8 stood recorded until it was fixed.
`ManualPlatform.get_attendance` now reads
`data/events/<event id>/attendance-import.csv.enc` first: a host encrypts
the raw export under the event's own published public key with
`convener-encrypt-attendance-export` (needs no secret at all -- see *Event
registration keys* above for why the public half is not one) and commits
the result; a CI job holding this event's `EVENT_PRIVATE_KEY` -- the same
key it already reads to decrypt `registrations.enc` -- decrypts it the
moment it is checked out. `tools/tests/test_event_chain.py` drives the
real commands against exactly this shape and asserts the chain completes,
for the manual implementation. With a token configured, this
command populates `conference_ids` too, the same
`_conference_ids_from_env` resolution `convener-issue-certificates` and
`convener-reissue-certificate` below already share -- match-attendance.yml
gives it the same `conference_id` input those two workflows take, closing
the gap the paragraph above once left open. Left blank, the FCC path still
refuses cleanly with "no FCC conference is recorded for event ..." rather
than an unhandled traceback; that refusal is now reachable
by choice, not only by a workflow that could not have named the id at
all.

## Issuing, reissuing and revoking certificates

Three operator actions, three workflows, none scheduled: an operator
decides an event's attendance is settled and triggers each one by hand from
the Actions tab (`workflow_dispatch`). All three re-derive registrations and
attendance from scratch on every run, so a
corrected match recalculates without anybody re-registering, the same way
*Handling a registration* re-derives rather than trusts a prior run's own
answer, and all three commit straight to `data/events/<event
id>/certificates.yml` with the same re-derive-rather-than-rebase retry
*Handling a registration* uses for `registrations.enc` -- see that section
above for why a rejected push is never resolved with `git pull --rebase`
here either.

**The register is written here, at issuance, not after delivery.**
Generating the certificate, delivering it and
writing the register read as three steps in that order; in the code it is two
steps, because idempotence requires it. `convener-deliver-certificates` (below)
re-signs the identical token on every run without ever writing to the
register again, which is what lets a failed delivery be retried without
regenerating anything -- see `tools/tests/test_event_chain.py`'s own module
docstring for the fuller reasoning.

**No workflow input is ever an address.** A `workflow_dispatch` input is
rendered on its own run's page and retained for as long as that run's
history exists -- longer than the 14-day artefact this project uses
everywhere else it has to carry personal data at all, and exactly the
exposure this same document already names for the confirmation resend.
`convener-reissue-certificate` and `convener-revoke-certificate` both take a
certificate id instead: random, public by design, already printed on the
document and already published in `certificates-public.json`, so it names
exactly one certificate without naming a person.
`convener-reissue-certificate` resolves that id to a registration the same way
`convener_ops.certificate.issue` computes a fingerprint in the first place, run
in the other direction -- see that module's own docstring and
`convener_ops.cli.reissue_certificate`'s.

- **Issue certificates** (`.github/workflows/issue-certificates.yml`,
  `convener-issue-certificates`). Inputs: the event id, and, optionally, the
  FreeConferenceCall conference id -- the same
  input `recording.yml` already takes, needed only when
  `CONVENER_MEETING_API_TOKEN` is configured; the manual implementation never
  reads it. Signs a certificate for every currently eligible attendee not
  already on record (the eligibility threshold, computed the same way
  `convener-match-attendance` computes it), and commits the register only when
  at least one certificate was freshly minted. Reading `CONVENER_SIGNING_KEY`
  absent, or `CONVENER_MATCHING_SALT` absent, are both ordinary D-13 states --
  nothing issued, a clean exit -- the latter for a stronger reason than
  the former: `certificate.py`'s own module docstring explains why a
  certificate fingerprint may never be computed without a real salt, so
  an absent salt forbids writing rather than licensing an unsafe write.
  Nothing used to populate the FCC path's own `conference_ids`
  at all, so it could never issue a single certificate -- see that
  round's own report for the full finding.
- **Reissue a certificate** (`.github/workflows/reissue-certificate.yml`,
  `convener-reissue-certificate`). Inputs: the event id, the certificate id to
  correct, and the same optional conference id as above. An operator's
  deliberate action for one person, never a scheduled job -- reusing
  `convener-issue-certificates`'s own idempotent lookup for a correction would
  let a routine re-run silently resurrect it. Mints a fresh identifier and
  a fresh signed token, and refuses (without writing anything) unless the
  standing row for that id is already revoked.
- **Revoke a certificate** (`.github/workflows/revoke-certificate.yml`,
  `convener-revoke-certificate`). Inputs: the event id, and the certificate id
  to revoke. Flips one register row to `revoked` and nothing else -- no
  signing key or matching salt is read at all, because revocation touches
  only the register, never the token a revoked certificate's holder still
  carries (the signature stays valid -- it is the
  register that has the final say on state). Before this command existed,
  the only way to revoke a certificate was a
  hand edit of the committed-clear register, which this project's own
  standing constraint against depending on a collaborator's goodwill or
  their post rules out, and which made `certificate.revoke`'s own guard
  against naming an identifier that is not on record unreachable from a
  text editor -- the one place that mistake actually gets made.

All three share one `concurrency` group per event
(`certificates-<event id>`), the same reasoning `recording.yml` and
`discard-recording.yml` (*Meeting platform* above) already share one for
the FCC conference recording those two touch: all three read and write the
same `certificates.yml`, so a run mid-write must finish before another one
starts.

**Secrets read:** issuing and reissuing both read `CONVENER_EVENT_KEY_<EVENT
ID>` (via the same `convener-registration-secret-name` resolve step *Handling a
registration* uses), `CONVENER_SIGNING_KEY`, `CONVENER_MATCHING_SALT` and
`CONVENER_MEETING_API_TOKEN` -- none new; all four are already documented in
their own sections above. Revoking reads neither an event key nor either
certificate secret, exactly as its own bullet above says: revocation never
touches anything that would need one.

**How the public projection actually gets rebuilt.**
*Deploy app*'s own `push:` trigger only fires from an
event GitHub itself raises for the push -- and none of these three jobs'
own commits raise one: all three push with the checkout's default
`GITHUB_TOKEN`, and GitHub does not start a new workflow run from an
event triggered by that same token (the recursion guard). Each of the
three jobs dispatches *Deploy app* directly, as its own last step, with
`gh workflow run deploy.yml` -- `workflow_dispatch` is one of the
documented exceptions to the recursion guard, so the job's own
`GITHUB_TOKEN` is enough and no new secret is needed. The dispatch only
fires once a change was genuinely pushed, never on a run that wrote
nothing. *Deploy app*'s own "Build public data" step is what actually
rebuilds `certificates.json` inside the app's built `dist/` -- the file
`src/verify/register.ts` fetches -- so this dispatch, not a *Publish
vitrine data* one, is what a verifier's page depends on. These three jobs
used to *also* dispatch *Publish vitrine data* alongside it, but nothing
a certificate change writes ever touches `data/speakers.yml`, the only
input that workflow's own "Build public data" step turns into anything
it pushes -- so that second dispatch was always a no-op run there, never
a second publication anything depended on, and it was removed.

**To verify:** run one of the three workflows for a test event with a
published key and a settled attendance export; `data/events/<event
id>/certificates.yml` gains, changes or flips the state of one row, and
that same job's own dispatch step starts *Deploy app*, which republishes
`certificates.json` with the new state -- visible as a second, separate
workflow run on the Actions tab, started a few seconds after the first.

## Delivering a certificate

The rule on delivery is categorical: by e-mail, and a document
naming a person is never deposited in a repository. Two commands, one
workflow step and one standalone workflow.

- **Deliver certificates for this event** -- a step in
  `.github/workflows/issue-certificates.yml`, `convener-deliver-certificates`,
  running immediately after *Issue certificates* in the same job and the
  same checkout. Re-derives registrations, attendance and eligibility from
  scratch, exactly as *Issue certificates* does, and for each currently
  eligible attendee calls `certificate.issue` again -- idempotent, so this
  reproduces the identifier and signed token *Issue certificates* just
  wrote (or, on a re-run, whatever an earlier run already wrote) rather
  than minting anything new -- renders a self-contained HTML certificate
  with an inline SVG verification code, and e-mails it as an attachment.
  Never writes the rendered document anywhere.

  **Restricted by default to what this run's own issuance step just
  minted.** *Issue certificates* writes the freshly
  issued identifiers to `$GITHUB_OUTPUT` -- public by design, already
  printed on the document, already published in
  `certificates-public.json` -- and this step reads them as `DELIVER_ONLY`,
  skipping every attendee not in that set. A re-dispatch of this whole
  workflow after nothing changed therefore mails nobody a second time; a
  re-dispatch after a corrected attendance export mails only the newly
  corrected certificates. Ticking the workflow's own `resend_all` input
  overrides this for a deliberate batch retry (e.g. after fixing outbound
  mail), sending every currently eligible attendee's certificate again --
  a choice an operator makes, never the default. A failed send is reported
  by *identifier*, not only as a count ("N sent, M not sent, ... not
  sent: `<identifier>`, `<identifier>`"), so a single bounce can be named
  directly to *Deliver a certificate* below rather than recovered by
  re-running the batch that caused it. This step's own failure --
  including a transient platform error re-fetching attendance -- no longer
  marks the whole run red (`continue-on-error: true`):
  the certificates were already committed and pushed by the step
  before it, and that outcome should not be hidden behind a delivery
  hiccup.
- **Deliver a certificate** (`.github/workflows/deliver-certificate.yml`,
  `convener-deliver-certificate`). A manual resend for one certificate -- a
  certificate sitting unread in a spam folder does not exist any more
  than a registration confirmation does -- named
  by `CERTIFICATE_ID`, never an address, resolved to a registration the
  same fingerprint-reversal `convener-reissue-certificate` already uses (the
  two commands now share that resolution code). Inputs: the event id, the
  certificate id to resend, and the same optional conference id the other
  three certificate workflows take. Read-only: this workflow writes
  nothing and dispatches nothing, so its job needs only `contents: read`,
  unlike the three that write `certificates.yml`. Its own `concurrency`
  group is keyed on `certificate_id` alone, so two
  dispatches naming the *same* certificate serialise against each other
  (never two e-mails for one resend) while two dispatches naming different
  certificates still run in parallel. **Refuses a revoked certificate
  outright:** a certificate the register
  marks revoked is never delivered, by this command or the bulk one above,
  regardless of how it is invoked.

**Secrets read:** both read `CONVENER_EVENT_KEY_<EVENT ID>`, `CONVENER_SIGNING_KEY`,
`CONVENER_MATCHING_SALT` and `CONVENER_MEETING_API_TOKEN` -- the same four *Issuing,
reissuing and revoking certificates* already documents -- plus
`email_transport`'s five `CONVENER_SMTP_*` secrets (*Outbound email*, above),
read here for the first time by anything other than the registration
confirmation. Absent `email_transport` secrets are ordinary D-13 here too,
and degrade the same way the confirmation does:
nothing is ever written anywhere, not even to a private, short-
retention artefact -- see `tools/convener_ops/delivery.py`'s own module
docstring for why that would have been the wrong pattern here regardless,
for a signed, nominative document.

**Replayable, bounded by retention.** A failed or retried delivery
reproduces the byte-identical document -- `certificate.issue`'s own
idempotent lookup plus `signing.sign`'s determinism -- for as long as this
event's `registrations.enc` still exists. Once the retention sweep
destroys the event's key, 90 days after the event, there is no address
left to deliver to: the certificate still verifies, forever, but
`convener-deliver-certificate` refuses cleanly (the same "no registrations
recorded" message a missing file always gives) rather than pretending the
certificate itself has become invalid.

**To verify:** run *Deliver certificates for this event* for a test event
with at least one eligible attendee and `email_transport` configured; the
run's own summary line reports a sent count, and the configured mailbox
receives one message per eligible attendee, each carrying the certificate
as an HTML attachment. Run *Deliver a certificate* for one of the
identifiers `certificates-public.json` already lists to confirm the
resend path independently.

## Inviting the post-event survey

The rule is precise: optional, switched on per event, short,
sent afterwards, and only to people recognised as present. It splits
in two — `tools/convener_ops/survey.py` is the anonymous
storage side, already covered above under *Handling a survey response*;
`tools/convener_ops/survey_invite.py` (16b) is who gets asked, which needs an
identity to invite even though the answer it collects carries none.

**`.github/workflows/invite-survey.yml`**, `workflow_dispatch` only, never
scheduled and never triggered by a push — an invitation is an outbound
message to real people, the same reason `issue-certificates.yml` is
dispatch-only. Run `convener-match-attendance` by hand first to review the join
before inviting from it, exactly as *Issuing, reissuing and revoking
certificates* already recommends. Inputs: the event id, the same optional
FreeConferenceCall conference id every attendance-reading workflow already
takes, and `resend_all` (below).

**Only a *matched* attendee is invited** — a stored registration the
attendance cascade (`tools/convener_ops/attendance.py`) tied to a room
presence, `attendance.match`'s own `matched` outcome, never `eligible`
(the certificate-issuing duration threshold): the rule asks only
whether we recognised someone present, not whether they stayed long enough
to earn a certificate. Neither an **unmatched** attendee (present, but the
cascade could not tie the address it saw to any registration) nor an
**unreachable** one (joined by phone, no address on file, at any point) is
invited — not by policy, but by fact: neither has an address this pipeline
holds. See `tools/convener_ops/survey_invite.py`'s own module docstring,
"ruling 1", for the argument in full.

**The invitation carries no per-person token, on purpose.** Every matched
attendee of the same event receives the exact same link
(`/survey/<event id>/`, no query string), because a per-person token would
be an identifier — the one thing `survey.py`'s own storage design refuses
to let a stored response carry. The e-mail itself is an ordinary,
personally-addressed message (`Dear <first name>,`, sent to the address on
that participant's own registration) — nothing about *sending* it is
anonymous; only the *response* the link leads to is designed to be. See
[Survey invitation](../toolkit/emails/survey-invitation.md) for the exact
wording, and this document's own "Anonymous against a stranger;
pseudonymous by metadata against the organiser" section, above, for the
claim this page and that one must never overstate.

**A resend invites everyone again, by choice, not because a finer grain is
unsafe.** Unlike `issue-certificates.yml`'s own
`resend_all`, which restricts an ordinary run to what was freshly
minted and can name a single failed delivery by its certificate's own
public identifier, `convener-invite-survey` mints no identifier at all.
`data/survey-invitations.yml` records only that an event was invited, and
on what day — no name, no address, no count. By default, it refuses
outright once an event already has an entry there, printing that date and
sending nothing; the workflow's own `resend_all` input is the only
override, and it re-invites *every* currently matched attendee, including
everyone the first run already reached.

This is not forced by anonymity — a repository-only, salted delivery
record (the same construction `certificate.fingerprint` already uses)
would not compromise the survey response's own anonymity, since it would
never appear in the invitation, the survey page, or the response. The real
reason is proportionality: a certificate register earns its permanence
because a certificate is an attestation its holder may need verified years
later; an invitation record exists only to avoid mailing one person twice
inside a single campaign, a purpose whose useful life is days, not years —
and `data/survey-invitations.yml` is one file shared across every event,
so a per-person handle kept there would not be swept with any one event's
key at all, unlike `certificates.yml`, which already lives under
`data/events/<id>/`. `CONVENER_MATCHING_SALT` is also ordinary D-13 for this
command (unlike for certificate issuance), so such a handle could not
always be computed in the first place. See
`tools/convener_ops/survey_invite.py`'s own module docstring
for the argument in full.

**What actually reduces how often a bounce needs any recovery at all: an
in-run retry, which needs no identifier.**
`convener-invite-survey` retries one immediate resend, in the same run, for any
delivery that fails on its first attempt — a transient SMTP hiccup no
longer forces mailing a whole batch again. `resend_all` remains the
recovery for what that cannot fix (the mailbox was never configured, or
the run itself was never re-dispatched at all): the message carries no
attachment and no signed document, so a duplicate is a mild inconvenience,
not a second copy of anything sensitive loose in the world.

**Secrets read:** `CONVENER_EVENT_KEY_<EVENT ID>` and, optionally,
`CONVENER_MEETING_API_TOKEN` — the same two *Matching attendance* already
reads, for the identical reason (attendance is re-derived, never trusted
from a prior run) — plus `email_transport`'s five `CONVENER_SMTP_*` secrets
(*Outbound email*, above). `CONVENER_MATCHING_SALT` is read too, but absent is
ordinary D-13 here, unlike for certificate issuance: nothing this command
does fingerprints anything, so the attendance cascade simply falls
through to the address and name levels, its own documented fallback.
Absent `email_transport` secrets are ordinary D-13 as well: every attempt
is folded into a bare sent/not-sent count, and — like a certificate
delivery, unlike the registration confirmation — nothing is written
anywhere as a fallback, because there is no identifier here to keep an
unsent message filed against.

**To verify:** with a test event whose survey is enabled and at least one
matched attendee, dispatch *Invite the post-event survey*; the run's own
summary line reports a sent count, the configured mailbox receives one
message per matched attendee, and `data/survey-invitations.yml` gains one
entry. Re-dispatching the same event without `resend_all` sends nothing
further and says so.

**If the recording step's own commit-and-push retry loop ever exhausts its
three attempts** (`::error::push failed after 3 attempts -- the invitation
was sent but not recorded`), the invitation itself already went out — only
the record that stops a re-dispatch from doing it again did not land. This
is the one state where re-dispatching the workflow re-invites every
currently matched attendee, which is exactly what ruling 3's whole bound
exists to prevent. **Do not re-dispatch to recover from it.** Instead,
commit `data/survey-invitations.yml` by hand, adding this event's own
`event_id`/`invited_on` row (`convener-record-survey-invitation`, run locally
with `EVENT_ID` set, produces the exact row to add) — the same recovery a
wedged `retention_sweep` already documents for its own registry, applied
here to a smaller one.

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
  scoped to the separate published repository (contents: read & write
  only) — `config/instance.json`'s `published_url` says which one — that
  both *Publish vitrine*
  (`.github/workflows/publish-vitrine.yml`) and *Deploy app*
  (`.github/workflows/deploy.yml`) use to push into it — the built
  showcase at that repository's root, and the built cockpit application
  under `app/`, two disjoint subtrees each workflow only ever touches (see
  *Publishing the showcase and the application* above). Without it,
  neither workflow fails loudly: each logs a message and exits cleanly at
  its own first push step, but nothing is pushed anywhere and there is no
  fallback publishing route, so there is no public site at all. Set as a
  repository secret on `example-cockpit`.
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

**This never touches the person's real GitHub access, and that gap is a
security-relevant one — a manual step this rule does not take.** `inactive`
is a flag in `data/config.yml`; a security review's finding on
write access is about a live GitHub setting (Settings → Collaborators, or
whichever team grants access to this repository), which nothing in this
codebase reads or writes. A member marked `inactive` here — or one who has
left the Board entirely, replaced by a nomination — can keep full `Write`
collaborator access indefinitely unless a maintainer separately removes it.
That matters because `Write` is what lets a collaborator push a branch, add
a step to a workflow that reads a sensitive secret, and dispatch that
workflow against the branch — the exact path this project narrows
with `.github/workflows/secret-workflow-monitor.yml` (detection, not
prevention — prevention itself needs a paid tier this project does not
have). Every person who
keeps write after they stop being active is a needless widening of that
population, at zero benefit to anyone.

**The fix is a checklist item, run by hand, every time someone is marked
`inactive` here or otherwise leaves an active role:** remove or downgrade
their access under the organisation's collaborator settings, and remove
them from any GitHub team that grants access to `example-cockpit`. There is no
command for this and there should not be one. Automating it would need a
token with organisation-admin (or at least member-management) permission —
a credential that could add or remove *anyone's* access to *anything* the
organisation holds is a far more dangerous secret than anything this system
holds today, including `CONVENER_RETENTION_TOKEN`'s `Secrets: write` (see *CI-only
secrets*, below, and *Retention and early erasure*, above, for what that one
can already do). Building one to save a few minutes, a few times a year, is
the exact trade a security review already named as this project's
own recurring mistake: a credential that can do more than its job. A person
reading a short checklist is the right size of solution for a change this
infrequent.

**Who runs this checklist is not a free choice.** D-28 maps the architect
onto GitHub's own organisation-owner role, independent of Board
membership, and a Board member onto repository `Write` and nothing more
— the architect is the only account that actually holds the permission
this checklist needs, so the architect is who runs it. This is also the
bound that mapping puts on the write-access finding: not
closed, but limited to however long it takes the architect to work
through this checklist after someone's role changes.

Three things the rule will not do:

- name anyone whose record cannot say when the silence began. Every
  `joined_on` in `data/config.yml` is empty today, so on the live data the
  proposal is empty — by design, not by accident. *`joined_on`, empty
  everywhere* under **Deferred governance configuration** below is what
  ends that, and until it is done this rule cannot say anything at all.
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

## Settling the thresholds, and where the cockpit refuses

The cockpit's **Settings** screen is where the numbers in `config/` are
changed. It exists to *validate*, not to host: a file accepts whatever is
written into it and nothing looks at the value until a scheduled job runs on
it, whereas the screen computes each bound from the declarations it is
derived from and refuses at the point of entry, naming the bound and where
it comes from.

**One pair is coupled, and today it leaves exactly one legal value.**
`config/queue-drain.yml`'s `alarm_after_hours` is bounded on both sides:

- its **floor** is twice the drain's own cron period in
  `.github/workflows/sweep-and-notify.yml` (48 hours today) — an alarm that
  fires before a healthy drain has had its chance is an alarm people learn
  to ignore;
- its **ceiling** is `config/registration-lanes.yml`'s `queue_beyond_hours`
  minus the same margin (96 − 48 = 48 today) — later than that and the Board
  is told about a registration as its seminar begins.

Those two meet at 48, so raising `queue_beyond_hours` is the only thing that
buys the alarm any room, and lowering it towards its own floor makes the pair
impossible. The screen says so before anybody needs it, and refuses either
end. Editing the files by hand still works and is still checked, but only
later, by `tools/tests/test_queue_watch.py`.

**When a saved value starts being read is not "on save", and it differs per
value.** `.github/workflows/deploy.yml` ignores `config/**`, so a commit here
starts nothing at all:

| value | read by | live from |
|---|---|---|
| `alarm_after_hours`, all of `config/actions-budget.yml` | *Sweep and notify the board* | its next run |
| `config/queue-drain.yml`'s `max_silent_days` | *Retention liveness watchdog* | its next run |
| `queue_beyond_hours` | the signup relay, through `public-data/registration-routing.json` | the next run of *Deploy app*, which regenerates and commits that file |

Until *Deploy app* runs, a registration is routed on the threshold already
published in `public-data/registration-routing.json`. Run that workflow by
hand (`workflow_dispatch`) if the change is urgent; nothing is lost either
way, because a stale threshold only routes a registration to the wrong
*lane*.

**`config/instance.json` is reported there and never edited there.** The
address, the identity and the edition prefix are compiled into the built
cockpit and the built showcase, so a change takes effect at the next deploy
and not before — and the screen doing the editing is running on the previous
build. The edition prefix is frozen besides: it is in published addresses, on
issued certificates and in key filenames.

**A duplicate that has not edited it says so, on its own pages.** Every value
in `instances/example/config/instance.json` is invented and reserved — `.test`
addresses no registry will ever delegate (RFC 2606), a GitHub Pages host nobody
is asked to register, an organisation that does not exist — so a declaration
still
carrying one of them cannot be a coincidence. While any is left, the showcase
prints a band above its masthead on every page and the cockpit prints one
above its sign-in screen, both naming the exact keys still to fill in. Edit
them and rebuild, and the band disappears with no switch to find: nothing
turns it off but configuring the instance. `identity.proposal_form` is
deliberately not one of the triggers — a proposal form nobody has opened yet
is an ordinary state that degrades on `/propose/` itself, and a permanent
warning about it would be a warning people learn to ignore.

**The screen never accepts a secret**, and cannot: the cockpit is a static
bundle that writes with the signed-in person's own token, so a token able to
write a repository secret would be a right every Board member held. What it
does instead is *report* — for each row of `config/integrations.yml`, whether
the names it declares exist among this repository's Actions secrets and
variables, and what the code does without them. Names only; no endpoint
returns a secret's value, and the screen asks for none. Set them where this
document says: **Settings → Secrets and variables → Actions**.

## What the Actions runs cost, and the alarm before the budget runs out

Every minute figure written down anywhere in this project is a
`timeout-minutes` **ceiling**, not a measurement, because nothing here has
ever run on GitHub. Ceilings and real durations can differ by a large
factor in either direction, so no ceiling should ever be quoted as a
prediction.

`data/actions-usage.yml` is the one place a *measured* minute lives. The
daily job in `.github/workflows/sweep-and-notify.yml` reads the Actions API
for this repository's own runs over a rolling window, adds up what each one
actually billed, and commits the result. It is committed rather than
printed so that reading it takes opening this repository — no run log to
scroll, no CI required — and so that the file's own history is the trend.

Two things it can tell you that a ceiling cannot: what each half of the
budget really costs (the scheduled half, which does not move, against
pushes and public submissions, which do), and how many public submissions
arrived on the busiest single day.

**These figures are a lower bound on the bill, never the bill.** The free
monthly allowance belongs to the organisation that owns this repository and
is shared with every other private repository it owns. Reading the
organisation's real consumption needs an `admin:org` credential, which
nobody has created — and a control that cannot run without one is not a
control, so this deliberately measures what a repository token can see and
says so on every line it prints.

Two things it also cannot see: runs GitHub has already aged out of its own
retention, and any minute multiplier — everything here runs on
`ubuntu-latest`, whose multiplier is one, and the measurement raises its own
alarm rather than quietly mis-adding if that ever stops being true.

**When it goes off.** The thresholds are in `config/actions-budget.yml`,
with the reasoning for each written beside it; they are configuration
precisely because they are guesses until real durations exist, and they are
meant to be re-cut once this file holds a few weeks of them. Two of them
matter most: the rate at which the window projects past a share of the
monthly allowance, and the number of public submissions in a single day.
The second is the one that can break suddenly rather than drift — it is the
only item in the budget whose volume is decided by strangers, and the only
one that grows when the series succeeds.

When either fires, the daily job **goes red** and posts on the Board's own
thread (see *Board notifications* above — the same thread and the same team
mention, no second channel). It goes red whether or not that channel is
configured: an unconfigured integration must never be able to turn a real
finding into silence.

**If the alarm itself stops.** An exhausted minute budget does not fail
loudly; it simply stops work — which includes the very job this alarm lives
in. `retention-watchdog.yml`, on its own independent schedule, therefore
checks that `data/actions-usage.yml` is still moving, exactly as it already
checks `data/retention-last-run.yml`. What neither can catch is the whole
repository going dark at once, for the reason that workflow's own header
comment gives; what survives even that is the committed file, readable by
anyone who opens this repository.

**Running it by hand.** `convener-actions-usage-window` prints the window;
`convener-record-actions-usage` reads whatever the collector step left in
`actions-usage-input.jsonl` and writes the record;
`convener-check-actions-usage-liveness` is the watchdog's own question. Only the
workflow step between the first two touches the network — the arithmetic is
a pure function, and no test in this repository ever makes an API call.

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
## Deferred governance configuration

Three settings in the governance data are ordinarily left unfinished
until an instance's people are in a room together. They are a **deferred
configuration** in the sense of decision D-13 — the state below is normal
and expected, not a defect to be rediscovered and not something to fix
piecemeal by guessing. All three touch `data/config.yml`, the first two
`data/speakers.yml` as well, and they are easiest done together, in one
commit, with `cd tools && uv run convener-validate` run before it is
pushed.

**What each costs while it is deferred** is below with the change that
ends it. **Which of them a particular instance still owes** is that
instance's own business and is not recorded here: this page is the
product's, and a duplicate that read its predecessor's unfinished
business here would be reading somebody else's to-do list.

### 1. Board identifiers that are not GitHub logins

`data/config.yml` lists the Board, and each entry's `login` is meant to be
a GitHub login. Entries are often seeded with first names instead — the
file is the only place that says which is which. Role detection matches
the signed-in GitHub account against these values, so an entry that is not
a login recognises nobody, and that member is treated as a visitor.

Collect each member's GitHub login, then rewrite both files in step:

1. `data/config.yml` — every `board[].login`.
2. `data/speakers.yml` — every `selection.ballots[].voter`, using exactly
   the same mapping. A ballot on record carries whatever identifier was
   current when it was cast, and a vote is tallied only from ballots whose
   voter is on the Board (`tools/convener_ops/governance.py`), so a Board
   renamed on its own would silently discard every vote already cast.

Check before starting that nothing *else* in `data/speakers.yml` holds a
Board identifier: `assigned_to` and `publication.approved_by` do, when
they are filled in, and `host_1` and `host_2` hold people's display names,
which are not logins and must not be rewritten.

`convener-validate` reports any voter you miss as `ballot from a
non-member`.

### 2. A member recorded twice, and `board_min`

Step 1 is what makes a duplicate visible: one person seeded under a first
name and later added under their GitHub login is two entries until both
carry the same one. Delete one of them, keeping the real GitHub login, and
rewrite the ballots of whichever identifier disappears to the surviving
one. If any lead ends up with two ballots from the merged person, keep
one: one person casts one voice, and a repeated voter is a validation
error. Do not assume no lead carries ballots from both identifiers —
search `data/speakers.yml` for each of the two before you merge, and
confirm it.

`board_min` is the Board's stated target, and a Board that has just
changed size is choosing a new one. Nothing fails if you forget:
`convener-validate` prints `board has N active members, below its target
of M (board_min)` and still exits `0`. The count is of *active* members:
an entry marked `inactive` stays in the file, keeps its `login` and
`joined_on`, and does not occupy a seat. Three is the floor set by
decision G-03 — a vote is suspended rather than decided below three
eligible members — so a target below three would be a target the Board
could meet and still not be able to decide anything.

### 3. `joined_on`, empty everywhere

`board[].joined_on` is what the inactivity rule measures silence from:
with no start date there is no window to count, so the rule proposes
nobody and goes on proposing nobody for as long as the field stays empty.
It is not a rule that has been switched off — it runs nightly, reads every
member, and declines to name anyone, which reads exactly like a Board
where everybody has voted recently. **That is the cost of deferring this
one, and it is the least visible of the three.**

Ask each member when they joined and record it as `YYYY-MM-DD`. An
approximate month is better than an empty field, because the window the
rule counts is twelve months long and a proposal is only ever a prompt for
a meeting to consider — nothing is applied automatically. Do not fill
these in from guesswork: a date nobody confirmed would start a silence the
member never had.

Once the dates are in, run `cd tools && uv run convener-sweep` and read
what it prints under `Board inactivity (G-09)`. Nothing there is applied;
it is the list the meeting discusses.
