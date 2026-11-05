# D-06 — Registration belongs to the organisation; the meeting vendor supplies only the room

**Status:** Accepted

## Context

A direct check of the chosen meeting vendor found it could not do the job of
a registration system, on two independent grounds:

- **No per-event room.** The account itself is the permanent room — there is
  no per-event link for the vendor to generate.
- **No pre-registration.** Name and email are typed at the moment of joining
  and never verified — not an acceptable basis for a named certificate.
- **No credible data-protection footing for the vendor's operating entity**:
  no EU–US Data Privacy Framework certification (current or historical), no
  standard contractual clauses invoked, a privacy policy left unrevised for
  years, no data-processing agreement on offer, and a subcontracting clause
  in its own terms that stops mid-sentence.

(A superficially similar, differently-operated product in the same market
*is* certified to the Data Privacy Framework — a reminder that vendor
due diligence has to be done on the entity actually processing the data, not
on the closest-sounding name.)

## Decision

**The meeting vendor supplies the audio/video room and the recording. The
organisation owns registration and identity.** Each event's page on the
public showcase carries its own registration form; a CI job processes the
submission and sends the confirmation email, which contains the room link.

## What this resolves at once

1. **Data protection.** The vendor never receives a roster — it sees only a
   name typed into a video call, exactly as it would for any public webinar.
   The absence of a data-processing agreement stops being a blocker, because
   no file of registrants is ever handed to it.
2. **Verifiable identity.** A certificate rests on an email address the
   organisation itself confirmed, not one typed unchecked into a meeting
   client.
3. **A link per event.** The organisation's own registration page carries the
   organisation's own branding and privacy notice, and is what a flyer's QR
   code points to.
4. **No vendor lock-in.** Switching video platforms later touches neither
   registrants, nor certificates, nor event pages.

## Rejected

Relying on the vendor for registration, in any form. It fails on identity
verification and data protection at the same time, independently of each
other.

## Cost

The organisation builds and maintains its own registration and confirmation
pipeline rather than using a vendor feature — though that feature does not
exist in a usable form regardless of this decision.
