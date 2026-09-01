"""The commands of `convener_ops.cli.publication` that write a projection
rather than a picture: the public feed, the survey-status feed and the
internal agenda.

Each is an entry point wired end to end -- what the command writes, not
what the function it calls returns -- because the mapping between the two
is where a published feed quietly stops matching the records it is derived
from. The three that render an image have their own modules beside this
one, for the reason theirs give: they need a browser and a pinned
rendering environment, and this one needs neither.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import config, speaker
from helpers.command_line import (
    write_data,
)

from convener_ops.cli.publication import (
    agenda_internal,
    public_data,
    survey_status_public_data,
)


def test_public_data_writes_the_allowlisted_feed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The entry point `convener-public-data` runs, wired end to end: a lead is
    # excluded (not a public status), a scheduled talk is included and
    # named by its edition_code (to_public's own id mapping, see
    # test_public_data.py) -- proving this writes to_public's *output*,
    # not merely that to_public itself works in isolation.
    speakers = [
        speaker(id="spk-001", status="lead"),
        speaker(
            id="spk-002",
            status="scheduled",
            edition_code="MRG-05",
            date="2026-01-08",
            host_1="H1",
            host_2="H2",
        ),
    ]
    write_data(tmp_path, speakers, config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert public_data() == 0
    assert "wrote 1 events" in capsys.readouterr().out

    written = json.loads(
        (tmp_path / "instance" / "public-data" / "events-public.json").read_text(
            encoding="utf-8"
        )
    )
    assert [row["id"] for row in written] == ["MRG-05"]


def test_public_data_reports_load_errors_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    (tmp_path / "instance" / "data").mkdir(parents=True)

    assert public_data() == 1
    assert "file missing" in capsys.readouterr().out
    assert not (tmp_path / "instance" / "public-data").exists()


def test_survey_status_public_data_writes_only_the_enabled_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`convener-survey-status-public-data`, wired end to end: an event
    with the switch off is excluded, one with it on is
    named by its lower-cased edition code -- proving this writes
    `to_survey_status`'s own output, not merely that the function works in
    isolation."""
    speakers = [
        speaker(id="spk-001", edition_code="MRG-05", survey_enabled=False),
        speaker(id="spk-002", edition_code="MRG-06", survey_enabled=True),
    ]
    write_data(tmp_path, speakers, config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert survey_status_public_data() == 0
    assert "wrote 1 event(s)" in capsys.readouterr().out

    written = json.loads(
        (tmp_path / "instance" / "public-data" / "survey-status.json").read_text(
            encoding="utf-8"
        )
    )
    assert written == ["mrg-06"]


def test_survey_status_public_data_reports_load_errors_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    (tmp_path / "instance" / "data").mkdir(parents=True)

    assert survey_status_public_data() == 1
    assert "file missing" in capsys.readouterr().out
    assert not (tmp_path / "instance" / "public-data").exists()


def test_agenda_internal_writes_pure_crlf_bytes_for_a_scheduled_edition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`convener-agenda-internal`, wired end to end: a
    `scheduled` speaker becomes one `VEVENT`, and the file this CLI
    command actually writes to disk carries the CRLF line endings RFC 5545
    requires -- `write_bytes`, not a text-mode write that this project's
    own Windows checkouts would corrupt (see `agenda_internal`'s own
    docstring)."""
    speakers = [
        speaker(
            id="spk-001", edition_code="MRG-07", status="scheduled", date="2026-09-10"
        )
    ]
    write_data(tmp_path, speakers, config())
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert agenda_internal() == 0
    assert "wrote 1 entrie(s)" in capsys.readouterr().out

    written = (
        tmp_path / "instance" / "public-data" / "agenda-internal.ics"
    ).read_bytes()
    assert b"BEGIN:VEVENT" in written
    assert b"mrg-07" in written
    assert b"\r\n" in written
    stripped = written.replace(b"\r\n", b"")
    assert b"\n" not in stripped, (
        "a bare LF survived the write -- CRLF was not preserved"
    )


def test_agenda_internal_reports_load_errors_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    (tmp_path / "instance" / "data").mkdir(parents=True)

    assert agenda_internal() == 1
    assert "file missing" in capsys.readouterr().out
    assert not (tmp_path / "instance" / "public-data").exists()
