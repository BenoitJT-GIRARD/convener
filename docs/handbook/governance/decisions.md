# Decision log

One line per decision: what, and why. We only add — never rewrite. This is what stops a changing team from re-arguing the same questions.

Add a row whenever the Board decides something a future member would otherwise have to guess.

## This log, and the register next to it (G-10)

There are two files, and they answer different questions.

- **This log** is written by hand and holds the Board's *reasoning*: the standing choices it made and why it made them. A human writes the "Why" column, because nothing else can.
- **[`register.md`](register.md)** is derived, and holds the Board's *acts*: which record was acted on, on which day, by which member. Nobody writes it. It is regenerated in full from the commit messages on every push to `main`, so an entry cannot be added, corrected or removed there by hand — the next regeneration simply replaces the file. That is the point: if a register entry could be typed, it would be a second source of truth able to disagree with the history it claims to summarise.

The register has no free-text column, only calendar days, identifiers, and phrases from the closed vocabulary in `tools/convener_ops/governance/commit_format.py`. It therefore records that a record changed and who changed it, and it has no place to put a remark about a volunteer. When a volunteer states a reason — for an objection, a recusal, a declined invitation — that reason stays with the record in `instance/data/speakers.yml`, where it can still be corrected. It is deliberately not copied into the register: a register line, once written, never changes, so it must not carry anything that might later need to.

The register begins with the grammar of decision commits, which is younger than the Board. Decisions taken before it have not been reconstituted into it. A short register dates the tooling, not the Board — this log is where the earlier decisions live.

Regenerate it locally with:

```bash
cd tools
uv run convener-register --dry-run   # print it
uv run convener-register             # rewrite the file
```

| Date | Decision | Why |
|---|---|---|
