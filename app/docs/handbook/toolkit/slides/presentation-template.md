# Slide template — the hosts' deck

The hosts' own deck: the slides that surround the talk. Nine of them, and the
speaker's own deck is slides 5 and 6 — you never touch it, and you never paste
it into this one.

**What each slide carries is below. When each one goes up, who speaks over it
and how long it lasts are in the [run of show](../run-of-show.md); what is
said over slides 2, 3 and 4 is in the [intro scripts](../intro-scripts.md).**
Three pages, three questions, one answer each — build the deck from this page
and run the session from the other two.

Build it wherever you like: Canva, Google Slides, PowerPoint, anything you
already have. Duplicate last edition's deck rather than editing it, change the
substitutions listed below, and you are done in ten minutes.

## The substitutions

The same names as in the [intro scripts](../intro-scripts.md), so a deck and a
script filled from the same record say the same thing:

| Substitution | Appears on |
|---|---|
| `{{ speaker.name }}` | Slides 1, 4 |
| `{{ speaker.affiliation }}` | Slides 1, 4 |
| `{{ speaker.title }}` | Slides 1, 4 |
| `{{ speaker.date }}`, `{{ speaker.time }}` | Slide 1 |
| `{{ speaker.edition_code }}` | Slides 1, 9 |
| `{{ speaker.forum_thread }}` | Slides 1, 8, 9 |
| `{{ host_1.name }}`, `{{ host_2.name }}` | Slide 1 |

Type none of them in by hand from memory. Every one is in the speaker's record
in the workspace, and the record is what the announcement and the emails were
built from too.

## The slides

### 1 — Holding slide

Up before the session starts, while people arrive.

- **{{ instance.organisation }} {{ instance.series }}** — the series name, large.
- **{{ speaker.title }}** — today's title.
- **{{ speaker.name }}, {{ speaker.affiliation }}** and their photo.
- *We start at {{ speaker.time }}* — so a person arriving at 12:22 knows
  nothing has been missed.
- Edition **{{ speaker.edition_code }}**, {{ speaker.date }}.
- The forum thread: {{ speaker.forum_thread }}, with the QR code.
- Small, at the foot: *the talk is recorded; the discussion is not.*

### 2 — Welcome

Little on it: the series name and the two hosts' names. The words carry this
slide, not the slide.

### 3 — {{ instance.organisation }} and the series

One slide, four or five words each: what the series is, that a talk starts a
conversation, the forum, and how to ask a question (chat or forum). No
paragraphs — the host is speaking them.

### 4 — Today's speaker

- Photo, **{{ speaker.name }}**, **{{ speaker.affiliation }}**.
- **{{ speaker.title }}**.
- Nothing else. The biography is spoken, not projected; a bulleted CV on
  screen is read instead of listened to.

### 5 — Conflict-of-interest slide

**The speaker's own slide, in the speaker's own deck.** Do not build it, and
do not build a stand-in for it in case they forget: a declaration written by
the hosts is not a declaration. It is asked for in the
[talk details email](../emails/talk-details.md), and what makes it a real one
is set out in [the run of show](../run-of-show.md), under "The
conflict-of-interest slide".

### 6 — The talk

The speaker's deck, shared from their own screen.

### 7 — Questions and discussion

A plain slide, up while the discussion runs, carrying only the forum thread
and its QR code so a person joining late can still find it.

### 8 — Closing and next session

- Thank you to the speaker, by name, and to the audience.
- The forum thread: {{ speaker.forum_thread }} — *the conversation carries on
  here*.
- The next session, if there is one to announce: date, speaker, title. If
  there is not one confirmed yet, leave this line off rather than promising
  one.
- The recording is **not** promised here. Whether it goes online is the
  speaker's answer to a question they have not been asked yet.

### 9 — Closing slide

Stays up while people leave, and is the last thing anybody screenshots:
the forum link and QR code, the series name, and the edition code
**{{ speaker.edition_code }}**.

## Making it readable

- One idea per slide, and no slide the audience has to read while somebody
  talks over it.
- Type large enough to survive a phone screen — a good share of the audience
  is on one.
- Keep contrast high and do not rely on colour alone to carry a distinction.
- Test the deck in the meeting room's screen share, at the size the audience sees it, during
  the tech check — not for the first time at 12:30.
