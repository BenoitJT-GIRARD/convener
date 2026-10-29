# Data protection record — speaker and event-lead candidates

This record covers `instance/data/speakers.yml`: everyone the series has ever
considered as a speaker, from an unsolicited or referred lead through to a
delivered talk. It is a separate processing activity from
[Data protection record — registration and certification](traitement-donnees.md),
which covers a different file, a different audience and a different legal
footing — a participant chooses to register for an event they already know
is happening; a candidate here may not know their name was put forward at
all. The two records are kept apart rather than merged into one, the same
reasoning [How we validate speakers](selection-criteria.md) already gives for
keeping editorial judgement and data handling on separate pages: one topic,
one home.

This page previously did not exist. `traitement-donnees.md` named this file
in a single sentence — "a different category of personal data, speakers' own
names and institutional email addresses" — and pointed at
`selection-criteria.md` for the rest. Neither was accurate: the file holds a
good deal more than a name and an address, and `selection-criteria.md` is the
Board's editorial judgement, not a data-handling process; it never described
one. This page replaces that sentence with an honest account, established
against the schema (`docs/engineering/schema.md`) and the code that reads each
field, not against what would be convenient to claim.

## What we hold

Of the fields `instance/data/speakers.yml` carries for a candidate, these describe an
identifiable person — the candidate themselves, or someone else named on
their behalf — rather than the workshop they might one day deliver:

- `name` — the candidate's name, as given at proposal or held since.
- `email` — a contact address, when one was given. Present on 12 of the
  file's 31 records today.
- `affiliation` — the candidate's institution, when given (17 of 31). Once a
  talk is confirmed this becomes part of the seminar's own public programme,
  the credential the audience comes for — see
  `app/src/state/consent.ts::PUBLISHABLE_ALWAYS`.
- `country` — where the candidate is based, or the talk would be billed
  from, when given (10 of 31). Read the same way as `affiliation` above, and
  aggregated — never published per candidate — in the diversity balance
  report described next.
- `gender`, `career_stage` — self-reported, with "undisclosed" a first-class
  answer rather than a missing one. Present on every record, and read only
  in aggregate, as marginal counts that never cross-tabulate two dimensions
  at once, for the Board's diversity balance report
  (`app/src/state/diversity.ts`). That module calls this "the most sensitive
  data in the repository — it is about identifiable researchers" and never
  emits it per row for exactly that reason. Today, honestly: all 31 records
  read "undisclosed" for both fields, so the report the mechanism feeds has
  no signal to show yet — the field is read, the read just has nothing to
  say.
- `links` — URLs the lead arrived with (an ORCID page, a lab page, a paper),
  shown to the Board on the record's own page as material for judging the
  candidate (22 of 31).
- `photo_url`, `bio`, `linkedin`, `seed_questions` — a portrait, a written
  biography, a linked professional identity, and discussion-opener
  questions in the candidate's own words. The schema has a place for each,
  none of the 31 records holds one today, and each one waits on the
  candidate's own recorded consent before it could ever leave this
  repository (`PUBLISHABLE_ON_CONSENT`) — the same gate a confirmed
  speaker's recording goes through.
- `conflicts_of_interest` — a declaration, by the candidate or noted by the
  Board, kept for the Board's own recusal rules — not the spoken declaration
  made to an audience during a session, which is a separate line of the
  runbook. Empty on every record today.
- `proposed_by` — not the candidate's own data: the name of whoever put them
  forward, self-reported at submission and kept exactly as given, often
  someone outside the team entirely. It is the only record of who to tell
  if the Board declines the lead, and it feeds the rotation that assigns an
  unsponsored lead to a Board member. Present on every record.
- `notes` — free-form text the Board keeps on the record. In practice this
  is mostly a review flag, and for leads carried over from before the
  Editorial Board's own ballot mechanism existed, a plain record of who
  voted for them under the earlier, informal process. Shown on the record's
  own page to anyone who opens it. Present on 30 of 31.

One further field deserves a plain word, though it is not personal data:
`metrics` — registrations, live peak attendance, 30-day YouTube views and
forum replies. These describe the *event*, not the person who delivered it,
which is exactly how `docs/engineering/schema.md` itself draws the line: "the
edition fields ... describe the workshop they deliver." It sits on this
record only because the schema treats a speaker and the edition they deliver
as one entity, and it is shown on the record's own page alongside everything
above.

This list is not a hand-kept promise. `app/src/state/candidate-data.ts`
classifies every field `Speaker` has, in code, against
`app/src/data/types.ts::SPEAKER_FIELDS` — exhaustively, the same way the
publication gate's own three sets are — and the classification is bound to
this page by `tools/tests/fixtures/governance-cases.json`, checked from both
languages (`app/tests/state/personal-data-fields.test.ts` and
`tools/tests/repository/test_candidate_data_protection_record.py`). A field the model
gains later and nobody classifies fails a test before it can reach this page
without a description.

## Purpose

To evaluate a lead against the Board's own selection criteria
([How we validate speakers](selection-criteria.md)), to reach and coordinate
with a candidate who is invited to speak, and — for the diversity attributes
specifically — to check, in aggregate, whether the programme the series
produces matches the balance it states as a goal. Nothing here is collected
to build a profile of a person beyond this series, and nothing here is used
for any purpose besides the ones just named.

## Legal basis

None is recorded, and this page will not claim one it cannot show. The
public and referred intake this file's leads arrive through carries no
privacy notice, so nothing here rests on a candidate's consent to be
evaluated — `publication.consent`, the one consent this schema does record,
governs a single later question, whether a confirmed speaker's recording may
be published, and answers nothing about being considered as a candidate in
the first place. This is a gap a security review named:
a real one, surfaced here rather than papered over, and left
for the maintainer to settle rather than resolved by this page inventing a
basis after the fact.

## Recipients

Unlike the registration pipeline, nothing here is encrypted.
`instance/data/speakers.yml` is a plain, committed file: anyone with read access to this private
repository can open it directly and read every field above in full, not only
the Board members the app's own screens present it to
(`app/src/screens/SpeakerPage.tsx`, `app/src/components/AdminOverride.tsx`).
Signing in to the app itself goes through the organisation's GitHub App and
device flow (see [D-03](../../engineering/decisions/d-03-github-app-device-flow.md)), which
is a convenience layer over that same repository access, not a narrower one.
No recipient outside this repository's collaborators is sent any of it.

## Duration

Kept indefinitely. There is no retention window for a candidate record
anywhere in `config.yml` or in code, and no scheduled job, sweep or operator
command destroys, redacts or expires any part of one — checked directly
against `tools/convener_ops`, the same way the registration pipeline's 90-day
window is pinned against `eventkeys.RETENTION_DAYS`, and finding nothing to
pin here. A lead the Board declines, or a candidate who never replies, stays
in this file exactly as first written, with no scheduled step that ever
revisits it.

## Rights

There is no erasure path. No command removes a candidate's record, in whole
or in part, from `instance/data/speakers.yml` — nothing plays the part
`convener-erase-registration` plays for the registration pipeline. The only
mechanism that changes what is held is a Board member editing the record by
hand through the app (`AdminOverride`), which happens for operational
reasons — correcting a detail, updating a status — not in response to a
request from the candidate, and is not offered as one.

## Measures

None beyond ordinary repository access control. No field here is encrypted,
padded, salted or otherwise protected beyond what git and the private
repository already provide, and this page will not describe a safeguard
that is not there. Whether that should change — encryption, a retention
window, a route for a candidate to ask what is held about them — is the
question that review raised and left for the maintainer to decide;
this page's job is to describe today's system accurately, not to resolve
that question by quietly claiming a protection this file does not have.

---

*See also: [Data protection record — registration and certification](traitement-donnees.md),
for the separate, encrypted pipeline a person enters once they register for
an event, and [How we validate speakers](selection-criteria.md), for what the
Board weighs when it reads a candidate record this page describes the data
of.*
