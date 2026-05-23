"""Validate data/*.yml against the unified schema.

Runs in CI on data/ commits. Fails on missing required fields, invalid
statuses, invalid co_hosts cardinality (for active scheduled status),
malformed dates, duplicate ids or edition_codes.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEAKERS = ROOT / "data" / "speakers.yml"
CONFIG = ROOT / "data" / "config.yml"

STATUSES = {
    "lead", "approved", "invited", "confirmed", "scheduled",
    "delivered", "wrapped", "archived",
    "parked", "decline-board", "decline-speaker",
}
GENDERS = {"M", "F", "NB", "undisclosed"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EDITION_RE = re.compile(r"^MRG-\d+$")
LOGIN_RE = re.compile(r"^[a-zA-Z0-9-]+$")
CONFIG_REQUIRED = {"season", "vw_counter", "vote_threshold", "overlap_window_days", "board_members"}

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
    seen_id: set[str] = set()
    seen_edition: set[str] = set()
    for i, s in enumerate(speakers):
        loc = f"speakers[{i}]"
        if not isinstance(s, dict):
            fail(f"{loc}: not a mapping")
            continue
        sid = s.get("id")
        if not sid:
            fail(f"{loc}: missing id")
        elif sid in seen_id:
            fail(f"{loc}: duplicate id {sid!r}")
        else:
            seen_id.add(sid)
        for k in ("name", "status"):
            if not s.get(k):
                fail(f"{loc} ({sid}): missing {k}")
        status = s.get("status")
        if status not in STATUSES:
            fail(f"{loc} ({sid}): invalid status {status!r}")
        gender = s.get("gender")
        if gender is not None and gender not in GENDERS:
            fail(f"{loc} ({sid}): invalid gender {gender!r}")
        date = s.get("date")
        if date and not DATE_RE.match(str(date)):
            fail(f"{loc} ({sid}): date must be YYYY-MM-DD, got {date!r}")
        edition = s.get("edition_code")
        if edition:
            if not EDITION_RE.match(edition):
                fail(f"{loc} ({sid}): edition_code must match MRG-N, got {edition!r}")
            elif edition in seen_edition:
                fail(f"{loc} ({sid}): duplicate edition_code {edition!r}")
            else:
                seen_edition.add(edition)
        # statuses that require edition + date
        if status in ("scheduled", "delivered", "wrapped", "archived"):
            if not edition:
                fail(f"{loc} ({sid}): status {status} requires edition_code")
            if not date:
                fail(f"{loc} ({sid}): status {status} requires date")
        # co_hosts is a list; for actively-scheduled we want exactly 2
        # (historical delivered/wrapped/archived may have empty co_hosts)
        co = s.get("co_hosts", [])
        if not isinstance(co, list):
            fail(f"{loc} ({sid}): co_hosts must be a list")
        elif status == "scheduled" and len(co) != 2:
            fail(f"{loc} ({sid}): co_hosts must have exactly 2 entries for scheduled")


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
    config = load(CONFIG)
    if speakers is not None:
        check_speakers(speakers)
    if config is not None:
        check_config(config)
    if errors:
        print("Data validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"Data OK — {len(speakers or [])} speakers, config=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
