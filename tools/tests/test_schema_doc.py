"""The schema appendix, and the guard that keeps it derived.

The handbook's appendix drifted four times in two phases -- `proposed_by`
defined as the wrong person, fields listed that the model had dropped, a
thirty-day view count under a window that had become configuration -- and was
corrected by hand every time. `tools/scripts/generate_schema_doc.py` derives it from
`app/src/data/types.ts` instead, and this module holds the two halves that make
that stick.

**The loop is proved, not assumed.** The register of decisions was given the
same treatment, and its `--check` went red the moment it was wired
in, because the file it guarded had never been produced: the job that wrote it
only ran on push to `main`. So the first test here reads the committed page off
disk and compares it with what today's types derive. It fails on a model
changed without regenerating, on a page edited by hand, and on a page that was
never generated at all.

**The check does not repair.** A mode that rewrote the file it was checking
would report success on a repository that still held the wrong page, which is
worse than no check: it would be a green tick over the exact defect it exists
to catch. `test_check_leaves_a_stale_page_exactly_as_it_found_it` pins that.

The parser is exercised on models written here rather than on the repository's
own, so a test about "a field nobody documented" does not require the
repository to hold one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import config, speaker
from generate_schema_doc import (
    COMMAND,
    DOC_PATH,
    TYPES_PATH,
    main,
    parse_types,
    render_schema_doc,
    schema_doc,
)

from convener_ops.declaration.paths import repo_root
from convener_ops.validate import STATUSES

ROOT = repo_root()

#: A whole small model, in the four forms `types.ts` uses. Written out rather
#: than trimmed from the repository's own, so that these tests keep meaning
#: what they say when the real model moves.
SAMPLE = """
/** Where a record stands. */
export type Colour =
  | 'red' // the first one
  | 'blue';

export const SIZES = ['small', 'large'] as const;
export type Size = (typeof SIZES)[number];

/** One nested record. */
export interface Wheel {
  /** How many spokes. */
  spokes: number;
}

/** One record reached through a map. */
export interface Spare {
  /** Who owes it. */
  owner: string;
}

export interface Inner {
  /** The colour it is painted.
   *
   *  The second paragraph argues about the colour and belongs in the code.
   */
  colour: Colour;
}

export interface Outer {
  /** Its name. */
  name: string;
  size: Size;
  inner: Inner;
  wheels: Wheel[];
  spares: Record<string, Spare>;
  counts: number | null;
  tags: string[];
  limits: {
    /** The highest it goes. */
    top: number;
  };
}
"""


def sample_page() -> str:
    """The sample model, rendered through the real renderer."""
    model = parse_types(SAMPLE)
    model.interfaces["Speaker"] = model.interfaces["Outer"]
    model.interfaces["Config"] = model.interfaces["Inner"]
    model.enums["SpeakerStatus"] = model.enums["Colour"]
    return render_schema_doc(model)


# --------------------------------------------------------------------------
# The repository's own page
# --------------------------------------------------------------------------


def test_the_committed_page_is_what_the_types_derive() -> None:
    """The whole point, on the real tree.

    A model changed without regenerating fails here, and so does a page
    corrected by hand -- which is how every previous drift was introduced.
    """
    committed = (ROOT / DOC_PATH).read_text(encoding="utf-8")
    assert committed == schema_doc(ROOT), (
        f"{DOC_PATH.as_posix()} is not what {TYPES_PATH.as_posix()} derives;"
        f" run `{COMMAND}` from `tools/`."
    )


def test_the_page_says_it_is_generated_and_names_the_command() -> None:
    """A derived file that does not say so is one somebody will edit."""
    head = (ROOT / DOC_PATH).read_text(encoding="utf-8")[:900]
    assert "generated" in head
    assert COMMAND in head
    assert TYPES_PATH.as_posix() in head


#: `SPEAKER_FIELD_SET` in `app/src/data/types.ts`, read as text.
#:
#: Deliberately not read through `generate_schema_doc.parse_types`: this is
#: the second opinion about the model, and a second opinion that shares the
#: first one's parser is not one. `SPEAKER_FIELD_SET` is also a different
#: declaration from `interface Speaker` -- it is a `Record<keyof Speaker,
#: true>`, which the TypeScript compiler holds exhaustive in both directions
#: -- so a field the parser cannot read is still listed here.
_FIELD_SET = re.compile(
    r"const SPEAKER_FIELD_SET: Record<keyof Speaker, true> = \{(.*?)\n\};", re.S
)


def _declared_speaker_fields() -> list[str]:
    source = (ROOT / TYPES_PATH).read_text(encoding="utf-8")
    listed = _FIELD_SET.search(source)
    assert listed is not None, (
        f"{TYPES_PATH.as_posix()} no longer declares SPEAKER_FIELD_SET in the "
        "form this test reads, so nothing holds the Python double to the model."
    )
    return re.findall(r"(\w+): true", listed.group(1))


def test_the_python_double_is_the_model_key_for_key() -> None:
    """What makes the check below a check.

    `test_every_stored_key_of_a_record_has_a_row` walks
    `tools/tests/conftest.py::speaker()`, and is worth exactly as much as the
    claim that that double is the record the model declares. Nothing held it
    to the model: the app suite pins `app/tests/data-doubles.ts`, a different
    double, so a field could be added to `Speaker` and left out of the Python
    double, and the row test would pass without ever asking for its row.

    That matters because the parser has a ceiling. `parse_types` reads four
    declaration forms; a field declared in a fifth -- a type wrapped over
    several lines, which is what prettier does to a long one -- is simply not
    seen, and `--check` cannot catch it: both sides of that comparison come
    from the same parser, so the short page matches itself. This pin is the
    independent path: the field is in `SPEAKER_FIELD_SET` whatever shape its
    declaration takes, so it is in this list, so it is in the double, so the
    page is asked for its row.
    """
    # Compared as sets: which keys the double holds is the claim, and the
    # order it holds them in reaches nothing -- the page's order is the
    # interface's, and the file's is the reader's (`data/validate.ts` rebuilds
    # every record in the order the model declares).
    assert set(_declared_speaker_fields()) == set(speaker())


def test_every_stored_key_of_a_record_has_a_row() -> None:
    """No field reaches the file without reaching the handbook.

    The double in `conftest` is the record as the model declares it --
    `test_the_python_double_is_the_model_key_for_key` above holds it key for
    key against `SPEAKER_FIELD_SET`, in both directions -- so a field added to
    the model and left out of the page is caught here as well as by the
    comparison above, with a message naming the field.
    """
    page = (ROOT / DOC_PATH).read_text(encoding="utf-8")
    for key in list(speaker()) + list(config()):
        assert f"| `{key}`" in page or f"| `{key}." in page, key


def test_every_status_the_readers_accept_is_listed_on_the_page() -> None:
    """The status list is the model's, not a second list kept beside it.

    `convener_ops.validate.STATUSES` is the Python reader's own vocabulary. It is
    read here as a second opinion about the same journey -- the page is
    derived from the TypeScript, so a status the two languages disagree about
    shows up as a status the handbook does not list.
    """
    page = (ROOT / DOC_PATH).read_text(encoding="utf-8")
    for status in STATUSES:
        assert f"- `{status}` " in page, status


# --------------------------------------------------------------------------
# Reading the model
# --------------------------------------------------------------------------


def test_a_field_is_a_row_carrying_its_first_paragraph() -> None:
    page = sample_page()
    assert "| `name` | string | Its name. |" in page
    assert "The colour it is painted." in page
    assert "argues about the colour" not in page


def test_an_enumeration_carries_its_values_however_it_is_spelled() -> None:
    """A `const` tuple and a union of literals are the same fact."""
    page = sample_page()
    assert "One of `small` or `large`." in page
    assert "One of `red` or `blue`." in page


def test_a_union_member_keeps_the_note_written_beside_it() -> None:
    page = sample_page()
    assert "- `red` " in page
    assert "the first one" in page
    assert "- `blue`" in page


def test_an_object_field_is_flattened_and_a_list_gets_its_own_table() -> None:
    """One level of dots, because a list of records is not one record."""
    page = sample_page()
    assert "| `inner.colour` |" in page
    assert "| `limits.top` | number | The highest it goes. |" in page
    assert "### `wheels` entries" in page
    assert "| `spokes` | number | How many spokes. |" in page


def test_a_map_of_records_gets_a_table_too() -> None:
    """A `checklist` block is documented like everything else it holds."""
    page = sample_page()
    assert "### `spares` entries" in page
    assert "| `owner` | string | Who owes it. |" in page


def test_a_cell_cannot_break_the_table_it_sits_in() -> None:
    """`number | null` is a type a reader needs and a pipe a table cannot."""
    page = sample_page()
    assert r"| `counts` | number \| null |" in page
    assert "| `tags` | list&lt;string&gt; |" in page


def test_the_rendering_is_a_function_of_the_model_alone() -> None:
    """Byte-identical over two runs, which is what makes `--check` a fact."""
    assert schema_doc(ROOT) == schema_doc(ROOT)


# --------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository holding only the model, with the page not yet written."""
    (tmp_path / TYPES_PATH).parent.mkdir(parents=True)
    (tmp_path / TYPES_PATH).write_text(
        (ROOT / TYPES_PATH).read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    return tmp_path


def test_check_fails_when_the_page_has_never_been_written(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The failure the decision register actually met.

    Its `--check` went red on the day it was wired in because the file it
    guarded had never been produced. A guard around something that does not
    exist has to fail loudly, and has to say what to run.
    """
    assert main(["--check"]) == 1
    assert not (fake_repo / DOC_PATH).exists()
    err = capsys.readouterr().err
    assert DOC_PATH.as_posix() in err
    assert COMMAND in err


def test_check_leaves_a_stale_page_exactly_as_it_found_it(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A check that repairs is not a check.

    Silently rewriting the file would turn the one signal that the repository
    holds a wrong page into a green tick.
    """
    page = fake_repo / DOC_PATH
    page.parent.mkdir(parents=True)
    page.write_text("stale\n", encoding="utf-8")

    assert main(["--check"]) == 1
    assert page.read_text(encoding="utf-8") == "stale\n"
    assert COMMAND in capsys.readouterr().err


def test_writing_then_checking_passes(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The loop end to end: generate, and the guard is satisfied."""
    assert main([]) == 0
    assert main(["--check"]) == 0
    assert "matches the types" in capsys.readouterr().out


def test_a_second_write_changes_nothing_and_says_so(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([]) == 0
    capsys.readouterr()
    assert main([]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_a_field_added_to_the_model_makes_the_check_fail(
    fake_repo: Path,
) -> None:
    """The mutation, as a test rather than as a thing somebody remembers.

    The page is generated from the model, then a field is added to the model
    and nothing is regenerated -- which is exactly what a contributor does
    when they change `types.ts` and commit. The guard has to notice.
    """
    assert main([]) == 0
    types = fake_repo / TYPES_PATH
    types.write_text(
        types.read_text(encoding="utf-8").replace(
            "  /** Free-form notes about the record. */\n  notes: string;",
            "  /** Free-form notes about the record. */\n  notes: string;\n"
            "  /** A field nobody regenerated the page for. */\n"
            "  invented_field: string;",
        ),
        encoding="utf-8",
    )
    assert main(["--check"]) == 1


def test_the_terminal_output_is_ascii(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The page is written in the handbook's English; the console is not.

    Nothing this repository's Python prints may be non-ASCII: the volunteers'
    console renders it as mojibake. The page itself is a file and is exempt,
    which is why there is no mode that prints it.
    """
    main([])
    main(["--check"])
    captured = capsys.readouterr()
    (captured.out + captured.err).encode("ascii")
