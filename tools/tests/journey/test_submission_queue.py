"""The submission queue and the drain that empties it.

Four groups of properties, in this order:

1. **The pure arithmetic** -- `submission_queue`: what one drain plans,
   what it produces, and what the ledger remembers. Driven from fixtures
   built in this file; nothing here touches the network, which is the
   project-wide rule and the reason the plan/drain split exists at all.
2. **Nothing is lost.** Cancellation, a failed clear and a replay are each
   *driven*, not reasoned about: the sequence a real interruption produces
   is played out step by step and the result asserted.
3. **The two console scripts** -- `convener-plan-queue-drain` and
   `convener-drain-queue` -- against a real repository root on disk, including
   the "no free text a participant wrote may ever reach the job log"
   discipline `test_cli.py` holds every decrypting job to.
4. **The workflow**, read as text: that the queue steps live in the daily
   job that already runs (never a workflow or a job of their own, which
   would cost a billed run a day), that the number of secret slots equals
   `MAX_EVENTS_PER_DRAIN`, and that the branch name in the YAML is the one
   the Python constant names.

And one sweep that is none of the four: `test_no_queue_file_is_committed_
to_the_default_branch`. There is a precondition no offline test can
enforce -- that no pull request is ever opened from the queue branch -- and
this is the consequence of breaking it, one step further on, where a file
*can* be seen. It fails on the pull request that would merge the queue onto
`main`, which is where five workflows per submission would start.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import config, speaker

from convener_ops.cli import drain_queue, plan_queue_drain
from convener_ops.declaration.paths import repo_root
from convener_ops.journey import eventkeys, submission_queue, survey
from convener_ops.journey.submission_queue import (
    DrainPlan,
    Entry,
    Note,
    annotation_lines,
    drain,
    entry_path,
    ledger_from_data,
    ledger_to_data,
    next_ledger,
    plan_drain,
    queue_files_in,
    read_entry,
    responses_path,
    secret_names,
    summary,
)

_ROOT = repo_root()
_EVENT = "mrg-042"
_OTHER_EVENT = "mrg-043"

#: The one string every `_answers()` default carries. A survey response
#: holds no name and no address, but it does hold free text a participant
#: wrote, and `test_cli.py`'s own `_SURVEY_LEAK_STRINGS` made exactly this
#: point about the job it replaced: a mutant printing `response.feedback`
#: would otherwise pass every test in this file.
_LEAK_STRINGS = ("Loved the live Q&A.",)


def _answers(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "overall_rating": 5,
        "recommend": True,
        "feedback": "Loved the live Q&A.",
    }
    base.update(overrides)
    return base


def _envelope(event_id: str, public_pem: str, **overrides: Any) -> str:
    """One submission exactly as `app/src/survey/encrypt.ts` produces it and
    `services/signup-relay` forwards it -- padded to
    `survey._PLAINTEXT_PAD_BYTES`, because the browser pads before
    encrypting and the drain's own validation measures the same bytes."""
    plaintext = json.dumps(_answers(**overrides)).encode("utf-8")
    envelope = json.loads(eventkeys.encrypt(public_pem, survey._pad(plaintext)))
    return json.dumps({"event_id": event_id, **envelope})


def _name(stamp: str = "m0000001") -> str:
    """A queue entry path shaped the way the relay writes one."""
    return entry_path(submission_queue.SURVEY_KIND, f"{stamp}-{uuid.uuid4()}")


def _always_open(_event_id: str) -> bool:
    return True


def _never_open(_event_id: str) -> bool:
    return False


# ------------------------------------------------------------------ #
# 1 - the pure arithmetic
# ------------------------------------------------------------------ #


def test_read_entry_recovers_the_kind_the_id_and_the_event() -> None:
    _, public_pem = eventkeys.generate()
    name = _name()
    entry = read_entry(name, _envelope(_EVENT, public_pem))
    assert isinstance(entry, Entry)
    assert entry.kind == submission_queue.SURVEY_KIND
    assert entry.event_id == _EVENT
    assert entry.name == name


@pytest.mark.parametrize(
    ("name", "text", "reason"),
    [
        ("queue/survey/x.json/extra.json", "{}", "not a queue entry path"),
        ("notqueue/survey/a.json", "{}", "not a queue entry path"),
        ("queue/survey/no-extension", "{}", "not a queue entry path"),
        ("queue/registration/m1-" + "0" * 8, "{}", "not a queue entry path"),
        (f"queue/proposal/m1-{uuid.uuid4()}.json", "{}", "no drain serves"),
        ("queue/survey/not-an-id.json", "{}", "not shaped like one"),
        (f"queue/survey/m1-{uuid.uuid4()}.json", "not json", "no valid event id"),
        (f"queue/survey/m1-{uuid.uuid4()}.json", "[]", "no valid event id"),
        (
            f"queue/survey/m1-{uuid.uuid4()}.json",
            '{"event_id": "../../etc"}',
            "no valid event id",
        ),
    ],
    ids=[
        "too-deep",
        "wrong-root",
        "no-json-suffix",
        "no-suffix-at-all",
        "unserved-kind",
        "malformed-id",
        "not-json",
        "not-an-object",
        "hostile-event-id",
    ],
)
def test_read_entry_refuses_what_it_cannot_read_and_says_which(
    name: str, text: str, reason: str
) -> None:
    """Every refusal names the shape it declined. A reader that answered
    plausibly about a path it did not understand would be worse than no
    reader: `../../etc` in particular has to be refused by the same
    validation `eventkeys.secret_name` already does, not by a second copy
    of it here."""
    note = read_entry(name, text)
    assert isinstance(note, Note)
    assert reason in note.reason
    assert text not in note.reason


def test_the_plan_orders_entries_by_name_and_events_by_their_oldest() -> None:
    """Two submissions in one drain must land in the order they would have
    landed in two, and a busy event must not be able to push a quiet one
    out of a slot -- so events are taken by their *oldest* waiting entry,
    never by how many they have."""
    _, public_pem = eventkeys.generate()
    busy = [_name(f"m000000{i}") for i in (3, 4, 5)]
    quiet = _name("m0000002")
    entries = {name: _envelope(_OTHER_EVENT, public_pem) for name in busy}
    entries[quiet] = _envelope(_EVENT, public_pem)

    plan = plan_drain(entries, frozenset(), _always_open, max_events=1)

    assert plan.event_ids == (_EVENT,)
    assert [entry.name for entry in plan.handle] == [quiet]
    assert sorted(note.name for note in plan.deferred) == sorted(busy)


def test_an_event_past_the_cap_is_deferred_and_never_dropped() -> None:
    _, public_pem = eventkeys.generate()
    entries = {
        _name(f"m00000{i:02d}"): _envelope(f"mrg-{i:03d}", public_pem)
        for i in range(1, submission_queue.MAX_EVENTS_PER_DRAIN + 3)
    }

    plan = plan_drain(entries, frozenset(), _always_open)

    assert len(plan.event_ids) == submission_queue.MAX_EVENTS_PER_DRAIN
    assert len(plan.deferred) == 2
    assert not plan.refused
    handled = {entry.name for entry in plan.handle}
    deferred = {note.name for note in plan.deferred}
    assert handled | deferred == set(entries)
    assert not handled & deferred


def test_a_closed_survey_is_refused_rather_than_left_to_block_the_queue() -> None:
    """It cannot become true by waiting, and an entry that waits for ever
    is a queue that never empties -- which is the silent failure the whole
    design exists to avoid."""
    _, public_pem = eventkeys.generate()
    name = _name()
    plan = plan_drain({name: _envelope(_EVENT, public_pem)}, frozenset(), _never_open)

    assert not plan.handle
    assert [note.name for note in plan.refused] == [name]
    assert _EVENT in plan.refused[0].reason


def test_a_closed_survey_does_not_spend_one_of_the_scarce_slots() -> None:
    """The slots are the scarce thing, so the switch is read before they
    are handed out, not after."""
    _, public_pem = eventkeys.generate()
    entries = {
        _name("m0000001"): _envelope("closed-event", public_pem),
        _name("m0000002"): _envelope(_EVENT, public_pem),
    }
    plan = plan_drain(
        entries, frozenset(), lambda event_id: event_id == _EVENT, max_events=1
    )
    assert plan.event_ids == (_EVENT,)
    assert len(plan.handle) == 1


def test_secret_names_fills_every_slot_even_when_the_drain_needs_none() -> None:
    """`${{ secrets[''] }}` is the empty string rather than an error, which
    is the whole reason one fixed set of expressions in the workflow can
    serve a drain of one event and a drain of eight."""
    names = secret_names(DrainPlan())
    assert len(names) == submission_queue.MAX_EVENTS_PER_DRAIN
    assert set(names) == {""}

    _, public_pem = eventkeys.generate()
    plan = plan_drain(
        {_name(): _envelope(_EVENT, public_pem)}, frozenset(), _always_open
    )
    names = secret_names(plan)
    assert names[0] == eventkeys.secret_name(_EVENT)
    assert names[1:] == [""] * (submission_queue.MAX_EVENTS_PER_DRAIN - 1)


def test_one_drain_of_two_gives_what_two_drains_of_one_gave() -> None:
    """Stated as an experiment rather than as prose: the batched path and
    the one-at-a-time path have to agree on the file they leave behind."""
    private_pem, public_pem = eventkeys.generate()
    first, second = _name("m0000001"), _name("m0000002")
    both = {first: _envelope(_EVENT, public_pem, overall_rating=4)}
    both[second] = _envelope(_EVENT, public_pem, overall_rating=2)
    path = responses_path(_EVENT)

    batched = drain(
        plan_drain(both, frozenset(), _always_open),
        {_EVENT: private_pem},
        {path: None},
        frozenset(),
        both,
    )

    one = drain(
        plan_drain({first: both[first]}, frozenset(), _always_open),
        {_EVENT: private_pem},
        {path: None},
        frozenset(),
        {first: both[first]},
    )
    two = drain(
        plan_drain({second: both[second]}, frozenset({first}), _always_open),
        {_EVENT: private_pem},
        {path: one.files[path]},
        frozenset({first}),
        {second: both[second]},
    )

    assert _ratings(batched.files[path], private_pem) == [4, 2]
    assert _ratings(two.files[path], private_pem) == [4, 2]


def _ratings(text: str, private_pem: str) -> list[int]:
    """Every stored response's rating, in file order -- the one field that
    distinguishes the fixtures above, read back through the same decrypt
    an operator would use."""
    file = survey.load_response_file(text)
    ratings: list[int] = []
    for entry in file.entries:
        plaintext = eventkeys.decrypt(private_pem, json.dumps(dict(entry)))
        ratings.append(json.loads(survey._unpad(plaintext))["overall_rating"])
    return ratings


def test_a_key_that_is_not_configured_defers_and_never_clears() -> None:
    """The sharpest "nothing is lost" case in the module: an operator who
    has not set an event's secret must not have that event's responses
    thrown away on their behalf."""
    _, public_pem = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}
    outcome = drain(
        plan_drain(entries, frozenset(), _always_open),
        {},
        {responses_path(_EVENT): None},
        frozenset(),
        entries,
    )

    assert outcome.handled == 0
    assert outcome.clear == ()
    assert outcome.ledger == ()
    assert [note.name for note in outcome.deferred] == [name]


def test_a_committed_file_that_will_not_parse_defers_that_events_entries() -> None:
    private_pem, public_pem = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}
    outcome = drain(
        plan_drain(entries, frozenset(), _always_open),
        {_EVENT: private_pem},
        {responses_path(_EVENT): '{"v": 99, "responses": []}'},
        frozenset(),
        entries,
    )

    assert outcome.files == {}
    assert outcome.clear == ()
    assert [note.name for note in outcome.deferred] == [name]


def test_a_malformed_entry_does_not_take_the_rest_of_the_drain_down() -> None:
    """One bad entry beside two good ones: the good ones are stored, the
    bad one is refused by name, and nothing raises."""
    private_pem, public_pem = eventkeys.generate()
    good = [_name("m0000001"), _name("m0000003")]
    rubbish = _name("m0000002")
    entries = {name: _envelope(_EVENT, public_pem) for name in good}
    entries[rubbish] = json.dumps({"event_id": _EVENT, "v": 1, "ciphertext": "nope"})

    outcome = drain(
        plan_drain(entries, frozenset(), _always_open),
        {_EVENT: private_pem},
        {responses_path(_EVENT): None},
        frozenset(),
        entries,
    )

    assert outcome.handled == 2
    assert [note.name for note in outcome.refused] == [rubbish]
    assert set(outcome.clear) == set(entries)


def test_ciphertext_that_will_not_decrypt_is_refused_by_name() -> None:
    private_pem, _ = eventkeys.generate()
    _, other_public = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, other_public)}

    outcome = drain(
        plan_drain(entries, frozenset(), _always_open),
        {_EVENT: private_pem},
        {responses_path(_EVENT): None},
        frozenset(),
        entries,
    )

    assert outcome.handled == 0
    assert [note.name for note in outcome.refused] == [name]
    assert "could not be read" in outcome.refused[0].reason


def test_a_refused_entry_is_cleared_so_the_queue_can_still_empty() -> None:
    _, public_pem = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}
    outcome = drain(
        plan_drain(entries, frozenset(), _never_open),
        {},
        {},
        frozenset(),
        entries,
    )
    assert outcome.clear == (name,)
    assert outcome.ledger == (name,)


def test_an_empty_queue_produces_nothing_at_all() -> None:
    outcome = drain(plan_drain({}, frozenset(), _always_open), {}, {}, frozenset(), {})
    assert outcome.files == {}
    assert outcome.clear == ()
    assert outcome.ledger == ()
    assert annotation_lines(outcome) == []


def test_a_deferral_is_the_error_and_a_refusal_the_warning() -> None:
    """The assignment is deliberately the opposite of the intuitive one --
    see `annotation_lines`' own docstring. A stranger who could turn the
    daily job red at will would train the operator to ignore it."""
    outcome = drain(
        DrainPlan(refused=(Note("a", "bad"),), deferred=(Note("b", "waiting"),)),
        {},
        {},
        frozenset(),
        (),
    )
    lines = annotation_lines(outcome)
    assert lines == ["::error::b: waiting", "::warning::a: bad"]


def test_the_summary_counts_and_names_nothing_else() -> None:
    _, public_pem = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}
    outcome = drain(
        plan_drain(entries, frozenset(), _never_open), {}, {}, frozenset(), entries
    )
    line = summary(outcome)
    assert "1 refused" in line
    assert name not in line


# ------------------------------------------------------------------ #
# 2 - nothing is lost: cancellation, a failed clear, a replay
# ------------------------------------------------------------------ #


def test_the_ledger_refuses_a_shape_it_cannot_read() -> None:
    """A ledger this reader guessed at is a ledger that could call an entry
    handled when it was not -- a lost submission -- or unhandled when it
    was -- a doubled one. Both are the failure the file exists to prevent,
    so every shape but the exact one raises."""
    shapes: list[Any] = [
        None,
        [],
        {"v": 2, "handled": []},
        {"v": 1},
        {"v": 1, "handled": [1]},
    ]
    for data in shapes:
        with pytest.raises(ValueError):
            ledger_from_data(data)


def test_the_ledger_round_trips_through_its_own_two_functions() -> None:
    assert ledger_from_data(ledger_to_data(["b", "a", "a"])) == frozenset({"a", "b"})
    assert ledger_to_data(["b", "a"])["handled"] == ["a", "b"]


def test_the_ledger_forgets_an_id_the_queue_no_longer_holds() -> None:
    """The pruning half, which is what stops the file growing for ever. An
    id the queue no longer holds was cleared by an earlier drain, and an
    entry id is a uuid, so nothing can bring that name back."""
    assert next_ledger(frozenset({"gone", "still"}), ["still"], []) == ("still",)


def test_the_ledger_keeps_an_id_the_queue_still_holds() -> None:
    """The case the ledger exists for: a drain that committed and was then
    interrupted before clearing."""
    assert next_ledger(frozenset({"waiting"}), ["waiting"], []) == ("waiting",)


def test_a_deferred_entry_never_enters_the_ledger() -> None:
    """If it did, the next drain would clear a submission it had never
    applied. The asymmetry with a refusal is the whole reason the two are
    different words."""
    _, public_pem = eventkeys.generate()
    entries = {
        _name(f"m00000{i:02d}"): _envelope(f"mrg-{i:03d}", public_pem)
        for i in range(1, 4)
    }
    outcome = drain(
        plan_drain(entries, frozenset(), _always_open, max_events=1),
        {},
        {},
        frozenset(),
        entries,
    )
    assert outcome.ledger == ()
    assert outcome.clear == ()
    assert len(outcome.deferred) == 3


def test_an_interrupted_drain_loses_nothing_and_doubles_nothing() -> None:
    """Driven, not reasoned about. The sequence played out below is exactly
    what a cancelled run leaves behind:

    1. a drain handles one entry, commits its file *and its ledger*, and is
       then killed before it can clear the queue;
    2. the next drain finds the same entry still in the queue.

    The second drain must store nothing new -- one submission, one stored
    response -- and must still clear the entry it can now see was handled.
    """
    private_pem, public_pem = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}
    path = responses_path(_EVENT)

    first = drain(
        plan_drain(entries, frozenset(), _always_open),
        {_EVENT: private_pem},
        {path: None},
        frozenset(),
        entries,
    )
    assert first.handled == 1
    assert first.ledger == (name,)
    # ... and here the run is cancelled: `first.clear` is never applied.

    second = drain(
        plan_drain(entries, frozenset(first.ledger), _always_open),
        {_EVENT: private_pem},
        {path: first.files[path]},
        frozenset(first.ledger),
        entries,
    )

    assert second.handled == 0
    assert second.files == {}
    assert second.clear == (name,)
    assert len(survey.load_response_file(first.files[path]).entries) == 1


def test_a_replayed_drain_records_nothing_a_second_time() -> None:
    """Idempotence in its own right: a drain run twice over a queue it has
    already drained produces no second record."""
    private_pem, public_pem = eventkeys.generate()
    name = _name()
    entries = {name: _envelope(_EVENT, public_pem)}
    path = responses_path(_EVENT)

    first = drain(
        plan_drain(entries, frozenset(), _always_open),
        {_EVENT: private_pem},
        {path: None},
        frozenset(),
        entries,
    )
    # The clear succeeded this time, so the queue is empty on the replay.
    replay = drain(
        plan_drain({}, frozenset(first.ledger), _always_open),
        {_EVENT: private_pem},
        {path: first.files[path]},
        frozenset(first.ledger),
        {},
    )

    assert replay.files == {}
    assert replay.handled == 0
    # And the ledger has now forgotten it -- there is nothing left that
    # could be replayed, so nothing left to remember.
    assert replay.ledger == ()


# ------------------------------------------------------------------ #
# 3 - the two console scripts, against a real repository root
# ------------------------------------------------------------------ #


def _repo(tmp_path: Path, *, survey_enabled: bool = True) -> Path:
    data = tmp_path / "instance" / "data"
    data.mkdir(parents=True)
    (data / "speakers.yml").write_text(
        yaml.safe_dump(
            [speaker(id="spk-001", edition_code=_EVENT, survey_enabled=survey_enabled)]
        ),
        encoding="utf-8",
    )
    (data / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    return tmp_path


def _queue(tmp_path: Path, **entries: str) -> Path:
    """Write `entries` (name-without-directory -> payload) as the drain's
    own exported queue directory."""
    queue = tmp_path / "queue-export"
    for stamp, payload in entries.items():
        path = queue / entry_path(submission_queue.SURVEY_KIND, stamp)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    queue.mkdir(exist_ok=True)
    return queue


def _outputs(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )


def test_plan_refuses_to_guess_where_the_queue_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(_repo(tmp_path)))
    monkeypatch.delenv("CONVENER_QUEUE_DIR", raising=False)
    assert plan_queue_drain() == 1
    assert "CONVENER_QUEUE_DIR" in capsys.readouterr().err


def test_plan_refuses_a_ledger_it_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refusing outright, never draining against an empty ledger: reading a
    broken ledger as "nothing has ever been handled" would re-apply every
    entry an earlier drain already did."""
    root = _repo(tmp_path)
    (root / submission_queue.LEDGER_PATH).write_text("v: 99\n", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(_queue(tmp_path)))
    assert plan_queue_drain() == 1
    assert "queue-ledger.yml" in capsys.readouterr().err


def test_plan_refuses_a_ledger_that_is_not_valid_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    (root / submission_queue.LEDGER_PATH).write_text("v: [unclosed\n", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(_queue(tmp_path)))
    assert plan_queue_drain() == 1
    assert "invalid YAML" in capsys.readouterr().err


def test_an_empty_queue_and_an_empty_ledger_are_not_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The silent case, and the one that matters most for cost: nothing
    waiting means the drain step never starts and no commit is made."""
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(_repo(tmp_path)))
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(_queue(tmp_path)))
    output = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert plan_queue_drain() == 0
    assert _outputs(output)["pending"] == "false"


def test_an_empty_queue_with_a_ledger_still_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise the ledger would never be pruned and would grow for ever."""
    root = _repo(tmp_path)
    (root / submission_queue.LEDGER_PATH).write_text(
        yaml.safe_dump(ledger_to_data(["queue/survey/gone.json"])), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(_queue(tmp_path)))
    output = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert plan_queue_drain() == 0
    assert _outputs(output)["pending"] == "true"


def test_plan_names_the_secret_for_the_event_it_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, public_pem = eventkeys.generate()
    root = _repo(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
    monkeypatch.setenv(
        "CONVENER_QUEUE_DIR",
        str(_queue(tmp_path, **{f"m1-{uuid.uuid4()}": _envelope(_EVENT, public_pem)})),
    )
    output = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert plan_queue_drain() == 0
    values = _outputs(output)
    assert values["pending"] == "true"
    assert values["event_1"] == _EVENT
    assert values["secret_1"] == eventkeys.secret_name(_EVENT)
    assert values[f"secret_{submission_queue.MAX_EVENTS_PER_DRAIN}"] == ""


def test_the_drain_writes_the_response_the_ledger_and_the_clear_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, public_pem = eventkeys.generate()
    root = _repo(tmp_path)
    stamp = f"m1-{uuid.uuid4()}"
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
    monkeypatch.setenv(
        "CONVENER_QUEUE_DIR",
        str(_queue(tmp_path, **{stamp: _envelope(_EVENT, public_pem)})),
    )
    clear_file = tmp_path / "clear.txt"
    monkeypatch.setenv("CONVENER_QUEUE_CLEAR_FILE", str(clear_file))
    monkeypatch.setenv("CONVENER_QUEUE_EVENT_1", _EVENT)
    monkeypatch.setenv("CONVENER_QUEUE_KEY_1", private_pem)
    output = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert drain_queue() == 0

    stored = (root / responses_path(_EVENT)).read_text(encoding="utf-8")
    assert len(survey.load_response_file(stored).entries) == 1
    ledger = yaml.safe_load((root / submission_queue.LEDGER_PATH).read_text("utf-8"))
    assert ledger_from_data(ledger) == frozenset(
        {entry_path(submission_queue.SURVEY_KIND, stamp)}
    )
    assert clear_file.read_text(encoding="utf-8").strip() == entry_path(
        submission_queue.SURVEY_KIND, stamp
    )
    assert _outputs(output)["handled"] == "1"

    combined = "".join(capsys.readouterr())
    for secret in _LEAK_STRINGS:
        assert secret not in combined, f"{secret!r} leaked into job output"


def test_the_drain_never_writes_plaintext_to_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same property `test_cli.py` held the job this replaced to: what
    a participant wrote must exist nowhere on the runner's disk once the
    drain has finished."""
    private_pem, public_pem = eventkeys.generate()
    root = _repo(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
    monkeypatch.setenv(
        "CONVENER_QUEUE_DIR",
        str(_queue(tmp_path, **{f"m1-{uuid.uuid4()}": _envelope(_EVENT, public_pem)})),
    )
    monkeypatch.setenv("CONVENER_QUEUE_EVENT_1", _EVENT)
    monkeypatch.setenv("CONVENER_QUEUE_KEY_1", private_pem)

    assert drain_queue() == 0

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for secret in _LEAK_STRINGS:
            assert secret not in text, f"{secret!r} written to {path}"


def test_the_drain_defers_when_the_slot_names_another_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Belt and braces on the one place the plan step and the drain step
    meet again. A mispaired slot holds a key that decrypts nothing, so the
    entry waits rather than being refused and cleared."""
    private_pem, public_pem = eventkeys.generate()
    root = _repo(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
    monkeypatch.setenv(
        "CONVENER_QUEUE_DIR",
        str(_queue(tmp_path, **{f"m1-{uuid.uuid4()}": _envelope(_EVENT, public_pem)})),
    )
    clear_file = tmp_path / "clear.txt"
    monkeypatch.setenv("CONVENER_QUEUE_CLEAR_FILE", str(clear_file))
    monkeypatch.setenv("CONVENER_QUEUE_EVENT_1", "some-other-event")
    monkeypatch.setenv("CONVENER_QUEUE_KEY_1", private_pem)
    output = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert drain_queue() == 0
    assert _outputs(output)["deferred"] == "1"
    assert clear_file.read_text(encoding="utf-8") == ""
    assert not (root / responses_path(_EVENT)).exists()


def test_the_drain_refuses_to_guess_where_the_queue_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(_repo(tmp_path)))
    monkeypatch.delenv("CONVENER_QUEUE_DIR", raising=False)
    assert drain_queue() == 1
    assert "CONVENER_QUEUE_DIR" in capsys.readouterr().err


def test_the_drain_refuses_when_the_committed_ledger_will_not_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    (root / submission_queue.LEDGER_PATH).write_text("v: 99\n", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(_queue(tmp_path)))
    assert drain_queue() == 1
    assert "queue-ledger.yml" in capsys.readouterr().err


def test_the_drain_refuses_a_response_for_an_event_whose_survey_is_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The relay checks too, but it is a courtesy that saves a queue write,
    never the authority -- the same split `handle_survey_response` used to
    hold."""
    private_pem, public_pem = eventkeys.generate()
    root = _repo(tmp_path, survey_enabled=False)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
    monkeypatch.setenv(
        "CONVENER_QUEUE_DIR",
        str(_queue(tmp_path, **{f"m1-{uuid.uuid4()}": _envelope(_EVENT, public_pem)})),
    )
    monkeypatch.setenv("CONVENER_QUEUE_EVENT_1", _EVENT)
    monkeypatch.setenv("CONVENER_QUEUE_KEY_1", private_pem)
    output = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert drain_queue() == 0
    assert _outputs(output)["refused"] == "1"
    assert not (root / responses_path(_EVENT)).exists()
    assert "::warning::" in capsys.readouterr().out


def test_the_drain_reads_an_unreadable_file_as_a_refusal_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bytes that are not UTF-8 at all. Losing the rest of the queue
    because one file is rubbish would be the worst possible trade."""
    private_pem, public_pem = eventkeys.generate()
    root = _repo(tmp_path)
    queue = _queue(tmp_path, **{f"m2-{uuid.uuid4()}": _envelope(_EVENT, public_pem)})
    bad = queue / entry_path(submission_queue.SURVEY_KIND, f"m1-{uuid.uuid4()}")
    bad.write_bytes(b"\xff\xfe\x00rubbish")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(root))
    monkeypatch.setenv("CONVENER_QUEUE_DIR", str(queue))
    monkeypatch.setenv("CONVENER_QUEUE_EVENT_1", _EVENT)
    monkeypatch.setenv("CONVENER_QUEUE_KEY_1", private_pem)
    output = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert drain_queue() == 0
    values = _outputs(output)
    assert values["handled"] == "1"
    assert values["refused"] == "1"


# ------------------------------------------------------------------ #
# 4 - the workflow, and the one thing no offline test can enforce
# ------------------------------------------------------------------ #

_SWEEP = (_ROOT / ".github" / "workflows" / "sweep-and-notify.yml").read_text(
    encoding="utf-8"
)


def test_the_drain_runs_as_steps_of_a_job_that_already_runs() -> None:
    """The whole economy of the feature. A workflow of its own, or a job of
    its own, would cost a billed run every day -- more than the runs it
    saves for any series that is not extremely busy."""
    assert "uv run convener-plan-queue-drain" in _SWEEP
    assert "uv run convener-drain-queue" in _SWEEP
    jobs = _SWEEP.split("jobs:")[1]
    declared = [
        line.strip()
        for line in jobs.splitlines()
        if line.startswith("  ") and not line.startswith("   ") and line.endswith(":")
    ]
    assert declared == ["immediate:", "daily:"], (
        f"this workflow now declares {declared} -- the queue steps live in "
        "`daily` precisely because it already runs, and a job added for "
        "them would bill a runner every day"
    )


def test_no_workflow_but_the_daily_job_mentions_the_queue() -> None:
    """A second consumer of the queue branch would be a second billed run,
    and a `push:` filter naming it would be worse still (the workflow
    sweep would catch that one; this catches the softer version)."""
    workflows = (_ROOT / ".github" / "workflows").glob("*.yml")
    mentions = {
        path.name
        for path in workflows
        if submission_queue.QUEUE_BRANCH in path.read_text(encoding="utf-8")
    }
    assert mentions == {"sweep-and-notify.yml"}


def test_the_workflow_spells_out_exactly_as_many_slots_as_the_cap() -> None:
    """The cap is not a performance number: it is how many
    `${{ secrets[...] }}` expressions exist in the YAML. If the two drift
    apart, either an event's key is silently unavailable or a slot names a
    secret nothing plans for."""
    for slot in range(1, submission_queue.MAX_EVENTS_PER_DRAIN + 1):
        event = f"steps.queue-plan.outputs.event_{slot}"
        secret = f"secrets[steps.queue-plan.outputs.secret_{slot}]"
        assert f"CONVENER_QUEUE_EVENT_{slot}: ${{{{ {event} }}}}" in _SWEEP
        assert f"CONVENER_QUEUE_KEY_{slot}: ${{{{ {secret} }}}}" in _SWEEP
    beyond = submission_queue.MAX_EVENTS_PER_DRAIN + 1
    assert f"CONVENER_QUEUE_KEY_{beyond}" not in _SWEEP


def test_the_workflow_and_the_module_agree_on_the_branch_name() -> None:
    assert f"QUEUE_BRANCH: {submission_queue.QUEUE_BRANCH}" in _SWEEP


def test_the_drain_commits_the_data_and_the_ledger_together() -> None:
    """One commit, or a replay records a submission twice: a ledger
    committed without its data, or data without its ledger, is exactly the
    interruption the ledger exists to survive."""
    assert "git add -- instance/data/queue-ledger.yml" in _SWEEP
    assert "git add -- instance/data/events" in _SWEEP
    commit = _SWEEP.index('git commit -m "data: drain the public submission queue"')
    assert _SWEEP.index("git add -- instance/data/queue-ledger.yml") < commit
    assert _SWEEP.index("git add -- instance/data/events") < commit


def test_the_queue_is_cleared_only_after_the_drain_has_pushed() -> None:
    """The ordering that is the whole of "nothing is lost". Asserted as a
    position in the file, because that is what the ordering *is*."""
    drain_at = _SWEEP.index("- name: Drain the submission queue")
    clear_at = _SWEEP.index("- name: Clear what the drain handled")
    assert drain_at < clear_at
    assert "if: always() && steps.queue-drain.outcome == 'success'" in _SWEEP


def test_the_queue_is_exported_outside_the_checkout() -> None:
    """A queued entry caught by a `git add` meant for `instance/data/` would land on
    the default branch, which is the one place it must never be."""
    assert "CONVENER_QUEUE_DIR: ${{ runner.temp }}/queue" in _SWEEP
    assert 'rm -rf "$RUNNER_TEMP/queue"' in _SWEEP


def test_only_a_deferral_can_turn_the_daily_job_red() -> None:
    """A stranger must not be able to decide the colour of this job -- see
    `annotation_lines`' own docstring."""
    assert "steps.queue-drain.outputs.deferred != '0'" in _SWEEP
    assert "steps.queue-drain.outputs.refused" not in _SWEEP


def test_the_dispatch_handler_it_replaces_is_gone() -> None:
    """`survey.yml` used to start one run per response. Leaving it behind
    would leave a `repository_dispatch` nothing sends and a secret nothing
    spends -- and would keep the per-submission run alive for anyone
    holding the relay's token."""
    assert not (_ROOT / ".github" / "workflows" / "survey.yml").exists()
    monitor = (
        _ROOT / ".github" / "workflows" / "secret-workflow-monitor.yml"
    ).read_text(encoding="utf-8")
    assert "Handle survey response" not in monitor


def test_no_queue_file_is_committed_to_the_default_branch() -> None:
    """The consequence of the one precondition no offline test can enforce.

    It is written down and cannot be held here: nobody may open a pull
    request from the queue branch, and whether one exists is repository
    state rather than file content. This is what breaking it looks like one
    step later -- queue files arriving on the default branch, where at
    least five workflows start on any commit -- and it is visible here, on
    the pull request that would cause it.
    """
    tracked = [
        path.relative_to(_ROOT).as_posix()
        for path in (_ROOT / submission_queue.QUEUE_DIR).rglob("*")
        if path.is_file()
    ]
    assert queue_files_in(tracked) == [], (
        "a queue entry has reached the default branch. Every commit to it "
        "starts derive-decision-register.yml, quality.yml and security.yml "
        "with no path filter at all, plus deploy.yml -- one submission, at "
        "least five "
        "billed runs, which is the exact inverse of what the queue is for. "
        "This is what an open pull request from "
        f"{submission_queue.QUEUE_BRANCH!r} looks like once it is merged"
    )
