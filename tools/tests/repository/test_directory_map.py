"""The map of the repository's root, and the guard that keeps it derived.

Two hand-written tables of top-level directories existed, nine rows in
`README.md` and eight in `docs/engineering/architecture.md`. They disagreed with each
other, and between them they placed eight of the twelve directories this
repository tracked then: `.claude/`, `brand/`, `fonts/` and `instances/`
were in neither, and `config/` was in one of the two.
`tools/scripts/generate_directory_map.py` derives the one that survives, and
this module holds the halves that make that stick.

**The map is held against `git ls-files`, not against itself.** Both sides of
`--check` come out of the same generator, so a generator that read half the
root would agree with a map of half the root and report success.
`test_the_map_names_every_tracked_top_level_directory` reads the index
directly, in this module, and requires a row for every directory it finds --
which is the check that would have caught the four missing directories on the
day one of them was added.

**The check does not repair.** A mode that rewrote the page it was checking
would report success on a repository that still held the wrong map.

**The rendering is exercised on a repository written here** rather than on this
one, so a test about a directory nobody wrote a line for does not require this
repository to hold one.
"""

from __future__ import annotations

import subprocess  # nosec B404
from pathlib import Path

import pytest
from generate_directory_map import (
    _BEGIN,
    _END,
    COMMAND,
    DOC_PATH,
    PURPOSE,
    ROOT_FILE_PURPOSE,
    crossings,
    directory_map,
    main,
    owner_of_directory,
    purposes_for,
    render_block,
    root_files,
    root_purposes_for,
    splice,
    top_level_directories,
    tracked_files,
)

from convener_ops.declaration.boundary import INSTANCE, PRODUCT, load
from convener_ops.declaration.paths import repo_root

ROOT = repo_root()
README = ROOT / "README.md"

#: The anchor `README.md` links to, and the heading it has to answer to.
HEADING = "## Every path at the root, and who owns it"
ANCHOR = "docs/engineering/architecture.md#every-path-at-the-root-and-who-owns-it"

#: A repository with this repository's shape and none of its content: one
#: tracked file per top-level directory, plus the four paths whose owner is
#: not their directory's obvious one. Written out rather than read off the
#: real tree, so the tests below keep meaning what they say when this
#: repository grows a directory.
FAKE_TREE: dict[str, tuple[str, ...]] = {
    ".github": ("workflows/quality.yml",),
    "app": ("src/main.tsx",),
    "assets": ("brand/convener/brand.json", "fonts/Archivo-LICENSE.txt"),
    "declarations": ("boundary.yml",),
    "docs": ("engineering/architecture.md", "handbook/governance/register.md"),
    "instance": ("data/config.yml", "data/schema.md", "keys/signing/README.md"),
    "examples": ("the-example-collective/README.md",),
    "services": ("auth-proxy/src/index.js",),
    "site": ("src/index.njk",),
    "tools": ("convener_ops/cli/__init__.py",),
}

#: The other half of the fake root: one tracked file per line of
#: `ROOT_FILE_PURPOSE`, written out for the reason `FAKE_TREE` is. The two
#: lists have to agree with the generator's two tables or `root_purposes_for`
#: refuses, which is the same coupling `FAKE_TREE` already has with
#: `PURPOSE` and the same one that makes a file added without a line a red
#: build rather than a shorter table.
FAKE_ROOT_FILES: tuple[str, ...] = (
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".gitleaks.toml",
    ".nvmrc",
    ".pre-commit-config.yaml",
    "ADDITIONAL-TERM.md",
    "AGENTS.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "CLAUDE.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE.json",
    "README.md",
    "SECURITY.md",
    "TRADEMARK.md",
    "cspell.json",
    "gates.sh",
)

#: `docs/engineering/architecture.md` as this script sees it: prose, the two
#: markers, and prose again. Nothing outside them may move.
SKELETON = f"""# Architecture

Prose the generator never touches.

{HEADING}

{_BEGIN}
{_END}

Prose after it, equally untouched.
"""


def fake_tracked() -> tuple[str, ...]:
    """Every path `FAKE_TREE` and `FAKE_ROOT_FILES` hold, as git reports
    them."""
    return tuple(
        sorted(
            [
                f"{directory}/{name}"
                for directory, names in FAKE_TREE.items()
                for name in names
            ]
            + list(FAKE_ROOT_FILES)
        )
    )


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository holding the declaration and an unfilled page.

    `tracked_files` is replaced rather than a real repository being
    initialised: what this fixture is for is the rendering and the guard, and
    `test_the_index_is_read_and_reaches_every_directory` below exercises the
    git call itself against the real tree.
    """
    (tmp_path / "declarations").mkdir()
    (tmp_path / "declarations" / "boundary.yml").write_text(
        (ROOT / "declarations" / "boundary.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="",
    )
    (tmp_path / DOC_PATH).parent.mkdir(parents=True)
    (tmp_path / DOC_PATH).write_text(SKELETON, encoding="utf-8", newline="")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "generate_directory_map.tracked_files", lambda _root: fake_tracked()
    )
    return tmp_path


# --------------------------------------------------------------------------
# The map is not vacuous
# --------------------------------------------------------------------------


def test_the_index_is_read_and_reaches_every_directory() -> None:
    """`git ls-files` answers, and answers about the whole repository.

    A call that failed, or that returned a handful of paths, would make
    every check below a comparison between two short lists.
    """
    tracked = tracked_files(ROOT)

    assert len(tracked) > 500, (
        f"git ls-files reported {len(tracked)} tracked paths, which is not "
        "this repository -- the call is reading somewhere else"
    )
    assert "README.md" in tracked
    assert "declarations/boundary.yml" in tracked
    assert "tools/scripts/generate_schema_doc.py" in tracked


def test_the_map_names_every_tracked_top_level_directory() -> None:
    """The one check that does not go through the generator twice.

    Both sides of `--check` are rendered by the same code, so a generator
    that saw two thirds of the root would produce a map of two thirds of the
    root and agree with itself. This reads the index here and requires a row
    for each directory it finds, which is the property the two hand-written
    tables failed for four directories and nobody noticed.
    """
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.splitlines()
    directories = sorted({name.split("/", 1)[0] for name in listed if "/" in name})

    assert directories, "no tracked path has a directory component at all"
    page = (ROOT / DOC_PATH).read_text(encoding="utf-8")
    block = page.partition(_BEGIN)[2].partition(_END)[0]
    for directory in directories:
        assert f"| `{directory}/` |" in block, (
            f"{DOC_PATH.as_posix()} has no row for the tracked directory "
            f"{directory}/ -- run `{COMMAND}` from `tools/`"
        )
    rows = [
        line
        for line in block.splitlines()
        if line.startswith("| `") and line.split("|")[1].strip().endswith("/`")
    ]
    assert len(rows) == len(directories), (
        f"the map holds {len(rows)} rows for {len(directories)} tracked "
        "directories, so it names something this repository does not track"
    )


def test_the_map_names_every_tracked_file_at_the_root() -> None:
    """The same reading, on the half of the root that had no table at all.

    `CHANGELOG.md`, `CODE_OF_CONDUCT.md`, `gates.sh`, `cspell.json` and
    `NOTICE.json` were on no page of this repository, and neither were the
    six dotfiles beside them: the map covered directories, and a file at
    the root is not one. This reads the index here rather than through the
    generator, for the reason the check above does.
    """
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.splitlines()
    files = sorted(name for name in listed if "/" not in name)

    assert len(files) > 10, (
        f"the index reports {len(files)} files at the root of this "
        "repository, which is not the root this map describes"
    )
    page = (ROOT / DOC_PATH).read_text(encoding="utf-8")
    block = page.partition(_BEGIN)[2].partition(_END)[0]
    for name in files:
        assert f"| `{name}` |" in block, (
            f"{DOC_PATH.as_posix()} has no row for the tracked root file "
            f"{name} -- run `{COMMAND}` from `tools/`"
        )
    rows = [
        line
        for line in block.splitlines()
        if line.startswith("| `") and not line.split("|")[1].strip().endswith("/`")
    ]
    assert len(rows) == len(files), (
        f"the map holds {len(rows)} file rows for {len(files)} tracked root "
        "files, so it names something this repository does not track"
    )


def test_a_path_inside_a_directory_is_not_read_as_a_root_file() -> None:
    """The two halves of the index divide it between them, with nothing
    counted twice and nothing dropped."""
    tracked = fake_tracked()

    assert root_files(tracked) == tuple(sorted(FAKE_ROOT_FILES))
    assert set(root_files(tracked)) & set(top_level_directories(tracked)) == set()
    assert len(root_files(tracked)) + sum(
        len(names) for names in FAKE_TREE.values()
    ) == len(tracked)


def test_a_root_file_with_no_line_is_refused_by_name() -> None:
    """The same failure the directory table has, on the file table."""
    with pytest.raises(ValueError) as raised:
        root_purposes_for([*sorted(ROOT_FILE_PURPOSE), "INVENTED.md"])

    assert "INVENTED.md" in str(raised.value)
    assert "ROOT_FILE_PURPOSE" in str(raised.value)


def test_a_line_for_a_root_file_that_is_gone_is_refused_too() -> None:
    remaining = [name for name in sorted(ROOT_FILE_PURPOSE) if name != "gates.sh"]

    with pytest.raises(ValueError) as raised:
        root_purposes_for(remaining)

    assert "gates.sh" in str(raised.value)


def test_every_root_file_line_is_one_line_of_prose() -> None:
    for name, sentence in ROOT_FILE_PURPOSE.items():
        assert "\n" not in sentence, f"{name}'s line is more than a line"
        assert "|" not in sentence, f"{name}'s line would break the table"
        assert sentence.endswith("."), f"{name}'s line is not a sentence"


def test_the_committed_page_is_what_the_repository_derives() -> None:
    """The loop, read off disk: the map matches the root it describes."""
    assert (ROOT / DOC_PATH).read_text(encoding="utf-8") == directory_map(ROOT)


def test_the_block_says_it_is_generated_and_names_the_command() -> None:
    """A reader who opens the page has to be told not to edit the block."""
    block = (
        (ROOT / DOC_PATH)
        .read_text(encoding="utf-8")
        .partition(_BEGIN)[2]
        .partition(_END)[0]
    )

    assert "generated" in block
    assert COMMAND in block


def test_the_readme_links_to_the_map_rather_than_restating_it() -> None:
    """`README.md` carried the second table. It carries the link now."""
    readme = README.read_text(encoding="utf-8")

    assert ANCHOR in readme
    assert HEADING in (ROOT / DOC_PATH).read_text(encoding="utf-8")
    assert "| Folder | What it holds |" not in readme, (
        "README.md holds a table of directories again -- the map it links to "
        "is the one home for that"
    )


# --------------------------------------------------------------------------
# The owner column
# --------------------------------------------------------------------------


def test_a_directory_the_declaration_hands_over_reads_as_the_instance_s() -> None:
    boundary = load(ROOT)
    tracked = fake_tracked()

    assert owner_of_directory("instance", tracked, boundary) == INSTANCE


def test_the_files_the_declaration_keeps_do_not_flip_the_directory() -> None:
    """`instance/` holds two of the product's own files, both declared.

    Counting them would make the directory the product's on the strength of
    a three-line stub and a wire-format note, which is the opposite of what
    `declarations/boundary.yml` says about it.
    """
    boundary = load(ROOT)
    kept = ("instance/data/schema.md", "instance/keys/signing/README.md")
    assert set(kept) <= set(boundary.kept_files)
    assert all(boundary.owner_of(name) == PRODUCT for name in kept)

    assert owner_of_directory("instance", (*kept,), boundary) == PRODUCT
    assert (
        owner_of_directory("instance", ("instance/data/config.yml", *kept), boundary)
        == INSTANCE
    )


def test_one_instance_path_does_not_make_a_product_directory_the_instance_s() -> None:
    boundary = load(ROOT)

    assert owner_of_directory("docs", fake_tracked(), boundary) == PRODUCT


def test_a_directory_with_no_tracked_file_is_the_product_s() -> None:
    """Total by construction: every directory gets one of the two answers."""
    assert owner_of_directory("nowhere", fake_tracked(), load(ROOT)) == PRODUCT


def test_every_crossing_is_listed_and_says_which_way_it_crosses() -> None:
    """The owner column is one word, and three paths contradict it."""
    boundary = load(ROOT)
    tracked = fake_tracked()
    owners = {name: owner_of_directory(name, tracked, boundary) for name in FAKE_TREE}

    crossed = crossings(owners, tracked, boundary)

    assert crossed == (
        ("docs/handbook/governance/register.md", INSTANCE),
        ("instance/data/schema.md", PRODUCT),
        ("instance/keys/signing/README.md", PRODUCT),
    )
    block = render_block(
        sorted(FAKE_TREE), owners, purposes_for(sorted(FAKE_TREE)), crossed
    )
    assert "the instance's, inside a directory the product owns" in block
    assert "the product's, inside a directory the instance owns" in block


# --------------------------------------------------------------------------
# The purpose line
# --------------------------------------------------------------------------


def test_a_directory_with_no_purpose_line_is_refused_by_name() -> None:
    """The failure the two hand-written tables never had.

    A directory added and left off a table is what produced the defect this
    generator removes, four times over. Here it raises, naming the
    directory, and `--check` turns that into a red build.
    """
    with pytest.raises(ValueError) as raised:
        purposes_for([*sorted(PURPOSE), "invented"])

    assert "invented" in str(raised.value)
    assert "PURPOSE" in str(raised.value)


def test_a_purpose_line_for_a_directory_that_is_gone_is_refused_too() -> None:
    """The same drift from the other end: a row nothing backs any more."""
    remaining = [name for name in sorted(PURPOSE) if name != "assets"]

    with pytest.raises(ValueError) as raised:
        purposes_for(remaining)

    assert "assets" in str(raised.value)


def test_every_purpose_line_is_one_line_of_prose() -> None:
    """One line per directory, and nothing that could break the table."""
    for name, sentence in PURPOSE.items():
        assert "\n" not in sentence, f"{name}'s purpose line is more than a line"
        assert "|" not in sentence, f"{name}'s purpose line would break the table"
        assert sentence.endswith("."), f"{name}'s purpose line is not a sentence"


# --------------------------------------------------------------------------
# The splice
# --------------------------------------------------------------------------


def test_nothing_outside_the_markers_moves() -> None:
    spliced = splice(SKELETON, "replaced\n")

    assert spliced.startswith("# Architecture\n\nProse the generator never touches.")
    assert spliced.endswith("Prose after it, equally untouched.\n")
    assert "replaced" in spliced


def test_a_missing_marker_raises_rather_than_leaving_the_page_alone() -> None:
    """A silent no-op would make `--check` compare the page with itself."""
    with pytest.raises(ValueError, match="markers not found"):
        splice("# Architecture\n", "replaced\n")


# --------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------


def test_writing_then_checking_passes(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([]) == 0
    assert main(["--check"]) == 0
    assert "matches the tracked root" in capsys.readouterr().out


def test_a_second_write_changes_nothing_and_says_so(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([]) == 0
    capsys.readouterr()
    assert main([]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_check_leaves_a_stale_page_exactly_as_it_found_it(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A check that repairs is a green tick over the defect it exists for."""
    page = fake_repo / DOC_PATH
    before = page.read_text(encoding="utf-8")

    assert main(["--check"]) == 1
    assert page.read_text(encoding="utf-8") == before
    assert COMMAND in capsys.readouterr().err


def test_a_directory_added_without_a_line_fails_the_check(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mutation, as a test rather than as something somebody remembers."""
    assert main([]) == 0
    monkeypatch.setattr(
        "generate_directory_map.tracked_files",
        lambda _root: (*fake_tracked(), "invented/thing.md"),
    )

    assert main(["--check"]) == 1
    assert "invented" in capsys.readouterr().err


def test_a_root_file_added_without_a_line_fails_the_check(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mutation the hand-written list this replaces could not have."""
    assert main([]) == 0
    monkeypatch.setattr(
        "generate_directory_map.tracked_files",
        lambda _root: (*fake_tracked(), "INVENTED.md"),
    )

    assert main(["--check"]) == 1
    assert "INVENTED.md" in capsys.readouterr().err


def test_an_owner_changed_in_the_declaration_fails_the_check(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other mutation: the same directories, one on the other side."""
    assert main([]) == 0
    declaration = fake_repo / "declarations" / "boundary.yml"
    declaration.write_text(
        declaration.read_text(encoding="utf-8").replace(
            "instance:\n  - path: instance/data/\n",
            "instance:\n  - path: assets/\n"
            "    reason: >-\n      Handed over for this test.\n"
            "  - path: instance/data/\n",
        ),
        encoding="utf-8",
        newline="",
    )

    assert main(["--check"]) == 1
    assert COMMAND in capsys.readouterr().err
    assert main([]) == 0
    block = (
        (fake_repo / DOC_PATH)
        .read_text(encoding="utf-8")
        .partition(_BEGIN)[2]
        .partition(_END)[0]
    )
    assert f"| `assets/` | {INSTANCE} |" in block


def test_a_declaration_that_cannot_be_read_stops_the_check(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A boundary nobody can read must not be guessed at."""
    (fake_repo / "declarations" / "boundary.yml").write_text(
        "owner: product\nv: 1\n", encoding="utf-8", newline=""
    )

    assert main(["--check"]) == 1
    assert "instance:" in capsys.readouterr().err


def test_an_empty_index_is_refused_rather_than_rendered(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A map of nothing would pass every check it is compared against."""
    monkeypatch.setattr("generate_directory_map.tracked_files", lambda _root: ())

    assert main([]) == 1
    assert "no tracked directory" in capsys.readouterr().err


def test_the_rendering_is_a_function_of_its_inputs_alone(fake_repo: Path) -> None:
    """Byte-identical over two runs, which is what makes `--check` a fact."""
    assert directory_map(fake_repo) == directory_map(fake_repo)


def test_the_top_level_reading_ignores_a_file_at_the_root() -> None:
    assert top_level_directories(("README.md", "app/src/main.tsx")) == ("app",)


def test_the_terminal_output_is_ascii(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The page is written in the handbook's English; the console is not."""
    main([])
    main(["--check"])
    captured = capsys.readouterr()
    (captured.out + captured.err).encode("ascii")
