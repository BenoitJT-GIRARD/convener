"""Persist the scheduled -> delivered transition, and expire vote windows.

The browser derives these for display; only this job writes them. A single
writer means two people opening the app at once can never race on the same
file.
"""

from __future__ import annotations

import calendar
import copy
from datetime import date, datetime, timedelta
from typing import Any

from convener_ops.governance import (
    MINIMUM_ELIGIBLE,
    PARIS,
    active_board,
    decide,
    last_ballot_on,
    paris_today,
)

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
    today = paris_today(now)
    board_logins, unavailable = active_board(config, today.isoformat())
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


# ------------------------------------------------------------------ #
# Inactivity (G-09)
#
# A member who has cast no ballot for `inactivity_months` stops counting
# toward `N`, so a board of five that has really been four for a year stops
# needing four voices to agree. That is the whole purpose of the rule, and it
# is also why the rule is not a departure: the entry stays in `config.yml`
# with its `login` and `joined_on` intact, `board.ts::seat` reactivates that
# same entry rather than adding a second one, and the annual meeting is what
# settles the question (G-09). Coming back costs one word in one field.
#
# `sweep_inactive_members` is a pure function and nothing in `cli.sweep`
# calls it. That absence is the design, not an oversight, and it has the same
# shape as the nomination vocabulary having no `rejected` value: a scheduled
# job with nobody's name on it must not be able to change a volunteer's
# standing overnight. What comes back is a *proposal* -- the config as it
# would read, and one line per member for a human to read, weigh and apply.
# The lines describe a silence in the ballot record; they do not describe a
# person.
# ------------------------------------------------------------------ #


def _inactivity_months(config: dict[str, Any]) -> int | None:
    """The configured silence threshold in months, or `None` for "nobody".

    Absent, zero, negative or non-integer all degrade to `None` rather than to
    a built-in default, which is the opposite choice from
    `_vote_window_days`'s. The two safe directions are opposite: there, the
    spec default is the value that parks nothing today; here, *any* number
    would name somebody, and no hand-edit to `config.yml` should be able to
    put a volunteer's name on a list by accident. A missing key means the
    board has not adopted the rule, so the rule says nothing.
    """
    raw = config.get("inactivity_months") if isinstance(config, dict) else None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        return None
    return raw


def _months_before(day: date, months: int) -> date:
    """`day` shifted back by whole calendar months, clamped to month length.

    Calendar months, not 30-day blocks: `inactivity_months` is written in the
    handbook as months, and a board reading "six months" at the annual meeting
    must get the same day the code used. 31 August minus six months is 28 (or
    29) February -- the last day of the target month, never a rollover into
    March, which would move the cutoff later and call a member silent a few
    days early.
    """
    index = (day.year * 12 + day.month - 1) - months
    year, month = divmod(index, 12)
    if year < date.min.year:
        return date.min
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _pending_candidates(config: dict[str, Any]) -> set[str]:
    """Logins carrying a nomination the board has not settled.

    The empty outcome and `waiting` are the two `board.ts::isPending` leaves
    open. A login the board is in the middle of admitting is already a live
    question; proposing the same person as inactive out of the same file would
    hand the annual meeting two contradictory papers about one person.
    """
    nominations = config.get("nominations")
    if not isinstance(nominations, list):
        return set()
    return {
        nomination["candidate"]
        for nomination in nominations
        if isinstance(nomination, dict)
        and isinstance(nomination.get("candidate"), str)
        and nomination.get("outcome") in ("", "waiting")
    }


def _is_away(member: dict[str, Any], today: date) -> bool:
    """Whether this entry declares an absence covering `today`.

    `unavailable_until` is inclusive -- the reading `active_board` and
    `board.ts::activeBoard` both apply.
    """
    until = member.get("unavailable_until")
    return isinstance(until, str) and bool(until) and until >= today.isoformat()


def _silent_since(
    member: dict[str, Any], speakers: list[dict[str, Any]], login: str
) -> date | None:
    """The day this member's silence is counted from, or `None` when it cannot
    be counted at all.

    The later of their last ballot and the day they joined -- not "the ballot,
    or `joined_on` if there is none". A member re-seated after a spell away
    (`board.ts::seat` rewrites `joined_on`) would otherwise be measured against
    ballots cast before they left, and could be proposed inactive on the very
    day they came back.

    `None` when neither date is usable, which is the live config's case today:
    every `joined_on` in `data/config.yml` is empty pending the identity merge.
    A record that cannot say when a silence began does not support a proposal
    -- inferring a start date would be inventing the evidence for it.
    """
    days = [
        parsed
        for value in (last_ballot_on(speakers, login), member.get("joined_on"))
        if isinstance(value, str) and value
        for parsed in (_parse_date(value),)
        if parsed is not None
    ]
    return max(days) if days else None


def sweep_inactive_members(
    config: dict[str, Any],
    speakers: list[dict[str, Any]],
    now: datetime,
) -> tuple[dict[str, Any], list[str]]:
    """Propose `active -> inactive` for members silent past the threshold.

    Returns the config as it would read once the proposal is applied -- a deep
    copy, the argument is never touched -- and one plain line per member for a
    human to read. Nothing here reaches disk and nothing in this package
    applies the result: see the note above.

    A member is proposed only when every one of these holds, and each of them
    is there to keep a contradictory pair out of the file rather than to be
    caught afterwards:

    * they are `active` -- an already-inactive entry is never re-proposed, so
      it can never collect a second line saying the same thing;
    * their silence has a countable start (`_silent_since`);
    * that start is strictly before today minus `inactivity_months` -- the
      threshold day itself is still a day on which they may vote, the same
      inclusive reading `expire_votes` gives the vote window;
    * they hold no absence covering today: a member who declared they are away
      told the board where they are, which is the opposite of silence, and
      `board.ts::declareUnavailability` only ever marks an *active* member
      away, so "inactive with an absence still running" would be a state no
      screen could produce and none could clear;
    * no unsettled nomination names them (`_pending_candidates`).

    Whatever remains is applied longest-silence-first and stops as soon as one
    more would leave fewer than `MINIMUM_ELIGIBLE` distinct active logins --
    the point below which `governance.decide` suspends every vote instead of
    deciding it. The held-back members still get a line, so the annual meeting
    reads the same list either way. That floor is `MINIMUM_ELIGIBLE` and not
    `board_min`: the live board is knowingly mis-declared (five entries for
    four people, `board_min: 5` pending the September merge to 3 -- see
    `docs/reference/operations.md`), and a rule keyed on that number would
    either do nothing at all on a wrong board or shrink it past the point
    where it can decide anything.
    """
    proposed: dict[str, Any] = copy.deepcopy(config) if isinstance(config, dict) else {}
    months = _inactivity_months(proposed)
    board = proposed.get("board")
    if months is None or not isinstance(board, list):
        return proposed, []

    today = paris_today(now)
    cutoff = _months_before(today, months)
    pending = _pending_candidates(proposed)
    speaker_list = speakers if isinstance(speakers, list) else []

    # Grouped by login, not by entry: a login the config lists twice is one
    # person, so it is proposed once, counted once against the floor, and both
    # of its entries move together rather than leaving a half-inactive member.
    entries: dict[str, list[dict[str, Any]]] = {}
    for member in board:
        if not isinstance(member, dict) or member.get("status") != "active":
            continue
        login = member.get("login")
        if isinstance(login, str) and login:
            entries.setdefault(login, []).append(member)

    silent: list[tuple[date, str]] = []
    for login, members in entries.items():
        if login in pending or any(_is_away(member, today) for member in members):
            continue
        starts = [
            since
            for member in members
            if (since := _silent_since(member, speaker_list, login)) is not None
        ]
        if not starts or min(starts) >= cutoff:
            continue
        silent.append((min(starts), login))

    order = list(entries)
    silent.sort(key=lambda row: (row[0], order.index(row[1])))

    remaining = len(entries)
    prompts: list[str] = []
    for since, login in silent:
        seen = since.isoformat()
        if remaining - 1 < MINIMUM_ELIGIBLE:
            prompts.append(
                f"{login}: no ballot since {seen}; not proposed - the board "
                f"would drop below the {MINIMUM_ELIGIBLE} members a vote needs"
            )
            continue
        for member in entries[login]:
            member["status"] = "inactive"
        remaining -= 1
        prompts.append(
            f"{login}: no ballot since {seen}; proposed inactive so the "
            f"threshold stops counting the seat - the seat is kept, the annual "
            f"meeting decides, and one word in config.yml undoes it"
        )
    return proposed, prompts
