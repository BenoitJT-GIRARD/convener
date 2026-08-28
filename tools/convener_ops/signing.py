"""The certificate signing key pair: who may say "this is real," forever.

A stranger who receives a certificate can confirm it without an
account, a login, or a request to us -- a public verification page
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

- An event key (`eventkeys.py`) is *destroyed* at the end of retention.
  Destruction is the point: it is what makes already-
  committed ciphertext permanently unreadable, and that irreversibility is
  the provable half of the retention promise.
- A signing key is *never* destroyed. Retiring one from active service --
  no longer used to sign new certificates -- must not invalidate a single
  certificate it already signed, which is why every superseded public key
  stays published rather than being withdrawn. A certificate is meant to
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
only has to hold for the 90-day retention window before
it is destroyed outright; a signing key has to hold for as long as any
certificate it ever signed still needs to verify, which this module's whole
design says is forever. NIST guidance rates 2048-bit RSA through roughly
2030 and 3072-bit meaningfully longer; given this key is generated rarely
and verified rarely (a stranger checking one certificate at a time, not a
high-throughput service), the larger size costs nothing that matters and
buys margin on the one parameter that cannot be revised after the fact
without minting a new key and asking a verification page to trust two.

The wire format transports what it signs -- it does not ask a verifier to rebuild it
---------------------------------------------------------------------------------------
`sign`'s return value, and `verify`'s `token` argument, is one compact JSON
string -- the same idiom `eventkeys.py`'s wire format uses, for the same
reason: `JSON.stringify` and `json.loads` read and write it on either side
without a library::

    {"v":1,"payload":"<base64 of the exact bytes signed>","signature":"<base64>"}

- ``v`` -- format version; 1 today, the same discipline as `eventkeys.py`'s
  own `"v"` field. `verify` rejects anything else.
- ``payload`` -- standard base64, the *exact bytes `sign` computed once and
  handed to RSA*. Not a nested JSON object.
- ``signature`` -- the raw PKCS1v15 signature over those same bytes,
  standard base64.

**This module's first cut got this wrong, and it is worth recording why, so
nobody "simplifies" it back.** The original wire format embedded `payload`
as a nested JSON object and had `verify` re-derive the signed bytes by
re-serialising it (`json.dumps(payload, sort_keys=True, separators=(",",
":"))`) before checking the signature. That makes the *exact byte sequence
a signature covers* a cross-language contract every verifier must
reproduce: `sort_keys`, `separators`, `ensure_ascii`, all of it, forever,
independently, in Python here and in whatever the verifier is written in.
Measured directly against this module's own certificate fixture: Python's
`json.dumps` emits `2.0` for a duration where `JSON.stringify` emits `2`,
and `\\u00c9` for an accented name where `JSON.stringify` emits the
character literally -- and a French name and an hours figure are exactly
the payload's *ordinary* content, not an edge case reachable only by
misuse. A verifier built against that first design would reject genuine
certificates the moment it hit real data, and the natural fix under time
pressure -- loosen the comparison -- is exactly how a verifier stops
verifying anything.

The fix is not to document the cross-language byte contract more
carefully. It is to not have one: `sign` computes the canonical bytes
**once**, signs exactly those bytes, and hands the verifier the *same
bytes*, base64-encoded, inside the token. `verify` never recomputes
anything -- it base64-decodes `payload`, checks the signature against
those decoded bytes directly, and only *then* `json.loads`es them to get a
displayable dict. A verifier in any language needs three primitives every
language already has for free (base64 decode, RSA-PKCS1v15-SHA256 verify,
JSON parse) and zero shared formatting knowledge. This is the same
discipline the PKCS1v15-over-PSS choice above already argues for one
parameter (`saltLength`); applied here, it removes an entire parameter --
canonicalisation -- rather than pin it.

`_canonical_bytes` still exists and is still used -- by `sign`, exactly
once, to decide what those bytes are. `verify` does not call it: there is
nothing left in this module for it to recompute. Standard base64, not
"base64url" -- this repository already has one base64 convention
(`eventkeys.py`'s wire format: "every base64 field uses the standard
alphabet"), and introducing a second dialect for a value that sits inside
a JSON string, never a URL, would be a needless inconsistency for zero
benefit.

Only these three fields are ever read. **No other field in a token is
ever consulted for anything**, and none should be added that would be --
this is not JWT, there is no negotiable `alg`, and the algorithm
(RSA-PKCS1v15-SHA256) is fixed by this module's own code, never read from
the token. A verifier "helpfully" written by pattern-matching on JWT
examples is the concrete risk this sentence exists to head off: JWT's own
history includes exactly this mistake (a verifier that honours a
token-supplied `alg`, including `"none"`). Grafting an `alg` field onto a
token here would ride along unauthenticated (nothing outside `payload`'s
bytes is ever covered by the signature) and must never be allowed to
change what algorithm a verifier uses.

The payload's shape is enforced here, not left to `certificate.py`
----------------------------------------------------------------------
`sign` refuses any payload whose key set is not exactly `PAYLOAD_FIELDS`
below (`identifier`, `event`, `name`, `date`, `duration_hours` -- exactly
what a certificate carries). This module's first cut left `sign`
content-agnostic, the same way `eventkeys.encrypt` is agnostic about a
registration's fields, and argued the discipline of "no address" belonged
to `certificate.py` alone. That reasoning does not survive contact with
what a generic signer actually permits: a payload carrying `address` and
`postal_address` signs exactly as cleanly as one that does not, and
travels inside the token **in the clear** for anyone holding the
certificate to read -- which is precisely the property "what is not in the
payload cannot leak from it" depends on never being true. `sign` is the
one place in the whole certificate pipeline where that property can be
made a checked fact instead of a convention a future `certificate.py` edit
could quietly stop honouring. `verify` does not re-check this: its job is
to authenticate whatever was genuinely signed, not to second-guess it, and
every payload `sign` has ever accepted already satisfies it by
construction.

Key layout: `instance/keys/signing/<YYYY-MM-DD>.pub`, and how a verifier chooses
--------------------------------------------------------------------------
`public_key_path(generated_on)` returns `instance/keys/signing/<date>.pub` -- the day
the pair was generated, ISO 8601, the same sortable-by-filename idiom
`eventkeys.py` uses for event ids, chosen here for a second reason: sorting
these filenames *is* sorting the keys by age, with no separate manifest
file to keep in sync. Every key this project ever generates is committed
here, forever -- rotating a key out of *service* (no longer used to sign
new certificates) never means removing its file. The promise that an
already-issued certificate keeps verifying after a rotation is kept
entirely by this file simply staying put; there is no companion
"retire" or "destroy" operation in this module, on purpose (see above). See
`instance/keys/signing/README.md` for the current, real state of that directory and
what a verifier should do with it.

`verify` accepts an ordered list, `public_pems: list[str]`, and tries each
in turn, returning the payload from the first one that checks out. The
order is the caller's choice, not this module's -- but the convention this
module's own layout implies, and the one the build step and any
future caller should follow, is **newest first**: list `instance/keys/signing/*.pub`,
sort filenames in *descending* order, and build the list from that. Almost
every verification is of a certificate signed under the key currently in
service, so that ordering makes the common case the cheapest one --
correctness never depends on getting the order right, only on the right key
being *somewhere* in the list, which is exactly what the rotation test
below proves.

One naming collision to avoid, the same shape as `eventkeys.py`'s own:
generating two signing keys on the same calendar day collides on the same
filename. Keys are rotated by deliberate operator action, not automation,
so this is a documented operational constraint -- do not rotate the signing
key twice in one day -- rather than something this module can detect; it
holds no registry of what is already committed to check against.

Verify before you parse: the envelope is unauthenticated, the payload never is
------------------------------------------------------------------------------
`verify` checks the signature against the decoded `payload` bytes
*before* it ever calls `json.loads` on them. Two different parses happen
inside this function, and they are not the same kind of parse:

- The **envelope** -- the outer `{"v":..., "payload":..., "signature":...}`
  object -- is necessarily parsed unauthenticated. There is no signature
  to check until one has been read out of that structure, so this parse
  has to come first; this is the same position a JWS envelope occupies.
- The **payload** -- what `payload` base64-decodes to -- is never parsed
  until some key in `public_pems` has confirmed that the bytes about to
  be parsed are the exact bytes that key signed. Nothing this module ever
  does authenticates a payload *after* reading it; the order is the
  guarantee.

The first version of this module got the second half backwards:
`json.loads(canonical)` ran inside the same `try` as the envelope parse,
ahead of the signature loop, so every token's payload was parsed whether
or not any key ever confirmed it. In Python the gap was harmless --
bounded by `MAX_TOKEN_BYTES`, and `RecursionError` was caught either way
-- and that is exactly why it is worth fixing anyway rather than filing
away as low-severity: this module is the reference implementation for
the browser-side verifier, and a verifier ported from the control
flow rather than from `instance/keys/signing/README.md`'s numbered steps inherits
"parse untrusted bytes before authenticating them" in a language whose
JSON parser this project does not control -- the one habit this module's
whole design argues against. One consequence fell out by accident, not by
design: once the payload parse only ever runs after a signature has
matched, a hostile deeply-nested payload can no longer reach `json.loads`
at all unless it was signed by one of our own keys -- see the
`RecursionError` bullet below for what that leaves as the one deep-nesting
path an outside attacker still has.

Reordering moved one outcome, deliberately, and it is worth naming so
nobody mistakes it for a regression later: transported bytes that are
valid base64 but not JSON used to return `MALFORMED` on their own,
because `verify` peeked at them regardless of who signed them. Now, an
*unsigned* token of that shape returns `NO_MATCHING_KEY`, and only a
token that *is* signed by one of our own keys and still fails to parse
returns `MALFORMED`. That is the more honest taxonomy, not a loosening:
for an unsigned blob, "no key confirms this" is true, and "this is
malformed" is a claim this module could only make by doing the thing it
says it will not do -- reading a payload before a key has vouched for it.
And `MALFORMED` now means what it always should have: *we* signed
something we cannot read, which is this module's bug, never the token
holder's.

Three outcomes, not two: `verify` returns a `VerifyResult`
---------------------------------------------------------------
A public verification page has to say something different for "this
certificate is genuine" than for "we could not confirm this," and those
two must never look the same as each other -- but "we could not confirm
this" itself is not one thing. `verify` reports three outcomes, not the
`dict | None` this module's first cut returned:

- **Valid** (`reason is None`, `payload` holds the dict): some key in
  `public_pems` produced a matching signature over the decoded `payload`
  bytes, and those bytes, only now parsed, are a JSON object.
- **`MALFORMED`**: either (a) the *envelope* is not even shaped like
  something this module ever produced -- not JSON, the wrong top-level
  shape, an unsupported `"v"`, or `payload`/`signature` that will not
  base64-decode -- or (b) a key in `public_pems` genuinely confirmed the
  decoded `payload` bytes, but those bytes do not parse as a JSON object
  once read. Case (b) can only happen if something signed by one of our
  own keys was never valid JSON to begin with -- our bug, never a
  forger's, and see "verify before you parse" above for why a token an
  outside attacker controls can never reach this case at all.
- **`NO_MATCHING_KEY`**: the envelope parses correctly -- it is JSON, its
  version is understood, `payload` and `signature` are valid base64 -- but
  no key in `public_pems` produces a signature that matches the decoded
  `payload` bytes. This is the outcome for a token whose decoded payload,
  had anyone gone looking, would not even be JSON: unlike this module's
  first cut, `verify` never learns that about a token no offered key
  confirms, because it never parses it.

**`NO_MATCHING_KEY` is not "forged," and must never be presented as
one.** A well-formed token that no offered key validates is exactly what a
tampered or forged certificate looks like from here -- and *exactly* what
a genuine certificate looks like when it was signed under a key this
caller's `public_pems` list does not (yet) include, which
`docs/reference/operations.md`'s own publish-before-secret ordering
warning names as a real, reachable failure mode: sign first, publish the
`.pub` second, and every certificate issued in between is genuine and
currently unconfirmable. This module has no way to tell those two apart --
doing so would require trusting some claim inside the token about which
key it was signed with, and a claim like that is exactly the kind of
unauthenticated field the paragraph above warns against; a forger can
write any claim they like into an unsigned field. So `NO_MATCHING_KEY`
reports the honest, narrower fact: *this caller does not currently hold a
key that confirms this token* -- not a verdict on the certificate itself.
A verification page must show a "cannot confirm" state for this outcome,
never an accusatory one, and must not collapse it together with
`MALFORMED`: a stranger who mistypes a certificate code and a stranger
holding a real, currently-unconfirmable certificate are not the same
situation and should not read the same message.

Two more properties `verify` guarantees regardless of input:

- **`public_pems == []` is not a special case in the code below** -- the
  trial loop simply never runs, falling straight to `NO_MATCHING_KEY` --
  but it is a real, expected input, not only a theoretical one:
  `instance/keys/signing/` legitimately holds no key at all until an operator
  generates the first one (see that directory's own `README.md`), and a
  caller that built its list from an empty directory listing must get the
  same honest "cannot confirm" outcome as any other unmatched token, never
  an exception and never acceptance for want of anything to check against.
- **`verify` never raises, for any input, including a hostile one.** A
  token is untrusted, attacker-controlled input by construction -- it is
  read off a document a stranger controls. Beyond refusing malformed
  shapes, this module bounds the raw token to `MAX_TOKEN_BYTES` before
  parsing anything (a legitimate token is a few hundred bytes; nothing
  this module ever produces approaches the bound) and catches
  `RecursionError` around *both* parses -- the envelope's and, separately,
  the payload's -- because Python's JSON decoder recurses on nested
  structures and a short, deliberately deeply-nested string can exhaust
  the interpreter's recursion limit well under any reasonable size cap.
  `MALFORMED` is the outcome for all of it -- a public verification page
  must never crash because someone pasted an adversarial string into it.
  Only the envelope's `RecursionError` is reachable by an attacker who
  does not hold a signing key, per "verify before you parse" above: a
  deeply-nested `payload` never reaches the second parse unless a key
  already confirmed it, which no forged or unsigned token can arrange.

The private half, and why its absence is an ordinary D-13 state here
------------------------------------------------------------------------
Unlike `eventkeys.py`'s private half, there is exactly one signing private
key in service at a time, held as the repository secret `CONVENER_SIGNING_KEY`
(`config/integrations.yml`), read only inside the job that issues
certificates and never elsewhere. Rotating it means: an
*operator* -- a person, interactively, never an automated step and never
this module acting on anyone's behalf -- runs `generate()`, commits the new
public half under a new date, and only then replaces the `CONVENER_SIGNING_KEY`
secret with the new private half, pasted directly into GitHub Secrets and
never written to a file at any point. That is the same publish-before-secret
ordering `eventkeys.py`'s own operations doc already argues for event keys,
and for the same reason: setting the secret first would let a job sign a
certificate under a key with no public half yet committed for anyone to
verify it against -- see `NO_MATCHING_KEY` above for exactly what that
produces on the verifying end. `generate` itself has no opinion on who
calls it or how the result is handled -- it is
`docs/reference/operations.md`'s "Certificate signing key" section, not
this module, that is the place this constraint is a procedure rather than
only a property of the function.

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
import binascii
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from . import paths

#: RSA modulus size for a signing key -- 3072, not `eventkeys.RSA_KEY_BITS`
#: (2048). See the module docstring's "Key size" section for why a key
#: meant to verify forever is sized differently than one meant to hold for
#: 90 days.
RSA_KEY_BITS: Final = 3072

#: The wire format version written into every token's `"v"` field.
WIRE_VERSION: Final = 1

#: A token's exact top-level key set -- exported so another module pinning
#: "this string is a signing token" has one definition to check against,
#: the same role `eventkeys.ENVELOPE_FIELDS` plays for a ciphertext
#: envelope. Not enforced as a strict equality inside `verify` itself (an
#: unrecognised extra field is ignored, never consulted -- see the module
#: docstring's warning about a token acquiring an unauthenticated `"alg"`
#: field or similar; `verify` must never start reading one).
TOKEN_FIELDS: Final = frozenset({"v", "payload", "signature"})

#: The certificate payload's exact field set -- everything a certificate
#: carries and nothing else. `sign` refuses any payload whose keys
#: are not exactly this set. See the module docstring's "payload's shape"
#: section for why this is enforced here rather than left to
#: `certificate.py` as a convention.
PAYLOAD_FIELDS: Final = frozenset(
    {"identifier", "event", "name", "date", "duration_hours"}
)

#: The largest raw token `verify` will attempt to parse, in UTF-8 bytes. A
#: real token (the certificate fixtures in this module's own tests) is a
#: few hundred bytes; this is generous headroom, not a realistic ceiling --
#: its job is to refuse a hostile input outright, cheaply, before any
#: parsing touches it, rather than to bound legitimate content.
MAX_TOKEN_BYTES: Final = 8192

#: Where the published public halves live, relative to the repository root.
KEYS_DIR: Final = paths.KEYS_DIR / "signing"

#: `VerifyResult.reason` for a token that does not even parse as a signing
#: token -- see `verify`'s docstring for the full list of what falls here.
MALFORMED: Final = "malformed"

#: `VerifyResult.reason` for a well-formed token that no offered key
#: validates. Deliberately not called "invalid" or "forged" -- see the
#: module docstring's "three outcomes" section for why that distinction
#: cannot be made from here, and what a verification page must display
#: instead.
NO_MATCHING_KEY: Final = "no_matching_key"

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
    `verify`: an unverifiable token is reported through `VerifyResult`,
    never an exception, because it is not this module's *caller's* mistake
    the way an unusable signing key is -- it is what an ordinary, untrusted
    input looks like to a public verification page that should never need
    a `try`/`except` to check a certificate."""


@dataclass(frozen=True)
class VerifyResult:
    """What `verify` returns -- always exactly one of three shapes, never
    an exception. See the module docstring's "three outcomes" section for
    what each means and, critically, what a verification page must display
    for each; the difference between `MALFORMED` and `NO_MATCHING_KEY` is
    not cosmetic.

    - Valid: `payload` is the certificate's dict, `reason` is `None`.
    - Not valid: `payload` is `None`, `reason` is `MALFORMED` or
      `NO_MATCHING_KEY`.
    """

    payload: dict[str, Any] | None
    reason: str | None

    @property
    def valid(self) -> bool:
        """`True` exactly when `payload` is present -- the one boolean a
        caller that only cares "is this genuine" needs, without having to
        know `reason`'s two failure spellings apart."""
        return self.reason is None


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
    """The exact bytes `sign` signs, computed once. Unlike this module's
    first cut, `verify` never calls this -- there is nothing left for it
    to recompute, because `sign` transports these same bytes, base64-
    encoded, inside the token. See the module docstring's "wire format"
    section for why that is the whole fix, not merely a smaller version of
    the old cross-language contract. `sort_keys`/compact separators/ASCII
    escaping are kept for a deterministic, easy-to-inspect internal
    representation -- no longer load-bearing for interoperability, since
    nothing outside this one call ever needs to reproduce them."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")


def _validate_payload_fields(payload: dict[str, Any]) -> None:
    """Refuses any payload whose key set is not exactly `PAYLOAD_FIELDS`.
    See the module docstring's "payload's shape" section for why this
    check lives in `sign` rather than in a future `certificate.py`."""
    fields = set(payload)
    if fields != PAYLOAD_FIELDS:
        unexpected = sorted(fields - PAYLOAD_FIELDS)
        missing = sorted(PAYLOAD_FIELDS - fields)
        detail = "; ".join(
            part
            for part in (
                f"unexpected field(s): {', '.join(unexpected)}" if unexpected else "",
                f"missing field(s): {', '.join(missing)}" if missing else "",
            )
            if part
        )
        raise ValueError(f"payload does not match the certificate schema -- {detail}")


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
    the clear, and is transported as the very bytes that were signed, not
    re-derived by a verifier).

    Raises `ValueError` if `payload`'s keys are not exactly
    `PAYLOAD_FIELDS` -- checked before the private key is even loaded, so a
    malformed payload never touches key material at all. Raises
    `SigningError` if `private_pem` is not a usable RSA private key.
    `PAYLOAD_FIELDS` pins the key *set*, not each value's type, so a
    payload can still carry a value `json.dumps` itself cannot serialise
    (a `date` object where a caller should have passed an ISO string, for
    instance) -- `sign` raises whatever `json.dumps` raises (`TypeError`)
    for that unwrapped, rather than translating it into `SigningError` or
    a domain-specific error: it is a mistake in what the caller built, not
    a signing failure.
    """
    _validate_payload_fields(payload)
    private_key = _load_private_key(private_pem)
    canonical = _canonical_bytes(payload)
    signature = private_key.sign(canonical, _PADDING, _HASH)
    token = {
        "v": WIRE_VERSION,
        "payload": base64.b64encode(canonical).decode("ascii"),
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    return json.dumps(token, separators=(",", ":"))


def derive_public_pem(private_pem: str) -> str:
    """The public half of `private_pem`, re-derived rather than read from a
    committed file.

    Mirrors `eventkeys.derive_public_pem` for an analogous reason: a job
    that holds `CONVENER_SIGNING_KEY` can confirm -- against
    `instance/keys/signing/<date>.pub` -- that the secret it was just handed is
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


def verify(token: str, public_pems: list[str]) -> VerifyResult:
    """Verify `token` against every key in `public_pems`, in order.

    Returns a `VerifyResult` -- never raises, for any input, including a
    hostile one. See the module docstring's "verify before you parse" and
    "three outcomes" sections for what `MALFORMED` and `NO_MATCHING_KEY`
    each mean and, critically, that they are not interchangeable:
    `MALFORMED` is "not shaped like a signing token at all, or signed by
    one of our own keys and still unreadable"; `NO_MATCHING_KEY` is
    "shaped correctly, but no key offered confirms it" -- which covers
    both a forged token and a genuine one signed under a key this caller
    does not yet have. A verification page must never present the second
    as the first.

    The payload is decoded and checked against every key in `public_pems`
    *before* it is ever parsed as JSON -- `json.loads` on the decoded
    `payload` bytes runs only once a key has confirmed those exact bytes
    are what it signed, never before. The outer envelope (`"v"`,
    `"payload"`, `"signature"`) is the one thing here parsed
    unauthenticated, of necessity: there is nothing to check a signature
    against until it has been read out of that structure.

    This is the one function this whole module exists for: **rotation must
    never invalidate the past.** A certificate signed under a key since
    retired from service still verifies here as long as that key's public
    half is somewhere in `public_pems` -- see the module docstring's "key
    layout" section for the recommended (but not required) order, and
    `test_signing.py`'s rotation test for the property itself.
    """
    if len(token.encode("utf-8", errors="surrogatepass")) > MAX_TOKEN_BYTES:
        return VerifyResult(None, MALFORMED)

    try:
        parsed: Any = json.loads(token)
        if not isinstance(parsed, dict):
            return VerifyResult(None, MALFORMED)
        if parsed.get("v") != WIRE_VERSION:
            return VerifyResult(None, MALFORMED)
        canonical = base64.b64decode(parsed["payload"], validate=True)
        signature = base64.b64decode(parsed["signature"], validate=True)
    except (KeyError, ValueError, TypeError, binascii.Error, RecursionError):
        return VerifyResult(None, MALFORMED)

    for public_pem in public_pems:
        if not _verifies_with(public_pem, canonical, signature):
            continue
        # A key has just confirmed these are genuinely the signed bytes --
        # only now is it safe to read them. See the module docstring's
        # "verify before you parse" section: this ordering, not merely the
        # size cap or the recursion guard, is what keeps an unauthenticated
        # payload from ever reaching `json.loads`.
        try:
            payload: Any = json.loads(canonical)
        except (ValueError, TypeError, RecursionError):
            return VerifyResult(None, MALFORMED)
        if not isinstance(payload, dict):
            return VerifyResult(None, MALFORMED)
        return VerifyResult(payload, None)
    return VerifyResult(None, NO_MATCHING_KEY)


def public_key_path(generated_on: date) -> Path:
    """Where the published public half generated on `generated_on` lives:
    `instance/keys/signing/<date>.pub`, relative to the repository root. Pure path
    computation -- reads nothing; see the module docstring's "key layout"
    section for the naming convention, the recommended verify order, and
    the one documented collision (two rotations on the same calendar day).
    """
    return paths.repo_root() / KEYS_DIR / f"{generated_on.isoformat()}.pub"
