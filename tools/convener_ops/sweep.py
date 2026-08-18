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

#: Spec default for the vote window when `config.vote_window_days` is absent
#: or unusable. Days, counted from `selection.opened_on`.
DEFAULT_VOTE_WINDOW_DAYS = 14


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


def _paris_today(now: datetime) -> date:
    """The calendar day `now` falls on in Paris.

    Every other date in this module is a Paris local date; a caller passing a
    UTC clock would otherwise still be on the previous day between 00:00 and
    02:00 Paris, and the vote window would close a day late.
    """
    return now.astimezone(PARIS).date()


def _active_board(config: dict[str, Any], on: date) -> tuple[list[str], list[str]]:
    """Active board logins as of `on`, and the subset of them unavailable that
    day (`unavailable_until` is inclusive: away *on* that date, back the day
    after; an empty value means no declared absence).

    Mirrors `app/src/state/board.ts::activeBoard` and its Python twin
    `convener_ops.proposal._active_board`, which supply exactly this pair to
    `decide`. `status: inactive` is a permanent departure and leaves the board
    entirely; an unavailable member is still a member, only out of `N`.
    """
    board = config.get("board")
    if not isinstance(board, list):
        return [], []
    logins: list[str] = []
    unavailable: list[str] = []
    for member in board:
        if not isinstance(member, dict) or member.get("status") != "active":
            continue
        login = member.get("login")
        if not login:
            continue
        logins.append(str(login))
        until = str(member.get("unavailable_until") or "")
        if until and until >= on.isoformat():
            unavailable.append(str(login))
    return logins, unavailable


def _vote_window_days(config: dict[str, Any]) -> int:
    """The configured vote window, or the spec's 14-day default.

    Absent, zero, negative or non-integer: all fall back to the default rather
    than to zero. A config that never mentions the key must degrade to "do
    nothing today", never to "park every open lead tomorrow" - the scheduled
    job runs without a validation pass, so an unchecked config reaches here.
    """
    raw = config.get("vote_window_days")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        return DEFAULT_VOTE_WINDOW_DAYS
    return raw


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

    Eligibility (`N`) is read as of the sweep day, the same way the display
    side reads it as of the day it renders: `activeBoard(config, today)`.
    Neither side keeps a per-ballot roster, so "the vote date" of a window
    open for two weeks can only be the day the question is asked.
    """
    window_days = _vote_window_days(config)
    today = _paris_today(now)
    board_logins, unavailable = _active_board(config, today)
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
        # The window is the candidate's in full: the closing day is still a day
        # on which the board may vote, so expiry can only bite the day after.
        deadline = opened_on + timedelta(days=window_days)
        if today <= deadline:
            continue

        ballots = selection.get("ballots")
        if not isinstance(ballots, list):
            ballots = []
        outcome = decide(board_logins, unavailable, ballots)
        if outcome.suspended or outcome.decided:
            continue

        entry["status"] = "parked"
        changes.append(f"{entry.get('id')}: lead -> parked (vote window expired)")
    return swept, changes
