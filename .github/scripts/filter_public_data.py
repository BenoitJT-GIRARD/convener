"""Filter data/speakers.yml down to public-safe fields and emit events-public.json.

The unified schema has all event-side fields on the speaker. Public output
exposes only the title, date, status, abstract, host institution + name, and
post-event YouTube URL. Never emits emails, votes, notes, host, or runbook_progress.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEAKERS_FILE = ROOT / 'data' / 'speakers.yml'

PUBLIC_STATUSES = {'scheduled', 'delivered', 'archived'}

speakers = yaml.safe_load(SPEAKERS_FILE.read_text(encoding='utf-8')) or []

out: list[dict] = []
for s in speakers:
    if not isinstance(s, dict):
        continue
    status = s.get('status', '')
    if status not in PUBLIC_STATUSES:
        continue
    youtube = s.get('youtube_url', '') if status in ('delivered', 'wrapped', 'archived') else ''
    registration = s.get('zoom_link', '') if status == 'scheduled' else ''
    out.append({
        'id': s.get('edition_code', ''),
        'title': s.get('title', ''),
        'date': s.get('date', ''),
        'status': status,
        'abstract': s.get('abstract', ''),
        'youtube_url': youtube,
        'registration_link': registration,
        'forum_thread': s.get('forum_thread', ''),
        'speaker_name': s.get('name', ''),
        'speaker_affiliation': s.get('affiliation', ''),
        'speaker_country': s.get('country', ''),
    })

out.sort(key=lambda r: r.get('date', ''), reverse=True)

out_dir = ROOT / 'public-data'
out_dir.mkdir(exist_ok=True)
(out_dir / 'events-public.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False) + '\n', encoding='utf-8',
)
print(f'wrote {len(out)} events to {out_dir / "events-public.json"}')
