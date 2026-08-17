from __future__ import annotations

from typing import Any


def speaker(**overrides: Any) -> dict[str, Any]:
    """A minimal valid speaker; override any field per test."""
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
        "selection": {"votes_for": [], "decided_on": ""},
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
    base: dict[str, Any] = {
        "season": 2026,
        "vw_counter": 5,
        "vote_threshold": 3,
        "overlap_window_days": 7,
        "seminar_duration_minutes": 90,
        "board_members": ["Anonymous"],
    }
    base.update(overrides)
    return base
