"""The watchdog for the failure the other four cannot see.

Every other module in `maintenance/` recomputes its signal from something
this repository holds, and each of those tests can therefore build the
world it measures. This one reads a declaration, because an expiry cannot
be recomputed from anything — so what is worth holding here is the reading
itself: that a malformed date is refused rather than repaired, that the
window has the boundaries it claims, and that a file nobody wrote is an
ordinary state which nonetheless *says so*.

That last one is the reason this module exists at all. A silent watchdog
and a healthy one look identical from outside, and the credential this was
built for -- the meeting token -- fails silently by design.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from convener_ops.cli.maintenance import check_credential_expiry
from convener_ops.maintenance import credential_expiry

TODAY = date(2026, 9, 12)


def entry(secret: str, expires: str) -> dict[str, str]:
    return {
        "secret": secret,
        "expires": expires,
        "renewed_by": "docs/operating/operations.md, Meeting platform",
    }


def renewals(*rows: dict[str, str]) -> list[credential_expiry.Renewal]:
    return credential_expiry.from_data({"v": 1, "renewals": list(rows)})


# ------------------------------------------------------------------ #
# Reading the declaration: refusing rather than repairing.
# ------------------------------------------------------------------ #


def test_an_absent_declaration_is_no_renewals_and_no_error(tmp_path: Path) -> None:
    """The state every duplicate starts in. It has minted nothing, so there
    is nothing to declare, and a watchdog that treated that as a fault
    would fire on every instance from its first commit."""
    assert credential_expiry.load(tmp_path) == []


def test_a_declaration_with_no_renewals_key_reads_as_none() -> None:
    assert credential_expiry.from_data({"v": 1}) == []
    assert credential_expiry.from_data(None) == []


def test_a_date_that_is_not_a_date_is_refused_by_name() -> None:
    """Named, because the operator who has to fix it is reading a run's log
    rather than a traceback."""
    with pytest.raises(ValueError, match="CONVENER_MEETING_API_TOKEN"):
        renewals(entry("CONVENER_MEETING_API_TOKEN", "October 13th"))


def test_a_date_in_another_order_is_refused_rather_than_guessed() -> None:
    """`13-10-2026` is a real date in one convention and nonsense in the
    other, and guessing which would put the notice five weeks out."""
    with pytest.raises(ValueError, match="ISO 8601"):
        renewals(entry("CONVENER_MEETING_API_TOKEN", "13-10-2026"))


def test_an_entry_with_no_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="names no secret"):
        credential_expiry.from_data(
            {"renewals": [{"expires": "2026-10-13", "renewed_by": "operations.md"}]}
        )


def test_an_entry_that_says_nothing_about_renewing_is_refused() -> None:
    """A date with no procedure beside it is a reminder to do something
    nobody has written down, which is the state this whole module exists to
    leave rather than to reproduce."""
    with pytest.raises(ValueError, match="says nothing about how"):
        credential_expiry.from_data(
            {
                "renewals": [
                    {"secret": "CONVENER_MEETING_API_TOKEN", "expires": "2026-10-13"}
                ]
            }
        )


def test_a_renewals_value_of_the_wrong_shape_is_refused() -> None:
    with pytest.raises(ValueError, match="has to be a list"):
        credential_expiry.from_data({"renewals": "CONVENER_MEETING_API_TOKEN"})


# ------------------------------------------------------------------ #
# The window, at its edges.
# ------------------------------------------------------------------ #


def test_a_date_on_the_last_day_of_the_window_is_inside_it() -> None:
    """Fourteen days, inclusive. A boundary read the other way would make
    the notice thirteen days, which is not what the constant says."""
    inside = renewals(entry("A", str(date(2026, 9, 26))))
    assert len(credential_expiry.due(inside, TODAY)) == 1


def test_a_date_one_day_past_the_window_is_outside_it() -> None:
    outside = renewals(entry("A", str(date(2026, 9, 27))))
    assert credential_expiry.due(outside, TODAY) == []


def test_a_date_already_past_is_a_finding_and_says_it_expired() -> None:
    fired = credential_expiry.due(renewals(entry("A", "2026-09-10")), TODAY)
    assert [finding.expired for finding in fired] == [True]
    assert fired[0].days_left == -2


def test_findings_come_out_most_urgent_first() -> None:
    """The first line of a notice is the one to act on, not whichever was
    declared first."""
    fired = credential_expiry.due(
        renewals(
            entry("LATER", "2026-09-24"),
            entry("EXPIRED", "2026-09-10"),
            entry("SOONER", "2026-09-14"),
        ),
        TODAY,
    )
    assert [finding.renewal.secret for finding in fired] == [
        "EXPIRED",
        "SOONER",
        "LATER",
    ]


# ------------------------------------------------------------------ #
# What a run's log says, which is the half a silent watchdog gets wrong.
# ------------------------------------------------------------------ #


def test_an_empty_declaration_says_nothing_is_being_watched() -> None:
    """The distinction this module exists for: "nothing is due" and
    "nothing was looked at" are the same silence otherwise, and only one of
    them is good news."""
    said = credential_expiry.summary([], [], TODAY)
    assert "declares no renewal dates" in said
    assert "never wrote them down" in said


def test_a_healthy_declaration_says_how_many_it_read_and_what_is_next() -> None:
    declared = renewals(entry("A", "2027-07-15"), entry("B", "2026-12-01"))
    said = credential_expiry.summary(declared, [], TODAY)
    assert "2 declared renewal date(s)" in said
    assert "2026-12-01" in said


def test_the_notice_names_the_secret_the_date_and_where_the_procedure_is() -> None:
    fired = credential_expiry.due(
        renewals(entry("CONVENER_MEETING_API_TOKEN", "2026-09-20")), TODAY
    )
    said = credential_expiry.message(fired, TODAY)
    assert "CONVENER_MEETING_API_TOKEN" in said
    assert "2026-09-20" in said
    assert "operations.md" in said
    assert "8 day(s)" in said


def test_an_expired_one_annotates_as_error_and_a_coming_one_as_warning() -> None:
    """Two severities, because a run's own summary is where this is read
    first and the two call for different things that morning."""
    fired = credential_expiry.due(
        renewals(entry("GONE", "2026-09-10"), entry("SOON", "2026-09-20")), TODAY
    )
    lines = credential_expiry.annotation_lines(fired)
    assert lines[0].startswith("::error::")
    assert lines[1].startswith("::warning::")


# ------------------------------------------------------------------ #
# The file this repository ships, and why it is empty.
# ------------------------------------------------------------------ #


def test_this_repository_ships_the_declaration_and_declares_nothing_in_it() -> None:
    """Empty on purpose, and held here so that nobody fills it in with a
    worked date: this repository's instance is invented and holds no
    credential that expires, so a shipped date would go stale and every
    duplicate would inherit an alarm about a token nobody ever minted.

    The shape a reader needs is in the file's own header instead, where an
    operator meets it at the moment of writing the first entry."""
    from convener_ops.declaration.paths import repo_root

    path = repo_root() / credential_expiry.RENEWALS_PATH
    assert path.is_file()
    assert credential_expiry.load() == []
    assert "renewed_by:" in path.read_text(encoding="utf-8")


# ------------------------------------------------------------------ #
# The command the daily job runs.
# ------------------------------------------------------------------ #


class _FixedDatetime:
    """A stand-in for the `datetime` class `cli/maintenance.py` imports,
    whose `now()` always returns the same instant -- the same idiom
    `test_routing_watch.py::_FixedDatetime` uses."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self, tz: Any = None) -> datetime:
        return self._fixed


def _repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, declared: str | None
) -> Path:
    if declared is not None:
        path = tmp_path / credential_expiry.RENEWALS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(declared, encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("CONVENER_NOTIFY_THREAD", raising=False)
    monkeypatch.delenv("CONVENER_NOTIFY_MENTION", raising=False)
    monkeypatch.setattr(
        "convener_ops.cli.maintenance.datetime",
        _FixedDatetime(datetime(2026, 9, 12, 9, 0, tzinfo=UTC)),
    )
    return tmp_path


def _outputs(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        values[key] = value
    return values


def _github_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return out


def test_a_credential_inside_the_window_fires_and_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The case this was built for: the meeting token, a week out, on an
    instance where nothing else would say so."""
    _repo(
        tmp_path,
        monkeypatch,
        "v: 1\nrenewals:\n"
        "  - secret: CONVENER_MEETING_API_TOKEN\n"
        "    expires: 2026-09-20\n"
        "    renewed_by: docs/operating/operations.md, Meeting platform\n",
    )
    out = _github_output(tmp_path, monkeypatch)

    assert check_credential_expiry() == 0
    assert _outputs(out)["renewal_alert"] == "true"
    printed = capsys.readouterr().out
    assert "::warning::CONVENER_MEETING_API_TOKEN" in printed
    assert "2026-09-20" in printed


def test_a_healthy_declaration_is_quiet_but_still_says_what_it_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An alarm that cries wolf about a working repository costs more
    credibility than this failure costs anybody -- and a run that says
    nothing at all cannot be told from one that looked at nothing."""
    _repo(
        tmp_path,
        monkeypatch,
        "v: 1\nrenewals:\n"
        "  - secret: CONVENER_RETENTION_TOKEN\n"
        "    expires: 2027-07-15\n"
        "    renewed_by: docs/operating/operations.md\n",
    )
    out = _github_output(tmp_path, monkeypatch)

    assert check_credential_expiry() == 0
    assert _outputs(out)["renewal_alert"] == "false"
    printed = capsys.readouterr().out
    assert "1 declared renewal date(s)" in printed
    assert "::warning::" not in printed


def test_an_instance_declaring_nothing_is_quiet_and_says_that_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every duplicate starts here, so this must not fire -- and it must
    not be silent either, or a repository nobody ever wrote a date into
    reads exactly like a healthy one."""
    _repo(tmp_path, monkeypatch, None)
    out = _github_output(tmp_path, monkeypatch)

    assert check_credential_expiry() == 0
    assert _outputs(out)["renewal_alert"] == "false"
    assert "declares no renewal dates" in capsys.readouterr().out


def test_a_declaration_that_cannot_be_read_is_this_repository_s_own_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """1 rather than 0, and the split is the one the three alarms beside it
    use: a finding is the workflow's to turn red, and a broken declaration
    is the command's."""
    _repo(
        tmp_path,
        monkeypatch,
        "v: 1\nrenewals:\n  - secret: A\n    expires: soon\n    renewed_by: x\n",
    )
    _github_output(tmp_path, monkeypatch)

    assert check_credential_expiry() == 1
    assert "::error::" in capsys.readouterr().err
