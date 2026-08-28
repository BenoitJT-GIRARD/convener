# Signup relay

The point of entry for a registration. `app/src/islands/signup/SignupForm.tsx`
encrypts a participant's first name, surname, email address and optional
institution in the browser (`app/src/signup/encrypt.ts`), under the target
event's published public key, and POSTs the result here. This worker never
holds a private key and never can: it only ever sees `{event_id, v,
encrypted_key, iv, ciphertext}`, and every field but `event_id` is base64
ciphertext.

It accepts `POST` (and the `OPTIONS` preflight a browser sends ahead of it)
on two routes, `/` and `/survey`, and nothing else. It reads the body raw,
checks its **shape**, applies the abuse protection below, and — if
everything holds — forwards it byte-identically, never re-serialised. The
two routes part company only there.

`/` turns it into a `repository_dispatch` of type `registration-submitted`,
the same `client_payload.body` pattern `services/form-relay` uses, and one
workflow run starts for it. That stays true because the confirmation
e-mail a registration produces carries the room link and the matching
code, and there is no other channel for either.

`/survey` **writes it to the submission queue instead**:
one Contents-API `PUT` of `queue/survey/<entry id>.json` on the
`submission-queue` branch, and no run starts at all. One daily drain
handles everything waiting — see `docs/reference/operations.md`, "Draining
the submission queue", for the branch, the ledger and the one precondition
nothing can enforce (never open a pull request from that branch). It costs
this worker the same number of GitHub API calls the dispatch did, and the
same credential: `Contents: read & write`, which
`repository_dispatch` already required. Nothing about a survey response is
sent back to the submitter, which is why the slowest cadence costs it
nothing.

It logs no request body and keeps nothing beyond the per-event counters
described below, and a counter is a count, never the data that produced
it.

## A second route, not a second worker

`app/src/islands/survey/SurveyForm.tsx` — the post-event survey —
encrypts a response in the browser exactly the way
`SignupForm.tsx` encrypts a registration (`app/src/survey/encrypt.ts` is the
sibling of `app/src/signup/encrypt.ts`, same wire format), and POSTs it to
`/survey` on this same worker rather than to a fourth worker. That is
deliberate, not a shortcut: the envelope this worker validates is
byte-identical in shape whichever route receives it — `validatedEventId`
draws no distinction between the two — the known-event check is the same
`instance/keys/events/<id>.pub` lookup, and the GitHub token is the one already
scoped to this repository. None of the reasoning in "Why this is a third
worker, not a route on either of the other two" below applies a second time
between `/` and `/survey`: there is no second trust boundary here, only a
second `client_payload.body` destination and a second `event_type`.

What genuinely is *also* separate: `/survey`
checks a second fact `/` never needs to, once the event is known to
exist — whether that event's survey switch is actually on. That check
used to be enforced in exactly one of four layers (the CI handler,
last), which meant a participant answering a closed survey was thanked and
had the answer discarded with no one told. `surveyEnabled` (`src/index.js`)
reads `instance/public-data/survey-status.json` through the same GitHub Contents API
call shape — the same credential, `CONVENER_DISPATCH_TOKEN`, and the same
`https://api.github.com/repos/.../contents/<path>` request — `eventKeyExists`
already spends one read of for `instance/keys/events/<id>.pub`, just a different
path, and refuses (`404`, the same bucket "no such event" already falls
into) when the event is not in the array it decodes.

That file was once read from a plain public HTTPS URL
instead (a page on the published site, no token, no GitHub API budget).
That is gone: the URL pointed at a deployment this project
had never actually wired up, so the relay's own answer depended on a site
that did not exist; it also carried a build-to-live latency the handler's
own read of `instance/data/speakers.yml` does not have, on top of which the relay
added a second one. Reading this repository's own committed copy instead
makes the relay's answer agree with the handler's by construction, not by
build timing — at the cost of one more Contents-API read on a route
already spending one and already ceiling-capped per event.
`instance/public-data/survey-status.json` is committed for exactly this reason (see
the root `.gitignore`'s own comment): a bare, sorted list of event ids, no
personal data, refreshed by `deploy.yml`'s "Commit survey status" step
every time it changes.

This is the relay's own layer, not the only one: `app/src/islands/survey/
SurveyForm.tsx` still fetches the deployed `survey-status.json` from the
published site — a static page has no token and cannot read the Contents API
any other way — and the daily drain checks the authoritative
`instance/data/speakers.yml` again regardless. Three layers still, for the same
reason as before: a page check is bypassable by posting straight to this
worker, and a relay check — even one now reading this repository's own
tip rather than a deployed artefact — is a courtesy that saves a wasted
queue entry, never the authority.

What genuinely is separate is the abuse ceiling. `/survey` is keyed by its
own KV counter (`count:survey:<event_id>`, distinct from `/`'s own
`count:<event_id>`) and its own rate-limiter key (`survey:<event_id>`,
distinct from the bare `<event_id>` `/` uses) — see `surveyCounterKey` and
`surveyRateLimiterKey` in `src/index.js`. Reusing `/`'s counter and limiter
keys for `/survey` would have let a flooded survey spend a registration's
budget, or a flooded registration silently starve a survey nobody has
abused at all; a distinct pair of keys on the *same* limiter and the *same*
KV namespace avoids that while adding no new binding, no new secret and no
new deploy.

## What "shape" means here, and what it deliberately cannot mean

This worker cannot read the ciphertext it forwards — that is the whole
point of encrypting in the browser (see `tools/convener_ops/eventkeys.py`'s and
`encrypt.ts`'s own module docstring comments) — so its validation is a
**shape** check, never a **content** check, and this README does not claim
otherwise:

- the five expected fields are present, and no others, and none of them is
  spelled twice (`hasDuplicateKey` in `src/index.js` — `JSON.parse` keeps
  only the last occurrence of a repeated key, so a check on the *parsed*
  object alone cannot see a second `"event_id"` hiding in the raw bytes
  this worker still forwards byte-identical);
- `event_id` is shaped like one (mirrors
  `tools/convener_ops/commit_format._TOKEN`) and names an event whose public key
  (`instance/keys/events/<event_id>.pub`) actually exists in the repository (see
  "Known events" below for how, and why);
- `v` is the wire version this worker was written against;
- `encrypted_key`, `iv` and `ciphertext` are valid base64 that decode to the
  lengths the wire format fixes: 256 bytes, 12 bytes, and at least 16 bytes
  (`tools/convener_ops/eventkeys.py`'s module docstring documents all three),
  measured in real bytes, not the UTF-16 code units JavaScript's own
  `.length` would give.

None of this proves the ciphertext decrypts to a real registration, or that
whoever sent it is a real participant rather than anyone who fetched the
same public key and encrypted anything under it — a public key is for
confidentiality, not for authenticating a sender, and no design here changes
that. What it protects is that a stranger's answers, once encrypted,
**cannot** be read by this worker, by an operator watching its logs, or by
anyone without the one private key that can decrypt them. That is a
structural guarantee — stronger than `services/form-relay`'s "we promise
not to log the body," because this worker could not log the plaintext if it
tried — and it is the only guarantee this file makes.

## Why this is a third worker, not a route on either of the other two

Turning a submission into a `repository_dispatch` requires a GitHub token,
so — for the same reason `services/form-relay/README.md` gives for not
folding itself into `services/auth-proxy` — this cannot be the
deliberately stateless, secret-free authentication relay either. And unlike
the form relay, there is no shared secret this worker's caller could sign
with: a static registration page cannot hold one, so this endpoint is open
by construction (see "Abuse protection" below) where the form relay's is
not. That is a different enough trust boundary to keep it in its own
worker, sharing only the Cloudflare account and the dispatch pattern, not
the code.

## Cross-origin requests (CORS)

The registration page is served from a different origin than this worker,
so a browser sends a preflight `OPTIONS` before the real `POST` — the form
sets `content-type: application/json`, which the Fetch spec does not
exempt from a preflight (only a handful of simple header values are).
`services/auth-proxy/src/index.js` already solved this once for a
different worker; this one copies that pattern rather than inventing a
second one: an `ALLOWED_ORIGIN` var (passed to `wrangler deploy --var` by
`deploy-signup-relay.yml`, which derives it from `instance/config.json`;
`services/auth-proxy/wrangler.toml`'s header says why it is written in no
configuration file), a 204 answer to the
preflight, and CORS headers on *every* response this worker sends, success
or error — a caller's `fetch` cannot read a response body or even a bare
status code cross-origin without `Access-Control-Allow-Origin` on that
specific response, not only on the ones that happen to succeed.

A request whose `Origin` does not exactly match `ALLOWED_ORIGIN` (including
one with no `Origin` header at all, and every request if `ALLOWED_ORIGIN`
itself is unset) gets a bare `403` with no CORS headers — again mirroring
`auth-proxy` exactly. This is not a security boundary; `Origin` is a header
any non-browser caller can set to anything, and this worker's real
authorisation is that it takes no data it cannot forward safely regardless
of who sent it. It exists so real browsers behave correctly, not so this
worker can trust it.

## Fail closed, not open

`tools/convener_ops/proposal.py::verify_signature` tolerates an absent secret by
design — it sits behind an authenticated `repository_dispatch`, so an
unset `TALLY_WEBHOOK_SECRET` there just skips a check a forged dispatch
could not have passed anyway. This worker has no such shelter: it is the
first thing a request from the open internet reaches. So a missing
`CONVENER_DISPATCH_TOKEN`, a `SIGNUP_RELAY_KV` binding that was never set up, a
`SIGNUP_RATE_LIMITER` binding that was never set up, or a
`GLOBAL_RATE_LIMITER` binding that was never set up,
refuses every request with `502` rather than falling back to "no
ceiling," "no burst limit" or "no known-event check" — none of GitHub,
the counter or either limiter is ever touched on a misconfigured deploy.
`REPOSITORY` is refused with them, and it is the one whose absence would
otherwise be silent: GitHub answers a Contents read under a repository
that is not there with a clean `404`, which this worker reads as "no such
event", so it would refuse every real registration for every real event as
an unknown one. `test/index.test.js` pins this for all five. `ALLOWED_ORIGIN` fails closed too, but visibly
differently — see "Cross-origin requests" above — because an unset var
naturally cannot equal any real `Origin` a browser sends, with no extra
code needed to enforce it.

## Abuse protection

No shared secret is possible — a browser cannot hold one — so this
endpoint is open by construction. Of the three options available:

| Option | Why not, here |
|---|---|
| Cloudflare rate-limiting rules | Configured in the dashboard, outside version control — a setting a successor inherits with no record of why it has the value it has, unlike everything else in this repository. It also targets traffic through a Cloudflare-proxied zone; this worker, like the other two, deploys to a plain `*.workers.dev` route with no custom domain, so the product would need one added first. |
| Turnstile | Costs nothing and stays on the same account, but it is a third-party script embedded in the registration page itself — outside this worker's own files, widening the change beyond this worker — on a page whose whole design argument (`SignupForm.tsx`'s own comments) is that nothing runs there beyond what the participant strictly needs. |
| **A limiter inside the worker** | **Chosen** — but the first pass at this, Workers KV alone, turned out not to hold against the exact scenario it was written to defend. What replaced it is below. |

### What Workers KV alone did not do

The first version of this worker used a single `SIGNUP_RELAY_KV` counter
per event, read before dispatching and incremented after, with a ceiling of
500. That does not survive a fast burst: Workers KV serves reads from an
edge cache that can be up to **60 seconds** stale, and restricts writes to
the **same key** to **one per second**, on every plan, not only Free. Ten
thousand requests arriving quickly at one event would see roughly the same
stale, under-500 count on every read for most of that window, and only
around sixty of the resulting writes would actually land in that first
minute — the other 9,940-odd requests would all read a ceiling that was
never breached, and all get dispatched. The counter was real, but it could
not count fast enough to stop what it existed to stop.

### The free-tier numbers, honestly

Two of Cloudflare's own pages disagree with each other. The **limits**
page (`developers.cloudflare.com/kv/platform/limits/`) says "Writes to
different keys: 1,000 per day." The **pricing** page
(`developers.cloudflare.com/workers/platform/pricing/`) says "Keys
written: 1,000 / day," with no "different keys" qualifier — read plainly,
every write counts, not only the first one to a new key. This worker's
design does not depend on resolving that contradiction: because
`count:<event_id>` is one key reused for the whole life of an event's
registration window, the generous reading costs this worker nothing extra
either way it turns out to be true, and the conservative reading only
matters if a single event's counter is written to more than 1,000 times —
above `PER_EVENT_CEILING` itself, so the ceiling would already have
refused further registrations for that event before the write quota could.
Both pages are cited so a successor can re-check them rather than trust
this paragraph.

### The burst limiter

`SIGNUP_RATE_LIMITER` (`wrangler.toml`, `[[ratelimits]]`) is Cloudflare's
**Workers Rate Limiting binding**, a native binding rather than the
zone-level rules ruled out above — and it exists for exactly the scenario
KV alone could not stop. Verified from
`developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/`
rather than assumed: the binding needs Wrangler `>= 4.36.0` (this worker's
`package.json` was bumped from the `^3.99.0` the other two relays still
pin, to `^4.36.0`, for this reason alone), and Cloudflare's own docs state
its behaviour plainly: *"The Rate Limiting API is permissive, eventually
consistent, and intentionally designed to not be used as an accurate
accounting system"* — quoted, not paraphrased, because that sentence is
the honest ceiling on what this section can claim.

**Plan availability could not be confirmed either way from the
documentation**, and that gap is recorded rather than papered over: the
binding's own reference page states no Free/Paid restriction at all, and —
unlike Workers KV, Durable Objects, Queues, D1, Hyperdrive, Vectorize, R2
and Containers, every one of which appears with explicit Free/Paid figures
on the pricing page — "Rate Limiting" does not appear on that page as a
line item at all, metered or not. The balance of that evidence (no stated
restriction, no billing line) leans toward free-tier availability, but it
is an inference, not a quoted confirmation, and it was checked directly
against `wrangler deploy --dry-run`, which resolved the binding and printed
`env.SIGNUP_RATE_LIMITER (30 requests/60s)` without needing a real
Cloudflare account — evidence the *configuration* is valid, not evidence
of *plan* availability. If the account this worker actually deploys to
cannot use it, `wrangler deploy` fails loudly, in CI, with Cloudflare's own
error naming the reason — a visible, fast failure, not a silent one.

Keyed per event (`rateLimiter.limit({ key: eventId })`, `simple = { limit:
30, period: 60 }`), so one flooded event's budget cannot starve another's.
Set to 30 requests per 60 seconds: generous enough that a genuine spike —
thirty people clicking a link within a minute of an announcement email — is
never refused, while cutting a ten-thousand-request burst at one event down
to roughly 30 requests per minute reaching the rest of the pipeline. That
throughput is comfortably under the very KV per-second-per-key limit that
broke the first design, which is what makes the two mechanisms work
together rather than merely coexist: the limiter is what keeps the counter
able to count. A thrown `.limit()` call is treated the same as every other
fail-closed check above — refused (`502`), never silently skipped.

### Why both, not one

The two are not redundant. `SIGNUP_RATE_LIMITER` bounds **velocity** — no
more than 30 requests per event per minute, checked first, before either
GitHub call. `SIGNUP_RELAY_KV`'s `count:<event_id>` bounds a **cumulative
total** over an event's entire registration window, which can span weeks —
a slow, sustained trickle of 25 requests/minute for hours would never trip
the limiter but would still climb toward, and eventually hit,
`PER_EVENT_CEILING`. Neither is exact — the limiter is explicitly "not…an
accurate accounting system," and the counter's read-before/write-after
shape (see `src/index.js`) is not atomic either — but together they cover
the two failure modes ("fast" and "sustained") a single mechanism does not.
An event does not have ten thousand registrants, and a count that goes
past a sane ceiling is worth surfacing as a signal even where it is not, on
its own, a hard defence; `500` — an order of magnitude above any real
seminar's attendance, three orders of magnitude below "ten thousand" — is
that ceiling.

A KV **write** failure after a successful dispatch is no longer discarded
silently: `console.error` records the event id (already public — the same
identifier every dispatch and every workflow run already names) and a
fixed message, never the body, so a counter that stops advancing leaves a
trace instead of just going quiet — the one thing a signal must not do.

### The per-event key was itself the gap

`SIGNUP_RATE_LIMITER` above is keyed on `eventId` — attacker-supplied,
read straight from the request body before this worker has any way to
tell a real event from a fabricated one. A fabricated id can never reach a
dispatch (`eventKeyExists` below refuses it with `404`), so the abuse this
originally protected against — burning a real registrant's own budget —
never happens. But a caller who sends a *different* fabricated id on every
request gets a fresh rate-limiter bucket every time: `rateLimiter.limit({
key: eventId })` never sees the same key twice, so it never trips,
regardless of how fast the requests arrive. Each one still costs this
worker a real Contents-API call against `CONVENER_DISPATCH_TOKEN`'s own shared
GitHub budget before the 404 — and that budget is the same one every real
registration, on every real event, and both `/survey` reads, all draw
from. The per-event limiter was never wrong about *what* it bounds; it was
wrong about *whose choice* the key was.

`GLOBAL_RATE_LIMITER` (`wrangler.toml`) is the fix — a second binding, not
a second key on `SIGNUP_RATE_LIMITER`: Cloudflare's Rate Limiting binding
applies one `limit`/`period` to every key it is asked about, so a global
ceiling that has to be more generous than any single event's own 30/60s
needs a binding of its own, not a second call against the first.
`GLOBAL_RATE_LIMITER_KEY` is one fixed literal (`'global'`) — never
anything a caller sends, the one property that actually closes this gap:
there is no field left on the request for an attacker to vary that would
give them a second bucket. Checked first, before the per-event limiter,
since it is the cheaper, coarser bound and the one an id-varying flood
cannot evade by construction. `60` requests per `60` seconds — double the
single-event ceiling — is generous enough that several real events open
for registration at once, each drawing its own legitimate per-event burst,
are never refused here first, while still capping this worker's total
throughput to roughly 3,600 requests an hour: comfortably inside
`CONVENER_DISPATCH_TOKEN`'s own 5,000/hour authenticated GitHub API budget even
at sustained maximum throughput, with headroom left for the survey route
sharing the same token and the same budget.

This does not replace the per-event limiter or the per-event ceiling —
both still matter for a flood aimed at one *real*, known event, where the
attacker has no reason to vary `event_id` at all. It closes the one case
those two could never reach: an attacker who never sends the same
`event_id` twice.

Cloudflare's own network-level DDoS mitigation sits beneath all of this,
for every Worker, on every plan, automatically — nothing here replaces
that layer or claims to; this design exists for the layer above it, where
one event's registration count needs to stay a plausible number.

## Known events: a live check, not a baked allow-list

`eventKeyExists` in `src/index.js` asks GitHub's Contents API,
`GET /repos/.../contents/instance/keys/events/<event_id>.pub`, live, on every
request, rather than checking a list of known event ids baked into the
worker at deploy time.

An earlier version of this rationale claimed the live check avoids
"deploy-time coupling between a new event key being committed and this
worker being redeployed." That does not hold up: the browser never fetches
the public key from this worker or from GitHub — it fetches
`instance/keys/events/<id>.pub` from the **app's own origin**
(`SignupForm.tsx`, `eventPublicKeyUrl`), which `app/scripts/
copy-event-keys.mjs` publishes there as an `app/package.json` `prebuild`
step, and `.github/workflows/deploy.yml` rebuilds and republishes the app
on **every** push to `main`. A newly committed event key is invisible to a
participant until that rebuild happens regardless of whether *this* worker
is ever redeployed — so the redeploy the live check was said to avoid
happens anyway, on the same commit, for an unrelated reason.

What the live check genuinely buys instead: no *stale allow-list* failure
mode, where a skipped or failed `deploy-signup-relay.yml` run would leave
this worker silently refusing a perfectly real, newly created event
indefinitely with no visible cause; and no new build tooling — a generated
list of ids and a `paths:` entry watching `instance/keys/events/**`, mirroring what
`copy-event-keys.mjs` already does for the app. Both are real, if modest,
advantages, worth the one extra GitHub API call and its own timeout per
registration (`GITHUB_FETCH_TIMEOUT_MS`) — not worth abandoning the design
for a claim that did not survive checking it against the rest of the
pipeline.

## Response codes

The caller only ever sees one of these seven:

- `204` — accepted and dispatched.
- `400` — the body is not well-shaped: not JSON, wrong, extra or duplicated
  fields, invalid base64, a field decoding to the wrong length, or a body
  that could not even be read (an aborted or broken request stream). Also
  the case checked before the body is read at all: a declared
  `Content-Length`, or the real encoded byte length once read, already past
  the plausible ceiling.
- `403` — the request's `Origin` does not match `ALLOWED_ORIGIN` (including
  no `Origin` at all). See "Cross-origin requests" above for why this is
  not a security check.
- `404` — the route (a `POST`/`OPTIONS` to any path but `/` or `/survey`;
  a method other than those two is `405` regardless of path, checked
  first), a well-shaped `event_id` naming an event whose public key does
  not exist in the repository, or — on `/survey` only — an
  event whose survey switch is not on. A caller cannot tell any of these
  apart and does not need to; all three mean "there is nothing here to
  send this to."
- `405` — any method other than `POST` or `OPTIONS`.
- `429` — this event has either tripped the burst limiter or already
  reached its cumulative ceiling; either way the response carries
  `Retry-After: 60`.
- `502` — this worker could not complete the request: a missing secret or
  storage/limiter binding (see "Fail closed" above), the known-event check
  failed for a reason other than "no such event," the dispatch to GitHub
  itself failed, or — on `/survey` only — the survey-status Contents-API
  read failed for a reason other than "not enabled" or "file does not
  exist yet" (a status other than `200`/`404`, a response that is not
  valid JSON, a `content` field that will not base64-decode, decoded
  content that is not valid JSON, or JSON that is not an array). Never
  GitHub's own status or body — a caller has no need to see GitHub's error
  detail, and passing it through would blur this worker's taxonomy with
  GitHub's, the same reasoning `services/form-relay/README.md` gives for
  its own `502`.

There is no `401`: unlike the form relay, there is no shared secret here
for a caller to get wrong.

## Deploying

Run *Deploy signup relay* from the Actions tab. Once, before the first
run, the KV namespace has to exist:

```bash
npm install
npx wrangler kv namespace create SIGNUP_RELAY_KV   # once, then paste the
                                                     # printed id into
                                                     # wrangler.toml
```

The workflow's own deploy command reads two values out of
`instance/config.json` — the one address this project is published at, and
the repository this cockpit lives in — and passes both to Wrangler:

```bash
npx wrangler deploy --var "ALLOWED_ORIGIN:$origin" --var "REPOSITORY:$repository"
```

Deploying from a laptop means running that same command with the same
derivations; a bare `wrangler deploy` leaves a worker that refuses every
request rather than one that answers for the wrong site or reads and
writes in somebody else's repository.

`SIGNUP_RATE_LIMITER` needs no equivalent creation step — see its comment
in `wrangler.toml`.

## Secrets

- Wrangler secret `CONVENER_DISPATCH_TOKEN` — set with
  `npx wrangler secret put CONVENER_DISPATCH_TOKEN`. A GitHub token scoped to
  *Contents: read & write* on the repository `instance/config.json`
  declares, the same
  scope `services/form-relay/README.md` documents for its own token: this
  worker uses it both to check whether an event's public key exists
  (a Contents-API read) and to send the `repository_dispatch` itself.
  Prefer a **separate** token from the form relay's, even though the scope
  is identical: this worker spends two GitHub API calls per registration
  against the same 5,000/hour authenticated budget the form relay also
  draws on, and sharing one token couples the two workers' quotas together
  — a flood at one becomes a `502` storm at the other. Wrangler secrets are
  per-worker regardless, so a separate token costs nothing extra to set up.
- `SIGNUP_RELAY_KV` — not a secret, but specific to the Cloudflare account
  this worker deploys to (see "Deploying" above); its namespace id belongs
  in `wrangler.toml`, never guessed or shared with another worker's
  namespace. `deploy-signup-relay.yml`'s own gate skips the deploy — rather
  than letting `wrangler deploy` fail on it — while this is still the
  placeholder `wrangler.toml` ships with.
- `SIGNUP_RATE_LIMITER` — also not a secret; see "The burst limiter" above
  and its comment in `wrangler.toml` for why, unlike the KV namespace, it
  needs no per-account value and ships already configured.

Neither `CONVENER_DISPATCH_TOKEN` nor a KV namespace id belongs in
`wrangler.toml` as a literal secret value — see that file's own comments.
`ALLOWED_ORIGIN` is not there either, for a different reason: it is this
instance's own address, and the deploy derives it rather than reading it
from a file the product owns.
