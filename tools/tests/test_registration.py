from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from convener_ops import eventkeys, published
from convener_ops.registration import (
    _CODE_ALPHABET,
    _MAX_FIELD_LENGTH,
    FILE_VERSION,
    SIGNUP_BASE,
    Registration,
    RegistrationFile,
    dump_registration_file,
    event_id_from_payload,
    find_by_email,
    load_registration_file,
    matching_code,
    to_registration,
    upsert,
)

#: A legal code alphabet symbol: exactly `_CODE_ALPHABET`'s own 30 symbols.
_CODE_SYMBOL_RE = re.compile(f"^[{_CODE_ALPHABET}]+$")


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


def test_to_registration_returns_none_for_decrypted_bytes_that_are_not_utf8() -> None:
    """`json.loads` decodes `bytes` as UTF-8 before it ever parses JSON, and
    raises `UnicodeDecodeError` -- not `JSONDecodeError` -- for anything
    that fails that step. Anyone who knows an event id can encrypt
    arbitrary non-UTF-8 bytes under its *published* public key, so this is
    real attacker-reachable input, not a hypothetical: without catching
    this specific exception, it would escape `to_registration` entirely,
    against the function's own "None covers everything" contract -- and
    `UnicodeDecodeError.object` carries the full plaintext, so an escaped
    instance is not a harmless crash."""
    private_pem, public_pem = eventkeys.generate()
    ciphertext = eventkeys.encrypt(public_pem, b"\x80\x81\x82 not valid utf-8")

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
# to_registration(): the length cap -- a reputation bound, not a
# data-quality check.
#
# Every test below used to build its input as
# `_MAX_FIELD_LENGTH` characters, or `_MAX_FIELD_LENGTH + 1` -- which
# passes for whatever value the constant holds, so mutating it from 200 to
# 5000 survived the entire suite. Written against the literal `200` now,
# the same way `test_survey.py`'s own boundary cases are written against
# the literal `2000`, not `_MAX_FEEDBACK_LENGTH`: a mutated constant no
# longer agrees with the literal, and the boundary these tests exist to
# check moves out from under them.
# ------------------------------------------------------------------ #


def test_max_field_length_is_two_hundred() -> None:
    """Pins the constant itself to the value every test below assumes --
    if this ever changes on purpose, every literal `200` below has to
    change with it, not silently keep passing against a stale number."""
    assert _MAX_FIELD_LENGTH == 200


def test_to_registration_accepts_a_field_at_exactly_the_cap() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, first_name="A" * 200)

    registration = to_registration(ciphertext, private_pem)

    assert registration is not None
    assert registration.first_name == "A" * 200


@pytest.mark.parametrize("field", ["first_name", "surname", "email", "institution"])
def test_to_registration_returns_none_for_a_field_one_over_the_cap(
    field: str,
) -> None:
    """The attacker-reachable case the cap exists for: a single field
    padded past the bound is refused whole, not truncated -- truncating
    would still deliver a stranger's text through the organisation's own
    mailbox, only a little shorter."""
    private_pem, public_pem = eventkeys.generate()
    overrides: dict[str, Any] = {field: "A" * 201}
    if field == "email":
        # A field one over the cap that is still shaped like an address --
        # the cap must fire on length alone, not ride along on the "@"
        # check catching it for an unrelated reason.
        overrides["email"] = ("a" * 189) + "@example.org"
        assert len(overrides["email"]) == 201
    ciphertext = _envelope(public_pem, **overrides)

    assert to_registration(ciphertext, private_pem) is None


def test_to_registration_length_cap_is_checked_after_stripping() -> None:
    """A field padded with whitespace out to just past the cap, but whose
    stripped content is well inside it, must be accepted -- the cap is
    about what a reader (or a mailbox) actually receives, and `compose`
    only ever sees the stripped value."""
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, first_name=" " * 50 + "Ada" + " " * 50)

    registration = to_registration(ciphertext, private_pem)

    assert registration is not None
    assert registration.first_name == "Ada"


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
    private_pem, _ = eventkeys.generate()
    registration = Registration("Ada", "Lovelace", "ada@example.org", "", False)

    updated, replaced = upsert(
        RegistrationFile(), registration, private_pem=private_pem
    )

    assert replaced is False
    assert len(updated.entries) == 1
    assert to_registration(json.dumps(updated.entries[0]), private_pem) == registration


def test_upsert_appends_a_second_registration_from_a_different_address() -> None:
    private_pem, _ = eventkeys.generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)

    updated, replaced = upsert(file, grace, private_pem=private_pem)

    assert replaced is False
    assert len(updated.entries) == 2


def test_upsert_replaces_rather_than_duplicates_the_same_address() -> None:
    """The mutation this test exists to catch: a dedup check that never
    fires would leave two entries for one registrant here instead of one."""
    private_pem, _ = eventkeys.generate()
    first = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    second = Registration(
        "Ada", "Lovelace", "ada@example.org", "Analytical Engines Institute", True
    )
    file, _replaced = upsert(RegistrationFile(), first, private_pem=private_pem)

    updated, replaced = upsert(file, second, private_pem=private_pem)

    assert replaced is True
    assert len(updated.entries) == 1
    assert to_registration(json.dumps(updated.entries[0]), private_pem) == second


def test_upsert_matches_the_same_address_regardless_of_case_or_whitespace() -> None:
    private_pem, _ = eventkeys.generate()
    first = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    second = Registration("Ada", "Lovelace", " Ada@Example.ORG ", "", True)
    file, _replaced = upsert(RegistrationFile(), first, private_pem=private_pem)

    _, replaced = upsert(file, second, private_pem=private_pem)

    assert replaced is True


def test_upsert_leaves_every_other_entrys_ciphertext_byte_for_byte_unchanged() -> None:
    """The property the module docstring names as the reason for one
    envelope per registration rather than one for the whole file: updating
    Grace's entry must not so much as re-encrypt Ada's or Marie's."""
    private_pem, _ = eventkeys.generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    marie = Registration("Marie", "Curie", "marie@example.org", "", True)
    file = RegistrationFile()
    for registration in (ada, grace, marie):
        file, _replaced = upsert(file, registration, private_pem=private_pem)
    ada_entry, grace_entry, marie_entry = file.entries

    grace_again = Registration("Grace", "Hopper", "grace@example.org", "US Navy", True)
    updated, replaced = upsert(file, grace_again, private_pem=private_pem)

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
    private_pem, _ = eventkeys.generate()
    stray_entry = {
        "v": 1,
        "encrypted_key": "AA==",
        "iv": "AAAAAAAAAAAAAAAA",
        "ciphertext": "AAAAAAAAAAAAAAAAAAAAAAA=",
    }
    file = RegistrationFile(entries=(stray_entry,))
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)

    updated, replaced = upsert(file, ada, private_pem=private_pem)

    assert replaced is False
    assert updated.entries[0] == stray_entry
    assert len(updated.entries) == 2


# ------------------------------------------------------------------ #
# Every entry is exactly ciphertext -- the structural guard against a
# cleartext lookup field ever sitting beside an envelope. A round-trip
# assertion ("it still decrypts") would not catch an *extra* field the
# way an exact key-set comparison does.
# ------------------------------------------------------------------ #


def test_upsert_writes_entries_that_are_exactly_ciphertext() -> None:
    """The mutation this test exists to catch: `upsert` writing
    `entry["email_lookup"] = registration.email` beside the envelope --
    a realistic "stop decrypting every existing entry" optimisation that
    would otherwise ship an address into the committed file in the clear
    while every round-trip ("it still decrypts") test kept passing."""
    private_pem, _ = eventkeys.generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)

    updated, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)

    for entry in updated.entries:
        assert set(entry) == eventkeys.ENVELOPE_FIELDS


def test_load_registration_file_rejects_an_entry_with_an_extra_field() -> None:
    """Pins `load_registration_file`'s own runtime guard directly, not only
    through `upsert`: a hand-edited or migrated file with a stray field
    beside an envelope must never load silently."""
    text = json.dumps(
        {
            "v": 1,
            "registrations": [
                {
                    "v": 1,
                    "encrypted_key": "AA==",
                    "iv": "AAAAAAAAAAAAAAAA",
                    "ciphertext": "AAAAAAAAAAAAAAAAAAAAAAA=",
                    "email_lookup": "ada@example.org",
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="not exactly ciphertext"):
        load_registration_file(text)


def test_load_registration_file_rejects_an_entry_missing_a_field() -> None:
    text = json.dumps(
        {
            "v": 1,
            "registrations": [
                {
                    "v": 1,
                    "encrypted_key": "AA==",
                    "ciphertext": "AAAAAAAAAAAAAAAAAAAAAAA=",
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="not exactly ciphertext"):
        load_registration_file(text)


# ------------------------------------------------------------------ #
# find_by_email(): the same question upsert() answers internally, asked
# about a file's state *before* an upsert call -- the confirmation's own need.
# ------------------------------------------------------------------ #


def test_find_by_email_is_none_on_an_empty_file() -> None:
    private_pem, _ = eventkeys.generate()
    assert find_by_email(RegistrationFile(), "ada@example.org", private_pem) is None


def test_find_by_email_finds_the_matching_entry() -> None:
    private_pem, _ = eventkeys.generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    file = RegistrationFile()
    for registration in (ada, grace):
        file, _replaced = upsert(file, registration, private_pem=private_pem)

    found = find_by_email(file, "ada@example.org", private_pem)

    assert found == ada


def test_find_by_email_matches_regardless_of_case_or_whitespace() -> None:
    private_pem, _ = eventkeys.generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)

    found = find_by_email(file, " Ada@Example.ORG ", private_pem)

    assert found == ada


def test_find_by_email_is_none_when_no_entry_matches() -> None:
    private_pem, _ = eventkeys.generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)

    assert find_by_email(file, "grace@example.org", private_pem) is None


def test_find_by_email_skips_an_entry_it_cannot_decrypt() -> None:
    """The `find_by_email` twin of the `upsert` test above with a matching
    name: a stray entry from another event's key must never read as a
    match."""
    private_pem, _ = eventkeys.generate()
    stray_entry = {
        "v": 1,
        "encrypted_key": "AA==",
        "iv": "AAAAAAAAAAAAAAAA",
        "ciphertext": "AAAAAAAAAAAAAAAAAAAAAAA=",
    }
    file = RegistrationFile(entries=(stray_entry,))

    assert find_by_email(file, "ada@example.org", private_pem) is None


def test_find_by_email_reflects_an_update_before_it_was_applied() -> None:
    """The property the confirmation needs directly: called against the file *before*
    `upsert`, this returns the pre-update registration, not the one about
    to replace it."""
    private_pem, _ = eventkeys.generate()
    first = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), first, private_pem=private_pem)
    second = Registration(
        "Ada", "Lovelace", "ada@example.org", "Analytical Engines Institute", True
    )

    old = find_by_email(file, second.email, private_pem)
    updated, replaced = upsert(file, second, private_pem=private_pem)

    assert old == first
    assert replaced is True
    assert to_registration(json.dumps(updated.entries[0]), private_pem) == second


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
    """The property a resend depends on directly: correcting only casing
    must not invalidate the code the first confirmation email already
    sent."""
    canonical = matching_code("mrg-042", "ada@example.org", "sh")
    resent = matching_code("mrg-042", " Ada@Example.ORG ", "sh")
    assert canonical == resent


def test_matching_code_differs_by_address() -> None:
    ada = matching_code("mrg-042", "ada@example.org", "sh")
    grace = matching_code("mrg-042", "grace@example.org", "sh")
    assert ada != grace


def test_matching_code_differs_by_event() -> None:
    """A code per event is only a code per event if it gives away nothing
    about the others -- the same property
    test_eventkeys.py::test_a_ciphertext_from_another_event_does_not_decrypt
    holds for the ciphertext, held here for the matching code."""
    event_a = matching_code("mrg-042", "ada@example.org", "sh")
    event_b = matching_code("mrg-043", "ada@example.org", "sh")
    assert event_a != event_b


def test_matching_code_differs_by_salt() -> None:
    """The property the whole secret exists for: a code derived under one
    salt must not be reproducible by whoever only knows the address."""
    one_salt = matching_code("mrg-042", "ada@example.org", "shhh-one")
    other_salt = matching_code("mrg-042", "ada@example.org", "shhh-two")
    assert one_salt != other_salt


def test_code_alphabet_has_30_symbols_and_excludes_every_confusion() -> None:
    """Pins the alphabet *constant* directly, not a single sampled code:
    a mutant restoring `O` (or any of `0`, `1`, `I`, `L`, `U`) would still
    pass a one-code sample about 29/30 of the time. This fails every time,
    on the alphabet itself, regardless of what any particular HMAC output
    happens to draw."""
    assert len(_CODE_ALPHABET) == 30
    assert len(set(_CODE_ALPHABET)) == 30
    assert set(_CODE_ALPHABET) & set("01ILOU") == set()


def test_matching_code_alphabet_excludes_the_classic_confusions() -> None:
    """A sampled-code companion to the constant-level test above: confirms
    the *derivation* draws from the alphabet it claims to, not only that
    the alphabet itself is correct in isolation."""
    code = matching_code("mrg-042", "ada@example.org", "sh")
    assert code is not None
    for forbidden in "01ILOU":
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


def test_matching_code_shows_avalanche_from_a_one_character_address_change() -> None:
    """`"ADA" not in code` holds for *any* derivation, including a
    reversible encoding that would defeat the whole point of hashing the
    address -- it asserts almost nothing about how the code was actually
    derived. A real HMAC has full avalanche: changing one input character
    should scramble most of the output, not shift it predictably. Two
    addresses one character apart should share few, if any, of the eight
    symbol positions; sharing at most a third of them (an extremely
    generous bound -- chance alone predicts under one shared position on
    average) is not something a substring-derived or otherwise reversible
    code could reliably do."""
    one = matching_code("mrg-042", "ada@example.org", "sh")
    other = matching_code("mrg-042", "adb@example.org", "sh")
    assert one is not None
    assert other is not None
    assert one != other

    positions_one = one.replace("-", "")
    positions_other = other.replace("-", "")
    shared = sum(a == b for a, b in zip(positions_one, positions_other, strict=True))
    assert shared <= len(positions_one) // 3


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
# SIGNUP_BASE -- nothing in the
# repository used to carry the address that reaches the registration page at
# all.
#
# Registration moved off the operators' application's own
# `/signup/:eventId` route onto an island mounted on the public event
# page, so this pin moved with it -- from a `HashRouter` fragment to a
# plain server path, `site/src/event.njk`'s own permalink.
# `test_workflows.py::test_registration_signup_base_matches_the_event_
# page_permalink` binds the value itself against that template; this only
# pins the literal shape a reader of this module can check without
# cross-referencing it.
# ------------------------------------------------------------------ #


def test_signup_base_is_the_event_pages_own_address() -> None:
    assert SIGNUP_BASE.endswith("/events/")
    assert SIGNUP_BASE.startswith(published.load().url)


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
