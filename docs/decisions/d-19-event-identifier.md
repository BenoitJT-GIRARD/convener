# D-19 — An event's identifier is its edition code, lower-cased

**Status:** Accepted

## Context

Three independent surfaces — the published event key, registration, and the
certificate — all need to agree on what "this event" means. Two
independently maintained identifier rules would eventually drift apart.

## Decision

`event_id` **is** the edition code, lower-cased: an edition `MRG-4` is event
`mrg-4`, whatever prefix the instance declares (`instance/config.json`'s
own `edition_prefix`). Nothing else stands in as an identifier. A duplicate edition code is
already rejected as a validation error upstream, so uniqueness does not need
re-establishing here.

## Rejected

Any surface inventing its own identifier scheme.

## Cost

Every new surface has to derive the identifier this one way rather than
picking whatever is convenient locally — including secret names, which fold
`.` and `-` to `_`.
