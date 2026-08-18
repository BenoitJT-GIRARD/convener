from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import board_member, config, speaker

from convener_ops.proposal import assign_lead, skip_reason, to_lead, verify_signature

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


def test_a_comma_separated_links_string_becomes_a_stripped_list() -> None:
    fields = _fields(
        ("Name", "Grace Hopper"), ("Links", " a@example.org , , b@example.org ")
    )
    lead = to_lead(fields, [], config(), TODAY)
    assert lead is not None
    assert lead["links"] == ["a@example.org", "b@example.org"]


def test_a_form_lead_is_assigned_to_a_board_member_not_the_visitor() -> None:
    # source: form leads never carry a member proposer -- the visitor's own
    # name is not a valid `proposed_by` (schema: "team member who proposed
    # this speaker"). assign_lead fills it instead.
    fields = _fields(("Name", "Grace Hopper"), ("Your name", "Grace Hopper"))
    lead = to_lead(fields, [], config(), TODAY)
    assert lead is not None
    assert lead["proposed_by"] == assign_lead([], config(), TODAY)
    assert lead["proposed_by"] != "Grace Hopper"


def test_assign_lead_prefers_the_member_carrying_fewer_open_leads() -> None:
    cfg = config(board=[board_member(login="ada"), board_member(login="grace")])
    existing = [
        speaker(id="spk-001", status="lead", proposed_by="ada"),
        speaker(id="spk-002", status="lead", proposed_by="ada"),
        speaker(id="spk-003", status="lead", proposed_by="grace"),
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
        speaker(id="spk-001", status="lead", proposed_by="ada"),
        speaker(id="spk-002", status="lead", proposed_by="grace"),
    ]
    first = assign_lead(existing, cfg, TODAY)
    second = assign_lead(existing, cfg, TODAY)
    assert first == second


@pytest.mark.parametrize("case", ASSIGN_LEAD_CASES, ids=lambda c: c["name"])
def test_assign_lead_matches_the_shared_fixture(case: dict) -> None:
    assert (
        assign_lead(case["speakers"], {"board": case["board"]}, case["on"])
        == (case["expected"])
    )
