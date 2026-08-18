# The speaker list and the event list

Two files hold the structured information of the series. They are kept in simple text so they last, and so the future companion app can read them.

## `speakers.yml` — the speaker list

One entry per speaker: name, the **stage** they have reached, the **owner**, contact details, topic, how they were proposed, and notes.

**Stages:** `lead` → `approved` → `invited` → `confirmed` → `scheduled`
Plus `parking-lot` (a good lead with no slot yet) and `declined`.

## `events.yml` — the event list

One entry per webinar (`MRG-01`, `MRG-02`, …): the speaker, title, date, status, the owner, the co-hosts, the links (Zoom, YouTube, forum) and the four numbers we track — registrations, peak live attendance, YouTube views, forum replies.

## Editing

The exact fields are listed at the top of each file. Keep the files tidy: two spaces per indentation level, never tabs. When the companion app arrives, it will edit these files for you.
