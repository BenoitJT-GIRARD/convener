from __future__ import annotations

import dataclasses
import hmac
import json
import math
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from convener_ops.attendance import MatchedAttendee
from convener_ops.certificate import (
    _CERTIFICATE_ID_RE,
    EVENTS_DIR,
    FILE_VERSION,
    ORGANISER,
    STATE_ISSUED,
    STATE_REVOKED,
    VERIFICATION_BASE,
    CertificateEntry,
    CertificateEvent,
    certificates_path,
    duration_hours,
    fingerprint,
    full_name,
    is_valid_identifier,
    issue,
    public_register,
    register_from_data,
    register_to_data,
    reissue,
    revoke,
    sign_for,
    verification_url,
)
from convener_ops.declaration import published
from convener_ops.declaration.paths import repo_root
from convener_ops.registration import (
    _CODE_ALPHABET,
    _CODE_GROUP,
    _CODE_SYMBOLS,
    Registration,
    matching_code,
    normalize_email,
)
from convener_ops.signing import (
    MALFORMED,
    NO_MATCHING_KEY,
    PAYLOAD_FIELDS,
    generate,
    verify,
)

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "certificate-verification.json").read_text(
        encoding="utf-8"
    )
)

_EXPECTED_REGISTER_FIELDS = frozenset(
    {"identifier", "event_id", "issued_on", "fingerprint", "state"}
)


# ------------------------------------------------------------------ #
# The register's own guarantee -- the most important property in this
# module, and the one every other test here is built around.
# ------------------------------------------------------------------ #


def test_the_register_holds_no_name_and_no_address() -> None:
    """Written as a sweep over the whole register rather than a field-by-
    field check -- a field added one day must make this test fall, not
    pass unnoticed.

    The register holds a certificate identifier, an event identifier, an
    issue date, a salted fingerprint of the address and a state -- no
    name, no address. This asserts the register's field set is *exactly*
    that, on both the in-memory type (`CertificateEntry`) and its
    serialised form (`register_to_data`) -- so a future change that adds
    anything else, a
    display name kept "just for debugging", an unsalted address, a
    free-text note, fails this test the moment it lands, whatever the new
    field is named. A check that instead asserted `not hasattr(entry,
    "name")` would pass right up until the day someone added a field
    called `participant` or `attendee_label` instead -- this test does not
    depend on guessing the name in advance.
    """
    dataclass_fields = frozenset(f.name for f in dataclasses.fields(CertificateEntry))
    assert dataclass_fields == _EXPECTED_REGISTER_FIELDS

    entry = CertificateEntry(
        identifier="a" * 32,
        event_id="mrg-042",
        issued_on=date(2026, 8, 20),
        fingerprint="b" * 64,
        state=STATE_ISSUED,
    )
    serialized = register_to_data((entry,))["certificates"][0]
    assert frozenset(serialized) == _EXPECTED_REGISTER_FIELDS

    # Never a field this type could be extended to hold under a plausible
    # alternative name either -- belt and braces alongside the exact-set
    # checks above, which already imply this.
    for forbidden in ("name", "first_name", "surname", "email", "address"):
        assert forbidden not in dataclass_fields
        assert forbidden not in serialized


def test_the_public_projection_holds_no_fingerprint_either() -> None:
    """The same sweep, aimed at `public_register`'s output rather than the
    internal register: the public projection carries identifiers and
    states *only* -- never a fingerprint, even though the
    internal register (which is not published) does hold one."""
    entry = CertificateEntry(
        identifier="a" * 32,
        event_id="mrg-042",
        issued_on=date(2026, 8, 20),
        fingerprint="b" * 64,
        state=STATE_ISSUED,
    )
    [row] = public_register((entry,))
    assert frozenset(row) == frozenset({"identifier", "state"})
    assert "b" * 64 not in row.values()


# ------------------------------------------------------------------ #
# The fingerprint: salted, domain-separated from matching_code, and
# never the same value as it.
# ------------------------------------------------------------------ #


def test_fingerprint_is_deterministic_and_normalises_the_address() -> None:
    a = fingerprint("mrg-042", "ada@example.org", "s3cr3t")
    b = fingerprint("mrg-042", "  Ada@Example.ORG", "s3cr3t")
    assert a == b


def test_fingerprint_differs_by_event() -> None:
    a = fingerprint("mrg-042", "ada@example.org", "s3cr3t")
    b = fingerprint("mrg-043", "ada@example.org", "s3cr3t")
    assert a != b


def test_fingerprint_differs_by_salt() -> None:
    a = fingerprint("mrg-042", "ada@example.org", "salt-a")
    b = fingerprint("mrg-042", "ada@example.org", "salt-b")
    assert a != b


def test_fingerprint_is_never_the_same_value_as_the_matching_code() -> None:
    """Kept as a cheap sanity check, but this alone proves nothing:
    `fingerprint` returns a 64-character hex digest,
    `matching_code` an 8-character hyphenated code from a 30-symbol
    alphabet, and those two renderings can never be equal for *any* input
    -- so this assertion is true whether or not `_FINGERPRINT_DOMAIN`
    still separates the two HMAC input spaces. Removing that prefix left
    the whole suite green, this test included. The two tests below pin
    the property that actually matters."""
    event_id, email, salt = "mrg-042", "ada@example.org", "s3cr3t"
    assert fingerprint(event_id, email, salt) != matching_code(event_id, email, salt)


def test_fingerprint_would_change_if_the_domain_prefix_were_dropped() -> None:
    """Pins the *input space*, not the rendered
    output. `matching_code` HMACs `f"{event_id}\\0{normalised address}"`
    under `CONVENER_MATCHING_SALT`; `fingerprint` is supposed to prefix that
    same input with `_FINGERPRINT_DOMAIN` before hashing, under the same
    salt. If a future edit ever dropped that prefix, `fingerprint` would
    hash exactly the bytes computed here, and this assertion would fail --
    unlike the tautology above, which stays green either way."""
    event_id, email, salt = "mrg-042", "ada@example.org", "s3cr3t"
    naked = hmac.new(
        salt.encode("utf-8"),
        f"{event_id}\0{normalize_email(email)}".encode(),
        sha256,
    ).hexdigest()
    assert fingerprint(event_id, email, salt) != naked


def test_fingerprints_digest_bytes_cannot_be_reduced_to_the_mailed_matching_code() -> (
    None
):
    """The concrete harm the domain prefix exists to prevent, reproduced
    directly: applying `matching_code`'s own digest-to-
    symbols transform (`bytes.fromhex`, modulo the alphabet, hyphenate) to
    `fingerprint`'s own hex digest must never recover the matching code
    the confirmation actually mails -- if it ever did, every row of the committed
    register would double as the participant's own, already-sent matching
    code. Under the domain-prefix-dropped mutant, this recomputation
    equals `matching_code(...)` exactly; with the prefix intact, it must
    not."""
    event_id, email, salt = "mrg-042", "ada@example.org", "s3cr3t"
    digest_bytes = bytes.fromhex(fingerprint(event_id, email, salt))
    symbols = "".join(
        _CODE_ALPHABET[byte % len(_CODE_ALPHABET)]
        for byte in digest_bytes[:_CODE_SYMBOLS]
    )
    recovered = "-".join(
        symbols[i : i + _CODE_GROUP] for i in range(0, len(symbols), _CODE_GROUP)
    )
    assert recovered != matching_code(event_id, email, salt)


# ------------------------------------------------------------------ #
# duration_hours -- the written rounding rule, both sides of the
# boundary, and the exact tie.
# ------------------------------------------------------------------ #


def test_duration_hours_below_the_quarter_hour_boundary_rounds_down() -> None:
    # 4049s = 1.124722...h -- just under the exact midpoint (4050s)
    # between the 1.0h and 1.25h quarter-hour marks.
    assert duration_hours(4049) == 1.0


def test_duration_hours_above_the_quarter_hour_boundary_rounds_up() -> None:
    assert duration_hours(4051) == 1.25


def test_duration_hours_on_an_exact_tie_rounds_up_not_to_even() -> None:
    """4050s is exactly 1.125h -- exactly halfway between the 1.0h and
    1.25h marks. Python's `Decimal` default (`ROUND_HALF_EVEN`) would
    round this DOWN to 1.0 (4 is the nearer even integer of quarters to
    4.5); this module's documented rule rounds ties up instead, so the
    boundary case never shortchanges a participant. If a future edit drops
    `rounding=ROUND_HALF_UP`, this is the test that catches it -- the two
    tests above alone would still pass under HALF_EVEN."""
    assert duration_hours(4050) == 1.25


def test_duration_hours_on_a_clean_multiple_is_unchanged() -> None:
    assert duration_hours(5400) == 1.5  # a 90-minute session, in full


def test_duration_hours_of_zero_seconds_is_zero() -> None:
    assert duration_hours(0) == 0.0


def test_duration_hours_of_a_negative_value_floors_at_zero_not_negative_zero() -> None:
    """Unreachable through `attendance._duration`
    (which already floors at zero) but this function is public and `int`
    is signed -- `duration_hours(-5)` rendered `-0.0` before this floor,
    a value with no honest reading on a certificate. `-0.0 == 0.0` is
    `True` in Python, so an equality check alone would not catch a
    regression here -- the sign has to be read separately."""
    result = duration_hours(-5)
    assert result == 0.0
    assert math.copysign(1.0, result) == 1.0


# ------------------------------------------------------------------ #
# issue() -- identifier randomness, idempotence, and the signed payload.
# ------------------------------------------------------------------ #

_EVENT = CertificateEvent(
    event_id="mrg-042", title="On analytical engines", date="2026-08-20"
)


def _attendee(
    email: str = "ada@example.org", duration_seconds: int = 5400
) -> MatchedAttendee:
    registration = Registration("Ada", "Lovelace", email, "", False)
    return MatchedAttendee(registration=registration, duration_seconds=duration_seconds)


def test_full_name_joins_first_name_and_surname_with_one_space() -> None:
    """The exact join `_sign_certificate` signs into the payload's own
    `name` field -- see this function's own docstring for why it is
    factored out at all: `delivery.render_certificate` must
    print the identical string, computed the identical way, never a
    second independently-typed join."""
    assert full_name(_attendee()) == "Ada Lovelace"


def test_issue_signs_the_same_name_full_name_would_compute() -> None:
    """Pins `_sign_certificate`'s own payload against `full_name` directly
    -- the property that stops the signed name and the printed name from
    ever drifting apart."""
    private_pem, public_pem = generate()
    attendee = _attendee()
    result = issue(
        attendee, _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )
    outcome = verify(result.token, [public_pem])
    assert outcome.payload is not None
    assert outcome.payload["name"] == full_name(attendee)


def test_issue_produces_a_token_that_verifies_and_carries_the_right_payload() -> None:
    private_pem, public_pem = generate()

    result = issue(
        _attendee(),
        _EVENT,
        private_pem,
        "s3cr3t",
        existing=(),
        issued_on=date(2026, 8, 20),
    )

    verified = verify(result.token, [public_pem])
    assert verified.valid
    assert verified.payload is not None
    assert set(verified.payload) == PAYLOAD_FIELDS
    assert verified.payload["identifier"] == result.entry.identifier
    assert verified.payload["event"] == "On analytical engines"
    assert verified.payload["name"] == "Ada Lovelace"
    assert verified.payload["date"] == "2026-08-20"
    assert verified.payload["duration_hours"] == 1.5


def test_issue_mints_a_fresh_random_identifier_each_time_no_register_matches() -> None:
    """Two different people, issued against an empty register each time:
    their identifiers must differ, and neither may be derivable from the
    other -- this is the negative half of "the identifier must not be
    deterministic": nothing here ties the identifier to the address by
    formula.

    Also pins the identifier's own shape:
    `_IDENTIFIER_BYTES` -- 128 bits, `secrets.token_hex` -- was asserted
    nowhere; reducing it to 2 bytes (16 bits, 65 536 possible values,
    trivially enumerable against the public projection) left the whole
    suite green. `len(...) == 32` and a hex-alphabet check catch that."""
    private_pem, _ = generate()
    ada = issue(
        _attendee("ada@example.org"),
        _EVENT,
        private_pem,
        "salt",
        (),
        issued_on=date(2026, 8, 20),
    )
    grace = issue(
        _attendee("grace@example.org"),
        _EVENT,
        private_pem,
        "salt",
        (),
        issued_on=date(2026, 8, 20),
    )
    assert ada.entry.identifier != grace.entry.identifier
    for identifier in (ada.entry.identifier, grace.entry.identifier):
        assert len(identifier) == 32
        assert all(c in "0123456789abcdef" for c in identifier)


# ------------------------------------------------------------------ #
# is_valid_identifier() -- the same one-line shape
# check eventkeys.secret_name already gives EVENT_ID, applied to
# CERTIFICATE_ID before cli.py ever echoes it into a job's own log.
# ------------------------------------------------------------------ #


def test_is_valid_identifier_accepts_a_genuine_identifier() -> None:
    private_pem, _ = generate()
    result = issue(
        _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )
    assert is_valid_identifier(result.entry.identifier)


@pytest.mark.parametrize(
    "candidate",
    [
        "",
        "abc",
        "g" * 32,  # right length, not hex
        "A" * 32,  # uppercase -- token_hex is always lowercase
        "a" * 31,
        "a" * 33,
        "a" * 32 + "\n::add-mask::secret",
        "a" * 16 + "\n" + "a" * 15,  # an embedded newline, right length overall
    ],
    ids=[
        "empty",
        "too-short-and-not-hex",
        "right-length-not-hex",
        "uppercase",
        "one-short",
        "one-long",
        "trailing-junk-after-newline",
        "embedded-newline-same-length",
    ],
)
def test_is_valid_identifier_refuses_anything_else(candidate: str) -> None:
    assert not is_valid_identifier(candidate)


def test_issue_never_derives_the_same_identifier_twice_from_a_fresh_register() -> None:
    """Calling `issue` twice for the *same* address against two
    independent, empty registers (never told about each other) still
    produces two different identifiers -- proof that identifier generation
    is genuine randomness, not a hidden function of the address, the event
    or the salt. Idempotence is bought a different way: see the tests
    below, which give `issue` the *same* register both times."""
    private_pem, _ = generate()
    first = issue(
        _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )
    second = issue(
        _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )
    assert first.entry.identifier != second.entry.identifier


def test_reissuing_the_same_attendee_does_not_grow_the_register() -> None:
    """A corrected match recalculates without re-registering.
    Given the register `issue` itself returned the first time, calling it
    again for the same attendee and event must reuse the same identifier
    and report `already_registered=True` -- this is the guarantee a
    mutation on `issue`'s fingerprint lookup would break."""
    private_pem, public_pem = generate()

    first = issue(
        _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )
    assert first.already_registered is False

    second = issue(
        _attendee(),
        _EVENT,
        private_pem,
        "salt",
        existing=(first.entry,),
        issued_on=date(2026, 8, 21),
    )

    assert second.already_registered is True
    assert second.entry == first.entry
    assert second.entry.identifier == first.entry.identifier
    # issued_on is NOT bumped to the second call's date -- the register
    # keeps the original issuance date, exactly what "reuse the entry" has
    # to mean.
    assert second.entry.issued_on == date(2026, 8, 20)
    # Deterministic re-signing (PKCS1v15): replaying issue() for an
    # already-registered attendee reproduces the identical token, which is
    # what lets a failed delivery retry without regenerating
    # anything.
    assert second.token == first.token
    assert verify(second.token, [public_pem]).valid


def test_a_different_event_for_the_same_address_gets_its_own_identifier() -> None:
    """The register lookup is scoped by `event_id` -- attending two
    different events under the same address must never collapse onto one
    certificate."""
    private_pem, _ = generate()
    first = issue(
        _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )
    other_event = CertificateEvent(
        event_id="mrg-043", title="A different talk", date="2026-09-01"
    )
    second = issue(
        _attendee(),
        other_event,
        private_pem,
        "salt",
        existing=(first.entry,),
        issued_on=date(2026, 9, 1),
    )
    assert second.already_registered is False
    assert second.entry.identifier != first.entry.identifier


def test_a_different_address_for_the_same_event_gets_its_own_identifier() -> None:
    private_pem, _ = generate()
    ada = issue(
        _attendee("ada@example.org"),
        _EVENT,
        private_pem,
        "salt",
        (),
        issued_on=date(2026, 8, 20),
    )
    grace = issue(
        _attendee("grace@example.org"),
        _EVENT,
        private_pem,
        "salt",
        existing=(ada.entry,),
        issued_on=date(2026, 8, 20),
    )
    assert grace.already_registered is False
    assert grace.entry.identifier != ada.entry.identifier


# ------------------------------------------------------------------ #
# Revocation -- the signature stays valid, the register alone says
# "no longer good".
# ------------------------------------------------------------------ #


def test_a_revoked_certificate_still_verifies_but_reports_revoked() -> None:
    """Both halves, in one test: a revoked certificate still verifies
    cryptographically *and* reports itself revoked."""
    private_pem, public_pem = generate()
    issued = issue(
        _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )

    register = revoke((issued.entry,), _EVENT.event_id, issued.entry.identifier)

    # Half one: the signature never stopped being valid. revoke() never
    # touched the token, and could not have -- it has no signing key.
    verified = verify(issued.token, [public_pem])
    assert verified.valid
    assert verified.payload is not None
    assert verified.payload["identifier"] == issued.entry.identifier

    # Half two: the register is what now says "no longer good".
    [entry] = register
    assert entry.state == STATE_REVOKED
    assert entry.identifier == issued.entry.identifier


def test_revoking_an_unknown_identifier_raises() -> None:
    with pytest.raises(ValueError, match="nope"):
        revoke((), "mrg-042", "nope")


def test_revoke_leaves_every_other_entry_untouched() -> None:
    a = CertificateEntry("aaa", "mrg-042", date(2026, 8, 20), "fa", STATE_ISSUED)
    b = CertificateEntry("bbb", "mrg-042", date(2026, 8, 20), "fb", STATE_ISSUED)
    register = revoke((a, b), "mrg-042", "aaa")
    assert register == (
        CertificateEntry("aaa", "mrg-042", date(2026, 8, 20), "fa", STATE_REVOKED),
        b,
    )


def test_revoke_refuses_an_identifier_that_belongs_to_a_different_event() -> None:
    """`revoke` used to match on `identifier`
    alone, while `reissue` above already filters on `event_id` too -- two
    commands disagreeing about what "this event's certificate" means. A
    register merged from more than one file by mistake, or hand-edited,
    could carry a foreign-event row that happens to share an identifier;
    this event's own revoke must not be able to touch it."""
    foreign = CertificateEntry(
        "shared-id", "mrg-999", date(2026, 8, 20), "f" * 64, STATE_ISSUED
    )
    with pytest.raises(ValueError, match="mrg-042"):
        revoke((foreign,), "mrg-042", "shared-id")


def test_revoke_matches_the_right_event_when_two_share_an_identifier() -> None:
    """The positive half of the guard above: given two entries that happen
    to share an identifier across two different events (never possible in
    practice -- `_new_identifier`'s 128 bits of randomness -- but the
    register type does not itself forbid it), `revoke` must touch only the
    row for the event it was asked about."""
    day = date(2026, 8, 20)
    this_event = CertificateEntry("shared-id", "mrg-042", day, "fa", STATE_ISSUED)
    other_event = CertificateEntry("shared-id", "mrg-999", day, "fb", STATE_ISSUED)
    register = revoke((this_event, other_event), "mrg-042", "shared-id")
    assert register == (
        CertificateEntry("shared-id", "mrg-042", day, "fa", STATE_REVOKED),
        other_event,
    )


def test_issuing_again_after_revocation_refuses_rather_than_resurrecting() -> None:
    """Supersedes an earlier test
    (which pinned `issue` *reusing* a revoked row -- exactly the
    defect that turned up: a routine re-run of `convener-issue-certificates`
    handing back, and `convener-deliver-certificates` mailing, a document whose
    own register row says it no longer stands).

    `issue`'s lookup is three-way, not two-way (see its own docstring):
    a fingerprint whose *every* row is revoked must be refused, not
    resurrected by reuse and not resurrected by minting a fresh one
    either (the warning against the naive two-way "fix" -- see
    `reissue`'s own docstring). This is the test the obvious mutation
    calls for: "make the three-way lookup two-way (skip revoked
    rows and mint) -- a test must fail, and it must be the one about a
    routine re-run after a revocation." Reverting to the old
    reuse-the-revoked-row behaviour, or to a two-way skip-and-mint
    behaviour, both fail this test."""
    private_pem, _ = generate()
    issued = issue(
        _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )
    register = revoke((issued.entry,), _EVENT.event_id, issued.entry.identifier)

    with pytest.raises(ValueError, match="convener-reissue-certificate"):
        issue(
            _attendee(),
            _EVENT,
            private_pem,
            "salt",
            register,
            issued_on=date(2026, 8, 21),
        )

    # Nothing resurrected, and nothing new minted either -- the register
    # this call was handed is the one true source; `issue` never mutates
    # it, so re-reading it after the refusal is only a belt-and-braces
    # check that the call itself did not sneak a second row in past the
    # exception.
    assert register == (dataclasses.replace(issued.entry, state=STATE_REVOKED),)


def test_issue_resolves_to_the_issued_row_after_a_reissue_not_the_revoked_one() -> None:
    """The other half of the reproduction (b): after a
    genuine correction (issue, revoke, reissue), the register holds both
    the old, revoked row and the new, issued one for the same fingerprint
    -- exactly the shape `reissue`'s own docstring describes. `issue`
    must resolve to the *issued* row, never the first match in file order
    (the old, revoked one comes first): mutating the three-way lookup back
    to "first match regardless of state" is what this test catches."""
    private_pem, public_pem = generate()
    issued = issue(
        _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )
    revoked_register = revoke((issued.entry,), _EVENT.event_id, issued.entry.identifier)
    corrected = reissue(
        _attendee(),
        _EVENT,
        private_pem,
        "salt",
        revoked_register,
        issued_on=date(2026, 8, 21),
    )
    register = (*revoked_register, corrected.entry)
    assert register[0].state == STATE_REVOKED
    assert register[1].state == STATE_ISSUED

    resolved = issue(
        _attendee(), _EVENT, private_pem, "salt", register, issued_on=date(2026, 8, 22)
    )

    assert resolved.already_registered is True
    assert resolved.entry == corrected.entry
    assert resolved.entry.identifier == corrected.entry.identifier
    assert resolved.entry.identifier != issued.entry.identifier
    assert resolved.token == corrected.token
    assert verify(resolved.token, [public_pem]).valid


# ------------------------------------------------------------------ #
# reissue() -- an operator's deliberate correction: a new identifier,
# gated on the row it replaces already being revoked.
# ------------------------------------------------------------------ #


def test_reissue_refuses_when_no_certificate_exists_for_the_fingerprint() -> None:
    private_pem, _ = generate()
    with pytest.raises(ValueError, match="no existing certificate"):
        reissue(
            _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
        )


def test_reissue_refuses_when_the_standing_certificate_is_still_issued() -> None:
    """The guard reissue exists for: reissuing over a still-`STATE_ISSUED`
    row would leave two valid, contradictory certificates standing at once
    -- the original defect. An operator must revoke first,
    a separate and deliberate act."""
    private_pem, _ = generate()
    issued = issue(
        _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )
    with pytest.raises(ValueError, match="revoke"):
        reissue(
            _attendee(),
            _EVENT,
            private_pem,
            "salt",
            (issued.entry,),
            issued_on=date(2026, 8, 21),
        )


def test_reissue_mints_a_new_identifier_while_the_old_row_stays_revoked() -> None:
    """The two-halves guarantee: a genuinely new identifier
    for the corrected certificate, and the revoked row this replaces is
    returned completely untouched -- `reissue` never mutates `existing`,
    it only reads it. The caller (`cli.py::reissue_certificate`) is what
    appends the new entry alongside the old one."""
    private_pem, public_pem = generate()
    issued = issue(
        _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )
    revoked_register = revoke((issued.entry,), _EVENT.event_id, issued.entry.identifier)
    [old_entry] = revoked_register

    corrected = reissue(
        _attendee(duration_seconds=1800),
        _EVENT,
        private_pem,
        "salt",
        revoked_register,
        issued_on=date(2026, 8, 21),
    )

    assert corrected.already_registered is False
    assert corrected.entry.identifier != old_entry.identifier
    assert corrected.entry.state == STATE_ISSUED
    assert corrected.entry.fingerprint == old_entry.fingerprint
    # The old row, still sitting in the register handed to reissue(), is
    # the identical object -- untouched, still revoked.
    assert revoked_register[0] == old_entry
    assert revoked_register[0].state == STATE_REVOKED

    verified = verify(corrected.token, [public_pem])
    assert verified.valid
    assert verified.payload is not None
    assert verified.payload["identifier"] == corrected.entry.identifier
    assert verified.payload["identifier"] != old_entry.identifier


# ------------------------------------------------------------------ #
# sign_for() -- sign an already-resolved
# register row directly, with no fingerprint lookup at all. The primitive
# cli.py::deliver_certificate needs so it can sign the exact row
# CERTIFICATE_ID named, rather than re-resolving one through issue() and
# risking naming one certificate while attaching another.
# ------------------------------------------------------------------ #


def test_sign_for_signs_the_row_it_is_given_not_one_it_resolves_itself() -> None:
    """The one property this function exists for: two entries sharing a
    fingerprint (the exact shape a revoke-and-reissue leaves behind) --
    `sign_for` must sign whichever one it is handed, never look the other
    up itself. Mutating this to resolve `entry` from a register instead of
    signing the argument directly -- making `deliver_certificate` sign
    something other than the row it resolved -- has to fail; this is that
    property, pinned at the unit level, one layer below the CLI test of
    the same name."""
    private_pem, public_pem = generate()
    attendee = _attendee()
    revoked = CertificateEntry(
        identifier="a" * 32,
        event_id=_EVENT.event_id,
        issued_on=date(2026, 8, 20),
        fingerprint=fingerprint(_EVENT.event_id, attendee.registration.email, "salt"),
        state=STATE_REVOKED,
    )
    issued = CertificateEntry(
        identifier="b" * 32,
        event_id=_EVENT.event_id,
        issued_on=date(2026, 8, 21),
        fingerprint=revoked.fingerprint,
        state=STATE_ISSUED,
    )

    token_for_issued = sign_for(issued, _EVENT, attendee, private_pem)
    token_for_revoked = sign_for(revoked, _EVENT, attendee, private_pem)

    outcome_issued = verify(token_for_issued, [public_pem])
    assert outcome_issued.payload is not None
    assert outcome_issued.payload["identifier"] == issued.identifier

    outcome_revoked = verify(token_for_revoked, [public_pem])
    assert outcome_revoked.payload is not None
    assert outcome_revoked.payload["identifier"] == revoked.identifier


def test_sign_for_matches_the_token_issue_would_have_produced_for_the_same_entry() -> (
    None
):
    """`sign_for` and `issue` share `_sign_certificate` -- this pins that
    they never drift into two different ideas of what gets signed for the
    same entry, attendee and event."""
    private_pem, _ = generate()
    attendee = _attendee()
    result = issue(
        attendee, _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )

    token = sign_for(result.entry, _EVENT, attendee, private_pem)

    assert token == result.token


def test_sign_for_does_not_inspect_or_refuse_a_revoked_entry_itself() -> None:
    """`sign_for` is a pure signing primitive -- refusing to deliver a
    revoked certificate is `cli.py`'s own decision (both delivery
    commands make it before ever calling this function), not something
    silently baked into the signer. If it were, a caller that legitimately
    needs to sign a revoked row for its own purposes (there is none today,
    but the module docstring is explicit that this function performs no
    state check) would be surprised by a refusal this function's own
    docstring says it will never raise."""
    private_pem, public_pem = generate()
    attendee = _attendee()
    revoked = CertificateEntry(
        identifier="c" * 32,
        event_id=_EVENT.event_id,
        issued_on=date(2026, 8, 20),
        fingerprint=fingerprint(_EVENT.event_id, attendee.registration.email, "salt"),
        state=STATE_REVOKED,
    )

    token = sign_for(revoked, _EVENT, attendee, private_pem)

    assert verify(token, [public_pem]).valid


# ------------------------------------------------------------------ #
# CertificateEvent.__post_init__ -- the event
# title is bounded here, once, so the signed payload and the rendered
# document can never disagree about what it is.
# ------------------------------------------------------------------ #


def test_certificate_event_truncates_a_title_longer_than_the_max_length() -> None:
    from convener_ops.certificate import _MAX_TITLE_LENGTH

    long_title = "x" * (_MAX_TITLE_LENGTH + 50)
    event = CertificateEvent(event_id="mrg-042", title=long_title, date="2026-08-20")

    assert len(event.title) == _MAX_TITLE_LENGTH
    assert event.title == long_title[:_MAX_TITLE_LENGTH]
    # The truncation is not silent --
    # this flag is what cli.py's own `_warn_if_title_truncated` reads.
    assert event.title_truncated is True


def test_certificate_event_leaves_a_title_at_or_under_the_max_length_untouched() -> (
    None
):
    from convener_ops.certificate import _MAX_TITLE_LENGTH

    exact_title = "y" * _MAX_TITLE_LENGTH
    event = CertificateEvent(event_id="mrg-042", title=exact_title, date="2026-08-20")

    assert event.title == exact_title
    assert event.title_truncated is False


def test_issue_signs_the_truncated_title_never_the_original() -> None:
    """The property that keeps a truncated title from ever becoming a
    "document says one thing, signature says another" bug: the
    truncation lives on `CertificateEvent` itself, so `issue`'s signed
    payload and any later `render_certificate` call reading
    `event.title` both see the identical, already-short string -- there
    is no way to reach the untruncated original from either."""
    from convener_ops.certificate import _MAX_TITLE_LENGTH

    private_pem, public_pem = generate()
    long_title = "z" * (_MAX_TITLE_LENGTH + 200)
    event = CertificateEvent(event_id="mrg-042", title=long_title, date="2026-08-20")

    result = issue(
        _attendee(), event, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )

    outcome = verify(result.token, [public_pem])
    assert outcome.payload is not None
    assert outcome.payload["event"] == long_title[:_MAX_TITLE_LENGTH]
    assert outcome.payload["event"] != long_title


# ------------------------------------------------------------------ #
# The register file: parse / serialise, round trip, and refusal of
# anything malformed.
# ------------------------------------------------------------------ #


def test_register_from_data_of_none_is_an_empty_register() -> None:
    assert register_from_data(None) == ()


def test_register_round_trips_through_its_own_data_shape() -> None:
    entries = (
        CertificateEntry("aaa", "mrg-042", date(2026, 8, 20), "fa", STATE_ISSUED),
        CertificateEntry("bbb", "mrg-042", date(2026, 8, 20), "fb", STATE_REVOKED),
    )
    data = register_to_data(entries)
    assert data["v"] == FILE_VERSION
    assert register_from_data(data) == entries


def test_register_from_data_rejects_the_wrong_version() -> None:
    with pytest.raises(ValueError, match="version"):
        register_from_data({"v": 999, "certificates": []})


def test_register_from_data_rejects_a_non_dict() -> None:
    with pytest.raises(ValueError):
        register_from_data(["not", "a", "dict"])


def test_register_from_data_rejects_certificates_not_a_list() -> None:
    with pytest.raises(ValueError, match="malformed"):
        register_from_data({"v": FILE_VERSION, "certificates": "nope"})


def test_register_from_data_rejects_an_entry_with_an_extra_field() -> None:
    entry: dict[str, Any] = {
        "identifier": "aaa",
        "event_id": "mrg-042",
        "issued_on": "2026-08-20",
        "fingerprint": "fa",
        "state": STATE_ISSUED,
        "email": "leaked@example.org",
    }
    with pytest.raises(ValueError, match="shape"):
        register_from_data({"v": FILE_VERSION, "certificates": [entry]})


def test_register_from_data_rejects_an_entry_missing_a_field() -> None:
    entry: dict[str, Any] = {
        "identifier": "aaa",
        "event_id": "mrg-042",
        "issued_on": "2026-08-20",
        "fingerprint": "fa",
    }
    with pytest.raises(ValueError, match="shape"):
        register_from_data({"v": FILE_VERSION, "certificates": [entry]})


def test_register_from_data_rejects_an_unknown_state() -> None:
    entry: dict[str, Any] = {
        "identifier": "aaa",
        "event_id": "mrg-042",
        "issued_on": "2026-08-20",
        "fingerprint": "fa",
        "state": "pending",
    }
    with pytest.raises(ValueError, match="state"):
        register_from_data({"v": FILE_VERSION, "certificates": [entry]})


def test_register_from_data_rejects_an_invalid_issued_on_date() -> None:
    entry: dict[str, Any] = {
        "identifier": "aaa",
        "event_id": "mrg-042",
        "issued_on": "not-a-date",
        "fingerprint": "fa",
        "state": STATE_ISSUED,
    }
    with pytest.raises(ValueError, match="date"):
        register_from_data({"v": FILE_VERSION, "certificates": [entry]})


def test_register_from_data_rejects_a_field_of_the_wrong_type() -> None:
    entry: dict[str, Any] = {
        "identifier": 12345,
        "event_id": "mrg-042",
        "issued_on": "2026-08-20",
        "fingerprint": "fa",
        "state": STATE_ISSUED,
    }
    with pytest.raises(ValueError, match="type"):
        register_from_data({"v": FILE_VERSION, "certificates": [entry]})


def test_register_from_data_rejects_a_duplicate_identifier() -> None:
    """A hand-edited or badly-merged file could
    otherwise pass with two rows sharing one identifier -- `revoke` would
    then flip both, and `issue`'s own lookup would silently prefer
    whichever it meets first."""
    entries = [
        {
            "identifier": "aaa",
            "event_id": "mrg-042",
            "issued_on": "2026-08-20",
            "fingerprint": "fa",
            "state": STATE_ISSUED,
        },
        {
            "identifier": "aaa",
            "event_id": "mrg-042",
            "issued_on": "2026-08-21",
            "fingerprint": "fb",
            "state": STATE_ISSUED,
        },
    ]
    with pytest.raises(ValueError, match="more than once"):
        register_from_data({"v": FILE_VERSION, "certificates": entries})


def test_register_from_data_rejects_two_issued_rows_for_one_fingerprint() -> None:
    """Two simultaneously-issued rows for the same
    fingerprint is the storage-layer shape of the same
    defect -- two documents claiming to be *the* current certificate for
    one person, neither the register can tell apart."""
    entries = [
        {
            "identifier": "aaa",
            "event_id": "mrg-042",
            "issued_on": "2026-08-20",
            "fingerprint": "fa",
            "state": STATE_ISSUED,
        },
        {
            "identifier": "bbb",
            "event_id": "mrg-042",
            "issued_on": "2026-08-21",
            "fingerprint": "fa",
            "state": STATE_ISSUED,
        },
    ]
    with pytest.raises(ValueError, match="currently-issued"):
        register_from_data({"v": FILE_VERSION, "certificates": entries})


def test_register_from_data_accepts_a_revoked_row_and_its_reissue() -> None:
    """The legitimate shape `reissue` leaves behind: the old,
    revoked row and its correction, both real, sharing one fingerprint --
    the duplicate-fingerprint guard must not reject this, or it
    would reject every register a correction was ever applied to."""
    entries = [
        {
            "identifier": "aaa",
            "event_id": "mrg-042",
            "issued_on": "2026-08-20",
            "fingerprint": "fa",
            "state": STATE_REVOKED,
        },
        {
            "identifier": "bbb",
            "event_id": "mrg-042",
            "issued_on": "2026-08-21",
            "fingerprint": "fa",
            "state": STATE_ISSUED,
        },
    ]
    parsed = register_from_data({"v": FILE_VERSION, "certificates": entries})
    assert len(parsed) == 2


# ------------------------------------------------------------------ #
# public_register: allowlisted, sorted, stable.
# ------------------------------------------------------------------ #


def test_public_register_is_sorted_by_identifier() -> None:
    a = CertificateEntry("zzz", "mrg-042", date(2026, 8, 20), "fa", STATE_ISSUED)
    b = CertificateEntry("aaa", "mrg-042", date(2026, 8, 20), "fb", STATE_REVOKED)
    assert public_register((a, b)) == [
        {"identifier": "aaa", "state": STATE_REVOKED},
        {"identifier": "zzz", "state": STATE_ISSUED},
    ]


def test_public_register_of_an_empty_tuple_is_an_empty_list() -> None:
    assert public_register(()) == []


# ------------------------------------------------------------------ #
# The verification address.
# ------------------------------------------------------------------ #


def _parse_hash_route(url: str) -> tuple[str, dict[str, list[str]]]:
    """`urlparse` treats everything after `#` as an opaque fragment, so a
    `HashRouter` URL's own route path and query string -- both of which
    live *inside* that fragment -- have to be pulled apart a second time.
    Mirrors what `react-router-dom`'s `useParams`/`useSearchParams` do at
    runtime for exactly this kind of address."""
    fragment = urlparse(url).fragment
    inner = urlparse(fragment)
    return inner.path, parse_qs(inner.query)


def test_verification_url_carries_the_identifier_and_the_token() -> None:
    url = verification_url("abc123", '{"v":1}')
    assert url.startswith(VERIFICATION_BASE)
    path, query = _parse_hash_route(url)
    assert path.rsplit("/", 1)[-1] == "abc123"
    assert query["token"] == ['{"v":1}']


def test_verification_url_percent_encodes_a_token_with_reserved_characters() -> None:
    token = '{"v":1,"payload":"a/b+c="}'
    url = verification_url("id", token)
    # The raw token, with its JSON punctuation and base64 characters, must
    # not appear unescaped in the URL -- if it did, "/", "+" and "=" would
    # be read as URL structure rather than token content.
    assert token not in url
    # And yet the exact original token round-trips back out through a
    # real query-string parser.
    _path, query = _parse_hash_route(url)
    assert query["token"] == [token]


def test_verification_url_carries_the_token_after_the_fragment_not_before_it() -> None:
    """A reviewer's own finding, pinned: `VERIFICATION_BASE`
    ends in `#/`, so the `?token=` this function appends -- which
    carries the holder's name -- sits inside the URL *fragment*. A
    fragment is never sent in an HTTP request and is stripped from
    `Referer` before a browser navigates away, so the name never reaches
    GitHub's servers or a third party's request log. That property holds
    only as long as the token appears *after* the first `#`. This address
    moved off `App.tsx`'s `HashRouter` route onto a static page's
    own island, which reads `location.hash` itself -- serving that page
    from a bare path instead, the way `registration.SIGNUP_BASE` moved,
    would silently move the token before the `#` and start
    leaking names in every verification. This test is what would catch
    that."""
    url = verification_url("abc123", '{"v":1,"payload":"eyJuYW1lIjoiQWRhIn0="}')
    fragment_start = url.index("#")
    token_start = url.index("token=")
    assert token_start > fragment_start


# ------------------------------------------------------------------ #
# ORGANISER: a module constant, not configuration.
# ------------------------------------------------------------------ #


def test_organiser_is_a_non_empty_constant() -> None:
    """Read back from the declaration itself rather than compared with
    the name this instance happens to declare: `ORGANISER` is what a
    stranger reads at the top of a certificate, and a literal here
    would be a second place the name is written down -- exactly the
    shape `instance/config.json` exists to end."""
    declared = json.loads(
        (repo_root() / published.INSTANCE_PATH).read_text(encoding="utf-8")
    )
    assert declared["identity"]["organisation"] == ORGANISER
    assert ORGANISER


# ------------------------------------------------------------------ #
# certificates_path: the one function naming where a register lives
# -- a symbol the retention sweep has to walk past, not a paragraph it can
# skip.
# ------------------------------------------------------------------ #


def test_certificates_path_is_the_events_directory_plus_certificates_yml() -> None:
    root = Path("/repo")
    assert certificates_path(root, "mrg-042") == (
        root / EVENTS_DIR / "mrg-042" / "certificates.yml"
    )


# ------------------------------------------------------------------ #
# docs/toolkit/certificate.md: the page claims a test pins its field list
# against signing.PAYLOAD_FIELDS and ORGANISER. This is that test.
# ------------------------------------------------------------------ #

#: Every signed payload field's own bracketed placeholder on the page --
#: kept as a dict, not a set, so a missing or renamed placeholder names
#: exactly which field is unaccounted for, rather than only "something is
#: wrong".
_TOOLKIT_PLACEHOLDERS = {
    "identifier": "[the certificate's identifier]",
    "event": "[the event's title]",
    "name": "[the participant's full name]",
    "date": "[the event's date]",
    "duration_hours": "[the duration, in hours]",
}


def test_the_toolkit_page_field_list_matches_the_signed_payload() -> None:
    text = (repo_root() / "docs" / "toolkit" / "certificate.md").read_text(
        encoding="utf-8"
    )
    assert set(_TOOLKIT_PLACEHOLDERS) == PAYLOAD_FIELDS
    for field, placeholder in _TOOLKIT_PLACEHOLDERS.items():
        assert placeholder in text, (
            f"docs/toolkit/certificate.md has no placeholder for the signed "
            f"field {field!r} -- expected {placeholder!r}"
        )


def test_the_toolkit_page_prints_the_organiser_constant() -> None:
    """The organiser's name is document furniture, never a signed field
    (`signing.sign` would refuse a payload that tried to include it) --
    but it must still appear on the page, and it must get there from the
    one declaration rather than being hand-typed a second time somewhere
    this test cannot see.

    The page carries `{{ instance.organisation }}`,
    and `ORGANISER` reads the same key of the same file. So this asserts
    both halves -- that the token is on the page, and that rendering it
    produces exactly the name the generated document prints. A page that
    had gone back to a literal would fail the first; a token that resolved
    to something else would fail the second.
    """
    text = (repo_root() / "docs" / "toolkit" / "certificate.md").read_text(
        encoding="utf-8"
    )
    token = "{{ instance.organisation }}"
    assert token in text, (
        "docs/toolkit/certificate.md no longer names the organiser through "
        "the substitution vocabulary -- a literal here is a name a duplicate "
        "has to find and edit by hand"
    )
    assert ORGANISER not in text, (
        "the organiser's name is written out in the page as well as "
        "substituted into it -- one of the two will be stale"
    )
    assert published.load_identity().namespace["organisation"] == ORGANISER


# ------------------------------------------------------------------ #
# The shared fixture (D-14) -- what stops this project shipping a
# verification page that verifies nothing.
# ------------------------------------------------------------------ #


def test_the_shared_fixture_reasons_match_signing_pys_own_constants() -> None:
    assert _FIXTURE["reasons"]["malformed"] == MALFORMED
    assert _FIXTURE["reasons"]["no_matching_key"] == NO_MATCHING_KEY


def test_the_shared_fixture_states_match_this_modules_own_constants() -> None:
    assert _FIXTURE["states"]["issued"] == STATE_ISSUED
    assert _FIXTURE["states"]["revoked"] == STATE_REVOKED


def test_the_shared_fixture_base_matches_this_modules_own_constant() -> None:
    """The fixture states the *path* -- `verify/#/`,
    which is the product's own route plus the fragment that keeps a
    holder's name out of every request -- and the root comes from
    `instance/config.json`, the one place it is written down."""
    assert published.load().under(_FIXTURE["verification_path"]) == VERIFICATION_BASE


def test_the_shared_fixtures_token_genuinely_verifies() -> None:
    example = _FIXTURE["signed_example"]
    result = verify(example["token"], [example["public_pem"]])
    assert result.valid
    # `payload_decoded`: the token's own `payload`
    # field is base64, `signed_example`'s is the already-decoded object --
    # renamed from the shared `payload` name the two used to collide on,
    # which threw `InvalidCharacterError` the moment a TypeScript reader
    # tried `atob(example.payload)` on the decoded form by mistake.
    assert result.payload == example["payload_decoded"]
    assert set(example["payload_decoded"]) == PAYLOAD_FIELDS


def test_the_shared_fixtures_url_is_reproducible_from_this_modules_own_function() -> (
    None
):
    example = _FIXTURE["signed_example"]
    assert verification_url(
        example["identifier"], example["token"]
    ) == published.load().under(example["verification_url_path"])


def test_the_shared_fixtures_projection_example_has_no_fingerprint_either() -> None:
    """`projection_example` is a bare
    array -- see this key's own `_projection_example_comment` for why it
    used to be nested under a `"certificates"` key and was wrong to be."""
    assert isinstance(_FIXTURE["projection_example"], list)
    for row in _FIXTURE["projection_example"]:
        assert frozenset(row) == frozenset({"identifier", "state"})
        assert row["state"] in (STATE_ISSUED, STATE_REVOKED)


def test_the_shared_fixtures_identifier_pattern_matches_certificate_pys_own() -> None:
    """The D-14 binding for
    `_CERTIFICATE_ID_RE` -- read from both sides rather than hand-retyped
    on the TypeScript one, which is exactly how a fixture goes stale."""
    assert _CERTIFICATE_ID_RE.pattern == _FIXTURE["identifier_pattern"]


def test_the_shared_fixtures_iterable_sections_carry_no_comment_key() -> None:
    """A TypeScript `Object.keys(fixture.states)` (or
    `.reasons`) sweep expecting exactly the declared spellings must never
    see a stray `_comment` key mixed in among them -- every explanatory
    comment lives at the top level instead, as a sibling `_x_comment` key,
    the same convention `governance-cases.json` already uses.

    `projection_example` is deliberately absent from this list:
    it is a bare array, not an object, so "no stray
    `_comment` key among the ones this section's own keys are swept for"
    is not a claim that means anything for it -- the array's own sibling
    `_projection_example_comment` already keeps the array itself
    comment-free, and each row is a plain `{"identifier", "state"}` object
    the test above already pins exactly."""
    for section in (
        "reasons",
        "states",
        "signed_example",
        "integer_duration_example",
    ):
        assert "_comment" not in _FIXTURE[section]


def test_the_shared_fixtures_rejects_are_each_correctly_labelled() -> None:
    """The fixture used to hold only a positive
    example, plus four bare strings with no input that actually produces
    them -- a verifier that always returned `valid: True`, or one that
    never called `verify` at all, satisfied every assertion this file
    could support. `verification_rejects` closes that gap: each token here
    must fail against `signed_example`'s own public key, with exactly the
    `reason` the case names."""
    public_pem = _FIXTURE["signed_example"]["public_pem"]
    cases = _FIXTURE["verification_rejects"]
    assert len(cases) == 3
    assert {case["reason"] for case in cases} == {MALFORMED, NO_MATCHING_KEY}
    for case in cases:
        result = verify(case["token"], [public_pem])
        assert result.valid is case["valid"] is False
        assert result.reason == case["reason"]


def test_the_shared_fixtures_integer_duration_example_genuinely_verifies() -> None:
    """`signed_example` only ever carries
    `duration_hours: 1.5` -- never the whole-number rendering hazard
    (`2.0` vs a browser's `JSON.stringify` writing `2`) `signing.py`'s own
    docstring names. This is a second, real, independently verifiable
    token that does carry one, for the verifier's own tests to check a
    display path against."""
    example = _FIXTURE["integer_duration_example"]
    result = verify(example["token"], [example["public_pem"]])
    assert result.valid
    assert result.payload == example["payload_decoded"]
    assert example["payload_decoded"]["duration_hours"] == 2.0
    assert verification_url(
        example["identifier"], example["token"]
    ) == published.load().under(example["verification_url_path"])
