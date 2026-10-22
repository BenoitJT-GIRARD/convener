# How a webinar happens

Running a webinar has two parts:

- **Part 1 — Finding a speaker:** from a suggested name to a confirmed date.
- **Part 2 — Running the webinar:** preparing, hosting, and following up.

## The four phases

| Phase | What happens |
|---|---|
| [1 · Finding & validating speakers](1-sourcing-selection.md) | Find speakers; the Board validates them |
| [2 · Preparing the webinar](2-preparation.md) | The six-week countdown to the event |
| [3 · Hosting day](3-hosting.md) | The day itself |
| [4 · After the webinar](4-after.md) | Recording, summary, thank-you |

## A speaker's journey

```
Lead → [ Gate: the Board validates ] → Approved → Invited → Confirmed → Scheduled
```

- **Lead** — suggested, not yet validated.
- **Approved** — the Board said yes.
- **Invited / Confirmed** — invitation sent; the speaker accepts and sends their details.
- **Scheduled** — date locked. The webinar now exists, and preparation begins.

Three side outcomes: **Parked** (a good idea, kept for later, and reversible), **Declined (board)** and **Declined (speaker)** — who said no is kept, because the two lead to different messages and different second chances.

## What closes each status

An event has a page of its own in the workspace, and that page shows one status at a time. Every one of them is laid out the same way: **what you need to know, then what you do, then how you record that you did it.** The last of the three is a control, and it is the way onward — a record leaves a status because somebody presses one of these, never because a box was ticked or a field was filled in.

| Status | The controls that close it |
|---|---|
| Lead | **Submit ballot**, once the Board has enough of them; **Park** and **Decline** for the two side outcomes |
| Approved | **Mark invitation sent**, under the draft it has just filled the dates into |
| Invited | **They can make this one**, on the evening the speaker agreed to — that click is both the acceptance and the choice of date. **Speaker declined** when none of them suit |
| Confirmed | **Lock this date**, once the title, the abstract and the edition number are in |
| Scheduled | **Mark it delivered**, available from the day before the talk |
| Delivered | **Publish the recording and archive** — or **Archive without publishing**, when the speaker or the Board has refused |

The wording above is the wording on the buttons themselves. `app/tests/state/pipeline-and-manual.test.ts` reads this table against the journey the workspace runs and against the components that draw each control, and fails if any of the three stops agreeing with the other two.

## The two gates

Almost everything you do, you do on your own initiative. Only **two moments** need the Editorial Board's approval:

- 🚪 **Validating a speaker** — before anyone is invited.
- 🚪 **Publishing a recording** — before it goes public.

Everything in between is yours to run.
