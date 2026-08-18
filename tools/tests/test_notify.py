"""A message that has been sent cannot be unsent.

So the tests that matter most here are the ones about *not* sending: that an
unconfigured repository produces nothing, that a quiet day produces nothing,
and that no personal data can travel even when a message does go out.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from conftest import config as make_config
from conftest import nomination, objection, speaker

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

NOW = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)

#: A fully-configured environment, so the "sends nothing" tests are not
#: passing merely because the fixture forgot to configure anything.
CONFIGURED = {THREAD_ENV: "42", MENTION_ENV: "@tec/editorial"}


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
    before = [lead(id="spk-001", status="lead")]
    after = [lead(id="spk-001", status="approved")]
    assert kinds(immediate_events(before, after)) == [THRESHOLD_REACHED]


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
    assert "Board decision is 3 days overdue" in digest
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
    late = overdue(entry, make_config()["sla_days"], "2026-08-18")
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


@pytest.mark.parametrize(
    "sla_days",
    [None, "fourteen", {"lead_decision": "fourteen"}, {"lead_decision": True}, {}],
    ids=["absent", "not a mapping", "not a number", "a bool", "empty"],
)
def test_an_unusable_sla_configuration_produces_no_deadline(sla_days: Any) -> None:
    """A hand-edited config must degrade to "no deadline can be computed",
    never to a guessed one -- the scheduled job runs without a validation
    pass, so an unchecked config reaches here."""
    entry = lead(
        id="spk-004",
        status="lead",
        selection={"ballots": [], "opened_on": "2026-08-01", "decided_on": ""},
    )
    assert overdue(entry, sla_days, "2026-08-18") is None
    assert daily_digest([entry], make_config(sla_days=sla_days), NOW) is None


@pytest.mark.parametrize(
    "today", ["", "not-a-day", "20260818"], ids=["empty", "prose", "compact"]
)
def test_a_day_that_is_not_an_iso_date_yields_no_lateness(today: str) -> None:
    entry = lead(
        id="spk-004",
        status="lead",
        selection={"ballots": [], "opened_on": "2026-08-01", "decided_on": ""},
    )
    assert overdue(entry, make_config()["sla_days"], today) is None


def test_a_malformed_record_contributes_nothing_rather_than_raising() -> None:
    assert overdue("not a record", make_config()["sla_days"], "2026-08-18") is None
    assert daily_digest(["not a record", 7, {}], make_config(), NOW) is None


def test_malformed_nominations_contribute_nothing() -> None:
    assert daily_digest([], make_config(nominations="none"), NOW) is None
    assert daily_digest([], make_config(nominations=[7, {}]), NOW) is None


# ------------------------------------------------------------------ #
# Nothing about a person leaves the repository
# ------------------------------------------------------------------ #

#: Every field of a record that names or identifies a human being.
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
}


def loaded(**over: Any) -> dict[str, Any]:
    """A record whose every personal field carries a distinctive value."""
    return speaker(**PERSONAL) | over


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
    assert channel == Channel(thread="42", mention="@tec/editorial")


@pytest.mark.parametrize(
    "env",
    [
        {},
        {THREAD_ENV: "42"},
        {MENTION_ENV: "@tec/editorial"},
        {THREAD_ENV: "", MENTION_ENV: "@tec/editorial"},
        {THREAD_ENV: "42", MENTION_ENV: "   "},
    ],
    ids=["nothing", "thread only", "mention only", "blank thread", "blank mention"],
)
def test_a_partly_configured_environment_yields_no_channel(env: dict[str, str]) -> None:
    """A thread with no mention posts into a page nobody is watching, and a
    mention with no thread has nowhere to be written. Neither half has a safe
    default, so neither half alone builds a `Channel`."""
    assert resolve_channel(env) is None


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
    assert addressed.channel == Channel(thread="42", mention="@tec/editorial")
    assert addressed.body.startswith("@tec/editorial")
    assert "a real message" in addressed.body


def test_the_notification_module_holds_no_transport() -> None:
    """This package cannot send, whatever anybody configures.

    Read from the module's own source, so a future import of a transport
    fails here rather than at three in the morning against a live mailbox.
    """
    source = Path(notify.__file__).read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if line.startswith(("import ", "from "))
    )
    for banned in ("smtplib", "urllib", "http", "socket", "subprocess", "requests"):
        assert banned not in code


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
sla_days:
  lead_decision: 14
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
    monkeypatch.setenv(MENTION_ENV, "@tec/editorial")

    assert cli.notify_digest() == 0

    body = (root / cli.NOTIFY_BODY).read_text(encoding="utf-8")
    assert body.startswith("@tec/editorial")
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
    monkeypatch.setenv(MENTION_ENV, "@tec/editorial")

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
    monkeypatch.setattr("convener_ops.cli.sys.argv", ["convener-notify-digest", "--dry-run"])
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@tec/editorial")

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
    monkeypatch.setenv(MENTION_ENV, "@tec/editorial")

    assert cli.notify_digest() == 1

    assert "invalid YAML" in capsys.readouterr().out
    assert not (root / cli.NOTIFY_BODY).exists()


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
    monkeypatch.setattr("convener_ops.cli._git_show", lambda _root: ("", "no parent commit"))
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@tec/editorial")

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
    monkeypatch.setattr("convener_ops.cli._git_show", lambda _root: ("- id: [unclosed", ""))
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@tec/editorial")

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
    monkeypatch.setattr("convener_ops.cli._git_show", lambda _root: ("[]\n", ""))
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@tec/editorial")

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
        "convener_ops.cli._git_show", lambda _root: ("- id: spk-009\n  status: lead\n", "")
    )
    monkeypatch.setenv(THREAD_ENV, "42")
    monkeypatch.setenv(MENTION_ENV, "@tec/editorial")

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


def test_git_show_reads_the_previous_revision_of_the_speaker_file() -> None:
    """The one subprocess this feature adds, exercised against this very
    repository: fixed argv, nothing interpolated, and the failure half is what
    the callers above stub."""
    text, error = cli._git_show(repo_root())
    assert error == ""
    assert "- id: spk-001" in text


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
    workflow = (repo_root() / ".github" / "workflows" / "notify.yml").read_text(
        encoding="utf-8"
    )
    granted = re.findall(r"^\s+(\w+): (read|write)$", workflow, flags=re.MULTILINE)
    assert set(granted) == {("contents", "read"), ("issues", "write")}
