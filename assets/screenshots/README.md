# The pictures the front page shows

Every picture `README.md` shows. Nothing else reads them, and nothing here is
drawn by hand.

They fall into three sets and one of them is not a page. **The banner** is the
mark on its own ground. **Six pages** are what a visitor and what the team
each see -- the showcase, an event page, the certificate verifier, and the
cockpit's inbox, pipeline and diversity screens -- all photographed in one
frame, so the front page scales them by one factor and a word is read at the
size the application sets it at. **Four posters** are the same generated
poster in each charter a duplicate may name, which is how the front page says
that the palette is chosen rather than given; they are the only pictures here
the renderer does not compose itself, because the composition is Python's
(`visual.render_announcement`) and the fixture is the boundary between the two
languages, never the code.

## Refreshing them

```
cd tools
uv run --frozen python scripts/render_readme_shots.py
```

That builds this repository as the instance `examples/the-example-collective/` declares —
the same manoeuvre `tools/tests/repository/test_second_instance.py` performs — and runs
`tools/visuals/render-readme-shots.mjs` inside the result, which assembles the
two builds into the tree the publishing workflows actually push, serves it on a
port the operating system hands out, and captures every page on the same
pinned browser the rest of this repository renders with. The PNGs are copied
back over the tracked ones, and the set is checked against what the index
holds rather than against what the run happened to write.

**The renderer refuses to run anywhere else.** Its first act is to compare the
declaration it can see against `examples/the-example-collective/instance/config.json`, value
by value, and stop while any of them is this repository's own. A masthead is
compiled into a build rather than fetched by it, so a picture taken here would
carry this series' name into files the derived public repository publishes
verbatim and no guard can read: `convener-check-derivation` reports the
non-text blobs it did not read on every run, and the second instance's sweep
skips a `.png` for the same reason. Both scripts' own comments carry the rest of
that reasoning, and `tools/tests/scripts/test_readme_shots.py` runs the refusal rather
than reading it.

**One day, twice pinned.** The renderer hands each page a fixed `Date`
before anything in it runs, and this script fixes the day the example
instance's own records are dated against
(`tools/scripts/example_dates.py`) to the same one. Both are needed and
they hold different halves: without the first, a day count printed on a
screen goes up every night; without the second, the records themselves
move by a week every seventh night, because they follow the week they are
read in. Measured: with the day free, two runs a fortnight apart produce a
different `event-page.png`; with it pinned, two runs produce byte-identical
files. The day is the one the certificate on the
verification shot says its holder attended, read off
`tools/tests/fixtures/certificate-verification.json` rather than written
down anywhere.

**Refresh them whenever either interface changes.** A screenshot in a README is
a claim about what the software does, and a stale one is a false claim nothing
else in this repository would catch.
