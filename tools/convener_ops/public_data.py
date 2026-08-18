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


def to_public(speakers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in speakers:
        if not isinstance(entry, dict):
            continue
        status = entry.get("status", "")
        if status not in PUBLIC_STATUSES:
            continue
        out.append(
            {
                "id": entry.get("edition_code", ""),
                "title": entry.get("title", ""),
                "date": entry.get("date", ""),
                "status": status,
                "abstract": entry.get("abstract", ""),
                "youtube_url": (
                    entry.get("youtube_url", "") if status in RECORDING_STATUSES else ""
                ),
                "registration_link": (
                    entry.get("zoom_link", "") if status == "scheduled" else ""
                ),
                "forum_thread": entry.get("forum_thread", ""),
                "speaker_name": entry.get("name", ""),
                "speaker_affiliation": entry.get("affiliation", ""),
                "speaker_country": entry.get("country", ""),
            }
        )
    out.sort(key=lambda row: row.get("date", ""), reverse=True)
    return out
