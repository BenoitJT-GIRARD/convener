"""The commit range the CI check reads, exercised against a real repository.

`log_range` returns arguments for `git log`, so asserting on the string it
builds would only restate the function. What has to hold is what those
arguments *select*: the commits under review, and never none of them.

The failure this module exists for is silent. Checking too few commits is the
safe direction and was chosen deliberately, but a range that resolves to
nothing is the same safe direction taken all the way: `convener-check-commits`
reads an empty stream, reports zero messages OK, and the job goes green having
verified nothing. So every test below counts the commits that come back, and
counts them against a repository built here rather than against a fixture.

No network: the repository is created in `tmp_path` with `git init` and three
local commits.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404
from pathlib import Path

import pytest

from convener_ops.declaration.paths import repo_root
from convener_ops.governance import commit_format
from convener_ops.governance.commit_format import (
    FIRST_PARENT,
    NO_PARENT,
    commit_range,
    local_start,
    log_range,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not on PATH"
)

SUBJECTS = [
    "ops: define the grammar of decision commits",
    "docs: state what the register may not say",
    "ci: check the commits under review",
]


def _git(repo: Path, *args: str) -> str:
    """One git invocation in `repo`. Fixed argv, no shell."""
    result = subprocess.run(  # nosec B603 B607
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout


@pytest.fixture
def history(tmp_path: Path) -> list[str]:
    """A repository with three commits; returns their names, oldest first."""
    _git(tmp_path, "init", "--quiet", "--initial-branch=main")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "user.email", "test@example.org")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    names = []
    for n, subject in enumerate(SUBJECTS):
        (tmp_path / f"file-{n}.txt").write_text(str(n), encoding="utf-8")
        _git(tmp_path, "add", f"file-{n}.txt")
        _git(tmp_path, "commit", "--quiet", "-m", subject)
        names.append(_git(tmp_path, "rev-parse", "HEAD").strip())
    return names


def selected(repo: Path, arguments: list[str]) -> list[str]:
    """The subjects `git log` returns for these arguments, as the job reads
    them: one stream, split on the NUL the format inserts."""
    raw = _git(repo, "log", "--format=%B%x00", *arguments)
    return [
        part.strip("\n").splitlines()[0] for part in raw.split("\0") if part.strip()
    ]


def test_a_pull_request_selects_every_commit_it_adds_to_its_base(
    tmp_path: Path, history: list[str]
) -> None:
    first, _, head = history

    arguments = log_range(base=first, before="", head=head)

    assert selected(tmp_path, arguments) == SUBJECTS[1:][::-1]


def test_a_push_selects_every_commit_it_moved_the_branch_by(
    tmp_path: Path, history: list[str]
) -> None:
    """`before` is used when there is no pull request to give a base."""
    first, _, head = history

    arguments = log_range(base="", before=first, head=head)

    assert selected(tmp_path, arguments) == SUBJECTS[1:][::-1]


def test_the_base_wins_when_a_pull_request_supplies_both(
    tmp_path: Path, history: list[str]
) -> None:
    first, second, head = history

    arguments = log_range(base=first, before=second, head=head)

    assert selected(tmp_path, arguments) == SUBJECTS[1:][::-1]


@pytest.mark.parametrize("before", ["", "   ", NO_PARENT])
def test_a_first_push_still_reads_one_commit_and_never_none(
    tmp_path: Path, history: list[str], before: str
) -> None:
    """The regression this module is really for.

    A branch pushed for the first time has no `before` -- GitHub sends the
    all-zero name, and a locally-run job may send nothing at all. Neither
    names a commit, so neither can be subtracted from the head. Getting this
    wrong does not produce an error: `<zeros>..<head>` and `..<head>` both
    make git return nothing, and the check passes having read no message.
    """
    head = history[-1]

    arguments = log_range(base="", before=before, head=head)

    assert selected(tmp_path, arguments) == SUBJECTS[-1:]


def test_no_shape_of_the_range_ever_selects_nothing(
    tmp_path: Path, history: list[str]
) -> None:
    """Stated once, over every combination, as the property it is."""
    first, second, head = history
    starts = ["", "   ", NO_PARENT, first, second]

    for base in starts:
        for before in starts:
            arguments = log_range(base=base, before=before, head=head)
            assert selected(tmp_path, arguments), f"empty for {base!r}/{before!r}"


def test_an_absent_head_falls_back_to_the_checked_out_commit(
    tmp_path: Path, history: list[str]
) -> None:
    """`HEAD` is a commit; the empty string is a syntax error waiting to be
    word-split away by the shell."""
    arguments = log_range(base="", before="", head="")

    assert selected(tmp_path, arguments) == SUBJECTS[-1:]


def test_the_entry_point_prints_one_line_the_shell_can_expand(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("BASE", "aaaa111")
    monkeypatch.setenv("BEFORE", "bbbb222")
    monkeypatch.setenv("HEAD", "cccc333")

    assert commit_range() == 0

    out = capsys.readouterr().out
    assert out == "--first-parent aaaa111..cccc333\n"
    out.encode("ascii")


def test_the_entry_point_reads_an_environment_that_says_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no event *and* no upstream to fall back on, the head alone --
    the one case `log_range`'s own fallback was written for."""
    for name in ("BASE", "BEFORE", "HEAD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(commit_format, "local_start", lambda: "")

    assert commit_range() == 0

    assert capsys.readouterr().out.split() == ["--first-parent", "-1", "HEAD"]


def test_the_entry_point_reads_the_branch_upstream_when_there_is_no_event(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The second half of the defect, as the entry point sees it.

    `gates.sh` runs this command with no GitHub event, took `log_range`'s
    first-push fallback, and so checked one commit while the push it was
    verifying checked thirty-six. A local run has the branch's own upstream
    available and that is what the push will be measured against.
    """
    for name in ("BASE", "BEFORE", "HEAD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(commit_format, "local_start", lambda: "@{u}")

    assert commit_range() == 0

    assert capsys.readouterr().out.split() == ["--first-parent", "@{u}..HEAD"]


def test_an_event_is_never_overridden_by_the_repository(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run that *has* an event reads it, and nothing local may displace
    it: in CI `@{u}` is whatever the checkout happens to track, which is not
    the push's own boundary."""
    monkeypatch.setenv("BEFORE", "bbbb222")
    monkeypatch.setenv("HEAD", "cccc333")
    monkeypatch.delenv("BASE", raising=False)
    monkeypatch.setattr(
        commit_format,
        "local_start",
        lambda: pytest.fail("an event was present and the repository was asked anyway"),
    )

    assert commit_range() == 0

    assert capsys.readouterr().out.split() == ["--first-parent", "bbbb222..cccc333"]


def test_local_start_prefers_the_upstream_then_the_default_branch() -> None:
    """Order, stated as the property it is. The upstream is what the next
    push is measured against; `origin/HEAD` answers for a branch that has
    never been pushed, and selects what a pull request from it would."""
    assert local_start(adds_commits=lambda name: True) == "@{u}"
    assert local_start(adds_commits=lambda name: name == "origin/HEAD") == "origin/HEAD"
    assert local_start(adds_commits=lambda name: False) == ""


def test_a_starting_point_that_selects_nothing_is_not_offered() -> None:
    """The failure an earlier draft of this fix introduced, and the one this
    whole module exists for.

    On a branch with no commits of its own -- a branch just created, which is
    the ordinary state when somebody runs `gates.sh` before committing --
    `origin/HEAD` exists and `origin/HEAD..HEAD` is empty.
    `convener-check-commits` then reads an empty stream, prints "0 commit
    message(s) OK" and the gate goes green having verified nothing. Measured
    exactly that way before this assertion existed.

    So each candidate is asked whether it *selects* anything, not whether it
    exists, and a branch that adds nothing falls back to `-1 HEAD`: one real
    commit, never none.
    """
    assert local_start(adds_commits=lambda name: False) == ""

    arguments = log_range(base="", before="", head="")

    assert arguments == [FIRST_PARENT, "-1", "HEAD"]


def test_the_real_predicate_rejects_an_unknown_ref_and_an_empty_range(
    tmp_path: Path, history: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_adds_commits` against a real repository, both ways it says no.

    Driven here rather than mocked, because what it actually relies on is
    `git rev-list`'s own two behaviours: a non-zero exit for a ref that does
    not exist, and a count of zero for one that exists and adds nothing.
    """
    monkeypatch.chdir(tmp_path)

    assert commit_format._adds_commits("no-such-ref") is False
    assert commit_format._adds_commits("HEAD") is False, (
        "HEAD..HEAD adds nothing, and a predicate that said otherwise would "
        "offer a range selecting no commit"
    )
    assert commit_format._adds_commits(history[0]) is True


def test_a_merge_puts_only_this_branch_own_commits_under_review(
    tmp_path: Path, history: list[str]
) -> None:
    """The first half of the defect, measured on a real merge.

    An instance taking a release merges the product's history into its own.
    Without `--first-parent` every commit of that release lands in the
    instance's own range -- and the first one that fails the grammar turns
    *its* `Quality` red for something it did not write. It happened: a
    Dependabot commit carrying `Co-authored-by:` reached
    `TheBehaviourForum/vws-cockpit` through a merge and failed there, having
    never been judged where it was written.
    """
    _git(tmp_path, "checkout", "--quiet", "-b", "upstream-side", history[0])
    (tmp_path / "theirs.txt").write_text("theirs", encoding="utf-8")
    _git(tmp_path, "add", "theirs.txt")
    _git(
        tmp_path,
        "commit",
        "--quiet",
        "-m",
        "\n".join(
            [
                "chore: a commit the other repository wrote",
                "",
                "Co-authored-by: someone <s@example.org>",
            ]
        ),
    )
    _git(tmp_path, "checkout", "--quiet", "main")
    start = _git(tmp_path, "rev-parse", "HEAD").strip()
    _git(
        tmp_path,
        "merge",
        "--quiet",
        "--no-ff",
        "-m",
        "ops: take their work",
        "upstream-side",
    )

    arguments = log_range(base="", before=start, head="HEAD")
    subjects = selected(tmp_path, arguments)

    assert subjects == ["ops: take their work"], (
        "the merged branch's own commits are under this branch's grammar "
        "check, which is the defect"
    )
    # The merge commit itself stays under review -- it is this branch's.
    assert selected(tmp_path, log_range("", start, "HEAD"))


def test_the_workflow_computes_the_range_with_this_function() -> None:
    """The extraction is only worth having while the workflow uses it."""
    workflow = (repo_root() / ".github" / "workflows" / "quality.yml").read_text(
        encoding="utf-8"
    )

    assert "uv run --frozen convener-commit-range" in workflow
    assert "$from..$HEAD" not in workflow


def _check_commits_options(text: str) -> list[str]:
    """Every `git log` option spelled literally on the line that feeds
    `convener-check-commits`, in the order written."""
    for line in text.splitlines():
        if "git log" in line and "convener-check-commits" in line:
            after = line.split("git log", 1)[1]
            return [
                token
                for token in after.split("|", 1)[0].split()
                if token.startswith("-")
            ]
    raise AssertionError("no line feeds convener-check-commits")


def test_the_two_callers_ask_git_log_the_same_question() -> None:
    """The half of this defect that cost a duplicate a red run.

    `gates.sh` opens by promising it is "every gate `quality.yml` runs, one
    target each", so that "a gate that passes by hand passes here and the two
    cannot drift into different checks". For this check they drifted: the
    local gate read one commit where the push it was verifying read
    thirty-six, and reported green.

    The fix is that neither file names a `git log` option of its own -- every
    one of them, `--first-parent` included, comes from
    `convener-commit-range`, so there is one place to get right rather than
    two that have to agree. This reads both files for that, because an option
    added to one and not the other is exactly how the drift happened.
    """
    root = repo_root()
    workflow = _check_commits_options(
        (root / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")
    )
    gates = _check_commits_options((root / "gates.sh").read_text(encoding="utf-8"))

    assert workflow == gates, (
        f"quality.yml passes {workflow} and gates.sh passes {gates} -- an "
        "option in one and not the other is a gate answering a different "
        "question from the one it promises to run"
    )
    assert workflow == ["--format=%B%x00"], (
        f"{workflow} names a revision-selecting option by hand; every one of "
        "them belongs in `log_range`, where both callers inherit it"
    )


def test_the_options_that_select_commits_come_from_the_function() -> None:
    """Non-vacuity for the assertion above, which would also pass if nobody
    selected commits at all."""
    assert FIRST_PARENT in log_range("aaa", "", "bbb")
    assert FIRST_PARENT in log_range("", "", "")
