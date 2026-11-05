# D-23 — One independent envelope per record, and its byte boundaries matter

**Status:** Accepted

## Context

[D-22](d-22-key-destruction-not-deletion.md)'s guarantee — that removing one
person's data leaves everyone else's untouched — only holds if the storage
shape allows it.

## Decision

Every per-event encrypted store — registrations, questionnaire answers,
attendance exports — uses **one independent envelope per record**, never a
single combined block. This is what makes D-22 possible: removing one
record leaves every other one intact, byte for byte. With a single block,
touching one record touches all of them.

## Two things learned about failure and cross-language agreement

**Every line failing to decrypt is not the same signal as some lines
failing.** Some undecryptable lines mean a damaged file, and that is
tolerated. **Every** line failing means the **wrong file** — encrypted under
a different event's key, most plausibly copied to the wrong identifier by
mistake. Reporting that case as "nobody attended" is the one reading that is
certainly wrong.

**The two languages have to agree in bytes, not just in value.** Plaintext
is padded to a fixed size before encryption — this *removes* the length
side-channel rather than merely documenting it, since otherwise the size of
the ciphertext would reveal the size of the answer underneath. And both
languages' encoders have to produce the same JSON bytes for the same value:
without matching output settings, one language escapes non-Latin characters
into six bytes apiece where the other does not, and a length cap counted in
characters would let through exactly what byte-based padding was built to
stop.

## Rejected

One encrypted block per event, covering every record inside it.

## Cost

More individual encrypted objects to manage per event, and a small, fixed
padding overhead added to every record regardless of its real size.
