"""The register is derived, and derivation has to be provably stable."""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

import pytest

from convener_ops import cli
from convener_ops.commit_format import (
    ACTS,
    QUALIFIERS,
    Decision,
    format_decision,
    judgemental_terms,
)
from convener_ops.register import (
    LOG_FORMAT,
    REGISTER_PATH,
    RegisterEntry,
    entries_from_log,
    render_register,
)


def log_line(instant: str, subject: str) -> str:
    """One line as `git log --format=LOG_FORMAT` would emit it."""
    return f"{instant}\x1f{subject}"


def decision_line(
    instant: str, kind: str, entity: str, actor: str, detail: str = ""
) -> str:
    return log_line(instant, format_decision(kind, entity, actor, detail))


def entry(
    day: str, kind: str, entity: str, actor: str, detail: str = ""
) -> RegisterEntry:
    return RegisterEntry(date.fromisoformat(day), Decision(kind, entity, actor, detail))


def prose(rendered: str) -> str:
    """The rendered text with its line wrapping collapsed.

    The preamble is wrapped for a human to read, so a sentence in it may be
    split anywhere. These tests are about what the register says, never about
    where the wrap falls, and asserting on the raw text would tie them to the
    latter.
    """
    return " ".join(rendered.split())


def rows(rendered: str) -> list[str]:
    """Every data row of the table, whatever shape the rows happen to have.

    Deliberately not "every line that looks like a row I expect": a helper
    that recognised only well-formed rows would go quiet exactly when the
    renderer started emitting malformed ones, and the tests below would pass
    on an empty list.
    """
    lines = rendered.splitlines()
    header = [
        n for n, line in enumerate(lines) if set(line) <= set("|- ") and "|" in line
    ]
    if not header:
        return []
    return [line for line in lines[header[-1] + 1 :] if line.startswith("|")]


def _first_qualifier(kind: str) -> str:
    return sorted(QUALIFIERS.get(kind, frozenset({""})))[0]


# --- the table ------------------------------------------------------------


def test_renders_one_row_per_decision_sorted_by_date() -> None:
    rendered = render_register(
        [
            entry("2026-03-04", "lead-decline", "spk-002", "grace"),
            entry("2026-03-01", "ballot-cast", "spk-001", "ada", "yes"),
        ]
    )

    assert rows(rendered) == [
        "| 2026-03-01 | record a ballot on (yes) | spk-001 | ada |",
        "| 2026-03-04 | decline | spk-002 | grace |",
    ]


def test_table_carries_the_four_columns_and_nothing_else() -> None:
    rendered = render_register([entry("2026-03-01", "lock-date", "spk-001", "ada")])

    assert "| Date | Act | Record | Recorded by |" in rendered
    assert rows(rendered)[0].count("|") == 5


def test_every_act_renders_its_own_phrase() -> None:
    """A new act cannot be added to the grammar and stay invisible here."""
    entries = [
        entry("2026-03-01", kind, "spk-001", "ada", _first_qualifier(kind))
        for kind in ACTS
    ]

    rendered = render_register(entries)

    assert len(rows(rendered)) == len(ACTS)
    for phrase in ACTS.values():
        assert f"| {phrase} |" in rendered or f"| {phrase} (" in rendered


# --- the property that makes the derivation safe --------------------------


def test_regenerating_from_the_same_commits_is_byte_identical() -> None:
    log = "\n".join(
        [
            decision_line(
                "2026-03-01T09:00:00+01:00", "ballot-cast", "spk-001", "ada", "yes"
            ),
            decision_line(
                "2026-03-02T09:00:00+01:00", "send-invitation", "spk-001", "grace"
            ),
            log_line("2026-03-02T10:00:00+01:00", "docs: tidy the runbook"),
        ]
    )

    first = render_register(entries_from_log(log))
    second = render_register(entries_from_log(log))

    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")


def test_rendering_does_not_depend_on_the_order_the_entries_arrive_in() -> None:
    entries = [
        entry(f"2026-03-0{n}", "ballot-cast", f"spk-00{n}", "ada", "yes")
        for n in range(1, 8)
    ]
    shuffled = list(entries)
    random.Random(7).shuffle(shuffled)

    assert render_register(shuffled) == render_register(entries)


def test_a_new_commit_only_appends_and_never_rewrites_a_line() -> None:
    history = [
        entry("2026-03-01", "ballot-cast", "spk-001", "ada", "yes"),
        entry("2026-03-05", "lock-date", "spk-001", "grace"),
    ]
    before = rows(render_register(history))

    after = rows(
        render_register([*history, entry("2026-03-09", "lead-park", "spk-002", "ada")])
    )

    assert after[: len(before)] == before
    assert len(after) == len(before) + 1


def test_a_commit_dated_before_an_existing_one_still_rewrites_nothing() -> None:
    """A rebase, or a laptop with a wrong clock, inserts; it never edits."""
    history = [
        entry("2026-03-05", "lock-date", "spk-001", "grace"),
        entry("2026-03-09", "lead-park", "spk-002", "ada"),
    ]
    before = rows(render_register(history))

    after = rows(
        render_register(
            [*history, entry("2026-03-01", "ballot-cast", "spk-001", "ada", "yes")]
        )
    )

    assert set(before) <= set(after)
    assert [line for line in after if line in before] == before


# --- what does not become a row -------------------------------------------


@pytest.mark.parametrize(
    "subject",
    [
        "docs: state the two permissions a recording needs before publication",
        "data: sweep elapsed events and expired vote windows",
        "data: open the vote window on the leads awaiting a decision",
        "ops: define and check the grammar of decision commits",
        "docs: regenerate the decision register",
    ],
)
def test_an_ordinary_commit_produces_no_row(subject: str) -> None:
    rendered = render_register(
        entries_from_log(log_line("2026-03-01T09:00:00+01:00", subject))
    )

    assert rows(rendered) == []
    assert "No decision has been recorded through the app yet." in rendered


@pytest.mark.parametrize(
    "subject",
    [
        "data: record a ballot on spk-001 by ada (maybe)",
        "data: record a ballot on spk-001",
        "data: approve publication of spk-001 by ada and grace",
        "data: record a ballot on spk-001 by ada (yes) and it was overdue",
    ],
)
def test_a_message_that_does_not_read_as_a_decision_produces_no_row(
    subject: str,
) -> None:
    assert entries_from_log(log_line("2026-03-01T09:00:00+01:00", subject)) == []


@pytest.mark.parametrize(
    "line", ["", "   ", "not-a-log-line", "2026-03-01T09:00:00+01:00"]
)
def test_a_line_that_is_not_a_log_record_produces_no_row(line: str) -> None:
    assert entries_from_log(line) == []


def test_an_unreadable_instant_produces_no_row() -> None:
    """Better a missing row than a row dated by guesswork."""
    assert entries_from_log(log_line("yesterday", "data: park spk-001 by ada")) == []


def test_the_actor_comes_from_the_message_not_from_the_commit_author() -> None:
    """A scheduled job has no `by <login>`, so it can write no row.

    The register never reads a commit's author, which is the only reason this
    holds: `convener-sweep` writes `data:` commits every night, and none of them can
    become a decision attributed to a machine.
    """
    log = log_line(
        "2026-03-01T09:00:00+01:00",
        "data: sweep elapsed events and expired vote windows",
    )

    assert entries_from_log(log) == []
    assert LOG_FORMAT == "%aI\x1f%s"  # no %an, %ae or %cn anywhere in it


# --- what the register may not say ----------------------------------------


def _every_sentence() -> list[RegisterEntry]:
    return [
        entry("2026-03-01", kind, "spk-001", "ada", detail)
        for kind in ACTS
        for detail in sorted(QUALIFIERS.get(kind, frozenset({""})))
    ]


def test_no_rendering_of_the_whole_vocabulary_judges_a_person() -> None:
    assert judgemental_terms(render_register(_every_sentence())) == []


def test_the_rendered_register_is_pure_ascii() -> None:
    render_register(_every_sentence()).encode("ascii")


def test_no_cell_can_break_the_table() -> None:
    """Identifiers are tokens and acts are constants, so no cell holds a pipe."""
    for row in rows(render_register(_every_sentence())):
        assert row.count("|") == 5


def test_an_empty_history_does_not_claim_that_nothing_was_decided() -> None:
    """The absence dates the tooling, and the file has to say so itself.

    The live history holds almost no decision commits: the grammar is one
    commit old and the speakers were migrated with their ballots rather than
    voted on through the app. A reader who met a bare table with no explanation
    would draw the one conclusion this register must never support.
    """
    rendered = render_register([])
    said = prose(rendered)

    assert "No decision has been recorded through the app yet." in said
    # the absence is explained, and pinned to when the mechanism arrived
    assert "have not been reconstituted from memory" in said
    assert "dates the arrival of the tooling, not the activity of the board" in said
    # and the reader is told where the earlier decisions actually are
    assert "are recorded elsewhere and are not lost" in said
    assert "data/speakers.yml" in said
    assert "decisions.md" in said
    # no empty table, which would read as a table of no decisions
    assert "| Date |" not in rendered


def test_the_file_says_it_is_derived_and_must_not_be_edited() -> None:
    rendered = render_register([entry("2026-03-01", "lock-date", "spk-001", "ada")])

    assert "Do not edit this file" in prose(rendered)
    assert "regenerated in full from the commits on every push" in prose(rendered)


# --- the days -------------------------------------------------------------


def test_the_day_is_the_paris_day_not_the_utc_one() -> None:
    """A commit made at 23:30 UTC belongs to the next Paris day."""
    entries = entries_from_log(
        decision_line("2026-03-01T23:30:00+00:00", "lock-date", "spk-001", "ada")
    )

    assert entries[0].day == date(2026, 3, 2)


def test_the_day_ignores_the_committer_own_offset() -> None:
    same_instant = [
        decision_line("2026-03-02T00:30:00+01:00", "lock-date", "spk-001", "ada"),
        decision_line("2026-03-01T23:30:00+00:00", "lock-date", "spk-001", "ada"),
    ]

    days = {entries_from_log(line)[0].day for line in same_instant}

    assert days == {date(2026, 3, 2)}


# --- the entry point ------------------------------------------------------


def _log(monkeypatch: pytest.MonkeyPatch, text: str, error: str = "") -> None:
    monkeypatch.setattr(cli, "_git_log", lambda root: (text, error))


def test_register_writes_the_file_under_the_repository_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["convener-register"])
    _log(
        monkeypatch,
        decision_line("2026-03-01T09:00:00+01:00", "lock-date", "spk-001", "ada"),
    )

    assert cli.register() == 0

    written = (tmp_path / REGISTER_PATH).read_text(encoding="utf-8")
    assert "| 2026-03-01 | lock the date of | spk-001 | ada |" in written
    assert (
        "wrote docs/governance/register.md - 1 decision(s)" in capsys.readouterr().out
    )


def test_register_reads_the_current_file_and_leaves_it_alone_when_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["convener-register"])
    _log(
        monkeypatch,
        decision_line("2026-03-01T09:00:00+01:00", "lock-date", "spk-001", "ada"),
    )
    assert cli.register() == 0
    path = tmp_path / REGISTER_PATH
    stamp = path.stat().st_mtime_ns
    capsys.readouterr()

    assert cli.register() == 0

    assert path.stat().st_mtime_ns == stamp
    assert "register unchanged - 1 decision(s)" in capsys.readouterr().out


def test_register_overwrites_a_hand_written_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The register cannot be authored: a row nobody committed cannot survive."""
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["convener-register"])
    path = tmp_path / REGISTER_PATH
    path.parent.mkdir(parents=True)
    path.write_text(
        "| 2026-03-01 | decline | spk-009 | ada |\nhe never showed up\n",
        encoding="utf-8",
    )
    _log(
        monkeypatch,
        decision_line("2026-03-01T09:00:00+01:00", "lock-date", "spk-001", "ada"),
    )

    assert cli.register() == 0

    written = path.read_text(encoding="utf-8")
    assert "spk-009" not in written
    assert "he never showed up" not in written


def test_register_dry_run_prints_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["convener-register", "--dry-run"])
    _log(
        monkeypatch,
        decision_line("2026-03-01T09:00:00+01:00", "lock-date", "spk-001", "ada"),
    )

    assert cli.register() == 0

    out = capsys.readouterr().out
    assert "| 2026-03-01 | lock the date of | spk-001 | ada |" in out
    assert not (tmp_path / REGISTER_PATH).exists()


def test_register_reports_a_history_it_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["convener-register"])
    _log(monkeypatch, "", error="not a git repository")

    assert cli.register() == 1

    assert "cannot read the commit history" in capsys.readouterr().err
    assert not (tmp_path / REGISTER_PATH).exists()


def test_git_log_returns_lines_this_module_can_parse() -> None:
    """The one test that runs git, so the format string cannot drift unnoticed."""
    from convener_ops.paths import repo_root

    root = repo_root()
    if not (root / ".git").exists():
        pytest.skip("not a git checkout")

    log, error = cli._git_log(root)

    assert error == ""
    assert log.strip()
    for line in log.splitlines():
        assert "\x1f" in line
