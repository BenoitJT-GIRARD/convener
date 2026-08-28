# Form relay

The bridge from the public Tally proposal form to GitHub. Tally signs a
submission as `base64(HMAC-SHA256(secret, rawBody))` in a `Tally-Signature`
header. This worker verifies that signature and, only if it holds, turns
the submission into a `proposal-submitted` `repository_dispatch` that
`.github/workflows/candidate-form.yml` already knows how to handle.

It accepts `POST` on a single route (`/`) and nothing else. It reads the
body raw, without parsing it, verifies it in constant time, and either
refuses it with `401` or forwards it, byte-identical, as
`client_payload.body`. It logs no request body and keeps nothing beyond
the abuse-protection counter described below, and a counter is a count,
never the data that produced it.

## Abuse protection

This worker once had no body-size bound, no rate limiter and no
counter at all — unlike `services/signup-relay`, which has all three (that
service's own README.md, "Abuse protection"). `.github/workflows/
candidate-form.yml` had no `concurrency:` block either, so its own runs
did not serialise; that half of the fix lives in that workflow file, not
here.

The gap this worker's bounds close is not "an anonymous stranger sends a
forged submission" — a caller without `TALLY_WEBHOOK_SECRET` still cannot
produce a signature this worker accepts, at any volume. It is "a caller
who *does* hold the secret" — a leak, an insider, a brute-forced weak
secret — who could otherwise flood `candidate-form.yml` with
`repository_dispatch` runs at no cost beyond signing each body, with
nothing here to slow it down or bound it. Three bounds, mirroring
`services/signup-relay`'s own shape:

- **A body-size bound.** `MAX_BODY_BYTES = 65_536` (64 KiB), checked twice
  — a pre-parse guard on a declared `Content-Length` before the body is
  even read, and a real, encoded-byte-length check afterwards (`.length`
  on a JavaScript string is UTF-16 code units, not bytes — the same
  distinction `services/signup-relay/src/index.js` draws for its own
  `MAX_BODY_BYTES`). Tally wraps up to eleven fields
  (`tools/convener_ops/proposal.py::FORM_FIELDS`) with their own question text
  and field metadata beside each answer, and a short abstract can run to a
  few paragraphs; 64 KiB is comfortably above any real submission's shape
  while remaining a firm, cheap-to-enforce ceiling far below "arbitrary".
- **A burst limiter.** `FORM_RATE_LIMITER` (`wrangler.toml`,
  `[[ratelimits]]`), Cloudflare's Workers Rate Limiting binding — the same
  mechanism `services/signup-relay` uses, at `10` requests per `60`
  seconds. Keyed on one fixed, literal string (`'proposal'`), never on
  anything a caller sends: there is only one form here, so there is no
  legitimate reason to key this any finer, and a key derived from
  caller-supplied data is exactly the gap next door — `services/signup-relay`'s
  limiter was keyed on the attacker-supplied event id, which let a caller
  who varies that field evade it entirely (see that service's own README.md
  for the fix). Checked only once a request's signature already verifies,
  so an unsigned flood never reaches, or spends, this budget.
- **A cumulative counter.** `FORM_RELAY_KV` (`wrangler.toml`,
  `[[kv_namespaces]]`), counting every accepted submission this worker has
  ever dispatched, refusing further ones once `PROPOSAL_CEILING = 2000` is
  reached. Deliberately a plain, ever-growing total, unlike
  `services/signup-relay`'s own per-event ceiling, which resets naturally
  because each event gets its own counter key — this form has no such
  natural reset boundary, so the ceiling is set an order of magnitude
  above any plausible number of real proposals this call-for-candidates
  form will ever receive over the project's life. Reaching it is a strong
  signal something is wrong, worth an operator's attention, not an
  expected event; resetting it, once the cause is understood, is
  `npx wrangler kv key delete "count:proposal" --binding FORM_RELAY_KV
  --remote`, run by hand — a deliberate operator action, never a
  self-service reset this internet-facing worker exposes to anyone.

`CONVENER_DISPATCH_TOKEN`, `FORM_RELAY_KV` and `FORM_RATE_LIMITER` all fail
closed exactly the way `TALLY_WEBHOOK_SECRET` already does: any of the
three missing or unbound refuses every request with `502` rather than
silently skipping the check it exists for. Checked only after a valid
signature is confirmed, so a signature-less flood is refused with `401`
before it ever touches either binding.

## Why this is a second worker, not a route on the auth relay

`services/auth-proxy/README.md` states that the authentication relay is
**deliberately secret-free**, and that this is what makes it redeployable
by anyone in the organisation with one command. This worker cannot make
that claim: it holds a GitHub token, because turning a webhook into a
`repository_dispatch` requires one. Folding it into the auth relay would
give that worker a secret too, destroying its redeployability for no gain
— so it is a separate worker instead, and only this one carries the token.

## Why the signature is checked twice

`tools/convener_ops/proposal.py::verify_signature` checks the same signature
again, on the GitHub Actions side, once the payload has already been
accepted here. That is not redundancy: this worker attests that the
request came from Tally; the check in `proposal.py` attests that the
payload was not forged by someone who already has write access to the
repository (a `repository_dispatch` can be sent by anyone holding a token
scoped to it). Both checks implement the same rule, pinned together by
the fixture `tools/tests/fixtures/governance-cases.json` (decision D-14),
read by both `test/index.test.js` here and `tools/tests/test_proposal.py`.

## Deploying

Run *Deploy form relay* from the Actions tab. Once, before the first run,
the KV namespace has to exist:

```bash
npm install
npx wrangler kv namespace create FORM_RELAY_KV   # once, then paste the
                                                   # printed id into
                                                   # wrangler.toml
```

The workflow's own deploy command reads the repository
`instance/config.json` declares this cockpit lives in and hands it to
Wrangler:

```bash
npx wrangler deploy --var "REPOSITORY:$repository"
```

A deploy from a laptop runs that same command with the same derivation.
A bare `wrangler deploy` leaves a worker holding no repository at all,
which refuses every submission with `502` — see "Fail closed, not
open" below.

`FORM_RATE_LIMITER` needs no equivalent creation step — see its comment in
`wrangler.toml`.

## Secrets

Both are Wrangler secrets, never values in `wrangler.toml`:

```bash
npx wrangler secret put TALLY_WEBHOOK_SECRET
npx wrangler secret put CONVENER_DISPATCH_TOKEN
```

- `TALLY_WEBHOOK_SECRET` — the same shared secret Tally signs with and
  `tools/convener_ops/proposal.py::verify_signature` reads on the other side of
  the dispatch. Same name on both sides on purpose: it is the same secret.
- `CONVENER_DISPATCH_TOKEN` — a GitHub token with permission to send a
  `repository_dispatch` to the repository `instance/config.json` declares
  (`Contents: read & write` is sufficient). This is not the same credential as the
  authentication relay's: that relay holds no token of its own — it only
  proxies GitHub's device-flow endpoints — and the user access token the
  device flow itself issues carries the broader classic `repo` scope, not
  this narrower one.
- `FORM_RELAY_KV` — not a secret, but specific to the Cloudflare account
  this worker deploys to (see "Deploying" above); its namespace id belongs
  in `wrangler.toml`, never guessed or shared with another worker's
  namespace (`services/signup-relay`'s own `SIGNUP_RELAY_KV` is a
  different namespace on the same account). `deploy-form-relay.yml`'s own
  gate skips the deploy — rather than letting `wrangler deploy` fail on
  it — while this is still the placeholder `wrangler.toml` ships with.
- `FORM_RATE_LIMITER` — also not a secret; see "Abuse protection" above
  and its own comment in `wrangler.toml` for why, unlike the KV namespace,
  it needs no per-account value and ships already configured.

## Fail closed, not open

Unlike `tools/convener_ops/proposal.py::verify_signature`, whose own copy of
`TALLY_WEBHOOK_SECRET` accepts everything when unset (D-13: an absent
integration is a normal state, not an error), a missing
`TALLY_WEBHOOK_SECRET` here refuses every request rather than accepting
them: this worker is the internet-facing boundary, so an unconfigured
secret must fail closed here even though the Actions side, reached only
after this worker already let the request through, fails open.

`REPOSITORY` — the repository this worker dispatches into, passed at
deploy time rather than written into `src/index.js` (`wrangler.toml`'s own
header argues why) — is refused the same way, and it is the member of that
set whose absence would be quietest. A missing secret or binding is
missing; an unset repository is present and wrong. The dispatch would
carry the word `undefined` where the repository belongs, GitHub would
answer `404`, and Tally's webhook log would show the same `502` an expired
`CONVENER_DISPATCH_TOKEN` produces — so an operator would go and rotate a
token that was never wrong. It is refused by name, before the call is
spent.
