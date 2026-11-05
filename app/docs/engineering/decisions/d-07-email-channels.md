# D-07 — Two separate email channels, for two separate needs

**Status:** Accepted

## Context

Notifying the board and writing to the outside world (registrants,
certificate recipients) are different problems with different guarantees
needed, and email deliverability depends on a sender's domain being properly
aligned (SPF/DKIM) with whatever service transmits the message.

## Decision

Two channels, kept distinct:

| Need | Channel |
|---|---|
| Notify the board (internal) | A CI job opens or comments on an issue mentioning the board's team; GitHub delivers the email itself |
| Write to the outside world (registrants, certificates) | An organisation-owned mailbox, sending through a configurable transport, with credentials in the organisation's secrets |

Two distinct functions are kept apart:

| Function | What holds it | Role |
|---|---|---|
| Organisation identity | a real, organisation-owned mailbox | owns service accounts, receives password resets and replies |
| Bulk sending | a transactional-style transport sending *on behalf of* that mailbox | sends confirmations and certificates |

A sending service does not grant an address — the mailbox has to exist
first, which is why it is created before any sending transport is chosen.

## Rejected

Two stronger options were considered and closed:

- **Send through records on the organisation's own domain.** The domain is
  administered by a party the project cannot get timely cooperation from —
  not a delay, a dead end for as long as that remains true.
- **A transactional service sending on behalf of a free consumer address.**
  This breaks SPF/DKIM alignment: the service signs with its own sending
  domain, not the sender's, and mainstream transactional providers
  themselves flag a free-mail sender address as not recommended. Without the
  first option, this one cannot be configured correctly either.

**Retained: SMTP through the organisation's own mailbox.** Sending from a
mainstream provider through that same provider's own SMTP is naturally
aligned — verified with a real delivered message. Its daily sending cap is
comfortably above what one event's confirmation-plus-certificate volume
requires. The account's two-factor secret lives in the shared vault, so
sending never depends on one person's phone.

## Cost

No bounce log, no deliverability metrics — accepted deliberately, because a
perfectly logged send that lands in spam has achieved nothing, and alignment
is what keeps it out of spam. `reply-to` always points at the organisation's
address regardless of which transport sends the message.

**What would reopen this.** If the organisation comes to administer its own
domain, sending through a transactional service on the organisation's
address becomes the better option again — and switching is a credential
change, not a code change, since the adapter is already generic SMTP.
