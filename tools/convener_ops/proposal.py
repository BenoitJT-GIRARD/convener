"""Turn a Tally form submission into a candidate lead.

Both functions are pure: no filesystem access, no environment reads. The
caller (``convener_ops.cli``) supplies the payload, the existing speakers, and the
webhook secret.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Sequence
from typing import Any

from convener_ops.governance import active_board

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


def skip_reason(fields: dict[str, str], existing: list[dict[str, Any]]) -> str | None:
    """Why ``to_lead`` would return None for this submission, or None if it wouldn't.

    Distinguishes an empty name from a duplicate submission so the caller can
    log which one happened.
    """
    name = _get(fields, "Name")
    if not name:
        return "empty name"

    email = _get(fields, "Email")
    if email and any(
        isinstance(s, dict) and s.get("email") == email and s.get("status") == "lead"
        for s in existing
    ):
        return "duplicate email"

    return None


def _id_order(speaker_id: str) -> int:
    """The numeric suffix of a speaker id (``spk-007`` -> 7), used only as a
    creation-order proxy for ``assign_lead``'s tie-break. ``-1`` for
    anything unparsable, so it sorts as "oldest"."""
    match = re.match(r"spk-(\d+)", speaker_id or "")
    return int(match.group(1)) if match else -1


def assign_lead(
    speakers: Sequence[dict[str, Any]], config: dict[str, Any], on: str
) -> str:
    """The active, available board member to whom a new lead falls (G-17):
    whoever carries the fewest open leads (status ``lead``, ``assigned_to``
    that member -- *not* ``proposed_by``, which stays the submitter's
    self-reported name and is never counted here).

    A tie goes to whoever's most recent open lead is the oldest, using the
    id's numeric suffix as a stand-in for creation order (ids are assigned
    in strictly increasing order -- see ``to_lead``). Any further tie falls
    back to alphabetical login order, so the result never depends on
    ``config["board"]``'s incidental ordering and repeated calls with the
    same input always agree.

    Mirrors ``app/src/state/board.ts::assignLead``, pinned together by
    ``tools/tests/fixtures/governance-cases.json``'s ``assign_lead_cases``.

    Never raises: an empty string means the caller should show that the
    assignment is pending, not surface a raw error to a volunteer.
    """
    logins, unavailable = active_board(config, on)
    away = set(unavailable)
    eligible = sorted(login for login in logins if login not in away)
    if not eligible:
        return ""

    open_lead_ids: dict[str, list[int]] = {login: [] for login in eligible}
    for s in speakers:
        if not isinstance(s, dict) or s.get("status") != "lead":
            continue
        assignee = s.get("assigned_to")
        ids = open_lead_ids.get(assignee) if isinstance(assignee, str) else None
        if ids is not None:
            ids.append(_id_order(s.get("id", "")))

    def _key(login: str) -> tuple[int, int]:
        ids = open_lead_ids[login]
        return (len(ids), max(ids) if ids else -1)

    return min(eligible, key=_key)


def to_lead(
    fields: dict[str, str],
    existing: list[dict[str, Any]],
    config: dict[str, Any],
    today: str,
) -> dict[str, Any] | None:
    """Build a v3-schema lead from form fields, or None if it should be skipped.

    Skipped when the name is empty, or when the email matches an existing
    record that is still in ``lead`` status (a duplicate submission). See
    ``skip_reason`` to tell the two cases apart.

    ``proposed_by`` keeps the submitter's self-reported name exactly as typed
    into the form -- it is the only record of who to tell if the Board
    declines the lead. ``assigned_to`` is a separate field: the board member
    who will look after the lead, chosen by ``assign_lead`` (G-17).
    """
    if skip_reason(fields, existing) is not None:
        return None

    name = _get(fields, "Name")
    email = _get(fields, "Email")

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
        "career_stage": "undisclosed",
        "email": email,
        "affiliation": _get(fields, "Institution", "Affiliation"),
        "country": _get(fields, "Country"),
        "title": _get(fields, "Preliminary title", "(preliminary) Title", "Title"),
        "abstract": _get(fields, "Short abstract", "Summary", "Abstract"),
        "conflicts_of_interest": _get(fields, "Conflicts of interest"),
        "source": "form",
        "proposed_by": _get(fields, "Your name", "Who are you", "How you propose"),
        "assigned_to": assign_lead(existing, config, today),
        "links": links,
        "host_1": "",
        "host_2": "",
        "status": "lead",
        # opened_on is the intake date, and it is what subjects the lead to
        # vote expiry: sweep.expire_votes skips - silently, so an overnight
        # job never dies on bad data - any lead whose opened_on does not
        # parse. A lead created without one would wait forever.
        "selection": {"ballots": [], "opened_on": today, "decided_on": ""},
        # The form asks for neither, and a lead the board has not yet heard
        # has nothing to consent to: both start where the v3 migration
        # leaves a speaker who never reached a publishable status.
        "publication": {
            "consent": "",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "",
        },
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
