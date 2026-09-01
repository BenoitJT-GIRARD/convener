"""One way in for an agent, and no vendor's own copy of anything.

`AGENTS.md` is the page an agent reads first. It carries no procedure: it
names `STANDING-UP.yml` and the two renderings generated from it, and
`tools/scripts/generate_standing_up_run_sheet.py` states the rule that stops a
third -- a second agent vendor is served by another line on that page, never
by a second rendering under a directory that vendor's tooling happens to
discover. That rule lived in a generator's docstring, which is the last place
somebody looks before adding `.cursor/` or `.gemini/`. It is a check here.

**And one bridge, measured rather than assumed.** Moving the run sheet out of
`.claude/` buys parity only if every vendor actually reaches `AGENTS.md`.
Claude Code does not: a session opened in this repository, asked with no tools
what the root declares, answers from `CLAUDE.md` and knows nothing of
`AGENTS.md`. So `CLAUDE.md` exists, holding a pointer and nothing else. That
is what these tests are for -- the file is one edit away from becoming a
second copy of the run sheet, which is exactly the defect the move was made to
remove, and the edit would look like a kindness.

**What is not held here.** Whether the run sheet is what the declaration
derives is `tools/tests/test_standing_up.py`'s question, and whether every
tracked top-level directory is on the map is
`tools/tests/test_directory_map.py`'s. This module asks who may hold a page
for an agent, and what the bridge to it may say.
"""

from __future__ import annotations

import subprocess  # nosec B404
from typing import Final

from generate_standing_up_run_sheet import ENTRY_POINT, RUN_SHEET_PATH

from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()

#: The bridge, and the only file at the root written for one vendor.
BRIDGE: Final = "CLAUDE.md"

#: A directory whose name is a single agent vendor's convention. Tracking a
#: page under one of these is what this module refuses: it is reached by that
#: vendor's discovery and by nothing else, so it ships a preference between
#: vendors in a repository that has none.
VENDOR_DIRECTORIES: Final = (
    ".claude/",
    ".codex/",
    ".cursor/",
    ".gemini/",
    ".github/copilot/",
    ".aider/",
    ".continue/",
    ".windsurf/",
)

#: What a bridge may be. Long enough for a sentence saying where to go and
#: why; far short of a procedure. The run sheet is over two hundred lines,
#: so nothing that grew a copy of it could sit under this.
BRIDGE_MAX_LINES: Final = 12


def tracked() -> tuple[str, ...]:
    """Every path in the index, POSIX-spelt."""
    out = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return tuple(line.strip() for line in out.splitlines() if line.strip())


def test_no_agent_vendor_directory_is_tracked() -> None:
    """The rule the generator argues for, as a check.

    Three renderings of one sequence is the defect the declaration exists to
    remove; a vendor directory is how the third one arrives, because adding it
    reads as serving one more tool rather than as writing the procedure down
    again.
    """
    inside = [
        path
        for path in tracked()
        for vendor in VENDOR_DIRECTORIES
        if path.startswith(vendor)
    ]
    assert not inside, (
        f"{inside} sit under an agent vendor's own directory. A page there is "
        f"found by that vendor's tooling and by no other, which is a "
        f"preference between vendors this product does not ship: "
        f"`{ENTRY_POINT}` names the one page and every agent reads it"
    )


def test_the_run_sheet_is_where_the_entry_point_says_it_is() -> None:
    """A pointer nobody can follow is worse than none: with the run sheet
    out of a discoverable path, this link is the only route to it."""
    named = RUN_SHEET_PATH.as_posix()
    assert named in (ROOT / ENTRY_POINT).read_text(encoding="utf-8"), (
        f"{ENTRY_POINT} does not name {named}, and nothing else does -- "
        "nothing discovers that page on its own"
    )
    assert named in tracked(), f"{named} is not tracked"


def test_the_bridge_exists_and_points_at_the_entry_point() -> None:
    """Measured, not assumed. Claude Code reads this file and not
    `AGENTS.md`; without it, the move that was made for parity leaves one
    vendor reading nothing."""
    assert BRIDGE in tracked(), (
        f"{BRIDGE} is not tracked. It is the only thing Claude Code reads at "
        f"the root, so without it that tool never reaches {ENTRY_POINT} and "
        "the run sheet is unreachable for it"
    )
    assert ENTRY_POINT in (ROOT / BRIDGE).read_text(encoding="utf-8"), (
        f"{BRIDGE} does not name {ENTRY_POINT}, which is the only thing it is for"
    )


def test_the_bridge_restates_nothing() -> None:
    """It is a pointer. The moment it carries a procedure it is the second
    copy the whole move was made to avoid, and it is the copy that goes
    stale, because nothing generates it."""
    lines = (ROOT / BRIDGE).read_text(encoding="utf-8").splitlines()
    body = [line for line in lines if line.strip()]
    assert len(body) <= BRIDGE_MAX_LINES, (
        f"{BRIDGE} is {len(body)} lines. It is a bridge to {ENTRY_POINT}, not "
        "a page: anything it says for itself is a second statement of "
        "something already written once"
    )
    run_sheet = (ROOT / RUN_SHEET_PATH).read_text(encoding="utf-8")
    headings = [line for line in run_sheet.splitlines() if line.startswith("## ")]
    copied = [heading for heading in headings if heading in lines]
    assert not copied, (
        f"{BRIDGE} carries {copied} out of {RUN_SHEET_PATH.as_posix()}. A "
        "bridge that started restating the run sheet is the third rendering "
        "of one sequence, arriving as a convenience"
    )
