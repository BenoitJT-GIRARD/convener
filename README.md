# The Example Collective — Monthly Reading Group

The operational workspace for our community webinar series: a single React
SPA that drives the entire workflow, from finding speakers to wrapping up
events. Everything a volunteer needs sits inside the app.

## What is here

| Folder | What it holds |
|---|---|
| `app/` | The React app (Vite + TypeScript). Deployed to GitHub Pages. |
| `data/` | `speakers.yml` (unified entity), `config.yml` (board, threshold, season). |
| `docs/` | Handbook content as Markdown — rendered *inside* the app at the point of action and in the Handbook tab. Not a separate site. |
| `scripts/` | One-shot scripts (e.g. schema migration). |
| `.github/` | CI: data validation, Tally proposal handler, public-data filter, vitrine sync. |

## How to work on it

```bash
cd app
npm install
npm run dev           # http://localhost:5173/workshop-series/
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
python .github/scripts/validate_data.py
```

## Architecture

- **One entity per speaker.** `data/speakers.yml` carries the whole lifecycle: lead → approved → invited → confirmed → scheduled → delivered → wrapped → archived (plus `parked`, `decline-board`, `decline-speaker`).
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
