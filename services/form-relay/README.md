# Form relay

The bridge from the public Tally proposal form to GitHub. Tally signs a
submission as `base64(HMAC-SHA256(secret, rawBody))` in a `Tally-Signature`
header. This worker verifies that signature and, only if it holds, turns
the submission into a `proposal-submitted` `repository_dispatch` that
`.github/workflows/candidate-form.yml` already knows how to handle.

It accepts `POST` on a single route (`/`) and nothing else. It reads the
body raw, without parsing it, verifies it in constant time, and either
refuses it with `401` or forwards it, byte-identical, as
`client_payload.body`. It logs no request body and keeps nothing.

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

```bash
npm install
npx wrangler deploy
```

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
  `repository_dispatch` to `example-instance/example-cockpit` (`Contents: read
  & write` is sufficient). This is not the same credential as the
  authentication relay's: that relay holds no token of its own — it only
  proxies GitHub's device-flow endpoints — and the user access token the
  device flow itself issues carries the broader classic `repo` scope, not
  this narrower one.

Unlike `tools/convener_ops/proposal.py::verify_signature`, whose own copy of
`TALLY_WEBHOOK_SECRET` accepts everything when unset (D-13: an absent
integration is a normal state, not an error), a missing
`TALLY_WEBHOOK_SECRET` here refuses every request rather than accepting
them: this worker is the internet-facing boundary, so an unconfigured
secret must fail closed here even though the Actions side, reached only
after this worker already let the request through, fails open.
