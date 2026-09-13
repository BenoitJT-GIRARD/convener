"""What must never reach a published page, read from both places it can live.

`publish-showcase.yml` greps the built site for every string this returns and
refuses to publish when one is found. That guard used to read
`instance/data/speakers.yml`'s own `zoom_link` and nothing else — which is
empty on every record of an instance whose account is one permanent room,
because D-06 makes the account itself the room and the address lives in
`instance/data/config.yml` as one value for the whole series.

So on that shape of instance the guard printed *"no speaker record carries a
room link -- nothing to check"* and checked nothing, on precisely the shape
where what leaks is a standing access code rather than one event's URL.
Measured on the instance this product was derived for: two editions at
`scheduled`, both with an empty `zoom_link`, and a series room with an access
code in the configuration the step never opened.

The shipped example is the other shape — a per-event link and no series
instructions — so it exercises only one half. These build both.
"""

from __future__ import annotations

from convener_ops.publication.public_data import MIN_SECRET_LENGTH, room_strings

SERIES = {
    "instructions": (
        "Join online: https://join.example.test/theseries\nAccess code: 8842798"
    )
}


def test_a_per_event_link_is_watched() -> None:
    found = room_strings([{"zoom_link": "https://meet.example.test/j/123456789"}], {})

    assert found == ["https://meet.example.test/j/123456789"]


def test_the_series_instructions_are_watched_line_by_line() -> None:
    """A line at a time, so the address and the access code are each searched
    for on their own. Searching the block whole would miss a page that leaked
    the code without the URL above it, which is the likelier accident: a
    volunteer pasting 'the number you dial in with' into a description."""
    found = room_strings([], SERIES)

    assert "Join online: https://join.example.test/theseries" in found
    assert "Access code: 8842798" in found


def test_a_permanent_room_instance_is_not_reported_as_nothing_to_check() -> None:
    """The defect itself, on the shape it happened to: every record's
    `zoom_link` empty, the room in the configuration."""
    speakers = [
        {"id": "spk-001", "status": "scheduled", "zoom_link": ""},
        {"id": "spk-002", "status": "scheduled", "zoom_link": ""},
    ]

    assert room_strings(speakers, SERIES), (
        "an instance whose room lives in its series instructions reads as "
        "having nothing to protect -- which is what let the guard pass a "
        "build it had not looked at"
    )


def test_both_sources_are_read_together() -> None:
    found = room_strings(
        [{"zoom_link": "https://meet.example.test/j/123456789"}], SERIES
    )

    assert "https://meet.example.test/j/123456789" in found
    assert "Access code: 8842798" in found


def test_one_string_written_in_both_places_is_returned_once() -> None:
    """An operator who fills the per-event field with the series address --
    which `convener-check-config` used to invite — should not make this step
    grep the same site twice for the same text."""
    shared = "https://join.example.test/theseries"
    found = room_strings([{"zoom_link": shared}], {"instructions": shared})

    assert found.count(shared) == 1


def test_a_line_too_short_to_be_evidence_is_dropped() -> None:
    """Free text holds words. A guard that failed a build because the site
    contains the word "Dial in" is a guard somebody turns off, and then the
    real room leaks with nothing watching."""
    found = room_strings([], {"instructions": "Dial in\nAccess code: 8842798"})

    assert "Dial in" not in found
    assert "Access code: 8842798" in found
    assert all(len(one) >= MIN_SECRET_LENGTH for one in found)


def test_nothing_configured_reads_as_nothing_to_watch() -> None:
    """An instance that has set no room at all. Not a failure here: it is
    `state/dates.ts::lockBlockers` that refuses to schedule such an edition,
    and this step's job is to find leaks, not to audit configuration."""
    assert room_strings([{"zoom_link": ""}], {"instructions": ""}) == []
    assert room_strings([], {}) == []


def test_shapes_that_are_not_records_are_stepped_over() -> None:
    """`safe_load` returns whatever the file holds. A guard that raised on a
    malformed line would fail the publish with a traceback instead of a
    finding, and the fix would be to skip the step."""
    assert room_strings(
        ["not a record", None, {"zoom_link": "https://meet.example.test/j/1"}],
        "not a config",
    ) == ["https://meet.example.test/j/1"]


def test_the_result_is_sorted_so_a_diff_of_the_log_means_something() -> None:
    found = room_strings(
        [
            {"zoom_link": "https://b.example.test/room"},
            {"zoom_link": "https://a.example.test/room"},
        ],
        {},
    )

    assert found == sorted(found)
