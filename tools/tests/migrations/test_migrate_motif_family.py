"""The motif family migration (tools/migrations/migrate_motif_family.py).

`motif` carried `ribbon_stroke` and `ribbon_width_ratio` and named no
drawing at all, because there was one drawing and `ribbon.py` was it.
Neither field is a property of the ribbon -- the first is the colour the
motif is stroked in, the second that stroke's weight -- so a charter whose
motif is a lattice would have been writing the ribbon's name for both. The
migration renames them and writes `family` down.

Like `migrate_charter_colour_names.py`, this one rewrites **text** rather
than a loaded mapping -- a charter is JSON carrying paragraphs of
commentary and blank lines between the groups of colours, neither of which
survives a load-and-dump round trip -- so the tests below are shaped the
same way: what the rewrite does to a line, what it refuses, and the
post-condition that proves it changed the names and nothing else.

Two claims are held here that no other module holds:

- **no value changes, and the drawing does not move.** Every field keeps
  its value under its new name, and the family written down is the one
  drawing every charter written before this migration meant;
- the table the migration renames from is the table
  `convener_ops.publication.brand` refuses an unmigrated charter from, so a
  person sent to the migration by the refusal cannot be sent to a different
  rename than the one that was made.

The charter below is nobody's: values picked so that the rewrite has
something to move, and no organisation's design.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from migrate_motif_family import (
    CHARTERS,
    DRAWN,
    FAMILY,
    FIELDS,
    RENAMES,
    MigrationRefusedError,
    main,
    migrate_charter_text,
    rename,
)

from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, motifs

ROOT = repo_root()

#: A charter as a file actually holds one: commentary first, blank lines
#: between the sections, the paragraph written beside a field. Written as
#: text rather than dumped, because text is what this migration reads and
#: the layout is half of what it has to preserve.
OLD_CHARTER = """\
{
  "_comment": "Nobody's, for a test. It says ribbon_stroke in its own prose.",

  "colour": {
    "dominant": "#123456",
    "field": "#f0c419",
    "band": "#faf7f0"
  },

  "motif": {
    "ribbon_stroke": "#123456",
    "ribbon_width_ratio": 0.02,
    "logo_dots": "#f0c419",
    "_ribbon": "ONE continuous meandering stroke, not a set of circles.",
    "_ribbon_width_ratio": "Measured against the reference at 1200x1200.",
    "_logo_dots": "The four filled squares of the wordmark."
  },

  "layout": {}
}
"""

#: The same charter past the migration. Written out rather than derived, so
#: that a rewrite going wrong in both directions at once could not agree
#: with itself.
NEW_CHARTER = (
    OLD_CHARTER.replace('"motif": {\n', '"motif": {\n    "family": "ribbon",\n')
    .replace('"ribbon_stroke":', '"stroke":')
    .replace('"ribbon_width_ratio":', '"width_ratio":')
    .replace('"_ribbon":', '"_family":')
    .replace('"_ribbon_width_ratio":', '"_width_ratio":')
)


def _motif_keys(text: str) -> list[str]:
    return list(json.loads(text)["motif"])


# --- what a name becomes --------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("ribbon_stroke", "stroke"),
        ("ribbon_width_ratio", "width_ratio"),
        ("_ribbon_stroke", "_stroke"),
        ("_ribbon_width_ratio", "_width_ratio"),
        ("_ribbon", "_family"),
        ("logo_dots", "logo_dots"),
        ("_logo_dots", "_logo_dots"),
        ("_motif", "_motif"),
        ("family", "family"),
        ("dominant", "dominant"),
    ],
)
def test_a_key_takes_the_name_of_what_it_actually_holds(
    before: str, after: str
) -> None:
    assert rename(before) == after


def test_the_table_is_the_one_the_reader_refuses_from() -> None:
    """A person meeting an unmigrated charter is sent here by
    `brand.SupersededCharterError`. If the two tables could disagree, that
    message would send them to a rename that was never made."""
    assert FIELDS is brand.SUPERSEDED_MOTIF_FIELDS


def test_the_family_written_down_is_one_the_product_can_draw() -> None:
    """A migration that wrote a name the registry does not hold would
    leave every charter refusing on the run after it."""
    assert DRAWN in motifs.FAMILIES
    assert FAMILY == brand.MOTIF_FAMILY


def test_a_commentary_key_follows_the_field_it_is_written_beside() -> None:
    """The decision this migration takes about the underscore keys: a
    paragraph named after a field that no longer exists is the same defect
    one line down, so each one moves with its own field. `_logo_dots`
    stays because `logo_dots` does."""
    for old, new in FIELDS.items():
        assert RENAMES[f"_{old}"] == f"_{new}"
    assert "_logo_dots" not in RENAMES


# --- what the rewrite does ------------------------------------------------


def test_every_superseded_field_is_renamed_and_keeps_its_value() -> None:
    before = json.loads(OLD_CHARTER)["motif"]
    after = json.loads(migrate_charter_text(OLD_CHARTER, where="a charter"))["motif"]
    for old, new in FIELDS.items():
        assert old not in after
        assert after[new] == before[old]


def test_the_family_is_written_first_and_holds_the_one_drawing_there_was() -> None:
    keys = _motif_keys(migrate_charter_text(OLD_CHARTER, where="a charter"))
    assert keys[0] == FAMILY
    assert (
        json.loads(migrate_charter_text(OLD_CHARTER, where="a charter"))["motif"][
            FAMILY
        ]
        == DRAWN
    )


def test_the_rename_happens_in_place_rather_than_at_the_end() -> None:
    """The diff has to read as renamed lines. A key re-inserted at the end
    of the section would be the same data and an unreviewable diff."""
    assert _motif_keys(migrate_charter_text(OLD_CHARTER, where="a charter")) == [
        "family",
        "stroke",
        "width_ratio",
        "logo_dots",
        "_family",
        "_width_ratio",
        "_logo_dots",
    ]


def test_the_whole_file_is_what_the_rewrite_makes_of_it() -> None:
    assert migrate_charter_text(OLD_CHARTER, where="a charter") == NEW_CHARTER


def test_the_commentary_and_the_blank_lines_survive() -> None:
    out = migrate_charter_text(OLD_CHARTER, where="a charter")
    assert "Nobody's, for a test." in out
    assert '\n\n  "motif": {' in out


def test_prose_that_says_a_field_name_is_left_alone() -> None:
    """A bare string replacement would have rewritten this. It is not a
    key: it is commentary about the section."""
    out = migrate_charter_text(OLD_CHARTER, where="a charter")
    assert "It says ribbon_stroke in its own prose." in out


def test_the_sections_that_are_not_the_motif_are_untouched() -> None:
    before = json.loads(OLD_CHARTER)
    after = json.loads(migrate_charter_text(OLD_CHARTER, where="a charter"))
    assert list(after) == list(before)
    for section in ("_comment", "colour", "layout"):
        assert after[section] == before[section]


def test_a_migrated_charter_is_a_complete_motif_the_reader_accepts() -> None:
    """The parade: what comes out is a section `brand.py` can draw from,
    field for field, under the family it names."""
    section = json.loads(migrate_charter_text(OLD_CHARTER, where="a charter"))["motif"]
    wanted = brand.MOTIF_FIELDS[section[FAMILY]]
    assert [field for field in wanted if field not in section] == []


# --- what it refuses ------------------------------------------------------


def test_a_section_carrying_both_names_is_refused_and_names_both_values() -> None:
    text = OLD_CHARTER.replace(
        '"ribbon_stroke": "#123456",',
        '"ribbon_stroke": "#123456",\n    "stroke": "#654321",',
    )
    with pytest.raises(MigrationRefusedError) as excinfo:
        migrate_charter_text(text, where="a charter")
    message = str(excinfo.value)
    assert "ribbon_stroke" in message and "stroke" in message
    assert "#123456" in message and "#654321" in message


def test_a_file_that_is_not_a_charter_is_refused() -> None:
    with pytest.raises(MigrationRefusedError, match="this is not a charter"):
        migrate_charter_text('{"colour": {}}', where="a charter")


def test_a_top_level_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(MigrationRefusedError, match="must be an object"):
        migrate_charter_text("[1, 2]", where="a charter")


def test_a_motif_that_does_not_open_on_a_line_of_its_own_is_refused() -> None:
    """There is nowhere to write `family` in a section written on one line
    without reformatting the file, and reformatting is what the whole
    text-in/text-out shape exists to avoid."""
    text = '{"colour": {}, "motif": {"ribbon_stroke": "#123456"}}'
    with pytest.raises(MigrationRefusedError, match="does not open on a line"):
        migrate_charter_text(text, where="a charter")


# --- idempotence and reversibility ----------------------------------------


def test_migrating_twice_produces_the_same_bytes() -> None:
    """Not a refusal on the second run: a migration that failed when
    replayed could not sit inside an upgrade script."""
    once = migrate_charter_text(OLD_CHARTER, where="a charter")
    assert migrate_charter_text(once, where="a charter") == once


def test_a_migrated_charter_is_returned_untouched() -> None:
    assert migrate_charter_text(NEW_CHARTER, where="a charter") == NEW_CHARTER


def test_a_half_migrated_charter_is_finished_rather_than_refused() -> None:
    """Somebody renamed the fields by hand and stopped. The family is
    still missing, and the run that follows writes it."""
    half = NEW_CHARTER.replace('    "family": "ribbon",\n', "")
    finished = migrate_charter_text(half, where="a charter")
    assert finished == NEW_CHARTER


def test_only_key_lines_change_and_only_their_names() -> None:
    """Why the migration ships no `--undo`: every line that changes is a
    key line, and on each of them everything after the colon is the same
    text as before. The one line that is added is the family. There is
    nothing an undo would have to reconstruct, and the prose is left
    saying whatever it said -- the paragraph under `_family` still
    describes the ribbon, because rewriting English would bury the rename
    this file exists to make reviewable."""
    before = OLD_CHARTER.splitlines()
    after = migrate_charter_text(OLD_CHARTER, where="a charter").splitlines()
    family_line = f'    "{FAMILY}": "{DRAWN}",'
    assert after.count(family_line) == 1
    assert len(after) == len(before) + 1

    without = [line for line in after if line != family_line]
    differing = [(b, a) for b, a in zip(before, without, strict=True) if b != a]
    assert len(differing) == 4
    for b, a in differing:
        assert b.partition(":")[2] == a.partition(":")[2]
        assert rename(b.split('"')[1]) == a.split('"')[1]


# --- the repository's own charters ----------------------------------------


def test_the_charters_it_names_are_the_ones_this_repository_ships() -> None:
    """A charter named here that does not exist would be a migration that
    quietly skipped a file; one that exists and is not named would be a
    charter left under the old shape."""
    assert brand.DEFAULT_PATH in CHARTERS
    assert brand.INSTANCE_PATH in CHARTERS
    for rel in CHARTERS:
        assert (ROOT / rel).is_file(), rel.as_posix()
    declared = {
        path.parent.as_posix()
        for path in ROOT.glob(f"examples/*/{brand.INSTANCE_PATH.as_posix()}")
    }
    assert {
        (ROOT / rel).parent.as_posix()
        for rel in CHARTERS
        if rel.as_posix().startswith("examples/")
    } == declared, "an instance charter exists that this migration does not name"


@pytest.mark.parametrize("rel", CHARTERS, ids=lambda p: p.as_posix())
def test_every_charter_here_is_past_the_migration(rel: Path) -> None:
    """The migration is finished only when every charter this repository
    ships is past it: the product's own default, this instance's, and the
    worked example `test_second_instance.py` builds the repository as."""
    section = json.loads((ROOT / rel).read_text(encoding="utf-8"))[brand.MOTIF_KEY]
    for key in section:
        assert rename(key) == key, f"{rel.as_posix()}: motif.{key}"
    assert section[FAMILY] in motifs.FAMILIES, rel.as_posix()
    wanted = brand.MOTIF_FIELDS[section[FAMILY]]
    assert [field for field in wanted if field not in section] == [], rel.as_posix()


# --- the script as it is actually run -------------------------------------


def _charters_at(root: Path, text: str) -> list[Path]:
    written: list[Path] = []
    for rel in CHARTERS:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
        written.append(path)
    return written


def test_main_migrates_every_charter_and_a_second_run_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    written = _charters_at(tmp_path, OLD_CHARTER)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main([]) == 0
    after = [path.read_text(encoding="utf-8") for path in written]
    assert all(text == NEW_CHARTER for text in after)

    assert main([]) == 0
    assert [path.read_text(encoding="utf-8") for path in written] == after
    assert capsys.readouterr().out.count("already migrated") == len(CHARTERS)


def test_a_duplicate_that_has_written_no_charter_of_its_own_is_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`instance/data/brand.json` is optional: a duplicate that has chosen
    no design has none, and builds from the product's own."""
    _charters_at(tmp_path, OLD_CHARTER)
    (tmp_path / brand.INSTANCE_PATH).unlink()
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main([]) == 0
    out = capsys.readouterr().out
    assert f"{brand.INSTANCE_PATH.as_posix()}: no charter here" in out


def test_main_writes_nothing_when_one_charter_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run that had already rewritten one charter when it met a refusal
    in another would leave the repository holding charters under two
    shapes, which is the one state no reader can draw from."""
    written = _charters_at(tmp_path, OLD_CHARTER)
    written[-1].write_text(
        OLD_CHARTER.replace(
            '"ribbon_stroke": "#123456",',
            '"ribbon_stroke": "#123456",\n    "stroke": "#654321",',
        ),
        encoding="utf-8",
        newline="",
    )
    before = [path.read_text(encoding="utf-8") for path in written]
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main([]) == 1
    assert [path.read_text(encoding="utf-8") for path in written] == before
    err = capsys.readouterr().err
    assert CHARTERS[-1].as_posix() in err


def test_a_dry_run_prints_the_diff_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    written = _charters_at(tmp_path, OLD_CHARTER)
    before = [path.read_text(encoding="utf-8") for path in written]
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert '-    "ribbon_stroke": "#123456",' in out
    assert '+    "stroke": "#123456",' in out
    assert '+    "family": "ribbon",' in out
    assert '-    "logo_dots": "#f0c419",' not in out
    assert "nothing written" in out
    assert [path.read_text(encoding="utf-8") for path in written] == before
