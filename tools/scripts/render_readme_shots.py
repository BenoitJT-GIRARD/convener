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

The day it all happens on
-------------------------
One, fixed, and the renderer is only half of what has to answer to it. It
pins the *browser's* clock, which is what stops the inbox's own day counts
moving overnight; this script pins the day the example instance's records are
dated against (`_pin_the_day`, `example_dates`), which is what stops the
records themselves moving every seventh night now that they follow the week
they are read in. Both come off the same committed fixture, so the four
pictures are one moment rather than four.

What comes back
---------------
The four PNGs, copied over the tracked ones. The set is checked against
what the index holds rather than against what the run happened to write:
a run that quietly produced three of four would otherwise leave one
stale picture claiming to be current, which is the failure a screenshot
in a README cannot survive.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Final

import example_dates
import second_instance_build

#: Where the pictures live, and the one directory this script writes to
#: outside its own scratch tree.
SHOTS = "assets/screenshots"

#: The renderer, in the built tree's own terms.
RENDERER: Final = Path("tools") / "visuals" / "render-readme-shots.mjs"

#: The one signed certificate this repository commits. The renderer already
#: reads it for the day it pins the browser's clock to; this script reads it
#: for the same day, to pin the *records* to it -- see `_pin_the_day`.
CERTIFICATE: Final = (
    Path("tools") / "tests" / "fixtures" / "certificate-verification.json"
)


def _pin_the_day() -> str:
    """Fix the day the example instance's own records are dated against, for
    this whole run.

    `examples/the-example-collective/instance/data/` is written for one day
    and read against the week it is read in (`example_dates`), which is what
    keeps the demonstration's inbox from filling with things it is late on.
    Left alone here, that would move the fixture forward every seventh night
    and change `cockpit.png` and `event-page.png` for a reason that has
    nothing to do with the software -- the same failure the browser's own
    clock had before it was pinned, one layer down and this time reaching two
    of the four pictures rather than one.

    So the day is set in this process's own environment, before anything
    reads it: `lay_out` reads it here, and `second_instance_build.environment`
    hands the same value to every child, which is where
    `app/scripts/example-instance.mjs` reads it when it compiles the records
    into the cockpit's bundle. One day, one moment, four pictures.

    The day the certificate on the verification shot says its holder
    attended, read off that fixture rather than written here -- the identical
    value the renderer pins the browser to, so a reader comparing two of
    these pictures is looking at one instant.
    """
    fixture = json.loads(
        (second_instance_build.ROOT / CERTIFICATE).read_text(encoding="utf-8")
    )
    day = str(fixture["signed_example"]["payload_decoded"]["date"])
    os.environ[example_dates.TODAY_ENV] = day
    return day


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

    day = _pin_the_day()
    print(f"shots: the example instance's records are dated against {day}")

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
