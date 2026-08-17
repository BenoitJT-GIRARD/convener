"""Command-line entry points. This is the only module that touches the disk."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from convener_ops.paths import repo_root
from convener_ops.validate import validate_config, validate_speakers


def _load(path: Path) -> tuple[Any, list[str]]:
    if not path.exists():
        return None, [f"{path.name}: file missing"]
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")), []
    except yaml.YAMLError as exc:
        return None, [f"{path.name}: invalid YAML — {exc}"]


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
    print(f"Data OK — {count} speakers, config=ok")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
