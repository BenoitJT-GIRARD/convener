"""Turn one decrypted registration into a stored, re-encrypted record.

This project's whole registration design (see
`tools/convener_ops/eventkeys.py`'s module docstring) rests on plaintext existing
in exactly one place: the memory of the CI job this module's functions run
inside. `to_registration` is the only place a submitted envelope is ever
turned into names an operator could read; every function below it either
stays inside that same job's memory or hands back ciphertext, never the
fields themselves. Nothing here touches the filesystem or the environment --
that belongs to `cli.py`, the same split `eventkeys.py` keeps.

The file shape, and why it is not one envelope for the whole event
--------------------------------------------------------------------
`instance/data/events/<id>/registrations.enc` is one JSON object::

    {"v": 1, "registrations": [ {<envelope>}, {<envelope>}, ... ]}

where each `<envelope>` is exactly one call to `eventkeys.encrypt`'s output
-- its own AES-256 key, its own nonce -- decoded back to a `dict` rather
than kept as the nested, escaped JSON string `encrypt` returns, so the file
reads as ordinary JSON, not JSON wrapped inside JSON.

The alternative -- one envelope wrapping the *whole list* -- was rejected
for a reason that only shows up later: erasure. A single registration has
to be removable before the
retention window ends, without rewriting history, and nothing says
about what happens to *everyone else's* ciphertext while that happens. If
the whole file were one envelope, erasing one person would mean decrypting
every registration, dropping one, and re-encrypting the rest under a fresh
AES key and nonce -- every remaining registrant's bytes on disk would
change for an erasure that named only one of them. With one independent
envelope per registration, erasure is deleting one array element and
rewriting the file: every other entry's `encrypted_key`, `iv` and
`ciphertext` stay byte for byte what they already were. This shape is what
makes that procedure possible without re-touching a
stranger's ciphertext to reach it.

The same independence is what deduplication needs, from the other
direction: replacing one person's entry (`upsert`, below) touches only that
entry's own three fields, never anyone else's -- no other entry is
re-encrypted, moved, or so much as re-serialised. That is not the same as
"an update is invisible": the entry keeps its array position, so a reader
of the commit history (never the private key) can still see which position
was rewritten and when, which is a stable positional handle on "the same
person came back" -- the residual this design accepts, named rather than
denied, in exchange for never storing anything derived from the address
itself.

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

A length cap, and why it is a threat-model line, not a data-quality one
--------------------------------------------------------------------------
The signup relay is a way to make the organisation's own mailbox deliver
text to an arbitrary address. `to_registration` is the first and only gate
a submission passes before `confirmation.compose` writes `first_name`
straight into
`Dear {name},`, and, before this, that gate checked *shape* only --
present, a string, non-empty after stripping -- never *size*.
`services/signup-relay/src/index.js::MAX_CIPHERTEXT_BYTES` allows 16 KB of
ciphertext per submission, and `PER_EVENT_CEILING`/its burst limiter do not
bound the length of any one field inside it, only how often a submission
can be made. So anyone who knows a published event id could already,
before this cap, have every field padded out to most of that budget,
addressed to any string containing `@`, delivered by the organisation's
real mailbox -- a reputation and phishing exposure the relay creates and
nothing else in this project does.

`_MAX_FIELD_LENGTH` closes it the same way every other malformed-shape
case in this function is refused: silently, by `to_registration` returning
`None`, exactly as an empty name already does. 200 characters is generous
for a real first name, surname or institution (the longest is refused, not
truncated -- truncating would still deliver an attacker's text, only
shorter) and small enough that even a submission built entirely of
near-maximum fields cannot come close to `MAX_CIPHERTEXT_BYTES`. It is not
a data-quality rule -- nothing here should second-guess a genuine name --
it is a bound on how much of a stranger's text this project's own mailbox
will ever be made to carry.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote

from . import eventkeys
from .declaration import published

#: `registrations.enc`'s own format version -- the file-level analogue of
#: `eventkeys.WIRE_VERSION`, in case the file's shape (not the envelope
#: inside it) ever has to change.
FILE_VERSION: Final = 1

#: The base of the one address that reaches this whole feature:
#: before this constant existed, nothing in the repository
#: -- no document, no template, no other constant -- carried
#: `#/signup/<event id>` at all, while the two public announcement
#: templates (`docs/toolkit/forum-post-announce.md`,
#: `docs/toolkit/linkedin-post.md`) published the meeting room link under
#: the word "Registration" instead. That both contradicted
#: `docs/toolkit/emails/registration-confirmed.md`'s own pinned claim that
#: the room link "is not otherwise published", and meant nobody could ever
#: reach the page `certificate.VERIFICATION_BASE` and `survey_invite.
#: SURVEY_BASE` already treat as this project's third public address.
#:
#: **A correction:** this once reasoned there was "no established
#: mapping from a Speaker record to the event id" and, on that basis,
#: published `SIGNUP_BASE` in both public templates with a hand-filled
#: `<event id>` placeholder. That was wrong. The mapping exists and is a
#: decided rule of this project -- `platform.py::find_speaker`:
#: "`event_id` is `edition_code`, lower-cased. Nothing else..." What
#: `eventkeys.py`'s module docstring says ("no `Identifier` type exists
#: yet") is a claim about a missing *type*, not about the mapping. A
#: Speaker record's own `edition_code` is exactly what that rule needs, and
#: `signup_url` below computes the same address `verification_url` and
#: `survey_url` already compute for their own bases. The two public
#: announcement templates now publish `{{ speaker.signup_link }}`, a value
#: `app/src/content/render.ts` derives the same way it already derives
#: `speaker.first_name` -- lower-casing `edition_code` itself,
#: since `find_speaker` expects its `event_id` argument already lower-case
#: and does not do that step for a caller. The rule crosses both
#: languages, so `tools/tests/fixtures/signup-link.json` binds it with a
#: shared, worked fixture -- deliberately holding a mixed-case
#: `edition_code` (`MRG-4` lower-cases to `mrg-4`), the same D-14 discipline
#: `certificate-verification.json` and `governance-cases.json` already
#: apply, rather than two constants trusted to agree.
#:
#: **A second correction:** this used to end `app/#/signup/`, a
#: `HashRouter` fragment matching `app/src/App.tsx`'s own
#: `path="/signup/:eventId"` -- the same convention `survey_invite.
#: SURVEY_BASE` still uses for its own address (`certificate.
#: VERIFICATION_BASE` used to as well -- see that constant's
#: own comment for why its own move looked different from this one).
#: Registration moved out of that application entirely, onto an island
#: mounted on the public event page (D-18); this now targets that page's
#: own, real address instead -- `site/src/event.njk`'s permalink,
#: `/events/<event id>/` (D-19) -- a server path this time, not a
#: fragment, since the site itself is what GitHub Pages serves at that
#: path. `test_workflows.py` pins the shape against `event.njk`'s own
#: permalink expression. Unlike `certificate.VERIFICATION_BASE`, dropping
#: the fragment here is safe: `signup_url` carries only an event id, never
#: a name.
#:
#: The host and prefix used to be typed in here, and
#: bound by test to the same address written out in eleven other files.
#: They now come from `instance/config.json` through `published.load()` --
#: one declaration, read from each side of the language boundary (D-14).
#: `events/` stays here: that segment is the *product's* own route shape,
#: inherited by every duplicate, not something an instance configures.
SIGNUP_BASE: Final = published.load().under("events/")


def signup_url(event_id: str, *, root: Path | None = None) -> str:
    """The one link a participant follows to register for `event_id` --
    the address of that event's own public page
    (`site/src/event.njk`'s permalink, D-19), which carries the
    registration island. Expects `event_id` already
    lower-cased (`platform.py::find_speaker`), the same contract
    `certificate.verification_url` and `survey_invite.survey_url` hold for
    their own bases; this function does not lower-case it itself. No
    Python caller invokes this today -- a registration confirmation email
    carries the room link a participant already reached, not the signup
    link that got them there -- but `render.ts`'s own `signup_link`
    derivation needs a Python-side value to be bound against, the same way
    `test_survey_invite.py` and `test_certificate.py` bind their own
    `_url` functions, so this exists to be that value rather than to be
    called from `cli.py`.

    `root` names the repository whose declaration the address is built
    from, and defaults to this one's -- `SIGNUP_BASE`, resolved once at
    import. It exists for the one caller that renders *as a different
    instance* inside this process: `visual.render_announcement` already
    takes a `root` for the charter, and a poster wearing one instance's
    colours under a QR code pointing at another instance's site is a
    disagreement nothing else would catch -- a QR code is bytes, and no
    text sweep reads it (`test_second_instance.py`, "Bytes"). Passing
    the same root to both is what keeps the poster one thing.
    """
    base = SIGNUP_BASE if root is None else published.load(root).under("events/")
    return f"{base}{quote(event_id, safe='')}/"


@dataclass(frozen=True)
class Registration:
    """What a participant supplies, and nothing else.
    Mirrors `app/src/signup/encrypt.ts`'s `Registration` interface field for
    field -- that is the shape the browser encrypts, so it is the shape
    `to_registration` has to recover.

    `email` is stored exactly as submitted, not normalised: normalisation
    (`normalize_email`) exists only for *comparing* and *hashing* an
    address, in `upsert`, `find_by_email` and `matching_code`, never for
    what a person reads back."""

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

#: The reputation-exposure bound the module docstring's "A length cap"
#: section explains. Applied to every string field after stripping, so a
#: field padded out with leading/trailing whitespace does not dodge it.
_MAX_FIELD_LENGTH: Final = 200


def normalize_email(email: str) -> str:
    """The form `upsert`, `find_by_email` and `matching_code` all compare or
    hash an address by. Local-part case is technically significant per RFC
    5321, but no mail provider in practice treats it that way, and a
    participant who resubmits with different capitalisation -- an
    autocapitalising phone keyboard is a common cause -- is still the same
    registrant, not a second one. The value stored on `Registration.email`
    is never passed through this; only comparisons and the matching-code
    derivation are.

    Public rather than module-private: the confirmation module needs
    the identical rule to decide whether an update changed the *address
    itself* (see `find_by_email`'s docstring) -- a second, hand-written
    definition of "the same address" here would risk disagreeing with this
    one about a case `upsert` already treats as a match."""
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
    wrong type, one whose required text is empty once whitespace is
    stripped, or one where any string field is longer than
    `_MAX_FIELD_LENGTH` once stripped (see the module docstring's "A length
    cap" section -- this is a reputation bound, not a data-quality check).
    This function is the first code that ever reads what a stranger
    encrypted with a *public* key -- anyone who knows an event's id can
    produce a syntactically valid envelope carrying anything at all -- so
    every one of those causes is treated as untrusted input, never as a
    bug worth raising on. Nothing here raises for a malformed submission;
    only `eventkeys.decrypt`'s own `DecryptionError` is caught, and only
    that one.
    """
    try:
        plaintext = eventkeys.decrypt(private_pem, ciphertext)
    except eventkeys.DecryptionError:
        return None

    try:
        data: Any = json.loads(plaintext)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # `json.loads` on `bytes` decodes as UTF-8 first and raises
        # `UnicodeDecodeError`, not `JSONDecodeError`, for plaintext that is
        # not valid UTF-8 -- a real case here, not a hypothetical: the
        # public key anyone can encrypt under makes the *decrypted* bytes
        # exactly as untrusted as the ciphertext was. Caught alongside
        # `JSONDecodeError` rather than separately, because both mean the
        # same thing to this function's caller: not a registration.
        # `UnicodeDecodeError.object` is the plaintext itself, so this is
        # also the one exception in this function that must never be
        # logged, formatted, or passed to anything that might print it.
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
    if any(
        len(value) > _MAX_FIELD_LENGTH
        for value in (first_name, surname, email, institution)
    ):
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
    # Every entry's key set must be exactly the wire format's four fields --
    # nothing more. This is the structural guard against the entry this file
    # exists to make impossible: a "helpful" extra field such as a cleartext
    # lookup key sitting in plain sight beside the ciphertext it was meant to
    # replace. A test can be forgotten; this runs on every load, including
    # the retention sweep's own read for erasure.
    if not all(set(e) == eventkeys.ENVELOPE_FIELDS for e in entries):
        raise ValueError(
            "registrations.enc holds an entry that is not exactly ciphertext"
        )
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

    There is no `public_pem` parameter: the re-encryption key is
    `eventkeys.derive_public_pem(private_pem)`, the public half that
    mathematically matches the private key this call already needs --
    never whatever happens to be committed at `instance/keys/events/<id>.pub`,
    which could in principle be stale, mid-rotation, or simply the wrong
    file. See `derive_public_pem`'s own docstring.

    A resend never changes `matching_code(event_id, registration.email,
    salt)`: it is a pure function of the address, and the address does not
    change on an update, so nothing here computes, compares, or carries a
    code at all -- see that function's own docstring.
    """
    new_entry: dict[str, Any] = json.loads(
        eventkeys.encrypt(
            eventkeys.derive_public_pem(private_pem), _to_plaintext(registration)
        )
    )
    target = normalize_email(registration.email)

    kept: list[Mapping[str, Any]] = []
    replaced = False
    for entry in file.entries:
        existing = None if replaced else to_registration(json.dumps(entry), private_pem)
        if existing is not None and normalize_email(existing.email) == target:
            kept.append(new_entry)
            replaced = True
        else:
            kept.append(entry)
    if not replaced:
        kept.append(new_entry)
    return RegistrationFile(entries=tuple(kept)), replaced


def find_by_email(
    file: RegistrationFile, email: str, private_pem: str
) -> Registration | None:
    """The existing entry addressed to `email` (case/whitespace-insensitive,
    via `normalize_email`), or `None` -- the same question `upsert` already
    answers internally to decide what to replace, exposed here so a caller
    can ask it about a file's state *before* calling `upsert`, which is
    exactly what the confirmation email needs: `upsert` overwrites
    the matched entry, so the *prior* `Registration` -- to say what changed
    -- has to be read out first, from the same file, under the same
    key, using the same notion of "the same registrant" `upsert` uses. A
    second, hand-written comparison here would risk drifting from that one.

    Decrypts entries in order and stops at the first match, the same
    early-exit `upsert`'s own loop performs; an entry that fails to decrypt
    under `private_pem` is skipped rather than treated as a match, mirroring
    `upsert`'s own handling of a stray undecryptable entry.

    Costs what `upsert`'s own module-docstring section already prices --
    up to 500 RSA-OAEP decrypts, milliseconds each -- and `cli.py`'s
    `handle_registration` calls this immediately before `upsert`, so one
    submission now pays that cost twice, roughly a thousand decrypts at
    the relay's per-event ceiling. Still cheap
    against the ten-minute job timeout; noted here rather than optimised
    away, because the alternative -- one combined find-and-replace pass --
    would have `upsert` hand back the entry it is about to overwrite,
    which is a real API change nothing here needs.
    """
    target = normalize_email(email)
    for entry in file.entries:
        existing = to_registration(json.dumps(entry), private_pem)
        if existing is not None and normalize_email(existing.email) == target:
            return existing
    return None


def erase(
    file: RegistrationFile, email: str, private_pem: str
) -> tuple[RegistrationFile, bool]:
    """Remove the one entry addressed to `email` from `file` -- the early
    erasure procedure: the encrypted file is rewritten without the record
    concerned, and nothing else moves.

    Returns the updated file and whether an entry was actually removed
    (`True`) as opposed to nothing matching (`False`) -- `cli.py` reports
    the second case as "no registration found", the same shape
    `find_by_email` already has no match for.

    This is `upsert`'s own replace loop with the matched entry dropped
    instead of swapped in: it walks `file.entries` once, decrypts each one
    with `private_pem` to find the single entry whose address normalises
    to `email` (the same "the same registrant" rule `upsert` and
    `find_by_email` already use), and keeps every other entry exactly as
    found -- not re-serialised, not touched. That is the property the
    module docstring's own reasoning for one envelope per registration
    exists to buy (see "The file shape, and why it is not one envelope for
    the whole event"): erasing Grace must not so much as re-encrypt Ada's
    or Marie's entry, the same guarantee `upsert` already gives an update,
    now given to a removal. Stops decrypting further entries once the
    target is found, the same early exit `upsert`'s own loop already
    performs, since only one entry can ever match one address.

    An entry this function cannot decrypt under `private_pem` (a stray
    entry from another event's key, in practice unreachable, or genuinely
    corrupt data) is kept exactly as found and never treated as a match --
    the same defensive handling `upsert` and `find_by_email` already give
    an undecryptable entry."""
    target = normalize_email(email)
    kept: list[Mapping[str, Any]] = []
    removed = False
    for entry in file.entries:
        existing = None if removed else to_registration(json.dumps(entry), private_pem)
        if (
            not removed
            and existing is not None
            and normalize_email(existing.email) == target
        ):
            removed = True
            continue
        kept.append(entry)
    return RegistrationFile(entries=tuple(kept)), removed


class AmbiguousMatchingCodeError(Exception):
    """Raised by `find_by_matching_code` when more than one entry's own
    code collides with the one supplied.

    `matching_code`'s own docstring prices this at about 1.9e-7 at the
    signup relay's 500-per-event ceiling -- negligible, and a reviewer
    judged it not worth code for that reason. The ruling overriding that
    recommendation is that the probability is not the point: a collision
    erases the *wrong person's* data irreversibly, with no signal at all,
    if the first match is trusted. `attendance._settle` already refuses to
    resolve a tie by guessing, for exactly this reason (see its own
    docstring, "guessing" section) -- this is the same rule, for the same
    reason, at the one other place in this codebase two people's identity
    can collide.

    **Carries `tied`, every colliding `Registration`, because refusing is
    not always the right answer.** A collision on the code alone must
    refuse -- there is nothing else to go on, and picking one would be
    exactly the guess `attendance._settle` exists to prevent. But a
    requester may supply an encrypted address (`EMAIL_ENVELOPE`)
    alongside the code, and if that address picks out
    exactly one of the tied entries,
    using it is not guessing -- it is reading the evidence the requester
    actually gave us. Refusing anyway would deny erasure to someone who
    supplied more than enough to identify themselves, which is the
    opposite of what this rule is for. `cli.py::erase_registration` is the
    one caller that attempts this second-field resolution against `tied`;
    it still refuses if no address was given, or if the address given
    does not narrow `tied` to exactly one entry."""

    def __init__(self, message: str, *, tied: tuple[Registration, ...]) -> None:
        super().__init__(message)
        self.tied = tied


def find_by_matching_code(
    file: RegistrationFile, event_id: str, code: str, salt: str | None, private_pem: str
) -> Registration | None:
    """The entry whose own `matching_code(event_id, entry.email, salt)`
    equals `code`, or `None` -- the preferred way to identify one
    registration for an early erasure request: the code is already
    in the participant's own confirmation e-mail, never stored
    anywhere on our side, and naming it does not require the requester to
    retype an address into an operator-facing form.

    `code` is compared case-insensitively, stripped of surrounding
    whitespace first -- `matching_code` itself always renders uppercase,
    but a participant forwarding it by hand may not preserve that.
    `None` immediately when `salt` is falsy: with no salt, `matching_code`
    itself returns `None` for every entry, so nothing here could ever
    match, and there is no reason to decrypt the whole file to learn that
    (the same ordinary D-13 absence `matching_code`'s own docstring
    describes -- an early erasure by code simply cannot be resolved
    without it; `cli.py` falls back to the address instead, the
    documented exception).

    Raises `AmbiguousMatchingCodeError` if more than one entry's own code
    equals `code` -- refusing to guess which one was meant, rather than
    returning whichever happens to be stored first. This is why every
    entry is decrypted and compared rather than stopping at the first
    match: a second match later in the file must still be seen. An entry
    that fails to decrypt under `private_pem` is skipped rather than
    treated as a match, unchanged from before."""
    if not salt:
        return None
    wanted = code.strip().upper()
    matches: list[Registration] = []
    for entry in file.entries:
        existing = to_registration(json.dumps(entry), private_pem)
        if existing is None:
            continue
        # `hmac.compare_digest`, not `==`:
        # `matching_code` returns an HMAC-derived code, and `wanted` is a
        # workflow_dispatch input a caller typed -- the same reasoning
        # `proposal.py`'s own signature check already applies.
        # `derived_code` is never `None` here: `matching_code` only
        # returns `None` for a falsy `salt`, already ruled out by the
        # early return above -- named separately from this function's own
        # `code` parameter so mypy sees the narrowed, non-optional type.
        derived_code = matching_code(event_id, existing.email, salt)
        if derived_code is not None and hmac.compare_digest(derived_code, wanted):
            matches.append(existing)
    if len(matches) > 1:
        # The code itself does not go in this message.
        # It reaches this point from MATCHING_CODE, a workflow_dispatch
        # input already rendered on the run page, but that is a
        # documented exception for *that* surface, not licence to repeat
        # it here -- this message reaches stderr through erase_registration
        # unconditionally, on a path nothing exempts. The invariant every
        # refusal path in convener_ops already holds -- no name, no address, no
        # matching code -- applies here too.
        raise AmbiguousMatchingCodeError(
            f"{len(matches)} registrations for event {event_id!r} share one "
            "matching code -- refusing to guess which one to erase",
            tied=tuple(matches),
        )
    return matches[0] if matches else None


#: The alphabet a matching code is drawn from: digits 2-9 and every
#: uppercase letter except I, L, O and U -- the first three are the pairs a
#: spoken or handwritten code is classically confused on (0/O, 1/I/l); U
#: joins them for the reason Crockford's own base32 drops it too -- an
#: eight-symbol code read aloud on a call should not have a chance of
#: spelling something a participant has to say out loud. 30 symbols; see
#: `matching_code` for why 8 of them, in two groups, is enough.
_CODE_ALPHABET: Final = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_SYMBOLS: Final = 8
_CODE_GROUP: Final = 4


def matching_code(event_id: str, email: str, salt: str | None) -> str | None:
    """A short, spoken-safe code identifying one registration -- read aloud
    or typed into a display name when joining, never
    stored: the same three inputs always derive the same code, so a resend
    of the confirmation email needs nothing on disk to repeat it.

    `None` when `salt` is not set. Unlike an event's own encryption key
    (`eventkeys.py`), an absent salt is an *ordinary* D-13 state here:
    nothing has to fail closed, because the matching cascade
    -- exact address, then normalised name -- still works with no code
    at all. See the `matching_salt` row in `config/integrations.yml`. A
    caller with no code to send falls back to describing that cascade
    instead, which is the confirmation's decision, not this function's.

    The alphabet drops the pairs a spoken or handwritten code confuses --
    `0`/`O`, `1`/`I`/`l` -- and `U`, for the same reason Crockford's own
    base32 drops it: an eight-symbol code read aloud on a call should never
    have a chance of spelling something. 30 symbols. 8 of them, in two
    groups of four, give `30**8` (about 6.56e11) possible codes for one
    event: at the signup relay's own per-event ceiling of 500 registrations
    (`services/signup-relay/src/index.js::PER_EVENT_CEILING`), the birthday
    collision probability -- `n*(n-1) / (2 * 30**8)` for `n = 500` -- is
    about 1.9e-7, still negligible, even accounting for each symbol coming
    from one HMAC byte reduced modulo 30, which is not perfectly uniform:
    that does not matter for a display code whose unforgeability already
    comes from the salted HMAC underneath it, not from the mapping onto
    this alphabet.

    Salted, not constant: a code anyone could derive from an address alone
    would prove nothing about who holds that address -- see `matching_salt`
    in `config/integrations.yml` for why this secret exists at all.
    `normalize_email` keeps the same property `upsert` relies on: two
    submissions of the same address, differently capitalised, still derive
    one code, matching `upsert`'s own notion of "the same registration".

    The result is always uppercase. A participant types it into a display
    name on their own keyboard, which may not match that case, so whoever
    compares a typed name against this code must case-fold the
    typed side first -- this function does not, and should not, guess at
    what a comparison needs.
    """
    if not salt:
        return None
    digest = hmac.new(
        salt.encode("utf-8"),
        f"{event_id}\0{normalize_email(email)}".encode(),
        sha256,
    ).digest()
    symbols = "".join(
        _CODE_ALPHABET[byte % len(_CODE_ALPHABET)] for byte in digest[:_CODE_SYMBOLS]
    )
    return "-".join(
        symbols[i : i + _CODE_GROUP] for i in range(0, len(symbols), _CODE_GROUP)
    )


def looks_like_a_matching_code(token: str) -> bool:
    """Whether `token` has a matching code's own shape -- eight symbols,
    every one drawn from `_CODE_ALPHABET` -- once punctuation is stripped
    and case is folded the same way `attendance.py`'s own
    `_code_signature` does. Deliberately shape, not proof: this never
    decides that `token` IS a real code for any particular registrant
    (only `matching_code` recomputed for a specific address can say that),
    only that it looks enough like one to have been typed as one.

    `attendance.py`'s level 3 (normalised name) uses this to drop a code
    typed alongside a name -- the confirmation e-mail's own worked example
    (`confirmation.MATCHING_INSTRUCTION`) keeps the participant's name IN
    the display name next to the code, not instead of it, so a genuine
    registrant's display name is expected to carry one extra token that
    level must not hold against them. Shape-only also means a *mistyped*
    code -- one wrong symbol, still drawn from the alphabet -- is still
    dropped: level 3 exists for when the code did not work, so refusing to
    recognise a near-miss as "a code was attempted here" would defeat the
    reason this function exists.

    Public rather than module-private, the same reasoning `normalize_email`
    gives for its own visibility: a second, hand-written notion of "looks
    like a code" in `attendance.py` would risk disagreeing with this one
    about what the alphabet is, and the alphabet is defined once, here."""
    stripped = "".join(ch for ch in token.upper() if ch.isalnum())
    return len(stripped) == _CODE_SYMBOLS and all(
        ch in _CODE_ALPHABET for ch in stripped
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
