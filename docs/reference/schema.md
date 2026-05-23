# Data schema

The repo stores all operational data in two YAML files under `data/`:

- `data/speakers.yml` — the unified speaker + event entity (one entry per invitation lifecycle)
- `data/config.yml` — repo-wide configuration (board, thresholds, season counters)

Both files are validated in CI by `.github/scripts/validate_data.py` on every commit.

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
| `title` | string | Talk title (split from the legacy `topic` field). |
| `abstract` | string | Talk abstract (multi-line). |
| `source` | enum | `form` (Tally), `outreach` (team email), or `organizer` (added by hand). |
| `proposed_by` | string | Team member who proposed this speaker. |
| `links` | list&lt;string&gt; | URLs (ORCID, lab page, paper). |
| `host` | string | Team member responsible. Defaults to `proposed_by` at approval; reassignable. |
| `co_hosts` | list&lt;string&gt; | Exactly 2 entries for any scheduled+ status. |
| `status` | enum | State-machine managed. See below. |
| `selection.votes_for` | list&lt;string&gt; | Logins of board members who voted yes on this lead. |
| `selection.decided_on` | string | YYYY-MM-DD when the vote threshold was reached. |
| `edition_code` | string | `MRG-N` (assigned at `confirmed → scheduled`). Empty for non-scheduled. |
| `date` | string | YYYY-MM-DD (assigned at scheduling). |
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
- `approved` — board voted in favor; preparing invitation
- `invited` — invitation sent, awaiting reply
- `confirmed` — speaker accepted, no date locked yet
- `scheduled` — date locked + edition code assigned; runbook drives the rest
- `delivered` — event date passed (automatic transition)
- `wrapped` — post-event items done
- `archived` — wrapped + 30 days (automatic transition)
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

## Migration from the legacy split schema

The legacy schema had two files (`speakers.yml` + `events.yml`) joined on
`event_id`. The migration script (`scripts/migrate_to_unified_schema.py`) joins
them into the unified schema, splits the legacy `topic` into `title` + `abstract`
(best effort), renames `owner → host`, and removes `data/events.yml`.

Run once:

```sh
python scripts/migrate_to_unified_schema.py
```

Inspect any warnings in `migration_warnings.txt`, fix `co_hosts` cardinality
manually, then commit.
