"""Open a gate issue when a lead exists or an event reaches delivered.

Idempotent: skips creation if an open issue with the same title already exists.
Triggered by changes to data/speakers.yml or data/events.yml.

Environment:
  GITHUB_REPOSITORY  — set by Actions ("owner/repo")
  GITHUB_TOKEN       — set by Actions
  ARCHITECT_USERNAME — optional GitHub login to assign as the default reviewer
  APP_URL            — optional base URL of the team app (e.g. https://.../app)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

REPO = os.environ['GITHUB_REPOSITORY']
TOKEN = os.environ['GITHUB_TOKEN']
ARCH = os.environ.get('ARCHITECT_USERNAME', '').strip()
APP_URL = os.environ.get('APP_URL', '').strip()

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


def issue_exists(title: str) -> bool:
    q = f'is:issue is:open repo:{REPO} in:title "{title}"'
    qs = urllib.parse.urlencode({'q': q})
    res = call('GET', f'/search/issues?{qs}')
    return any(item['title'] == title for item in res.get('items', []))


def open_issue(title: str, body: str) -> None:
    if issue_exists(title):
        print(f'already open: {title}')
        return
    payload: dict = {'title': title, 'body': body, 'labels': ['gate']}
    if ARCH:
        payload['assignees'] = [ARCH]
    res = call('POST', f'/repos/{REPO}/issues', payload)
    print(f'opened #{res["number"]}: {title}')


def main() -> int:
    speakers = yaml.safe_load(Path('data/speakers.yml').read_text(encoding='utf-8')) or []
    events = yaml.safe_load(Path('data/events.yml').read_text(encoding='utf-8')) or []

    for s in speakers:
        if s.get('status') == 'lead':
            name = s.get('name') or s.get('id', 'unknown')
            title = f'Gate 1 — Vote: {name}'
            link = f'{APP_URL}/speakers/{s.get("id", "")}' if APP_URL else '(team app)'
            body = (
                f'A new lead needs Board validation.\n\n'
                f'**Speaker:** {name} ({s.get("affiliation", "?")})\n'
                f'**Topic:** {s.get("topic", "?")}\n\n'
                f'Cast your vote: {link}'
            )
            open_issue(title, body)

    for e in events:
        if e.get('status') == 'delivered':
            eid = e.get('id', '?')
            title = f'Gate 2 — Publish: {eid}'
            link = f'{APP_URL}/events/{eid}' if APP_URL else '(team app)'
            body = (
                f'Webinar **{e.get("title", eid)}** is ready for the publication check.\n\n'
                f'Approve: {link}'
            )
            open_issue(title, body)

    return 0


if __name__ == '__main__':
    sys.exit(main())
