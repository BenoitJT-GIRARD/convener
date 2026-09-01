"""A registration that took the slow lane, from the queue to the e-mail.

`test_submission_queue.py` holds the queue's mechanism; this
file holds the second kind that now travels through it, and the one thing
the survey response never needed: **the confirmation has to go out exactly
once, after the record has landed, and the entry may not be cleared until
it has.**

Every property here is driven rather than reasoned about -- an interruption
is played out step by step and the next drain's result asserted, never
inferred from reading the ordering. Two of these tests found real defects
while they were being written; the comments say which.

Nothing here touches the network, and nothing here decrypts into anything
this file then prints: `_LEAK_STRINGS` is checked against every job's own
output, the same discipline `tools/tests/cli/journey/` holds every
decrypting command
to.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import config, speaker

from convener_ops.cli.journey.registration import (
    confirm_queued_registrations,
    drain_queue,
    plan_queue_drain,
    send_confirmation,
)
from convener_ops.journey import confirmation, eventkeys, registration, submission_queue
from convener_ops.journey.submission_queue import (
    REGISTRATION_KIND,
    SURVEY_KIND,
    drain,
    entry_path,
    plan_drain,
)

_EVENT = "mrg-042"

#: Everything that would identify Ada personally in the fixture below. No
#: job in this path may print any of it, on any branch.
_LEAK_STRINGS = ("Ada", "Lovelace", "ada@example.org", "Analytical Engines")

#: The room link the confirmation carries. `_repo` puts it on the
#: speaker record so the two lanes can be compared on the one field
#: this e-mail is the only channel for.
_ROOM_LINK = "https://meet.example.org/mrg-042-room"


def _fields(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "first_name": "Ada",
        "surname": "Lovelace",
        "email": "ada@example.org",
        "institution": "Analytical Engines Institute",
        "membership_opt_in": True,
    }
    base.update(overrides)
    return base


def _envelope(event_id: str, public_pem: str, **overrides: Any) -> str:
    """The whole body `services/signup-relay/src/index.js` writes to the
    queue for a far-lane registration -- byte for byte what it received
    from the browser."""
    plaintext = json.dumps(_fields(**overrides)).encode("utf-8")
    envelope = json.loads(eventkeys.encrypt(public_pem, plaintext))
    return json.dumps({"event_id": event_id, **envelope})


def _name(stamp: str = "m0000001", kind: str = REGISTRATION_KIND) -> str:
    return entry_path(kind, f"{stamp}-{uuid.uuid4()}")


def _always_open(_event_id: str) -> bool:
    return True


def _stored(outcome: submission_queue.DrainOutcome, event_id: str = _EVENT) -> str:
    return outcome.files[submission_queue.registrations_path(event_id)]


# ------------------------------------------------------------------ #
# 1 - the pure arithmetic: storing, and what is left to do afterwards
# ------------------------------------------------------------------ #


def test_a_queued_registration_is_stored_and_left_waiting_for_its_e_mail() -> None:
    private_pem, public_pem = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}

    plan = plan_drain(entries, frozenset(), _always_open)
    outcome = drain(plan, {_EVENT: private_pem}, {}, frozenset(), entries)

    # Stored, and in the ledger, so a replay cannot record it twice.
    assert submission_queue.registrations_path(_EVENT) in outcome.files
    assert outcome.ledger == (name,)
    # And deliberately *not* cleared: the entry stays in the queue until
    # its confirmation has actually been attempted.
    assert outcome.clear == ()
    assert [item.name for item in outcome.confirm] == [name]
    assert outcome.confirm[0].event_id == _EVENT
    assert outcome.confirm[0].changed == ()


def test_the_stored_file_is_the_one_the_immediate_lane_writes() -> None:
    """Not a second format for the slow lane: the same
    `registrations.enc`, written by the same `registration.upsert`, so a
    participant who registered before the announcement and one who
    registered on the morning are one list, not two."""
    private_pem, public_pem = eventkeys.generate()
    entries = {_name(): _envelope(_EVENT, public_pem)}
    plan = plan_drain(entries, frozenset(), _always_open)
    outcome = drain(plan, {_EVENT: private_pem}, {}, frozenset(), entries)

    file = registration.load_registration_file(_stored(outcome))
    found = registration.find_by_email(file, "ada@example.org", private_pem)
    assert found is not None
    assert found.surname == "Lovelace"


def test_a_registration_and_its_update_in_one_drain_give_what_two_drains_gave() -> None:
    """The property a single drain has to hold outright. Applied in name
    order, which is submission order, so the later entry wins -- and the confirmation
    for it names what changed, exactly as `registration.yml` would have."""
    private_pem, public_pem = eventkeys.generate()
    first, second = _name("m0000001"), _name("m0000002")
    entries = {
        first: _envelope(_EVENT, public_pem),
        second: _envelope(_EVENT, public_pem, institution="Difference Engines"),
    }

    together = drain(
        plan_drain(entries, frozenset(), _always_open),
        {_EVENT: private_pem},
        {},
        frozenset(),
        entries,
    )

    # Separately: drain the first, then the second against what the first
    # wrote -- the real sequence two days would produce.
    one = {first: entries[first]}
    step_one = drain(
        plan_drain(one, frozenset(), _always_open),
        {_EVENT: private_pem},
        {},
        frozenset(),
        one,
    )
    two = {second: entries[second]}
    step_two = drain(
        plan_drain(two, frozenset(), _always_open),
        {_EVENT: private_pem},
        {submission_queue.registrations_path(_EVENT): _stored(step_one)},
        frozenset(),
        two,
    )

    for text in (_stored(together), _stored(step_two)):
        file = registration.load_registration_file(text)
        # One entry, not two: `upsert` matched the same address.
        assert len(file.entries) == 1
        found = registration.find_by_email(file, "ada@example.org", private_pem)
        assert found is not None
        assert found.institution == "Difference Engines"

    # And the same two confirmations, carrying the same diff.
    assert [item.changed for item in together.confirm] == [(), ("institution",)]
    assert step_one.confirm[0].changed == ()
    assert step_two.confirm[0].changed == ("institution",)


def test_a_registration_that_will_not_decrypt_is_refused_and_never_confirmed() -> None:
    private_pem, _ = eventkeys.generate()
    _, other_public = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, other_public)}

    outcome = drain(
        plan_drain(entries, frozenset(), _always_open),
        {_EVENT: private_pem},
        {},
        frozenset(),
        entries,
    )

    assert [note.name for note in outcome.refused] == [name]
    assert outcome.confirm == ()
    # Cleared, because leaving it would block the queue for ever.
    assert outcome.clear == (name,)
    assert submission_queue.registrations_path(_EVENT) not in outcome.files


def test_a_key_nobody_configured_defers_a_registration_and_clears_nothing() -> None:
    private_pem, public_pem = eventkeys.generate()
    assert private_pem
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}

    outcome = drain(
        plan_drain(entries, frozenset(), _always_open), {}, {}, frozenset(), entries
    )

    assert [note.name for note in outcome.deferred] == [name]
    assert outcome.clear == ()
    assert outcome.ledger == ()
    assert outcome.confirm == ()


def test_a_registrations_file_that_will_not_parse_defers_rather_than_refuses() -> None:
    private_pem, public_pem = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}

    outcome = drain(
        plan_drain(entries, frozenset(), _always_open),
        {_EVENT: private_pem},
        {submission_queue.registrations_path(_EVENT): "{not json"},
        frozenset(),
        entries,
    )

    assert [note.name for note in outcome.deferred] == [name]
    assert outcome.clear == ()
    assert outcome.confirm == ()


# ------------------------------------------------------------------ #
# 2 - nothing is lost, and nothing is doubled
# ------------------------------------------------------------------ #


def test_a_drain_interrupted_before_the_e_mail_confirms_without_re_storing() -> None:
    """The interruption this design exists for, driven: the drain committed
    the record and the ledger together and the job then stopped, so the
    entry is still in the queue *and* in the ledger. The next drain must
    read that as "stored, not yet confirmed" -- confirm it, and not write a
    second copy of the registration."""
    private_pem, public_pem = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}

    first = drain(
        plan_drain(entries, frozenset(), _always_open),
        {_EVENT: private_pem},
        {},
        frozenset(),
        entries,
    )
    committed = _stored(first)
    ledger = frozenset(first.ledger)

    second = drain(
        plan_drain(entries, ledger, _always_open),
        {_EVENT: private_pem},
        {submission_queue.registrations_path(_EVENT): committed},
        ledger,
        entries,
    )

    # Nothing re-stored -- the drain wrote no file at all this time.
    assert second.files == {}
    # But the confirmation is still owed, and is now sent.
    assert [item.name for item in second.confirm] == [name]
    # With no diff: the entry it would have been computed against was
    # overwritten by the drain that stored it, and a resend repeats the
    # current registration rather than describing an update to it.
    assert second.confirm[0].changed == ()
    # Still not cleared here: the confirming step is what clears it.
    assert second.clear == ()
    # And still in the ledger, because it is still in the queue.
    assert second.ledger == (name,)


def test_once_cleared_a_replayed_drain_does_nothing_at_all() -> None:
    private_pem, public_pem = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}
    first = drain(
        plan_drain(entries, frozenset(), _always_open),
        {_EVENT: private_pem},
        {},
        frozenset(),
        entries,
    )

    # The confirming step cleared it, so the queue is empty next time.
    ledger = frozenset(first.ledger)
    replayed = drain(
        plan_drain({}, ledger, _always_open),
        {_EVENT: private_pem},
        {},
        ledger,
        {},
    )

    assert replayed.files == {}
    assert replayed.confirm == ()
    # The ledger forgets it: nothing can bring that entry id back.
    assert replayed.ledger == ()


def test_a_registration_never_shares_a_ledger_entry_with_a_survey_response() -> None:
    """Both kinds in one drain, both handled, and the survey response is
    cleared while the registration waits for its e-mail."""
    private_pem, public_pem = eventkeys.generate()
    reg = _name("m0000001")
    survey_name = _name("m0000002", kind=SURVEY_KIND)
    from convener_ops.journey import survey as survey_module

    plaintext = json.dumps(
        {"overall_rating": 5, "recommend": True, "feedback": "Loved it."}
    ).encode("utf-8")
    survey_body = json.dumps(
        {
            "event_id": _EVENT,
            **json.loads(eventkeys.encrypt(public_pem, survey_module._pad(plaintext))),
        }
    )
    entries = {reg: _envelope(_EVENT, public_pem), survey_name: survey_body}

    outcome = drain(
        plan_drain(entries, frozenset(), _always_open),
        {_EVENT: private_pem},
        {},
        frozenset(),
        entries,
    )

    assert outcome.clear == (survey_name,)
    assert [item.name for item in outcome.confirm] == [reg]
    assert set(outcome.ledger) == {reg, survey_name}
    assert submission_queue.responses_path(_EVENT) in outcome.files
    assert submission_queue.registrations_path(_EVENT) in outcome.files


# ------------------------------------------------------------------ #
# 3 - the scarce slots, now shared
# ------------------------------------------------------------------ #


def test_a_waiting_registration_takes_a_slot_before_a_survey_only_event() -> None:
    """The competition two kinds of submission create, and the answer this
    picked. The two
    kinds do not lose the same thing by waiting: a deferred survey response
    costs its submitter nothing, a deferred registration spends one of the
    two drain periods the floor reserves for a dropped run."""
    _, public_pem = eventkeys.generate()
    entries: dict[str, str] = {}
    # `max_events` survey-only events arrive first, then one event with a
    # registration. Purely by age, the registration would lose.
    for index in range(1, submission_queue.MAX_EVENTS_PER_DRAIN + 1):
        envelope = json.loads(eventkeys.encrypt(public_pem, b"x" * 8))
        entries[_name(f"m000000{index}", kind=SURVEY_KIND)] = json.dumps(
            {"event_id": f"mrg-1{index:02d}", **envelope}
        )
    late = _name("m0000099")
    entries[late] = _envelope(_EVENT, public_pem)

    plan = plan_drain(entries, frozenset(), _always_open)

    assert _EVENT in plan.event_ids
    assert len(plan.event_ids) == submission_queue.MAX_EVENTS_PER_DRAIN
    # The one displaced event is deferred, never dropped, and reported.
    assert plan.deferred
    assert all(note.name != late for note in plan.deferred)


def test_a_registration_awaiting_confirmation_still_costs_its_event_a_slot() -> None:
    """It has to: the message can only be composed from the plaintext, and
    only that event's own key opens it. An entry the plan could not give a
    slot to is deferred and confirmed next time, never silently skipped."""
    _, public_pem = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}

    plan = plan_drain(entries, frozenset({name}), _always_open)

    assert plan.handle == ()
    assert [entry.name for entry in plan.confirm_only] == [name]
    assert plan.event_ids == (_EVENT,)
    assert plan.already_handled == ()


def test_an_unreadable_entry_the_ledger_holds_is_still_just_cleared() -> None:
    name = entry_path(REGISTRATION_KIND, "not-an-entry-id")
    plan = plan_drain({name: "{}"}, frozenset({name}), _always_open)
    assert plan.already_handled == (name,)
    assert plan.confirm_only == ()


# ------------------------------------------------------------------ #
# 4 - the two console scripts, against a real repository root
# ------------------------------------------------------------------ #


def _repo(tmp_path: Path, event_id: str = _EVENT) -> tuple[str, str]:
    (tmp_path / "instance" / "data").mkdir(parents=True)
    (tmp_path / "instance" / "data" / "speakers.yml").write_text(
        yaml.safe_dump(
            [
                speaker(
                    edition_code=event_id.upper(),
                    date="2026-09-24",
                    time="12:30",
                    status="scheduled",
                    zoom_link=_ROOM_LINK,
                )
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "instance" / "data" / "config.yml").write_text(
        yaml.safe_dump(config()), encoding="utf-8"
    )
    return eventkeys.generate()


def _queue_file(queue_dir: Path, name: str, body: str) -> None:
    path = queue_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_the_two_scripts_store_then_confirm_and_only_then_allow_a_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end through the real console scripts, in the order the
    workflow runs them -- the ordering *is* the correctness, so it is
    driven rather than asserted from the YAML."""
    private_pem, public_pem = _repo(tmp_path)
    queue_dir = tmp_path / "queue-export"
    name = _name()
    _queue_file(queue_dir, name, _envelope(_EVENT, public_pem))

    clear_file = tmp_path / "clear.txt"
    confirm_file = tmp_path / "confirm.txt"
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(queue_dir))
    monkeypatch.setenv("CONVENER_QUEUE_CLEAR_FILE", str(clear_file))
    monkeypatch.setenv("CONVENER_QUEUE_CONFIRM_FILE", str(confirm_file))
    monkeypatch.setenv("CONVENER_QUEUE_EVENT_1", _EVENT)
    monkeypatch.setenv("CONVENER_QUEUE_KEY_1", private_pem)
    for slot in range(2, submission_queue.MAX_EVENTS_PER_DRAIN + 1):
        monkeypatch.setenv(f"CONVENER_QUEUE_EVENT_{slot}", "")
        monkeypatch.setenv(f"CONVENER_QUEUE_KEY_{slot}", "")

    assert drain_queue() == 0
    drained = capsys.readouterr().out
    # Stored, and nothing to clear yet: the confirmation is still owed.
    assert (tmp_path / submission_queue.registrations_path(_EVENT)).exists()
    assert clear_file.read_text(encoding="utf-8") == ""
    assert confirm_file.read_text(encoding="utf-8").startswith(f"{name}\t")

    assert confirm_queued_registrations() == 0
    confirmed = capsys.readouterr().out
    # Now, and only now, the entry may be cleared.
    assert clear_file.read_text(encoding="utf-8") == f"{name}\n"
    assert "1 queued registration(s) confirmed" in confirmed
    # No transport is configured here -- this project's ordinary state --
    # so the message is reported, never delivered, and the entry is
    # cleared regardless. A queue that only emptied on a configured mailer
    # would alarm every single day.
    assert "not sent" in confirmed

    for leaked in _LEAK_STRINGS:
        assert leaked.lower() not in drained.lower()
        assert leaked.lower() not in confirmed.lower()


def test_the_confirming_script_leaves_an_entry_whose_key_is_missing_in_the_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rescue property, one step further on than the queue proves it: a
    confirmation that could not be composed must not clear the entry that
    still needs one."""
    _, public_pem = _repo(tmp_path)
    queue_dir = tmp_path / "queue-export"
    name = _name()
    _queue_file(queue_dir, name, _envelope(_EVENT, public_pem))
    confirm_file = tmp_path / "confirm.txt"
    confirm_file.write_text(f"{name}\t\n", encoding="utf-8")
    clear_file = tmp_path / "clear.txt"
    clear_file.write_text("", encoding="utf-8")

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(queue_dir))
    monkeypatch.setenv("CONVENER_QUEUE_CONFIRM_FILE", str(confirm_file))
    monkeypatch.setenv("CONVENER_QUEUE_CLEAR_FILE", str(clear_file))
    for slot in range(1, submission_queue.MAX_EVENTS_PER_DRAIN + 1):
        monkeypatch.setenv(f"CONVENER_QUEUE_EVENT_{slot}", "")
        monkeypatch.setenv(f"CONVENER_QUEUE_KEY_{slot}", "")

    assert confirm_queued_registrations() == 0
    out = capsys.readouterr().out
    assert "::error::" in out
    assert "still waiting" in out
    assert clear_file.read_text(encoding="utf-8") == ""


def test_the_confirming_script_sends_nothing_twice_for_an_entry_already_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An entry named on the confirm list that the queue no longer holds
    was cleared by an earlier run -- which, by this step's own ordering,
    means its confirmation already went out."""
    private_pem, _ = _repo(tmp_path)
    queue_dir = tmp_path / "queue-export"
    queue_dir.mkdir()
    name = _name()
    (tmp_path / "confirm.txt").write_text(f"{name}\t\n", encoding="utf-8")
    (tmp_path / "clear.txt").write_text("", encoding="utf-8")

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(queue_dir))
    monkeypatch.setenv("CONVENER_QUEUE_CONFIRM_FILE", str(tmp_path / "confirm.txt"))
    monkeypatch.setenv("CONVENER_QUEUE_CLEAR_FILE", str(tmp_path / "clear.txt"))
    monkeypatch.setenv("CONVENER_QUEUE_EVENT_1", _EVENT)
    monkeypatch.setenv("CONVENER_QUEUE_KEY_1", private_pem)

    assert confirm_queued_registrations() == 0
    assert "no longer in the queue, nothing sent" in capsys.readouterr().out
    assert (tmp_path / "clear.txt").read_text(encoding="utf-8") == ""


def test_the_confirming_script_refuses_to_guess_where_the_queue_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("CONVENER_QUEUE_DIR", raising=False)
    assert confirm_queued_registrations() == 1
    assert "CONVENER_QUEUE_DIR is not set" in capsys.readouterr().err


def test_the_confirming_script_says_nothing_to_do_when_the_drain_stored_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(tmp_path / "queue-export"))
    monkeypatch.setenv("CONVENER_QUEUE_CONFIRM_FILE", str(tmp_path / "absent.txt"))
    assert confirm_queued_registrations() == 0
    assert "no registration that still needs a confirmation" in capsys.readouterr().out


def test_the_plan_names_the_secret_a_queued_registration_needs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, public_pem = _repo(tmp_path)
    queue_dir = tmp_path / "queue-export"
    _queue_file(queue_dir, _name(), _envelope(_EVENT, public_pem))
    output = tmp_path / "out.txt"
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(queue_dir))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert plan_queue_drain() == 0
    values = dict(
        line.split("=", 1)
        for line in output.read_text(encoding="utf-8").splitlines()
        if line
    )
    assert values["pending"] == "true"
    assert values["event_1"] == _EVENT
    assert values["secret_1"] == eventkeys.secret_name(_EVENT)
    for leaked in _LEAK_STRINGS:
        assert leaked.lower() not in capsys.readouterr().out.lower()


# ------------------------------------------------------------------ #
# 5 - the workflow, read as text
# ------------------------------------------------------------------ #

_WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"
_SWEEP_PATH = _WORKFLOWS / "sweep-and-notify.yml"
_SWEEP = _SWEEP_PATH.read_text(encoding="utf-8")


def _step_names() -> list[str]:
    loaded = yaml.safe_load(_SWEEP)
    return [step.get("name", "") for step in loaded["jobs"]["daily"]["steps"]]


def test_the_confirmation_runs_between_the_push_and_the_clear() -> None:
    """The ordering is the whole of "no confirmation for a registration
    that is not on the branch, and no clear for one that has not been
    confirmed". Read from the parsed step order, not from a substring: a
    reordering that left every step present would otherwise pass."""
    names = _step_names()
    drain_at = names.index("Drain the submission queue")
    confirm_at = names.index("Send the confirmations the drain stored")
    clear_at = names.index("Clear what the drain handled")
    assert drain_at < confirm_at < clear_at


def test_the_confirming_step_runs_only_after_a_drain_that_pushed() -> None:
    loaded = yaml.safe_load(_SWEEP)
    step = next(
        s for s in loaded["jobs"]["daily"]["steps"] if s.get("id") == "queue-confirm"
    )
    assert "steps.queue-drain.outcome == 'success'" in step["if"]
    assert step["run"] == "uv run convener-confirm-queued-registrations"


def test_the_confirming_step_carries_the_transport_the_immediate_lane_uses() -> None:
    """The same set `registration.yml`'s own sending step reads. A queued
    registration and a dispatched one must produce the same message, and a
    missing variable here would silently make the slow lane a lane that
    only ever reports."""
    loaded = yaml.safe_load(_SWEEP)
    confirming = next(
        s for s in loaded["jobs"]["daily"]["steps"] if s.get("id") == "queue-confirm"
    )
    registration_yml = yaml.safe_load(
        (_WORKFLOWS / "registration.yml").read_text(encoding="utf-8")
    )
    immediate = next(
        s
        for s in registration_yml["jobs"]["handle"]["steps"]
        if s.get("name") == "Send the registration confirmation"
    )
    wanted = {
        name
        for name in immediate["env"]
        if name.startswith("CONVENER_SMTP_")
        or name in {"CONVENER_MATCHING_SALT", "CONVENER_MEETING_API_TOKEN"}
    }
    assert wanted <= set(confirming["env"])


def test_the_drain_hands_the_confirming_step_the_list_it_wrote() -> None:
    loaded = yaml.safe_load(_SWEEP)
    steps = {s.get("id"): s for s in loaded["jobs"]["daily"]["steps"]}
    written = steps["queue-drain"]["env"]["CONVENER_QUEUE_CONFIRM_FILE"]
    read = steps["queue-confirm"]["env"]["CONVENER_QUEUE_CONFIRM_FILE"]
    assert written == read
    # And both steps append to the one clear list the clearing step reads.
    assert (
        steps["queue-drain"]["env"]["CONVENER_QUEUE_CLEAR_FILE"]
        == steps["queue-confirm"]["env"]["CONVENER_QUEUE_CLEAR_FILE"]
        == steps["queue-clear"]["env"]["CLEAR_FILE"]
    )


def test_the_confirming_step_spends_no_slot_the_drain_did_not_select() -> None:
    loaded = yaml.safe_load(_SWEEP)
    steps = {s.get("id"): s for s in loaded["jobs"]["daily"]["steps"]}
    for slot in range(1, submission_queue.MAX_EVENTS_PER_DRAIN + 1):
        for prefix in ("CONVENER_QUEUE_EVENT_", "CONVENER_QUEUE_KEY_"):
            assert (
                steps["queue-confirm"]["env"][f"{prefix}{slot}"]
                == steps["queue-drain"]["env"][f"{prefix}{slot}"]
            )
    beyond = submission_queue.MAX_EVENTS_PER_DRAIN + 1
    assert f"CONVENER_QUEUE_EVENT_{beyond}" not in steps["queue-confirm"]["env"]


def test_both_lanes_hand_the_confirmation_the_identical_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The equivalence the whole two-lane design rests on: **a queued
    registration's confirmation must be the same e-mail a dispatched one
    produces**, room link and matching code included, or the slow lane has
    quietly become a different experience rather than a later one.

    Driven by composing the real message on both paths and comparing the
    rendered text -- `convener-send-confirmation` (what `registration.yml` runs
    for the immediate lane) against `convener-confirm-queued-registrations`
    (what the drain runs for the slow one) -- over the same payload, the
    same event and the same salt.
    """
    private_pem, public_pem = _repo(tmp_path)
    payload = _envelope(_EVENT, public_pem)

    composed: list[str] = []

    def _capture(message: object, _env: object) -> object:
        composed.append(f"{message.subject}\n{message.body}")  # type: ignore[attr-defined]
        return confirmation.SendResult(sent=False)

    monkeypatch.setattr(confirmation, "deliver", _capture)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "a-salt-for-the-test")

    # The immediate lane, exactly as registration.yml runs it.
    monkeypatch.setenv("REGISTRATION_PAYLOAD", payload)
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CHANGED_FIELDS", "")
    assert send_confirmation() == 0

    # The slow lane, exactly as the drain's own step runs it.
    queue_dir = tmp_path / "queue-export"
    name = _name()
    _queue_file(queue_dir, name, payload)
    (tmp_path / "confirm.txt").write_text(f"{name}\t\n", encoding="utf-8")
    (tmp_path / "clear.txt").write_text("", encoding="utf-8")
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(queue_dir))
    monkeypatch.setenv("CONVENER_QUEUE_CONFIRM_FILE", str(tmp_path / "confirm.txt"))
    monkeypatch.setenv("CONVENER_QUEUE_CLEAR_FILE", str(tmp_path / "clear.txt"))
    monkeypatch.setenv("CONVENER_QUEUE_EVENT_1", _EVENT)
    monkeypatch.setenv("CONVENER_QUEUE_KEY_1", private_pem)
    assert confirm_queued_registrations() == 0

    assert len(composed) == 2
    assert composed[0] == composed[1]
    # And the code really is in it -- a comparison of two empty strings
    # would otherwise pass this test without either message existing.
    code = registration.matching_code(_EVENT, "ada@example.org", "a-salt-for-the-test")
    assert code
    assert code in composed[0]
    # And the room link, the other half of what makes this message an
    # entry ticket rather than a receipt.
    assert _ROOM_LINK in composed[0]
    capsys.readouterr()
