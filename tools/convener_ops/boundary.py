"""Which paths an instance owns, and which ones the product keeps.

This repository is meant to be duplicated, and for a duplicate an update is
a **merge**. It succeeds when upstream's commits and the instance's commits
never touch the same file; it fails into a field of conflicts otherwise, at
which point people stop updating and the whole idea of a template dies
quietly. So "instance" cannot stay an intention -- it has to be a set of
paths something can enumerate, and this module is what reads it.

**One declaration, two halves, no copy.** `config/boundary.yml` names the
directories the instance owns whole. The configuration files `CONFIG_DIRS`
holds directly state their own answer in their own `owner:` key, next to
the argument for it, and this module reads that -- `declaration_from_data`
*refuses* a declaration that also names one of them, so the two halves can
never drift into disagreeing. That refusal is the whole point: this repository's
recurring defect is the copy (three palettes, five addresses, two path
lists), and a boundary built out of a second list would be the same defect
wearing a new name.

**The default is the product.** Everything the declaration does not name
belongs to the product: `owner_of` answers `PRODUCT` for it. A path only
becomes the instance's by being named, never by being forgotten.

**Ownership is a property of a file, not of a value**, because a merge is a
file-level event. A file holding one instance-owned value is an instance
file even when its other values would have made perfectly good product
defaults -- upstream cannot ship half a file. That is the rule that settled
`config/`, where `actions-budget.yml` mixed an organisation's GitHub
allowance with a bound on the collector's own runtime and now sits in
`instance/` for it.

What this module does **not** do is decide anything about the future. No
offline check can promise that a later upstream commit will not touch
`instance/data/`. What it can do, and what `tools/tests/test_boundary.py` builds on
top of it, is refuse the states that make such a commit *necessary* -- see
that module's own docstring for the formulation held and for what it
leaves uncovered.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

import yaml

#: The declaration itself, relative to a repository root. In `config/`
#: rather than beside it: this is the product's own statement about what
#: an instance owns, and it belongs with the product's own configuration.
DECLARATION_PATH: Final = Path("config") / "boundary.yml"

#: Where a configuration file states its own owner in its own header, and
#: the only two places one may. `config/` is the product's own directory
#: and `instance/` is this instance's, so a file's location already says
#: which side it is on; the header is what refuses, by name, the file that
#: lands on the wrong one. Only the files these directories hold
#: *directly* answer for themselves -- `instance/`'s subdirectories are
#: handed over whole, by the declaration above.
CONFIG_DIRS: Final = (Path("config"), Path("instance"))

#: What a configuration file may be written in, and how to read each. YAML
#: for anything only this repository's Python reads; JSON for anything
#: read from more than one side of the language boundary, because it is
#: the only format `site/` and `services/` can parse without a dependency
#: neither of them has and the zero-cost constraint forbids adding
#: (`instance/config.json`). Both are listed here for one reason: a
#: format nobody enumerated is a file in one of those directories whose
#: owner nothing asks for, and "every file answers" would quietly become
#: "every file we happened to look at".
CONFIG_READERS: Final[dict[str, Callable[[str], Any]]] = {
    ".yml": yaml.safe_load,
    ".json": json.loads,
}

#: `config/boundary.yml`'s own format version.
DECLARATION_VERSION: Final = 1

#: Where git is told how to merge a path, and the attribute that has to be
#: on a `regenerated:` one. See `Handed.regenerated` for the argument;
#: `tools/tests/test_boundary.py` holds the two together, so declaring a
#: path regenerated and forgetting the attribute is a failing test rather
#: than a field of conflicts in somebody else's repository a year later.
GIT_ATTRIBUTES_PATH: Final = Path(".gitattributes")
REGENERATED_MERGE_ATTRIBUTE: Final = "merge=ours"

#: The two answers, and the only two. A third would mean a path nobody has
#: decided about, which is the state this module exists to make impossible.
INSTANCE: Final = "instance"
PRODUCT: Final = "product"
OWNERS: Final = (INSTANCE, PRODUCT)

#: What makes a file *code* for the purposes of this boundary: something
#: this repository runs, imports, type-checks or lints. The list is
#: deliberately generous -- a template file the site renders is as much a
#: thing upstream fixes bugs in as a `.py` is, and the failure being
#: prevented is upstream needing to edit a path it promised never to touch.
CODE_SUFFIXES: Final = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".sh",
        ".ps1",
        ".bat",
        ".njk",
        ".css",
        ".html",
    }
)


@dataclass(frozen=True)
class Kept:
    """One file the product keeps inside a directory the instance owns.

    Not an escape hatch: every entry has to exist, has to be tracked, and
    carries its reason beside its path rather than in a document nobody
    reads at the moment it matters. Two exist today, both documentation of
    a contract that happens to live where an operator will meet it.
    """

    path: str
    reason: str


@dataclass(frozen=True)
class Handed:
    """One path the product hands to the instance.

    A directory when the path ends in `/`, otherwise a single file. The
    distinction is not cosmetic: a directory entry covers files that do not
    exist yet (an instance's own event keys, its published data), which is
    exactly what a fresh duplicate has, whereas a file entry names
    something that is in this repository right now.

    `regenerated` marks the harder case, and it is a statement about
    *upstream* rather than about the instance. Ownership says upstream will
    not edit a path; it cannot say upstream will not *run* — and upstream
    is itself a running instance, whose own scheduled jobs rewrite some of
    these paths on every push. `docs/governance/register.md` is the one
    that bites: it is a total re-rendering of one repository's own commit
    history, so upstream's copy and a duplicate's copy are both correct,
    entirely different, and rewritten on both sides between any two merges.
    Git sees two sides that changed the same lines and raises a conflict
    with no correct resolution except "mine", every time, for ever.

    So the declaration says so, and `.gitattributes` gives that path
    `merge=ours` -- git's own answer to a generated file both sides
    regenerate. It is not free: a `merge=ours` driver has to be configured
    once per clone (`git config merge.ours.driver true`), and a clone that
    has not done so falls back to exactly the conflict it has today, which
    is the right way round for a mechanism to fail. Naming the property
    here rather than only in `.gitattributes` is what lets a test refuse a
    path declared regenerated and never given the attribute.
    """

    path: str
    reason: str
    kept: tuple[Kept, ...] = ()
    regenerated: bool = False

    @property
    def is_directory(self) -> bool:
        return self.path.endswith("/")

    def covers(self, relative: str) -> bool:
        """Whether this entry hands `relative` (a POSIX, root-relative
        path) to the instance. A `kept` file inside it is not handed."""
        if any(kept.path == relative for kept in self.kept):
            return False
        if self.is_directory:
            return relative.startswith(self.path)
        return relative == self.path


@dataclass(frozen=True)
class Boundary:
    """The whole answer: the declared paths, and the headers the
    configuration files state their own owner in."""

    handed: tuple[Handed, ...]
    config_owners: Mapping[str, str]

    def owner_of(self, relative: str | Path) -> str:
        """`INSTANCE` or `PRODUCT` for one root-relative path.

        Total by construction -- an unnamed path is the product's. There is
        no "unknown": a boundary with a third answer would be a boundary
        somebody still has to interpret.
        """
        name = str(relative).replace("\\", "/")
        declared = self.config_owners.get(name)
        if declared is not None:
            return declared
        if any(entry.covers(name) for entry in self.handed):
            return INSTANCE
        return PRODUCT

    def owns_directory(self, relative: str | Path) -> bool:
        """Whether the instance owns a *directory*, everything in it
        included.

        `owner_of` answers about one path, and a caller that has a
        directory rather than a file cannot always spell it as one: `git
        rev-list --objects` names a directory by its tree object, whose
        path carries no trailing slash, and `instance/data` does not start
        with `instance/data/`. This asks the question the caller actually
        has.

        A directory holding a file the product keeps is **not** the
        instance's, whatever the entry above it says: `instance/keys/signing/`
        cannot be dropped without dropping `instance/keys/signing/README.md` with
        it, and that file is the product's by this same declaration. So
        the answer is the `kept:` answer again, applied to the only other
        kind of thing a repository holds.
        """
        directory = str(relative).replace("\\", "/").rstrip("/") + "/"
        if self.owner_of(directory) != INSTANCE:
            return False
        return not any(
            kept.path.startswith(directory)
            for entry in self.handed
            for kept in entry.kept
        )

    @property
    def regenerated_paths(self) -> tuple[str, ...]:
        """Every instance path a scheduled job rewrites in full, upstream's
        own runs included -- see `Handed.regenerated`. Sorted, computed,
        and the input to the `.gitattributes` check in
        `tools/tests/test_boundary.py`."""
        return tuple(sorted(entry.path for entry in self.handed if entry.regenerated))

    @property
    def instance_paths(self) -> tuple[str, ...]:
        """Every path an instance owns, from both halves of the
        declaration, sorted. Computed, never retyped."""
        from_config = [
            name for name, owner in self.config_owners.items() if owner == INSTANCE
        ]
        return tuple(sorted([entry.path for entry in self.handed] + from_config))


def _relative_path(raw: Any, what: str) -> str:
    """One POSIX, root-relative path, or a `ValueError` naming what it was
    supposed to be. A declaration that cannot be read must stop the check
    rather than run it against a guess: this is the file that decides what
    upstream may write, so a value it cannot read is the one thing it must
    never quietly substitute for."""
    named = DECLARATION_PATH.as_posix()
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{named}: {what} must be a non-empty path, got {raw!r}")
    path = raw.strip()
    if path != raw:
        raise ValueError(f"{named}: {what} has surrounding whitespace: {raw!r}")
    if path.startswith("/") or "\\" in path or ".." in PurePosixPath(path).parts:
        raise ValueError(
            f"{named}: {what} must be a relative POSIX path inside this "
            f"repository, got {raw!r}"
        )
    return path


def states_its_own_owner(path: str) -> bool:
    """Whether `path` is a configuration file that answers for itself.

    One of `CONFIG_DIRS` holds it directly, and it is written in a format
    `CONFIG_READERS` knows. Those two conditions are the whole of what
    `config_owners` reads, so this is the same set seen from the other
    end -- which is what lets the declaration refuse a path whose owner a
    header already states, rather than a path that merely looks like one.
    """
    named = PurePosixPath(path)
    parents = {directory.as_posix() for directory in CONFIG_DIRS}
    return named.parent.as_posix() in parents and named.suffix in CONFIG_READERS


def _reason(raw: Any, what: str) -> str:
    named = DECLARATION_PATH.as_posix()
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{named}: {what} must carry a reason")
    return raw.strip()


def _kept_from(raw: Any, inside: str) -> tuple[Kept, ...]:
    named = DECLARATION_PATH.as_posix()
    if raw is None:
        return ()
    if not inside.endswith("/"):
        raise ValueError(
            f"{named}: {inside!r} names a single file, so nothing can be kept "
            "inside it -- only a directory entry may carry kept:"
        )
    if not isinstance(raw, list):
        raise ValueError(f"{named}: {inside}'s kept: must be a list, got {raw!r}")
    kept: list[Kept] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"{named}: {inside}'s kept: holds {entry!r}, not an entry")
        path = _relative_path(entry.get("path"), f"a kept path under {inside}")
        if path.endswith("/") or not path.startswith(inside):
            raise ValueError(
                f"{named}: kept path {path!r} is not a file inside {inside!r} -- "
                "a file the product keeps has to be inside the directory it is "
                "kept out of, or naming it here says nothing"
            )
        kept.append(Kept(path=path, reason=_reason(entry.get("reason"), path)))
    return tuple(kept)


def declaration_from_data(data: Any) -> tuple[Handed, ...]:
    """Parse an already YAML-loaded `config/boundary.yml`.

    Refuses, rather than repairs, anything that is not this exact shape --
    including the two mistakes that would quietly hollow the boundary out:
    a configuration file named here (its answer belongs in its own header,
    and a second home for it is how the two start disagreeing), and one
    entry nested inside another (whichever is read first wins, silently).
    """
    named = DECLARATION_PATH.as_posix()
    if not isinstance(data, dict) or data.get("v") != DECLARATION_VERSION:
        raise ValueError(f"{named} is not a supported format version")
    if data.get("owner") != PRODUCT:
        raise ValueError(
            f"{named} must declare `owner: {PRODUCT}` -- the list of what an "
            "instance owns is the product's own statement about itself"
        )
    raw = data.get("instance")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{named}: instance: must be a non-empty list")
    entries: list[Handed] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{named}: instance: holds {item!r}, not an entry")
        path = _relative_path(item.get("path"), "an instance path")
        if states_its_own_owner(path):
            raise ValueError(
                f"{named}: {path!r} is a configuration file in "
                f"{PurePosixPath(path).parent.as_posix()}/, whose files "
                "state their own owner in their own `owner:` key. Naming "
                "it here too would make one fact two places."
            )
        regenerated = item.get("regenerated", False)
        if not isinstance(regenerated, bool):
            raise ValueError(
                f"{named}: {path}'s regenerated: must be true or false, got "
                f"{regenerated!r}"
            )
        if regenerated and path.endswith("/"):
            raise ValueError(
                f"{named}: {path!r} is a directory, and regenerated: names "
                "one file git is told how to merge -- a directory has no "
                "merge attribute of its own"
            )
        entries.append(
            Handed(
                path=path,
                reason=_reason(item.get("reason"), path),
                kept=_kept_from(item.get("kept"), path),
                regenerated=regenerated,
            )
        )
    for entry in entries:
        for other in entries:
            if entry is not other and entry.covers(other.path):
                raise ValueError(
                    f"{named}: {other.path!r} sits inside {entry.path!r}. One "
                    "path, one entry -- nesting them means whichever is read "
                    "first decides, which is not a decision anybody made."
                )
    return tuple(entries)


def config_owners(root: Path) -> dict[str, str]:
    """What each configuration file says it is, read from its own header.

    Every file `CONFIG_DIRS` holds directly must answer, in whichever of
    `CONFIG_READERS`' formats it is written -- a JSON file states the same
    `owner` key a YAML one does, next to the same argument for it, in a
    `_comment` because JSON has nowhere else to put one. A file with no
    `owner` is refused by name rather than defaulted to either side:
    `config/` was found mixing product and instance precisely because it
    filled up by accumulation, with nobody ever deciding, and a default
    here would be that same silence with a friendlier face.
    """
    owners: dict[str, str] = {}
    candidates = sorted(
        path
        for directory in CONFIG_DIRS
        for suffix in CONFIG_READERS
        for path in (root / directory).glob(f"*{suffix}")
    )
    for path in candidates:
        name = path.relative_to(root).as_posix()
        read = CONFIG_READERS[path.suffix]
        loaded = read(path.read_text(encoding="utf-8"))
        declared = loaded.get("owner") if isinstance(loaded, dict) else None
        if declared not in OWNERS:
            raise ValueError(
                f"{name} declares no owner. Every configuration file in "
                f"{PurePosixPath(name).parent.as_posix()}/ has to say "
                "whether it is the instance's or the product's: add "
                f"`owner:` with one of {', '.join(OWNERS)}, and the "
                "argument for it, to its header."
            )
        owners[name] = declared
    return owners


def load(root: Path | None = None) -> Boundary:
    """The boundary as this repository declares it."""
    # Imported here because `paths` reads this declaration at import to
    # give each path it hands to the instance a name, and a module-level
    # import in both directions is a cycle. `load` is the only place in
    # this module that needs a root.
    from .paths import repo_root

    base = root if root is not None else repo_root()
    data = yaml.safe_load((base / DECLARATION_PATH).read_text(encoding="utf-8"))
    return Boundary(
        handed=declaration_from_data(data),
        config_owners=config_owners(base),
    )


def instance_files(root: Path, boundary: Boundary) -> tuple[str, ...]:
    """Every file the working tree actually holds inside an instance path.

    A walk of the declared paths only, never of the whole tree: that is the
    surface the rule is about, and it keeps this function free of the
    "which build directories do we skip" list that a full sweep would need
    and that would rot.
    """
    found: list[str] = []
    for entry in boundary.handed:
        target = root / entry.path
        candidates = (
            sorted(p for p in target.rglob("*") if p.is_file())
            if entry.is_directory
            else ([target] if target.is_file() else [])
        )
        for path in candidates:
            relative = path.relative_to(root).as_posix()
            if boundary.owner_of(relative) == INSTANCE:
                found.append(relative)
    for name, owner in boundary.config_owners.items():
        if owner == INSTANCE and (root / name).is_file():
            found.append(name)
    return tuple(sorted(found))


def code_among(relatives: Iterable[str]) -> tuple[str, ...]:
    """The paths in `relatives` that are source code.

    Pure, and separate from the walk above, so the rule can be exercised
    against a list somebody made up rather than only against whatever this
    repository happens to hold today.
    """
    return tuple(
        sorted(
            name
            for name in relatives
            if PurePosixPath(name).suffix.lower() in CODE_SUFFIXES
        )
    )
