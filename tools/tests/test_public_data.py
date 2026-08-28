from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import speaker

import convener_ops.public_data as public_data
from convener_ops.public_data import (
    NEVER_PUBLISHED,
    PUBLIC_FIELD_SOURCES,
    PUBLIC_FIELDS,
    PUBLISHABLE_ALWAYS,
    PUBLISHABLE_ON_CONSENT,
    to_public,
    to_survey_status,
)


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


def test_a_non_mapping_entry_is_skipped_not_crashed() -> None:
    # speakers.yml is read unvalidated (convener_ops.cli._load) before to_public
    # ever sees it -- a stray non-mapping list item must not crash the
    # public feed; it is dropped, and everything else still comes through.
    rows = to_public([None, _scheduled()])  # type: ignore[list-item]
    assert len(rows) == 1
    assert rows[0]["id"] == "MRG-05"


def test_no_field_outside_the_allowlist_is_emitted() -> None:
    # A sweep of real output, but against `PUBLIC_FIELDS` -- a set *derived*
    # from `PUBLIC_FIELD_SOURCES` and the three classification sets below.
    # It catches a column mapped straight past the classification (the
    # loop-bypass class of bug); it cannot catch a column that is mapped
    # *and* whose source field is misclassified as publishable in the same
    # mistake, because that mistake moves this set too. See
    # `test_the_feed_never_emits_a_column_outside_the_fixed_set` for the
    # sweep that mutation cannot fool.
    out = to_public([_scheduled()])
    assert set(out[0]) <= PUBLIC_FIELDS


#: The exact columns `to_public` may ever emit, spelled out here
#: independently of `PUBLIC_FIELD_SOURCES` and the classification sets --
#: nothing in `public_data.py` can move this set, because it is never read
#: from the module under test. Growing it is a deliberate act: whoever adds
#: a column has to come here and say so.
_EXPECTED_PUBLIC_COLUMNS = frozenset(
    {
        "id",
        "title",
        "date",
        "status",
        "abstract",
        "photo_url",
        "bio",
        "linkedin",
        "seed_questions",
        "youtube_url",
        "forum_thread",
        "speaker_name",
        "speaker_affiliation",
        "speaker_country",
    }
)


def test_the_feed_never_emits_a_column_outside_the_fixed_set() -> None:
    """The sweep `test_no_field_outside_the_allowlist_is_emitted` cannot be:
    that test compares the real output to `PUBLIC_FIELDS`, which is itself
    *derived* from `PUBLIC_FIELD_SOURCES` and the three classification
    sets -- a mistake that adds a column mapped to a newly-added internal
    field, and in the same breath misclassifies that field as publishable,
    moves the derived allowlist and the output together, so a test built
    from that derivation would still pass. This compares the real output
    to a literal set instead, and it does not merely need the added column
    to be wrong -- a genuinely new, correctly classified column also fails
    it, on purpose, until this set is edited to say so.

    Exercised on `_person()` (an archived talk, every consent-gated field
    filled in and the gate open) so every column this function can ever
    populate is actually present -- a scheduled talk alone would pass this
    assertion by never populating half the set, proving nothing about the
    other half.
    """
    out = to_public([_person()])
    assert set(out[0]) == _EXPECTED_PUBLIC_COLUMNS


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


def test_the_room_link_never_reaches_the_public_feed_under_any_name() -> None:
    # This column used to exist, called `registration_link`, and published
    # `zoom_link` under it -- a name that, once the event page carried its
    # own registration form, read as exactly the wrong thing (somebody
    # nearly rendered it believing it was the address to register
    # at). Nothing reads it any more: registration happens on the event
    # page's own address, and the room link now reaches a participant only
    # through the confirmation e-mail. Swept on the output, not on
    # `PUBLIC_FIELD_SOURCES`, so a future attempt to republish the same
    # value under a *different* column name still fails this test.
    out = to_public([_scheduled()])
    assert "registration_link" not in out[0]
    assert "zoom_link" not in out[0]
    serialised = repr(out)
    assert "https://example.org/room" not in serialised


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
    # The property, stated over whatever `instance/data/speakers.yml` happens to
    # hold: no row carries a link unless that row's gate opened.
    from convener_ops.paths import repo_root
    from convener_ops.yaml_safe import safe_load

    path = repo_root() / "instance" / "data" / "speakers.yml"
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


# --- The classification, and the gate it feeds -------------------------------

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "governance-cases.json").read_text(
        encoding="utf-8"
    )
)
CLASSIFICATION = CASES["speaker_field_classification"]


def _person(
    publication: dict[str, Any] | None = None, **overrides: Any
) -> dict[str, Any]:
    """An archived record whose gate opened, with the personal fields filled in.

    `_published` sends its keyword arguments into the *publication block*, so
    the block goes in as one argument here and everything else is applied to
    the speaker afterwards. Mixing the two would have written `photo_url` into
    the publication block, where nothing reads it, and the tests below would
    have passed by asserting that a field nobody set came out empty.
    """
    entry = _published(**(publication or {}))
    entry.update(
        {
            "photo_url": "https://example.org/ada.jpg",
            "bio": "Ada works on analytical engines.",
            "linkedin": "ada-lovelace",
            "seed_questions": "What would you ask an engine?",
        }
    )
    entry.update(overrides)
    return entry


def test_the_classification_matches_the_shared_fixture() -> None:
    # The same three sets are written in `app/src/state/consent.ts`, and
    # `app/tests/consent-fields.test.ts` asserts them against this same file.
    # A field moved on one side only fails in the language left behind.
    assert frozenset(CLASSIFICATION["publishable_always"]) == PUBLISHABLE_ALWAYS
    assert frozenset(CLASSIFICATION["publishable_on_consent"]) == PUBLISHABLE_ON_CONSENT
    assert frozenset(CLASSIFICATION["never_published"]) == NEVER_PUBLISHED


def test_the_three_sets_are_disjoint() -> None:
    # Exhaustiveness over `keyof Speaker` is checked on the TypeScript side,
    # where the model lives; what Python can check without inventing a second
    # copy of that model is that no field is claimed twice -- which is what
    # would let one placement quietly win over another.
    assert not PUBLISHABLE_ALWAYS & PUBLISHABLE_ON_CONSENT
    assert not PUBLISHABLE_ALWAYS & NEVER_PUBLISHED
    assert not PUBLISHABLE_ON_CONSENT & NEVER_PUBLISHED


def test_every_published_column_names_a_publishable_field() -> None:
    for column, source in PUBLIC_FIELD_SOURCES.items():
        assert source not in NEVER_PUBLISHED, column
        assert source in PUBLISHABLE_ALWAYS or source in PUBLISHABLE_ON_CONSENT, column


def test_a_column_drawn_from_an_internal_field_is_dropped_from_the_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The derivation is the guarantee: somebody adding a column sourced from
    # `notes` does not get a reported error, they get nothing published. This
    # rebuilds PUBLIC_FIELDS exactly as the module does, from a mapping that
    # has such a line in it.
    sources = dict(PUBLIC_FIELD_SOURCES, leak="notes")
    derived = frozenset(
        name
        for name, source in sources.items()
        if source in PUBLISHABLE_ALWAYS or source in PUBLISHABLE_ON_CONSENT
    )
    assert "leak" not in derived
    monkeypatch.setattr(public_data, "PUBLIC_FIELDS", derived)
    out = public_data.to_public([_scheduled(notes="internal note")])
    assert "leak" not in out[0]


def test_the_personal_fields_wait_for_a_recorded_consent() -> None:
    # A scheduled seminar, every personal field filled in, no consent
    # recorded: the programme goes out and the person does not.
    filled = _scheduled(
        photo_url="https://example.org/ada.jpg",
        bio="Ada works on analytical engines.",
        linkedin="ada-lovelace",
        seed_questions="What would you ask an engine?",
    )
    out = to_public([filled])[0]
    assert out["photo_url"] == ""
    assert out["bio"] == ""
    assert out["linkedin"] == ""
    assert out["seed_questions"] == ""
    assert out["speaker_name"] == "Ada Lovelace"
    assert out["title"] == "On analytical engines"


def test_the_personal_fields_go_out_once_the_gate_has_opened() -> None:
    out = to_public([_person()])[0]
    assert out["photo_url"] == "https://example.org/ada.jpg"
    assert out["bio"] == "Ada works on analytical engines."
    assert out["linkedin"] == "ada-lovelace"
    assert out["seed_questions"] == "What would you ask an engine?"


def test_a_withdrawn_consent_pulls_the_person_as_well_as_the_recording() -> None:
    # G-15 is not only about the video. A speaker who withdraws has their
    # portrait, biography and questions taken out of the feed too; what stays
    # is the programme of a talk that happened.
    out = to_public([_person({"consent": "refused", "outcome": "withheld"})])[0]
    assert out["photo_url"] == ""
    assert out["bio"] == ""
    assert out["seed_questions"] == ""
    assert out["youtube_url"] == ""
    assert out["title"] == "On analytical engines"
    assert out["speaker_name"] == "Ada Lovelace"


def test_silence_never_discloses_the_person() -> None:
    # The same asymmetry the recording is gated on, asserted on the fields
    # added for the volunteers' checklist: an unanswered, blank or
    # unrecognised consent is not a permission, and neither is a record whose
    # consent says yes but whose gate was never run.
    for consent in ("pending", "", "unknown"):
        out = to_public([_person({"consent": consent})])[0]
        assert out["photo_url"] == "", consent
        assert out["bio"] == "", consent
    for outcome in ("", "withheld", "pending"):
        out = to_public([_person({"outcome": outcome})])[0]
        assert out["photo_url"] == "", outcome
        assert out["bio"] == "", outcome
    unreadable = _person()
    unreadable["publication"] = "nonsense"
    assert to_public([unreadable])[0]["bio"] == ""


def test_a_standing_objection_pulls_the_person_too() -> None:
    # An objection with no `resolved_on` still stands, and a hand-edited file
    # that omits the key reads as standing too -- so the person comes out of
    # the feed for exactly as long as the recording does.
    out = to_public(
        [
            _person(
                {
                    "objections": [
                        {"member": "carol", "reason": "wait", "date": "2026-01-10"}
                    ]
                }
            )
        ]
    )[0]
    assert out["bio"] == ""
    assert out["youtube_url"] == ""


def test_the_hosts_are_never_published_on_any_consent() -> None:
    # `host_1` and `host_2` name volunteers. The consent this gate reads is
    # the speaker's, and it cannot answer for somebody else -- so no value of
    # the publication block puts a host in the feed.
    assert "host_1" in NEVER_PUBLISHED
    assert "host_2" in NEVER_PUBLISHED
    serialised = repr(to_public([_person(host_1="H1", host_2="H2")]))
    assert "H1" not in serialised
    assert "H2" not in serialised


def test_the_availability_and_the_deliberation_stay_in_the_repository() -> None:
    # `candidate_dates` records which slots a speaker turned down: their
    # availability, not the programme. `publication` is the record of a
    # permission and is never published by the gate that reads it.
    out = to_public(
        [
            _person(
                candidate_dates=[
                    {"date": "2026-02-05", "time": "16:00", "answer": "no"}
                ],
                notes="internal note",
                conflicts_of_interest="advises the funder",
            )
        ]
    )
    serialised = repr(out)
    for forbidden in (
        "2026-02-05",
        "candidate_dates",
        "publication",
        "internal note",
        "advises the funder",
    ):
        assert forbidden not in serialised


# ------------------------------------------------------------------ #
# to_survey_status(): the enabled set as an
# operational fact, published outside the consent gate entirely.
# ------------------------------------------------------------------ #


def test_to_survey_status_includes_only_enabled_events() -> None:
    speakers = [
        speaker(id="spk-001", edition_code="MRG-01", survey_enabled=False),
        speaker(id="spk-002", edition_code="MRG-02", survey_enabled=True),
    ]
    assert to_survey_status(speakers) == ["mrg-02"]


def test_to_survey_status_lower_cases_the_edition_code() -> None:
    assert to_survey_status([speaker(edition_code="MRG-42", survey_enabled=True)]) == [
        "mrg-42"
    ]


def test_to_survey_status_skips_a_record_with_no_edition_code() -> None:
    """A record with the switch on but nothing to key on can never be
    reached by SurveyForm.tsx or the relay either, which both look up by
    edition code -- publishing it would be a dead entry, not a bug in
    itself, but it is worth excluding rather than shipping."""
    assert to_survey_status([speaker(edition_code="", survey_enabled=True)]) == []


def test_to_survey_status_ignores_publication_status_and_consent() -> None:
    """Deliberately not a projection of PUBLISHABLE_ALWAYS/ON_CONSENT: a
    lead with no scheduled date and no publication consent at all still
    has its switch honoured -- the survey status feed answers a different
    question than the programme feed does."""
    assert to_survey_status(
        [speaker(edition_code="MRG-09", status="lead", survey_enabled=True)]
    ) == ["mrg-09"]


def test_to_survey_status_is_sorted_and_deduplicated() -> None:
    speakers = [
        speaker(id="spk-001", edition_code="MRG-09", survey_enabled=True),
        speaker(id="spk-002", edition_code="MRG-02", survey_enabled=True),
    ]
    assert to_survey_status(speakers) == ["mrg-02", "mrg-09"]


def test_to_survey_status_carries_nothing_but_the_id() -> None:
    """The structural guarantee the module docstring claims: no name, no
    email, no title -- checked directly on the output, not merely on the
    function's declared return type."""
    out = to_survey_status(
        [
            speaker(
                id="spk-001",
                name="Ada Lovelace",
                email="ada@example.org",
                edition_code="MRG-03",
                survey_enabled=True,
            )
        ]
    )
    assert out == ["mrg-03"]
    serialised = repr(out)
    assert "Ada" not in serialised
    assert "ada@example.org" not in serialised


def test_to_survey_status_ignores_a_non_mapping_entry() -> None:
    assert to_survey_status(["not a mapping"]) == []
