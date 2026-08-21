# Data protection record — registration and certification

The processing record spec §4 asks for: what we hold about a participant in
the registration, attendance and certificate pipeline, why, on what basis,
who can reach it, for how long, and what actually protects it. Written as
the code behaves, not as we would like to describe it — every claim below is
checkable against `tools/convener_ops` and `app/src`, and `tools/tests` pins the
two numbers that carry legal weight against the constants the code itself
uses, so this page cannot quietly drift from what runs.

This page covers one pipeline: registering for an event, being recognised
in the room, and being issued a certificate afterwards. It does not cover
`data/speakers.yml`, which holds a different category of personal data —
speakers' own names and institutional email addresses — under a different
process; see [How we validate speakers](selection-criteria.md).

## What we hold

- **Registration**, per event, encrypted (`data/events/<id>/registrations.enc`):
  first name, surname, email address, an optional institution, and an
  announce-list opt-in — exactly the fields the event page's form asks for,
  and nothing else.
- **Attendance**, matched automatically against the registration above by a
  matching code, then an exact email address, then a normalised name — see
  the two boundaries on the event page for when that matching cannot reach
  someone.
- **Survey answers**, optional per event, encrypted alongside the
  registration: a rating, a recommendation and free-text feedback, with no
  name and no address attached to any of it. See "Survey answers" under
  Measures, below.
- **Certificates**: a public identifier and a state, published for anyone to
  check; a narrower internal register alongside it that adds the event id,
  the date of issue, and a salted fingerprint of the address — never the
  address itself, and never a name.

## Purpose

To register a participant for one event, to recognise them in the room well
enough to know whether they attended for long enough to earn a certificate,
and to issue and let anyone verify that certificate afterwards. Nothing here
is collected for any other purpose, and nothing here is used to build a
profile of a participant across events.

## Legal basis

Consent. A participant registers voluntarily, is told before they do — by
the notice on the event page, before the form — that their browser will
encrypt what they type, and can ask to see, correct, withdraw or erase it at
any time before the retention deadline below.

## Recipients

Nobody outside the organising team, and not even all of it. The signup
relay, the service a participant's browser actually talks to, checks that
the encrypted envelope it receives is shaped correctly and forwards it — it
never holds a key that could decrypt it, and it never sees plaintext.
Every later step that needs to read a registration — recording it, matching
attendance, issuing a certificate — does so inside its own GitHub Actions
job, for the length of that job's run, never on a laptop and never in a
browser.

**Two documented exceptions** put an address somewhere outside that
pipeline, and both are named, deliberate, and narrow rather than
overlooked: resending a confirmation
(`.github/workflows/resend-confirmation.yml`) and the early-erasure fallback
for someone who no longer has their matching code
(`.github/workflows/erase-registration.yml`) each take an address as a
manually-triggered workflow input, which GitHub retains on that run's own
page for as long as the run's history exists. Both are restricted to
collaborators with write access to this repository — the same boundary
that already gates every other administrative action here — and both are
named in `config/integrations.yml` and `docs/reference/operations.md`.

## Duration

Registration and attendance data is destroyed **90 days** after the event,
by destroying the one key that could ever decrypt it — the retention window
`tools/convener_ops/eventkeys.py` reads for every event. The encrypted files
themselves are not deleted: `data/events/<id>/registrations.enc` and the
attendance export stay committed, exactly as spec §4 asks — unreadable, not
absent, so no commit history anywhere in this repository is ever rewritten
to make that happen. The one credential this destruction depends on is the
one integration this project will not let fail quietly: if it is missing,
the scheduled job that would destroy an event's key fails outright, every
day, rather than skipping the day's work unnoticed.

The certificate register survives this destruction. A certificate must
still verify however long after it was issued someone checks it, so its
identifier, event id, issue date, salted fingerprint and state are never
touched by this deadline.

## Rights

- **Access and rectification.** Handled by hand, during retention, by
  writing to the contact address below.
- **Erasure before the deadline.** A documented, tested procedure removes
  one participant's own registration from the encrypted file, without
  touching any other registrant's entry.
- **After the key is destroyed, there is nothing left to erase — and this
  is provable, not merely claimed.** Requesting erasure for an event
  already on record as destroyed reports the destruction date and stops,
  rather than asking for a key that would contradict that record.
- **Survey answers cannot be erased individually on request.** Nothing
  links a stored answer to a person — see "Survey answers" below — so there
  is no way to identify which answer to remove. The only lever that reaches
  a survey answer at all is destroying that event's key early, which erases
  the registration and every survey answer for that event together, not one
  answer on its own.

Write to `reading-group@example.test` for any of the above — the same
address the confirmation email and the event page's own notice both name.

## Measures

- **The browser encrypts before anything leaves it.** A registration or a
  survey answer is encrypted under the event's own published public key,
  inside the participant's own browser, before it is ever sent anywhere.
- **One key per event, and the private half never touches disk outside a
  job.** Destruction of that key is the act that makes an event's data
  unreadable, not a separate deletion step.
- **The retention sweep's own credential is not an ordinary absence.**
  Every other missing integration in this project degrades quietly; this
  one is the deliberate exception, because a retention job that runs and
  destroys nothing must never look, from the outside, identical to one that
  had nothing to do.
- **The certificate register holds no name and no address.** An identifier,
  an event id, an issue date, a salted fingerprint of the address, and a
  state — nothing else, and it is written to hold nothing else by
  construction, not by omission.
- **Verification shows a certificate holder's name without the register
  storing it.** The name travels inside the signed certificate token, in
  the verification link's URL fragment — the part after `#`, which a
  browser never sends in an HTTP request and strips from `Referer` before
  navigating anywhere else. The verification page reads the name from that
  token, never from anything we store.
- **Survey answers are anonymous in their content, and pseudonymous by
  metadata against us specifically.** Each stored answer carries no name,
  address or identifier, and is padded to a fixed size before encryption so
  its length reveals nothing about how much a participant wrote. One fact
  is not closed the same way: each answer is committed to this repository
  individually, at the wall-clock minute it arrived, so whoever holds both
  the event's key and its attendance list — the organiser, and only the
  organiser — can pair an answer's position with roughly when it was
  submitted. `docs/reference/operations.md` records this in full; this page
  does not describe it more favourably than that one does.

---

*See also: the event page's own notice, `app/src/signup/SignupForm.tsx`, for
what a participant reads before registering, and
[Operations](../reference/operations.md) for the full procedures behind
every measure named above.*
