"""Where a test of the cockpit sits is what its name says it is about.

`app/tests/` held ninety-two files in one directory, in one alphabet:
`agenda.test.ts`, `announce-drafts.test.ts`, `api.test.ts` are three
unrelated subjects in a row, and the way to find the module holding a rule
was to open files until one of them held it. That is the defect
`tools/tests/repository/test_package_layout.py` describes on the Python
side, and the Python side had already been sorted: the repository gave two
answers to one question, `convener_ops/`'s own shape and a flat suite
beside it.

The suite is one directory per domain of `app/src/` now, plus two:

* **`scripts/`** for the build's own plumbing under `app/scripts/`, which
  has tests and nothing in `src/` to sit under. It is a directory of
  `app/` rather than of `app/src/`, and that is the whole of the
  exception.
* **`helpers/`** for what several modules need and none owns -- the
  speaker and config doubles, the boundary samples, the reader of the one
  instance, and the `setupFiles` entry `vite.config.ts` names. The same
  directory, for the same reason, as `tools/tests/helpers/`.

**Nothing sits at the root.** A module left there is the drawer this
structure exists to close, and it is the one shape a directory listing
cannot tell from a module that has simply not been placed yet.

**Every other directory is a directory of `app/src/`, read rather than
listed.** A domain added to the cockpit is a directory this suite may
open with nothing here to edit; a directory named after nothing is
refused by name. `net/`, `signup/` and `survey/` carry one module each
and are directories all the same: which domain a test is about is not a
question of how many tests that domain has yet.
"""

from __future__ import annotations

from typing import Final

from convener_ops.declaration.paths import repo_root
from repository.test_cross_references import _tracked

ROOT: Final = repo_root()

#: The suite, and the source tree it mirrors, root-relative.
SUITE: Final = "app/tests/"
SOURCE: Final = "app/src/"

#: The one directory that mirrors nothing under `app/src/`, and the one
#: that mirrors nothing at all. `scripts/` is `app/scripts/`, which is the
#: build's own plumbing; `helpers/` is what several modules need and none
#: owns.
BUILD_SCRIPTS: Final = "scripts"
SHARED: Final = "helpers"

#: What a test module of this suite is called, either way vitest spells
#: it.
TEST_SUFFIXES: Final = (".test.ts", ".test.tsx")


def _suite_files() -> list[str]:
    """Every tracked file of the cockpit's suite, root-relative."""
    return [name for name in _tracked() if name.startswith(SUITE)]


def _domains() -> set[str]:
    """Every directory of `app/src/`, read from what git tracks."""
    return {
        name[len(SOURCE) :].split("/", 1)[0]
        for name in _tracked()
        if name.startswith(SOURCE) and "/" in name[len(SOURCE) :]
    }


def test_the_suite_walk_finds_the_modules_this_repository_has() -> None:
    """Reader control before the three properties that rest on it: a walk
    matching nothing would satisfy every one of them by finding no module
    out of place."""
    found = _suite_files()
    assert len(found) > 50, (
        f"the walk over {SUITE} found {len(found)} file(s), which is not a "
        "suite of this size -- the reader itself is wrong"
    )
    assert _domains(), f"the walk over {SOURCE} found no domain at all"


def test_no_test_module_sits_at_the_root_of_the_suite() -> None:
    """The drawer. A module at the root is one nobody has said what it is
    about, and it is the shape ninety-two of these were in."""
    loose = sorted(
        name
        for name in _suite_files()
        if "/" not in name[len(SUITE) :] and name.endswith(TEST_SUFFIXES)
    )
    assert loose == [], (
        f"{loose} sit at the root of {SUITE} rather than under the domain "
        "of `app/src/` they are about"
    )


def test_every_directory_of_the_suite_names_a_domain_of_the_source() -> None:
    """The mirror itself, read from both trees rather than from a list
    here: a domain added to `app/src/` is a directory this suite may open,
    and a directory named after nothing is refused by name."""
    domains = _domains() | {BUILD_SCRIPTS, SHARED}
    directories = {
        name[len(SUITE) :].split("/", 1)[0]
        for name in _suite_files()
        if "/" in name[len(SUITE) :]
    }
    stray = sorted(directories - domains)
    assert stray == [], (
        f"{stray} under {SUITE} name no domain of {SOURCE}, and neither "
        f"{BUILD_SCRIPTS}/ nor {SHARED}/"
    )


def test_what_no_module_owns_sits_in_the_one_directory_for_it() -> None:
    """A file of this suite that is not a test module is something several
    modules share, and it has one home. The alternative is a double kept
    beside the first module that needed it, which is how a suite grows two
    of them."""
    misplaced = sorted(
        name
        for name in _suite_files()
        if not name.endswith(TEST_SUFFIXES) and not name.startswith(f"{SUITE}{SHARED}/")
    )
    assert misplaced == [], (
        f"{misplaced} are not test modules, so they are shared and belong "
        f"in {SUITE}{SHARED}/"
    )
