"""What each npm tree says it needs of Node, against what its lock file
requires.

`engines.node` is the one restatement of the Node version that has to
exist: npm reads it and reads no `.nvmrc`, so it is what warns a
maintainer whose machine is too old. It warns only if it is true, and it
was not. Every tree said `>=24`, one tree's dependencies needed 24.15.0,
and the gap was invisible until a machine on 24.14.1 ran `npm install` in
`app/` and read `EBADENGINE` -- from `jsdom`, after the fact. Continuous
integration never saw it: `.nvmrc` says `24`, a runner resolves a bare
major to the newest release of that line, and the newest release of a
line is always above its floor.

**What this refuses.** A `package.json` whose own `engines.node` admits a
version of the Node line `.nvmrc` names that one of its installed
dependencies refuses. The floor is derived, never written here: every
`engines.node` the lock file records is read, and the message names the
package that raised it and the tree it sits in, so the reader does not
have to repeat the sweep.

**Why the line, and not every version there is.** `>=24.15.0` admits
25.0.0, and `jsdom` refuses 25.0.0 -- so a rule asking about every
version there is would be red the day it was written and stay red until
somebody deleted it. It would also be asking a question nobody here has:
`.nvmrc` names one line, every workflow installs from it, and a
maintainer runs what it names. So the window is that line, and it is read
from `.nvmrc` rather than stated, which is what keeps this module from
being a second place the version is written.

**The range reader is a reader.** `^22.22.2 || ^24.15.0 || >=26.0.0` is a
disjunction, and "does `>=24` admit a version this refuses" is a
comparison between two sets, not a shape a regular expression can match.
`_admitted` turns a range into the union of half-open intervals it
admits, and the rule is then subtraction. Nothing here guesses: a range
it cannot read raises `UnreadableRangeError` rather than returning an answer,
so the way this fails is a red suite naming the range, never a quiet
`True`.

**Soundness was measured against node-semver rather than argued.** No
Python dependency of this repository reasons about semver, so the reader
is this module's own. Every distinct `engines.node` the six lock files
record -- 82 of them -- and 34 more written to exercise the grammar --
caret, tilde, hyphen, x-ranges, a bare operator with a space after it,
a leading `v`, several comparators in one alternative -- were each put to
3 906 versions, and all 453 096 answers compared with `semver.satisfies`
from `semver@6.3.1` and again from `semver@7.8.5`, both already in
`app/`'s installed tree. Zero disagreements, both times.
`test_the_reader_agrees_with_the_published_grammar` pins the handful of
those cases that carry the reasoning, so a change to the reader has to
answer them again.

**An optional dependency is not a floor.** `@img/sharp-win32-ia32` asks
for `^20.9.0`, which admits no Node 24 at all, and it sits in all three
relay lock files. It is never installed: npm omits an optional dependency
it cannot use rather than failing the install, so it warns about nothing
and constrains nothing. Measured rather than reasoned from the
documentation -- `npm ci` in `services/auth-proxy` on Node 24.21.0 leaves
`node_modules/@img/` holding `sharp-win32-x64` and no `sharp-win32-ia32`,
and prints no `EBADENGINE`. Read in, it would make every relay's floor
unsatisfiable and this whole module red on the day it was written.

**One direction only, and the other one is a judgement.** A tree that
says more than its lock file requires is refused here. A tree that says
*less* -- `>=24.15.0` where nothing above 24.0.0 is required -- is not,
because a floor can come from something no lock file records: source that
calls a Node API added mid-line. Refusing that would be this module
overruling a maintainer about their own code. What it costs is that
`>=24.15.0` copied across six trees passes, and the report a change
leaves is where that is caught.

**Its relation to `test_workflows.py`.** That module's own
`_range_floor_major` reads the lowest major a range admits, takes the
lowest branch of a disjunction, and its docstring says what that cannot
see. It holds two properties this one does not -- that no workflow spells
a version out, and that `.nvmrc` is not below the majors the lock files
name -- and it reads majors because those are questions about majors.
This module is the finer half, inside one line, and the two do not
overlap: neither would catch what the other does.
"""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404
from pathlib import Path
from typing import Final, NamedTuple

import pytest

from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()

#: The file naming the Node line this repository runs on. Read, never
#: restated: the window every comparison below is made inside comes out of
#: it, so raising it moves this module's own subject with it.
NODE_LINE: Final = Path(".nvmrc")

Version = tuple[int, int, int]

#: A half-open interval of versions, `[low, high)`.
Interval = tuple[Version, Version]

#: What a range admits: intervals, sorted, disjoint and merged, so two
#: ranges are equal when their tuples are.
Admitted = tuple[Interval, ...]

LOWEST: Final[Version] = (0, 0, 0)

#: Above every version anybody will publish, standing in for an open upper
#: bound so that one comparison covers both. `_partial` refuses a major
#: this large rather than letting a real version reach it.
BEYOND: Final[Version] = (1_000_000, 0, 0)

EVERYTHING: Final[Admitted] = ((LOWEST, BEYOND),)
NOTHING: Final[Admitted] = ()

_WILDCARD: Final = frozenset({"x", "X", "*", ""})
_HYPHEN: Final = re.compile(r"^\s*(\S+)\s+-\s+(\S+)\s*$")
_COMPARATOR: Final = re.compile(r"\s*(<=|>=|<|>|=|\^|~)?\s*([0-9xX*v][^\s]*)")
_NUMBER_OR_WILDCARD: Final = re.compile(r"^(?:0|[1-9][0-9]*|[xX*])$")


class UnreadableRangeError(ValueError):
    """A version expression this reader will not guess at.

    Raised rather than answered. A control that reads `>=24` correctly and
    a prerelease range approximately is worse than one that stops, because
    the approximate answer is the one nobody checks.
    """


class Requirement(NamedTuple):
    """One `engines.node` a lock file records, and what it admits."""

    package: str
    version: str
    spec: str
    admits: Admitted


class Tree(NamedTuple):
    """One npm tree: what it declares, and what its lock file requires."""

    manifest: str
    lockfile: str
    declared: str
    requirements: tuple[Requirement, ...]


# --------------------------------------------------------------------------
# The range reader
# --------------------------------------------------------------------------


def _partial(text: str) -> tuple[Version, Version, int]:
    """A partial version, as its own lowest member, its exclusive upper
    bound and the number of parts it actually names.

    `1.2.3` names three and covers itself alone; `1.2` names two and
    covers all of `1.2.x`; `1`, `1.x` and `*` widen from there. Every
    operator below is a function of those three values, which is why
    `^1.2` and `^1.2.0` differ without either being a special case.
    """
    if any(character in text for character in "-+"):
        raise UnreadableRangeError(f"{text!r} carries a prerelease or build identifier")
    body = text[1:] if text[:1] == "v" else text
    if body in _WILDCARD:
        return LOWEST, BEYOND, 0
    parts = body.split(".")
    if len(parts) > 3:
        raise UnreadableRangeError(f"{text!r} has more than three parts")
    for part in parts:
        if not _NUMBER_OR_WILDCARD.match(part):
            raise UnreadableRangeError(
                f"{text!r} holds {part!r}, which is not a number"
            )
    named: list[int] = []
    for part in parts:
        if part in _WILDCARD:
            break
        named.append(int(part))
    if named and named[0] >= BEYOND[0]:
        raise UnreadableRangeError(
            f"{text!r} names a major beyond what this reader counts"
        )
    if not named:
        return LOWEST, BEYOND, 0
    if len(named) == 1:
        return (named[0], 0, 0), (named[0] + 1, 0, 0), 1
    if len(named) == 2:
        return (named[0], named[1], 0), (named[0], named[1] + 1, 0), 2
    return (named[0], named[1], named[2]), (named[0], named[1], named[2] + 1), 3


def _comparator(operator: str, text: str) -> Admitted:
    """One comparator, as the versions it admits."""
    low, high, named = _partial(text)
    if operator in ("", "="):
        return ((low, high),) if named else EVERYTHING
    if operator == ">":
        return NOTHING if named == 0 else ((high, BEYOND),)
    if operator == ">=":
        return EVERYTHING if named == 0 else ((low, BEYOND),)
    if operator == "<":
        return NOTHING if named == 0 else ((LOWEST, low),)
    if operator == "<=":
        return EVERYTHING if named == 0 else ((LOWEST, high),)
    if operator == "~":
        if named == 0:
            return EVERYTHING
        if named == 1:
            return ((low, (low[0] + 1, 0, 0)),)
        return ((low, (low[0], low[1] + 1, 0)),)
    if operator == "^":
        if named == 0:
            return EVERYTHING
        major, minor, patch = low
        if major > 0 or named == 1:
            return ((low, (major + 1, 0, 0)),)
        if minor > 0 or named == 2:
            return ((low, (0, minor + 1, 0)),)
        return ((low, (0, 0, patch + 1)),)
    raise UnreadableRangeError(f"{operator!r} is not an operator this reader knows")


def _merge(intervals: list[Interval]) -> Admitted:
    """Sorted, disjoint and merged, dropping the empty ones."""
    merged: list[Interval] = []
    for low, high in sorted(pair for pair in intervals if pair[0] < pair[1]):
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return tuple(merged)


def _both(left: Admitted, right: Admitted) -> Admitted:
    """What two ranges admit between them -- the `and` of a comparator set."""
    return _merge(
        [
            (max(a_low, b_low), min(a_high, b_high))
            for a_low, a_high in left
            for b_low, b_high in right
        ]
    )


def _without(left: Admitted, right: Admitted) -> Admitted:
    """What the first admits and the second does not. The whole rule."""
    kept: list[Interval] = []
    for low, high in left:
        cursor = low
        for taken_low, taken_high in right:
            if taken_high <= cursor or taken_low >= high:
                continue
            if taken_low > cursor:
                kept.append((cursor, min(taken_low, high)))
            cursor = max(cursor, taken_high)
            if cursor >= high:
                break
        if cursor < high:
            kept.append((cursor, high))
    return _merge(kept)


def _alternative(text: str) -> Admitted:
    """One branch of a `||`: a hyphen range, or comparators `and`-ed."""
    body = text.strip()
    if not body:
        return EVERYTHING
    hyphen = _HYPHEN.match(body)
    if hyphen is not None:
        low, _, _ = _partial(hyphen.group(1))
        _, high, named = _partial(hyphen.group(2))
        return _merge([(low, BEYOND if named == 0 else high)])
    kept = EVERYTHING
    position = 0
    read = 0
    while position < len(body):
        match = _COMPARATOR.match(body, position)
        if match is None:
            raise UnreadableRangeError(
                f"{text!r} does not read as a version expression"
            )
        kept = _both(kept, _comparator(match.group(1) or "", match.group(2)))
        position = match.end()
        while position < len(body) and body[position].isspace():
            position += 1
        read += 1
    if read == 0:
        raise UnreadableRangeError(f"{text!r} does not read as a version expression")
    return kept


def _admitted(spec: str) -> Admitted:
    """Every version a whole `engines.node` range admits.

    `||` is a union of branches, whitespace inside a branch is an
    intersection of comparators. Those two rules and `_partial` are the
    entire grammar.
    """
    whole: Admitted = NOTHING
    for alternative in spec.split("||"):
        whole = _merge([*whole, *_alternative(alternative)])
    return whole


def _spell(admitted: Admitted) -> str:
    """A set of intervals written back as a range a reader can compare
    with the one in the file."""
    if not admitted:
        return "nothing"
    branches = [
        f">={low[0]}.{low[1]}.{low[2]}"
        if high == BEYOND
        else f">={low[0]}.{low[1]}.{low[2]} <{high[0]}.{high[1]}.{high[2]}"
        for low, high in admitted
    ]
    return " || ".join(branches)


# --------------------------------------------------------------------------
# The trees
# --------------------------------------------------------------------------


def _tracked(pattern: str) -> list[str]:
    """Every tracked path matching `pattern`, from the index.

    The index rather than a directory walk: `node_modules/` holds
    thousands of `package.json` files a walk would read, none of them this
    repository's, and a fresh clone has none of them at all.
    """
    found = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", pattern],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(line for line in found.stdout.splitlines() if line)


def _requirements(relative: str) -> tuple[Requirement, ...]:
    """Every `engines.node` a lock file records for a package it installs.

    The tree's own entry is left out -- that is the declaration being
    checked, not a requirement on it -- and so is every entry the lock
    file marks `optional`, for the reason this module's docstring gives.
    """
    lock = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    found: list[Requirement] = []
    for name, entry in (lock.get("packages") or {}).items():
        if not name or not isinstance(entry, dict) or entry.get("optional") is True:
            continue
        spec = (entry.get("engines") or {}).get("node")
        if isinstance(spec, str):
            found.append(
                Requirement(name, str(entry.get("version")), spec, _admitted(spec))
            )
    return tuple(found)


def npm_trees() -> tuple[Tree, ...]:
    """Every tracked `package.json` with the lock file beside it."""
    trees: list[Tree] = []
    for relative in _tracked("*package.json"):
        manifest = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        engines = manifest.get("engines")
        declared = engines.get("node") if isinstance(engines, dict) else None
        assert isinstance(declared, str), (
            f"{relative} declares no engines.node, so npm has nothing to "
            "check a maintainer's Node against"
        )
        lock = Path(relative).with_name("package-lock.json").as_posix()
        assert (ROOT / lock).is_file(), (
            f"{relative} has no {lock} beside it, so no floor can be derived for it"
        )
        trees.append(Tree(relative, lock, declared, _requirements(lock)))
    return tuple(trees)


def node_line() -> Admitted:
    """The Node line `.nvmrc` names, as the versions it resolves to.

    A bare `24` is a version expression like any other, so the same reader
    answers it: it admits every 24.x, which is what `actions/setup-node`
    resolves it to. A `.nvmrc` saying `lts/*` or `node` is not a version
    expression, and this raises rather than inventing a window for it.
    """
    written = (ROOT / NODE_LINE).read_text(encoding="utf-8").strip()
    assert written, f"{NODE_LINE} is empty, so it names no Node at all"
    return _admitted(written)


def shortfall(tree: Tree, line: Admitted) -> str | None:
    """What is wrong with one tree's `engines.node`, or `None`.

    Takes the tree rather than reading one, so the rule can be shown a
    declaration this repository does not hold -- which is how
    `test_the_rule_refuses_the_declaration_this_module_was_written_for`
    proves it bites.
    """
    declared = _both(_admitted(tree.declared), line)
    if not declared:
        return (
            f"{tree.manifest} declares engines.node {tree.declared!r}, which "
            f"admits no version of the Node line {NODE_LINE} names "
            f"({_spell(line)}) -- so npm refuses the runtime every workflow "
            "installs"
        )
    allowed = line
    for requirement in tree.requirements:
        allowed = _both(allowed, requirement.admits)
    over = _without(declared, allowed)
    if not over:
        return None
    raised = sorted(
        f"{requirement.package} {requirement.version} requires {requirement.spec!r}"
        for requirement in tree.requirements
        if _without(over, requirement.admits)
    )
    if allowed:
        low = allowed[0][0]
        measured = f"The floor {tree.lockfile} measures is {low[0]}.{low[1]}.{low[2]}"
    else:
        measured = (
            f"{tree.lockfile} leaves no version of that line at all: its "
            "dependencies disagree with each other"
        )
    return (
        f"{tree.manifest} declares engines.node {tree.declared!r}, which "
        f"admits {_spell(over)} -- Node its own lock file refuses: "
        f"{'; '.join(raised)}. {measured}"
    )


# --------------------------------------------------------------------------
# The reader, before anything rests on it
# --------------------------------------------------------------------------


def test_the_sweep_reads_every_tree_and_every_lock_file() -> None:
    """Non-vacuity, on both halves at once. A sweep finding no tree, or
    trees whose lock files record no `engines.node`, leaves the rule below
    comparing nothing with nothing and passing."""
    trees = npm_trees()
    assert len(trees) >= 6, (
        f"the sweep found {[tree.manifest for tree in trees]}, which is not "
        "this repository's npm trees -- the rule below would pass over them"
    )
    recorded = sum(len(tree.requirements) for tree in trees)
    assert recorded > 200, (
        f"the lock files between them record {recorded} engines.node "
        "entries, which is far fewer than they hold -- the reader is "
        "looking in the wrong place and every floor below is 24.0.0 by "
        "default"
    )
    assert any(
        requirement.package == "node_modules/jsdom"
        for tree in trees
        for requirement in tree.requirements
    ), (
        "no tree records jsdom's own engines.node, and jsdom is the package "
        "this module exists downstream of -- the lock file reader has "
        "stopped seeing the entries it is for"
    )


def test_the_line_comes_out_of_the_one_file_that_names_it() -> None:
    """The window is read out of `.nvmrc`, so raising that file moves what
    every comparison below is made inside. The tests further down name 24
    on purpose -- they are about the reader and about the defect this
    module was written for -- and the rule itself names no version at
    all."""
    written = (ROOT / NODE_LINE).read_text(encoding="utf-8").strip()
    assert node_line() == _admitted(written)
    assert len(node_line()) == 1, (
        f"{NODE_LINE} says {written!r}, which resolves to more than one "
        "stretch of versions -- a runner installs one release, so a window "
        "in two pieces is a file this module cannot reason about"
    )


def _admits(admitted: Admitted, version: Version) -> bool:
    """Whether one version falls in what a range admits. The reader's
    answer in the shape `semver.satisfies` gives it, so the two can be
    compared case for case."""
    return any(low <= version < high for low, high in admitted)


def test_the_reader_agrees_with_the_published_grammar() -> None:
    """The cases that carry the reasoning, out of the 453 096 checked
    against node-semver. Each one is a shape this repository's lock files
    actually hold, and each one is a shape a regular expression reading
    for the first number in the string would answer wrongly."""
    jsdom = _admitted("^22.22.2 || ^24.15.0 || >=26.0.0")
    assert _admits(jsdom, (24, 15, 0)) and _admits(jsdom, (24, 99, 0))
    assert not _admits(jsdom, (24, 14, 1)) and not _admits(jsdom, (25, 0, 0))
    assert _admits(jsdom, (22, 22, 2)) and not _admits(jsdom, (22, 22, 1))

    vitest = _admitted("^22.12.0 || ^24.0.0 || >=26.0.0")
    assert _admits(vitest, (24, 0, 0)) and _admits(vitest, (24, 99, 99))
    assert not _admits(vitest, (25, 0, 0))

    assert _admits(_admitted(">=20.19.0 <22.0.0 || >=22.12.0"), (24, 0, 0))
    assert not _admits(_admitted(">=20.19.0 <22.0.0 || >=22.12.0"), (22, 0, 0))
    assert _admits(_admitted("6.* || 8.* || >= 10.*"), (24, 0, 0))
    assert _admits(_admitted(">=16 || 14 >=14.17"), (14, 17, 0))
    assert not _admits(_admitted(">=16 || 14 >=14.17"), (15, 0, 0))
    assert _admits(_admitted(">= 0.8.0"), (24, 0, 0))
    assert _admits(_admitted(">=v12.22.7"), (24, 0, 0))
    assert not _admits(_admitted("^20.9.0"), (24, 0, 0))
    assert _admits(_admitted("^0.0.3"), (0, 0, 3))
    assert not _admits(_admitted("^0.0.3"), (0, 0, 4))
    assert _admits(_admitted("~1.2.3"), (1, 2, 99)) and not _admits(
        _admitted("~1.2.3"), (1, 3, 0)
    )
    assert _admits(_admitted("1.2.3 - 2.3.4"), (2, 3, 4))
    assert not _admits(_admitted("1.2.3 - 2.3.4"), (2, 3, 5))
    assert _admits(_admitted("*"), (24, 0, 0))


def test_the_reader_stops_rather_than_guessing() -> None:
    """The property the whole control rests on. A reader that returned
    `EVERYTHING` for what it could not parse would report every tree clean
    the day a dependency started writing a range in a shape it had never
    seen."""
    for spec in ("lts/*", "node", ">=24.0.0-rc.1", "1.2.3.4", "&&24", ">>24"):
        with pytest.raises(UnreadableRangeError):
            _admitted(spec)


def test_the_subtraction_is_a_comparison_and_not_a_floor() -> None:
    """A disjunction is a union with holes in it, and the hole is the
    whole point: taking the lowest branch of jsdom's range reads it as
    22.22.2 and finds nothing wrong with `>=24`, and taking the highest
    reads it as 26.0.0 and condemns every tree here."""
    jsdom = _admitted("^22.22.2 || ^24.15.0 || >=26.0.0")
    line = _admitted("24")
    assert _spell(_without(_both(_admitted(">=24"), line), jsdom)) == (
        ">=24.0.0 <24.15.0"
    )
    assert _without(_both(_admitted(">=24.15.0"), line), jsdom) == NOTHING
    assert _spell(_without(line, _admitted("^20.9.0"))) == ">=24.0.0 <25.0.0"


# --------------------------------------------------------------------------
# The rule
# --------------------------------------------------------------------------


def test_no_tree_admits_a_node_its_own_dependencies_refuse() -> None:
    """The rule, on this repository.

    A dependency that raises its floor lands in a lock file, and until
    this existed the only thing downstream of that was a warning on
    whichever machine happened to be old enough to see it.
    """
    line = node_line()
    refused = [
        message
        for tree in npm_trees()
        if (message := shortfall(tree, line)) is not None
    ]

    assert refused == [], (
        "a package.json admits a Node version its own installed "
        "dependencies refuse, so `npm install` warns where nothing in this "
        "repository said it would:\n" + "\n".join(refused)
    )


def test_the_rule_refuses_the_declaration_this_module_was_written_for() -> None:
    """`>=24`, against `app/`'s real lock file: the state this repository
    was in, refused, with the package named.

    A rule whose only evidence is an empty list is a rule nobody can tell
    apart from one that reads nothing, and this module's own subject is
    that a control can look right and answer wrongly.
    """
    app = next(tree for tree in npm_trees() if tree.manifest == "app/package.json")
    message = shortfall(app._replace(declared=">=24"), node_line())

    assert message is not None
    assert "app/package.json" in message
    assert "node_modules/jsdom" in message
    assert ">=24.0.0 <24.15.0" in message
    assert "24.15.0" in message


def test_the_rule_passes_a_tree_whose_dependencies_ask_for_nothing() -> None:
    """The other direction, on a tree written here rather than on one of
    this repository's, so that the two halves are shown on declarations
    that cannot both be true of the same file."""
    line = _admitted("24")
    modest = Tree(
        "made-up/package.json",
        "made-up/package-lock.json",
        ">=24",
        (Requirement("node_modules/anything", "1.0.0", ">=18", _admitted(">=18")),),
    )
    assert shortfall(modest, line) is None

    excluded = modest._replace(declared=">=26")
    message = shortfall(excluded, line)
    assert message is not None and "admits no version of the Node line" in message
