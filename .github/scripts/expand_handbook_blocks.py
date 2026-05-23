"""Expand <!-- runbook:steps --> markers in handbook pages with content
generated from app/src/data/runbook.ts. Run by MkDocs as a hook before build.

The marker pair:
  <!-- runbook:steps -->
  ...auto-generated content here...
  <!-- /runbook:steps -->
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_TS = ROOT / 'app' / 'src' / 'data' / 'runbook.ts'

WINDOW_LABEL = {
    'T-6w': '6 weeks before',
    'T-4w': '4 weeks before',
    'T-2w': '2 weeks before',
    'T-1w': '1 week before',
    'T-1d': 'The day before',
}

def parse_runbook():
    text = RUNBOOK_TS.read_text(encoding='utf-8')
    rows = re.findall(
        r"\{\s*key:\s*'([^']+)'\s*,\s*window:\s*'([^']+)'\s*,\s*label:\s*'([^']+)'",
        text,
    )
    return rows  # list of (key, window, label)

def render_markdown(rows):
    by_window: dict[str, list[tuple[str, str]]] = {}
    for key, window, label in rows:
        by_window.setdefault(window, []).append((key, label))
    out = []
    for w in ['T-6w', 'T-4w', 'T-2w', 'T-1w', 'T-1d']:
        items = by_window.get(w, [])
        if not items:
            continue
        out.append(f"### {w} — {WINDOW_LABEL[w]}\n")
        for _, label in items:
            out.append(f"- [ ] {label}")
        out.append("")
    return "\n".join(out)

MARKER_RE = re.compile(
    r"(<!--\s*runbook:steps\s*-->)(.*?)(<!--\s*/runbook:steps\s*-->)",
    re.DOTALL,
)

def expand_file(path: Path) -> bool:
    text = path.read_text(encoding='utf-8')
    if '<!-- runbook:steps -->' not in text:
        return False
    rows = parse_runbook()
    md = render_markdown(rows)
    new = MARKER_RE.sub(lambda m: f"{m.group(1)}\n{md}\n{m.group(3)}", text)
    if new != text:
        path.write_text(new, encoding='utf-8')
        return True
    return False

def main():
    docs_dir = ROOT / 'docs'
    changed = []
    for p in docs_dir.rglob('*.md'):
        if expand_file(p):
            changed.append(p.relative_to(ROOT))
    if changed:
        print('expanded:', ', '.join(str(c) for c in changed))

if __name__ == '__main__':
    main()
