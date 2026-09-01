"""`gates.sh` runs what it says `.github/workflows/quality.yml` runs.

**The claim, and why it needed holding.** The runner's own header says
each of its lines is the command the operating documentation already told
a reader to type, "so a gate that passes here passes there and the two
cannot drift into different checks". It was a claim about two files and
nothing compared them. They drifted, and the drift ran one way only:
`quality.yml` grew the six generators' `--check`, the decision register,
the commit-message check, the security scan, seven dependency audits, the
application's own lint and types, the showcase's lint, the performance
budget and the relays' lint, while `gates.sh` stayed at eight targets.
Twenty of `quality.yml`'s twenty-eight checks were things a maintainer
believed `sh gates.sh` had just run.

That is worse than a missing check, and the reason is the same one D-25
gives about a check that cannot fail: a gate nobody runs is a gate nobody
trusts, and a gate everybody believes they ran is a gate nobody looks at
again. It is also exactly the failure that hides behind a green local run
before a publication.

**What is compared, and why it is the step name.** Not the commands: the
two sides deliberately spell four of them differently (`--frozen`,
`python -m`, `actionlint`'s two disabled linters, the audits run
together), each difference argued for in `gates.sh`'s own header, and a
comparison that demanded byte-identical commands would fail on every one
of those arguments. What has to be complete is the *set of checks*, and a
step's name is what `quality.yml` calls a check. So the table in
`gates.sh` names every step of that workflow and the target that runs it,
this module reads both files, and a step in one and not the other is red.

**`Install ...` is not a check.** `gates.sh`'s header says why the three
installs are not targets -- they are run once per tree, in an order that
page states, and a target would invite running the gates before them --
so a step whose name begins with `Install` is left out of the comparison
by both sides. It is a rule about a word, stated here because it is the
one assumption in this module that a reader cannot see in either file.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest
import yaml

from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()

GATES: Final = Path("gates.sh")
QUALITY: Final = Path(".github/workflows/quality.yml")

#: A step that installs a toolchain rather than checking anything. The
#: prefix, not a list of the nine that exist today: a tenth tree would
#: arrive with an install step of its own and nothing here should have to
#: be edited for it.
INSTALL: Final = "Install"

#: What a table line says when the step deliberately has no target.
NONE: Final = "none"

#: The two case labels that are not gates: the default, and the usage
#: message.
NOT_A_TARGET: Final = frozenset({"all", "*"})

_TABLE_LINE: Final = re.compile(r"^#   (?P<step>.+?) -> (?P<target>\S+)$")
_CASE_LABEL: Final = re.compile(r"^  (?P<label>[a-z*][a-z|*-]*)\)")
_ALL_TARGETS: Final = re.compile(
    r"^  all\)\s+for gate in (?P<targets>[a-z ]+);", re.MULTILINE
)
_USAGE: Final = re.compile(r"usage: sh \$0 \[(?P<targets>[a-z|]+)\]")


def _gates_text() -> str:
    return (ROOT / GATES).read_text(encoding="utf-8")


def workflow_steps(text: str) -> list[str]:
    """Every check one workflow declares, in the order it runs them.

    Named steps only, and installs dropped. A step with no `name:` is a
    bare `uses:` -- the checkout, `setup-python`, `setup-node` -- which is
    machinery rather than a check and has nothing a runner could mirror.
    """
    loaded = yaml.safe_load(text)
    return [
        step["name"]
        for job in loaded["jobs"].values()
        for step in job["steps"]
        if "name" in step and not step["name"].startswith(INSTALL)
    ]


def gates_table(text: str) -> list[tuple[str, str]]:
    """The runner's own claim about the workflow, as (step, target) pairs
    in the order it makes them."""
    return [
        (match["step"], match["target"])
        for match in (_TABLE_LINE.match(line) for line in text.splitlines())
        if match is not None
    ]


def gates_targets(text: str) -> list[str]:
    """Every target the runner dispatches on, `all` and the usage arm
    excluded."""
    return [
        match["label"]
        for match in (_CASE_LABEL.match(line) for line in text.splitlines())
        if match is not None and match["label"] not in NOT_A_TARGET
    ]


def test_the_readers_find_something_in_both_files() -> None:
    """Non-vacuity, first, because every assertion below is a comparison
    of two lists and two empty lists agree perfectly.

    A regex that stopped matching -- an indent changed, a table reflowed,
    a `case` rewritten as an `if` -- would otherwise turn this whole
    module green and silent, which is the exact failure it exists to stop
    `gates.sh` itself from having.
    """
    text = _gates_text()
    assert workflow_steps((ROOT / QUALITY).read_text(encoding="utf-8"))
    assert gates_table(text)
    assert gates_targets(text)


def test_every_check_the_workflow_runs_has_a_line_in_the_runner() -> None:
    """The direction that drifted. A step added to `quality.yml` and
    nowhere else lands here, and the fix is either a target or a `none`
    with the argument for it beside the table.
    """
    steps = workflow_steps((ROOT / QUALITY).read_text(encoding="utf-8"))
    claimed = {step for step, _target in gates_table(_gates_text())}
    missing = [step for step in steps if step not in claimed]
    assert not missing, (
        f"{QUALITY.as_posix()} runs {missing}, and {GATES.as_posix()} says "
        "nothing about them -- so a maintainer who runs every target still "
        "has not run these, and nothing but a pushed branch will say so. "
        "Give each one a target, or a `none` in the table with the reason "
        "written beside it"
    )


def test_the_runner_claims_no_check_the_workflow_stopped_running() -> None:
    """The other direction, and the one that goes stale quietly: a step
    renamed or deleted leaves a line here that still reads as coverage.
    """
    steps = set(workflow_steps((ROOT / QUALITY).read_text(encoding="utf-8")))
    stale = [step for step, _target in gates_table(_gates_text()) if step not in steps]
    assert not stale, (
        f"{GATES.as_posix()} claims to mirror {stale}, which "
        f"{QUALITY.as_posix()} does not run under that name any more -- "
        "either the step was renamed and this line was not, or the check "
        "is gone and the line is a claim about nothing"
    )


def test_the_table_is_in_the_order_the_workflow_runs_them() -> None:
    """The table says it is in the workflow's own order, which is the only
    thing that makes it readable against the file it mirrors. Order is
    also what makes a missing line obvious to a person rather than only to
    this module.
    """
    steps = workflow_steps((ROOT / QUALITY).read_text(encoding="utf-8"))
    claimed = [step for step, _target in gates_table(_gates_text())]
    assert claimed == steps, (
        f"{GATES.as_posix()}'s table is not in {QUALITY.as_posix()}'s own "
        "order any more, so reading one against the other stops being a "
        "line-by-line comparison"
    )


def test_every_target_the_table_names_is_one_the_runner_dispatches() -> None:
    """A table naming a target the `case` does not carry sends
    `sh gates.sh <target>` to the usage message, which exits 2 -- loud,
    but only for whoever types that one target rather than `all`.
    """
    text = _gates_text()
    targets = set(gates_targets(text))
    unknown = sorted(
        {
            target
            for _step, target in gates_table(text)
            if target != NONE and target not in targets
        }
    )
    assert not unknown, (
        f"{GATES.as_posix()}'s table names {unknown}, which its own `case` "
        "has no arm for -- the table promises a gate the runner cannot run"
    )


def test_no_target_the_runner_carries_runs_nothing() -> None:
    """The mirror of the clause above, and the same argument
    `test_codeowners.py` makes about a pattern that matches nothing: a
    target no line of the table sends anything to is a gate whose subject
    has gone, kept alive by the `case` arm that still dispatches it.
    """
    text = _gates_text()
    claimed = {target for _step, target in gates_table(text)}
    idle = [target for target in gates_targets(text) if target not in claimed]
    assert not idle, (
        f"{GATES.as_posix()} dispatches {idle}, and no step of "
        f"{QUALITY.as_posix()} is mapped to it -- either the table lost a "
        "line or the target has outlived the check it was written for"
    )


def test_all_runs_every_target() -> None:
    """`all` is the default, so it is what a maintainer actually runs, and
    a target left out of its list is a check that exists and never
    happens.
    """
    text = _gates_text()
    listed = _ALL_TARGETS.search(text)
    assert listed is not None, (
        f"{GATES.as_posix()}'s `all` arm is not the `for gate in ...` loop "
        "this reader was written for -- widen the reader with the reason, "
        "rather than leaving it reporting green about a shape it cannot see"
    )
    assert listed["targets"].split() == gates_targets(text), (
        f"`all` runs {listed['targets'].split()} and {GATES.as_posix()} "
        f"dispatches {gates_targets(text)} -- a target outside that list "
        "is one nothing but a deliberate invocation ever reaches"
    )


def test_the_usage_message_offers_every_target() -> None:
    """The line a mistyped target prints. It is the only list of targets a
    reader ever sees at a terminal, and it is the one most likely to be
    left behind when a target is added.
    """
    text = _gates_text()
    usage = _USAGE.search(text)
    assert usage is not None, f"{GATES.as_posix()} prints no usage message"
    offered = usage["targets"].split("|")
    assert offered == [*gates_targets(text), "all"], (
        f"the usage message offers {offered}, and the runner dispatches "
        f"{[*gates_targets(text), 'all']}"
    )


@pytest.mark.parametrize(
    ("removed", "expected"),
    [("Types", "Types"), ("Performance budget", "Performance budget")],
)
def test_the_comparison_reproduces_the_drift_it_exists_for(
    removed: str, expected: str
) -> None:
    """Positive control, on a copy of the runner's own text rather than on
    a fixture invented here: delete one line of the real table and the
    real workflow's step must come back as missing. A comparison that
    could not do that would pass over any table at all, including an empty
    one.
    """
    text = _gates_text()
    without = "\n".join(
        line
        for line in text.splitlines()
        if not (line.startswith("#   ") and line.startswith(f"#   {removed} -> "))
    )
    steps = workflow_steps((ROOT / QUALITY).read_text(encoding="utf-8"))
    claimed = {step for step, _target in gates_table(without)}
    assert expected in steps
    assert expected not in claimed
