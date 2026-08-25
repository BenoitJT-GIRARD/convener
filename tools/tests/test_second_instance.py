"""Build this repository as a second instance, and refuse anything of the
first in what comes out.

Phase 10, task 5 -- the acceptance criterion the whole phase rests on
(spec § 6). Tasks 1 to 4 each drove a second-instance build by hand and
each found something a single-instance run could not: two sentences the
substitution made ungrammatical, a GitHub team named wrongly in the
operator's own instructions, a forum address set in its own background
colour and therefore invisible in every downloaded poster. This module is
that manoeuvre made permanent.

**A build, not a reading.** `test_published.py` proves that no *source*
writes this instance's identity a second time. That is a different claim,
and a weaker one: a source can be clean while the thing a reader receives
is not, because between them sit four bundlers, a static-site generator,
a handbook copy, two generated SVGs and a poster renderer. So this module
constructs a whole second instance and sweeps what it *produced*.

How the second instance is constructed
--------------------------------------
Not by overriding values, and not by patching this repository in place --
by building a repository that *is* another instance:

1. every tracked file is copied into a scratch tree;
2. every file `config/boundary.yml` hands to the instance is **deleted**
   from that tree (`boundary.instance_files`, so `kept:` files stay);
3. `instances/example/` is laid into the holes that leaves.

Step 2 is why this test also tests the boundary. If a path carrying this
instance's identity is not declared there, it survives the deletion, and
the sweep in step 4 finds it -- the declaration and the proof are the same
mechanism seen from two ends.

The one exception is a `regenerated:` path. `docs/governance/register.md`
is rewritten in full by a scheduled job on both sides of any merge, which
is what that flag means, so a duplicate does not author one before its
first build: it inherits upstream's and its own next push replaces it.
The tree therefore keeps it, and the sweep covers it as inherited. See
`test_the_example_instance_answers_every_path_an_instance_owns`.

`node_modules` is linked rather than copied (a junction on Windows, a
symbolic link elsewhere): `npm ci` is a network call and no test here may
make one, and the packages are the product's, identical in both trees.

What is swept
-------------
Everything a reader receives: the showcase and its feeds (`site/_site`),
all four bundles the cockpit builds and the handbook copied into them
(`app/dist`), the published projections the scheduled jobs write
(`public-data`), the two SVG templates a collaborator downloads
(`docs/assets`), and the posters a collaborator prints (`posters`, this
build's own output directory for `convener-render-visuals`).

What this module cannot see, stated rather than left to be found
-----------------------------------------------------------------
- **Anything that is not derivable from a declaration.** A needle is a
  value `config/instance.json` or the charter in force actually holds
  (`instance_identity.needles`). Three things this instance owns are held
  by neither, so nothing here can look for them: the series' **strapline**
  ("Read together", hard-typed in `visual.py`), the **time
  zone** and the **standing start time** (`Europe/Paris` and 12:30, in
  `visual.py`, `governance.py` and forty-odd other places), and the
  **names of the people** who run the series -- `docs/reference/contacts.md`
  names four of them in a paragraph the cockpit publishes to every
  instance, and `site/src/style.css` names the designer in a comment that
  ships inside the showcase's own stylesheet. Each is recorded in
  `docs/superpowers/inventaire-instance.md`; none can become a needle
  until it becomes a declared value.
- **Bytes.** `BINARY_SUFFIXES` skips images and fonts, and three of them
  are real identity surfaces:
  `app/dist/handbook/assets/zoom-background.png` ships inside the bundle
  swept here and carries the first instance's mark, while
  `visuals/references/*.png` pin what `visual.py` renders. A second
  instance's build regenerates none of them.
- **The edition prefix.** `validate.py::EDITION_RE` fixes an edition code
  as `MRG-` and one to four digits -- an abbreviation of *this* series'
  name, in the product's own validator. The example instance therefore
  numbers a reading group's sessions `MRG-1`, and no needle can catch that
  because both instances are forced to write it.
- **Rows this instance's own history wrote.** `docs/governance/register.md`
  is inherited (above). It holds no identity today because it holds no
  rows; the day it holds some, a duplicate's handbook would publish this
  instance's governance decisions and nothing here would notice, because a
  row is a date, an identifier and a word from a closed vocabulary.
- **A second process.** `registration.SIGNUP_BASE`, `certificate.
  VERIFICATION_BASE` and `confirmation.CONTACT_EMAIL` are module-level
  constants, resolved once at import. Every command below therefore runs
  in its own subprocess: a second instance is a second *process*, never a
  second call inside this one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import instance_identity
import pytest

from convener_ops import boundary
from convener_ops.paths import repo_root

ROOT = repo_root()

#: Where the fictional instance lives. Product-owned: upstream ships it,
#: upstream maintains it, and a duplicate that edits it is editing an
#: example rather than its own configuration.
EXAMPLE = Path("instances") / "example"

#: Where this build puts the posters. Not `visuals/`, which the tracked
#: tree already uses for the reference renders and which
#: `convener-render-visuals` regenerates *whole* -- pointing it there would
#: delete them.
POSTERS = "posters"

#: The instance paths that deliberately have no counterpart under
#: `instances/example/`, each with the reason. Checked in both directions,
#: so a path that gains a counterpart cannot stay listed here and a path
#: that loses one cannot go unnoticed.
DELIBERATELY_ABSENT: Final = {
    "keys/": (
        "A fresh duplicate holds no cryptographic material at all: "
        "generating an event key or a signing key is an operator's act, "
        "never upstream's, and this repository's own keys/ is empty of "
        "keys too. Shipping one in an example would ship a private half "
        "somebody might use."
    ),
    "public-data/": (
        "Empty in a fresh clone by construction -- everything in it is "
        "derived from data/ by the product's own commands, and this "
        "build runs them (see `_publish`). An example that carried a "
        "committed projection would be carrying a stale copy of its own "
        "input."
    ),
    "docs/governance/register.md": (
        "Declared `regenerated: true`: a total re-rendering of one "
        "repository's own commit history, written by a scheduled job on "
        "both sides of any merge. A duplicate does not author one -- it "
        "inherits upstream's and its own next push replaces it -- so an "
        "authored copy here would be an authored copy of a generated "
        "file, which this repository refuses everywhere else."
    ),
}

#: The trees and files this module reads back, relative to the built root.
_ARTEFACT_TREES: Final = ("site/_site", "app/dist", "public-data", POSTERS)
_ARTEFACT_FILES: Final = (
    "docs/assets/announcement-template.svg",
    "docs/assets/flyer-template.svg",
)

#: Run one `convener_ops.cli` entry point in a process of its own. `sys.argv`
#: is rebuilt because several of those functions read it for their own
#: arguments, and `sys.executable` is this suite's own interpreter, which
#: is the one with `convener_ops` installed -- no `uv` on PATH, no console
#: script to locate.
_CLI_RUNNER: Final = (
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
_BUILD_VARIABLES: Final = (
    "VITE_AUTH_PROXY_URL",
    "VITE_GITHUB_APP_CLIENT_ID",
    "VITE_SIGNUP_RELAY_URL",
)


@dataclass(frozen=True)
class Built:
    """A second instance's repository, built."""

    root: Path

    @property
    def artefacts(self) -> list[Path]:
        found: list[Path] = []
        for tree in _ARTEFACT_TREES:
            base = self.root / tree
            if base.is_dir():
                found += sorted(p for p in base.rglob("*") if p.is_file())
        for name in _ARTEFACT_FILES:
            path = self.root / name
            if path.is_file():
                found.append(path)
        return found

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def readable(self) -> list[tuple[str, str]]:
        """Every artefact this sweep can actually read, as (path, text)."""
        pairs: list[tuple[str, str]] = []
        for path in self.artefacts:
            if path.suffix.lower() in instance_identity.BINARY_SUFFIXES:
                continue
            try:
                pairs.append((self.relative(path), path.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                continue
        return pairs


def _link_directory(target: Path, link: Path) -> None:
    """`link` -> `target`, without needing a privilege.

    Windows refuses `os.symlink` to anybody without
    `SeCreateSymbolicLinkPrivilege`, which a developer's shell and a CI
    runner both ordinarily lack; a directory *junction* needs none and
    behaves like a directory for every filesystem call `node` makes.
    `shutil.rmtree` unlinks a junction rather than descending into it
    (Python 3.12's `DirEntry.is_junction`), and this module's own fixture
    removes both links before anything else cleans up, so a scratch tree
    can never take `node_modules` with it.
    """
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
        return
    os.symlink(target, link, target_is_directory=True)


def _run(args: list[str], *, cwd: Path, env: dict[str, str], what: str) -> None:
    result = subprocess.run(
        args, cwd=cwd, env=env, capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        raise AssertionError(
            f"the second instance's build failed at {what}:\n"
            f"{result.stdout[-4000:]}\n{result.stderr[-4000:]}"
        )


def _environment(root: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _BUILD_VARIABLES}
    env["CONVENER_REPO_ROOT"] = str(root)
    return env


def _lay_out(root: Path) -> None:
    """The scratch tree: this repository's product, the example's instance."""
    tracked = subprocess.run(
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


def _publish(root: Path) -> None:
    """Everything the scheduled jobs derive, in the order they derive it.

    The same commands `deploy.yml` and `publish-vitrine.yml` run, and in
    their order: the charter's stylesheets and templates before either
    bundler reads them, the public projection before the showcase's
    fixture is refreshed from it.
    """
    env = _environment(root)
    for name in (
        "validate",
        "public_data",
        "survey_status_public_data",
        "registration_routing_public_data",
        "certificates_public_data",
        "agenda_internal",
    ):
        _run(
            [sys.executable, "-c", _CLI_RUNNER, name],
            cwd=root,
            env=env,
            what=f"convener-{name.replace('_', '-')}",
        )
    _run(
        [sys.executable, str(root / "scripts" / "generate_brand_css.py")],
        cwd=root,
        env=env,
        what="generate_brand_css.py",
    )
    _run(
        [sys.executable, "-c", _CLI_RUNNER, "render_visuals", str(root / POSTERS)],
        cwd=root,
        env=env,
        what="convener-render-visuals",
    )
    # `publish-vitrine.yml`'s own "Refresh site data" step: the showcase
    # builds from a committed fixture, refreshed from the public
    # projection before every real build.
    shutil.copyfile(
        root / "public-data" / "events-public.json",
        root / "site" / "src" / "_data" / "events.json",
    )


def _build(root: Path) -> None:
    """The two bundlers, invoked the way a build invokes them."""
    env = _environment(root)
    for script in (
        "copy-fonts.mjs",
        "copy-handbook.mjs",
        "copy-event-keys.mjs",
        "copy-signing-keys.mjs",
        "copy-certificates.mjs",
        "copy-survey-status.mjs",
    ):
        _run(
            ["node", str(root / "app" / "scripts" / script)],
            cwd=root / "app",
            env=env,
            what=script,
        )
    vite = root / "app" / "node_modules" / "vite" / "bin" / "vite.js"
    for island in ("", "island-signup", "island-verify", "island-survey"):
        mode = ["--mode", island] if island else []
        _run(
            ["node", str(vite), "build", *mode],
            cwd=root / "app",
            env=env,
            what=f"vite build {island or 'production'}",
        )
    eleventy = root / "site" / "node_modules" / "@11ty" / "eleventy" / "cmd.cjs"
    _run(
        ["node", str(eleventy), f"--output={(root / 'site' / '_site').as_posix()}"],
        cwd=root / "site",
        env=env,
        what="eleventy",
    )


@pytest.fixture(scope="module")
def second_instance(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Built]:
    """The whole thing, built once for this module.

    Skips rather than fails when a toolchain is missing, exactly as
    `test_site.py::built_site` already does: `node_modules` is installed
    by a step of the job, not by a test, because installing it is the one
    thing here that would touch the network.
    """
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH -- cannot build a second instance")
    for package in ("app", "site"):
        if not (ROOT / package / "node_modules").is_dir():
            pytest.skip(
                f"{package}/node_modules is missing -- run `npm ci` in "
                f"{package}/ before this suite (quality.yml's own python "
                "job does)"
            )
    root = tmp_path_factory.mktemp("second-instance") / "repository"
    root.mkdir()
    links = [root / package / "node_modules" for package in ("app", "site")]
    try:
        _lay_out(root)
        for link in links:
            _link_directory(ROOT / link.relative_to(root), link)
        _publish(root)
        _build(root)
        yield Built(root=root)
    finally:
        for link in links:
            if link.exists():
                os.rmdir(link)


# ------------------------------------------------------------------ #
# 1 -- the fictional instance answers for everything an instance owns
# ------------------------------------------------------------------ #


def test_the_example_instance_answers_every_path_an_instance_owns() -> None:
    """`config/boundary.yml` enumerates what an instance owns; this is the
    clause that makes the example answer all of it.

    Both directions. A declared path with no counterpart and no stated
    reason is a gap in the example, and a stated reason for a path that
    does have a counterpart is a note nobody removed -- either way, the
    day somebody adds an entry to the boundary, this fails until a
    decision is written down beside it.
    """
    declared = boundary.load(ROOT)
    answered: list[str] = []
    missing: list[str] = []
    for path in declared.instance_paths:
        counterpart = ROOT / EXAMPLE / path
        provided = (
            any(counterpart.rglob("*")) if path.endswith("/") else counterpart.is_file()
        )
        (answered if provided else missing).append(path)

    unstated = [path for path in missing if path not in DELIBERATELY_ABSENT]
    assert unstated == [], (
        f"{EXAMPLE.as_posix()} answers nothing for these paths, which "
        "config/boundary.yml hands to the instance -- give it a "
        "counterpart, or state in DELIBERATELY_ABSENT why it deliberately "
        f"has none: {unstated}"
    )
    stale = [path for path in answered if path in DELIBERATELY_ABSENT]
    assert stale == [], (
        f"DELIBERATELY_ABSENT still explains why {stale} has no "
        "counterpart, and it now has one"
    )
    assert answered, "the example answers nothing at all"


def test_the_two_instances_disagree_about_every_needle(
    second_instance: Built,
) -> None:
    """A needle whose two instances happen to write the same value proves
    nothing at all: it would be absent from a build for the same reason it
    is present. This is what makes the sweep below meaningful, so it runs
    before it rather than being assumed."""
    here = instance_identity.needles(ROOT)
    there = instance_identity.needles(second_instance.root)
    assert set(here) == set(there)
    shared = {name: here[name] for name in here if here[name] == there[name]}
    assert shared == {}, (
        "these needles are the same string in both instances, so sweeping "
        f"for them says nothing about separation: {shared}"
    )


# ------------------------------------------------------------------ #
# 2 -- the sweep
# ------------------------------------------------------------------ #


def _leaks(
    built: Built, wanted: dict[str, str], patterns: dict[str, frozenset[str]]
) -> list[tuple[str, str]]:
    """Every (artefact, needle) the build still carries, once the phrases
    the deferred register accounts for have been taken out of the
    artefacts that register names."""
    offending: list[tuple[str, str]] = []
    for relative, original in built.readable():
        text = original
        for phrase in instance_identity.allowed_for(relative, patterns):
            text = text.replace(phrase, " ")
        for name, needle in wanted.items():
            if instance_identity.contains(text, needle):
                offending.append((relative, name))
    return offending


def test_a_second_instances_build_carries_nothing_of_this_one(
    second_instance: Built,
) -> None:
    """The acceptance criterion of phase 10, § 6.

    Everything a reader receives, swept for every writable form of this
    instance's name, its addresses, its series and its charter. The only
    thing tolerated is a phrase a file in the deferred register actually
    contains, inside an artefact that register says it reaches -- see
    `instance_identity`'s own docstring for why the exemption is a phrase
    and not a file.
    """
    wanted = instance_identity.needles(ROOT)
    patterns = instance_identity.allowance(ROOT, wanted)
    offending = _leaks(second_instance, wanted, patterns)
    assert offending == [], (
        "a build made with another instance's configuration still carries "
        "this instance's identity, which is the one thing phase 10 exists "
        f"to make impossible: {offending}"
    )


def test_every_needle_is_found_in_the_second_instances_own_output(
    second_instance: Built,
) -> None:
    """A sweep that matches nothing passes green for ever.

    Each needle is proved to be the right shape by finding it in the
    build, in the *second* instance's own form -- the same corpus, the
    same matcher, the same needle names. So the test above says "none of
    the first instance's forms are here", not "this scan finds nothing
    anywhere".
    """
    theirs = instance_identity.needles(second_instance.root)
    seen: dict[str, list[str]] = {name: [] for name in theirs}
    for relative, text in second_instance.readable():
        for name, needle in theirs.items():
            if instance_identity.contains(text, needle):
                seen[name].append(relative)
    unmatched = {name: theirs[name] for name, where in seen.items() if not where}
    assert unmatched == {}, (
        "these needles match nothing in a build made from the very "
        "declaration they were read out of, so sweeping another build for "
        f"them would pass for free: {unmatched}"
    )


def test_the_sweep_sees_what_the_deferred_register_accounts_for(
    second_instance: Built,
) -> None:
    """The deferred register, proved rather than trusted.

    Run the same sweep with nothing allowed. It must find something --
    otherwise an entry is being kept for a file that no longer reaches a
    build, and the register has become a list of apologies for nothing --
    and everything it finds must sit in an artefact some entry claims. The
    first half is what fails the day an entry is removed without the file
    being fixed; the second is what fails the day a *new* leak hides
    behind an old entry's name.
    """
    wanted = instance_identity.needles(ROOT)
    offending = _leaks(second_instance, wanted, {})
    assert offending, (
        "nothing in the build carries this instance's identity any more, "
        "not even what the deferred register accounts for -- the entries "
        "with a `carried_into` should lose it, or leave the register"
    )
    unclaimed = sorted(
        {
            relative
            for relative, _ in offending
            if not instance_identity.claimed_by_any(relative)
        }
    )
    assert unclaimed == [], (
        "these built artefacts carry this instance's identity and no "
        f"deferred entry claims them: {unclaimed}"
    )


def test_every_deferred_entry_that_claims_a_build_reaches_it(
    second_instance: Built,
) -> None:
    """An entry claiming to reach a built artefact has to reach one.

    A `carried_into` that matches nothing is a standing exemption for a
    leak that no longer exists -- it costs nothing today and blinds the
    sweep the day somebody reintroduces exactly that phrase.
    """
    wanted = instance_identity.needles(ROOT)
    texts = dict(second_instance.readable())
    for entry in instance_identity.DEFERRED:
        if not entry.carried_into:
            continue
        source = (ROOT / entry.path).read_text(encoding="utf-8")
        runs = instance_identity.literal_runs(
            source, [value for value in wanted.values() if value in source]
        )
        assert runs, f"{entry.path.as_posix()} no longer names this instance"
        patterns = dict.fromkeys(entry.carried_into, runs)
        reached = [
            relative
            for relative, text in texts.items()
            if instance_identity.allowed_for(relative, patterns)
            and any(run in text for run in runs)
        ]
        assert reached, (
            f"{entry.path.as_posix()} claims to reach {entry.carried_into} "
            f"({entry.owner}) and reaches nothing there any more -- drop "
            "the claim, or the entry"
        )


# ------------------------------------------------------------------ #
# 3 -- D-26: served under *its* prefix, not this one's
# ------------------------------------------------------------------ #


def test_the_second_instances_showcase_resolves_under_its_own_prefix(
    second_instance: Built,
) -> None:
    """D-26, asked of a second instance rather than of this one.

    A build served at a bare root passes every local check while the
    deployed shape is broken, which is the whole of that decision. Every
    root-relative link the showcase emits has to resolve under the prefix
    the *second* declaration names -- and, because Eleventy's `url` filter
    is what does the prefixing, a page that forgot the filter is a link
    one path segment above where the site is served.
    """
    prefix = instance_identity.needles(second_instance.root)["path_prefix"]
    pattern = 'href="/'
    offending: list[str] = []
    for relative, text in second_instance.readable():
        if not relative.startswith("site/_site/") or not relative.endswith(".html"):
            continue
        index = text.find(pattern)
        while index != -1:
            link = text[index + len('href="') :]
            if not link.startswith(prefix):
                offending.append(f"{relative}: {link[:60]}")
            index = text.find(pattern, index + 1)
    assert offending == [], (
        f"these links resolve above {prefix}, where this instance is not "
        f"served (D-26): {offending[:10]}"
    )
