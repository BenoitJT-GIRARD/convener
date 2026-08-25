from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from conftest import EDITIONS, board_member, config, speaker

from convener_ops.proposal import (
    CAREER_STAGE_ORDER,
    CAREER_STAGES,
    GENDER_ORDER,
    GENDERS,
    assign_lead,
    field_value,
    skip_reason,
    to_lead,
    verify_signature,
)
from convener_ops.sweep import expire_votes
from convener_ops.validate import validate_speakers

TODAY = "2026-01-08"

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "governance-cases.json").read_text(
        encoding="utf-8"
    )
)
ASSIGN_LEAD_CASES = _FIXTURE["assign_lead_cases"]
WEBHOOK_SIGNATURE_CASES = _FIXTURE["webhook_signature_cases"]
# A parametrize over an emptied fixture list silently collects zero tests and
# still passes -- this project has a history of vacuously passing tests, so
# this guard makes that impossible for this block specifically.
assert WEBHOOK_SIGNATURE_CASES


def _fields(*pairs: tuple[str, str]) -> dict[str, str]:
    return dict(pairs)


def test_a_body_signed_the_way_tally_signs_it_verifies() -> None:
    secret = "s3cr3t"
    body = '{"data":{"fields":[]}}'
    sig = base64.b64encode(
        hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    ).decode()
    assert verify_signature(body, sig, secret)


def test_a_hex_signature_is_refused() -> None:
    """The regression this task exists to fix: hexdigest was what the code
    computed, and base64 is what Tally sends."""
    secret = "s3cr3t"
    body = '{"data":{"fields":[]}}'
    hexsig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    assert not verify_signature(body, hexsig, secret)


def test_one_changed_byte_fails() -> None:
    secret = "s3cr3t"
    body = '{"data":{"fields":[{"label":"Name","value":"Ada Lovelace"}]}}'
    tampered = body.replace("Ada", "Bda")
    sig = base64.b64encode(
        hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    ).decode()
    assert not verify_signature(tampered, sig, secret)


def test_a_non_ascii_signature_is_refused_not_crashed() -> None:
    """hmac.compare_digest raises TypeError comparing two str when either
    holds a non-ASCII character. signature is attacker-controlled (relayed
    verbatim from an HTTP header by the Cloudflare Worker), so a crafted
    header must be refused, not let the exception escape the console-script
    entry point."""
    secret = "s3cr3t"
    body = '{"data":{"fields":[]}}'
    assert verify_signature(body, "h\u00e9llo-not-a-real-signature", secret) is False


def test_a_lone_surrogate_signature_is_refused_not_crashed() -> None:
    """A lone surrogate half (possible from a header carrying invalid
    UTF-8) cannot be encoded at all -- `UnicodeEncodeError`, not the
    `TypeError` the non-ASCII case above raises -- and this is the only
    test that reaches that `except` branch."""
    secret = "s3cr3t"
    body = '{"data":{"fields":[]}}'
    assert verify_signature(body, "\ud800", secret) is False


def test_a_signature_with_a_trailing_space_is_refused() -> None:
    secret = "s3cr3t"
    body = '{"data":{"fields":[]}}'
    sig = base64.b64encode(
        hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    ).decode()
    assert verify_signature(body, sig + " ", secret) is False


def test_an_invalid_signature_is_rejected() -> None:
    assert verify_signature('{"fields": []}', "deadbeef", "shh") is False


def test_with_no_secret_configured_the_payload_is_accepted() -> None:
    # D-13: an unconfigured integration is a normal state, not an error, and
    # this stays true whatever body or signature-shaped string shows up.
    assert verify_signature('{"fields": []}', "anything-or-nothing", "") is True


@pytest.mark.parametrize("case", WEBHOOK_SIGNATURE_CASES, ids=lambda c: c["name"])
def test_verify_signature_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    assert (
        verify_signature(case["body"], case["signature"], case["secret"])
        == case["valid"]
    )


def test_the_next_id_is_assigned_from_the_highest_existing_one() -> None:
    existing = [speaker(id="spk-001"), speaker(id="spk-007")]
    fields = _fields(("Name", "Grace Hopper"), ("Email", "grace@example.org"))
    lead = to_lead(fields, existing, config(), TODAY)
    assert lead is not None
    assert lead["id"] == "spk-008"


def test_the_next_id_generation_skips_a_non_mapping_entry_in_existing() -> None:
    # `existing` is `speakers.yml` as `cli._load` parsed it -- raw YAML, not
    # schema-checked (validation is a separate step, `convener-validate`) --
    # before handle_proposal ever passes it in. A list item that is not a
    # mapping (a stray scalar from a hand-edit) must be skipped rather than
    # crash `.get("id")` on it.
    existing = [
        speaker(id="spk-001"),
        "not-a-mapping",
        speaker(id="spk-007"),
    ]
    fields = _fields(("Name", "Grace Hopper"))
    lead = to_lead(fields, existing, config(), TODAY)  # type: ignore[arg-type]
    assert lead is not None
    assert lead["id"] == "spk-008"


def test_the_next_id_generation_skips_an_id_outside_the_spk_pattern() -> None:
    # validate_speakers checks that `id` is present and unique, not that it
    # matches "spk-NNN" (convener_ops.validate.validate_speakers) -- so a legacy
    # or hand-typed id in another shape can reach here. It must not raise,
    # and must not perturb the next id computed from the ids that do match.
    existing = [speaker(id="legacy-042"), speaker(id="spk-007")]
    fields = _fields(("Name", "Grace Hopper"))
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


def test_assign_lead_ignores_a_speaker_that_has_moved_past_the_lead_stage() -> None:
    # assign_lead balances by *open* leads only (G-17): a speaker who moved
    # on to "confirmed" must not still count against the member who
    # onboarded them, or that member would look permanently busier than
    # they are. ada carries two non-lead records against grace's one real
    # lead, so a filter that counted every status regardless would pick
    # grace instead -- the two outcomes disagree outright, not just on a
    # tie-break.
    cfg = config(board=[board_member(login="ada"), board_member(login="grace")])
    existing = [
        speaker(id="spk-001", status="confirmed", assigned_to="ada"),
        speaker(id="spk-002", status="delivered", assigned_to="ada"),
        speaker(id="spk-003", status="lead", assigned_to="grace"),
    ]
    assert assign_lead(existing, cfg, TODAY) == "ada"


def test_a_form_lead_is_written_in_the_v3_shape() -> None:
    lead = to_lead(_fields(("Name", "Ada Lovelace")), [], config(), TODAY)
    assert lead is not None
    assert lead["selection"] == {"ballots": [], "opened_on": TODAY, "decided_on": ""}
    assert lead["career_stage"] == "undisclosed"
    assert lead["publication"]["consent"] == ""
    assert (
        validate_speakers(
            [lead], {m["login"] for m in config()["board"]}, editions=EDITIONS
        )
        == []
    )


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


# --------------------------------------------------------------------- #
# GENDER_ORDER/CAREER_STAGE_ORDER -- the guard against re-introducing the
# hash-seed drift the sets used to carry (prerequisite for R-9).
# --------------------------------------------------------------------- #


def test_gender_order_is_exactly_the_set_it_derives() -> None:
    assert set(GENDER_ORDER) == GENDERS
    assert len(GENDER_ORDER) == len(GENDERS)


def test_career_stage_order_is_exactly_the_set_it_derives() -> None:
    assert set(CAREER_STAGE_ORDER) == CAREER_STAGES
    assert len(CAREER_STAGE_ORDER) == len(CAREER_STAGES)


def test_the_vocabulary_this_form_offers_is_pinned() -> None:
    # A change to either set changes what scripts/create_tally_form.py
    # should build a dropdown from; pinned literally here -- not only in
    # test_create_tally_form.py, which this pin outlives if that script is
    # ever deleted -- so the change is caught, not only inferred from a
    # form nobody happened to be looking at.
    assert {"M", "F", "NB", "undisclosed"} == GENDERS
    assert {
        "phd",
        "postdoc",
        "independent",
        "group-leader",
        "other",
        "undisclosed",
    } == CAREER_STAGES


# --------------------------------------------------------------------- #
# field_value -- resolving a picker's chosen option id(s) against that
# field's own `options` array (R-9).
# --------------------------------------------------------------------- #


def test_field_value_resolves_a_single_select_id_to_its_text() -> None:
    field = {
        "label": "Gender",
        "value": ["opt-nb"],
        "options": [
            {"id": "opt-f", "text": "F"},
            {"id": "opt-nb", "text": "NB"},
        ],
    }
    assert field_value(field) == "NB"


def test_field_value_joins_a_multi_select_answer_with_a_comma() -> None:
    field = {
        "label": "Interests",
        "value": ["a", "b"],
        "options": [
            {"id": "a", "text": "Soccer"},
            {"id": "b", "text": "Skiing"},
        ],
    }
    assert field_value(field) == "Soccer, Skiing"


def test_field_value_falls_back_to_the_raw_id_when_unmapped() -> None:
    # A malformed or truncated payload -- an id absent from `options` --
    # must read as an odd value, not disappear.
    assert field_value({"value": ["mystery-id"], "options": []}) == "mystery-id"


def test_field_value_on_an_empty_selection_is_an_empty_string() -> None:
    assert field_value({"value": [], "options": []}) == ""


def test_field_value_passes_a_plain_text_answer_through_unchanged() -> None:
    assert field_value({"value": "Ada Lovelace"}) == "Ada Lovelace"


def test_field_value_stringifies_a_number_or_boolean_answer() -> None:
    assert field_value({"value": 10}) == "10"
    assert field_value({"value": True}) == "True"


def test_field_value_on_a_missing_value_is_an_empty_string() -> None:
    assert field_value({}) == ""


def test_get_still_degrades_a_raw_unresolved_list_to_recognisable_text() -> None:
    # The last line of defence: field_value is meant to run first, but if a
    # caller ever skips it, `_get` (exercised here through to_lead) must not
    # let "['FR', 'BE']" reach a record.
    #
    # Gender was the wrong field to prove this through: "opt-nb" and
    # "['opt-nb']" are *both* outside GENDERS, so to_lead's fallback to
    # "undisclosed" produces the same result whether or not `_get`'s list
    # branch ever runs -- a `_get` rewritten without that branch still
    # passes. Country passes its resolved value straight through with no
    # such fallback, so a joined "FR, BE" and an unjoined "['FR', 'BE']"
    # are distinguishable, and this test actually depends on the branch it
    # names.
    fields = {"Name": "Ada Lovelace", "Country": ["FR", "BE"]}
    lead = to_lead(fields, [], config(), TODAY)  # type: ignore[arg-type]
    assert lead is not None
    assert lead["country"] == "FR, BE"
