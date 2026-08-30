"""Where a file the instance owns has to sit.

`config/boundary.yml` and each configuration file's own `owner:` header say
*which* paths belong to the instance. Between them they are complete, they
are machine-read, and until the tree was sorted they were also invisible:
`data/`, `keys/` and `public-data/` sat at the root between `app/` and
`site/`, and four of the six files in `config/` were the instance's while
two were the product's. A duplicate opening the repository could not see
the line it was about to merge across.

So the line is a directory now. Everything the declaration hands over
lives under `instance/`, and this module is what keeps it there: it reads
the declaration, walks the tracked tree, and refuses a file the boundary
calls the instance's that sits anywhere else. That is the check that stops
the next person putting an instance file back at the root -- not a
convention anybody has to remember, and not a review anybody has to do
twice.

**The one exception is declared, not typed here.**
`docs/governance/register.md` is the instance's and does not move: it is
written for a volunteer to read, two handbook pages link to it and the
cockpit publishes it, all of which break if it moves. The rule below
therefore admits any entry the declaration *itself* places outside
`instance/`, and a separate assertion holds that set to the one path this
repository decided on -- so widening it is an edit somebody has to make
here, in front of the reason.

**Tracked files, and only those.** The boundary exists because a duplicate
updates by merging, and a merge is an event about tracked files. An
ignored build artefact under a declared directory (`instance/public-data/`
is empty in a fresh clone and `.gitignore` names the three files a running
instance commits into it) is nobody's to merge.

**What this does not cover.** Whether a path is the instance's at all --
that is `test_boundary.py`'s question, and this module takes its answer.
Nor does it look at content: a product file under `instance/` that holds
this series' own identity is `test_second_instance.py`'s to find, and a
`.py` under a declared directory is `test_boundary.py`'s clause 2.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

import pytest
from test_cross_references import _tracked

from convener_ops.declaration import boundary
from convener_ops.declaration.boundary import INSTANCE, PRODUCT, Boundary, Handed, Kept
from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()

#: The directory every path the instance owns sits under, spelt with the
#: separator the declaration spells its own paths with.
INSTANCE_DIR: Final = "instance/"


def board() -> Boundary:
    """The boundary this repository declares, read inside a function.

    A derived repository is entitled not to have the paths this reads
    until its own derivation lays them in, and a read at module scope
    would take the whole module down at collection rather than failing
    the tests that are about the declaration
    (`test_boundary.py::test_no_test_module_reads_an_instance_path_while_it_loads`).
    """
    return boundary.load(ROOT)


def declared_elsewhere(known: Boundary) -> tuple[str, ...]:
    """Every path the declaration itself puts outside `instance/`.

    Read from the declaration rather than listed here: an entry that sits
    somewhere else carries its own argument for doing so, next to the
    path, and this is that argument being honoured rather than restated.
    """
    return tuple(
        sorted(
            entry.path
            for entry in known.handed
            if not entry.path.startswith(INSTANCE_DIR)
        )
    )


def misplaced(known: Boundary, names: Iterable[str]) -> tuple[str, ...]:
    """The paths in `names` the instance owns and that sit elsewhere.

    Pure, and separate from the walk below, so the rule can be exercised
    against a list somebody made up rather than only against whatever this
    repository happens to hold today.
    """
    allowed = declared_elsewhere(known)
    return tuple(
        sorted(
            name
            for name in names
            if known.owner_of(name) == INSTANCE
            and not name.startswith(INSTANCE_DIR)
            and name not in allowed
        )
    )


def kept_by_the_product(known: Boundary) -> tuple[str, ...]:
    """Every file the product keeps inside a directory the instance owns."""
    return tuple(sorted(kept.path for entry in known.handed for kept in entry.kept))


# ------------------------------------------------------------------ #
# The exception is one, and it is the one that was argued for
# ------------------------------------------------------------------ #


def test_the_one_declared_path_outside_the_directory_is_the_register() -> None:
    """The anchor. The rule below admits whatever the declaration places
    outside `instance/`, so without this it could be widened by adding an
    entry and nobody would have had to decide anything."""
    assert declared_elsewhere(board()) == ("docs/governance/register.md",)


# ------------------------------------------------------------------ #
# The rule itself
# ------------------------------------------------------------------ #


def test_the_walk_sees_a_tree_it_could_fail_on() -> None:
    """A sweep that quietly read nothing would make the rule below pass
    over an empty list, which is how a check stops meaning anything."""
    tracked = _tracked()
    assert len(tracked) > 400, f"the walk found {len(tracked)} tracked files"
    assert "instance/data/config.yml" in tracked
    assert "instance/queue-drain.yml" in tracked
    assert "docs/governance/register.md" in tracked


def test_every_file_the_instance_owns_sits_under_the_instance_directory() -> None:
    """The clause that bites, over the files this repository really holds.

    Both halves of the declaration are asked: a path handed over by
    `config/boundary.yml`, and a configuration file whose own header says
    `owner: instance`. A file of either kind at the root, or in `config/`,
    or anywhere else, is a file a reader cannot see the boundary of.
    """
    offenders = misplaced(board(), _tracked())

    assert offenders == (), (
        "these are the instance's and do not sit under "
        f"{INSTANCE_DIR}: {', '.join(offenders)}. Everything "
        f"{boundary.DECLARATION_PATH.as_posix()} and a configuration "
        f"file's own `owner:` header hand to the instance lives under "
        f"{INSTANCE_DIR}, so that the line a duplicate merges across is "
        "visible in the tree rather than only in a declaration."
    )


def test_nothing_under_the_instance_directory_is_the_product_s_but_what_it_keeps() -> (
    None
):
    """The other direction, which is what makes the directory readable.

    `instance/` says *the instance's* to somebody who opens it, and a
    product file inside it would make that a guess again. Two exist, both
    declared `kept:` with their reasons and both documentation of a
    contract that lives where an operator will meet it, and they are
    read from the declaration rather than named here.
    """
    known = board()
    kept = kept_by_the_product(known)
    found = [
        name
        for name in _tracked()
        if name.startswith(INSTANCE_DIR)
        and known.owner_of(name) == PRODUCT
        and name not in kept
    ]

    assert found == [], (
        f"these sit under {INSTANCE_DIR} and are the product's, without "
        f"being one of the files it declares it keeps there: "
        f"{', '.join(found)}"
    )


# ------------------------------------------------------------------ #
# The rule bites, and it admits what the declaration admits
# ------------------------------------------------------------------ #


@pytest.fixture
def made_up() -> Boundary:
    """A boundary in the shape the real one has, made up here.

    Deliberately not this repository's: a fixture that tracked the real
    declaration would make the assertions below restate the thing they are
    meant to check.
    """
    return Boundary(
        handed=(
            Handed(
                path="instance/records/",
                reason="the instance's own records",
                kept=(Kept("instance/records/schema.md", "the product's model"),),
            ),
            Handed(path="elsewhere/ledger.md", reason="two pages link to it"),
        ),
        config_owners={
            "instance/thresholds.yml": INSTANCE,
            "config/integrations.yml": PRODUCT,
        },
    )


@pytest.mark.parametrize(
    "name",
    [
        "records/config.yml",
        "records/events/mrg-042/registrations.enc",
        "config/thresholds.yml",
    ],
)
def test_a_path_put_back_outside_the_directory_is_refused(name: str) -> None:
    """A declaration with the records at the root again, and a
    configuration file the instance owns left in the product's own
    directory -- the two shapes this repository was in before the move,
    and the two a later commit could put it back into."""
    put_back = Boundary(
        handed=(
            Handed(path="records/", reason="the instance's own records"),
            Handed(path="elsewhere/ledger.md", reason="two pages link to it"),
        ),
        config_owners={"config/thresholds.yml": INSTANCE},
    )

    assert misplaced(put_back, [name]) == (name,)


@pytest.mark.parametrize(
    "name",
    [
        "instance/records/config.yml",
        "instance/thresholds.yml",
        "elsewhere/ledger.md",
        "instance/records/schema.md",
        "config/integrations.yml",
        "app/src/main.tsx",
    ],
)
def test_a_path_the_declaration_admits_is_left_alone(
    made_up: Boundary, name: str
) -> None:
    """The load-bearing half: two under the directory, one the declaration
    itself places elsewhere, one the product keeps inside it, and two that
    were never the instance's at all."""
    assert misplaced(made_up, [name]) == ()
