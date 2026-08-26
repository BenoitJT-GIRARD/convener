# Convener

## Two repositories, not one

Running this needs **two repositories on GitHub**: one **private**, holding
the cockpit and the participant data it works on, and one **public**, whose
only job is to be the thing that gets published.

The split is forced, not preferred. `data/speakers.yml` and the per-event
registration files hold personal data, so whatever repository holds them
has to be private — and GitHub Pages will not serve a private repository
without a paid plan, which this project's no-cost constraint rules out. The
public repository is therefore the publication target and nothing else:
continuous integration in the private one builds `site/` and `app/` and
pushes the result into its root. Nobody edits anything there. Every byte in
it is reproducible from the private one, so losing it costs a rebuild.

Anyone standing this up for themselves needs both before anything else
works. `docs/reference/operations.md` says which settings each one needs.

### Which repository is which

| Repository | Visibility | What it is |
|---|---|---|
| `convener` | public | The product — the origin every instance is derived from. Public, so it serves its own demonstration out of itself. |
| `example-cockpit` | private | This instance. Holds the real data. |
| `example-showcase` | public | This instance's publication target. Nobody works in it. |

There is no `convener-vitrine`, and the asymmetry is the whole explanation:
`example-showcase` exists **only** because `example-cockpit` is private and Pages
will not serve a private repository without that paid plan. `convener` is
public already, so Pages serves its pages from the repository itself and a
second one would hold a copy of what the first can already publish.

Locally the picture is smaller than that table: the product, and — only
where one person happens to hold both roles — the instance beside it. **An
ordinary instance is one repository on a working machine, not two.**

## What this is

The operational workspace for our community webinar series, from finding a
speaker to certifying attendance — and the source of the public showcase
those webinars are announced and registered on. See
[`docs/architecture.md`](docs/architecture.md) for the full picture: how
the two applications and the public showcase fit together, why the
structural choices were made, where a participant's personal data goes
and when it stops being readable, and how to take this project over.

## What is here

| Folder | What it holds |
|---|---|
| `app/` | The cockpit (Vite + TypeScript + React), gated by GitHub sign-in — plus the public *islands* (registration, certificate verification) built alongside it and mounted on the showcase's static pages. Built here and published to the separate `example-showcase` repository — see *Publishing the showcase and the application* in `docs/reference/operations.md`. |
| `site/` | Source of the public showcase (Eleventy): the home page, one page per event, the archives, the speaker-proposal entry, the data notice. Generated into `example-showcase` the same way `app/` is — nothing there is hand-edited. |
| `data/` | `speakers.yml` (unified entity), `config.yml` (board, threshold, season), and, per event, an encrypted registration and survey-response file. |
| `docs/` | Handbook content as Markdown — rendered *inside* the cockpit at the point of action and in the Handbook tab — plus reference material such as [`architecture.md`](docs/architecture.md). Not a separate site. |
| `tools/` | The `convener-ops` package: data validation, integration status, the sweep, the public-data filter, certificate issuance and revocation, the retention sweep. |
| `services/auth-proxy/` | The Cloudflare Worker that relays the GitHub device-flow sign-in. |
| `services/form-relay/` | The Cloudflare Worker that verifies a Tally webhook and relays it into a GitHub `repository_dispatch`. Holds a GitHub token. |
| `services/signup-relay/` | The Cloudflare Worker a registration or survey response passes through on its way in — forwards ciphertext it cannot read, and holds a GitHub token. |
| `.github/` | CI: data validation, the public-data filter, certificate issuance and revocation, the retention sweep, publishing the showcase and the cockpit, quality and security gates. |

## How to work on it

```bash
cd app
npm install
npm run dev           # served under the base config/instance.json declares
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
npm start             # served under the prefix config/instance.json declares
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
- **The showcase is generated, not hand-built.** The published repository holds no source of its own — continuous integration here builds `site/` and `app/` and pushes the output to its root.

See [`docs/architecture.md`](docs/architecture.md) for how these pieces
fit together, the diagram of where personal data goes, and the handover
procedure, and [`docs/decisions/`](docs/decisions/index.md) for why each
structural choice was made — one record per decision, what was rejected,
and what it costs. There is no separate design document to read after
them: why the cockpit is shaped the way it is *is* those records.

## Contributing

A pull request is expected to leave every gate green — the same
formatting, linting, British-English spelling, type-checking and test
commands continuous integration runs on every push; see
[`docs/architecture.md`](docs/architecture.md#contributing) for the
per-directory commands. None of it needs an account or a secret to run.

## Licence

Free software under the [GNU Affero General Public License, version 3 or
later](LICENSE). Section 13 of it is the point: a hosted, *modified* version
has to offer its source to the people using it, so this cannot quietly become
somebody's closed fork.

The name and the mark are **not** covered by that grant — a term at the head
of `LICENSE`, under section 7 of the licence itself, declines them, and
[`TRADEMARK.md`](TRADEMARK.md) says what a fork renames and how little an
unregistered mark is actually worth. Both the showcase and the cockpit display
the licence notice in their footer; its text is `NOTICE.json`, and no part of
it is an instance's to configure. See
[D-29](docs/decisions/d-29-licence-and-attribution.md) for the whole argument,
including the two licence families that were rejected and why.

## Spot a mistake?

Every Markdown file under `docs/` is the source of truth for its content.
Edit on GitHub (pencil icon) — your change becomes a pull request. Once
merged, the app shows the updated content live (cached for ~5 minutes).
