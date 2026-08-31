# screenshots

The four pictures `README.md` shows. Nothing else reads them, and nothing
here is drawn by hand.

## Refreshing them

```
cd app && npm run build
cd ../site && npm run build
cd ../tools/visuals && npm run shots
```

`render-readme-shots.mjs` assembles those two builds into the tree the
publishing workflows actually push — the showcase at the path prefix
`instance/config.json` declares, the cockpit one level under it — serves it
on a port the operating system hands out, and captures the four pages on the
same pinned browser the rest of this repository renders with. Its own module
comment says what each picture is allowed to show and where its data comes
from.

**Refresh them whenever either interface changes.** A screenshot in a README
is a claim about what the software does, and a stale one is a false claim
nothing else in this repository would catch.
