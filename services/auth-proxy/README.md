# Authentication relay

GitHub's OAuth endpoints send no CORS headers, so the browser application
cannot call them directly. This worker forwards exactly two paths and adds
the headers.

It holds no state, stores nothing, and logs no request body.

## Why it is here and not somewhere else

The source lives in this repository and deploys from CI. If the hosting
account is ever lost, anyone with organisation access redeploys it with one
command. That is the condition of transferability — see decision D-03.

## Deploying

Run *Deploy auth relay* from the Actions tab. That workflow reads the one
address `config/instance.json` declares this project is published at, and
passes its origin to Wrangler:

```bash
npx wrangler deploy --var "ALLOWED_ORIGIN:$origin"
```

`ALLOWED_ORIGIN` is the only origin this worker answers cross-origin
requests for, and it is deliberately not written in `wrangler.toml` — that
file's own header says why, and what was rejected. Deploying from a laptop
means running the same command with the same derivation; a `wrangler
deploy` without it leaves a worker that refuses every request, which is the
loud half of D-25 rather than a silent one.

No client secret is required. The device flow's initial exchange
(`grant_type=urn:ietf:params:oauth:grant-type:device_code`) does not need
one for a public GitHub App client. Refreshing a user access token would
have needed one — this relay is deliberately stateless and secret-free, so
the app does not attempt to refresh: it re-runs the 30-second device flow
each session instead. See decision on the refresh path in `operations.md`.
