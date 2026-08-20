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
  `{{ speaker.zoom_link }}`, `{{ speaker.forum_thread }}`,
  `{{ speaker.youtube_url }}`, `{{ speaker.live_peak }}`;
- the people around it — `{{ host_1.name }}`, `{{ host_2.name }}`,
  `{{ proposed_by.name }}`;
- what the series publishes — `{{ consent.published_always }}` and
  `{{ consent.published_on_consent }}`, composed from the publication gate
  itself so that no message can promise something the gate would not do.

A name that is not in that vocabulary does not resolve: it comes out as
`«missing: …»` in the message, which is what a volunteer would paste into an
e-mail. So anything you have to write in by hand is written in **square
brackets** instead — `[the day the LinkedIn post goes out]` — and reads as an
instruction rather than as a field the workspace forgot to fill.

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

One message is not on the list above because nobody sends it from this
page: [Registration confirmed](emails/registration-confirmed.md) goes out
the moment a participant registers, composed and sent by
`tools/convener_ops/confirmation.py`. It is kept in this section anyway, for the
same reason every other message is — so its exact wording is one click
away — but its placeholders are written in square brackets, not double
braces, since nobody ever opens it here to fill them in.

## Posts & scripts

- [Forum post — announce](forum-post-announce.md)
- [Forum post — discussion summary](forum-post-summary.md)
- [LinkedIn post](linkedin-post.md)
- [Intro scripts](intro-scripts.md) — what the hosts say over the opening slides
- [Run of show](run-of-show.md) — the session slide by slide, and the split between the two hosts
- [Slide template](slides/presentation-template.md) — what goes on the hosts' own slides
- [Visual kit](visual-kit.md) — the announcement image, the flyer and the video-call background, as source files you download and edit yourself
