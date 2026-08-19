# Data schema

The repo stores all operational data in two YAML files under `data/`:

- `data/speakers.yml` — the unified speaker + event entity (one entry per invitation lifecycle)
- `data/config.yml` — repo-wide configuration (board, thresholds, season counters)

Both files are validated in CI by `convener-validate` (see `docs/reference/operations.md`)
on every commit.

## `data/speakers.yml`

Top-level: a list of speaker entries. Each entry covers the full lifecycle from
lead to archived. Speaker and event are the same record — the speaker fields
describe the human; the edition fields (`edition_code`, `date`, runbook, metrics)
describe the workshop they deliver.

### Fields

Every field below is a key each entry carries. A key left out is an
incomplete record and both readers refuse the file; an empty value is an
answer -- "none given" -- and is well formed.

| Field | Type | Notes |
|---|---|---|
| `id` | string | Immutable identifier, e.g. `spk-001`. Generated at creation. |
| `name` | string | Required. |
| `gender` | enum | `M`, `F`, `NB`, or `undisclosed`. |
| `career_stage` | enum | `phd`, `postdoc`, `independent`, `group-leader`, `other`, or `undisclosed`. Used for the programme balance report. |
| `email` | string | Speaker contact. |
| `affiliation` | string | Institution. |
| `country` | string | Two-letter code or full name. |
| `photo_url` | string | Link to the speaker's portrait, used by the announcement visual. Empty when none has been sent; the key is always present. |
| `bio` | string | Short biography, in the speaker's own words, which the introduction script is built from. Multi-line. Empty means none given. |
| `linkedin` | string | LinkedIn handle, used to mention the speaker in the promotion posts. |
| `title` | string | Talk title. |
| `abstract` | string | Talk abstract (multi-line). |
| `seed_questions` | string | A few sentences from the speaker to open the forum discussion with. Free text, not a list this app parses. |
| `conflicts_of_interest` | string | Declared by the speaker or noted by the Board. |
| `source` | enum | `form` (Tally), `outreach` (team email), or `organizer` (added by hand). |
| `proposed_by` | string | Whoever put this speaker forward, self-reported at submission and kept verbatim — often someone outside the team, since most leads arrive through the public form. It is the only record of who has to be told if the Board declines, so it is never overwritten by an assignment. |
| `assigned_to` | string | Login of the Board member who owns this lead and does the following up. Set by the rotation rule (G-17, `app/src/state/board.ts::assignLead`), empty while nobody owns it. Distinct from `proposed_by`: one says who suggested the speaker, the other who is handling them. |
| `links` | list&lt;string&gt; | URLs (ORCID, lab page, paper). |
| `host_1`, `host_2` | string | The two Event Hosts. Both required for `scheduled` and later statuses. |
| `status` | enum | State-machine managed. See below. |
| `selection.ballots` | list&lt;ballot&gt; | One entry per voting Board member — see the ballot fields below. Replaces the former `votes_for` list of logins. |
| `selection.opened_on` | string | YYYY-MM-DD the vote opened. The vote window (`vote_window_days`) is counted from here; an empty value means `convener-sweep` can never expire the lead. |
| `selection.decided_on` | string | YYYY-MM-DD the threshold was reached. Empty while the lead is still open. |
| `publication.consent` | enum | `granted`, `refused`, or `pending` — the speaker's own permission to publish the recording. Only `granted` opens the gate: `pending` is where every delivered speaker starts, and no delay turns it into a `granted`. Only `granted` and `refused` can be written by the app; `pending` is a starting value, never a decision. |
| `publication.approved_by` | string | Login of the Board member who recorded the approval. |
| `publication.approved_on` | string | YYYY-MM-DD of that approval. |
| `publication.objections` | list&lt;objection&gt; | `member`, `reason`, `date`, `resolved_on` — objections raised during the objection window. An empty or missing `resolved_on` means the objection still stands and publication is blocked. Nomination objections (G-08) carry no `resolved_on`: they defer the candidate to the annual meeting rather than being resolved. |
| `publication.outcome` | enum | `published`, `withheld`, or empty while undecided. `published` is written in exactly one place, the gated archiving transition, so it cannot coexist with a refused consent, a standing objection, a missing approval, or an objection window that has not run. |
| `edition_code` | string | `MRG-N` (assigned at `confirmed → scheduled`). Empty for non-scheduled. |
| `candidate_dates` | list&lt;slot&gt; | The slots put to the speaker with the invitation: `date` (YYYY-MM-DD), `time` (HH:MM) and `answer`. Kept after the date is locked in, because which slots were offered and which were refused is the record of how the chosen one was chosen. |
| `date` | string | YYYY-MM-DD (assigned at scheduling). |
| `time` | string | HH:MM, Paris local time (assigned at scheduling). |
| `zoom_link` | string | Set during runbook step. |
| `youtube_url` | string | Filled after delivery. |
| `forum_thread` | string | Link to forum announcement thread. |
| `runbook_progress` | map&lt;string,bool&gt; | Keys follow `phase/item` convention. See below. |
| `checklist` | map&lt;string,block&gt; | Who owes each runbook item, keyed the same way as `runbook_progress`. Each block holds one field, `assignee`, a login. `{}` -- and an item with no entry -- means nobody in particular, which means the hosts; that is the default and is not a defect. Distinct from `assigned_to`, which is the board member who owns the *lead*: the two are never derived from one another. |
| `metrics.registrations` | int \| null | Fill after delivery. |
| `metrics.live_peak` | int \| null | Peak concurrent attendees. |
| `metrics.youtube_views_30d` | int \| null | 30-day YouTube views. |
| `metrics.forum_replies` | int \| null | Replies on the forum thread. |
| `notes` | string | Free-form. |

### `candidate_dates` entries

| Field | Type | Notes |
|---|---|---|
| `date` | string | YYYY-MM-DD of the slot offered. Required. |
| `time` | string | HH:MM, Paris local time. Required. |
| `answer` | enum | `accepted`, `declined`, or empty. Empty is the answer that has not come back yet; there is no value for a soft yes, so the transition that locks the date in never has to interpret one. |

### `selection.ballots` entries

| Field | Type | Notes |
|---|---|---|
| `voter` | string | Login of the Board member casting the ballot. One ballot per member: re-voting replaces the earlier entry in place rather than adding a second. |
| `value` | enum | `yes`, `abstain`, or `recused`. |
| `comment` | string | Optional on any ballot. Asked for by the Board so a decision can be read years later without having to ask whoever cast it. |
| `coi_reason` | string | Required when `value` is `recused` — a recusal with no written reason is refused, not recorded. Empty otherwise. |
| `date` | string | YYYY-MM-DD the ballot was cast. |

There is no stored vote threshold. It is computed from the eligible Board —
active members, minus those who declared an absence, minus those recused on
this lead — as two thirds rounded up, never fewer than three yes ballots. Below
three eligible members the vote is suspended rather than decided on a bar that
has stopped meaning anything. The rule lives in `app/src/state/governance.ts`
and `tools/convener_ops/governance.py`, pinned in both languages by
`tools/tests/fixtures/governance-cases.json`.

### Status values

The state machine governs transitions. Statuses:

- `lead` — submitted, awaiting board review
- `approved` — board voted in favour; preparing invitation
- `invited` — invitation sent, awaiting reply
- `confirmed` — speaker accepted, no date locked yet
- `scheduled` — date locked + edition code assigned; runbook drives the rest
- `delivered` — event date passed (automatic transition, see `convener-sweep`)
- `archived` — post-event items done (explicit gesture, not automatic)
- `parked` — board paused this lead (reversible)
- `decline-board` — board collectively declined (reversible)
- `decline-speaker` — speaker declined the invitation

### `runbook_progress` key convention

Keys follow `phase/item` (e.g. `approved/hosts-decided`, `scheduled/T-14/zoom-link`).
The phase definitions and gate semantics live in `app/src/state/phases.ts`.
Checking the last gate of a phase auto-advances the speaker to the next status.

`checklist` is keyed the same way, one entry per line somebody has been put
down for:

```yaml
checklist:
  scheduled/T-30/visuals:
    assignee: ada
```

A line with no entry is nobody's in particular and stays the hosts'. Naming an
owner has never been asked of anybody and is not asked for here either: the app
raises no warning and no reminder over an empty checklist.

## `data/config.yml`

```yaml
season: 2026                       # current season number
vw_counter: 5                      # next MRG-N to assign
overlap_window_days: 7             # forbidden window around each scheduled date
seminar_duration_minutes: 90
board:                             # replaces the flat board_members list
  - login: Anonymous
    joined_on: 2024-01-01
    status: active                 # active | inactive
    unavailable_until: ''          # inclusive last day of a declared absence
nominations: []                    # candidate, sponsor, opened_on, objections, outcome
board_min: 3
board_max: 9
vote_window_days: 14               # counted from selection.opened_on
objection_window_working_days: 3    # working days, not calendar days (G-10)
inactivity_months: 12              # G-09: twelve months without a ballot
balance_window_months: 12
sla_days:
  lead_decision: 14
  invitation_follow_up: 7
  summary_after_delivery: 5
  recording_after_delivery: 10
```

`board` replaces the former flat `board_members` list of logins: a member now
carries the date they joined, whether they are still active, and any declared
absence, because all three feed the vote threshold. There is no
`vote_threshold` key — see the ballot section above for why it is computed
rather than stored.

The `board` entries are used as fallback when the GitHub team API call (for
role detection) fails or returns no membership info. The authoritative source
is the org's `editorial-board` team; the config is a safety net.

## History

`data/speakers.yml` was originally split across two files, joined on an event
id. `scripts/` holds the one-shot scripts that merged them into today's
unified schema; they already ran and are kept only as a record, not as
something to run again.
