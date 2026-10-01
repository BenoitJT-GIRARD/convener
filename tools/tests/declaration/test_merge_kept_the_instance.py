"""A merge driver only runs on a conflict, and that is the hole this closes.

`declarations/boundary.yml` says of the instance's ledgers that "none of it
is a value upstream could ship correctly for anybody else", and
`.gitattributes` gives those paths the `ours` merge driver to enforce it.

It cannot. A merge driver runs **only when git has a conflict to resolve**.
A file that one side alone has changed has no conflict, so git takes that
side and never calls the driver — and when that side is upstream, the
instance silently inherits upstream's value while the declaration's rule
goes unapplied.

**Measured, not imagined.** On the instance this product was derived for,
three weeks with no Actions minutes froze every ledger its own jobs write
while the product's kept moving. The next merge carried three of them:

* `retention-last-run.yml` — makes the instance claim its retention sweep
  ran on a day it did not, which is a false assurance on the one record
  `check_retention_liveness` calls a promise with legal weight;
* `actions-usage.yml` — what the budget alarm reasons from, so it would
  have reasoned from the *product's* consumption rather than its own;
* `queue-watch.yml` — the record the queue watchdog calls stale when it
  stops moving.

Nothing about a lost allowance is needed to reach this. A duplicate that
takes two releases without its own jobs running in between has the same
hole, on an ordinary month.

The tests here come in two halves: the reading, driven against lists
somebody made up, and the command, driven against a real merge in a real
repository — because the reading being right proves nothing about whether
anything calls it.
"""

from __future__ import annotations

import subprocess  # nosec B404
from pathlib import Path

import pytest

from convener_ops.cli import maintenance
from convener_ops.declaration import boundary
from convener_ops.declaration.paths import repo_root

LEDGERS = (
    "instance/data/retention-last-run.yml",
    "instance/data/actions-usage.yml",
    "instance/data/queue-watch.yml",
)


@pytest.fixture
def board() -> boundary.Boundary:
    return boundary.load(repo_root())


# ------------------------------------------------------------------ #
# The reading.
# ------------------------------------------------------------------ #


def test_a_modified_ledger_is_reported(board: boundary.Boundary) -> None:
    """The three the merge actually carried."""
    changes = [("M", name) for name in LEDGERS]

    assert boundary.overwritten_by_a_merge(changes, board) == tuple(sorted(LEDGERS))


def test_a_removed_ledger_is_reported(board: boundary.Boundary) -> None:
    """Upstream deleting a file is the instance's record disappearing, which
    is the same loss by another route."""
    changes = [("D", "instance/data/retention-last-run.yml")]

    assert boundary.overwritten_by_a_merge(changes, board) == (
        "instance/data/retention-last-run.yml",
    )


def test_an_added_ledger_is_not_reported(board: boundary.Boundary) -> None:
    """The distinction this function exists to make.

    Upstream introducing a new ledger is how a duplicate ever gets the file
    at all, and its own jobs overwrite the value on their next run. A rule
    that refused additions would stop every new record from ever arriving.
    """
    changes = [("A", "instance/data/a-ledger-nobody-has-yet.yml")]

    assert boundary.overwritten_by_a_merge(changes, board) == ()


def test_a_rename_reports_where_the_content_landed(board: boundary.Boundary) -> None:
    """`git diff --name-status` gives a rename two paths. The destination is
    the one now holding the content, and the one a reader has to go and
    look at."""
    changes = [("R100", "instance/data/queue-watch.yml")]

    assert boundary.overwritten_by_a_merge(changes, board) == (
        "instance/data/queue-watch.yml",
    )


def test_the_product_s_own_files_are_not_reported(board: boundary.Boundary) -> None:
    """Non-vacuity in the direction that would be silent. A reading that
    flagged everything would make a descent impossible and be switched off
    within the week, taking the real rule with it."""
    changes = [
        ("M", "app/src/state/dates.ts"),
        ("M", "tools/convener_ops/cli/maintenance.py"),
        ("M", "docs/operating/taking-an-update.md"),
        # Declared `kept:` inside an instance path: it describes the
        # product's model, not this instance's records, so upstream's
        # version is the one to take.
        ("M", "instance/data/schema.md"),
    ]

    assert boundary.overwritten_by_a_merge(changes, board) == ()


# ------------------------------------------------------------------ #
# The command, against a real merge.
# ------------------------------------------------------------------ #


def _git(repo: Path, *arguments: str) -> None:
    subprocess.run(  # nosec B603 B607
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _instance_repository(tmp_path: Path) -> Path:
    """A repository shaped like a duplicate: the declaration, one ledger,
    and the `ours` driver configured exactly as a duplicate configures it.

    Small on purpose. What is being exercised is git's own behaviour over a
    merge, and the smallest tree that can show it is the one where the
    result cannot be an accident of anything else in the repository.
    """
    repo = tmp_path / "cockpit"
    (repo / "declarations").mkdir(parents=True)
    (repo / "instance" / "data").mkdir(parents=True)
    (repo / "declarations" / "boundary.yml").write_text(
        (repo_root() / "declarations" / "boundary.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (repo / ".gitattributes").write_text(
        "instance/data/** merge=ours\n", encoding="utf-8"
    )
    (repo / "instance" / "data" / "retention-last-run.yml").write_text(
        "# Evidence the retention sweep still runs\nv: 1\nlast_run: '2026-09-13'\n",
        encoding="utf-8",
    )

    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "a duplicate")
    _git(repo, "config", "user.email", "duplicate@example.test")
    # The one line `taking-an-update.md` asks for once per clone. Configured
    # here precisely so the test cannot be dismissed as "the driver was not
    # set up": it is, and it still does not fire.
    _git(repo, "config", "merge.ours.driver", "true")
    (repo / "instance" / "data" / "speakers.yml").write_text(
        "- id: spk-001\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "the merge base")
    return repo


def _our_side_moved_on(repo: Path) -> None:
    """A commit of the instance's own after the base, so the merge is a real
    three-way merge rather than a fast-forward.

    This is not scaffolding: a descent always happens on a cockpit that has
    been used since the last one, and the first version of this test
    fast-forwarded and so proved nothing. It touches a *different* file, so
    the ledger below is still one only upstream has changed -- which is the
    whole condition the defect needs.
    """
    (repo / "instance" / "data" / "speakers.yml").write_text(
        "- id: spk-001\n- id: spk-002\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "data: record a new lead for spk-002 by somebody")


def _upstream_moved_the_ledger(repo: Path) -> None:
    """Upstream's side: the product's own sweep advanced the date. Our side
    is untouched, which is what a duplicate whose jobs are not running looks
    like."""
    _git(repo, "checkout", "-q", "-b", "upstream")
    (repo / "instance" / "data" / "retention-last-run.yml").write_text(
        "# Evidence the retention sweep still runs\nv: 1\nlast_run: '2026-09-14'\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "data: record that the retention sweep ran today")
    _git(repo, "checkout", "-q", "main")


def test_the_merge_driver_does_not_fire_on_a_file_only_upstream_changed(
    tmp_path: Path,
) -> None:
    """The mechanism itself, executed.

    This is the claim the whole module rests on, and it is git's behaviour
    rather than this repository's, so it is run rather than asserted from a
    docstring. The driver is configured; the merge still takes upstream's
    value.
    """
    repo = _instance_repository(tmp_path)
    _upstream_moved_the_ledger(repo)
    _our_side_moved_on(repo)

    _git(repo, "merge", "-q", "--no-edit", "upstream")

    parents = subprocess.run(  # nosec B603 B607
        ["git", "rev-list", "--parents", "-n", "1", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert len(parents) >= 3, (
        "the merge fast-forwarded, so there is no three-way merge here and "
        "nothing has been shown about the driver -- the first version of "
        "this test did exactly that and passed"
    )

    carried = (repo / "instance" / "data" / "retention-last-run.yml").read_text(
        encoding="utf-8"
    )
    assert "2026-09-14" in carried, (
        "git kept our value, so the `ours` driver fired after all -- if that "
        "is now true of a file only one side changed, this whole module is "
        "describing a defect git no longer has, and the command below is "
        "guarding nothing"
    )


def test_the_command_refuses_the_merge_that_carried_a_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The net, over the merge the driver let through."""
    repo = _instance_repository(tmp_path)
    _upstream_moved_the_ledger(repo)
    _our_side_moved_on(repo)
    _git(repo, "merge", "-q", "--no-edit", "upstream")

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(repo))
    monkeypatch.chdir(repo)

    assert maintenance.check_merge_kept_the_instance() == 1


def test_the_command_passes_the_merge_that_kept_the_instance_s_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same merge, with the one line `taking-an-update.md` now asks for.

    Non-vacuity: a command that refused every merge would be switched off,
    so the corrected descent has to pass it.
    """
    repo = _instance_repository(tmp_path)
    _upstream_moved_the_ledger(repo)
    _our_side_moved_on(repo)
    _git(repo, "merge", "-q", "--no-commit", "--no-ff", "upstream")
    _git(
        repo,
        "restore",
        "--source=HEAD",
        "--staged",
        "--worktree",
        "--",
        "instance/data/retention-last-run.yml",
    )
    _git(repo, "commit", "-q", "--no-edit")

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(repo))
    monkeypatch.chdir(repo)

    assert maintenance.check_merge_kept_the_instance() == 0
    assert "2026-09-13" in (
        repo / "instance" / "data" / "retention-last-run.yml"
    ).read_text(encoding="utf-8")


def test_an_ordinary_commit_is_not_a_merge_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every commit on an instance except the handful a descent makes. A
    command that had anything to say about those would be noise, and noise
    is what this whole family of fixes exists to remove."""
    repo = _instance_repository(tmp_path)

    monkeypatch.setenv("CONVENER_REPO_ROOT", str(repo))
    monkeypatch.chdir(repo)

    assert maintenance.check_merge_kept_the_instance() == 0
