"""Turn a Tally form submission into a candidate lead.

Both functions are pure: no filesystem access, no environment reads. The
caller (``convener_ops.cli``) supplies the payload, the existing speakers, and the
webhook secret.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from collections.abc import Sequence
from typing import Any

from convener_ops.governance import active_board

GENDERS = {"M", "F", "NB", "undisclosed"}

# Mirrors CAREER_STAGES in app/src/data/types.ts. "undisclosed" is a real
# answer, not a missing one: the form must be answerable without declaring a
# career stage, and the balance figures count the people who did not answer
# rather than dropping them (app/src/state/diversity.ts).
CAREER_STAGES = {
    "phd",
    "postdoc",
    "independent",
    "group-leader",
    "other",
    "undisclosed",
}

# The eleven labels ``to_lead`` reads a submission by -- canonical name first,
# any alias this module also accepts after it. ``scripts/create_tally_form.py``
# builds the live form's questions from these same tuples, not from a second,
# hand-typed copy of them, so a label renamed on one side breaks a test
# instead of breaking the form in production (R-3, D-03).
LABEL_NAME = ("Name",)
LABEL_EMAIL = ("Email",)
LABEL_INSTITUTION = ("Institution", "Affiliation")
LABEL_COUNTRY = ("Country",)
LABEL_TITLE = ("Preliminary title", "(preliminary) Title", "Title")
LABEL_ABSTRACT = ("Short abstract", "Summary", "Abstract")
LABEL_CAREER_STAGE = ("Career stage", "Career level")
LABEL_GENDER = ("Gender",)
LABEL_LINKS = ("Links", "Profile links")
LABEL_CONFLICTS = ("Conflicts of interest",)
# The submitter, not the speaker being proposed -- distinct from LABEL_NAME
# above. Kept as ``proposed_by`` on the resulting lead (G-17).
LABEL_PROPOSED_BY = ("Your name", "Who are you", "How you propose")

#: Every field ``to_lead`` reads, in the order the form asks them, each as
#: ``(aliases, required)`` with the canonical label first in ``aliases``.
#: ``Name`` is the only required one. ``scripts/create_tally_form.py`` walks
#: this exact tuple to build the form's questions.
FORM_FIELDS: tuple[tuple[tuple[str, ...], bool], ...] = (
    (LABEL_NAME, True),
    (LABEL_EMAIL, False),
    (LABEL_INSTITUTION, False),
    (LABEL_COUNTRY, False),
    (LABEL_TITLE, False),
    (LABEL_ABSTRACT, False),
    (LABEL_CAREER_STAGE, False),
    (LABEL_GENDER, False),
    (LABEL_LINKS, False),
    (LABEL_CONFLICTS, False),
    (LABEL_PROPOSED_BY, False),
)


def verify_signature(body: str, signature: str, secret: str) -> bool:
    """Check the HMAC-SHA256 signature of a raw webhook body.

    ``body`` must be exactly the bytes Tally signed -- the raw JSON it POSTed,
    untransformed -- and ``signature`` is base64, the encoding Tally sends in
    its ``Tally-Signature`` header (never hex: that was a defect this
    function used to have).

    With no secret configured, the check is skipped and the body is
    accepted: the webhook secret is one of the integrations that may not
    exist yet (D-13).

    ``signature`` reaches here from an HTTP header, relayed verbatim by a
    Cloudflare Worker -- it is attacker-controlled and may hold anything,
    including bytes that are not valid ASCII. ``hmac.compare_digest`` raises
    ``TypeError`` when given two ``str`` and either holds a non-ASCII
    character, which would otherwise let a crafted header crash this
    function instead of being refused. Comparing as ``bytes`` sidesteps that
    restriction entirely -- ``bytes`` carries no such ASCII requirement --
    so any string, ASCII or not, compares safely and still refuses to match.
    """
    if not secret:
        return True
    expected = base64.b64encode(
        hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    )
    try:
        given = signature.encode()
    except UnicodeEncodeError:
        # A lone surrogate (from a header carrying invalid UTF-8) cannot be
        # encoded at all -- refuse it exactly as any other non-match, rather
        # than letting the encode error escape as an unhandled crash.
        return False
    return hmac.compare_digest(expected, given)


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
    name = _get(fields, *LABEL_NAME)
    if not name:
        return "empty name"

    email = _get(fields, *LABEL_EMAIL)
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

    name = _get(fields, *LABEL_NAME)
    email = _get(fields, *LABEL_EMAIL)

    nums: list[int] = []
    for s in existing:
        if isinstance(s, dict):
            match = re.match(r"spk-(\d+)", s.get("id", ""))
            if match:
                nums.append(int(match.group(1)))
    sid = f"spk-{(max(nums or [0]) + 1):03d}"

    gender = _get(fields, *LABEL_GENDER) or "undisclosed"
    if gender not in GENDERS:
        gender = "undisclosed"

    # Declared by the submitter or not at all. An unrecognised answer -- a
    # free-text field, a renamed form option, a translation -- falls back to
    # "undisclosed" rather than being kept verbatim: a value outside the
    # vocabulary would open a career stage of its own in the balance figures
    # and read as a finding.
    career_stage = _get(fields, *LABEL_CAREER_STAGE) or "undisclosed"
    if career_stage not in CAREER_STAGES:
        career_stage = "undisclosed"

    raw_links = _get(fields, *LABEL_LINKS)
    links = [s.strip() for s in raw_links.split(",") if s.strip()]

    return {
        "id": sid,
        "name": name,
        "gender": gender,
        "career_stage": career_stage,
        "email": email,
        "affiliation": _get(fields, *LABEL_INSTITUTION),
        "country": _get(fields, *LABEL_COUNTRY),
        # Written as answers, not left out. The public form does not ask for
        # a portrait, a biography, a handle or seed questions -- those are
        # asked for once the Board has approved the lead and the speaker has
        # accepted -- and '' says "none on record" where a missing key would
        # say the record was never finished.
        "photo_url": "",
        "bio": "",
        "linkedin": "",
        "seed_questions": "",
        "title": _get(fields, *LABEL_TITLE),
        "abstract": _get(fields, *LABEL_ABSTRACT),
        "conflicts_of_interest": _get(fields, *LABEL_CONFLICTS),
        "source": "form",
        "proposed_by": _get(fields, *LABEL_PROPOSED_BY),
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
        # No slot has been put to anyone: the Board has not voted yet.
        "candidate_dates": [],
        "date": "",
        "time": "",
        "zoom_link": "",
        "youtube_url": "",
        "forum_thread": "",
        "runbook_progress": {},
        # Nobody is down for any line yet, and nobody has to be: an item with
        # no owner is the hosts', which is what every line has always meant.
        "checklist": {},
        "metrics": {
            "registrations": None,
            "live_peak": None,
            "youtube_views_30d": None,
            "forum_replies": None,
        },
        "notes": "",
    }
