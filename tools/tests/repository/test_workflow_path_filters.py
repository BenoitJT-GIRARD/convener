"""Every path a workflow filters on names something this repository tracks.

A `paths:` entry that matches nothing is silent in both directions. The
workflow simply never starts, no run goes red, and the line goes on reading
like a decision somebody made -- so a filter left behind by a rename is
indistinguishable, from the outside, from a filter that is working.

This repository has met that twice and paid differently each time.
`visuals.yml` filtered on a charter path that no longer named any charter, so
the render never re-ran when one changed; `templates.yml` needed a glob for
the same reason, and had been watching one file out of four. Both were found
by reading. `deploy.yml`'s own `paths-ignore:` has had a check of this shape
since (`test_workflows.py::test_every_ignored_path_still_names_something_in_
this_repository`), and this module is that check widened to the other list and
to every workflow: `paths:` decides whether a job runs at all, which is the
half where a dead entry costs a check rather than a wasted run.

**Against the index, never a working tree.** A runner sees tracked files and
nothing else, so a filter is evaluated here against `git ls-files` -- the
correction that module's own docstring already records for `paths-ignore:`,
made once and not twice.

**The reader refuses what it was not written for.** GitHub's filter syntax is
not `fnmatch`'s: `*` does not cross a `/` there and `**` does. Rather than
answer plausibly and wrongly for a shape nobody in this repository writes, the
translation below refuses `?`, `[` and `!`, and every entry today is a plain
path, a `dir/**` subtree or one `*` inside a single segment.

**One exemption, named with its reason.** A path an instance writes and this
repository never holds matches nothing here and is still a correct filter.
`EMPTY_IN_THIS_REPOSITORY` is the one place such an entry may be admitted, and
both halves are refused: an entry nobody exempted, and an exemption naming no
filter. That is the shape `tools/tests/repository/test_docs_directory.py::EXCEPTIONS`
already uses, and for its reason -- a list that may only grow stops describing
anything.

**And one entry whose emptiness is the instance's answer rather than this
repository's.** `OPTIONAL_FOR_THE_INSTANCE` is for a path product code
declares optional: present where the instance running this repository wrote
one, absent where its declaration names one of the product's instead, and
both are states the product ships in. Such an entry may not be held to
either direction -- upstream tracks the file and a repository
`convener-derive` produces does not -- and a filter that has to fire the day
one appears must name it before it does. What is checked instead is that
every entry there really is a path `declarations/boundary.yml` hands to the
instance, so this cannot become a way to excuse a product path that a rename
left behind.

**What this does not ask.** Whether the filter is the *right* set of inputs is
each workflow's own test's question -- `test_visuals_workflow.py`,
`test_templates_workflow.py`, `test_visuals_production_workflow.py` and
`test_path_filters.py` each pin their own list against what their job actually
reads. This one asks the question none of them can ask about the others: does
the line name anything at all.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
from typing import Final

import pytest
import yaml

from convener_ops.declaration import boundary
from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand

ROOT: Final = repo_root()
WORKFLOWS: Final = ROOT / ".github" / "workflows"


def _tracked() -> tuple[str, ...]:
    out = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return tuple(line.strip() for line in out.splitlines() if line.strip())


TRACKED: Final = _tracked()


def as_regex(pattern: str) -> re.Pattern[str]:
    """One GitHub path filter, as a regular expression over a POSIX path.

    `**` crosses separators, `*` does not, and everything else is literal.
    A shape this reader was not written for raises rather than being
    guessed at.
    """
    assert not any(character in pattern for character in "?[]!+"), (
        f"the path filter {pattern!r} uses a shape this reader was not "
        "written for -- GitHub's filter syntax is not `fnmatch`'s, and a "
        "pattern read wrongly would report a clean result about a line "
        "that means something else"
    )
    out: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return re.compile(f"^{''.join(out)}$")


def matches(pattern: str) -> list[str]:
    """Every tracked path one filter entry covers. A directory entry with
    no wildcard covers what is under it, the way GitHub reads it."""
    expression = as_regex(pattern)
    hits = [path for path in TRACKED if expression.match(path)]
    if not hits and not any(character in pattern for character in "*"):
        prefix = pattern.rstrip("/") + "/"
        hits = [path for path in TRACKED if path.startswith(prefix)]
    return hits


def filters() -> list[tuple[str, str, str]]:
    """`(workflow, list, entry)` for every `paths:` and `paths-ignore:`
    entry every workflow declares, on every trigger."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        triggers = document.get(True) or document.get("on") or {}
        if not isinstance(triggers, dict):
            continue
        for options in triggers.values():
            if not isinstance(options, dict):
                continue
            for key in ("paths", "paths-ignore"):
                for entry in options.get(key) or []:
                    found.append((path.name, key, str(entry)))
    return found


FILTERS: Final = filters()

#: Filter entries that match nothing here and are still right. One entry, and
#: the reason is the whole of it: a running instance commits a certificate
#: register per event, and this repository has run no event whose register it
#: carries -- `git ls-files instance/data/events` is empty, and `.gitignore`
#: has kept it that way deliberately since the registrations were encrypted.
#: The filter is what makes the showcase rebuild when one lands, so it has to
#: name the path before the path exists.
EMPTY_IN_THIS_REPOSITORY: Final[dict[str, str]] = {
    "instance/data/events/*/certificates.yml": (
        "the per-event certificate register a running instance commits; this "
        "repository tracks nothing under instance/data/events/"
    ),
}

#: Filter entries naming a path the instance owns and may not have written.
#: One entry, keyed off the product's own constant rather than typed:
#: `brand.INSTANCE_PATH` is optional by declaration -- an instance either
#: writes its own charter there or its declaration names one of the
#: product's, and `brand.source` gives both answers. Upstream is in the
#: first state and every repository `convener-derive` produces is in the
#: second, so this one entry is tracked here and tracked nowhere in the
#: published product, and the two workflows that re-render on a charter
#: change have to name it either way.
OPTIONAL_FOR_THE_INSTANCE: Final[dict[str, str]] = {
    brand.INSTANCE_PATH.as_posix(): (
        "the charter an instance writes for itself; an instance that names "
        "one of the product's instead holds no such file, and both are "
        "states brand.source answers"
    ),
}


def test_this_repository_has_path_filters_to_check() -> None:
    """Non-vacuity: a reader that stopped finding any filter at all would
    pass every parametrised case below by having none."""
    assert len(FILTERS) >= 20, (
        f"only {len(FILTERS)} path filter(s) found across "
        f"{len(list(WORKFLOWS.glob('*.yml')))} workflows -- the reader has "
        "stopped seeing the lists it is meant to check"
    )


@pytest.mark.parametrize(
    ("workflow", "key", "entry"),
    FILTERS,
    ids=[f"{workflow}:{key}:{entry}" for workflow, key, entry in FILTERS],
)
def test_every_path_filter_names_something_tracked(
    workflow: str, key: str, entry: str
) -> None:
    """The rule. A line that filters on nothing is a decision nobody
    enforces, and a rename is the ordinary way one arrives."""
    if entry in EMPTY_IN_THIS_REPOSITORY or entry in OPTIONAL_FOR_THE_INSTANCE:
        return
    assert matches(entry), (
        f"{workflow}'s `{key}:` names {entry!r}, which matches nothing this "
        "repository tracks. A runner only ever sees tracked files, so that "
        "line filters nothing while reading like a decision -- the shape a "
        "renamed directory leaves behind"
    )


def test_the_reader_reads_the_two_wildcards_the_way_github_does() -> None:
    """Held here rather than trusted: the check above compares a pattern
    with the index and would agree with a reader that matched everything."""
    assert as_regex("assets/fonts/**").match("assets/fonts/a/b.woff2")
    assert as_regex("assets/brand/*/brand.json").match("assets/brand/steps/brand.json")
    assert not as_regex("assets/brand/*/brand.json").match(
        "assets/brand/a/b/brand.json"
    )
    assert not as_regex("app/**").match("site/index.njk")
    with pytest.raises(AssertionError, match="was not written for"):
        as_regex("app/[abc].ts")


def test_every_exemption_is_still_a_filter_somebody_writes() -> None:
    """The other half. An exemption for an entry no workflow carries any
    more excuses nothing and hides the next dead line behind a name that
    reads like a decision."""
    declared = {entry for _, _, entry in FILTERS}
    stale = sorted(set(EMPTY_IN_THIS_REPOSITORY) - declared)
    assert not stale, (
        f"{stale} are exempted here and no workflow filters on them any "
        "more -- an exemption no case reaches is a line nobody can fail"
    )


def test_every_optional_entry_is_a_path_the_instance_owns() -> None:
    """The half that keeps the second list from becoming a hole.

    An entry there is excused in both directions, so the one thing that has
    to hold is that the path is the instance's to write at all --
    `declarations/boundary.yml` is what says so, and a product path a
    rename left behind can never be admitted this way.
    """
    board = boundary.load(ROOT)
    theirs = [
        entry
        for entry in OPTIONAL_FOR_THE_INSTANCE
        if board.owner_of(entry) != boundary.INSTANCE
    ]
    assert theirs == [], (
        f"{theirs} are exempted as files an instance may or may not have "
        "written, and declarations/boundary.yml hands them to the product -- "
        "a product path that matches nothing is the dead filter this module "
        "is about"
    )


def test_every_optional_entry_is_still_a_filter_somebody_writes() -> None:
    """And the other half, the same one `EMPTY_IN_THIS_REPOSITORY` gets: an
    exemption for an entry no workflow carries any more excuses nothing."""
    declared = {entry for _, _, entry in FILTERS}
    stale = sorted(set(OPTIONAL_FOR_THE_INSTANCE) - declared)
    assert not stale, (
        f"{stale} are exempted here and no workflow filters on them any "
        "more -- an exemption no case reaches is a line nobody can fail"
    )


def test_every_exemption_really_does_match_nothing() -> None:
    """And the third. An exemption for an entry that has since started
    matching something is an entry now going unchecked."""
    live = sorted(entry for entry in EMPTY_IN_THIS_REPOSITORY if matches(entry))
    assert not live, (
        f"{live} are exempted as matching nothing and now match tracked "
        "files -- the exemption has stopped being a statement and become "
        "a hole"
    )
