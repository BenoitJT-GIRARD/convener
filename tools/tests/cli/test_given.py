"""`cli.given.value`: which of the two ways of handing a command a value
wins, and what "not given" means.

The rule itself is `cli/given.py`'s own docstring -- the option first, the
environment second -- and this is the measurement of it. Four cases, and
the fourth is the one an implementation reaching for `or` gets wrong: an
option deliberately passed empty is an empty value the command refuses in
its own words, not an invitation to read the environment instead.
"""

from __future__ import annotations

import pytest

from convener_ops.cli import given


def test_the_option_is_what_the_operator_meant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both given: the one they typed at the command wins. A workflow's
    `env:` is a standing arrangement, and a command line is a decision
    taken now."""
    monkeypatch.setenv("CONVENER_TEST_VALUE", "from-the-environment")

    assert given.value("from-the-option", "CONVENER_TEST_VALUE") == "from-the-option"


def test_the_environment_answers_when_no_option_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback every workflow depends on: `retention.yml` passes
    `DESTROYED_IDS` in `env:` and names no option, and goes on working."""
    monkeypatch.setenv("CONVENER_TEST_VALUE", "from-the-environment")

    assert given.value(None, "CONVENER_TEST_VALUE") == "from-the-environment"


def test_neither_is_the_empty_string_rather_than_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each command refuses an empty value in words of its own -- "no
    valid event id supplied", "no e-mail address supplied" -- so this
    hands the emptiness on rather than raising over it."""
    monkeypatch.delenv("CONVENER_TEST_VALUE", raising=False)

    assert given.value(None, "CONVENER_TEST_VALUE") == ""


def test_an_option_given_empty_is_not_a_missing_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--event ""` names an empty event, which is refused. Falling back
    to the environment here would run the command against an event the
    operator did not name, which is the one outcome worth refusing
    outright."""
    monkeypatch.setenv("CONVENER_TEST_VALUE", "from-the-environment")

    assert given.value("", "CONVENER_TEST_VALUE") == ""


def test_both_sides_are_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pasted value carries whitespace either way it arrives."""
    monkeypatch.setenv("CONVENER_TEST_VALUE", "  spaced  ")

    assert given.value(None, "CONVENER_TEST_VALUE") == "spaced"
    assert given.value("  typed  ", "CONVENER_TEST_VALUE") == "typed"
