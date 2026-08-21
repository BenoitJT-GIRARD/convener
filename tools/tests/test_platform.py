from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from convener_ops import eventkeys
from convener_ops.platform import (
    ENCRYPTED_ATTENDANCE_FILENAME,
    AttendanceExportFile,
    AttendanceImportError,
    AttendanceIssue,
    AttendanceRow,
    EventNotFoundError,
    ManualPlatform,
    Platform,
    Recording,
    decrypt_attendance_rows,
    encrypt_attendance_rows,
    erase_attendance_rows,
    find_speaker,
    load_attendance_export_file,
    parse_attendance_csv,
)

CSV_HEADER = "display_name,email,joined_at,left_at,duration_seconds"


def _write_csv(path: Path, *rows: str) -> None:
    path.write_text("\n".join((CSV_HEADER, *rows)) + "\n", encoding="utf-8")


def _rows_from_csv_lines(*rows: str) -> list[AttendanceRow]:
    """The same rows `_write_csv` would have written, already parsed --
    the input `encrypt_attendance_rows` takes (fix round 1, R-45: one
    envelope per row, not one for the whole CSV)."""
    parsed, issues = parse_attendance_csv("\n".join((CSV_HEADER, *rows)) + "\n")
    assert issues == []
    return parsed


def _write_encrypted_csv(path: Path, public_pem: str, *rows: str) -> None:
    """The committed shape (fix round 1): one independent `eventkeys`
    envelope per row, hybrid-encrypted under `public_pem` via
    `encrypt_attendance_rows` -- the real function this module ships,
    never a hand-rolled stand-in for it."""
    path.write_text(
        encrypt_attendance_rows(public_pem, _rows_from_csv_lines(*rows)),
        encoding="utf-8",
    )


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
    private_pem: str | None = None,
) -> ManualPlatform:
    return ManualPlatform(
        events_dir=tmp_path / "events",
        speakers=speakers,
        config=config,
        private_pem=private_pem,
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


def test_missing_attendance_file_message_does_not_leak_the_repository_root(
    tmp_path: Path,
) -> None:
    """Small item 2 (fix round 3): the message used to interpolate the
    absolute `path` this class actually checked, which carries
    `CONVENER_REPO_ROOT` -- here, `tmp_path` itself, standing in for a CI
    runner's own filesystem layout -- into a job's own log for no reason,
    the same leak minor 5 of fix round 1 already closed for `cli.py`'s own
    register-path messages. Only the repository-relative form should ever
    appear; `tmp_path`'s own absolute string must not."""
    with pytest.raises(AttendanceImportError) as excinfo:
        _platform(tmp_path).get_attendance("mrg-918")

    message = str(excinfo.value)
    assert str(tmp_path) not in message
    assert "data/events/mrg-918/attendance-import.csv" in message


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
    with pytest.raises(AttendanceImportError, match="1 duplicate column"):
        parse_attendance_csv(
            "display_name,email,email,joined_at,left_at,duration_seconds\n"
            "Ada Lovelace,ada@example.org,ada@example.org,t1,t2,3600\n"
        )


def test_duplicate_column_message_names_the_count_and_position_never_the_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Important 5, fix round 1: this branch used to echo the duplicated
    column's own *name* -- the file's own header text, written by
    whatever export tool produced it -- and task 17 is what made this
    branch reachable from a CI job log at all (the manual path previously
    had no file to read there). The message must still be enough to find
    and fix the file: the count, and the 1-based header position(s)."""
    with pytest.raises(AttendanceImportError) as excinfo:
        parse_attendance_csv(
            "ada@example.org,ada@example.org,joined_at,left_at,duration_seconds\n"
        )
    message = str(excinfo.value)
    assert "ada@example.org" not in message
    assert "1 duplicate column name(s), at header position(s): 1, 2" in message


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


def test_a_malformed_durations_reason_never_echoes_the_cells_content(
    tmp_path: Path,
) -> None:
    """A column shift -- an export tool that reorders a name or an
    address into the `duration_seconds` column by mistake -- must not put
    that cell's own content into the reported reason. The reason names
    the column and what was wrong with it, and nothing else."""
    rows, issues = parse_attendance_csv(
        "\n".join(
            (
                CSV_HEADER,
                "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
                "2026-08-20T19:00:00Z,ada@example.org",
            )
        )
        + "\n"
    )

    assert rows == []
    assert issues == [
        AttendanceIssue(line_number=2, reason="duration_seconds is not a whole number")
    ]


def test_a_column_shift_never_prints_the_shifted_cells_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same property, exercised through `ManualPlatform.get_attendance`
    -- the path that actually prints a dropped row's reason to the job
    log, which is where this leak would actually reach a reader."""
    event_dir = tmp_path / "events" / "mrg-941"
    event_dir.mkdir(parents=True)
    _write_csv(
        event_dir / "attendance-import.csv",
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,"
        "2026-08-20T19:00:00Z,ada@example.org",
    )

    rows = _platform(tmp_path).get_attendance("mrg-941")

    assert rows == []
    printed = capsys.readouterr().out
    assert "ada@example.org" not in printed
    assert "duration_seconds" in printed


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
# get_attendance -- the encrypted export (task 17, AC8: the manual
# implementation must run end to end with no external account). See
# `platform.py`'s own module docstring, "the plaintext CSV is never
# committed -- the encrypted export is", for why this exists at all.
# ------------------------------------------------------------------ #


def test_get_attendance_reads_the_encrypted_export_in_preference_to_plaintext(
    tmp_path: Path,
) -> None:
    """The committed shape a real event uses: `attendance-import.csv.enc`,
    produced by `convener-encrypt-attendance-export` and decrypted here with the
    same private key `EVENT_PRIVATE_KEY` already supplies every other
    command in this event's chain. Also proves the encrypted file wins when
    both exist -- the production shape never has both, but a caller must
    not be able to smuggle an unencrypted row past this path by dropping a
    plaintext file alongside a stale encrypted one."""
    private_pem, public_pem = eventkeys.generate()
    event_dir = tmp_path / "events" / "mrg-940"
    event_dir.mkdir(parents=True)
    _write_encrypted_csv(
        event_dir / ENCRYPTED_ATTENDANCE_FILENAME,
        public_pem,
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )
    _write_csv(
        event_dir / "attendance-import.csv",
        "Someone Else,someone@example.org,2026-08-20T18:00:00Z,"
        "2026-08-20T18:10:00Z,600",
    )

    rows = _platform(tmp_path, private_pem=private_pem).get_attendance("mrg-940")

    assert [row.display_name for row in rows] == ["Ada Lovelace"]


def test_get_attendance_refuses_the_encrypted_export_without_a_private_key(
    tmp_path: Path,
) -> None:
    """Fail closed, not D-13's ordinary absence: a committed encrypted
    export is personal data waiting to be read, so a caller with no key
    configured must get a loud refusal, never a quiet "no attendance"."""
    _, public_pem = eventkeys.generate()
    event_dir = tmp_path / "events" / "mrg-941"
    event_dir.mkdir(parents=True)
    _write_encrypted_csv(
        event_dir / ENCRYPTED_ATTENDANCE_FILENAME,
        public_pem,
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )

    with pytest.raises(AttendanceImportError, match="no private key configured"):
        _platform(tmp_path, private_pem=None).get_attendance("mrg-941")


def test_get_attendance_returns_nothing_when_every_row_fails_to_decrypt(
    tmp_path: Path,
) -> None:
    """Fix round 1, R-45: with one independent envelope per row, a private
    key that matches no row (the whole export was committed for a
    different event's key by mistake) is not a whole-file failure any
    more -- each row is skipped on its own, the same tolerance
    `registration.py`'s own callers already give a stray undecryptable
    entry in `registrations.enc`. This is parity, not a regression: a
    wrong-event key against `registrations.enc` already produces exactly
    this "quietly nothing" outward shape today (`to_registration` returns
    `None` per entry, silently skipped by every `cli.py` loop) -- this
    test pins the identical behaviour for its attendance-export twin."""
    _, public_pem = eventkeys.generate()
    other_private_pem, _ = eventkeys.generate()
    event_dir = tmp_path / "events" / "mrg-942"
    event_dir.mkdir(parents=True)
    _write_encrypted_csv(
        event_dir / ENCRYPTED_ATTENDANCE_FILENAME,
        public_pem,
        "Ada Lovelace,ada@example.org,2026-08-20T18:00:00Z,2026-08-20T19:30:00Z,5400",
    )

    rows = _platform(tmp_path, private_pem=other_private_pem).get_attendance("mrg-942")

    assert rows == []


def test_get_attendance_refuses_a_malformed_encrypted_file(tmp_path: Path) -> None:
    """A committed `.enc` file that is not this module's own file shape at
    all (not the right format version, not a list of entries, an entry
    that is not exactly ciphertext) is a whole-file failure -- unlike a
    row that merely fails to decrypt, this is not "personal data with the
    wrong key", it is not personal data in the expected shape at all, and
    papering over it would be exactly the kind of malformed-file
    tolerance `registration.load_registration_file` already refuses."""
    private_pem, _public_pem = eventkeys.generate()
    event_dir = tmp_path / "events" / "mrg-944"
    event_dir.mkdir(parents=True)
    (event_dir / ENCRYPTED_ATTENDANCE_FILENAME).write_text(
        "not json at all", encoding="utf-8"
    )

    with pytest.raises(AttendanceImportError, match="could not be read"):
        _platform(tmp_path, private_pem=private_pem).get_attendance("mrg-944")


def test_encrypt_attendance_rows_and_decrypt_attendance_rows_round_trip(
    tmp_path: Path,
) -> None:
    """The real pair `ManualPlatform.get_attendance` and
    `convener-encrypt-attendance-export` both build on -- pinned directly,
    independent of either, so a future change to either side shows up
    here first. Two rows, including a telephone joiner (`email=None`),
    to prove the round trip preserves the one field this whole task
    exists to get right."""
    private_pem, public_pem = eventkeys.generate()
    rows = [
        AttendanceRow(
            display_name="Ada Lovelace",
            email="ada@example.org",
            joined_at="2026-08-20T18:00:00Z",
            left_at="2026-08-20T19:30:00Z",
            duration_seconds=5400,
        ),
        AttendanceRow(
            display_name="+1 555 0100",
            email=None,
            joined_at="2026-08-20T18:00:00Z",
            left_at="2026-08-20T18:10:00Z",
            duration_seconds=600,
        ),
    ]

    envelope_text = encrypt_attendance_rows(public_pem, rows)
    file = load_attendance_export_file(envelope_text)

    assert len(file.entries) == 2
    assert decrypt_attendance_rows(file, private_pem) == rows


def test_decrypt_attendance_rows_skips_one_row_that_fails_to_decrypt(
    tmp_path: Path,
) -> None:
    """One damaged or foreign row costs one row, not the whole file --
    the same tolerance `registration.py`'s own callers already give a
    stray undecryptable entry."""
    private_pem, public_pem = eventkeys.generate()
    _other_private_pem, other_public_pem = eventkeys.generate()
    good = AttendanceRow(
        display_name="Ada Lovelace",
        email="ada@example.org",
        joined_at="x",
        left_at="y",
        duration_seconds=60,
    )
    stray = AttendanceRow(
        display_name="Grace Hopper",
        email="grace@example.org",
        joined_at="x",
        left_at="y",
        duration_seconds=60,
    )
    good_file = load_attendance_export_file(encrypt_attendance_rows(public_pem, [good]))
    stray_file = load_attendance_export_file(
        encrypt_attendance_rows(other_public_pem, [stray])
    )
    mixed = AttendanceExportFile(entries=(*good_file.entries, *stray_file.entries))

    rows = decrypt_attendance_rows(mixed, private_pem)

    assert rows == [good]


def test_load_attendance_export_file_rejects_the_wrong_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a supported format version"):
        load_attendance_export_file('{"v": 999, "rows": []}')


def test_load_attendance_export_file_rejects_an_entry_that_is_not_ciphertext(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="not exactly ciphertext"):
        load_attendance_export_file('{"v": 1, "rows": [{"name": "not an envelope"}]}')


def test_load_attendance_export_file_starts_empty_when_text_is_none() -> None:
    assert load_attendance_export_file(None) == AttendanceExportFile()


# ------------------------------------------------------------------ #
# erase_attendance_rows -- fix round 1, R-45 / Critical 1: an early
# erasure request has to remove a person's rows from the committed
# attendance export too, or the request is not actually satisfied.
# ------------------------------------------------------------------ #


def test_erase_attendance_rows_removes_the_target_and_leaves_neighbours_byte_identical(
    tmp_path: Path,
) -> None:
    """Task 15's existing shape for `registrations.enc`, applied unchanged:
    erasing one row must not so much as re-serialise another. Compares
    the two surviving envelopes verbatim, not merely "still decrypts to
    the same row" -- the guarantee is that nothing else moved at all."""
    private_pem, public_pem = eventkeys.generate()
    ada = AttendanceRow("Ada Lovelace", "ada@example.org", "x", "y", 60)
    grace = AttendanceRow("Grace Hopper", "grace@example.org", "x", "y", 90)
    marie = AttendanceRow("Marie Curie", "marie@example.org", "x", "y", 120)
    original = load_attendance_export_file(
        encrypt_attendance_rows(public_pem, [ada, grace, marie])
    )

    updated, removed = erase_attendance_rows(original, "ada@example.org", private_pem)

    assert removed == 1
    assert len(updated.entries) == 2
    assert updated.entries == (original.entries[1], original.entries[2])
    assert decrypt_attendance_rows(updated, private_pem) == [grace, marie]


def test_erase_attendance_rows_removes_every_row_for_a_reconnection(
    tmp_path: Path,
) -> None:
    """One person can carry several rows (a reconnection) -- erasure must
    remove all of theirs, not just the first found."""
    private_pem, public_pem = eventkeys.generate()
    first_connection = AttendanceRow("Marie Curie", "marie@example.org", "a", "b", 60)
    second_connection = AttendanceRow("marie curie", "marie@example.org", "c", "d", 90)
    grace = AttendanceRow("Grace Hopper", "grace@example.org", "x", "y", 30)
    original = load_attendance_export_file(
        encrypt_attendance_rows(
            public_pem, [first_connection, second_connection, grace]
        )
    )

    updated, removed = erase_attendance_rows(original, "marie@example.org", private_pem)

    assert removed == 2
    assert decrypt_attendance_rows(updated, private_pem) == [grace]


def test_erase_attendance_rows_never_matches_a_telephone_joiner(
    tmp_path: Path,
) -> None:
    """`email=None` can never equal a normalised target address -- the
    same boundary the module docstring names for matching in general,
    applied here so an erasure request can never accidentally claim a
    phone joiner's row by matching on nothing."""
    private_pem, public_pem = eventkeys.generate()
    phone = AttendanceRow("+1 555 0100", None, "x", "y", 60)
    original = load_attendance_export_file(encrypt_attendance_rows(public_pem, [phone]))

    updated, removed = erase_attendance_rows(
        original, "someone@example.org", private_pem
    )

    assert removed == 0
    assert updated.entries == original.entries


def test_erase_attendance_rows_keeps_an_undecryptable_row_untouched(
    tmp_path: Path,
) -> None:
    """A row this key cannot even read is kept exactly as found and never
    treated as a match -- the same defensive handling
    `registration.erase` already gives an undecryptable entry."""
    private_pem, _public_pem = eventkeys.generate()
    _other_private, other_public = eventkeys.generate()
    ada = AttendanceRow("Ada Lovelace", "ada@example.org", "x", "y", 60)
    stray_file = load_attendance_export_file(
        encrypt_attendance_rows(other_public, [ada])
    )

    updated, removed = erase_attendance_rows(stray_file, "ada@example.org", private_pem)

    assert removed == 0
    assert updated.entries == stray_file.entries


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
