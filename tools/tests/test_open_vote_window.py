"""Opening the vote window on the backlog (scripts/open_vote_window.py).

The transformation is pure and tested here before it is ever pointed at
`instance/data/`, because the file it rewrites holds real people's names and e-mail
addresses. Three properties matter more than the rest:

* only a record still awaiting the Board is stamped -- a concluded vote must
  never be reopened retroactively;
* nothing outside `selection.opened_on` is touched -- pinned field by field
  on a realistic record rather than on a minimal one;
* it is idempotent -- a second run must not move a deadline that a lead is
  already being judged against.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import speaker
from open_vote_window import (
    AWAITING,
    DEFAULT_ON,
    _ascii,
    main,
    needs_window,
    open_window,
    open_windows,
)

from convener_ops.cli import SPEAKERS_HEADER
from convener_ops.validate import STATUSES

ON = "2026-08-18"


def lead(**overrides: Any) -> dict[str, Any]:
    """A lead as the v3 migration leaves it: ballots cast, no window open."""
    return speaker(**overrides)


# --- which records get a window -------------------------------------------


def test_a_lead_with_no_window_gets_one() -> None:
    stamped = open_window(lead(), ON)
    assert stamped["selection"]["opened_on"] == ON


def test_every_status_that_is_not_a_lead_is_left_alone() -> None:
    # A vote that concluded -- by approval, by refusal, or by expiry -- must
    # not be reopened retroactively. `lead` is the only status for which the
    # Board is still being asked.
    for status in STATUSES - AWAITING:
        entry = lead(status=status)
        assert not needs_window(entry), status
        assert open_window(entry, ON) == entry, status


def test_a_lead_whose_vote_was_decided_is_left_alone() -> None:
    # The question was answered, whatever the status still says; a window
    # would expose a settled decision to expiry.
    entry = lead(selection={"ballots": [], "opened_on": "", "decided_on": "2026-03-01"})
    assert not needs_window(entry)
    assert open_window(entry, ON) == entry


def test_an_existing_window_is_never_moved() -> None:
    entry = lead(selection={"ballots": [], "opened_on": "2026-07-01", "decided_on": ""})
    assert open_window(entry, ON)["selection"]["opened_on"] == "2026-07-01"


def test_a_record_without_a_selection_mapping_is_left_alone() -> None:
    entry = lead(selection=None)
    assert not needs_window(entry)
    assert open_window(entry, ON) == entry


def test_a_non_mapping_entry_is_passed_through_untouched() -> None:
    assert open_windows(["not a mapping"], ON) == ["not a mapping"]


# --- what the change may not do -------------------------------------------


def test_no_field_outside_opened_on_is_touched() -> None:
    before = lead()
    stamped = open_window(before, ON)
    assert set(stamped) == set(before)
    for key, value in before.items():
        if key != "selection":
            assert stamped[key] == value, key
    for key, value in before["selection"].items():
        if key != "opened_on":
            assert stamped["selection"][key] == value, key


def test_the_original_record_is_not_mutated() -> None:
    before = lead()
    open_window(before, ON)
    assert before["selection"]["opened_on"] == ""


def test_the_keys_keep_their_order() -> None:
    # The file is read by hand and reviewed as a diff: one changed line per
    # record, never a reshuffle.
    before = lead()
    stamped = open_window(before, ON)
    assert list(stamped) == list(before)
    assert list(stamped["selection"]) == list(before["selection"])


def test_stamping_twice_changes_nothing() -> None:
    once = open_windows([lead(), lead(id="spk-002", status="delivered")], ON)
    twice = open_windows(once, "2026-12-25")
    assert twice == once
    assert once[0]["selection"]["opened_on"] == ON


# --- the script as it is actually run -------------------------------------


def _repo(tmp_path: Path, speakers: list[dict[str, Any]]) -> Path:
    data = tmp_path / "instance" / "data"
    data.mkdir(parents=True)
    (data / "config.yml").write_text("season: 2026\n", encoding="utf-8")
    path = data / "speakers.yml"
    path.write_text(
        SPEAKERS_HEADER + yaml.safe_dump(speakers, sort_keys=False), encoding="utf-8"
    )
    return path


def test_main_writes_the_file_and_a_second_run_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _repo(tmp_path, [lead(), lead(id="spk-002", status="confirmed")])
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main([]) == 0
    written = path.read_text(encoding="utf-8")
    assert written.startswith(SPEAKERS_HEADER)
    assert written.count(f"opened_on: '{DEFAULT_ON}'") == 1

    assert main([]) == 0
    assert path.read_text(encoding="utf-8") == written
    assert "already has a vote window" in capsys.readouterr().out


def test_a_dry_run_prints_the_diff_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _repo(tmp_path, [lead()])
    before = path.read_text(encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main(["--dry-run", "--on", ON]) == 0
    out = capsys.readouterr().out
    assert f"+    opened_on: '{ON}'" in out
    assert "1 leads would be stamped" in out
    assert path.read_text(encoding="utf-8") == before


def test_the_dry_run_prints_nothing_a_windows_console_cannot_render() -> None:
    # The operator reads this diff on a console that renders non-ASCII as
    # mojibake, and it is a diff of records about real people: an escaped
    # name still shows a change, a mojibake one hides it.
    printed = _ascii("affiliation: Universite du Quebec a Montreal\u00e9")
    assert printed.isascii()
    assert r"\xe9" in printed
