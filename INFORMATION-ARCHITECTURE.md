# Information architecture

This is the contract the handbook and the team app honour. Five rules.

## 1 · One source per piece of information

Each concept, term, rule, step has exactly one home file. If two places talk about it, one is generated from the other.

| Topic | Canonical home |
|---|---|
| Editorial line | `docs/governance/editorial-line.md` |
| Roles | `docs/roles.md` |
| The two gates (mechanics) | `docs/governance/editorial-board.md` |
| Selection criteria | `docs/governance/selection-criteria.md` |
| Conflict-of-interest policy | `docs/governance/conflict-of-interest.md` |
| Pipeline statuses | `app/src/data/types.ts` (described in handbook workflow pages) |
| T-minus runbook steps | `app/src/data/runbook.ts` (rendered into handbook via build hook) |
| Templates | `docs/toolkit/` |
| Live speakers & events data | `data/speakers.yml` and `data/events.yml` |

## 2 · Doctrine in the handbook, state in the app

The handbook explains *who · what · why*. The app shows *where you are · click to advance*. Never the other way around. The team app contains no explanatory paragraphs; small `↗ in the handbook` links bridge the two.

The two surfaces share the same shell: the handbook is the entire MkDocs Material site,
and the team app is one page inside it (`team-app.md`). One nav, one chrome, one URL space.
The app uses hash routing for its sub-routes so MkDocs serves a single HTML page.

## 3 · Same labels everywhere, via generation

Where the same identifier appears in both surfaces (runbook step labels, pipeline statuses), it lives in a single source file in the repo. A build hook injects it into the handbook page. The app reads it directly.

## 4 · Hierarchy by urgency, not by topic

The nav reflects how soon a volunteer needs the page:

- **First** (essential, 5 min read): Start here · Editorial line · Roles.
- **When you act**: Workflow phases · Governance · Templates.
- **Reference, occasional**: Decision log · Tools & access · Contacts · Glossary.

## 5 · Coherent terminology

A single glossary at `docs/start-here/glossary.md` defines every term. Every other page conforms to it. Notable canonical terms:

- **Event Host** — the person who runs a webinar (each webinar has two co-hosting).
- **Editorial Board** — the curatorial body. Always capitalised.
- **Architecte** — the system-design role (intentionally kept in French).
- **Gate** — one of the two Board approvals (lowercase as a common noun).
- **Lead / Approved / Invited / Confirmed / Scheduled / Parking Lot / Declined** — pipeline statuses, lowercase in prose, kebab-cased in data.

---

*This file is the contract. If you find a duplication or a drift, fix it (or open a PR — the Board will review).*
