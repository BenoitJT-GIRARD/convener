from __future__ import annotations

from typing import Any

import pytest
from conftest import speaker

import convener_ops.public_data as public_data
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


def test_public_fields_is_load_bearing_not_just_documentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # If a field is removed from the allowlist, it must actually disappear
    # from the emitted row -- proving `to_public` is built by projecting
    # through PUBLIC_FIELDS, not by a dict literal that merely resembles it.
    monkeypatch.setattr(
        public_data, "PUBLIC_FIELDS", frozenset(PUBLIC_FIELDS - {"abstract"})
    )
    out = public_data.to_public([_scheduled(abstract="a summary")])
    assert "abstract" not in out[0]


def test_output_is_sorted_newest_first() -> None:
    rows = [
        _scheduled(id="spk-001", edition_code="MRG-01", date="2025-01-08"),
        _scheduled(id="spk-002", edition_code="MRG-02", date="2026-01-08"),
    ]
    assert [r["date"] for r in to_public(rows)] == ["2026-01-08", "2025-01-08"]


def _delivered(**publication: Any) -> dict[str, Any]:
    """A delivered seminar whose recording is in the feed, with the
    publication block under test."""
    block: dict[str, Any] = {
        "consent": "granted",
        "approved_by": "alice",
        "approved_on": "2026-01-09",
        "objections": [],
        "outcome": "published",
    }
    block.update(publication)
    return _scheduled(status="delivered", publication=block)


def test_a_refused_consent_pulls_the_recording_from_the_feed() -> None:
    # G-15: a speaker may withdraw permission at any time, and the recording
    # has to come out of the public feed when they do. The talk itself stays
    # listed - it happened - but the link to the recording does not.
    out = to_public([_delivered(consent="refused", outcome="withheld")])
    assert out[0]["youtube_url"] == ""
    assert out[0]["title"] == "On analytical engines"


def test_a_withheld_recording_is_not_linked() -> None:
    out = to_public([_delivered(outcome="withheld")])
    assert out[0]["youtube_url"] == ""


def test_a_standing_objection_pulls_the_recording() -> None:
    out = to_public(
        [
            _delivered(
                objections=[
                    {
                        "member": "carol",
                        "reason": "unpublished data on a slide",
                        "date": "2026-01-10",
                        "resolved_on": "",
                    }
                ]
            )
        ]
    )
    assert out[0]["youtube_url"] == ""


def test_an_objection_missing_resolved_on_still_counts_as_standing() -> None:
    # A hand-edited file that omits the key must read as "still open". The
    # safe direction is the one that leaves the talk offline.
    out = to_public(
        [
            _delivered(
                objections=[{"member": "carol", "reason": "wait", "date": "2026-01-10"}]
            )
        ]
    )
    assert out[0]["youtube_url"] == ""


def test_a_resolved_objection_does_not_pull_the_recording() -> None:
    out = to_public(
        [
            _delivered(
                objections=[
                    {
                        "member": "carol",
                        "reason": "wait",
                        "date": "2026-01-10",
                        "resolved_on": "2026-01-12",
                    }
                ]
            )
        ]
    )
    assert out[0]["youtube_url"] == "https://youtu.be/abc"


def test_an_unreadable_publication_block_is_not_a_permission() -> None:
    out = to_public([_scheduled(status="delivered", publication="nonsense")])
    assert out[0]["youtube_url"] == ""


def test_a_malformed_objections_value_does_not_pull_a_clean_recording() -> None:
    # `validate.py` reports the shape; this function only decides whether the
    # link goes out, and an unreadable objections list says nothing about
    # anyone having objected.
    out = to_public([_delivered(objections="nonsense")])
    assert out[0]["youtube_url"] == "https://youtu.be/abc"
