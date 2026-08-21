"""External integrations: what they need, and what happens without them.

An integration with no secret set is *absent*. For every integration but
one, that is a normal state -- never an error, and nothing in this module
raises because a secret is missing. The one exception is declared, not
hard-coded here: `absent_is_normal: false` in `config/integrations.yml`
(carried on `Integration` below) marks a row whose absence is not a
harmless fallback. `event_keys` is that row today -- see
`tools/convener_ops/eventkeys.py` for why -- and `cli.py::render_check` is what
turns the flag into the operator-facing text.
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
    absent_behaviour: str
    #: True for every row but one. See the module docstring; the exception
    #: is data, not a name checked against a hard-coded list, so a future
    #: integration with the same property declares itself the same way.
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
