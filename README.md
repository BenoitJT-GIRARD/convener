# Convener

**Convener runs a scholarly seminar series end to end — proposals, an
editorial board's votes, invitations, registration, attendance, verifiable
certificates, and the destruction of participants' personal data on a
deadline — for the volunteer-run societies, reading groups and departmental
seminars that have nobody to pay and nothing to pay them with.**

![Convener](assets/screenshots/banner.png)

## What it looks like

**The cockpit**, where a volunteer or a board member works. This is the
demonstration mode: no account, no repository, the example instance's own
invented records.

![The cockpit inbox: two leads to vote on, five webinars needing an action and two lines waiting on the person signed in, each with its speaker and institution](assets/screenshots/cockpit.png)

**A public event page.** One per edition, generated — nobody writes these.
The registration form on it encrypts what a participant types before it
leaves their browser.

![A public event page: the talk title, the speaker, the abstract, and the panel above the registration form](assets/screenshots/event-page.png)

**The verification page.** Anyone holding a certificate can confirm it,
years later, without an account and without sending anybody the certificate
itself.

![The verification page, showing a Certificate Verified panel with the holder, the event, the date and the identifier](assets/screenshots/verification.png)

[![Licence: AGPL-3.0-or-later](https://img.shields.io/badge/licence-AGPL--3.0--or--later-012765)](LICENSE)
[![Cost to run: zero](https://img.shields.io/badge/cost%20to%20run-%E2%82%AC0-012765)](docs/engineering/architecture.md)

## Seeing it run

The demonstration is this product built as the invented series it ships as
its worked example, and it is the whole of one: the showcase, an event page
with its registration form, the certificate verifier, the post-event survey
and the cockpit — the same five surfaces a deployed instance has, with the
same navigation between them.

`.github/workflows/demonstration.yml` builds it and publishes it to this
repository's own GitHub Pages. It builds on every push and rebuilds every
Thursday, and it publishes nothing until the repository variable
`CONVENER_DEMONSTRATION_PAGES` is set to `true` and Pages is pointed at the
`gh-pages` branch — two settings no workflow can make for itself, so until
somebody makes them there is no link here to click.

Build it and serve it yourself, from a real build, with no account and no
data of anybody's:

```bash
cd site && npm install && cd ../app && npm install && cd ../tools
uv run python scripts/demonstration_build.py ../demonstration
cd ../demonstration && python -m http.server 8731
```

Then open <http://localhost:8731/example-showcase/> — the address the
example instance declares, prefix and all, because a build served at a bare
root is a different topology from the deployed one
([D-26](docs/engineering/decisions/d-26-verify-deployed-shape.md)).

The records are the example instance's. What you do to them stays in the
tab you did it in, for as long as that tab is open, and is never sent
anywhere: the cockpit in demonstration mode reads only from the address
that served it and writes nothing at all.

> [!WARNING]
> **Do not fork this repository — duplicate it.**
>
> GitHub offers *Fork* as the obvious action, and it is the wrong one here.
> An instance holds
> participants' names, addresses and affiliations, so the repository
> holding it has to be private — and:
>
> 1. **A fork of a public repository cannot be made private.** GitHub does
>    not offer the change.
> 2. **Repositories in one fork network share an object store.** A commit
>    pushed to a fork stays reachable from the public parent — permanently,
>    by anyone holding or guessing its hash, and after the fork is deleted.
> 3. So a private-looking fork holding a registration file publishes it by
>    a route nobody would think to check, and no setting inside that fork
>    closes the route.
>
> **Duplicate instead**: a new *private* repository of your own, holding
> these contents, with no fork relationship to this one.
> [D-15](docs/engineering/decisions/d-15-publication-topology.md) has the
> reasoning in full.

## Installing

An instance is a duplicate of this repository, three files edited, and a
handful of accounts that all have a free tier this project fits inside.

- **[Standing up an instance](docs/operating/standing-up.md)** — the whole
  path from no repositories and no accounts to a running instance, step by
  step, walkable with a web browser and a text editor.
- **[What a duplicate edits](docs/operating/what-a-duplicate-edits.md)** —
  six files, and what everything else is that nobody has to touch.
- **[The same sequence, written for an
  agent](docs/operating/standing-up-for-an-agent.md)** — if you work with one. Both
  it and the guide are generated from `declarations/standing-up.yml`, so
  an agent cannot shorten the work by getting ahead of the browser route.
- **[What each release asks of you](CHANGELOG.md)** — an update is a merge,
  so every entry names the paths a release reached that are yours rather
  than upstream's, and what to do about each.

## What the architecture is for

Two facts about the people who run these series decide almost everything
here. **The work is unpaid and there is no budget**, so there is no
database, no server and no subscription: the repository is the store,
continuous integration is the compute, and three small edge workers hold
the three things that have to answer continuously. **Whoever does the work
changes every year or two, and is a researcher rather than an engineer**, so
a handover is a repository transfer rather than a migration, a volunteer's
instructions render beside the button they apply to, and a control that only
works when somebody remembers to run it is treated as no control at all.
Knowing a little GitHub is the whole prerequisite.

[**How it is built**](docs/engineering/architecture.md) is the full picture:
the two applications and the public showcase, where a participant's personal
data goes and when it stops being readable, and the handover procedure.
[**The decision records**](docs/engineering/decisions/index.md) are one per
structural choice, with what was rejected and what it costs. Every tracked
directory and every file at the root, with its owner and what it is, is [one
generated
table](docs/engineering/architecture.md#every-path-at-the-root-and-who-owns-it):
a path added without a row fails the build.

### Which documentation is yours

`docs/` is three trees, one reader each, and each opens with what it holds
and what it does not:

- [**`docs/handbook/`**](docs/handbook/index.md) — for a volunteer running a
  webinar.
- [**`docs/operating/`**](docs/operating/index.md) — for the operator
  standing an instance up and keeping it running.
- [**`docs/engineering/`**](docs/engineering/index.md) — for somebody
  changing this code, or deciding whether to build on it.

## Licence, and what you take on

Free software under the [GNU Affero General Public License, version 3 or
later](LICENSE). Section 13 of it is the point: a hosted, *modified* version
has to offer its source to the people using it, so this cannot quietly
become somebody's closed fork. If those terms do not suit your use, a
separate licence can be negotiated with the copyright holder. The name and
the mark are not covered by that grant — [`TRADEMARK.md`](TRADEMARK.md) says
what a fork renames.

**[What you take on](docs/operating/what-you-take-on.md)** is the other half
and is worth the five minutes: run an instance and *you* are the data
controller, not the author of this software; this software destroys
cryptographic keys deliberately and on a schedule, with no recovery and no
escrow; and it comes with no warranty of any kind.

**Provided as is. Issues are read. No response is guaranteed** — one unpaid
person, with a day job. [`CONTRIBUTING.md`](CONTRIBUTING.md) says what a
pull request certifies and which gates it has to leave green;
[`SECURITY.md`](SECURITY.md) has a private channel for a vulnerability, and
says what it does and does not promise; [`CITATION.cff`](CITATION.cff) is
behind GitHub's *Cite this repository* button, which for the audience this
is written for is worth more than any clause of the licence.
