"""What holds the README's four pictures to a build nobody's identity
reaches.

`screenshots/` is the product's, so its four rasters travel into the
derived public repository exactly as committed. They used to be taken
from a build of *this* instance, which put one series' name and one
series' editions into four files no later check could read:
`convener_ops.derivation.derivation_guard` says in every report it writes
that it did not read the non-text blobs, and `test_second_instance.py`'s
sweep skips a `.png` for the same reason. `docs/assets/zoom-background.png`
had already been deleted for exactly that.

What is checkable here, and what is not
---------------------------------------
**Not the pixels.** Nothing in this repository can look at a committed
raster and say which build produced it, or whether one was produced by a
build at all. A picture pasted in by hand would pass everything below,
and no test written in any language available here would catch it. That
is the limit, and it is why the check is aimed at the only mechanism that
can put a file in that directory rather than at the files.

**The renderer's refusal is.** `render-readme-shots.mjs` stops unless
every value the declaration it can see carries about who is publishing is
still the example's, so the only repository it can photograph is one
carrying nobody's identity. Both halves of that are proved below by
running it: it refuses here, and it gets past the refusal in a tree whose
declaration is the example's -- a refusal that fired unconditionally
would satisfy the first test and fail the second.

**The set of pictures is.** Every tracked raster under `screenshots/` has
to be one `SHOTS` promises, so a fifth image cannot arrive beside the four
without the renderer being taught to produce it.
"""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404
from pathlib import Path
from typing import Final

import instance_identity
import pytest
import render_readme_shots
import toolchain

from convener_ops.declaration import published
from convener_ops.declaration.paths import repo_root

ROOT = repo_root()

#: The renderer, and the directory it has to be run from -- puppeteer
#: resolves out of `tools/visuals/` and nowhere else.
RENDERER: Final = Path("tools") / "visuals" / "render-readme-shots.mjs"

#: Where the pictures are.
SHOTS_DIR: Final = "screenshots"

#: What did not happen when `node` is absent, in the words
#: `toolchain.absent` carries.
_NEVER_RUN: Final = "the renderer's own refusal was never run"

#: `name: 'cockpit',` in the renderer's own `SHOTS` table.
_SHOT_NAME = re.compile(r"^\s*name: '([a-z-]+)',$", re.MULTILINE)


def _node_or_skip() -> None:
    if shutil.which("node") is None:
        toolchain.absent(
            "node is not on PATH, so the renderer cannot be run at all",
            "Install Node 22.",
            unrun=_NEVER_RUN,
        )


def _run_renderer(root: Path) -> subprocess.CompletedProcess[str]:
    """The renderer, in `root`, from the directory it lives in."""
    return subprocess.run(  # nosec B603 B607
        ["node", str(root / RENDERER)],
        cwd=root / RENDERER.parent,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_the_renderer_refuses_the_repository_it_is_committed_in() -> None:
    """The whole of the fix, run rather than read.

    This repository is configured -- `published.unconfigured` returns
    nothing for it -- so the renderer must stop, and it must say which
    values made it stop, because a reader told only "configured" goes
    looking through a file instead of at a line.

    The guard above is what the derived repository needs, and it was
    missing: there the declaration *is* the example's, so the renderer is
    right to run and this test failed by construction in every derivation
    -- red for the one reason it can never fix, which is the shape
    `instance_identity.ONE_INSTANCE` exists to name. The assertion below
    stays as well: it is the same condition asked where a failure would
    otherwise be silent, on a repository the skip did not catch.
    """
    _node_or_skip()
    assert published.unconfigured(ROOT) == (), (
        "this instance's declaration still carries the example's values, "
        "so the test below cannot tell a refusal from an accident -- "
        "configure instance/config.json"
    )
    result = _run_renderer(ROOT)
    assert result.returncode != 0, (
        "the renderer ran to completion in a configured repository, which "
        f"is how four rasters carrying this instance's identity reach {SHOTS_DIR}/ "
        f"where nothing can read them again:\n{result.stdout[-2000:]}"
    )
    assert "this repository is configured" in result.stderr, result.stderr[-2000:]
    for name in ("identity.organisation", "identity.series", "published_url"):
        assert name in result.stderr, (
            f"the refusal does not name {name}, so it does not tell a reader "
            f"which line to look at:\n{result.stderr[-2000:]}"
        )


def test_the_refusal_lifts_where_the_example_is_what_declares(
    tmp_path: Path,
) -> None:
    """And is therefore a condition rather than a wall.

    The smallest tree the refusal can be answered in: the example's
    declaration on both sides of the comparison, and the renderer. It gets
    past the refusal and stops at the next thing it insists on -- a real
    build to photograph -- which is the only way to tell "it accepted this
    declaration" from "it refuses everything".
    """
    _node_or_skip()
    declaration = ROOT / published.EXAMPLE_INSTANCE_PATH
    for relative in (published.INSTANCE_PATH, published.EXAMPLE_INSTANCE_PATH):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(declaration, tmp_path / relative)
    (tmp_path / RENDERER).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / RENDERER, tmp_path / RENDERER)

    result = _run_renderer(tmp_path)
    assert "this repository is configured" not in result.stderr, (
        "the renderer refused a tree declared by the example instance itself, "
        f"which is the one tree it exists to photograph:\n{result.stderr[-2000:]}"
    )
    assert "build it first" in result.stderr, (
        "the renderer got past the refusal and stopped somewhere other than "
        f"the missing build, so this test is no longer reading it:\n"
        f"{result.stderr[-2000:]}"
    )


def _promised() -> set[str]:
    text = (ROOT / RENDERER).read_text(encoding="utf-8")
    names = set(_SHOT_NAME.findall(text))
    assert names, f"no `name:` entries found in {RENDERER.as_posix()}'s SHOTS table"
    return names


def _tracked() -> set[str]:
    listing = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", SHOTS_DIR],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return {Path(name).stem for name in listing if name.endswith(".png")}


def test_every_tracked_raster_is_one_the_renderer_promises() -> None:
    """A fifth picture cannot appear beside the four by any other route.

    Both directions: a raster nothing renders is one somebody drew or
    pasted, and a subject the renderer promises with no file to show for
    it is a run that reported success on three of four.
    """
    assert _tracked() == _promised()


@pytest.mark.parametrize("name", sorted(_promised()))
def test_each_promised_picture_is_committed(name: str) -> None:
    """One at a time, so a missing file says which one."""
    assert (ROOT / SHOTS_DIR / f"{name}.png").is_file()


def test_the_only_documented_way_to_refresh_them_is_the_driver() -> None:
    """`screenshots/README.md` is where somebody looks before running
    anything, so it has to send them to the script that builds the example
    instance rather than to the renderer they would otherwise run here."""
    text = (ROOT / SHOTS_DIR / "README.md").read_text(encoding="utf-8")
    assert "scripts/render_readme_shots.py" in text
    assert (ROOT / "tools" / "scripts" / "render_readme_shots.py").is_file()


def test_the_driver_and_the_renderer_agree_on_where_the_renderer_is() -> None:
    """The driver runs the renderer by path inside the built tree; a
    rename that missed one of the two would fail at the end of a build
    that takes a browser and four bundles to reach."""
    assert render_readme_shots.RENDERER == RENDERER
    assert render_readme_shots.SHOTS == SHOTS_DIR
