# The Editorial Board

The Editorial Board is the small group that **steers the series**: it validates the speakers, approves recordings, and keeps the series true to its [editorial line](editorial-line.md).

## Who is on it

- A small, named group — not a crowd. To start: the four current organisers. Aim: about six.
- It is reviewed once a year (see below).
- Being on the Board is a real commitment: you take part in the speaker votes. The Board is the dependable core of the series.

## What a Board member does

Takes part in validating speakers; may approve recordings for publishing; reviews edits to the handbook; welcomes and confirms new Event Hosts; helps shape the editorial line and the rules.

## 🚪 The two gates, in one paragraph each

**Validating a speaker.** A suggested speaker is put to a vote; each Board member votes yes, abstains, or recuses themselves. Two-thirds of the eligible Board must say yes (a board of 6 → 4 yes; of 9 → 6), and the vote runs over about two weeks. Enough yes votes → validated. Not enough by the end of the window → kept for later. Never an automatic refusal.

**Publishing a recording.** A quick check (conflicts of interest, commercial content): one Board member approves, and it is done unless another member objects within three working days. That green light is only half of it — the speaker's own agreement is the other half, it is asked for separately, and silence is never taken for it. See [after the webinar](../workflow/4-after.md).

The exact mechanics of both — who counts, how the bar is computed, what a recusal does, how an objection is closed — are in **[the Board's rules, in detail](board-rules.md)**. Read that page once when you join; it is the whole of what binds you.

## Where the Board is written down — and why it is in two places

Two records name the Board, they answer different questions, and neither is
derived from the other.

**Who votes** is `data/config.yml`, edited from the cockpit's Board screen.
Every count the app makes reads it and nothing else: who is eligible, what the
two-thirds bar is today, who has declared an absence, which members a yearly
inactivity check would propose. It is the governance record, and it carries
what a record has to carry — the day each member joined, their status, the day
their absence ends.

**Who gets in** is a GitHub team, `editorial-board`, in the organisation this
repository belongs to. Signing in asks GitHub whether you are on it, and
GitHub's answer wins; the list above is read only when that call cannot be
made at all. It is access control, and it is deliberately not a file the
cockpit can write: everybody who could edit such a file is already inside it.

Neither can be folded into the other — a GitHub team has nowhere to record a
joining day or an absence, and a file the Board itself writes cannot be what
decides who the Board is. **What nothing yet enforces is that the two agree.**
A member removed from the team but left `active` in the file still counts
toward a bar they can no longer reach the app to meet; one added to the team
and not to the file signs in as a Board member and casts a ballot nothing
counts. Noticing that needs a call to GitHub with a token, so it is an
operator's check rather than a test — and it belongs with the "what is
configured, what is missing" command this project still owes itself.

## The Board as it stands today

Both of these are known, accepted and dated. Neither is a defect to be
rediscovered, and neither is a rule: the rules are on
[the Board's rules, in detail](board-rules.md), written against whoever the
Board happens to be.

**The Board is declared with five entries for four people, using first names rather than GitHub logins.** Until that is corrected at the September meeting, the bar is four out of four available voices — effective unanimity — and the app recognises only one of the five identifiers as a signed-in member. What has to change, and in what order, is written up in `docs/reference/operations.md` ("After the September collaborators' meeting"). Do not fix it piecemeal beforehand.

**No speaker on record has given publication consent.** All 31 have it empty or not yet answered, and none of them has been asked. Nothing may be published for any of them until they are asked and their answer is recorded — which is the gate working, not the gate being broken.

## Once a year — the start-of-season meeting

Each year the Board meets to:

1. **Review who is on the Board** — who joins, who leaves, the size for the year.
2. **Re-read the editorial line** and adjust the rules if needed.
3. **Set the season's aims** — the themes and the balance to aim for.

!!! warning "Season aims are a compass, not a fixed line-up"
    Speakers arrive all year round — you cannot choose a whole season in advance. The aims simply guide the choices; they never lock in slots.

## Other Board decisions

Changing a rule, adding a member, standing back from the Board: one member proposes it, and it carries unless another member objects in writing — in which case it waits for the yearly meeting. Joining and stepping back have their own windows and their own safeguards, all set out in [the Board's rules, in detail](board-rules.md).

That sentence stops one clause too early, and the missing clause is the one that decides what actually happens: what an objection has to carry, why it defers rather than refuses, and who — only ever one person — can lift it again. An objection here works exactly as it does on a nomination, so it is written once, there:

{{> fragments/board-rules-objection }}
