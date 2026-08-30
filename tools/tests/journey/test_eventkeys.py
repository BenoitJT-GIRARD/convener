from __future__ import annotations

import base64
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from secrets import token_bytes as _real_token_bytes
from typing import Any

import pytest
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from convener_ops.journey import eventkeys
from convener_ops.journey.eventkeys import (
    ACTIVE,
    DESTROYED,
    ENVELOPE_FIELDS,
    GCM_NONCE_BYTES,
    NEVER_CREATED,
    RSA_KEY_BITS,
    WIRE_VERSION,
    DecryptionError,
    DestructionRecord,
    decrypt,
    derive_public_pem,
    destroy,
    encrypt,
    generate,
    key_status,
    public_key_path,
    secret_name,
)

#: A legal GitHub Actions secret name, end to end: `[A-Za-z_][A-Za-z0-9_]*`.
_LEGAL_SECRET_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ------------------------------------------------------------------ #
# The four tests that matter here -- the second is the one the whole
# design rests on.
# ------------------------------------------------------------------ #


def test_a_payload_encrypted_with_the_public_half_is_read_by_the_private_half() -> None:
    private_pem, public_pem = generate()
    plaintext = b'{"name": "a registrant, never committed"}'

    ciphertext = encrypt(public_pem, plaintext)

    assert decrypt(private_pem, ciphertext) == plaintext


def test_the_public_half_alone_cannot_decrypt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The property everything else rests on: the browser, which holds
    only the published half, cannot read back what it encrypted.

    Not "decrypt() raises when handed the public PEM" -- that is a type
    check that never reaches any cryptography. The property that actually
    matters is that the envelope `encrypt` hands back carries nothing a
    holder of only the public half could use: no extra field, and no trace
    of the plaintext or of the throwaway AES key that sealed it.
    """
    aes_keys_drawn: list[bytes] = []

    def spy(count: int) -> bytes:
        drawn = _real_token_bytes(count)
        if count == eventkeys.AES_KEY_BYTES:
            aes_keys_drawn.append(drawn)
        return drawn

    monkeypatch.setattr("convener_ops.journey.eventkeys.token_bytes", spy)

    _, public_pem = generate()
    plaintext = b'{"email": "a registrant, never committed"}'

    ciphertext = encrypt(public_pem, plaintext)

    assert len(aes_keys_drawn) == 1
    aes_key = aes_keys_drawn[0]
    envelope = json.loads(ciphertext)

    # The wire format's entire vocabulary -- nothing else is on offer for a
    # holder of only the public half to read, decode or brute-force from.
    # A mutant that smuggles the AES key out as an extra field is caught
    # right here.
    assert set(envelope) == {"v", "encrypted_key", "iv", "ciphertext"}
    # Neither the plaintext nor the raw AES key appears anywhere in the
    # envelope, encoded or not -- catches a mutant that hides the key
    # inside an existing field instead of adding a new one.
    assert b"registrant" not in ciphertext.encode("ascii")
    assert base64.b64encode(aes_key).decode("ascii") not in ciphertext
    assert aes_key.hex() not in ciphertext


def test_decrypt_refuses_a_public_pem_passed_as_the_private_key() -> None:
    """A type check, not the confidentiality property above: this never
    reaches any ciphertext data, because a public PEM is not a private key
    PEM at all."""
    _, public_pem = generate()
    ciphertext = encrypt(public_pem, b"a registration")

    with pytest.raises(DecryptionError):
        decrypt(public_pem, ciphertext)


def test_a_ciphertext_from_another_event_does_not_decrypt() -> None:
    """A key per event is only a key per event if it cannot read the
    others."""
    private_b, _ = generate()
    _, public_a = generate()
    ciphertext = encrypt(public_a, b"event a's registration")

    with pytest.raises(DecryptionError):
        decrypt(private_b, ciphertext)


def _with_ciphertext_field(envelope: dict[str, Any], body: bytes) -> str:
    updated = dict(envelope)
    updated["ciphertext"] = base64.b64encode(body).decode("ascii")
    return json.dumps(updated)


def test_a_truncated_or_tampered_ciphertext_is_refused_not_returned_garbled() -> None:
    """Both mutations act on the decoded AES-GCM body itself -- the bytes
    behind the envelope's `ciphertext` field -- not on the surrounding JSON,
    so both are refused by the GCM authentication tag rather than by
    `json.loads` failing to parse first."""
    private_pem, public_pem = generate()
    ciphertext = encrypt(public_pem, b"a registration")
    envelope = json.loads(ciphertext)
    body = base64.b64decode(envelope["ciphertext"])
    assert len(body) >= 16  # the 16-byte GCM tag alone, plus at least 1 byte

    # Truncated: drop the body's last byte, inside the 16-byte tag.
    truncated = _with_ciphertext_field(envelope, body[:-1])
    with pytest.raises(DecryptionError):
        decrypt(private_pem, truncated)

    # Tampered: flip one bit inside the tag itself. The structure still
    # parses and RSA-OAEP still recovers the AES key -- only AES-GCM's own
    # authentication check can catch this one.
    tampered_body = bytearray(body)
    tampered_body[-1] ^= 0x01
    tampered = _with_ciphertext_field(envelope, bytes(tampered_body))
    with pytest.raises(DecryptionError):
        decrypt(private_pem, tampered)


# ------------------------------------------------------------------ #
# generate() and encrypt(): supporting properties
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


def test_encrypt_draws_a_fresh_nonce_every_call() -> None:
    """A reused nonce under the same AES-GCM key breaks both confidentiality
    and authenticity outright, so this checks the nonce field itself rather
    than a proxy for it (the previous version of this test compared whole
    envelopes, which stayed different from the fresh AES key alone -- a
    mutant with a hard-coded, constant nonce passed it)."""
    _, public_pem = generate()
    first = json.loads(encrypt(public_pem, b"same payload"))
    second = json.loads(encrypt(public_pem, b"same payload"))

    assert first["iv"] != second["iv"]
    for envelope in (first, second):
        assert len(base64.b64decode(envelope["iv"])) == GCM_NONCE_BYTES


def test_encrypt_handles_a_payload_far_larger_than_one_rsa_block() -> None:
    """The reason for the hybrid scheme: RSA-OAEP alone could not carry this."""
    private_pem, public_pem = generate()
    plaintext = b"x" * 5000

    ciphertext = encrypt(public_pem, plaintext)

    assert decrypt(private_pem, ciphertext) == plaintext


def test_encrypt_handles_an_empty_payload() -> None:
    private_pem, public_pem = generate()

    ciphertext = encrypt(public_pem, b"")

    assert decrypt(private_pem, ciphertext) == b""


# ------------------------------------------------------------------ #
# The wire format: a cross-language contract, pinned by test
# ------------------------------------------------------------------ #


def test_wire_format_has_exactly_the_documented_fields_and_lengths() -> None:
    _, public_pem = generate()

    envelope = json.loads(encrypt(public_pem, b"a registration"))

    assert set(envelope) == {"v", "encrypted_key", "iv", "ciphertext"}
    assert envelope["v"] == WIRE_VERSION == 1
    assert len(base64.b64decode(envelope["encrypted_key"])) == RSA_KEY_BITS // 8
    assert len(base64.b64decode(envelope["iv"])) == GCM_NONCE_BYTES


def test_decrypt_does_not_care_about_json_formatting_or_key_order() -> None:
    """`JSON.stringify` on the browser side is not guaranteed to produce
    compact, insertion-ordered JSON the way `json.dumps(...,
    separators=...)` does here; decoding must not silently depend on
    either."""
    private_pem, public_pem = generate()
    envelope = json.loads(encrypt(public_pem, b"a registration"))
    reordered = {
        "ciphertext": envelope["ciphertext"],
        "iv": envelope["iv"],
        "v": envelope["v"],
        "encrypted_key": envelope["encrypted_key"],
    }
    reformatted = json.dumps(reordered, indent=2)
    assert reformatted != json.dumps(envelope, separators=(",", ":"))

    assert decrypt(private_pem, reformatted) == b"a registration"


def test_decrypt_rejects_an_unknown_wire_format_version() -> None:
    private_pem, public_pem = generate()
    envelope = json.loads(encrypt(public_pem, b"a registration"))
    envelope["v"] = 2

    with pytest.raises(DecryptionError):
        decrypt(private_pem, json.dumps(envelope))


# ------------------------------------------------------------------ #
# decrypt(): malformed input is refused, never garbled
# ------------------------------------------------------------------ #


def test_decrypt_rejects_ciphertext_that_is_not_json() -> None:
    private_pem, _ = generate()
    with pytest.raises(DecryptionError):
        decrypt(private_pem, "not json at all")


def test_decrypt_rejects_a_ciphertext_missing_a_field() -> None:
    private_pem, public_pem = generate()
    ciphertext = encrypt(public_pem, b"a registration")
    # Drop the "iv" field entirely rather than corrupt a byte, to exercise
    # the structural check separately from the cryptographic one.
    envelope = json.loads(ciphertext)
    del envelope["iv"]
    broken = json.dumps(envelope)

    with pytest.raises(DecryptionError):
        decrypt(private_pem, broken)


def test_decrypt_rejects_an_empty_private_key() -> None:
    _, public_pem = generate()
    ciphertext = encrypt(public_pem, b"a registration")

    with pytest.raises(DecryptionError):
        decrypt("", ciphertext)


def test_decrypt_rejects_a_ciphertext_that_is_valid_json_but_not_an_object() -> None:
    private_pem, _ = generate()
    with pytest.raises(DecryptionError):
        decrypt(private_pem, "[1, 2, 3]")


def test_decrypt_rejects_a_private_key_of_the_wrong_kind() -> None:
    """Not every PEM-encoded private key is RSA. An EC key loads as a valid
    private key, just not one `decrypt` can use -- refused all the same."""
    ec_key = ec.generate_private_key(ec.SECP256R1())
    ec_pem = ec_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    _, public_pem = generate()
    ciphertext = encrypt(public_pem, b"a registration")

    with pytest.raises(DecryptionError):
        decrypt(ec_pem, ciphertext)


def test_decrypt_converts_unsupported_algorithm_to_decryption_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`UnsupportedAlgorithm` is a real failure mode of
    `load_pem_private_key` (an exotic or partially-supported key type), but
    triggering it authentically depends on backend/OpenSSL build details
    that are impractical to construct portably in a test. This pins the
    module's own conversion contract directly instead: whatever the cause,
    it must not escape `decrypt` as itself."""
    calls = {"count": 0}

    def raise_unsupported(*_args: object, **_kwargs: object) -> None:
        calls["count"] += 1
        raise UnsupportedAlgorithm("not supported")

    monkeypatch.setattr(
        "convener_ops.journey.eventkeys.serialization.load_pem_private_key",
        raise_unsupported,
    )
    _, public_pem = generate()
    ciphertext = encrypt(public_pem, b"a registration")

    with pytest.raises(DecryptionError):
        decrypt("does-not-matter", ciphertext)
    assert calls["count"] == 1


def test_encrypt_rejects_a_public_key_of_the_wrong_kind() -> None:
    ec_key = ec.generate_private_key(ec.SECP256R1())
    ec_public_pem = (
        ec_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )

    with pytest.raises(ValueError, match="RSA"):
        encrypt(ec_public_pem, b"a registration")


# ------------------------------------------------------------------ #
# derive_public_pem(): the public half, re-derived rather than read from a
# file -- so a re-encryption never depends on what is (or is not) committed
# at instance/keys/events/<id>.pub.
# ------------------------------------------------------------------ #


def test_derive_public_pem_matches_the_pair_generate_produced() -> None:
    private_pem, public_pem = generate()
    assert derive_public_pem(private_pem) == public_pem


def test_derive_public_pem_lets_the_original_public_half_decrypt_nothing_new() -> None:
    """Not a new property -- `encrypt`/`decrypt` already prove the pair
    works -- but pinned here as the direct round trip through the derived
    key specifically, since that is the key `registration.py::upsert`
    actually encrypts under."""
    private_pem, _ = generate()
    derived_public_pem = derive_public_pem(private_pem)

    ciphertext = encrypt(derived_public_pem, b"a registration")

    assert decrypt(private_pem, ciphertext) == b"a registration"


def test_derive_public_pem_rejects_a_public_pem_passed_as_the_private_key() -> None:
    _, public_pem = generate()
    with pytest.raises(DecryptionError):
        derive_public_pem(public_pem)


def test_derive_public_pem_rejects_a_private_key_of_the_wrong_kind() -> None:
    ec_key = ec.generate_private_key(ec.SECP256R1())
    ec_pem = ec_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    with pytest.raises(DecryptionError):
        derive_public_pem(ec_pem)


# ------------------------------------------------------------------ #
# ENVELOPE_FIELDS: the one definition of "this dict is ciphertext"
# ------------------------------------------------------------------ #


def test_envelope_fields_matches_what_encrypt_actually_produces() -> None:
    _, public_pem = generate()
    envelope = json.loads(encrypt(public_pem, b"a registration"))
    assert set(envelope) == ENVELOPE_FIELDS


# ------------------------------------------------------------------ #
# public_key_path(): where the published half lives
# ------------------------------------------------------------------ #


def test_public_key_path_is_under_keys_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    assert (
        public_key_path("mrg-042")
        == tmp_path / "instance" / "keys" / "events" / "mrg-042.pub"
    )


@pytest.mark.parametrize(
    "bad_id", ["", "../escape", "vw 042", "vw/042", ".hidden", "vw|042"]
)
def test_public_key_path_rejects_an_id_that_is_not_a_plain_token(
    bad_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="event id"):
        public_key_path(bad_id)


# ------------------------------------------------------------------ #
# secret_name(): the id-to-secret-suffix transform
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    "event_id", ["mrg-042", "mrg.042", "vw2026", "a", "MRG-Autumn.2026"]
)
def test_secret_name_is_always_a_legal_github_actions_secret_name(
    event_id: str,
) -> None:
    """Every id `_EVENT_ID_RE` admits -- including the tests' own canonical
    `mrg-042`, which uppercasing alone does not make legal -- must produce a
    name GitHub Actions will actually accept."""
    assert _LEGAL_SECRET_NAME.fullmatch(secret_name(event_id))


def test_secret_name_uppercases_and_folds_dots_and_hyphens_to_underscore() -> None:
    assert secret_name("mrg-042") == "CONVENER_EVENT_KEY_MRG_042"
    assert secret_name("vw2026") == "CONVENER_EVENT_KEY_VW2026"


def test_secret_name_is_lossy_dot_and_hyphen_collide() -> None:
    """Documented, not hidden: the transform folds both '.' and '-' to '_',
    so two distinct, individually valid event ids can land on the same
    secret name. See `secret_name`'s docstring for why this is an
    operational constraint rather than something the function can detect."""
    assert secret_name("mrg-042") == secret_name("mrg.042")


def test_secret_name_rejects_an_invalid_event_id() -> None:
    with pytest.raises(ValueError, match="event id"):
        secret_name("../escape")


def test_secret_name_accepts_an_event_id_at_the_length_cap() -> None:
    """`_EVENT_ID_MAX_LENGTH` is 64, matching
    `services/signup-relay/src/index.js::EVENT_ID_RE`'s own cap -- see
    `_EVENT_ID_RE`'s own comment. Exactly at the boundary must still be
    accepted; over it must not (below)."""
    event_id = "a" * 64
    assert secret_name(event_id) == "CONVENER_EVENT_KEY_" + "A" * 64


def test_secret_name_rejects_an_event_id_over_the_length_cap() -> None:
    """A 65-character id is exactly the shape
    `services/signup-relay/src/index.js::EVENT_ID_RE` already refuses with
    a bare 400 -- before this fix, `secret_name` accepted it, so an id
    this long could be published as `instance/keys/events/<id>.pub` and be
    unusable at the one place a participant would ever submit against
    it."""
    event_id = "a" * 65
    with pytest.raises(ValueError, match="event id"):
        secret_name(event_id)


# ------------------------------------------------------------------ #
# key_status() and destroy(): pure, and the three states they must tell
# apart.
# ------------------------------------------------------------------ #


def test_key_status_is_never_created_with_no_key_and_no_registry_entry() -> None:
    assert key_status("mrg-042", key_was_published=False, registry={}) == NEVER_CREATED


def test_key_status_is_active_once_the_public_key_is_published() -> None:
    assert key_status("mrg-042", key_was_published=True, registry={}) == ACTIVE


def test_key_status_is_destroyed_once_the_registry_says_so() -> None:
    registry = {"mrg-042": date(2026, 8, 20)}
    # key_was_published is False here on purpose: the public file staying in
    # git after destruction (only the private half is gone) is exactly what
    # a real destroyed event looks like, but the registry entry alone must
    # already be enough to answer "destroyed".
    status = key_status("mrg-042", key_was_published=False, registry=registry)
    assert status == DESTROYED


def test_destroy_raises_for_a_key_that_was_never_created() -> None:
    """Distinguishing "destroyed" from "never created" starts here: this must
    not be the operation that quietly manufactures a destroyed record for an
    event whose key never existed."""
    now = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="never created"):
        destroy("mrg-042", now, key_was_published=False, registry={})


def test_destroy_returns_the_event_id_and_todays_paris_date() -> None:
    # 23:30 UTC on the 19th is already the 20th in Paris (UTC+2 in August).
    now = datetime(2026, 8, 19, 23, 30, tzinfo=UTC)
    record = destroy("mrg-042", now, key_was_published=True, registry={})
    expected = DestructionRecord(event_id="mrg-042", destroyed_on=date(2026, 8, 20))
    assert record == expected


def test_destroy_is_idempotent_on_an_already_destroyed_event() -> None:
    """A retention job that reruns after a partial failure must be able to
    call this again without minting a second record."""
    much_later = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    registry = {"mrg-042": date(2026, 8, 20)}

    record = destroy("mrg-042", much_later, key_was_published=True, registry=registry)

    expected = DestructionRecord(event_id="mrg-042", destroyed_on=date(2026, 8, 20))
    assert record == expected


# ------------------------------------------------------------------ #
# D-14: what the browser encrypts, this module must be able to decrypt.
# `tools/tests/fixtures/governance-cases.json::event_registration_encryption`
# is the shared contract -- see its own `_event_registration_encryption_comment`
# for how the fixture was built. `app/tests/signup-encrypt.test.ts` reads the
# same cases on the other side.
# ------------------------------------------------------------------ #

_FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "governance-cases.json"
_FIXTURE = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))[
    "event_registration_encryption"
]


def test_the_shared_encryption_fixture_still_has_cases() -> None:
    """Guards the fixture itself: an emptied `cases` list would let the
    parametrized test below collect zero tests and still exit green, which
    is exactly the silent loss D-14 exists to prevent."""
    assert len(_FIXTURE["cases"]) > 0


@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=lambda c: c["name"])
def test_a_browser_encrypted_envelope_from_the_shared_fixture_decrypts_here(
    case: dict[str, Any],
) -> None:
    """`case["envelope"]` is not built by this test, or by anything in this
    module: it is the literal, captured output of the real `encryptRegistration`
    in `app/src/signup/encrypt.ts`, run once under Node's own `crypto.subtle`.
    Decrypting it here with the fixture's `private_pem`, through the real
    `decrypt`, is the one place that proves a browser-encrypted registration
    is actually readable by the job that has to read it -- not merely that
    both languages pass their own, separately-written tests."""
    plaintext = decrypt(_FIXTURE["private_pem"], case["envelope"])
    assert json.loads(plaintext) == case["fields"]
