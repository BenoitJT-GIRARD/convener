# D-22 — Destroying the key makes data unreadable; deleting the file does not

**Status:** Accepted

## Context

Removing a committed, encrypted file from the working tree does not make it
unreadable — git history keeps it regardless of what the current tree
contains. Only destroying the key that could decrypt it carries any real
guarantee.

## Decision

Past the retention window, **the private key is destroyed and the
ciphertext stays committed.** The data becomes permanently *unreadable*,
never *absent*.

Leaving the unreadable block in place says exactly what this guarantees;
removing it instead would teach the next person that deletion is what
protects the data, and invite them to skip the key.

## A deliberate exception to D-13

Every other integration in this system degrades gracefully when
unconfigured ([D-13](d-13-deferred-configuration.md)). This one does not:
**the absence of the permission needed to destroy a key must fail the
retention job loudly, not pass it.** Any other missing integration degrades
a feature; a retention job that reports success without having destroyed
anything would assert a promise was kept when it was not. A daily red badge
is the correct pressure to keep on a promise with legal weight.

## Rejected

Deleting the file as the retention action, and erasing data early by
rewriting git history. Rewriting history to erase one person's data reaches
**every** store that carries them, not the one record that needed it.

## Cost

A repository that has "erased" a person's data still contains their
ciphertext, forever — the entire guarantee rests on the key, which must
therefore be independently verified: a test decrypts *neighbouring* records
after an erasure and compares their envelopes byte-for-byte, to confirm an
erasure that quietly re-encrypted everyone would be caught, not mistaken for
success.
