# The pinned rendering harness

A small Node package that opens a page in a browser and takes a picture of
it. Nothing here ships to anybody: no visitor loads a file from this
directory, and no page of the showcase or the cockpit imports one.

It is driven from `convener_ops`, which composes the HTML first and then
calls one of these scripts to render it. Three of them exist:
`render-and-compare.mjs` renders one fixed, invented fixture and compares
the result against the committed reference images beside it;
`render-production.mjs` renders the real editions a command has already
written out; `render-readme-shots.mjs` takes the pictures the repository's
front page shows. `check-templates.mjs` and `check-posters.mjs` are the two
checks run over what comes out.

`browser.mjs` renders nothing and opens no page. It is the one place this
repository says what a browser is launched with, and it carries the whole
of the argument for the single flag it ever passes. All five scripts above
launch through it, and so does `site/scripts/check-a11y.mjs`, which is
handed a browser the machine already had and is given no flag at all. Read
that file before adding an argument to any launch.

`puppeteer` — the full package, with its own bundled Chromium — is the one
dependency, and it is isolated here rather than added to `site/` or `app/`
so that only the jobs that actually render pay for the download. Pinning
the engine in this package's own lockfile is what makes a red comparison
mean *the picture changed* rather than *the runner changed*.

```bash
cd tools/visuals
npm ci
npm run check
```

`npm run update-references` rewrites the committed reference images, and is
run deliberately after a change to what is drawn, never to make a failing
comparison pass.
