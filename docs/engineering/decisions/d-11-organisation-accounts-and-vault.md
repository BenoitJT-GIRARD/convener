# D-11 — Every account belongs to the organisation, held in a shared vault

**Status:** Accepted

## Context

Transferability depends on no service account ever being tied to one
person's own address — otherwise the system's continuity depends on that
person staying reachable and willing.

## Decision

No service account is ever created with a personal address.

1. A dedicated address belonging to the organisation is created first.
2. A shared, offline password vault is kept outside the repository — in the
   organisation's own shared storage or a password manager, **never
   committed** — with its master password shared out of band with several
   board members, not one.
3. Every account created afterwards (meeting platform, email sending,
   Cloudflare, video channel) is created with that address and stored in the
   same vault.

This is the concrete mechanism behind the project's governance succession
requirement, G-16: the role that sets a system like this up must be able to
stop, at any time, without changing anyone else's ability to keep running it.

## Rejected

Storing credentials inside the repository, even the private one. A private
repository does not prevent leakage if it is ever made public by mistake or
cloned, and speaker records already carry personal data — one more reason
not to add credentials to the same tree.

## Cost

Every new integration needs an explicit account-creation step before it can
be switched on, rather than a developer minting a credential under their own
account to move faster. That step is exactly what keeps the system running
after any one person leaves.
