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

| Field | Type | Notes |
|---|---|---|
| `id` | string | Immutable identifier, e.g. `spk-001`. Generated at creation. |
| `name` | string | Required. |
| `gender` | enum | `M`, `F`, `NB`, or `undisclosed`. |
| `email` | string | Speaker contact. |
| `affiliation` | string | Institution. |
| `country` | string | Two-letter code or full name. |
| `title` | string | Talk title. |
| `abstract` | string | Talk abstract (multi-line). |
| `conflicts_of_interest` | string | Declared by the speaker or noted by the Board. |
| `source` | enum | `form` (Tally), `outreach` (team email), or `organizer` (added by hand). |
| `proposed_by` | string | Team member who proposed this speaker. |
| `links` | list&lt;string&gt; | URLs (ORCID, lab page, paper). |
| `host_1`, `host_2` | string | The two Event Hosts. Both required for `scheduled` and later statuses. |
| `status` | enum | State-machine managed. See below. |
| `selection.votes_for` | list&lt;string&gt; | Logins of board members who voted yes on this lead. |
| `selection.decided_on` | string | YYYY-MM-DD when the vote threshold was reached. |
| `edition_code` | string | `MRG-N` (assigned at `confirmed → scheduled`). Empty for non-scheduled. |
| `date` | string | YYYY-MM-DD (assigned at scheduling). |
| `time` | string | HH:MM, Paris local time (assigned at scheduling). |
| `zoom_link` | string | Set during runbook step. |
| `youtube_url` | string | Filled after delivery. |
| `forum_thread` | string | Link to forum announcement thread. |
| `runbook_progress` | map&lt;string,bool&gt; | Keys follow `phase/item` convention. See below. |
| `metrics.registrations` | int \| null | Fill after delivery. |
| `metrics.live_peak` | int \| null | Peak concurrent attendees. |
| `metrics.youtube_views_30d` | int \| null | 30-day YouTube views. |
| `metrics.forum_replies` | int \| null | Replies on the forum thread. |
| `notes` | string | Free-form. |

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

## `data/config.yml`

```yaml
season: 2026                 # current season number
vw_counter: 5                # next MRG-N to assign
vote_threshold: 3            # majority of board for lead → approved
overlap_window_days: 7       # forbidden window around each scheduled date
board_members:               # GitHub logins with board role
  - Anonymous
  - alice
  - bob
```

`board_members` is used as fallback when the GitHub team API call (for role
detection) fails or returns no membership info. The authoritative source is
the org's `editorial-board` team; the config is a safety net.

## History

`data/speakers.yml` was originally split across two files, joined on an event
id. `scripts/` holds the one-shot scripts that merged them into today's
unified schema; they already ran and are kept only as a record, not as
something to run again.
