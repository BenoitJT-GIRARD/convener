"""The internal agenda feed (task 8, phase 6) -- see `convener_ops.agenda`'s own
module docstring for the feed in full, and its architecture against the
public one.

Every test here parses the generated `.ics` bytes back with
`ics_reader.parse_calendar` -- a reader written independently of this
module's own escape/fold functions (see that module's own docstring) --
rather than asserting on `build_internal_calendar`'s return value as a
plain string. A test that only ever eyeballed the string could not tell a
correctly-escaped comma from a corrupted file; a test that parses it back
the way a client would can.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from conftest import config, speaker
from ics_reader import parse_calendar, unescape_text

from convener_ops.agenda import (
    _escape_text,
    _fold_line,
    _seminar_duration_minutes,
    _slug,
    build_internal_calendar,
)
from convener_ops.notify import due_date
from convener_ops.paths import repo_root
from convener_ops.registration import signup_url

_ROOT = repo_root()
_FIXTURE_PATH = _ROOT / "tools" / "tests" / "fixtures" / "paris-standing-start.json"
_FIXTURE: list[dict[str, Any]] = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _scheduled(**overrides: Any) -> dict[str, Any]:
    base = {
        "edition_code": "MRG-07",
        "status": "scheduled",
        "date": "2026-09-10",
        "title": "Neuroethological approaches to social behaviour",
    }
    base.update(overrides)
    return speaker(**base)


# ------------------------------------------------------------------ #
# Calendar-level shape
# ------------------------------------------------------------------ #


def test_the_calendar_carries_the_properties_a_client_requires() -> None:
    raw = build_internal_calendar([_scheduled()], config()).encode("utf-8")
    parsed = parse_calendar(raw)
    assert parsed.calendar.properties["VERSION"] == "2.0"
    assert parsed.calendar.properties["PRODID"], "PRODID must not be blank"
    assert parsed.calendar.properties["CALSCALE"] == "GREGORIAN"


def test_no_scheduled_edition_and_no_deadline_is_a_valid_empty_calendar() -> None:
    raw = build_internal_calendar([], config()).encode("utf-8")
    parsed = parse_calendar(raw)
    assert parsed.events == []
    assert parsed.calendar.properties["VERSION"] == "2.0"


def test_output_is_byte_identical_across_two_builds_from_the_same_data() -> None:
    """The churn check: a feed rebuilt from unchanged data must not change
    -- otherwise every subscriber's client re-syncs for nothing, and a real
    change hides in that noise."""
    speakers = [
        _scheduled(),
        speaker(status="lead", selection={"opened_on": "2026-08-01"}),
    ]
    cfg = config()
    first = build_internal_calendar(speakers, cfg)
    second = build_internal_calendar(speakers, cfg)
    assert first == second


def test_output_carries_no_bare_line_feed() -> None:
    raw = build_internal_calendar([_scheduled()], config()).encode("utf-8")
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")


# ------------------------------------------------------------------ #
# The scheduled-edition VEVENT
# ------------------------------------------------------------------ #


def test_a_scheduled_edition_becomes_one_vevent_addressed_to_the_event_page() -> None:
    entry = _scheduled(edition_code="MRG-07", title="On analytical engines")
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    parsed = parse_calendar(raw)
    assert len(parsed.events) == 1
    event = parsed.events[0].properties
    expected_url = signup_url("mrg-07")
    assert event["SUMMARY"] == "On analytical engines"
    assert event["UID"] == expected_url
    assert event["LOCATION"] == expected_url
    assert event["URL"] == expected_url
    # DTSTAMP mirrors DTSTART -- never the real clock (see the module
    # docstring): the churn test above already proves this in practice,
    # this is the same fact stated directly.
    assert event["DTSTAMP"] == event["DTSTART"]


def test_dtend_is_the_configured_seminar_duration_after_dtstart() -> None:
    from datetime import datetime

    entry = _scheduled()
    raw = build_internal_calendar([entry], config(seminar_duration_minutes=45)).encode(
        "utf-8"
    )
    event = parse_calendar(raw).events[0].properties
    start = datetime.strptime(event["DTSTART"], "%Y%m%dT%H%M%SZ")
    end = datetime.strptime(event["DTEND"], "%Y%m%dT%H%M%SZ")
    assert (end - start).total_seconds() == 45 * 60


def test_a_non_scheduled_edition_contributes_no_edition_vevent() -> None:
    entry = speaker(status="confirmed", edition_code="MRG-09", date="2026-09-10")
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    assert parse_calendar(raw).events == []


def test_a_blank_edition_code_is_skipped_rather_than_published_at_a_wrong_address() -> (
    None
):
    entry = _scheduled(edition_code="")
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    assert parse_calendar(raw).events == []


def test_an_unparsable_date_is_skipped_rather_than_raised() -> None:
    entry = _scheduled(date="not-a-date")
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    assert parse_calendar(raw).events == []


def test_multiple_scheduled_editions_are_ordered_soonest_first() -> None:
    later = _scheduled(edition_code="MRG-08", date="2026-10-01", title="Later talk")
    sooner = _scheduled(edition_code="MRG-07", date="2026-09-10", title="Sooner talk")
    raw = build_internal_calendar([later, sooner], config()).encode("utf-8")
    titles = [event.properties["SUMMARY"] for event in parse_calendar(raw).events]
    assert titles == ["Sooner talk", "Later talk"]


# ------------------------------------------------------------------ #
# Timezone: reused, not re-derived -- the shared fixture, all eight cases
# ------------------------------------------------------------------ #


@pytest.mark.parametrize("case", _FIXTURE, ids=lambda c: c["iso_date"])
def test_dtstart_matches_the_shared_paris_offset_fixture(case: dict[str, Any]) -> None:
    """Every one of the eight shared-fixture dates, both sides of both DST
    transitions, both years -- not only a winter date, which would pass
    against a feed that hard-typed a single offset (three of this
    project's five real fixture editions fall in summer)."""
    entry = _scheduled(date=case["iso_date"])
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    event = parse_calendar(raw).events[0].properties

    # Independent of `agenda.py`: 12:30 local minus the fixture's own
    # UTC offset, computed here by plain arithmetic on the offset string
    # itself, not by asking `zoneinfo` or `Intl` to resolve it again.
    sign = 1 if case["offset"].startswith("+") else -1
    offset_hours = int(case["offset"][1:3])
    utc_hour = 12 - sign * offset_hours
    expected = f"{case['iso_date'].replace('-', '')}T{utc_hour:02d}3000Z"
    assert event["DTSTART"] == expected


def test_the_fixture_covers_both_sides_of_both_dst_boundaries() -> None:
    abbreviations = {c["abbreviation"] for c in _FIXTURE}
    assert abbreviations == {"CET", "CEST"}


# ------------------------------------------------------------------ #
# No personal data, no room link (D-19, project-wide rule)
# ------------------------------------------------------------------ #


def test_a_room_link_never_reaches_the_internal_calendar() -> None:
    """Fix round 2 (branch review, Important 1): the previous 61-octet
    fixture link sat just under RFC 5545's 75-octet fold threshold and so
    never exercised folding at all -- a byte-substring search against the
    *unfolded* string would still report "absent" for a link that reached
    the file but got folded by `_fold_line` first, the same false-pass
    shape `test_site.py::test_a_built_public_page_never_carries_a_room_link`
    already found and fixed for the built public site. This fixture is a
    realistic 93-octet Zoom URL (a meeting id plus password), long enough
    to actually cross the fold boundary, and the check strips the
    `"\\r\\n "` fold-continuation marker before searching, mirroring that
    fix verbatim.
    """
    room_link = (
        "https://us02web.zoom.us/j/89234567890"
        "?pwd=aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890abcdef"
    )
    entry = _scheduled(zoom_link=room_link)
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    text = raw.decode("utf-8")
    unfolded = text.replace("\r\n ", "")
    assert room_link not in text
    assert room_link not in unfolded


def test_no_speaker_name_or_email_reaches_a_deadline_entry() -> None:
    distinctive_name = "Zzyzx Distinctivename"
    distinctive_email = "zzyzx@example.org"
    entry = speaker(
        id="spk-042",
        name=distinctive_name,
        email=distinctive_email,
        status="lead",
        selection={"opened_on": "2026-08-01"},
    )
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    assert distinctive_name.encode("utf-8") not in raw
    assert distinctive_email.encode("utf-8") not in raw
    assert b"spk-042" in raw


# ------------------------------------------------------------------ #
# Preparation deadlines: `notify.due_date` reused, not re-derived
# ------------------------------------------------------------------ #


def test_a_lead_awaiting_a_board_decision_gets_its_deadline_from_notify() -> None:
    entry = speaker(id="spk-042", status="lead", selection={"opened_on": "2026-08-01"})
    cfg = config(vote_window_days=14)
    expected = due_date(entry, cfg)
    assert expected is not None

    raw = build_internal_calendar([entry], cfg).encode("utf-8")
    events = parse_calendar(raw).events
    assert len(events) == 1
    event = events[0].properties
    params = events[0].params
    assert params["DTSTART"] == "VALUE=DATE"
    assert event["DTSTART"] == expected.due.replace("-", "")
    assert expected.step in event["SUMMARY"]
    assert "spk-042" in event["SUMMARY"]


def test_a_scheduled_edition_carries_no_deadline_entry_of_its_own() -> None:
    """`notify.due_date` returns `None` for `scheduled` (it only tracks
    `lead`, `invited` and `delivered`) -- so the one event a purely
    `scheduled` speaker contributes is its own edition VEVENT, never a
    second, spurious deadline entry."""
    entry = _scheduled()
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    assert len(parse_calendar(raw).events) == 1


def test_an_invited_speaker_awaiting_follow_up_gets_a_deadline_too() -> None:
    entry = speaker(
        id="spk-050", status="invited", selection={"decided_on": "2026-08-01"}
    )
    cfg = config(sla_days={"invitation_follow_up": 5})
    expected = due_date(entry, cfg)
    assert expected is not None

    raw = build_internal_calendar([entry], cfg).encode("utf-8")
    event = parse_calendar(raw).events[0].properties
    assert event["DTSTART"] == expected.due.replace("-", "")


def test_a_record_with_no_computable_deadline_contributes_nothing() -> None:
    entry = speaker(id="spk-060", status="parked")
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    assert parse_calendar(raw).events == []


def test_a_record_missing_its_id_is_skipped_even_with_a_real_deadline() -> None:
    entry = speaker(status="lead", selection={"opened_on": "2026-08-01"})
    entry["id"] = ""
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    assert parse_calendar(raw).events == []


# ------------------------------------------------------------------ #
# RFC 5545 mechanics: escaping and 75-octet folding
# ------------------------------------------------------------------ #


def test_a_123_character_title_folds_and_round_trips_intact() -> None:
    """The exact defect this feed exists to avoid: an unfolded long content
    line, or a fold that corrupts a multi-byte character. 123 characters,
    including a comma (which must itself be escaped) -- long enough that
    the property line exceeds the 75-octet fold limit on its own."""
    title = (
        "Reproducible, open-source behavioural neuroscience: motion tracking, "
        "kinematics and cross-species comparison across borders"
    )
    assert len(title) == 123, f"fixture title is {len(title)} characters, expected 123"
    entry = _scheduled(title=title)
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    parsed = parse_calendar(raw)  # raises if any physical line exceeds 75 octets
    assert parsed.events[0].properties["SUMMARY"] == title


def test_a_title_with_accented_and_non_latin_characters_folds_on_a_char_boundary() -> (
    None
):
    title = (
        "Étude comportementale : 行動科学の再現性, "
        "une comparaison inter-espèces approfondie"
    )
    entry = _scheduled(title=title)
    raw = build_internal_calendar([entry], config()).encode("utf-8")
    parsed = parse_calendar(raw)  # raises on a corrupted UTF-8 fold
    assert parsed.events[0].properties["SUMMARY"] == title


def test_escape_text_handles_all_four_rfc_5545_cases() -> None:
    value = "back\\slash; semicolon, comma\nnewline"
    escaped = _escape_text(value)
    assert unescape_text(escaped) == value
    assert escaped == "back\\\\slash\\; semicolon\\, comma\\nnewline"


def test_fold_line_leaves_a_short_line_untouched() -> None:
    short = "SUMMARY:short"
    assert _fold_line(short) == short


def test_fold_line_folds_at_exactly_75_octets_not_76() -> None:
    exactly_75 = "X" * 75
    assert _fold_line(exactly_75) == exactly_75
    over_by_one = "X" * 76
    folded = _fold_line(over_by_one)
    assert folded == "X" * 75 + "\r\n X"


def test_slug_collapses_a_label_to_a_readable_uid_suffix() -> None:
    assert _slug("Board decision") == "board-decision"
    assert _slug("Forum summary") == "forum-summary"


def test_fold_line_backs_up_off_a_multibyte_character_boundary() -> None:
    """A direct hit on the UTF-8 boundary correction itself, not merely a
    round trip that happens not to need it: 74 ASCII bytes, then a
    three-byte character (`行`) straddling the 75-octet fold point, so the
    naive 75-octet cut would land on that character's own second byte --
    a continuation byte, `10xxxxxx` -- and the loop must back up to the
    character's first byte instead."""
    line = "A" * 74 + "行" + "BBBBB"
    folded = _fold_line(line)
    assert folded == "A" * 74 + "\r\n " + "行BBBBB"
    # Every physical line stays valid UTF-8 on its own -- the corruption
    # this function exists to prevent would raise here.
    for physical in folded.split("\r\n "):
        physical.encode("utf-8").decode("utf-8")


def test_non_mapping_entries_are_skipped_in_both_the_edition_and_deadline_passes() -> (
    None
):
    """`speakers` need not be well-formed (the module docstring's own
    claim): a `None`, a bare string or a stray integer mixed into the list
    must not raise, in either of `build_internal_calendar`'s two passes
    over it."""
    speakers: list[Any] = [None, "not-a-record", 42, _scheduled()]
    raw = build_internal_calendar(speakers, config()).encode("utf-8")
    events = parse_calendar(raw).events
    assert len(events) == 1
    assert events[0].properties["SUMMARY"] == _scheduled()["title"]


# ------------------------------------------------------------------ #
# The seminar duration default (mirrors sweep.sweep's own fallback)
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    "raw_config",
    [
        {},
        {"seminar_duration_minutes": "ninety"},
        {"seminar_duration_minutes": True},
        {"seminar_duration_minutes": 0},
        {"seminar_duration_minutes": -5},
        "not-a-mapping",
        None,
    ],
)
def test_seminar_duration_falls_back_to_ninety_on_anything_unusable(
    raw_config: Any,
) -> None:
    assert _seminar_duration_minutes(raw_config) == 90


def test_seminar_duration_reads_a_real_configured_value() -> None:
    assert _seminar_duration_minutes({"seminar_duration_minutes": 45}) == 45


# ------------------------------------------------------------------ #
# Publication allowlist discipline: nothing copies this feed into a
# published bundle
# ------------------------------------------------------------------ #


def test_nothing_in_the_build_ever_names_the_internal_agenda_feed() -> None:
    """The internal feed is never published to the public site (a project
    constraint, not merely today's behaviour): this sweeps every app/
    build-copy script and both `deploy.yml`/`publish-vitrine.yml`'s own
    "Push to example-showcase" steps for the one string that would put it
    there, the same allowlist discipline `registry.ts`/`public_data.py`
    already apply to what may leave this repository at all -- here,
    proven by the *absence* of a reference, not by a list of what is
    permitted.
    """
    haystacks: list[tuple[str, str]] = []
    scripts_dir = _ROOT / "app" / "scripts"
    for script in sorted(scripts_dir.glob("copy-*.mjs")):
        haystacks.append((str(script), script.read_text(encoding="utf-8")))
    for workflow_name in ("deploy.yml", "publish-vitrine.yml"):
        workflow_path = _ROOT / ".github" / "workflows" / workflow_name
        haystacks.append(
            (str(workflow_path), workflow_path.read_text(encoding="utf-8"))
        )

    offending = [path for path, text in haystacks if "agenda-internal" in text]
    # Exactly one file is allowed to name it: deploy.yml's own "Commit
    # internal agenda" step, which commits it back to *this* repository,
    # never into a published bundle.
    allowed = {str(_ROOT / ".github" / "workflows" / "deploy.yml")}
    assert set(offending) <= allowed, (
        f"'agenda-internal' referenced outside the allowed commit step: "
        f"{sorted(set(offending) - allowed)}"
    )


def test_agenda_internal_ics_is_declared_binary_in_gitattributes() -> None:
    """The other half of the CRLF guarantee: `.gitattributes` must mark
    this path binary, or a checkin would renormalise its CRLF line
    endings to this repository's own blanket `eol=lf` rule -- see
    `agenda_internal`'s own docstring."""
    text = (_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "public-data/agenda-internal.ics" in text
    line = next(
        line for line in text.splitlines() if "public-data/agenda-internal.ics" in line
    )
    assert "binary" in line


def test_gitignore_carries_a_named_exception_for_the_internal_feed() -> None:
    text = (_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "!public-data/agenda-internal.ics" in text
