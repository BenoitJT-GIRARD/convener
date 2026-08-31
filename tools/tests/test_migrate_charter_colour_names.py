"""The charter colour rename (tools/migrations/migrate_charter_colour_names.py).

Three colour keys named hues -- `purple`, `turquoise`, `cream` -- and the
product's own charter holds a navy under the first and a coral under the
second. They are read by name by every template, so the first palette
anybody measured named the keys for every palette after it. The migration
renames them to the positions they hold: `dominant`, `field`, `band`.

Like `migrate_v6.py`, this one rewrites **text** rather than a loaded
mapping -- a charter is JSON carrying paragraphs of commentary and blank
lines between the groups of colours, neither of which survives a
load-and-dump round trip -- so the tests below are shaped the same way:
what the rewrite does to a line, what it refuses, and the post-condition
that proves it changed the names and nothing else.

Two claims are held here that no other module holds:

- **no colour changes.** Every contrast figure in a charter is the same
  number after the rename as before it, under its renamed key, and
  `brand.contrast_problems` still recomputes all twelve;
- the table the migration renames from is the table
  `convener_ops.publication.brand` refuses an unmigrated charter from, so
  a person sent to the migration by the refusal cannot be sent to a
  different rename than the one that was made.

The charter below is nobody's: three colours picked so that the
arithmetic has something to measure, and no organisation's palette.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from migrate_charter_colour_names import (
    CHARTERS,
    POSITIONS,
    MigrationRefusedError,
    main,
    migrate_charter_text,
    rename,
)

from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand

ROOT = repo_root()

#: A charter as a file actually holds one: commentary first, blank lines
#: between the groups of colours, the roles written beside them. Written
#: as text rather than dumped, because text is what this migration reads
#: and the layout is half of what it has to preserve.
OLD_CHARTER = """\
{
  "_comment": "Nobody's, for a test. It says purple in its own prose.",

  "colour": {
    "purple": "#123456",
    "turquoise": "#f0c419",
    "cream": "#faf7f0",
    "ink": "#222222",
    "ink_muted": "#555555",
    "rule": "#cccccc",
    "white": "#ffffff",
    "black": "#000000",

    "_roles": {
      "purple": "Headlines, ribbon, wordmark.",
      "turquoise": "A ground.",
      "cream": "Bands laid across the field."
    }
  },

  "derived": {
    "_comment": "Values no measurement supplies.",
    "turquoise_text": "#7a5c00",
    "turquoise_tint": "#fdf0c4",
    "purple_hover": "#0d2338",
    "purple_tint": "#d5dae0",
    "ink_faint": "#6a6a6a",
    "rule_strong": "#999999",
    "_purple_hover": "A note about purple_hover."
  },

  "contrast": {
    "purple_on_turquoise": 7.64,
    "white_on_purple": 12.72,
    "ink_on_cream": 14.87,
    "_forbidden": "turquoise as text on white."
  },

  "motif": {
    "family": "ribbon",
    "stroke": "#123456",
    "width_ratio": 0.02,
    "logo_dots": "#f0c419"
  },

  "layout": {}
}
"""

#: The same charter with every colour key under its position. Written out
#: rather than derived, so that a rewrite going wrong in both directions
#: at once could not agree with itself.
NEW_CHARTER = (
    OLD_CHARTER.replace('"purple":', '"dominant":')
    .replace('"turquoise":', '"field":')
    .replace('"cream":', '"band":')
    .replace('"turquoise_text":', '"field_text":')
    .replace('"turquoise_tint":', '"field_tint":')
    .replace('"purple_hover":', '"dominant_hover":')
    .replace('"purple_tint":', '"dominant_tint":')
    .replace('"_purple_hover":', '"_dominant_hover":')
    .replace('"purple_on_turquoise":', '"dominant_on_field":')
    .replace('"white_on_purple":', '"white_on_dominant":')
    .replace('"ink_on_cream":', '"ink_on_band":')
)


def _colour_names(text: str) -> list[str]:
    charter = json.loads(text)
    return [key for key in charter["colour"] if not key.startswith("_")]


# --- what a name becomes --------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("purple", "dominant"),
        ("turquoise", "field"),
        ("cream", "band"),
        ("turquoise_text", "field_text"),
        ("purple_hover", "dominant_hover"),
        ("_purple_hover", "_dominant_hover"),
        ("purple_on_turquoise", "dominant_on_field"),
        ("white_on_purple", "white_on_dominant"),
        ("turquoise_on_purple", "field_on_dominant"),
        ("ink", "ink"),
        ("ink_muted", "ink_muted"),
        ("ink_faint", "ink_faint"),
        ("rule_strong", "rule_strong"),
        ("white", "white"),
        ("black", "black"),
        ("_roles", "_roles"),
        ("_comment", "_comment"),
        ("stroke", "stroke"),
        ("width_ratio", "width_ratio"),
    ],
)
def test_a_key_takes_the_name_of_the_position_it_holds(before: str, after: str) -> None:
    assert rename(before) == after


def test_the_table_is_the_one_the_reader_refuses_from() -> None:
    """A person meeting an unmigrated charter is sent here by
    `brand.SupersededCharterError`. If the two tables could disagree, that
    message would send them to a rename that was never made."""
    assert POSITIONS is brand.SUPERSEDED_COLOURS


# --- what the rewrite does ------------------------------------------------


def test_every_colour_key_is_renamed_and_keeps_its_value() -> None:
    before = json.loads(OLD_CHARTER)
    after = json.loads(migrate_charter_text(OLD_CHARTER, where="a charter"))
    for old, new in POSITIONS.items():
        assert old not in after["colour"]
        assert after["colour"][new] == before["colour"][old]


def test_the_rename_happens_in_place_rather_than_at_the_end() -> None:
    """The diff has to read as renamed lines. A key re-inserted at the end
    of the section would be the same data and an unreviewable diff."""
    assert _colour_names(migrate_charter_text(OLD_CHARTER, where="a charter")) == [
        "dominant",
        "field",
        "band",
        "ink",
        "ink_muted",
        "rule",
        "white",
        "black",
    ]


def test_the_whole_file_is_what_the_rename_makes_of_it() -> None:
    assert migrate_charter_text(OLD_CHARTER, where="a charter") == NEW_CHARTER


def test_the_commentary_and_the_blank_lines_survive() -> None:
    out = migrate_charter_text(OLD_CHARTER, where="a charter")
    assert "Nobody's, for a test." in out
    assert '\n\n  "colour": {' in out


def test_prose_that_says_a_colour_name_is_left_alone() -> None:
    """A bare string replacement would have rewritten all three of these.
    None of them is a key: two are commentary about the palette and the
    third is the value of a key that stays."""
    out = migrate_charter_text(OLD_CHARTER, where="a charter")
    assert "It says purple in its own prose." in out
    assert "A note about purple_hover." in out
    assert '"_forbidden": "turquoise as text on white."' in out


def test_the_sections_that_hold_no_colour_name_are_untouched() -> None:
    before = json.loads(OLD_CHARTER)
    after = json.loads(migrate_charter_text(OLD_CHARTER, where="a charter"))
    assert list(after) == list(before)
    for section in ("_comment", "motif", "layout"):
        assert after[section] == before[section]


# --- no colour changes ----------------------------------------------------


def test_every_contrast_figure_is_the_same_number_afterwards() -> None:
    """The parade the whole migration rests on: the file changes shape and
    the palette does not. Each pairing keeps its value, under the name
    made of the same two colours."""
    before = json.loads(OLD_CHARTER)["contrast"]
    after = json.loads(migrate_charter_text(OLD_CHARTER, where="a charter"))["contrast"]
    assert {rename(key): value for key, value in before.items()} == after


def test_the_migrated_charter_still_recomputes_every_pairing() -> None:
    """`brand.contrast_problems` splits each pairing's name back into two
    colours and measures them. A rename that moved a key without moving
    the pairing that names it would surface here."""
    migrated = json.loads(migrate_charter_text(OLD_CHARTER, where="a charter"))
    assert brand.contrast_problems(migrated, named="a charter") == []


@pytest.mark.parametrize("rel", CHARTERS, ids=lambda p: p.as_posix())
def test_every_pairing_in_every_committed_charter_recomputes(
    rel: Path,
) -> None:
    """The same claim against the real files, from the other end: undo the
    rename on the committed charter and every pairing recomputes to the
    figure standing beside it now."""
    charter: dict[str, Any] = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    colours = brand.colours(charter)
    for name, stored in charter["contrast"].items():
        if name.startswith("_"):
            continue
        ink, _, ground = name.rpartition("_on_")
        computed = round(brand.contrast_ratio(colours[ink], colours[ground]), 2)
        assert computed == stored, f"{rel.as_posix()}: {name}"


# --- what it refuses ------------------------------------------------------


def test_a_section_carrying_both_names_is_refused_and_names_both_values() -> None:
    text = OLD_CHARTER.replace(
        '"purple": "#123456",', '"purple": "#123456",\n    "dominant": "#654321",'
    )
    with pytest.raises(MigrationRefusedError) as excinfo:
        migrate_charter_text(text, where="a charter")
    message = str(excinfo.value)
    assert "purple" in message and "dominant" in message
    assert "#123456" in message and "#654321" in message


def test_a_file_that_is_not_a_charter_is_refused() -> None:
    with pytest.raises(MigrationRefusedError, match="this is not a charter"):
        migrate_charter_text('{"colour": {}, "derived": {}}', where="a charter")


def test_a_top_level_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(MigrationRefusedError, match="must be an object"):
        migrate_charter_text("[1, 2]", where="a charter")


# --- idempotence and reversibility ----------------------------------------


def test_migrating_twice_produces_the_same_bytes() -> None:
    once = migrate_charter_text(OLD_CHARTER, where="a charter")
    assert migrate_charter_text(once, where="a charter") == once


def test_a_migrated_charter_is_returned_untouched() -> None:
    assert migrate_charter_text(NEW_CHARTER, where="a charter") == NEW_CHARTER


def test_only_key_lines_change_and_only_their_names() -> None:
    """Why the migration ships no `--undo`: every line that changes is a
    key line, and on each of them everything after the colon is the same
    text as before. There is nothing an undo would have to reconstruct,
    and the prose is left saying whatever it said -- the note beside
    `_dominant_hover` still spells the old name, because rewriting English
    would bury the rename this file exists to make reviewable."""
    before = OLD_CHARTER.splitlines()
    after = migrate_charter_text(OLD_CHARTER, where="a charter").splitlines()
    differing = [(b, a) for b, a in zip(before, after, strict=True) if b != a]
    assert len(differing) == 14
    for b, a in differing:
        assert b.partition(":")[2] == a.partition(":")[2]
        assert rename(b.split('"')[1]) == a.split('"')[1]


# --- the repository's own charters ----------------------------------------


def test_the_charters_it_names_are_the_ones_this_repository_ships() -> None:
    """A charter named here that does not exist would be a migration that
    quietly skipped a file; one that exists and is not named would be a
    charter left under the old names."""
    assert brand.DEFAULT_PATH in CHARTERS
    assert brand.INSTANCE_PATH in CHARTERS
    for rel in CHARTERS:
        assert (ROOT / rel).is_file(), rel.as_posix()
    declared = {
        path.parent.as_posix()
        for path in ROOT.glob(f"instances/*/{brand.INSTANCE_PATH.as_posix()}")
    }
    assert {
        (ROOT / rel).parent.as_posix()
        for rel in CHARTERS
        if rel.as_posix().startswith("instances/")
    } == declared, "an instance charter exists that this migration does not name"


@pytest.mark.parametrize("rel", CHARTERS, ids=lambda p: p.as_posix())
def test_every_charter_here_is_past_the_rename(rel: Path) -> None:
    """The migration is finished only when every charter this repository
    ships is past it: the product's own default, this instance's, and the
    worked example `test_second_instance.py` builds the repository as."""
    charter = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    for section in ("colour", "derived", "contrast"):
        for key in charter[section]:
            assert rename(key) == key, f"{rel.as_posix()}: {section}.{key}"
    for new in POSITIONS.values():
        assert new in charter["colour"], f"{rel.as_posix()}: colour.{new}"


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
    no colours has none, and builds from the product's own."""
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
    in another would leave the repository holding charters under two sets
    of names, which is the one state no reader can draw from."""
    written = _charters_at(tmp_path, OLD_CHARTER)
    written[-1].write_text(
        OLD_CHARTER.replace(
            '"purple": "#123456",', '"purple": "#123456",\n    "dominant": "#654321",'
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
    assert '-    "purple": "#123456",' in out
    assert '+    "dominant": "#123456",' in out
    assert '-    "ink": "#222222",' not in out
    assert "nothing written" in out
    assert [path.read_text(encoding="utf-8") for path in written] == before
