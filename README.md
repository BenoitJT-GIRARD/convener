# The Example Collective — Monthly Reading Group

The operational workspace for our community webinar series: a single React
SPA that drives the entire workflow, from finding speakers to wrapping up
events. Everything a volunteer needs sits inside the app.

## What is here

| Folder | What it holds |
|---|---|
| `app/` | The React app (Vite + TypeScript). Built here and published to the separate `example-showcase` repository — see *Publishing the application (GitHub Pages)* in `docs/reference/operations.md`. |
| `data/` | `speakers.yml` (unified entity), `config.yml` (board, threshold, season). |
| `docs/` | Handbook content as Markdown — rendered *inside* the app at the point of action and in the Handbook tab. Not a separate site. |
| `tools/` | The `convener-ops` package: data validation, integration status, the sweep, the public-data filter, and the form-proposal handler. |
| `services/auth-proxy/` | The Cloudflare Worker that relays the GitHub device-flow sign-in. |
| `services/form-relay/` | The Cloudflare Worker that verifies a Tally webhook and relays it into a GitHub `repository_dispatch`. Holds a GitHub token. |
| `.github/` | CI: data validation, Tally proposal handler, public-data filter, vitrine sync, quality and security gates. |

## How to work on it

```bash
cd app
npm install
npm run dev           # http://localhost:5173/example-showcase/app/
```

You'll be prompted for a GitHub fine-grained PAT scoped to this repository
(`Contents: read & write`, `Issues: read & write`). Or visit `?demo=1` to see
the app with mocked data — no sign-in.

Build + tests:

```bash
cd app
npm test -- --run
npm run build
```

Validate data:

```bash
cd tools && uv run convener-validate
```

Check which external integrations are configured:

```bash
cd tools && uv run convener-check-config
```

See `docs/reference/operations.md` for what each integration needs, and what
happens without it.

### Local checks (optional)

```bash
uvx pre-commit install
```

Runs formatting, linting, secret detection and British-English spelling
before each commit — the same checks the `quality.yml` and `security.yml`
workflows run in CI. It is a convenience, not a gate — CI remains the
authority.

## Architecture

- **One entity per speaker.** `data/speakers.yml` carries the whole lifecycle: lead → approved → invited → confirmed → scheduled → delivered → archived (plus `parked`, `decline-board`, `decline-speaker`).
- **State machine.** Status changes are a consequence of explicit gestures (vote, send invitation, log reply, lock date). The free-form status field is gone (except a board-only admin override).
- **Two personas.** Active organizer and board member, served at parity. The inbox adapts to the role.
- **Handbook content rendered inline.** Each runbook step links to the relevant Markdown chunk (template email, instructions) which renders next to the action. No back-and-forth with a separate doc site.
- **Vitrine separate.** [`example-showcase`](https://github.com/example-instance/example-showcase) is the public marketing site, fed by the filtered public-data sync.

See `docs/superpowers/specs/2026-05-23-convener-app-refonte-design.md` for the
full design and `docs/superpowers/plans/2026-05-23-convener-app-refonte.md`
for the implementation plan.

## Spot a mistake?

Every Markdown file under `docs/` is the source of truth for its content.
Edit on GitHub (pencil icon) — your change becomes a pull request. Once
merged, the app shows the updated content live (cached for ~5 minutes).
