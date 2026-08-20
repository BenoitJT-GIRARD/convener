from __future__ import annotations

from pathlib import Path

import pytest

from convener_ops.platform import (
    AttendanceImportError,
    AttendanceIssue,
    AttendanceRow,
    ManualPlatform,
    Platform,
    Recording,
    Room,
    RoomConfigError,
    parse_attendance_csv,
)

CSV_HEADER = "display_name,email,joined_at,left_at,duration_seconds"


def _write_csv(path: Path, *rows: str) -> None:
    path.write_text("\n".join((CSV_HEADER, *rows)) + "\n", encoding="utf-8")


def _write_room_config(
    path: Path,
    join_url: str = "https://meet.example.org/room",
    instructions: str = "",
    recording_url: str = "",
) -> None:
    path.write_text(
        "join_url: "
        + repr(join_url)
        + "\ninstructions: "
        + repr(instructions)
        + "\nrecording_url: "
        + repr(recording_url)
        + "\n",
        encoding="utf-8",
    )


def _platform(tmp_path: Path) -> ManualPlatform:
    return ManualPlatform(events_dir=tmp_path / "events")


# ------------------------------------------------------------------ #
# Protocol conformance
# ------------------------------------------------------------------ #


def test_manual_platform_satisfies_the_platform_protocol(tmp_path: Path) -> None:
    """`ManualPlatform` is not a stopgap: a caller written against the
    `Platform` interface must accept it without an isinstance check ever
    failing, exactly as it will later accept task 3's platform_fcc.py."""
    assert isinstance(_platform(tmp_path), Platform)


# ------------------------------------------------------------------ #
# get_room -- the event's configuration
# ------------------------------------------------------------------ #


def test_get_room_reads_join_url_and_instructions_from_the_event_config(
    tmp_path: Path,
) -> None:
    event_dir = tmp_path / "events" / "mrg-901"
    event_dir.mkdir(parents=True)
    _write_room_config(
        event_dir / "config.yml",
        join_url="https://meet.example.org/permanent-room",
        instructions="Dial +1 555 0100 if the link fails.",
    )

    room = _platform(tmp_path).get_room("mrg-901")

    assert room == Room(
        join_url="https://meet.example.org/permanent-room",
        instructions="Dial +1 555 0100 if the link fails.",
    )


def test_get_room_allows_empty_instructions(tmp_path: Path) -> None:
    """An empty string is an answer -- 'nothing beyond the link' -- the same
    convention `data/config.yml` uses throughout."""
    event_dir = tmp_path / "events" / "mrg-902"
    event_dir.mkdir(parents=True)
    _write_room_config(event_dir / "config.yml", instructions="")

    room = _platform(tmp_path).get_room("mrg-902")

    assert room.instructions == ""


def test_get_room_raises_when_no_configuration_exists_for_the_event(
    tmp_path: Path,
) -> None:
    with pytest.raises(RoomConfigError, match="mrg-903"):
        _platform(tmp_path).get_room("mrg-903")


def test_get_room_names_the_missing_key(tmp_path: Path) -> None:
    """A volunteer editing this file by hand needs to know which key is
    missing, not merely that the file could not be read -- the same
    requirement acceptance criterion 3 of the brief makes of the CSV
    reader."""
    event_dir = tmp_path / "events" / "mrg-904"
    event_dir.mkdir(parents=True)
    (event_dir / "config.yml").write_text(
        "join_url: 'https://meet.example.org/room'\n", encoding="utf-8"
    )

    with pytest.raises(RoomConfigError) as excinfo:
        _platform(tmp_path).get_room("mrg-904")

    assert "instructions" in str(excinfo.value)
    assert "recording_url" in str(excinfo.value)


def test_get_room_raises_when_the_config_is_not_a_mapping(tmp_path: Path) -> None:
    event_dir = tmp_path / "events" / "mrg-905"
    event_dir.mkdir(parents=True)
    (event_dir / "config.yml").write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(RoomConfigError):
        _platform(tmp_path).get_room("mrg-905")


def test_get_room_treats_a_blank_hand_typed_value_as_empty_string(
    tmp_path: Path,
) -> None:
    """A volunteer typing `instructions:` with nothing after the colon
    writes YAML `null`, not `''` -- both mean the same thing here: no
    answer given yet."""
    event_dir = tmp_path / "events" / "mrg-906"
    event_dir.mkdir(parents=True)
    (event_dir / "config.yml").write_text(
        "join_url: 'https://meet.example.org/room'\ninstructions:\nrecording_url: ''\n",
        encoding="utf-8",
    )

    room = _platform(tmp_path).get_room("mrg-906")

    assert room.instructions == ""


def test_get_room_raises_when_a_key_holds_the_wrong_type(tmp_path: Path) -> None:
    event_dir = tmp_path / "events" / "mrg-907"
    event_dir.mkdir(parents=True)
    (event_dir / "config.yml").write_text(
        "join_url: 42\ninstructions: ''\nrecording_url: ''\n", encoding="utf-8"
    )

    with pytest.raises(RoomConfigError, match="join_url"):
        _platform(tmp_path).get_room("mrg-907")


# ------------------------------------------------------------------ #
# event id validation -- checked before any filesystem access
# ------------------------------------------------------------------ #


@pytest.mark.parametrize("bad_id", ["../secret", "a/b", "", ".hidden"])
def test_an_invalid_event_id_is_refused_before_touching_the_filesystem(
    tmp_path: Path, bad_id: str
) -> None:
    events_dir = tmp_path / "events"
    with pytest.raises(ValueError):
        _platform(tmp_path).get_room(bad_id)
    # No directory was created or read as a side effect of the attempt.
    assert not events_dir.exists()


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
# get_recording / delete_recording
# ------------------------------------------------------------------ #


def test_get_recording_is_unavailable_when_no_recording_url_is_set(
    tmp_path: Path,
) -> None:
    event_dir = tmp_path / "events" / "mrg-920"
    event_dir.mkdir(parents=True)
    _write_room_config(event_dir / "config.yml", recording_url="")

    recording = _platform(tmp_path).get_recording("mrg-920")

    assert recording == Recording(url="", size=0, available=False)


def test_get_recording_is_available_once_a_url_is_typed_in_by_hand(
    tmp_path: Path,
) -> None:
    """`video_publishing`'s own row in `config/integrations.yml` already
    says this: recording URLs are entered by hand after publishing, and no
    upload is attempted -- so `size` is not knowable here (the file is not
    hosted by us) and is always 0 for the manual implementation."""
    event_dir = tmp_path / "events" / "mrg-921"
    event_dir.mkdir(parents=True)
    _write_room_config(
        event_dir / "config.yml",
        recording_url="https://videos.example.org/mrg-921",
    )

    recording = _platform(tmp_path).get_recording("mrg-921")

    assert recording == Recording(
        url="https://videos.example.org/mrg-921", size=0, available=True
    )


def test_delete_recording_is_a_documented_no_op(tmp_path: Path) -> None:
    """`delete_recording` exists because of the chosen platform's storage
    quota (spec 2): a manual recording lives wherever it was uploaded by
    hand, under nobody's quota this project manages, so there is nothing
    for the manual implementation to reclaim."""
    event_dir = tmp_path / "events" / "mrg-922"
    event_dir.mkdir(parents=True)
    _write_room_config(event_dir / "config.yml")

    _platform(tmp_path).delete_recording("mrg-922")  # does not raise
    # Nothing on disk was touched by the no-op.
    assert (event_dir / "config.yml").exists()


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
