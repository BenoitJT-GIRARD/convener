"""Schema v3 validation: ballots, board membership, and the publication gate.

Eleven cases, from task-4-brief.md, each pinned on the exact substring its
error message must contain (the migration's own tests and CI both grep for
these strings). A twelfth case (board_members obsolete) is added per the
task's decision 2, which is not itself in the brief's table.
"""

from __future__ import annotations

from conftest import ballot, board_member, config, nomination, objection, speaker

from convener_ops.validate import validate_config, validate_speakers


def test_ballot_with_unknown_value_is_rejected() -> None:
    s = speaker(
        selection={
            "ballots": [ballot(value="bogus")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins={"Anonymous"})
    assert any("invalid ballot value" in e for e in errors)


def test_recused_ballot_without_coi_reason_is_rejected() -> None:
    s = speaker(
        selection={
            "ballots": [ballot(value="recused", coi_reason="")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins={"Anonymous"})
    assert any("recusal requires coi_reason" in e for e in errors)


def test_two_ballots_from_the_same_voter_on_a_lead_is_rejected() -> None:
    s = speaker(
        selection={
            "ballots": [ballot(voter="a"), ballot(voter="a")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins={"a"})
    assert any("duplicate ballot" in e for e in errors)


def test_ballot_from_a_login_absent_from_the_board_is_rejected() -> None:
    s = speaker(
        selection={
            "ballots": [ballot(voter="not-on-board")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins={"Anonymous"})
    assert any("ballot from a non-member" in e for e in errors)


def test_unknown_career_stage_is_rejected() -> None:
    errors = validate_speakers([speaker(career_stage="professor")])
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
    errors = validate_speakers([s])
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
    # Not in the brief's table, but decision 2 of the task requires the same
    # loud treatment for board_members as for vote_threshold: a file that
    # still carries the flat login list has not been migrated to `board`.
    errors = validate_config(config(board_members=["Anonymous"]))
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
    assert validate_speakers([s], board_logins=board_logins) == []
    assert validate_config(config()) == []


# --- Fix round 1 (coordinator review) ------------------------------------


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


def test_accepted_nomination_with_open_objections_is_rejected() -> None:
    # Cross-field backstop: outcome and objections can disagree, and no type
    # forbids it. This is the backstop for a hand-edited file, ahead of the
    # transformations (later tasks) that are meant to prevent it in the app.
    errors = validate_config(
        config(nominations=[nomination(outcome="accepted", objections=[objection()])])
    )
    assert any("accepted nomination has open objections" in e for e in errors)


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
            "approved_by": "Anonymous",
            "approved_on": "not-a-date",
            "objections": [],
            "outcome": "",
        }
    )
    errors = validate_speakers([s])
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
    errors = validate_speakers([s])
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
    errors = validate_speakers([s])
    assert any("invalid objection member" in e for e in errors)


def test_refused_consent_with_published_outcome_is_rejected() -> None:
    # Cross-field backstop: consent and outcome can disagree, and no type
    # forbids it. This is the backstop for a hand-edited file, ahead of the
    # transformations (later tasks) that are meant to prevent it in the app.
    s = speaker(
        publication={
            "consent": "refused",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "published",
        }
    )
    errors = validate_speakers([s])
    assert any("refused consent cannot have outcome published" in e for e in errors)


def test_ballot_date_must_be_a_date() -> None:
    s = speaker(
        selection={
            "ballots": [ballot(date="not-a-date")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins={"Anonymous"})
    assert any("date must be YYYY-MM-DD" in e for e in errors)


def test_selection_opened_on_must_be_a_date() -> None:
    s = speaker(selection={"ballots": [], "opened_on": "not-a-date", "decided_on": ""})
    errors = validate_speakers([s])
    assert any("opened_on must be YYYY-MM-DD" in e for e in errors)


def test_board_size_outside_bounds_is_rejected() -> None:
    errors = validate_config(config(board=[board_member()]))
    assert any("outside board_min..board_max" in e for e in errors)


def test_ballot_from_non_member_fires_even_when_board_is_empty() -> None:
    # Minor 2: an empty board must not silently disable the non-member
    # check - it must fail loudly, the same as any ballot would in a config
    # with no board yet.
    s = speaker(
        selection={
            "ballots": [ballot(voter="anyone")],
            "opened_on": "",
            "decided_on": "",
        }
    )
    errors = validate_speakers([s], board_logins=frozenset())
    assert any("ballot from a non-member" in e for e in errors)


# --- Fix round 2 (coordinator review) -------------------------------------


def test_selection_decided_on_must_be_a_date() -> None:
    # The migration copies decided_on into every generated ballot's date
    # (scripts/migrate_v3.py, Task 5): a malformed value here would
    # propagate into every ballot it touches, not stay in one field.
    s = speaker(selection={"ballots": [], "opened_on": "", "decided_on": "not-a-date"})
    errors = validate_speakers([s])
    assert any("decided_on must be YYYY-MM-DD" in e for e in errors)


def test_nominations_must_be_a_list() -> None:
    errors = validate_config(config(nominations="not-a-list"))
    assert any("nominations must be a list" in e for e in errors)


def test_nomination_entry_must_be_a_mapping() -> None:
    errors = validate_config(config(nominations=["not-a-mapping"]))
    nomination_errors = [e for e in errors if e.startswith("config.yml: nominations")]
    assert any("not a mapping" in e for e in nomination_errors)


def test_publication_must_be_a_mapping() -> None:
    s = speaker(publication="not-a-mapping")
    errors = validate_speakers([s])
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
