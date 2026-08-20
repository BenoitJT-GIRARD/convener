from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from convener_ops.platform import (
    AttendanceImportError,
    AttendanceIssue,
    AttendanceRow,
    EventNotFoundError,
    ManualPlatform,
    Platform,
    Recording,
    find_speaker,
    parse_attendance_csv,
)

CSV_HEADER = "display_name,email,joined_at,left_at,duration_seconds"


def _write_csv(path: Path, *rows: str) -> None:
    path.write_text("\n".join((CSV_HEADER, *rows)) + "\n", encoding="utf-8")


def _speaker(**overrides: Any) -> dict[str, Any]:
    """A minimal loaded `data/speakers.yml` record -- only the two fields
    `ManualPlatform` reads. Real records carry far more; this class never
    looks at the rest, the same way `public_data.py` only ever reads the
    fields its own allowlist names."""
    base: dict[str, Any] = {
        "edition_code": "MRG-901",
        "zoom_link": "https://meet.example.org/permanent-room",
        "youtube_url": "",
    }
    base.update(overrides)
    return base


def _platform(
    tmp_path: Path,
    speakers: Sequence[Mapping[str, Any]] = (),
    config: Mapping[str, Any] | None = None,
) -> ManualPlatform:
    return ManualPlatform(
        events_dir=tmp_path / "events", speakers=speakers, config=config
    )


# ------------------------------------------------------------------ #
# Protocol conformance
# ------------------------------------------------------------------ #


def test_manual_platform_satisfies_the_platform_protocol(tmp_path: Path) -> None:
    """`ManualPlatform` is not a stopgap: a caller written against the
    `Platform` interface must accept it without an isinstance check ever
    failing, exactly as it will later accept task 3's platform_fcc.py."""
    assert isinstance(_platform(tmp_path), Platform)


# ------------------------------------------------------------------ #
# find_speaker -- R-5: event_id is edition_code, lower-cased
# ------------------------------------------------------------------ #


def test_find_speaker_matches_the_lower_cased_edition_code() -> None:
    record = _speaker(edition_code="MRG-1")
    assert find_speaker([record], "mrg-1") is record


def test_find_speaker_raises_naming_the_id_when_nothing_matches() -> None:
    with pytest.raises(EventNotFoundError, match="mrg-2"):
        find_speaker([_speaker(edition_code="MRG-1")], "mrg-2")


def test_find_speaker_does_not_match_on_case_alone(tmp_path: Path) -> None:
    """`event_id` is expected to already be lower-case -- this is not a
    case-insensitive search in the other direction. An `event_id` that is
    not already lower-case is simply an id nothing matches, same as any
    other wrong id."""
    with pytest.raises(EventNotFoundError):
        find_speaker([_speaker(edition_code="MRG-1")], "MRG-1")


def test_find_speaker_ignores_a_record_with_no_edition_code() -> None:
    unscheduled = _speaker(edition_code="")
    scheduled = _speaker(edition_code="MRG-1")
    assert find_speaker([unscheduled, scheduled], "mrg-1") is scheduled


# ------------------------------------------------------------------ #
# get_room -- the room comes from the speaker record, instructions from
# data/config.yml (R-5, R-6)
# ------------------------------------------------------------------ #


def test_get_room_reads_the_join_url_from_the_matching_speaker_record(
    tmp_path: Path,
) -> None:
    speakers = [
        _speaker(
            edition_code="MRG-901",
            zoom_link="https://meet.example.org/permanent-room",
        )
    ]

    room = _platform(tmp_path, speakers=speakers).get_room("mrg-901")

    assert room.join_url == "https://meet.example.org/permanent-room"


def test_get_room_reads_instructions_from_config_not_the_speaker_record(
    tmp_path: Path,
) -> None:
    """R-6: D-06 makes the account itself the permanent room, so join
    instructions describe a room that never changes -- a property of the
    series (`data/config.yml`), not of one event."""
    speakers = [_speaker(edition_code="MRG-901")]
    config = {"instructions": "Dial +1 555 0100 if the link fails."}

    room = _platform(tmp_path, speakers=speakers, config=config).get_room("mrg-901")

    assert room.instructions == "Dial +1 555 0100 if the link fails."


def test_get_room_with_no_config_supplied_has_no_instructions(
    tmp_path: Path,
) -> None:
    """No `config` supplied is not a data-integrity failure -- it reads as
    the same 'nothing more to say' an explicit empty string would."""
    speakers = [_speaker(edition_code="MRG-901")]

    room = _platform(tmp_path, speakers=speakers).get_room("mrg-901")

    assert room.instructions == ""


def test_get_room_treats_a_missing_instructions_key_as_empty_string(
    tmp_path: Path,
) -> None:
    speakers = [_speaker(edition_code="MRG-901")]

    room = _platform(tmp_path, speakers=speakers, config={}).get_room("mrg-901")

    assert room.instructions == ""


def test_get_room_raises_when_no_speaker_record_matches_the_event(
    tmp_path: Path,
) -> None:
    with pytest.raises(EventNotFoundError, match="mrg-903"):
        _platform(tmp_path).get_room("mrg-903")


def test_get_room_the_same_instructions_apply_to_every_event(tmp_path: Path) -> None:
    """The point of R-6, made concrete: two different events, one config,
    the same instructions -- because it is the same room."""
    speakers = [
        _speaker(edition_code="MRG-901", zoom_link="https://meet.example.org/room"),
        _speaker(edition_code="MRG-902", zoom_link="https://meet.example.org/room"),
    ]
    config = {"instructions": "Dial +1 555 0100 if the link fails."}
    platform = _platform(tmp_path, speakers=speakers, config=config)

    first = platform.get_room("mrg-901")
    second = platform.get_room("mrg-902")

    expected = "Dial +1 555 0100 if the link fails."
    assert first.instructions == second.instructions == expected
    assert first.join_url == second.join_url


# ------------------------------------------------------------------ #
# event id validation -- checked before any filesystem access
# ------------------------------------------------------------------ #


@pytest.mark.parametrize("bad_id", ["../secret", "a/b", "", ".hidden"])
def test_an_invalid_event_id_is_refused_before_touching_the_filesystem(
    tmp_path: Path, bad_id: str
) -> None:
    events_dir = tmp_path / "events"
    with pytest.raises(ValueError):
        _platform(tmp_path).get_attendance(bad_id)
    # No directory was created or read as a side effect of the attempt.
    assert not events_dir.exists()


def test_get_room_also_validates_the_event_id_first(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _platform(tmp_path).get_room("../secret")


# ------------------------------------------------------------------ #
# get_attendance -- the email boundary is the point of this task
# ------------------------------------------------------------------ #


def test_get_attendance_reads_the_csv_rows(tmp_path: Path) -> None:
    event_dir = tmp_path / "events" / "mrg-910"
    event_dir.mkdir(parents=True)
    _write_csv(
        event_dir / "attendance-import.csv",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )

    rows = _platform(tmp_path).get_attendance("mrg-910")

    assert rows == [
        AttendanceRow(
            display_name="Ada Lovelace",
            email="ada@example.org",
            joined_at="2026-08-20T18:00:00Z",
            left_at="2026-08-20T19:30:00Z",
            duration_seconds=5400,
        )
    ]


def test_a_participant_who_joins_by_telephone_has_no_email(tmp_path: Path) -> None:
    """The boundary the revalidation wrote into 5: a telephone joiner has no
    address, the platform never collects one, and no matching cascade can
    ever reach them. `email` must be `None`, never `''` -- a caller that
    matches on `row.email == other.email` must not be able to make two
    telephone joiners collide on an empty string."""
    event_dir = tmp_path / "events" / "mrg-911"
    event_dir.mkdir(parents=True)
    _write_csv(
        event_dir / "attendance-import.csv",
        "Grace Hopper,,2026-08-20T18:05:00Z,2026-08-20T19:00:00Z,3300",
    )

    rows = _platform(tmp_path).get_attendance("mrg-911")

    assert rows[0].email is None


def test_email_is_never_an_empty_string(tmp_path: Path) -> None:
    event_dir = tmp_path / "events" / "mrg-912"
    event_dir.mkdir(parents=True)
    _write_csv(
        event_dir / "attendance-import.csv",
        "Phone Joiner,   ,2026-08-20T18:00:00Z,2026-08-20T18:30:00Z,1800",
    )

    rows = _platform(tmp_path).get_attendance("mrg-912")

    assert rows[0].email is None
    assert rows[0].email != ""


def test_a_reconnection_produces_two_separate_rows_not_a_summed_one(
    tmp_path: Path,
) -> None:
    """Confirmed empirically against the real platform (task 3's brief): a
    disconnect-and-rejoin produces several rows for the same person, summed
    downstream. Summing here would make that impossible to do correctly
    later -- it belongs to attendance.py, not to the platform reader."""
    event_dir = tmp_path / "events" / "mrg-913"
    event_dir.mkdir(parents=True)
    _write_csv(
        event_dir / "attendance-import.csv",
        "Marie Curie,marie@example.org,2026-08-20T18:00:00Z,2026-08-20T18:20:00Z,1200",
        "marie curie,marie@example.org,2026-08-20T18:25:00Z,2026-08-20T19:30:00Z,3900",
    )

    rows = _platform(tmp_path).get_attendance("mrg-913")

    assert len(rows) == 2
    assert sum(row.duration_seconds for row in rows) == 5100


def test_name_casing_is_preserved_not_normalised(tmp_path: Path) -> None:
    """Confirmed empirically: capitalisation varies between two connections
    by the same person, and the address -- never the name -- is the join
    key. Normalising here would hide that fact from the matching code that
    is supposed to rely on it."""
    event_dir = tmp_path / "events" / "mrg-914"
    event_dir.mkdir(parents=True)
    _write_csv(
        event_dir / "attendance-import.csv",
        "marie curie,marie@example.org,2026-08-20T18:00:00Z,2026-08-20T18:20:00Z,1200",
    )

    rows = _platform(tmp_path).get_attendance("mrg-914")

    assert rows[0].display_name == "marie curie"


def test_missing_attendance_file_raises_and_names_the_event(tmp_path: Path) -> None:
    with pytest.raises(AttendanceImportError, match="mrg-915"):
        _platform(tmp_path).get_attendance("mrg-915")


def test_missing_column_raises_and_names_it(tmp_path: Path) -> None:
    event_dir = tmp_path / "events" / "mrg-916"
    event_dir.mkdir(parents=True)
    (event_dir / "attendance-import.csv").write_text(
        "display_name,email,joined_at,left_at\n"
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:00:00Z\n",
        encoding="utf-8",
    )

    with pytest.raises(AttendanceImportError) as excinfo:
        _platform(tmp_path).get_attendance("mrg-916")

    assert "duration_seconds" in str(excinfo.value)


def test_missing_column_is_a_whole_file_failure_not_reported_per_row(
    tmp_path: Path,
) -> None:
    event_dir = tmp_path / "events" / "mrg-917"
    event_dir.mkdir(parents=True)
    (event_dir / "attendance-import.csv").write_text(
        "display_name,joined_at,left_at,duration_seconds\n"
        "Ada Lovelace,2026-08-20T18:00:00Z,2026-08-20T19:00:00Z,3600\n",
        encoding="utf-8",
    )

    with pytest.raises(AttendanceImportError, match="email"):
        _platform(tmp_path).get_attendance("mrg-917")


def test_duplicate_column_names_are_refused_not_silently_collapsed() -> None:
    """`csv.DictReader` keeps only the last `email` column's value, and a
    plain `set(fieldnames)` would collapse the duplicate before the
    missing-column check ever saw it -- checked explicitly, named like a
    missing column would be."""
    with pytest.raises(AttendanceImportError, match="email"):
        parse_attendance_csv(
            "display_name,email,email,joined_at,left_at,duration_seconds\n"
            "Ada Lovelace,ada@example.org,ada@example.org,t1,t2,3600\n"
        )


def test_a_malformed_row_is_reported_and_dropped_the_rest_still_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one test the brief's mutation check bites on: a row this
    malformed must be reported (printed to the job log) and excluded, never
    silently dropped, and never allowed to abort the whole import."""
    event_dir = tmp_path / "events" / "mrg-918"
    event_dir.mkdir(parents=True)
    _write_csv(
        event_dir / "attendance-import.csv",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
        "2026-08-20T19:00:00Z,not-a-number",
        "Grace Hopper,grace@example.org,2026-08-20T18:05:00Z,2026-08-20T19:05:00Z,3600",
    )

    rows = _platform(tmp_path).get_attendance("mrg-918")

    assert [row.display_name for row in rows] == ["Grace Hopper"]
    printed = capsys.readouterr().out
    assert "line 2" in printed
    assert "duration_seconds" in printed


def test_a_row_with_an_empty_display_name_is_reported_and_dropped(
    tmp_path: Path,
) -> None:
    event_dir = tmp_path / "events" / "mrg-919"
    event_dir.mkdir(parents=True)
    _write_csv(
        event_dir / "attendance-import.csv",
        ",ghost@example.org,2026-08-20T18:00:00Z,2026-08-20T19:00:00Z,3600",
    )

    rows, issues = parse_attendance_csv(
        (event_dir / "attendance-import.csv").read_text(encoding="utf-8")
    )

    assert rows == []
    assert issues == [AttendanceIssue(line_number=2, reason="display_name is empty")]


def test_a_row_with_a_negative_duration_is_reported_and_dropped(
    tmp_path: Path,
) -> None:
    rows, issues = parse_attendance_csv(
        "\n".join(
            (
                CSV_HEADER,
                "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
                "2026-08-20T17:00:00Z,-60",
            )
        )
        + "\n"
    )

    assert rows == []
    assert len(issues) == 1
    assert "duration_seconds" in issues[0].reason


def test_a_row_with_no_joined_at_is_reported_and_dropped(tmp_path: Path) -> None:
    rows, issues = parse_attendance_csv(
        "\n".join(
            (
                CSV_HEADER,
                "Ada Lovelace,ada@example.org,,2026-08-20T19:00:00Z,3600",
            )
        )
        + "\n"
    )

    assert rows == []
    assert issues == [AttendanceIssue(line_number=2, reason="joined_at is empty")]


def test_a_short_row_is_reported_and_dropped(tmp_path: Path) -> None:
    """A row with fewer fields than the header (a hand-truncated export)
    fills the missing cells with `None`, not an empty string -- `csv`'s own
    behaviour. Any required field landing on `None` must still be reported
    like any other malformed row, never raise an uncaught `AttributeError`."""
    rows, issues = parse_attendance_csv(
        "\n".join((CSV_HEADER, "Ada Lovelace,ada@example.org")) + "\n"
    )

    assert rows == []
    assert len(issues) == 1


def test_an_empty_import_with_only_a_header_yields_no_rows_and_no_issues(
    tmp_path: Path,
) -> None:
    rows, issues = parse_attendance_csv(CSV_HEADER + "\n")

    assert rows == []
    assert issues == []


def test_extra_unexpected_columns_do_not_fail_the_import(tmp_path: Path) -> None:
    """Extra columns an export tool adds are harmless -- only a *missing*
    required column is a whole-file failure."""
    rows, issues = parse_attendance_csv(
        "\n".join(
            (
                CSV_HEADER + ",device",
                "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
                "2026-08-20T19:00:00Z,3600,desktop",
            )
        )
        + "\n"
    )

    assert issues == []
    assert rows[0].display_name == "Ada Lovelace"


# ------------------------------------------------------------------ #
# get_attendance against real bytes, not hand-built strings -- the BOM,
# CRLF, a trailing blank line and an over-long row all arrive this way in
# practice, at the file-reading boundary `parse_attendance_csv` alone
# cannot exercise.
# ------------------------------------------------------------------ #


def test_get_attendance_reads_a_file_with_a_utf8_bom(tmp_path: Path) -> None:
    """The Important review finding: a plain `utf-8` read leaves the BOM on
    the first header cell, and this module used to report `display_name`
    missing on a file that has it. Real bytes, because a hand-built Python
    string would never carry a BOM by accident the way a Windows or
    Excel-adjacent export tool does."""
    event_dir = tmp_path / "events" / "mrg-930"
    event_dir.mkdir(parents=True)
    content = (
        CSV_HEADER + "\n"
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:00:00Z,3600\n"
    )
    (event_dir / "attendance-import.csv").write_bytes(
        b"\xef\xbb\xbf" + content.encode("utf-8")
    )

    rows = _platform(tmp_path).get_attendance("mrg-930")

    assert [row.display_name for row in rows] == ["Ada Lovelace"]


def test_get_attendance_handles_crlf_line_endings(tmp_path: Path) -> None:
    event_dir = tmp_path / "events" / "mrg-931"
    event_dir.mkdir(parents=True)
    content = (
        CSV_HEADER + "\r\n"
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
        "2026-08-20T19:00:00Z,3600\r\n"
    )
    (event_dir / "attendance-import.csv").write_bytes(content.encode("utf-8"))

    rows = _platform(tmp_path).get_attendance("mrg-931")

    assert [row.display_name for row in rows] == ["Ada Lovelace"]


def test_get_attendance_skips_trailing_blank_lines(tmp_path: Path) -> None:
    event_dir = tmp_path / "events" / "mrg-932"
    event_dir.mkdir(parents=True)
    content = (
        CSV_HEADER + "\n"
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:00:00Z,3600\n"
        "\n\n"
    )
    (event_dir / "attendance-import.csv").write_bytes(content.encode("utf-8"))

    rows = _platform(tmp_path).get_attendance("mrg-932")

    assert [row.display_name for row in rows] == ["Ada Lovelace"]


def test_get_attendance_ignores_extra_cells_on_an_over_long_row(
    tmp_path: Path,
) -> None:
    """A row with more cells than the header has columns puts the extras
    under `csv.DictReader`'s `None` restkey. `_parse_row` only ever reads
    the five named columns, so the extras are silently harmless -- pinned
    here through the real read path, not assumed."""
    event_dir = tmp_path / "events" / "mrg-933"
    event_dir.mkdir(parents=True)
    content = (
        CSV_HEADER + "\n"
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
        "2026-08-20T19:00:00Z,3600,extra,extra2\n"
    )
    (event_dir / "attendance-import.csv").write_bytes(content.encode("utf-8"))

    rows = _platform(tmp_path).get_attendance("mrg-933")

    assert [row.display_name for row in rows] == ["Ada Lovelace"]


# ------------------------------------------------------------------ #
# get_recording / delete_recording
# ------------------------------------------------------------------ #


def test_get_recording_is_unavailable_when_no_recording_url_is_set(
    tmp_path: Path,
) -> None:
    speakers = [_speaker(edition_code="MRG-920", youtube_url="")]

    recording = _platform(tmp_path, speakers=speakers).get_recording("mrg-920")

    assert recording == Recording(url="", size=0, available=False)


def test_get_recording_is_available_once_a_url_is_typed_in_by_hand(
    tmp_path: Path,
) -> None:
    """`video_publishing`'s own row in `config/integrations.yml` already
    says this: recording URLs are entered by hand after publishing, and no
    upload is attempted -- so `size` is not knowable here (the file is not
    hosted by us) and is always 0 for the manual implementation."""
    speakers = [
        _speaker(edition_code="MRG-921", youtube_url="https://videos.example.org/mrg-921")
    ]

    recording = _platform(tmp_path, speakers=speakers).get_recording("mrg-921")

    assert recording == Recording(
        url="https://videos.example.org/mrg-921", size=0, available=True
    )


def test_get_recording_raises_when_no_speaker_record_matches_the_event(
    tmp_path: Path,
) -> None:
    with pytest.raises(EventNotFoundError, match="mrg-923"):
        _platform(tmp_path).get_recording("mrg-923")


def test_delete_recording_is_a_documented_no_op(tmp_path: Path) -> None:
    """`delete_recording` exists because of the chosen platform's storage
    quota (spec SS2): a manual recording lives wherever it was uploaded by
    hand, under nobody's quota this project manages, so there is nothing
    for the manual implementation to reclaim. No speaker record is needed
    either -- unlike `get_room` / `get_recording`, this never looks one up."""
    _platform(tmp_path).delete_recording("mrg-922")  # does not raise


def test_delete_recording_still_validates_the_event_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _platform(tmp_path).delete_recording("../escape")


# ------------------------------------------------------------------ #
# construction
# ------------------------------------------------------------------ #


def test_events_dir_defaults_to_the_repository_data_events_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "config.yml").write_text("season: 2026\n", encoding="utf-8")

    assert ManualPlatform().events_dir == tmp_path / "data" / "events"


def test_speakers_and_config_default_to_empty(tmp_path: Path) -> None:
    """No speaker data or config supplied is not a construction error --
    every lookup then simply fails to find anything, the honest answer to
    'nothing was given'."""
    platform = ManualPlatform(events_dir=tmp_path / "events")

    assert platform.speakers == ()
    assert platform.config is None
