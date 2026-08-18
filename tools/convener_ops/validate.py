"""Pure validation of the operational data files.

Every function takes already-parsed data and returns a list of human-readable
errors. Nothing here touches the filesystem — that belongs to cli.py.
"""

from __future__ import annotations

import re
from collections.abc import Collection
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

#: Governance model (schema v3, see app/src/data/types.ts). Kept in this
#: module rather than imported from governance.py because governance.py
#: does not define these vocabularies - it consumes already-valid ballots
#: and never needed to enumerate the legal values itself.
BALLOT_VALUES = frozenset({"yes", "abstain", "recused"})
CAREER_STAGES = frozenset(
    {"phd", "postdoc", "independent", "group-leader", "other", "undisclosed"}
)
#: '' is a legal consent: the migration sets it for any speaker whose status
#: never reached a publishable state (see scripts/migrate_v3.py, Task 5).
PUBLICATION_CONSENTS = frozenset({"", "granted", "refused", "pending"})

CONFIG_REQUIRED = frozenset(
    {
        "season",
        "vw_counter",
        "overlap_window_days",
        "seminar_duration_minutes",
        "board",
        "nominations",
        "board_min",
        "board_max",
        "vote_window_days",
        "objection_window_working_days",
        "inactivity_months",
        "balance_window_months",
        "sla_days",
    }
)
CONFIG_INTS = (
    "season",
    "vw_counter",
    "overlap_window_days",
    "seminar_duration_minutes",
    "board_min",
    "board_max",
    "vote_window_days",
    "objection_window_working_days",
    "inactivity_months",
    "balance_window_months",
)
SLA_DAYS_KEYS = frozenset(
    {
        "lead_decision",
        "invitation_follow_up",
        "summary_after_delivery",
        "recording_after_delivery",
    }
)
NEEDS_SCHEDULE = frozenset({"scheduled", "delivered", "archived"})

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
EDITION_RE = re.compile(r"^MRG-\d+$")
LOGIN_RE = re.compile(r"^[a-zA-Z0-9-]+$")


def _validate_ballots(
    entry: dict[str, Any], where: str, board_logins: Collection[str]
) -> list[str]:
    """Validate one speaker's selection.ballots against the governance model.

    Note on scope: this deliberately duplicates none of governance.py's
    eligibility math (threshold_for, eligible_voters, decide) - those answer
    "was this vote decided", a different question from "is this data well
    formed". In particular, decide() silently ignores a ballot cast by a
    login absent from the board (eligible_voters filters the board, so a
    stray ballot never inflates a count) - that tolerance is intentional and
    correct for tallying. Here, the same situation is an error: the
    validator's job is to say the data itself is malformed, not to shrug and
    carry on the way the tally must.
    """
    errors: list[str] = []
    selection = entry.get("selection")
    ballots = selection.get("ballots") if isinstance(selection, dict) else None
    if not isinstance(ballots, list):
        return errors

    seen_voters: set[Any] = set()
    for bindex, raw_ballot in enumerate(ballots):
        bwhere = f"{where}.selection.ballots[{bindex}]"
        if not isinstance(raw_ballot, dict):
            errors.append(f"{bwhere}: not a mapping")
            continue

        value = raw_ballot.get("value")
        if value not in BALLOT_VALUES:
            errors.append(f"{bwhere}: invalid ballot value {value!r}")

        if value == "recused" and not raw_ballot.get("coi_reason"):
            errors.append(f"{bwhere}: recusal requires coi_reason")

        voter = raw_ballot.get("voter")
        if voter in seen_voters:
            errors.append(f"{bwhere}: duplicate ballot from {voter!r}")
        else:
            seen_voters.add(voter)

        if board_logins and voter not in board_logins:
            errors.append(f"{bwhere}: ballot from a non-member ({voter!r})")

    return errors


def validate_speakers(
    speakers: Any, board_logins: Collection[str] = frozenset()
) -> list[str]:
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

        # career_stage and publication are schema-v3 additions (Task 1); a
        # not-yet-migrated file simply lacks them, same as gender above, so
        # only a present-but-unrecognised value is an error.
        career_stage = entry.get("career_stage")
        if career_stage is not None and career_stage not in CAREER_STAGES:
            errors.append(f"{where}: invalid career_stage {career_stage!r}")

        publication = entry.get("publication")
        if publication is not None:
            consent = (
                publication.get("consent") if isinstance(publication, dict) else None
            )
            if consent not in PUBLICATION_CONSENTS:
                errors.append(f"{where}: invalid publication consent {consent!r}")

        errors.extend(_validate_ballots(entry, where, board_logins))

    return errors


def validate_config(cfg: Any) -> list[str]:
    if not isinstance(cfg, dict):
        return ["config.yml: top-level must be a mapping"]

    errors: list[str] = []

    # Loud, explicit errors for the two schema-v2 keys schema v3 replaces.
    # A file that still carries either has not been migrated - saying so
    # here is far cheaper than a reader discovering it from a downstream
    # KeyError or, worse, from silently-ignored governance data.
    if "vote_threshold" in cfg:
        errors.append("config.yml: vote_threshold is obsolete, migrate to sla_days")
    if "board_members" in cfg:
        errors.append("config.yml: board_members is obsolete, migrate to board")

    missing = CONFIG_REQUIRED - set(cfg)
    if missing:
        errors.append(f"config.yml: missing keys {sorted(missing)}")

    board = cfg.get("board")
    if "board" in cfg and not isinstance(board, list):
        errors.append("config.yml: board must be a list")
    elif isinstance(board, list):
        for member in board:
            login = member.get("login") if isinstance(member, dict) else None
            if not isinstance(login, str) or not LOGIN_RE.match(login):
                errors.append(f"config.yml: invalid board member {login!r}")

    board_min = cfg.get("board_min")
    board_max = cfg.get("board_max")
    if (
        isinstance(board_min, int)
        and isinstance(board_max, int)
        and board_min > board_max
    ):
        errors.append("config.yml: board_min cannot exceed board_max")

    sla_days = cfg.get("sla_days")
    if "sla_days" in cfg and not isinstance(sla_days, dict):
        errors.append("config.yml: sla_days must be a mapping")
    elif isinstance(sla_days, dict):
        missing_sla = SLA_DAYS_KEYS - set(sla_days)
        if missing_sla:
            errors.append(f"config.yml: missing sla_days keys {sorted(missing_sla)}")

    for key in CONFIG_INTS:
        if key in cfg and not isinstance(cfg[key], int):
            errors.append(f"config.yml: {key} must be an integer")

    return errors
