"""Pure validation of the operational data files.

Every function takes already-parsed data and returns a list of human-readable
errors. Nothing here touches the filesystem — that belongs to cli.py.
"""

from __future__ import annotations

import re
from typing import Any

STATUSES = frozenset(
    {
        "lead",
        "approved",
        "invited",
        "confirmed",
        "scheduled",
        "delivered",
        "archived",
        "parked",
        "decline-board",
        "decline-speaker",
    }
)
GENDERS = frozenset({"M", "F", "NB", "undisclosed"})
CONFIG_REQUIRED = frozenset(
    {
        "season",
        "vw_counter",
        "vote_threshold",
        "overlap_window_days",
        "seminar_duration_minutes",
        "board_members",
    }
)
CONFIG_INTS = (
    "season",
    "vw_counter",
    "vote_threshold",
    "overlap_window_days",
    "seminar_duration_minutes",
)
NEEDS_SCHEDULE = frozenset({"scheduled", "delivered", "archived"})

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
EDITION_RE = re.compile(r"^MRG-\d+$")
LOGIN_RE = re.compile(r"^[a-zA-Z0-9-]+$")


def validate_speakers(speakers: Any) -> list[str]:
    if not isinstance(speakers, list):
        return ["speakers.yml: top-level must be a list"]

    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_editions: set[str] = set()

    for index, entry in enumerate(speakers):
        where = f"speakers[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: not a mapping")
            continue

        sid = entry.get("id")
        where = f"{where} ({sid})"
        if not sid:
            errors.append(f"{where}: missing id")
        elif sid in seen_ids:
            errors.append(f"{where}: duplicate id {sid!r}")
        else:
            seen_ids.add(sid)

        for key in ("name", "status"):
            if not entry.get(key):
                errors.append(f"{where}: missing {key}")

        status = entry.get("status")
        if status not in STATUSES:
            errors.append(f"{where}: invalid status {status!r}")

        gender = entry.get("gender")
        if gender is not None and gender not in GENDERS:
            errors.append(f"{where}: invalid gender {gender!r}")

        date = entry.get("date")
        if date and not DATE_RE.match(str(date)):
            errors.append(f"{where}: date must be YYYY-MM-DD, got {date!r}")

        time = entry.get("time")
        if time and not TIME_RE.match(str(time)):
            errors.append(f"{where}: time must be HH:MM, got {time!r}")

        edition = entry.get("edition_code")
        if edition:
            if not EDITION_RE.match(str(edition)):
                errors.append(f"{where}: edition_code must match MRG-N, got {edition!r}")
            elif edition in seen_editions:
                errors.append(f"{where}: duplicate edition_code {edition!r}")
            else:
                seen_editions.add(edition)

        for key in ("host_1", "host_2"):
            value = entry.get(key, "")
            if value is not None and not isinstance(value, str):
                errors.append(f"{where}: {key} must be a string")

        if status in NEEDS_SCHEDULE:
            if not edition:
                errors.append(f"{where}: status {status} requires edition_code")
            if not date:
                errors.append(f"{where}: status {status} requires date")

        if status == "scheduled" and not (entry.get("host_1") and entry.get("host_2")):
            errors.append(f"{where}: scheduled requires both host_1 and host_2")

    return errors


def validate_config(cfg: Any) -> list[str]:
    if not isinstance(cfg, dict):
        return ["config.yml: top-level must be a mapping"]

    errors: list[str] = []

    missing = CONFIG_REQUIRED - set(cfg)
    if missing:
        errors.append(f"config.yml: missing keys {sorted(missing)}")

    members = cfg.get("board_members")
    if not isinstance(members, list):
        errors.append("config.yml: board_members must be a list")
    else:
        for member in members:
            if not isinstance(member, str) or not LOGIN_RE.match(member):
                errors.append(f"config.yml: invalid board_member {member!r}")

    for key in CONFIG_INTS:
        if key in cfg and not isinstance(cfg[key], int):
            errors.append(f"config.yml: {key} must be an integer")

    return errors
