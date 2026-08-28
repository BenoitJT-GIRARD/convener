"""Where the repository is, and where the instance's own paths sit inside it.

`repo_root` walks upwards for a marker, so that no caller has to know how
deep this file sits.

The constants below are the paths `config/boundary.yml` hands to the
instance, one name each. Their values are read from that declaration at
import, and every other module in `convener_ops` builds the instance paths
it touches out of them: `DATA_DIR / "config.yml"`, `KEYS_DIR / "events"`,
`PUBLIC_DATA_DIR / "registration-routing.json"`. That is what makes the
whole set movable from one place: change where the declaration puts
`data/` and these constants follow, and the hundred-odd places that build
on them follow with it. `tools/tests/test_paths.py` sweeps the package and
fails on a module that writes one of these paths out in a string of its
own.

A file inside a declared directory is built from that directory's
constant. The declaration has no entry to take it from:
`boundary.declaration_from_data` refuses an entry nested inside another,
so `data/config.yml` cannot be listed there while `data/` is. Ownership is
settled once, for the directory; the file names inside it stay with the
module that reads and writes them.

Each constant is looked up by the last component of a declared path.
Moving `data/` in the declaration moves `DATA_DIR` with it and leaves this
module untouched; a declaration that hands none of its paths a given last
component raises at import, naming the constant that lost its path and
listing what the declaration does hand over.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .boundary import Handed

#: The file whose presence marks a repository root. Written out here
#: because finding the root is how the declaration below gets read, so
#: this one path has to be known before any of them can be. It is held
#: against `DATA_DIR` at the bottom of this module.
_MARKER = Path("data") / "config.yml"


def repo_root(start: Path | None = None) -> Path:
    """Walk upwards until the repository marker is found.

    Honours CONVENER_REPO_ROOT so tests and CI can point elsewhere.
    """
    override = os.environ.get("CONVENER_REPO_ROOT")
    if override:
        return Path(override).resolve()
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / _MARKER).exists():
            return candidate
    raise FileNotFoundError(f"repository root not found above {here}")


def by_last_component(entries: Iterable[Handed]) -> dict[str, Path]:
    """The declared instance paths, keyed by their final component.

    The key is what the path holds -- `data`, `keys`, `public-data`,
    `register.md` -- so a declaration that moves one of them keeps
    answering to the same key. Two entries sharing a final component are
    refused: the constants below would have no way to say which of the two
    they meant.
    """
    found: dict[str, Path] = {}
    for entry in entries:
        name = PurePosixPath(entry.path).name
        if name in found:
            raise ValueError(
                f"two declared instance paths end in {name!r} "
                f"({found[name].as_posix()} and {entry.path}), so a constant "
                "in paths.py has no way to name one of them."
            )
        found[name] = Path(entry.path)
    return found


@cache
def _declaration() -> tuple[Path, dict[str, Path]]:
    """`config/boundary.yml`'s own path, and what it hands to the
    instance."""
    # `boundary` reads `repo_root` from this file, so a module-level
    # import in both directions would be a cycle. This one happens on the
    # first call.
    from .boundary import DECLARATION_PATH, declaration_from_data

    text = (repo_root() / DECLARATION_PATH).read_text(encoding="utf-8")
    return DECLARATION_PATH, by_last_component(
        declaration_from_data(yaml.safe_load(text))
    )


def handed(name: str) -> Path:
    """The declared instance path whose final component is `name`."""
    declaration, found = _declaration()
    if name not in found:
        raise ValueError(
            f"{declaration.as_posix()} hands the instance no path ending in "
            f"{name!r}. It hands over {', '.join(sorted(found))}."
        )
    return found[name]


#: The instance's own records and its governance configuration.
DATA_DIR: Final = handed("data")

#: The instance's published public keys, event keys and signing keys both.
KEYS_DIR: Final = handed("keys")

#: Everything the instance publishes about itself, derived from `DATA_DIR`
#: by the product's own commands.
PUBLIC_DATA_DIR: Final = handed("public-data")

#: The decision register, re-rendered from this repository's own commit
#: history on every push.
REGISTER_PATH: Final = handed("register.md")


if _MARKER.parent != DATA_DIR:
    raise RuntimeError(
        f"repo_root finds a repository by {_MARKER.as_posix()}, and "
        f"{_declaration()[0].as_posix()} puts the instance's records in "
        f"{DATA_DIR.as_posix()}/. Move the marker to where the records are."
    )
