# D-15 — Private source, public artefact

**Status:** Accepted

## Context

GitHub Pages only serves a private repository on a paid plan, and the
zero-cost constraint rules that out. Three options existed: pay, host
elsewhere, or publish the built output into a public repository.

## Decision

The repository that holds the data and every workflow that touches a secret
stays **private**. Continuous integration publishes the **compiled
output** — both the public showcase and the cockpit application — to a
separate **public** repository, which serves both the showcase and the
certificate-verification page.

Hosting the compiled output in a public repository, rather than with a
third-party host, adds no new account — a third-party host would have
required one, and the project's own operations documentation had already
anticipated needing a fallback of this kind.

**What this does not expose.** The compiled bundle contains no real data —
checked directly in the built artefact, the only addresses present are
fixtures. The cockpit reads the private repository's data at runtime, using
the signed-in volunteer's own token. Someone without repository access can
open the page, sign in, and be refused — a public sign-in page is not a
public account.

**Addresses:**

```
example-instance.github.io/example-showcase/                the showcase
example-instance.github.io/example-showcase/events/<id>/     one page per event
example-instance.github.io/example-showcase/app/             the cockpit
example-instance.github.io/example-showcase/verify/          certificate verification
```

## Rejected

Naming the public repository so it would serve from the organisation's root
and shorten these addresses. Refused on principle: one project among others
should not occupy an organisation's root. The cost is a longer address on a
printed certificate — which carries a machine-readable code alongside it
regardless.

## Cost

The deploy token that publishes to the public repository is no longer
optional — it is what makes the application reachable at all, and the
deploy workflow can no longer rely on GitHub's own Pages actions, which only
publish from the repository they run in.
