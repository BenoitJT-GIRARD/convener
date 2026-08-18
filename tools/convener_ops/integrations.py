"""External integrations: what they need, and what happens without them.

An integration with no secret set is *absent*, which is a normal state — never
an error. Nothing in this module raises because a secret is missing.
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
