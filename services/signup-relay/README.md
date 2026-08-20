# Signup relay

The point of entry for a registration. `app/src/signup/SignupForm.tsx`
encrypts a participant's first name, surname, email address and optional
institution in the browser (`app/src/signup/encrypt.ts`), under the target
event's published public key, and POSTs the result here. This worker never
holds a private key and never can: it only ever sees `{event_id, v,
encrypted_key, iv, ciphertext}`, and every field but `event_id` is base64
ciphertext.

It accepts `POST` on a single route (`/`) and nothing else. It reads the
body raw, checks its **shape**, applies the abuse protection below, and — if
everything holds — turns it into a `registration-submitted`
`repository_dispatch`, byte-identical to what it received, the same
`client_payload.body` pattern `services/form-relay` uses. It logs no request
body and keeps nothing beyond the per-event counter described below, and
that counter is a count, never the data that produced it.

## What "shape" means here, and what it deliberately cannot mean

This worker cannot read the ciphertext it forwards — that is the whole
point of encrypting in the browser (see `tools/convener_ops/eventkeys.py`'s and
`encrypt.ts`'s own module docstring comments) — so its validation is a
**shape** check, never a **content** check, and this README does not claim
otherwise:

- the five expected fields are present, and no others;
- `event_id` is shaped like one (mirrors
  `tools/convener_ops/commit_format._TOKEN`) and names an event whose public key
  (`keys/events/<event_id>.pub`) actually exists in the repository;
- `v` is the wire version this worker was written against;
- `encrypted_key`, `iv` and `ciphertext` are valid base64 that decode to the
  lengths the wire format fixes: 256 bytes, 12 bytes, and at least 16 bytes
  (`tools/convener_ops/eventkeys.py`'s module docstring documents all three).

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

## Fail closed, not open

`tools/convener_ops/proposal.py::verify_signature` tolerates an absent secret by
design — it sits behind an authenticated `repository_dispatch`, so an
unset `TALLY_WEBHOOK_SECRET` there just skips a check a forged dispatch
could not have passed anyway. This worker has no such shelter: it is the
first thing a request from the open internet reaches. So a missing
`CONVENER_DISPATCH_TOKEN`, or a `SIGNUP_RELAY_KV` binding that was never set up,
refuses every request with `502` rather than falling back to "no ceiling"
or "no known-event check" — neither GitHub nor the counter is ever touched
on a misconfigured deploy. `test/index.test.js` pins this for both.

## Abuse protection

No shared secret is possible — a browser cannot hold one — so this
endpoint is open by construction. Of the three options considered:

| Option | Why not, here |
|---|---|
| Cloudflare rate-limiting rules | Configured in the dashboard, outside version control — a setting a successor inherits with no record of why it has the value it has, unlike everything else in this repository. It also targets traffic through a Cloudflare-proxied zone; this worker, like the other two, deploys to a plain `*.workers.dev` route with no custom domain, so the product would need one added first. |
| Turnstile | Costs nothing and stays on the same account, but it is a third-party script embedded in the registration page itself — outside this worker's own files, widening a diff this task does not own — on a page whose whole design argument (`SignupForm.tsx`'s own comments) is that nothing runs there beyond what the participant strictly needs. |
| **A limiter inside the worker** | **Chosen.** Needs state, so a storage binding — Workers KV, same account, no new vendor. |

**Workers KV, verified rather than assumed** (Cloudflare's published Free
plan limits, checked while writing this): 100,000 reads/day, writes to
**1,000 distinct keys per day**, and — separately, on every plan, not just
Free — at most **one write per second to the same key**. That last number
shapes the design directly: this worker holds exactly one mutable key per
event (`count:<event_id>`), so an event's entire registration volume,
however large, only ever spends **one** of the 1,000-distinct-keys/day
budget — the limiting factor at this project's scale would have to be well
over a thousand events open for registration on the same day. The
one-write-per-second-per-key limit is the real constraint: two people
registering for the same popular event within the same second can collide,
and the loser's write may be rejected or delayed by KV's own eventual
consistency (up to ~60 seconds to propagate globally).

That collision is accepted, not defended against, because of what this
counter is *for*. **A per-event ceiling is needed regardless of which of
the three options above was chosen** — an event does not have ten thousand
registrants, and a count that goes past a sane ceiling is worth surfacing
as a signal even where it is not, on its own, a hard defence. So the
counter is read before the two GitHub calls (cheaper to refuse here than to
spend an API call on a request that will be refused anyway), a read
failure is treated as "no count yet" rather than blocking a legitimate
registration, and the write happens only after a confirmed dispatch and is
itself best-effort: a registration that already reached GitHub is never
undone because the count afterwards could not be written. None of this
needs to be exact to do its job — three or four registrations racing past
the ceiling in the same second is not the failure this design defends
against; a script hammering one event to ten thousand rows is.

The ceiling itself, `PER_EVENT_CEILING` in `src/index.js`, is `500` — an
order of magnitude above any real seminar's attendance, and three orders of
magnitude below a number ("ten thousand registrants") nobody would mistake
for a real one.

Cloudflare's own network-level DDoS mitigation sits beneath all of this,
for every Worker, on every plan, automatically — nothing here replaces
that layer or claims to; this design exists for the layer above it, where
one event's registration count needs to stay a plausible number.

## Response codes

The caller only ever sees one of these six:

- `204` — accepted and dispatched.
- `400` — the body is not well-shaped: not JSON, wrong or extra fields,
  invalid base64, or a field decoding to the wrong length. Also the one
  case checked before the body is even read: a declared `Content-Length`
  already past the plausible ceiling.
- `404` — either the route (any path but `/`), or a well-shaped `event_id`
  naming an event whose public key does not exist in the repository. A
  caller cannot tell these apart and does not need to; both mean "there is
  nothing here to send this to."
- `405` — any method other than `POST`.
- `429` — this event has already reached its registration ceiling.
- `502` — this worker could not complete the request: a missing secret or
  storage binding (see "Fail closed" above), or the dispatch to GitHub
  itself failed. Never GitHub's own status or body — a caller has no need
  to see GitHub's error detail, and passing it through would blur this
  worker's taxonomy with GitHub's, the same reasoning
  `services/form-relay/README.md` gives for its own `502`.

There is no `401`: unlike the form relay, there is no shared secret here
for a caller to get wrong.

## Deploying

```bash
npm install
npx wrangler kv namespace create SIGNUP_RELAY_KV   # once, then paste the
                                                     # printed id into
                                                     # wrangler.toml
npx wrangler deploy
```

## Secrets

- Wrangler secret `CONVENER_DISPATCH_TOKEN` — set with
  `npx wrangler secret put CONVENER_DISPATCH_TOKEN`. A GitHub token scoped to
  *Contents: read & write* on `example-instance/example-cockpit`, the same
  scope `services/form-relay/README.md` documents for its own token: this
  worker uses it both to check whether an event's public key exists
  (a Contents-API read) and to send the `repository_dispatch` itself. It
  may be the same credential already created for the form relay, or a
  separate one with the same scope — Wrangler secrets are per-worker
  either way, so it is set here independently regardless.
- `SIGNUP_RELAY_KV` — not a secret, but specific to the Cloudflare account
  this worker deploys to (see "Deploying" above); its namespace id belongs
  in `wrangler.toml`, never guessed or shared with another worker's
  namespace.

Neither belongs in `wrangler.toml` as a literal secret value — see that
file's own comments.
