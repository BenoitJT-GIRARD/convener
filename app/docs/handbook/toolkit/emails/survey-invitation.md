# Email — Survey invitation

*Sent by hand, once an operator dispatches* Invite the post-event survey
*(`.github/workflows/invite-survey.yml`), to every attendee that run's own
attendance match recognises present for that event — never automatically,
and never to a registrant who did not attend, an attendee the cascade
could not tie to a registration, or a telephone joiner with no address on
file. As with the other messages this project sends automatically rather
than a volunteer composing it here, this page's own placeholders sit in
**square brackets** rather than double braces — there being no speaker
record to fill `{{ … }}` markers in from in the first place — kept
anyway so a board member can read exactly what a participant receives
without opening `tools/convener_ops/journey/survey_invite.py`.
`tools/tests/journey/test_survey_invite.py` pins this page's subject line and its
one fixed sentence against that module's own constants, so the two cannot
quietly say different things.*

*This message goes only to people we recognise as having
attended, and to nobody else — the questionnaire itself is optional, and
so is answering it. The link below is the same one for every recipient of
the same event:
there is no per-person code or token in it, on purpose — see
`tools/convener_ops/journey/survey_invite.py`'s own module docstring for why minting
one would undo the anonymity the survey response itself is built to
have.*

---

**Subject:** Tell us what you thought — [the event's title, when known]

Dear [participant's first name],

Thank you for attending [the event's title]. We would like to hear what
you thought.

This short, optional survey is only sent to people we have recorded as
present at this event.

Answer the survey here: [the survey link for this event]

It takes about two minutes.

Best regards,
{{ instance.organisation }} team

---

## Notes for whoever reads this page

- **This message is ordinary, personally-addressed e-mail — the survey
  answer it links to is not.** The invitation opens "Dear [first name],"
  and goes to the address on the participant's own registration, exactly
  like their registration confirmation or their certificate. Nothing about
  *this message* is anonymous. Only the response the link leads to is
  designed to carry no identity at all — see `tools/convener_ops/journey/survey.py`'s
  own module docstring and
  `docs/operating/operations.md`'s "Anonymous against a stranger;
  pseudonymous by metadata against the organiser" section for the
  qualified claim this page must never say more plainly than it is true:
  against a stranger a stored answer is anonymous; against whoever holds
  the event's own key and its attendance list, the arrival time of each
  response is still a real, if narrow, handle.
- **Who is invited, and why not the other two.** *Invite the post-event
  survey* only ever e-mails a *matched* attendee — a stored registration
  the attendance cascade tied to a room presence. An attendee the cascade
  could not tie to any registration has no stored address to send to
  either; a telephone joiner never had one on file, by any means, at any
  point — see `tools/convener_ops/journey/attendance.py`'s own module docstring, "Three
  outcomes, not two". Neither exclusion is a policy choice this message
  enforces; both are a plain fact this pipeline cannot get around.
- **A resend invites everyone again, not only whoever missed the first
  round — by choice, not because anonymity forces it.** Unlike a
  certificate resend, which `certificate.py`'s own public identifiers let
  target precisely, `convener-invite-survey` mints no identifier at all — see
  `tools/convener_ops/journey/survey_invite.py`'s own module docstring
  for the full argument: a per-person handle
  here would not undo the survey response's own anonymity, but it would be
  a permanent, cross-event linkage kept for a purpose that expires in
  days, so it is not built. A single in-place retry inside the same run
  (needing no identifier at all) already removes most transient failures.
  By default, once an event has already been invited once
  (`instance/data/survey-invitations.yml`), a second dispatch of this workflow
  sends nothing further; ticking that workflow's own `resend_all` input is
  the recovery for what the in-run retry could not fix, and it re-sends to
  everyone the first run already reached too — a harmless duplicate, since
  this message carries no attachment and no signed document, unlike a
  certificate resend.
- **Without `email_transport`'s five secrets configured**
  (`declarations/integrations.yml`), nothing here is sent, and — unlike the
  registration confirmation — nothing is written anywhere as a fallback
  either: every attempt is folded into a bare sent/not-sent count, the
  same choice `tools/convener_ops/journey/delivery.py` makes for a certificate, made
  here for a plainer reason — this pipeline holds no identifier to write
  an unsent invitation *against* in the first place.
