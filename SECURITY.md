# Reporting a security problem

**Report it privately, through GitHub: the *Security* tab of this
repository, then *Report a vulnerability*.** That opens a draft security
advisory only the maintainers can read. It costs nothing, it needs no
account beyond the GitHub one you already have to be reading this, and it
is the only channel on this page.

**Not an issue.** An issue is public from the moment it is opened, and
there is no way to make it private afterwards. Somebody who finds a hole
and has nowhere private to put it does one of two things: publishes it, or
gives up. Both are worse than reading it here first.

**Not an email address either.** There is deliberately none on this page,
for the same reason `TRADEMARK.md` gives for its own: this file is
published, and a published address is one more thing for a scraper to
collect. The private advisory is the address.

If the *Report a vulnerability* button is not there, private vulnerability
reporting has not been switched on for the repository you are looking at
(Settings → Advanced Security). On this one it is. On a duplicate it is
that operator's to switch on, and worth doing before the first
registration arrives rather than after.

## What to expect

Reports are read. **No response time is promised, and none should be
inferred.** This is unpaid work by one maintainer, and a page claiming a
72-hour acknowledgement it cannot honour would be worse than this
paragraph: the first missed deadline would teach every later reporter that
nothing here means anything.

What does happen, when a report is valid: a fix lands on the default
branch, the advisory is published with it, and you are credited in it
unless you ask not to be. There are no releases and no backports — an
instance takes the fix through the merge it already does with upstream, so
"fixed" and "fixed everywhere" are the same event here, whenever each
operator next merges.

## What is in scope

The product's own code, wherever it runs: the three Cloudflare Workers
under `services/`, the workflows under `.github/workflows/` and the secrets
they name, the browser-side encryption of a registration and the
certificate signing and verification behind it, the retention sweep that
destroys an event's key, and the two checks that decide what may leave a
private repository at all — the boundary declaration (`config/boundary.yml`)
and the derivation guard (`tools/convener_ops/derivation.py`).

A weakness in a template is worth more to an attacker than the same
weakness in one repository, because every duplicate inherits it. That is
D-15's own reasoning for publishing this at all, and it is the reason a
report about the product matters more here than a report about any single
instance.

## What is out of scope, and where it goes instead

- **Somebody's running instance** — their repository, their settings, their
  secrets, their Workers, their participants' data. That operator is the
  data controller for it and the only person who can act on it: report to
  them, not here. If what you found is a defect in the code they are
  running, it is in scope above and both reports are worth making.
- **Limits this project already documents rather than claims to have
  closed.** `docs/reference/operations.md` records that whoever holds an
  event's key and its attendance list can pair a survey answer with roughly
  when it arrived; `docs/governance/traitement-donnees.md` records what a
  certificate register does and does not hold; `TRADEMARK.md` records that
  the mark is unregistered and what that is worth. A report that one of
  these is true is a report that the documentation is accurate.
- **The absence of a configured integration.** Every external integration
  here is optional and degrades visibly when it is missing, by design
  (D-13). The one deliberate exception fails the build outright rather than
  degrading, and it is the one protecting personal data.

## Supported versions

The default branch, and nothing else. There is no release series to
support: this product is duplicated rather than installed, and every
instance is a merge behind the branch that carries the fix.
