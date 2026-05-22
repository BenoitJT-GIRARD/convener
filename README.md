# Workshop Series — Operating Handbook

The single source of truth for **The Example Collective Monthly Reading Group (Convener)** — a community-run series of online behavioural-science webinars.

This repository holds everything needed to run the series: the workflow, the runbooks, the speaker pipeline, the templates, the governance, and the archive of past events.

## How to read it

The handbook lives in `docs/` as Markdown and is published as a website (MkDocs Material). New here? Start with **[`docs/start-here/`](docs/start-here/index.md)**.

To preview the site locally:

```bash
pip install mkdocs-material mkdocs-git-revision-date-localized-plugin
mkdocs serve
```

## How to edit it

This is a **living handbook**. Commit directly to `main` — no pull request required; the Git history is the safety net. If you change how something works, update the docs in the same move (the last item of the post-event checklist exists for exactly this).

## Repository structure

| Folder | Contents |
|---|---|
| `docs/` | The handbook — rendered as the website |
| `data/` | Structured data: the speaker pipeline and the event registry (YAML) |
| `archive/` | Artefacts of past webinars, correspondence, strategy documents |
| `app/` | Reserved for the future dynamic layer (Chantier B) |

## Governance in one line

Volunteers contribute in autonomy; the **Editorial Board** curates and validates at two gates; everything is transparent. See **[`docs/roles.md`](docs/roles.md)** and **[`docs/governance/`](docs/governance/editorial-board.md)**.
