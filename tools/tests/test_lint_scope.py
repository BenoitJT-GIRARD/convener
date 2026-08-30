"""The local hook and continuous integration lint the same files.

`ruff` runs twice over this repository: once in `.pre-commit-config.yaml`,
over what is about to become a commit, and once in
`.github/workflows/quality.yml`, over the checkout. Each is configured
separately -- the hook by a `files:` regular expression, the workflow by
the path arguments it hands `ruff` -- and nothing joined the two. They
disagreed for months: the hook was scoped to `^tools/` while the workflow
linted `. ../scripts`, so every generator and every migration was linted
in continuous integration and not locally. Nobody chose that; it followed
from where the files sat, and a comment saying the two agreed would have
been just as wrong as the silence was.

So the two are compared here rather than asserted, and both halves are
read out of the files that carry them:

* the hook's reach is its own `files:` pattern applied to what this
  repository tracks, the way `pre-commit` applies it -- `re.search` over
  the repository-relative path, narrowed by whatever `exclude:` sits
  beside it and at the top of the file;
* the workflow's reach is measured rather than modelled. The `run:` line
  is parsed for the arguments it gives `ruff`, and `ruff` itself is then
  asked which files those arguments reach, from the workflow's own
  `working-directory`. A repository-wide `exclude` added to
  `tools/pyproject.toml` would move that answer, and this test would say
  so instead of comparing against a walk of its own that never read it.

**What this cannot compare, and what is done about each.**

*The rules, and what is done with a finding.* The hook runs `ruff check
--fix` and rewrites the file; the workflow runs `ruff check` and fails.
That difference is deliberate and is not scope, so it is not compared.
Both read the same `tools/pyproject.toml`, which is the only ruff
configuration in the repository, so the rule set cannot differ between
them at all.

*What a single run actually inspects.* `pre-commit` passes the hook only
the files in the commit, so any one run covers a subset of its reach.
The claim held here is about what each side is configured to reach, which
is the property that drifts.

*The hook's own file types.* `ruff-pre-commit` declares `types_or:` in its
own repository, which is a network fetch away and unreadable here, so it
cannot be read and compared. Both sides are therefore compared over the
Python files this repository tracks, and a notebook -- the one shape whose
membership would turn on that unreadable declaration -- is refused below
rather than guessed at.

*The format check's own discovery.* `ruff format` has no `--show-files`,
so the format step's reach is measured by asking `ruff check` which files
the format step's *own arguments* reach. The two subcommands share one
file walker and one configuration; what is measured is that walk over
those arguments.
"""

from __future__ import annotations

import re
import shlex
import subprocess  # nosec B404
import sys
import tomllib
from pathlib import Path
from typing import Final

import pytest
import yaml

from convener_ops.paths import repo_root

ROOT: Final = repo_root()
PRE_COMMIT_CONFIG: Final = ROOT / ".pre-commit-config.yaml"
QUALITY_WORKFLOW: Final = ROOT / ".github" / "workflows" / "quality.yml"
RUFF_REPO: Final = "https://github.com/astral-sh/ruff-pre-commit"

#: The hook that lints and the hook that checks formatting, each beside the
#: `ruff` subcommand the workflow runs for the same purpose. Compared pair
#: by pair rather than as one set: two hooks scoped differently from each
#: other is the same defect one step further in, and a single set would
#: hide it.
PAIRS: Final = (("ruff", "check"), ("ruff-format", "format"))

#: What `ruff` reads as Python, and what both sides are compared over.
#: `.ipynb` is deliberately absent -- see `test_no_tracked_notebook_makes_
#: the_two_sides_incomparable`.
PYTHON_SUFFIXES: Final = (".py", ".pyi")

#: Flags this reader knows take no separate value, so that everything else
#: after the subcommand is a path. A `--config` or an `--extend-exclude`
#: added to either step would be mis-read as a path by a reader that
#: guessed, so it raises instead.
VALUELESS_FLAGS: Final = frozenset({"--check", "--fix", "--diff", "--quiet"})


def _tracked() -> list[str]:
    """Every file this repository tracks, as repository-relative POSIX
    paths -- what a runner checks out, and what `pre-commit` matches its
    `files:` pattern against."""
    # Fixed argv, shell=False.
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return listed.stdout.split()


def _tracked_python() -> set[str]:
    return {path for path in _tracked() if path.endswith(PYTHON_SUFFIXES)}


# ------------------------------------------------------------------ #
# The hook's half: a pattern, read and applied
# ------------------------------------------------------------------ #


def _pre_commit() -> dict[str, object]:
    loaded = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _hook(hook_id: str) -> dict[str, object]:
    """One hook of the ruff repository, by id."""
    config = _pre_commit()
    repos = config["repos"]
    assert isinstance(repos, list)
    ruff_repos = [
        repo
        for repo in repos
        if isinstance(repo, dict) and repo.get("repo") == RUFF_REPO
    ]
    assert len(ruff_repos) == 1, (
        f"{PRE_COMMIT_CONFIG.name} declares {len(ruff_repos)} ruff repositories; "
        "this reader knows one, and would compare the wrong half of a second"
    )
    hooks = ruff_repos[0]["hooks"]
    assert isinstance(hooks, list)
    found = [hook for hook in hooks if isinstance(hook, dict) and hook["id"] == hook_id]
    assert len(found) == 1, (
        f"{PRE_COMMIT_CONFIG.name} declares {len(found)} `{hook_id}` hooks; "
        "the local half of this comparison is not there to be read"
    )
    return found[0]


def _hook_reach(hook_id: str) -> set[str]:
    """The tracked Python files `pre-commit` would hand this hook.

    `files:` and `exclude:` are `re.search` patterns over the
    repository-relative path, and the file's own top-level pair applies to
    every hook in it, so both levels are read.
    """
    config = _pre_commit()
    hook = _hook(hook_id)
    include = [
        str(config.get("files", "")),
        str(hook.get("files", "")),
    ]
    exclude = [
        str(config.get("exclude", "^$")),
        str(hook.get("exclude", "^$")),
    ]
    assert any(pattern for pattern in include), (
        f"the `{hook_id}` hook scopes itself to nothing in particular, so it "
        "reaches every file in the repository -- which may be right, but it "
        "is not what this file says, and the comparison below would then be "
        "checking a default rather than a decision"
    )
    return {
        path
        for path in _tracked_python()
        if all(re.search(pattern, path) for pattern in include if pattern)
        and not any(re.search(pattern, path) for pattern in exclude)
    }


# ------------------------------------------------------------------ #
# The workflow's half: arguments, read and then measured
# ------------------------------------------------------------------ #


def _ruff_steps() -> dict[str, tuple[str, list[str]]]:
    """Each `ruff` subcommand the quality workflow runs, with the
    directory it runs in and the paths it is given.

    Read out of the `run:` lines rather than out of the step names, so
    that renaming a step changes nothing and adding a third `ruff` call
    fails here instead of going uncompared.
    """
    workflow = yaml.safe_load(QUALITY_WORKFLOW.read_text(encoding="utf-8"))
    steps: dict[str, tuple[str, list[str]]] = {}
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            run = str(step.get("run", ""))
            for line in run.splitlines():
                if "ruff" not in line.split():
                    continue
                tokens = shlex.split(line, posix=False)
                rest = tokens[tokens.index("ruff") + 1 :]
                assert rest, f"{line!r} runs ruff with no subcommand"
                subcommand, *arguments = rest
                paths: list[str] = []
                for argument in arguments:
                    if argument.startswith("-"):
                        assert argument in VALUELESS_FLAGS, (
                            f"{line!r} passes {argument!r}, which this reader "
                            "does not know to be a flag carrying no separate "
                            "value -- it refuses to guess whether the next "
                            "token is that flag's value or a path"
                        )
                        continue
                    paths.append(argument)
                assert subcommand not in steps, (
                    f"the workflow runs `ruff {subcommand}` more than once; "
                    "this reader compares one invocation per subcommand and "
                    "would silently drop the rest"
                )
                steps[subcommand] = (str(step.get("working-directory", "")), paths)
    return steps


def _workflow_reach(subcommand: str) -> set[str]:
    """The tracked Python files that step's own arguments reach, as `ruff`
    itself answers from that step's own working directory.

    Narrowed to what is tracked, because that is the universe the hook's
    own pattern is matched against: a runner checks out tracked files and
    nothing else, and a file not yet added to the index cannot reach either
    gate. Comparing a walk of the working tree against a pattern applied to
    the index would report a gap every time somebody starts a new module.
    """
    directory, paths = _ruff_steps()[subcommand]
    assert paths, (
        f"the workflow's `ruff {subcommand}` step is given no path at all; "
        "there is nothing to compare the hook against"
    )
    working = ROOT / directory if directory else ROOT
    # Fixed argv, shell=False; the paths come out of the workflow file and
    # `--show-files` writes nothing.
    listed = subprocess.run(  # nosec B603
        [sys.executable, "-m", "ruff", "check", "--show-files", *paths],
        cwd=working,
        capture_output=True,
        text=True,
        check=True,
    )
    reached: set[str] = set()
    for line in listed.stdout.splitlines():
        if not line.strip():
            continue
        path = Path(line.strip()).resolve().relative_to(ROOT).as_posix()
        if path.endswith(PYTHON_SUFFIXES):
            reached.add(path)
    return reached & _tracked_python()


# ------------------------------------------------------------------ #
# Neither half may be empty, and neither may be everything
# ------------------------------------------------------------------ #


def test_no_tracked_notebook_makes_the_two_sides_incomparable() -> None:
    """`ruff` lints `.ipynb`; whether the hook is handed one is declared in
    `ruff-pre-commit`'s own repository, which cannot be read from here. No
    notebook is tracked, so the question does not arise -- and the day one
    is, this fails rather than reporting an agreement it could not check.
    """
    notebooks = sorted(path for path in _tracked() if path.endswith(".ipynb"))
    assert notebooks == [], (
        f"{notebooks} are tracked. Whether the local hook lints them turns on "
        "`types_or:` in ruff-pre-commit's own repository, which this test "
        "cannot read, so the two sides can no longer be compared file for file"
    )


@pytest.mark.parametrize(("hook_id", "subcommand"), PAIRS)
def test_each_half_of_the_comparison_reaches_the_whole_of_tools(
    hook_id: str, subcommand: str
) -> None:
    """Non-vacuity. Two empty sets are equal, and so are two sets that
    happen to hold only the package: the four trees under `tools/` arrived
    there at four different times, and each has been outside one of these
    two gates at some point."""
    halves = (
        (hook_id, _hook_reach(hook_id)),
        (f"ruff {subcommand}", _workflow_reach(subcommand)),
    )
    for where, reach in halves:
        for tree in (
            "tools/convener_ops/",
            "tools/scripts/",
            "tools/migrations/",
            "tools/tests/",
        ):
            assert any(path.startswith(tree) for path in reach), (
                f"{where} reaches nothing under {tree} -- the comparison "
                "below would pass while that directory is linted by neither"
            )


def test_the_comparison_can_tell_a_narrower_hook_from_the_workflow() -> None:
    """Positive control, on the mechanism rather than on the files. The
    whole of this module is one equality, and an equality between two sets
    computed the same wrong way holds just as well as one between two right
    ones. So the hook's own reader is run against a pattern narrowed to the
    package, and the difference has to appear and has to name what it
    dropped."""
    narrowed = {
        path for path in _tracked_python() if re.search("^tools/convener_ops/", path)
    }
    missed = _workflow_reach("check") - narrowed
    assert missed, "a hook scoped to the package alone was found to miss nothing"
    assert any(path.startswith("tools/scripts/") for path in missed)
    assert any(path.startswith("tools/migrations/") for path in missed)
    assert any(path.startswith("tools/tests/") for path in missed)


# ------------------------------------------------------------------ #
# The comparison
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(("hook_id", "subcommand"), PAIRS)
def test_the_hook_and_continuous_integration_reach_the_same_files(
    hook_id: str, subcommand: str
) -> None:
    """The one thing this module exists for.

    A file on one side and not the other is the shape this repository
    already shipped: linted on the way in and not on the way out, or the
    reverse. Both directions are named, because they fail differently --
    a file the hook misses is caught late and loudly, a file the workflow
    misses is not caught at all.
    """
    hook = _hook_reach(hook_id)
    workflow = _workflow_reach(subcommand)
    assert hook == workflow, (
        f"the `{hook_id}` hook in {PRE_COMMIT_CONFIG.name} and "
        f"`ruff {subcommand}` in {QUALITY_WORKFLOW.name} do not cover the "
        f"same files. Only continuous integration reaches "
        f"{sorted(workflow - hook)}; only the hook reaches "
        f"{sorted(hook - workflow)}. Either the hook's `files:` pattern or "
        "the step's own path arguments has to move"
    )


def test_the_two_workflow_steps_are_given_the_same_paths() -> None:
    """The same question asked sideways. `ruff check` and `ruff format
    --check` are two steps with two argument lists, and a path added to one
    of them is exactly as easy to forget as a path added to neither."""
    steps = _ruff_steps()
    assert set(steps) == {subcommand for _, subcommand in PAIRS}, (
        f"the workflow runs `ruff {sorted(steps)}`; this comparison is "
        f"written for {sorted(subcommand for _, subcommand in PAIRS)}"
    )
    directories = {directory for directory, _ in steps.values()}
    arguments = {tuple(paths) for _, paths in steps.values()}
    assert len(directories) == 1 and len(arguments) == 1, (
        f"the two ruff steps run in {sorted(directories)} over "
        f"{sorted(arguments)} -- one of them checks a tree the other does not"
    )


def _declares_ruff_settings(path: str) -> bool:
    """Whether one tracked file is somewhere `ruff` reads its settings
    from. `ruff.toml` and `.ruff.toml` are settings wherever they sit; a
    `pyproject.toml` is only settings if it carries a `[tool.ruff]` table.
    """
    name = Path(path).name
    if name in ("ruff.toml", ".ruff.toml"):
        return True
    if name != "pyproject.toml":
        return False
    settings = tomllib.loads((ROOT / path).read_text(encoding="utf-8"))
    tools = settings.get("tool", {})
    return isinstance(tools, dict) and "ruff" in tools


def test_both_halves_read_one_ruff_configuration() -> None:
    """What makes the rule sets impossible to compare unnecessary: there is
    one ruff configuration in the repository, so the hook and the workflow
    cannot be running different rules over the files they agree on."""
    configurations = sorted(
        path for path in _tracked() if _declares_ruff_settings(path)
    )
    assert configurations == ["tools/pyproject.toml"], (
        f"ruff settings are declared in {configurations}. Two of them means "
        "the hook and the workflow can disagree on the rules even where they "
        "agree on the files, and nothing here would say so"
    )
