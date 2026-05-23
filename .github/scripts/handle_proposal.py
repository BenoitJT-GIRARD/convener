"""Receive a Tally proposal payload and append a lead to data/speakers.yml.

Triggered via `repository_dispatch` event type `proposal-submitted`. Validates the
HMAC signature when a shared secret is configured, parses the form fields, assigns
the next `spk-NNN` id, and writes the YAML back on the unified schema.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEAKERS_FILE = ROOT / 'data' / 'speakers.yml'

GENDERS = {'M', 'F', 'NB', 'undisclosed'}

payload_str = os.environ.get('PROPOSAL_PAYLOAD', '')
signature = os.environ.get('PROPOSAL_SIGNATURE', '').strip()
secret = os.environ.get('TALLY_WEBHOOK_SECRET', '').strip()

if not payload_str:
    print('no payload', file=sys.stderr)
    sys.exit(1)

if secret:
    expected = hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        print('invalid signature', file=sys.stderr)
        sys.exit(1)

payload = json.loads(payload_str)

fields_list = (
    payload.get('data', {}).get('fields')
    if isinstance(payload.get('data'), dict)
    else payload.get('fields')
)
if not isinstance(fields_list, list):
    fields_list = []
fields = {f.get('label', ''): f.get('value', '') for f in fields_list if isinstance(f, dict)}


def get(*keys: str) -> str:
    for k in keys:
        if k in fields and fields[k]:
            return str(fields[k]).strip()
    return ''


speakers = yaml.safe_load(SPEAKERS_FILE.read_text(encoding='utf-8')) or []

# Idempotency: don't double-create on same email when still a lead.
new_email = get('Email')
if new_email and any(
    isinstance(s, dict) and s.get('email') == new_email and s.get('status') == 'lead'
    for s in speakers
):
    print(f'duplicate lead by email; skipping ({new_email})')
    sys.exit(0)

nums: list[int] = []
for s in speakers:
    if isinstance(s, dict):
        m = re.match(r'spk-(\d+)', s.get('id', ''))
        if m:
            nums.append(int(m.group(1)))
sid = f'spk-{(max(nums or [0]) + 1):03d}'

gender = get('Gender') or 'undisclosed'
if gender not in GENDERS:
    gender = 'undisclosed'

raw_links = get('Links', 'Profile links')
links: list[str] = []
if raw_links:
    if isinstance(raw_links, list):
        links = [str(x).strip() for x in raw_links if str(x).strip()]
    else:
        links = [s.strip() for s in str(raw_links).split(',') if s.strip()]

lead = {
    'id': sid,
    'name': get('Name'),
    'gender': gender,
    'email': new_email,
    'affiliation': get('Institution', 'Affiliation'),
    'country': get('Country'),
    'title': get('Preliminary title', '(preliminary) Title', 'Title'),
    'abstract': get('Short abstract', 'Summary', 'Abstract'),
    'source': 'form',
    'proposed_by': get('How you propose', 'Who are you'),
    'links': links,
    'host': '',
    'co_hosts': [],
    'status': 'lead',
    'selection': {'votes_for': [], 'decided_on': ''},
    'edition_code': '',
    'date': '',
    'zoom_link': '',
    'youtube_url': '',
    'forum_thread': '',
    'runbook_progress': {},
    'metrics': {
        'registrations': None,
        'live_peak': None,
        'youtube_views_30d': None,
        'forum_replies': None,
    },
    'notes': f"CoI: {get('Conflicts of interest')}".strip(),
}

if not lead['name']:
    print('skipping: empty name', file=sys.stderr)
    sys.exit(0)

speakers.append(lead)

text = '# Speakers (unified schema — see docs/reference/schema.md)\n' + yaml.safe_dump(
    speakers, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000,
)
SPEAKERS_FILE.write_text(text, encoding='utf-8')
print(f'created {sid} from form proposal')
