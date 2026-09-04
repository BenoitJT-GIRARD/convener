"""The index of the numbered governance rules, and what keeps it honest.

Fifteen rules carried a number and no page listed them.
`docs/handbook/governance/board-rules.md` said "a few of the numbered rules
are written on other pages" and named none of them, three of the fifteen were
stated somewhere else entirely, and two numbers in the middle of the sequence
were numbers nobody could account for.
`tools/scripts/generate_rule_index.py` derives the list that replaces that
sentence, and this module holds the halves that make it stick.

**The sequence is measured here, not read.** Both sides of `--check` come out
of the same generator, so a generator that saw half the pages would agree
with an index of half the pages and report success.
`test_the_rules_this_repository_states_are_a_continuous_ascending_sequence`
reads the real pages in this module and requires the numbers to be `G-01`
upwards with nothing missing, which is the property the numbering did not
have and nothing could have said so.

**The check does not repair.** A mode that rewrote the page it was checking
would report success on a repository whose index was already wrong.

**The rendering and the refusals are exercised on a documentation tree
written here**, so a test about a rule stated on two pages, or about a rule
inserted in the middle of the walk, does not need this repository to hold
one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from generate_rule_index import (
    _BEGIN,
    _END,
    COMMAND,
    DOC_PATH,
    RETIRED,
    Rule,
    declarations_in,
    declared_rule_ids,
    held,
    main,
    render_block,
    rule_index,
    rules_in_walk_order,
    sequence_for,
    splice,
    title_of,
    tree_order,
)

from convener_ops.declaration.paths import repo_root

ROOT = repo_root()

#: The heading the generated block sits under on the real page.
HEADING = "## The numbered rules, and where each one is stated"

#: The numbers a four-rule tree carries, given this repository's own
#: withdrawals, and the number a fifth rule would take. Derived rather than
#: written out: retiring a rule moves the sequence, and a fixture holding
#: the numbers it carried before that withdrawal would fail as a
#: contradiction with `RETIRED` rather than as a defect in the walk.
FAKE_RULES = sequence_for(4, RETIRED)
FAKE_NEXT = sequence_for(5, RETIRED)[4]

#: A documentation tree with this repository's shape and none of its
#: content: a front page naming three trees, and one page per tree stating
#: rules. Written out rather than read off the real `docs/`, so the tests
#: below keep meaning what they say when this repository writes a rule.
FRONT_PAGE = """# Documentation, by reader

| tree | written for |
|---|---|
| [`handbook/`](handbook/index.md) | a volunteer running a webinar |
| [`operating/`](operating/index.md) | the operator |
| [`engineering/`](engineering/index.md) | somebody changing this code |
"""

#: `docs/handbook/governance/board-rules.md` as the script sees it: prose,
#: two rules, the two markers, and prose again. Nothing outside them may
#: move.
SKELETON = f"""# The Board's rules

Prose the generator never touches.

## The bar ({FAKE_RULES[0]})

Two thirds, rounded up.

**Declaring an absence ({FAKE_RULES[1]})** is something you do for yourself.

{HEADING}

{_BEGIN}
{_END}

Prose after it, equally untouched.
"""

#: The operator's manual, holding the third rule of the walk.
OPERATIONS = f"""# Operations

## Inactivity ({FAKE_RULES[2]})

A member who has cast no ballot for twelve months.
"""

#: The engineering reference, holding the fourth.
ARCHITECTURE = f"""# Architecture

- **Handover ({FAKE_RULES[3]}).** The role is transferable.
"""


def write_tree(root: Path) -> None:
    """The four pages above, at the paths the walk reads them from."""
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "README.md").write_text(FRONT_PAGE, encoding="utf-8", newline="")
    (root / DOC_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / DOC_PATH).write_text(SKELETON, encoding="utf-8", newline="")
    for relative, text in (
        (Path("docs") / "operating" / "operations.md", OPERATIONS),
        (Path("docs") / "engineering" / "architecture.md", ARCHITECTURE),
    ):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text, encoding="utf-8", newline="")


@pytest.fixture
def fake_docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository holding those four pages and an unfilled index."""
    write_tree(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    return tmp_path


# --------------------------------------------------------------------------
# The sequence, measured on the real pages
# --------------------------------------------------------------------------


def test_the_walk_reads_this_repository_and_finds_its_rules() -> None:
    """A walk that found nothing would make every check below vacuous."""
    rules = rules_in_walk_order(ROOT)

    assert len(rules) >= 10, (
        f"the walk of docs/ found {len(rules)} numbered rules, which is not "
        "this repository -- either it is reading somewhere else or the rules "
        "stopped being titled with their numbers"
    )
    assert rules[0].number == "G-01"
    assert rules[0].page == "docs/handbook/governance/board-rules.md"


def test_the_rules_this_repository_states_are_a_continuous_ascending_sequence() -> None:
    """The property this numbering did not have, held by measurement.

    Two numbers in the middle of the sequence were stated by no page, cited
    by no file and retired by no declaration. This reads the pages directly
    rather than through
    the generated block, so an index that agreed with a holed sequence would
    still fail here.
    """
    numbers = [rule.number for rule in rules_in_walk_order(ROOT)]

    assert numbers == list(sequence_for(len(numbers), RETIRED)), (
        f"the rules this repository states carry {numbers}, which is not "
        "G-01 upwards with the retired numbers skipped"
    )
    assert numbers == sorted(numbers), "the numbers do not ascend along the walk"


def test_the_numbers_this_repository_withdrew_are_stated_by_nothing() -> None:
    """The withdrawal rule, measured on the real pages rather than on a tree
    written here. A number `RETIRED` declares and a page still titles is a
    contradiction `held` refuses; this is the same reading taken directly,
    so it fails on the commit that puts the number back on a page.
    """
    stated = {rule.number for rule in rules_in_walk_order(ROOT)}

    for number in RETIRED:
        assert number not in stated, (
            f"{number} is declared retired and a page still states it -- "
            "either the entry goes or the title does"
        )
        assert RETIRED[number].strip(), f"{number} is retired with no reason"


def test_every_rule_the_index_carries_is_stated_by_one_page() -> None:
    """The *stated in* column has one answer per rule, and it is a real
    page a reader can open."""
    for rule in rules_in_walk_order(ROOT):
        assert (ROOT / rule.page).is_file(), f"{rule.number} names {rule.page}"
        assert rule.title, f"{rule.number} has no title on {rule.page}"


def test_the_index_names_the_pages_outside_the_main_one() -> None:
    """What the sentence this index replaces would not say: which rules are
    written somewhere other than the Board's own page."""
    main_page = DOC_PATH.as_posix()
    elsewhere = {
        rule.page for rule in rules_in_walk_order(ROOT) if rule.page != main_page
    }

    assert len(elsewhere) >= 3, (
        f"the rules outside {DOC_PATH.as_posix()} are stated on {elsewhere}, "
        "and this index exists because that set is not empty"
    )


# --------------------------------------------------------------------------
# What a page does when it states a rule
# --------------------------------------------------------------------------


def test_a_heading_and_a_bold_lead_both_state_a_rule() -> None:
    assert declared_rule_ids("## Inactivity (G-14)") == {"G-14"}
    assert declared_rule_ids("**Declaring an absence (G-06)** is yours.") == {"G-06"}
    assert declared_rule_ids("- **Diversity (G-11).** A deliberate aim") == {"G-11"}


def test_a_citation_does_not_state_a_rule() -> None:
    """Without this the index would list a rule because a comment quoted
    it."""
    assert declared_rule_ids("| `inactivity_months` | ... (G-14). |") == set()
    assert declared_rule_ids("G-16 says the role is transferable") == set()
    assert declared_rule_ids("The second gate (G-07, G-08): what has to be") == set()


def test_the_title_is_the_page_s_own_name_for_the_rule() -> None:
    assert title_of("### The bar (G-01)") == "The bar"
    assert title_of("- **Diversity (G-11).**") == "Diversity"
    assert title_of("**Declaring an absence (G-06)**") == "Declaring an absence"


def test_a_page_is_read_in_the_order_it_is_written() -> None:
    offsets = [offset for offset, _, _ in declarations_in(SKELETON)]

    assert offsets == sorted(offsets)
    assert [number for _, number, _ in declarations_in(SKELETON)] == list(
        FAKE_RULES[:2]
    )


# --------------------------------------------------------------------------
# The order the numbering follows
# --------------------------------------------------------------------------


def test_the_tree_order_is_read_from_the_documentation_s_front_page() -> None:
    assert tree_order(FRONT_PAGE) == ("handbook", "operating", "engineering")
    assert tree_order((ROOT / "docs" / "README.md").read_text(encoding="utf-8")) == (
        "handbook",
        "operating",
        "engineering",
    )


def test_a_front_page_with_no_table_of_trees_is_refused() -> None:
    """An empty order would put every rule outside the walk at once."""
    with pytest.raises(ValueError, match="no tree is listed"):
        tree_order("# Documentation\n\nThree trees, and no table.\n")


def test_the_walk_follows_the_trees_then_the_paths(fake_docs: Path) -> None:
    walked = rules_in_walk_order(fake_docs)

    assert [rule.page for rule in walked] == [
        DOC_PATH.as_posix(),
        DOC_PATH.as_posix(),
        "docs/operating/operations.md",
        "docs/engineering/architecture.md",
    ]


def test_a_tree_the_front_page_names_and_the_repository_lacks_is_refused(
    fake_docs: Path,
) -> None:
    """A walk that skipped it would number the other two and say nothing."""
    for path in sorted((fake_docs / "docs" / "operating").glob("*.md")):
        path.unlink()
    (fake_docs / "docs" / "operating").rmdir()

    with pytest.raises(ValueError, match="is not a directory"):
        rules_in_walk_order(fake_docs)


def test_a_rule_stated_outside_the_three_trees_is_refused(fake_docs: Path) -> None:
    """The walk has nowhere to put it, so it says so instead of dropping
    it."""
    (fake_docs / "docs" / "README.md").write_text(
        FRONT_PAGE + f"\n## A stray rule ({FAKE_NEXT})\n",
        encoding="utf-8",
        newline="",
    )

    with pytest.raises(ValueError, match=r"docs/README\.md"):
        rules_in_walk_order(fake_docs)


def test_a_rule_two_pages_state_is_refused(fake_docs: Path) -> None:
    """The one case this repository held: inactivity, titled on the Board's
    page and on the operator's manual, with the first deferring to the
    second in its own last sentence."""
    page = fake_docs / "docs" / "engineering" / "architecture.md"
    page.write_text(
        ARCHITECTURE + f"\n## Inactivity ({FAKE_RULES[2]})\n",
        encoding="utf-8",
        newline="",
    )

    with pytest.raises(ValueError) as raised:
        rules_in_walk_order(fake_docs)

    assert f"{FAKE_RULES[2]} on docs/operating/operations.md" in str(raised.value)


# --------------------------------------------------------------------------
# Continuity, and what a withdrawal does to it
# --------------------------------------------------------------------------


def test_the_sequence_is_the_numbers_no_withdrawal_has_taken() -> None:
    assert sequence_for(4, {}) == ("G-01", "G-02", "G-03", "G-04")
    assert sequence_for(3, {"G-02": "gone"}) == ("G-01", "G-03", "G-04")


def test_a_retired_number_leaves_the_rules_after_it_where_they_were() -> None:
    """Why a withdrawal declares rather than renumbers: the rules that did
    not change keep the numbers they had."""
    before = sequence_for(4, {})
    after = sequence_for(3, {"G-02": "gone"})

    assert after == (before[0], before[2], before[3])


def test_a_gap_nothing_declared_is_refused() -> None:
    rules = (
        Rule("G-01", "The bar", "docs/handbook/governance/board-rules.md"),
        Rule("G-03", "Inactivity", "docs/operating/operations.md"),
    )

    with pytest.raises(ValueError) as raised:
        held(rules, {})

    assert "rule 2 is G-03" in str(raised.value)
    assert "reaches G-02" in str(raised.value)


def test_a_gap_a_withdrawal_declared_is_accepted() -> None:
    rules = (
        Rule("G-01", "The bar", "docs/handbook/governance/board-rules.md"),
        Rule("G-03", "Inactivity", "docs/operating/operations.md"),
    )

    assert held(rules, {"G-02": "The old quorum rule, withdrawn on 2026-09-04."})


def test_a_number_both_stated_and_retired_is_refused() -> None:
    """One of the two is describing a rule that is not there."""
    rules = (Rule("G-01", "The bar", "docs/handbook/governance/board-rules.md"),)

    with pytest.raises(ValueError) as raised:
        held(rules, {"G-01": "Withdrawn."})

    assert "G-01 is declared retired" in str(raised.value)


def test_two_rules_out_of_the_walk_s_order_are_refused() -> None:
    """The same comparison catches a pair whose numbers descend."""
    rules = (
        Rule("G-02", "The bar", "docs/handbook/governance/board-rules.md"),
        Rule("G-01", "Inactivity", "docs/operating/operations.md"),
    )

    with pytest.raises(ValueError, match="rule 1 is G-02"):
        held(rules, {})


# --------------------------------------------------------------------------
# The block
# --------------------------------------------------------------------------


def test_the_block_names_every_rule_and_its_page() -> None:
    block = render_block(
        (Rule("G-01", "The bar", "docs/handbook/governance/board-rules.md"),), {}
    )

    assert "| Rule | What it is | Stated in |" in block
    assert "| G-01 | The bar | `docs/handbook/governance/board-rules.md` |" in block


def test_the_block_carries_the_retired_numbers() -> None:
    block = render_block(
        (Rule("G-01", "The bar", "docs/handbook/governance/board-rules.md"),),
        {"G-02": "The old quorum rule, withdrawn on 2026-09-04."},
    )

    assert "**G-02**" in block
    assert "withdrawn on 2026-09-04" in block


def test_the_block_says_nothing_about_retirement_when_there_is_none() -> None:
    block = render_block(
        (Rule("G-01", "The bar", "docs/handbook/governance/board-rules.md"),), {}
    )

    assert "no rule carries any more" not in block


def test_nothing_outside_the_markers_moves() -> None:
    spliced = splice(SKELETON, "replaced\n")

    assert spliced.startswith("# The Board's rules\n\nProse the generator")
    assert spliced.endswith("Prose after it, equally untouched.\n")
    assert "replaced" in spliced


def test_a_missing_marker_raises_rather_than_leaving_the_page_alone() -> None:
    """A silent no-op would make `--check` compare the page with itself."""
    with pytest.raises(ValueError, match="markers not found"):
        splice("# The Board's rules\n", "replaced\n")


# --------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------


def test_writing_then_checking_passes(
    fake_docs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([]) == 0
    assert main(["--check"]) == 0
    assert "matches the rules the pages state" in capsys.readouterr().out


def test_a_second_write_changes_nothing_and_says_so(
    fake_docs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([]) == 0
    capsys.readouterr()
    assert main([]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_check_leaves_a_stale_page_exactly_as_it_found_it(
    fake_docs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A check that repairs is a green tick over the defect it exists for."""
    page = fake_docs / DOC_PATH
    before = page.read_text(encoding="utf-8")

    assert main(["--check"]) == 1
    assert page.read_text(encoding="utf-8") == before
    assert COMMAND in capsys.readouterr().err


def test_a_rule_written_on_another_page_fails_the_check(
    fake_docs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mutation this index exists for: a rule stated somewhere the main
    page does not name."""
    assert main([]) == 0
    page = fake_docs / "docs" / "engineering" / "schema.md"
    page.write_text(
        f"# Schema\n\n- **Diversity ({FAKE_NEXT}).** A deliberate aim.\n",
        encoding="utf-8",
        newline="",
    )

    assert main(["--check"]) == 1
    assert COMMAND in capsys.readouterr().err
    assert main([]) == 0
    block = (
        (fake_docs / DOC_PATH)
        .read_text(encoding="utf-8")
        .partition(_BEGIN)[2]
        .partition(_END)[0]
    )
    assert f"| {FAKE_NEXT} | Diversity | `docs/engineering/schema.md` |" in block


def test_a_rule_inserted_in_the_middle_of_the_walk_fails_the_check(
    fake_docs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What the numbering rule costs, as a red build rather than as
    something somebody remembers: the rules after it have to move up."""
    assert main([]) == 0
    page = fake_docs / DOC_PATH
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            f"## The bar ({FAKE_RULES[0]})",
            f"## A prior rule ({FAKE_NEXT})\n\n## The bar ({FAKE_RULES[0]})",
        ),
        encoding="utf-8",
        newline="",
    )

    assert main(["--check"]) == 1
    assert f"rule 1 is {FAKE_NEXT}" in capsys.readouterr().err


def test_a_rule_taken_off_its_page_without_a_retirement_fails_the_check(
    fake_docs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half of the withdrawal rule: a rule that goes and leaves a
    hole nothing declares."""
    assert main([]) == 0
    page = fake_docs / "docs" / "operating" / "operations.md"
    page.write_text(
        page.read_text(encoding="utf-8").replace(f" ({FAKE_RULES[2]})", ""),
        encoding="utf-8",
        newline="",
    )

    assert main(["--check"]) == 1
    assert f"rule 3 is {FAKE_RULES[3]}" in capsys.readouterr().err


def test_a_documentation_tree_with_no_rule_at_all_is_refused(
    fake_docs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An index of nothing would pass every check it is compared against."""
    for relative in (
        DOC_PATH,
        Path("docs") / "operating" / "operations.md",
        Path("docs") / "engineering" / "architecture.md",
    ):
        page = fake_docs / relative
        page.write_text(
            page.read_text(encoding="utf-8")
            .replace(f" ({FAKE_RULES[0]})", "")
            .replace(f" ({FAKE_RULES[1]})", "")
            .replace(f" ({FAKE_RULES[2]})", "")
            .replace(f" ({FAKE_RULES[3]})", ""),
            encoding="utf-8",
            newline="",
        )

    assert main([]) == 1
    assert "titles a section or a paragraph" in capsys.readouterr().err


def test_the_rendering_is_a_function_of_its_inputs_alone(fake_docs: Path) -> None:
    """Byte-identical over two runs, which is what makes `--check` a fact."""
    assert rule_index(fake_docs) == rule_index(fake_docs)


def test_the_terminal_output_is_ascii(
    fake_docs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The page is written in the handbook's English; the console is not."""
    main([])
    main(["--check"])
    captured = capsys.readouterr()
    (captured.out + captured.err).encode("ascii")


def test_the_real_page_carries_the_markers_and_the_heading() -> None:
    """The block has somewhere to go, and a reader has a heading to reach
    it by."""
    page = (ROOT / DOC_PATH).read_text(encoding="utf-8")

    assert HEADING in page
    assert _BEGIN in page and _END in page
