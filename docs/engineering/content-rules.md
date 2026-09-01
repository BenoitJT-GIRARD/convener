# Content rules

This is the contract the handbook and the app honour. Seven rules: six about where a page's content sits, and one about how its sentences are written.

## 1 · One source per piece of information

Each concept, term, rule, step has exactly one home file. If two places talk about it, one is generated from the other.

**Repetition is allowed; copying is not.** A reader who lands halfway down a page needs the rule in front of them, not a link to it — so a passage may appear on two pages, provided the second one **includes** it from the first. A page includes a passage by naming a registry fragment on a line of its own:

```
{{> fragments/board-rules-publication-gate }}
```

The fragment is an entry in `app/src/content/registry.ts` carrying an `anchor`: the same file as the page that owns the passage, scoped to one of its headings. The app replaces the line with the passage, under a line saying which page and section it came from and linking to it. Two rules hold this up, and both are tests: every include resolves to a registered, anchored fragment (`app/tests/content/transclusion.test.ts`), and no run of prose of a hundred characters or more appears in two served pages (`tools/tests/repository/test_no_literal_copies.py`).

| Topic | Canonical home |
|---|---|
| Editorial line | `docs/handbook/governance/editorial-line.md` |
| Roles | `docs/handbook/roles.md` |
| The two gates (mechanics) | `docs/handbook/governance/board-rules.md` |
| What the Board is, and its yearly meeting | `docs/handbook/governance/editorial-board.md` |
| Selection criteria | `docs/handbook/governance/selection-criteria.md` |
| Conflict-of-interest policy | `docs/handbook/governance/conflict-of-interest.md` |
| Data protection record (registration & certification) | `docs/handbook/governance/traitement-donnees.md` |
| Data protection record (speaker & event-lead candidates) | `docs/handbook/governance/candidate-data-protection.md` |
| Pipeline statuses | `app/src/data/types.ts` (described in handbook workflow pages) |
| T-minus runbook steps | `app/src/state/phases.ts` |
| Templates | `docs/handbook/toolkit/` |
| What each screen of the app is for | `docs/handbook/the-workspace.md` |
| Live speaker & event data | `instance/data/speakers.yml` |
| External integrations | `declarations/integrations.yml`, documented in `docs/operating/operations.md` |
| How somebody with no repositories and no accounts gets a running instance | `STANDING-UP.yml`, rendered by `tools/scripts/generate_standing_up_doc.py` into `docs/operating/standing-up.md` for a person and by `tools/scripts/generate_standing_up_run_sheet.py` into `docs/operating/standing-up-for-an-agent.md` for an agent — which carries the order and the actor, and reads every step's own content back out of the declaration |
| Which paths belong to this series rather than to the code | `declarations/boundary.yml`, and each configuration file's own `owner:` key |
| The address this project is published at | `instance/config.json`, read by `tools/convener_ops/declaration/published.py`, `app/scripts/published.mjs` and `site/scripts/published.cjs` |
| A second, invented instance to build as | `examples/the-example-collective/`, one file per path `declarations/boundary.yml` hands to the instance |
| The terms this software is under, and what the name is not under | `LICENSE`, whose head carries the term declining the name, and `TRADEMARK.md` |
| How to report a vulnerability, and what a report can expect | `SECURITY.md` |
| What a contributor certifies, and what an issue can expect | `CONTRIBUTING.md` |
| The behaviour expected of anybody taking part, and what enforcement here actually is | `CODE_OF_CONDUCT.md` |
| What each published state changed, and what a merge asks of a duplicate | `CHANGELOG.md`, whose list of the paths a duplicate owns is generated from `declarations/boundary.yml` by `tools/scripts/generate_changelog.py` |
| How to cite this software | `CITATION.cff` |
| The notice both interfaces display in their footer | `NOTICE.json`, read by `site/scripts/notice.cjs` and `app/scripts/notice.mjs` |

## 2 · Doctrine in the handbook, state in the app

The handbook explains *who · what · why*. The app shows *where you are · click to advance*. Never the other way around. The app's own screens contain no explanatory paragraphs; small `↗ in the handbook` links bridge the two.

The handbook content under `docs/handbook/` is not a separate site: the React
app fetches it at runtime via the GitHub API and renders it inline — at the
point of action for templates, in the Handbook tab for long-form reading. One
app, one URL space. Why they are rendered that way rather than built into a
site of their own is
`docs/engineering/decisions/d-18-static-pages-with-islands.md`.

## 3 · Same labels everywhere, via a single source

Where the same identifier appears in both surfaces (runbook step labels, pipeline statuses), it lives in a single source file in the repo (`app/src/state/phases.ts`, `app/src/data/types.ts`). The app reads it directly; the handbook pages that describe the workflow are written to match, not generated.

## 4 · Hierarchy by urgency, not by topic

The nav reflects how soon a volunteer needs the page:

- **First** (essential, 5 min read): Start here · Editorial line · Roles.
- **When you act**: Workflow phases · Governance · Templates.
- **Reference, occasional**: Decision log · The workspace · Tools & access · Contacts · Operations · Glossary.

## 5 · Coherent terminology

A single glossary at `docs/handbook/start-here/glossary.md` defines every term. Every other page conforms to it. Notable canonical terms:

- **Event Host** — the person who runs a webinar (each webinar has two co-hosting).
- **Editorial Board** — the curatorial body. Always capitalised.
- **Architecte** — the system-design role (intentionally kept in French).
- **Gate** — one of the two Board approvals (lowercase as a common noun).
- **Lead / Approved / Invited / Confirmed / Scheduled / Delivered / Archived / Parked / Decline (board or speaker)** — pipeline statuses, lowercase in prose, kebab-cased in data. There is no *parking lot* and no bare *declined*: both were renamed and a page still using them sends a reader looking for a column that is not there.

## 6 · Three trees under `docs/`, one reader each

Which directory a page sits in says who it is written for.

- **`handbook/`** — the volunteer's manual: how a webinar is run, from sourcing a speaker to the certificate that follows it, what each screen of the workspace is for, which tools a volunteer needs and how the Board is reached. The cockpit serves almost everything it renders from here.
- **`operating/`** — the operator's reference: standing an instance up, the settings each repository needs, and the procedures a running instance is kept on. The cockpit serves nothing from here, because every page is addressed to somebody standing an instance up or keeping it running, and `operating/standing-up.md`, generated from `STANDING-UP.yml`, is written for a reader who has no instance to sign in to yet.
- **`engineering/`** — how the system is built and why: the architecture, the decision records, the record schema generated from `app/src/data/types.ts`, and this file. The cockpit serves the decision records and the schema from here, in the same tab as the handbook; both are written from the code rather than from the work, which is what puts them in this tree.

One file sits at the root of `docs/` and it is `README.md`, which GitHub renders when a person opens the directory in a browser: three rows saying who each tree is written for, and a link to each index. Every page is in a tree. `tools/tests/repository/test_docs_directory.py` refuses a tracked file under `docs/` that is in none of the three, and refuses an exception with no reason beside it; the exceptions are named in that module, and that README is the only one. The root of `docs/` once held an index written for a volunteer and a note written for a developer, side by side with nothing saying which was which, and the three trees are what ended that.

## 7 · How a page is written

The six rules above place a page's content. This one shapes its sentences. It applies to every page under `docs/` and to the pages at the repository root.

1. **Do not argue against an alternative the reader has not proposed.** A page says what the thing is and what to do with it. Why it is this and not something else is a decision record under `docs/engineering/decisions/`, and a page that needs the argument links to it.
2. **No hollow antithesis.** "X, not Y", where Y is a suspicion of carelessness nobody voiced — *not an accident*, *not an oversight*, *not a preference* — defends a choice against a reader who was not attacking it. A contrast carrying something the reader can act on is a different sentence: "square brackets, not double braces" is an instruction.
3. **No meta-commentary.** A page does not narrate its own act of stating — *worth saying out loud*, *stated rather than left to be discovered*. Write the sentence and let it stand.
4. **The first paragraph says what the thing is.** Not what it replaces, and not what it is mistaken for.

`tools/tests/repository/test_writing_rules.py` holds 2 and 3. Both are literal shapes with a closed list behind them, checked on every page this section applies to, and it names this page as the one exception: the rules above are stated by quoting the shapes they refuse, so a sweep including it would refuse the sentences that define it.

That module holds neither 1 nor 4, and says so in its own docstring. Whether an alternative was one the reader had in mind, and whether an opening paragraph defines rather than positions, are judgements — a test claiming to make them would pass on every page ever written, which is the shape this repository treats as a failed control. Those two are a reviewer's, and a reviewer's alone.

---

*This file is the contract. If you find a duplication or a drift, fix it (or open a PR — the Board will review).*
