# Intro scripts

What the two hosts say in the first five minutes, in the order the
[run of show](run-of-show.md) puts it. That page owns the running order, the
timings and the split between Host 1 and Host 2; this page owns only the
words. Each script below is headed by the slide it is spoken over, so the two
pages cannot drift into disagreeing about what comes when.

**These are words to say, not a checklist.** Nothing in the app reads whether
you used them, and the pair who prefer their own phrasing are welcome to it.
They exist so that nobody has to invent a welcome at 12:29, and so that a
listener who came to two sessions in a row hears the same series described the
same way. Together they run about four minutes. Read them out loud once before
the session: a sentence that reads well is not always a sentence that says
well.

## Filling them in

Everything in `{{ double braces }}` is substituted from the speaker's record —
the workspace does it for you when it shows this page on the day, and shows
`«missing: …»` wherever the record is still empty rather than quietly leaving
a gap you would read aloud.

| Substitution | What it becomes |
|---|---|
| `{{ speaker.name }}` | The speaker's name as they gave it |
| `{{ speaker.first_name }}` | What you call them for the rest of the session |
| `{{ speaker.affiliation }}` | Their institution or lab |
| `{{ speaker.title }}` | The title of today's talk |
| `{{ speaker.bio }}` | The short biography they sent with the talk details |
| `{{ host_1.name }}`, `{{ host_2.name }}` | The two hosts |
| `{{ consent.spoken_recording }}` | What may be said about the recording |

One of those is not from the speaker's record. `{{ consent.spoken_recording }}`
is composed from the publication rule itself — the classification in
`app/src/state/consent.ts` that decides whether a recording may go online, and
on what. It is the one sentence here that states a rule rather than a fact
about today, so it is the one sentence that must not be typed out: if the rule
ever changes, the words the hosts read change with it, in the same commit.
Unlike the rest, it is filled in wherever this page is shown, including here.

Nothing here carries a worked example of a real past speaker. An example left
in a script is the sentence that gets read out by mistake — if you want to see
one filled in, open a delivered session in the workspace and read it there.

## Slide 2 — Welcome and housekeeping (Host 1)

*Said once the room has settled, and after the recording has been started.
The recording sequence itself — the one part of the day a mistake cannot
repair — belongs to [the run of show](run-of-show.md), under "Where the
recording starts and stops", and is not repeated here.*

> Good afternoon, everyone, and welcome. {{ consent.spoken_recording }}. So if
> you would rather not be in it, keep your camera and microphone off and you
> will not be. **The discussion after the talk is not published.**
> Questions are very welcome throughout: put them in the chat or in the forum
> thread, and we will bring them to the speaker at the end. And please do keep
> yourselves on mute until then. Over to {{ host_2.name }}, who is going to
> say a word about who we are.

## Slide 3 — {{ instance.organisation }} and the series (Host 2)

*Derived from the [editorial line](../governance/editorial-line.md) — the
series is described there, and if the two ever disagree, that page is right.*

> Welcome, everyone, and thank you for joining us. This is a seminar of
> **{{ instance.organisation }} {{ instance.series }}** — a community series on
> behavioural science. Our idea is simple: a talk is the start of a
> conversation, not the end. There is a discussion thread on our forum before
> and after every talk, and the Q&A today is a real discussion. If you have
> questions, drop them in the chat or on the forum and we will relay them.
> Now, over to my co-host to introduce today's speaker.

## Slide 4 — Today's speaker (Host 1)

*Fill from the biography collected with the
[talk details email](emails/talk-details.md). Read the biography as prose, not
as a list of posts — and check the pronunciation of the name with the speaker
in the tech check beforehand, not live.*

> Today we are delighted to host **{{ speaker.name }}**, from
> {{ speaker.affiliation }}. {{ speaker.bio }} Today,
> {{ speaker.first_name }} will present **{{ speaker.title }}**.
> {{ speaker.first_name }}, thank you so much for accepting our invitation; it
> is a real pleasure to have you. Before you begin, we ask every speaker to
> take us through their declaration of interests — then the floor is yours,
> and you can share your screen.

*The declaration slide that follows is the speaker's own, and the run of show
says what makes it a real one. Give them the silence to read it; do not fill
it.*

## What the hosts do not say

- **Do not name the person who asked a question** when you read one out.
- **Do not close on "no more questions? Then we stop."** The wording that
  works instead is in [Phase 3 — Hosting day](../workflow/3-hosting.md).
- **Do not promise that the recording will be published.** At this point in
  the day nobody has asked the speaker yet, and the answer is theirs.
