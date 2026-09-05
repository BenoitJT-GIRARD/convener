# Reporting a security problem

**Report it privately, through GitHub: the *Security* tab of this
repository, then *Report a vulnerability*.** That opens a draft security
advisory only the maintainers can read. It costs nothing, it needs no
account beyond the GitHub one you already have to be reading this, and it
is the only channel on this page.

**Not an issue.** An issue is public from the moment it is opened, and
there is no way to make it private afterwards.

If the *Report a vulnerability* button is not there, private vulnerability
reporting has not been switched on for the repository you are looking at
(Settings → Advanced Security). Switching it on is the operator's act,
on this repository and on every duplicate, and worth doing before the
first registration arrives rather than after.

## What to expect

Reports are read. **No response time is promised, and none should be
inferred.** This is unpaid work by one maintainer.

What does happen, when a report is valid: a fix lands on the default
branch, the advisory is published with it, and you are credited in it
unless you ask not to be. Nothing is backported and no patched version is
issued — an instance takes the fix through the merge it already does with
upstream, so "fixed" and "fixed everywhere" are the same event here,
whenever each operator next merges. `CHANGELOG.md` names the state the fix
landed in, which is a name for a commit on that branch and never a version
anybody goes back to.

## What is in scope

The product's own code, wherever it runs: the three Cloudflare Workers
under `services/`, the workflows under `.github/workflows/` and the secrets
they name, the browser-side encryption of a registration and the
certificate signing and verification behind it, the retention sweep that
destroys an event's key, and the two checks that decide what may leave a
private repository at all — the boundary declaration (`declarations/boundary.yml`)
and the derivation guard (`tools/convener_ops/derivation/repository.py`).

A weakness in a template is worth more to an attacker than the same
weakness in one repository, because every duplicate inherits it. That is
the reasoning for publishing this at all.

## What is out of scope, and where it goes instead

- **Somebody's running instance** — their repository, their settings, their
  secrets, their Workers, their participants' data. That operator is the
  data controller for it and the only person who can act on it: report to
  them, not here. If what you found is a defect in the code they are
  running, it is in scope above and both reports are worth making.
- **Limits this project already documents.** `docs/operating/operations.md` records that whoever holds an
  event's key and its attendance list can pair a survey answer with roughly
  when it arrived, and `docs/handbook/governance/traitement-donnees.md`
  records what a certificate register does and does not hold. A report that
  one of these is true is a report that the documentation is accurate.
- **The absence of a configured integration.** Every external integration
  here is optional and degrades visibly when it is missing, by design.
  The one deliberate exception fails the build outright rather than
  degrading, and it is the one protecting personal data.

## Supported versions

The default branch, and nothing else. There is no release series to
support: this product is duplicated rather than installed, and every
instance is a merge behind the branch that carries the fix. The tags this
repository carries name states of that branch, so that an operator can say
which one they are on; none of them is a version this project maintains
alongside it.
