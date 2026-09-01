# The pictures the front page shows

The four pictures `README.md` shows. Nothing else reads them, and nothing
here is drawn by hand.

## Refreshing them

```
cd tools && uv run --frozen python scripts/render_readme_shots.py
```

That builds this repository as the instance `examples/the-example-collective/` declares —
the same manoeuvre `tools/tests/repository/test_second_instance.py` performs — and runs
`tools/visuals/render-readme-shots.mjs` inside the result, which assembles the
two builds into the tree the publishing workflows actually push, serves it on a
port the operating system hands out, and captures the four pages on the same
pinned browser the rest of this repository renders with. The four PNGs are
copied back over the tracked ones.

**The renderer refuses to run anywhere else.** Its first act is to compare the
declaration it can see against `examples/the-example-collective/instance/config.json`, value
by value, and stop while any of them is this repository's own. A masthead is
compiled into a build rather than fetched by it, so a picture taken here would
carry this series' name into four files the derived public repository publishes
verbatim and no guard can read: `convener-check-derivation` reports the
non-text blobs it did not read on every run, and the second instance's sweep
skips a `.png` for the same reason. Both scripts' own comments carry the rest of
that reasoning, and `tools/tests/scripts/test_readme_shots.py` runs the refusal rather
than reading it.

**Refresh them whenever either interface changes.** A screenshot in a README is
a claim about what the software does, and a stale one is a false claim nothing
else in this repository would catch.
