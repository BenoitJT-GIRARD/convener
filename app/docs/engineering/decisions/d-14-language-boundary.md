# D-14 — The boundary between the two languages is the schema, not the rule

**Status:** Accepted

## Context

The project is deliberately polyglot: TypeScript owns the browser, Python
owns the CI tooling. A rule that exists in both risks drifting apart. A
review of every real divergence that had occurred between the two sides
found four: a time value read back as the wrong type by serialisation; an
empty login accepted on one side and not the other (a genuine duplicated
*rule*); one status transition still writing an old record shape (a
*schema* mismatch); and one field silently overwritten (also a schema
mismatch). **Three of the four were schema problems, not rule problems.**
Any fix that concentrates on deduplicating the *rule* — including making the
browser decide and reducing the scheduled sweep to only applying that
decision — repairs the one case already best covered by tests and leaves
the other three untouched.

## Decision

The project stays polyglot. A rule duplicated between the two languages is
addressed by **extending the shared boundary fixture**, not by moving which
side decides.

**Rules that follow:**

1. `tools/tests/fixtures/speakers-from-app.yml` is the boundary contract. It
   must cover every shape either side writes — configuration and the output
   of every transition — and both languages must read it. A fixture read by
   only one side is not a fixture; it is a second test suite.
2. No new dependency. Generating shared types from a schema on both sides
   would work, but it is tooling added for a repository this size, against
   the project's own no-new-tooling constraint.
3. A duplicated rule is acceptable **only if** the shared fixture pins it
   end to end, from raw input — not only from an already-normalised state.

## Rejected

**Considered, and deliberately left open rather than closed.** Making the
browser persist a decision in the same mutation as its own action, and
removing that decision from the scheduled sweep entirely. Rejected because
it hands a write to a client that can fail mid-way — exactly what having a
single writer exists to prevent — and because it targets the rule, not the
class of defect actually observed. **This is worth re-opening if a third
rule-level divergence appears** — one occurrence does not justify reworking
how writes happen.

## Cost

Every new cross-language boundary needs its shape added to the fixture and
exercised from both languages, which is more upfront work than trusting one
side to be the reference. In exchange, three of the four divergences that
have actually occurred in this project would have been caught before
shipping.
