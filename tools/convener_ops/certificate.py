"""Issue a certificate of attendance, and keep a register of it whose
*public projection* -- an identifier and a state, nothing else -- really
could be published on a lamp-post. The register itself is a narrower
claim than that; see "the fingerprint is reversible, given the salt"
below (Important 8, fix round 1) for what it can and cannot survive being
read by a stranger who also holds `CONVENER_MATCHING_SALT`.

Phase 4 spec S:7 draws the line this whole module exists to enforce: the
*document* a participant receives carries their name, because a certificate
with no name on it is not a certificate. The *register* we keep about it --
what survives here, in this repository, after the document has gone out --
carries none of that. "Identifiant de certificat, identifiant d'événement,
date d'émission, empreinte salée de l'adresse, état. Aucun nom, aucune
adresse." Not redacted, not hashed-but-reversible, not encrypted-but-held:
absent. `test_the_register_holds_no_name_and_no_address` below is written as
a sweep over every field the register type has, not a check on the two
fields a name or an address might have been tempted into -- see that test's
own docstring for why the difference matters.

How a document can name someone the register never stores
-----------------------------------------------------------
`issue` signs a payload -- `identifier`, `event`, `name`, `date`,
`duration_hours` (`signing.PAYLOAD_FIELDS`, task 11) -- and hands the whole
signed token back to its caller. The token is what goes on the document,
printed as text and encoded as the machine-readable code spec S:7 asks for
(`verification_url` below builds the address that carries it). Nothing
about *that* trip through this module ever reaches disk here: `issue`
returns the token, `cli.py` mails it (task 14), and this module's own
persistence -- the register -- only ever receives the `CertificateEntry`
this file defines, which has no field a name could occupy. The name lives
exactly once, in the token, in the recipient's own inbox. We do not keep a
second copy "just in case"; that copy is what spec S:1 forbids.

Two numbers a stranger must never be able to confuse (ruling 3)
-------------------------------------------------------------------
This module computes two different values from the same registration, and
conflating them would quietly undo the whole design:

- **`identifier`** -- `secrets.token_hex(16)`, pure randomness, 128 bits.
  Public: printed on the document, signed inside the payload, carried in
  the verification URL, and the only column the public projection exposes
  (`public_register` below). Its randomness is not a style choice --
  see "why the identifier must not be deterministic" below.
- **`fingerprint`** -- an HMAC of the participant's address, salted with
  `CONVENER_MATCHING_SALT`. Private: it lives only in the internal register
  (`data/events/<id>/certificates.yml`), is never signed into a payload,
  never printed, and `public_register` strips it before anything leaves
  this module for `public-data/certificates-public.json`.

Why the identifier must not be deterministic
-----------------------------------------------
A first draft of this module derived `identifier` the same way
`matching_code` derives its own value: HMAC the address, format the
digest, done -- free idempotence, because the same address always
produces the same identifier. That draft does not survive contact with
where the identifier ends up: **printed on the document, and published in
`certificates-public.json` for anyone to read.** A deterministic identifier
is a public, reversible function of an address the moment its formula is
known (and a formula this simple would not stay secret), which would let
anyone holding a handful of guessed addresses test them against the public
projection and learn who attended -- publishing exactly the fact this
module exists to keep unpublished. So identifier and fingerprint are
computed differently on purpose: `identifier` gets its guarantees from
*true* randomness (nothing to invert, because nothing was derived), and
`fingerprint` gets its privacy from a *salted* derivation that is only
ever compared, never published. Idempotence -- not reissuing a second
certificate to the same person for the same event -- is bought a different
way instead: see "Idempotent without being deterministic" below.

The fingerprint's own HMAC domain, and why it cannot reuse `matching_code`'s
--------------------------------------------------------------------------------
`registration.matching_code` already HMACs `event_id` and a normalised
address under `CONVENER_MATCHING_SALT` -- and that value is **sent to the
participant** in their confirmation e-mail (task 7), so it is not a secret
from them, only from a stranger. If `fingerprint` below hashed the exact
same bytes under the exact same key, it would not be a second value: it
would be a second *name* for `matching_code`, and the "private, never
published" half of the design above would be publishing the matching code
itself the moment `public_register` (which strips `fingerprint`, not
`identifier`... this sentence is about the *register* file, which is not
public, but is read by anyone with repository access, and a certificate
register whose "private" column was secretly the participant's own,
already-mailed matching code would not be private at all).

So `fingerprint` prefixes its input with `_FINGERPRINT_DOMAIN`, a constant
naming this derivation's purpose and version, before the event id and the
normalised address -- the same `salt`, a disjoint input space. Two HMACs
under one key, computed over inputs that cannot collide because one of
them starts with a string the other's input space cannot produce (`\0`
after a name that itself contains no NUL), are two unrelated values as far
as anything downstream can tell -- this is the ordinary domain-separation
discipline for reusing one key across more than one derivation, applied
here because `matching_code` already claimed the key for one purpose
first.

Idempotent without being deterministic
------------------------------------------
Spec S:8: "un appariement corrigé se recalcule sans réinscrire" -- a
corrected match recalculates without re-registering. `issue` below is
called with the *whole current register* for the event (`existing`), looks
up `fingerprint` against every entry already in it, and reuses that
entry's `identifier` and `issued_on` when found rather than minting a new
one. A second call for the same person, whether a delivery is being
retried (task 14) or the same job simply ran twice, produces
`already_registered=True` and never grows the register --
`test_reissuing_the_same_attendee_does_not_grow_the_register` below is
one of this task's mutation-tested guarantees.

That lookup is also what makes a retried delivery reproduce the *same*
document, not merely the same register row. `signing.sign` uses
RSA-PKCS1v15, which is deterministic (see that module's own docstring for
why PSS's randomised salt was rejected) -- so signing the same payload dict
twice under the same key produces byte-identical tokens. Once `identifier`
is pinned by the register lookup, every other payload field (`event`,
`name`, `date`, `duration_hours`) is already a pure function of the same
inputs `issue` was called with, so calling `issue` again for an
already-registered attendee reproduces the exact token the first call
did -- which is what lets task 14 say "a failed delivery replays without
regenerating" and mean it literally: nothing is regenerated, because
recomputing and regenerating give the same bytes.

**A "corrected match" is not always the safe case above (Important 3,
fixed by R-18).** The reuse this section describes is a retry: the same
inputs, called again, reproduce the same bytes. A correction that changes
what gets *signed* -- a mis-typed name, a duration fixed after an
attendance export was repaired -- is a different thing: calling `issue`
again for it reuses the *old* identifier but signs a *new* payload, which
leaves two contradictory tokens both verifying under one register row,
neither distinguishable from the other. `issue` cannot fix that itself
(see `reissue`'s own docstring for why widening this lookup to skip
revoked rows would be worse than the defect it was meant to solve); a
correction that changes signed content goes through `reissue` instead,
which requires the standing certificate to be revoked first and mints a
genuinely new identifier, precisely so the register can tell the two
documents apart.

The register survives the data it was derived from (ruling 2, for task 15)
--------------------------------------------------------------------------------
`data/events/<id>/registrations.enc` is destroyed -- the event's private
key deleted, its ciphertext left permanently unreadable -- 90 days after
the event (spec S:4, task 15). `data/events/<id>/certificates.yml` is a
**different file in the same directory, on a different, indefinite
lifetime**, and task 15 must not treat the two alike. The whole reason
this register holds no name and no address is so that its own survival
past that destruction is unconditionally safe: a certificate has to remain
checkable -- against revocation, at least -- for as long as an
accreditation body might ask about it, which spec S:7 explicitly extends
past the 90-day window ("les clés publiques antérieures restent
publiées, pour que la rotation n'invalide jamais un certificat déjà
émis"). Task 15's retention sweep must delete or rewrite
`registrations.enc` and leave `certificates.yml` in the same directory
completely untouched -- there is nothing in it retention could ever apply
to, because there was never anything identifying in it to begin with.

Revocation touches the register, never the signature (ruling 11)
----------------------------------------------------------------------
`revoke` flips one entry's `state` to `STATE_REVOKED` and returns a new
register. It has no access to, and does not need, the signing key: the
token issued earlier keeps verifying successfully forever, exactly as
`signing.verify` was built to guarantee across a key *rotation* -- a
revocation is not a rotation, but the same underlying fact applies, that a
signature attests authorship, not current standing. "Currently standing"
is answered by the register alone, and `state` is the only column that
answers it. A verifier (task 13) must check both: the signature (is this
genuine) and the register's state (is it still good) -- collapsing either
check into the other is the one mistake this split is built to prevent,
and `test_a_revoked_certificate_still_verifies_but_reports_revoked` below
is the test that catches a future edit doing exactly that.

The duration a document prints is rounded, on a written rule (ruling 10)
------------------------------------------------------------------------------
`duration_hours` rounds a summed attendance duration to the nearest
**quarter hour**, ties rounding **up** (`ROUND_HALF_UP`, not Python's
default banker's rounding, which would round a boundary case down as
often as up and could not be described as a rule to an accreditation body
in one sentence). Quarter-hour granularity, not a raw fraction: attendance
is measured to the second, but nobody accredits continuing-education
credit to five decimal places, and most accreditation schemes this project
has seen quote credit in quarter- or half-hour units already. Rounding up
on an exact tie -- rather than down, or to even -- is the direction that
never shortchanges a real 3600-second attendee whose duration happens to
land exactly between two quarter-hour marks; the alternative (round down
on a tie) would be defensible too, but only one of the two can be *the*
rule, and this module picks the one that never asks a participant to
accept less credit than the boundary they actually reached.

This is a genuinely signed, permanent value -- `duration_hours` is one of
`signing.PAYLOAD_FIELDS`, transported inside the token exactly as
`_canonical_bytes` renders it (see `signing.py`'s own docstring for why
the *bytes* a Python `float` renders as, `2.0` where a browser's
`JSON.stringify` would write `2`, cannot bite a verifier: the token
transports bytes, it does not ask anything to re-render the number). What
this module still has to get right, that transporting bytes does not fix
for free, is the *value* those bytes hold -- a duration a human reads on a
certificate for the rest of that certificate's life -- which is exactly
why the rounding rule above is written down rather than left as whatever
`duration_seconds / 3600` happens to produce.

`CONVENER_MATCHING_SALT`'s absence is ordinary for `matching_code`, and is not ordinary here
------------------------------------------------------------------------------------------
`registration.matching_code` already documents its own salt as an
ordinary D-13 absence: without it, no code is derived, and spec S:5's
cascade (exact address, then normalised name) still finds the same
attendees. `fingerprint` below takes `salt: str`, not `str | None` --
deliberately narrower than `matching_code`'s own signature, because there
is no equivalent fallback here. A register entry's `fingerprint` is a
*mandatory* field (see `_ENTRY_FIELDS`); the only way to populate it
without a salt would be to hash the address unsalted, which a small,
guessable space of institutional addresses makes practically reversible --
publishing the address in every sense that matters, from a register this
whole module exists to keep clear of exactly that. So this is one of this
project's rare exceptions to D-13's "an absent integration is a normal
state": **`cli.py` must not call `issue` at all when `CONVENER_MATCHING_SALT`
is unset** -- no certificate issued this run, the same *outward* shape as
an ordinary D-13 absence (the job says so and exits cleanly), but for the
stronger reason the global constraints name: an absent key here forbids
writing, it does not license writing insecurely. `fingerprint` itself
enforces the narrower type rather than trusting every future caller to
remember the check; there is no code path in this module that can produce
an unsalted fingerprint by omission.

The fingerprint is reversible, given the salt -- and rotation has a cost
(Important 8, fix round 1)
------------------------------------------------------------------------------
Two claims about this register were stronger than what actually holds, and
both are corrected here rather than left standing. This module's own
opening line used to say a register of this shape "could be published on a
lamp-post" -- true of `public_register`'s output (identifiers and states,
nothing else), **not** true of `certificates.yml` itself: given
`CONVENER_MATCHING_SALT`, the address space this salt actually has to cover is
small and guessable (an institutional `first-initial.surname@domain`
shape, in practice a few hundred plausible guesses per person), so
recovering an address from its fingerprint costs a dictionary and
milliseconds, not a lifetime -- an *ordinary* property of any HMAC over a
low-entropy input, not a defect in the construction. Publishing this
register would let anyone who ever held the salt confirm attendance for
any guessed address; only the projection is the lamp-post artefact.
Likewise, `docs/toolkit/certificate.md` used to call the fingerprint
"never reversible in practice", unqualified -- the honest version is "not
reversible by anyone who does not hold the salt". The salt is the entire
protection, not a detail alongside it.

That has a consequence for rotation that nothing used to write down:
rotating `CONVENER_MATCHING_SALT` changes every fingerprint this module ever
computed, so `issue`'s own lookup (see "idempotent without being
deterministic" above) stops finding any of them -- every past attendee's
fingerprint fails to match, and the next `convener-issue-certificates` run
mints each of them a **second** certificate, exactly the double-issue the
fingerprint-keyed lookup exists to prevent. Unlike `CONVENER_SIGNING_KEY`,
which spec S:7 gives an explicit rotation story ("les clés publiques
antérieures restent publiées"), this salt has none: **the intended answer
is that `CONVENER_MATCHING_SALT` is never rotated once any event's register
exists.** If it ever leaks, the register's own protection depends on
issuing a new salt going forward and accepting that every certificate
already issued under the old one is described by an address space that is
no longer secret -- not on rotating the value in place, which breaks
idempotence for every event with a register already on file rather than
fixing anything.

The public projection: identifiers and states, nothing else (ruling 5)
-----------------------------------------------------------------------------
`public_register` is this module's other pure output: a list of
`{"identifier", "state"}` dicts, sorted by identifier, built from a
register the same way `public_data.to_public` builds `events-public.json`
from the speaker list -- an allowlist of exactly two columns, not a
denylist of the one column (`fingerprint`) that must never leave. `cli.py`
writes the result to `public-data/certificates-public.json`, following
`events-public.json`'s own precedent (`publish-vitrine.yml` copies that
file to the public showcase; a future workflow does the same for this
one). Task 13's verification page fetches this file for exactly one
purpose -- learning whether the identifier a certificate's own token
already named is currently revoked -- and never sees `certificates.yml`
itself, which is not published anywhere.

The verification address: one URL, carrying the token (ruling 7)
-----------------------------------------------------------------------
Spec S:7 lists "adresse de vérification" as part of a certificate's
printed content, and step 2 of this task separately asks for "un code
lisible par machine, contenant le jeton" -- read together, this module
treats the two as one element: `verification_url(identifier, token)`
returns a single address, printed as readable text and encoded as this
certificate's machine-readable code (a QR, rendered by whatever produces
the document itself -- out of this module's scope), carrying **both** the
identifier, as a path segment, and the token itself, as a query
parameter.

Both are needed, and for different reasons. Task 13's page must verify
*entirely offline* the moment it loads (that task's own brief, step 2) --
with no request to us for the payload or the signature -- which is only
possible if the URL already carries the token; a page that had to fetch
the token from us first would not be verifying "without owning anything",
it would be asking us to hand a stranger a name on request, exactly the
kind of on-demand disclosure this whole design exists to avoid. The
identifier is redundant with the payload's own `identifier` field once the
token has been verified (`signing.PAYLOAD_FIELDS` includes it) -- but it
is what lets a verifier's route match one certificate to one address
*before* verification has run at all, so the page can be a plain,
bookmarkable link rather than requiring the visitor to paste a token in by
hand.

**Task 7 moved this page off the operators' application entirely, onto its
own static page mounted as an island** (`site/src/verify.njk`,
`app/src/islands/verify/`) -- the same move task 6 made for registration
(`site/src/event.njk`, `app/src/islands/signup/`), so a stranger checking
a certificate no longer downloads the whole operators' cockpit -- its
routing, its authentication, every screen -- to read four lines back.
Registration's own move is not the template for the *address*, though:
`registration.SIGNUP_BASE` moved onto a real, bare path
(`site/src/event.njk`'s own permalink) because `signup_url` only ever
carries an event id, nothing a server log could turn into a person.
`verification_url` carries a **name**, so `VERIFICATION_BASE` keeps
routing through a URL fragment even though it no longer routes through
`App.tsx` -- see the next paragraph for why that half could not move with
the rest. `VERIFICATION_BASE` and the whole address are pinned into this
module's shared fixture (`tools/tests/fixtures/certificate-verification.json`,
see below) so the island is bound to the exact shape rather than trusted
to reconstruct it from this docstring.

The fragment is not a routing detail -- it is the second, more important
privacy property, and it is why the move above kept it. `VERIFICATION_BASE`
ends in `#/`, so the `?token=` `verification_url` appends sits *inside the
URL fragment*, everything after `#`. A fragment is never sent in an HTTP
request (a browser resolves it locally and never transmits it to the
server) and is stripped from `Referer` before a page navigates away. The
token carries the holder's **name** (`signing.PAYLOAD_FIELDS`'s own
`name` field) -- so serving this page from a bare path instead, the way
`SIGNUP_BASE` was moved, would silently start sending every verified
participant's name to GitHub's servers in a query string, and to whatever
site a link is clicked from after, through `Referer`. The static page at
`VERIFICATION_BASE`'s own host and path reads `location.hash` itself,
exactly as well as `App.tsx`'s old `HashRouter` route did -- a router is
not what made the fragment safe, and losing the router when task 7 moved
this page off `App.tsx` does not lose the property either.
`test_verification_url_carries_the_token_after_the_fragment_not_before_it`
below is what would catch a future edit losing it anyway; the property is
pinned as a test, not left as a paragraph a future editor might not read.

The shared fixture (D-14) -- what stops task 13 verifying nothing
------------------------------------------------------------------------
`tools/tests/fixtures/certificate-verification.json` holds a **real
signed token**, generated once by this task from a throwaway key pair
whose private half was never written to disk and is not recoverable from
anything committed -- only the public half and the token it produced are
in the fixture, both of which are safe to publish by the very design
`signing.py` argues for (a public key's whole job is to be public; a
token's payload sits in the clear by construction, "signing is not
encryption"). Committed rather than generated fresh by each test, because
task 13 is TypeScript and cannot invoke `signing.generate()` to produce
its own matching pair -- a fixture that regenerated itself every run would
give the two languages two different tokens to agree about, which is no
contract at all. The fixture also carries: the two `signing.verify`
`reason` spellings (`MALFORMED`, `NO_MATCHING_KEY`) -- already pinned
Python-side by `test_signing.py`'s own
`test_the_two_reasons_keep_the_spelling_that_crosses_the_language_border`,
which names this fixture as the thing that would eventually bind both
sides -- this module's own two `state` spellings (`STATE_ISSUED`,
`STATE_REVOKED`), a worked `public_register` shape, and `VERIFICATION_BASE`
plus one complete `verification_url` example. A verification page built
without ever reading this file could still compile, still render, and
still verify nothing real; this file is the thing task 13's own tests
check themselves against instead.
"""

from __future__ import annotations

import hmac
import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote

from . import published
from .attendance import MatchedAttendee
from .registration import normalize_email
from .signing import sign

__all__ = [
    "EVENTS_DIR",
    "FILE_VERSION",
    "ORGANISER",
    "STATE_ISSUED",
    "STATE_REVOKED",
    "VERIFICATION_BASE",
    "CertificateEntry",
    "CertificateEvent",
    "IssueResult",
    "certificates_path",
    "duration_hours",
    "fingerprint",
    "full_name",
    "issue",
    "public_register",
    "register_from_data",
    "register_to_data",
    "reissue",
    "revoke",
    "sign_for",
    "verification_url",
]

#: The organisation's own name, printed on the document as spec S:7's
#: "organisateur". A module constant, not a `data/config.yml` key: it does
#: not vary between events (ruling 8), so a config key here would buy a
#: TypeScript ripple -- `types.ts`, `validate.ts`, `CONFIG_KEYS`,
#: `readConfig`, every hand-built `Config` literal in the app's tests, a
#: regenerated `schema.md` -- for a value that is, in fact, a constant.
ORGANISER: Final = "The Example Collective"

#: The base of every certificate's verification address -- see the module
#: docstring's "verification address" section for the full route shape and
#: why it carries the token, not only the identifier. Task 7 moved this
#: off `app/src/App.tsx`'s own `HashRouter` route onto its own static page
#: (`site/src/verify.njk`'s permalink, `/verify/`), mounted as an island
#: (`app/src/islands/verify/`) -- but the host and path still end `#/`,
#: unchanged in kind though not in host: that is load-bearing beyond
#: routing, not a routing detail at all. It puts `verification_url`'s
#: `?token=` -- which carries a participant's name -- inside the URL
#: *fragment*, which browsers never send in a request and always strip
#: from `Referer`. Serving this page from a bare path instead, the way
#: task 6 moved `registration.SIGNUP_BASE`, would silently lose that
#: property; see the module docstring's "verification address" section and
#: `test_verification_url_carries_the_token_after_the_fragment_not_before_it`.
#:
#: **Phase 10, task 2:** the host and prefix now come from
#: `config/instance.json` through `published.load()`, the one declaration
#: every published address in this repository is built from. The value for
#: this instance is byte-identical to the literal it replaces -- a
#: certificate already delivered carries this address printed on it, and
#: changing an address that has already gone out is a maintainer's call,
#: not a refactor's. `verify/` is the product's own route
#: (`site/src/verify.njk`'s permalink) and `#/` is the privacy property
#: above, so both stay written here: neither is anything an instance
#: configures.
VERIFICATION_BASE: Final = f"{published.load().under('verify/')}#/"

#: `certificates.yml`'s own format version -- the file-level analogue of
#: `registration.FILE_VERSION`.
FILE_VERSION: Final = 1

#: `CertificateEntry.state` -- a certificate stands, cryptographically,
#: forever (`signing.verify` never consults this register at all); these
#: two values are the register's own answer to "does it currently stand".
#: Spellings pinned into the shared fixture (see the module docstring) the
#: same way `signing.MALFORMED`/`signing.NO_MATCHING_KEY` are, because
#: task 13 (TypeScript) compares literal strings, never a Python constant.
#:
#: Exactly these two, and no third value for "not yet delivered" (R-20,
#: fix round 1, task 12): this register is authoritative on *validity*,
#: not on delivery logistics, and the projection built from it
#: (`public_register` below) is public forever -- "issued but never
#: delivered" is operational detail about one identifiable certificate
#: that buys a reader of the public feed nothing. Delivery is replayable
#: by re-sending (spec S:8), so it needs no state here; task 14 records or
#: derives it somewhere else.
STATE_ISSUED: Final = "issued"
STATE_REVOKED: Final = "revoked"
_STATES: Final = frozenset({STATE_ISSUED, STATE_REVOKED})

#: A certificate register entry's exact field set. See `register_from_data`.
_ENTRY_FIELDS: Final = frozenset(
    {"identifier", "event_id", "issued_on", "fingerprint", "state"}
)

#: The identifier's byte length (`secrets.token_hex`): 128 bits. See the
#: module docstring's "two numbers" section for why this value is random
#: rather than derived, and `registration._CODE_SYMBOLS` for the unrelated,
#: much shorter, *spoken* code this is not trying to be -- an identifier
#: here is read by a machine (a URL, a QR code), never read aloud, so
#: nothing about it needs to be short or unambiguous by ear.
_IDENTIFIER_BYTES: Final = 16

#: `_new_identifier`'s own output shape, by construction: `token_hex(16)`
#: is always exactly 32 lowercase hex characters. Minor 2, fix round 3:
#: `CERTIFICATE_ID` reaches `cli.py::reissue_certificate` and
#: `cli.py::revoke_certificate` straight from an operator's own
#: `workflow_dispatch` input, validated by nothing before this, and echoed
#: into the job's own log once a lookup succeeds. `.strip()` alone removes
#: a *leading or trailing* newline but not one embedded in the middle, so
#: an id shaped `"abc\n::add-mask::secret"` would put a GitHub Actions
#: workflow command at the start of a log line -- the same class of gap
#: `eventkeys.secret_name` already closes for `EVENT_ID` with its own
#: one-line shape check (`_EVENT_ID_RE.fullmatch`, which a value carrying
#: an embedded newline also fails, since the token alphabet admits none).
_CERTIFICATE_ID_RE: Final = re.compile(r"^[0-9a-f]{32}$")


def is_valid_identifier(identifier: str) -> bool:
    """Whether `identifier` has the exact shape `_new_identifier` produces
    -- 32 lowercase hex characters, nothing more, nothing embedded. Callers
    that read a certificate id from an untrusted source (an operator's own
    `workflow_dispatch` input, in practice) call this immediately, before
    that value is ever echoed into a log line -- see this module's own
    `_CERTIFICATE_ID_RE` for the guard this checks."""
    return bool(_CERTIFICATE_ID_RE.fullmatch(identifier))


#: This derivation's own domain -- see the module docstring's "fingerprint
#: domain" section for why this exists at all: `registration.matching_code`
#: already claims `CONVENER_MATCHING_SALT` for one HMAC input space, and this is
#: a second, disjoint one under the same key. The version suffix exists so
#: a future, incompatible change to what gets hashed (a fifth input added,
#: say) can mint `-v2` rather than silently reusing `-v1`'s domain for
#: different bytes.
_FINGERPRINT_DOMAIN: Final = "convener-certificate-fingerprint-v1"

#: The rounding grain `duration_hours` snaps to, and the tie-break rule --
#: see the module docstring's "duration a document prints" section.
_ROUNDING_INCREMENT: Final = Decimal("0.25")
_SECONDS_PER_HOUR: Final = 3600

#: The longest event title this module will ever sign or display, in
#: characters (Important 3, fix round 1). `delivery.py`'s own module
#: docstring already assumed "two 200-character names plus a
#: 300-character event title" as the realistic worst case when it chose
#: `_QR_ERROR_LEVEL` -- this is that same number, now enforced here rather
#: than merely assumed. Measured by execution, not by a capacity table: a
#: title longer than roughly 705-1089 characters (depending on how long
#: the two signed names are) makes `segno.make` raise `DataOverflowError`,
#: which the bulk delivery command's own broad `except Exception` folded
#: silently into "not sent", forever, since every retry hit the identical
#: wall -- `event.title` comes from `data/speakers.yml`, bounded nowhere
#: before this. Truncated, not refused: unlike
#: `registration._MAX_FIELD_LENGTH` (a reputation bound on a *stranger's*
#: public-key-encrypted submission, refused rather than shortened because
#: truncating would still deliver an attacker's text), a title comes from
#: the organisation's own data, and a pasted abstract or a copy-paste
#: accident should not silently stop every attendee of the event from
#: receiving a certificate -- a shortened title is still recognisably the
#: same talk. Enforced once, in `CertificateEvent.__post_init__`, so every
#: caller -- `issue`, `reissue`, and every `render_certificate` call in
#: `cli.py`, all of which read `CertificateEvent.title` -- signs and
#: displays the identical, already-bounded string; a document showing one
#: title while the signed payload carries another is exactly what R-22
#: forbids, so this cannot be a truncation applied to the document alone.
_MAX_TITLE_LENGTH: Final = 300


@dataclass(frozen=True)
class CertificateEvent:
    """What `issue` needs to know about the event, beyond the attendee --
    deliberately not `confirmation.EventDetails`: that dataclass also
    carries a `Room`, which a certificate has no use for and which would
    drag a `Platform` dependency into a module that otherwise touches
    nothing but plain data.

    `title` becomes the signed payload's `event` field (spec S:7:
    "intitulé de l'événement" -- the human-readable name of the talk, not
    `event_id`); `date` becomes the payload's own `date` field, sourced
    from the same speaker record field `docs/reference/schema.md` documents
    as "YYYY-MM-DD of the talk, frozen at scheduling" -- the day the
    session happened, not the day a certificate for it was issued (that
    second date is `CertificateEntry.issued_on`, a genuinely different
    fact, which is why the two live on two different objects in this
    module rather than sharing one field).

    `title` is bounded to `_MAX_TITLE_LENGTH` characters, truncated here
    rather than refused (Important 3, fix round 1) -- see that constant's
    own comment for why. `__post_init__` on a frozen dataclass still needs
    `object.__setattr__` to apply the truncation; every other field is
    left exactly as given.

    `title_truncated` (carried item 8, fix wave 2): `True` exactly when
    the truncation above actually did something, `False` otherwise --
    never a constructor argument (`init=False`), always derived the same
    way `title` itself is. Before this, the truncation was silent: a
    signed, delivered certificate could quietly carry a shortened title
    with nothing anywhere telling an operator it happened. `cli.py`'s
    `issue_certificates` and `deliver_certificates` both read this flag,
    once, to print a `::warning::` naming the event -- the same
    discipline this module already gives R-26's revoked-refusal case,
    surfaced rather than swallowed."""

    event_id: str
    title: str
    date: str
    title_truncated: bool = field(default=False, init=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.title) > _MAX_TITLE_LENGTH:
            object.__setattr__(self, "title", self.title[:_MAX_TITLE_LENGTH])
            object.__setattr__(self, "title_truncated", True)


@dataclass(frozen=True)
class CertificateEntry:
    """One register row -- see the module docstring's opening section for
    what this deliberately does not carry. `event_id` is included even
    though `certificates.yml` already lives at
    `data/events/<event_id>/certificates.yml`: it is what lets
    `public_register`'s aggregation over *every* event's file still be
    traced back to the right one internally, and what lets `issue`, `reissue`
    and `revoke` (fix round 3) all refuse to match against the wrong
    event's entry if a caller ever hands one of them a register merged
    from more than one file by mistake."""

    identifier: str
    event_id: str
    issued_on: date
    fingerprint: str
    state: str


@dataclass(frozen=True)
class IssueResult:
    """What `issue` returns: the register row (freshly minted or reused --
    see `already_registered`) and the signed token to hand to whoever
    delivers it (task 14). `token` is recomputed on every call, never
    cached anywhere in this module -- see the module docstring's
    "idempotent without being deterministic" section for why recomputing
    it is exactly as good as replaying a stored one."""

    entry: CertificateEntry
    token: str
    #: `True` when `entry` already existed in the register `issue` was
    #: given -- this attendee has already been issued a certificate for
    #: this event, under this same fingerprint, and no new row was added.
    #: `False` when `entry` is freshly minted. The caller (`cli.py`)
    #: decides what to do with either: append `entry` to the register on
    #: `False`, leave it untouched on `True`.
    already_registered: bool


def fingerprint(event_id: str, email: str, salt: str) -> str:
    """The register's private, salted trace of one address -- see the
    module docstring's "two numbers" and "fingerprint domain" sections for
    what this is (an HMAC, domain-separated from `matching_code`'s own use
    of the same salt) and is not (reversible, published, or derived the
    same way `identifier` is).

    `salt` is `str`, not `str | None` -- unlike `matching_code`, which
    treats an absent `CONVENER_MATCHING_SALT` as an ordinary D-13 fallback, this
    function has no fallback to offer: a mandatory register field cannot be
    populated safely without a real salt (see the module docstring's
    "absence is not ordinary here" section), so the type itself refuses to
    let a caller pass `None` and get something back. `cli.py` must resolve
    the secret's presence *before* calling this at all.

    `normalize_email` keeps the same "same address, same value" property
    `matching_code` and `upsert` already rely on: two submissions of one
    address, differently capitalised, fingerprint identically."""
    digest = hmac.new(
        salt.encode("utf-8"),
        f"{_FINGERPRINT_DOMAIN}\0{event_id}\0{normalize_email(email)}".encode(),
        sha256,
    ).digest()
    return digest.hex()


def duration_hours(duration_seconds: int) -> float:
    """The signed `duration_hours` payload field -- see the module
    docstring's "duration a document prints" section for the rule this
    implements: round to the nearest quarter hour, ties rounding up.

    Uses `Decimal` throughout, never a raw `float` division, so the
    rounding decision is made against the exact rational value
    `duration_seconds / 3600`, not against whatever binary approximation a
    `float` division happened to land on either side of the boundary --
    the same reasoning `attendance.EligibilityThreshold.threshold_seconds`
    already applies to its own boundary comparison, via `Fraction` there
    and `Decimal` here (a `Decimal` suffices in this direction: the result
    is quantised to a fixed grain and then handed back as a `float` for
    JSON, whereas `threshold_seconds` is compared against, never rounded,
    so it keeps `Fraction`'s exactness all the way through).

    `duration_seconds` must already be bounded by the seminar's own
    scheduled length (`seminar_duration_minutes * 60`) before it reaches
    here (R-17, fix round 1, Critical 1) -- this function does not clamp
    it itself; `cli.py::issue_certificates` does, once, before calling
    `issue`, because that is the one place both the attendee's summed
    duration and `EligibilityThreshold.seminar_duration_minutes` are
    already in hand. The clamp is not a workaround for a double count, it
    is the correct number: a certificate attests attendance *of the
    seminar*, and the seminar's own scheduled length is what an
    accreditation body credits, not however long a participant's
    connections happened to add up to. It bounds two distinct causes the
    same way -- a session that overran its schedule, and a double count
    `attendance.match` cannot itself rule out: two rows for one person
    arriving from a reconnection and a genuinely simultaneous second
    device look identical by the time they reach this module, both sum,
    and neither this function nor `match` can tell them apart after the
    fact. Capping at the scheduled length is correct either way, because
    the certificate is never allowed to claim more than the seminar
    itself offered.

    Floored at zero (Minor 7, fix round 1): unreachable today --
    `attendance._duration` already floors at zero, so nothing this module
    calls ever passes a negative value -- but this function is public and
    `int` is signed, and `duration_hours(-5)` would otherwise render as
    `-0.0`, a value with no honest reading on a certificate.
    """
    hours = Decimal(max(0, duration_seconds)) / Decimal(_SECONDS_PER_HOUR)
    quarters = (hours / _ROUNDING_INCREMENT).quantize(
        Decimal(1), rounding=ROUND_HALF_UP
    )
    return float(quarters * _ROUNDING_INCREMENT)


def full_name(attendee: MatchedAttendee) -> str:
    """The exact name a certificate signs, and the exact name its document
    prints: first name and surname, joined by one space (task 14).

    Factored out of `_sign_certificate` so the payload `signing.sign`
    covers and the document `delivery.render_certificate` shows can never
    drift into two different ideas of "the name" -- the one property a
    signed document's whole design depends on: a certificate has to show
    exactly what its own signature attests, never a name computed a
    second, independently-maintained way. Before this, `_sign_certificate`
    was the only place this join happened; `delivery.py` calling
    `certificate.full_name` instead of re-typing
    `f"{attendee.registration.first_name} {attendee.registration.surname}"`
    a second time is what this function exists to make impossible to get
    wrong."""
    return f"{attendee.registration.first_name} {attendee.registration.surname}"


def _new_identifier() -> str:
    """A fresh, random certificate identifier -- see the module docstring's
    "why the identifier must not be deterministic" section. `token_hex`,
    not the spoken-safe alphabet `registration._CODE_ALPHABET` uses: this
    identifier is read by a machine, never read aloud, so nothing about it
    needs to avoid a confusable pair of characters."""
    return secrets.token_hex(_IDENTIFIER_BYTES)


def issue(
    attendee: MatchedAttendee,
    event: CertificateEvent,
    private_pem: str,
    salt: str,
    existing: Sequence[CertificateEntry],
    *,
    issued_on: date,
) -> IssueResult:
    """Issue a certificate for `attendee`'s attendance at `event`, or
    reproduce the one already on record -- see the module docstring's
    "idempotent without being deterministic" section for what "reproduce"
    means here and why it is safe to call this again for someone already
    registered.

    **Three-way, not two-way, since R-26 (fix round 1, Critical 1).** Looks
    `attendee`'s `fingerprint` up against `existing` (this event's current
    register, in whatever order the caller holds it -- this function never
    sorts or mutates it):

    - No row at all for this fingerprint at this event -> mint a fresh
      one. The first certificate, exactly as before.
    - An `issued` row exists -> reuse it, rather than the first match in
      file order regardless of state. `already_registered=True`, the
      register never grows a second row, and a routine re-run stays
      idempotent (spec S:8: "recalcule sans réinscrire") -- unchanged
      behaviour from before this round.
    - Rows exist and *every one* is `STATE_REVOKED` -> refuse
      (`ValueError`), naming `convener-reissue-certificate` as the correction
      path.

    The third branch is what closes Critical 1 without reopening the trap
    R-18 named: filtering the lookup down to "an issued row, or nothing"
    would make a fingerprint whose only row is revoked match nothing,
    so a routine, scheduled re-run of `convener-issue-certificates` would then
    silently mint a **fresh** certificate for someone whose certificate was
    deliberately revoked -- worse than the defect this closes. Refusing
    instead preserves the no-resurrection property `reissue`'s own
    docstring already relies on (a revoked certificate is corrected only
    by an operator's deliberate `reissue` call, never by this function),
    while still stopping `issue` from ever handing back a document that no
    longer stands. A caller iterating many attendees (`cli.py`'s own
    per-attendee loops) is expected to catch this per attendee and
    continue, the same way it already handles a render or transport
    failure -- never let one revoked fingerprint stop the whole run.

    `already_registered` on the result tells the caller whether to append
    `entry` to the register at all.

    Signs a payload of exactly `signing.PAYLOAD_FIELDS` -- `identifier`
    (this entry's), `event` (`event.title`, spec S:7's "intitulé", not
    `event.event_id`), `name` (`attendee.registration`'s first name and
    surname, joined by one space -- the one place in this whole pipeline a
    name is ever read, and it is never written to anything this function
    returns except `token`), `date` (`event.date`) and `duration_hours`
    (`duration_hours(attendee.duration_seconds)`). Raises whatever
    `signing.sign` raises for a key that will not load
    (`signing.SigningError`); never raises for a bad `attendee` or `event`,
    because both are already-validated data by the time either reaches
    this module -- the one new exception this round adds is the
    `ValueError` above, for a fingerprint whose every row is revoked.
    """
    entry_fingerprint = fingerprint(event.event_id, attendee.registration.email, salt)
    matches = [
        entry
        for entry in existing
        if entry.event_id == event.event_id
        # `hmac.compare_digest`, not `==` (security audit 2026-08-23, L1):
        # both sides are HMAC output, the same reasoning `proposal.py`'s
        # own signature check already applies -- this call site is not
        # reachable by an adversary who lacks a cheaper, more direct
        # oracle, but the inconsistency itself is what this fix closes.
        and hmac.compare_digest(entry.fingerprint, entry_fingerprint)
    ]
    issued_match = next(
        (entry for entry in matches if entry.state == STATE_ISSUED), None
    )

    if issued_match is not None:
        target = issued_match
    elif matches:
        # R-26: every existing row for this fingerprint is revoked -- do
        # not resurrect it here. `reissue` (an operator's own deliberate
        # act, never called from this loop) is the only correction path.
        raise ValueError(
            "every certificate on record for this fingerprint at this "
            "event is revoked -- use convener-reissue-certificate to correct it, "
            "not a routine re-run of convener-issue-certificates"
        )
    else:
        target = CertificateEntry(
            identifier=_new_identifier(),
            event_id=event.event_id,
            issued_on=issued_on,
            fingerprint=entry_fingerprint,
            state=STATE_ISSUED,
        )

    token = _sign_certificate(target, event, attendee, private_pem)
    return IssueResult(
        entry=target, token=token, already_registered=issued_match is not None
    )


def sign_for(
    entry: CertificateEntry,
    event: CertificateEvent,
    attendee: MatchedAttendee,
    private_pem: str,
) -> str:
    """Sign `entry` for `attendee` at `event`, without performing any
    register lookup at all (R-26, fix round 1, Critical 1) -- the exact
    primitive `cli.py::deliver_certificate` needs: it has already resolved
    `entry` by `CERTIFICATE_ID`, a stronger, caller-supplied key than
    fingerprint, and must sign *that* row, never re-resolve one by
    fingerprint through `issue` and risk naming one certificate in the
    log while attaching another -- the exact bug Critical 1 found
    (`deliver_certificate` named the certificate `CERTIFICATE_ID`
    identified, then called `issue`, which re-resolved by fingerprint and
    could hand back a different, revoked row).

    A thin, public wrapper around `_sign_certificate` -- the same private
    function `issue` and `reissue` already share -- rather than exposing
    that name directly, so a caller cannot mistake this for participating
    in either of their own register lookups. Raises whatever
    `signing.sign` raises for a key that will not load
    (`signing.SigningError`); never inspects `entry.state` itself --
    refusing to sign a revoked entry is the caller's own decision
    (`cli.py`'s both delivery commands make it before ever reaching this
    function), not something a signing primitive should silently decide."""
    return _sign_certificate(entry, event, attendee, private_pem)


def _sign_certificate(
    entry: CertificateEntry,
    event: CertificateEvent,
    attendee: MatchedAttendee,
    private_pem: str,
) -> str:
    """The payload both `issue` and `reissue` sign, factored out once so
    the two never risk drifting into two different ideas of what a
    certificate's payload contains -- see `issue`'s own docstring for what
    each field is and why. `entry` supplies `identifier`; every other
    field is a pure function of `event` and `attendee` alone, which is
    exactly why `issue` can reproduce a byte-identical token for an
    already-registered attendee (the module docstring's "idempotent
    without being deterministic" section) and why `reissue` produces a
    genuinely different token under a genuinely different identifier."""
    payload = {
        "identifier": entry.identifier,
        "event": event.title,
        "name": full_name(attendee),
        "date": event.date,
        "duration_hours": duration_hours(attendee.duration_seconds),
    }
    return sign(payload, private_pem)


def reissue(
    attendee: MatchedAttendee,
    event: CertificateEvent,
    private_pem: str,
    salt: str,
    existing: Sequence[CertificateEntry],
    *,
    issued_on: date,
) -> IssueResult:
    """An operator's deliberate correction (R-18, fix round 1, Important 3)
    -- mint a brand-new identifier and a brand-new signed token for
    `attendee`, never reusing, and never touching, any existing entry for
    the same fingerprint.

    `issue` cannot do this safely: its fingerprint lookup is what makes a
    *routine* re-run of `convener-issue-certificates` refuse to grow the
    register (spec S:8, "recalcule sans réinscrire"), and the register is
    keyed on fingerprint alone, so a second `issue` call for a corrected
    attendee reuses the *same* identifier and signs a *different* token
    under it -- two contradictory documents, one register row, neither
    one distinguishable from the other (Important 3). Widening `issue`'s
    own lookup to *skip* revoked rows and mint past them would "fix" that
    by making every scheduled re-run silently re-issue a certificate
    someone deliberately revoked -- strictly worse than the defect (R-18's
    own warning). `issue` was widened once since, in fix round 1 (R-26,
    Critical 1) -- but to a third branch that *refuses* a fingerprint whose
    only rows are revoked, never one that mints past them, which is
    exactly the property this paragraph's own warning still protects; see
    `issue`'s own docstring, "three-way, not two-way". So this remains a
    second, separate function, never called from `issue`'s own logic or
    from `cli.py::issue_certificates`'s loop -- see
    `cli.py::reissue_certificate` for the operator-facing command
    that calls this, run by hand, for one person at a time, never on a
    schedule.

    Requires every existing entry for this fingerprint at this event to
    already carry `STATE_REVOKED`. Raises `ValueError` if none exists at
    all (nothing to correct -- `issue` is what mints a first certificate),
    or if any of them is still `STATE_ISSUED` (the standing certificate
    must be revoked first, an operator's own separate, deliberate act --
    see the module docstring's "revocation touches the register, never
    the signature" section for why `revoke` has no signing key parameter
    and cannot be folded into this call). This is the one guard that
    keeps `issue`'s idempotence safe: as long as reissuing requires a
    prior revocation, and `issue` itself never revokes anything, a
    routine re-run of `convener-issue-certificates` can never resurrect a
    corrected certificate on its own.

    The new entry's `identifier` is fresh (`_new_identifier`, the same
    true randomness a first certificate gets -- never derived from the
    old identifier, the fingerprint, or anything else recoverable), so the
    corrected certificate is a genuinely distinct register row: the
    register can now tell the two documents apart, which is exactly what
    `issue`'s single, identifier-reusing row could never do.
    """
    entry_fingerprint = fingerprint(event.event_id, attendee.registration.email, salt)
    matches = [
        entry
        for entry in existing
        # `hmac.compare_digest`, not `==` -- see `issue`'s own comment on
        # its identical comparison (security audit 2026-08-23, L1).
        if entry.event_id == event.event_id
        and hmac.compare_digest(entry.fingerprint, entry_fingerprint)
    ]
    if not matches:
        raise ValueError(
            "no existing certificate for this fingerprint at this event -- "
            "reissue() corrects one, it does not mint a first one; use "
            "issue() instead"
        )
    if any(entry.state != STATE_REVOKED for entry in matches):
        raise ValueError(
            "an issued (not revoked) certificate already exists for this "
            "fingerprint -- revoke it before reissuing a correction"
        )

    target = CertificateEntry(
        identifier=_new_identifier(),
        event_id=event.event_id,
        issued_on=issued_on,
        fingerprint=entry_fingerprint,
        state=STATE_ISSUED,
    )
    token = _sign_certificate(target, event, attendee, private_pem)
    return IssueResult(entry=target, token=token, already_registered=False)


def revoke(
    existing: Sequence[CertificateEntry], event_id: str, identifier: str
) -> tuple[CertificateEntry, ...]:
    """`existing`, with the entry named by `identifier` **for `event_id`**
    marked `STATE_REVOKED` -- see the module docstring's "revocation
    touches the register, never the signature" section for why this
    function has no signing key parameter at all and cannot touch the
    token a revoked certificate's holder still carries.

    Filters on `event_id` too, not on `identifier` alone (minor 1, fix
    round 3): `reissue` above already requires both
    (`entry.event_id == event.event_id and entry.fingerprint ==
    entry_fingerprint`) precisely because `existing` is not guaranteed to
    hold only this event's own rows -- a register merged from more than
    one file by mistake, or hand-edited, could carry a foreign-event row
    that happens to share an identifier. Before this, `revoke` was the one
    command in this module that disagreed with `reissue` about what "this
    event's certificate" means; two commands answering that question
    differently is exactly the kind of drift this module is otherwise
    careful about. `identifier` alone is already effectively unique
    (`_new_identifier`'s 128 bits of randomness), so this changes no
    ordinary call's outcome -- it only closes a case that should never
    have mattered but, until now, silently could have.

    Raises `ValueError` naming both `identifier` and `event_id` when no
    entry in `existing` carries that exact pair -- revoking a certificate
    that was never issued for this event is a caller mistake worth
    surfacing, not a silent no-op. Every other entry is returned
    unchanged, in its original order and as the same object (dataclasses
    are immutable, so there is nothing to copy defensively)."""
    if not any(
        entry.event_id == event_id and entry.identifier == identifier
        for entry in existing
    ):
        raise ValueError(
            f"no certificate {identifier!r} on record for event {event_id!r}"
        )
    return tuple(
        replace(entry, state=STATE_REVOKED)
        if entry.event_id == event_id and entry.identifier == identifier
        else entry
        for entry in existing
    )


def public_register(entries: Sequence[CertificateEntry]) -> list[dict[str, Any]]:
    """The public projection: `{"identifier", "state"}` for every entry in
    `entries`, sorted by identifier for a stable, diff-friendly file --
    see the module docstring's "public projection" section for why
    `fingerprint`, `event_id` and `issued_on` are not columns this
    function could ever be asked to add: it is an allowlist of exactly two
    fields, the same discipline `public_data.to_public` applies to the
    speaker list, not a denylist of the one field that must never leave.
    """
    return [
        {"identifier": entry.identifier, "state": entry.state}
        for entry in sorted(entries, key=lambda entry: entry.identifier)
    ]


def verification_url(identifier: str, token: str) -> str:
    """The address printed on a certificate as both readable text and a
    machine-readable code -- see the module docstring's "verification
    address" section for why one URL serves both spec S:7's "adresse de
    vérification" and this task's own "code lisible par machine, contenant
    le jeton"."""
    return (
        f"{VERIFICATION_BASE}{quote(identifier, safe='')}?token={quote(token, safe='')}"
    )


def register_from_data(data: Any) -> tuple[CertificateEntry, ...]:
    """Parse an already YAML-loaded `certificates.yml`, or start empty when
    `data` is `None` -- the event's first certificate, which finds no
    register on disk yet. This function never touches a filesystem path;
    `cli.py` is the only place `certificates.yml` is ever opened, the same
    split `registration.load_registration_file` draws for
    `registrations.enc`.

    Raises `ValueError` on anything that is not this exact format: unlike
    a missing file, a malformed one is not a normal state for this
    function to paper over. Every entry's key set must be exactly
    `_ENTRY_FIELDS` -- the same "closed shape" discipline
    `registration.to_registration` applies to a decrypted registration --
    so a "helpful" extra column (a cleartext address sitting in plain
    sight beside a fingerprint meant to replace it, say) is refused at
    load rather than silently carried forward.

    Also refuses a duplicate `identifier`, and two entries that are both
    currently `STATE_ISSUED` for the same `(event_id, fingerprint)` (Minor
    6, fix round 1) -- a hand-edited or badly-merged file could otherwise
    pass load with either, and `issue`'s own fingerprint lookup would then
    silently reuse whichever entry it meets first, while `public_register`
    projected both. Two entries sharing one fingerprint *while at most one
    of them is issued* is not refused: that is exactly the shape a
    correction leaves behind (see `reissue`'s own docstring) -- the old,
    revoked row and the new, issued one, both real, both meant to coexist.
    """
    if data is None:
        return ()
    if not isinstance(data, dict) or data.get("v") != FILE_VERSION:
        raise ValueError("certificates.yml is not a supported format version")
    raw_entries = data.get("certificates")
    if not isinstance(raw_entries, list):
        raise ValueError("certificates.yml is malformed")

    entries: list[CertificateEntry] = []
    identifiers_seen: set[str] = set()
    issued_fingerprints_seen: set[tuple[str, str]] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict) or set(raw) != _ENTRY_FIELDS:
            raise ValueError(
                "certificates.yml holds an entry that is not exactly the "
                "certificate register shape"
            )
        identifier, event_id, issued_on_raw, entry_fingerprint, state = (
            raw["identifier"],
            raw["event_id"],
            raw["issued_on"],
            raw["fingerprint"],
            raw["state"],
        )
        if not (
            isinstance(identifier, str)
            and isinstance(event_id, str)
            and isinstance(issued_on_raw, str)
            and isinstance(entry_fingerprint, str)
            and isinstance(state, str)
        ):
            raise ValueError("certificates.yml holds a field of the wrong type")
        if state not in _STATES:
            raise ValueError(f"certificates.yml holds an unknown state {state!r}")
        try:
            issued_on = date.fromisoformat(issued_on_raw)
        except ValueError as exc:
            raise ValueError(
                "certificates.yml holds an invalid issued_on date"
            ) from exc
        if identifier in identifiers_seen:
            raise ValueError(
                f"certificates.yml holds identifier {identifier!r} more than once"
            )
        identifiers_seen.add(identifier)
        if state == STATE_ISSUED:
            fingerprint_key = (event_id, entry_fingerprint)
            if fingerprint_key in issued_fingerprints_seen:
                raise ValueError(
                    "certificates.yml holds two currently-issued entries for "
                    f"the same fingerprint at event {event_id!r}"
                )
            issued_fingerprints_seen.add(fingerprint_key)
        entries.append(
            CertificateEntry(
                identifier=identifier,
                event_id=event_id,
                issued_on=issued_on,
                fingerprint=entry_fingerprint,
                state=state,
            )
        )
    return tuple(entries)


def register_to_data(entries: Sequence[CertificateEntry]) -> dict[str, Any]:
    """The inverse of `register_from_data`: a plain, YAML-safe structure
    `cli.py` hands to its own YAML writer (`cli._dump`). Field order is
    fixed here so a diff on `certificates.yml` shows only what actually
    changed, never a reordering."""
    return {
        "v": FILE_VERSION,
        "certificates": [
            {
                "identifier": entry.identifier,
                "event_id": entry.event_id,
                "issued_on": entry.issued_on.isoformat(),
                "fingerprint": entry.fingerprint,
                "state": entry.state,
            }
            for entry in entries
        ],
    }


#: `data/events/<event_id>/`, relative to a repository root -- the
#: directory `certificates_path` below builds on, and the one
#: `cli.py::certificates_public_data` globs. Exported (Minor 11, fix round
#: 1) rather than buried inside `certificates_path` alone, so the one
#: other place that needs "where do events' own directories live" (the
#: glob) shares this one definition instead of typing `"data" / "events"`
#: a second time.
EVENTS_DIR: Final = Path("data") / "events"


def certificates_path(root: Path, event_id: str) -> Path:
    """`data/events/<event_id>/certificates.yml`, relative to `root` --
    the one function that names where this event's certificate register
    lives on disk (Minor 11, fix round 1). Pure path computation, like
    `signing.public_key_path`: reads nothing, touches nothing; `cli.py` is
    still the only module that ever opens the path this returns.

    Exported specifically so a *symbol* stands between this file and
    `registrations.enc`, its sibling in the same directory that task 15's
    retention sweep destroys 90 days after the event: see the module
    docstring's "the register survives the data it was derived from"
    section (ruling 2) for why the two must never be treated alike, and
    `eventkeys.py`'s own module docstring for the destruction side of that
    boundary. A future task-15 implementation that deletes this event's
    whole directory, rather than calling `eventkeys.destroy` for
    `registrations.enc` specifically, has to walk past this function (and
    the test that pins it) to do it -- a paragraph in a docstring is
    something a reader can skip; an exported symbol referenced by name in
    two modules is not.
    """
    return root / EVENTS_DIR / event_id / "certificates.yml"
