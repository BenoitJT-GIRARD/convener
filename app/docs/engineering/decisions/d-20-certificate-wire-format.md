# D-20 — A certificate transports the exact bytes it signs

**Status:** Accepted

## Context

Verifying a certificate by recomputing a canonical form from its parsed
fields requires every verifier — in more than one language — to reproduce
field ordering, separators and escaping byte-for-byte. Measured, this does
not hold: Python renders a number one way where JavaScript renders it
another, and the two disagree on Unicode normalisation for accented
characters — exactly the kind of content a certificate actually carries, a
person's name and a number of hours.

## Decision

The token carries the **signed bytes themselves**, encoded, in the manner of
a JWS. A verifier checks the signature **against the bytes it received**,
and only then parses them — never the reverse, and never by recomputing a
canonical form.

**Order matters.** Verify before parsing: the bytes are only ever
interpreted once a key has confirmed them. The outer envelope necessarily
gets parsed before it is authenticated — that is JWS's own shape, and it is
unavoidable — but the **payload** is never parsed before its signature is
checked. This module is the reference implementation other verifiers are
written against, and a future port written from the code rather than from
the rule could otherwise inherit "parse unauthenticated bytes" in a language
whose parser nobody chose carefully.

## Rejected

Verifying by recomputing a canonical form from parsed fields and comparing
it to the signature.

## Cost

None beyond the inherent one: an envelope is unavoidably parsed before it is
authenticated. Everything past that boundary — the payload — is
authenticated before it is ever interpreted.
