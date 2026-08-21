# Phase 4 — After the webinar

Quick and simple beats slow and polished. Aim to finish within a few days.

## Note the discussion as it happens

Nobody writes the discussion down for you, so the two of you do — in a few lines, while hosting. Notes that cost more than a couple of seconds each will not be taken, so keep them cheap:

- **Agree beforehand who holds the notes.** The host reading the questions out cannot write at the same time; the other one can. Swap when you swap roles.
- **Write the question in a few words, and the point of the answer in one line.** Not the wording — the point. If a name, a paper or a link is mentioned, that is the one thing worth catching in full.
- **Mark what comes back twice.** A theme that returns in three questions is a paragraph of the summary; a one-off is a line, or nothing.
- **Half of it is already written.** The questions from the forum are in the thread, in the askers' own words, and the host watching the chat can paste the ones asked there straight into the notes as they come.
- **Give it five minutes at the end**, before closing anything: fill the gaps while it is all still fresh. This is the step people skip, and it is the one that makes the write-up easy.

## Post a summary on the forum

Write your notes up into a short, readable summary and post it under the announcement thread — [template](../toolkit/forum-post-summary.md), which says how to structure it and what to check before posting. It is a **summary, not a record of everything said**: give context, be tactful, organise it well. Show the draft to the speaker before you post it.

## If the event ran without a meeting-platform account

Skip this section entirely if the series' own meeting-platform account handled the session — attendance is read automatically and nothing here applies.

Otherwise, before anyone can issue certificates: download the attendance export from wherever the session actually ran, then encrypt and commit it.

1. Save it locally as `data/events/<event id>/attendance-import.csv` (never commit this file directly — it holds names and addresses in the clear).
2. From `tools/`, run `EVENT_ID=<event id> uv run convener-encrypt-attendance-export`. This needs no account and no secret; it only reads the event's already-published public key.
3. Commit and push the `attendance-import.csv.enc` file this writes.

See [operations reference](../reference/operations.md) ("Encrypting the manual attendance export") for the full procedure. Tick the matching line below once this is done — issuing certificates re-reads this file, so nothing can proceed without it.

## Two boundaries when matching attendance

Before certificates are issued, attendance is matched against registrations by matching code, then by address, then by normalised name. Two things can come out of that which are not the same, and must not be reported as if they were:

- **Unmatched** — someone was in the room, but nothing tied their address or name to a registration. This is the case worth resolving by hand: [operations reference](../reference/operations.md#matching-attendance) ("Matching attendance") writes a short list for exactly that.
- **Unreachable** — someone joined by telephone, so the platform gave us no address and no display name to match against at all. This is not a case to resolve — it is a boundary of the phone connection itself, and it is stated on the event page too, for the same reason: turning up without registering, or joining in a way that cannot be matched, are both reported honestly, never silently folded into "not eligible" without saying why.

Never report a telephone joiner as unmatched. They were never reachable to begin with, and treating the two the same sends whoever is doing the manual review chasing an address the platform never collected.

## Retrieve the recording before the platform copy is deleted

Whichever platform hosted the session has limited storage, and a scheduled job frees it by deleting its own copy once retrieval is confirmed. Download the recording and archive it somewhere durable — your own drive, the series' own storage, wherever the team keeps these — before that happens. Tick the matching line below once it is safely saved elsewhere; only tick it once the file genuinely exists somewhere else, since a premature tick is what lets the platform's own copy be deleted.

## 🚪 The gate — publishing the recording

{{> fragments/board-rules-publication-gate }}

Once cleared, publish the recording on the series' own video channel and announce it on the forum. There is nobody outside the team to send it to — see [Contacts](../reference/contacts.md).

## Thank the speaker

Send a short, warm thank-you — [template](../toolkit/emails/thank-you.md). Mention the engagement and the audience numbers; speakers value it.

## Note the numbers

Add the four numbers for this webinar to the event list: registrations, peak live attendance, video views once the counting window has passed, and forum replies. They feed the Board's yearly review.

**The counting window is a convention.** Views keep arriving for years, so a view count is not a fact about a talk until somebody says when it was read off; without an agreed moment the four numbers are not comparable with each other, and a session from March quietly outranks one from November for no reason but its age. The series reads them **30 days after the talk**. There is nothing behind the 30: it is long enough that most of the views have arrived and short enough that somebody still remembers to look, and any other number chosen once would do the same job. What matters is that it is the same number every time.

Because it is a convention and not a law, it is configuration: `view_count_window_days` in `data/config.yml`. Change it there and both the app and the validator follow: the Archive's field relabels itself, and the number stated above is read out of this page and checked against the file (`tools/tests/test_handbook_claims.py`), so the handbook and the form cannot end up claiming different windows. Change it rarely, and know that counts taken under the old window and the new one are not comparable, which is exactly the problem the convention exists to avoid.

## Checklist

- [ ] Notes from the discussion written up while fresh
- [ ] Attendance export encrypted and committed — manual implementation only, skip if the meeting-platform account handled the session
- [ ] Recording retrieved and archived somewhere durable
- [ ] Draft summary shown to the speaker
- [ ] Summary posted on the forum thread
- [ ] Recording published on the video channel — only after the Board's green light
- [ ] Thank-you sent to the speaker
- [ ] Numbers noted in the event list
- [ ] **Handbook improved** — fix anything that was unclear or could be smoother. This is what keeps the handbook trustworthy.
