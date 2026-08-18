"""Schema v3 validation: ballots, board membership, and the publication gate.

Eleven cases, from task-4-brief.md, each pinned on the exact substring its
error message must contain (the migration's own tests and CI both grep for
these strings). A twelfth case (board_members obsolete) is added per the
task's decision 2, which is not itself in the brief's table.
"""

from __future__ import annotations

from conftest import ballot, board_member, config, speaker

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
