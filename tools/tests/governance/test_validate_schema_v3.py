"""Schema v3 validation: ballots, board membership, and the publication gate.

Eleven cases, each pinned on the exact substring its
error message must contain (the migration's own tests and CI both grep for
these strings), plus a twelfth (board_members obsolete) that carries the
same loud treatment for the same reason.
"""

from __future__ import annotations

import pytest
from conftest import (
    EDITIONS,
    ballot,
    board_member,
    config,
    nomination,
    objection,
    speaker,
)

from convener_ops.governance.validate import validate_config, validate_speakers


def test_ballot_with_unknown_value_is_rejected() -> None:
    s = speaker(
        selection={
            "ballots": [ballot(value="bogus")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins={"carol"}, editions=EDITIONS)
    assert any("invalid ballot value" in e for e in errors)


def test_recused_ballot_without_coi_reason_is_rejected() -> None:
    s = speaker(
        selection={
            "ballots": [ballot(value="recused", coi_reason="")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins={"carol"}, editions=EDITIONS)
    assert any("recusal requires coi_reason" in e for e in errors)


def test_two_ballots_from_the_same_voter_on_a_lead_is_rejected() -> None:
    s = speaker(
        selection={
            "ballots": [ballot(voter="a"), ballot(voter="a")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins={"a"}, editions=EDITIONS)
    assert any("duplicate ballot" in e for e in errors)


def test_ballot_from_a_login_absent_from_the_board_is_rejected() -> None:
    s = speaker(
        selection={
            "ballots": [ballot(voter="not-on-board")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins={"carol"}, editions=EDITIONS)
    assert any("ballot from a non-member" in e for e in errors)


def test_a_selection_with_no_ballots_list_is_not_a_ballot_error() -> None:
    # A hand-edited file can leave "ballots" out of a present "selection"
    # block, the same way tests/fixtures/hand-edited-speakers.yml leaves
    # "selection" out entirely. validate_speakers is lenient about the
    # block's shape the same way it is about the block's absence: it is not
    # this validator's job to invent a threshold-affecting default for a
    # field it cannot see.
    s = speaker(selection={"opened_on": "", "decided_on": ""})
    errors = validate_speakers([s], board_logins={"carol"}, editions=EDITIONS)
    assert not any("ballot" in e for e in errors)


def test_a_non_mapping_ballot_is_rejected() -> None:
    s = speaker(
        selection={
            "ballots": ["not-a-mapping"],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins={"carol"}, editions=EDITIONS)
    assert any("not a mapping" in e for e in errors)


def test_unknown_career_stage_is_rejected() -> None:
    errors = validate_speakers([speaker(career_stage="professor")], editions=EDITIONS)
    assert any("invalid career_stage" in e for e in errors)


def test_unknown_publication_consent_is_rejected() -> None:
    s = speaker(
        publication={
            "consent": "maybe",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "",
        }
    )
    errors = validate_speakers([s], editions=EDITIONS)
    assert any("invalid publication consent" in e for e in errors)


def test_board_containing_a_malformed_login_is_rejected() -> None:
    errors = validate_config(config(board=[board_member(login="not a login!")]))
    assert any("invalid board member" in e for e in errors)


def test_board_min_cannot_exceed_board_max() -> None:
    errors = validate_config(config(board_min=10, board_max=9))
    assert any("board_min cannot exceed board_max" in e for e in errors)


def test_vote_threshold_still_present_is_obsolete() -> None:
    errors = validate_config(config(vote_threshold=3))
    assert any("vote_threshold is obsolete" in e for e in errors)


def test_board_members_still_present_is_obsolete() -> None:
    # The same loud treatment for board_members as for vote_threshold: a
    # file that still carries the flat login list has not been migrated to
    # `board`.
    errors = validate_config(config(board_members=["carol"]))
    assert any("board_members is obsolete" in e for e in errors)


def test_incomplete_sla_days_is_rejected() -> None:
    cfg = config()
    del cfg["sla_days"]["recording_after_delivery"]
    errors = validate_config(cfg)
    assert any("missing sla_days keys" in e for e in errors)


def test_valid_config_and_speakers_produce_no_errors() -> None:
    board_logins = {m["login"] for m in config()["board"]}
    s = speaker(
        selection={
            "ballots": [ballot(voter=next(iter(board_logins)))],
            "opened_on": "",
            "decided_on": "",
        }
    )
    assert validate_speakers([s], board_logins=board_logins, editions=EDITIONS) == []
    assert validate_config(config()) == []


# --- Found on review ------------------------------------------------------


def test_vote_threshold_message_points_to_the_computed_threshold() -> None:
    # Finding 1: the old message ("migrate to sla_days") sent the reader to
    # the wrong place - vote_threshold is deleted, not moved. The corrected
    # message must say where the value now comes from, and must not still
    # claim sla_days is its destination.
    errors = validate_config(config(vote_threshold=3))
    joined = " | ".join(errors)
    assert "vote_threshold is obsolete" in joined
    assert "computed from the eligible board" in joined
    assert "migrate to sla_days" not in joined


def test_nomination_candidate_must_look_like_a_login() -> None:
    errors = validate_config(config(nominations=[nomination(candidate="not a login!")]))
    assert any("invalid nomination candidate" in e for e in errors)


def test_nomination_sponsor_must_look_like_a_login() -> None:
    errors = validate_config(config(nominations=[nomination(sponsor="not a login!")]))
    assert any("invalid nomination sponsor" in e for e in errors)


def test_nomination_opened_on_must_be_a_date() -> None:
    errors = validate_config(config(nominations=[nomination(opened_on="01/01/2026")]))
    nomination_errors = [e for e in errors if e.startswith("config.yml: nominations")]
    assert any("opened_on must be YYYY-MM-DD" in e for e in nomination_errors)


def test_nomination_outcome_must_be_valid() -> None:
    errors = validate_config(config(nominations=[nomination(outcome="bogus")]))
    assert any("invalid nomination outcome" in e for e in errors)


def test_nomination_objection_member_must_look_like_a_login() -> None:
    errors = validate_config(
        config(nominations=[nomination(objections=[objection(member="not a login!")])])
    )
    assert any("invalid objection member" in e for e in errors)


def test_nomination_support_member_must_look_like_a_login() -> None:
    errors = validate_config(
        config(
            nominations=[
                nomination(supports=[{"member": "not a login!", "date": "2026-01-02"}])
            ]
        )
    )
    assert any("invalid support member" in e for e in errors)


def test_nomination_support_needs_a_day() -> None:
    # The day is what makes a support count: one recorded after the window
    # closed is on the record and out of the count
    # (app/src/state/board.ts::nominationStanding). A support with no day
    # could not be placed on either side of that line.
    errors = validate_config(
        config(nominations=[nomination(supports=[{"member": "ada", "date": ""}])])
    )
    assert any("date must be YYYY-MM-DD" in e for e in errors)


def test_one_member_cannot_support_the_same_nomination_twice() -> None:
    # `board.ts::nominationStanding` counts distinct members, so a repeated
    # entry does not inflate the count in the browser; refusing the pair here
    # is what stops it reaching the browser at all.
    errors = validate_config(
        config(
            nominations=[
                nomination(
                    supports=[
                        {"member": "ada", "date": "2026-01-02"},
                        {"member": "ada", "date": "2026-01-03"},
                    ]
                )
            ]
        )
    )
    assert any("supports this nomination twice" in e for e in errors)


def test_a_nomination_with_no_supports_key_at_all_is_read_as_none() -> None:
    # The loader in the browser refuses a missing key outright
    # (app/src/data/validate.ts::readNomination). Here an absent list reads
    # as no supports, the same reading `_validate_objections` takes, so an
    # older file is reported for the state it is in rather than for the key
    # it lacks.
    entry = nomination()
    del entry["supports"]
    errors = validate_config(config(nominations=[entry]))
    assert not [e for e in errors if "supports" in e]


def test_supports_that_are_not_a_list_are_refused() -> None:
    errors = validate_config(config(nominations=[nomination(supports="ada")]))
    assert any("supports: must be a list" in e for e in errors)


def test_a_support_that_is_not_a_mapping_is_refused() -> None:
    errors = validate_config(config(nominations=[nomination(supports=["ada"])]))
    assert any("supports[0]: not a mapping" in e for e in errors)


def test_a_member_cannot_both_support_and_object_to_one_nomination() -> None:
    # The app cannot write the pair: objecting takes the objector's support
    # off in the same transformation. Typed in by hand it would show a member
    # backing a candidate they objected to in writing.
    errors = validate_config(
        config(
            nominations=[
                nomination(
                    supports=[{"member": "ada", "date": "2026-01-02"}],
                    objections=[objection(member="ada")],
                )
            ]
        )
    )
    assert any("both supports and objects" in e for e in errors)


def test_accepted_nomination_with_open_objections_is_rejected() -> None:
    # Cross-field backstop: outcome and objections can disagree, and no type
    # forbids it. This is the backstop for a hand-edited file, ahead of the
    # transformations (later tasks) that are meant to prevent it in the app.
    errors = validate_config(
        config(nominations=[nomination(outcome="accepted", objections=[objection()])])
    )
    assert any("accepted nomination has open objections" in e for e in errors)


def test_a_deferred_nomination_and_a_fresh_one_cannot_stand_together() -> None:
    # G-05's deferral rule. The app refuses the second nomination
    # (app/src/state/board.ts::nominationBlocker), so this pair can only be
    # typed in by hand - and left there it routes straight around the
    # objection the deferral records.
    errors = validate_config(
        config(
            nominations=[
                nomination(
                    candidate="hopper", outcome="deferred", objections=[objection()]
                ),
                nomination(candidate="hopper", outcome=""),
            ]
        )
    )
    assert any("already has an unsettled nomination" in e for e in errors)


def test_a_nomination_reopened_after_the_objection_was_withdrawn_is_accepted() -> None:
    # The withdrawal removes the objection and re-opens the very nomination
    # that was deferred, so only one unsettled entry is ever left behind. An
    # older deferral with nothing standing on it is history, not a live
    # question, and must not flag the new attempt.
    errors = validate_config(
        config(
            nominations=[
                nomination(candidate="hopper", outcome="deferred", objections=[]),
                nomination(candidate="hopper", outcome=""),
            ]
        )
    )
    assert not [e for e in errors if "unsettled nomination" in e]


def test_two_settled_nominations_for_one_candidate_are_accepted() -> None:
    errors = validate_config(
        config(
            nominations=[
                nomination(candidate="grace", outcome="accepted"),
                nomination(candidate="grace", outcome="accepted"),
            ]
        )
    )
    assert not [e for e in errors if "unsettled nomination" in e]


def test_accepted_nomination_without_a_seat_is_rejected() -> None:
    # The app writes the acceptance and the board entry together, so this
    # pair can only disagree in a hand-edited file.
    errors = validate_config(
        config(nominations=[nomination(candidate="hopper", outcome="accepted")])
    )
    assert any("holds no board seat" in e for e in errors)


def test_accepted_nomination_of_a_seated_member_is_accepted() -> None:
    errors = validate_config(
        config(nominations=[nomination(candidate="grace", outcome="accepted")])
    )
    assert not [e for e in errors if e.startswith("config.yml: nominations")]


def test_accepted_nomination_of_an_inactive_member_is_accepted() -> None:
    # G-14 moves a silent member to `inactive` without taking their seat away
    # (tools/convener_ops/maintenance/sweep.py::sweep_inactive_members). The nomination
    # records that the board granted the seat, which stays true; requiring the member
    # to be active here would make that rule unable to touch anyone the board
    # itself admitted.
    errors = validate_config(
        config(
            board=[
                board_member(login="carol"),
                board_member(login="ada"),
                board_member(login="grace", status="inactive"),
            ],
            nominations=[nomination(candidate="grace", outcome="accepted")],
        )
    )
    assert not [e for e in errors if e.startswith("config.yml: nominations")]


def test_board_member_status_must_be_valid() -> None:
    errors = validate_config(config(board=[board_member(status="bogus")]))
    assert any("invalid board member status" in e for e in errors)


def test_board_member_joined_on_must_be_a_date() -> None:
    errors = validate_config(config(board=[board_member(joined_on="01/01/2024")]))
    assert any("board member joined_on must be YYYY-MM-DD" in e for e in errors)


def test_board_member_unavailable_until_must_be_a_date() -> None:
    errors = validate_config(
        config(board=[board_member(unavailable_until="not-a-date")])
    )
    assert any("board member unavailable_until must be YYYY-MM-DD" in e for e in errors)


def test_publication_approved_on_must_be_a_date() -> None:
    s = speaker(
        publication={
            "consent": "granted",
            "approved_by": "carol",
            "approved_on": "not-a-date",
            "objections": [],
            "outcome": "",
        }
    )
    errors = validate_speakers([s], editions=EDITIONS)
    assert any("approved_on must be YYYY-MM-DD" in e for e in errors)


def test_publication_outcome_must_be_valid() -> None:
    s = speaker(
        publication={
            "consent": "",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "bogus",
        }
    )
    errors = validate_speakers([s], editions=EDITIONS)
    assert any("invalid publication outcome" in e for e in errors)


def test_publication_objection_member_must_look_like_a_login() -> None:
    s = speaker(
        publication={
            "consent": "",
            "approved_by": "",
            "approved_on": "",
            "objections": [objection(member="not a login!")],
            "outcome": "",
        }
    )
    errors = validate_speakers([s], editions=EDITIONS)
    assert any("invalid objection member" in e for e in errors)


def test_refused_consent_with_published_outcome_is_rejected() -> None:
    # Cross-field check: consent and outcome can disagree in a YAML file, and
    # no type forbids it. This is now a statement about the past rather than
    # a live defence -- the app writes `outcome: published` in exactly one
    # place, behind `canArchive` -- so what it still catches is a file
    # hand-edited outside the app.
    s = speaker(
        publication={
            "consent": "refused",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "published",
        }
    )
    errors = validate_speakers([s], editions=EDITIONS)
    assert any("refused consent cannot have outcome published" in e for e in errors)


def test_ballot_date_must_be_a_date() -> None:
    s = speaker(
        selection={
            "ballots": [ballot(date="not-a-date")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins={"carol"}, editions=EDITIONS)
    assert any("date must be YYYY-MM-DD" in e for e in errors)


def test_selection_opened_on_must_be_a_date() -> None:
    s = speaker(selection={"ballots": [], "opened_on": "not-a-date", "decided_on": ""})
    errors = validate_speakers([s], editions=EDITIONS)
    assert any("opened_on must be YYYY-MM-DD" in e for e in errors)


def test_a_board_over_its_ceiling_is_rejected() -> None:
    # The ceiling is enforced at the moment of seating, so a file above it is
    # one the app could not have written. The floor is a target and is
    # reported instead - see test_validate.py.
    board = [board_member(login=f"m{i}") for i in range(10)]
    errors = validate_config(config(board=board, board_min=3, board_max=9))
    assert any("over board_max" in e for e in errors)


def test_ballot_from_non_member_fires_even_when_board_is_empty() -> None:
    # An empty board must not silently disable the non-member
    # check - it must fail loudly, the same as any ballot would in a config
    # with no board yet.
    s = speaker(
        selection={
            "ballots": [ballot(voter="anyone")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins=frozenset(), editions=EDITIONS)
    assert any("ballot from a non-member" in e for e in errors)


# --- Found on a second review ---------------------------------------------


def test_selection_decided_on_must_be_a_date() -> None:
    # The migration copies decided_on into every generated ballot's date
    # to schema v3: a malformed value here would
    # propagate into every ballot it touches, not stay in one field.
    s = speaker(selection={"ballots": [], "opened_on": "", "decided_on": "not-a-date"})
    errors = validate_speakers([s], editions=EDITIONS)
    assert any("decided_on must be YYYY-MM-DD" in e for e in errors)


def test_nominations_must_be_a_list() -> None:
    errors = validate_config(config(nominations="not-a-list"))
    assert any("nominations must be a list" in e for e in errors)


def test_a_missing_nominations_key_is_reported_once_not_twice() -> None:
    # Reported once, by the missing-keys check -- must not also trip
    # "nominations must be a list" (guarded by `"nominations" in cfg`, for
    # the same reason as the board and sla_days checks in test_validate.py)
    # or be iterated as an empty list.
    cfg = config()
    del cfg["nominations"]
    errors = validate_config(cfg)
    assert any("missing keys ['nominations']" in e for e in errors)
    assert not any("nominations must be a list" in e for e in errors)
    assert not any("nominations[" in e for e in errors)


def test_a_nomination_with_no_objections_key_is_not_an_error() -> None:
    # None (the field simply absent) means the record predates the field or
    # never had one -- absent is not malformed, only a non-list value is
    # (see test_nomination_objections_must_be_a_list below).
    nom = nomination()
    del nom["objections"]
    errors = validate_config(config(nominations=[nom]))
    assert not any(".objections" in e for e in errors)


def test_a_nomination_with_no_candidate_is_skipped_in_the_deferral_check() -> None:
    # The deferral backstop (below) tracks open nominations by candidate
    # name; one with no usable candidate -- already flagged invalid by the
    # check above -- must not be tracked under an empty-string key, or two
    # such nominations would wrongly trip "already has an unsettled
    # nomination" against each other.
    errors = validate_config(
        config(nominations=[nomination(candidate=""), nomination(candidate="")])
    )
    assert not any("already has an unsettled nomination" in e for e in errors)


def test_nomination_entry_must_be_a_mapping() -> None:
    errors = validate_config(config(nominations=["not-a-mapping"]))
    nomination_errors = [e for e in errors if e.startswith("config.yml: nominations")]
    assert any("not a mapping" in e for e in nomination_errors)


def test_publication_must_be_a_mapping() -> None:
    s = speaker(publication="not-a-mapping")
    errors = validate_speakers([s], editions=EDITIONS)
    assert any(".publication: not a mapping" in e for e in errors)


def test_nomination_objections_must_be_a_list() -> None:
    errors = validate_config(config(nominations=[nomination(objections="not-a-list")]))
    assert any(".objections: must be a list" in e for e in errors)


def test_nomination_objection_entry_must_be_a_mapping() -> None:
    errors = validate_config(
        config(nominations=[nomination(objections=["not-a-mapping"])])
    )
    assert any(".objections[0]: not a mapping" in e for e in errors)


def test_nomination_objection_date_must_be_a_date() -> None:
    errors = validate_config(
        config(nominations=[nomination(objections=[objection(date="not-a-date")])])
    )
    assert any("objections[0]: date must be YYYY-MM-DD" in e for e in errors)


# --- The migration's own guarantees ---------------------------------------


def test_assigned_to_must_be_present_and_a_string() -> None:
    # Every migrated speaker carries the field, empty when no
    # board member owns the lead yet. A missing one is an unmigrated record.
    s = speaker()
    del s["assigned_to"]
    assert any(
        "assigned_to must be a string" in e
        for e in validate_speakers([s], editions=EDITIONS)
    )


def test_assigned_to_must_name_a_board_member_when_set() -> None:
    errors = validate_speakers(
        [speaker(assigned_to="someone-else")],
        board_logins={"carol"},
        editions=EDITIONS,
    )
    assert any("assigned_to is not a board member" in e for e in errors)


def test_an_empty_assigned_to_is_accepted() -> None:
    assert (
        validate_speakers([speaker(assigned_to="")], {"carol"}, editions=EDITIONS) == []
    )


def test_proposed_by_is_never_checked_against_the_board() -> None:
    # It is the submitter's self-reported name, often someone outside the
    # team entirely - checking it against the board would reject the public
    # form's own leads.
    assert (
        validate_speakers(
            [speaker(proposed_by="A Passer-By")], {"carol"}, editions=EDITIONS
        )
        == []
    )


@pytest.mark.parametrize("spelling", ["form", "Form", "  OUTREACH ", "organizer"])
def test_proposed_by_may_not_be_spelt_like_a_provenance(spelling: str) -> None:
    """A record whose `proposed_by` is the name of a `source` value is
    refused, however it is cased or padded.

    The defect this closes was in the data, not the code: rows imported
    before the schema existed wrote the channel into the field that names a
    person, while `source` on the same rows said something else -- so the
    field held a person on some records and a provenance on others, and
    every reader downstream had to guess. `source` is the field that
    answers "how did this arrive", and this is the only part of the
    question a validator can settle without deciding what is a name.
    """
    errors = validate_speakers([speaker(proposed_by=spelling)], editions=EDITIONS)
    assert [e for e in errors if "proposed_by names a person" in e], errors
    assert all("spk-001" in error for error in errors), errors


def test_proposed_by_may_hold_a_name_that_merely_contains_one() -> None:
    """The rule matches the whole field, never a word inside it: somebody
    actually called Form-something is a person, and a validator that read
    their name as a channel would be the same guess in the other
    direction."""
    assert validate_speakers([speaker(proposed_by="Formby")], editions=EDITIONS) == []
    assert (
        validate_speakers(
            [speaker(proposed_by="the organizers' own list")], editions=EDITIONS
        )
        == []
    )


def test_an_empty_proposed_by_is_accepted() -> None:
    """Nobody on record is a state the file has to be able to hold -- a
    lead the board raised itself has no submitter to name."""
    assert validate_speakers([speaker(proposed_by="")], editions=EDITIONS) == []


def test_a_speaker_without_career_stage_is_rejected() -> None:
    # Unconditional since the migration: before it, absence
    # was a legacy state; after it, absence means a field was dropped.
    s = speaker()
    del s["career_stage"]
    assert any(
        "invalid career_stage" in e for e in validate_speakers([s], editions=EDITIONS)
    )


def test_a_speaker_without_a_publication_block_is_rejected() -> None:
    s = speaker()
    del s["publication"]
    assert any(
        ".publication: not a mapping" in e
        for e in validate_speakers([s], editions=EDITIONS)
    )


def test_a_board_member_without_a_status_is_rejected() -> None:
    # governance.active_board keeps only members whose status is exactly
    # 'active': a member with none silently leaves the board, and with it
    # the denominator of every vote.
    member = board_member()
    del member["status"]
    errors = validate_config(config(board=[member, board_member(login="ada")]))
    assert any("invalid board member status" in e for e in errors)


def test_published_recording_with_no_approval_is_rejected() -> None:
    s = speaker(
        publication={
            "consent": "granted",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "published",
        }
    )
    errors = validate_speakers([s], editions=EDITIONS)
    assert any("has no approval on record" in e for e in errors)


def test_published_recording_with_a_standing_objection_is_rejected() -> None:
    s = speaker(
        publication={
            "consent": "granted",
            "approved_by": "alice",
            "approved_on": "2026-01-09",
            "objections": [
                {
                    "member": "carol",
                    "reason": "unpublished data",
                    "date": "2026-01-10",
                    "resolved_on": "",
                }
            ],
            "outcome": "published",
        }
    )
    errors = validate_speakers([s], editions=EDITIONS)
    assert any("has a standing objection" in e for e in errors)


def test_a_resolved_objection_does_not_trip_the_published_check() -> None:
    s = speaker(
        publication={
            "consent": "granted",
            "approved_by": "alice",
            "approved_on": "2026-01-09",
            "objections": [
                {
                    "member": "carol",
                    "reason": "unpublished data",
                    "date": "2026-01-10",
                    "resolved_on": "2026-01-12",
                }
            ],
            "outcome": "published",
        }
    )
    assert validate_speakers([s], editions=EDITIONS) == []


def test_a_malformed_resolved_on_is_reported() -> None:
    s = speaker(
        publication={
            "consent": "granted",
            "approved_by": "alice",
            "approved_on": "2026-01-09",
            "objections": [
                {
                    "member": "carol",
                    "reason": "x",
                    "date": "2026-01-10",
                    "resolved_on": "12 January",
                }
            ],
            "outcome": "",
        }
    )
    errors = validate_speakers([s], editions=EDITIONS)
    assert any("resolved_on must be YYYY-MM-DD" in e for e in errors)
