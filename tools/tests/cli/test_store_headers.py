"""A write of a data file keeps the header that file already had.

The constants in `cli/store.py` are what a *fresh* file gets, and they are
pinned byte for byte against `app/src/data/yaml.ts` by the YAML-boundary
fixture. They were also being handed back to files that already had a header
of their own, and the loss was not hypothetical: this repository's own
`instance/data/speakers.yml` opened with sixty-seven lines saying that nobody
in it is real, why every address is under `.test` and why every board login is
prefixed. The nightly sweep replaced all of it with one line, in a commit
whose subject said it had swept elapsed events.

That file is reviewed in ordinary pull requests and, on a real instance, holds
personal data. Its header is what tells a reader which of the two they are
looking at.
"""

from __future__ import annotations

import pytest

from convener_ops.cli import store

FALLBACK = "# a fresh file gets this\n"

OWN_HEADER = """# The example instance's own speakers.
#
# Nobody here is real.
"""


def test_a_file_with_a_header_keeps_it() -> None:
    written = store.under_its_own_header(
        OWN_HEADER + "- id: spk-001\n", "- id: spk-001\n- id: spk-002\n", FALLBACK
    )

    assert written.startswith(OWN_HEADER)
    assert FALLBACK not in written
    assert "- id: spk-002" in written


def test_a_file_with_no_header_gets_the_fallback() -> None:
    """The only case the constant was ever for."""
    written = store.under_its_own_header("- id: spk-001\n", "- id: spk-001\n", FALLBACK)

    assert written.startswith(FALLBACK)


def test_an_empty_file_gets_the_fallback() -> None:
    assert store.under_its_own_header("", "- id: spk-001\n", FALLBACK).startswith(
        FALLBACK
    )


def test_blank_lines_below_the_header_are_part_of_it() -> None:
    """A header ending in a blank line is how every file in this repository is
    written, and re-emitting it without the blank would change the bytes of a
    file nothing had edited."""
    original = "# one\n\n# two\n\n- id: spk-001\n"
    written = store.under_its_own_header(original, "- id: spk-001\n", FALLBACK)

    assert written == "# one\n\n# two\n\n- id: spk-001\n"


def test_nothing_below_the_first_record_is_mistaken_for_a_header() -> None:
    """Non-vacuity in the direction that would be silent: a reader that took
    comments from anywhere would carry a note about one record onto a file
    that no longer has it."""
    original = "# the header\n- id: spk-001\n  # a note inside a record\n"
    written = store.under_its_own_header(original, "- id: spk-002\n", FALLBACK)

    assert written == "# the header\n- id: spk-002\n"


def test_the_speakers_writer_keeps_the_header_the_sweep_used_to_delete() -> None:
    """The defect itself, on the shape it happened to. `dump_speakers` still
    exists and still substitutes the constant -- it is what writes a file that
    does not exist yet, and it is what the boundary fixture pins."""
    original = OWN_HEADER + "- id: spk-001\n  name: A Speaker\n"

    written = store.speakers_under_own_header(original, [{"id": "spk-001"}])

    assert written.startswith(OWN_HEADER)
    assert store.SPEAKERS_HEADER not in written


@pytest.mark.shipped_data
def test_the_shipped_speakers_file_still_carries_its_own_explanation() -> None:
    """An anchor, because this one was lost once and nothing noticed for a
    day. It is prose rather than a value, so nothing else in this suite would
    miss it."""
    from convener_ops.declaration.paths import DATA_DIR, repo_root

    text = (repo_root() / DATA_DIR / "speakers.yml").read_text(encoding="utf-8")
    header = [line for line in text.split("\n")[:80] if line.lstrip().startswith("#")]

    assert len(header) > 20, (
        "instance/data/speakers.yml has lost its header again. It explains "
        "that nobody in the file is real, which is the one thing a reader "
        "needs to know before reading it -- see this module's own docstring"
    )
