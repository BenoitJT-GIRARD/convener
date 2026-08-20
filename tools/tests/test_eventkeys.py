from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from convener_ops.eventkeys import (
    ACTIVE,
    DESTROYED,
    NEVER_CREATED,
    DecryptionError,
    DestructionRecord,
    decrypt,
    destroy,
    encrypt,
    generate,
    key_status,
    public_key_path,
)

# ------------------------------------------------------------------ #
# The four tests the brief names -- the second is the one the whole
# design rests on.
# ------------------------------------------------------------------ #


def test_a_payload_encrypted_with_the_public_half_is_read_by_the_private_half() -> None:
    private_pem, public_pem = generate()
    plaintext = b'{"name": "a registrant, never committed"}'

    ciphertext = encrypt(public_pem, plaintext)

    assert decrypt(private_pem, ciphertext) == plaintext


def test_the_public_half_alone_cannot_decrypt() -> None:
    """C'est la propriete sur laquelle repose tout le reste : le navigateur, qui
    ne detient que la moitie publiee, ne peut pas relire ce qu'il a chiffre."""
    _, public_pem = generate()
    ciphertext = encrypt(public_pem, b"a registration")

    with pytest.raises(DecryptionError):
        decrypt(public_pem, ciphertext)


def test_a_ciphertext_from_another_event_does_not_decrypt() -> None:
    """Une cle par evenement n'est une cle par evenement que si elle ne lit pas
    les autres."""
    private_b, _ = generate()
    _, public_a = generate()
    ciphertext = encrypt(public_a, b"event a's registration")

    with pytest.raises(DecryptionError):
        decrypt(private_b, ciphertext)


def test_a_truncated_or_tampered_ciphertext_is_refused_not_returned_garbled() -> None:
    private_pem, public_pem = generate()
    ciphertext = encrypt(public_pem, b"a registration")

    # Truncated: drops the closing brace, so this fails to parse at all.
    with pytest.raises(DecryptionError):
        decrypt(private_pem, ciphertext[:-1])

    # Tampered: one character flipped in the middle of the payload, so this
    # parses fine but the AES-GCM authentication tag no longer matches.
    middle = len(ciphertext) // 2
    flipped = "0" if ciphertext[middle] != "0" else "1"
    tampered = ciphertext[:middle] + flipped + ciphertext[middle + 1 :]
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


def test_encrypt_draws_a_fresh_nonce_and_key_every_call() -> None:
    """Two encryptions of the same plaintext must not produce the same
    ciphertext, or the nonce is being reused -- which breaks AES-GCM."""
    _, public_pem = generate()
    first = encrypt(public_pem, b"same payload")
    second = encrypt(public_pem, b"same payload")
    assert first != second


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
# public_key_path(): where the published half lives
# ------------------------------------------------------------------ #


def test_public_key_path_is_under_keys_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    assert public_key_path("mrg-042") == tmp_path / "keys" / "events" / "mrg-042.pub"


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
    assert key_status("mrg-042", key_was_published=False, registry=registry) == DESTROYED


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
