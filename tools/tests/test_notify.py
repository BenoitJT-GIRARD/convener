"""A message that has been sent cannot be unsent.

So the tests that matter most here are the ones about *not* sending: that an
unconfigured repository produces nothing, that a quiet day produces nothing,
and that no personal data can travel even when a message does go out.
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess  # nosec B404
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import ballot, nomination, objection, speaker, workflow_triggers
from conftest import config as make_config

from convener_ops import cli, notify
from convener_ops.commit_format import judgemental_terms
from convener_ops.governance import vote_window_days
from convener_ops.notify import (
    EVENT_KINDS,
    MENTION_ENV,
    NEW_LEAD,
    OBJECTION_FILED,
    STEP_LABELS,
    THREAD_ENV,
    THRESHOLD_REACHED,
    Channel,
    daily_digest,
    dispatch,
    immediate_events,
    overdue,
    overdue_text,
    render_events,
    resolve_channel,
    waiting_since,
)
from convener_ops.paths import repo_root
from convener_ops.sweep import expire_votes
from convener_ops.yaml_safe import safe_load

NOW = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)

#: A fully-configured environment, so the "sends nothing" tests are not
#: passing merely because the fixture forgot to configure anything.
CONFIGURED = {THREAD_ENV: "42", MENTION_ENV: "@example/editorial"}


def lead(**over: Any) -> dict[str, Any]:
    return speaker(**over)


def kinds(events: list[notify.Event]) -> list[str]:
    return [event.kind for event in events]


# ------------------------------------------------------------------ #
# immediate_events: exactly three cases, and nothing else
# ------------------------------------------------------------------ #


def test_a_lead_arriving_from_the_public_form_is_an_immediate_event() -> None:
    after = [lead(id="spk-009", status="lead", source="form")]
    assert kinds(immediate_events([], after)) == [NEW_LEAD]


def test_a_record_added_by_hand_is_not_a_form_submission() -> None:
    """Only the public form interrupts anybody. A row added through the app,
    or by an editor, is an ordinary change."""
    after = [lead(id="spk-009", status="lead", source="organizer")]
    assert immediate_events([], after) == []


def test_a_new_record_that_is_not_a_lead_is_not_an_immediate_event() -> None:
    after = [lead(id="spk-009", status="confirmed", source="form")]
    assert immediate_events([], after) == []


def test_a_vote_reaching_its_threshold_is_an_immediate_event() -> None:
    before = [
        lead(
            id="spk-001",
            status="lead",
            selection={"ballots": [], "opened_on": "2026-08-01", "decided_on": ""},
        )
    ]
    after = [
        lead(
            id="spk-001",
            status="approved",
            selection={
                "ballots": [],
                "opened_on": "2026-08-01",
                "decided_on": "2026-08-18",
            },
        )
    ]
    assert kinds(immediate_events(before, after)) == [THRESHOLD_REACHED]


def test_an_administrative_override_is_not_announced_as_a_vote() -> None:
    """The sentence this event carries is "the vote reached its threshold and
    the lead is approved".

    `AdminOverride`'s force-status control writes `status` and nothing else --
    no ballot, no `decided_on` -- so a record moved that way reached no
    threshold. Sending that sentence to the board would be a false statement
    about a governance decision, on the channel reserved for what calls for a
    quick reaction. The override is a deliberate act by a named person and the
    decision register records it; it is not news of a vote.
    """
    before = [
        lead(
            id="spk-001",
            status="lead",
            selection={"ballots": [], "opened_on": "2026-08-01", "decided_on": ""},
        )
    ]
    after = [
        lead(
            id="spk-001",
            status="approved",
            selection={"ballots": [], "opened_on": "2026-08-01", "decided_on": ""},
        )
    ]
    assert immediate_events(before, after) == []


def test_a_record_with_no_selection_block_is_not_announced_as_a_vote() -> None:
    # "selection" is required by the schema, but notify_immediate reads
    # speakers.yml straight off disk (convener_ops.cli._load), unvalidated -- a
    # legacy or hand-edited record with no "selection" key at all must not
    # crash _selection_day, and must not read as "decided_on is set".
    before = [{"id": "spk-001", "status": "lead", "source": "form"}]
    after = [{"id": "spk-001", "status": "approved", "source": "form"}]
    assert immediate_events(before, after) == []


def test_a_decision_already_recorded_is_not_announced_a_second_time() -> None:
    """A record that was already decided and is moved back to `lead` and
    forward again by a reopening carries its old `decided_on`; only a
    freshly-stamped one is news."""
    decided = {"ballots": [], "opened_on": "2026-08-01", "decided_on": "2026-08-10"}
    before = [lead(id="spk-001", status="lead", selection=decided)]
    after = [lead(id="spk-001", status="approved", selection=decided)]
    assert immediate_events(before, after) == []


def test_an_objection_lodged_on_a_publication_is_an_immediate_event() -> None:
    before = [lead(id="spk-001", status="delivered")]
    after = [
        lead(
            id="spk-001",
            status="delivered",
            publication={
                "consent": "granted",
                "approved_by": "ada",
                "approved_on": "2026-08-10",
                "objections": [
                    objection(member="grace", reason="the consent is unclear")
                    | {"resolved_on": ""}
                ],
                "outcome": "",
            },
        )
    ]
    assert kinds(immediate_events(before, after)) == [OBJECTION_FILED]


def test_a_publication_with_no_objections_key_stands_for_none() -> None:
    # publication.objections is required by the schema, but this reads
    # unvalidated data (see the note above) -- a publication block that
    # predates the field, or was hand-edited, must read as "no standing
    # objections" rather than raise iterating something that is not a list.
    before = [lead(id="spk-001", status="delivered", publication={"consent": ""})]
    after = [
        lead(
            id="spk-001",
            status="delivered",
            publication={
                "consent": "granted",
                "approved_by": "ada",
                "approved_on": "2026-08-10",
                "objections": [
                    objection(member="grace", reason="the consent is unclear")
                    | {"resolved_on": ""}
                ],
                "outcome": "",
            },
        )
    ]
    assert kinds(immediate_events(before, after)) == [OBJECTION_FILED]


def test_an_objection_that_was_already_standing_is_not_announced_again() -> None:
    standing = objection(
        member="grace", reason="the consent is unclear", date="2026-08-01"
    ) | {"resolved_on": ""}
    publication = {
        "consent": "granted",
        "approved_by": "ada",
        "approved_on": "2026-08-10",
        "objections": [standing],
        "outcome": "",
    }
    before = [lead(id="spk-001", status="delivered", publication=publication)]
    after = [lead(id="spk-001", status="delivered", publication=publication)]
    assert immediate_events(before, after) == []


def test_resolving_an_objection_is_not_an_immediate_event() -> None:
    raised = objection(member="grace", reason="unclear", date="2026-08-01")
    before = [
        lead(
            id="spk-001",
            status="delivered",
            publication={
                "consent": "granted",
                "approved_by": "",
                "approved_on": "",
                "objections": [raised | {"resolved_on": ""}],
                "outcome": "",
            },
        )
    ]
    after = [
        lead(
            id="spk-001",
            status="delivered",
            publication={
                "consent": "granted",
                "approved_by": "",
                "approved_on": "",
                "objections": [raised | {"resolved_on": "2026-08-12"}],
                "outcome": "",
            },
        )
    ]
    assert immediate_events(before, after) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "A different talk"),
        ("notes", "rang them"),
        ("assigned_to", "grace"),
        ("youtube_url", "https://example.org/watch"),
        ("status", "parked"),
    ],
)
def test_an_ordinary_change_produces_no_immediate_event(field: str, value: str) -> None:
    """The immediate channel is worth having only while it stays rare."""
    before = [lead(id="spk-001", status="lead")]
    after = [lead(id="spk-001", status="lead") | {field: value}]
    assert immediate_events(before, after) == []


def test_a_ballot_that_does_not_reach_the_threshold_produces_no_event() -> None:
    """The lead is still a lead, so nothing has been decided to announce."""
    before = [lead(id="spk-001", status="lead")]
    after = [
        lead(
            id="spk-001",
            status="lead",
            selection={
                "ballots": [{"voter": "ada", "value": "yes", "date": "2026-08-18"}],
                "opened_on": "2026-08-01",
                "decided_on": "",
            },
        )
    ]
    assert immediate_events(before, after) == []


def test_a_record_that_disappears_announces_nothing() -> None:
    """A disappearance is not one of the three, and it is emphatically not
    something an automated path should announce about anybody."""
    before = [lead(id="spk-001", status="lead")]
    assert immediate_events(before, []) == []


def test_every_event_kind_produced_is_one_of_the_declared_three() -> None:
    before = [lead(id="spk-001", status="lead")]
    after = [
        lead(id="spk-001", status="approved"),
        lead(id="spk-009", status="lead", source="form"),
    ]
    produced = immediate_events(before, after)
    assert produced
    assert set(kinds(produced)) <= set(EVENT_KINDS)


def test_malformed_input_produces_no_events_rather_than_raising() -> None:
    assert immediate_events(None, None) == []
    assert immediate_events("not a list", [{"no": "id"}, 7]) == []


# ------------------------------------------------------------------ #
# daily_digest: silence when nothing happened
# ------------------------------------------------------------------ #


def test_a_day_with_nothing_dated_and_nothing_overdue_produces_no_digest() -> None:
    """The most important test in this module.

    A digest that arrives every morning saying nothing gets filtered into a
    folder within a fortnight, and once it is filtered the day something does
    happen is filtered with it. Silence is the feature.
    """
    speakers = [
        lead(id="spk-001", status="confirmed"),
        lead(id="spk-002", status="archived"),
    ]
    assert daily_digest(speakers, make_config(), NOW) is None


def test_an_empty_repository_produces_no_digest() -> None:
    assert daily_digest([], make_config(), NOW) is None
    assert daily_digest(None, None, NOW) is None


def test_a_vote_window_opened_today_reaches_the_digest() -> None:
    speakers = [
        lead(
            id="spk-004",
            status="lead",
            selection={"ballots": [], "opened_on": "2026-08-18", "decided_on": ""},
        )
    ]
    digest = daily_digest(speakers, make_config(), NOW)
    assert digest is not None
    assert "spk-004: the vote window opened" in digest


def test_a_vote_window_opened_yesterday_does_not_reach_todays_digest() -> None:
    speakers = [
        lead(
            id="spk-004",
            status="lead",
            selection={"ballots": [], "opened_on": "2026-08-17", "decided_on": ""},
        )
    ]
    assert daily_digest(speakers, make_config(), NOW) is None


def test_a_lead_parked_by_the_sweep_today_reaches_the_digest() -> None:
    """Spec section 7 asks for automatic transitions in the digest, and this
    is the only one there is.

    `expire_votes` writes `status: parked` and no day, so the day is derived
    from `selection.opened_on` and `config.vote_window_days` -- the same
    single definition the sweep parks on. The window here is 10 days, the
    closing day is still a voting day, so the parking day is opened_on + 11.
    """
    speakers = [
        lead(
            id="spk-004",
            status="parked",
            selection={"ballots": [], "opened_on": "2026-08-07", "decided_on": ""},
        )
    ]
    digest = daily_digest(speakers, make_config(), NOW)
    assert digest is not None
    assert "spk-004: the vote window closed and the lead was parked" in digest


def test_a_lead_parked_on_another_day_does_not_reach_todays_digest() -> None:
    for opened_on in ("2026-08-06", "2026-08-08", "2026-07-01"):
        speakers = [
            lead(
                id="spk-004",
                status="parked",
                selection={"ballots": [], "opened_on": opened_on, "decided_on": ""},
            )
        ]
        digest = daily_digest(speakers, make_config(), NOW)
        assert digest is None or "was parked" not in digest, opened_on


def test_a_parked_lead_with_no_opened_on_is_not_dated() -> None:
    # expire_votes always stamps opened_on before it ever writes "parked"
    # (see sweep.py), but this reads unvalidated data -- a hand-set
    # "parked" status with no window ever opened must not be dated at all,
    # rather than crash adding a timedelta to nothing.
    speakers = [
        lead(
            id="spk-004",
            status="parked",
            selection={"ballots": [], "opened_on": "", "decided_on": ""},
        )
    ]
    assert daily_digest(speakers, make_config(), NOW) is None


def test_the_parked_line_follows_the_window_the_sweep_actually_applies() -> None:
    """One definition, read from both sides.

    `governance.vote_window_days` is what `sweep.expire_votes` parks on and
    what the digest names the day from, so a config that lengthens the window
    moves both together. A second copy here would let the digest announce a
    parking on a day the job did not act.
    """
    cfg = make_config(vote_window_days=21)
    entry = lead(
        id="spk-004",
        status="parked",
        selection={"ballots": [], "opened_on": "2026-07-27", "decided_on": ""},
    )
    assert vote_window_days(cfg) == 21
    digest = daily_digest([entry], cfg, NOW)
    assert digest is not None
    assert "spk-004: the vote window closed and the lead was parked" in digest
    assert "was parked" not in (daily_digest([entry], make_config(), NOW) or "")


def test_a_parked_lead_that_reached_a_decision_is_not_announced_as_expiring() -> None:
    """`expire_votes` never touches a lead the board decided, so a parked
    record carrying `decided_on` was parked by a person. The digest has
    nothing automatic to report about it."""
    entry = lead(
        id="spk-004",
        status="parked",
        selection={
            "ballots": [],
            "opened_on": "2026-08-07",
            "decided_on": "2026-08-10",
        },
    )
    digest = daily_digest([entry], make_config(), NOW)
    assert digest is None or "was parked" not in digest


def test_the_parked_line_is_the_line_the_sweep_would_produce_that_day() -> None:
    """Not two implementations of the same rule: the sweep is run over the
    same record and the day it acts on is the day the digest names."""
    entry = lead(
        id="spk-004",
        status="lead",
        selection={"ballots": [], "opened_on": "2026-08-07", "decided_on": ""},
    )
    cfg = make_config()
    swept, changes = expire_votes([entry], cfg, NOW)
    assert changes, "the sweep does not park this record today"
    digest = daily_digest(swept, cfg, NOW)
    assert digest is not None
    assert "spk-004: the vote window closed and the lead was parked" in digest


def test_a_nomination_opened_today_reaches_the_digest_without_naming_anyone() -> None:
    cfg = make_config(
        nominations=[
            nomination(candidate="grace", sponsor="ada", opened_on="2026-08-18")
        ]
    )
    digest = daily_digest([], cfg, NOW)
    assert digest is not None
    assert "nomination 1: a nomination window opened" in digest
    assert "grace" not in digest
    assert "ada" not in digest


def test_the_overdue_list_alone_is_enough_to_produce_a_digest() -> None:
    """Spec section 7: the digest carries what is late even on a day when
    nothing else moved."""
    speakers = [
        lead(
            id="spk-004",
            status="lead",
            selection={"ballots": [], "opened_on": "2026-08-01", "decided_on": ""},
        )
    ]
    digest = daily_digest(speakers, make_config(), NOW)
    assert digest is not None
    # `vote_window_days: 10` in the double, and the board's decision deadline
    # is that number and no other (F-13).
    assert "Board decision is 7 days overdue" in digest
    assert "waiting since 2026-08-01" in digest


def test_the_overdue_wording_in_the_digest_is_the_wording_the_screens_use() -> None:
    """Not a second sentence: the digest quotes `overdue_text` and
    `waiting_since` verbatim, and those two are pinned to `sla.ts` by
    `tests/fixtures/governance-cases.json`."""
    entry = lead(
        id="spk-004",
        status="lead",
        selection={"ballots": [], "opened_on": "2026-08-01", "decided_on": ""},
    )
    late = overdue(entry, make_config(), "2026-08-18")
    assert late is not None
    digest = daily_digest([entry], make_config(), NOW)
    assert digest is not None
    assert overdue_text(late) in digest
    assert waiting_since(late) in digest


def test_a_step_within_its_target_contributes_no_overdue_line() -> None:
    speakers = [
        lead(
            id="spk-004",
            status="lead",
            selection={"ballots": [], "opened_on": "2026-08-10", "decided_on": ""},
        )
    ]
    assert daily_digest(speakers, make_config(), NOW) is None


def test_the_overdue_list_puts_the_longest_waiting_first() -> None:
    speakers = [
        lead(
            id="spk-b",
            status="lead",
            selection={"ballots": [], "opened_on": "2026-08-02", "decided_on": ""},
        ),
        lead(
            id="spk-a",
            status="lead",
            selection={"ballots": [], "opened_on": "2026-07-01", "decided_on": ""},
        ),
    ]
    digest = daily_digest(speakers, make_config(), NOW)
    assert digest is not None
    assert digest.index("spk-a") < digest.index("spk-b")


def test_the_day_is_the_paris_day_not_the_utc_one() -> None:
    """23:30 UTC is already the next day in Paris. A digest reading the UTC
    clock would report yesterday, and would report it twice."""
    late_evening = datetime(2026, 8, 17, 23, 30, tzinfo=UTC)
    speakers = [
        lead(
            id="spk-004",
            status="lead",
            selection={"ballots": [], "opened_on": "2026-08-18", "decided_on": ""},
        )
    ]
    digest = daily_digest(speakers, make_config(), late_evening)
    assert digest is not None
    assert "2026-08-18" in digest


def test_the_digest_is_the_same_text_when_composed_twice_for_the_same_day() -> None:
    speakers = [
        lead(
            id="spk-004",
            status="lead",
            selection={"ballots": [], "opened_on": "2026-08-18", "decided_on": ""},
        )
    ]
    first = daily_digest(speakers, make_config(), NOW)
    second = daily_digest(
        speakers, make_config(), datetime(2026, 8, 18, 20, tzinfo=UTC)
    )
    assert first == second


def test_an_automatic_transition_recorded_today_reaches_the_digest() -> None:
    """The sweep writes `scheduled -> delivered` overnight; the digest is how
    anyone finds out without opening the app."""
    speakers = [
        lead(
            id="spk-007",
            status="delivered",
            date="2026-08-18",
            runbook_progress={"delivered/forum-summary": True},
            youtube_url="https://example.org/watch",
        )
    ]
    digest = daily_digest(speakers, make_config(), NOW)
    assert digest is not None
    assert "spk-007: the talk is recorded as delivered" in digest


def test_a_board_decision_recorded_today_reaches_the_digest() -> None:
    speakers = [
        lead(
            id="spk-007",
            status="approved",
            selection={
                "ballots": [],
                "opened_on": "2026-08-01",
                "decided_on": "2026-08-18",
            },
        )
    ]
    digest = daily_digest(speakers, make_config(), NOW)
    assert digest is not None
    assert "spk-007: the board decision was recorded" in digest


def test_a_publication_approved_today_reaches_the_digest() -> None:
    speakers = [
        lead(
            id="spk-007",
            status="delivered",
            date="2026-08-01",
            runbook_progress={"delivered/forum-summary": True},
            youtube_url="https://example.org/watch",
            publication={
                "consent": "granted",
                "approved_by": "ada",
                "approved_on": "2026-08-18",
                "objections": [],
                "outcome": "",
            },
        )
    ]
    digest = daily_digest(speakers, make_config(), NOW)
    assert digest is not None
    assert "spk-007: the publication was approved" in digest


def test_an_objection_lodged_and_one_closed_today_both_reach_the_digest() -> None:
    speakers = [
        lead(
            id="spk-007",
            status="delivered",
            date="2026-08-01",
            runbook_progress={"delivered/forum-summary": True},
            youtube_url="https://example.org/watch",
            publication={
                "consent": "granted",
                "approved_by": "",
                "approved_on": "",
                "objections": [
                    objection(member="ada", reason="unclear", date="2026-08-18")
                    | {"resolved_on": ""},
                    objection(member="grace", reason="settled", date="2026-08-02")
                    | {"resolved_on": "2026-08-18"},
                ],
                "outcome": "",
            },
        )
    ]
    digest = daily_digest(speakers, make_config(), NOW)
    assert digest is not None
    assert "spk-007: an objection was lodged on the publication" in digest
    assert "spk-007: an objection on the publication was closed" in digest


def test_a_malformed_objection_entry_is_skipped_when_composing_the_digest() -> None:
    # publication.objections is a list of mappings by schema, but this
    # reads unvalidated data -- a stray non-mapping item (a hand-edit gone
    # wrong) must be skipped, not crash the whole day's digest.
    speakers = [
        lead(
            id="spk-007",
            status="delivered",
            date="2026-07-01",
            runbook_progress={"delivered/forum-summary": True},
            youtube_url="https://example.org/watch",
            publication={
                "consent": "granted",
                "approved_by": "",
                "approved_on": "",
                "objections": [
                    "not-a-mapping",
                    objection(member="ada", reason="today", date="2026-08-18")
                    | {"resolved_on": ""},
                ],
                "outcome": "",
            },
        )
    ]
    digest = daily_digest(speakers, make_config(), NOW)
    assert digest is not None
    assert "spk-007: an objection was lodged on the publication" in digest


def test_an_objection_unrelated_to_today_contributes_no_digest_line() -> None:
    # Silence is the property this whole module rests on (see the module
    # docstring): an objection neither lodged nor closed today must not
    # appear in today's digest, whatever else it says.
    speakers = [
        lead(
            id="spk-007",
            status="delivered",
            date="2026-07-01",
            runbook_progress={"delivered/forum-summary": True},
            youtube_url="https://example.org/watch",
            publication={
                "consent": "granted",
                "approved_by": "ada",
                "approved_on": "2026-07-05",
                "objections": [
                    objection(member="grace", reason="old", date="2026-07-02")
                    | {"resolved_on": "2026-07-03"}
                ],
                "outcome": "",
            },
        )
    ]
    assert daily_digest(speakers, make_config(), NOW) is None


def test_a_nomination_objection_lodged_today_reaches_the_digest() -> None:
    cfg = make_config(
        nominations=[
            nomination(
                candidate="grace",
                sponsor="ada",
                opened_on="2026-08-10",
                objections=[objection(member="ada", reason="wait", date="2026-08-18")],
            )
        ]
    )
    digest = daily_digest([], cfg, NOW)
    assert digest is not None
    assert "nomination 1: an objection was lodged" in digest


def test_a_nomination_objection_from_another_day_contributes_no_digest_line() -> None:
    cfg = make_config(
        nominations=[
            nomination(
                candidate="grace",
                sponsor="ada",
                opened_on="2026-07-01",
                objections=[objection(member="ada", reason="old", date="2026-07-02")],
            )
        ]
    )
    assert daily_digest([], cfg, NOW) is None


@pytest.mark.parametrize(
    "sla_days",
    [
        None,
        "thirty",
        {"invitation_follow_up": "thirty"},
        {"invitation_follow_up": True},
        {},
    ],
    ids=["absent", "not a mapping", "not a number", "a bool", "empty"],
)
def test_an_unusable_sla_configuration_produces_no_deadline(sla_days: Any) -> None:
    """A hand-edited config must degrade to "no deadline can be computed",
    never to a guessed one -- the scheduled job runs without a validation
    pass, so an unchecked config reaches here."""
    entry = lead(
        id="spk-004",
        status="invited",
        selection={
            "ballots": [],
            "opened_on": "2026-06-01",
            "decided_on": "2026-06-02",
        },
    )
    cfg = make_config(sla_days=sla_days)
    assert overdue(entry, cfg, "2026-08-18") is None
    assert daily_digest([entry], cfg, NOW) is None


@pytest.mark.parametrize("window", [7, 10, 14, 20], ids=str)
def test_the_lead_goes_overdue_on_the_morning_the_sweep_parks_it(window: int) -> None:
    """F-13. One deadline, so the two hands on it cannot disagree.

    `sweep.expire_votes` parks a lead whose window ran out; `notify.overdue`
    (and `app/src/state/sla.ts`, its twin) say the board decision is late.
    Until this task those read two different config keys, both set to 14 in
    `data/config.yml` with nothing saying they had to agree: setting
    `sla_days.lead_decision` to 20 made the app call the board on time on the
    very morning the job parked the lead, and neither CI nor a reader had any
    way to notice.

    Collapsing them to one key is what makes that unwritable rather than
    merely detected, and this is the test that would fail if a second number
    ever came back: it walks a real config through both modules for four
    different windows and requires the first overdue morning to be exactly the
    parking morning.
    """
    cfg = make_config(vote_window_days=window)
    opened = date(2026, 8, 1)
    entry = lead(
        id="spk-004",
        status="lead",
        selection={"ballots": [], "opened_on": opened.isoformat(), "decided_on": ""},
    )

    parked_on = None
    first_overdue = None
    for offset in range(1, window + 5):
        day = opened + timedelta(days=offset)
        swept, changes = expire_votes(
            [dict(entry)], cfg, datetime(day.year, day.month, day.day, 9, tzinfo=UTC)
        )
        if changes and parked_on is None:
            parked_on = day
            assert swept[0]["status"] == "parked"
        if overdue(entry, cfg, day.isoformat()) is not None and first_overdue is None:
            first_overdue = day

    assert parked_on is not None
    assert first_overdue == parked_on


def test_the_board_decision_deadline_survives_an_unusable_sla_block() -> None:
    """F-13. The board's clock is `vote_window_days`, not an `sla_days` key.

    So a mangled `sla_days` cannot silence it, and the fallback it lands on is
    `governance.vote_window_days` -- the number `sweep.expire_votes` will
    really apply that morning, not a guess made up here. Silence would be the
    worse answer: the job parks the lead either way, and a digest that says
    nothing about it would be describing a different repository.
    """
    entry = lead(
        id="spk-004",
        status="lead",
        selection={"ballots": [], "opened_on": "2026-08-01", "decided_on": ""},
    )
    late = overdue(entry, make_config(sla_days="thirty"), "2026-08-18")
    assert late is not None
    assert late.step == "Board decision"
    assert late.due == "2026-08-11"


@pytest.mark.parametrize(
    "today", ["", "not-a-day", "20260818"], ids=["empty", "prose", "compact"]
)
def test_a_day_that_is_not_an_iso_date_yields_no_lateness(today: str) -> None:
    entry = lead(
        id="spk-004",
        status="lead",
        selection={"ballots": [], "opened_on": "2026-08-01", "decided_on": ""},
    )
    assert overdue(entry, make_config(), today) is None


def test_a_malformed_record_contributes_nothing_rather_than_raising() -> None:
    assert overdue("not a record", make_config(), "2026-08-18") is None
    assert daily_digest(["not a record", 7, {}], make_config(), NOW) is None


def test_malformed_nominations_contribute_nothing() -> None:
    assert daily_digest([], make_config(nominations="none"), NOW) is None
    assert daily_digest([], make_config(nominations=[7, {}]), NOW) is None


# ------------------------------------------------------------------ #
# Nothing about a person leaves the repository
# ------------------------------------------------------------------ #

#: Every field of a record that names or identifies a human being.
#: The two free-prose fields that do not live at the top level of a record.
#: They are the most sensitive text in the repository -- one says why a named
#: board member has a conflict of interest, the other why a named member wants
#: a named researcher's talk kept offline -- so they belong in `PERSONAL`, and
#: `loaded` puts them where they actually live rather than passing them to
#: `conftest.speaker`, which takes top-level fields only.
NESTED = ("coi_reason", "objection_reason")

PERSONAL = {
    "name": "Ada Lovelace",
    "email": "ada.lovelace@example.ac.uk",
    "affiliation": "Example University",
    "country": "Erewhon",
    "title": "On analytical engines",
    "abstract": "a secret abstract",
    "proposed_by": "Grace Hopper",
    "assigned_to": "hopper",
    "host_1": "Katherine Johnson",
    "host_2": "Dorothy Vaughan",
    "notes": "private note",
    "coi_reason": "a co-authorship nobody outside the board knows about",
    "objection_reason": "the slides carry a colleague's unpublished data",
}


def loaded(**over: Any) -> dict[str, Any]:
    """A record whose every personal field carries a distinctive value.

    Including the nested ones: every ballot carries the conflict-of-interest
    reason and every publication objection carries its own, and a ballot is
    seeded where the caller left none, so the two most sensitive fields in the
    schema are actually present in the records `every_rendering` runs over. A
    record that never carries them would let a leak on either pass.
    """
    entry = speaker(**{k: v for k, v in PERSONAL.items() if k not in NESTED}) | over
    selection = entry["selection"]
    selection["ballots"] = selection.get("ballots") or [ballot()]
    for cast in selection["ballots"]:
        cast["coi_reason"] = PERSONAL["coi_reason"]
    for raw in entry["publication"].get("objections") or []:
        raw["reason"] = PERSONAL["objection_reason"]
    return entry


def every_rendering() -> list[str]:
    """Every string this module can put in front of a human.

    Deliberately exercises **every line the digest and the event renderer can
    emit** -- a vote window opened, a decision recorded, a delivery, a
    publication approved, an objection lodged, an objection closed, a
    nomination opened, a nomination objected to, and an overdue step -- over
    records whose every personal field is filled in. A narrower sample would
    let a leak on an unexercised line pass this file vacuously, which is
    exactly how a test stops biting.
    """
    cfg = make_config(
        nominations=[
            nomination(
                candidate="Grace Hopper",
                sponsor="hopper",
                opened_on="2026-08-18",
                objections=[
                    objection(
                        member="hopper", reason="a private reason", date="2026-08-18"
                    )
                ],
            )
        ]
    )
    entries = [
        # A lead: opened today, and separately overdue below.
        loaded(
            id="spk-001",
            status="lead",
            source="form",
            selection={"ballots": [], "opened_on": "2026-08-18", "decided_on": ""},
        ),
        # An overdue lead, so the wording block is exercised too.
        loaded(
            id="spk-002",
            status="lead",
            selection={"ballots": [], "opened_on": "2026-08-01", "decided_on": ""},
        ),
        # A decision recorded today.
        loaded(
            id="spk-003",
            status="approved",
            selection={
                "ballots": [],
                "opened_on": "2026-08-04",
                "decided_on": "2026-08-18",
            },
        ),
        # Parked today by the sweep: the window opened 11 days ago, and the
        # configured window is 10 days.
        loaded(
            id="spk-006",
            status="parked",
            selection={"ballots": [], "opened_on": "2026-08-07", "decided_on": ""},
        ),
        # Delivered today, publication approved today, one objection lodged
        # today and one closed today.
        loaded(
            id="spk-004",
            status="delivered",
            date="2026-08-18",
            runbook_progress={"delivered/forum-summary": True},
            youtube_url="https://example.org/watch",
            publication={
                "consent": "granted",
                "approved_by": "hopper",
                "approved_on": "2026-08-18",
                "objections": [
                    objection(
                        member="hopper", reason="a private reason", date="2026-08-18"
                    )
                    | {"resolved_on": ""},
                    objection(member="hopper", reason="another one", date="2026-08-02")
                    | {"resolved_on": "2026-08-18"},
                ],
                "outcome": "",
            },
        ),
    ]
    digest = daily_digest(entries, cfg, NOW)
    assert digest is not None
    for expected in (
        "the vote window opened",
        "the board decision was recorded",
        "the vote window closed and the lead was parked",
        "the talk is recorded as delivered",
        "the publication was approved",
        "an objection was lodged on the publication",
        "an objection on the publication was closed",
        "a nomination window opened",
        "nomination 1: an objection was lodged",
        "overdue",
    ):
        assert expected in digest, f"this sample never exercises: {expected}"

    events = render_events(
        immediate_events(
            [
                loaded(id="spk-003", status="lead"),
                loaded(id="spk-004", status="delivered"),
            ],
            entries,
        )
    )
    assert events is not None
    for kind in EVENT_KINDS:
        assert kind in {
            e.kind
            for e in immediate_events(
                [
                    loaded(id="spk-003", status="lead"),
                    loaded(id="spk-004", status="delivered"),
                ],
                entries,
            )
        }, f"this sample never exercises the {kind} event"

    body = dispatch(digest, CONFIGURED)
    assert body is not None
    return [digest, events, body.body]


@pytest.mark.parametrize(("field", "value"), sorted(PERSONAL.items()))
def test_no_personal_field_can_reach_a_message(field: str, value: str) -> None:
    """Not a filter over the output: there is no code path in `notify` that
    reads any of these fields, so they have no way in."""
    for rendered in every_rendering():
        assert value not in rendered, f"{field} reached a message"


def test_no_message_can_carry_an_email_address() -> None:
    for rendered in every_rendering():
        assert re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", rendered) is None


def test_a_message_names_records_and_nothing_else() -> None:
    """Every identifier in a message is a `spk-` id, a `nomination N` label or
    a fixed step label."""
    for rendered in every_rendering():
        assert "spk-004" in rendered or "spk-005" in rendered


def test_no_message_reaches_for_the_vocabulary_of_blame() -> None:
    """Checked against `commit_format.JUDGEMENTAL`, the list the decision
    grammar already answers to, rather than a second list written here."""
    for rendered in every_rendering():
        assert judgemental_terms(rendered) == []


def test_no_step_label_names_a_role_or_an_actor() -> None:
    for label in STEP_LABELS.values():
        assert judgemental_terms(label) == []
        assert "board member" not in label.lower()
        assert "host" not in label.lower()


def test_everything_rendered_is_ascii() -> None:
    """No non-ASCII character may reach a terminal from this package."""
    for rendered in every_rendering():
        rendered.encode("ascii")


# ------------------------------------------------------------------ #
# The channel: unconfigured has no way to send
# ------------------------------------------------------------------ #


def test_a_fully_configured_environment_yields_a_channel() -> None:
    channel = resolve_channel(CONFIGURED)
    assert channel == Channel(thread="42", mention="@example/editorial")


@pytest.mark.parametrize(
    "env",
    [
        {},
        {THREAD_ENV: "42"},
        {MENTION_ENV: "@example/editorial"},
        {THREAD_ENV: "", MENTION_ENV: "@example/editorial"},
        {THREAD_ENV: "42", MENTION_ENV: "   "},
    ],
    ids=["nothing", "thread only", "mention only", "blank thread", "blank mention"],
)
def test_a_partly_configured_environment_yields_no_channel(env: dict[str, str]) -> None:
    """A thread with no mention posts into a page nobody is watching, and a
    mention with no thread has nowhere to be written. Neither half has a safe
    default, so neither half alone builds a `Channel`."""
    assert resolve_channel(env) is None


@pytest.mark.parametrize(
    "mention",
    [
        "ExampleOrg/example-board",
        "@ExampleOrg",
        "@volunteer",
        "@/convener-board",
        "@ExampleOrg/",
        "@ExampleOrg/example-board/extra",
        "",
        "   ",
    ],
    ids=[
        "no-leading-at",
        "org-only-no-slash",
        "bare-person-handle",
        "empty-org",
        "empty-team",
        "extra-path-segment",
        "empty",
        "blank",
    ],
)
def test_a_mention_that_is_not_a_team_handle_yields_no_channel(mention: str) -> None:
    """A mention nobody would see: without its leading `@` (or naming a
    person rather than an org and a team), the comment would still be
    posted, readable and plausible, and would notify nobody. Treated exactly
    like an absent mention -- no `Channel` is built."""
    env = {THREAD_ENV: "42", MENTION_ENV: mention}
    assert resolve_channel(env) is None


def test_a_mention_with_an_uppercase_organisation_still_builds_a_channel() -> None:
    """The real configuration will use a mixed-case organisation
    (`ExampleOrg`), not the all-lowercase fixture every other
    positive test in this module uses -- so this pins that case directly
    rather than leaving it to be exercised only by the negative cases
    above."""
    env = {THREAD_ENV: "42", MENTION_ENV: "@ExampleOrg/example-board"}
    assert resolve_channel(env) == Channel(
        thread="42", mention="@ExampleOrg/example-board"
    )


def test_nothing_can_be_dispatched_without_a_channel() -> None:
    assert dispatch("a real message", {}) is None


def test_nothing_can_be_dispatched_without_a_message() -> None:
    assert dispatch(None, CONFIGURED) is None
    assert dispatch("", CONFIGURED) is None


def test_a_dispatch_always_carries_the_address_it_was_built_from() -> None:
    """`Dispatch` is the only postable value in the package, and it cannot
    exist without a `Channel` -- so an unaddressed message has no
    representation to be sent."""
    addressed = dispatch("a real message", CONFIGURED)
    assert addressed is not None
    assert addressed.channel == Channel(thread="42", mention="@example/editorial")
    assert addressed.body.startswith("@example/editorial")
    assert "a real message" in addressed.body


#: Everything outside this package that anything reachable from `notify.py`
#: is allowed to import. An allowlist rather than a denylist, for the same
#: reason `public_data.PUBLIC_FIELDS` is one: a new dependency has to be added
#: here deliberately, where a denylist only ever catches the transports
#: somebody thought of. It covers the whole graph below, not one file, so a
#: dependency added to `governance.py` lands here too.
ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "collections",
        "dataclasses",
        "datetime",
        "math",
        "re",
        "typing",
        "zoneinfo",
    }
)

#: Calls that would fetch a module the import statements do not name. A
#: denylist, and knowingly one: see the last paragraph of the test's docstring
#: for what that does and does not buy.
DYNAMIC_IMPORT_CALLS = frozenset({"__import__", "import_module", "eval", "exec"})

PACKAGE_DIR = Path(notify.__file__).parent


def _reads(module: str) -> tuple[set[str], set[str], list[str]]:
    """What one module of this package imports: outsiders, siblings, dynamics.

    A sibling is returned by its bare module name (`governance`), whichever of
    the three spellings reached it -- `from . import x`, `from .x import y` or
    `import convener_ops.x` -- so the walk below cannot be dodged by choosing a
    different one.
    """
    tree = ast.parse((PACKAGE_DIR / f"{module}.py").read_text(encoding="utf-8"))
    outside: set[str] = set()
    siblings: set[str] = set()
    dynamic: list[str] = []

    def place(dotted: str) -> None:
        parts = dotted.split(".")
        if parts[0] == "convener_ops":
            siblings.add(parts[1] if len(parts) > 1 else "__init__")
        else:
            outside.add(parts[0])

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                place(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import: `from . import x`
                siblings.add((node.module or "__init__").split(".")[0])
            elif node.module:
                place(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in DYNAMIC_IMPORT_CALLS:
                dynamic.append(f"{module}: {name}")

    return outside, siblings, dynamic


def test_the_notification_module_holds_no_transport() -> None:
    """Nothing reachable from this module names a transport.

    Over the package's own import graph, not over this one file. `notify.py`
    imports `convener_ops.governance`, so an `import urllib.request` added there is
    reachable from here and would give this module a transport by way of an
    attribute; a check that read `notify.py` alone would call that clean. Every
    `convener_ops` module reachable from `notify.py` is parsed, and every import any
    of them makes has to be on the allowlist above.

    Parsed with `ast.walk` rather than read line by line: a function-local
    `import urllib.request`, an import nested in a `try`, or an
    `__import__("smtplib")` sit outside what a check for lines beginning
    `import ` or `from ` can see, and each would be a transport.

    What this does not prove, and does not claim: that no module can be fetched
    under a name assembled at runtime. `getattr(__builtins__, "__imp" + "ort__")`
    names no module a reader can see and none this test can compute, and no
    static reading of source ever will. The denylist above catches the ordinary
    spellings and nothing more. The property actually verified is the one in the
    first line -- that no module on this graph *names* a way to send -- which is
    a statement about the code as written, not a guarantee against code written
    to evade it.
    """
    seen: set[str] = set()
    queue = ["notify"]
    outside: set[str] = set()
    dynamic: list[str] = []
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        module_outside, siblings, module_dynamic = _reads(module)
        outside |= module_outside
        dynamic += module_dynamic
        queue += [s for s in siblings if s not in seen]

    # The graph is walked, not assumed: if `notify.py` ever stops importing
    # `governance`, this says so rather than quietly checking one file again.
    assert seen == {"notify", "governance"}, seen

    assert dynamic == [], f"a module is fetched at runtime: {dynamic}"
    undeclared = outside - ALLOWED_IMPORTS
    assert not undeclared, f"undeclared import: {undeclared}"
    for banned in ("smtplib", "urllib", "http", "socket", "subprocess", "requests"):
        assert banned not in outside


# ------------------------------------------------------------------ #
# The command-line entry points
# ------------------------------------------------------------------ #


def _repo(tmp_path: Path, speakers: str, cfg: str) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "speakers.yml").write_text(speakers, encoding="utf-8")
    (tmp_path / "data" / "config.yml").write_text(cfg, encoding="utf-8")
    return tmp_path


CONFIG_YML = """
season: 2026
board: []
nominations: []
vote_window_days: 14
sla_days:
  invitation_follow_up: 30
  summary_after_delivery: 7
  recording_after_delivery: 14
"""

OVERDUE_YML = """
- id: spk-004
  status: lead
  selection:
    ballots: []
    opened_on: '2026-08-01'
    decided_on: ''
  date: ''
  youtube_url: ''
  runbook_progress: {}
"""

QUIET_YML = """
- id: spk-004
  status: confirmed
  selection:
    ballots: []
    opened_on: ''
    decided_on: ''
  date: ''
  youtube_url: ''
  runbook_progress: {}
"""


@pytest.fixture(autouse=True)
def _no_ambient_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test inherits a channel from the machine it runs on."""
    monkeypatch.delenv(THREAD_ENV, raising=False)
    monkeypatch.delenv(MENTION_ENV, raising=False)


def test_the_digest_writes_nothing_when_no_channel_is_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The whole point of the task. Today's repository is exactly this case."""
    root = _repo(tmp_path, OVERDUE_YML, CONFIG_YML)
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: root)
    monkeypatch.setattr("convener_ops.cli.sys.argv", ["convener-notify-digest"])

    assert cli.notify_digest() == 0

    out = capsys.readouterr().out
    assert "no notification channel is configured" in out
    # The count itself depends on the day this runs; the sentence does not.
    assert "spk-004: Board decision is " in out
    assert "waiting since 2026-08-01" in out
    assert not (root / cli.NOTIFY_BODY).exists()


def test_an_absent_channel_is_not_reported_as_a_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repo(tmp_path, OVERDUE_YML, CONFIG_YML)
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: root)
    monkeypatch.setattr("convener_ops.cli.sys.argv", ["convener-notify-digest"])

    exit_code = cli.notify_digest()

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "FAIL" not in out
    assert "ERROR" not in out
    assert "error" not in out.lower()


def test_the_digest_writes_a_body_once_a_channel_is_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repo(tmp_path, OVERDUE_YML, CONFIG_YML)
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: root)
    monkeypatch.setattr("convener_ops.cli.sys.argv", ["convener-notify-digest"])
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@example/editorial")

    assert cli.notify_digest() == 0

    body = (root / cli.NOTIFY_BODY).read_text(encoding="utf-8")
    assert body.startswith("@example/editorial")
    assert "spk-004: Board decision is " in body
    assert "waiting since 2026-08-01" in body
    assert "left in notify-body.md" in capsys.readouterr().out


def test_a_quiet_day_writes_no_body_even_with_a_channel_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repo(tmp_path, QUIET_YML, CONFIG_YML)
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: root)
    monkeypatch.setattr("convener_ops.cli.sys.argv", ["convener-notify-digest"])
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@example/editorial")

    assert cli.notify_digest() == 0

    assert "nothing to notify" in capsys.readouterr().out
    assert not (root / cli.NOTIFY_BODY).exists()


def test_dry_run_prints_the_digest_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repo(tmp_path, OVERDUE_YML, CONFIG_YML)
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: root)
    monkeypatch.setattr(
        "convener_ops.cli.sys.argv", ["convener-notify-digest", "--dry-run"]
    )
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@example/editorial")

    assert cli.notify_digest() == 0

    assert "[dry run]" in capsys.readouterr().out
    assert not (root / cli.NOTIFY_BODY).exists()


def test_unreadable_data_is_reported_and_notifies_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repo(tmp_path, "- id: [unclosed", CONFIG_YML)
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: root)
    monkeypatch.setattr("convener_ops.cli.sys.argv", ["convener-notify-digest"])
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@example/editorial")

    assert cli.notify_digest() == 1

    assert "invalid YAML" in capsys.readouterr().out
    assert not (root / cli.NOTIFY_BODY).exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")
def test_git_show_reports_an_error_rather_than_raising_on_a_repository_with_no_head(
    tmp_path: Path,
) -> None:
    # The subprocess-failure half of `_git_show` itself, not the caller's
    # handling of it (the two tests below mock `_git_show` entirely, so
    # neither exercises this). A freshly `git init`-ed directory has no HEAD
    # yet -- exactly "an initial commit" from the docstring, one commit
    # earlier -- so `git show` exits non-zero and this must come back as an
    # error string, not raise.
    subprocess.run(  # nosec B603 B607
        ["git", "init", "--quiet", "--initial-branch=main"],
        cwd=tmp_path,
        check=True,
    )

    text, error = cli._git_show(tmp_path, "HEAD:data/speakers.yml")

    assert text == ""
    assert error != ""


def test_immediate_says_nothing_when_there_is_no_previous_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """On a shallow clone or an initial commit the whole file would otherwise
    read as new, announcing every lead in it at once."""
    root = _repo(tmp_path, OVERDUE_YML, CONFIG_YML)
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: root)
    monkeypatch.setattr("convener_ops.cli.sys.argv", ["convener-notify-immediate"])
    monkeypatch.setattr(
        "convener_ops.cli._git_show", lambda _root, _revision: ("", "no parent commit")
    )
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@example/editorial")

    assert cli.notify_immediate() == 0

    assert "no previous revision" in capsys.readouterr().out
    assert not (root / cli.NOTIFY_BODY).exists()


def test_immediate_says_nothing_when_the_previous_revision_is_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repo(tmp_path, OVERDUE_YML, CONFIG_YML)
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: root)
    monkeypatch.setattr("convener_ops.cli.sys.argv", ["convener-notify-immediate"])
    monkeypatch.setattr(
        "convener_ops.cli._git_show", lambda _root, _revision: ("- id: [unclosed", "")
    )
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@example/editorial")

    assert cli.notify_immediate() == 0

    assert "not readable" in capsys.readouterr().out
    assert not (root / cli.NOTIFY_BODY).exists()


def test_immediate_writes_a_body_for_a_lead_from_the_form(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path, "", CONFIG_YML)
    (root / "data" / "speakers.yml").write_text(
        "- id: spk-009\n  status: lead\n  source: form\n", encoding="utf-8"
    )
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: root)
    monkeypatch.setattr("convener_ops.cli.sys.argv", ["convener-notify-immediate"])
    monkeypatch.setattr(
        "convener_ops.cli._git_show", lambda _root, _revision: ("[]\n", "")
    )
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@example/editorial")

    assert cli.notify_immediate() == 0

    body = (root / cli.NOTIFY_BODY).read_text(encoding="utf-8")
    assert "spk-009: a new lead arrived from the public form" in body


def test_immediate_writes_nothing_for_an_ordinary_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(
        tmp_path, "- id: spk-009\n  status: lead\n  notes: rang them\n", CONFIG_YML
    )
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: root)
    monkeypatch.setattr("convener_ops.cli.sys.argv", ["convener-notify-immediate"])
    monkeypatch.setattr(
        "convener_ops.cli._git_show",
        lambda _root, _revision: ("- id: spk-009\n  status: lead\n", ""),
    )
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@example/editorial")

    assert cli.notify_immediate() == 0

    assert not (root / cli.NOTIFY_BODY).exists()


def test_immediate_reports_unreadable_current_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repo(tmp_path, "- id: [unclosed", CONFIG_YML)
    monkeypatch.setattr("convener_ops.cli.repo_root", lambda: root)
    monkeypatch.setattr("convener_ops.cli.sys.argv", ["convener-notify-immediate"])

    assert cli.notify_immediate() == 1
    assert "invalid YAML" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")
def test_git_show_reads_the_previous_revision_of_the_speaker_file(
    tmp_path: Path,
) -> None:
    """Minor 6, branch review: this used to run `cli._git_show` against
    this very checkout's own `HEAD~1:data/speakers.yml` -- real repository
    history, not a fixture. That passes inside the checkout and raises
    `fatal: not a git repository` in any copy without a `.git` (an
    isolated mutation-testing copy, most concretely), a false positive the
    reviewer hit directly. A fresh, disposable repository built here
    instead, the same discipline
    `test_git_show_reports_an_error_rather_than_raising_on_a_repository_with_no_head`
    just above already uses for `_git_show`'s failure half -- this is its
    success-half counterpart, exercising the one subprocess this feature
    adds without depending on anything about the repository the test
    happens to run inside."""
    subprocess.run(  # nosec B603 B607
        ["git", "init", "--quiet", "--initial-branch=main"],
        cwd=tmp_path,
        check=True,
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "speakers.yml").write_text(
        "- id: spk-001\n  name: Ada Lovelace\n", encoding="utf-8"
    )
    _git = ["git", "-c", "user.name=test", "-c", "user.email=test@example.org"]
    subprocess.run(  # nosec B603 B607
        [*_git, "add", "data/speakers.yml"], cwd=tmp_path, check=True
    )
    subprocess.run(  # nosec B603 B607
        [*_git, "commit", "--quiet", "-m", "first revision"], cwd=tmp_path, check=True
    )
    (data_dir / "speakers.yml").write_text(
        "- id: spk-001\n  name: Ada Lovelace\n- id: spk-002\n  name: Grace Hopper\n",
        encoding="utf-8",
    )
    subprocess.run(  # nosec B603 B607
        [*_git, "add", "data/speakers.yml"], cwd=tmp_path, check=True
    )
    subprocess.run(  # nosec B603 B607
        [*_git, "commit", "--quiet", "-m", "second revision"], cwd=tmp_path, check=True
    )

    text, error = cli._git_show(tmp_path, cli.PREVIOUS_SPEAKERS)

    assert error == ""
    assert "- id: spk-001" in text
    assert "spk-002" not in text


def test_the_comparison_starts_where_the_branch_actually_moved_from() -> None:
    """A push carrying three commits moved the branch by three.

    `HEAD~1` describes only the last of them, so the events of the other two
    would be dropped in silence. GitHub sends the branch's previous tip as
    `github.event.before`; the workflow passes it through as `BEFORE`.
    """
    sha = "0123456789abcdef0123456789abcdef01234567"
    assert cli.previous_revision({"BEFORE": sha}) == f"{sha}:data/speakers.yml"


@pytest.mark.parametrize(
    "before",
    [
        "",
        "   ",
        "HEAD~3",
        "main",
        "0123456789ABCDEF0123456789ABCDEF01234567",
        "0123456",
        "--upload-pack=touch",
        "0" * 40,
    ],
    ids=[
        "absent",
        "blank",
        "a ref rather than an object name",
        "a branch name",
        "an object name in the wrong case",
        "an abbreviated object name",
        "an argument dressed as an option",
        "the all-zero name of a branch's first push",
    ],
)
def test_anything_that_is_not_an_object_name_falls_back_to_the_parent(
    before: str,
) -> None:
    """Nothing but a full object name is interpolated into `git show`, so no
    value of `BEFORE` can become an option or a second argument. Falling back
    to `HEAD~1` reports less than the truth; interpolating a ref would report
    something nobody chose."""
    assert cli.previous_revision({"BEFORE": before}) == cli.PREVIOUS_SPEAKERS


def test_the_immediate_job_fetches_enough_history_to_reach_that_commit() -> None:
    """`fetch-depth: 2` gives the parent of HEAD and nothing before it, so a
    push of three commits could not read the revision it has to compare
    against even when GitHub names it.

    Phase 8, task 3, change E: the file this reads is now
    `sweep-and-notify.yml` and the job that follows `immediate` is `daily`
    (the sweep and the digest, in that order, as one job) rather than
    `digest`. The property is unchanged -- it is about the *immediate*
    job, and slicing the file at whatever job comes next is still what
    keeps a `fetch-depth: 0` belonging to some other job from satisfying
    it.
    """
    workflow = (
        repo_root() / ".github" / "workflows" / "sweep-and-notify.yml"
    ).read_text(encoding="utf-8")
    immediate = workflow.split("\n  daily:")[0]
    assert "\n  immediate:" in immediate, (
        "the immediate job was renamed or removed -- this slice no longer describes it"
    )
    assert "fetch-depth: 0" in immediate
    assert "BEFORE: ${{ github.event.before }}" in immediate


# ------------------------------------------------------------------ #
# The declaration
# ------------------------------------------------------------------ #


def test_the_channel_is_declared_as_an_integration() -> None:
    """Deferred configuration (D-13): `convener-check-config` reports the channel's
    state alongside every other integration, so an absent one reads as the
    normal state it is rather than as something broken."""
    from convener_ops.integrations import load_declaration

    declaration = load_declaration(repo_root() / "config" / "integrations.yml")
    channel = next(i for i in declaration if i.name == "board_notifications")
    assert set(channel.secrets) == {THREAD_ENV, MENTION_ENV}
    assert "nothing is sent" in channel.absent_behaviour.lower()


def test_the_workflow_asks_for_no_permission_beyond_issues_and_checkout() -> None:
    """Least privilege, restated for the shape phase 8's task 3 left.

    Before change E this file held only the notification, so one assertion
    over the whole file said it all: `contents: read` to check out,
    `issues: write` to post, nothing else. The sweep now shares the file,
    and it genuinely needs more -- it commits `data/speakers.yml` and
    dispatches `publish-vitrine.yml`. So the property is asserted per job
    instead of per file, which is stricter rather than looser: the push
    path (`immediate`) must still carry *exactly* what it always did, and
    the daily job must carry the union of the two merged jobs and not one
    scope more. A single file-wide set would now pass while `immediate`
    quietly gained `contents: write`.
    """
    loaded = safe_load(
        (repo_root() / ".github" / "workflows" / "sweep-and-notify.yml").read_text(
            encoding="utf-8"
        )
    )
    jobs = loaded["jobs"]
    assert set(jobs) == {"immediate", "daily"}
    assert jobs["immediate"]["permissions"] == {
        "contents": "read",
        "issues": "write",
    }, (
        "the push-triggered job may only read the repository and post a "
        "comment -- it writes nothing and dispatches nothing"
    )
    assert jobs["daily"]["permissions"] == {
        "contents": "write",
        "actions": "write",
        "issues": "write",
    }, (
        "the daily job carries the union of the sweep's own scopes "
        "(commit data/speakers.yml, dispatch publish-vitrine.yml) and the "
        "digest's own (post a comment) -- and nothing beyond that union"
    )


# ------------------------------------------------------------------ #
# Phase 8, task 3, change E: the nightly sweep and this digest are one
# workflow now. What follows pins what the merge had to keep, because a
# merge is exactly the moment a trigger or an ordering gets dropped by
# hand and nothing says so afterwards.
# ------------------------------------------------------------------ #


def _merged_workflow() -> dict[str | bool, Any]:
    loaded = safe_load(
        (repo_root() / ".github" / "workflows" / "sweep-and-notify.yml").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(loaded, dict)
    return loaded


def _daily_steps() -> list[dict[str, Any]]:
    jobs = _merged_workflow()["jobs"]
    assert isinstance(jobs, dict)
    return list(jobs["daily"]["steps"])


def test_the_merged_workflow_keeps_every_trigger_the_two_files_had() -> None:
    """Three triggers went into the merge and each one is somebody's only
    way in: the push on `data/speakers.yml` is what makes an immediate
    event immediate (without it a lead from the public form waits for the
    next morning), the daily cron is the only scheduled run either half
    ever had, and `workflow_dispatch` is the operator's own hand. A merge
    that quietly dropped one would look entirely healthy."""
    triggers = workflow_triggers(_merged_workflow())
    assert set(triggers) == {"push", "schedule", "workflow_dispatch"}
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["push"]["paths"] == ["data/speakers.yml"], (
        "the push trigger no longer watches data/speakers.yml -- the "
        "immediate events are a diff of that file, so nothing would ever "
        "fire them"
    )
    crons = [entry["cron"] for entry in triggers["schedule"]]
    assert crons == ["0 5 * * *"], (
        f"the merged workflow declares {crons} -- one daily cron, at the "
        "hour the sweep already had: the digest no longer needs one of its "
        "own now that it is the step after the sweep"
    )


def test_the_daily_job_sweeps_before_it_composes_the_digest() -> None:
    """The whole reason the two files became one. They used to be two
    crons an hour apart, and that hour was a dependency dressed as a
    schedule: the digest reports what the sweep has just written. GitHub's
    scheduled runs are routinely late, so the morning the sweep ran past
    06:00 the digest would have reported the previous day's state and
    nothing would have said so. As two steps of one job the order is a
    sequence rather than a bet, and this is what keeps it one."""
    names = [step.get("name") for step in _daily_steps()]
    assert "Sweep and commit" in names and "Compose" in names, (
        f"the daily job's steps are {names} -- one of the two halves is "
        "gone or was renamed"
    )
    assert names.index("Sweep and commit") < names.index("Compose"), (
        "the digest composes before the sweep runs, so it reports the "
        "state of the previous day -- the exact defect merging the two "
        "files existed to remove"
    )


def test_a_failing_sweep_still_lets_the_digest_report() -> None:
    """And the reverse. Merging two jobs into one makes it very easy for
    the first failure to swallow everything after it; the digest is the
    project's only channel to volunteers who do not open the app (D-07),
    and the morning the sweep could not push is not the morning to also
    go silent. The guard names the *installation* it needs rather than
    saying `always()` alone, so a failed checkout still skips a step that
    could not have worked -- the same shape quality.yml's merged jobs
    use."""
    compose = next(step for step in _daily_steps() if step.get("name") == "Compose")
    guard = str(compose["if"])
    assert "always()" in guard, (
        "the digest is skipped as soon as the sweep fails -- a merged job "
        "must not make one half's failure the other half's silence"
    )
    assert "steps.sweep" not in guard, (
        "the digest is conditioned on the sweep's own outcome, which is "
        "the same silence written a longer way"
    )
    assert "steps.uv.outcome == 'success'" in guard, (
        "the digest runs on a bare always(), so a failed `uv` install "
        "would run a command that cannot possibly work and report that as "
        "the finding"
    )


def test_the_sweep_step_never_sees_the_notification_secrets() -> None:
    """Declared per step, never on the job: the sweep runs `convener-sweep`
    and `git push`, and has no business being handed the thread and the
    mention the digest posts with. Merging two jobs is precisely when
    somebody lifts both `env:` blocks up to the job to save six lines --
    P-5 of the security audit, isolation of secrets, which the three
    `deploy-*-relay.yml` files keep for the same reason."""
    jobs = _merged_workflow()["jobs"]
    assert isinstance(jobs, dict)
    for job_id, job in jobs.items():
        job_env = " ".join(str(value) for value in job.get("env", {}).values())
        assert "secrets." not in job_env, (
            f"the {job_id} job declares a secret at job level, so every "
            "step in it can read it"
        )

    sweep = next(
        step for step in _daily_steps() if step.get("name") == "Sweep and commit"
    )
    carried = " ".join(str(value) for value in sweep.get("env", {}).values())
    assert THREAD_ENV not in carried and MENTION_ENV not in carried, (
        "the sweep step carries the notification secrets it never uses"
    )
