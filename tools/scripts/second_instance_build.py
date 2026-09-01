"""This repository, built as the instance `examples/the-example-collective/` declares.

The manoeuvre is one thing and it has two consumers, so it lives here
rather than inside either of them. `tools/tests/repository/test_second_instance.py`
drives it to sweep what comes out for anything of the instance that
happens to run this repository; `tools/scripts/render_readme_shots.py`
drives it so that the pictures `README.md` shows are pictures of the
example collective and never of that instance. Both need the same tree
built the same way, and a second copy of these forty lines would be two
builds free to diverge.

How the tree is constructed
---------------------------
Not by overriding values, and not by patching this repository in place --
by building a repository that *is* another instance:

1. every tracked file is copied into a scratch tree;
2. every file `declarations/boundary.yml` hands to the instance is **deleted**
   from that tree (`boundary.instance_files`, so `kept:` files stay);
3. `examples/the-example-collective/` is laid into the holes that leaves.

The one exception is a `regenerated:` path, which the tree keeps: it is
rewritten in full by a scheduled job on both sides of any merge, so a
duplicate inherits upstream's rather than authoring one.

`node_modules` is linked rather than copied (a junction on Windows, a
symbolic link elsewhere): `npm ci` is a network call and nothing here may
make one, and the packages are the product's, identical in both trees.

**A second process, always.** `registration.SIGNUP_BASE`,
`certificate.VERIFICATION_BASE` and `confirmation.CONTACT_EMAIL` are
module-level constants, resolved once at import. Every command below
therefore runs in a subprocess of its own: a second instance is a second
*process*, never a second call inside this one.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from convener_ops.declaration import boundary
from convener_ops.declaration.paths import repo_root

ROOT = repo_root()

#: Where the fictional instance lives. Product-owned: upstream ships it,
#: upstream maintains it, and a duplicate that edits it is editing an
#: example rather than its own configuration.
EXAMPLE = Path("examples") / "the-example-collective"

#: Where this build puts the posters. Not `tools/visuals/`, which the tracked
#: tree already uses for the reference renders and which
#: `convener-render-visuals` regenerates *whole* -- pointing it there would
#: delete them.
POSTERS = "posters"

#: The packages whose `node_modules` a build needs, in the built tree's own
#: terms. `tools/visuals` is here for the screenshot driver: puppeteer
#: resolves from that directory and nowhere else.
NODE_PACKAGES: Final = ("app", "site", "tools/visuals")

#: Run one `convener_ops.cli` entry point in a process of its own. `sys.argv`
#: is rebuilt because several of those functions read it for their own
#: arguments, and `sys.executable` is the calling interpreter, which is the
#: one with `convener_ops` installed -- no `uv` on PATH, no console script
#: to locate.
CLI_RUNNER: Final = (
    "import sys\n"
    "from convener_ops import cli\n"
    "name = sys.argv[1]\n"
    "sys.argv = [name.replace('_', '-'), *sys.argv[2:]]\n"
    "raise SystemExit(getattr(cli, name)())\n"
)

#: Cleared for the build. `deploy.yml` forwards these from repository
#: variables and D-13 makes their absence the ordinary state; letting a
#: developer's own environment supply one would build a second instance
#: pointed at this one's relay.
BUILD_VARIABLES: Final = (
    "VITE_AUTH_PROXY_URL",
    "VITE_GITHUB_APP_CLIENT_ID",
    "VITE_SIGNUP_RELAY_URL",
)


def link_directory(target: Path, link: Path) -> None:
    """`link` -> `target`, without needing a privilege.

    Windows refuses `os.symlink` to anybody without
    `SeCreateSymbolicLinkPrivilege`, which a developer's shell and a CI
    runner both ordinarily lack; a directory *junction* needs none and
    behaves like a directory for every filesystem call `node` makes.
    `shutil.rmtree` unlinks a junction rather than descending into it
    (Python 3.12's `DirEntry.is_junction`), and every caller here removes
    the links before anything else cleans up, so a scratch tree can never
    take `node_modules` with it.
    """
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
        return
    os.symlink(target, link, target_is_directory=True)


def link_node_modules(root: Path, packages: Iterable[str]) -> list[Path]:
    """This repository's own installed packages, reachable from the built
    tree. Returns the links, for the caller's own `finally`."""
    links = [root / package / "node_modules" for package in packages]
    for link in links:
        link.parent.mkdir(parents=True, exist_ok=True)
        link_directory(ROOT / link.relative_to(root), link)
    return links


def unlink_node_modules(links: Iterable[Path]) -> None:
    """Undo `link_node_modules`. `os.rmdir` unlinks a junction and a
    symbolic link alike; it never descends into one."""
    for link in links:
        if link.exists():
            os.rmdir(link)


def run(args: list[str], *, cwd: Path, env: dict[str, str], what: str) -> None:
    result = subprocess.run(  # nosec B603
        args, cwd=cwd, env=env, capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        raise AssertionError(
            f"the second instance's build failed at {what}:\n"
            f"{result.stdout[-4000:]}\n{result.stderr[-4000:]}"
        )


def environment(root: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in BUILD_VARIABLES}
    env["CONVENER_REPO_ROOT"] = str(root)
    return env


def lay_out(root: Path) -> None:
    """The scratch tree: this repository's product, the example's instance."""
    tracked = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert len(tracked) > 100, f"the file listing found almost nothing: {tracked}"
    for name in tracked:
        source = ROOT / name
        if not source.is_file():
            continue
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    declared = boundary.load(ROOT)
    inherited = set(declared.regenerated_paths)
    for name in boundary.instance_files(ROOT, declared):
        if name in inherited:
            continue
        owned = root / name
        if owned.is_file():
            owned.unlink()

    for source in sorted((ROOT / EXAMPLE).rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(ROOT / EXAMPLE)
        if relative.parts[0] == "README.md":
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def publish(root: Path) -> None:
    """Everything the scheduled jobs derive, in the order they derive it.

    The same commands `deploy.yml` and `publish-showcase.yml` run, and in
    their order: the charter's stylesheets and templates before either
    bundler reads them, the public projection before the showcase's
    fixture is refreshed from it.
    """
    env = environment(root)
    for name in (
        "validate",
        "public_data",
        "survey_status_public_data",
        "registration_routing_public_data",
        "certificates_public_data",
        "agenda_internal",
    ):
        run(
            [sys.executable, "-c", CLI_RUNNER, name],
            cwd=root,
            env=env,
            what=f"convener-{name.replace('_', '-')}",
        )
    run(
        [sys.executable, str(root / "tools" / "scripts" / "generate_brand_css.py")],
        cwd=root,
        env=env,
        what="generate_brand_css.py",
    )
    run(
        [sys.executable, str(root / "tools" / "scripts" / "generate_motif.py")],
        cwd=root,
        env=env,
        what="generate_motif.py",
    )
    run(
        [sys.executable, "-c", CLI_RUNNER, "render_visuals", str(root / POSTERS)],
        cwd=root,
        env=env,
        what="convener-render-visuals",
    )
    # `publish-showcase.yml`'s own "Refresh site data" step: the showcase
    # builds from a committed fixture, refreshed from the public
    # projection before every real build.
    shutil.copyfile(
        root / "instance" / "public-data" / "events-public.json",
        root / "site" / "src" / "_data" / "events.json",
    )


def build(root: Path) -> None:
    """The two bundlers, invoked the way a build invokes them."""
    env = environment(root)
    for script in (
        "copy-fonts.mjs",
        "copy-handbook.mjs",
        "copy-event-keys.mjs",
        "copy-signing-keys.mjs",
        "copy-certificates.mjs",
        "copy-survey-status.mjs",
    ):
        run(
            ["node", str(root / "app" / "scripts" / script)],
            cwd=root / "app",
            env=env,
            what=script,
        )
    vite = root / "app" / "node_modules" / "vite" / "bin" / "vite.js"
    for island in ("", "island-signup", "island-verify", "island-survey"):
        mode = ["--mode", island] if island else []
        run(
            ["node", str(vite), "build", *mode],
            cwd=root / "app",
            env=env,
            what=f"vite build {island or 'production'}",
        )
    eleventy = root / "site" / "node_modules" / "@11ty" / "eleventy" / "cmd.cjs"
    run(
        ["node", str(eleventy), f"--output={(root / 'site' / '_site').as_posix()}"],
        cwd=root / "site",
        env=env,
        what="eleventy",
    )
