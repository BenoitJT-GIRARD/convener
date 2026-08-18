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
Whether a client secret is also required depends on whether the OAuth
application is registered as a GitHub App or an OAuth App — confirm before
first deployment.
