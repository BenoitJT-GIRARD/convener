# Workflow — overview

Running a webinar is really two jobs, so the workflow has **two tracks**:

- **Track 1 — the speaker pipeline:** *getting* a speaker, from a name on a list to a locked date.
- **Track 2 — the event lifecycle:** *delivering* the webinar once a speaker and date are set.

They meet at a single handoff.

```
TRACK 1 — Speaker pipeline
  Lead ──▶ [Gate 1: Selection] ──▶ Approved ──▶ Invited ──▶ Confirmed ──▶ Scheduled
   │                                                                         │
   ├─▶ Parking Lot                                                           │
   └─▶ Declined                                                     HANDOFF ─┘
                                                                              ▼
TRACK 2 — Event lifecycle
  Upcoming (T-minus runbook) ──▶ Delivered ──▶ Wrapped ──▶ Archived
```

## The four phases

| Phase | Track | What happens |
|---|---|---|
| [1 · Sourcing & selection](1-sourcing-selection.md) | 1 | Find speakers, vet them at Gate 1 |
| [2 · Preparation](2-preparation.md) | 2 | The T-minus runbook, from invitation to the day before |
| [3 · Hosting day](3-hosting.md) | 2 | The day-of timeline and run-of-show |
| [4 · After the webinar](4-after.md) | 2 | Recording, summary, thank-you, metrics |

## The two gates

Most of the work happens in **autonomy** — an Event Owner advances without asking permission. Only two transitions pass a gate, validated by the Editorial Board:

- **🚪 Gate 1 — Selection:** a Lead becomes an invited speaker. Two-thirds supermajority of the Board.
- **🚪 Gate 2 — Publication:** content goes public (YouTube, forum summary). Lazy consensus.

See [Roles & ownership](../roles.md) for the gate mechanics.

## The handoff

When a speaker reaches **Scheduled** (date locked), an **event** is born: it gets an ID (`MRG-NN`), an entry in `data/events.yml`, and its own T-minus runbook. Track 1 found the speaker; Track 2 now delivers the webinar.
