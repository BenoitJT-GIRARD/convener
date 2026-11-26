# D-05 — The meeting platform sits behind an interface

**Status:** Accepted

## Context

An earlier arrangement fell back to a university's own video-conferencing
account when the organisation had none of its own. That recreated exactly
the kind of dependency the project exists to remove: a webinar's video
platform depended on one collaborator's continued goodwill and institutional
access, and it had already failed in practice — an unavailable contact, a
link borrowed from another institution. Separately, the chosen meeting
vendor's API is young: an early, versioned-as-unstable release, with routed
but undocumented endpoints and no published rate limit.

## Decision

A `Platform` interface — retrieve the room, retrieve attendance, retrieve
the recording, remove the recording — with two implementations: the chosen
vendor's adapter (the default), and a manual adapter that takes a hand-typed
link as a last resort. Neither implementation depends on the other, and
nothing in the system requires either to exist for the rest of the system to
run.

## Rejected

Falling back to an institutional account belonging to a collaborator. It
solves the immediate gap but reproduces the dependency this decision exists
to remove, and that dependency has already caused real outages.

## Cost

An abstraction layer to maintain for a vendor whose undocumented API could
change without notice, and a manual mode that captures no attendance data
automatically — an organiser must record who attended by hand when it is in
use.
