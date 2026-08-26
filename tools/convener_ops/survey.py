"""Turn one decrypted survey response into a stored, re-encrypted record.

The post-event questionnaire is optional, short, sent only
to people recognised present (`survey_invite.py`'s job, not this module's), and rides
the *same* intake as registration -- "meme entree que l'inscription, meme
stockage chiffre, meme destruction de cle." This module is the storage half
of that sentence: `app/src/survey/encrypt.ts` hybrid-encrypts a response in
the browser exactly the way `app/src/signup/encrypt.ts` encrypts a
registration (same wire format, `tools/convener_ops/eventkeys.py`), and this
module decrypts, validates and re-stores it, in a CI job's memory only, the
same discipline `registration.py`'s own module docstring holds itself to.

The three questions, and why these three
------------------------------------------
Fixed for every event (ruling 1: the spec says the survey is short and
optional *per event*, never that the questions vary), so one shape, one
validator, one template, and a switch that is a single boolean rather than a
per-event question bank nobody has asked for yet:

- ``overall_rating`` -- an integer 1-5. The one number an accreditation body
  or an organiser can act on without reading free text: "was this session
  worth running again."
- ``recommend`` -- a plain yes/no. Net-promoter-style questions are the
  shortest way to learn whether the series is reaching people who tell
  others about it, and a boolean costs a participant one tap.
- ``feedback`` -- free text, optional. The only place a participant can say
  what a five-point scale cannot: what worked, what did not. `''` is a
  legal, complete answer -- declining to write anything is not the same as
  not having been asked, the same "absence means blank string" idiom
  `registration.Registration.institution` already uses.

Three questions, not four or more: every additional question is one more
reason to abandon a survey the spec already calls short, and the spec's own
risk table (S:9) is explicit that a certificate attests presence, not
learning -- this questionnaire is a signal the organisers can act on, not an
assessment participants must pass.

Why no identity travels with a response
------------------------------------------
Unlike `registration.Registration`, nothing here carries a name or an
address. Two things follow from that, deliberately:

1. **Storage is append-only, never upsert.** `registration.py::upsert`
   replaces an existing entry addressed to the same normalised email --
   there is no address here to normalise or compare against, so
   `add_response` only ever appends a fresh, independently encrypted entry.
   A participant who submits twice leaves two entries; nothing here can or
   should tell that those two entries came from the same person, and
   nothing about eligibility -- the invitation's own gate, "recognised as
   present" -- depends on this module being able to.
2. **There is no erase-by-identity path**, unlike
   `registration.py::erase` and `find_by_matching_code`. A right-to-erasure
   request naming one person's *survey answers* specifically cannot be
   actioned by this module today, because nothing stored here can be
   matched back to that person without asking them to quote their own free
   text -- an operator's only lever for "erase this event's survey
   responses" is the same lever that erases its registrations: destroying
   the event's key early, which `eventkeys.destroy` already supports and
   which this module adds no new procedure for. This is a real, named gap
   between what the spec's S:4 rights section promises for registrations
   and what this module can deliver for anonymous survey text -- recorded
   here rather than quietly assumed away.

Anonymity is achieved by what does not travel with a response -- no name,
no address, no matching code -- and by `_PLAINTEXT_PAD_BYTES` (below),
which closes the one channel outside that list the encryption itself did
not already cover: an unpadded ciphertext's length reveals `feedback`'s
length. What remains, on purpose, is the one channel padding cannot touch
-- `data/events/<id>/survey-responses.enc`'s own commit history pairs
array position with arrival time, at whatever resolution the workflow that
writes it commits at. That is a property of an append-only git store, not
a defect this module introduces or could remove without breaking the
independent-envelope-per-response shape retention needs -- see
`docs/reference/operations.md`'s "Retention and early erasure" section,
which carries the full argument for whoever next builds on this file.

Same storage shape, same reason, as `registration.py`
--------------------------------------------------------
`data/events/<id>/survey-responses.enc` is one JSON object::

    {"v": 1, "responses": [ {<envelope>}, {<envelope>}, ... ]}

where each `<envelope>` is one independent `eventkeys.encrypt` output, for
exactly the reason `registration.py`'s own module docstring gives at length
("The file shape, and why it is not one envelope for the whole event"):
whatever future task ever needs to touch one entry -- destroy the event key
early, drop a corrupt entry a hand edit introduced -- must be able to do so
without re-encrypting every sibling entry's bytes. This module does not
build that future operation; it only refuses to make the file shape that
would make it impossible.

Same destruction, and nothing new to destroy
------------------------------------------------
`eventkeys.destroy` operates on an event id, not on a filename: destroying
`CONVENER_EVENT_KEY_<ID>` makes *both* `registrations.enc` and
`survey-responses.enc` for that event permanently unreadable in the same
one operation, on the same 90-day schedule the sweep already runs. Nothing
in `tools/convener_ops/cli.py::retention_sweep` or `record_destructions` needed
to change for this file to be covered -- that is the point of "meme
destruction de cle" being a design property of the key, not a second
procedure this module would otherwise have had to add and then keep in
sync with the sweep's.

A length cap, for the same reason registration.py has one
--------------------------------------------------------------
`_MAX_FEEDBACK_LENGTH` bounds `feedback` the same way
`registration._MAX_FIELD_LENGTH` bounds a registration's text fields: the
signup relay's own `MAX_CIPHERTEXT_BYTES` (16 KB) already bounds the whole
envelope, but a field-level cap keeps one field from being able to consume
nearly all of that budget on its own, and keeps this module's validation
honest about what "short" (spec S:6) means rather than leaving it entirely
to the relay's coarser, envelope-wide ceiling.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from . import eventkeys

#: `survey-responses.enc`'s own format version -- the file-level analogue of
#: `eventkeys.WIRE_VERSION` and `registration.FILE_VERSION`.
FILE_VERSION: Final = 1


@dataclass(frozen=True)
class SurveyResponse:
    """One participant's answers, and nothing else. Mirrors
    `app/src/survey/encrypt.ts`'s `SurveyResponse` interface field for
    field -- that is the shape the browser encrypts, so it is the shape
    `to_survey_response` has to recover."""

    overall_rating: int
    recommend: bool
    feedback: str


#: The exact field set `SurveyResponse` and the browser's
#: `encryptSurveyResponse` agree on -- the same "closed shape" discipline
#: `registration._FIELDS` holds itself to.
_FIELDS: Final = frozenset({"overall_rating", "recommend", "feedback"})

#: `overall_rating`'s legal range: a five-point scale, inclusive both ends.
_RATING_MIN: Final = 1
_RATING_MAX: Final = 5

#: See the module docstring's "A length cap" section.
_MAX_FEEDBACK_LENGTH: Final = 2000

#: AES-GCM does not pad, so an unpadded ciphertext's
#: length is a deterministic function of the plaintext's -- measured
#: before this fix, an empty `feedback` produced a 92-character base64
#: ciphertext and a 2000-character one produced 2756, and even
#: `recommend: true` differed from `false` by a byte. Against a stranger
#: that is harmless (the encryption already hides the content), but
#: against the organiser -- who holds the key and is the only party for
#: whom anonymity is a promise rather than a tautology -- a distinctively
#: long or short answer is a distinctive length, a real quasi-identifier
#: on a small cohort. Padding every plaintext to this one fixed size
#: before encryption makes every stored and transmitted ciphertext the
#: same length regardless of content, removing the channel rather than
#: merely documenting it.
#:
#: Sized generously above the worst case rather than tightly: the JSON
#: encoding of a `SurveyResponse` is at most `_MAX_FEEDBACK_LENGTH`
#: characters of `feedback`, each up to 4 UTF-8 bytes, plus
#: `overall_rating`, `recommend` and JSON punctuation (well under 100
#: bytes) -- `4 * 2000 + 100 = 8100`, rounded up to 8192 (8 KiB) for a
#: clean, round margin. At the signup relay's own per-event ceiling (500
#: responses) that is at most ~4 MB of padding overhead across an event's
#: whole file, which is nothing next to what it buys.
_PLAINTEXT_PAD_BYTES: Final = 8192


def _pad(data: bytes) -> bytes:
    """Pad `data` to exactly `_PLAINTEXT_PAD_BYTES` with trailing zero
    bytes. Raises `ValueError` if `data` is already at or past that size --
    a caller's bug, not untrusted input: every caller here first validates
    through `to_survey_response`'s own length cap, so this should be
    unreachable in practice, and a silent truncation would be a worse
    failure than a loud one."""
    if len(data) >= _PLAINTEXT_PAD_BYTES:
        raise ValueError("plaintext is already at or past the pad target")
    return data + b"\x00" * (_PLAINTEXT_PAD_BYTES - len(data))


def _unpad(data: bytes) -> bytes:
    """The inverse of `_pad`: everything up to the first `0x00` byte.

    Sound, not approximate: JSON's own grammar forbids a literal NUL byte
    anywhere in valid output -- every control character below `0x20`,
    NUL included, is escaped as `\u0000` rather than written raw (both
    `json.dumps` here and `JSON.stringify` in `encrypt.ts` do this by
    default) -- so the first `0x00` byte in a decrypted plaintext can only
    ever be padding, never content. A plaintext with no `0x00` at all
    (unpadded, e.g. an older wire-format entry) round-trips unchanged:
    `bytes.split` on an absent separator returns the whole input.
    """
    return data.split(b"\x00", 1)[0]


def _to_plaintext(response: SurveyResponse) -> bytes:
    """The inverse of `to_survey_response`'s field extraction -- the JSON
    `add_response` encrypts afresh for storage, and the same bytes
    `to_survey_response`'s own length check below measures before
    accepting a response at all. Parsed back through `json.loads`, never by
    position, so field order here does not have to match anything; only the
    same three keys have to round trip.

    `ensure_ascii=False`: the default flips every
    non-ASCII character to a `\\uXXXX` escape -- six bytes for a BMP
    character, twelve for an astral one via a surrogate pair -- while
    `encrypt.ts`'s `JSON.stringify` leaves non-ASCII as itself, at most 4
    UTF-8 bytes per character. `_PLAINTEXT_PAD_BYTES`'s own sizing
    (`4 * 2000 + 100 = 8100`) was always computed on that 4-byte
    assumption; with the default `ensure_ascii=True` here, Python alone
    could produce up to `12 * 2000 = 24000` bytes for the same
    `_MAX_FEEDBACK_LENGTH`-length answer, silently breaking the assumption
    the pad target was sized against. `ensure_ascii=False` makes both
    languages measure the same bytes for the same characters, which is
    what the two encoders have to do to agree at all (D-14) -- not an
    optimisation, the fix.
    """
    return json.dumps(
        {
            "overall_rating": response.overall_rating,
            "recommend": response.recommend,
            "feedback": response.feedback,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def to_survey_response(ciphertext: str, private_pem: str) -> SurveyResponse | None:
    """Decrypt one submitted envelope into a `SurveyResponse`, or `None`.

    `ciphertext` is the *whole* relayed payload -- `{event_id, v,
    encrypted_key, iv, ciphertext}` -- exactly as
    `registration.to_registration` reads it; see that function's own
    docstring for why passing the payload through whole, rather than
    stripping `event_id` first, is correct rather than merely convenient.

    `None` covers everything that can go wrong, uniformly, the same
    reasoning `registration.to_registration` gives for its own uniform
    `None`: a ciphertext that does not decrypt at all, a plaintext that is
    not the JSON object this module writes, a field missing, extra, or of
    the wrong type, a rating outside `[1, 5]`, feedback text longer than
    `_MAX_FEEDBACK_LENGTH` once stripped in code points, or a response
    whose re-encoded bytes would not fit
    `_PLAINTEXT_PAD_BYTES` once re-serialised for storage. That last check
    exists because `_MAX_FEEDBACK_LENGTH` bounds *characters*, not bytes:
    a script where each character costs up to 4 UTF-8 bytes (most non-Latin
    scripts, all emoji) can pass the character cap while still not fitting
    the pad target `add_response` re-encrypts into, and `_pad` itself
    raises rather than truncates on overflow (see its own docstring) -- a
    guard that can throw past its caller is not a guard, so this function
    checks the exact bytes `_to_plaintext` will produce, here, and refuses
    with the same uniform `None` every other rejection in this function
    uses, before `add_response` ever runs. This is the first code that
    ever reads what a stranger encrypted with a *public* key, so every
    failure is untrusted input, never a bug worth raising on.
    """
    try:
        plaintext = eventkeys.decrypt(private_pem, ciphertext)
    except eventkeys.DecryptionError:
        return None

    try:
        data: Any = json.loads(_unpad(plaintext))
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Same reasoning as registration.to_registration's identical guard:
        # `UnicodeDecodeError.object` is the plaintext itself and must never
        # be logged, formatted, or passed to anything that might print it.
        return None
    if not isinstance(data, dict) or set(data) != _FIELDS:
        return None

    rating = data["overall_rating"]
    # bool is a subclass of int in Python; True/False must not pass as 1/0
    # here, the same guard registration.py and validate.py both apply to
    # every integer field a stranger could submit.
    if isinstance(rating, bool) or not isinstance(rating, int):
        return None
    if not (_RATING_MIN <= rating <= _RATING_MAX):
        return None

    if not isinstance(data["recommend"], bool):
        return None

    feedback = data["feedback"]
    if not isinstance(feedback, str):
        return None
    feedback = feedback.strip()
    if len(feedback) > _MAX_FEEDBACK_LENGTH:
        return None

    candidate = SurveyResponse(
        overall_rating=rating,
        recommend=data["recommend"],
        feedback=feedback,
    )
    # The character cap above is not a byte cap -- see
    # this function's own docstring. `>=`, not `>`, to match `_pad`'s own
    # boundary exactly: `_pad` raises at `>= _PLAINTEXT_PAD_BYTES`, so this
    # must refuse at that same boundary for `_pad` to never be reachable
    # with an over-target plaintext from here.
    if len(_to_plaintext(candidate)) >= _PLAINTEXT_PAD_BYTES:
        return None

    return candidate


@dataclass(frozen=True)
class ResponseFile:
    """`survey-responses.enc`'s in-memory shape: the entries. (This
    dataclass carries `entries` only -- the file's own `"v"`
    key is a module constant, `FILE_VERSION`, supplied by
    `dump_response_file` on the way out and checked by `load_response_file`
    on the way in; it is never stored on this object.) Every entry is a
    `dict` carrying exactly `eventkeys`'s wire-format keys -- see the
    module docstring for why one independent envelope per entry, not one
    envelope for the whole file."""

    entries: tuple[Mapping[str, Any], ...] = ()


def load_response_file(text: str | None) -> ResponseFile:
    """Parse `survey-responses.enc`, or start empty when `text` is `None`
    -- the event's first response, which finds no file on disk yet.

    Raises `ValueError` on anything committed that is not this format --
    the same "a missing file is normal, a malformed one is not" discipline
    `registration.load_registration_file` holds itself to.
    """
    if text is None:
        return ResponseFile()
    data: Any = json.loads(text)
    if not isinstance(data, dict) or data.get("v") != FILE_VERSION:
        raise ValueError("survey-responses.enc is not a supported format version")
    entries = data.get("responses")
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise ValueError("survey-responses.enc is malformed")
    # Every entry's key set must be exactly the wire format's four fields --
    # the structural guard against a "helpful" extra field sitting in plain
    # sight beside the ciphertext it was meant to replace, mirroring
    # registration.load_registration_file's identical check.
    if not all(set(e) == eventkeys.ENVELOPE_FIELDS for e in entries):
        raise ValueError(
            "survey-responses.enc holds an entry that is not exactly ciphertext"
        )
    return ResponseFile(entries=tuple(entries))


def dump_response_file(file: ResponseFile) -> str:
    """The bytes `survey-responses.enc` is written as: stable structure,
    two-space indent, one trailing newline -- the same shape
    `registration.dump_registration_file` writes its own file as."""
    return (
        json.dumps({"v": FILE_VERSION, "responses": list(file.entries)}, indent=2)
        + "\n"
    )


def add_response(
    file: ResponseFile, response: SurveyResponse, *, private_pem: str
) -> ResponseFile:
    """Append `response` to `file` as a fresh, independently encrypted
    entry -- never an upsert, because nothing here identifies "the same
    person came back" (see the module docstring's "Why no identity travels
    with a response"). Every existing entry survives byte for byte: this
    function only ever adds one new dict to the end of the tuple, never
    touches, re-encrypts or reorders anything already there.

    There is no `public_pem` parameter, for the same reason
    `registration.upsert` has none: the re-encryption key is
    `eventkeys.derive_public_pem(private_pem)`, the public half that
    mathematically matches the private key this call already needs to have
    been handed to decrypt the incoming submission in the first place --
    never whatever happens to be committed at `keys/events/<id>.pub`.

    The plaintext is padded to `_PLAINTEXT_PAD_BYTES` before encryption:
    re-encrypting for storage is exactly the moment this module
    controls the plaintext going into AES-GCM, so it is also the moment
    that fixes the stored ciphertext's length regardless of what
    `response.feedback` holds.
    """
    new_entry: dict[str, Any] = json.loads(
        eventkeys.encrypt(
            eventkeys.derive_public_pem(private_pem), _pad(_to_plaintext(response))
        )
    )
    return ResponseFile(entries=(*file.entries, new_entry))
