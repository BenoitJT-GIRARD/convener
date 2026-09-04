"""External integrations: what they need, and what happens without them.

An integration with no secret set is *absent*. For most integrations that
is a normal state -- never an error, and nothing in this module raises
because a secret is missing. The exceptions are declared, not hard-coded
here: `absent_is_normal: false` in `declarations/integrations.yml` (carried on
`Integration` below) marks a row whose absence is not a harmless fallback,
and `cli/declaration.py::render_check` is what turns the flag into the operator-facing
text.

**Three rows carry it today**, not one -- `event_keys` (see
`tools/convener_ops/journey/eventkeys.py`), `retention_token` and
`certificate_fingerprint`. This paragraph used to say "the one exception ...
`event_keys` is that row today", which was true when it was written and had
quietly stopped being so; it was corrected while counting the
rows for the cockpit's settings screen, and left the same sentence standing
in the declaration's own header and in `Integration.absent_is_normal`'s
comment below -- the first of those being the more authoritative of the two,
and the one the settings screen reads and ships into the demonstration. Task
8 corrected both. Nothing read the count, which is exactly why nothing
noticed; `tools/tests/declaration/test_integrations.py` reads it against that header
now.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

ABSENT = "absent"
TRIAL = "trial"
PRODUCTION = "production"


@dataclass(frozen=True)
class Integration:
    name: str
    label: str
    secrets: list[str]
    #: What this integration does when it *is* set, and what to fill in to
    #: get there. Required, like `absent_behaviour` beside it and for the
    #: mirror-image reason: every row said what breaks without it and no row
    #: said what it was for, so a maintainer reading the cockpit's settings
    #: screen could see five SMTP secrets and no way to learn that they
    #: serve three scheduled messages to participants rather than a send
    #: button for the event journey's own templates. A row that cannot say
    #: what it is for is a row nobody can decide whether to configure.
    purpose: str
    absent_behaviour: str
    #: True for every row but three. See the module docstring; which rows
    #: those are is data, not a name checked against a hard-coded list, so
    #: a future integration with the same property declares itself the
    #: same way.
    absent_is_normal: bool = True
    state: str = ABSENT
    missing: list[str] = field(default_factory=list)


def load_declaration(path: Path) -> list[Integration]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("integrations") or []
    return [
        Integration(
            name=entry["name"],
            label=entry["label"],
            secrets=list(entry.get("secrets") or []),
            purpose=entry["purpose"],
            absent_behaviour=entry["absent_behaviour"],
            absent_is_normal=bool(entry.get("absent_is_normal", True)),
        )
        for entry in entries
    ]


def _is_set(env: Mapping[str, str], key: str) -> bool:
    return bool(env.get(key, "").strip())


def resolve_states(
    integrations: list[Integration], env: Mapping[str, str]
) -> list[Integration]:
    resolved: list[Integration] = []
    for integration in integrations:
        missing = [s for s in integration.secrets if not _is_set(env, s)]
        if missing:
            state = ABSENT
        elif _is_set(env, f"CONVENER_{integration.name.upper()}_TRIAL"):
            state = TRIAL
        else:
            state = PRODUCTION
        resolved.append(replace(integration, state=state, missing=missing))
    return resolved
