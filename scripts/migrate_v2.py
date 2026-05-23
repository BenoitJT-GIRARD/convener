"""Migrate data/speakers.yml from v1 (host/co_hosts) to v2 (host_1/host_2,
plus time, conflicts_of_interest). One-shot. Promotes any 'wrapped' status
to 'archived'.
"""
from __future__ import annotations
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEAKERS = ROOT / "data" / "speakers.yml"
CONFIG = ROOT / "data" / "config.yml"

ORDER = [
    "id", "name", "gender", "email", "affiliation", "country",
    "title", "abstract", "conflicts_of_interest",
    "source", "proposed_by", "links",
    "host_1", "host_2", "status", "selection",
    "edition_code", "date", "time",
    "zoom_link", "youtube_url", "forum_thread",
    "runbook_progress", "metrics", "notes",
]


def split_coi(notes: str) -> tuple[str, str]:
    if not notes:
        return "", ""
    m = re.match(r"^CoI:\s*(.*)$", notes.strip(), flags=re.IGNORECASE | re.DOTALL)
    if m:
        return "", m.group(1).strip()
    return notes, ""


def migrate_speaker(s: dict) -> dict:
    co_hosts = s.get("co_hosts") or []
    s["host_1"] = s.pop("host", "") or ""
    s["host_2"] = co_hosts[0] if len(co_hosts) >= 1 else ""
    s.pop("co_hosts", None)
    notes, coi = split_coi(s.get("notes", "") or "")
    s["notes"] = notes
    s["conflicts_of_interest"] = coi
    if "time" not in s:
        s["time"] = ""
    if s.get("status") == "wrapped":
        s["status"] = "archived"
    # Canonical order
    out: dict = {}
    for k in ORDER:
        if k in s:
            out[k] = s[k]
        else:
            # provide a sensible default for any missing key
            out[k] = (
                {} if k == "runbook_progress"
                else {"votes_for": [], "decided_on": ""} if k == "selection"
                else {"registrations": None, "live_peak": None, "youtube_views_30d": None, "forum_replies": None} if k == "metrics"
                else [] if k == "links"
                else ""
            )
    return out


def main():
    raw = yaml.safe_load(SPEAKERS.read_text(encoding="utf-8")) or []
    migrated = [migrate_speaker(dict(s)) for s in raw]
    out = "# Speakers (unified schema v2 — see docs/reference/schema.md)\n" + yaml.dump(
        migrated, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000,
    )
    SPEAKERS.write_text(out, encoding="utf-8")

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    if "seminar_duration_minutes" not in cfg:
        cfg["seminar_duration_minutes"] = 90
        text = "# Repo-wide config for the Convener app\n" + yaml.dump(
            cfg, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000,
        )
        CONFIG.write_text(text, encoding="utf-8")
        print("added seminar_duration_minutes=90 to config.yml")

    print(f"migrated {len(migrated)} speakers to v2 schema")


if __name__ == "__main__":
    main()
