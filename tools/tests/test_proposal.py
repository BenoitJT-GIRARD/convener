from __future__ import annotations

from conftest import speaker

from convener_ops.proposal import to_lead, verify_signature


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
    lead = to_lead(fields, existing)
    assert lead is not None
    assert lead["id"] == "spk-008"


def test_a_submission_matching_a_lead_by_email_is_ignored_as_duplicate() -> None:
    existing = [speaker(id="spk-001", email="grace@example.org", status="lead")]
    fields = _fields(("Name", "Grace Hopper"), ("Email", "grace@example.org"))
    assert to_lead(fields, existing) is None


def test_a_submission_with_an_empty_name_is_ignored() -> None:
    fields = _fields(("Name", ""), ("Email", "grace@example.org"))
    assert to_lead(fields, []) is None


def test_an_unrecognised_gender_falls_back_to_undisclosed() -> None:
    fields = _fields(("Name", "Grace Hopper"), ("Gender", "not-a-gender"))
    lead = to_lead(fields, [])
    assert lead is not None
    assert lead["gender"] == "undisclosed"


def test_a_comma_separated_links_string_becomes_a_stripped_list() -> None:
    fields = _fields(
        ("Name", "Grace Hopper"), ("Links", " a@example.org , , b@example.org ")
    )
    lead = to_lead(fields, [])
    assert lead is not None
    assert lead["links"] == ["a@example.org", "b@example.org"]
