"""What a command hands back to the workflow step that ran it.

A step reads its predecessor's answer out of `$GITHUB_OUTPUT`, and a
command run outside Actions has no such file. One writer for both, so the
fallback -- print it, rather than lose it -- cannot drift between the
commands that use it.
"""

from __future__ import annotations

import os


def write(line: str) -> None:
    """`line` (already `key=value\n`-shaped, one or more) to
    `$GITHUB_OUTPUT`, or printed when that path is unset -- a run outside
    Actions, the "inspectable instead of silent" idiom
    `resolve_registration_secret` originated. Shared with
    `handle_registration` now, so the fallback cannot drift between the
    two call sites."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(line)
    else:
        print(line, end="")
