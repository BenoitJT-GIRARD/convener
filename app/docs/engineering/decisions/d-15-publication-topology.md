# D-15 — A private instance, a public product

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
<owner>.github.io/<repository>/                the showcase
<owner>.github.io/<repository>/events/<id>/    one page per event
<owner>.github.io/<repository>/app/            the cockpit
<owner>.github.io/<repository>/verify/         certificate verification
```

The two halves come from `instance/config.json`'s `published_url` and are
written down nowhere else — including the repository this build pushes
into, which is derived from that same address
(`published.Published.publish_repository`) rather than named beside it.

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

## Amendment — the product's own source is public too

The decision above was taken when there were two repositories and the source
was in the private one. There are three now: the product itself is published,
as a template for anyone who wants to run a series of their own, and the
threat model was re-read before that push rather than after it.

**Which is which.** The **instance** repository is private and holds the
records, the keys and every secret. The **published output** repository is
public and holds the compiled showcase and application. The **product**
repository is public and holds the code, the decisions, the workflows and an
invented example instance — and nothing else: what belongs to an instance is
enumerated in `declarations/boundary.yml`, and a check runs over every blob of every
reference before anything is pushed.

**Obscurity was never the protection, and publishing proves it rather than
weakening it.** What the product's source discloses is which workflows exist,
which secret each one names, where keys live, exactly what a relay accepts
from the public internet, what its limits are, and how long a registration
stays readable. None of that is a credential and none of it is a datum. Two
of those are better published than not: the validation a relay performs on
untrusted input is a parser, which gains from being read, and a retention
period is a promise the people whose data it concerns are entitled to see.

**What publication costs.** An
attacker no longer has to work out where the weak points are: the scheduled
jobs are visible, so the running cost of an instance can be computed instead
of probed; the secret-bearing workflows are indexed by the monitor that
watches them; and a weakness in a template is worth more than the same
weakness in one repository, because every duplicate inherits it. The answer
to that is not to publish less. It is that every control here has to hold
against somebody who has read it — which is the standard the cryptography in
this project was already held to, and is now the standard for the rest.

**Two consequences, and each of them is a control.**

**An instance repository must be private, and it must not be a fork.** GitHub
offers "Fork" as the obvious action on a public repository, and it is the
wrong one here. Repositories in a fork network share an object store: a commit
pushed to a fork stays reachable from the public parent, permanently, even
after the fork is deleted. An instance holds participants' personal data, so
forking would publish it by a route nobody would think to check. Duplicate the
template instead — the entry documentation makes this its first practical
instruction for exactly this reason.

**A value that belongs to an instance may not sit in a product file.** The
boundary already says so for merges; publication makes the same rule a
security rule. A relay that names the repository it writes into, or an origin
written into a deployment file, publishes which private repository a
write-capable token reaches — which is the target, not the key. The example
instance's own values are laid into those files before anything is published.

**What this does not change.** The compiled output repository is still public
for the reason given above, and still carries no real data. An instance that
duplicates this template is its own data controller and makes its own
disclosure decisions; the product ships the mechanism, never the judgement.
