# What a duplicate edits

Six files, and no more. Three the boundary declares, and three of the
product's carrying one hand-typed value each.

## The three the boundary declares

Before the first build:

| File | What is in it |
|---|---|
| `instance/config.json` | Who is publishing, and where. Eleven values: the organisation and its short form, the series, its strapline and its tagline, the forum, the contact address, the proposal form, the cockpit's own repository, the published address, and the edition prefix. While any of them is still the example's, the showcase prints a band above its masthead and the cockpit prints one above its sign-in screen, naming the keys left to fill in. |
| `instance/data/config.yml` | The Editorial Board's GitHub logins, the season, and the thresholds a vote is measured against. |
| `instance/data/speakers.yml` | Your own records. A duplicate starts it empty. |

That is the whole list, and it is short because the separation is declared
and checked rather than intended: [`declarations/boundary.yml`](../../declarations/boundary.yml)
names every path an instance owns, each configuration file states its own
answer in its own header, and this repository builds itself as a second,
invented instance on every test run — deleting everything the declaration
hands to the instance, laying
[`examples/the-example-collective/`](../../examples/the-example-collective/README.md)'s files into the holes,
and refusing any trace of the first instance in the output.

## What the declaration hands over and nobody has to touch

Everything else the declaration hands over needs no edit before a first
run, and why is worth knowing:

- **`instance/data/brand.json` is not on the list, and a duplicate arrives
  without one.** The product ships a palette *and* a motif of its own, and
  `instance/config.json` arrives naming them (`"charter": "convener"`) — so a
  duplicate builds a finished-looking site in the product's navy and coral
  without providing a single design file. Change that one word to name
  another directory under `assets/brand/`, or delete the line and write your
  own values into `instance/data/brand.json`. Whole file or whole file,
  never a merge of the two, and a palette measuring below AA does not
  build, yours or ours.
  [D-16](../engineering/decisions/d-16-brand-source-of-truth.md) is the
  argument.
- **`instance/actions-budget.yml`, `instance/queue-drain.yml` and
  `instance/registration-lanes.yml`** carry numbers rather than identity: an
  Actions allowance, a queue alarm, the distance to an event at which a
  registration stops queueing. The shipped values work. They are worth
  re-cutting once a series has a rhythm, and each file says against what.
- **`instance/keys/`, `instance/public-data/`, and the ledgers under
  `instance/data/`** are written, never authored. Generating an event key
  or a signing key is an operator's act; everything under
  `instance/public-data/` is derived from `instance/data/` by this
  project's own commands and committed by a workflow.
- **`docs/handbook/governance/register.md`** is a total re-rendering of a
  repository's own commit history, rewritten by a scheduled job on every
  push. A duplicate inherits ours, and its own next push replaces it.

## The three the product owns

Three files is the list for a first *build*, and it is the list for a first
deploy too. Two of the three edge workers still need one value a duplicate
fills in by hand, in a file the product otherwise owns: the identifier of
the storage namespace each binds to, which does not exist until
`wrangler kv namespace create` has printed it. Two other values used to be
on that list and are not: the origin those workers answer cross-origin
requests for, and the repository the two of them dispatch into. Neither is
written down anywhere but `instance/config.json` now — the deploy workflow
derives each and passes it to `wrangler deploy`, so there is nothing to
correct and nothing that can disagree. The second of the two was the more
expensive to leave: it sat in the workers' own source rather than in their
configuration, so nothing ever told a duplicate to change it, and a relay
left uncorrected would have gone on writing into this instance's
repository. `docs/operating/standing-up.md` gives the namespace step as a
step of its own.

**One more product file carries a value nothing can derive for it, and a
duplicate meets it before its first pull request.**
[`.github/CODEOWNERS`](../../.github/CODEOWNERS) names the team every review
request goes to, `@<organisation>/editorial-board`, and the organisation
half is the owner of `instance/config.json`'s `identity.repository`.
GitHub parses that file itself, before any code of this project's can
run, so it cannot read the declaration the way the origin and the
repository now do; generating it with a `--check` in continuous
integration was the alternative, and it keeps a copy honest without
removing it, at the price of a Python toolchain in a sequence a text
editor has to be enough for. Left uncorrected it sends every review
request to an organisation the duplicate does not own, and
`tools/tests/declaration/test_published.py::test_the_literals_that_cannot_read_the_declaration_still_agree_with_it`
goes red on the first run.

## Where the rest of it is

`docs/operating/operations.md` covers the rest of standing an instance up —
the accounts, the secrets, and what degrades without each — and
[Standing up an instance](standing-up.md) is the ordered path through all of
it, from a person who has neither repository to an instance that runs.
