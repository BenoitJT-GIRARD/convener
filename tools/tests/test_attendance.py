"""Tests for `convener_ops.attendance` -- the appariement cascade (spec S:5) and
the summing that turns several connections into one person's duration.

Historical figures at `@example.org` throughout, per project convention:
nothing here is a real registrant.
"""

from __future__ import annotations

from fractions import Fraction

from convener_ops.attendance import (
    DEFAULT_ELIGIBILITY_SHARE,
    EligibilityThreshold,
    Matched,
    MatchedAttendee,
    MatchEvent,
    UnmatchedAttendee,
    UnreachableAttendee,
    _name_tokens,
    _name_tokens_for_matching,
    eligible,
    eligible_attendees,
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
# A tie at any level is never resolved by guessing: `None`, so the row
# lands in `unmatched` where a host with the room roster can tell the
# candidates apart. Reviewed and required: the first-match idiom used
# elsewhere in this package (`find_speaker`, `find_by_email`) resolves on
# keys unique by construction; a normalised name is not.
# ------------------------------------------------------------------ #


def test_two_marie_martins_with_no_deciding_address_land_unmatched() -> None:
    """The exact case the review named: two registrants share a normalised
    name, the row's own address matches neither, and nothing in the
    cascade may pick a winner by position in the registrations list --
    that would let who signed up first decide who was in the room."""
    first_marie = Registration("Marie", "Martin", "marie.m1@example.org", "", False)
    second_marie = Registration("Marie", "Martin", "marie.m2@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("Marie Martin", "someone-else@example.org")

    result = match([row], [first_marie, second_marie], event)

    assert result.matched == ()
    assert [u.email for u in result.unmatched] == ["someone-else@example.org"]
    assert set(result.unmatched[0].tied_with) == {
        "marie.m1@example.org",
        "marie.m2@example.org",
    }


def test_two_marie_martins_tie_regardless_of_registration_order() -> None:
    """The reverse of the test above: swapping the two registrants' order
    must not change the answer -- a first-match idiom would have the
    winner flip with the order; refusing the tie does not, and the same
    two candidates are surfaced either way."""
    first_marie = Registration("Marie", "Martin", "marie.m1@example.org", "", False)
    second_marie = Registration("Marie", "Martin", "marie.m2@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("Marie Martin", "someone-else@example.org")

    result = match([row], [second_marie, first_marie], event)

    assert result.matched == ()
    assert [u.email for u in result.unmatched] == ["someone-else@example.org"]
    assert set(result.unmatched[0].tied_with) == {
        "marie.m1@example.org",
        "marie.m2@example.org",
    }


def test_jean_martin_and_martin_jean_are_a_name_tie_not_two_people() -> None:
    """Because level 3 compares a *set* of words, the collision class is
    wider than two people sharing one spelling: "Jean Martin" and "Martin
    Jean" are two different registrants whose word sets are identical, so
    a row reading either name (with no deciding address) must not resolve
    to either of them by guessing."""
    jean_martin = Registration("Jean", "Martin", "jean@example.org", "", False)
    martin_jean = Registration("Martin", "Jean", "martin@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("Jean Martin", "someone-else@example.org")

    result = match([row], [jean_martin, martin_jean], event)

    assert result.matched == ()
    assert [u.email for u in result.unmatched] == ["someone-else@example.org"]
    assert set(result.unmatched[0].tied_with) == {
        "jean@example.org",
        "martin@example.org",
    }


def test_two_codes_in_one_display_name_is_a_tie_at_level_1() -> None:
    """A display name that somehow carries two different registrants'
    codes is not a person to guess about either."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    ada_code = _code_for(ada.email)
    grace_code = _code_for(grace.email)
    row = _row(f"Whoever {ada_code} {grace_code}", "someone-else@example.org")

    result = match([row], [ada, grace], event)

    assert result.matched == ()
    assert [u.email for u in result.unmatched] == ["someone-else@example.org"]
    assert set(result.unmatched[0].tied_with) == {
        "ada@example.org",
        "grace@example.org",
    }


def test_a_level_1_tie_is_terminal_and_not_overridden_by_a_deciding_address() -> None:
    """A tie is not merely inconclusive -- it stops the cascade outright,
    the same way an unambiguous level-1 match already overrides a
    contradicting address. Here the row's own address *would* uniquely
    identify Ada if level 2 were tried, but it never is: the level-1 tie
    (both Ada's and Grace's codes present) ends the cascade first."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    ada_code = _code_for(ada.email)
    grace_code = _code_for(grace.email)
    row = _row(f"Whoever {ada_code} {grace_code}", ada.email)

    result = match([row], [ada, grace], event)

    assert result.matched == ()
    assert [u.email for u in result.unmatched] == [ada.email]
    assert set(result.unmatched[0].tied_with) == {
        "ada@example.org",
        "grace@example.org",
    }


def test_a_shared_address_is_a_tie_at_level_2() -> None:
    """`upsert` deduplicates addresses within one event, so this should
    not occur in practice -- the guard is exercised directly here anyway,
    against a `registrations` list built some other way than through
    `upsert`."""
    first_ada = Registration("Ada", "Lovelace", "shared@example.org", "", False)
    second_ada = Registration("Ada", "Lovelace-Byron", "shared@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=None)
    row = _row("Whoever this is", "shared@example.org")

    result = match([row], [first_ada, second_ada], event)

    assert result.matched == ()
    assert [u.email for u in result.unmatched] == ["shared@example.org"]
    assert set(result.unmatched[0].tied_with) == {"shared@example.org"}


def test_a_code_tie_on_a_telephone_row_still_lands_unreachable() -> None:
    """A rare edge case: a phone-in row (no address at all) whose display
    name somehow carries two different registrants' codes. The tie is
    still refused -- `_resolve` never falls through to guess -- and the
    row still lands in `unreachable`, since there is no address for it to
    land in `unmatched` under; there is nothing further to surface here,
    since an unreachable row is never host-resolvable regardless."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    ada_code = _code_for(ada.email)
    grace_code = _code_for(grace.email)
    row = _row(f"Whoever {ada_code} {grace_code}", None, duration_seconds=120)

    result = match([row], [ada, grace], event)

    assert result.matched == ()
    assert result.unmatched == ()
    assert result.unreachable == (
        UnreachableAttendee(
            display_name=f"Whoever {ada_code} {grace_code}", duration_seconds=120
        ),
    )


def test_a_display_name_that_normalises_to_nothing_never_matches_by_name() -> None:
    """A display name of nothing but combining marks and whitespace
    normalises to an empty token set -- guarded explicitly, so it can
    never compare equal to a registrant whose own name (pathologically)
    also normalised to empty; two empties are not "the same name"."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("́ ́", "typo@example.org")

    result = match([row], [ada], event)

    assert result.matched == ()
    assert [u.email for u in result.unmatched] == ["typo@example.org"]


# ------------------------------------------------------------------ #
# Level 3 ignores a token shaped like a matching code, because the
# confirmation e-mail's own worked example keeps the participant's real
# name in the display name *alongside* the code, not instead of it.
# ------------------------------------------------------------------ #


def test_a_mistyped_code_still_lets_level_3_match_on_the_name_beside_it() -> None:
    """The perverse case the review traced through two tasks: a
    participant who followed the confirmation e-mail's instruction and
    typed their real name plus a mistyped code must still be reachable at
    level 3 -- refusing to strip the code token would make following the
    instruction the reason the match fails, while someone who ignored the
    e-mail entirely and joined under a different address would still
    match at the same level."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    real_code = _code_for(ada.email)
    wrong_first = "Z" if real_code[0] != "Z" else "Q"
    mistyped_code = wrong_first + real_code[1:]
    row = _row(f"Ada Lovelace {mistyped_code}", "not-ada@example.org")

    result = match([row], [ada], event)

    assert [m.registration for m in result.matched] == [ada]


def test_a_code_shaped_token_is_dropped_even_when_it_is_nobodys_real_code() -> None:
    """`looks_like_a_matching_code` is shape-only: any eight-symbol,
    alphabet-only token is dropped from the name comparison, whether or
    not it happens to be a real code for anyone in `registrations`."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=None)
    row = _row("Ada Lovelace ZZZZ-9999", "typo@example.org")

    result = match([row], [ada], event)

    assert [m.registration for m in result.matched] == [ada]


def test_code_stripping_applies_to_the_display_name_side_only() -> None:
    """`_name_tokens_for_matching` (the display-name side) drops a
    code-shaped token; `_name_tokens` (used for a registrant's own
    `first_name`/`surname` in `_name_candidates`) does not -- a
    registration whose own surname happens to look code-shaped (contrived,
    but not excluded by `to_registration`) is not silently rewritten by
    the level-3 comparison. Tested directly against the two private
    tokenisers rather than through `match`: a display name that types that
    same code-shaped surname has it stripped from *its own* token set too
    (the rule is unconditional, not aware of whose surname it might be),
    so this asymmetry is not otherwise observable from `match`'s outcome
    alone."""
    text = "Ada ZZZZ9999"
    assert _name_tokens(text) == frozenset({"ada", "zzzz9999"})
    assert _name_tokens_for_matching(text) == frozenset({"ada"})


# ------------------------------------------------------------------ #
# Two invariants `match` enforces rather than only trusting: a blank
# address is not an address, and a negative duration is not time present.
# ------------------------------------------------------------------ #


def test_a_blank_address_is_treated_as_no_address_at_all() -> None:
    """`platform.py`'s own reader never produces this (a blank cell
    becomes `None`), but `match` does not merely trust that -- a
    whitespace-only `email` must still route to `unreachable`, never to
    `unmatched` under a blank key."""
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    row = _row("+1 555 0100", "   ", duration_seconds=300)

    result = match([row], [], event)

    assert result.unmatched == ()
    assert result.unreachable == (
        UnreachableAttendee(display_name="+1 555 0100", duration_seconds=300),
    )


def test_a_negative_duration_never_reduces_a_matched_persons_total() -> None:
    """`platform_fcc.py` deliberately preserves a negative
    `audio_duration` exactly as the provider sent it; `match` is where
    both platforms' rows are summed toward a certificate-worthy total, so
    a negative contribution is floored at zero there, without touching or
    rejecting the row itself."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    good = _row("Ada Lovelace", ada.email, duration_seconds=1200)
    bad = _row("Ada Lovelace", ada.email, duration_seconds=-9999)

    result = match([good, bad], [ada], event)

    assert result.matched == (MatchedAttendee(registration=ada, duration_seconds=1200),)


def test_a_negative_duration_is_floored_for_unmatched_and_unreachable_too() -> None:
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    unmatched_row = _row("Someone", "someone@example.org", duration_seconds=-30)
    unreachable_row = _row("+1 555 0100", None, duration_seconds=-30)

    result = match([unmatched_row, unreachable_row], [], event)

    assert result.unmatched == (
        UnmatchedAttendee(
            display_name="Someone", email="someone@example.org", duration_seconds=0
        ),
    )
    assert result.unreachable == (
        UnreachableAttendee(display_name="+1 555 0100", duration_seconds=0),
    )


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


# ------------------------------------------------------------------ #
# Eligibility (spec S:5): a share of the session, not a fixed cutoff.
# ------------------------------------------------------------------ #


def _attendee(duration_seconds: int) -> MatchedAttendee:
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    return MatchedAttendee(registration=ada, duration_seconds=duration_seconds)


def test_a_duration_exactly_at_the_threshold_is_eligible() -> None:
    """The brief's own boundary case: exactly the fraction asked for
    counts, not only strictly more than it."""
    threshold = EligibilityThreshold(seminar_duration_minutes=90, share=0.5)

    assert eligible(_attendee(2700), threshold) is True


def test_one_second_under_the_threshold_is_not_eligible() -> None:
    threshold = EligibilityThreshold(seminar_duration_minutes=90, share=0.5)

    assert eligible(_attendee(2699), threshold) is False


def test_zero_seconds_is_never_eligible() -> None:
    threshold = EligibilityThreshold(seminar_duration_minutes=90, share=0.5)

    assert eligible(_attendee(0), threshold) is False


def test_the_default_share_matches_data_config_ymls_own_chosen_literal() -> None:
    """`DEFAULT_ELIGIBILITY_SHARE` is `data/config.yml`'s own
    `0.6666666666666666`, digit for digit -- the closest
    float64 to two thirds, chosen fractionally *below* the exact value so
    a duration of exactly 3600 seconds against a 90-minute session still
    reads as eligible, not refused by a rounding artefact. Not `Fraction(2,
    3)`: an exact fallback would be quietly stricter than the real file's
    own, slightly more forgiving, threshold."""
    threshold = EligibilityThreshold(seminar_duration_minutes=90)

    assert threshold.share == DEFAULT_ELIGIBILITY_SHARE == 0.6666666666666666
    assert threshold.threshold_seconds < Fraction(3600)
    assert eligible(_attendee(3600), threshold) is True
    assert eligible(_attendee(3599), threshold) is False


def test_a_configured_share_of_one_requires_the_entire_session() -> None:
    """The top of the legal range ``]0, 1]``: allowed, and means "all of
    it"."""
    threshold = EligibilityThreshold(seminar_duration_minutes=60, share=1.0)

    assert eligible(_attendee(3600), threshold) is True
    assert eligible(_attendee(3599), threshold) is False


def test_from_config_defaults_the_share_when_the_key_is_absent() -> None:
    threshold = EligibilityThreshold.from_config({"seminar_duration_minutes": 90})

    assert threshold.seminar_duration_minutes == 90
    assert threshold.share == DEFAULT_ELIGIBILITY_SHARE


def test_from_config_reads_an_explicit_eligibility_share() -> None:
    threshold = EligibilityThreshold.from_config(
        {"seminar_duration_minutes": 90, "eligibility_share": 0.5}
    )

    assert threshold.share == 0.5
    assert threshold.threshold_seconds == Fraction(2700)


def test_eligible_attendees_returns_only_those_crossing_the_threshold() -> None:
    threshold = EligibilityThreshold(seminar_duration_minutes=90, share=0.5)
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    matched = Matched(
        matched=(
            MatchedAttendee(registration=ada, duration_seconds=2700),
            MatchedAttendee(registration=grace, duration_seconds=100),
        ),
        unmatched=(),
        unreachable=(),
    )

    result = eligible_attendees(matched, threshold)

    assert result == (matched.matched[0],)


def test_present_without_registration_is_never_a_candidate_for_eligibility() -> None:
    """An `UnmatchedAttendee` -- present in the room, no registration the
    cascade could tie them to -- is excluded from `eligible_attendees` by
    never being offered to it, not by a computed `False`. Spec S:9 calls
    this person "non eligible"; this test proves the module reaches that
    verdict by construction rather than by asking `eligible` a question it
    has no honest answer for (see the module docstring)."""
    threshold = EligibilityThreshold(seminar_duration_minutes=90, share=0.5)
    matched = Matched(
        matched=(),
        unmatched=(
            UnmatchedAttendee(
                display_name="Walk-in",
                email="walkin@example.org",
                duration_seconds=5400,
            ),
        ),
        unreachable=(),
    )

    assert eligible_attendees(matched, threshold) == ()


def test_a_telephone_joiner_is_never_a_candidate_for_eligibility_either() -> None:
    """The other case the match's types separate from `unmatched`: a phone
    joiner has a duration and no way to ever acquire an identity. Same
    exclusion-by-construction as the unmatched case above, for the same
    reason -- see the module docstring's "Eligibility answers a question
    only a matched attendee can be asked"."""
    threshold = EligibilityThreshold(seminar_duration_minutes=90, share=0.5)
    matched = Matched(
        matched=(),
        unmatched=(),
        unreachable=(
            UnreachableAttendee(display_name="+1 555 0100", duration_seconds=5400),
        ),
    )

    assert eligible_attendees(matched, threshold) == ()


def test_a_registrant_who_never_attended_has_no_eligibility_to_compute() -> None:
    """No `AttendanceRow` named them, so `match` places them in none of the
    three outcomes (its own "Nobody disappears in silence") -- and with no
    entry in `matched.matched`, `eligible_attendees` has nothing to
    examine either."""
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    event = MatchEvent(event_id=_EVENT_ID, salt=_SALT)
    threshold = EligibilityThreshold(seminar_duration_minutes=90, share=0.5)

    result = match([], [ada], event)

    assert result.matched == ()
    assert eligible_attendees(result, threshold) == ()
