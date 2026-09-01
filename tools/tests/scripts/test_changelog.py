"""The changelog, and the two halves that keep it worth reading.

`CHANGELOG.md` is written for one reader who is not the maintainer: the
operator of a duplicate, deciding whether the merge in front of them is one
they can take by merging. Everything held here is about that reader.

**The list of paths is derived, so the page cannot be checked against
itself.** Both sides of `--check` come out of the same generator, so a
generator that read half the declaration would agree with a block holding
half the declaration and report success.
`test_the_block_names_every_path_the_declaration_hands_over` reads
`declarations/boundary.yml` through the boundary reader in this module and
requires a line for each of them.

**The entries are not derived, and the rules on them are what stands in for
that.** A release note is prose somebody writes at the end of a long day.
The three states that make it useless -- an entry with no section for the
duplicate, an entry naming a path the duplicate does not own, a version
that disagrees with the one the package declares -- are the three `problems`
refuses, and each is exercised below on a page written here rather than on
this repository's own, so that proving the refusal works does not require
breaking the page.

**The check does not repair.** A mode that rewrote the file it was checking
would report success on a repository whose changelog still said something
else.
"""

from __future__ import annotations

import pytest
from generate_changelog import (
    _BEGIN,
    _END,
    COMMAND,
    DOC_PATH,
    HAND_EDITED,
    MERGE_HEADING,
    VERSION_PATH,
    changelog,
    declared_version,
    hand_edited_for,
    main,
    named_paths,
    owned,
    problems,
    render_block,
    sections,
    splice,
    tracked_files,
)

from convener_ops.declaration.boundary import INSTANCE, load
from convener_ops.declaration.paths import repo_root

ROOT = repo_root()


#: A page with the shape this one has and none of its content. Everything
#: about an entry is exercised against this rather than against the real
#: changelog, so that a test about a missing section does not need the real
#: page to be missing one.
def _page(entries: str) -> str:
    return f"# Changelog\n\n{_BEGIN}\nnothing yet\n{_END}\n\n{entries}"


def _entry(version: str, date: str, merge: str | None) -> str:
    body = f"## {version} — {date}\n\nSomething changed.\n"
    if merge is not None:
        body += f"\n{MERGE_HEADING}\n\n{merge}\n"
    return body


# ------------------------------------------------------------------ #
# The derived half.
# ------------------------------------------------------------------ #


def test_the_block_names_every_path_the_declaration_hands_over() -> None:
    """Read from the declaration here, not from the generator, so that a
    generator reading half the boundary cannot agree with itself."""
    board = load(ROOT)
    page = (ROOT / DOC_PATH).read_text(encoding="utf-8")
    block = page.split(_BEGIN, 1)[1].split(_END, 1)[0]
    missing = [path for path in board.instance_paths if f"`{path}`" not in block]
    assert missing == [], (
        f"{DOC_PATH.as_posix()}'s generated block names none of {missing}, "
        "which the declaration hands to the instance -- a duplicate reading "
        "that block would believe those paths are upstream's to change"
    )


def test_the_block_names_every_product_file_a_duplicate_types_into() -> None:
    """The other half of the same list, and the half no declaration
    carries: a duplicate's copy of each of these differs from upstream's by
    a value it entered, so a release changing one arrives at that edit."""
    page = (ROOT / DOC_PATH).read_text(encoding="utf-8")
    block = page.split(_BEGIN, 1)[1].split(_END, 1)[0]
    for path in HAND_EDITED:
        assert f"`{path}`" in block, (
            f"{DOC_PATH.as_posix()}'s generated block does not name {path}"
        )


def test_the_hand_edited_list_is_held_against_the_repository() -> None:
    """A list of three paths typed into a generator is exactly the shape
    that outlives what it was written for. Both directions are refused: a
    path this repository does not track, and a path the declaration has
    since handed to the instance, which would put it in the derived list
    above and name it twice."""
    board = load(ROOT)
    tracked = tracked_files(ROOT)
    assert hand_edited_for(tracked, board) == dict(HAND_EDITED)

    with pytest.raises(ValueError, match="does not track"):
        hand_edited_for(
            tuple(name for name in tracked if name != ".github/CODEOWNERS"), board
        )


def test_the_rendering_is_exercised_on_a_declaration_written_here() -> None:
    """Pure, and taking everything it prints as an argument, so a block can
    be rendered for a repository nobody has to create."""
    block = render_block(
        ("made-up/", "invented.yml"),
        {"product/typed.toml": "one value nobody can derive."},
        ("made-up/README.md",),
        ("invented.yml",),
    )
    assert "`made-up/`" in block
    assert "`invented.yml`" in block
    assert "rewritten in full by your own next push" in block
    assert "`product/typed.toml`" in block
    assert "one value nobody can derive" in block
    assert "`made-up/README.md`" in block


def test_a_missing_marker_raises_rather_than_passing() -> None:
    """A check comparing a page with itself reports success on a page with
    nowhere left to write."""
    with pytest.raises(ValueError, match="markers not found"):
        splice("# Changelog\n\nno markers here\n", "anything")


def test_the_page_carries_the_command_that_writes_it() -> None:
    """A generated block that does not say what regenerates it is one the
    next reader edits by hand."""
    page = (ROOT / DOC_PATH).read_text(encoding="utf-8")
    assert COMMAND in page


# ------------------------------------------------------------------ #
# The half nothing generates.
# ------------------------------------------------------------------ #


def test_a_release_heading_is_read_and_a_mistyped_one_is_refused() -> None:
    """A `## ` heading opening with a digit is meant to be a release, so
    one that does not parse is a failure rather than a paragraph: read as
    prose, a mistyped version is an entry no reader is ever shown."""
    text = _page(_entry("1.2.3", "2026-01-01", "Nothing."))
    assert [version for version, _date, _body in sections(text)] == ["1.2.3"]

    with pytest.raises(ValueError, match="opens with a digit"):
        sections(_page("## 1.2 — 2026-01-01\n\nSomething.\n"))


def test_an_entry_without_a_section_for_a_duplicate_is_refused() -> None:
    """An operator has no way to tell a silence from an omission, so the
    section is required even of an entry whose answer is that there is
    nothing to do."""
    board = load(ROOT)
    text = _page(_entry(declared_version(ROOT), "2026-01-01", None))
    found = problems(text, ROOT, board)
    assert any(MERGE_HEADING in problem for problem in found), found


def test_an_entry_naming_a_product_path_for_a_duplicate_is_refused() -> None:
    """That section is what an operator acts on, so a product path in it is
    a false alarm sent to every duplicate at once."""
    board = load(ROOT)
    text = _page(
        _entry(
            declared_version(ROOT),
            "2026-01-01",
            "- `app/src/main.tsx` moved, so edit yours.",
        )
    )
    found = problems(text, ROOT, board)
    assert any("app/src/main.tsx" in problem for problem in found), found


def test_an_instance_path_in_that_section_is_accepted() -> None:
    """The other direction, and the one that proves the clause above is
    reading rather than refusing everything."""
    board = load(ROOT)
    text = _page(
        _entry(
            declared_version(ROOT),
            "2026-01-01",
            "- `instance/config.json` gained a key. Copy it across.",
        )
    )
    assert problems(text, ROOT, board) == []
    assert owned("instance/config.json", board)
    assert owned("instance/data/config.yml", board)
    assert owned(".github/CODEOWNERS", board)
    assert not owned("app/src/main.tsx", board)


def test_only_the_duplicates_own_section_is_read() -> None:
    """The rest of an entry names product paths on purpose, because that is
    what most of a release is."""
    body = (
        "Something in `app/src/main.tsx` changed.\n\n"
        f"{MERGE_HEADING}\n\n- `instance/config.json` gained a key.\n"
    )
    assert named_paths(body) == ["instance/config.json"]


def test_versions_descend_and_do_not_repeat() -> None:
    board = load(ROOT)
    newest = declared_version(ROOT)
    text = _page(
        _entry("0.9.0", "2026-01-01", "Nothing.")
        + "\n"
        + _entry(newest, "2026-02-01", "Nothing.")
    )
    found = problems(text, ROOT, board)
    assert any("strictly descending" in problem for problem in found), found


def test_the_newest_entry_names_the_version_the_package_declares() -> None:
    """One number, in one place. A release that bumps the package and
    forgets the page names two states and neither is checkable."""
    board = load(ROOT)
    text = _page(_entry("99.0.0", "2026-01-01", "Nothing."))
    found = problems(text, ROOT, board)
    assert any(VERSION_PATH.as_posix() in problem for problem in found), found


def test_a_page_with_no_entry_at_all_is_refused() -> None:
    """Non-vacuity: every rule above reads the entries, so a page that lost
    them would pass the lot by having nothing to check."""
    board = load(ROOT)
    found = problems(_page(""), ROOT, board)
    assert any("no release entry" in problem for problem in found), found


# ------------------------------------------------------------------ #
# The command, and the real page.
# ------------------------------------------------------------------ #


def test_the_committed_page_is_what_this_repository_derives() -> None:
    assert (ROOT / DOC_PATH).read_text(encoding="utf-8") == changelog(ROOT)
    assert problems(changelog(ROOT), ROOT, load(ROOT)) == []
    assert main(["--check"]) == 0


def test_the_declared_version_is_the_one_the_newest_entry_names() -> None:
    version = declared_version(ROOT)
    assert sections((ROOT / DOC_PATH).read_text(encoding="utf-8"))[0][0] == version


def test_every_instance_path_the_declaration_names_is_owned() -> None:
    """`owned` is the clause the entries are held against, so it is asked
    of the declaration rather than of a list written here."""
    board = load(ROOT)
    for path in board.instance_paths:
        assert board.owner_of(path) == INSTANCE
        assert owned(path, board)
