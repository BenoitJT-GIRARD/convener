"""Command-line entry points. This is the only module that touches the disk."""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from convener_ops.integrations import Integration, load_declaration, resolve_states
from convener_ops.paths import repo_root
from convener_ops.validate import validate_config, validate_speakers


def _load(path: Path) -> tuple[Any, list[str]]:
    if not path.exists():
        return None, [f"{path.name}: file missing"]
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")), []
    except yaml.YAMLError as exc:
        return None, [f"{path.name}: invalid YAML - {exc}"]


def validate() -> int:
    root = repo_root()
    speakers, errors = _load(root / "data" / "speakers.yml")
    cfg, cfg_errors = _load(root / "data" / "config.yml")
    errors += cfg_errors

    if speakers is not None:
        errors += validate_speakers(speakers)
    if cfg is not None:
        errors += validate_config(cfg)

    if errors:
        print("Data validation FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1

    count = len(speakers or [])
    print(f"Data OK - {count} speakers, config=ok")
    return 0


_SYMBOL = {"production": "[ok]", "trial": "[trial]", "absent": "[--]"}


def render_check(integrations: list[Integration]) -> str:
    lines = ["Integration status", "=================="]
    for integration in integrations:
        lines.append(
            f"{_SYMBOL[integration.state]} {integration.label} - {integration.state}"
        )
        if integration.missing:
            lines.append(f"      waiting on: {', '.join(integration.missing)}")
            lines.append(f"      meanwhile:  {integration.absent_behaviour.strip()}")
    counts = Counter(i.state for i in integrations)
    summary = ", ".join(
        f"{counts[state]} {state}"
        for state in ("production", "trial", "absent")
        if counts[state]
    )
    lines.append("")
    lines.append(f"Summary: {summary}")
    lines.append("An absent integration is a normal state, not a failure.")
    return "\n".join(lines)


def check_config() -> int:
    declaration = repo_root() / "config" / "integrations.yml"
    integrations = resolve_states(load_declaration(declaration), env=os.environ)
    print(render_check(integrations))
    return 0


if __name__ == "__main__":
    sys.exit(validate())
