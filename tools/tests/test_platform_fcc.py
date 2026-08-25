from __future__ import annotations

import urllib.error
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from email.message import Message
from typing import Any

import pytest

from convener_ops.platform import (
    AttendanceRow,
    EventNotFoundError,
    ManualPlatform,
    Platform,
    Recording,
    Room,
)
from convener_ops.platform_fcc import (
    RETRIEVED_TICK,
    TOKEN_ENV,
    FCCRequestError,
    PlatformFCC,
    _UrllibTransport,
    converted_recording_is_reachable,
    missing_retrieval_evidence,
    platform_from_env,
)

# ------------------------------------------------------------------ #
# Fixtures -- stand-ins for the real, undocumented endpoint
# (GET /api/v4/conferences/{id}/calls). No test in this module opens a
# socket: every response below is a Python literal shaped exactly like
# what the task 3 brief records as empirically verified, never a live
# call. `_call` mirrors the fields the brief names: custom_name, email,
# service_types, time_created_utc, time_disconnected_utc, audio_duration
# -- plus is_host, which the API also returns but AttendanceRow has no
# field for, so it is present in the fixtures (to prove it is ignored,
# not merely absent) and never read by anything under test.
# ------------------------------------------------------------------ #


def _epoch(y: int, m: int, d: int, hh: int, mm: int, ss: int = 0) -> int:
    return int(datetime(y, m, d, hh, mm, ss, tzinfo=UTC).timestamp())


def _iso(y: int, m: int, d: int, hh: int, mm: int, ss: int = 0) -> str:
    return f"{y:04d}-{m:02d}-{d:02d}T{hh:02d}:{mm:02d}:{ss:02d}Z"


def _call(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "custom_name": "Ada Lovelace",
        "email": "ada@example.org",
        "service_types": ["voip"],
        "time_created_utc": _epoch(2026, 8, 20, 18, 0, 0),
        "time_disconnected_utc": _epoch(2026, 8, 20, 19, 0, 0),
        "audio_duration": 3600,
        "is_host": False,
    }
    base.update(overrides)
    return base


#: Fixture 1 -- a person who disconnects and rejoins: two rows, same
#: address, capitalised differently between the two -- the shape verified
#: empirically against a real reconnection (phase-4-prep-notes.md, 2026-08-19
#: "a reconnection is two rows"). 12s then 157s of real audio; the reader
#: must hand back both rows, never their sum -- summing is attendance.py's
#: job (task 8/9), same boundary platform.py already draws for the manual
#: CSV path.
RECONNECTION_CALLS: list[dict[str, Any]] = [
    _call(
        custom_name="Marie Curie",
        email="marie.curie@example.org",
        time_created_utc=_epoch(2026, 8, 20, 18, 17, 40),
        time_disconnected_utc=_epoch(2026, 8, 20, 18, 18, 4),
        audio_duration=12,
    ),
    _call(
        custom_name="marie curie",
        email="marie.curie@example.org",
        time_created_utc=_epoch(2026, 8, 20, 18, 19, 28),
        time_disconnected_utc=_epoch(2026, 8, 20, 18, 22, 16),
        audio_duration=157,
    ),
]

#: Fixture 2 -- a participant who joined by telephone: `service_types`
#: is exactly `["toll"]`. `email` is `None` in the raw payload here (as the
#: real API sends it), and `custom_name` is a phone number, not a typed
#: name -- both verified in phase-4-prep-notes.md's POC call notes.
TELEPHONE_CALL: dict[str, Any] = _call(
    custom_name="+33636843236",
    email=None,
    service_types=["toll"],
    time_created_utc=_epoch(2026, 8, 20, 18, 5, 0),
    time_disconnected_utc=_epoch(2026, 8, 20, 18, 15, 0),
    audio_duration=600,
)

#: Fixture 3 -- the same person's two connections carry differently
#: capitalised names. A distinct fixture from #1 on purpose: #1 also
#: proves non-summing, this one is read only for the casing, so a future
#: reader who "fixes" #1 to summed durations still has this one standing
#: guard on casing alone.
NAME_CASING_CALLS: list[dict[str, Any]] = [
    _call(
        custom_name="grace hopper",
        email="grace@example.org",
        time_created_utc=_epoch(2026, 8, 20, 19, 0, 0),
        time_disconnected_utc=_epoch(2026, 8, 20, 19, 10, 0),
        audio_duration=600,
    ),
    _call(
        custom_name="Grace HOPPER",
        email="grace@example.org",
        time_created_utc=_epoch(2026, 8, 20, 19, 15, 0),
        time_disconnected_utc=_epoch(2026, 8, 20, 19, 20, 0),
        audio_duration=300,
    ),
]


# ------------------------------------------------------------------ #
# A fake transport -- the injection point that keeps every test off the
# network. Records what it was asked for, so a test can also assert on
# the path and the token, not only on the mapped result.
# ------------------------------------------------------------------ #


class FakeTransport:
    def __init__(
        self,
        get_responses: Mapping[str, Any] | None = None,
        get_errors: Mapping[str, Exception] | None = None,
        head_responses: Mapping[str, Mapping[str, str] | None] | None = None,
    ) -> None:
        self.get_responses = dict(get_responses or {})
        self.get_errors = dict(get_errors or {})
        self.head_responses = dict(head_responses or {})
        self.get_calls: list[tuple[str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []
        self.head_calls: list[str] = []

    def get_json(self, path: str, token: str) -> Any:
        self.get_calls.append((path, token))
        if path in self.get_errors:
            raise self.get_errors[path]
        if path not in self.get_responses:
            raise AssertionError(f"unexpected GET {path}")
        return self.get_responses[path]

    def delete(self, path: str, token: str) -> None:
        self.delete_calls.append((path, token))

    def head(self, url: str) -> Mapping[str, str] | None:
        self.head_calls.append(url)
        return self.head_responses.get(url)


def _speaker(**overrides: Any) -> dict[str, Any]:
    """A minimal loaded `data/speakers.yml` record -- only the fields
    `PlatformFCC` reads, the same minimalism `test_platform.py::_speaker`
    uses for `ManualPlatform`."""
    base: dict[str, Any] = {
        "edition_code": "MRG-901",
        "zoom_link": "https://join.freeconferencecall.com/example-room",
        "youtube_url": "",
    }
    base.update(overrides)
    return base


def _platform(
    *,
    speakers: Sequence[Mapping[str, Any]] = (),
    config: Mapping[str, Any] | None = None,
    conference_ids: Mapping[str, str] | None = None,
    transport: FakeTransport | None = None,
    access_token: str = "test-token",
) -> PlatformFCC:
    if conference_ids is None:
        conference_ids = {"mrg-901": "618515381"}
    return PlatformFCC(
        access_token=access_token,
        speakers=speakers,
        config=config,
        conference_ids=conference_ids,
        transport=transport or FakeTransport(),
    )


# ------------------------------------------------------------------ #
# Protocol conformance
# ------------------------------------------------------------------ #


def test_platform_fcc_satisfies_the_platform_protocol() -> None:
    """A caller written against `Platform` must accept `PlatformFCC`
    exactly as it already accepts `ManualPlatform` -- the whole point of
    D-05 being a `Protocol` rather than a base class."""
    assert isinstance(_platform(), Platform)


# ------------------------------------------------------------------ #
# get_attendance -- the endpoint mapping is the point of this task
# ------------------------------------------------------------------ #


def test_get_attendance_maps_the_documented_fields() -> None:
    transport = FakeTransport(get_responses={"/conferences/618515381/calls": [_call()]})
    platform = _platform(transport=transport)

    rows = platform.get_attendance("mrg-901")

    assert rows == [
        AttendanceRow(
            display_name="Ada Lovelace",
            email="ada@example.org",
            joined_at=_iso(2026, 8, 20, 18, 0, 0),
            left_at=_iso(2026, 8, 20, 19, 0, 0),
            duration_seconds=3600,
        )
    ]


def test_get_attendance_calls_the_conferences_calls_endpoint_with_the_token() -> None:
    transport = FakeTransport(get_responses={"/conferences/618515381/calls": [_call()]})
    platform = _platform(transport=transport, access_token="secret-bearer-token")

    platform.get_attendance("mrg-901")

    assert transport.get_calls == [
        ("/conferences/618515381/calls", "secret-bearer-token")
    ]


def test_a_reconnection_produces_two_separate_rows_not_a_summed_one() -> None:
    """Confirmed empirically (phase-4-prep-notes.md, 2026-08-19): a
    disconnect-and-rejoin is two rows, 12s then 157s, real presence 169s.
    Summing here would make it impossible to do correctly later -- that is
    attendance.py's job (task 8/9), not this reader's."""
    transport = FakeTransport(
        get_responses={"/conferences/618515381/calls": RECONNECTION_CALLS}
    )
    platform = _platform(transport=transport)

    rows = platform.get_attendance("mrg-901")

    assert len(rows) == 2
    assert [row.duration_seconds for row in rows] == [12, 157]
    assert sum(row.duration_seconds for row in rows) == 169
    assert {row.email for row in rows} == {"marie.curie@example.org"}


def test_name_casing_is_preserved_not_normalised_across_two_rows() -> None:
    """Confirmed empirically: capitalisation varies between two connections
    by the same person, and the address -- never the name -- is the join
    key. Normalising here would hide that fact from the matching code that
    is supposed to rely on it."""
    transport = FakeTransport(
        get_responses={"/conferences/618515381/calls": NAME_CASING_CALLS}
    )
    platform = _platform(transport=transport)

    rows = platform.get_attendance("mrg-901")

    assert [row.display_name for row in rows] == ["grace hopper", "Grace HOPPER"]
    assert rows[0].email == rows[1].email == "grace@example.org"


def test_a_telephone_joiner_has_no_email() -> None:
    """`service_types == ["toll"]` is a telephone joiner. `email` must be
    `None`, never `""` -- a caller matching on `row.email == other.email`
    must not be able to make two telephone joiners collide on an empty
    string. This is the boundary platform.py's module docstring calls "a
    boundary, not a matching weakness": a certificate is only ever
    available to someone who joins by the link."""
    transport = FakeTransport(
        get_responses={"/conferences/618515381/calls": [TELEPHONE_CALL]}
    )
    platform = _platform(transport=transport)

    rows = platform.get_attendance("mrg-901")

    assert rows[0].email is None
    assert rows[0].email != ""


def test_a_telephone_joiners_display_name_is_the_number_verbatim() -> None:
    transport = FakeTransport(
        get_responses={"/conferences/618515381/calls": [TELEPHONE_CALL]}
    )
    platform = _platform(transport=transport)

    rows = platform.get_attendance("mrg-901")

    assert rows[0].display_name == "+33636843236"


def test_a_toll_row_is_forced_to_none_even_if_the_payload_sends_an_empty_string() -> (
    None
):
    """Belt and braces: the rule is keyed on `service_types`, not on
    whatever the `email` field happens to hold. An export tool that sends
    `""` instead of `null` for a toll row must not slip an empty string
    past the boundary."""
    call = _call(
        custom_name="+15550100",
        email="",
        service_types=["toll"],
    )
    transport = FakeTransport(get_responses={"/conferences/618515381/calls": [call]})
    platform = _platform(transport=transport)

    rows = platform.get_attendance("mrg-901")

    assert rows[0].email is None


@pytest.mark.parametrize(
    ("label", "service_types"),
    [
        ("absent", None),
        ("empty", []),
        ("multi-value-with-toll", ["toll", "voip"]),
    ],
)
def test_non_exact_toll_service_types_keep_the_raw_email(
    label: str, service_types: list[str] | None
) -> None:
    """`_is_telephone_joiner` matches `service_types == ["toll"]` exactly.
    None of these three near-misses is the empirically verified telephone
    shape, so none of them forces `email` to `None` -- the raw address the
    payload sent is kept. Guards against a future "tidy-up" that widened
    the match to `"toll" in service_types`, which would pass every other
    test in this file while silently changing behaviour for someone whose
    audio fell back to the phone line while still connected some other
    way."""
    call = _call(custom_name="Ada Lovelace", email="ada@example.org")
    if service_types is None:
        del call["service_types"]
    else:
        call["service_types"] = service_types
    transport = FakeTransport(get_responses={"/conferences/618515381/calls": [call]})

    rows = _platform(transport=transport).get_attendance("mrg-901")

    assert rows[0].email == "ada@example.org", label


def test_a_call_with_a_negative_duration_is_returned_verbatim() -> None:
    """Deliberate, not an oversight: `platform.py`'s CSV path drops a
    negative `duration_seconds` because a person might mistype a minus
    sign. `audio_duration` here is computed by the provider from its own
    two timestamps, has never been observed negative, and if it ever were,
    that would be a fact about the response worth seeing, not a typo to
    quietly correct. This reader builds no second per-row issue-reporting
    mechanism for API data -- see the module docstring -- so an anomalous
    value is returned exactly as received."""
    call = _call(audio_duration=-5)
    transport = FakeTransport(get_responses={"/conferences/618515381/calls": [call]})

    rows = _platform(transport=transport).get_attendance("mrg-901")

    assert rows[0].duration_seconds == -5


def test_get_attendance_raises_when_the_event_has_no_recorded_conference() -> None:
    platform = _platform(speakers=[_speaker(edition_code="MRG-901")], conference_ids={})
    with pytest.raises(EventNotFoundError, match="mrg-901"):
        platform.get_attendance("mrg-901")


def test_get_attendance_raises_a_platform_error_on_a_non_2xx_response() -> None:
    transport = FakeTransport(
        get_errors={
            "/conferences/618515381/calls": FCCRequestError(
                "GET /conferences/618515381/calls returned HTTP 401"
            )
        }
    )
    with pytest.raises(FCCRequestError, match="401"):
        _platform(transport=transport).get_attendance("mrg-901")


def test_get_attendance_raises_when_the_response_shape_is_not_a_list() -> None:
    """The endpoint is not documented by the vendor (task 3 brief) -- it
    answers, verified, but nothing guarantees the shape stays a bare JSON
    array. A response this module cannot recognise must fail loudly, never
    silently return no rows, which would read as "nobody attended"."""
    transport = FakeTransport(
        get_responses={"/conferences/618515381/calls": {"unexpected": "shape"}}
    )
    with pytest.raises(FCCRequestError):
        _platform(transport=transport).get_attendance("mrg-901")


def test_get_attendance_raises_when_the_payload_is_neither_list_nor_mapping() -> None:
    transport = FakeTransport(get_responses={"/conferences/618515381/calls": "oops"})
    with pytest.raises(FCCRequestError):
        _platform(transport=transport).get_attendance("mrg-901")


def test_a_call_with_a_non_numeric_timestamp_falls_back_to_the_epoch() -> None:
    """API data, not a hand-edited file -- so this reader does not build a
    per-row issue-reporting mechanism the way `platform.py`'s CSV path
    does. A malformed timestamp still produces a row rather than raising,
    tolerant in the same spirit `notify.py` is tolerant of malformed
    input for an unattended job."""
    call = _call(time_created_utc="not-a-number", time_disconnected_utc=None)
    transport = FakeTransport(get_responses={"/conferences/618515381/calls": [call]})

    rows = _platform(transport=transport).get_attendance("mrg-901")

    assert rows[0].joined_at == _iso(1970, 1, 1, 0, 0, 0)
    assert rows[0].left_at == _iso(1970, 1, 1, 0, 0, 0)


def test_a_call_with_a_non_numeric_duration_falls_back_to_zero() -> None:
    call = _call(audio_duration="not-a-number")
    transport = FakeTransport(get_responses={"/conferences/618515381/calls": [call]})

    rows = _platform(transport=transport).get_attendance("mrg-901")

    assert rows[0].duration_seconds == 0


def test_get_attendance_accepts_a_data_wrapped_response() -> None:
    """Defensive only -- never verified against the real endpoint, unlike
    the bare-list shape the fixtures above use. Documented in the module
    docstring as the one thing in this file that is not empirically
    confirmed."""
    transport = FakeTransport(
        get_responses={"/conferences/618515381/calls": {"data": [_call()]}}
    )
    rows = _platform(transport=transport).get_attendance("mrg-901")
    assert len(rows) == 1


# ------------------------------------------------------------------ #
# get_room -- D-06: the account is the permanent room, so this reads the
# same two sources ManualPlatform does, not the API. No fixture needed:
# nothing here touches transport.
# ------------------------------------------------------------------ #


def test_get_room_reads_the_join_url_from_the_matching_speaker_record() -> None:
    speakers = [_speaker(edition_code="MRG-901", zoom_link="https://example.org/room")]
    platform = _platform(speakers=speakers)

    room = platform.get_room("mrg-901")

    assert room == Room(join_url="https://example.org/room", instructions="")


def test_get_room_reads_instructions_from_config_not_the_speaker_record() -> None:
    speakers = [_speaker(edition_code="MRG-901")]
    config = {"instructions": "Dial +1 555 0100 if the link fails."}
    platform = _platform(speakers=speakers, config=config)

    room = platform.get_room("mrg-901")

    assert room.instructions == "Dial +1 555 0100 if the link fails."


def test_get_room_never_calls_the_transport() -> None:
    transport = FakeTransport()
    speakers = [_speaker(edition_code="MRG-901")]
    _platform(speakers=speakers, transport=transport).get_room("mrg-901")

    assert transport.get_calls == []


def test_get_room_raises_when_no_speaker_record_matches_the_event() -> None:
    with pytest.raises(EventNotFoundError, match="mrg-903"):
        _platform(conference_ids={"mrg-903": "1"}).get_room("mrg-903")


# ------------------------------------------------------------------ #
# get_recording / delete_recording -- the raw primitives task 10 builds
# its retrieve-then-delete safety on top of. This module reports what the
# provider says and performs the deletion it is asked to perform; deciding
# *when* it is safe to call delete_recording is the caller's job, exactly
# as it already is for ManualPlatform.delete_recording.
# ------------------------------------------------------------------ #


def test_get_recording_reports_the_real_size_when_available() -> None:
    transport = FakeTransport(
        get_responses={
            "/conferences/618515381": {
                "recording_url": "https://cdn.example.org/rec/618515381",
                "file_size": 1_645_000_000,
                "is_recorded": True,
                "deleted": False,
            }
        }
    )
    platform = _platform(transport=transport)

    recording = platform.get_recording("mrg-901")

    assert recording == Recording(
        url="https://cdn.example.org/rec/618515381",
        size=1_645_000_000,
        available=True,
    )


def test_get_recording_is_unavailable_once_deleted() -> None:
    """Verified empirically: after `DELETE /conferences/{id}`, `file_size`
    drops to 0 and `deleted` flips to true, but every `/calls` row survives
    -- deleting the recording never loses attendance."""
    transport = FakeTransport(
        get_responses={
            "/conferences/618515381": {
                "recording_url": "https://cdn.example.org/rec/618515381",
                "file_size": 0,
                "is_recorded": True,
                "deleted": True,
            }
        }
    )
    platform = _platform(transport=transport)

    recording = platform.get_recording("mrg-901")

    assert recording.available is False
    assert recording.size == 0


def test_get_recording_is_unavailable_when_never_recorded() -> None:
    transport = FakeTransport(
        get_responses={
            "/conferences/618515381": {
                "recording_url": "",
                "file_size": 0,
                "is_recorded": False,
                "deleted": False,
            }
        }
    )
    platform = _platform(transport=transport)

    recording = platform.get_recording("mrg-901")

    assert recording == Recording(url="", size=0, available=False)


def test_get_recording_raises_when_the_response_shape_is_not_a_mapping() -> None:
    transport = FakeTransport(get_responses={"/conferences/618515381": ["oops"]})
    with pytest.raises(FCCRequestError):
        _platform(transport=transport).get_recording("mrg-901")


def test_get_recording_treats_a_non_numeric_file_size_as_zero() -> None:
    transport = FakeTransport(
        get_responses={
            "/conferences/618515381": {
                "recording_url": "https://cdn.example.org/rec/618515381",
                "file_size": "not-a-number",
                "is_recorded": True,
                "deleted": False,
            }
        }
    )
    platform = _platform(transport=transport)

    recording = platform.get_recording("mrg-901")

    assert recording.available is True
    assert recording.size == 0


def test_delete_recording_calls_the_delete_endpoint_with_the_token() -> None:
    transport = FakeTransport()
    platform = _platform(transport=transport, access_token="secret-bearer-token")

    platform.delete_recording("mrg-901")

    assert transport.delete_calls == [("/conferences/618515381", "secret-bearer-token")]


def test_delete_recording_raises_when_the_event_has_no_recorded_conference() -> None:
    platform = _platform(speakers=[_speaker(edition_code="MRG-901")], conference_ids={})
    with pytest.raises(EventNotFoundError, match="mrg-901"):
        platform.delete_recording("mrg-901")


def test_get_recording_raises_when_the_event_has_no_recorded_conference() -> None:
    """Cheap to pin even though it walks the same `_conference_id` path
    `get_attendance` and `delete_recording` already exercise: a reader
    checking `get_recording` alone should not have to trust that the third
    caller of a shared helper behaves like the first two."""
    platform = _platform(speakers=[_speaker(edition_code="MRG-901")], conference_ids={})
    with pytest.raises(EventNotFoundError, match="mrg-901"):
        platform.get_recording("mrg-901")


# ------------------------------------------------------------------ #
# _conference_id -- digits-only validation (fix round 1, Important 2).
# `conference_ids` has no production populator; its one caller
# (cli.py::release_recording) reads an operator-typed value, and this is
# where it is validated before it can reach a URL this module builds.
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    "bad_id",
    [
        "618/../999",
        "THIS-IS-THE-WRONG-CONFERENCE",
        "618515381 ",
        "-618515381",
        "",
    ],
)
def test_conference_id_must_be_digits_only(bad_id: str) -> None:
    transport = FakeTransport()
    platform = _platform(transport=transport, conference_ids={"mrg-901": bad_id})

    with pytest.raises(ValueError, match="not a valid FCC conference id"):
        platform.get_recording("mrg-901")

    assert transport.get_calls == []


def test_a_path_traversal_shaped_conference_id_never_reaches_delete() -> None:
    """The reviewer's own probe, round 1, Important 2: a hand-typed
    conference id shaped like a path-traversal payload must be refused
    before it can reach `DELETE /conferences/{id}`."""
    transport = FakeTransport()
    platform = _platform(transport=transport, conference_ids={"mrg-901": "618/../999"})

    with pytest.raises(ValueError, match="not a valid FCC conference id"):
        platform.delete_recording("mrg-901")

    assert transport.delete_calls == []


def test_a_valid_digits_only_conference_id_is_accepted() -> None:
    transport = FakeTransport()
    platform = _platform(transport=transport, conference_ids={"mrg-901": "618515381"})

    platform.delete_recording("mrg-901")

    assert transport.delete_calls == [("/conferences/618515381", "test-token")]


# ------------------------------------------------------------------ #
# converted_recording_is_reachable / missing_retrieval_evidence -- task
# 10's whole answer to "what does verified retrieval mean". Two
# independent, host-driven traces: a `runbook_progress` tick
# (`RETRIEVED_TICK`), and a successful open of the converted recording at
# the provider, checked against `video/mp4` + `Accept-Ranges: bytes`, not
# a bare 2xx status (fix round 1, Important 3). Neither function here ever
# calls get_recording or delete_recording itself -- the caller
# (cli.py::release_recording) already holds `recording` from its own
# earlier call, and decides what to do with the result.
# ------------------------------------------------------------------ #

_VIDEO_URL = "https://cdn.example.org/rec/618515381.video.mp4"


def _video_headers(*, content_length: int = 900_000_000) -> dict[str, str]:
    return {
        "content_type": "video/mp4",
        "accept_ranges": "bytes",
        "content_length": str(content_length),
    }


def test_converted_recording_is_reachable_when_the_transport_confirms_it() -> None:
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport(head_responses={_VIDEO_URL: _video_headers()})

    assert converted_recording_is_reachable(recording, transport) is True


def test_converted_recording_is_reachable_checks_the_video_mp4_suffix() -> None:
    """Verified empirically (phase-4-prep-notes.md, 2026-08-19): the
    pattern is `recording_url + ".video.mp4"`, not `.mp4` alone."""
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport()

    converted_recording_is_reachable(recording, transport)

    assert transport.head_calls == [_VIDEO_URL]


def test_converted_recording_is_reachable_is_false_when_the_transport_denies_it() -> (
    None
):
    """An untouched recording's `.video.mp4` answers 404 -- verified
    empirically. The host has not clicked Download yet."""
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport(head_responses={})

    assert converted_recording_is_reachable(recording, transport) is False


def test_converted_recording_is_reachable_is_false_with_no_recording_url() -> None:
    """Nothing to check when the provider never reported a `recording_url`
    at all -- there is no converted artefact that could be reachable."""
    recording = Recording(url="", size=0, available=False)
    transport = FakeTransport()

    assert converted_recording_is_reachable(recording, transport) is False
    assert transport.head_calls == []


def test_converted_recording_is_reachable_is_false_for_a_200_html_error_page() -> None:
    """Reviewer probe, round 1, Important 3: a bare 2xx status is not
    proof of conversion. `urlopen` follows redirects transparently, so a
    CDN answering an absent object with its own 200 error page must not
    pass -- only a real `video/mp4` response does."""
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport(
        head_responses={_VIDEO_URL: {"content_type": "text/html; charset=utf-8"}}
    )

    assert converted_recording_is_reachable(recording, transport) is False


def test_converted_recording_is_reachable_is_false_without_accept_ranges() -> None:
    """The prep notes record both `video/mp4` and `Accept-Ranges: bytes`
    for a genuine converted file -- both are required, not just the
    content type."""
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport(
        head_responses={_VIDEO_URL: {"content_type": "video/mp4"}}
    )

    assert converted_recording_is_reachable(recording, transport) is False


def test_converted_recording_is_reachable_is_false_with_a_zero_content_length() -> None:
    """`content_length` is free from the same `HEAD`; a `0` means an
    empty body behind headers that otherwise look right, and is rejected
    the same way a missing header would be."""
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport(
        head_responses={_VIDEO_URL: _video_headers(content_length=0)}
    )

    assert converted_recording_is_reachable(recording, transport) is False


def test_converted_recording_is_reachable_ignores_a_content_type_parameter() -> None:
    """A `;`-separated parameter (e.g. a charset a CDN adds) must not
    defeat the exact `video/mp4` match."""
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport(
        head_responses={
            _VIDEO_URL: {
                "content_type": "video/mp4; charset=binary",
                "accept_ranges": "bytes",
            }
        }
    )

    assert converted_recording_is_reachable(recording, transport) is True


def test_converted_recording_is_reachable_is_false_with_a_bad_content_length() -> None:
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport(
        head_responses={
            _VIDEO_URL: {
                "content_type": "video/mp4",
                "accept_ranges": "bytes",
                "content_length": "not-a-number",
            }
        }
    )

    assert converted_recording_is_reachable(recording, transport) is False


def test_missing_retrieval_evidence_is_empty_when_both_traces_agree() -> None:
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport(head_responses={_VIDEO_URL: _video_headers()})
    platform = _platform(transport=transport)

    problems = missing_retrieval_evidence(platform, recording, {RETRIEVED_TICK: True})

    assert problems == []


def test_missing_retrieval_evidence_names_a_missing_tick() -> None:
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport(head_responses={_VIDEO_URL: _video_headers()})
    platform = _platform(transport=transport)

    problems = missing_retrieval_evidence(platform, recording, {})

    assert len(problems) == 1
    assert RETRIEVED_TICK in problems[0]


def test_missing_retrieval_evidence_ignores_youtube_url() -> None:
    """The concrete Important 4 fix, pinned at the unit level: this
    function no longer takes or reads `youtube_url` at all -- only the
    runbook tick and the provider's own confirmation. A caller with
    `youtube_url` set but no tick is still refused; a caller with no
    `youtube_url` but a tick set is still accepted."""
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport(head_responses={_VIDEO_URL: _video_headers()})
    platform = _platform(transport=transport)

    assert missing_retrieval_evidence(platform, recording, {RETRIEVED_TICK: True}) == []


def test_missing_retrieval_evidence_names_an_unreached_conversion() -> None:
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    platform = _platform(transport=FakeTransport())

    problems = missing_retrieval_evidence(platform, recording, {RETRIEVED_TICK: True})

    assert len(problems) == 1
    assert "converted recording" in problems[0]


def test_missing_retrieval_evidence_names_both_when_neither_trace_agrees() -> None:
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    platform = _platform(transport=FakeTransport())

    problems = missing_retrieval_evidence(platform, recording, {})

    assert len(problems) == 2


def test_missing_retrieval_evidence_never_calls_get_json_or_delete() -> None:
    """The whole point of this function: it only reads what the caller
    already holds (`recording`, `runbook_progress`) and the transport's
    existence check -- it never itself asks the platform for anything, and
    it never deletes anything."""
    recording = Recording(
        url="https://cdn.example.org/rec/618515381", size=900_000_000, available=True
    )
    transport = FakeTransport(head_responses={_VIDEO_URL: _video_headers()})
    platform = _platform(transport=transport)

    missing_retrieval_evidence(platform, recording, {RETRIEVED_TICK: True})

    assert transport.get_calls == []
    assert transport.delete_calls == []


# ------------------------------------------------------------------ #
# _UrllibTransport -- the real HTTP implementation. Still no socket: every
# test below substitutes `urllib.request.urlopen` itself via monkeypatch,
# the same technique that keeps the rest of this suite off the network,
# extended to the one class the rest of the suite never constructs.
# ------------------------------------------------------------------ #


class _FakeHTTPResponse:
    def __init__(
        self,
        body: bytes,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._body = body
        self.status = status
        self.headers: Mapping[str, str] = headers if headers is not None else {}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def test_urllib_transport_sends_bearer_auth_and_accept_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["authorization"] = request.get_header("Authorization")
        captured["accept"] = request.get_header("Accept")
        return _FakeHTTPResponse(b'{"ok": true}')

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    result = _UrllibTransport().get_json("/conferences/1/calls", "tok123")

    assert result == {"ok": True}
    expected_url = "https://www.freeconferencecall.com/api/v4/conferences/1/calls"
    assert captured["url"] == expected_url
    assert captured["method"] == "GET"
    assert captured["authorization"] == "Bearer tok123"
    assert captured["accept"] == "application/json"


def test_urllib_transport_delete_uses_the_delete_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        captured["method"] = request.get_method()
        captured["authorization"] = request.get_header("Authorization")
        return _FakeHTTPResponse(b"")

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    _UrllibTransport().delete("/conferences/1", "tok123")

    assert captured["method"] == "DELETE"
    assert captured["authorization"] == "Bearer tok123"


def test_urllib_transport_maps_an_http_error_to_fcc_request_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", Message(), None
        )

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(FCCRequestError, match="401"):
        _UrllibTransport().get_json("/conferences/1/calls", "tok")


def test_urllib_transport_maps_a_url_error_to_fcc_request_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(FCCRequestError, match="failed"):
        _UrllibTransport().get_json("/conferences/1/calls", "tok")


def test_urllib_transport_maps_invalid_json_to_fcc_request_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(b"not json")

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(FCCRequestError, match="valid JSON"):
        _UrllibTransport().get_json("/conferences/1/calls", "tok")


# ------------------------------------------------------------------ #
# _UrllibTransport.head -- task 10's HEAD check. No socket, and no
# Authorization header (the recording's own media URLs need none,
# verified empirically): a caller must not send the bearer token to an
# address it did not build from base_url itself.
# ------------------------------------------------------------------ #


def test_urllib_transport_head_sends_a_head_request_with_no_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["authorization"] = request.get_header("Authorization")
        return _FakeHTTPResponse(
            b"",
            status=200,
            headers={
                "Content-Type": "video/mp4",
                "Accept-Ranges": "bytes",
                "Content-Length": "900000000",
            },
        )

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    result = _UrllibTransport().head("https://cdn.example.org/rec/1.video.mp4")

    assert result == {
        "content_type": "video/mp4",
        "accept_ranges": "bytes",
        "content_length": "900000000",
    }
    assert captured["url"] == "https://cdn.example.org/rec/1.video.mp4"
    assert captured["method"] == "HEAD"
    assert captured["authorization"] is None


def test_urllib_transport_head_reads_no_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point: never download any part of the recording."""

    class _ExplodingBodyResponse(_FakeHTTPResponse):
        def read(self) -> bytes:
            raise AssertionError("head() must never read a response body")

    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        return _ExplodingBodyResponse(b"", status=200, headers={})

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    result = _UrllibTransport().head("https://cdn.example.org/rec/1.video.mp4")

    assert result == {}


def test_urllib_transport_head_omits_a_header_the_response_never_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(b"", status=200, headers={"Content-Type": "video/mp4"})

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    result = _UrllibTransport().head("https://cdn.example.org/rec/1.video.mp4")

    assert result == {"content_type": "video/mp4"}
    assert "accept_ranges" not in (result or {})


def test_urllib_transport_head_is_none_on_a_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verified empirically: an untouched recording's `.video.mp4`
    answers 404."""

    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        raise urllib.error.HTTPError(
            request.full_url, 404, "Not Found", Message(), None
        )

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    assert _UrllibTransport().head("https://cdn.example.org/rec/1.video.mp4") is None


def test_urllib_transport_head_is_none_on_a_non_2xx_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`urlopen` itself only raises `HTTPError` for a non-2xx status in
    the common case, but this must not assume that -- a response object
    reporting a non-2xx `status` directly is handled the same way."""

    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(b"", status=500, headers={})

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    assert _UrllibTransport().head("https://cdn.example.org/rec/1.video.mp4") is None


def test_urllib_transport_head_is_none_on_a_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    assert _UrllibTransport().head("https://cdn.example.org/rec/1.video.mp4") is None


def test_urllib_transport_head_is_none_on_a_bad_status_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix round 1, minor 2: `http.client.BadStatusLine` is not an
    `OSError` and previously propagated as an uncaught traceback instead
    of reading as `None` -- reproduced by the reviewer, fixed by widening
    the caught exceptions to `http.client.HTTPException`."""
    import http.client

    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        raise http.client.BadStatusLine("garbage status line")

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    assert _UrllibTransport().head("https://cdn.example.org/rec/1.video.mp4") is None


def test_urllib_transport_head_is_none_on_a_malformed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix round 1, minor 2: `Request(...)` construction now lives inside
    the same `try` as the request itself, so a `ValueError` it raises
    (a malformed URL) reads as `None` too, never propagates."""

    def fake_request(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("malformed URL")

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.Request", fake_request)

    assert _UrllibTransport().head("https://cdn.example.org/rec/1.video.mp4") is None


def test_urllib_transport_head_is_none_and_never_opens_a_non_https_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        raise AssertionError("a non-https URL must never be opened")

    monkeypatch.setattr("convener_ops.platform_fcc.urllib.request.urlopen", fake_urlopen)

    assert _UrllibTransport().head("http://cdn.example.org/rec/1.video.mp4") is None


# ------------------------------------------------------------------ #
# platform_from_env -- D-13: an absent account is the ordinary case, and
# the manual implementation keeps the whole chain working by the other
# path. This is the fallback the task 3 brief's commit message names.
# ------------------------------------------------------------------ #


def test_platform_from_env_returns_the_manual_implementation_when_absent() -> None:
    platform = platform_from_env({})
    assert isinstance(platform, ManualPlatform)


def test_platform_from_env_treats_a_blank_token_as_absent() -> None:
    """The same "empty string counts as unset" rule `resolve_states`
    already applies to every other secret in this project."""
    platform = platform_from_env({TOKEN_ENV: "   "})
    assert isinstance(platform, ManualPlatform)


def test_platform_from_env_returns_platform_fcc_when_the_token_is_set() -> None:
    platform = platform_from_env({TOKEN_ENV: "a-real-token"})
    assert isinstance(platform, PlatformFCC)
    assert platform.access_token == "a-real-token"


def test_platform_from_env_forwards_speakers_and_config_either_way() -> None:
    speakers = [_speaker(edition_code="MRG-1")]
    config = {"instructions": "note"}

    manual = platform_from_env({}, speakers=speakers, config=config)
    fcc = platform_from_env({TOKEN_ENV: "tok"}, speakers=speakers, config=config)

    assert isinstance(manual, ManualPlatform)
    assert manual.speakers == speakers
    assert manual.config == config
    assert isinstance(fcc, PlatformFCC)
    assert fcc.speakers == speakers
    assert fcc.config == config


def test_platform_from_env_forwards_private_pem_to_the_manual_implementation() -> None:
    """Task 17: `ManualPlatform.get_attendance` needs an event's private
    key to read a committed, encrypted attendance export -- `cli.py`'s
    callers already hold it (the same key that decrypts
    `registrations.enc`), and `platform_from_env` is the one seam that
    hands it to `ManualPlatform` without either side reading it directly."""
    manual = platform_from_env({}, private_pem="a-pem-string")
    assert isinstance(manual, ManualPlatform)
    assert manual.private_pem == "a-pem-string"


def test_platform_from_env_does_not_pass_private_pem_to_platform_fcc() -> None:
    """`PlatformFCC` reads attendance from the provider's own API and never
    touches a committed export, so it has no `private_pem` field to
    receive -- forwarding it there would be a `TypeError` waiting to
    happen, not silently accepted."""
    fcc = platform_from_env({TOKEN_ENV: "tok"}, private_pem="a-pem-string")
    assert isinstance(fcc, PlatformFCC)
    assert not hasattr(fcc, "private_pem")


def test_platform_from_env_forwards_conference_ids() -> None:
    platform = platform_from_env(
        {TOKEN_ENV: "tok"}, conference_ids={"mrg-901": "618515381"}
    )
    assert isinstance(platform, PlatformFCC)
    assert platform.conference_ids == {"mrg-901": "618515381"}


# ------------------------------------------------------------------ #
# The token secret name matches config/integrations.yml -- guards
# against the declaration and the code drifting apart.
# ------------------------------------------------------------------ #


def test_token_env_matches_the_declared_integration_secret() -> None:
    from convener_ops.integrations import load_declaration
    from convener_ops.paths import repo_root

    declaration = load_declaration(repo_root() / "config" / "integrations.yml")
    meeting_provider = next(i for i in declaration if i.name == "meeting_provider")
    assert meeting_provider.secrets == [TOKEN_ENV]


# ------------------------------------------------------------------ #
# D-14: RETRIEVED_TICK is the one runbook_progress key both Python and
# the app agree on by name (task 17 wires phases.ts's own key against
# this same fixture -- see tools/tests/fixtures/event-chain-keys.json's
# own comment for why a drift here is worse than most).
# ------------------------------------------------------------------ #


def test_retrieved_tick_matches_the_shared_fixture() -> None:
    import json
    from pathlib import Path

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "event-chain-keys.json").read_text(
            encoding="utf-8"
        )
    )
    assert fixture["retrieved_tick_key"] == RETRIEVED_TICK
