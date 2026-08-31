# D-02 — Participant data: encrypted per event, key destroyed on schedule

**Status:** Accepted

## Context

[D-01](d-01-repository-of-record.md) puts every population's data in the
repository, but registration, attendance and quiz data arrive at a different
scale and sensitivity than speaker records: hundreds of participants per
event, and none of them consented to being a permanent, plain-text line in a
public organisation's version history.

## Decision

Registration data is stored **encrypted, per event**, in the private
repository. Each event gets its own key, held in the organisation's secrets.
Past the retention window, the key is destroyed.

- Git history holds ciphertext only.
- Destroying an event's key makes the whole of that event's registration
  data permanently unreadable, in one operation, without rewriting history
  (crypto-shredding — see [D-22](d-22-key-destruction-not-deletion.md)).
- **Only the automated pipeline ever decrypts. The browser never does.** An
  organiser does not need the list of names — only the count, which the
  data model already exposes.
- Retention: event date + 90 days.

What survives key destruction is a non-identifying register:
`{certificate_id, event_id, issue_date, hash(email + salt)}`. No name, no
email. A public verification page can answer "certificate #ABC is valid for
this event" without disclosing anything else.

## Rejected

Keeping a plain, organiser-readable roster. Nothing in the actual workflow
needs one — the aggregate count already answers the only question an
organiser asks.

## Cost

An organiser cannot casually browse who has registered; getting a name out
of an active event's data requires the decrypting pipeline, not a UI
screen. That friction is deliberate: it keeps the browser, and therefore
every client-side bug, out of the one place a leak would matter most.
