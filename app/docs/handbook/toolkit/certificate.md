# Certificate of attendance

*Generated automatically, once per eligible attendee, by
`tools/convener_ops/journey/certificate.py` and delivered by e-mail --
never committed to this repository, ever, for any attendee (this project is
categorical about it: no document naming a person is ever deposited here).
Nobody opens this page and fills it in by
hand, so its placeholders are written in **square brackets**, not double
braces, the same convention
[Registration confirmed](emails/registration-confirmed.md) uses for the same
reason. Kept here anyway, so a board member can read what a certificate says
without opening the Python module that renders it.
`tools/tests/journey/test_certificate.py` pins this page's field list against that
module's own `signing.PAYLOAD_FIELDS` and `certificate.py` constants, so the
two cannot quietly say different things.*

*What is signed and what is furniture: **name, event, date, duration in
hours and the identifier are the signed payload** -- exactly the five fields
`tools/convener_ops/journey/signing.py::PAYLOAD_FIELDS` allows, no more, no less. The
organiser's name and the verification address below are document furniture,
not signed facts (both are content the certificate carries, but
`signing.sign` would refuse a payload that tried to include them) -- a
verifier reads them off the page, never off the cryptographic payload,
because neither one is a fact about the attendee that needs attesting.*

---

**{{ instance.organisation }}**

## Certificate of attendance

This certifies that **[the participant's full name]** attended
**[the event's title]**, held on **[the event's date]**, for
**[the duration, in hours]**.

Identifier: **[the certificate's identifier]**

Verify this certificate at: **[the verification address]**

[a machine-readable code -- a QR, encoding the verification address above,
which itself carries the signed token -- so a reader can confirm this
certificate offline, without an account and without asking us anything.
The address is meant to be scanned or clicked, never typed by hand: it
carries the signed token itself, not only the identifier, so it is far
longer than the identifier printed above it.]

---

## Notes for whoever reads this page

- **Who receives one.** Every attendee `tools/convener_ops/journey/attendance.py`'s
  `eligible_attendees` names for this event -- present, matched to our own
  registration (never the platform's own, self-typed name), for at least
  the configurable share of the session `instance/data/config.yml`'s
  `eligibility_share` sets. Eligible is a calculation; issuing
  one is `tools/convener_ops/cli/journey/certificate.py::issue_certificates`' own decision, made
  once per attendee, not automatic from eligibility alone.
- **The name comes from our registration, never from the platform.** A
  display name typed into the meeting platform is never trusted directly
  (the whole matching cascade exists because it cannot be) -- the
  name on this certificate is `[first name] [surname]`, exactly as
  submitted at registration.
- **The duration is rounded to the nearest quarter hour, ties rounding
  up** -- `tools/convener_ops/journey/certificate.py::duration_hours`'s own documented
  rule, chosen because accreditation bodies read this figure and quote
  continuing-education credit in quarter- or half-hour units, not to five
  decimal places.
- **The identifier is random, not derived from the address.** A
  deterministic identifier would double as a way to test a guessed address
  against the public register; this one carries no information about who
  holds it. It is the only column `instance/public-data/certificates-public.json`
  ever publishes, alongside the certificate's current state (issued or
  revoked) -- never a name, an address, or the salted fingerprint our own
  internal register keeps instead.
- **Verification is offline.** The verification address carries the signed
  token itself, so the verification page checks the signature the moment
  it loads, against public keys it already has embedded -- no request to
  us for the payload. The one thing it does still ask us, over the network,
  is whether this identifier is currently revoked, by reading the public
  projection above.
- **A revoked certificate still verifies cryptographically.** Revocation
  is recorded in our internal register (`instance/data/events/<id>/certificates.yml`)
  alone, never by touching the signature -- see
  `tools/convener_ops/journey/certificate.py`'s own module docstring, "revocation
  touches the register, never the signature".
- **We keep no name and no address once this is issued.** Our own register
  holds the certificate's identifier, the event id, the date it was issued,
  a salted fingerprint of the address (never published, and not reversible
  by anyone who does not hold the matching salt -- see
  `tools/convener_ops/journey/certificate.py`'s own module docstring, "the fingerprint
  is reversible, given the salt", for what that qualification means and
  why the salt itself is never rotated), and its state. That register
  outlives the registration it was derived from:
  `instance/data/events/<id>/registrations.enc` is destroyed 90 days after the
  event; `certificates.yml`, in the same directory, is not.
