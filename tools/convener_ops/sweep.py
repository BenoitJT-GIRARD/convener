"""Persist the scheduled -> delivered transition.

The browser derives this for display; only this job writes it. A single writer
means two people opening the app at once can never race on the same file.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def _start(date: str, time: str) -> datetime:
    naive = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=PARIS)


def _has_ended(entry: dict[str, Any], duration_minutes: int, now: datetime) -> bool:
    date = entry.get("date") or ""
    if not date:
        return False
    time = entry.get("time") or ""
    if time:
        return now >= _start(date, time) + timedelta(minutes=duration_minutes)
    # No wall-clock time is known for this entry, so there is no Paris local
    # instant to compare against; fall back to now's own calendar date.
    return date < now.date().isoformat()


def sweep(
    speakers: list[dict[str, Any]],
    config: dict[str, Any],
    now: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return the swept list and a human-readable log of what changed."""
    duration = int(config.get("seminar_duration_minutes") or 90)
    swept = copy.deepcopy(speakers)
    changes: list[str] = []
    for entry in swept:
        if entry.get("status") != "scheduled":
            continue
        if _has_ended(entry, duration, now):
            entry["status"] = "delivered"
            changes.append(f"{entry.get('id')}: scheduled -> delivered")
    return swept, changes
