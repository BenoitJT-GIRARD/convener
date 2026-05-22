"""Receive a Tally proposal payload and append a lead to data/speakers.yml.

Triggered via `repository_dispatch` event type `proposal-submitted`. Validates the
signature (if a shared secret is configured), parses the fields, assigns the next
`spk-NNN` id, and writes the YAML back. Commit + push happen in the workflow.
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

# Tally payloads put fields under data.fields[].label / data.fields[].value.
# Some clients send top-level fields; support both for robustness.
fields_list = payload.get('data', {}).get('fields') if isinstance(payload.get('data'), dict) else payload.get('fields')
if not isinstance(fields_list, list):
    fields_list = []
fields = {f.get('label', ''): f.get('value', '') for f in fields_list if isinstance(f, dict)}


def get(*keys: str) -> str:
    for k in keys:
        if k in fields and fields[k]:
            return str(fields[k]).strip()
    return ''


speakers = yaml.safe_load(SPEAKERS_FILE.read_text(encoding='utf-8')) or []

nums: list[int] = []
for s in speakers:
    if isinstance(s, dict):
        m = re.match(r'spk-(\d+)', s.get('id', ''))
        if m:
            nums.append(int(m.group(1)))
sid = f'spk-{(max(nums or [0]) + 1):03d}'

lead = {
    'id': sid,
    'name': get('Name'),
    'status': 'lead',
    'owner': '',
    'email': get('Email'),
    'affiliation': get('Institution', 'Affiliation'),
    'country': get('Country'),
    'topic': get('Topic', 'Main topic'),
    'source': 'form',
    'proposed_by': get('How you propose', 'Who are you'),
    'links': [],
    'selection': {'votes_for': [], 'decided_on': ''},
    'next_action': 'Review at next selection round',
    'next_action_date': '',
    'event_id': '',
    'notes': (
        f"Proposed title: {get('Preliminary title', '(preliminary) Title')} | "
        f"Abstract: {get('Short abstract', 'Summary', 'Abstract')} | "
        f"CoI: {get('Conflicts of interest')}"
    ).strip(' |'),
}
speakers.append(lead)

text = '# Speaker pipeline (Track 1) — see schema.md\n' + yaml.safe_dump(
    speakers, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000,
)
SPEAKERS_FILE.write_text(text, encoding='utf-8')
print(f'created {sid} from form proposal')
