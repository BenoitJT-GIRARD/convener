# Engineering

For someone changing this code, reviewing a change to it, or deciding
whether to build on it at all.

## What is here

- **[Architecture](architecture.md)** — how the two applications, the
  showcase and the three edge workers fit together, where a participant's
  personal data goes and when it stops being readable, the per-directory
  commands a pull request has to leave green, and the handover procedure.
- **[Decision records](decisions/index.md)** — one record per structural
  decision, with what was rejected and what it costs. The codebase cites
  them by number.
- **[Data schema](schema.md)** — every field of the record store, its
  type and its enumerated values, generated from `app/src/data/types.ts`
  and refused by continuous integration when the two drift.
- **[Content rules](content-rules.md)** — the seven rules the
  documentation itself is held to: one home per piece of information,
  doctrine in the handbook and state in the app, one glossary, these three
  trees, and how a page's sentences are written.

## What is not here

**How to run a webinar**, and how to run an instance of this software.
Those are [`handbook/`](../handbook/index.md) and
[`operating/`](../operating/index.md).
