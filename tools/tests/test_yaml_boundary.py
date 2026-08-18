"""The JS/Python YAML boundary (phase-1 review finding I1).

`app/tests/yaml.test.ts` writes the very same fixture from
`serializeSpeakers` and asserts it stays byte-for-byte identical to the file
checked in here. This test is the other half: it proves that what the
browser actually emits parses back into exactly what the Python side
expects, with no validation errors -- the round-trip this language boundary
never had a test for.

`fixtures/speakers-from-app.yml` was deliberately generated with a
non-empty `time` (`12:30`) and `date` (`2026-06-01`): those are the two
scalars YAML 1.1's implicit resolvers (still active in PyYAML's default
SafeLoader) misread when unquoted -- `12:30` as the sexagesimal integer
750, and a bare date as a `datetime.date`. js-yaml already quotes both on
write, so this fixture is safe either way; `convener_ops.yaml_safe.safe_load` is
what keeps a *hand-edited*, unquoted copy safe too.
"""

from __future__ import annotations

from pathlib import Path

from convener_ops.validate import validate_speakers
from convener_ops.yaml_safe import safe_load

FIXTURE = Path(__file__).parent / "fixtures" / "speakers-from-app.yml"

#: The logins that cast the fixture's ballots. The validator rejects a
#: ballot from a non-member, so the board this fixture is validated against
#: has to be stated -- there is no config.yml on this side of the boundary.
BOARD = frozenset({"alice", "bob", "carol"})


def test_fixture_has_a_non_empty_time_and_date() -> None:
    # Guards against the fixture being regenerated down to an empty/trivial
    # case that would no longer exercise the bug this test exists for.
    text = FIXTURE.read_text(encoding="utf-8")
    assert "time: '12:30'" in text
    assert "date: '2026-06-01'" in text


def test_python_reads_time_and_date_as_strings_not_int_or_date() -> None:
    speakers = safe_load(FIXTURE.read_text(encoding="utf-8"))
    assert speakers[0]["time"] == "12:30"
    assert isinstance(speakers[0]["time"], str)
    assert speakers[0]["date"] == "2026-06-01"
    assert isinstance(speakers[0]["date"], str)


def test_validator_accepts_what_the_browser_actually_writes() -> None:
    speakers = safe_load(FIXTURE.read_text(encoding="utf-8"))
    assert validate_speakers(speakers, BOARD) == []


def test_python_reads_a_yes_ballot_as_the_string_and_not_as_true() -> None:
    # The third scalar YAML 1.1 misreads, and the one schema v3 added:
    # bare `yes` is the boolean True. js-yaml quotes it on write, and
    # `value: 'yes'` in the fixture is what that quoting looks like -- but
    # a hand-edited copy may well not be quoted, and a ballot read as True
    # is a ballot with no recognisable value at all.
    speakers = safe_load(FIXTURE.read_text(encoding="utf-8"))
    values = [b["value"] for b in speakers[0]["selection"]["ballots"]]
    assert values == ["yes", "yes", "recused"]


def test_the_fixture_carries_the_v3_governance_fields() -> None:
    # Guards against the fixture drifting back to a shape that no longer
    # exercises what the two languages have to agree on: without ballots,
    # career_stage and publication in it, this boundary test would pass on
    # a file neither side would accept in practice.
    speaker = safe_load(FIXTURE.read_text(encoding="utf-8"))[0]
    assert speaker["career_stage"] == "postdoc"
    assert speaker["assigned_to"] == "bob"
    assert speaker["publication"]["consent"] == "pending"
    assert speaker["selection"]["opened_on"] == "2025-12-20"
