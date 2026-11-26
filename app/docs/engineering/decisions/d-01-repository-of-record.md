# D-01 — The repository is the source of truth; no database

**Status:** Accepted

## Context

The project runs on two non-negotiable constraints: zero recurring cost, and
transferability — no account, secret or service may be tied to one person. A
hosted database or application backend fails both. It acquires a billing
owner, and a project built on someone's personal account of a paid service
does not survive that person leaving.

## Decision

There is no database and no application backend. The handbook, templates,
governance records, configuration and speaker data all live as
version-controlled files in the organisation's own private repository.

This does not mean every kind of data belongs in git in the same way. The
relevant split is not "git versus a database" but **which population**:

| Population | Volume | Treatment |
|---|---|---|
| Speakers | tens per year, professional contacts | plain text, in the private repository |
| Participants (registration, attendance, certificates) | hundreds per event | never committed in plain text — see [D-02](d-02-participant-data-encryption.md) |

## Rejected

A hosted backend (a managed database, an application platform). It would
have been quicker to stand up, but it creates exactly the kind of dependency
the project is built to avoid: an owner, a bill, and an account that outlives
no one but the person who opened it.

## Cost

Everything the system needs to run has to fit in files a human can review in
a pull request — there is no schema migration tool, no query layer, no admin
console. In exchange, git already provides an immutable audit log of every
change, for free, and the repository is exactly as transferable as any other
asset the organisation owns.
