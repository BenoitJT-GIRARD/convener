"""Migrate the split Speaker + Event schema to a single unified Speaker entity.

Reads data/speakers.yml + data/events.yml, joins them on event_id, writes
the unified data/speakers.yml, and removes data/events.yml. Writes
migration_warnings.txt for any co_hosts != 2 cases.
"""
from __future__ import annotations
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEAKERS = ROOT / "data" / "speakers.yml"
EVENTS = ROOT / "data" / "events.yml"
WARNINGS = ROOT / "migration_warnings.txt"

STATUS_MAP = {
    "lead": "lead",
    "approved": "approved",
    "invited": "invited",
    "confirmed": "confirmed",
    "scheduled": "scheduled",
    "parking-lot": "parked",
    "declined": "decline-board",
}

EVENT_STATUS_OVERRIDE = {
    "delivered": "delivered",
    "wrapped": "wrapped",
    "archived": "archived",
}


def split_topic(topic: str) -> tuple[str, str]:
    """Best-effort: first clause = title, rest = abstract."""
    if not topic:
        return "", ""
    for sep in [". ", " — ", " - ", ": "]:
        if sep in topic:
            head, _, tail = topic.partition(sep)
            return head.strip(), tail.strip()
    return topic.strip(), ""


def main() -> int:
    speakers = yaml.safe_load(SPEAKERS.read_text(encoding="utf-8")) or []
    events = yaml.safe_load(EVENTS.read_text(encoding="utf-8")) or [] if EVENTS.exists() else []
    events_by_id = {e["id"]: e for e in events}
    warnings: list[str] = []
    unified: list[dict] = []

    for s in speakers:
        title, abstract = split_topic(s.get("topic", ""))
        new = {
            "id": s["id"],
            "name": s["name"],
            "gender": "undisclosed",
            "email": s.get("email", "") or "",
            "affiliation": s.get("affiliation", "") or "",
            "country": s.get("country", "") or "",
            "title": title,
            "abstract": abstract,
            "source": s.get("source", "organizer") or "organizer",
            "proposed_by": s.get("proposed_by", "") or "",
            "links": s.get("links", []) or [],
            "host": s.get("owner", "") or "",
            "co_hosts": [],
            "status": STATUS_MAP.get(s.get("status", ""), "lead"),
            "selection": s.get("selection", {"votes_for": [], "decided_on": ""}) or {"votes_for": [], "decided_on": ""},
            "edition_code": "",
            "date": "",
            "zoom_link": "",
            "youtube_url": "",
            "forum_thread": "",
            "runbook_progress": {},
            "metrics": {
                "registrations": None, "live_peak": None,
                "youtube_views_30d": None, "forum_replies": None,
            },
            "notes": s.get("notes", "") or "",
        }

        eid = s.get("event_id", "")
        if eid and eid in events_by_id:
            e = events_by_id[eid]
            new["edition_code"] = eid
            new["date"] = e.get("date", "") or ""
            new["zoom_link"] = e.get("zoom_link", "") or ""
            new["youtube_url"] = e.get("youtube_url", "") or ""
            new["forum_thread"] = e.get("forum_thread", "") or ""
            new["runbook_progress"] = e.get("runbook_progress", {}) or {}
            new["metrics"] = e.get("metrics", new["metrics"]) or new["metrics"]
            ev_status = e.get("status", "")
            if ev_status in EVENT_STATUS_OVERRIDE:
                new["status"] = EVENT_STATUS_OVERRIDE[ev_status]
            ch = e.get("co_hosts", []) or []
            new["co_hosts"] = ch
            if new["status"] in ("scheduled", "delivered", "wrapped", "archived") and len(ch) != 2:
                warnings.append(f"{s['id']} ({s['name']}): co_hosts has {len(ch)} entries (expected 2 for {new['status']})")

        unified.append(new)

    out = "# Speakers (unified schema — see docs/reference/schema.md)\n" + yaml.dump(
        unified, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000,
    )
    SPEAKERS.write_text(out, encoding="utf-8")
    if warnings:
        WARNINGS.write_text("\n".join(warnings) + "\n", encoding="utf-8")
        print(f"WARNING: {len(warnings)} issue(s) written to {WARNINGS.name}")
    if EVENTS.exists():
        EVENTS.unlink()
        print("Removed data/events.yml")
    print(f"Wrote {len(unified)} unified speaker entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
