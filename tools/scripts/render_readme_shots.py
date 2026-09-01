"""Refresh the four pictures `README.md` shows.

`tools/visuals/render-readme-shots.mjs` takes the pictures. It refuses to
take them anywhere but in a repository whose declaration is the one
`examples/the-example-collective/instance/config.json` carries, and this script is what
gives it such a repository: `second_instance_build.lay_out` builds one in a
scratch directory -- this repository's product, the example collective's
instance -- and the renderer is then run *inside that tree*, on its own
copy of itself.

Why not simply render here
--------------------------
Because a masthead is compiled, not fetched. `app/vite.config.ts` carries
`identity` into the cockpit's bundle through Vite's own `define` and
`site/.eleventy.js` composes the same values into every showcase page, so
a picture of a build made here is a picture of *this* series' name, in
four files the derivation carries verbatim into the public repository --
where nothing can read them back out again, because
`convener_ops.derivation.derivation_guard` cannot read a raster and says
so in every report it writes. `docs/assets/zoom-background.png` was
removed for exactly that once already.

So the images are taken from a build nobody's identity reaches, which is
the same answer `convener-render-visual-fixtures` already gives for the
reference renders under `tools/visuals/references/`: render as the
example, and there is nothing in the file to leak.

What comes back
---------------
The four PNGs, copied over the tracked ones. The set is checked against
what the index holds rather than against what the run happened to write:
a run that quietly produced three of four would otherwise leave one
stale picture claiming to be current, which is the failure a screenshot
in a README cannot survive.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Final

import second_instance_build

#: Where the pictures live, and the one directory this script writes to
#: outside its own scratch tree.
SHOTS = "assets/screenshots"

#: The renderer, in the built tree's own terms.
RENDERER: Final = Path("tools") / "visuals" / "render-readme-shots.mjs"


def _tracked_shots() -> set[str]:
    """The rasters `assets/screenshots/` holds, as git sees them. The index is
    the authority rather than the directory listing: an untracked file
    somebody dropped there is not a picture this repository publishes."""
    listing = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", SHOTS],
        cwd=second_instance_build.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return {Path(name).name for name in listing if name.endswith(".png")}


def _render(root: Path) -> None:
    """The renderer, in the built tree, against the built tree."""
    second_instance_build.run(
        ["node", str(root / RENDERER)],
        cwd=root / RENDERER.parent,
        env=second_instance_build.environment(root),
        what="render-readme-shots.mjs",
    )


def main() -> int:
    expected = _tracked_shots()
    if not expected:
        print(f"::error::{SHOTS}/ holds no tracked raster to refresh", file=sys.stderr)
        return 1

    scratch = Path(tempfile.mkdtemp(prefix="convener-readme-shots-")) / "repository"
    scratch.mkdir()
    links: list[Path] = []
    try:
        second_instance_build.lay_out(scratch)
        links = second_instance_build.link_node_modules(
            scratch, second_instance_build.NODE_PACKAGES
        )
        second_instance_build.publish(scratch)
        second_instance_build.build(scratch)
        _render(scratch)

        produced = {path.name for path in (scratch / SHOTS).glob("*.png")}
        if produced != expected:
            print(
                "::error::the build produced "
                f"{sorted(produced)} where {SHOTS}/ holds {sorted(expected)}",
                file=sys.stderr,
            )
            return 1
        for name in sorted(expected):
            shutil.copyfile(
                scratch / SHOTS / name, second_instance_build.ROOT / SHOTS / name
            )
            print(f"shots: refreshed {SHOTS}/{name}")
    finally:
        second_instance_build.unlink_node_modules(links)
        shutil.rmtree(scratch.parent, ignore_errors=True)
    print(f"shots: refreshed {len(expected)} picture(s) from the example instance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
