"""Validate data/*.yml against the expected shape.

Run by CI on every commit/PR touching data/. Fails on:
- Invalid YAML.
- Missing required fields (id, name, status).
- Invalid status values.
- Duplicate ids.
- Malformed dates (must be YYYY-MM-DD).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEAKERS = ROOT / "data" / "speakers.yml"
EVENTS = ROOT / "data" / "events.yml"
CONFIG = ROOT / "data" / "config.yml"

SPEAKER_STATUSES = {
    "lead", "approved", "invited", "confirmed", "scheduled",
    "parking-lot", "declined",
}
EVENT_STATUSES = {"upcoming", "delivered", "wrapped", "archived"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CONFIG_REQUIRED = {"season", "vw_counter", "vote_threshold", "overlap_window_days", "board_members"}
LOGIN_RE = re.compile(r"^[a-zA-Z0-9-]+$")

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def load(path: Path):
    if not path.exists():
        fail(f"{path.name}: file missing")
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        fail(f"{path.name}: invalid YAML — {e}")
        return None


def check_speakers(speakers) -> None:
    if not isinstance(speakers, list):
        fail("speakers.yml: top-level must be a list")
        return
    seen: set[str] = set()
    for i, entry in enumerate(speakers):
        loc = f"speakers[{i}]"
        if not isinstance(entry, dict):
            fail(f"{loc}: not a mapping")
            continue
        sid = entry.get("id")
        if not sid:
            fail(f"{loc}: missing id")
        elif sid in seen:
            fail(f"{loc}: duplicate id {sid!r}")
        else:
            seen.add(sid)
        if not entry.get("name"):
            fail(f"{loc} ({sid}): missing name")
        status = entry.get("status")
        if status not in SPEAKER_STATUSES:
            fail(f"{loc} ({sid}): invalid status {status!r}")


def check_events(events) -> None:
    if not isinstance(events, list):
        fail("events.yml: top-level must be a list")
        return
    seen: set[str] = set()
    for i, entry in enumerate(events):
        loc = f"events[{i}]"
        if not isinstance(entry, dict):
            fail(f"{loc}: not a mapping")
            continue
        eid = entry.get("id")
        if not eid:
            fail(f"{loc}: missing id")
        elif eid in seen:
            fail(f"{loc}: duplicate id {eid!r}")
        else:
            seen.add(eid)
        status = entry.get("status")
        if status is not None and status not in EVENT_STATUSES:
            fail(f"{loc} ({eid}): invalid status {status!r}")
        date = entry.get("date")
        if date and not DATE_RE.match(str(date)):
            fail(f"{loc} ({eid}): date must be YYYY-MM-DD, got {date!r}")


def check_config(cfg) -> None:
    if not isinstance(cfg, dict):
        fail("config.yml: top-level must be a mapping")
        return
    missing = CONFIG_REQUIRED - set(cfg.keys())
    if missing:
        fail(f"config.yml: missing keys {sorted(missing)}")
    bm = cfg.get("board_members")
    if not isinstance(bm, list):
        fail("config.yml: board_members must be a list")
    else:
        for b in bm:
            if not isinstance(b, str) or not LOGIN_RE.match(b):
                fail(f"config.yml: invalid board_member {b!r}")
    for k in ("season", "vw_counter", "vote_threshold", "overlap_window_days"):
        if k in cfg and not isinstance(cfg[k], int):
            fail(f"config.yml: {k} must be an integer")


def main() -> int:
    speakers = load(SPEAKERS)
    events = load(EVENTS) if EVENTS.exists() else None
    config = load(CONFIG) if CONFIG.exists() else None
    if speakers is not None:
        check_speakers(speakers)
    if events is not None:
        check_events(events)
    if config is not None:
        check_config(config)
    if errors:
        print("Data validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    nevents = len(events) if events else 0
    print(f"Data OK — {len(speakers or [])} speakers, {nevents} events, config={'ok' if config else 'missing'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
