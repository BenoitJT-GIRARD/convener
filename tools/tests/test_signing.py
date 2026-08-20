from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from convener_ops.signing import (
    RSA_KEY_BITS,
    SECRET_NAME,
    TOKEN_FIELDS,
    WIRE_VERSION,
    SigningError,
    derive_public_pem,
    generate,
    public_key_path,
    sign,
    verify,
)

#: The shape a certificate payload actually takes (phase 4 spec §7):
#: identifier, event, name, date, duration -- and nothing else. Used
#: throughout this file instead of an arbitrary example dict, on purpose:
#: this module's own docstring asks whoever builds a real payload
#: (`certificate.py`, task 12) to keep exactly this discipline, and an
#: address slipped into a convenience fixture here would be the wrong
#: example to set. `test_the_shared_fixture_carries_no_address` pins it.
CERT_PAYLOAD: dict[str, Any] = {
    "identifier": "cert-2026-08-20-001",
    "event": "mrg-042",
    "name": "Élodie Fontâine",
    "date": "2026-08-20",
    "duration_hours": 2.5,
}


def test_the_shared_fixture_carries_no_address() -> None:
    """Guards the discipline every other test in this file relies on: if a
    future edit adds a convenience field to `CERT_PAYLOAD`, this is the
    test that should fail, not something a reader has to notice by eye."""
    assert set(CERT_PAYLOAD) == {
        "identifier",
        "event",
        "name",
        "date",
        "duration_hours",
    }


# ------------------------------------------------------------------ #
# The properties the whole design rests on.
# ------------------------------------------------------------------ #


def test_a_token_signed_with_the_private_half_verifies_with_the_public_half() -> None:
    private_pem, public_pem = generate()

    token = sign(CERT_PAYLOAD, private_pem)

    assert verify(token, [public_pem]) == CERT_PAYLOAD


def test_a_certificate_signed_by_a_retired_key_still_verifies() -> None:
    """Le test sur lequel repose toute la conception : la rotation ne doit
    jamais invalider un certificat deja emis.

    `retired_private` signs the token below and is never used again --
    exactly what "no longer in service" means. Its public half stays
    published (`retired_public`), alongside the public half of whatever key
    *is* now in service (`current_public`, generated but never used to sign
    anything here). `verify` is handed the list a real caller would build
    from `keys/signing/*.pub`, newest first (the current key, then the
    retired one) -- and still returns the payload, because the retired
    key's public half is *somewhere* in the list, which is the only thing
    correctness ever depended on.
    """
    retired_private, retired_public = generate()
    _current_private, current_public = generate()

    token = sign(CERT_PAYLOAD, retired_private)

    assert verify(token, [current_public, retired_public]) == CERT_PAYLOAD
    # Order is a recommendation, not a requirement -- the retired key
    # working even listed first proves this is not an accident of order.
    assert verify(token, [retired_public, current_public]) == CERT_PAYLOAD


def test_verifying_against_a_key_that_never_signed_the_token_fails() -> None:
    """Signer avec une cle, verifier avec une autre : l'echec est le point."""
    private_a, _public_a = generate()
    _private_b, public_b = generate()

    token = sign(CERT_PAYLOAD, private_a)

    assert verify(token, [public_b]) is None


def test_a_single_byte_changed_in_the_payload_fails_verification() -> None:
    """Changer un octet de la charge, et verifier l'echec."""
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)

    tampered_payload = dict(parsed["payload"])
    tampered_payload["identifier"] = tampered_payload["identifier"][:-1] + (
        "0" if tampered_payload["identifier"][-1] != "0" else "1"
    )
    tampered = json.dumps({**parsed, "payload": tampered_payload})

    assert verify(tampered, [public_pem]) is None
    # The untampered token still verifies with the same key -- this is a
    # property of the mutation, not of the key or of `verify` itself.
    assert verify(token, [public_pem]) == CERT_PAYLOAD


def test_a_tampered_signature_fails_verification() -> None:
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)

    signature = bytearray(base64.b64decode(parsed["signature"]))
    signature[-1] ^= 0x01
    tampered = json.dumps(
        {**parsed, "signature": base64.b64encode(bytes(signature)).decode("ascii")}
    )

    assert verify(tampered, [public_pem]) is None


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


def test_sign_lets_a_json_encoding_failure_pass_through_unwrapped() -> None:
    """Not a domain-specific failure mode -- a payload holding something
    `json.dumps` itself cannot serialise (a `date` object rather than an
    ISO string, here) is the caller's own mistake in what it built, and
    surfaces as whatever `json.dumps` raises rather than being translated
    into `SigningError`."""
    private_pem, _ = generate()
    bad_payload: dict[str, Any] = {**CERT_PAYLOAD, "date": date(2026, 8, 20)}

    with pytest.raises(TypeError):
        sign(bad_payload, private_pem)


# ------------------------------------------------------------------ #
# verify(): malformed input is refused, never garbled, never raised
# ------------------------------------------------------------------ #


def test_verify_returns_none_for_an_empty_key_list() -> None:
    """Not only a defensive edge case: `keys/signing/` genuinely holds no
    key at all until an operator generates the first one (see that
    directory's own README), so a caller that built `public_pems` from an
    empty directory listing must get this same clean refusal, never a
    crash and never a token accepted for want of anything to check it
    against."""
    private_pem, _ = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    assert verify(token, []) is None


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

    assert verify(token, [ec_public_pem, public_pem]) == CERT_PAYLOAD


def test_verify_skips_a_public_pem_that_will_not_even_load_and_keeps_trying() -> None:
    """A `public_pems` entry that is not valid PEM at all -- not even a key
    of the wrong kind, just garbage -- must be skipped the same way an
    EC key is, not raised through to the caller."""
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)

    assert verify(token, ["not a pem at all", public_pem]) == CERT_PAYLOAD


def test_verify_returns_none_for_a_token_that_is_not_json() -> None:
    _, public_pem = generate()
    assert verify("not json at all", [public_pem]) is None


def test_verify_returns_none_for_a_token_that_is_valid_json_but_not_an_object() -> None:
    _, public_pem = generate()
    assert verify("[1, 2, 3]", [public_pem]) is None


def test_verify_returns_none_for_a_token_missing_a_field() -> None:
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    del parsed["signature"]

    assert verify(json.dumps(parsed), [public_pem]) is None


def test_verify_returns_none_when_the_payload_is_not_an_object() -> None:
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    parsed["payload"] = ["not", "an", "object"]

    assert verify(json.dumps(parsed), [public_pem]) is None


def test_verify_returns_none_for_an_unknown_wire_format_version() -> None:
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    parsed["v"] = 2

    assert verify(json.dumps(parsed), [public_pem]) is None


def test_verify_returns_none_for_a_signature_that_is_not_valid_base64() -> None:
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    parsed["signature"] = "not base64!!"

    assert verify(json.dumps(parsed), [public_pem]) is None


def test_verify_does_not_care_about_json_formatting_or_outer_key_order() -> None:
    """`JSON.stringify` on a future browser-side verifier is not guaranteed
    to produce compact, insertion-ordered JSON the way `json.dumps(...,
    separators=...)` does here; decoding must not silently depend on
    either."""
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

    assert verify(reformatted, [public_pem]) == CERT_PAYLOAD


def test_verify_does_not_care_about_payload_key_order() -> None:
    """Canonicalisation (`sort_keys=True`) is what makes this hold even when
    the *payload*'s own key order differs from what `sign` originally
    produced -- not just the outer token's, which the test above already
    covers."""
    private_pem, public_pem = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)
    parsed["payload"] = dict(reversed(list(parsed["payload"].items())))

    assert verify(json.dumps(parsed), [public_pem]) == CERT_PAYLOAD


# ------------------------------------------------------------------ #
# The wire format: a cross-language contract, pinned by test
# ------------------------------------------------------------------ #


def test_wire_format_has_exactly_the_documented_fields() -> None:
    private_pem, _ = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    parsed = json.loads(token)

    assert set(parsed) == TOKEN_FIELDS
    assert parsed["v"] == WIRE_VERSION == 1
    assert parsed["payload"] == CERT_PAYLOAD
    assert len(base64.b64decode(parsed["signature"])) == RSA_KEY_BITS // 8


def test_the_token_is_pure_ascii() -> None:
    """The payload's accented name must not turn the signed bytes -- or the
    token that carries them -- non-ASCII; see the module docstring's "wire
    format" section."""
    private_pem, _ = generate()
    token = sign(CERT_PAYLOAD, private_pem)
    token.encode("ascii")  # raises UnicodeEncodeError if this is not pure ASCII
    assert "É" not in token
    assert "\\u00c9" in token  # the escaped "É" of "Élodie"


# ------------------------------------------------------------------ #
# public_key_path(): where the published half lives
# ------------------------------------------------------------------ #


def test_public_key_path_is_under_keys_signing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    assert public_key_path(date(2026, 8, 20)) == (
        tmp_path / "keys" / "signing" / "2026-08-20.pub"
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
