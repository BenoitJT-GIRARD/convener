"""Persist the scheduled -> delivered transition, and expire vote windows.

The browser derives these for display; only this job writes them. A single
writer means two people opening the app at once can never race on the same
file.
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from convener_ops.governance import decide

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


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _active_board_logins(config: dict[str, Any]) -> list[str]:
    board = config.get("board")
    if not isinstance(board, list):
        return []
    return [
        str(member["login"])
        for member in board
        if isinstance(member, dict)
        and member.get("status") != "inactive"
        and member.get("login")
    ]


def _unavailable_logins(config: dict[str, Any], today: date) -> list[str]:
    """Logins declared away as of `today` (a temporary absence, distinct from
    the permanent `status: inactive` filtered in `_active_board_logins`)."""
    board = config.get("board")
    if not isinstance(board, list):
        return []
    away: list[str] = []
    for member in board:
        if not isinstance(member, dict):
            continue
        until = _parse_date(str(member.get("unavailable_until") or ""))
        if until is not None and until >= today:
            away.append(str(member.get("login")))
    return away


def expire_votes(
    speakers: list[dict[str, Any]],
    config: dict[str, Any],
    now: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Park a `lead` whose vote window closed without reaching the threshold.

    The decision itself is never re-derived here: `governance.decide` (the
    single source for that rule, shared with the display side) says whether
    the vote is decided or suspended. This function only adds the "the clock
    ran out" condition on top and never distinguishes decline from parking -
    a refusal is always a deliberate act, so expiry can only ever park.
    """
    window_days = int(config.get("vote_window_days") or 0)
    board_logins = _active_board_logins(config)
    swept = copy.deepcopy(speakers)
    changes: list[str] = []
    for entry in swept:
        if entry.get("status") != "lead":
            continue
        selection = entry.get("selection")
        if not isinstance(selection, dict):
            continue
        opened_on = _parse_date(str(selection.get("opened_on") or ""))
        if opened_on is None:
            continue
        deadline = opened_on + timedelta(days=window_days)
        if now.date() <= deadline:
            continue

        ballots = selection.get("ballots")
        if not isinstance(ballots, list):
            ballots = []
        unavailable = _unavailable_logins(config, now.date())
        outcome = decide(board_logins, unavailable, ballots)
        if outcome.suspended or outcome.decided:
            continue

        entry["status"] = "parked"
        changes.append(f"{entry.get('id')}: lead -> parked (vote window expired)")
    return swept, changes
