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
from convener_ops.governance.commit_format import NO_PARENT, commit_range, log_range

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
    assert out == "aaaa111..cccc333\n"
    out.encode("ascii")


def test_the_entry_point_reads_an_environment_that_says_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("BASE", "BEFORE", "HEAD"):
        monkeypatch.delenv(name, raising=False)

    assert commit_range() == 0

    assert capsys.readouterr().out.split() == ["-1", "HEAD"]


def test_the_workflow_computes_the_range_with_this_function() -> None:
    """The extraction is only worth having while the workflow uses it."""
    workflow = (repo_root() / ".github" / "workflows" / "quality.yml").read_text(
        encoding="utf-8"
    )

    assert "uv run convener-commit-range" in workflow
    assert "$from..$HEAD" not in workflow
