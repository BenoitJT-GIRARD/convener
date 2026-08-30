from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from convener_ops.journey.signing import (
    MALFORMED,
    MAX_TOKEN_BYTES,
    NO_MATCHING_KEY,
    PAYLOAD_FIELDS,
    RSA_KEY_BITS,
    SECRET_NAME,
    TOKEN_FIELDS,
    WIRE_VERSION,
    SigningError,
    VerifyResult,
    derive_public_pem,
    generate,
    public_key_path,
    sign,
    verify,
)

#: The shape a certificate payload actually takes:
#: identifier, event, name, date, duration -- and nothing else. Used
#: throughout this file instead of an arbitrary example dict, on purpose:
#: this module's own docstring asks whoever builds a real payload
#: (`certificate.py`) to keep exactly this discipline, and `sign`
#: itself now enforces it via `PAYLOAD_FIELDS` -- so an address slipped
#: into this fixture would fail every test in this file, not just the one
#: that used to guard it alone.
CERT_PAYLOAD: dict[str, Any] = {
    "identifier": "cert-2026-08-20-001",
    "event": "mrg-042",
    "name": "Élodie Fontâine",
    "date": "2026-08-20",
    "duration_hours": 2.5,
}


def _retoken_with_tampered_payload(token: str, **overrides: Any) -> str:
    """Rebuilds `token` with one or more payload fields changed, keeping
    the *original* signature untouched -- exactly what an attacker gets
    without the private key: a payload they can edit, and a signature that
    no longer matches it. Used by the parametrized tamper test below."""
    parsed = json.loads(token)
    canonical = json.loads(base64.b64decode(parsed["payload"]))
    canonical.update(overrides)
    tampered_bytes = json.dumps(
        canonical, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    tampered = dict(parsed)
    tampered["payload"] = base64.b64encode(tampered_bytes).decode("ascii")
    return json.dumps(tampered)


def test_the_shared_fixture_matches_the_enforced_payload_schema() -> None:
    assert set(CERT_PAYLOAD) == PAYLOAD_FIELDS


def test_the_two_reasons_keep_the_spelling_that_crosses_the_language_border() -> None:
    """Asserts the literal strings, not the constants -- and that is the
    whole point of the test.

    Every other assertion in this file compares `result.reason` against
    `MALFORMED` or `NO_MATCHING_KEY`, so it pins the *distinction* between
    the two outcomes but not the *spelling* of either. Swap the two
    constants' values and every one of those tests still passes: verified
    by mutation, and the reason this test exists.

    The verification page cannot import a Python constant. It
    compares whatever string reaches the browser against a literal of its
    own, and the two outcomes are displayed differently on purpose -- one
    says "we cannot confirm this", the other says "this is not a token".
    A silent drift here would make the page show the accusing message for
    the reassuring case, which is the single failure the tri-state was
    built to prevent. So the spellings are part of the contract, not an
    implementation detail, and they are pinned here (D-14) until the
    shared fixture binds both sides directly.
    """
    assert MALFORMED == "malformed"
    assert NO_MATCHING_KEY == "no_matching_key"


# ------------------------------------------------------------------ #
# The properties the whole design rests on.
# ------------------------------------------------------------------ #


def test_a_token_signed_with_the_private_half_verifies_with_the_public_half() -> None:
    private_pem, public_pem = generate()

    token = sign(CERT_PAYLOAD, private_pem)
    result = verify(token, [public_pem])

    assert result.valid
    assert result.payload == CERT_PAYLOAD
    assert result.reason is None


def test_a_certificate_signed_by_a_retired_key_still_verifies() -> None:
    """The test the whole design rests on: rotation must never invalidate
    a certificate already issued.

    `retired_private` signs the token below and is never used again --
    exactly what "no longer in service" means. Its public half stays
    published (`retired_public`), alongside the public half of whatever key
    *is* now in service (`current_public`, generated but never used to sign
    anything here). `verify` is handed the list a real caller would build
    from `instance/keys/signing/*.pub`, newest first (the current key, then the
    retired one) -- and still returns the payload, because the retired
    key's public half is *somewhere* in the list, which is the only thing
    correctness ever depended on.
    """
    retired_private, retired_public = generate()
    _current_private, current_public = generate()

    token = sign(CERT_PAYLOAD, retired_private)

    assert verify(token, [current_public, retired_public]).payload == CERT_PAYLOAD
    # Order is a recommendation, not a requirement -- the retired key
    # working even listed first proves this is not an accident of order.
    assert verify(token, [retired_public, current_public]).payload == CERT_PAYLOAD


def test_verifying_against_a_key_that_never_signed_the_token_fails() -> None:
    """Sign with one key, verify against another: the failure is the point."""
    private_a, _public_a = generate()
    _private_b, public_b = generate()

    token = sign(CERT_PAYLOAD, private_a)
    result = verify(token, [public_b])

    assert not result.valid
    assert result.reason == NO_MATCHING_KEY
    assert result.payload is None


@pytest.mark.parametrize("field", sorted(PAYLOAD_FIELDS))
def test_tampering_any_single_payload_field_fails_verification(field: str) -> None:
    """The finding this test exists to close: a mutant tree
    that dropped one field at a time from what actually gets signed found
    that only "identifier" was caught by this file's earlier, single-field
    tamper test -- "event", "name", "date" and "duration_hours" all
    survived, meaning the production code was correct (it signs the whole
    payload) but nothing in the suite actually held it there. This test
    tampers each of the five fields' *values* in turn and requires
    verification to fail for every one, not just one."""
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)

    tampered_value: Any = 999.0 if field == "duration_hours" else "TAMPERED"
    tampered = _retoken_with_tampered_payload(token, **{field: tampered_value})

    result = verify(tampered, [public_pem])

    assert not result.valid
    assert result.reason == NO_MATCHING_KEY
    assert result.payload is None


def test_a_tampered_signature_fails_verification() -> None:
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)

    signature = bytearray(base64.b64decode(parsed["signature"]))
    signature[-1] ^= 0x01
    tampered = json.dumps(
        {**parsed, "signature": base64.b64encode(bytes(signature)).decode("ascii")}
    )

    result = verify(tampered, [public_pem])

    assert not result.valid
    assert result.reason == NO_MATCHING_KEY


# ------------------------------------------------------------------ #
# The wire format: transports the signed bytes, never recomputes them.
# ------------------------------------------------------------------ #


def test_wire_format_transports_the_signed_bytes_not_a_nested_object() -> None:
    private_pem, _ = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)

    assert set(parsed) == TOKEN_FIELDS
    assert parsed["v"] == WIRE_VERSION == 1
    assert isinstance(parsed["payload"], str)  # base64, not a nested JSON object
    decoded = json.loads(base64.b64decode(parsed["payload"]))
    assert decoded == CERT_PAYLOAD
    assert len(base64.b64decode(parsed["signature"])) == RSA_KEY_BITS // 8


def test_verify_accepts_payload_bytes_in_any_valid_json_formatting() -> None:
    """Proves `verify` does not recompute or expect any specific
    canonicalisation -- it checks the signature against exactly the
    transported bytes, whatever their formatting, and only afterwards
    parses them for display. Signs an alternately-formatted (indented,
    unsorted-key) serialisation of the same payload directly, bypassing
    `sign`'s own `_canonical_bytes` call entirely, to prove no specific
    format is assumed anywhere in `verify`."""
    private_pem, public_pem = generate()
    alt_bytes = json.dumps(CERT_PAYLOAD, indent=2, sort_keys=False).encode("utf-8")
    key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    signature = key.sign(alt_bytes, padding.PKCS1v15(), hashes.SHA256())
    token = json.dumps(
        {
            "v": 1,
            "payload": base64.b64encode(alt_bytes).decode("ascii"),
            "signature": base64.b64encode(signature).decode("ascii"),
        }
    )

    result = verify(token, [public_pem])

    assert result.valid
    assert result.payload == CERT_PAYLOAD


def test_verify_does_not_care_about_outer_json_formatting_or_key_order() -> None:
    """`JSON.stringify` on a future browser-side verifier is not guaranteed
    to produce compact, insertion-ordered JSON the way `json.dumps(...,
    separators=...)` does here; decoding the *outer* token must not
    silently depend on either. (The inner `payload` bytes are transported
    verbatim and never reformatted at all -- see the test above.)"""
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    reordered = {
        "signature": parsed["signature"],
        "payload": parsed["payload"],
        "v": parsed["v"],
    }
    reformatted = json.dumps(reordered, indent=2)
    assert reformatted != token

    result = verify(reformatted, [public_pem])

    assert result.valid
    assert result.payload == CERT_PAYLOAD


def test_the_token_is_pure_ascii() -> None:
    """The payload's accented name must not turn the token non-ASCII; see
    the module docstring's "wire format" section. Base64 already guarantees
    this regardless of the inner JSON's own escaping choice -- pinned here
    directly rather than trusted by construction."""
    private_pem, _ = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    token.encode("ascii")  # raises UnicodeEncodeError if this is not pure ASCII


def test_the_accented_name_round_trips_through_the_base64_payload() -> None:
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)

    result = verify(token, [public_pem])

    assert result.payload is not None
    assert result.payload["name"] == "Élodie Fontâine"


# ------------------------------------------------------------------ #
# PAYLOAD_FIELDS: the certificate payload contract, enforced by `sign`.
# ------------------------------------------------------------------ #


def test_payload_fields_is_exactly_the_phase_4_certificate_schema() -> None:
    assert {"identifier", "event", "name", "date", "duration_hours"} == PAYLOAD_FIELDS
    assert "address" not in PAYLOAD_FIELDS
    assert "postal_address" not in PAYLOAD_FIELDS


def test_sign_rejects_a_payload_with_an_unexpected_field() -> None:
    private_pem, _ = generate()
    bad_payload = {**CERT_PAYLOAD, "address": "somewhere, never signed"}

    with pytest.raises(ValueError, match="unexpected"):
        sign(bad_payload, private_pem)


def test_sign_rejects_a_payload_with_two_unexpected_fields() -> None:
    """The exact scenario this refuses: a payload carrying both `address`
    and `postal_address` must not sign cleanly."""
    private_pem, _ = generate()
    bad_payload = {**CERT_PAYLOAD, "address": "x", "postal_address": "y"}

    with pytest.raises(ValueError, match="unexpected"):
        sign(bad_payload, private_pem)


def test_sign_rejects_a_payload_missing_a_required_field() -> None:
    private_pem, _ = generate()
    bad_payload = dict(CERT_PAYLOAD)
    del bad_payload["date"]

    with pytest.raises(ValueError, match="missing"):
        sign(bad_payload, private_pem)


def test_sign_checks_the_payload_shape_before_touching_the_private_key() -> None:
    """A malformed payload must be refused even when the private key handed
    to `sign` is itself unusable garbage -- proving the field check runs
    first. If key-loading ran first, this would raise `SigningError`
    instead of `ValueError`."""
    bad_payload = {**CERT_PAYLOAD, "address": "somewhere"}

    with pytest.raises(ValueError):
        sign(bad_payload, "not a key at all")


def test_sign_lets_a_json_encoding_failure_pass_through_unwrapped() -> None:
    """Not a domain-specific failure mode -- `PAYLOAD_FIELDS` pins the key
    *set*, not each value's type, so a payload holding something
    `json.dumps` itself cannot serialise (a `date` object rather than an
    ISO string, here) still passes the field check and reaches
    `_canonical_bytes`. That is the caller's own mistake in what it built,
    and surfaces as whatever `json.dumps` raises rather than being
    translated into `SigningError` or any error this module defines."""
    private_pem, _ = generate()
    bad_payload: dict[str, Any] = {**CERT_PAYLOAD, "date": date(2026, 8, 20)}

    with pytest.raises(TypeError):
        sign(bad_payload, private_pem)


# ------------------------------------------------------------------ #
# generate(): supporting properties
# ------------------------------------------------------------------ #


def test_generate_returns_private_then_public_as_distinct_pem_blocks() -> None:
    private_pem, public_pem = generate()
    assert private_pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert public_pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert private_pem != public_pem


def test_generate_produces_a_fresh_pair_every_call() -> None:
    first_private, _ = generate()
    second_private, _ = generate()
    assert first_private != second_private


def test_generate_uses_the_documented_key_size() -> None:
    private_pem, _ = generate()
    key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    assert key.key_size == RSA_KEY_BITS == 3072


# ------------------------------------------------------------------ #
# derive_public_pem(): the public half, re-derived rather than read from a
# committed file.
# ------------------------------------------------------------------ #


def test_derive_public_pem_matches_the_pair_generate_produced() -> None:
    private_pem, public_pem = generate()
    assert derive_public_pem(private_pem) == public_pem


def test_derive_public_pem_rejects_a_public_pem_passed_as_the_private_key() -> None:
    _, public_pem = generate()
    with pytest.raises(SigningError):
        derive_public_pem(public_pem)


def test_derive_public_pem_rejects_a_private_key_of_the_wrong_kind() -> None:
    ec_key = ec.generate_private_key(ec.SECP256R1())
    ec_pem = ec_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    with pytest.raises(SigningError):
        derive_public_pem(ec_pem)


# ------------------------------------------------------------------ #
# sign(): rejects an unusable private key rather than guessing
# ------------------------------------------------------------------ #


def test_sign_rejects_a_public_pem_passed_as_the_private_key() -> None:
    _, public_pem = generate()
    with pytest.raises(SigningError):
        sign(CERT_PAYLOAD, public_pem)


def test_sign_rejects_an_empty_private_key() -> None:
    with pytest.raises(SigningError):
        sign(CERT_PAYLOAD, "")


def test_sign_rejects_a_private_key_of_the_wrong_kind() -> None:
    """Not every PEM-encoded private key is RSA. An EC key loads as a valid
    private key, just not one this module can use to sign -- refused all
    the same."""
    ec_key = ec.generate_private_key(ec.SECP256R1())
    ec_pem = ec_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    with pytest.raises(SigningError):
        sign(CERT_PAYLOAD, ec_pem)


# ------------------------------------------------------------------ #
# verify(): three outcomes, never an exception -- malformed input is
# refused, never garbled, never raised.
# ------------------------------------------------------------------ #


def test_verify_returns_no_matching_key_for_an_empty_key_list() -> None:
    """Not only a defensive edge case: `instance/keys/signing/` genuinely holds no
    key at all until an operator generates the first one (see that
    directory's own README), so a caller that built `public_pems` from an
    empty directory listing must get this same honest "cannot confirm"
    outcome, never a crash and never a token accepted for want of anything
    to check it against."""
    private_pem, _ = generate()
    token = sign(CERT_PAYLOAD, private_pem)

    result = verify(token, [])

    assert not result.valid
    assert result.reason == NO_MATCHING_KEY
    assert result.payload is None


def test_verify_skips_an_unusable_key_and_keeps_trying_the_rest() -> None:
    """A `public_pems` entry that will not even load as an RSA public key
    (an EC key here) must not stop `verify` from trying the ones after it --
    the exact tolerance a rotated-key verifier depends on when one entry in
    its list is, for whatever reason, unusable."""
    private_pem, public_pem = generate()
    ec_key = ec.generate_private_key(ec.SECP256R1())
    ec_public_pem = (
        ec_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    token = sign(CERT_PAYLOAD, private_pem)

    result = verify(token, [ec_public_pem, public_pem])

    assert result.valid
    assert result.payload == CERT_PAYLOAD


def test_verify_skips_a_public_pem_that_will_not_even_load_and_keeps_trying() -> None:
    """A `public_pems` entry that is not valid PEM at all -- not even a key
    of the wrong kind, just garbage -- must be skipped the same way an
    EC key is, not raised through to the caller."""
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)

    result = verify(token, ["not a pem at all", public_pem])

    assert result.valid
    assert result.payload == CERT_PAYLOAD


def test_verify_returns_malformed_for_a_token_that_is_not_json() -> None:
    _, public_pem = generate()
    result = verify("not json at all", [public_pem])
    assert result.reason == MALFORMED
    assert result.payload is None


def test_verify_returns_malformed_when_json_but_not_an_object() -> None:
    _, public_pem = generate()
    result = verify("[1, 2, 3]", [public_pem])
    assert result.reason == MALFORMED


def test_verify_returns_malformed_for_a_token_missing_a_field() -> None:
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    del parsed["signature"]

    result = verify(json.dumps(parsed), [public_pem])

    assert result.reason == MALFORMED


def test_verify_returns_no_matching_key_when_a_tampered_payload_is_not_an_object() -> (
    None
):
    """Swapping in a payload that will not even parse
    as a JSON object, while leaving the *original* signature untouched,
    used to return `MALFORMED` -- because `verify` parsed the payload
    before checking any key. Now the signature check runs first, and this
    tampered payload's bytes do not match the signature at all (it was
    computed over the real `CERT_PAYLOAD` bytes, not `[1, 2, 3]`), so no
    key in `public_pems` ever confirms it: `NO_MATCHING_KEY`, the same
    outcome any other tampered-but-unsigned payload gets. `verify` never
    learns this payload is not an object, because it never gets far enough
    to look."""
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    not_an_object = base64.b64encode(b"[1, 2, 3]").decode("ascii")
    parsed["payload"] = not_an_object

    result = verify(json.dumps(parsed), [public_pem])

    assert result.reason == NO_MATCHING_KEY
    assert result.payload is None


def test_verify_returns_no_matching_key_when_a_tampered_payload_is_not_json() -> None:
    """Same reasoning as the test above, for payload
    bytes that are not JSON at all rather than JSON-but-not-an-object. The
    original signature does not match these substituted bytes, so
    `verify`'s signature loop rejects it as `NO_MATCHING_KEY` before ever
    attempting to parse it -- it used to return `MALFORMED` only because
    the old code parsed first and checked signatures second."""
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    parsed["payload"] = base64.b64encode(b"not json at all").decode("ascii")

    result = verify(json.dumps(parsed), [public_pem])

    assert result.reason == NO_MATCHING_KEY
    assert result.payload is None


def test_verify_returns_malformed_when_a_signed_payload_is_not_json_at_all() -> None:
    """The genuine, post-reorder `MALFORMED` case: bytes that a key in
    `public_pems` really did sign (the signature is computed directly over
    these exact bytes, bypassing `sign`'s own JSON-producing
    `_canonical_bytes`), but that are not JSON at all. This can only arise
    from our own signing mistake -- `sign` never hands RSA anything but
    JSON-encoded bytes -- which is exactly why it is `MALFORMED` rather
    than `NO_MATCHING_KEY`: a key did confirm these bytes, and we still
    cannot read them."""
    private_pem, public_pem = generate()
    key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    canonical = b"not json at all"
    signature = key.sign(canonical, padding.PKCS1v15(), hashes.SHA256())
    token = json.dumps(
        {
            "v": 1,
            "payload": base64.b64encode(canonical).decode("ascii"),
            "signature": base64.b64encode(signature).decode("ascii"),
        }
    )

    result = verify(token, [public_pem])

    assert result.reason == MALFORMED
    assert result.payload is None


def test_verify_returns_malformed_when_a_signed_payload_is_not_an_object() -> None:
    """The other half of the genuine `MALFORMED` case above: the signed
    bytes are valid JSON, just not an object -- still our own mistake, not
    a forger's, and still confirmed by a real signature before `verify`
    ever looks at what it says."""
    private_pem, public_pem = generate()
    key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    canonical = b"[1, 2, 3]"
    signature = key.sign(canonical, padding.PKCS1v15(), hashes.SHA256())
    token = json.dumps(
        {
            "v": 1,
            "payload": base64.b64encode(canonical).decode("ascii"),
            "signature": base64.b64encode(signature).decode("ascii"),
        }
    )

    result = verify(token, [public_pem])

    assert result.reason == MALFORMED
    assert result.payload is None


def test_verify_returns_malformed_for_an_unknown_wire_format_version() -> None:
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    parsed["v"] = 2

    result = verify(json.dumps(parsed), [public_pem])

    assert result.reason == MALFORMED


def test_verify_returns_malformed_for_a_payload_field_that_is_not_valid_base64() -> (
    None
):
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    parsed["payload"] = "not base64!!"

    result = verify(json.dumps(parsed), [public_pem])

    assert result.reason == MALFORMED


def test_verify_returns_malformed_for_a_signature_that_is_not_valid_base64() -> None:
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    parsed["signature"] = "not base64!!"

    result = verify(json.dumps(parsed), [public_pem])

    assert result.reason == MALFORMED


# ------------------------------------------------------------------ #
# verify(): never raises, even for hostile input.
# ------------------------------------------------------------------ #


def test_verify_rejects_a_token_larger_than_the_size_cap_without_parsing_it() -> None:
    huge = "x" * (MAX_TOKEN_BYTES + 1)

    result = verify(huge, [])

    assert result.reason == MALFORMED


def test_verify_refuses_deeply_nested_json_without_raising() -> None:
    """A short token can still exhaust Python's json decoder's recursion
    depth well under any reasonable size cap: nesting the attack directly
    in the *outer* token (in place of the `payload` string) skips the
    base64 expansion that would otherwise dilute the byte-to-depth ratio,
    so `MAX_TOKEN_BYTES` alone does not defend against this. `verify` must
    catch `RecursionError` itself, not let it escape as an exception --
    a public verification page must never crash because someone pasted an
    adversarial string into it."""
    depth = 3000
    nested = "[" * depth + "]" * depth
    hostile = '{"v":1,"payload":' + nested + ',"signature":"x"}'
    assert len(hostile.encode("utf-8")) < MAX_TOKEN_BYTES

    result = verify(hostile, [])

    assert result.reason == MALFORMED


# ------------------------------------------------------------------ #
# VerifyResult: the tri-state contract itself
# ------------------------------------------------------------------ #


def test_verify_result_valid_property_reflects_reason() -> None:
    assert VerifyResult(payload={"a": 1}, reason=None).valid is True
    assert VerifyResult(payload=None, reason=MALFORMED).valid is False
    assert VerifyResult(payload=None, reason=NO_MATCHING_KEY).valid is False


def test_malformed_and_no_matching_key_are_distinct_reasons() -> None:
    """The two failure outcomes must never collapse into one -- that is the
    entire point. Garbage input and a
    well-formed-but-unconfirmable token must be told apart."""
    _, public_pem = generate()
    garbage = verify("not json at all", [public_pem])

    private_pem, _ = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    unconfirmable = verify(token, [])  # well-formed, but no key offered

    assert garbage.reason == MALFORMED
    assert unconfirmable.reason == NO_MATCHING_KEY
    assert garbage.reason != unconfirmable.reason


# ------------------------------------------------------------------ #
# public_key_path(): where the published half lives
# ------------------------------------------------------------------ #


def test_public_key_path_is_under_keys_signing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    assert public_key_path(date(2026, 8, 20)) == (
        tmp_path / "instance" / "keys" / "signing" / "2026-08-20.pub"
    )


def test_public_key_path_names_are_lexicographically_sortable_by_age(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The "newest first" convention the module docstring recommends to a
    verifier only works because the filenames sort the same way the dates
    do -- pinned here directly rather than trusted by construction."""
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    older = public_key_path(date(2026, 1, 1)).name
    newer = public_key_path(date(2026, 8, 20)).name
    assert sorted([older, newer]) == [older, newer]
    assert sorted([older, newer], reverse=True) == [newer, older]


# ------------------------------------------------------------------ #
# SECRET_NAME: the fixed secret this module documents, not a pattern
# ------------------------------------------------------------------ #


def test_secret_name_is_a_single_fixed_name_not_a_pattern() -> None:
    """Unlike `eventkeys.secret_name(event_id)`, there is exactly one
    signing key in service at a time -- so this is a constant, not a
    function. Pinned so a reader does not have to infer it from
    `config/integrations.yml` alone."""
    assert SECRET_NAME == "CONVENER_SIGNING_KEY"
