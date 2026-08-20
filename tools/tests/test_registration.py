from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from convener_ops import eventkeys
from convener_ops.registration import (
    FILE_VERSION,
    Registration,
    RegistrationFile,
    dump_registration_file,
    event_id_from_payload,
    load_registration_file,
    matching_code,
    to_registration,
    upsert,
)

#: A legal code alphabet symbol: neither the "31 symbols" `matching_code`
#: documents nor `0`/`O`/`1`/`I`/`L`.
_CODE_SYMBOL_RE = re.compile(r"^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]+$")


def _fields(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "first_name": "Ada",
        "surname": "Lovelace",
        "email": "ada@example.org",
        "institution": "Analytical Engines Institute",
        "membership_opt_in": True,
    }
    base.update(overrides)
    return base


def _envelope(public_pem: str, **overrides: Any) -> str:
    """A registration payload, encrypted exactly the way the browser
    encrypts one -- the four `eventkeys` wire fields, whatever `_fields`
    gives as the plaintext."""
    plaintext = json.dumps(_fields(**overrides)).encode("utf-8")
    return eventkeys.encrypt(public_pem, plaintext)


def _dispatch_payload(event_id: str, public_pem: str, **overrides: Any) -> str:
    """The whole relayed body: `{event_id, v, encrypted_key, iv,
    ciphertext}`, exactly what `services/signup-relay/src/index.js`
    forwards -- the shape `event_id_from_payload` and `to_registration`
    both have to read, the second one ignoring the `event_id` key."""
    envelope = json.loads(_envelope(public_pem, **overrides))
    return json.dumps({"event_id": event_id, **envelope})


# ------------------------------------------------------------------ #
# to_registration(): the only place a submitted envelope becomes names
# ------------------------------------------------------------------ #


def test_to_registration_recovers_every_field() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem)

    registration = to_registration(ciphertext, private_pem)

    assert registration == Registration(
        first_name="Ada",
        surname="Lovelace",
        email="ada@example.org",
        institution="Analytical Engines Institute",
        membership_opt_in=True,
    )


def test_to_registration_ignores_the_dispatch_wrapping_event_id() -> None:
    """The whole relayed payload -- `event_id` and all -- decrypts exactly
    like the bare envelope: `eventkeys.decrypt` reads only its own four
    fields and ignores the rest."""
    private_pem, public_pem = eventkeys.generate()
    payload = _dispatch_payload("mrg-042", public_pem)

    registration = to_registration(payload, private_pem)

    assert registration is not None
    assert registration.email == "ada@example.org"


def test_to_registration_accepts_optional_fields_at_their_blank_default() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, institution="", membership_opt_in=False)

    registration = to_registration(ciphertext, private_pem)

    assert registration == Registration(
        first_name="Ada",
        surname="Lovelace",
        email="ada@example.org",
        institution="",
        membership_opt_in=False,
    )


def test_to_registration_strips_surrounding_whitespace() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(
        public_pem, first_name=" Ada ", surname=" Lovelace ", email=" ada@example.org "
    )

    registration = to_registration(ciphertext, private_pem)

    assert registration is not None
    assert registration.first_name == "Ada"
    assert registration.surname == "Lovelace"
    assert registration.email == "ada@example.org"


def test_to_registration_returns_none_for_the_wrong_key() -> None:
    private_b, _ = eventkeys.generate()
    _, public_a = eventkeys.generate()
    ciphertext = _envelope(public_a)

    assert to_registration(ciphertext, private_b) is None


def test_to_registration_returns_none_for_ciphertext_that_is_not_json() -> None:
    private_pem, _ = eventkeys.generate()
    assert to_registration("not json at all", private_pem) is None


@pytest.mark.parametrize(
    "override",
    [
        {"first_name": ""},
        {"first_name": "   "},
        {"surname": ""},
        {"email": "not-an-address"},
        {"email": ""},
    ],
)
def test_to_registration_returns_none_for_blank_required_fields(
    override: dict[str, Any],
) -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, **override)

    assert to_registration(ciphertext, private_pem) is None


def test_to_registration_returns_none_for_a_field_of_the_wrong_type() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, membership_opt_in="true")

    assert to_registration(ciphertext, private_pem) is None


def test_to_registration_returns_none_for_a_string_field_of_the_wrong_type() -> None:
    """`membership_opt_in` is the only non-string field -- this exercises
    the loop that type-checks the four string fields, separately from the
    bool check above it."""
    private_pem, public_pem = eventkeys.generate()
    fields = _fields()
    fields["first_name"] = 42
    ciphertext = eventkeys.encrypt(public_pem, json.dumps(fields).encode("utf-8"))

    assert to_registration(ciphertext, private_pem) is None


def test_to_registration_returns_none_for_a_decrypted_plaintext_that_is_not_json() -> (
    None
):
    """Distinct from an envelope that is not JSON at all
    (`test_to_registration_returns_none_for_ciphertext_that_is_not_json`):
    here `eventkeys.decrypt` succeeds and hands back bytes that are simply
    not JSON -- a stranger encrypting arbitrary data under a *published*
    public key can do exactly this."""
    private_pem, public_pem = eventkeys.generate()
    ciphertext = eventkeys.encrypt(public_pem, b"not json at all")

    assert to_registration(ciphertext, private_pem) is None


def test_to_registration_returns_none_for_a_missing_field() -> None:
    private_pem, public_pem = eventkeys.generate()
    fields = _fields()
    del fields["institution"]
    ciphertext = eventkeys.encrypt(public_pem, json.dumps(fields).encode("utf-8"))

    assert to_registration(ciphertext, private_pem) is None


def test_to_registration_returns_none_for_an_extra_field() -> None:
    """A stranger encrypting arbitrary JSON under a *published* public key
    can add any key at all -- this is the first code that ever reads it,
    so an unexpected field is refused, not silently dropped."""
    private_pem, public_pem = eventkeys.generate()
    fields = _fields()
    fields["is_admin"] = True
    ciphertext = eventkeys.encrypt(public_pem, json.dumps(fields).encode("utf-8"))

    assert to_registration(ciphertext, private_pem) is None


def test_to_registration_returns_none_for_a_plaintext_that_is_not_an_object() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = eventkeys.encrypt(public_pem, b"[1, 2, 3]")

    assert to_registration(ciphertext, private_pem) is None


# ------------------------------------------------------------------ #
# RegistrationFile: load_registration_file() / dump_registration_file()
# ------------------------------------------------------------------ #


def test_load_registration_file_with_no_text_starts_empty() -> None:
    assert load_registration_file(None) == RegistrationFile()


def test_dump_and_load_round_trip() -> None:
    file = RegistrationFile(
        entries=({"v": 1, "encrypted_key": "a", "iv": "b", "ciphertext": "c"},)
    )

    text = dump_registration_file(file)

    assert load_registration_file(text) == file


def test_dump_registration_file_is_stable_and_diff_friendly() -> None:
    text = dump_registration_file(RegistrationFile())
    assert text == '{\n  "v": 1,\n  "registrations": []\n}\n'


@pytest.mark.parametrize(
    "text",
    [
        "not json at all",
        "[]",
        '{"v": 2, "registrations": []}',
        '{"v": 1}',
        '{"v": 1, "registrations": "nope"}',
        '{"v": 1, "registrations": [1, 2]}',
    ],
)
def test_load_registration_file_rejects_anything_not_this_format(text: str) -> None:
    with pytest.raises(ValueError):
        load_registration_file(text)


def test_file_version_is_1() -> None:
    assert FILE_VERSION == 1


# ------------------------------------------------------------------ #
# upsert(): step 3 -- the same address updates, it never duplicates
# ------------------------------------------------------------------ #


def test_upsert_appends_the_first_registration() -> None:
    private_pem, public_pem = eventkeys.generate()
    registration = Registration("Ada", "Lovelace", "ada@example.org", "", False)

    updated, replaced = upsert(
        RegistrationFile(), registration, public_pem=public_pem, private_pem=private_pem
    )

    assert replaced is False
    assert len(updated.entries) == 1
    assert to_registration(json.dumps(updated.entries[0]), private_pem) == registration


def test_upsert_appends_a_second_registration_from_a_different_address() -> None:
    private_pem, public_pem = eventkeys.generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    file, _ = upsert(
        RegistrationFile(), ada, public_pem=public_pem, private_pem=private_pem
    )

    updated, replaced = upsert(
        file, grace, public_pem=public_pem, private_pem=private_pem
    )

    assert replaced is False
    assert len(updated.entries) == 2


def test_upsert_replaces_rather_than_duplicates_the_same_address() -> None:
    """The mutation this test exists to catch: a dedup check that never
    fires would leave two entries for one registrant here instead of one."""
    private_pem, public_pem = eventkeys.generate()
    first = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    second = Registration(
        "Ada", "Lovelace", "ada@example.org", "Analytical Engines Institute", True
    )
    file, _ = upsert(
        RegistrationFile(), first, public_pem=public_pem, private_pem=private_pem
    )

    updated, replaced = upsert(
        file, second, public_pem=public_pem, private_pem=private_pem
    )

    assert replaced is True
    assert len(updated.entries) == 1
    assert to_registration(json.dumps(updated.entries[0]), private_pem) == second


def test_upsert_matches_the_same_address_regardless_of_case_or_whitespace() -> None:
    private_pem, public_pem = eventkeys.generate()
    first = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    second = Registration("Ada", "Lovelace", " Ada@Example.ORG ", "", True)
    file, _ = upsert(
        RegistrationFile(), first, public_pem=public_pem, private_pem=private_pem
    )

    _, replaced = upsert(file, second, public_pem=public_pem, private_pem=private_pem)

    assert replaced is True


def test_upsert_leaves_every_other_entrys_ciphertext_byte_for_byte_unchanged() -> None:
    """The property the module docstring names as the reason for one
    envelope per registration rather than one for the whole file: updating
    Grace's entry must not so much as re-encrypt Ada's or Marie's."""
    private_pem, public_pem = eventkeys.generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    marie = Registration("Marie", "Curie", "marie@example.org", "", True)
    file = RegistrationFile()
    for registration in (ada, grace, marie):
        file, _ = upsert(
            file, registration, public_pem=public_pem, private_pem=private_pem
        )
    ada_entry, grace_entry, marie_entry = file.entries

    grace_again = Registration("Grace", "Hopper", "grace@example.org", "US Navy", True)
    updated, replaced = upsert(
        file, grace_again, public_pem=public_pem, private_pem=private_pem
    )

    assert replaced is True
    assert updated.entries[0] == ada_entry
    assert updated.entries[2] == marie_entry
    assert updated.entries[1] != grace_entry
    assert to_registration(json.dumps(updated.entries[1]), private_pem) == grace_again


def test_upsert_keeps_an_undecryptable_entry_rather_than_treating_it_as_a_match() -> (
    None
):
    """An entry that cannot be decrypted with this event's own key should
    never happen in practice, but `upsert` must not crash on one, and must
    not treat it as "the same address" by default -- it is kept exactly as
    found, and the new registration is appended instead."""
    private_pem, public_pem = eventkeys.generate()
    stray_entry = {
        "v": 1,
        "encrypted_key": "AA==",
        "iv": "AAAAAAAAAAAAAAAA",
        "ciphertext": "AAAAAAAAAAAAAAAAAAAAAAA=",
    }
    file = RegistrationFile(entries=(stray_entry,))
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)

    updated, replaced = upsert(
        file, ada, public_pem=public_pem, private_pem=private_pem
    )

    assert replaced is False
    assert updated.entries[0] == stray_entry
    assert len(updated.entries) == 2


# ------------------------------------------------------------------ #
# matching_code(): short, spoken-safe, salted, stable
# ------------------------------------------------------------------ #


def test_matching_code_is_none_without_a_salt() -> None:
    assert matching_code("mrg-042", "ada@example.org", None) is None
    assert matching_code("mrg-042", "ada@example.org", "") is None


def test_matching_code_is_deterministic() -> None:
    first = matching_code("mrg-042", "ada@example.org", "sh")
    second = matching_code("mrg-042", "ada@example.org", "sh")
    assert first == second


def test_matching_code_does_not_change_when_only_case_or_whitespace_differs() -> None:
    """The property step 3 of the plan names directly: a resend that
    corrects only casing must not invalidate the code the first
    confirmation email already sent."""
    canonical = matching_code("mrg-042", "ada@example.org", "sh")
    resent = matching_code("mrg-042", " Ada@Example.ORG ", "sh")
    assert canonical == resent


def test_matching_code_differs_by_address() -> None:
    ada = matching_code("mrg-042", "ada@example.org", "sh")
    grace = matching_code("mrg-042", "grace@example.org", "sh")
    assert ada != grace


def test_matching_code_differs_by_event() -> None:
    """Une cle par evenement n'est une cle par evenement que si elle ne
    laisse pas deviner les autres -- meme propriete que
    test_eventkeys.py::test_a_ciphertext_from_another_event_does_not_decrypt,
    pour le code plutot que pour le chiffre."""
    event_a = matching_code("mrg-042", "ada@example.org", "sh")
    event_b = matching_code("mrg-043", "ada@example.org", "sh")
    assert event_a != event_b


def test_matching_code_differs_by_salt() -> None:
    """The property the whole secret exists for: a code derived under one
    salt must not be reproducible by whoever only knows the address."""
    one_salt = matching_code("mrg-042", "ada@example.org", "shhh-one")
    other_salt = matching_code("mrg-042", "ada@example.org", "shhh-two")
    assert one_salt != other_salt


def test_matching_code_alphabet_excludes_the_classic_confusions() -> None:
    code = matching_code("mrg-042", "ada@example.org", "sh")
    assert code is not None
    for forbidden in "0O1IL":
        assert forbidden not in code


def test_matching_code_shape_is_two_groups_of_four() -> None:
    code = matching_code("mrg-042", "ada@example.org", "sh")
    assert code is not None
    groups = code.split("-")
    assert len(groups) == 2
    assert all(len(group) == 4 for group in groups)
    assert all(_CODE_SYMBOL_RE.fullmatch(group) for group in groups)


def test_matching_code_never_reveals_the_address_it_derives_from() -> None:
    code = matching_code("mrg-042", "ada.lovelace@example.org", "sh")
    assert code is not None
    assert "ADA" not in code
    assert "LOVELACE" not in code


# ------------------------------------------------------------------ #
# event_id_from_payload(): the first, cheapest gate on a dispatch payload
# ------------------------------------------------------------------ #


def test_event_id_from_payload_reads_the_real_dispatch_shape() -> None:
    _, public_pem = eventkeys.generate()
    payload = _dispatch_payload("mrg-042", public_pem)
    assert event_id_from_payload(payload) == "mrg-042"


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "[1, 2, 3]",
        '{"v": 1}',
        '{"event_id": 42}',
        '{"event_id": "../escape"}',
        '{"event_id": "vw 042"}',
    ],
)
def test_event_id_from_payload_returns_none_for_anything_malformed(
    payload: str,
) -> None:
    assert event_id_from_payload(payload) is None


# ------------------------------------------------------------------ #
# D-14: the shared fixture -- what the browser encrypts, this module must
# be able to turn into a Registration. See test_eventkeys.py's own copy of
# this comment for how the fixture was built.
# ------------------------------------------------------------------ #

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "governance-cases.json"
_FIXTURE = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))[
    "event_registration_encryption"
]


@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=lambda c: c["name"])
def test_a_browser_encrypted_envelope_becomes_the_same_registration(
    case: dict[str, Any],
) -> None:
    registration = to_registration(case["envelope"], _FIXTURE["private_pem"])
    assert registration is not None
    assert registration.first_name == case["fields"]["first_name"]
    assert registration.surname == case["fields"]["surname"]
    assert registration.email == case["fields"]["email"]
    assert registration.institution == case["fields"]["institution"]
    assert registration.membership_opt_in == case["fields"]["membership_opt_in"]
