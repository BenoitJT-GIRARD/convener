from __future__ import annotations

from typing import Any

from conftest import speaker

from convener_ops.public_data import PUBLIC_FIELDS, to_public


def _scheduled(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": "scheduled",
        "edition_code": "MRG-05",
        "date": "2026-01-08",
        "host_1": "H1",
        "host_2": "H2",
        "zoom_link": "https://example.org/room",
        "youtube_url": "https://youtu.be/abc",
        "email": "private@example.org",
        "notes": "internal note",
    }
    base.update(overrides)
    return speaker(**base)


NON_PUBLIC_STATUSES = (
    "lead",
    "approved",
    "invited",
    "confirmed",
    "parked",
    "decline-board",
    "decline-speaker",
)


def test_only_public_statuses_are_emitted() -> None:
    rows = [
        speaker(id=f"spk-{i:03d}", status=status)
        for i, status in enumerate(NON_PUBLIC_STATUSES, start=1)
    ]
    rows.append(_scheduled(id="spk-999"))
    assert [r["id"] for r in to_public(rows)] == ["MRG-05"]


def test_no_field_outside_the_allowlist_is_emitted() -> None:
    out = to_public([_scheduled()])
    assert set(out[0]) <= PUBLIC_FIELDS


def test_private_fields_never_leak() -> None:
    out = to_public([_scheduled(notes="secret", conflicts_of_interest="none")])
    serialised = repr(out)
    for forbidden in ("private@example.org", "internal note", "secret", "H1"):
        assert forbidden not in serialised


def test_recording_is_only_exposed_after_delivery() -> None:
    assert to_public([_scheduled()])[0]["youtube_url"] == ""
    delivered = to_public([_scheduled(status="delivered")])[0]
    assert delivered["youtube_url"] == "https://youtu.be/abc"


def test_registration_link_is_only_exposed_while_scheduled() -> None:
    assert to_public([_scheduled()])[0]["registration_link"] != ""
    assert to_public([_scheduled(status="delivered")])[0]["registration_link"] == ""


def test_archived_events_expose_the_recording() -> None:
    assert to_public([_scheduled(status="archived")])[0]["youtube_url"] != ""


def test_output_is_sorted_newest_first() -> None:
    rows = [
        _scheduled(id="spk-001", edition_code="MRG-01", date="2025-01-08"),
        _scheduled(id="spk-002", edition_code="MRG-02", date="2026-01-08"),
    ]
    assert [r["date"] for r in to_public(rows)] == ["2026-01-08", "2025-01-08"]
