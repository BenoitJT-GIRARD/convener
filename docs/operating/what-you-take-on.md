# What you take on

Running an instance of this software makes you responsible for three
things the author of it is not responsible for: the personal data it
holds, the keys it destroys, and everything the licence declines to
promise. Each is written out below in ordinary words.

## Personal data, and who answers for it

**If you run an instance of this software, you are the data controller for
the personal data it holds. The author of this software is not.**

That sentence is here because somebody will assume the opposite on the day
it matters. This product ships the mechanism — a registration encrypted in
the participant's own browser, one key per event, a retention deadline that
destroys that key — and never the judgement. Who is told what, on what
legal basis, for how long, and who answers a participant asking what is
held about them: every one of those is the operator's, because every one of
them is a decision about a processing operation the operator chose to carry
out.

For an operator, concretely:

- **The processing record is yours.**
  [Registration and certification](../handbook/governance/traitement-donnees.md)
  and
  [Speaker and event-lead candidates](../handbook/governance/candidate-data-protection.md)
  describe mechanisms a duplicate genuinely shares, which is why a duplicate
  inherits them — but the controller each names is the instance's own, and
  every claim on those pages is one you are making about your own
  processing. Read them as drafts you are adopting, not as cover somebody
  else has given you.
- **The contact address a participant is told to write to is yours**, and
  it is answered by you.
- **Nothing reaches the author of this software.** No telemetry, no phoning
  home, no shared service: the repository is yours, the Actions runs are
  yours, the workers are deployed under your own account. Which is also why
  nobody here can help you when a key is gone.

## No warranty, in ordinary words

The licence states this in capitals and in legal English. Here it is in
neither: **this software comes with no warranty of any kind, and nobody
here is liable for what it does to your data or to anybody else's.**

Two of the things it does are worth reading that sentence twice for:

- **It destroys cryptographic keys, deliberately and on a schedule.** That
  is the mechanism by which a participant's registration stops being
  readable after an event: the key is destroyed, the encrypted file stays,
  and nothing can decrypt it again. There is no recovery, no escrow and no
  support line. A key destroyed early, or an event given the wrong
  retention window, takes its data with it —
  [D-22](../engineering/decisions/d-22-key-destruction-not-deletion.md) is why that
  is the design rather than an accident.
- **It processes other people's personal data.** Names, addresses,
  institutional affiliations, attendance and survey answers, belonging to
  people who registered for a talk and never agreed to be anybody's test
  case.

Try it against your own arrangements before it holds anybody's data.

## What the terms are

Free software under the [GNU Affero General Public License, version 3 or
later](../../LICENSE). Section 13 of it is the point: a hosted, *modified*
version has to offer its source to the people using it, so this cannot
quietly become somebody's closed fork.

The name and the mark are **not** covered by that grant — a term at the head
of `LICENSE`, under section 7 of the licence itself, declines them, and
[`TRADEMARK.md`](../../TRADEMARK.md) says what a fork renames and what it
keeps. Both the showcase and the cockpit display the licence notice in their
footer; its text is `NOTICE.json`, and no part of it is an instance's to
configure.
[D-29](../engineering/decisions/d-29-licence-and-attribution.md) is the whole
argument, including the two licence families that were rejected and why.

**If those terms do not suit your use, a separate licence can be negotiated
with the copyright holder.** The AGPL is what this repository offers, and it
is offered to everybody on the same terms; it is not the only licence the
holder is able to grant.
