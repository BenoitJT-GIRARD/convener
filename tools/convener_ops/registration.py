"""Turn one decrypted registration into a stored, re-encrypted record.

Phase 4's whole design (see the phase 4 spec, S:3-4, and
`tools/convener_ops/eventkeys.py`'s module docstring) rests on plaintext existing
in exactly one place: the memory of the CI job this module's functions run
inside. `to_registration` is the only place a submitted envelope is ever
turned into names an operator could read; every function below it either
stays inside that same job's memory or hands back ciphertext, never the
fields themselves. Nothing here touches the filesystem or the environment --
that belongs to `cli.py`, the same split `eventkeys.py` keeps.

The file shape, and why it is not one envelope for the whole event
--------------------------------------------------------------------
`data/events/<id>/registrations.enc` is one JSON object::

    {"v": 1, "registrations": [ {<envelope>}, {<envelope>}, ... ]}

where each `<envelope>` is exactly one call to `eventkeys.encrypt`'s output
-- its own AES-256 key, its own nonce -- decoded back to a `dict` rather
than kept as the nested, escaped JSON string `encrypt` returns, so the file
reads as ordinary JSON, not JSON wrapped inside JSON.

The alternative -- one envelope wrapping the *whole list* -- was rejected
for a reason that only shows up three tasks from now: erasure. The phase 4
spec (S:4) requires a single registration to be removable before the
retention window ends, "sans reecriture d'historique", but says nothing
about what happens to *everyone else's* ciphertext while that happens. If
the whole file were one envelope, erasing one person would mean decrypting
every registration, dropping one, and re-encrypting the rest under a fresh
AES key and nonce -- every remaining registrant's bytes on disk would
change for an erasure that named only one of them. With one independent
envelope per registration, erasure is deleting one array element and
rewriting the file: every other entry's `encrypted_key`, `iv` and
`ciphertext` stay byte for byte what they already were. Task 15 builds that
procedure; this shape is what makes it possible without re-touching a
stranger's ciphertext to reach it.

The same independence is what deduplication needs, from the other
direction: replacing one person's entry (`upsert`, below) touches only that
entry's own three fields, never anyone else's. On disk, an update is
indistinguishable from that person having been the only one who ever
registered.

No stored identifier for "whose entry is this"
--------------------------------------------------
An entry carries nothing naming whose record it is -- no id, no salted
lookup key, nothing derived from the address at all. Storing one would be
exactly the kind of address-shaped fact this file exists to avoid holding,
salted or not: a fingerprint that never changes is still a stable handle on
"the same person came back", readable by anyone who can read the file's
structure even without the private key. Finding "is this the same address
as an existing entry" instead means decrypting each existing entry with the
private key this job already holds (it needs it to decrypt the incoming
submission anyway) and comparing plaintext addresses in memory -- see
`upsert`. That costs one RSA-OAEP decrypt per existing registration for
every new submission; at the signup relay's own per-event ceiling
(`services/signup-relay/src/index.js::PER_EVENT_CEILING`, 500) that is at
most 500 decrypts in one job run, milliseconds each -- cheap next to a file
that would otherwise leak "who resubmitted" to a reader who never held the
key.

`matching_code` needs none of this stored either: it is a pure function of
the event id, the address and a salt (see its own docstring), so a resend
recomputes exactly the same code from exactly the same three inputs, and
nothing here ever writes it down.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Final

from . import eventkeys

#: `registrations.enc`'s own format version -- the file-level analogue of
#: `eventkeys.WIRE_VERSION`, in case the file's shape (not the envelope
#: inside it) ever has to change.
FILE_VERSION: Final = 1


@dataclass(frozen=True)
class Registration:
    """What a participant supplies, and nothing else (phase 4 spec, S:3).
    Mirrors `app/src/signup/encrypt.ts`'s `Registration` interface field for
    field -- that is the shape the browser encrypts, so it is the shape
    `to_registration` has to recover.

    `email` is stored exactly as submitted, not normalised: normalisation
    (`_normalize_email`) exists only for *comparing* and *hashing* an
    address, in `upsert` and `matching_code`, never for what a person reads
    back."""

    first_name: str
    surname: str
    email: str
    institution: str
    membership_opt_in: bool


#: The exact field set `Registration` and the browser's `encryptRegistration`
#: agree on. `to_registration` requires the incoming plaintext to match this
#: set exactly -- no field missing, none extra -- the same "closed shape"
#: discipline `services/signup-relay/src/index.js::validatedEventId` applies
#: to the envelope one layer out.
_FIELDS: Final = frozenset(
    {"first_name", "surname", "email", "institution", "membership_opt_in"}
)
_STRING_FIELDS: Final = ("first_name", "surname", "email", "institution")


def _normalize_email(email: str) -> str:
    """The form `upsert` and `matching_code` both compare or hash an address
    by. Local-part case is technically significant per RFC 5321, but no
    mail provider in practice treats it that way, and a participant who
    resubmits with different capitalisation -- an autocapitalising phone
    keyboard is a common cause -- is still the same registrant, not a
    second one. The value stored on `Registration.email` is never passed
    through this; only comparisons and the matching-code derivation are."""
    return email.strip().lower()


def to_registration(ciphertext: str, private_pem: str) -> Registration | None:
    """Decrypt one submitted envelope into a `Registration`, or `None`.

    `ciphertext` is the *whole* relayed payload -- `{event_id, v,
    encrypted_key, iv, ciphertext}`, exactly what
    `services/signup-relay/src/index.js` forwards untouched -- not a value
    stripped of `event_id` first: `eventkeys.decrypt` only ever reads the
    four fields its own wire format defines and ignores anything else in
    the object, so passing the payload straight through is correct, not
    merely convenient.

    `None` covers everything that can go wrong, uniformly: a ciphertext
    that does not decrypt at all (`eventkeys.DecryptionError` -- wrong key,
    wrong event, tampered, truncated), a plaintext that is not the JSON
    object this module writes, one with a field missing, extra, or of the
    wrong type, or one whose required text is empty once whitespace is
    stripped. This function is the first code that ever reads what a
    stranger encrypted with a *public* key -- anyone who knows an event's
    id can produce a syntactically valid envelope carrying anything at all
    -- so every one of those causes is treated as untrusted input, never as
    a bug worth raising on. Nothing here raises for a malformed submission;
    only `eventkeys.decrypt`'s own `DecryptionError` is caught, and only
    that one.
    """
    try:
        plaintext = eventkeys.decrypt(private_pem, ciphertext)
    except eventkeys.DecryptionError:
        return None

    try:
        data: Any = json.loads(plaintext)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or set(data) != _FIELDS:
        return None
    for name in _STRING_FIELDS:
        if not isinstance(data[name], str):
            return None
    if not isinstance(data["membership_opt_in"], bool):
        return None

    first_name = data["first_name"].strip()
    surname = data["surname"].strip()
    email = data["email"].strip()
    institution = data["institution"].strip()
    if not first_name or not surname or "@" not in email:
        return None

    return Registration(
        first_name=first_name,
        surname=surname,
        email=email,
        institution=institution,
        membership_opt_in=data["membership_opt_in"],
    )


def _to_plaintext(registration: Registration) -> bytes:
    """The inverse of `to_registration`'s field extraction -- the JSON
    `upsert` encrypts afresh for storage. `to_registration` parses this
    through `json.loads`, never by position, so field order here does not
    have to match anything; only the same five keys have to round trip."""
    return json.dumps(
        {
            "first_name": registration.first_name,
            "surname": registration.surname,
            "email": registration.email,
            "institution": registration.institution,
            "membership_opt_in": registration.membership_opt_in,
        },
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class RegistrationFile:
    """`registrations.enc`'s in-memory shape: a version and the entries.
    Every entry is a `dict` carrying exactly `eventkeys`'s wire-format keys
    (`v`, `encrypted_key`, `iv`, `ciphertext`) -- see the module docstring
    for why it is not a bespoke class: `eventkeys.py` itself never wraps
    its own envelope in one either, it hands back the `dict` `json.loads`
    gives."""

    entries: tuple[Mapping[str, Any], ...] = ()


def load_registration_file(text: str | None) -> RegistrationFile:
    """Parse `registrations.enc`, or start empty when `text` is `None` --
    the event's first registration, which finds no file on disk yet.

    Raises `ValueError` on anything committed that is not this format:
    unlike a missing file, a *malformed* one is not a normal state for this
    function to paper over silently."""
    if text is None:
        return RegistrationFile()
    data: Any = json.loads(text)
    if not isinstance(data, dict) or data.get("v") != FILE_VERSION:
        raise ValueError("registrations.enc is not a supported format version")
    entries = data.get("registrations")
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise ValueError("registrations.enc is malformed")
    return RegistrationFile(entries=tuple(entries))


def dump_registration_file(file: RegistrationFile) -> str:
    """The bytes `registrations.enc` is written as: stable structure,
    two-space indent, one trailing newline -- readable in a diff, the same
    reason `cli.py::_dump` formats `speakers.yml` deliberately rather than
    however a library default would."""
    return (
        json.dumps({"v": FILE_VERSION, "registrations": list(file.entries)}, indent=2)
        + "\n"
    )


def upsert(
    file: RegistrationFile,
    registration: Registration,
    *,
    public_pem: str,
    private_pem: str,
) -> tuple[RegistrationFile, bool]:
    """Insert `registration` into `file`, replacing any existing entry for
    the same address rather than adding a second one (plan step 3: same
    address, same event, the second submission updates the first).

    Returns the updated file and whether an entry was replaced (`True`) as
    opposed to appended (`False`) -- for the caller's own log line, which
    never carries anything address-shaped either way.

    Every entry, kept or freshly written, is its own independent
    `eventkeys.encrypt` call -- see the module docstring for why: an update
    re-encrypts only the one entry that changed, at a fresh AES key and
    nonce, and every other entry survives byte for byte. Finding the entry
    to replace means decrypting each existing one with `private_pem` -- the
    same key this call already needs to encrypt the new entry -- and
    comparing normalised addresses in memory; the loop stops decrypting
    further entries the moment a match is found, since only one can ever
    exist (this same function is what keeps a second from ever being
    written).

    A resend never changes `matching_code(event_id, registration.email,
    salt)`: it is a pure function of the address, and the address does not
    change on an update, so nothing here computes, compares, or carries a
    code at all -- see that function's own docstring.
    """
    new_entry: dict[str, Any] = json.loads(
        eventkeys.encrypt(public_pem, _to_plaintext(registration))
    )
    target = _normalize_email(registration.email)

    kept: list[Mapping[str, Any]] = []
    replaced = False
    for entry in file.entries:
        existing = None if replaced else to_registration(json.dumps(entry), private_pem)
        if existing is not None and _normalize_email(existing.email) == target:
            kept.append(new_entry)
            replaced = True
        else:
            kept.append(entry)
    if not replaced:
        kept.append(new_entry)
    return RegistrationFile(entries=tuple(kept)), replaced


#: The alphabet a matching code is drawn from: digits 2-9 and every
#: uppercase letter except I, L and O -- the pairs a spoken or handwritten
#: code is classically confused on (0/O, 1/I/l). 31 symbols; see
#: `matching_code` for why 8 of them, in two groups, is enough.
_CODE_ALPHABET: Final = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_CODE_SYMBOLS: Final = 8
_CODE_GROUP: Final = 4


def matching_code(event_id: str, email: str, salt: str | None) -> str | None:
    """A short, spoken-safe code identifying one registration -- read aloud
    or typed into a display name when joining (phase 4 spec, S:5), never
    stored: the same three inputs always derive the same code, so a resend
    of the confirmation email (task 7) needs nothing on disk to repeat it.

    `None` when `salt` is not set. Unlike an event's own encryption key
    (`eventkeys.py`), an absent salt is an *ordinary* D-13 state here:
    nothing has to fail closed, because the cascade the phase 4 spec names
    (S:5 -- exact address, then normalised name) still works with no code
    at all. See the `matching_salt` row in `config/integrations.yml`. A
    caller with no code to send falls back to describing that cascade
    instead, which is task 7's decision, not this function's.

    The alphabet drops the pairs a spoken or handwritten code confuses --
    `0`/`O`, `1`/`I`/`l` -- leaving 31 symbols. 8 of them, in two groups of
    four, give `31**8` (about 8.5e11) possible codes for one event: at the
    signup relay's own per-event ceiling of 500 registrations
    (`services/signup-relay/src/index.js::PER_EVENT_CEILING`), the chance
    any two collide is negligible even though each symbol comes from one
    HMAC byte reduced modulo 31, which is not perfectly uniform -- that does
    not matter for a display code whose unforgeability already comes from
    the salted HMAC underneath it, not from the mapping onto this alphabet.

    Salted, not constant: a code anyone could derive from an address alone
    would prove nothing about who holds that address -- see `matching_salt`
    in `config/integrations.yml` for why this secret exists at all.
    `_normalize_email` keeps the same property `upsert` relies on: two
    submissions of the same address, differently capitalised, still derive
    one code, matching `upsert`'s own notion of "the same registration".
    """
    if not salt:
        return None
    digest = hmac.new(
        salt.encode("utf-8"),
        f"{event_id}\0{_normalize_email(email)}".encode(),
        sha256,
    ).digest()
    symbols = "".join(
        _CODE_ALPHABET[byte % len(_CODE_ALPHABET)] for byte in digest[:_CODE_SYMBOLS]
    )
    return "-".join(
        symbols[i : i + _CODE_GROUP] for i in range(0, len(symbols), _CODE_GROUP)
    )


def event_id_from_payload(payload: str) -> str | None:
    """The `event_id` field of a raw registration dispatch payload -- the
    same JSON string `to_registration` also reads in full as `ciphertext`
    (its own `event_id` key is simply ignored there).

    `None` for anything not shaped like a genuine dispatch payload: absent,
    not JSON, not an object, or an `event_id` that `eventkeys.secret_name`
    itself would refuse -- so a malformed or hostile payload is turned away
    before any private key is looked up, reusing the validation
    `secret_name` already has to do rather than keeping a second copy of
    it.
    """
    try:
        data: Any = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    event_id = data.get("event_id")
    if not isinstance(event_id, str):
        return None
    try:
        eventkeys.secret_name(event_id)
    except ValueError:
        return None
    return event_id
