"""The three relays are linted by one configuration, and each of them adds
only what is its own.

`services/*/eslint.config.js` was the same twenty-five lines three times,
differing in the six globals each relay's own source reaches for. Three
files that agree on everything but six lines are worse than three that
agree on nothing: they read as three configurations, so a rule added to
one is a rule missing from the other two, and nothing says so. The shape
and the rules are `services/eslint.config.base.mjs` now, and a relay's own
file passes it a list of globals.

**What is refused, and what is not.** A relay that does not read the
shared file, and a relay that restates the shape after reading it -- its
own `rules:`, its own `ecmaVersion:`, its own `sourceType:`. What is not
refused is a second configuration block: `signup-relay` has one, granting
`Buffer` under `test/` alone because the Worker runtime it deploys to has
no `Buffer` and a global granted for the tests would let `src/` reference
it and still lint clean. That is a fact about one relay, it is written
where it is true, and a rule refusing it would refuse the one thing these
files are for.

**The relays are read rather than listed.** A fourth Worker under
`services/` is held to this the day it arrives, with nothing here to edit,
which is the half a list would not do.
"""

from __future__ import annotations

import re
from typing import Final

from convener_ops.declaration.paths import repo_root
from repository.test_cross_references import _tracked

ROOT: Final = repo_root()

#: Where the three Workers live, and what each one's own lint
#: configuration is called.
SERVICES: Final = "services/"
CONFIG: Final = "eslint.config.js"

#: The one file holding the shape and the rules, root-relative.
SHARED: Final = "services/eslint.config.base.mjs"

#: How a relay's own file reaches it. Matched as an import of that exact
#: path rather than as the word, so a comment naming the file is not read
#: as a use of it.
IMPORTS_SHARED: Final = re.compile(
    r"^import\s.*from\s+'\.\./eslint\.config\.base\.mjs';$", re.M
)

#: The keys a relay's own file may not carry: each one is the shape
#: restated, and the shape has one home.
RESTATED: Final = ("rules:", "ecmaVersion:", "sourceType:")


def relay_configs() -> list[str]:
    """Every relay's own lint configuration, root-relative."""
    return sorted(
        name
        for name in _tracked()
        if name.startswith(SERVICES)
        and name.endswith(f"/{CONFIG}")
        and name.count("/") == 2
    )


def test_the_walk_finds_the_relays_this_repository_has() -> None:
    """Reader control: a walk finding nothing would pass every check
    below by having nothing to check."""
    found = relay_configs()
    assert len(found) >= 3, (
        f"the walk over {SERVICES} found {found}, and this repository has "
        "carried three Workers since the registration relay was written"
    )


def test_the_shared_configuration_holds_the_rules() -> None:
    """The other side of the two checks below: they say no relay states a
    rule, and this says the rules are stated somewhere."""
    shared = (ROOT / SHARED).read_text(encoding="utf-8")
    for rule in ("no-unused-vars", "no-undef", "eqeqeq"):
        assert rule in shared, f"{SHARED} no longer declares {rule}"
    assert "export function relayConfig" in shared, (
        f"{SHARED} no longer exports the function each relay calls"
    )


def test_every_relay_reads_the_shared_configuration() -> None:
    """A relay linted by a configuration of its own is a relay held to
    whatever that file happened to say on the day it was copied."""
    missing = [
        name
        for name in relay_configs()
        if not IMPORTS_SHARED.search((ROOT / name).read_text(encoding="utf-8"))
    ]
    assert missing == [], (
        f"{missing} do not import {SHARED}, so they are linted by a "
        "configuration nothing else can reach"
    )


def test_no_relay_restates_the_shape_it_reads() -> None:
    """Importing the shared file and then setting the same keys again is
    the copy back, one indirection later: the import passes the check
    above while the file it imports decides nothing."""
    restated = sorted(
        f"{name} states {key}"
        for name in relay_configs()
        for key in RESTATED
        if key in (ROOT / name).read_text(encoding="utf-8")
    )
    assert restated == [], f"a relay states what {SHARED} states: " + "; ".join(
        restated
    )
