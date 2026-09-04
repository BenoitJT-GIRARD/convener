# The workspace

The handbook you are reading is one tab of an application, and the other tabs
are where the series is actually run. This page says what each of them is for.
It says nothing about *how* to decide anything — that is what the rest of the
handbook is — and it is deliberately short: a screen that needs a page of
explanation is a screen to fix, not to document.

You sign in with a GitHub account. Two roles exist and neither is applied for:
you are a **board** user if you are on the organisation's editorial team, and an
**organizer** user otherwise. The difference shows up as controls that are
present or absent, never as an error after you press something.

## The ten tabs

| Tab | What it answers |
|---|---|
| **Inbox** | What is waiting, mine first. Votes the Board owes, work an event owes, and the lines somebody has put their name against. Rows are ordered by how late they are against the turnaround times the series sets — `vote_window_days` for a Board decision, `sla_days` for the rest. |
| **Pipeline** | Where every live speaker stands, one column per status that still asks for work — from a suggested name to a talk that has been given and not yet wrapped up. This is also where a new speaker is added by hand. |
| **Agenda** | What still owes you something, month by month: booked webinars, and ones that have happened but are not wrapped up. It shows the gap the overlap window keeps between them, and it empties as the work is done — an empty Agenda is a clear horizon, not a screen that failed. |
| **Archive** | What is closed: archived webinars, parked leads, and the two kinds of decline. An event moves here the moment somebody archives it, and not before. The wrap-up numbers can still be filled in here weeks later. |
| **Board** | Membership and its rules in one place — who is active, who has declared an absence, nominations open and what they are due to become. |
| **Diversity** | How the programme is composed, one dimension at a time, applicants beside those selected. |
| **Consent** | Which speakers have not yet been asked whether their recording may be published, and the message that asks them. |
| **Handbook** | This handbook, rendered from the same files that are in the repository. |
| **Templates** | Every message and script, filled in from a record when you open one from an event, blank when you browse them here. |
| **Settings** | What this copy of the product owns and what it can reach: the paths an update leaves alone, the numbers the scheduled jobs read — settled here because several of them bound each other — and one row per outside service saying what it does, what to set to get it, and what happens meanwhile. No field on it holds a secret; those are set in the repository's own settings. |

The two lists never hold the same event. **The Agenda holds what still owes you
something; the Archive holds what is closed**, and archiving is the gesture
that moves a record from one to the other.

An event has a page of its own, reached from any of those lists. It carries the
record, the journey for the status it is in, and the two gates.

### Diversity, and why it looks understated

It reports counts against the denominator they were taken from, never
percentages, and never two dimensions at once. Both are on purpose. Over a
programme this size, a career stage crossed with a country is one identifiable
person, and a percentage of eleven people reads like a finding. Below ten
people who told us anything, it declines to break the numbers down at all and
says so. Nothing on it blocks anything: [the selection
criteria](governance/selection-criteria.md) are what the Board applies, and
this screen only shows the Board what it has been doing.

### Board, and what it will not do for you

Everything the [Board's rules](governance/board-rules.md) describe is
enacted here — opening a nomination, supporting one, objecting to one with a
reason, declaring an absence, recording what a nomination came to. Each open
nomination shows its own count against the bar and how far into its days it
is, so the Board can see how close it is while it still has time to act. What
the screen never does is close one by itself. It shows which nominations have
come due and then waits for a member to say so; nobody is seated overnight by
a job, and nobody is appointed by a quiet fortnight either.

## What runs when nobody is looking

Four scheduled jobs touch the data or the Board's mailbox. None of them decides
anything about a person, and none of them needs a volunteer's machine to be on.

- **The nightly sweep** moves a talk to delivered once its date has passed, and
  parks a lead whose vote window has run out. It also prints what the
  inactivity rule would propose about Board membership, and applies none of it.
- **The daily digest** posts one comment to the Board's notification thread
  saying what moved. Urgent things — a lead from the public form, a vote
  reaching its threshold, an objection — are posted when they happen instead of
  waiting for the morning.
- **The decision register** is rewritten from the commit history on every push,
  which is why [that page](governance/register.md) says not to edit it.
- **The public feed** is published for the public site from the records that
  have cleared the publication gate, and only those.

Two more run on every push and are how a mistake is caught early: the data
files are validated, and the application's own checks are run before it is
deployed. What each one needs configured, and what it does when it is not, is
in `docs/operating/operations.md`.

## When something looks wrong

The workspace reads and writes the files in this repository and nothing else.
So a number that looks wrong on a screen is a number in `instance/data/speakers.yml`,
and it can be corrected in either place. If a screen refuses something and does
not say why, that is a defect worth reporting rather than a rule you have not
understood: every refusal here is meant to name its reason.
