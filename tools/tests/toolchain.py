"""A missing toolchain: a skip on a developer's machine, a failure on a
runner -- D-25.

Two modules need this rule and neither owns it. `test_second_instance.py`
builds this repository as a different instance, which needs `node` and both
`node_modules`. `test_published.py` loads the four configurations a build
loads, through Vite's own `loadConfigFromFile`, which needs `app/`'s own copy
of Vite. Each absence means one thing on a laptop and the opposite on a
runner, and a second spelling of that sentence is the copy this repository
refuses everywhere else -- so it is written once, here, and the branch is
proved once, by `test_second_instance.py::test_a_missing_toolchain_skips_on_a_
laptop_and_fails_on_a_runner`.

A skip is not wrong in itself: a developer who has never run `npm ci`
genuinely cannot build anything, and neither module may install the packages
for them, because installing them is the one thing in this suite that would
touch the network. What is wrong is one sentence covering that machine *and*
the one environment where the packages are installed on purpose.
`quality.yml`'s own `python` job sets up node 22 and runs `npm ci` in both
`app/` and `site/` before it runs `pytest`, so on a runner their absence means
that install stopped happening -- and a skip there would let the property a
module exists to hold not run at all while the suite reported green.

That is the failure D-25 names, and it has been committed in both directions.
Quiet where it should have been loud: a fresh clone passed the entire suite
without the second-instance build ever executing. Loud where it should have
been quiet: a fresh derivation, following its own published procedure, met
four red bundle tests that meant only that `npm ci` had not been run yet. The
answer to both is one sentence -- the absence is loud where it means something
is broken, and quiet where it means nothing at all.
"""

from __future__ import annotations

import os
from typing import Final, NoReturn

import pytest

#: The environment variables an automated run sets for itself. GitHub's
#: runner sets both; `CI` alone is what nearly every other service sets,
#: and it is here so that moving this project off GitHub Actions cannot
#: silently restore the skip `absent` refuses below.
AUTOMATED: Final = ("CI", "GITHUB_ACTIONS")


def automated_run() -> bool:
    """Whether this suite is running somewhere a toolchain was installed
    for it. `false` and `0` are read as unset, because a variable set to
    the word "false" is how a job turns one off."""
    return any(
        os.environ.get(name, "").strip().lower() not in ("", "false", "0")
        for name in AUTOMATED
    )


def absent(missing: str, remedy: str, *, unrun: str) -> NoReturn:
    """Skip, or fail by name where a skip would be a green suite claiming
    a coverage it does not have.

    `unrun` is what did not happen, and the caller names it because this
    module cannot: a failure saying only that a toolchain is missing
    leaves a reader to work out which property stopped being checked,
    which is the whole cost of the failure it exists to report.
    """
    if automated_run():
        pytest.fail(
            f"{missing}. This is an automated run "
            f"({' or '.join(AUTOMATED)} is set), where quality.yml's own "
            "`python` job installs node and both node_modules before it "
            "runs pytest -- so this is a broken pipeline rather than a "
            f"machine without a toolchain, and {unrun}. {remedy}",
            pytrace=False,
        )
    pytest.skip(f"{missing} -- {remedy}")
