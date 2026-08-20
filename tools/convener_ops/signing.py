"""The certificate signing key pair: who may say "this is real," forever.

Phase 4 lets a stranger who receives a certificate confirm it without an
account, a login, or a request to us -- a public verification page (task 13)
reads a machine-readable code off the document, checks it against a
published key, and shows what the code says. That promise rests on one fact
this module exists to guarantee: a signature proves the payload came from
whoever holds the private half, and proves nothing else -- in particular, it
does not hide the payload. **Signing is not encryption.** `sign` produces a
token whose payload sits in the clear, readable by anyone who receives the
certificate, whether or not they ever check the signature; what the private
key proves is *authorship*, not *secrecy*.

Do not confuse this module with `eventkeys.py`
------------------------------------------------
`eventkeys.py` encrypts a registration so the *only* thing the public half
lets anyone do is write ciphertext nobody but us can read -- the plaintext
never becomes visible to a holder of the public key. This module does the
opposite kind of work: here the public key is exactly what lets a stranger
*read* the payload and confirm it is genuine, in the same step. A reader who
carries over "public key cannot read the payload" -- the property
`eventkeys.py` guarantees -- would be carrying the wrong assumption into
this module entirely.

The two modules exist separately for a second, sharper reason than "signing
differs from encryption": **their key lifecycles run in opposite
directions.**

- An event key (`eventkeys.py`) is *destroyed* at the end of retention
  (phase 4 spec §4). Destruction is the point: it is what makes already-
  committed ciphertext permanently unreadable, and that irreversibility is
  the provable half of the retention promise.
- A signing key is *never* destroyed. Retiring one from active service --
  no longer used to sign new certificates -- must not invalidate a single
  certificate it already signed; the phase 4 spec (§7) says so explicitly:
  "les clés publiques antérieures restent publiées, pour que la rotation
  n'invalide jamais un certificat déjà émis." A certificate is meant to
  outlive the event it was earned at, in some cases by years (accreditation
  bodies keep records), so "signed under a key we later stopped using" must
  still mean "valid," permanently.

A module that tried to serve both properties with one set of functions
would get one of them backwards the day someone reused `destroy` here, or
reused `verify`'s multi-key tolerance over there. Keeping them apart keeps
each lifecycle enforceable by its own code, not by a shared function
remembering which caller it is talking to. This module has no `destroy`,
no registry, and no `NEVER_CREATED`/`ACTIVE`/`DESTROYED` distinction at
all -- there is nothing here to destroy, and pretending otherwise would be
the exact mistake this docstring exists to prevent.

Why RSA-PKCS1v15 + SHA-256, and not the hybrid scheme `eventkeys.py` uses
---------------------------------------------------------------------------
`eventkeys.py`'s hybrid construction exists because RSA-OAEP only encrypts
one short block (its module docstring works out the exact byte budget) --
a payload larger than that would silently stop fitting. Signing has no such
ceiling: RSA does not sign the payload itself, it signs a fixed-size hash of
it (SHA-256, 32 bytes, however large the payload), so nothing here needs a
second, symmetric layer. The plain construction is the right one, not a
simplification that happens to still work.

Padding scheme: **PKCS1v15, not PSS.** Both remain valid for RSA signatures
under current guidance. PSS is the more modern default and is the better
choice for a system defending against a sophisticated attacker at scale --
but it is also probabilistic (a random salt drawn on every signature) and
its safety depends on both sides agreeing on a `saltLength` neither
`crypto.subtle` nor `cryptography` defaults the same way -- exactly the kind
of cross-language parameter this project already paid once for OAEP's mask
hash and label (see `eventkeys.py`). PKCS1v15 is deterministic and takes no
extra parameter at all: `RSASSA-PKCS1-v1_5` with `SHA-256` is the entire
contract, on both sides, nothing further to keep in sync. For attesting
attendance at a workshop, that reduction in cross-language surface is worth
more than PSS's marginal proof-theoretic edge.

Key size: **3072 bits, not the 2048 `eventkeys.py` uses.** An event key
only has to hold for the 90-day retention window (phase 4 spec §4) before
it is destroyed outright; a signing key has to hold for as long as any
certificate it ever signed still needs to verify, which this module's whole
design says is forever. NIST guidance rates 2048-bit RSA through roughly
2030 and 3072-bit meaningfully longer; given this key is generated rarely
and verified rarely (a stranger checking one certificate at a time, not a
high-throughput service), the larger size costs nothing that matters and
buys margin on the one parameter that cannot be revised after the fact
without minting a new key and asking a verification page to trust two.

The wire format
----------------
`sign`'s return value, and `verify`'s `token` argument, is one compact JSON
string -- the same idiom `eventkeys.py`'s wire format uses, for the same
reason: `JSON.stringify` and `json.loads` read and write it on either side
without a library::

    {"v":1,"payload":{...},"signature":"<base64>"}

- ``v`` -- format version; 1 today, the same discipline as `eventkeys.py`'s
  own `"v"` field. `verify` rejects anything else.
- ``payload`` -- a JSON object, embedded whole, not re-encoded as a nested
  string. This is deliberate: a verifier that already parsed the token has
  the payload as data immediately, with no second `JSON.parse` needed
  before it can display it.
- ``signature`` -- the raw PKCS1v15 signature over the *canonical bytes* of
  `payload` (see below), standard base64.

Canonicalisation: the bytes actually signed are
`json.dumps(payload, sort_keys=True, separators=(",", ":"))`, ASCII (JSON's
default `ensure_ascii` escapes anything outside it as `\\uXXXX` rather than
writing it literally) -- a certificate holder whose name carries an accent
must not turn the signed bytes non-ASCII, since the whole token is meant to
sit inside a machine-readable code on the printed certificate and this
project prints nothing non-ASCII to a terminal either. `sort_keys=True` is
what makes the result reproducible independent of the payload dict's own
insertion order, or of how the *outer* token JSON happens to be formatted or
reordered before `verify` sees it -- the same robustness `eventkeys.py`'s
own wire-format test pins for its envelope. `verify` recomputes these same
canonical bytes from the parsed `payload` before checking any signature, so
signing and verifying are guaranteed to agree on what was actually signed,
byte for byte.

This module does not itself decide what a certificate's payload contains --
that is `certificate.py`'s job (task 12), and `sign`/`verify` are as
content-agnostic about it as `eventkeys.encrypt`/`decrypt` are about a
registration's fields. But every payload used as an example or a test
fixture here holds exactly what the phase 4 spec's §7 lists and nothing
else: identifier, event, name, date, duration. **No address.** The
verification page (task 13) has no reason to display one, and a field that
is never in the payload cannot leak from it -- a discipline worth keeping
even though `sign` itself would happily sign whatever dict it is handed.

Key layout: `keys/signing/<YYYY-MM-DD>.pub`, and how a verifier chooses
--------------------------------------------------------------------------
`public_key_path(generated_on)` returns `keys/signing/<date>.pub` -- the day
the pair was generated, ISO 8601, the same sortable-by-filename idiom
`eventkeys.py` uses for event ids, chosen here for a second reason: sorting
these filenames *is* sorting the keys by age, with no separate manifest
file to keep in sync. Every key this project ever generates is committed
here, forever -- rotating a key out of *service* (no longer used to sign
new certificates) never means removing its file. §7's rotation promise is
kept entirely by this file simply staying put; there is no companion
"retire" or "destroy" operation in this module, on purpose (see above).

`verify` accepts an ordered list, `public_pems: list[str]`, and tries each
in turn, returning the payload from the first one that checks out (or
`None` if none do). The order is the caller's choice, not this module's --
but the convention this module's own layout implies, and the one task 13's
build step and any future caller should follow, is **newest first**: list
`keys/signing/*.pub`, sort filenames in *descending* order, and build the
list from that. Almost every verification is of a certificate signed under
the key currently in service, so that ordering makes the common case the
cheapest one -- while correctness never depends on getting the order right,
only on the right key being *somewhere* in the list, which is exactly what
the rotation test below proves. There is deliberately no "key id" hint
carried in the token that would let a verifier jump straight to the right
key: such a hint is not itself authenticated by anything a reader could
check before trying the key it names, so the only thing it could ever be is
a speed optimisation -- and RSA verification over a handful of keys is not
slow enough to be worth the added field and the added thing to keep
consistent with the file layout.

One naming collision to avoid, the same shape as `eventkeys.py`'s own:
generating two signing keys on the same calendar day collides on the same
filename. Keys are rotated by deliberate operator action, not automation,
so this is a documented operational constraint -- do not rotate the signing
key twice in one day -- rather than something this module can detect; it
holds no registry of what is already committed to check against.

The private half, and why its absence is an ordinary D-13 state here
------------------------------------------------------------------------
Unlike `eventkeys.py`'s private half, there is exactly one signing private
key in service at a time, held as the repository secret `CONVENER_SIGNING_KEY`
(`config/integrations.yml`), read only inside the job that issues
certificates (task 12/14) and never elsewhere. Rotating it means: an
*operator* -- a person, interactively, never an automated step and never
this module acting on anyone's behalf -- runs `generate()`, commits the new
public half under a new date, and only then replaces the `CONVENER_SIGNING_KEY`
secret with the new private half, pasted directly into GitHub Secrets and
never written to a file at any point. That is the same publish-before-secret
ordering `eventkeys.py`'s own operations doc already argues for event keys,
and for the same reason: setting the secret first would let a job sign a
certificate under a key with no public half yet committed for anyone to
verify it against. `generate` itself has no opinion on who calls it or how
the result is handled -- it is `docs/reference/operations.md`'s
"Certificate signing key" section, not this module, that is the place this
constraint is a procedure rather than only a property of the function.

`eventkeys.py`'s module docstring carves out one deliberate exception to
D-13 ("an absent integration is a normal state"): a missing event key must
not let a decryption job fall back to writing personal data to disk in the
clear, so that job fails closed instead. **No equivalent exception applies
here.** An absent `CONVENER_SIGNING_KEY` means the job that would issue a
certificate cannot sign one, and does not -- no certificate for this run,
nothing partially written, nothing sensitive exposed by the absence. That is
exactly the shape of an ordinary, documented D-13 fallback (compare
`video_publishing`'s "entered by hand," `board_notifications`'s "printed
instead of sent"), not the one row (`event_keys`) that fails closed over a
confidentiality risk. `config/integrations.yml` declares `signing_key`
accordingly, with `absent_is_normal` left at its default of `true`.
"""

from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path
from typing import Any, Final

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .paths import repo_root

#: RSA modulus size for a signing key -- 3072, not `eventkeys.RSA_KEY_BITS`
#: (2048). See the module docstring's "Key size" section for why a key
#: meant to verify forever is sized differently than one meant to hold for
#: 90 days.
RSA_KEY_BITS: Final = 3072

#: The wire format version written into every token's `"v"` field.
WIRE_VERSION: Final = 1

#: A token's exact key set -- exported so another module pinning "this
#: string is a signing token" has one definition to check against, the same
#: role `eventkeys.ENVELOPE_FIELDS` plays for a ciphertext envelope. Not
#: enforced as a strict equality inside `verify` itself (an unrecognised
#: extra field is ignored, not refused -- the same forward-compatible
#: tolerance `eventkeys.decrypt` already applies to its own envelope).
TOKEN_FIELDS: Final = frozenset({"v", "payload", "signature"})

#: Where the published public halves live, relative to the repository root.
KEYS_DIR: Final = Path("keys") / "signing"

#: The repository secret holding the private half currently in service.
#: Unlike `eventkeys.py`'s per-event `CONVENER_EVENT_KEY_<ID>`, there is exactly
#: one of these at a time -- see `config/integrations.yml` and the module
#: docstring's "private half" section.
SECRET_NAME: Final = "CONVENER_SIGNING_KEY"

#: RSA-PKCS1v15 with SHA-256: the entire padding contract, no extra
#: parameter to keep in sync with a future browser-side verifier. See the
#: module docstring for why this, and not PSS.
_HASH: Final = hashes.SHA256()
_PADDING: Final = padding.PKCS1v15()


class SigningError(Exception):
    """A key handed to `sign` (or re-derived by `derive_public_pem`) was not
    usable: not a real RSA private key at all -- an empty string, a public
    key by mistake, a key of another kind entirely. Never raised by
    `verify`: an unverifiable token is reported through its `None` return,
    never an exception, because it is not this module's *caller's* mistake
    the way an unusable signing key is -- it is what an ordinary
    "invalid signature" outcome looks like from a public verification page
    that should never need a `try`/`except` to check a certificate."""


def generate() -> tuple[str, str]:
    """A fresh RSA key pair, PEM-encoded: `(private, public)`.

    Deliberately a separate call from `eventkeys.generate`, even though the
    two produce PEM in the same shapes -- see the module docstring for why
    a signing key and an event key are not the same key pair wearing two
    names; reusing one RSA key across an encryption padding scheme (OAEP)
    and a signature scheme (PKCS1v15) is exactly the kind of key-reuse
    modern cryptographic guidance warns against, even where both uses
    happen to be `cryptography`-library calls in the same repository.

    The private half is PKCS8, unencrypted -- its protection is the
    repository secret it becomes (`CONVENER_SIGNING_KEY`), never a password on
    the PEM itself. The public half is `SubjectPublicKeyInfo` PEM, the same
    format `eventkeys.generate` returns.
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


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    """The exact bytes a signature covers: sorted keys, compact separators,
    ASCII-escaped. See the module docstring's "wire format" section for why
    each choice is load-bearing, not cosmetic -- both `sign` and `verify`
    call this, so the two are guaranteed to agree on what was signed."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")


def _load_private_key(private_pem: str) -> rsa.RSAPrivateKey:
    try:
        private_key = serialization.load_pem_private_key(
            private_pem.encode("ascii"), password=None
        )
    except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise SigningError("not a usable RSA private key") from exc
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise SigningError("not an RSA private key")
    return private_key


def sign(payload: dict[str, Any], private_pem: str) -> str:
    """Sign `payload` with `private_pem`, returning a compact JSON token --
    see the module docstring for the exact wire format and what "signed"
    means here (authorship, not secrecy: the payload sits in the token in
    the clear).

    `payload` is content-agnostic here: any JSON-serialisable dict is
    accepted. See the module docstring for why the *discipline* of what a
    certificate payload actually holds belongs to `certificate.py`
    (task 12), not to this generic signer -- the same division
    `eventkeys.py` draws between `encrypt` and `registration.py`.

    Raises `SigningError` if `private_pem` is not a usable RSA private key.
    Raises whatever `json.dumps` itself raises (`TypeError`) for a payload
    that is not JSON-serialisable -- a mistake in what the caller built, not
    something this module tries to translate into a domain-specific error.
    """
    private_key = _load_private_key(private_pem)
    canonical = _canonical_bytes(payload)
    signature = private_key.sign(canonical, _PADDING, _HASH)
    token = {
        "v": WIRE_VERSION,
        "payload": payload,
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    return json.dumps(token, separators=(",", ":"))


def derive_public_pem(private_pem: str) -> str:
    """The public half of `private_pem`, re-derived rather than read from a
    committed file.

    Mirrors `eventkeys.derive_public_pem` for an analogous reason: a job
    that holds `CONVENER_SIGNING_KEY` can confirm -- against
    `keys/signing/<date>.pub` -- that the secret it was just handed is
    genuinely the private half of the key that date's file publishes,
    rather than trusting a filename-to-secret correspondence nothing else
    checks. Raises `SigningError` for a key that will not load or is not
    RSA, the same single failure mode `sign` itself uses.
    """
    private_key = _load_private_key(private_pem)
    return (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )


def _verifies_with(public_pem: str, canonical: bytes, signature: bytes) -> bool:
    try:
        public_key = serialization.load_pem_public_key(public_pem.encode("ascii"))
    except (ValueError, TypeError, UnsupportedAlgorithm):
        return False
    if not isinstance(public_key, rsa.RSAPublicKey):
        return False
    try:
        public_key.verify(signature, canonical, _PADDING, _HASH)
    except InvalidSignature:
        return False
    return True


def verify(token: str, public_pems: list[str]) -> dict[str, Any] | None:
    """Verify `token` against every key in `public_pems`, in order, and
    return the payload from the first one that checks out -- or `None` if
    none do, or `token` is not well-formed at all.

    This is the one function this whole module exists for: **rotation must
    never invalidate the past.** A certificate signed under a key since
    retired from service still verifies here as long as that key's public
    half is somewhere in `public_pems` -- see the module docstring's "how a
    verifier chooses" section for the recommended (but not required) order,
    and `test_signing.py`'s rotation test for the property itself.

    Returns `None`, never raises, for every failure mode: malformed JSON, an
    unsupported `"v"`, a payload that is not itself a JSON object, a
    signature that fails to base64-decode, a `public_pems` entry that is
    not a usable RSA public key (skipped, not fatal -- trying the next one
    is exactly what a rotated-key verifier needs), and, of course, a
    signature that does not check out against any key offered. A public
    verification page needs one boolean-shaped answer, not a `try`/`except`
    around a call it cannot recover from differently either way.

    `public_pems == []` is not a special case in the code below -- the loop
    simply never runs -- but it is a real, expected input, not only a
    theoretical one: `keys/signing/` legitimately holds no key at all until
    an operator generates the first one (see that directory's own
    `README.md`), and a caller that built its list by globbing an empty
    directory must still get a clean `None` back, never an exception and
    never a token accepted for want of anything to check it against.
    """
    try:
        parsed: Any = json.loads(token)
        if not isinstance(parsed, dict):
            return None
        if parsed.get("v") != WIRE_VERSION:
            return None
        payload = parsed["payload"]
        if not isinstance(payload, dict):
            return None
        signature = base64.b64decode(parsed["signature"], validate=True)
    except (KeyError, ValueError, TypeError):
        return None

    canonical = _canonical_bytes(payload)
    for public_pem in public_pems:
        if _verifies_with(public_pem, canonical, signature):
            return payload
    return None


def public_key_path(generated_on: date) -> Path:
    """Where the published public half generated on `generated_on` lives:
    `keys/signing/<date>.pub`, relative to the repository root. Pure path
    computation -- reads nothing; see the module docstring's "key layout"
    section for the naming convention, the recommended verify order, and
    the one documented collision (two rotations on the same calendar day).
    """
    return repo_root() / KEYS_DIR / f"{generated_on.isoformat()}.pub"
