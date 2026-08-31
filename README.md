# Convener

## Two repositories, not one

Running this needs **two repositories on GitHub**: one **private**, holding
the cockpit and the participant data it works on, and one **public**, whose
only job is to be the thing that gets published.

The split is forced, not preferred. `instance/data/speakers.yml` and the per-event
registration files hold personal data, so whatever repository holds them
has to be private — and GitHub Pages will not serve a private repository
without a paid plan, which this project's no-cost constraint rules out. The
public repository is therefore the publication target and nothing else:
continuous integration in the private one builds `site/` and `app/` and
pushes the result into its root. Nobody edits anything there. Every byte in
it is reproducible from the private one, so losing it costs a rebuild.

Anyone standing this up for themselves needs both before anything else
works. `docs/operating/standing-up.md` is the whole path from nothing —
no repositories, no accounts — to a running instance, step by step, with
every step that exists only in a browser written out in full; it is
walkable with a web browser and a text editor, and every account it asks
for has a free tier this project fits inside. That page and the run sheet
an agent follows are both generated from one declaration,
`STANDING-UP.yml`, so an agent shortens the work without the browser route
falling behind it — that route is the one the product is designed around.
`AGENTS.md` says where each rendering lives.
`docs/operating/operations.md` says which settings each repository needs,
and takes over once the instance is standing.

### Which repository is which

| Repository | Visibility | What it is |
|---|---|---|
| `convener` | public | The product — the origin every instance is derived from. |
| `example-cockpit` | private | This instance. Holds the real data. |
| `example-showcase` | public | This instance's publication target. Nobody works in it. |

There is no `convener-vitrine`, and the asymmetry is the whole explanation:
`example-showcase` exists **only** because `example-cockpit` is private and Pages
will not serve a private repository without that paid plan. The product
repository publishes nothing and needs no target of its own: the instance
it carries is the invented one under `instances/example/`, whose declared
address is reserved and answers nowhere, and both publishing workflows
refuse a target that is the repository the build came from. Its
demonstration is that instance, built and served out of a working copy —
`site/README.md` gives the command, and the prefix it says to open at is
the one a real deployment is served under. Creating and pushing that
repository happens once and is written out in
`docs/operating/publishing-the-product.md`, which is the one sequence
`STANDING-UP.yml` deliberately does not declare.

Locally the picture is smaller than that table: the product, and — only
where one person happens to hold both roles — the instance beside it. **An
ordinary instance is one repository on a working machine, not two.**

## What this is

**Convener runs a scholarly seminar series end to end, and costs nothing to
run.** A proposal arrives, an editorial board votes on it, a speaker is
invited and a date is locked, participants register, attendance is matched
against those registrations, certificates are issued and stay verifiable
years later, and the personal data behind all of it is destroyed on a
deadline. There is no database, no server and no subscription: the
repository is the store, continuous integration is the compute, and three
small edge workers hold the three things that have to answer continuously.

**It is written for the people who actually run these series** — volunteer
scholarly societies, reading groups, departmental seminars, early-career
networks — where the work is unpaid, whoever does it changes every year or
two, and there is no budget to lose. Nearly every structural choice here
follows from those three facts: a handover is a repository transfer rather
than a migration, a volunteer's instructions render beside the button they
apply to, and a control that only works when somebody remembers to run it
is treated as no control at all.

An operator duplicates this repository, edits the three files under *What a
duplicate edits* below, and has their own instance.

This repository is also one of those instances: the operational workspace
for our community webinar series, from finding a speaker to certifying
attendance — and the source of the public showcase those webinars are
announced and registered on. See
[`docs/engineering/architecture.md`](docs/engineering/architecture.md) for the full picture: how
the two applications and the public showcase fit together, why the
structural choices were made, where a participant's personal data goes
and when it stops being readable, and how to take this project over.

## Do not fork this repository — duplicate it

**GitHub offers *Fork* as the obvious action on a public repository, and it
is the wrong one here. This is a security instruction, not a preference.**

An instance holds participants' personal data — names, email addresses,
institutional affiliations — so **the repository holding it has to be
private**. Three facts make a fork incompatible with that:

1. **A fork of a public repository cannot be made private.** GitHub does
   not offer the change.
2. **Repositories in one fork network share an object store.** A commit
   pushed to a fork stays reachable from the public parent — permanently,
   by anyone holding or guessing its hash, and after the fork is deleted.
3. So a private-looking fork holding a registration file publishes it by a
   route nobody would think to check, and no setting inside that fork
   closes the route.

**Duplicate instead**: a new *private* repository of your own, holding
these contents, with no fork relationship to this one.
`docs/operating/operations.md` has what to do;
[D-15](docs/engineering/decisions/d-15-publication-topology.md) has the reasoning in
full, including why the product itself is published even so.

## What a duplicate edits

Three files, before the first build:

| File | What is in it |
|---|---|
| `instance/config.json` | Who is publishing, and where. Eleven values: the organisation and its short form, the series, its strapline and its tagline, the forum, the contact address, the proposal form, the cockpit's own repository, the published address, and the edition prefix. While any of them is still the example's, the showcase prints a band above its masthead and the cockpit prints one above its sign-in screen, naming the keys left to fill in. |
| `instance/data/config.yml` | The Editorial Board's GitHub logins, the season, and the thresholds a vote is measured against. |
| `instance/data/speakers.yml` | Your own records. A duplicate starts it empty. |

That is the whole list, and it is short because the separation is declared
and checked rather than intended: [`config/boundary.yml`](config/boundary.yml)
names every path an instance owns, each file under `config/` states its own
answer in its own header, and this repository builds itself as a second,
invented instance on every test run — deleting everything the declaration
hands to the instance, laying
[`instances/example/`](instances/example/README.md)'s files into the holes,
and refusing any trace of the first instance in the output.

Everything else the declaration hands over needs no edit before a first
run, and why is worth knowing:

- **`instance/data/brand.json` is not on the list.** The product ships a palette
  *and* a motif of its own, and one reader takes them whenever an instance
  has written nothing — so a duplicate builds a finished-looking site
  without providing a single design file. Whole file or whole file, never a
  merge of the two, and a palette measuring below AA does not build, yours
  or ours. [D-16](docs/engineering/decisions/d-16-brand-source-of-truth.md) is the
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
[`.github/CODEOWNERS`](.github/CODEOWNERS) names the team every review
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

**Six files, then**: three the boundary declares, and three of the
product's carrying one hand-typed value each — two storage namespace
identifiers and one team handle.

`docs/operating/operations.md` covers the rest of standing an instance up —
the accounts, the secrets, and what degrades without each — and
`docs/operating/standing-up.md` is the ordered path through all of it, from
a person who has neither repository to an instance that runs.

## What is here

Every tracked directory at the root of this repository, with its owner
and what it holds, is one generated table: [*Every directory, and who owns
it*](docs/engineering/architecture.md#every-directory-and-who-owns-it). It is derived
from `config/boundary.yml` and from the repository's own tracked files by
`tools/scripts/generate_directory_map.py`, so a directory added without a
row fails the build.

## How to work on it

```bash
cd app
npm install
npm run dev           # served under the base instance/config.json declares
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

The public showcase is a separate, static project — no sign-in, no secret:

```bash
cd site
npm install
npm start             # served under the prefix instance/config.json declares
```

Validate data:

```bash
cd tools && uv run convener-validate
```

Check which external integrations are configured:

```bash
cd tools && uv run convener-check-config
```

See `docs/operating/operations.md` for what each integration needs, and what
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

- **One entity per speaker.** `instance/data/speakers.yml` carries the whole lifecycle: lead → approved → invited → confirmed → scheduled → delivered → archived (plus `parked`, `decline-board`, `decline-speaker`).
- **State machine.** Status changes are a consequence of explicit gestures (vote, send invitation, log reply, lock date). The free-form status field is gone (except a board-only admin override).
- **Two personas.** Active organizer and board member, served at parity. The inbox adapts to the role.
- **Handbook content rendered inline.** Each runbook step links to the relevant Markdown chunk (template email, instructions) which renders next to the action. No back-and-forth with a separate doc site.
- **The showcase is generated, not hand-built.** The published repository holds no source of its own — continuous integration here builds `site/` and `app/` and pushes the output to its root.

See [`docs/engineering/architecture.md`](docs/engineering/architecture.md) for how these pieces
fit together, the diagram of where personal data goes, and the handover
procedure, and [`docs/engineering/decisions/`](docs/engineering/decisions/index.md) for why each
structural choice was made — one record per decision, what was rejected,
and what it costs. There is no separate design document to read after
them: why the cockpit is shaped the way it is *is* those records.

## Personal data, and who answers for it

**If you run an instance of this software, you are the data controller for
the personal data it holds. The author of this software is not.**

That sentence is here because somebody will assume the opposite on the day
it matters. This product ships the mechanism — a registration encrypted in
the participant's own browser, one key per event, a retention deadline that
destroys that key — and never the judgement. Who is told what, on what
legal basis, for how long, and who answers a participant asking what is
held about them: every one of those is the operator's, because every one of
them is a decision about a processing operation the operator chose to carry
out.

For an operator, concretely:

- **The processing record is yours.**
  [`docs/handbook/governance/traitement-donnees.md`](docs/handbook/governance/traitement-donnees.md)
  and
  [`docs/handbook/governance/candidate-data-protection.md`](docs/handbook/governance/candidate-data-protection.md)
  describe mechanisms a duplicate genuinely shares, which is why a duplicate
  inherits them — but the controller each names is the instance's own, and
  every claim on those pages is one you are making about your own
  processing. Read them as drafts you are adopting, not as cover somebody
  else has given you.
- **The contact address a participant is told to write to is yours**, and
  it is answered by you.
- **Nothing reaches the author of this software.** No telemetry, no phoning
  home, no shared service: the repository is yours, the Actions runs are
  yours, the workers are deployed under your own account. Which is also why
  nobody here can help you when a key is gone.

## Contributing, and what to expect back

**Provided as is. Issues are read. No response is guaranteed.** Saying so
costs a line and saves a reader the guess between "abandoned" and "one
unpaid person, with a day job".

A pull request is expected to leave every gate green — the same
formatting, linting, British-English spelling, type-checking and test
commands continuous integration runs on every push; see
[`docs/engineering/architecture.md`](docs/engineering/architecture.md#contributing) for the
per-directory commands. None of it needs an account or a secret to run.

[`CONTRIBUTING.md`](CONTRIBUTING.md) has the rest: one `Signed-off-by` line
per commit, by which you certify your right to contribute the code, and no
contributor licence agreement to sign.

Found a security problem? Not an issue — [`SECURITY.md`](SECURITY.md) has a
private channel, and says what it does and does not promise.

## Licence

Free software under the [GNU Affero General Public License, version 3 or
later](LICENSE). Section 13 of it is the point: a hosted, *modified* version
has to offer its source to the people using it, so this cannot quietly become
somebody's closed fork.

**If those terms do not suit your use, a separate licence can be negotiated
with the copyright holder.** The AGPL is what this repository offers, and it
is offered to everybody on the same terms; it is not the only licence the
holder is able to grant.

The name and the mark are **not** covered by that grant — a term at the head
of `LICENSE`, under section 7 of the licence itself, declines them, and
[`TRADEMARK.md`](TRADEMARK.md) says what a fork renames and how little an
unregistered mark is actually worth. Both the showcase and the cockpit display
the licence notice in their footer; its text is `NOTICE.json`, and no part of
it is an instance's to configure. See
[D-29](docs/engineering/decisions/d-29-licence-and-attribution.md) for the whole argument,
including the two licence families that were rejected and why.

### No warranty, in ordinary words

The licence states this in capitals and in legal English. Here it is in
neither: **this software comes with no warranty of any kind, and nobody
here is liable for what it does to your data or to anybody else's.**

Two of the things it does are worth reading that sentence twice for:

- **It destroys cryptographic keys, deliberately and on a schedule.** That
  is the mechanism by which a participant's registration stops being
  readable after an event: the key is destroyed, the encrypted file stays,
  and nothing can decrypt it again. There is no recovery, no escrow and no
  support line. A key destroyed early, or an event given the wrong
  retention window, takes its data with it —
  [D-22](docs/engineering/decisions/d-22-key-destruction-not-deletion.md) is why that
  is the design rather than an accident.
- **It processes other people's personal data.** Names, addresses,
  institutional affiliations, attendance and survey answers, belonging to
  people who registered for a talk and never agreed to be anybody's test
  case.

Try it against your own arrangements before it holds anybody's data.

### Citing this

There is a *Cite this repository* button, and [`CITATION.cff`](CITATION.cff)
behind it — GitHub produces APA and BibTeX from that file. For the audience
this is written for, a citation is worth more than any clause of the
licence, which is why it is asked for rather than required.

## Spot a mistake?

Every Markdown file under `docs/` is the source of truth for its content.
Edit on GitHub (pencil icon) — your change becomes a pull request. Once
merged, the app shows the updated content live (cached for ~5 minutes).
