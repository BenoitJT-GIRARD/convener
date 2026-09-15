# D-21 — A certificate's lifecycle

**Status:** Accepted

## Context

A certificate attests attendance at one specific session, and needs a way to
be corrected that cannot, under any automated path, hand someone a fresh
certificate after it was deliberately taken away from them.

## Decision

Four linked points.

1. **The signed duration is bounded by the session itself.** A certificate
   attests presence *at the seminar*, and it is the seminar's own advertised
   length that any accrediting body credits.
2. **A correction is a revocation followed by reissue under a new
   identifier.** The old token still verifies — its signature was genuine —
   and the register marks it revoked. That is what "the register is
   authoritative on state" means in practice.
3. **Reissue lookup has three outcomes:** no matching line → issue; one
   `issued` line → reuse it; **only revoked lines → refuse**, naming the
   reissue command explicitly.
4. **The register holds exactly two states**, `issued` and `revoked`.
   Whether a certificate was delivered is not one of them.

## Rejected

Filtering reissue lookups to `issued` records only. The obvious-looking
approach is a trap: a revoked-and-not-reissued fingerprint would then match
nothing, so an unattended rerun would **silently reissue a certificate to
someone it had deliberately been taken from.** Refusing preserves that
outcome instead of quietly reversing it. The register is authoritative on
**validity**, not on logistics, and its projection is public — delivery
status is neither.

## Cost

Reissue is always an explicit operator action; nothing scheduled may ever
perform it. A reconnection during a session and a second device joining the
same session produce separate attendance lines that are not distinguished
from each other — the duration bound in point 1 covers both regardless.
