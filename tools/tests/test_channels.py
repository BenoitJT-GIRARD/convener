"""The promotion channels, on the side that writes the file.

The list is configuration and not a constant: whether the seven channels
are still the right seven cannot be confirmed without asking the
collaborators, which this project never does. Nothing here counts them and
nothing here names one -- a channel added, renamed or dropped in
`instance/data/config.yml` passes this validator unchanged, and the test that would
have frozen the list is deliberately absent.

What is checked is what a hand-edited file can get wrong and what the app
could then not read: a key that cannot be a checklist key, a channel with no
words on it, two channels sharing one key, and a list that is not a list.
The browser makes the same refusals in `app/src/data/validate.ts`; the rule
lives on both sides because both sides read `config.yml`.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import config

from convener_ops.validate import validate_config


def test_the_channels_are_required() -> None:
    cfg = config()
    del cfg["channels"]
    errors = validate_config(cfg)
    assert any("missing keys ['channels']" in e for e in errors)


def test_an_empty_channel_list_is_accepted() -> None:
    """Nothing promoted is a decision; a broken list is not.

    The two must not look alike, which is why the absent key above is an
    error and this is not: an explicitly empty list says the app promotes
    nowhere, and does nothing -- the safe direction of the standing pattern.
    """
    assert validate_config(config(channels=[])) == []


def test_a_list_of_any_length_is_accepted() -> None:
    """One channel, or a dozen, or a set with nothing in common with today's.

    This is the assertion that keeps the list free. Anything counting the
    entries, or expecting a particular key among them, would put back in the
    validator the constant the configuration replaced.
    """
    for channels in (
        [{"key": "only", "label": "Only one"}],
        [{"key": f"c{n}", "label": f"Channel {n}"} for n in range(12)],
        [{"key": "pigeon-post", "label": "Pigeon post"}],
    ):
        assert validate_config(config(channels=channels)) == []


def test_channels_must_be_a_list() -> None:
    errors = validate_config(config(channels={"forum": "Community forum"}))
    assert any("channels must be a list" in e for e in errors)


def test_a_channel_entry_must_be_a_mapping() -> None:
    errors = validate_config(config(channels=["forum"]))
    assert any("channels[0]: not a mapping" in e for e in errors)


@pytest.mark.parametrize(
    "key",
    [
        "Forum Announcement",  # spaces and capitals
        "",  # nothing to store an owner against
        "-leading-hyphen",
        "forum!",
        7,
        None,
    ],
)
def test_a_channel_key_that_could_not_be_a_checklist_key_is_rejected(key: Any) -> None:
    """The key reaches `instance/data/speakers.yml` as a checklist key.

    It is read back by both languages and skimmed in hand-reviewed diffs, so
    it is held to the same narrow shape here as in the browser. The label,
    which nothing stores, is free.
    """
    errors = validate_config(config(channels=[{"key": key, "label": "Somewhere"}]))
    assert any("invalid channel key" in e for e in errors)


@pytest.mark.parametrize("label", ["", "   ", None, 7])
def test_a_channel_with_no_label_is_rejected(label: Any) -> None:
    errors = validate_config(config(channels=[{"key": "forum", "label": label}]))
    assert any("has no label" in e for e in errors)


def test_two_channels_sharing_a_key_are_rejected_and_the_first_is_named() -> None:
    """Both would write to one checklist key: ticking one would tick the other."""
    errors = validate_config(
        config(
            channels=[
                {"key": "forum", "label": "Forum"},
                {"key": "risc", "label": "RISC newsletter"},
                {"key": "forum", "label": "Forum again"},
            ]
        )
    )
    assert any("channels[2]: 'forum' already used at channels[0]" in e for e in errors)


def test_a_channel_carrying_an_unknown_setting_is_rejected() -> None:
    """An owner belongs on the record, not on the channel.

    A line of the journey is owed by somebody *for one event*
    (`Speaker.checklist`); a name written here would read as an owner for
    every event there will ever be, and nothing would ever act on it.
    """
    errors = validate_config(
        config(channels=[{"key": "forum", "label": "Forum", "owner": "ada"}])
    )
    assert any("unknown keys ['owner']" in e for e in errors)
