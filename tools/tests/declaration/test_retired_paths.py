"""`retired:` held against the history it makes a claim about.

`declarations/boundary.yml` answers two questions with two lists. `instance:`
is present tense -- whose is this path now -- and it is what a working tree,
the settings screen and a second-instance build ask. `retired:` is the other
one: whose were the bytes ever stored at this path. `Boundary.ever_owned` is
`owner_of` widened by that second list, and anything walking this
repository's commits rather than its working tree reads the widened answer.

**The list widens *instance* ownership, which is why a wrong entry in it is
not a harmless precaution.** Whatever reads a history through `ever_owned`
treats everything a retired entry covers as the instance's and not the
product's -- so an entry naming a directory the *product* renamed says that
the product's own past was somebody's private data, and a public copy made
by that reading arrives with the whole of that past missing. Nothing about
such an entry looks wrong: it names a path that existed, does not exist now,
and is not handed to the instance, which is everything the parser can see.
`boundary.retirements_must_land_where_the_instance_is` closes the part of
that a declaration can close, at load, by refusing an entry whose `became:`
is not a path the instance owns today. This module closes the rest, against
this repository's own commits.

Four readings, and none of them is the others
---------------------------------------------
* **The bytes.** Every object ever stored under a retired path, looked for
  at the tip. A rename that changes nothing writes no new blob, so a blob
  still tracked at a path the product owns is the same bytes under a new
  name -- no similarity threshold, no `--follow`, and nothing to tune.
* **The rename git can see.** The reading above is exact and easy to slip
  past without meaning to: every directory renamed here so far was renamed
  *and* edited in one commit, because the prose inside it named its own old
  path, and not one shared blob survived that. So the second reading asks
  git where `--find-renames` says the files went, which is how a reader
  would find it.
* **The destination, against the act.** Both readings above ask about the
  tip, so both pass in silence over a path that was **deleted** rather than
  moved: no tip copy to find, no rename to detect. What closes that is the
  act. A move is one commit -- the place it leaves goes empty in the same
  breath as the place it arrives at is written -- so the commit that took
  the last file out of a retired path has to be the commit that wrote
  `became:`.
* **That each entry was ever the instance's at all.** An entry covering
  nothing this history recorded excludes nothing and misleads the next
  reader about what this repository once looked like.

Why the third reading is about the *act* and not about content
--------------------------------------------------------------
It used to be about lines: something stored under the retired path had to
still be readable at its destination. Resemblance is not provenance.
`examples/` holds one file per path the instance owns, at the same relative
path, so a file there resembles an instance file by construction -- and an
entry retiring the worked example's own charter with `became: instance/data/`
shared lines with the instance's charter for no better reason than both
being a `brand.json`. It satisfied every reading, and it withheld a file the
product owns from every copy made by that reading. A resemblance cannot
forge an act, which is why the reading is the act.

Where this lives, and why it is not in `test_boundary.py`
---------------------------------------------------------
`test_boundary.py` opens by ruling git history out of its own scope, and
that exclusion is load-bearing rather than incidental: the rule it holds is
about the repository as the product ships it, and a check reading the past
to make a claim about the next pull request would be worse than none. Every
reading here is a reading of the past, and is sound only because the claim
it makes is about the past -- where the instance's files *were*. Two
opposite rules about the same declaration, so two modules, beside each
other and beside the file they are both about.

What none of this covers, said here rather than discovered
-----------------------------------------------------------
A move split across two commits, one deleting and a later one adding.
Nothing in this repository is one, and an entry for one is refused here
rather than passed -- the stricter of the two answers, and the one that does
not rest on a destination happening to resemble a source.
"""

from __future__ import annotations

import subprocess  # nosec B404
from collections.abc import Iterable
from typing import Final

import pytest

from convener_ops.declaration.boundary import PRODUCT, Boundary, Handed, load
from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()

#: The worked example's own charter, deleted on the day that example took to
#: naming one of the product's rather than writing one of its own. A path the
#: product owns that looks exactly like a path the instance owns, which is
#: what `examples/` is built to be, and what the reading below is measured
#: against rather than argued at.
EXAMPLE_CHARTER: Final = "examples/the-example-collective/instance/data/brand.json"

#: The six one-shot migrations, deleted rather than renamed. The deletion
#: the two tip readings pass over in silence, and the measurement that
#: started the third one.
DELETED_DIRECTORY: Final = "tools/migrations/"

#: Whether this repository holds the half that produces the product
#: repository. `declarations/boundary.yml` keeps `convener_ops/derivation/`
#: out of what it produces, so this is present here and absent in the
#: product and in every duplicate made from it.
#:
#: It is the precondition of every reading in this module, stated as the
#: one fact that distinguishes the two. Each reading asks this
#: repository's own commits where the instance's files used to be, and
#: a derived history is not the history those moves happened in: the
#: derivation filters the instance's paths out of every commit it carries
#: over, so a move it did carry arrives with the place it left already
#: empty. `keys/`, `config/instance.json` and five more entries name
#: nothing at all there -- correctly, and for a reason no repository
#: reading them can do anything about.
#:
#: Deliberately not a retired path, the way the same guard in
#: `tools/tests/derivation/test_repository.py` is: every retired path is a
#: subject of the readings below, so probing one of them would be the
#: check excusing itself with its own finding. This is measured outside
#: the declaration instead.
#:
#: Deliberately not `instance_identity.ships_the_example_as_its_instance`
#: either, which is the condition twenty-seven other tests abstain on. It
#: lifts the moment a duplicate declares its own values -- and a
#: duplicate's history is still the derived one, so these three would come
#: back red on the day that duplicate was configured, for the one reason
#: it can never fix.
AUTHORS_THE_DECLARATION: Final = (
    ROOT / "tools" / "convener_ops" / "derivation"
).is_dir()

NOT_THE_HISTORY_THESE_MOVES_HAPPENED_IN: Final = (
    "this repository does not hold the derivation, so its history is one "
    "the derivation produced: the instance's paths were filtered out of "
    "every commit, and the acts `retired:` describes are not in it to be "
    "read. The declaration is still inherited whole and is still checked "
    "where it is written"
)

#: The whole module and not the three that went red. Four of the seven
#: readings below pass in a derived repository by finding nothing, which
#: is a check that cannot fail -- the shape this project treats as worse
#: than a missing one, because it passes on the day it is written and
#: again on the day the defect comes back. Three of them find nothing and
#: say so. All seven read the same history, so all seven abstain on the
#: same fact rather than three abstaining and four reporting green about
#: a history they never had.
pytestmark = pytest.mark.skipif(
    not AUTHORS_THE_DECLARATION,
    reason=NOT_THE_HISTORY_THESE_MOVES_HAPPENED_IN,
)


def _git(*args: str) -> str:
    return subprocess.run(  # nosec B603 B607
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def historical_blobs() -> tuple[tuple[str, str], ...]:
    """Every `(object name, path)` any commit in this repository ever
    recorded.

    Trees appear too and carry a path with no trailing slash; they are left
    in deliberately, because a tree's own name is one of the two spellings a
    caller with a directory can have and `Handed.covers` answers both.
    """
    pairs: list[tuple[str, str]] = []
    for line in _git("rev-list", "--objects", "--all").splitlines():
        name, _, path = line.partition(" ")
        if path:
            pairs.append((name, path.strip()))
    return tuple(pairs)


def files_ever_under(path: str) -> set[str]:
    """Every *file* any commit ever wrote under `path`.

    `git log --name-only` rather than `rev-list --objects`, because this is
    the one reading that has to be able to say "nothing" and a tree object
    would answer for a directory that only ever held somebody else's file.
    """
    listing = _git("log", "--all", "--format=", "--name-only", "--", path.rstrip("/"))
    return {line.strip() for line in listing.splitlines() if line.strip()}


def instance_files_under(entry: Handed) -> set[str]:
    """Every file this history recorded that `entry` says was the
    instance's. `Handed.covers` is what takes the entry's own `kept:` files
    back out, so a retired directory that only ever held one file the
    product keeps answers with nothing."""
    return {name for name in files_ever_under(entry.path) if entry.covers(name)}


#: Whether this history carries what `retired:` is a claim about.
#:
#: The entries say where the instance's own files sat. A history in which no
#: entry covers a single file -- only the `kept:` ones the product owns
#: inside them, or nothing at all -- is a history those files were never
#: written into: a copy published with them filtered out, or a duplicate
#: standing up from such a copy and carrying its own records from its first
#: commit. Every reading guarded by this would then be about a past this
#: repository does not have, and would report a clean sweep it never made.
#:
#: Asked of the declaration rather than of one path chosen by hand, so a
#: duplicate that retires a path of its own is read rather than skipped from
#: the day it does. It is deliberately *any* entry and not *every* entry: a
#: single bogus entry among sound ones leaves this true, and the readings
#: below then have the bogus one to find.
_RETIRED_HISTORY: Final = any(instance_files_under(entry) for entry in load().retired)
_NO_RETIRED_HISTORY: Final = (
    "no retired entry covers a file this history ever recorded, so the "
    "instance's own records were never written into it and there is "
    "nothing here for this reading to be about"
)


def tracked_blobs() -> dict[str, str]:
    """`{object name: path}` for every file in the index."""
    out: dict[str, str] = {}
    for line in _git("ls-files", "-s").splitlines():
        meta, _, path = line.partition("\t")
        fields = meta.split()
        if len(fields) >= 2 and path:
            out[fields[1]] = path.strip()
    return out


def _covered(board: Boundary, path: str) -> Iterable[str]:
    """The retired entries covering `path`, if any."""
    return [entry.path for entry in board.retired if entry.covers(path)]


def _under(prefix: str, path: str) -> bool:
    """Whether `path` is `prefix` or sits inside it, for a `prefix` that may
    be spelled as a directory or as a single file."""
    return path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")


def emptying_commit(path: str) -> str | None:
    """The commit that took the last file out of `path`, or `None` if no
    commit ever deleted anything under it.

    The most recent deletion rather than every one: a directory loses a file
    now and then while it is still in use, and the act a retirement is about
    is the one after which nothing under the path was left.
    """
    commits = _git(
        "log", "--all", "--diff-filter=D", "--format=%H", "--", path.rstrip("/")
    ).split()
    return commits[0] if commits else None


def paths_touched(commit: str) -> set[str]:
    """Every path `commit` wrote, both sides of a rename.

    `-M` so that a move reports where it landed rather than one deletion and
    one unrelated addition; both sides are kept because the reading below
    discards the retired path's own side by name and wants whatever else the
    commit did.
    """
    found: set[str] = set()
    for line in _git("show", "-M", "--name-status", "--format=", commit).splitlines():
        fields = line.split("\t")
        found |= {field.strip() for field in fields[1:] if field.strip()}
    return found


def spelled_today(board: Boundary, path: str) -> str:
    """`path` as this declaration spells it now, through any retirement
    covering it.

    The one place `retired:` is read *forwards*. A commit from before a move
    wrote the paths of its own day, so asking whether it wrote
    `instance/config.json` is asking the wrong question of
    `site/src/_data/site.json`'s folding commit: it wrote
    `config/instance.json`, which is what `instance/config.json` was called
    then, and this declaration is the only thing that knows those are one
    file.
    """
    for entry in board.retired:
        if not entry.covers(path):
            continue
        if not entry.path.endswith("/"):
            return entry.became
        tail = path[len(entry.path) :]
        return entry.became.rstrip("/") + "/" + tail if tail else entry.became
    return path


def landed_at(board: Boundary, entry: Handed, destination: str) -> list[str]:
    """Every path the act that emptied `entry.path` wrote at or under
    `destination`, spelled as the declaration spells it now.

    The entry's own path is never one of them: the commit that emptied it
    deleted it, so counting that deletion would let every entry answer for
    itself out of the very act it is a claim about -- which is how a path
    that merely resembles an instance path used to pass.
    """
    commit = emptying_commit(entry.path)
    if commit is None:
        return []
    return sorted(
        {
            name
            for name in paths_touched(commit)
            if not entry.covers(name)
            and _under(destination, spelled_today(board, name))
        }
    )


def renames_out_of(path: str) -> list[tuple[str, str]]:
    """`(before, after)` for every rename git detects in a commit that
    deleted something under `path`.

    `git show -M` per commit rather than one sweep, because rename detection
    is a property of a single diff: a file deleted in one commit and added
    in another is not a rename to git, and this makes no claim that it is.
    """
    commits = _git("log", "--all", "--diff-filter=D", "--format=%H", "--", path).split()
    out: list[tuple[str, str]] = []
    for commit in commits:
        listing = _git("show", "-M", "--name-status", "--format=", commit)
        for line in listing.splitlines():
            fields = line.split("\t")
            if len(fields) == 3 and fields[0].startswith("R"):
                out.append((fields[1].strip(), fields[2].strip()))
    return out


# ------------------------------------------------------------------ #
# The two readings of the tip
# ------------------------------------------------------------------ #


def test_no_retired_entry_drops_bytes_the_product_still_ships() -> None:
    """The exact reading, and the cheap one.

    A product directory renamed keeps its blobs; retiring the old name says
    those blobs were the instance's, and every copy made by reading this
    list then loses them. Nothing in the entry's own shape says so, which is
    why this is measured against the tip rather than read.
    """
    board = load()
    tip = tracked_blobs()
    wrong: list[str] = []
    for name, path in historical_blobs():
        entries = list(_covered(board, path))
        if not entries:
            continue
        at_tip = tip.get(name)
        if at_tip is None or board.owner_of(at_tip) != PRODUCT:
            continue
        wrong.append(f"{entries[0]} covers {path}, whose bytes are {at_tip} today")
    assert not wrong, (
        "a `retired:` entry names a path holding bytes this repository still "
        f"tracks as the product's: {sorted(set(wrong))}. `retired:` widens "
        "*instance* ownership over this repository's history, so an entry "
        "for a product path renamed says the product's own past was private "
        "data and takes it out of every copy made by reading this list. A "
        "product directory that moves needs no entry at all."
    )


def test_no_retired_entry_renames_a_path_the_product_still_owns() -> None:
    """The reading that catches a directory renamed *and* edited at once,
    which is every rename this repository has made.

    A retired entry is a statement that the instance's files used to sit
    there. If git can see that what sat there is a path the product owns
    today, the entry is about a product move.
    """
    board = load()
    tip = set(tracked_blobs().values())
    wrong: list[str] = []
    for entry in board.retired:
        for before, after in renames_out_of(entry.path):
            if not entry.covers(before):
                continue
            if after in tip and board.owner_of(after) == PRODUCT:
                wrong.append(f"{entry.path} covers {before}, which is {after} today")
    assert not wrong, (
        "a `retired:` entry names a path git can see was renamed to one the "
        f"product owns today: {sorted(set(wrong))}. The entry claims the "
        "instance's files sat there and git says the product's did, and it "
        "is the entry that decides what a history reader may not carry. A "
        "product directory that moves needs no entry at all."
    )


def test_every_retired_path_held_the_instance_s_own_files() -> None:
    """The other half, and the positive statement a reader of the list
    needs: every entry names somewhere this instance's own files sat.

    Stated as *the instance's* files rather than as any file, because a
    retired directory whose only recorded content is the one file the
    product keeps inside it excludes nothing and says nothing -- the
    `kept:` clause has already taken that file back out.
    """
    if not _RETIRED_HISTORY:
        pytest.skip(_NO_RETIRED_HISTORY)
    board = load()
    assert board.retired, "no retirement declared; this module holds nothing"
    empty = [entry.path for entry in board.retired if not instance_files_under(entry)]
    assert not empty, (
        f"{empty} are retired, and no commit in this repository ever wrote a "
        "file under them that the entry itself covers. An entry here says "
        "where the instance's files used to be; one covering nothing this "
        "history recorded excludes nothing and misleads the next reader "
        "about what this repository once looked like"
    )


# ------------------------------------------------------------------ #
# The destination each entry declares, held against the act
# ------------------------------------------------------------------ #


def test_the_readings_below_have_something_to_read() -> None:
    """Non-vacuity. A `git log` that found no deletion, or a `git show` that
    listed no path, would make the reading below pass on an empty set, which
    is the shape of a control that has quietly stopped being one."""
    if not _RETIRED_HISTORY:
        pytest.skip(_NO_RETIRED_HISTORY)
    for entry in load().retired:
        commit = emptying_commit(entry.path)
        assert commit is not None, (
            "no commit in this history ever deleted anything under "
            f"{entry.path}, so the reading below has no act to read"
        )
        assert paths_touched(commit), (
            f"{commit} is the act that emptied {entry.path}, and git lists "
            "no path on it, so the reading below would compare against "
            "nothing"
        )


def test_git_agrees_with_the_destination_every_retirement_declares() -> None:
    """`became:` is declared, so the readings that *can* see a move are what
    hold it honest.

    Where git detects a rename out of a retired path, that rename's target
    is where the content went, and `became:` claims to be the same place.
    The two disagreeing means one of them is wrong, and the declared one is
    the one a history reader believes.

    Every file under the entry counts here, `kept:` ones included: a
    directory's move is the directory's move, and `keys/`'s only detected
    rename is the product's own readme going to `instance/keys/signing/`.
    Filtering that out is what left `keys/` with no visible destination when
    this was measured.
    """
    board = load()
    wrong: list[str] = []
    for entry in board.retired:
        for before, after in renames_out_of(entry.path):
            if not _under(entry.path, before):
                continue
            if not _under(entry.became, after):
                wrong.append(f"{before} became {after}, not {entry.became}")
    assert not wrong, (
        "a `retired:` entry declares a destination git can see its files did "
        f"not go to: {sorted(set(wrong))}. `became:` is where the entry's "
        "content is today, and it is the half of the entry nothing else "
        "checks: one pointing at an instance path its files never reached "
        "passes every ownership check and still says a history the product "
        "owns was the instance's"
    )


def test_every_retirement_is_the_act_that_wrote_the_destination_it_names() -> None:
    """The reading that catches both a *deleted* path retired and a path
    that merely *resembles* an instance path, which is the pair the tip
    readings pass over.

    A destination that is the instance's is not yet the right destination --
    there are eight instance paths in this declaration and any of them
    satisfies `boundary.retirements_must_land_where_the_instance_is`. What
    distinguishes the entry that is a move is the act: the commit that took
    the last file out of the retired path is the commit that wrote
    `became:`. Content is not asked about at all.
    """
    if not _RETIRED_HISTORY:
        pytest.skip(_NO_RETIRED_HISTORY)
    board = load()
    lost: list[str] = []
    for entry in board.retired:
        if not landed_at(board, entry, entry.became):
            lost.append(
                f"{entry.path} says it became {entry.became}, and "
                f"{emptying_commit(entry.path)} -- the act that emptied "
                "it -- wrote nothing there"
            )
    assert not lost, (
        f"{lost}. `retired:` is where the instance's paths *moved to*, so an "
        "entry whose destination no act of this repository ever wrote is a "
        "deletion wearing a move's clothes, or a path that merely looks like "
        "the instance's -- and either one hands the whole history of a path "
        "the product owns to a reader that will treat it as private data. A "
        "path the product deleted needs no entry here, and neither does a "
        "copy of an instance path the product keeps on purpose"
    )


def test_the_reading_can_tell_a_deletion_and_a_resemblance_from_a_move() -> None:
    """The positive control, on both mistakes this reading is for, run
    against this repository's own history rather than described.

    `tools/migrations/` is the deletion that started it: six one-shot
    migrations deleted rather than renamed, so neither tip reading sees
    them. `EXAMPLE_CHARTER` is the resemblance: the worked example's own
    charter, the product's, deleted on the day that example took to naming
    one of the product's charters instead of writing one -- and a
    `brand.json` shares lines with the instance's `brand.json` by being a
    `brand.json`.

    Each is asked about every path the instance owns in turn, because an
    author reaching for `became:` would try them.
    """
    if not _RETIRED_HISTORY:
        pytest.skip(_NO_RETIRED_HISTORY)
    board = load()
    for path in (DELETED_DIRECTORY, EXAMPLE_CHARTER):
        assert emptying_commit(path), f"{path} is not in this history to read"
        for landing in board.instance_paths:
            pretend = Handed(
                path=path, reason="invented for this control", became=landing
            )
            assert not landed_at(board, pretend, landing), (
                f"the act that emptied {path} wrote something at {landing}, "
                "so an entry naming it would satisfy the reading above"
            )
