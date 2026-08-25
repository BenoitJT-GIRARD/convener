"""Which paths an instance owns, and which ones the product keeps.

This repository is meant to be duplicated, and for a duplicate an update is
a **merge**. It succeeds when upstream's commits and the instance's commits
never touch the same file; it fails into a field of conflicts otherwise, at
which point people stop updating and the whole idea of a template dies
quietly. So "instance" cannot stay an intention -- it has to be a set of
paths something can enumerate, and this module is what reads it.

**One declaration, two halves, no copy.** `config/boundary.yml` names the
paths outside `config/` that the instance owns. Inside `config/`, each file
states its own answer in its own `owner:` key, next to the argument for it,
and this module reads that -- `declaration_from_data` *refuses* a
declaration that also names a `config/` path, so the two halves can never
drift into disagreeing. That refusal is the whole point: this repository's
recurring defect is the copy (three palettes, five addresses, two path
lists), and a boundary built out of a second list would be the same defect
wearing a new name.

**The default is the product.** Everything the declaration does not name
belongs to the product: `owner_of` answers `PRODUCT` for it. A path only
becomes the instance's by being named, never by being forgotten.

**Ownership is a property of a file, not of a value**, because a merge is a
file-level event. A file holding one instance-owned value is an instance
file even when its other values would have made perfectly good product
defaults -- upstream cannot ship half a file. That is the rule that settles
`config/`, where `actions-budget.yml` mixes an organisation's GitHub
allowance with a bound on the collector's own runtime.

What this module does **not** do is decide anything about the future. No
offline check can promise that a later upstream commit will not touch
`data/`. What it can do, and what `tools/tests/test_boundary.py` builds on
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

from .paths import repo_root

#: The declaration itself, relative to a repository root. In `config/`
#: rather than beside it: the revalidation of the phase 10 spec found that
#: directory already mixing product and instance by accumulation, and the
#: answer to a directory nobody sorted is to sort it, not to open a second
#: one next to it.
DECLARATION_PATH: Final = Path("config") / "boundary.yml"

#: Where a file states its own owner in its own header.
CONFIG_DIR: Final = Path("config")

#: What a file in `config/` may be written in, and how to read each. YAML
#: for anything only this repository's Python reads; JSON for anything
#: read from more than one side of the language boundary, because it is
#: the only format `site/` and `services/` can parse without a dependency
#: neither of them has and the zero-cost constraint forbids adding
#: (`config/instance.json`). Both are listed here for one reason: a
#: format nobody enumerated is a file in this directory whose owner
#: nothing asks for, and "every file answers" would quietly become "every
#: file we happened to look at".
CONFIG_READERS: Final[dict[str, Callable[[str], Any]]] = {
    ".yml": yaml.safe_load,
    ".json": json.loads,
}

#: `config/boundary.yml`'s own format version.
DECLARATION_VERSION: Final = 1

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
    """

    path: str
    reason: str
    kept: tuple[Kept, ...] = ()

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
    """The whole answer: the declared paths, and `config/`'s own headers."""

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

    @property
    def instance_paths(self) -> tuple[str, ...]:
        """Every path an instance owns, from both halves of the
        declaration, sorted. The enumeration phase 10 asks for -- computed,
        never retyped."""
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
    a `config/` path named here (its answer belongs in its own header, and
    a second home for it is how the two start disagreeing), and one entry
    nested inside another (whichever is read first wins, silently).
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
        if PurePosixPath(path).parts[0] == CONFIG_DIR.name:
            raise ValueError(
                f"{named}: {path!r} is under {CONFIG_DIR.as_posix()}/, whose "
                "files state their own owner in their own `owner:` key. "
                "Naming it here too would make one fact two places."
            )
        entries.append(
            Handed(
                path=path,
                reason=_reason(item.get("reason"), path),
                kept=_kept_from(item.get("kept"), path),
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
    """What each file in `config/` says it is, read from its own header.

    Every file must answer, in whichever of `CONFIG_READERS`' formats it
    is written -- a JSON file states the same `owner` key a YAML one
    does, next to the same argument for it, in a `_comment` because JSON
    has nowhere else to put one. A file with no `owner` is refused by
    name rather than defaulted to either side: the phase 10 spec found this
    directory mixing product and instance precisely because it filled up by
    accumulation, with nobody ever deciding, and a default here would be
    that same silence with a friendlier face.
    """
    directory = root / CONFIG_DIR
    owners: dict[str, str] = {}
    candidates = sorted(
        path for suffix in CONFIG_READERS for path in directory.glob(f"*{suffix}")
    )
    for path in candidates:
        name = path.relative_to(root).as_posix()
        read = CONFIG_READERS[path.suffix]
        loaded = read(path.read_text(encoding="utf-8"))
        declared = loaded.get("owner") if isinstance(loaded, dict) else None
        if declared not in OWNERS:
            raise ValueError(
                f"{name} declares no owner. Every file in "
                f"{CONFIG_DIR.as_posix()}/ has to say whether it is the "
                f"instance's or the product's: add `owner:` with one of "
                f"{', '.join(OWNERS)}, and the argument for it, to its header."
            )
        owners[name] = declared
    return owners


def load(root: Path | None = None) -> Boundary:
    """The boundary as this repository declares it."""
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
