# Templates

Ready-to-use templates for every outbound communication. **Open it on the speaker's page, read it through, send it.** Do not edit a template in place — work on a copy, and leave the original for the next person.

## Placeholders

Anything a template writes in double braces is filled in for you from the
speaker's record when you open it in the workspace. The vocabulary is the
record's own field names, reached through the object that holds them:

- the speaker — `{{ speaker.name }}`, `{{ speaker.first_name }}`,
  `{{ speaker.affiliation }}`, `{{ speaker.country }}`, `{{ speaker.bio }}`;
- their talk — `{{ speaker.title }}`, `{{ speaker.abstract }}`,
  `{{ speaker.edition_code }}`, `{{ speaker.date }}`, `{{ speaker.time }}`,
  `{{ speaker.when }}` (the date and time together, with the real Paris
  offset for that day — "Thursday, 12 March 2026 at 12:30 CET" — never
  write `{{ speaker.time }}` beside a hand-typed "CET": half the year that
  is wrong), `{{ speaker.zoom_link }}`, `{{ speaker.forum_thread }}`,
  `{{ speaker.youtube_url }}`, `{{ speaker.live_peak }}`;
- the people around it — `{{ host_1.name }}`, `{{ host_2.name }}`,
  `{{ proposed_by.name }}`;
- what the series publishes — `{{ consent.published_always }}` and
  `{{ consent.published_on_consent }}`, composed from the publication gate
  itself so that no message can promise something the gate would not do;
- who is writing — `{{ instance.organisation }}` (the name a stranger is
  told), `{{ instance.short_name }}` (the abbreviation, for somebody who
  already knows — the form that reads naturally in a subject line),
  `{{ instance.series }}`,
  `{{ instance.forum_host }}` and `{{ instance.contact }}`. These are the
  only ones that do not come from a record: they come from
  `instance/config.json`, the one file that says whose series this is, and
  they are therefore the same on every page. They resolve on the Templates
  screen with no speaker in hand, exactly as the `consent.…` group does, so
  what you read there is what a speaker would receive.

**Never type the organisation's name, the series' title, the forum's address
or the contact address into a template.** They are the instance's, not this
handbook's, and a duplicate of this repository runs a different series under
a different name. Writing one out by hand is how, a year from now, half the
messages say one thing and half say another.

A page drafted to be **posted somewhere public** — a forum announcement, a
LinkedIn post, a mailing list message, a recording announcement — reads a
speaker's personal fields (`bio`, `photo_url`, `linkedin`, `youtube_url`)
through a second vocabulary instead, `{{ public.… }}` rather than
`{{ speaker.… }}`. It carries the same names, but each one comes out empty —
and so shows as `«missing: …»` — until the speaker's own recorded consent and
the board's approval have actually cleared it, exactly the gate
`tools/convener_ops/public_data.py` applies to the public feed itself
(`state/consent.ts::toPublicFields`). A page that only ever tells the team
something, never the outside world, keeps reading `{{ speaker.… }}`
unfiltered, the same as it always has.

A name that is not in that vocabulary does not resolve: it comes out as
`«missing: …»` in the message, which is what a volunteer would paste into an
e-mail. So anything you have to write in by hand is written in **square
brackets** instead — `[the day the LinkedIn post goes out]` — and reads as an
instruction rather than as a field the workspace forgot to fill.

A biography and a forum thread link are not fields the workspace forgot,
though — they are ordinarily absent, waiting on a consent nobody is obliged
to give or a thread nobody has opened yet — so `«missing: …»` is the wrong
thing to show for them inside a page meant to be posted as-is. Three pages
(`recording-announce.md`, `linkedin-post.md`, `mailing-list-announce.md`)
pair each such field across two lines instead: `{{ public.bio? }}` (a
trailing `?`) resolves to the value when there is one, and otherwise drops
its *entire line* from the text rather than leaving the marker behind;
`{{ public.bio! }}` (a trailing `!`), in "Notes for the volunteer", does the
opposite — it drops its line when the field *is* there, and otherwise keeps
the rest of that line as a plain sentence saying so. The two read
differently on purpose: a withheld biography is finished business, nothing
to add; an unopened forum thread is a task the volunteer may be the one to
close.

## Emails

- [Proposal received](emails/proposal-received.md) — acknowledging a proposal, the day it arrives
- [Invitation](emails/invitation.md) — first contact with an approved speaker
- [Talk details](emails/talk-details.md) — collect title, abstract, bio
- [Promotion starting](emails/promotion-starting.md) — telling the speaker, three weeks out, that the series is about to announce them
- [Reminder](emails/reminder.md) — reminder to the speaker before the event
- [Thank-you](emails/thank-you.md) — after the talk
- [Recording consent](emails/consent-request.md) — asking whether the recording may be published, after the talk
- [Video online](emails/video-online.md) — telling the speaker the recording is published, once they have agreed to it
- [Registration confirmation](emails/registration-confirmation.md) — confirm the announcement is live
- [Decision — declined](emails/decision-declined.md) — to a candidate not retained
- [Decision — parked](emails/decision-parked.md) — to a candidate kept for later
- [Outreach — sourcing](emails/outreach-sourcing.md) — invite a lab/institute to suggest speakers

## Sent automatically, not from here

Four items are not on the list above because nobody sends them from this
page: [Registration confirmed](emails/registration-confirmed.md) goes out
the moment a participant registers, composed and sent by
`tools/convener_ops/confirmation.py`. [Certificate of attendance](certificate.md)
is generated once per eligible attendee after an event, by
`tools/convener_ops/certificate.py`, and delivered by e-mail with
[Certificate delivered](emails/certificate-delivered.md) as the message that
carries it, composed and sent by `tools/convener_ops/delivery.py`.
[Survey invitation](emails/survey-invitation.md) goes out only when an
operator dispatches `.github/workflows/invite-survey.yml` for one event,
to every attendee that run's own attendance match recognises present —
composed and sent by `tools/convener_ops/survey_invite.py`. All four are kept in
this section anyway, for the same reason every other message is — so their
exact wording is one click away — but their placeholders are written in
square brackets, not double braces, since nobody ever opens any of them
here to fill them in.

## Posts & scripts

- [Forum post — announce](forum-post-announce.md)
- [Forum post — discussion summary](forum-post-summary.md)
- [LinkedIn post](linkedin-post.md)
- [Mailing list / newsletter message](mailing-list-announce.md) — for every mailing list and newsletter the series announces on; which ones those are is the Board's own list of channels, kept in `instance/data/config.yml` and shown on each speaker's promotion checklist, not written out here
- [Recording announcement](recording-announce.md) — once the recording is actually published, for every channel the seminar was announced on
- [Intro scripts](intro-scripts.md) — what the hosts say over the opening slides
- [Run of show](run-of-show.md) — the session slide by slide, and the split between the two hosts
- [Slide template](slides/presentation-template.md) — what goes on the hosts' own slides
- [Visual kit](visual-kit.md) — the announcement image, the flyer and the video-call background, as source files you download and edit yourself
