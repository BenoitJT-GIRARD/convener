"""The v5 -> v6 migration (tools/migrations/migrate_v6.py).

Schema v6 renames one configuration key: `vw_counter` becomes
`next_edition_number`. Unlike the three migrations before it, this one
rewrites **text** rather than a loaded mapping -- both files it touches
open with paragraphs of YAML comments that a load-and-dump round trip
would delete -- so the tests below are shaped around that: what the
rewrite does to a line, what it refuses, and the post-condition that
proves it changed the key and nothing else.

Two claims are held here that no other module can hold:

- the version this migration stamps is the one **both** later writers
  stamp (`convener_ops.cli.SPEAKERS_HEADER` and `app/src/data/yaml.ts`), so a
  file migrated today and swept tomorrow does not produce a second diff;
- the migrated shape is the shape **both** validators require, checked
  against the real `instance/data/config.yml` rather than against a fixture built
  here, because the file this repository actually carries is the one the
  migration was written for.

No record below is anybody's. The fixtures are the smallest legal config
this repository's own `conftest.config()` produces, and the two names that
appear are invented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import instance_identity
import pytest
import yaml
from conftest import config as minimal_config
from migrate_v6 import (
    _V5_STAMP,
    _V6_STAMP,
    DATA_DIRS,
    NEW_KEY,
    OLD_KEY,
    _ascii,
    main,
    migrate_config_text,
    migrate_speakers_text,
)

from convener_ops.cli.store import SPEAKERS_HEADER, dump_config
from convener_ops.declaration.paths import repo_root
from convener_ops.governance.validate import validate_config

ROOT = repo_root()

#: A v5 config as a file actually holds one: a comment paragraph first,
#: the counter under its old name second, and the rest of the settings
#: after it. Written as text rather than dumped, because text is what this
#: migration reads and the comments are half of what it has to preserve.
V5_CONFIG = (
    "# Repo-wide config for the convener app\n"
    "# A second comment line, so the test notices if a rewrite eats one.\n"
    "season: 2026\n"
    f"{OLD_KEY}: 5\n"
    "overlap_window_days: 7\n"
)

V5_SPEAKERS = (
    f"# Speakers ({_V5_STAMP} - see docs/engineering/schema.md)\n- id: spk-001\n"
)


# --- what the rename does -------------------------------------------------


def test_the_counter_is_renamed_and_keeps_its_value() -> None:
    migrated = yaml.safe_load(migrate_config_text(V5_CONFIG))
    assert OLD_KEY not in migrated
    assert migrated[NEW_KEY] == 5


def test_the_rename_happens_in_place_rather_than_at_the_end() -> None:
    """The diff has to read as one renamed line. A key re-inserted at the
    end of the mapping would be the same data and an unreviewable diff."""
    keys = list(yaml.safe_load(migrate_config_text(V5_CONFIG)))
    assert keys == ["season", NEW_KEY, "overlap_window_days"]


def test_the_comments_survive() -> None:
    out = migrate_config_text(V5_CONFIG)
    assert "# Repo-wide config for the convener app" in out
    assert "# A second comment line" in out


def test_only_the_one_line_changes() -> None:
    before = V5_CONFIG.splitlines()
    after = migrate_config_text(V5_CONFIG).splitlines()
    differing = [
        i for i, (b, a) in enumerate(zip(before, after, strict=True)) if b != a
    ]
    assert differing == [3]


def test_the_old_name_written_anywhere_but_as_the_key_is_left_alone() -> None:
    """A bare string replacement would have rewritten all three of these.

    The comment is prose about the migration itself, the nested key
    belongs to no reader this migration knows, and the value is text a
    volunteer typed."""
    text = (
        f"# renamed from {OLD_KEY} by schema v6\n"
        "season: 2026\n"
        f"{OLD_KEY}: 5\n"
        f"instructions: 'the {OLD_KEY} is not a room instruction'\n"
        f"sla_days:\n  {OLD_KEY}: 3\n"
    )
    out = migrate_config_text(text)
    assert f"# renamed from {OLD_KEY}" in out
    assert f"the {OLD_KEY} is not a room instruction" in out
    assert f"  {OLD_KEY}: 3" in out
    assert f"\n{NEW_KEY}: 5\n" in out


# --- what it refuses ------------------------------------------------------


def test_a_file_carrying_both_names_is_refused_and_names_both_values() -> None:
    text = f"season: 2026\n{OLD_KEY}: 5\n{NEW_KEY}: 9\n"
    with pytest.raises(RuntimeError) as excinfo:
        migrate_config_text(text)
    message = str(excinfo.value)
    assert OLD_KEY in message and NEW_KEY in message
    assert "5" in message and "9" in message


def test_a_config_that_is_not_a_mapping_is_refused() -> None:
    with pytest.raises(RuntimeError, match="must be a mapping"):
        migrate_config_text("- a\n- b\n")


# --- idempotence ----------------------------------------------------------


def test_migrating_twice_produces_the_same_bytes() -> None:
    once = migrate_config_text(V5_CONFIG)
    assert migrate_config_text(once) == once


def test_a_v6_file_is_returned_untouched() -> None:
    v6 = V5_CONFIG.replace(OLD_KEY, NEW_KEY)
    assert migrate_config_text(v6) == v6


# --- reversibility --------------------------------------------------------


def test_the_rename_is_reversible_byte_for_byte() -> None:
    """The claim the module docstring makes, driven rather than asserted
    in prose: renaming back gives the original file, byte for byte. That
    is why no `--undo` ships -- there is nothing an undo would have to
    reconstruct."""
    forwards = migrate_config_text(V5_CONFIG)
    backwards = forwards.replace(f"\n{NEW_KEY}:", f"\n{OLD_KEY}:")
    assert backwards == V5_CONFIG


# --- the header stamp -----------------------------------------------------


def test_the_speakers_header_is_restamped_and_nothing_else_moves() -> None:
    out = migrate_speakers_text(V5_SPEAKERS)
    assert out.startswith(f"# Speakers ({_V6_STAMP}")
    assert out.endswith("- id: spk-001\n")


def test_a_bespoke_first_line_keeps_its_own_wording() -> None:
    """`examples/the-example-collective/instance/data/speakers.yml` opens with
    a sentence of its own rather than the standard header, and that sentence
    is prose."""
    text = f"# The example instance's own speakers ({_V5_STAMP} --\n- id: x\n"
    assert migrate_speakers_text(text) == text.replace(_V5_STAMP, _V6_STAMP)


def test_a_file_already_stamped_v6_is_returned_untouched() -> None:
    v6 = V5_SPEAKERS.replace(_V5_STAMP, _V6_STAMP)
    assert migrate_speakers_text(v6) == v6


def test_the_stamp_it_writes_is_the_one_every_later_writer_writes() -> None:
    """Three constants say what version a speakers file announces: this
    migration's, the package's writer, and the browser's. A migrated file
    swept the next morning must not gain a second diff, so all three are
    held together here rather than by one importing another and leaving
    the third free to drift."""
    browser = (ROOT / "app" / "src" / "data" / "yaml.ts").read_text(encoding="utf-8")
    assert _V6_STAMP in SPEAKERS_HEADER
    assert _V5_STAMP not in SPEAKERS_HEADER
    assert f"'# Speakers ({_V6_STAMP}" in browser
    assert _V5_STAMP not in browser


# --- against the validators and the real files ----------------------------


def test_the_migrated_config_passes_the_validator() -> None:
    v5 = dump_config(
        {
            (OLD_KEY if key == NEW_KEY else key): value
            for key, value in minimal_config().items()
        }
    )
    assert any(error for error in validate_config(yaml.safe_load(v5)))
    assert validate_config(yaml.safe_load(migrate_config_text(v5))) == []


def test_this_repository_and_its_example_both_hold_the_migrated_shape() -> None:
    """The migration is only finished when both trees it names are past
    it. Read off the files themselves rather than off a fixture: the
    example instance is the one `test_second_instance.py` builds this
    whole repository as, and a v5 file there fails that build's own
    `convener-validate` (D-25)."""
    for directory in DATA_DIRS:
        config = yaml.safe_load(
            (ROOT / directory / "config.yml").read_text(encoding="utf-8")
        )
        assert NEW_KEY in config, directory
        assert OLD_KEY not in config, directory
        speakers = (ROOT / directory / "speakers.yml").read_text(encoding="utf-8")
        assert _V6_STAMP in speakers.partition("\n")[0], directory


def test_no_reader_of_the_config_still_asks_for_the_old_name() -> None:
    """The rename is only real when every reader moved with it. The three
    that decide whether a file loads at all: this package's validator, the
    browser's narrowing, and the model both derive from."""
    for name in (
        "tools/convener_ops/governance/validate.py",
        "app/src/data/validate.ts",
        "app/src/data/types.ts",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert NEW_KEY in text, name
        assert OLD_KEY not in text, name


def test_the_generated_schema_page_names_the_new_key() -> None:
    """`docs/engineering/schema.md` is derived from the model and shipped
    inside every duplicate's handbook, so it is where the old name would
    have outlived the rename in the one place a volunteer reads."""
    page = (ROOT / "docs" / "engineering" / "schema.md").read_text(encoding="utf-8")
    assert f"| `{NEW_KEY}` |" in page
    assert OLD_KEY not in page


def test_nothing_published_carries_the_key_at_all() -> None:
    """The reason this rename was safe to make, checked rather than
    recited: the counter's *name* is in no address, on no certificate and
    in no key filename. Those three are built by the modules below, and
    none of them reads the key under either name -- so renaming it moved
    nothing a reader outside this repository can reach."""
    for name in (
        "tools/convener_ops/declaration/published.py",
        "tools/convener_ops/journey/certificate.py",
        "tools/convener_ops/journey/eventkeys.py",
        "tools/convener_ops/journey/registration.py",
        "tools/convener_ops/publication/agenda.py",
        "tools/convener_ops/journey/signing.py",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert OLD_KEY not in text, name
        assert NEW_KEY not in text, name


# --- the script as it is actually run -------------------------------------


def _tree(root: Path, directory: str, config: str, speakers: str) -> tuple[Path, Path]:
    data = root / directory
    data.mkdir(parents=True, exist_ok=True)
    config_path = data / "config.yml"
    speakers_path = data / "speakers.yml"
    config_path.write_text(config, encoding="utf-8", newline="")
    speakers_path.write_text(speakers, encoding="utf-8", newline="")
    return config_path, speakers_path


def _both_trees(root: Path) -> list[Path]:
    written: list[Path] = []
    for directory in DATA_DIRS:
        written.extend(_tree(root, directory, V5_CONFIG, V5_SPEAKERS))
    return written


def test_main_migrates_both_trees_and_a_second_run_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    written = _both_trees(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main([]) == 0
    after = [path.read_text(encoding="utf-8") for path in written]
    assert all(OLD_KEY not in text for text in after[0::2])
    assert all(_V6_STAMP in text for text in after[1::2])

    assert main([]) == 0
    assert [path.read_text(encoding="utf-8") for path in written] == after
    assert capsys.readouterr().out.count("already migrated") == 4


def test_main_refuses_a_tree_that_carries_both_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _both_trees(tmp_path)
    _tree(
        tmp_path,
        DATA_DIRS[1],
        f"season: 2026\n{OLD_KEY}: 5\n{NEW_KEY}: 9\n",
        V5_SPEAKERS,
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main([]) == 1
    err = capsys.readouterr().err
    assert f"{DATA_DIRS[1]}/config.yml" in err
    assert OLD_KEY in err and NEW_KEY in err


def test_a_dry_run_prints_the_diff_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    written = _both_trees(tmp_path)
    before = [path.read_text(encoding="utf-8") for path in written]
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"-{OLD_KEY}: 5" in out
    assert f"+{NEW_KEY}: 5" in out
    assert "-season: 2026" not in out
    assert "nothing written" in out
    assert [path.read_text(encoding="utf-8") for path in written] == before


def test_the_dry_run_prints_nothing_a_windows_console_cannot_render() -> None:
    printed = _ascii("# Speakers (unified schema v6 — see docs/engineering/schema.md)")
    assert printed.isascii()
    assert "\\u2014" in printed


def test_the_two_trees_it_names_are_the_two_this_repository_ships() -> None:
    """A directory named here that does not exist would be a migration
    that quietly skipped a file; one that exists and is not named would be
    a tree left at v5."""
    assert DATA_DIRS == (
        "instance/data",
        "examples/the-example-collective/instance/data",
    )
    for directory in DATA_DIRS:
        assert (ROOT / directory / "config.yml").is_file(), directory
        assert (ROOT / directory / "speakers.yml").is_file(), directory
    declared = {
        path.parent.as_posix()
        for path in ROOT.glob("examples/*/instance/data/config.yml")
        if path.is_file()
    }
    assert {(ROOT / directory).as_posix() for directory in DATA_DIRS[1:]} == declared, (
        "an instance tree exists that this migration does not name"
    )


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_the_example_instance_declares_a_number_of_its_own() -> None:
    """Guards the fixture the test above stands on: if the example's own
    counter ever became this instance's, migrating it would prove nothing
    about a second instance."""
    here = yaml.safe_load(
        (ROOT / "instance" / "data" / "config.yml").read_text(encoding="utf-8")
    )
    there = yaml.safe_load(
        (
            ROOT
            / "examples"
            / "the-example-collective"
            / "instance"
            / "data"
            / "config.yml"
        ).read_text(encoding="utf-8")
    )
    assert here[NEW_KEY] != there[NEW_KEY]


def test_the_key_is_not_in_the_declaration_either() -> None:
    """The counter is the instance's *data*, not its declaration: a rename
    in `instance/data/config.yml` must not have needed a companion edit in
    `instance/config.json`, which is the file a duplicate hand-edits."""
    declaration: dict[str, Any] = json.loads(
        (ROOT / "instance" / "config.json").read_text(encoding="utf-8")
    )
    assert OLD_KEY not in declaration
    assert NEW_KEY not in declaration
