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


def test_the_diversity_attributes_never_reach_the_feed() -> None:
    # gender and career_stage are collected for one purpose: an aggregate the
    # board reads, over a window, inside the app (app/src/state/diversity.ts).
    # Published per row they stop being a measure and become an attribute
    # attached to a named researcher on the open web. Neither is on the
    # allowlist, and this pins that they stay off it.
    assert "gender" not in PUBLIC_FIELDS
    assert "career_stage" not in PUBLIC_FIELDS
    out = to_public([_scheduled(gender="F", career_stage="postdoc")])
    assert "gender" not in out[0]
    assert "career_stage" not in out[0]
    serialised = repr(out)
    for forbidden in ("postdoc", "'F'"):
        assert forbidden not in serialised


def test_recording_is_only_exposed_once_the_gate_has_published_it() -> None:
    assert to_public([_scheduled()])[0]["youtube_url"] == ""
    # Delivered, with a URL typed into the wrap-up checklist, but the
    # publication gate never run: nothing goes out.
    assert to_public([_scheduled(status="delivered")])[0]["youtube_url"] == ""
    assert to_public([_published()])[0]["youtube_url"] == "https://youtu.be/abc"


def test_registration_link_is_only_exposed_while_scheduled() -> None:
    assert to_public([_scheduled()])[0]["registration_link"] != ""
    assert to_public([_scheduled(status="delivered")])[0]["registration_link"] == ""


def test_archived_events_expose_the_recording() -> None:
    assert to_public([_published()])[0]["youtube_url"] != ""


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


def _published(**publication: Any) -> dict[str, Any]:
    """An archived seminar whose recording the gate actually published, with
    the publication block under test.

    `outcome: published` is written by one transition only,
    `finalize-archive`, and only when `canArchive` opens -- so this is the
    shape the app produces, not a shape invented for the test.
    """
    block: dict[str, Any] = {
        "consent": "granted",
        "approved_by": "alice",
        "approved_on": "2026-01-09",
        "objections": [],
        "outcome": "published",
    }
    block.update(publication)
    return _scheduled(status="archived", publication=block)


def test_a_refused_consent_pulls_the_recording_from_the_feed() -> None:
    # G-15: a speaker may withdraw permission at any time, and the recording
    # has to come out of the public feed when they do. The talk itself stays
    # listed - it happened - but the link to the recording does not.
    out = to_public([_published(consent="refused", outcome="withheld")])
    assert out[0]["youtube_url"] == ""
    assert out[0]["title"] == "On analytical engines"


def test_a_withheld_recording_is_not_linked() -> None:
    out = to_public([_published(outcome="withheld")])
    assert out[0]["youtube_url"] == ""


def test_a_standing_objection_pulls_the_recording() -> None:
    out = to_public(
        [
            _published(
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
            _published(
                objections=[{"member": "carol", "reason": "wait", "date": "2026-01-10"}]
            )
        ]
    )
    assert out[0]["youtube_url"] == ""


def test_a_resolved_objection_does_not_pull_the_recording() -> None:
    out = to_public(
        [
            _published(
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
    # On an `archived` record, because `archived` is the only status at which
    # a recording is linked at all (`RECORDING_STATUSES`). Asserted on a
    # `delivered` one, this passes whatever the gate decides -- that record
    # has no URL to withhold for a second, unrelated reason -- and the arm
    # under test would be untested while reading as covered.
    out = to_public([_scheduled(status="archived", publication="nonsense")])
    assert out[0]["youtube_url"] == ""
    # The talk itself still appears: an unreadable block says nothing about
    # the programme, only about the recording.
    assert out[0]["title"] == "On analytical engines"


def test_a_malformed_objections_value_does_not_pull_a_clean_recording() -> None:
    # `validate.py` reports the shape; this function only decides whether the
    # link goes out, and an unreadable objections list says nothing about
    # anyone having objected.
    out = to_public([_published(objections="nonsense")])
    assert out[0]["youtube_url"] == "https://youtu.be/abc"


def test_a_pending_consent_never_reaches_the_feed() -> None:
    # The asymmetry the whole gate is built on: the board's silence clears
    # the objection window, the speaker's silence clears nothing. A
    # `pending` consent is silence, and silence is not a permission --
    # least of all on the one path that leaves the repository.
    for consent in ("pending", "", "unknown"):
        out = to_public([_published(consent=consent, outcome="published")])
        assert out[0]["youtube_url"] == "", consent


def test_an_ungated_record_never_reaches_the_feed() -> None:
    # Everything else in the block says yes; `outcome` says the gate was
    # never run. That is the state a hand edit, or a forced status, leaves
    # behind, and it publishes nothing.
    for outcome in ("", "withheld", "pending"):
        out = to_public([_published(outcome=outcome)])
        assert out[0]["youtube_url"] == "", outcome


def test_the_programme_is_published_whatever_the_consent_says() -> None:
    # Only the recording is conditional. A speaker who agreed to give a
    # public webinar is in its programme; withholding their name would be a
    # different (and wrong) rule.
    out = to_public([_published(consent="refused", outcome="withheld")])[0]
    assert out["youtube_url"] == ""
    assert out["speaker_name"] == "Ada Lovelace"
    assert out["speaker_affiliation"] == "Example University"
    assert out["speaker_country"] == "UK"
    assert out["title"] == "On analytical engines"
    assert out["date"] == "2026-01-08"
    assert out["status"] == "archived"


def test_no_recording_in_the_real_feed_lacks_recorded_consent() -> None:
    # The property, stated over whatever `data/speakers.yml` happens to
    # hold: no row carries a link unless that row's gate opened.
    from convener_ops.paths import repo_root
    from convener_ops.yaml_safe import safe_load

    path = repo_root() / "data" / "speakers.yml"
    speakers = safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(speakers, list)
    by_code = {s.get("edition_code", ""): s for s in speakers}
    for row in to_public(speakers):
        if row["youtube_url"]:
            entry = by_code[row["id"]]
            assert entry["publication"]["outcome"] == "published"
            assert entry["publication"]["consent"] == "granted"


def test_the_wrap_up_checklist_is_not_a_second_door_into_the_feed() -> None:
    # `phases.ts` offers a free `youtube_url` field on the delivered
    # checklist. Filling it in records where the recording is; it does not
    # publish it. Both locks are asserted: the status is not one at which a
    # recording is linked, and the gate never ran.
    from convener_ops.public_data import RECORDING_STATUSES

    assert "delivered" not in RECORDING_STATUSES
    out = to_public([_published(), _published()])
    filled_in = _published()
    filled_in["status"] = "delivered"
    assert to_public([filled_in])[0]["youtube_url"] == ""
    assert out[0]["youtube_url"] != ""


def test_a_forced_status_is_not_a_path_to_publication() -> None:
    # `AdminOverride`'s force-status control writes `status` and nothing
    # else, so a record forced to `archived` keeps the untouched
    # publication block it had -- and that block is what this reads.
    forced = _scheduled(status="archived")
    assert forced["publication"]["outcome"] == ""
    assert to_public([forced])[0]["youtube_url"] == ""
