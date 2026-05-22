"""Filter data/ down to public-safe fields and emit events-public.json.

Whitelist (events): id, title, date, status, season, abstract, youtube_url,
                   registration_link, forum_thread, speaker_name, speaker_affiliation.
NEVER emitted: emails, votes, notes, owner, next_action, candidate proposals.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EVENTS_FILE = ROOT / 'data' / 'events.yml'
SPEAKERS_FILE = ROOT / 'data' / 'speakers.yml'

ALLOWED_STATUSES = {'upcoming', 'delivered', 'wrapped', 'archived'}

events = yaml.safe_load(EVENTS_FILE.read_text(encoding='utf-8')) or []
speakers = yaml.safe_load(SPEAKERS_FILE.read_text(encoding='utf-8')) or []
spk_by_id = {s['id']: s for s in speakers if isinstance(s, dict) and 'id' in s}

out: list[dict] = []
for e in events:
    if not isinstance(e, dict):
        continue
    if e.get('status') not in ALLOWED_STATUSES:
        continue
    s = spk_by_id.get(e.get('speaker_id'), {})
    status = e.get('status', '')
    youtube = e.get('youtube_url', '') if status in ('delivered', 'wrapped', 'archived') else ''
    registration = e.get('zoom_link', '') if status == 'upcoming' else ''
    out.append({
        'id': e.get('id', ''),
        'title': e.get('title', ''),
        'date': e.get('date', ''),
        'status': status,
        'season': e.get('season'),
        'abstract': e.get('abstract', ''),
        'youtube_url': youtube,
        'registration_link': registration,
        'forum_thread': e.get('forum_thread', ''),
        'speaker_name': s.get('name', ''),
        'speaker_affiliation': s.get('affiliation', ''),
    })

out_dir = ROOT / 'public-data'
out_dir.mkdir(exist_ok=True)
(out_dir / 'events-public.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(f'wrote {len(out)} events to {out_dir / "events-public.json"}')
