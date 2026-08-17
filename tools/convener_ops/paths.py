"""Locate the repository root without depending on this file's own depth."""
from __future__ import annotations

import os
from pathlib import Path

_MARKER = Path("data") / "config.yml"


def repo_root(start: Path | None = None) -> Path:
    """Walk upwards until the repository marker is found.

    Honours CONVENER_REPO_ROOT so tests and CI can point elsewhere.
    """
    override = os.environ.get("CONVENER_REPO_ROOT")
    if override:
        return Path(override).resolve()
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / _MARKER).exists():
            return candidate
    raise FileNotFoundError(f"repository root not found above {here}")
