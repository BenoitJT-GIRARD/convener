# Data model

The `data/` folder is the **structured source of truth** for the speaker pipeline and the event registry. Two YAML files, both plain text and versioned in Git. Any future interface (Chantier B) is just a projection of these files.

## `speakers.yml` — the speaker pipeline (Track 1)

A list of speaker entries. Each entry:

| Field | Meaning |
|---|---|
| `id` | Stable identifier (`spk-NNN`). Never reused. |
| `name` | Speaker full name. |
| `status` | Pipeline stage — see below. |
| `owner` | The DRI: the Event Owner / member shepherding this entry. Never blank once active. |
| `email` | Contact email. |
| `affiliation` | University / company. |
| `country` | Country. |
| `topic` | Talk topic / keywords. |
| `source` | How the lead arrived: `form` · `outreach` · `organizer`. |
| `proposed_by` | Who suggested this speaker. |
| `links` | List of URLs (profile, paper, …). |
| `selection.votes_for` | Editorial Board members who voted YES at Gate 1 — Selection. |
| `selection.decided_on` | Date the selection vote concluded (`YYYY-MM-DD`). |
| `next_action` | The single next thing to do. |
| `next_action_date` | When that next action is due (`YYYY-MM-DD`). |
| `event_id` | Once `scheduled`, links to an `events.yml` entry (`MRG-NN`). |
| `notes` | Free text. |

### `status` values

Active pipeline: `lead` → `approved` → `invited` → `confirmed` → `scheduled`
Off-pipeline buckets: `parking-lot` (good lead, no slot yet) · `declined`.

- `lead` — proposed, not yet vetted.
- `approved` — passed Gate 1 (Selection), cleared to invite.
- `invited` — invitation email sent.
- `confirmed` — speaker accepted; talk details collected.
- `scheduled` — date locked; an `events.yml` entry now exists.

## `events.yml` — the event registry (Track 2)

A list of webinar entries. Each entry:

| Field | Meaning |
|---|---|
| `id` | Webinar identifier (`MRG-NN`, zero-padded). |
| `speaker_id` | Links to a `speakers.yml` entry. |
| `title` | Talk title. |
| `date` | Webinar date (`YYYY-MM-DD`, a Thursday). |
| `status` | `upcoming` → `delivered` → `wrapped` → `archived`. |
| `season` | The year — the season. |
| `event_owner` | The DRI for this webinar. |
| `co_hosts` | `[host_mc, tech_producer]` for the day. |
| `zoom_link` / `youtube_url` / `forum_thread` | Links. |
| `metrics` | `registrations`, `live_peak`, `youtube_views_30d`, `forum_replies`. |

## Editing

Edit these files directly (Git web editor or any text editor). Keep them valid YAML — two spaces per indent level, no tabs. When Chantier B arrives it will read and write these same files; nothing else needs to change.

> Migrated from `Speakers database.xlsx` on 2026-05-22. Legacy per-organizer votes were preserved in `notes` — they predate the Editorial Board model and are not binding.
