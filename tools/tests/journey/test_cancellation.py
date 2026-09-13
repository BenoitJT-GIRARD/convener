"""Telling the registrants of a cancelled edition.

The decisions are pure and live in `journey/cancellation.py`; what reads a
file or sends a message is in `cli/journey/cancellation.py` and is read at the
bottom of this module. The division is the one the rest of the journey keeps,
and here it earns its keep twice: the message somebody receives is a function
of two arguments and can be read as one, and the guard that refuses to send
for an edition that is not cancelled can be exercised without an SMTP host.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from convener_ops.journey import cancellation
from convener_ops.journey.confirmation import EventDetails
from convener_ops.journey.platform import Room
from convener_ops.journey.registration import Registration

EVENT = EventDetails(
    title="On analytical engines",
    date="2026-09-17",
    room=Room(join_url="", instructions="Join online: https://example.test/room"),
)


def _registration(
    email: str = "ada@example.test", first_name: str = "Ada"
) -> Registration:
    return Registration(
        first_name=first_name,
        surname="Lovelace",
        email=email,
        institution="",
        membership_opt_in=False,
    )


def _edition(event_id: str, status: str = "cancelled") -> dict[str, Any]:
    return {"id": event_id, "status": status}


# ------------------------------------------------------------------ #
# Which editions are still owed a message.
# ------------------------------------------------------------------ #


def test_a_cancelled_edition_nobody_has_written_to_is_waiting() -> None:
    assert cancellation.pending([_edition("mrg-042")], {}) == ("mrg-042",)


def test_one_already_in_the_ledger_is_not_waiting_again() -> None:
    """The whole reason the ledger exists. A re-run -- a rejected push, a
    catch-up schedule, somebody pressing the button twice -- must not reach
    two hundred people a second time."""
    told = {"mrg-042": date(2026, 9, 14)}
    assert cancellation.pending([_edition("mrg-042")], told) == ()


@pytest.mark.parametrize("status", ["scheduled", "delivered", "archived", "lead"])
def test_an_edition_that_was_not_cancelled_is_never_waiting(status: str) -> None:
    """The dangerous direction. Telling the registrants of a scheduled
    edition that it is off would empty a room for a talk that is going
    ahead, and nothing downstream could undo it."""
    assert cancellation.pending([_edition("mrg-042", status)], {}) == ()


def test_the_id_is_read_the_way_every_other_reader_reads_it() -> None:
    assert cancellation.pending([_edition("MRG-042")], {}) == ("mrg-042",)
    assert cancellation.pending([_edition("MRG-042")], {"mrg-042": date.today()}) == ()


# ------------------------------------------------------------------ #
# The ledger.
# ------------------------------------------------------------------ #


def test_an_absent_ledger_means_nobody_has_been_told() -> None:
    """`None` is what an instance that has never cancelled anything has, and
    it must read as "tell everybody" rather than as an error -- the file is
    created by the first cancellation, not by standing up."""
    assert cancellation.ledger_from_data(None) == {}
    assert cancellation.ledger_from_data({"v": 1}) == {}


def test_a_ledger_that_cannot_be_read_is_refused() -> None:
    """Refused rather than treated as empty. An unreadable ledger read as
    empty would send a second message to everybody it had already reached."""
    with pytest.raises(ValueError, match="not a mapping"):
        cancellation.ledger_from_data([1, 2, 3])
    with pytest.raises(ValueError, match="has to be a list"):
        cancellation.ledger_from_data({"cancellations": "mrg-042"})
    with pytest.raises(ValueError, match="names no event"):
        cancellation.ledger_from_data({"cancellations": [{"told_on": date.today()}]})
    with pytest.raises(ValueError, match="not a date"):
        cancellation.ledger_from_data(
            {"cancellations": [{"event": "mrg-042", "told_on": "yesterday"}]}
        )


def test_the_ledger_round_trips_and_sorts() -> None:
    """Sorted so a diff reads as one line added rather than a file
    reordered: this file is reviewed in ordinary pull requests."""
    told = {"mrg-042": date(2026, 9, 14), "mrg-007": date(2026, 3, 1)}
    data = cancellation.ledger_to_data(told)
    assert [row["event"] for row in data["cancellations"]] == ["mrg-007", "mrg-042"]
    assert cancellation.ledger_from_data(data) == told


def test_recording_twice_keeps_the_day_they_were_told() -> None:
    """Not the day of the re-run. The record is when the people heard."""
    told = {"mrg-042": date(2026, 9, 14)}
    assert cancellation.recorded(told, "mrg-042", date(2026, 12, 1)) == told


# ------------------------------------------------------------------ #
# The message.
# ------------------------------------------------------------------ #


def test_the_first_line_says_it_is_off() -> None:
    """Somebody scanning a subject line and one sentence on a phone must not
    have to read to the end to learn that they should not turn up."""
    message = cancellation.compose(_registration(), EVENT)

    assert "Cancelled" in message.subject
    assert "On analytical engines" in message.subject
    body = message.body.split("\n")
    assert body[0] == "Dear Ada,"
    assert "has been cancelled" in body[2]
    assert "will not take place" in body[2]


def test_it_never_says_why() -> None:
    """The reason is in the register, in a closed vocabulary, and none of its
    four values is anybody's business but the series'. "The speaker withdrew"
    is a fact about a person who did not agree to it being mailed to two
    hundred strangers."""
    body = cancellation.compose(_registration(), EVENT).body

    for reason in ("speaker", "withdrew", "board", "unworkable", "paused"):
        assert reason not in body.lower(), reason


def test_it_says_what_becomes_of_what_they_gave() -> None:
    """A registrant handed over a name and an address on a promise about
    retention. A cancellation is exactly when somebody wonders what happened
    to it, and exactly when nothing would otherwise say."""
    body = cancellation.compose(_registration(), EVENT).body

    assert "encrypted" in body
    assert "destroyed" in body


def test_it_is_addressed_to_the_person_and_deterministic() -> None:
    """Deterministic in both arguments, like `confirmation.compose`: a re-run
    that reaches somebody twice reaches them with the identical message
    rather than a second, differently-worded one."""
    first = cancellation.compose(_registration(), EVENT)
    second = cancellation.compose(_registration(), EVENT)

    assert first.to == "ada@example.test"
    assert first == second


def test_one_message_per_registration_in_the_order_taken() -> None:
    people = [
        _registration("a@example.test", "Ada"),
        _registration("b@example.test", "Bea"),
    ]
    messages = cancellation.every_registrant(people, EVENT)

    assert [m.to for m in messages] == ["a@example.test", "b@example.test"]


# ------------------------------------------------------------------ #
# What a run says.
# ------------------------------------------------------------------ #


def test_nobody_to_tell_is_said_out_loud() -> None:
    """The commonest case by far -- most cancellations happen before anybody
    has signed up -- and the one a silent run makes indistinguishable from a
    run that could not read the file."""
    assert "nobody had registered" in cancellation.summary("mrg-042", 0, 0, 0)


def test_what_could_not_be_sent_is_counted_rather_than_swallowed() -> None:
    said = cancellation.summary("mrg-042", 12, 1, 2)

    assert "12 told" in said
    assert "1 could not be sent" in said
    assert "2 entry(ies) could not be read" in said


# ------------------------------------------------------------------ #
# The command, and the guard that matters.
# ------------------------------------------------------------------ #


def _instance(tmp_path: Path, status: str) -> Path:
    data = tmp_path / "instance" / "data"
    data.mkdir(parents=True)
    (data / "speakers.yml").write_text(
        f"- id: mrg-042\n  name: A Speaker\n  status: {status}\n",
        encoding="utf-8",
    )
    (data / "config.yml").write_text("v: 1\n", encoding="utf-8")
    return tmp_path


def test_the_command_refuses_an_edition_that_is_not_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guard the whole design rests on. A run that wrote to the
    registrants of a *scheduled* edition would tell a room full of people not
    to come to a talk that is going ahead, and no later step could take it
    back. So the status is read again here, from the file, rather than
    trusted from whatever handed this command an id.
    """
    from convener_ops.cli.journey import cancellation as command

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(_instance(tmp_path, "scheduled")))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert command.tell_cancelled([]) == 1
    assert "not 'cancelled'" in capsys.readouterr().err


def test_the_command_reports_an_edition_nobody_registered_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Zero, not an error. A command that exited non-zero on the commonest
    case would leave a red Actions tab for a series doing nothing wrong,
    which is how an operator learns to stop reading that tab."""
    from convener_ops.cli.journey import cancellation as command

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(_instance(tmp_path, "cancelled")))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert command.tell_cancelled([]) == 0
    assert "nobody had registered" in capsys.readouterr().out


def test_recording_writes_the_ledger_and_repeats_harmlessly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from convener_ops.cli.journey import cancellation as command

    root = _instance(tmp_path, "cancelled")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert command.record_cancellation([]) == 0
    ledger = root / cancellation.LEDGER_PATH
    first = ledger.read_text(encoding="utf-8")
    assert "mrg-042" in first

    assert command.record_cancellation([]) == 0
    assert ledger.read_text(encoding="utf-8") == first


def test_the_command_needs_an_event_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from convener_ops.cli.journey import cancellation as command

    monkeypatch.delenv("EVENT_ID", raising=False)
    assert command.tell_cancelled([]) == 1
    assert "no event id" in capsys.readouterr().err
    assert os.environ.get("EVENT_ID") is None
