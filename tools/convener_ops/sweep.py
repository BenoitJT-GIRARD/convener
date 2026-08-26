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
    vote_window_days,
)


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
    window_days = vote_window_days(config)
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
# needing four voices to agree. G-09 sets that window at twelve months and
# the code reads whatever `config.yml` declares: the series runs roughly
# monthly, so half a year of silence is a heavy teaching year, a sabbatical
# or a leave, and the rule has to be impossible to trigger by accident
# because the line it prints carries a real volunteer's login.
#
# Dropping out of `N` is the whole purpose of the rule, and it
# is also why the rule is not a departure: the entry stays in `config.yml`
# with its `login` and `joined_on` intact, `board.ts::seat` reactivates that
# same entry rather than adding a second one, and the annual meeting is what
# settles the question (G-09). Coming back costs one word in one field.
#
# `sweep_inactive_members` is a pure function. `cli._report_inactivity` calls
# it -- detection is what the scheduled task operates (G-09) -- and prints the
# lines only: the config it returns is dropped there and reaches no writer.
# That split is the design, not an oversight, and it has the same shape as the
# nomination vocabulary having no `rejected` value: a scheduled job with
# nobody's name on it must not be able to change a volunteer's standing
# overnight. What comes back is a *proposal* -- the config as it would read,
# and one line per member for a human to read, weigh and apply. The lines
# describe a silence in the ballot record; they do not describe a person.
#
# Voting eligibility in `config.yml` is the only thing this rule touches.
# Marking a member inactive does nothing to their GitHub repository write
# access -- the two are separate systems, and a former board member proposed
# inactive keeps that access, and with it the ability to read or exfiltrate
# any secret this repository holds -- this project applies least
# privilege to data, never to credentials. The proposed-inactive line below
# says so every time, at the moment a human is already reading it to act on
# that person, rather than once in a document nobody opens at the point of
# action.
#
# This function does not revoke that access itself, and it must not gain
# that ability later. Doing so would need an organisation-admin token -- a
# credential able to rewrite permissions across the whole organisation,
# more powerful than any secret this project currently holds. Adding it to
# close this gap would create a larger secret to protect than the one being
# closed. The fix is a human reading the line below and acting on GitHub
# directly, never a second scheduled job.
# ------------------------------------------------------------------ #


def _inactivity_months(config: dict[str, Any]) -> int | None:
    """The configured silence threshold in months, or `None` for "nobody".

    Absent, zero, negative or non-integer all degrade to `None` rather than to
    a built-in default, which is the opposite choice from
    `governance.vote_window_days`'s. The two safe directions are opposite:
    there, the spec default is the value that parks nothing today; here, *any*
    number
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


def _unsettled_candidates(config: dict[str, Any]) -> set[str]:
    """Logins carrying a nomination the board has not finished with.

    The same question `board.ts::isUnsettled` answers, and pinned to it by
    `tests/fixtures/governance-cases.json`'s `unsettled_nomination_cases`,
    read by both languages. A login the board is in the middle of admitting
    -- or in the middle of arguing about -- is already a live question;
    proposing the same person as inactive out of the same file would hand the
    annual meeting two contradictory papers about one person.

    Two ways a nomination is unsettled, and the second is the one this used
    to miss. It is *pending* while its outcome is empty or `waiting`: the
    automated path may still settle it. It is also unsettled while any
    objection stands on it, whatever the outcome says -- a `deferred`
    nomination is not a closed question, it is a question moved to the annual
    meeting, and "stands" is simply "is in the list", because a nomination
    objection is never marked resolved and the only thing that ends one is
    its author withdrawing it (`board.ts::withdrawObjection`). A hand-edited
    `deferred` carrying no objection at all is therefore settled here too:
    there would be nothing left to withdraw.
    """
    nominations = config.get("nominations")
    if not isinstance(nominations, list):
        return set()
    return {
        nomination["candidate"]
        for nomination in nominations
        if isinstance(nomination, dict)
        and isinstance(nomination.get("candidate"), str)
        and (
            nomination.get("outcome") in ("", "waiting")
            or bool(nomination.get("objections"))
        )
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

    `None` when neither date is usable. A record that cannot say when a
    silence began does not support a proposal -- inferring a start date would
    be inventing the evidence for it -- and an empty `joined_on` on a member
    who has never voted is exactly that record, whichever file it sits in.
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
    applies the result: its only caller prints the lines and drops the config,
    see the note above.

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
    * no unsettled nomination names them (`_unsettled_candidates`),
      including one deferred to the annual meeting over an objection that
      still stands -- the board is already arguing about that member;

    Whatever remains is applied longest-silence-first and stops as soon as one
    more would leave fewer than `MINIMUM_ELIGIBLE` distinct active logins --
    the point below which `governance.decide` suspends every vote instead of
    deciding it. The held-back members still get a line, so the annual meeting
    reads the same list either way. That floor is `MINIMUM_ELIGIBLE` and not
    `board_min`, and it would be whatever any file happened to declare:
    `board_min` is the size the board aims to be -- a target the tools
    report on and nothing enforces -- while `MINIMUM_ELIGIBLE` is the size
    below which `governance.decide` suspends every vote instead of deciding
    it. A rule that removes members must never be the thing that takes the
    board past the point where it can decide anything, including the
    decision to let those members go. A target cannot serve as that floor in
    either direction: keyed on `board_min`, this rule would decline to act
    on a board aiming high, and would strip one aiming low of the members a
    vote needs.
    """
    proposed: dict[str, Any] = copy.deepcopy(config) if isinstance(config, dict) else {}
    months = _inactivity_months(proposed)
    board = proposed.get("board")
    if months is None or not isinstance(board, list):
        return proposed, []

    today = paris_today(now)
    cutoff = _months_before(today, months)
    unsettled = _unsettled_candidates(proposed)
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
        if login in unsettled or any(_is_away(member, today) for member in members):
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
            f"meeting decides, and one word in config.yml undoes it. This "
            f"does not touch {login}'s GitHub repository write access - "
            f"revoke that separately on GitHub if their time on the board "
            f"is really ending"
        )
    return proposed, prompts
