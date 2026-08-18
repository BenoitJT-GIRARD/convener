from __future__ import annotations

from typing import Any


def ballot(**overrides: Any) -> dict[str, Any]:
    """A minimal valid ballot (schema v3); override any field per test."""
    base: dict[str, Any] = {
        "voter": "Anonymous",
        "value": "yes",
        "comment": "",
        "coi_reason": "",
        "date": "2026-01-08",
    }
    base.update(overrides)
    return base


def board_member(**overrides: Any) -> dict[str, Any]:
    """A minimal valid board member (schema v3); override any field per test."""
    base: dict[str, Any] = {
        "login": "Anonymous",
        "joined_on": "2024-01-01",
        "status": "active",
        "unavailable_until": "",
    }
    base.update(overrides)
    return base


def objection(**overrides: Any) -> dict[str, Any]:
    """A minimal valid PublicationObjection (schema v3); shared by
    Publication and Nomination."""
    base: dict[str, Any] = {
        "member": "Anonymous",
        "reason": "",
        "date": "",
    }
    base.update(overrides)
    return base


def nomination(**overrides: Any) -> dict[str, Any]:
    """A minimal valid nomination (schema v3); override any field per test."""
    base: dict[str, Any] = {
        "candidate": "grace",
        "sponsor": "Anonymous",
        "opened_on": "2026-01-01",
        "objections": [],
        "outcome": "",
    }
    base.update(overrides)
    return base


def speaker(**overrides: Any) -> dict[str, Any]:
    """A minimal valid speaker (schema v3); override any field per test."""
    base: dict[str, Any] = {
        "id": "spk-001",
        "name": "Ada Lovelace",
        "gender": "undisclosed",
        "email": "ada@example.org",
        "affiliation": "Example University",
        "country": "UK",
        "title": "On analytical engines",
        "abstract": "",
        "conflicts_of_interest": "",
        "source": "organizer",
        "proposed_by": "someone",
        "links": [],
        "host_1": "",
        "host_2": "",
        "status": "lead",
        "career_stage": "undisclosed",
        "publication": {
            "consent": "",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "",
        },
        "selection": {"ballots": [], "opened_on": "", "decided_on": ""},
        "edition_code": "",
        "date": "",
        "time": "",
        "zoom_link": "",
        "youtube_url": "",
        "forum_thread": "",
        "runbook_progress": {},
        "metrics": {
            "registrations": None,
            "live_peak": None,
            "youtube_views_30d": None,
            "forum_replies": None,
        },
        "notes": "",
    }
    base.update(overrides)
    return base


def config(**overrides: Any) -> dict[str, Any]:
    """A minimal valid config (schema v3); override any field per test."""
    base: dict[str, Any] = {
        "season": 2026,
        "vw_counter": 5,
        "overlap_window_days": 7,
        "seminar_duration_minutes": 90,
        "board": [
            board_member(login="Anonymous"),
            board_member(login="grace"),
            board_member(login="ada"),
        ],
        "nominations": [],
        "board_min": 3,
        "board_max": 9,
        "vote_window_days": 10,
        "objection_window_working_days": 5,
        "inactivity_months": 6,
        "balance_window_months": 12,
        "sla_days": {
            "lead_decision": 14,
            "invitation_follow_up": 7,
            "summary_after_delivery": 5,
            "recording_after_delivery": 10,
        },
    }
    base.update(overrides)
    return base
