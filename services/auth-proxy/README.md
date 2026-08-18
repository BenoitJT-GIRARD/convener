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

```bash
npm install
npx wrangler deploy
```

Set `ALLOWED_ORIGIN` in `wrangler.toml` to the application's origin.

No client secret is required. The device flow's initial exchange
(`grant_type=urn:ietf:params:oauth:grant-type:device_code`) does not need
one for a public GitHub App client. Refreshing a user access token would
have needed one — this relay is deliberately stateless and secret-free, so
the app does not attempt to refresh: it re-runs the 30-second device flow
each session instead. See decision on the refresh path in `operations.md`.
