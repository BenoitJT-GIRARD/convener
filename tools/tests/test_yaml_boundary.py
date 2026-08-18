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
    assert validate_speakers(speakers) == []
