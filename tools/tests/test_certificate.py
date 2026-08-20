from __future__ import annotations

import dataclasses
import json
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from convener_ops.attendance import MatchedAttendee
from convener_ops.certificate import (
    FILE_VERSION,
    ORGANISER,
    STATE_ISSUED,
    STATE_REVOKED,
    VERIFICATION_BASE,
    CertificateEntry,
    CertificateEvent,
    duration_hours,
    fingerprint,
    issue,
    public_register,
    register_from_data,
    register_to_data,
    revoke,
    verification_url,
)
from convener_ops.registration import Registration, matching_code
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
# Step 1 -- the register's own guarantee. Written first, per the brief:
# "C'est le test le plus important de la tâche."
# ------------------------------------------------------------------ #


def test_the_register_holds_no_name_and_no_address() -> None:
    """Written as a sweep over the whole register rather than a field-by-
    field check -- a field added one day must make this test fall, not
    pass unnoticed.

    Spec S:4/S:7: "identifiant de certificat, identifiant d'événement,
    date d'émission, empreinte salée de l'adresse, état. Aucun nom, aucune
    adresse." This asserts the register's field set is *exactly* that, on
    both the in-memory type (`CertificateEntry`) and its serialised form
    (`register_to_data`) -- so a future change that adds anything else, a
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
    internal register: ruling 5 says the public projection carries
    identifiers and states *only* -- never a fingerprint, even though the
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
# never the same value as it (ruling 4).
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
    """The load-bearing property ruling 4 exists for: `matching_code` is
    *sent to the participant* in their confirmation e-mail, so if
    `fingerprint` ever collapsed onto the same HMAC input space under the
    same salt, the register's "private" column would secretly be a value
    we already mailed out. The domain prefix (`_FINGERPRINT_DOMAIN`) is
    what keeps the two apart; this test is what would catch it if a future
    edit accidentally dropped that prefix."""
    event_id, email, salt = "mrg-042", "ada@example.org", "s3cr3t"
    assert fingerprint(event_id, email, salt) != matching_code(event_id, email, salt)


# ------------------------------------------------------------------ #
# duration_hours -- the written rounding rule, both sides of the
# boundary, and the exact tie (ruling 10).
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
    other -- this is the negative half of ruling 3's "identifier must not
    be deterministic": nothing here ties the identifier to the address by
    formula."""
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
    """Spec S:8: "un appariement corrigé se recalcule sans réinscrire."
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
    # what lets a failed delivery (task 14) retry without regenerating
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
# "no longer good" (ruling 11, brief step 4).
# ------------------------------------------------------------------ #


def test_a_revoked_certificate_still_verifies_but_reports_revoked() -> None:
    """Both halves, in one test, per the brief: "un test doit vérifier
    qu'un certificat révoqué se vérifie toujours cryptographiquement ET se
    rapporte comme révoqué."."""
    private_pem, public_pem = generate()
    issued = issue(
        _attendee(), _EVENT, private_pem, "salt", (), issued_on=date(2026, 8, 20)
    )

    register = revoke((issued.entry,), issued.entry.identifier)

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
        revoke((), "nope")


def test_revoke_leaves_every_other_entry_untouched() -> None:
    a = CertificateEntry("aaa", "mrg-042", date(2026, 8, 20), "fa", STATE_ISSUED)
    b = CertificateEntry("bbb", "mrg-042", date(2026, 8, 20), "fb", STATE_ISSUED)
    register = revoke((a, b), "aaa")
    assert register == (
        CertificateEntry("aaa", "mrg-042", date(2026, 8, 20), "fa", STATE_REVOKED),
        b,
    )


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
# The verification address (ruling 7).
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


# ------------------------------------------------------------------ #
# ORGANISER: a module constant, not configuration (ruling 8).
# ------------------------------------------------------------------ #


def test_organiser_is_a_non_empty_constant() -> None:
    assert ORGANISER == "The Example Collective"


# ------------------------------------------------------------------ #
# The shared fixture (D-14, ruling 6) -- what stops task 13 shipping a
# verification page that verifies nothing.
# ------------------------------------------------------------------ #


def test_the_shared_fixture_reasons_match_signing_pys_own_constants() -> None:
    assert _FIXTURE["reasons"]["malformed"] == MALFORMED
    assert _FIXTURE["reasons"]["no_matching_key"] == NO_MATCHING_KEY


def test_the_shared_fixture_states_match_this_modules_own_constants() -> None:
    assert _FIXTURE["states"]["issued"] == STATE_ISSUED
    assert _FIXTURE["states"]["revoked"] == STATE_REVOKED


def test_the_shared_fixture_base_matches_this_modules_own_constant() -> None:
    assert _FIXTURE["verification_base"] == VERIFICATION_BASE


def test_the_shared_fixtures_token_genuinely_verifies() -> None:
    example = _FIXTURE["signed_example"]
    result = verify(example["token"], [example["public_pem"]])
    assert result.valid
    assert result.payload == example["payload"]
    assert set(example["payload"]) == PAYLOAD_FIELDS


def test_the_shared_fixtures_url_is_reproducible_from_this_modules_own_function() -> (
    None
):
    example = _FIXTURE["signed_example"]
    assert (
        verification_url(example["identifier"], example["token"])
        == example["verification_url"]
    )


def test_the_shared_fixtures_projection_example_has_no_fingerprint_either() -> None:
    for row in _FIXTURE["projection_example"]["certificates"]:
        assert frozenset(row) == frozenset({"identifier", "state"})
        assert row["state"] in (STATE_ISSUED, STATE_REVOKED)
