"""One map of the repository's root, derived from what the root actually holds.

Two hand-written tables of top-level directories existed: one in `README.md`
under *What is here*, one in `docs/architecture.md`. They disagreed with each
other, and between them they described nine and eight of the twelve tracked
top-level directories. `brand/`, `fonts/`, `instances/` and `.claude/` were in
neither, and `config/` was in one of the two. A reader who cannot place a third
of the root concludes the root is disorganised even when it is not.

That is also the one place this repository broke its own first rule.
`INFORMATION-ARCHITECTURE.md` asks for one home per notion, and for a passage
needed twice to be *included* rather than copied. Two directory tables were
exactly that copy, and they escaped `tools/tests/test_no_literal_copies.py`
only because that sweep compares served handbook pages and the root
`README.md` is not one.

So the map is derived, written once, into `docs/architecture.md`, and
`README.md` links to it.

What is derived
---------------
**The list of directories** comes from `git ls-files`: every tracked path that
has a directory component contributes its first one. Nothing enumerates the
root by hand, so a directory added in a commit is a row in the map on that same
commit or `--check` fails the build. The list is *tracked* rather than
on-disk, deliberately: `node_modules/`, `.venv/`, `__pycache__` and every other
build residue is on disk in a working copy and is not part of this repository.

**The owner** comes from `config/boundary.yml`, through
`convener_ops.declaration.boundary`. A directory is the instance's when every
tracked file inside it is the instance's, once the files the declaration itself
names as `kept:` are set aside; otherwise it is the product's. That rule is
what makes `instance/` read as the instance's -- the two product files inside
it are both declared `kept:` -- while `docs/` reads as the product's, which is
what it is, one generated register aside.

**The paths that cross their own directory's answer** are derived from the same
comparison and listed under the table, because a single-word owner column
cannot say them and leaving them unsaid is how the previous tables came to be
wrong. There are three today and nothing here counts them: the sentence
introducing them names no number, so the list can grow or shrink without a
figure beside it going stale.

Where the purpose line comes from, and why
------------------------------------------
The purpose line is the part nothing can derive, and this module holds it, in
`PURPOSE` below. Three places were available and two were worse.

**A declared field** would have meant widening `config/boundary.yml`. That file
is the product's statement about which paths an instance owns, and it names
four -- `instance/data/`, `instance/keys/`, `instance/public-data/` and
`docs/governance/register.md`. Not one of them is a top-level directory, so
every entry would have to be invented, and the file would stop being a
declaration about merges and become a second index of the repository. Its own
header argues against precisely that: the list is "deliberately short", and
`declaration_from_data` refuses an entry whose owner is already stated
elsewhere. A parallel `purpose:` on twelve invented entries would be the copy
this generator exists to remove, one file further along.

**A per-directory README** would have meant writing ten new files, since only
`docs/` and `site/` have one. Two things are wrong with it beyond the count.
`.github/README.md` is a file GitHub itself gives a meaning to -- it is one of
the three locations GitHub renders as a repository's front page -- so this
repository would be putting a table row's source sentence in a file whose
content is published somewhere nobody writing it intended. And harvesting a
sentence out of a README makes that sentence's exact wording load-bearing for a
table on another page: an editor improving a README's opening line would be
silently editing the architecture document, with nothing on either side saying
so.

**A table in the generator** is what is left, and it is what
`tools/scripts/generate_schema_doc.py` already does for the same kind of text:
that script derives every field, type and note from the model and keeps the
*narrative* -- the sentences nothing derives -- in the generator, "where the
person who needs it is already reading". A purpose line is narrative about the
repository. It has one home, it sits beside the code that publishes it, and it
is inside the reach of `--check`.

That last clause is the part that makes it a maintained table rather than a
copy maintained nowhere. `purposes_for` refuses two states and refuses them by
name: a tracked directory with no sentence, and a sentence naming a directory
this repository does not have. So a directory added without a line fails, a
directory removed without its line being removed fails, and the table cannot
silently narrow -- which is the failure mode the two hand-written tables had,
and had for long enough that four directories were missing from both.

Spliced, not written whole
--------------------------
`docs/architecture.md` is a hand-authored page. Only the block between the two
markers below is this script's, in the shape `generate_brand_css.py` already
uses for the two stylesheets: read the committed file, keep everything outside
the markers exactly as it stood, replace what is between them. A missing marker
raises rather than being ignored, because a check comparing a file with itself
reports success on a repository with nowhere left to write.

Pure, so `--check` means something
----------------------------------
The rendering reads the index, the declaration and the page it splices into:
no clock, no network, no environment. Two runs over the same commit produce
byte-identical files, so a difference can only be an edit made outside those
inputs -- which is what `--check` refuses, without repairing it.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python scripts/generate_directory_map.py            # write the page
    uv run python scripts/generate_directory_map.py --check    # assert only

There is no mode that prints the block: the page is written in the handbook's
British English, and nothing this repository's Python writes to a terminal is
allowed to be non-ASCII.
"""

from __future__ import annotations

import argparse
import subprocess  # nosec B404
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final

from convener_ops.declaration.boundary import INSTANCE, PRODUCT, Boundary, load
from convener_ops.declaration.paths import repo_root

#: The page the map is spliced into, relative to the repository root.
DOC_PATH: Final = Path("docs") / "architecture.md"

#: The declaration the owner column is read from. Named here only for the
#: failure messages and the page's own preamble; the reading itself is
#: `convener_ops.declaration.boundary.load`.
DECLARATION: Final = "config/boundary.yml"

#: How the script is invoked, quoted in the page and in every failure
#: message. One string, so the two cannot come to name two commands.
COMMAND: Final = "uv run python scripts/generate_directory_map.py"

#: Markers wrapping the generated block inside the hand-authored page.
#: Everything outside them is this script's to leave alone.
_BEGIN: Final = (
    "<!-- BEGIN GENERATED DIRECTORY MAP -- tools/scripts/generate_directory_map.py -->"
)
_END: Final = (
    "<!-- END GENERATED DIRECTORY MAP -- "
    "edit tools/scripts/generate_directory_map.py, not this block -->"
)

#: One line per tracked top-level directory, saying what it holds. The one
#: thing on the map that nothing derives -- see this module's docstring for
#: why it lives here and not in a declaration or in twelve READMEs. Every
#: sentence a reader of the two removed tables would recognise is kept as
#: it was written; the four directories that appeared in neither table, and
#: the one that appeared in only one, have a line each for the first time.
#:
#: A key here that names no tracked directory, and a tracked directory with
#: no key here, are both refused by `purposes_for` below.
PURPOSE: Final[Mapping[str, str]] = {
    ".claude": (
        "The run sheet an agent follows to stand an instance up, generated "
        "from `STANDING-UP.yml` by `tools/scripts/generate_standing_up_skill.py`."
    ),
    ".github": (
        "The whole automation surface: data validation, the public-data "
        "filter, certificate issuance and revocation, the retention sweep, "
        "publishing the showcase and the cockpit, quality and security "
        "gates. Nothing in this system runs anywhere else."
    ),
    "app": (
        "The cockpit (React + Vite): the board's and volunteers' "
        "application, gated by GitHub sign-in. Also builds the two public "
        "*islands* — registration and certificate verification — mounted "
        "on the showcase's static pages."
    ),
    "brand": (
        "The product's own charter and marks, read by any duplicate that "
        "has measured no palette of its own yet."
    ),
    "config": (
        "The product's own declarations, which the cockpit never reads: the "
        "external integrations the code knows about, and `boundary.yml`, "
        "which names the paths the instance owns."
    ),
    "docs": (
        "This handbook: volunteer-facing workflow and governance pages "
        "(rendered inline by the cockpit), plus reference material like "
        "this file."
    ),
    "fonts": (
        "The two typefaces both interfaces are set in, self-hosted so that "
        "no page fetches a font from anybody else, each beside its licence."
    ),
    "instance": (
        "Everything this series owns rather than the code: the store itself "
        "under `data/`, the published public keys under `keys/`, what the "
        "instance publishes about itself under `public-data/`, and the four "
        "declarations a maintainer edits."
    ),
    "instances": (
        "The invented second instance this repository builds itself as on "
        "every test run: one file for each path the declaration hands over, "
        "at the same relative path."
    ),
    "services": (
        "Three small Cloudflare Workers with no server of their own to "
        "maintain: `auth-proxy` relays a volunteer's GitHub sign-in; "
        "`form-relay` turns a speaker-proposal submission into a commit; "
        "`signup-relay` does the same for a registration or a survey "
        "response."
    ),
    "site": (
        "Source of the public showcase (Eleventy): the home page, one page "
        "per event, the archives, the speaker-proposal entry, and the data "
        "notice."
    ),
    "tools": (
        "Every operational tool, whatever the language: the `convener_ops` "
        "package every automated workflow runs, the generators under "
        "`scripts/`, the one-shot migrations under `migrations/`, the Node "
        "rendering harness under `visuals/`, and the tests for all of them."
    ),
}


# --------------------------------------------------------------------------
# What the repository holds, read from the index
# --------------------------------------------------------------------------


def tracked_files(root: Path) -> tuple[str, ...]:
    """Every path this repository tracks, as git reports it.

    The index rather than a walk of the working tree, because a walk cannot
    tell a directory this repository holds from one a build left behind:
    `node_modules/`, `.venv/`, `__pycache__` and `site/_site/` are all on
    disk in an ordinary working copy and none of them is part of the root
    this map describes.
    """
    # Fixed argv, shell=False: B603 and B607 describe a risk this call does
    # not carry.
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git ls-files failed in {root}: "
            f"{result.stderr.strip() or result.returncode}"
        )
    return tuple(line for line in result.stdout.splitlines() if line)


def top_level_directories(tracked: Iterable[str]) -> tuple[str, ...]:
    """The first component of every tracked path that has one, sorted.

    A file at the root contributes nothing, which is the intended reading:
    `README.md` and `LICENSE` are not directories and the map does not
    claim to place them.
    """
    return tuple(sorted({name.split("/", 1)[0] for name in tracked if "/" in name}))


def owner_of_directory(
    directory: str, tracked: Iterable[str], boundary: Boundary
) -> str:
    """`INSTANCE` when the whole directory is the instance's, else `PRODUCT`.

    "The whole directory" sets aside the files `config/boundary.yml` itself
    names as `kept:` -- the product's own files inside a directory handed
    over, two of which exist. Without that clause `instance/` would read as
    the product's on the strength of a three-line stub and a wire-format
    note, which is the opposite of what the declaration says about it.

    A directory holding no tracked file at all is the product's. None
    exists -- a directory with no tracked file is not tracked -- so the
    clause is there to make the answer total rather than to decide a real
    case.
    """
    kept = set(boundary.kept_files)
    inside = [
        name
        for name in tracked
        if name.startswith(f"{directory}/") and name not in kept
    ]
    if inside and all(boundary.owner_of(name) == INSTANCE for name in inside):
        return INSTANCE
    return PRODUCT


def crossings(
    owners: Mapping[str, str], tracked: Iterable[str], boundary: Boundary
) -> tuple[tuple[str, str], ...]:
    """Every tracked file whose own owner is not its directory's, sorted.

    The owner column is one word per directory and cannot hold these. They
    are the whole reason the column can be one word at all, so they are
    listed under the table rather than dropped: a reader told that `docs/`
    is the product's and then finding a file in it that a duplicate
    rewrites has been told something false by omission.
    """
    found = []
    for name in sorted(tracked):
        directory = name.split("/", 1)[0] if "/" in name else ""
        if directory not in owners:
            continue
        owner = boundary.owner_of(name)
        if owner != owners[directory]:
            found.append((name, owner))
    return tuple(found)


def purposes_for(directories: Sequence[str]) -> dict[str, str]:
    """`PURPOSE`, held against what the repository actually holds.

    Refuses both halves of the drift this generator exists to end: a
    tracked directory nobody wrote a line for, and a line for a directory
    that is not there. Either one raises, naming the directories, and
    `--check` turns that into a failed build rather than a shorter table
    nobody notices.
    """
    missing = [name for name in directories if name not in PURPOSE]
    extra = [name for name in PURPOSE if name not in directories]
    if missing or extra:
        parts = []
        if missing:
            parts.append(
                "no line in PURPOSE for tracked "
                f"{'directories' if len(missing) > 1 else 'directory'} "
                f"{', '.join(missing)}"
            )
        if extra:
            parts.append(
                "a line in PURPOSE for "
                f"{', '.join(extra)}, which this repository does not track"
            )
        raise ValueError(
            "tools/scripts/generate_directory_map.py: "
            + "; and ".join(parts)
            + ". The owner is derived and the purpose is not: add or remove "
            "the sentence in PURPOSE on the same commit as the directory."
        )
    return {name: PURPOSE[name] for name in directories}


# --------------------------------------------------------------------------
# The block
# --------------------------------------------------------------------------


_PREAMBLE: Final = f"""\
*The rows below are generated: every tracked top-level directory, with
the owner `{DECLARATION}` gives it. Do not edit this block — run*
`{COMMAND}`
*from `tools/` and commit what it writes. What each directory holds is
the one line nothing derives, and it is written in
`tools/scripts/generate_directory_map.py`, beside the code that
publishes it.*
"""

_CROSSING_LEAD: Final = f"""\
`{DECLARATION}` also names paths sitting on the other side of the directory
that holds them:
"""


def _crossing_line(path: str, owner: str) -> str:
    """One bullet under the table, saying which way the path crosses."""
    if owner == INSTANCE:
        return f"- `{path}` — the instance's, inside a directory the product owns."
    return f"- `{path}` — the product's, inside a directory the instance owns."


def render_block(
    directories: Sequence[str],
    owners: Mapping[str, str],
    purposes: Mapping[str, str],
    crossed: Sequence[tuple[str, str]],
) -> str:
    """The text between the markers, for exactly these inputs.

    Pure, and takes everything it prints as an argument, so the rendering
    can be exercised against a repository somebody made up rather than only
    against whatever this one happens to hold today.
    """
    rows = ["| Directory | Owner | What it holds |", "|---|---|---|"]
    for name in directories:
        rows.append(f"| `{name}/` | {owners[name]} | {purposes[name]} |")
    blocks = [_PREAMBLE, "\n".join(rows)]
    if crossed:
        blocks.append(_CROSSING_LEAD)
        blocks.append("\n".join(_crossing_line(path, owner) for path, owner in crossed))
    return "\n".join(block.rstrip("\n") + "\n" for block in blocks)


def splice(current: str, inner: str) -> str:
    """`current`, with the text between the markers replaced by `inner`.

    Raises rather than guessing when a marker is missing: silently leaving
    the file untouched would make `--check` compare the page with itself
    and report a match on a page with nowhere left to write to.
    """
    if _BEGIN not in current or _END not in current:
        raise ValueError(
            f"{DOC_PATH.as_posix()}: markers not found ({_BEGIN!r} / {_END!r}); "
            "the generated block cannot be located"
        )
    before, _, rest = current.partition(_BEGIN)
    _, _, after = rest.partition(_END)
    return f"{before}{_BEGIN}\n{inner}{_END}{after}"


def directory_map(root: Path) -> str:
    """The whole of `docs/architecture.md`, with the map this root derives."""
    boundary = load(root)
    tracked = tracked_files(root)
    directories = top_level_directories(tracked)
    if not directories:
        raise ValueError(
            f"git ls-files reported no tracked directory under {root} -- a map "
            "of nothing would pass every check it is compared against"
        )
    owners = {name: owner_of_directory(name, tracked, boundary) for name in directories}
    purposes = purposes_for(directories)
    crossed = crossings(owners, tracked, boundary)
    inner = render_block(directories, owners, purposes, crossed)
    return splice((root / DOC_PATH).read_text(encoding="utf-8"), inner)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the map of the repository's top-level "
        "directories in docs/architecture.md."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if the committed page is not what the "
        "repository derives",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    path = root / DOC_PATH
    try:
        rendered = directory_map(root)
    except (RuntimeError, ValueError) as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if args.check:
        if current != rendered:
            # Naming the file, the reason and the command, and repairing
            # nothing: a check that wrote the file it was checking would
            # pass on a repository that still held the wrong map.
            print(
                f"{DOC_PATH.as_posix()} is not the map this repository's own "
                f"directories and {DECLARATION} derive.",
                file=sys.stderr,
            )
            print(
                f"That block is generated, not authored: run `{COMMAND}` from "
                "`tools/` and commit the file it writes.",
                file=sys.stderr,
            )
            return 1
        print(f"{DOC_PATH.as_posix()} matches the tracked directories")
        return 0

    if current == rendered:
        print(f"{DOC_PATH.as_posix()} unchanged")
        return 0
    path.write_text(rendered, encoding="utf-8", newline="")
    print(f"wrote {DOC_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
