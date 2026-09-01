# The operators' cockpit

This is the cockpit: the application the Board and the volunteers sign in
to, and it is not the website. The public site anybody can reach without an
account is `site/`, built by a different toolchain from a different
directory.

The same build also produces the three *islands* — the registration form,
the certificate verifier and the post-event survey — which are compiled
here, published inside this bundle's own `dist/`, and mounted on three of
the showcase's static pages. So a change to `src/islands/` changes what a
visitor sees on the showcase without a single file under `site/` moving.

For what this directory is inside the system as a whole, and which parts of
it a duplicate owns, read
[the architecture page](../docs/engineering/architecture.md).

## Running it

```bash
npm install
npm run dev
```

The dev server serves under the path prefix `instance/config.json`
declares, never at a bare root, and the first screen asks for a GitHub
fine-grained personal access token scoped to this repository.

`?demo=1` on any URL skips the sign-in entirely and runs the same
application against `examples/the-example-collective/` — an invented
instance with its own speakers, its own board and its own edition
numbering, carried into the bundle at build time. Nothing in demonstration
mode reaches the network: `src/net/request.ts` is the one door out, and it
is shut.

## The four builds

`npm run build` runs `vite build` four times, and `vite.config.ts` chooses
between four configurations on `--mode`: the cockpit itself, then
`island-signup`, `island-verify` and `island-survey`. Each island is its
own artefact with a fixed, unhashed file name, because the page that loads
it is a Nunjucks template compiled by Eleventy with no manifest to read a
hashed name out of. That file's own comments carry the rest, including why
every substituted value is declared for all four rather than for the one
that references it.

The stylesheet is Tailwind v4 with its theme in `src/index.css` and its
colours read from `src/design/tokens.css`, which
`tools/scripts/generate_brand_css.py` writes from the charter in force. No
hex digit belongs anywhere in this directory.

## What is under `src/`

| Directory | What it holds |
|---|---|
| `auth/` | Signing in: the device flow, the token, and who the signed-in person is. |
| `components/` | The pieces screens are assembled from — the layout, the buttons, the journey checklist. |
| `content/` | The handbook, fetched from GitHub at run time: which pages are registered, how a template's substitutions resolve, and how an included passage is pulled from the page that owns it. |
| `data/` | The records themselves: the types, the YAML reader and writer, the validator, and the provider every screen reads them through. |
| `design/` | The charter tokens and the motif, both generated. |
| `github/` | The API client, the two calls that read and write a file, and the errors they raise. |
| `islands/` | The three public components mounted on the showcase's pages, one directory each. |
| `net/` | The one place this bundle makes a request at all. |
| `screens/` | One module per tab of the cockpit. |
| `settings/` | The settings screen's own logic: which declaration a field edits, what bound it refuses, and the surgical edit that leaves the rest of a file alone. |
| `signup/` | Encrypting a registration in the browser, to a key only the workflow can read. |
| `state/` | Every rule the records are read under: the governance thresholds, the journey phases, the transitions, the working-day deadlines. |
| `survey/` | The same encryption for a survey response, and whether an event's survey is open. |
| `verify/` | Checking a certificate's signature against the published keys. |

`scripts/` beside `src/` is the build's own plumbing — the copy steps that
run before every `dev` and `build`, and the modules `vite.config.ts` reads
a declaration through. `tests/` mirrors `src/`, one directory per row of
the table above, plus `scripts/` for those and `helpers/` for what several
modules share.
