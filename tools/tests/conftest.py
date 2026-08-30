from __future__ import annotations

import os
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Final

import pytest

from convener_ops.declaration.published import EditionPrefix

#: `tools/scripts/` holds the generators and one-off utilities, and
#: `tools/migrations/` the one-shot migrations. Both live outside the
#: installed package (the wheel ships `convener_ops` alone) but are tested
#: with it, so their directories join the import path here rather than in
#: each test module.
_TOOLS = Path(__file__).resolve().parents[1]
for _directory in (_TOOLS / "scripts", _TOOLS / "migrations"):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))


@pytest.fixture(autouse=True)
def _isolate_environment() -> Iterator[None]:
    """A finding from proving `test_event_chain.py`'s replay
    tests actually bite: `monkeypatch.setenv`/`delenv` only undoes changes
    made *through monkeypatch itself* -- a stray `os.environ[key] = value`
    written directly by production code would survive past that test's
    own teardown and leak into whichever test runs next in the same
    process. Nothing in `convener_ops`, the generators, the migrations or
    this test tree does that
    today (checked by grep and by removing this
    fixture entirely: the suite's result is identical either way) -- this
    guards against a mutant introducing exactly that coupling, not a live
    leak. A mutant that made one CLI step secretly depend on a previous
    one having "just run", by reading an env var the previous step's own
    code sets on success, would go undetected purely because an earlier
    test in the same session happened to set that variable first -- not
    because the replay test was wrong, but because the process's
    environment was never reset between tests at all. Verified with a
    second, independent mutant beyond the one this fixture was first built
    for: 0 failures across the suite without this fixture, 14 with it.

    Snapshots `os.environ` before every test and restores exactly the keys
    that changed afterwards -- diff-based, not `clear()` then `update()`,
    so `PATH`, `SYSTEMROOT` and `TEMP` (on Windows) are never even briefly
    unset while the restore runs.

    **One gap, by construction, not by neglect: `os.putenv`.** It writes
    the process environment directly, bypassing the `os.environ` mapping
    this fixture snapshots and restores, so a write made that way is
    invisible here and leaks into every later child process for the rest
    of the session. Nothing in this tree calls `os.putenv`; if that ever
    changes, this fixture does not cover it."""
    before = dict(os.environ)
    yield
    for key in set(os.environ) - set(before):
        del os.environ[key]
    for key, value in before.items():
        if os.environ.get(key) != value:
            os.environ[key] = value


# ------------------------------------------------------------------ #
# Reading a workflow file: the one key that is not a string.
# ------------------------------------------------------------------ #

#: A GitHub Actions workflow as PyYAML hands it back. Deliberately not
#: `dict[str, Any]`: PyYAML implements YAML 1.1, whose bool resolver reads
#: the bare `on:` key -- the trigger block every workflow must declare --
#: as the boolean `True`, before any of this suite looks at the file's own
#: content. Every other key really is the string the file spells, so the
#: key type is `str | bool` and that single boolean is reached through the
#: two readers below rather than written out as `loaded[True]` at each
#: call site, where it reads as a typo rather than as a fact about YAML.
type WorkflowYaml = dict[str | bool, Any]

#: What `on:` actually parses to, named so a reader meets the reason
#: rather than a bare `True` subscript.
_ON_KEY_UNDER_YAML_1_1: Final = True


def workflow_triggers(loaded: Mapping[str | bool, Any]) -> dict[str, Any]:
    """A workflow's `on:` block in its mapping form -- `on:` with each
    event name as a key of its own, the shape every workflow in this
    repository uses.

    Fails the test that asked for it, by name, when there is no such block
    -- a workflow that lost its trigger, or one written in either of the
    two scalar forms GitHub also accepts, which `workflow_event_names`
    below reads instead."""
    triggers = loaded.get(_ON_KEY_UNDER_YAML_1_1)
    assert isinstance(triggers, dict), (
        f"this workflow's `on:` block is {triggers!r}, not a mapping of "
        "event names -- either it declares no trigger at all, or it uses "
        "the bare-string or list form, which `workflow_event_names` reads"
    )
    return triggers


def workflow_event_names(loaded: Mapping[str | bool, Any]) -> set[str]:
    """Every event name a workflow declares under `on:`, in all three
    shapes GitHub accepts: one bare event name, a list of them, or a
    mapping from each event name to that event's own options. The empty
    set when the workflow declares no trigger at all -- callers here sweep
    every workflow file and report per file, so a missing block is a
    finding to carry, not an exception to raise."""
    triggers = loaded.get(_ON_KEY_UNDER_YAML_1_1)
    if isinstance(triggers, str):
        return {triggers}
    if isinstance(triggers, list | dict):
        return {str(event) for event in triggers}
    return set()


def ballot(**overrides: Any) -> dict[str, Any]:
    """A minimal valid ballot (schema v3); override any field per test."""
    base: dict[str, Any] = {
        "voter": "carol",
        "value": "yes",
        "comment": "",
        "coi_reason": "",
        "date": "2026-01-08",
    }
    base.update(overrides)
    return base


def board_member(**overrides: Any) -> dict[str, Any]:
    """A minimal valid board member (schema v3); override any field per test."""
    base: dict[str, Any] = {
        "login": "carol",
        "joined_on": "2024-01-01",
        "status": "active",
        "unavailable_until": "",
    }
    base.update(overrides)
    return base


def objection(**overrides: Any) -> dict[str, Any]:
    """A minimal valid PublicationObjection (schema v3); shared by
    Publication and Nomination."""
    base: dict[str, Any] = {
        "member": "carol",
        "reason": "",
        "date": "",
    }
    base.update(overrides)
    return base


def nomination(**overrides: Any) -> dict[str, Any]:
    """A minimal valid nomination (schema v3); override any field per test."""
    base: dict[str, Any] = {
        "candidate": "grace",
        "sponsor": "carol",
        "opened_on": "2026-01-01",
        "objections": [],
        "outcome": "",
    }
    base.update(overrides)
    return base


#: The edition prefix these doubles are numbered under, and the one
#: `validate_speakers` is handed unless a test is about the prefix itself.
#:
#: Written here rather than read from `instance/config.json`, and the
#: difference matters: this suite tests the *validator*, so what it needs
#: is a prefix, any prefix, held still. Reading the declaration would make
#: every assertion below move the day the declaration moved, which is the
#: property `tools/tests/test_second_instance.py` exists to check and the
#: last thing a unit test should be quietly repeating. `MRG` is the one
#: this repository happens to declare, so a fixture reading `MRG-07` still
#: reads like the file it stands for.
EDITIONS: Final = EditionPrefix(value="MRG")


def speaker(**overrides: Any) -> dict[str, Any]:
    """A minimal valid speaker (schema v5); override any field per test.

    Minimal, not partial: every key the model declares is here, with the
    empty value where the record has nothing to say. A double that left keys
    out would be a record the validator refuses, and tests written against
    it would agree with each other about a file the repository cannot hold.
    """
    base: dict[str, Any] = {
        "id": "spk-001",
        "name": "Ada Lovelace",
        "gender": "undisclosed",
        "email": "ada@example.org",
        "affiliation": "Example University",
        "country": "UK",
        "photo_url": "",
        "bio": "",
        "linkedin": "",
        "seed_questions": "",
        "candidate_dates": [],
        "title": "On analytical engines",
        "abstract": "",
        "conflicts_of_interest": "",
        "source": "organizer",
        "proposed_by": "someone",
        "assigned_to": "",
        "links": [],
        "host_1": "",
        "host_2": "",
        "status": "lead",
        "career_stage": "undisclosed",
        "publication": {
            "consent": "",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "",
        },
        "selection": {"ballots": [], "opened_on": "", "decided_on": ""},
        "edition_code": "",
        "date": "",
        "time": "",
        "zoom_link": "",
        "youtube_url": "",
        "forum_thread": "",
        "survey_enabled": False,
        "runbook_progress": {},
        # Nobody down for any line, which is the state every record starts in
        # and most lines stay in.
        "checklist": {},
        "metrics": {
            "registrations": None,
            "live_peak": None,
            "youtube_views_30d": None,
            "forum_replies": None,
        },
        "notes": "",
    }
    base.update(overrides)
    return base


def config(**overrides: Any) -> dict[str, Any]:
    """A minimal valid config (schema v3); override any field per test."""
    base: dict[str, Any] = {
        "season": 2026,
        "next_edition_number": 5,
        "overlap_window_days": 7,
        "seminar_duration_minutes": 90,
        "eligibility_share": 0.6666666666666666,
        "board": [
            board_member(login="carol"),
            board_member(login="grace"),
            board_member(login="ada"),
        ],
        "nominations": [],
        "board_min": 3,
        "board_max": 9,
        "vote_window_days": 10,
        "objection_window_working_days": 5,
        "inactivity_months": 6,
        "balance_window_months": 12,
        "view_count_window_days": 30,
        "instructions": "",
        "sla_days": {
            "invitation_follow_up": 7,
            "summary_after_delivery": 5,
            "recording_after_delivery": 10,
        },
        # Two, where `instance/data/config.yml` lists seven: the channels are
        # configuration, and a double that restated the seven of today would
        # make every unrelated test depend on a list this repository leaves
        # editable. A test about the channels states its own.
        "channels": [
            {"key": "forum", "label": "Community forum"},
            {"key": "linkedin_page", "label": "Team LinkedIn page"},
        ],
    }
    base.update(overrides)
    return base
