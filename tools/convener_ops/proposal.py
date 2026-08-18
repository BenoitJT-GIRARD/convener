"""Turn a Tally form submission into a candidate lead.

Both functions are pure: no filesystem access, no environment reads. The
caller (``convener_ops.cli``) supplies the payload, the existing speakers, and the
webhook secret.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

GENDERS = {"M", "F", "NB", "undisclosed"}


def verify_signature(payload: str, signature: str, secret: str) -> bool:
    """Check the HMAC-SHA256 signature of a payload.

    With no secret configured, the check is skipped and the payload is
    accepted: the webhook secret is one of the integrations that may not
    exist yet.
    """
    if not secret:
        return True
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _get(fields: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = fields.get(key)
        if value:
            return str(value).strip()
    return ""


def to_lead(
    fields: dict[str, str], existing: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Build a v2-schema lead from form fields, or None if it should be skipped.

    Skipped when the name is empty, or when the email matches an existing
    record that is still in ``lead`` status (a duplicate submission).
    """
    name = _get(fields, "Name")
    if not name:
        return None

    email = _get(fields, "Email")
    if email and any(
        isinstance(s, dict) and s.get("email") == email and s.get("status") == "lead"
        for s in existing
    ):
        return None

    nums: list[int] = []
    for s in existing:
        if isinstance(s, dict):
            match = re.match(r"spk-(\d+)", s.get("id", ""))
            if match:
                nums.append(int(match.group(1)))
    sid = f"spk-{(max(nums or [0]) + 1):03d}"

    gender = _get(fields, "Gender") or "undisclosed"
    if gender not in GENDERS:
        gender = "undisclosed"

    raw_links = _get(fields, "Links", "Profile links")
    links = [s.strip() for s in raw_links.split(",") if s.strip()]

    return {
        "id": sid,
        "name": name,
        "gender": gender,
        "email": email,
        "affiliation": _get(fields, "Institution", "Affiliation"),
        "country": _get(fields, "Country"),
        "title": _get(fields, "Preliminary title", "(preliminary) Title", "Title"),
        "abstract": _get(fields, "Short abstract", "Summary", "Abstract"),
        "conflicts_of_interest": _get(fields, "Conflicts of interest"),
        "source": "form",
        "proposed_by": _get(fields, "Your name", "Who are you", "How you propose"),
        "links": links,
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
