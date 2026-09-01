"""The register is derived from commit subjects, so their shape is a contract.

Three things are being pinned here, in order of how much they matter:

1. an ordinary commit is never flagged -- a grammar that fought every code
   commit would be switched off within a week, and then the register would
   have no grammar at all;
2. a decision message round-trips exactly, so reading the register back is
   never guesswork;
3. the vocabulary itself cannot judge a volunteer.
"""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from convener_ops.governance import commit_format
from convener_ops.governance.commit_format import (
    ACTS,
    QUALIFIERS,
    Decision,
    DecisionRejectedError,
    format_decision,
    judgemental_terms,
    parse_decision,
    validate_messages,
)

CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "governance-cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", CASES["commit_message_cases"], ids=lambda c: c["name"])
def test_the_message_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    """`app/tests/state/decisions.test.ts` writes these same lines from the browser."""
    assert (
        format_decision(case["kind"], case["entity"], case["actor"], case["detail"])
        == case["message"]
    )


@pytest.mark.parametrize("case", CASES["commit_message_cases"], ids=lambda c: c["name"])
def test_the_message_reads_back_to_exactly_what_was_written(
    case: dict[str, Any],
) -> None:
    assert parse_decision(case["message"]) == Decision(
        kind=case["kind"],
        entity=case["entity"],
        actor=case["actor"],
        detail=case["detail"],
    )


@pytest.mark.parametrize(
    "case", CASES["commit_message_rejects"], ids=lambda c: c["name"]
)
def test_a_malformed_decision_is_reported(case: dict[str, Any]) -> None:
    problems = validate_messages([case["message"]])
    assert problems, f"not flagged: {case['message']!r}"


@pytest.mark.parametrize(
    "case", CASES["commit_message_ordinary"], ids=lambda c: c["name"]
)
def test_an_ordinary_commit_is_left_alone(case: dict[str, Any]) -> None:
    """The case this whole module lives or dies on.

    `ops: drop the stale public-data cache` uses a word the register would
    never use about a person, and is none of the grammar's business: it
    records no decision, so nothing here looks at it.
    """
    assert validate_messages([case["message"]]) == []


def test_every_act_has_a_kind_and_every_qualifier_an_act() -> None:
    assert set(QUALIFIERS) <= set(ACTS)


def test_no_act_or_qualifier_can_judge_a_person() -> None:
    """The wording rule, checked against the vocabulary rather than the prose.

    Nothing but this table can supply the verb of a decision message, so a
    table that passes here cannot produce a message that fails.
    """
    for kind, act in ACTS.items():
        assert judgemental_terms(act) == [], f"{kind} judges: {act!r}"
    for kind, allowed in QUALIFIERS.items():
        for value in allowed:
            assert judgemental_terms(value) == [], f"{kind} qualifier judges: {value!r}"


def test_the_six_words_phase_2_already_bans_are_a_consequence_not_a_list() -> None:
    """`test_inactivity.py` bans six words in the sweep's wording. They are not
    enumerated here: they fall out of the stems, and so do the words nobody
    thought to enumerate."""
    six = ("removed", "expelled", "dropped", "failed", "negligent", "left")
    for word in six:
        assert judgemental_terms(f"data: park {word} by ada") == [word]
    # The same idea in a form the six-word list would have missed.
    for word in ("removal", "expelling", "dismissal", "ousted", "failure", "leaving"):
        assert judgemental_terms(word) == [word]


def test_an_ordinary_word_is_not_mistaken_for_a_judgement() -> None:
    for word in ("record", "ballot", "nomination", "recording", "withdraw", "decline"):
        assert judgemental_terms(word) == []


def test_a_kind_outside_the_vocabulary_is_not_writable() -> None:
    with pytest.raises(DecisionRejectedError):
        format_decision("expel-member", "ada", "grace")


def test_a_qualifier_outside_the_act_is_not_writable() -> None:
    with pytest.raises(DecisionRejectedError):
        format_decision("ballot-cast", "spk-001", "ada", "withhold")
    with pytest.raises(DecisionRejectedError):
        format_decision("lead-park", "spk-001", "ada", "yes")


def test_an_identifier_that_is_not_one_is_not_writable() -> None:
    with pytest.raises(DecisionRejectedError):
        format_decision("lead-park", "spk 001", "ada")
    with pytest.raises(DecisionRejectedError):
        format_decision("lead-park", "spk-001", "")


def test_the_longest_act_wins_so_two_objections_never_blur() -> None:
    """`record an objection to the nomination of` and `record an objection to
    publishing` share an opening. Reading one as the other would file a board
    seat under a recording."""
    nomination = parse_decision(
        "data: record an objection to the nomination of curie by ada"
    )
    assert nomination is not None and nomination.kind == "nomination-object"
    publishing = parse_decision(
        "data: record an objection to publishing spk-009 by ada"
    )
    assert publishing is not None and publishing.kind == "publication-object"


def test_a_message_that_is_not_a_decision_parses_to_nothing() -> None:
    assert parse_decision("app: gate archiving on the publication approval") is None
    assert parse_decision("data: new lead from public form") is None
    assert parse_decision("") is None


def test_the_problems_name_the_message_and_say_what_was_expected() -> None:
    (problem,) = validate_messages(["data: record a ballot on spk-007 by ada"])
    assert "record a ballot on" in problem
    assert "<record> by <login>" in problem
    assert "abstain|recused|yes" in problem


def test_a_mention_of_an_assistant_is_a_problem_anywhere() -> None:
    for message in (
        "app: tidy the list\n\nCo-authored-by: Someone <s@example.org>",
        "app: tidy the list (generated with a tool)",
        "data: park spk-003 by claude",
    ):
        assert validate_messages([message]), message


def test_every_problem_is_reported_not_just_the_first() -> None:
    problems = validate_messages(
        [
            "data: record a ballot on spk-007",
            "app: a perfectly ordinary commit",
            "data: reopen the vote on spk-007 by",
        ]
    )
    assert len(problems) == 2


def test_a_decision_reports_one_problem_at_a_time() -> None:
    """A message that is both malformed and judgemental is reported once, on
    the judgement: fixing the wording is the first thing to do, and a wall of
    problems about one line helps nobody."""
    problems = validate_messages(["data: delete the record of expelled by"])
    assert len(problems) == 1
    assert "judges a person" in problems[0]


def test_the_prompts_stay_ascii_so_a_terminal_can_print_them() -> None:
    for kind, act in ACTS.items():
        act.encode("ascii")
        kind.encode("ascii")
    for problem in validate_messages(["data: record a ballot on spk-007"]):
        problem.encode("ascii")


def test_the_cli_reads_whole_messages_from_stdin_and_passes_a_clean_range(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sys,
        "stdin",
        # NUL-separated, exactly as `git log --format=%B%x00` writes it, so a
        # message keeps its body instead of arriving as loose lines.
        io.StringIO(
            "app: gate archiving on the publication approval\n\x00"
            "data: record a ballot on spk-007 by ada (yes)\n\x00"
        ),
    )
    assert commit_format.check_commits() == 0
    assert "2 commit message(s) OK." in capsys.readouterr().out


def test_the_cli_fails_the_build_on_a_malformed_decision(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("data: record a ballot on spk-007\n"))
    assert commit_format.check_commits() == 1
    out = capsys.readouterr().out
    assert out.startswith("error: ")
    assert "1 commit message(s) to fix." in out


@pytest.mark.parametrize("case", CASES["identifier_cases"], ids=lambda c: c["name"])
def test_what_a_decision_may_point_at_is_the_same_rule_on_both_sides(
    case: dict[str, Any],
) -> None:
    """`app/tests/state/decisions.test.ts` reads this same table.

    The browser's copy is a branded type, so free text cannot reach
    `formatDecision` at all; this asserts the two agree on which strings are
    identifiers, which is what keeps the browser from writing a line this
    module cannot read back.
    """
    from convener_ops.governance.commit_format import _TOKEN

    assert bool(re.fullmatch(_TOKEN, case["value"])) is case["identifier"]


@pytest.mark.parametrize(
    "case",
    [c for c in CASES["identifier_cases"] if not c["identifier"]],
    ids=lambda c: c["name"],
)
def test_a_decision_cannot_be_written_about_a_person_by_name(
    case: dict[str, Any],
) -> None:
    with pytest.raises(DecisionRejectedError):
        format_decision("nomination-open", case["value"], "ada")
