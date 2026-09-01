"""Every pattern in `.github/CODEOWNERS` names something this repository
tracks.

**The defect this exists for, in full, because it is the reason the shape
of the check is what it is.** The file ended on three lines:

    # instance/data/ is driven by the team app and validated by CI on
    # every commit. No required review here.
    /data/

The comment named `instance/data/` and the pattern named `/data/`. The
move that put the instance's own records under `instance/` took the
comment with it and left the pattern where it was, and there is no
`data/` at the root of this repository any more -- so the last rule in
the file matched nothing, `instance/data/` fell back to the `*` above it,
and every commit the cockpit writes to `speakers.yml` and every ledger a
scheduled job writes back asked the Editorial Board for a review. The
exact opposite of what the two lines above it say, reached without a
single thing going red.

**Nothing would ever have caught it.** A CODEOWNERS pattern that matches
no file is not an error to GitHub: the file parses, the rule is loaded,
and it simply never fires. GitHub's own CODEOWNERS validator reports
syntax and unknown owners, and neither of those was wrong here. A dead
rule in this file is invisible from every side except this one -- reading
the pattern against the repository it is a pattern *of*.

This is `test_workflows.py::test_every_ignored_path_still_names_
something_in_this_repository` asked of a different file, and the argument
is the same one that module already makes: an entry that names nothing is
not dangerous on its own, it is *illegible* -- it reads as a decision and
enforces nothing, so the next reader believes a review requirement is
where it is not.

**Against `git ls-files`, never against a working tree.** GitHub
evaluates this file against what a pull request changes, which is
tracked content; a working tree can hold anything beside it. The same
correction `test_workflows.py` records having had to make.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Final

import pytest

from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()

CODEOWNERS: Final = Path(".github/CODEOWNERS")

#: The one pattern that is deliberately not a path. It is the default
#: rule -- everything this repository tracks, reviewed by the Editorial
#: Board unless a later line says otherwise -- and asking whether it
#: names something tracked is asking whether the repository is empty.
_EVERYTHING: Final = "*"


def _rules() -> list[tuple[int, str, tuple[str, ...]]]:
    """Every rule `.github/CODEOWNERS` declares, as (line number, pattern,
    owners).

    Line numbers because a failure here sends a reader to a line, and a
    file of twenty-eight comment lines and two rules is one where "the
    third rule" means nothing to anybody.

    Comments and blank lines are dropped, and a comment is the whole of
    what follows a `#` -- GitHub reads this file with a comment syntax
    and nothing else, so a `#` cannot be part of a pattern here.
    """
    text = (ROOT / CODEOWNERS).read_text(encoding="utf-8")
    rules = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.partition("#")[0].strip()
        if not line:
            continue
        pattern, *owners = line.split()
        rules.append((number, pattern, tuple(owners)))
    return rules


def _tracked_under(pattern: str) -> list[str]:
    """What this repository tracks under one CODEOWNERS pattern.

    Two shapes are evaluated and every other one raises rather than being
    guessed at: a path anchored at the root (`/instance/data/`,
    `/keys/signing/README.md`), and the bare `*` handled by the caller.
    CODEOWNERS accepts a good deal more than that -- unanchored names,
    `*` inside a segment, `**` -- and a reader that translated one of
    those approximately would report a clean result about a rule that
    means something else, which is the whole failure being closed here.
    Widen this the day the file needs a shape it cannot read, and widen
    it with the test below beside it.
    """
    assert pattern.startswith("/"), (
        f"the CODEOWNERS pattern {pattern!r} is not anchored at the "
        "repository root -- this reader refuses to evaluate a pattern "
        "shape it was not written for rather than answer plausibly and "
        "wrongly"
    )
    assert not any(character in pattern for character in "*?[!"), (
        f"the CODEOWNERS pattern {pattern!r} carries a wildcard -- this "
        "reader evaluates anchored plain paths only, and refuses the "
        "rest rather than translating one approximately"
    )
    # Fixed argv, shell=False; `pattern` comes out of a tracked file in
    # this repository.
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "--", pattern.lstrip("/")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return listed.stdout.split()


@pytest.mark.parametrize(
    "rule", _rules(), ids=lambda rule: f"line {rule[0]}: {rule[1]}"
)
def test_every_codeowners_pattern_names_something_in_this_repository(
    rule: tuple[int, str, tuple[str, ...]],
) -> None:
    """A rule that matches nothing is a review requirement -- or a review
    *exemption* -- that a reader believes and GitHub never applies.

    The exemption direction is the one that bit: a pattern with no owners
    after it says "no review here", and one that matches nothing says it
    about nothing while the rule above goes on demanding a review for the
    subtree it was written to release. Both directions fail the same way
    here, because both are the same mistake -- a line about a path that is
    not this repository's any more.
    """
    number, pattern, _owners = rule
    if pattern == _EVERYTHING:
        pytest.skip(
            "the default rule matches every tracked file by construction; "
            "asking whether it names something asks whether the "
            "repository is empty"
        )
    tracked = _tracked_under(pattern)
    assert tracked, (
        f"{CODEOWNERS.as_posix()} line {number} declares {pattern!r}, "
        "which matches nothing this repository tracks -- GitHub loads the "
        "rule, never fires it, and reports nothing, so the line reads as "
        "a decision and is one only to whoever reads the file. Either the "
        "path moved and the pattern did not, or the rule has outlived "
        "what it was written for and belongs deleted"
    )


def test_the_reader_reproduces_the_defect_it_exists_for() -> None:
    """Positive control, in the exact shape the repository carried.

    `/data/` was the pattern; `/instance/data/` is where those records
    live. A check that could not tell the two apart would have passed on
    the broken file, which is the only thing worth proving about it.
    """
    assert not _tracked_under("/data/")
    assert _tracked_under("/instance/data/")


def test_at_least_one_pattern_is_actually_evaluated() -> None:
    """Non-vacuity, in a file that has two legal shapes.

    Every rule but `*` is skipped by name above, so an *instance*'s file --
    which carries a path rule releasing `/instance/data/` from the review
    the catch-all demands -- has to bring that rule here, or a file that
    lost it, or a parser that stopped finding rules at all, would leave
    the sweep reporting green over nothing.

    The **product**'s own file has no path rule to find and never will:
    one maintainer, one line, `*` and a handle, written after the first
    push by `docs/operating/publishing-the-product.md`. So that shape is
    admitted by *being* it -- exactly one rule, the catch-all, with an
    owner on it -- rather than by the sweep finding nothing and taking
    silence for a decision. A file that had lost its last path rule would
    still carry the rules above it and fail here, which is the difference
    between the two.
    """
    rules = _rules()
    evaluated = [
        pattern for _number, pattern, _owners in rules if pattern != _EVERYTHING
    ]
    if evaluated:
        return
    assert len(rules) == 1 and rules[0][1] == _EVERYTHING and rules[0][2], (
        f"{CODEOWNERS.as_posix()} declares no rule this sweep evaluates, and "
        "it is not the product's one-line shape either (a single "
        f"{_EVERYTHING!r} rule with an owner on it). Every pattern in it is "
        "the catch-all, so the sweep above proves nothing about any path"
    )


def test_every_rule_that_demands_a_review_names_who_gives_it() -> None:
    """The other half of a rule, and the one GitHub is silent about in the
    opposite direction: a pattern with owners after it requests a review
    from each of them, and a pattern with none releases the paths it
    covers from the rule above. Both are deliberate here -- `*` names the
    Board, `/instance/data/` names nobody -- and the file's own comments
    say which is which. What must never happen is a *third* shape: an
    owner that is not a team or an account, which GitHub reports as a
    syntax error on a file it then ignores in full.
    """
    for number, pattern, owners in _rules():
        for owner in owners:
            assert owner.startswith("@") or "@" in owner, (
                f"{CODEOWNERS.as_posix()} line {number} gives {pattern!r} "
                f"the owner {owner!r}, which is neither an `@account`, an "
                "`@organisation/team` nor an e-mail address -- GitHub "
                "refuses the whole file on a malformed owner, which "
                "leaves every rule in it unenforced rather than only "
                "this one"
            )
