"""Tests for `convener_ops.attendance` -- the appariement cascade (spec S:5) and
the summing that turns several connections into one person's duration.

Historical figures at `@example.org` throughout, per project convention:
nothing here is a real registrant.
"""

from __future__ import annotations

from convener_ops.attendance import (
    Matched,
    MatchedAttendee,
    MatchEvent,
    UnmatchedAttendee,
    UnreachableAttendee,
    match,
)
from convener_ops.platform import AttendanceRow
from convener_ops.registration import Registration, matching_code

_EVENT_ID = "mrg-042"
_SALT = "s3cr3t-salt-value"


def _row(
    display_name: str,
    email: str | None,
    duration_seconds: int = 1800,
    *,
    joined_at: str = "2026-08-20T18:00:00Z",
    left_at: str = "2026-08-20T18:30:00Z",
) -> AttendanceRow:
    return AttendanceRow(
        display_name=display_name,
        email=email,
        joined_at=joined_at,
        left_at=left_at,
        duration_seconds=duration_seconds,
    )


def _code_for(email: str) -> str:
    code = matching_code(_EVENT_ID, email, _SALT)
    assert code is not None
    return code


# ------------------------------------------------------------------ #
# Level 1: the matching code, tried first and unconditionally.
# ------------------------------------------------------------------ #


def test_code_in_display_name_matches_even_with_a_non_matching_address() -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    code = _code_for(ada.email)
    row = _row(f"Some Name {code}", "not-ada@example.org")

    result = match([row], [ada], event)

    assert result.matched == (MatchedAttendee(registration=ada, duration_seconds=1800),)
    assert result.unmatched == ()
    assert result.unreachable == ()


def test_a_present_code_wins_over_a_contradicting_address() -> None:
    """Level 1 overriding level 2: the row's address is Grace's, but the
    display name carries Ada's own code. A code present must win, or the
    strongest defence in the cascade is decorative."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    ada_code = _code_for(ada.email)
    row = _row(f"Grace Hopper {ada_code}", grace.email)

    result = match([row], [ada, grace], event)

    assert [m.registration for m in result.matched] == [ada]


def test_code_matching_absorbs_case_and_separator_variation() -> None:
    """How much punctuation/case drift level 1 forgives (see the module
    docstring): case-fold, and drop every non-alphanumeric character on
    both sides before searching. Hyphen dropped, doubled as an
    underscore, turned into a space, or wrapped in parentheses -- and the
    whole code typed in lower case -- all still match."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    code = _code_for(ada.email)
    spellings = [
        code,
        code.lower(),
        code.replace("-", ""),
        code.replace("-", " "),
        f"({code})",
        code.replace("-", "_"),
    ]

    for spelling in spellings:
        row = _row(f"Ada Lovelace {spelling}", "someone-else@example.org")
        result = match([row], [ada], event)
        assert [m.registration for m in result.matched] == [ada], spelling


def test_code_matching_does_not_tolerate_a_wrong_character() -> None:
    """The other half of the same trade-off: a genuine typo in the code
    itself is never forgiven. Absorbing punctuation is a convenience;
    absorbing a wrong letter would let a code matched too loosely bind the
    wrong person's presence."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    code = _code_for(ada.email)
    wrong_first = "Z" if code[0] != "Z" else "Q"
    wrong = wrong_first + code[1:]
    row = _row(f"Someone {wrong}", "unmatched@example.org")

    result = match([row], [ada], event)

    assert result.matched == ()


def test_no_salt_disables_level_1_for_every_row() -> None:
    """`matching_code` returns `None` with no salt configured -- an
    ordinary D-13 absence, not a failure -- so level 1 never finds
    anything and every row falls straight through to level 2."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=None)
    row = _row("Ada Lovelace WXYZ-2345", ada.email)

    result = match([row], [ada], event)

    assert [m.registration for m in result.matched] == [ada]


# ------------------------------------------------------------------ #
# Level 2: the exact address, tried once level 1 finds nothing.
# ------------------------------------------------------------------ #


def test_exact_address_matches_when_no_code_present() -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("Whatever the platform kept on file", "ada@example.org")

    result = match([row], [ada], event)

    assert [m.registration for m in result.matched] == [ada]


def test_address_match_ignores_case_and_surrounding_whitespace() -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("Ada L.", " Ada@Example.ORG ")

    result = match([row], [ada], event)

    assert [m.registration for m in result.matched] == [ada]


def test_address_wins_over_a_contradicting_name() -> None:
    """Level 2 overriding level 3: the display name reads as Grace, but
    the connection's own address is Ada's."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("Grace Hopper", ada.email)

    result = match([row], [ada, grace], event)

    assert [m.registration for m in result.matched] == [ada]


# ------------------------------------------------------------------ #
# Level 3: the normalised name, tried only once 1 and 2 both fail.
# ------------------------------------------------------------------ #


def test_normalized_name_matches_when_no_code_and_no_address_match() -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("ada lovelace", "typo@example.org")

    result = match([row], [ada], event)

    assert [m.registration for m in result.matched] == [ada]


def test_normalized_name_ignores_word_order() -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("Lovelace Ada", "typo@example.org")

    result = match([row], [ada], event)

    assert [m.registration for m in result.matched] == [ada]


def test_normalized_name_ignores_accents() -> None:
    adele = Registration("Adele", "Breguet", "adele@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("Adèle Bréguet", "typo@example.org")

    result = match([row], [adele], event)

    assert [m.registration for m in result.matched] == [adele]


# ------------------------------------------------------------------ #
# Unmatched vs. unreachable: two outcomes, never folded into one.
# ------------------------------------------------------------------ #


def test_present_address_that_matches_nobody_is_unmatched_not_unreachable() -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("Someone Else", "someone@example.org")

    result = match([row], [ada], event)

    assert result.matched == ()
    assert result.unreachable == ()
    assert [u.email for u in result.unmatched] == ["someone@example.org"]


def test_a_telephone_joiner_with_no_code_is_unreachable_not_unmatched() -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("+1 555 0100", None, duration_seconds=900)

    result = match([row], [ada], event)

    assert result.matched == ()
    assert result.unmatched == ()
    assert result.unreachable == (
        UnreachableAttendee(display_name="+1 555 0100", duration_seconds=900),
    )


def test_a_telephone_joiner_is_never_matched_by_name_alone() -> None:
    """Structural, not incidental: `platform.py`'s own docstring holds
    that a telephone joiner's display name can never stand in for a real
    name, so levels 2 and 3 are never even offered a `None`-email row.
    Proven directly with a display name that WOULD satisfy level 3 if it
    were tried."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("Ada Lovelace", None)

    result = match([row], [ada], event)

    assert result.matched == ()
    assert result.unreachable == (
        UnreachableAttendee(display_name="Ada Lovelace", duration_seconds=1800),
    )


def test_a_telephone_row_can_still_be_matched_by_code() -> None:
    """Level 1 does not depend on an address, so a telephone row that
    somehow does carry the code is still reachable through it."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    code = _code_for(ada.email)
    row = _row(f"Ada Lovelace {code}", None)

    result = match([row], [ada], event)

    assert [m.registration for m in result.matched] == [ada]
    assert result.unreachable == ()


# ------------------------------------------------------------------ #
# Durations sum per person.
# ------------------------------------------------------------------ #


def test_two_connections_by_the_same_person_sum_to_one_duration() -> None:
    """Une deconnexion suivie d'un retour produit deux lignes. Les compter
    separement priverait de certificat quelqu'un qui a suivi la seance
    entiere avec une coupure reseau -- exactement la personne qu'il faut
    ne pas punir."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    # Reconnection: capitalisation drifted between the two connections,
    # per platform.py's own measured note that the platform returns
    # different spellings for one person across two connections.
    first = _row("Ada Lovelace", ada.email, duration_seconds=1200)
    second = _row("ADA LOVELACE", ada.email, duration_seconds=1800)

    result = match([first, second], [ada], event)

    assert result.matched == (MatchedAttendee(registration=ada, duration_seconds=3000),)


def test_two_different_people_are_not_summed_together() -> None:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    ada_row = _row("Ada Lovelace", ada.email, duration_seconds=1200)
    grace_row = _row("Grace Hopper", grace.email, duration_seconds=1800)

    result = match([ada_row, grace_row], [ada, grace], event)

    totals = {m.registration.email: m.duration_seconds for m in result.matched}
    assert totals == {"ada@example.org": 1200, "grace@example.org": 1800}


def test_unmatched_rows_sharing_an_address_are_summed_too() -> None:
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    first = _row("Someone", "someone@example.org", duration_seconds=600)
    second = _row(
        "Someone (typed differently)", " Someone@Example.ORG ", duration_seconds=900
    )

    result = match([first, second], [], event)

    assert result.unmatched == (
        UnmatchedAttendee(
            display_name="Someone", email="someone@example.org", duration_seconds=1500
        ),
    )


def test_unreachable_rows_are_never_summed_together() -> None:
    """No address exists to group telephone rows by, so two of them are
    never folded into one -- inventing a shared identity for them would be
    exactly the kind of manual-recovery invention the task rules out."""
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    first = _row("+1 555 0100", None, duration_seconds=600)
    second = _row("+1 555 0100", None, duration_seconds=900)

    result = match([first, second], [], event)

    assert len(result.unreachable) == 2
    assert {u.duration_seconds for u in result.unreachable} == {600, 900}


# ------------------------------------------------------------------ #
# Nobody disappears in silence.
# ------------------------------------------------------------------ #


def test_no_attendance_row_is_lost_between_input_and_output() -> None:
    """The three categories together account for every distinct person who
    arrived: two rows for Ada are one matched person, two rows sharing an
    unmatched address are one unresolved person, and two telephone rows
    with no address to group by are two separate, unreachable people --
    four distinct people from five rows, and every second of duration
    still accounted for on the way out."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    rows = [
        _row("Ada Lovelace", ada.email, duration_seconds=1200),
        _row("ADA LOVELACE", ada.email, duration_seconds=600),
        _row("Someone", "someone@example.org", duration_seconds=300),
        _row("+1 555 0100", None, duration_seconds=400),
        _row("+1 555 0101", None, duration_seconds=500),
    ]

    result = match(rows, [ada], event)

    distinct_people = (
        len(result.matched) + len(result.unmatched) + len(result.unreachable)
    )
    assert distinct_people == 4

    total_in = sum(row.duration_seconds for row in rows)
    total_out = (
        sum(m.duration_seconds for m in result.matched)
        + sum(u.duration_seconds for u in result.unmatched)
        + sum(u.duration_seconds for u in result.unreachable)
    )
    assert total_out == total_in


def test_no_rows_produces_an_empty_result() -> None:
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)

    result = match([], [], event)

    assert result == Matched(matched=(), unmatched=(), unreachable=())


def test_no_registrations_leaves_addressed_rows_unmatched() -> None:
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("Nobody Registered", "nobody@example.org")

    result = match([row], [], event)

    assert result.matched == ()
    assert [u.email for u in result.unmatched] == ["nobody@example.org"]
