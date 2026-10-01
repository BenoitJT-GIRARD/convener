# Data protection record — registration and certification

The processing record: what we hold about a participant in
the registration, attendance and certificate pipeline, why, on what basis,
who can reach it, for how long, and what actually protects it. Written as
the code behaves, not as we would like to describe it — every claim below is
checkable against `tools/convener_ops` and `app/src`, and `tools/tests` pins the
two numbers that carry legal weight against the constants the code itself
uses, so this page cannot quietly drift from what runs.

This page covers one pipeline: registering for an event, being recognised
in the room, and being issued a certificate afterwards. It does not cover
`instance/data/speakers.yml`, a different file under a different legal footing
entirely — a participant here chose to register for an event they already
knew was happening, where a speaker candidate may not know their name was
put forward at all. That file has its own record:
[Data protection record — speaker and event-lead candidates](candidate-data-protection.md).

## Controller

**{{ instance.organisation }}** is the controller for everything set out
below, and answers for it at `{{ instance.contact }}`.

That names whoever is *running* this instance, and it never names whoever
wrote the software. This page ships with the product because the mechanisms
it describes — encryption in the participant's own browser, one key per
event, destruction of that key on a deadline — are identical in every
instance and checkable against the code of any of them. The judgements are
not shipped and could not be: the basis relied on, the window chosen, the
recipients, and who replies to a participant asking what is held about them
are decided by the organisation running the series and answered for by it.
An instance that duplicated this repository has adopted this record as its
own, with its own name at the head of it. The software's author is not a
controller, a joint controller or a processor for any of it, and receives
none of the data — there is no telemetry and no shared service for any of
it to travel through.

## What we hold

- **Registration (G-12)**, per event, encrypted
  (`instance/data/events/<id>/registrations.enc`): first name, surname, email address, an optional institution, and an
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
  check; an internal register alongside it, open to a narrower audience,
  that adds the event id, the date of issue, and a salted fingerprint of
  the address — never the address itself, and never a name.

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

Two services outside the organising team see a participant in the clear:
the mailbox that sends a confirmation, a certificate or a survey
invitation sees the address it goes to and what the message says, and the
meeting platform sees the name and the address each person joins the room
with. `docs/operating/what-you-take-on.md`, in the operator's own tree,
is the whole list of what an instance leans on, what each one sees, and
what an operator changes by choosing others.

Nobody else, and inside the organising team not even everybody. The signup
relay, the service a participant's browser actually talks to, checks that
the encrypted envelope it receives is shaped correctly and forwards it — it
never holds a key that could decrypt it, and it never sees plaintext.
Every later step that needs to read a registration — recording it, matching
attendance, issuing a certificate — does so inside its own GitHub Actions
job, for the length of that job's run, never on a laptop and never in a
browser.

**Two documented exceptions** still name a participant by address rather
than by matching code, and both are named, deliberate, and narrow rather
than overlooked: resending a confirmation
(`.github/workflows/resend-confirmation.yml`) and the early-erasure fallback
for someone who no longer has their matching code
(`.github/workflows/erase-registration.yml`). Neither puts the address
itself outside the pipeline any more: since a security-review fix,
both take that address hybrid-encrypted under the event's
own published public key, produced locally with `convener-encrypt-identifier`,
never the address itself — GitHub still retains the manually-triggered
workflow input on that run's own page for as long as the run's history
exists, but what it retains is ciphertext, decryptable only by whichever
CI job later holds this event's own private key. Both are also restricted
to collaborators with write access to this repository — the same boundary
that already gates every other administrative action here — and both are
named in `declarations/integrations.yml` and `docs/operating/operations.md`.

## Duration

Registration and attendance data is destroyed **90 days** after the event,
by destroying the one key that could ever decrypt it — the retention window
`tools/convener_ops/journey/eventkeys.py` reads for every event. The encrypted files
themselves are not deleted: `instance/data/events/<id>/registrations.enc`, the
attendance export and `survey-responses.enc` all stay committed —
unreadable, not absent, so no commit history anywhere in
this repository is ever rewritten to make that happen. The one credential
this destruction depends on is the
one integration this project will not let fail quietly: if it is missing,
the scheduled job that would destroy an event's key fails outright, every
day, rather than skipping the day's work unnoticed.

The certificate register survives this destruction. A certificate must
still verify however long after it was issued someone checks it, so its
identifier, event id, issue date, salted fingerprint and state are never
touched by this deadline.

## Rights

- **Access and rectification.** Rectifying the name, institution or
  announce-list preference on a registration has a procedure: registering
  again with the same address is an update, not a second entry
  (`tools/convener_ops/journey/registration.py::upsert`) — the same "second submission
  updates the first" mechanism the event page's form already uses.
  Rectifying the address itself, and access to what is held beyond that,
  do not: `convener-resend-confirmation` reproduces most of a registration back
  to a participant's own address — their name and their matching code —
  but not their institution or announce-list preference, and nothing
  automates correcting an address or answering "what do you hold about
  me" in full. Both are handled by hand, during retention, by writing to
  the contact address below, and this record does not claim a procedure
  for them that does not exist.
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

Write to `{{ instance.contact }}` for any of the above — the same
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
  submitted. `docs/operating/operations.md` records this in full; this page
  does not describe it more favourably than that one does.

---

*See also: the event page's own notice, `site/src/event.njk`, carrying the
registration form itself as a mounted island
(`app/src/islands/signup/SignupForm.tsx`), for what a participant reads before
registering, and
`docs/operating/operations.md` for the full procedures behind
every measure named above.*
