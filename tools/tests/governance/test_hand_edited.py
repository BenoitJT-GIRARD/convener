"""The hand-edited half of the boundary: files the app did not write.

`speakers-from-app.yml` pins what the browser emits. This module pins the
other thing both languages have to survive: a file a volunteer typed into
GitHub's web editor, with keys left out and scalars left unquoted. That is
not a hypothetical -- keeping the data in YAML is what makes the repository
editable without this app at all, so the two readers have to agree about
what a hand edit means.

`app/tests/data/data-validate.test.ts` reads these same two files and asserts
what the browser tells whoever opened it. Here: what `convener-validate` tells
whoever runs it.
"""

from __future__ import annotations

from pathlib import Path

from conftest import EDITIONS

from convener_ops.declaration.yaml_safe import safe_load
from convener_ops.governance.validate import validate_config, validate_speakers

FIXTURES = Path(__file__).parents[1] / "fixtures"
SPEAKERS = FIXTURES / "hand-edited-speakers.yml"
CONFIG = FIXTURES / "hand-edited-config.yml"


def test_an_unquoted_time_typed_by_hand_is_still_text() -> None:
    """The defect, in the form it can still arrive in.

    js-yaml quotes `time` on write, so a file the app produced is safe under
    any loader. This file was not produced by the app: `time: 12:30` is bare,
    and PyYAML's stock resolvers would hand back the integer 750.
    """
    assert "time: 12:30" in SPEAKERS.read_text(encoding="utf-8")
    speaker = safe_load(SPEAKERS.read_text(encoding="utf-8"))[0]
    assert speaker["time"] == "12:30"
    assert speaker["date"] == "2026-06-01"
    assert isinstance(speaker["date"], str)


def test_the_validator_names_the_fields_a_hand_edit_left_out() -> None:
    """Absent, not empty -- and reported as the defect it is.

    The browser refuses the whole file (`data/validate.ts`); this side lists
    every field at once, because an operator fixing a file wants the list,
    not the first line of it.
    """
    speakers = safe_load(SPEAKERS.read_text(encoding="utf-8"))
    errors = validate_speakers(speakers, ["alice", "bob", "carol"], editions=EDITIONS)
    joined = " | ".join(errors)
    assert "career_stage" in joined
    assert "publication" in joined
    assert "assigned_to" in joined
    # Named by id, so the line points at a record rather than at an offset.
    assert all("spk-201" in error for error in errors)


def test_the_validator_still_names_the_setting_the_rule_replaced() -> None:
    """`vote_threshold` is the reason the browser now checks its read too.

    Three tests once round-tripped this key through `DataProvider` and
    passed, because the cast let any key survive; they stood as a green
    specification for storing a threshold G-01 forbids. This side has always
    caught it, and says so in the same words.
    """
    errors = validate_config(safe_load(CONFIG.read_text(encoding="utf-8")))
    assert any("vote_threshold" in error for error in errors)
    assert all(error.startswith("config.yml:") for error in errors)


def test_nothing_else_in_the_hand_edited_config_is_wrong() -> None:
    """Guards the fixture: if the rest of the file drifts out of shape, the
    test above would pass on the wrong error and stop saying anything about
    `vote_threshold`."""
    errors = validate_config(safe_load(CONFIG.read_text(encoding="utf-8")))
    assert len(errors) == 1
