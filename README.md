# The Example Collective — Monthly Reading Group

This is the **handbook** for our community webinar series: everything a volunteer needs to find speakers, prepare an event, host it, and follow up.

## Start here

Open **[`docs/start-here`](docs/start-here/index.md)** — in two minutes it explains how the series works and how to help.

Once the website is online, the handbook reads much better there than on GitHub.

## What is in here

| Folder | What it holds |
|---|---|
| `docs/` | The handbook — every guide, checklist and template |
| `data/` | The speaker list and the event list |
| `app/` | The team app (React), embedded in the handbook as the *Team app* page |

## How to read it

The handbook lives in `docs/` as Markdown and is published as a website (MkDocs Material).
The team app is one page inside that same site — *Team app* in the nav. New here? Start with
**[`docs/start-here`](docs/start-here/index.md)**.

To preview locally:

```bash
pip install mkdocs-material mkdocs-git-revision-date-localized-plugin
cd app && npm install && npm run build && cd ..
mkdir -p docs/assets/app && cp -r app/dist/* docs/assets/app/
mkdocs serve
```

## Spot a mistake?

Every page has a pencil icon. Your edit becomes a pull request reviewed by the Editorial Board, then merged. The handbook is meant to evolve — just send the change.
