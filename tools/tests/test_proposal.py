from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from conftest import board_member, config, speaker

from convener_ops.proposal import assign_lead, skip_reason, to_lead, verify_signature
from convener_ops.sweep import expire_votes
from convener_ops.validate import validate_speakers

TODAY = "2026-01-08"

ASSIGN_LEAD_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "governance-cases.json").read_text(
        encoding="utf-8"
    )
)["assign_lead_cases"]


def _fields(*pairs: tuple[str, str]) -> dict[str, str]:
    return dict(pairs)


def test_a_valid_signature_is_accepted() -> None:
    payload = '{"fields": []}'
    secret = "shh"
    import hashlib
    import hmac as hmac_mod

    signature = hmac_mod.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    assert verify_signature(payload, signature, secret) is True


def test_an_invalid_signature_is_rejected() -> None:
    assert verify_signature('{"fields": []}', "deadbeef", "shh") is False


def test_with_no_secret_configured_the_payload_is_accepted() -> None:
    assert verify_signature('{"fields": []}', "anything-or-nothing", "") is True


def test_the_next_id_is_assigned_from_the_highest_existing_one() -> None:
    existing = [speaker(id="spk-001"), speaker(id="spk-007")]
    fields = _fields(("Name", "Grace Hopper"), ("Email", "grace@example.org"))
    lead = to_lead(fields, existing, config(), TODAY)
    assert lead is not None
    assert lead["id"] == "spk-008"


def test_a_submission_matching_a_lead_by_email_is_ignored_as_duplicate() -> None:
    existing = [speaker(id="spk-001", email="grace@example.org", status="lead")]
    fields = _fields(("Name", "Grace Hopper"), ("Email", "grace@example.org"))
    assert to_lead(fields, existing, config(), TODAY) is None


def test_a_submission_with_an_empty_name_is_ignored() -> None:
    fields = _fields(("Name", ""), ("Email", "grace@example.org"))
    assert to_lead(fields, [], config(), TODAY) is None


def test_skip_reason_distinguishes_empty_name_from_duplicate() -> None:
    existing = [speaker(id="spk-001", email="grace@example.org", status="lead")]
    empty_name = _fields(("Name", ""), ("Email", "grace@example.org"))
    duplicate = _fields(("Name", "Grace Hopper"), ("Email", "grace@example.org"))
    fresh = _fields(("Name", "Grace Hopper"), ("Email", "new@example.org"))

    assert skip_reason(empty_name, existing) == "empty name"
    assert skip_reason(duplicate, existing) == "duplicate email"
    assert skip_reason(fresh, existing) is None


def test_an_unrecognised_gender_falls_back_to_undisclosed() -> None:
    fields = _fields(("Name", "Grace Hopper"), ("Gender", "not-a-gender"))
    lead = to_lead(fields, [], config(), TODAY)
    assert lead is not None
    assert lead["gender"] == "undisclosed"


def test_a_declared_career_stage_is_kept() -> None:
    fields = _fields(("Name", "Grace Hopper"), ("Career stage", "postdoc"))
    lead = to_lead(fields, [], config(), TODAY)
    assert lead is not None
    assert lead["career_stage"] == "postdoc"


def test_an_unrecognised_career_stage_falls_back_to_undisclosed() -> None:
    # A free-text answer, a renamed form option or a translation must not open
    # a career stage of its own in the balance figures.
    fields = _fields(("Name", "Grace Hopper"), ("Career stage", "Assistant Professor"))
    lead = to_lead(fields, [], config(), TODAY)
    assert lead is not None
    assert lead["career_stage"] == "undisclosed"


def test_a_submission_that_declares_no_career_stage_is_still_a_lead() -> None:
    # The form is answerable without declaring one, and the answer is recorded
    # as "undisclosed" rather than left absent -- it is counted, not dropped.
    lead = to_lead(_fields(("Name", "Grace Hopper")), [], config(), TODAY)
    assert lead is not None
    assert lead["career_stage"] == "undisclosed"
    assert lead["gender"] == "undisclosed"


def test_a_comma_separated_links_string_becomes_a_stripped_list() -> None:
    fields = _fields(
        ("Name", "Grace Hopper"), ("Links", " a@example.org , , b@example.org ")
    )
    lead = to_lead(fields, [], config(), TODAY)
    assert lead is not None
    assert lead["links"] == ["a@example.org", "b@example.org"]


def test_a_form_lead_keeps_the_submitters_name_and_assigns_a_board_member() -> None:
    # A form submission is self-reported by a visitor, not a team member.
    # `proposed_by` keeps that name verbatim -- it is the only record of who
    # to tell if the Board declines the lead. `assigned_to` is a separate
    # field: the board member who will look after the lead, filled by
    # assign_lead (G-17). Both facts are asserted in one test so they cannot
    # drift apart again.
    fields = _fields(("Name", "Grace Hopper"), ("Your name", "Grace Hopper"))
    lead = to_lead(fields, [], config(), TODAY)
    assert lead is not None
    assert lead["proposed_by"] == "Grace Hopper"
    assert lead["assigned_to"] == assign_lead([], config(), TODAY)
    assert lead["assigned_to"] != "Grace Hopper"


def test_assign_lead_prefers_the_member_carrying_fewer_open_leads() -> None:
    cfg = config(board=[board_member(login="ada"), board_member(login="grace")])
    existing = [
        speaker(id="spk-001", status="lead", assigned_to="ada"),
        speaker(id="spk-002", status="lead", assigned_to="ada"),
        speaker(id="spk-003", status="lead", assigned_to="grace"),
    ]
    assert assign_lead(existing, cfg, TODAY) == "grace"


def test_assign_lead_never_picks_an_unavailable_member() -> None:
    cfg = config(
        board=[
            board_member(login="ada", unavailable_until=TODAY),
            board_member(login="grace"),
        ]
    )
    assert assign_lead([], cfg, TODAY) == "grace"


def test_assign_lead_returns_an_empty_string_rather_than_raising() -> None:
    cfg = config(board=[board_member(login="ada", unavailable_until=TODAY)])
    assert assign_lead([], cfg, TODAY) == ""


def test_assign_lead_tie_break_is_reproducible_across_calls() -> None:
    cfg = config(board=[board_member(login="ada"), board_member(login="grace")])
    existing = [
        speaker(id="spk-001", status="lead", assigned_to="ada"),
        speaker(id="spk-002", status="lead", assigned_to="grace"),
    ]
    first = assign_lead(existing, cfg, TODAY)
    second = assign_lead(existing, cfg, TODAY)
    assert first == second


@pytest.mark.parametrize("case", ASSIGN_LEAD_CASES, ids=lambda c: c["name"])
def test_assign_lead_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    assert (
        assign_lead(case["speakers"], {"board": case["board"]}, case["on"])
        == (case["expected"])
    )


def test_a_form_lead_is_written_in_the_v3_shape() -> None:
    lead = to_lead(_fields(("Name", "Ada Lovelace")), [], config(), TODAY)
    assert lead is not None
    assert lead["selection"] == {"ballots": [], "opened_on": TODAY, "decided_on": ""}
    assert lead["career_stage"] == "undisclosed"
    assert lead["publication"]["consent"] == ""
    assert validate_speakers([lead], {m["login"] for m in config()["board"]}) == []


def test_a_form_lead_opens_its_vote_window_so_it_can_expire() -> None:
    # sweep.expire_votes skips any lead whose opened_on does not parse, and
    # it does so silently so an overnight job never dies on bad data. A lead
    # written without one was therefore exempt from expiry, for ever, with
    # nothing anywhere reporting it.
    lead = to_lead(_fields(("Name", "Ada Lovelace")), [], config(), "2026-01-01")
    assert lead is not None
    now = datetime(2026, 3, 1, tzinfo=UTC)
    swept, changes = expire_votes([lead], config(), now)
    assert swept[0]["status"] == "parked"
    assert any("vote window expired" in c for c in changes)
