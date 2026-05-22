# Phase 1 — Sourcing & selection

This phase fills **Track 1** of the pipeline: turning potential speakers into confirmed, scheduled ones.

## Two ways speakers arrive

- **Inbound — the form.** A public application form (linked from the vitrine and the forum) lets anyone propose a speaker, or propose themselves. Each submission becomes a `lead`.
- **Outbound — outreach.** The Editorial Board and Event Owners can actively invite labs, institutes or individuals to suggest speakers, using the [outreach template](../templates/emails/outreach-sourcing.md). Outbound sourcing is steered by the season's editorial objectives.

Both feed the same place: a new `lead` in `data/speakers.yml`, with an `owner` (a DRI) assigned from the start.

## The pipeline states

```
Lead ──▶ Approved ──▶ Invited ──▶ Confirmed ──▶ Scheduled
```

Plus two off-pipeline buckets:

- **Parking Lot** — a good lead with no slot right now. Kept warm, revisited later.
- **Declined** — not retained, or the speaker said no. Kept on record so nobody re-pitches the same person.

## 🚪 Gate 1 — Selection

A `lead` becomes `approved` only by passing the Selection gate.

- **Decision rule:** a **two-thirds supermajority of the Editorial Board** votes YES. Default board of 6 → 4 YES. The vote runs on a ~2-week window.
- **If the threshold is reached** → `approved`: cleared to invite, ready to be matched to a slot and an Event Owner.
- **If not** → `parking-lot` (revisit later) or `declined`.
- **Criteria:** quality, diversity, a soft preference for early-career researchers, and conflicts of interest — all derived from the [editorial line](../governance/editorial-line.md). See [selection criteria](../governance/selection-criteria.md).

## Feedback to candidates

Nobody is left without an answer:

- **On submission** — an automatic acknowledgement (the form's confirmation message + email).
- **On decision** — a templated, kind message: [declined](../templates/emails/decision-declined.md) or [parked](../templates/emails/decision-parked.md).

## After approval

An `approved` speaker is picked up by an Event Owner, who sends the invitation — moving the entry to `invited`, then `confirmed` (speaker accepts and talk details are collected), then `scheduled` (date locked). At `scheduled`, the [handoff](overview.md#the-handoff) to Track 2 happens and the T-minus runbook begins.
