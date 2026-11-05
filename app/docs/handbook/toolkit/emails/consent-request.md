# Email — Asking to publish a recording

*To a speaker whose talk has already been given. It asks a question. It does
not assume an answer, and no part of it should be sent as though the answer
were already known.*

*The two lists below are not typed into this file: they are composed from the
field classification the publication gate itself reads
(`app/src/state/consent.ts`), so what this message promises and what the
repository would actually publish cannot drift apart.*

---

**Subject:** May we publish the recording of your {{ instance.short_name }} talk?

Dear {{ speaker.first_name }},

Thank you again for your talk, *{{ speaker.title }}*, given on
{{ speaker.date }} in {{ instance.organisation }} {{ instance.series }}. We recorded
the session, as we do for every seminar, and we are writing to ask whether we
may publish that recording. We have not published it, and we will not unless
you tell us we may.

**What we would publish, if you agree.** On our public events feed at
{{ instance.forum_host }}, and on our YouTube channel:
{{ consent.published_on_consent }}. Nothing else about you would go out. Your
e-mail address is never published, and neither is anything we hold internally
about how the seminar was organised.

**What is already public.** The programme of the seminar itself:
{{ consent.published_always }}. That is the announcement of a public talk, and
it went out when the seminar was scheduled.

**If you would rather we did not.** Please just say so — a single line is
plenty, and you do not owe us a reason. A no carries no consequence of any
kind. It changes nothing about your talk having been given, nothing about your
place in the series, and nothing about our inviting you again. We will not ask
you a second time, and nobody will chase you about it.

**You can change your mind afterwards, in either direction.** If you agree now
and would rather the recording came down in a month or in three years, write
to us and it comes down: your permission is what the publication check reads
every time our public data is rebuilt, so withdrawing it takes the recording
out of the feed. Agreeing today does not sign anything away permanently.

Either answer is genuinely useful to us, and a short reply is all we need.

Warm regards,

{{ host_1.name }}
*for {{ instance.organisation }} team*

---

## Notes for the volunteer sending this

- Send it to one speaker at a time, from a real person, and record what they
  reply — exactly what they reply. The workspace offers two answers, *they
  agreed* and *they refused*, because those are the only two things a speaker
  can tell you. Silence is not a third answer; if nobody replies, leave the
  record alone.
- A refusal is a complete and ordinary outcome. Record it the same day, with
  the same lack of ceremony as an agreement.
- If a speaker writes back later to withdraw an agreement, record the refusal:
  that takes the recording out of the public feed on the next rebuild, and
  somebody still has to take the video down from YouTube by hand.
