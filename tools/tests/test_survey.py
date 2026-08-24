from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from convener_ops import eventkeys
from convener_ops.survey import (
    _MAX_FEEDBACK_LENGTH,
    _PLAINTEXT_PAD_BYTES,
    FILE_VERSION,
    ResponseFile,
    SurveyResponse,
    _pad,
    _to_plaintext,
    _unpad,
    add_response,
    dump_response_file,
    load_response_file,
    to_survey_response,
)


def _fields(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "overall_rating": 5,
        "recommend": True,
        "feedback": "Loved the live Q&A.",
    }
    base.update(overrides)
    return base


def _envelope(public_pem: str, **overrides: Any) -> str:
    plaintext = json.dumps(_fields(**overrides)).encode("utf-8")
    return eventkeys.encrypt(public_pem, plaintext)


def _dispatch_payload(event_id: str, public_pem: str, **overrides: Any) -> str:
    envelope = json.loads(_envelope(public_pem, **overrides))
    return json.dumps({"event_id": event_id, **envelope})


# ------------------------------------------------------------------ #
# to_survey_response(): the only place a submitted envelope becomes answers
# ------------------------------------------------------------------ #


def test_to_survey_response_recovers_every_field() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem)

    response = to_survey_response(ciphertext, private_pem)

    assert response == SurveyResponse(
        overall_rating=5, recommend=True, feedback="Loved the live Q&A."
    )


def test_to_survey_response_ignores_the_dispatch_wrapping_event_id() -> None:
    private_pem, public_pem = eventkeys.generate()
    payload = _dispatch_payload("mrg-042", public_pem)

    response = to_survey_response(payload, private_pem)

    assert response is not None
    assert response.overall_rating == 5


def test_to_survey_response_accepts_feedback_at_its_blank_default() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, recommend=False, feedback="")

    response = to_survey_response(ciphertext, private_pem)

    assert response == SurveyResponse(overall_rating=5, recommend=False, feedback="")


def test_to_survey_response_strips_surrounding_whitespace_from_feedback() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, feedback="  Great talk!  ")

    response = to_survey_response(ciphertext, private_pem)

    assert response is not None
    assert response.feedback == "Great talk!"


def test_to_survey_response_returns_none_for_the_wrong_key() -> None:
    private_b, _ = eventkeys.generate()
    _, public_a = eventkeys.generate()
    ciphertext = _envelope(public_a)

    assert to_survey_response(ciphertext, private_b) is None


def test_to_survey_response_returns_none_for_ciphertext_that_is_not_json() -> None:
    private_pem, _ = eventkeys.generate()
    assert to_survey_response("not json at all", private_pem) is None


def test_to_survey_response_returns_none_for_decrypted_plaintext_not_json() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = eventkeys.encrypt(public_pem, b"not json at all")

    assert to_survey_response(ciphertext, private_pem) is None


def test_to_survey_response_returns_none_for_decrypted_bytes_that_are_not_utf8() -> (
    None
):
    """Same attacker-reachable case `test_registration.py`'s own identical
    test names: anyone who knows an event id can encrypt arbitrary non-UTF-8
    bytes under its *published* public key."""
    private_pem, public_pem = eventkeys.generate()
    ciphertext = eventkeys.encrypt(public_pem, b"\x80\x81\x82 not valid utf-8")

    assert to_survey_response(ciphertext, private_pem) is None


def test_to_survey_response_returns_none_for_a_missing_field() -> None:
    private_pem, public_pem = eventkeys.generate()
    fields = _fields()
    del fields["feedback"]
    ciphertext = eventkeys.encrypt(public_pem, json.dumps(fields).encode("utf-8"))

    assert to_survey_response(ciphertext, private_pem) is None


def test_to_survey_response_returns_none_for_an_extra_field() -> None:
    private_pem, public_pem = eventkeys.generate()
    fields = _fields()
    fields["is_admin"] = True
    ciphertext = eventkeys.encrypt(public_pem, json.dumps(fields).encode("utf-8"))

    assert to_survey_response(ciphertext, private_pem) is None


def test_to_survey_response_returns_none_for_a_plaintext_that_is_not_an_object() -> (
    None
):
    private_pem, public_pem = eventkeys.generate()
    ciphertext = eventkeys.encrypt(public_pem, b"[1, 2, 3]")

    assert to_survey_response(ciphertext, private_pem) is None


@pytest.mark.parametrize("rating", [0, 6, -1, 100])
def test_to_survey_response_returns_none_for_a_rating_outside_1_to_5(
    rating: int,
) -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, overall_rating=rating)

    assert to_survey_response(ciphertext, private_pem) is None


@pytest.mark.parametrize("rating", [1, 2, 3, 4, 5])
def test_to_survey_response_accepts_every_rating_in_range(rating: int) -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, overall_rating=rating)

    response = to_survey_response(ciphertext, private_pem)

    assert response is not None
    assert response.overall_rating == rating


def test_to_survey_response_returns_none_for_a_rating_that_is_not_an_integer() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, overall_rating=4.5)

    assert to_survey_response(ciphertext, private_pem) is None


def test_to_survey_response_returns_none_for_a_rating_given_as_a_bool() -> None:
    """bool is a subclass of int in Python -- `True` must not silently pass
    as `1`, the same guard `registration.py` and `validate.py` both apply
    to every integer field a stranger could submit."""
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, overall_rating=True)

    assert to_survey_response(ciphertext, private_pem) is None


def test_to_survey_response_returns_none_for_a_recommend_of_the_wrong_type() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, recommend="yes")

    assert to_survey_response(ciphertext, private_pem) is None


def test_to_survey_response_returns_none_for_a_feedback_of_the_wrong_type() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, feedback=42)

    assert to_survey_response(ciphertext, private_pem) is None


def test_to_survey_response_accepts_feedback_at_exactly_the_length_cap() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, feedback="A" * 2000)

    response = to_survey_response(ciphertext, private_pem)

    assert response is not None
    assert len(response.feedback) == 2000


def test_to_survey_response_returns_none_for_feedback_one_over_the_length_cap() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, feedback="A" * 2001)

    assert to_survey_response(ciphertext, private_pem) is None


def test_to_survey_response_length_cap_is_checked_after_stripping() -> None:
    private_pem, public_pem = eventkeys.generate()
    ciphertext = _envelope(public_pem, feedback=" " * 50 + "Great!" + " " * 50)

    response = to_survey_response(ciphertext, private_pem)

    assert response is not None
    assert response.feedback == "Great!"


# ------------------------------------------------------------------ #
# _pad() / _unpad(): R-39, fix round 1 -- the fixed-size plaintext
# padding that removes the ciphertext-length quasi-identifier.
# ------------------------------------------------------------------ #


def test_pad_reaches_exactly_the_target_size() -> None:
    assert len(_pad(b"hello")) == _PLAINTEXT_PAD_BYTES


def test_pad_of_empty_bytes_still_reaches_the_target_size() -> None:
    assert len(_pad(b"")) == _PLAINTEXT_PAD_BYTES


def test_pad_appends_only_zero_bytes() -> None:
    padded = _pad(b"hello")
    assert padded[:5] == b"hello"
    assert padded[5:] == b"\x00" * (_PLAINTEXT_PAD_BYTES - 5)


def test_pad_refuses_data_already_at_the_target_size() -> None:
    with pytest.raises(ValueError, match="pad target"):
        _pad(b"x" * _PLAINTEXT_PAD_BYTES)


def test_pad_refuses_data_past_the_target_size() -> None:
    with pytest.raises(ValueError, match="pad target"):
        _pad(b"x" * (_PLAINTEXT_PAD_BYTES + 1))


def test_unpad_recovers_the_original_bytes() -> None:
    assert _unpad(_pad(b"hello")) == b"hello"


def test_unpad_recovers_empty_bytes() -> None:
    assert _unpad(_pad(b"")) == b""


def test_unpad_is_a_no_op_on_data_with_no_null_byte() -> None:
    # Backward-compatible with an older, unpadded wire-format entry: no
    # NUL means nothing to strip.
    assert _unpad(b"hello") == b"hello"


def test_two_different_lengths_pad_to_the_identical_size() -> None:
    # The property R-39 exists for, pinned directly rather than only
    # through the two layers (encrypt.ts, add_response) that use it.
    assert len(_pad(b"short")) == len(_pad(b"a much, much longer message"))


# ------------------------------------------------------------------ #
# ResponseFile: load_response_file() / dump_response_file()
# ------------------------------------------------------------------ #


def test_load_response_file_with_no_text_starts_empty() -> None:
    assert load_response_file(None) == ResponseFile()


def test_dump_and_load_round_trip() -> None:
    file = ResponseFile(
        entries=({"v": 1, "encrypted_key": "a", "iv": "b", "ciphertext": "c"},)
    )

    text = dump_response_file(file)

    assert load_response_file(text) == file


def test_dump_response_file_is_stable_and_diff_friendly() -> None:
    text = dump_response_file(ResponseFile())
    assert text == '{\n  "v": 1,\n  "responses": []\n}\n'


@pytest.mark.parametrize(
    "text",
    [
        "not json at all",
        "[]",
        '{"v": 2, "responses": []}',
        '{"v": 1}',
        '{"v": 1, "responses": "nope"}',
        '{"v": 1, "responses": [1, 2]}',
    ],
)
def test_load_response_file_rejects_anything_not_this_format(text: str) -> None:
    with pytest.raises(ValueError):
        load_response_file(text)


def test_load_response_file_rejects_an_entry_with_an_extra_field() -> None:
    text = json.dumps(
        {
            "v": 1,
            "responses": [
                {
                    "v": 1,
                    "encrypted_key": "AA==",
                    "iv": "AAAAAAAAAAAAAAAA",
                    "ciphertext": "AAAAAAAAAAAAAAAAAAAAAAA=",
                    "extra": "x",
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="not exactly ciphertext"):
        load_response_file(text)


def test_load_response_file_rejects_an_entry_missing_a_field() -> None:
    text = json.dumps(
        {
            "v": 1,
            "responses": [
                {
                    "v": 1,
                    "encrypted_key": "AA==",
                    "ciphertext": "AAAAAAAAAAAAAAAAAAAAAAA=",
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="not exactly ciphertext"):
        load_response_file(text)


def test_file_version_is_1() -> None:
    assert FILE_VERSION == 1


# ------------------------------------------------------------------ #
# add_response(): append-only, one independent envelope per record --
# the mutation this suite exists to catch: one person's submission must
# never touch, re-encrypt or reorder a sibling entry's bytes.
# ------------------------------------------------------------------ #


def test_add_response_appends_the_first_response() -> None:
    private_pem, _ = eventkeys.generate()
    response = SurveyResponse(overall_rating=5, recommend=True, feedback="Great!")

    updated = add_response(ResponseFile(), response, private_pem=private_pem)

    assert len(updated.entries) == 1
    assert to_survey_response(json.dumps(updated.entries[0]), private_pem) == response


def test_add_response_appends_a_second_response_without_merging_with_the_first() -> (
    None
):
    private_pem, _ = eventkeys.generate()
    first = SurveyResponse(overall_rating=5, recommend=True, feedback="First.")
    second = SurveyResponse(overall_rating=2, recommend=False, feedback="Second.")
    file = add_response(ResponseFile(), first, private_pem=private_pem)

    updated = add_response(file, second, private_pem=private_pem)

    assert len(updated.entries) == 2
    recovered = [
        to_survey_response(json.dumps(entry), private_pem) for entry in updated.entries
    ]
    assert recovered == [first, second]


def test_add_response_never_replaces_an_existing_entry_even_for_identical_answers() -> (
    None
):
    """Unlike registration.upsert, add_response has no notion of "the same
    person came back" -- two submissions with byte-identical answers must
    still produce two entries, never a dedup."""
    private_pem, _ = eventkeys.generate()
    response = SurveyResponse(overall_rating=4, recommend=True, feedback="")
    file = add_response(ResponseFile(), response, private_pem=private_pem)

    updated = add_response(file, response, private_pem=private_pem)

    assert len(updated.entries) == 2


def test_add_response_leaves_existing_entries_byte_for_byte_unchanged() -> None:
    """The mutation-testing target named in task 16's brief: adding a third
    response must not so much as re-encrypt the first or the second."""
    private_pem, _ = eventkeys.generate()
    file = ResponseFile()
    for rating in (5, 3, 1):
        file = add_response(
            file,
            SurveyResponse(overall_rating=rating, recommend=True, feedback=""),
            private_pem=private_pem,
        )
    first_entry, second_entry, third_entry = file.entries

    updated = add_response(
        file,
        SurveyResponse(overall_rating=2, recommend=False, feedback="new"),
        private_pem=private_pem,
    )

    assert updated.entries[0] == first_entry
    assert updated.entries[1] == second_entry
    assert updated.entries[2] == third_entry
    assert len(updated.entries) == 4


def test_add_response_writes_entries_that_are_exactly_ciphertext() -> None:
    """The mutation this test exists to catch: writing a stray lookup or
    identity field beside the envelope -- the structural guard against
    identity ever sitting in plain sight next to a response's ciphertext,
    mirroring `registration.py`'s identical test."""
    private_pem, _ = eventkeys.generate()
    response = SurveyResponse(overall_rating=5, recommend=True, feedback="")

    updated = add_response(ResponseFile(), response, private_pem=private_pem)

    for entry in updated.entries:
        assert set(entry) == eventkeys.ENVELOPE_FIELDS


def test_add_response_re_encrypts_under_derived_key_not_a_stale_published_one() -> None:
    """Mirrors `registration.py::upsert`'s own reasoning: there is no
    `public_pem` parameter, so a caller cannot accidentally re-encrypt
    under a stale or mismatched `keys/events/<id>.pub`."""
    private_pem, public_pem = eventkeys.generate()
    other_private, _ = eventkeys.generate()
    response = SurveyResponse(overall_rating=3, recommend=False, feedback="")

    updated = add_response(ResponseFile(), response, private_pem=private_pem)

    assert to_survey_response(json.dumps(updated.entries[0]), private_pem) == response
    assert to_survey_response(json.dumps(updated.entries[0]), other_private) is None
    assert public_pem  # sanity: a real, distinct key exists for this event


# ------------------------------------------------------------------ #
# D-14: the shared fixture -- what the browser encrypts, this module must
# be able to turn into a SurveyResponse. Mirrors
# test_registration.py's own copy of this comment.
# ------------------------------------------------------------------ #

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "governance-cases.json"
_FIXTURE = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))[
    "event_survey_response_encryption"
]


@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=lambda c: c["name"])
def test_a_browser_encrypted_envelope_becomes_the_same_survey_response(
    case: dict[str, Any],
) -> None:
    response = to_survey_response(case["envelope"], _FIXTURE["private_pem"])
    assert response is not None
    assert response.overall_rating == case["fields"]["overall_rating"]
    assert response.recommend == case["fields"]["recommend"]
    assert response.feedback == case["fields"]["feedback"]


def test_the_pad_target_is_bound_by_the_shared_fixture_not_its_own_symbol() -> None:
    """Minor 2, fix round 2: before this test, every assertion in the
    `_pad`/`_unpad` block above compared `_PLAINTEXT_PAD_BYTES` to itself
    (`len(_pad(...)) == _PLAINTEXT_PAD_BYTES`), so changing the constant
    to 4096 left this whole suite green -- every comparison moved with it.
    `governance-cases.json::event_survey_response_encryption.pad_bytes` is
    a literal, independent of this module's own symbol, written once when
    the fixture's own R-40 case was captured; `encrypt.ts`'s test suite
    binds the identical literal on its own side (`survey-encrypt.test.ts`).
    A real disagreement between the two languages -- or a drive-by change
    to just one -- fails here, not by coincidence."""
    assert _FIXTURE["pad_bytes"] == _PLAINTEXT_PAD_BYTES


# ------------------------------------------------------------------ #
# R-40, fix round 2: `_to_plaintext`'s `ensure_ascii=False`, and
# `to_survey_response`'s own byte-bound check. `governance-cases.json`'s
# third survey case (2000 non-Latin code points) is the D-14 half of this
# -- read from both languages, captured once under Node's own
# crypto.subtle exactly like the first two cases. What follows here is
# the Python-only half: the two failure directions a shared fixture case
# alone cannot exercise (the byte-bound *rejecting* something, and a
# direct measurement proving the two encoders now agree byte for byte).
# ------------------------------------------------------------------ #


def test_to_plaintext_agrees_with_json_stringify_on_non_ascii_byte_length() -> None:
    """The mechanism R-40 names directly: `json.dumps`'s default
    `ensure_ascii=True` would have inflated a non-ASCII character to a
    six-byte (or, for an astral character, twelve-byte) escape, while
    `encrypt.ts`'s `JSON.stringify` leaves it as itself -- at most 4 UTF-8
    bytes. `_to_plaintext`'s own `ensure_ascii=False` closes that gap by
    matching the 4-byte-per-character ceiling `_PLAINTEXT_PAD_BYTES` was
    always sized against (`4 * 2000 + 100 = 8100`, see that constant's own
    docstring)."""
    feedback = "你" * 2000  # a BMP character: 3 UTF-8 bytes each, not 6
    response = SurveyResponse(overall_rating=4, recommend=True, feedback=feedback)
    plaintext = _to_plaintext(response)

    # Reconstructed independently of _to_plaintext's own implementation --
    # the feedback's raw UTF-8 bytes plus the JSON envelope around an
    # empty feedback string, the same "content plus fixed overhead" shape
    # _PLAINTEXT_PAD_BYTES's own docstring reasons from.
    overhead = len(
        json.dumps(
            {"overall_rating": 4, "recommend": True, "feedback": ""},
            separators=(",", ":"),
        )
    )
    assert len(plaintext) == len(feedback.encode("utf-8")) + overhead
    # Comfortably inside the pad target -- before ensure_ascii=False, the
    # same input measured 12051 bytes here (six bytes per character) and
    # overflowed it by nearly a factor of 1.5.
    assert len(plaintext) < _PLAINTEXT_PAD_BYTES


@pytest.mark.parametrize(
    "feedback",
    [
        "x" * 2000,  # ASCII: 1 byte/char, the cheapest case
        "你" * 2000,  # CJK, a BMP character: 3 bytes/char
        "\U0001f600" * 2000,  # emoji, an astral character: 4 bytes/char
    ],
    ids=["ascii", "cjk", "emoji"],
)
def test_every_script_at_the_character_cap_fits_the_pad_target(feedback: str) -> None:
    """R-40's own headline claim, proven for the worst case in each byte
    class UTF-8 can produce: at `_MAX_FEEDBACK_LENGTH` (2000) code points,
    even an answer written entirely in 4-byte characters must still round
    -trip, not crash. Before this fix, the emoji and CJK cases here both
    raised an uncaught `ValueError` out of `add_response` -- accepted by
    the browser and the relay, confirmed to the participant as sent, then
    destroyed."""
    private_pem, public_pem = eventkeys.generate()
    response = SurveyResponse(overall_rating=5, recommend=True, feedback=feedback)
    envelope = eventkeys.encrypt(public_pem, _pad(_to_plaintext(response)))
    decoded = to_survey_response(envelope, private_pem)
    assert decoded == response


def test_to_survey_response_refuses_rather_than_lets_pad_raise() -> None:
    """R-40's other half: `_MAX_FEEDBACK_LENGTH` bounds code points, not
    bytes, so a hypothetical future change to it (or a bug in the byte
    math) must not resurrect the crash by way of `_pad` itself raising
    inside `add_response`, past `to_survey_response`'s own uniform `None`
    contract. Simulated here by raising the character cap far enough that
    an astral-heavy feedback text exceeds `_PLAINTEXT_PAD_BYTES` once
    re-serialised -- `to_survey_response` must refuse it with `None`
    itself, at the point it decrypts and validates, never handing
    `add_response` something `_pad` would raise on."""
    private_pem, public_pem = eventkeys.generate()
    feedback = "\U0001f600" * 3000  # 4 bytes/char * 3000 = 12000 bytes alone
    response = SurveyResponse(overall_rating=1, recommend=False, feedback=feedback)
    # Bypasses to_survey_response's own MAX_FEEDBACK_LENGTH gate on the way
    # in -- the module under test is being asked "if this ever got past
    # the character cap, would the byte cap still catch it," not "does the
    # character cap work" (already covered elsewhere in this file).
    envelope = eventkeys.encrypt(public_pem, _to_plaintext(response))
    assert to_survey_response(envelope, private_pem) is None


def test_to_survey_response_refuses_a_capped_answer_that_is_still_too_many_bytes() -> (
    None
):
    """The byte cap's own reachable case, which the test above does not
    reach: it raises the *character* count past the cap too, so it is the
    character gate that refuses it and the byte gate is never asked.

    Two thousand control characters is inside the character cap exactly --
    `_MAX_FEEDBACK_LENGTH` counts code points, and `strip()` leaves these
    where it would remove whitespace -- while `json.dumps` writes each one
    as a six-byte `\\uXXXX` escape even with `ensure_ascii=False`, because
    JSON's own grammar has no other way to spell a control character. So
    the same answer is 2000 characters and 12000 bytes, and only the byte
    check can turn it away before `_pad` raises on it.

    Phase 9, task 2: this is checked here rather than through a job,
    because the job that used to reach it (`handle_survey_response`) is
    gone -- the queue drain calls `to_survey_response` directly.
    """
    private_pem, public_pem = eventkeys.generate()
    response = SurveyResponse(
        overall_rating=3, recommend=True, feedback="\x01" * _MAX_FEEDBACK_LENGTH
    )
    plaintext = _to_plaintext(response)
    assert len(response.feedback) == _MAX_FEEDBACK_LENGTH
    assert len(plaintext) >= _PLAINTEXT_PAD_BYTES

    assert (
        to_survey_response(eventkeys.encrypt(public_pem, plaintext), private_pem)
        is None
    )
