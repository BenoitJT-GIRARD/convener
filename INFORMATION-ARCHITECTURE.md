# Information architecture

This is the contract the handbook and the app honour. Five rules.

## 1 · One source per piece of information

Each concept, term, rule, step has exactly one home file. If two places talk about it, one is generated from the other.

**Repetition is allowed; copying is not.** A reader who lands halfway down a page needs the rule in front of them, not a link to it — so a passage may appear on two pages, provided the second one **includes** it from the first. A page includes a passage by naming a registry fragment on a line of its own:

```
{{> fragments/board-rules-publication-gate }}
```

The fragment is an entry in `app/src/content/registry.ts` carrying an `anchor`: the same file as the page that owns the passage, scoped to one of its headings. The app replaces the line with the passage, under a line saying which page and section it came from and linking to it. Two rules hold this up, and both are tests: every include resolves to a registered, anchored fragment (`app/tests/transclusion.test.ts`), and no run of prose of a hundred characters or more appears in two served pages (`tools/tests/test_no_literal_copies.py`).

| Topic | Canonical home |
|---|---|
| Editorial line | `docs/governance/editorial-line.md` |
| Roles | `docs/roles.md` |
| The two gates (mechanics) | `docs/governance/board-rules.md` |
| What the Board is, and its yearly meeting | `docs/governance/editorial-board.md` |
| Selection criteria | `docs/governance/selection-criteria.md` |
| Conflict-of-interest policy | `docs/governance/conflict-of-interest.md` |
| Data protection record (registration & certification) | `docs/governance/traitement-donnees.md` |
| Data protection record (speaker & event-lead candidates) | `docs/governance/candidate-data-protection.md` |
| Pipeline statuses | `app/src/data/types.ts` (described in handbook workflow pages) |
| T-minus runbook steps | `app/src/state/phases.ts` |
| Templates | `docs/toolkit/` |
| What each screen of the app is for | `docs/reference/the-workspace.md` |
| Live speaker & event data | `data/speakers.yml` |
| External integrations | `config/integrations.yml`, documented in `docs/reference/operations.md` |
| Which paths belong to this series rather than to the code | `config/boundary.yml`, and each `config/` file's own `owner:` key |
| The address this project is published at | `config/instance.json`, read by `tools/convener_ops/published.py`, `app/scripts/published.mjs` and `site/scripts/published.cjs` |
| A second, invented instance to build as | `instances/example/`, one file per path `config/boundary.yml` hands to the instance |
| The terms this software is under, and what the name is not under | `LICENSE`, whose head carries the term declining the name, and `TRADEMARK.md` |
| The notice both interfaces display in their footer | `NOTICE.json`, read by `site/scripts/notice.cjs` and `app/scripts/notice.mjs` |

## 2 · Doctrine in the handbook, state in the app

The handbook explains *who · what · why*. The app shows *where you are · click to advance*. Never the other way around. The app's own screens contain no explanatory paragraphs; small `↗ in the handbook` links bridge the two.

The handbook content under `docs/` is not a separate site: the React app
fetches it at runtime via the GitHub API and renders it inline — at the point
of action for templates, in the Handbook tab for long-form reading. One app,
one URL space.

## 3 · Same labels everywhere, via a single source

Where the same identifier appears in both surfaces (runbook step labels, pipeline statuses), it lives in a single source file in the repo (`app/src/state/phases.ts`, `app/src/data/types.ts`). The app reads it directly; the handbook pages that describe the workflow are written to match, not generated.

## 4 · Hierarchy by urgency, not by topic

The nav reflects how soon a volunteer needs the page:

- **First** (essential, 5 min read): Start here · Editorial line · Roles.
- **When you act**: Workflow phases · Governance · Templates.
- **Reference, occasional**: Decision log · The workspace · Tools & access · Contacts · Operations · Glossary.

## 5 · Coherent terminology

A single glossary at `docs/start-here/glossary.md` defines every term. Every other page conforms to it. Notable canonical terms:

- **Event Host** — the person who runs a webinar (each webinar has two co-hosting).
- **Editorial Board** — the curatorial body. Always capitalised.
- **Architecte** — the system-design role (intentionally kept in French).
- **Gate** — one of the two Board approvals (lowercase as a common noun).
- **Lead / Approved / Invited / Confirmed / Scheduled / Delivered / Archived / Parked / Decline (board or speaker)** — pipeline statuses, lowercase in prose, kebab-cased in data. There is no *parking lot* and no bare *declined*: both were renamed and a page still using them sends a reader looking for a column that is not there.

---

*This file is the contract. If you find a duplication or a drift, fix it (or open a PR — the Board will review).*
