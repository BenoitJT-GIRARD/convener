"""Reduce the speaker list to what may be published.

This is an allowlist, deliberately. With a denylist, adding an internal field
would publish it by accident — which is exactly the failure this guards
against.
"""

from __future__ import annotations

from typing import Any

PUBLIC_STATUSES = frozenset({"scheduled", "delivered", "archived"})
RECORDING_STATUSES = frozenset({"delivered", "archived"})

PUBLIC_FIELDS = frozenset(
    {
        "id",
        "title",
        "date",
        "status",
        "abstract",
        "youtube_url",
        "registration_link",
        "forum_thread",
        "speaker_name",
        "speaker_affiliation",
        "speaker_country",
    }
)


def recording_withheld(entry: dict[str, Any]) -> bool:
    """Whether this speaker's recording must not appear in the public feed.

    The takedown half of the second gate (G-10, G-15). The app decides
    whether a recording may be published in the first place
    (`app/src/state/governance.ts::canArchive`); this decides whether one
    already in the feed has to come out of it, which is the half an
    unattended job can reach. The two are different questions, so there is
    one implementation of each and nothing to pin in
    `tools/tests/fixtures/governance-cases.json`.

    A recording appears only when two things are recorded, and each is asked
    for in the affirmative:

    - the speaker's consent is `granted` (G-15). Not "did they refuse" but
      "did they agree": `pending`, `''` and any value nobody recognises are
      silence, and silence is never a permission. This is the only path on
      which anything leaves the repository, so it is the last place an
      absent answer may be read as a yes;
    - the publication gate opened: `publication.outcome == "published"`,
      written by the single transition `finalize-archive`, which refuses
      unless the board approved and its objection window has run
      (`app/src/state/governance.ts::canArchive`). `withheld`, `''` and an
      untouched record are all "the gate was never run".

    Either half turning back to silence is also a takedown, and so is one
    more thing: a standing objection, i.e. an entry in `objections` with no
    `resolved_on`. A missing key reads as standing, never as settled, so a
    hand-edited file errs towards leaving the talk offline.

    Only the recording is conditional. The programme fields -- name,
    affiliation, country, title, abstract, date -- are published for every
    speaker at a public status: agreeing to give a public webinar is
    agreeing to appear in its programme. The recording is the separate
    artefact the consent model exists for, and it is the only field this
    function governs.

    The migrated backlog (31 speakers) carries `consent: pending` or `''` and
    no `youtube_url` at all, so requiring the gate's own verdict takes
    nothing out of the feed that is in it.
    """
    publication = entry.get("publication")
    if not isinstance(publication, dict):
        # An unreadable publication block is not a permission. `validate.py`
        # reports it; here it simply keeps the recording out.
        return True
    if publication.get("consent") != "granted":
        # Not "did they refuse" but "did they agree": `pending`, `''` and a
        # hand-written value nobody recognises are all silence.
        return True
    if publication.get("outcome") != "published":
        # Not "is it withheld" but "did the gate open": `withheld` and an
        # untouched record both land here.
        return True
    objections = publication.get("objections")
    if isinstance(objections, list):
        return any(isinstance(o, dict) and not o.get("resolved_on") for o in objections)
    return False


def to_public(speakers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in speakers:
        if not isinstance(entry, dict):
            continue
        status = entry.get("status", "")
        if status not in PUBLIC_STATUSES:
            continue
        row = {
            "id": entry.get("edition_code", ""),
            "title": entry.get("title", ""),
            "date": entry.get("date", ""),
            "status": status,
            "abstract": entry.get("abstract", ""),
            "youtube_url": (
                entry.get("youtube_url", "")
                if status in RECORDING_STATUSES and not recording_withheld(entry)
                else ""
            ),
            "registration_link": (
                entry.get("zoom_link", "") if status == "scheduled" else ""
            ),
            "forum_thread": entry.get("forum_thread", ""),
            "speaker_name": entry.get("name", ""),
            "speaker_affiliation": entry.get("affiliation", ""),
            "speaker_country": entry.get("country", ""),
        }
        # Project through the allowlist rather than trusting `row` above was
        # built correctly: adding a key to `row` without adding it to
        # PUBLIC_FIELDS silently drops it here instead of publishing it.
        out.append({field: row[field] for field in row if field in PUBLIC_FIELDS})
    out.sort(key=lambda row: row.get("date", ""), reverse=True)
    return out
