"""Close gate issues once their underlying decision has been made.

- A Gate 1 (Vote) issue closes when the speaker leaves status `lead`.
- A Gate 2 (Publish) issue closes when the event leaves status `delivered`.

Environment: GITHUB_REPOSITORY, GITHUB_TOKEN.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

REPO = os.environ['GITHUB_REPOSITORY']
TOKEN = os.environ['GITHUB_TOKEN']

HEADERS = {
    'Authorization': f'Bearer {TOKEN}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'tec-convener-gate-bot',
}


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f'https://api.github.com{path}',
        method=method, headers=HEADERS, data=data,
    )
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def list_open_gate_issues():
    qs = urllib.parse.urlencode({'state': 'open', 'labels': 'gate', 'per_page': '100'})
    return call('GET', f'/repos/{REPO}/issues?{qs}')


def close_issue(number: int, comment: str) -> None:
    call('POST', f'/repos/{REPO}/issues/{number}/comments', {'body': comment})
    call('PATCH', f'/repos/{REPO}/issues/{number}', {'state': 'closed'})
    print(f'closed #{number}')


def main() -> int:
    speakers = yaml.safe_load(Path('data/speakers.yml').read_text(encoding='utf-8')) or []
    events = yaml.safe_load(Path('data/events.yml').read_text(encoding='utf-8')) or []
    spk_status = {s['id']: s.get('status') for s in speakers if 'id' in s}
    ev_status = {e['id']: e.get('status') for e in events if 'id' in e}

    for issue in list_open_gate_issues():
        if 'pull_request' in issue:
            continue
        title = issue['title']
        if title.startswith('Gate 1 — Vote:'):
            for s in speakers:
                name = s.get('name')
                if name and name in title:
                    status = spk_status.get(s['id'])
                    if status and status != 'lead':
                        close_issue(issue['number'], f'Decision recorded: `{s["id"]}` is now `{status}`.')
                        break
        elif title.startswith('Gate 2 — Publish:'):
            for eid, st in ev_status.items():
                if eid in title and st and st != 'delivered':
                    close_issue(issue['number'], f'Publication handled: `{eid}` is now `{st}`.')
                    break

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
