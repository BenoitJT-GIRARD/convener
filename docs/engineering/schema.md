# Data schema

*This page is generated from `app/src/data/types.ts` — the model the browser
and `convener-validate` both read. Do not edit it: run* `uv run --frozen python scripts/generate_schema_doc.py` *from `tools/`
and commit what it writes, and CI refuses a page the types do not derive.
Every field, type, enumerated value and note below comes from the model; the
prose between the tables lives in `tools/scripts/generate_schema_doc.py`.*

The repository stores all operational data in two YAML files under `instance/data/`:

- `instance/data/speakers.yml` — the unified speaker + event entity, one entry per
  invitation lifecycle
- `instance/data/config.yml` — repository-wide configuration: the board, the thresholds,
  the season counters

Both files are validated in CI by `convener-validate` (see
`docs/operating/operations.md`) on every commit.

## `instance/data/speakers.yml`

Top-level: a list of speaker entries. Each entry covers the full lifecycle from
lead to archived. Speaker and event are the same record — the speaker fields
describe the human; the edition fields (`edition_code`, `date`, runbook,
metrics) describe the workshop they deliver.

### Fields

Every field below is a key each entry carries. A key left out is an incomplete
record and both readers refuse the file; an empty value is an answer — "none
given" — and is well formed.

| Field | Type | Notes |
|---|---|---|
| `id` | string | Immutable identifier, e.g. `spk-001`. Generated at creation. |
| `name` | string | The speaker's name, as they write it. |
| `gender` | enum | Self-reported, and only ever as the speaker gave it. Feeds the programme balance report. One of `M`, `F`, `NB` or `undisclosed`. |
| `career_stage` | enum | Self-reported career stage. Feeds the programme balance report. One of `phd`, `postdoc`, `independent`, `group-leader`, `other` or `undisclosed`. |
| `email` | string | Speaker contact address. |
| `affiliation` | string | Institution. |
| `country` | string | Two-letter code or full name. |
| `photo_url` | string | Portrait, asked for by the announcement visual. A link, not an upload: the repository holds records, not media. |
| `bio` | string | Short biography, which feeds the introduction script the host reads out. `''` is an answer -- "none given" -- and a missing key is not. |
| `linkedin` | string | LinkedIn handle, used to name the speaker in the promotion posts. |
| `title` | string | Talk title. |
| `abstract` | string | Talk abstract. Multi-line. |
| `seed_questions` | string | A few sentences from the speaker to open the forum discussion with. Free text, in their words, not a list this app parses. |
| `conflicts_of_interest` | string | Declared by the speaker or noted by the Board, for the Board's own recusal rules. Not the declaration made to the audience during the session, which is three lines of the runbook. |
| `source` | enum | How the lead reached the series: the public form, the team's own outreach, or a record added by hand. One of `form`, `outreach` or `organizer`. |
| `proposed_by` | string | Who suggested this speaker, as self-reported at submission time -- often someone outside the team. A person or nobody: `''` where nobody is on record. How the lead arrived is `source`'s answer and never this field's. Kept verbatim otherwise -- it is the only record of who to tell if the Board declines the lead -- and never overwritten by assignment. |
| `assigned_to` | string | Which board member currently looks after this lead, assigned by rotation (see `state/board.ts::assignLead`). Distinct from `proposed_by` -- do not merge the two: one is who nominated the speaker, the other is who is handling the follow-up. Empty until an assignment is made. |
| `links` | list&lt;string&gt; | URLs the lead arrived with: ORCID, lab page, a paper. |
| `host_1` | string | Login of the first Event Host. Both hosts are required from `scheduled` onwards. |
| `host_2` | string | Login of the second Event Host. |
| `status` | enum | Where the record stands. Managed by the state machine; see the statuses below. One of `lead`, `approved`, `invited`, `confirmed`, `scheduled`, `delivered`, `archived`, `parked`, `decline-board` or `decline-speaker`. |
| `selection.ballots` | list&lt;Ballot&gt; | One entry per voting board member. Replaces the former `votes_for` list of logins. |
| `selection.opened_on` | string | YYYY-MM-DD the vote opened. The vote window (`vote_window_days`) is counted from here; an empty value means `convener-sweep` can never expire the lead. |
| `selection.decided_on` | string | YYYY-MM-DD the threshold was reached. Empty while the lead is still open. |
| `publication.consent` | enum | The speaker's own permission to publish the recording. Only `granted` opens the gate: `pending` is where every delivered speaker starts, and no delay turns it into an agreement. One of `granted`, `refused`, `pending` or empty. |
| `publication.approved_by` | string | Login of the board member who recorded the approval. |
| `publication.approved_on` | string | YYYY-MM-DD of that approval. |
| `publication.objections` | list&lt;PublicationObjection&gt; | Objections raised during the objection window. An unresolved one blocks publication. |
| `publication.outcome` | enum | Where the record ended up. `published` is written in exactly one place, the gated archiving transition, so it cannot coexist with a refused consent, a standing objection, a missing approval, or an objection window that has not run. Empty while undecided. One of `published`, `withheld` or empty. |
| `edition_code` | string | The instance's declared `edition_prefix`, a hyphen and 1-4 digits (`MRG-7`, under the example instance's own prefix); assigned when a confirmed record is scheduled. Empty for a record that has not been scheduled. |
| `candidate_dates` | list&lt;CandidateDate&gt; | The slots put to the speaker, with their answers. Empty until the invitation goes out; it stays populated after the lock-in, because which dates were offered and which were refused is the record of how the chosen one was chosen. |
| `date` | string | YYYY-MM-DD of the talk, frozen at scheduling. |
| `time` | string | HH:MM, Paris local time, frozen at scheduling. |
| `zoom_link` | string | The meeting link the session runs on. |
| `youtube_url` | string | Where the recording sits. Recorded here; published only through the publication gate. |
| `forum_thread` | string | Link to the forum announcement thread. |
| `survey_enabled` | bool | Whether the post-event survey is open for this event. A per-event fact, not a `instance/data/config.yml` setting: the survey is switched on per event, and every other per-event fact -- the room link, the recording, the forum thread -- already lives on the speaker record rather than in the shared config. The three questions themselves are fixed for every event (`tools/convener_ops/journey/survey.py`'s module docstring); this is the only thing that varies. |
| `runbook_progress` | map&lt;string, bool&gt; | Which lines of the journey are ticked, keyed `phase/item`. |
| `checklist` | map&lt;string, ChecklistAssignee&gt; | Who owes each line of the journey, keyed by runbook item. An item with no entry here is nobody's in particular, which means the hosts' -- the behaviour the app has always had, and still the default. Never read from, and never written to, `assigned_to`. |
| `metrics.registrations` | number \| null | How many people registered. |
| `metrics.live_peak` | number \| null | Peak concurrent attendees during the live session. |
| `metrics.youtube_views_30d` | number \| null | Views of the recording, read off the number of days after the talk that `view_count_window_days` sets. The key keeps its historical name; the window it is read at is configuration. |
| `metrics.forum_replies` | number \| null | Replies on the forum thread. |
| `notes` | string | Free-form notes about the record. |

### `selection.ballots` entries

| Field | Type | Notes |
|---|---|---|
| `voter` | string | Login of the board member casting it. One ballot per member: re-voting replaces the earlier entry in place rather than adding a second. |
| `value` | enum | How they voted. One of `yes`, `abstain` or `recused`. |
| `comment` | string | Optional on every ballot. Asked for by the Board so a decision can be read years later without asking whoever cast it. |
| `coi_reason` | string | Required when value is 'recused'. A recusal without a written reason is not recorded — see governance.ts. |
| `date` | string | YYYY-MM-DD the ballot was cast. |

### `publication.objections` entries

| Field | Type | Notes |
|---|---|---|
| `member` | string | Login of the board member raising it. |
| `reason` | string | Why, in their own words. |
| `date` | string | YYYY-MM-DD it was raised. |
| `resolved_on` | string | YYYY-MM-DD the objection was closed. Empty means it still stands and publication is blocked. |

### `candidate_dates` entries

| Field | Type | Notes |
|---|---|---|
| `date` | string | YYYY-MM-DD of the slot offered. |
| `time` | string | HH:MM, Paris local time. |
| `answer` | enum | What the speaker said about this slot. Empty is the answer that has not come back yet; there is no value for a soft yes, so the transition that locks the date in never has to interpret one. One of `accepted`, `declined` or empty. |

### `checklist` entries

| Field | Type | Notes |
|---|---|---|
| `assignee` | string | Login of whoever owes this line. Empty -- and an item with no entry at all -- means nobody in particular, which means the hosts. |

There is no stored vote threshold. It is computed from the
eligible Board — active members, minus those who declared an absence, minus those
recused on this lead — as two thirds rounded up, never fewer than three yes ballots.
Below three eligible members the vote is suspended rather than decided on a bar that has
stopped meaning anything. The rule lives in `app/src/state/governance.ts` and
`tools/convener_ops/governance/rule.py`, pinned in both languages by
`tools/tests/fixtures/governance-cases.json`.

### Status values

The state machine governs transitions. Statuses:

- `lead` — submitted, awaiting board review
- `approved` — board voted in favour, invitation being prepared
- `invited` — invitation sent, awaiting reply
- `confirmed` — speaker accepted, no date locked yet
- `scheduled` — date locked and edition code assigned, the runbook drives the rest
- `delivered` — event date passed (automatic transition, see `convener-sweep`)
- `archived` — post-event items done (an explicit gesture, never automatic)
- `parked` — board paused this lead (reversible)
- `decline-board` — board collectively declined (reversible)
- `decline-speaker` — speaker declined the invitation

### `runbook_progress` key convention

Keys follow `phase/item` (e.g. `approved/host_1`, `scheduled/T-14/zoom-link`).
The phase definitions and gate semantics live in `app/src/state/phases.ts`, and
the countdown in `docs/handbook/workflow/2-preparation.md` is checked against them.
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

**Only a line somebody *does* carries a name.** A page to read (`Selection
criteria`) and a field whose content already names whoever is doing the thing
(`Host 1`, `Host 2`) are not work anybody owes, so the app draws no control
beside them and `app/src/state/assignment.ts` refuses a name written under one.
An entry left under such a key by an earlier edit stays in the file and is read
by nothing.

## `instance/data/config.yml`

One mapping, with the keys below.

| Field | Type | Notes |
|---|---|---|
| `season` | number | Current season number. |
| `next_edition_number` | number | The next edition number to assign, under the prefix `instance/config.json` declares. |
| `overlap_window_days` | number | Forbidden window around each scheduled date, in days. |
| `seminar_duration_minutes` | number | How long a seminar runs, in minutes. |
| `eligibility_share` | number | A share of `seminar_duration_minutes` a matched attendee's summed duration must reach to earn a certificate, in `]0, 1]`: above zero, at most one. Configuration, not a constant: the real number has to align with accreditation requirements this project does not yet know, and alignment happens by editing this file, not by editing code. |
| `board` | list&lt;BoardMember&gt; | The editorial board, one entry per member. Replaces the flat `board_members` list of logins. |
| `nominations` | list&lt;Nomination&gt; | Candidates put forward for the board, with their objection windows. |
| `board_min` | number | Fewest members the board may hold. |
| `board_max` | number | Most members the board may hold. |
| `vote_window_days` | number | How long a vote stays open, in days, counted from `selection.opened_on`. |
| `objection_window_working_days` | number | How long an objection window runs, in working days rather than calendar days (G-08). |
| `inactivity_months` | number | How many months without a ballot make a member inactive (G-14). |
| `balance_window_months` | number | How far back the programme balance report looks, in months. |
| `view_count_window_days` | number | How long after a talk its view count is read off, in days. |
| `instructions` | string | How to join the permanent room beyond the link itself -- a dial-in number, an access code, anything the room needs that the URL alone does not say. `''` is a legal answer: nothing more to add. |
| `sla_days.invitation_follow_up` | number | Days before an unanswered invitation is followed up. |
| `sla_days.summary_after_delivery` | number | Days after a talk before the forum summary is overdue. |
| `sla_days.recording_after_delivery` | number | Days after a talk before the recording is overdue. |
| `channels` | list&lt;Channel&gt; | Where an event is announced, in the order the volunteers work through them. Read only through `state/channels.ts::channelsOf`; an empty list is a legal answer and means nothing is promoted through this app. |

### `board` entries

| Field | Type | Notes |
|---|---|---|
| `login` | string | GitHub login. |
| `joined_on` | string | YYYY-MM-DD they joined the board. |
| `status` | enum | Whether they still vote. Inactive is not a departure and not a judgement. One of `active` or `inactive`. |
| `unavailable_until` | string | Inclusive end date of a declared absence. Empty when available. |

### `nominations` entries

| Field | Type | Notes |
|---|---|---|
| `candidate` | string | Login of the candidate. |
| `sponsor` | string | Login of the member who put them forward. |
| `opened_on` | string | YYYY-MM-DD the window opened. |
| `supports` | list&lt;Support&gt; | Members who have said yes. The sponsor's own is written when the nomination is opened; a majority of the eligible board is what carries it (G-05), and silence is a refusal rather than a consent. |
| `objections` | list&lt;Objection&gt; | Objections raised during that window. One defers the candidate to the annual meeting rather than being resolved. |
| `outcome` | enum | Where the nomination ended up. Empty while the window is still open. One of `accepted`, `deferred`, `waiting` or empty. |

### `nominations.supports` entries

| Field | Type | Notes |
|---|---|---|
| `member` | string | Login of the board member recording it. |
| `date` | string | YYYY-MM-DD it was recorded. |

### `nominations.objections` entries

| Field | Type | Notes |
|---|---|---|
| `member` | string | Login of the board member raising it. |
| `reason` | string | Why, in their own words. |
| `date` | string | YYYY-MM-DD it was raised. |

### `channels` entries

| Field | Type | Notes |
|---|---|---|
| `key` | string | What the record stores: it becomes the last segment of the promotion line's key, so renaming one re-keys what is already written and is a migration rather than an edit. |
| `label` | string | What a volunteer reads. Only ever shown, so it can be reworded at any time without touching a stored record. |

`board` replaces the former flat `board_members` list of
logins: a member now carries the date they joined, whether they are still active, and
any declared absence, because all three feed the vote threshold. There is no
`vote_threshold` key — see the ballot table above for why it is computed rather than
stored.

Each channel becomes one line of the promotion phase, keyed `promotion/<key>`,
so it carries an owner in `checklist` exactly like every other line. The `key`
is what records store, so renaming one re-keys what is already written and is a
migration rather than an edit; the `label` is only ever shown, and can be
reworded at any time. Removing a channel has the same property from the other
side: the owners already written under `promotion/<key>` stay in
`instance/data/speakers.yml`, on a line no screen shows any more. They are harmless, and
nothing in the app offers to clear them: the record page lists the lines the
journey currently has, so a key it no longer has has no control beside it.
Clearing one means putting the channel back in `channels`, taking the name off
the line on the record page, and removing the channel again — or editing
`instance/data/speakers.yml` on GitHub. Neither is urgent: an entry under a key no phase
holds is read by nothing. An empty list is a legal answer and means nothing is
promoted through this app; a `channels` that is missing, that is not a list,
that repeats a key, or that holds a channel with no label stops the file being
read at all, with a message naming the entry — a broken list must not read as a
deliberately empty one.

The `board` entries and the organisation's `editorial-board` team answer two
different questions, and neither is derived from the other. **This list is who
votes**: every count in the app — the eligible Board, the two-thirds bar, an
absence, an inactivity proposal — is computed from it, and from nothing else.
**The team is who gets in**: `detectRole` asks GitHub whether a signed-in
person is on it, and an answer from GitHub wins over this list, which is read
only when the call fails or cannot be made at all (demo mode, no network).

That split is deliberate. A GitHub team has no `joined_on`, no
`unavailable_until` and no `status`, so it cannot hold a governance record; a
file the cockpit writes with a signed-in volunteer's own token cannot be the
access control, because everyone who could edit it is already inside. What
nothing enforces is that the two agree — a member removed from the team but
left `active` here still counts toward the bar they can no longer reach the
app to meet. Comparing them needs a call to GitHub, so it is an operator's
check and not a test; see `docs/handbook/governance/editorial-board.md`.

## History

`instance/data/speakers.yml` was originally split across two files, joined on an event
id. One-shot migrations, since deleted, merged them into
today's unified schema; they already ran and are kept only as a record, not as
something to run again.
