"""Per-event key pairs: generation, publication, and provable destruction.

A stranger registers for an event without their answers ever
existing in plain text outside a CI job. That promise rests on one fact this
module exists to guarantee: a public key published in the repository cannot
decrypt anything, only encrypt -- so the static registration page, which
holds nothing but the published half, genuinely cannot read what it just
sent.

Why RSA-OAEP + AES-GCM, and not RSA-OAEP alone
-----------------------------------------------
The hard constraint is that the **browser** encrypts, with `WebCrypto` and no
library, and **Python** decrypts; the two have to speak one wire format
without either side adding a dependency. RSA-OAEP with SHA-256 is available
on both sides for free -- natively in `crypto.subtle`, and in `cryptography`
here -- a dependency verified rather than assumed, since it was neither
declared nor installed before it was needed (see `pyproject.toml`). Python
has no asymmetric primitive of its own -- `hashlib`, `hmac` and `secrets`
are hashing and symmetric only -- and a symmetric key a
public registration page could hold would not be a key, so the real choice
was between this well-audited library and hand-rolling RSA in the one module
that handles a stranger's personal data. That is not a choice a project
should make quietly, so it is written down here for whoever finds it next.

RSA-OAEP only ever encrypts one short block -- with a 2048-bit key and
SHA-256 (see `RSA_KEY_BITS` below), 190 bytes at most. A registration today
fits inside that with room to spare, but relying on that headroom is exactly
how a field added two years from now would silently break encryption for
whoever adds it, at the moment they can least afford to notice. So `encrypt`
never puts the payload through RSA at all: it generates a throwaway
AES-256-GCM key, encrypts the payload with *that*, and encrypts only the
32-byte AES key with RSA-OAEP. This is the ordinary hybrid construction, not
a departure from "keep it simple" -- removing it to save a few lines is the
simplification a successor should not make.

The wire format
----------------
`encrypt`'s return value, and `decrypt`'s `ciphertext` argument, is one
compact JSON string, because both `JSON.stringify` and `json.loads` read and
write it without a library on either side::

    {"v": 1, "encrypted_key": "<base64>", "iv": "<base64>", "ciphertext": "<base64>"}

- ``v`` -- format version; 1 today. `decrypt` rejects anything else
  outright, so a later format change has somewhere to signal itself instead
  of being silently misread as the current one.
- ``encrypted_key`` -- the 32-byte AES-256 key, RSA-OAEP-encrypted (SHA-256
  hash and MGF1, no label) with the event's public key.
- ``iv`` -- the AES-GCM nonce: 12 random bytes (96 bits), the size
  `crypto.subtle` and `cryptography` both default to and NIST recommends for
  GCM. A fresh one is drawn for every call to `encrypt`; nothing here ever
  reuses one.
- ``ciphertext`` -- the AES-256-GCM output, with its 16-byte authentication
  tag appended -- exactly how both `crypto.subtle.encrypt` and
  `AESGCM.encrypt` already return it, so there is no separate tag field to
  keep in sync between the two implementations.

Every base64 field uses the standard alphabet, decodable in the browser over
the raw bytes (`atob`/`btoa`, or `Uint8Array` conversion). These parameters
are a cross-language contract: the browser implementation has to
reproduce this exactly, so a change here is a change there too.

The public half is a file, not a secret
----------------------------------------
`public_key_path` returns `instance/keys/events/<id>.pub`, committed PEM. It is not a
secret -- publishing it is what lets a static registration page encrypt
without asking a server for anything first.

One gap for the browser side to close, not this module's:
`crypto.subtle.importKey` takes DER (`"spki"` format), not PEM. Fetching the
`.pub` file is not enough on its own -- the browser has to strip the
`-----BEGIN/END PUBLIC KEY-----` lines and `atob` the base64 body first, the
same DER bytes this module's PEM wraps.

The private half, and the one place D-13 does not apply
---------------------------------------------------------
The private half lives only as `CONVENER_EVENT_KEY_<ID>`, a repository secret
declared in `declarations/integrations.yml` alongside every other integration --
`convener-check-config` reports it absent exactly like any other missing secret.

Everywhere else in this project a missing integration is D-13's normal
state: the job says so and exits 0, because the feature it powers has a
documented, harmless fallback. **There is no harmless fallback here.**
Without the private key, a job cannot decrypt a registration -- and it must
not write the ciphertext, or any part of it, to disk unencrypted instead.
That would be personal data reaching plain text for want of a key, which is
the one outcome this whole design exists to prevent. So the job that decrypts
an event's registrations exits in *error*, not zero, when its key is absent.
D-13 exists so a missing integration does not stop the system from working;
it was never meant to let personal data fall back to plain text because a
secret was not set.

`decrypt` already enforces the sharper half of this by construction: called
with anything that is not a real RSA private key -- an empty string, a stray
placeholder, the public half by mistake -- it raises `DecryptionError` rather
than returning anything. A caller that reads `CONVENER_EVENT_KEY_<ID>` from the
environment and finds it unset has nothing it could pass to `decrypt` that
would succeed by accident; the only way to get plaintext out of this module
is to already hold the real key.

Destruction is an operation, not a procedure
-----------------------------------------------
`destroy` and `key_status` are pure, like `validate.py`'s functions and for
the same reason its own docstring gives: "nothing here touches the
filesystem -- that belongs to `cli.py`." Deciding whether an event's key is
`NEVER_CREATED`, `ACTIVE` or `DESTROYED`, and producing the record a
destruction should write, do not need a disk read to be correct -- they need
the two facts a caller already has cheaply: whether `public_key_path
(event_id)` exists, and what the on-disk registry already says. Actually
removing `CONVENER_EVENT_KEY_<ID>` from the repository's secrets, and persisting
the record `destroy` returns, are real side effects, and belong to the
retention job that calls this module, the same way `cli.py` -- not
`validate.py` -- is the one that writes `instance/data/speakers.yml`.

The distinction the registry has to preserve is `DESTROYED` versus
`NEVER_CREATED`: without it, an event with no key two years from now could
mean "protected, on schedule" or "the key was simply lost," and nothing
short of the registry can tell those two apart. `destroy` refuses to
manufacture a `DESTROYED` record for an event whose key was never created
(`key_was_published=False`) -- that is not destruction, it is a typo in an
event id, and recording it as destruction would erase the very difference
the registry exists to keep. Once a record exists, calling `destroy` again
for the same event returns the existing record rather than raising or
minting a second one: a retention job that reruns after a partial failure
must be able to repeat the call safely, and the record's date is the day it
was first destroyed, never the day of the retry.

The deadline is computed, never read off a form
--------------------------------------------------
`is_due_for_destruction` is the whole of the event's date plus ninety
days: `event_date + RETENTION_DAYS` days, compared against
`governance.paris_today(now)` -- the same clock discipline every other
deadline in this repository already uses (`sweep.py`'s own vote-window
expiry), never a raw `datetime.now()` a caller might read on the wrong
side of midnight UTC. Inclusive at the boundary: an event is due starting
on day 90 itself, not day 91 -- unlike `sweep.expire_votes`'s own one-day
grace for a board vote window, there is no benefit of the doubt to extend
here. The retention job (`cli.py::retention_sweep`) calls this once per
event whose key is still `ACTIVE`, and destroys exactly the ones it
returns `True` for.

The destruction registry lives in one file, not one per event
---------------------------------------------------------------
`destroy` and `key_status` above take `registry: Mapping[str, date]`
already assembled; `registry_from_data` and `registry_to_data` are its
parse and serialise halves, reading and writing
`instance/data/event-key-destructions.yml` (`destructions_path`) the same way
`certificate.register_from_data`/`register_to_data` read and write
`certificates.yml` -- pure, no filesystem access, `cli.py` is still the
only module that opens the path. One file for every event, not a marker
dropped into each event's own `instance/data/events/<id>/` directory: a scheduled
sweep spanning many events writes one small file and one commit, not one
commit per event, and an operator who wants "which events has this ever
destroyed" reads one page rather than globbing a tree.

Only `event_id` and `destroyed_on` -- nothing else survives here either,
the same discipline `certificate.py`'s own register holds itself to. This
file is never personal data and never becomes unreadable: unlike
`registrations.enc`, there is no key it depends on and no reason it would
ever need destroying itself.

The file is not deleted, and here is why
------------------------------------------
Destroying a key does **not** delete `instance/data/events/<id>/registrations.enc`
from the working tree. Deleting the file would not, on its own, make
anything more unreadable than destroying the key already has -- git
history still holds every byte of the ciphertext, deletion or not -- and
it would invite a future reader to believe the *file's absence* is what
protects the data, which is backwards: the key is the only thing that
ever made the ciphertext readable, and once it is gone, an intact,
committed, permanently unreadable blob is exactly what a promise that the
data becomes permanently unreadable describes -- unreadable,
not absent. Leaving it in place is also cheaper and safer than rewriting
history to remove it, which this project rules out by name.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from secrets import token_bytes
from typing import Any, Final

from cryptography.exceptions import InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..declaration import paths
from ..governance.commit_format import _TOKEN
from ..governance.rule import paris_today

#: RSA modulus size. 2048 bits keeps key generation and RSA-OAEP fast in
#: both a browser and a CI job, and is accepted by NIST guidance well past
#: this project's retention window, 90 days. It is
#: also the OAEP block size the wire format's `encrypted_key` field assumes:
#: with SHA-256 (32-byte digest) the usable payload is
#: 256 - 2*32 - 2 = 190 bytes, comfortably more than the 32-byte AES-256 key
#: this module ever encrypts with it.
RSA_KEY_BITS: Final = 2048

#: The AES key size in bytes (AES-256).
AES_KEY_BYTES: Final = 32

#: The AES-GCM nonce size in bytes (96 bits) -- the size `crypto.subtle` and
#: `cryptography` both default to, and NIST SP 800-38D recommends.
GCM_NONCE_BYTES: Final = 12

#: The wire format version written into every ciphertext's `"v"` field.
WIRE_VERSION: Final = 1

#: The envelope's exact key set -- nothing more, nothing less. Exported so a
#: caller storing envelopes verbatim (`registration.py::load_registration_file`)
#: can pin "this dict is ciphertext and only ciphertext" against the one
#: definition of what ciphertext looks like, rather than a second, hand-typed
#: copy of these four names that could drift from this module's own.
ENVELOPE_FIELDS: Final = frozenset({"v", "encrypted_key", "iv", "ciphertext"})

#: Where the published public half of an event's key pair lives, relative to
#: the repository root.
KEYS_DIR: Final = paths.KEYS_DIR / "events"

#: The RSA-OAEP parameters both sides of the wire format use: SHA-256 for
#: both the hash and the MGF1 mask, no label. `crypto.subtle`'s
#: `RsaOaepParams` defaults to the same hash for both when only `hash` is
#: given, which is what makes this reproducible without a library in the
#: browser.
_OAEP: Final = padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()),
    algorithm=hashes.SHA256(),
    label=None,
)

#: An event id: a plain token, the exact shape `commit_format._TOKEN`
#: accepts for a decision register entity -- imported, not copied, so the
#: two cannot drift apart into two different definitions of "a token" by
#: hand-edit. No `Identifier` type exists yet anywhere in this codebase
#: (Python or TypeScript), so this module
#: treats one as a validated `str` rather than inventing a wrapper type
#: nothing else uses. The validation exists because this string becomes a
#: path component (`public_key_path`): an id that is not a plain token
#: could otherwise walk out of `instance/keys/events/`. It does *not* by itself
#: guarantee a legal environment variable suffix -- `_TOKEN` admits `.` and
#: `-`, neither legal in a GitHub Actions secret name, which is why
#: `secret_name` below exists as a separate step.
#:
#: **Length-capped at `_EVENT_ID_MAX_LENGTH`.**
#: `services/signup-relay/src/index.js::EVENT_ID_RE` mirrors `_TOKEN`'s own
#: charset (it cannot import this pattern -- the two languages share no
#: regex object) but, unlike this pattern before this fix, also bounds the
#: length to 64: "no event id in this project is remotely close to that,
#: the cap exists only so a pathological input cannot inflate the GitHub
#: API URL or the dispatch payload it participates in" (that module's own
#: comment). Without a matching bound here, a >64-character id could pass
#: every check in this module, get published as `instance/keys/events/<id>.pub`,
#: and be refused by the relay with a bare 400 on every registration
#: attempt -- fail-closed, but confusingly, and only at signup time. The
#: lookahead enforces the length without touching `_TOKEN` itself, which
#: `commit_format.py`'s own decision-register tokens still use unbounded.
_EVENT_ID_MAX_LENGTH: Final = 64
_EVENT_ID_RE: Final = re.compile(rf"^(?=.{{1,{_EVENT_ID_MAX_LENGTH}}}$){_TOKEN}$")

#: GitHub Actions secret names are restricted to `[A-Za-z_][A-Za-z0-9_]*`.
#: `secret_name` folds the two characters `_EVENT_ID_RE` admits but that
#: charset does not -- `.` and `-` -- to `_` before uppercasing.
_SECRET_UNSAFE_RE: Final = re.compile(r"[.-]")

#: `key_status` and the registry `destroy` reasons about: the key exists,
#: was never made, or was made and has since been destroyed on purpose.
NEVER_CREATED: Final = "never_created"
ACTIVE: Final = "active"
DESTROYED: Final = "destroyed"


class DecryptionError(Exception):
    """A ciphertext could not be decrypted.

    Wrong private key, wrong event, truncated, or tampered all become this
    same exception, and the message never says which of those it was: a
    caller able to distinguish them by exception type or text would have an
    oracle a real attacker could use to probe which *cryptographic* failure
    mode they hit. That promise covers the cryptographic failure modes
    specifically. A small number of pre-cryptographic causes -- a key that
    is not RSA at all, a ciphertext that is not even a JSON object -- do get
    a distinct, still plaintext-free message from `_decrypt`, because they
    are detected before any key material is touched and naming them gives
    an attacker nothing they could not already see from the input itself.
    Never carries plaintext, key material, or a fragment of either, in any
    case.
    """


@dataclass(frozen=True)
class DestructionRecord:
    """What `destroy` records, and nothing else: an event id and the day its
    private key was destroyed. No actor, on purpose -- the retention job
    that calls this runs unattended, and a `by <someone>` column with no one
    in it is worse than no column at all."""

    event_id: str
    destroyed_on: date


def _validate_event_id(event_id: str) -> None:
    if not _EVENT_ID_RE.fullmatch(event_id):
        raise ValueError(f"not a valid event id: {event_id!r}")


def secret_name(event_id: str) -> str:
    """The `CONVENER_EVENT_KEY_<ID>` environment variable name for `event_id`.

    `declarations/integrations.yml` declares the *pattern*
    `CONVENER_EVENT_KEY_<ID>`; this is what `<ID>` concretely is for a given
    event. Uppercasing the id is not enough on its own -- an id such as the
    tests' own canonical `mrg-042` uppercases to `MRG-042`, and
    `CONVENER_EVENT_KEY_MRG-042` is not a legal GitHub Actions secret name, which
    only admits `[A-Za-z_][A-Za-z0-9_]*`. So both characters `_EVENT_ID_RE`
    admits but that charset does not -- `.` and `-` -- become `_` first.
    The result is always legal by construction: the prefix is fixed and
    already legal, and the transformed suffix can only contain letters,
    digits and `_`.

    This transform is lossy on purpose to keep it simple, and that has one
    consequence: `mrg-042` and `mrg.042` both become `MRG_042` and would
    collide on the same secret. Event ids are chosen by whoever creates the
    event, never by a participant, so this is a documented operational
    constraint -- do not create two events whose ids collide once `.` and
    `-` are folded to `_` -- rather than something this function can detect
    on its own; it holds no registry of any other event's id to check
    against.
    """
    _validate_event_id(event_id)
    suffix = _SECRET_UNSAFE_RE.sub("_", event_id).upper()
    return f"CONVENER_EVENT_KEY_{suffix}"


def generate() -> tuple[str, str]:
    """A fresh RSA key pair, PEM-encoded: `(private, public)`.

    The private half is PKCS8, unencrypted -- its protection is the
    repository secret it is stored as (`CONVENER_EVENT_KEY_<ID>`), not a
    password on the PEM itself, which would only move the secret one layer
    down. The public half is `SubjectPublicKeyInfo` PEM -- see the module
    docstring for the one extra step the browser needs before
    `crypto.subtle.importKey("spki", ...)` will accept it.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=RSA_KEY_BITS)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return private_pem, public_pem


def derive_public_pem(private_pem: str) -> str:
    """The public half of `private_pem`, re-derived rather than read from a
    file on disk.

    A job re-encrypting a registration (`registration.py::upsert`) only
    ever needs the public half that *mathematically matches* the private
    key it already holds -- and deriving it is what guarantees exactly
    that. Reading `instance/keys/events/<id>.pub` instead would trust whatever
    happens to be committed there: ordinarily the same key, but a stale
    commit, a mid-rotation state, or a swapped file would silently
    re-encrypt under the wrong public half, and the failure would not
    surface until someone tried to decrypt with the *actual* private key
    and found the ciphertext did not match it. Deriving instead makes that
    class of mismatch structurally impossible, and removes a filesystem
    read -- and the "no published public key" failure mode that came with
    it -- from a job whose only other filesystem interaction is the file
    it writes.

    Raises `DecryptionError` for a key that will not load or is not RSA --
    the same single failure mode `decrypt` uses for every "not a usable
    key" cause, rather than a second exception type this module's callers
    would also have to catch. Callers of this function already hold a
    `private_pem` proven valid by an earlier successful `decrypt` call, so
    this is not a new input-validation boundary in practice -- but the
    contract holds regardless of how it is called.
    """
    try:
        private_key = serialization.load_pem_private_key(
            private_pem.encode("ascii"), password=None
        )
    except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise DecryptionError("not a usable RSA private key") from exc
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise DecryptionError("not an RSA private key")
    return (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )


def encrypt(public_pem: str, plaintext: bytes) -> str:
    """Hybrid-encrypt `plaintext` for the holder of the matching private key.

    See the module docstring for the wire format and why it is hybrid
    rather than RSA-OAEP alone.
    """
    public_key = serialization.load_pem_public_key(public_pem.encode("ascii"))
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError("not an RSA public key")

    aes_key = token_bytes(AES_KEY_BYTES)
    nonce = token_bytes(GCM_NONCE_BYTES)
    body = AESGCM(aes_key).encrypt(nonce, plaintext, None)
    encrypted_key = public_key.encrypt(aes_key, _OAEP)

    envelope = {
        "v": WIRE_VERSION,
        "encrypted_key": base64.b64encode(encrypted_key).decode("ascii"),
        "iv": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(body).decode("ascii"),
    }
    return json.dumps(envelope, separators=(",", ":"))


def decrypt(private_pem: str, ciphertext: str) -> bytes:
    """The inverse of `encrypt`, or `DecryptionError` -- never a guess.

    Every expected way this can fail (wrong key, wrong event, truncated,
    tampered, malformed) is caught here and re-raised as `DecryptionError`;
    see that exception's docstring for why they are not told apart.
    """
    try:
        return _decrypt(private_pem, ciphertext)
    except (
        ValueError,
        TypeError,
        KeyError,
        InvalidTag,
        UnsupportedAlgorithm,
    ) as exc:
        raise DecryptionError("ciphertext could not be decrypted") from exc


def _decrypt(private_pem: str, ciphertext: str) -> bytes:
    private_key = serialization.load_pem_private_key(
        private_pem.encode("ascii"), password=None
    )
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise DecryptionError("not an RSA private key")

    envelope: Any = json.loads(ciphertext)
    if not isinstance(envelope, dict):
        raise DecryptionError("malformed ciphertext")
    if envelope.get("v") != WIRE_VERSION:
        raise DecryptionError("unsupported ciphertext format version")

    encrypted_key = base64.b64decode(envelope["encrypted_key"], validate=True)
    nonce = base64.b64decode(envelope["iv"], validate=True)
    body = base64.b64decode(envelope["ciphertext"], validate=True)

    aes_key = private_key.decrypt(encrypted_key, _OAEP)
    return AESGCM(aes_key).decrypt(nonce, body, None)


def public_key_path(event_id: str) -> Path:
    """Where the published public half for `event_id` lives: `instance/keys/events/
    <event_id>.pub`, relative to the repository root. Pure path computation
    -- this reads nothing, and callers decide whether to check `.exists()`
    or read it."""
    _validate_event_id(event_id)
    return paths.repo_root() / KEYS_DIR / f"{event_id}.pub"


def key_status(
    event_id: str, *, key_was_published: bool, registry: Mapping[str, date]
) -> str:
    """`NEVER_CREATED`, `ACTIVE`, or `DESTROYED`, from state the caller
    already read: whether `public_key_path(event_id)` exists
    (`key_was_published`), and the destruction registry
    (`event_id -> destroyed_on`). Pure -- see the module docstring."""
    _validate_event_id(event_id)
    if event_id in registry:
        return DESTROYED
    return ACTIVE if key_was_published else NEVER_CREATED


def destroy(
    event_id: str,
    now: datetime,
    *,
    key_was_published: bool,
    registry: Mapping[str, date],
) -> DestructionRecord:
    """The record a destruction should write: `event_id` and today's Paris
    day. Pure -- see the module docstring for why, and for what still has to
    happen outside this function (removing the secret, persisting this
    record).

    Raises `ValueError` if `key_was_published` is false: destroying a key
    that was never created would erase the distinction the registry exists
    to preserve. Idempotent once a record exists: calling this again for an
    already-destroyed event returns that same record rather than a new one.
    """
    _validate_event_id(event_id)
    destroyed_on = registry.get(event_id)
    if destroyed_on is not None:
        return DestructionRecord(event_id=event_id, destroyed_on=destroyed_on)
    if not key_was_published:
        raise ValueError(
            f"cannot destroy a key that was never created for event {event_id!r}"
        )
    return DestructionRecord(event_id=event_id, destroyed_on=paris_today(now))


#: The retention window: the event's date, plus 90 days.
#: A module constant, not a `instance/data/config.yml` value: retention is a legal
#: commitment, stated once here and once in the confirmation e-mail
#: (`confirmation.py::_DATA_PROTECTION`), never something an operator
#: tunes per event.
RETENTION_DAYS: Final = 90


def is_due_for_destruction(event_date: date, today: date) -> bool:
    """Whether an event whose talk was held on `event_date` has reached the
    end of its retention window, as of `today` -- see the module
    docstring's "the deadline is computed" section for the boundary rule
    (inclusive: due starting on day 90 itself) and why `today` must always
    be `governance.paris_today(now)`, never a raw clock read.
    """
    return today >= event_date + timedelta(days=RETENTION_DAYS)


#: Where the destruction registry lives, relative to a repository root --
#: see the module docstring's "the destruction registry lives in one
#: file" section for why this is a single file rather than one per event.
DESTRUCTIONS_PATH: Final = paths.DATA_DIR / "event-key-destructions.yml"

#: `instance/data/event-key-destructions.yml`'s own format version -- the file-level
#: analogue of `WIRE_VERSION` and `registration.FILE_VERSION`.
DESTRUCTIONS_FILE_VERSION: Final = 1

#: A destruction registry entry's exact field set. See `registry_from_data`.
_DESTRUCTION_FIELDS: Final = frozenset({"event_id", "destroyed_on"})


def destructions_path(root: Path) -> Path:
    """`instance/data/event-key-destructions.yml`, relative to `root` -- the one
    function that names where the destruction registry lives on disk, the
    same role `certificate.certificates_path` plays for that register.
    Pure path computation: reads nothing, touches nothing; `cli.py` is
    still the only module that ever opens the path this returns."""
    return root / DESTRUCTIONS_PATH


def registry_from_data(data: Any) -> dict[str, date]:
    """Parse an already YAML-loaded `instance/data/event-key-destructions.yml` into
    the `Mapping[str, date]` `key_status` and `destroy` expect, or start
    empty when `data` is `None` -- no event has ever been destroyed yet,
    the ordinary state before the first retention sweep that finds
    anything due.

    Raises `ValueError` on anything committed that is not this exact
    format -- unlike a missing file, a malformed one is not a normal state
    to paper over, the same "closed shape" discipline
    `registration.load_registration_file` and
    `certificate.register_from_data` already hold themselves to. Also
    refuses a duplicate `event_id`: two rows for one event would leave
    `destroy`'s own idempotence (the day of the *first* destruction) unable
    to answer which of the two is authoritative.
    """
    if data is None:
        return {}
    if not isinstance(data, dict) or data.get("v") != DESTRUCTIONS_FILE_VERSION:
        raise ValueError(
            f"{DESTRUCTIONS_PATH.as_posix()} is not a supported format version"
        )
    raw_entries = data.get("destructions")
    if not isinstance(raw_entries, list):
        raise ValueError(f"{DESTRUCTIONS_PATH.as_posix()} is malformed")

    registry: dict[str, date] = {}
    for raw in raw_entries:
        if not isinstance(raw, dict) or set(raw) != _DESTRUCTION_FIELDS:
            raise ValueError(
                f"{DESTRUCTIONS_PATH.as_posix()} holds an entry that is "
                "not exactly an event id and a destruction date"
            )
        event_id, destroyed_on_raw = raw["event_id"], raw["destroyed_on"]
        if not isinstance(event_id, str) or not isinstance(destroyed_on_raw, str):
            raise ValueError(
                f"{DESTRUCTIONS_PATH.as_posix()} holds a field of the wrong type"
            )
        _validate_event_id(event_id)
        if event_id in registry:
            raise ValueError(
                f"{DESTRUCTIONS_PATH.as_posix()} holds event id "
                f"{event_id!r} more than once"
            )
        try:
            registry[event_id] = date.fromisoformat(destroyed_on_raw)
        except ValueError as exc:
            raise ValueError(
                f"{DESTRUCTIONS_PATH.as_posix()} holds an invalid "
                f"destroyed_on date for event {event_id!r}"
            ) from exc
    return registry


def registry_to_data(registry: Mapping[str, date]) -> dict[str, Any]:
    """The inverse of `registry_from_data`: a plain, YAML-safe structure
    `cli.py` hands to its own YAML writer. Sorted by event id -- like
    `certificate.register_to_data`'s own field ordering -- so a diff on
    `instance/data/event-key-destructions.yml` shows only what a sweep actually
    added, never a reordering."""
    return {
        "v": DESTRUCTIONS_FILE_VERSION,
        "destructions": [
            {"event_id": event_id, "destroyed_on": registry[event_id].isoformat()}
            for event_id in sorted(registry)
        ],
    }
