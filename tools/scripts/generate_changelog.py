"""The changelog, and the one section of it a duplicate reads first.

An ordinary repository without tags or a changelog has an inconvenience.
This one has a product gap, and the distribution model is why: an instance
is a **duplicate** of this repository and an update is a **merge**
(`declarations/boundary.yml`). So an operator running a duplicate had no
name for the upstream state they were on, no way to read what a merge would
bring before pulling it, and -- the one that costs -- no warning that a
change reached a file the boundary hands to *them*. A merge that touches
one of those is the merge that ends in a conflict nobody can resolve, which
is the failure the boundary exists to prevent.

What is derived, and what is not
================================
**Derived: which paths a change has to be reported against.** That is a
fact this repository already declares. `declarations/boundary.yml` names
every path an instance owns, `Boundary.instance_paths` computes the list,
and `HAND_EDITED` below carries the product's own files a duplicate types a
value into -- three of them, each held against `git ls-files` and against
the declaration, so an entry that stops being true fails rather than going
stale. The block between the markers is that list, spliced into
`CHANGELOG.md` above the entries, which is where the person writing one is
already reading.

**Derived: that an entry stays inside it.** Every path an entry names under
*Before you merge this* has to be one of those. A release note naming a product
path under that heading is a false alarm sent to every duplicate at once,
and `problems` refuses it by name.

**Not derived: which of those paths a given release touched.** It reads as
though `git diff` between two tags would answer it, and it does not, for a
reason that was measured rather than supposed:

1. **The ranges are tags, and no tag survives the derivation.**
   `convener_ops.derivation.repository.clone` passes `--no-tags`, and the
   filter rewrites every commit, so the public repository -- the one a
   duplicate actually merges from -- carries no range to compute over.
   `docs/operating/publishing-the-product.md` says where the product's own
   tags are made instead.
2. **This repository's own history answers a different question.** Most
   commits here touching `instance/data/` are the cockpit recording a vote
   and the scheduled jobs writing their ledgers. None of them reaches the
   product at all -- the derivation filters those paths out of every commit
   -- so a range read here would report this instance's own week as work a
   duplicate must act on.
3. **What to do about a change is a judgement.** A key added to
   `instance/config.json` is copied across and filled in; a key renamed is
   renamed in place; a ledger's shape changing is absorbed by the next run.
   A generator can say which file moved and nothing about which of those
   three it was, and the sentence a duplicate needs is the second half.

So the entry under that heading is written by hand, against a generated
list of the paths it may name, checked by the clause above.

The version number
==================
`tools/pyproject.toml` holds it, once. `problems` requires the newest
release in the changelog to be that value, so the two cannot drift into
naming different states -- which is the whole of what a version here is
for. Nothing else in this repository writes a version: `CITATION.cff`
carries none deliberately, and its own header says why.

Spliced, not written whole
==========================
`CHANGELOG.md` is a hand-authored page and only the block between the two
markers is this script's, in the shape `generate_directory_map.py` and
`generate_brand_css.py` already use. A missing marker raises rather than
being ignored, because a check comparing a file with itself reports success
on a page with nowhere left to write.

Pure, so `--check` means something
==================================
The rendering reads the declaration, the index and the page it splices
into: no clock, no network, no history. Two runs over the same commit
produce byte-identical files, and the same two runs in a derived repository
produce the same bytes again -- the declaration travels, and so does every
path in it.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python scripts/generate_changelog.py            # write the page
    uv run python scripts/generate_changelog.py --check    # assert only
"""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404
import sys
import textwrap
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final

from convener_ops.declaration.boundary import INSTANCE, Boundary, load
from convener_ops.declaration.paths import repo_root

#: The page, relative to the repository root.
DOC_PATH: Final = Path("CHANGELOG.md")

#: Where the one version number lives. Read, never copied.
VERSION_PATH: Final = Path("tools") / "pyproject.toml"

#: The declaration the owned half of the list comes from. Named here for
#: the failure messages and the page's own preamble; the reading itself is
#: `convener_ops.declaration.boundary.load`.
DECLARATION: Final = "declarations/boundary.yml"

#: How the script is invoked, quoted in the page and in every failure
#: message. One string, so the two cannot come to name two commands.
COMMAND: Final = "uv run python scripts/generate_changelog.py"

#: The heading each release entry carries the duplicate's own half under.
MERGE_HEADING: Final = "### Before you merge this"

#: Markers wrapping the generated block inside the hand-authored page.
_BEGIN: Final = (
    "<!-- BEGIN GENERATED PATHS A DUPLICATE OWNS -- "
    "tools/scripts/generate_changelog.py -->"
)
_END: Final = (
    "<!-- END GENERATED PATHS A DUPLICATE OWNS -- "
    "edit tools/scripts/generate_changelog.py, not this block -->"
)

#: The product's own files a duplicate types a value into, and why each one
#: cannot be read out of a declaration instead.
#:
#: These are the other half of the answer and the half `declarations/boundary.yml`
#: cannot give: upstream writes and maintains all three, so the boundary
#: says `product` about each, while a duplicate has still edited its copy
#: and a release that changes one arrives at that edit. The list is short,
#: it is the one `docs/operating/what-a-duplicate-edits.md` already
#: enumerates for a reader, and `hand_edited_for` refuses an entry naming a
#: path this repository does not track or a path the declaration has since
#: handed to the instance -- so it cannot outlive what it was written for.
HAND_EDITED: Final[Mapping[str, str]] = {
    ".github/CODEOWNERS": (
        "read by GitHub verbatim, before any code of this project's can "
        "run, so the team a review request goes to is typed rather than "
        "derived. A duplicate writes its own organisation's team into it "
        "before its first pull request."
    ),
    "services/form-relay/wrangler.toml": (
        "the identifier of the storage namespace the proposal relay binds "
        "to, which does not exist until `wrangler kv namespace create` has "
        "printed it and so cannot be shipped filled in."
    ),
    "services/signup-relay/wrangler.toml": (
        "the same one value, for the relay a registration and a survey "
        "response pass through."
    ),
}

#: A release heading: a semantic version and the day it was tagged.
_RELEASE: Final = re.compile(r"^## (\d+\.\d+\.\d+) — (\d{4}-\d{2}-\d{2})$")

#: A heading that opens with a digit and is therefore meant to be a release
#: one. Anchored on the digit so that a prose heading is left alone and a
#: mistyped version is refused rather than read as prose.
_MEANT_AS_RELEASE: Final = re.compile(r"^## \d")

#: A path named inside a release's own section: anything in backticks with
#: a `/` in it. The slash is what separates a path from a command -- `git
#: merge` and `npm ci` belong in that prose and are not paths.
_BACKTICKED_PATH: Final = re.compile(r"`([^`\s]*/[^`\s]*)`")


# --------------------------------------------------------------------------
# What a duplicate owns
# --------------------------------------------------------------------------


def tracked_files(root: Path) -> tuple[str, ...]:
    """Every path this repository tracks, as git reports it.

    The index rather than a walk: `HAND_EDITED` is held against what this
    repository ships, and a working copy holds whatever anybody left in it.
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


def kept_inside(board: Boundary) -> tuple[str, ...]:
    """The product's own files inside a directory the instance owns, sorted.

    `Boundary.kept_files` answers this for the retired paths as well, and a
    changelog is about the repository as it stands, so the live entries are
    read directly. A duplicate does nothing about a change to one of these:
    upstream owns the file and the merge is clean.
    """
    return tuple(sorted(kept.path for entry in board.handed for kept in entry.kept))


def hand_edited_for(tracked: Iterable[str], board: Boundary) -> dict[str, str]:
    """`HAND_EDITED`, held against the repository it makes claims about.

    Two states are refused and both are the drift a hand-written list
    acquires: an entry naming a path this repository does not track, and an
    entry naming a path the declaration has since handed to the instance --
    which would put it in the derived list above and name it twice.
    """
    listed = set(tracked)
    missing = [name for name in HAND_EDITED if name not in listed]
    declared = [name for name in HAND_EDITED if board.owner_of(name) == INSTANCE]
    if missing or declared:
        parts = []
        if missing:
            parts.append(
                f"HAND_EDITED names {', '.join(missing)}, which this "
                "repository does not track"
            )
        if declared:
            parts.append(
                f"HAND_EDITED names {', '.join(declared)}, which "
                f"{DECLARATION} now hands to the instance -- the derived "
                "list above already carries it"
            )
        raise ValueError(
            "tools/scripts/generate_changelog.py: "
            + "; and ".join(parts)
            + ". This list is the product's own files a duplicate types a "
            "value into; correct it on the same commit as the file."
        )
    return dict(HAND_EDITED)


def owned(path: str, board: Boundary) -> bool:
    """Whether a release entry may name this path under `MERGE_HEADING`.

    The instance's by the declaration, at any depth -- `instance/data/`
    covers `instance/data/config.yml` -- or one of the three product files
    a duplicate types a value into.
    """
    return board.owner_of(path) == INSTANCE or path in HAND_EDITED


# --------------------------------------------------------------------------
# The block
# --------------------------------------------------------------------------


_PREAMBLE: Final = f"""\
*The lists below are generated from* `{DECLARATION}` *and from this
repository's own index: the paths a merge can arrive at that are not
upstream's to change. Do not edit this block — run*
`{COMMAND}`
*from* `tools/` *and commit what it writes.*
"""

_OWNED_LEAD: Final = """\
**Yours, by the declaration.** Upstream ships each of these filled in for
the instance that happens to run this repository, and never edits one
afterwards. A release that changes the *shape* of one names it below.
"""

_HAND_LEAD: Final = """\
**The product's, with one value of yours typed into it.** Upstream
maintains these; your copy differs from upstream's by the value you
entered, so a release that changes one arrives at that edit.
"""

_KEPT_LEAD: Final = """\
**Inside those directories and not yours.** Upstream owns and maintains
each of these, so a release that changes one needs nothing from you:
"""


#: Where this repository's prose breaks. The bullets are wrapped to it so
#: that a reason written in the table above arrives on the page looking
#: like every other paragraph around it rather than as one long line.
_COLUMN: Final = 76


def _bullet(path: str, reason: str | None) -> str:
    """One list item, wrapped, with its continuation lines indented."""
    text = f"`{path}`" + (f" — {reason}" if reason else "")
    return textwrap.fill(
        text,
        width=_COLUMN,
        initial_indent="- ",
        subsequent_indent="  ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def render_block(
    owned_paths: Sequence[str],
    hand_edited: Mapping[str, str],
    kept: Sequence[str],
    regenerated: Sequence[str],
) -> str:
    """The text between the markers, for exactly these inputs.

    Pure, and takes everything it prints as an argument, so the rendering
    can be exercised against a declaration somebody made up rather than
    only against the one this repository ships.
    """
    lines = [_PREAMBLE, _OWNED_LEAD]
    lines.append(
        "\n".join(
            _bullet(
                path,
                "rewritten in full by your own next push."
                if path in regenerated
                else None,
            )
            for path in owned_paths
        )
    )
    lines.append(_HAND_LEAD)
    lines.append(
        "\n".join(_bullet(path, reason) for path, reason in hand_edited.items())
    )
    if kept:
        lines.append(_KEPT_LEAD)
        lines.append("\n".join(_bullet(path, None) for path in kept))
    return "\n".join(block.rstrip("\n") + "\n" for block in lines)


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


# --------------------------------------------------------------------------
# The entries, which nothing generates
# --------------------------------------------------------------------------


def declared_version(root: Path) -> str:
    """The one version number this repository holds."""
    data = tomllib.loads((root / VERSION_PATH).read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(
            f"{VERSION_PATH.as_posix()} declares no project version, so "
            "nothing here can say which state the newest entry names"
        )
    return version


def sections(text: str) -> list[tuple[str, str, str]]:
    """Every release entry, as (version, date, its own text).

    A `## ` heading opening with a digit is meant to be a release heading,
    so one that does not parse is a failure rather than a paragraph: a
    mistyped version silently read as prose is an entry no reader of this
    file would ever be shown.
    """
    found: list[tuple[str, str, str]] = []
    current: tuple[str, str] | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                found.append((*current, "\n".join(body)))
                current, body = None, []
            match = _RELEASE.match(line)
            if match:
                current = (match.group(1), match.group(2))
                continue
            if _MEANT_AS_RELEASE.match(line):
                raise ValueError(
                    f"{DOC_PATH.as_posix()}: {line!r} opens with a digit and "
                    "is not a release heading. One shape only: "
                    "`## <major>.<minor>.<patch> — <YYYY-MM-DD>`"
                )
            continue
        if current is not None:
            body.append(line)
    if current is not None:
        found.append((*current, "\n".join(body)))
    return found


def _ordering(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def named_paths(body: str) -> list[str]:
    """Every path a release names under `MERGE_HEADING`, in order.

    Sliced to that subsection rather than searched over the whole entry:
    the rest of an entry names product paths on purpose, because that is
    what most of a release is.
    """
    if MERGE_HEADING not in body:
        return []
    after = body.split(MERGE_HEADING, 1)[1].split("\n### ", 1)[0]
    return [match.group(1) for match in _BACKTICKED_PATH.finditer(after)]


def problems(text: str, root: Path, board: Boundary) -> list[str]:
    """Everything wrong with the entries, as sentences naming what to fix.

    Every clause here is about the half nothing generates. A generated
    block is compared byte for byte and needs no rules; a hand-written
    entry needs the four below, and each one is a way this file has of
    going quietly wrong rather than loudly.
    """
    found: list[str] = []
    entries = sections(text)
    if not entries:
        return [
            f"{DOC_PATH.as_posix()} carries no release entry, so every check "
            "on its entries would pass by reading nothing"
        ]

    versions = [version for version, _date, _body in entries]
    ordered = sorted(versions, key=_ordering, reverse=True)
    if versions != ordered or len(set(versions)) != len(versions):
        found.append(
            f"{DOC_PATH.as_posix()} lists {versions}, which is neither "
            "strictly descending nor free of repeats -- newest first, and "
            "one entry per version"
        )

    declared = declared_version(root)
    if versions[0] != declared:
        found.append(
            f"{DOC_PATH.as_posix()}'s newest entry is {versions[0]} and "
            f"{VERSION_PATH.as_posix()} says {declared}. The version has one "
            "home and the tag, the package and this page all name the same "
            "state; change both on the commit that releases"
        )

    for version, _date, body in entries:
        if MERGE_HEADING not in body:
            found.append(
                f"{DOC_PATH.as_posix()}: {version} carries no "
                f"{MERGE_HEADING!r} section. Every entry carries one, "
                "including an entry whose answer is that there is nothing "
                "to do -- an operator reading a release note has no way to "
                "tell a silence from an omission"
            )
            continue
        for path in named_paths(body):
            if not owned(path, board):
                found.append(
                    f"{DOC_PATH.as_posix()}: {version} names `{path}` under "
                    f"{MERGE_HEADING!r}, and {DECLARATION} says that path is "
                    "the product's. That section is what a duplicate acts "
                    "on, so a product path in it is a false alarm sent to "
                    "every duplicate at once"
                )
    return found


# --------------------------------------------------------------------------
# Rendering and the command
# --------------------------------------------------------------------------


def changelog(root: Path) -> str:
    """The whole of `CHANGELOG.md`, with this repository's own block."""
    board = load(root)
    tracked = tracked_files(root)
    owned_paths = board.instance_paths
    if not owned_paths:
        raise ValueError(
            f"{DECLARATION} hands no path to the instance, so the list this "
            "block exists to publish would be empty and every entry would "
            "pass the check below by having nothing it could name"
        )
    inner = render_block(
        owned_paths,
        hand_edited_for(tracked, board),
        kept_inside(board),
        board.regenerated_paths,
    )
    return splice((root / DOC_PATH).read_text(encoding="utf-8"), inner)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the list of paths a duplicate owns in "
        "CHANGELOG.md, and check the entries written beside it."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if the committed page is not what the "
        "declaration derives, or if an entry breaks a rule",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    path = root / DOC_PATH
    try:
        rendered = changelog(root)
        found = problems(rendered, root, load(root))
    except (RuntimeError, ValueError) as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    for problem in found:
        print(problem, file=sys.stderr)
    current = path.read_text(encoding="utf-8") if path.exists() else ""

    if args.check:
        if current != rendered:
            # Naming the file, the reason and the command, and repairing
            # nothing: a check that wrote the file it was checking would
            # pass on a repository that still held the wrong list.
            print(
                f"{DOC_PATH.as_posix()}'s generated block is not the list "
                f"{DECLARATION} derives.",
                file=sys.stderr,
            )
            print(
                f"That block is generated, not authored: run `{COMMAND}` "
                "from `tools/` and commit the file it writes.",
                file=sys.stderr,
            )
        if found or current != rendered:
            return 1
        print(f"{DOC_PATH.as_posix()} matches the declaration, and its entries hold")
        return 0

    if found:
        return 1
    if current == rendered:
        print(f"{DOC_PATH.as_posix()} unchanged")
        return 0
    path.write_text(rendered, encoding="utf-8", newline="")
    print(f"wrote {DOC_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
