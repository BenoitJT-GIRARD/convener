"""Build this repository as a second instance, and refuse anything of the
first in what comes out.

This is what the separation between the instance and the code rests on.
Several earlier passes each drove a second-instance build by hand and
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

When this module does not run, and where that is refused
--------------------------------------------------------
It needs `node` and both `node_modules` and may not install them, so on a
machine that has never run `npm ci` the build cannot happen. That is a
circumstance, not a defect, and it skips -- **except on a runner**, where
a step of `quality.yml`'s own `python` job installs exactly those before
`pytest` starts. There a missing toolchain fails by name
(`_toolchain_absent`), because a skip in the one environment that was set
up for this test is a green suite reporting a coverage it does not have,
and what silently would not have run is the one property this whole module
exists to hold.

Two claims are held below the build line so that they hold everywhere:
`test_the_example_instance_answers_every_path_an_instance_owns` reads the
boundary and the example, and `test_the_two_instances_disagree_about_
every_needle` reads two declarations -- neither needs an artefact, so
neither is lost with the toolchain. What that still leaves is stated
rather than implied: a developer's own run can report `passed` with the
sweep itself skipped, and only those two will have said anything. The
merge gate is the runner, not the laptop.

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
  value `instance/config.json` or the charter in force actually holds
  (`convener_ops.declaration.needles.needles`, which this module still reaches through
  `instance_identity`). Two things this instance owns are held by
  neither, so nothing here can look for them: the **time zone** and the
  **standing start time** (`Europe/Paris` and 12:30, in `visual.py`,
  `governance.py` and forty-odd other places). It is recorded rather than
  glossed over; it cannot become a needle
  until it becomes a declared value.

  **The names of the people who run the series were a second, until this
  paragraph was read against the files.**
  `docs/reference/contacts.md` and `docs/reference/operations.md` each
  named four of them, in paragraphs the cockpit publishes to every
  instance; the reference pages name roles now, and the one page that
  described one organisation's own deferred configuration describes the
  configuration instead. Nothing here could have noticed either way --
  a name is not a declared value -- which is what this list is for, and
  also its limit: an entry stays true only for as long as somebody
  re-reads it.

  `site/src/style.css` was a third: it named the
  designer in seven comments that shipped verbatim inside the showcase's
  own stylesheet, and the charter's author asked on 2026-08-25 not to
  have her charter offered as a product option. The comments now say
  *the designer* and *the measured charter*, which is what they were
  explaining in the first place; `instance/data/brand.json` still names her,
  because a record of whose charter it is belongs with the instance.
  **This module never saw any of it** -- a name is not a declared value
  and no sweep here could have found one, which is exactly what this
  paragraph is for. `convener_ops.derivation_guard` can, by reading the
  instance's own records rather than by knowing what a name is; see its
  docstring for where that stops.

  The series' **strapline** was another
  until it got a key of its own: `visual.py` reads
  `identity.strapline` now, and `needles` carries it, so the poster's own
  hero line is swept like everything else on it.
- **Bytes.** `BINARY_SUFFIXES` skips images and fonts, and nothing left
  in that set is an identity surface any more.
  `app/dist/handbook/assets/zoom-background.png` was the last one: it
  shipped inside the bundle swept here, carrying the first instance's
  name, address and strapline, and a second instance's build did not
  regenerate it. It is `video-call-background.svg` now -- generated from
  `instance/data/brand.json` and `instance/config.json`, regenerated by the
  derivation, and swept here as text like every other file in the bundle.

  `tools/visuals/references/*.png` used to be a second, and are not any more.
  They pin what `visual.py` renders, and that render points at
  `instances/example/`: the palette, the motif, the strapline,
  the wordmark and the address inside the registration QR are the
  example's now, so those three images carry nothing a duplicate would
  have to replace. The blind spot has not moved -- nothing here can read a
  PNG, and nothing here could have told you what those three held -- what
  changed is that there is no longer anything in them to read. Proven
  where it can be, on the pages they are rendered from, by
  `test_cli_render_visual_fixtures.py::
  test_no_value_of_the_instance_running_this_repository_reaches_the_page`.
- **The edition prefix was a fourth.**
  `validate.py` fixed an edition code as `MRG-` and one to four digits --
  an abbreviation of *this* series' name, in the product's own validator,
  so the example instance numbered a reading group's sessions `MRG-1` and
  no needle could catch it: both instances were forced to write it.
  `instance/config.json` declares it now, and `needles` carries the two
  forms it reaches an artefact as -- the code the showcase prints, and
  the event id in every event page's address, in `instance/keys/events/<id>.pub`
  and in a certificate's verification link.
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

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NoReturn

import instance_identity
import pytest
import toolchain

from convener_ops.declaration import boundary, published
from convener_ops.declaration.paths import repo_root

ROOT = repo_root()

#: Where the fictional instance lives. Product-owned: upstream ships it,
#: upstream maintains it, and a duplicate that edits it is editing an
#: example rather than its own configuration.
EXAMPLE = Path("instances") / "example"

#: Where this build puts the posters. Not `tools/visuals/`, which the tracked
#: tree already uses for the reference renders and which
#: `convener-render-visuals` regenerates *whole* -- pointing it there would
#: delete them.
POSTERS = "posters"

#: The instance paths that deliberately have no counterpart under
#: `instances/example/`, each with the reason. Checked in both directions,
#: so a path that gains a counterpart cannot stay listed here and a path
#: that loses one cannot go unnoticed.
DELIBERATELY_ABSENT: Final = {
    "instance/keys/": (
        "A fresh duplicate holds no cryptographic material at all: "
        "generating an event key or a signing key is an operator's act, "
        "never upstream's, and this repository's own instance/keys/ is empty of "
        "keys too. Shipping one in an example would ship a private half "
        "somebody might use."
    ),
    "instance/public-data/": (
        "Empty in a fresh clone by construction -- everything in it is "
        "derived from instance/data/ by the product's own commands, and this "
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


#: What did not happen when the toolchain is absent here, in the words the
#: failure below carries. `tools/tests/toolchain.py` takes it as an
#: argument rather than knowing it: the same rule serves
#: `test_published.py`, whose loss is a different one.
_NEVER_BUILT: Final = "the second instance was never built"


def _toolchain_absent(missing: str, remedy: str) -> NoReturn:
    """A skip on a laptop, a failure on a runner -- `toolchain.absent`
    carries the rule and the argument for it; this is that rule with the
    one thing this module loses when it does not run."""
    toolchain.absent(missing, remedy, unrun=_NEVER_BUILT)


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
        [sys.executable, str(root / "tools" / "scripts" / "generate_brand_css.py")],
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
        root / "instance" / "public-data" / "events-public.json",
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
def second_instance_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The second instance's repository, laid out but not yet built.

    Split out of `second_instance` below because none of it needs a
    toolchain: copying the tracked tree, deleting what the boundary hands
    the instance and laying `instances/example/` into the holes is
    filesystem work and nothing else. What can be proved without a build
    is therefore proved without one, on every machine, whether or not
    `npm ci` has ever been run here -- and the thing that can be is not a
    detail: `test_the_two_instances_disagree_about_every_needle` is what
    makes the sweep mean anything at all.
    """
    root = tmp_path_factory.mktemp("second-instance") / "repository"
    root.mkdir()
    _lay_out(root)
    return root


@pytest.fixture(scope="module")
def second_instance(second_instance_tree: Path) -> Iterator[Built]:
    """The whole thing, built once for this module, in the tree above.

    Skips on a machine that never installed the packages and fails on one
    that was supposed to have -- see `_toolchain_absent` for why those are
    not the same sentence.
    """
    if shutil.which("node") is None:
        _toolchain_absent(
            "node is not on PATH, so no second instance can be built",
            "Install Node 22.",
        )
    for package in ("app", "site"):
        if not (ROOT / package / "node_modules").is_dir():
            _toolchain_absent(
                f"{package}/node_modules is missing",
                f"Run `npm ci` in {package}/ before this suite.",
            )
    root = second_instance_tree
    links = [root / package / "node_modules" for package in ("app", "site")]
    try:
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
# 0 -- the control that says whether the rest of this module ran
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    ("environment", "automated"),
    [
        ({}, False),
        ({"CI": ""}, False),
        ({"CI": "false"}, False),
        ({"CI": "0"}, False),
        ({"CI": "true"}, True),
        ({"CI": "1"}, True),
        ({"GITHUB_ACTIONS": "true"}, True),
        ({"CI": "false", "GITHUB_ACTIONS": "true"}, True),
    ],
)
def test_a_missing_toolchain_skips_on_a_laptop_and_fails_on_a_runner(
    environment: dict[str, str], automated: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clause that makes everything below a control rather than a
    formality, proved rather than trusted -- and the only proof
    `tools/tests/toolchain.py` has, here rather than in a module of its
    own because this is where the rule bites hardest.

    Every test in this module needs a build, a build needs `node_modules`,
    and until this branch existed a machine without them turned this
    whole module into six skips inside a green suite. It is the
    one branch here nothing else exercises -- a runner that has its
    toolchain never reaches it -- so it is exercised directly, with the
    environment a runner sets and with the environments that only look
    like one. `test_published.py`'s four bundle tests take the same rule
    with a loss of their own, so what is held here is held for them too.
    """
    for name in toolchain.AUTOMATED:
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    expected = pytest.fail.Exception if automated else pytest.skip.Exception
    # Both outcomes are caught and the right one is then asserted, rather
    # than `pytest.raises(expected)` alone. A skip is an exception pytest
    # acts on: raised where a failure was expected and not caught here, it
    # would end this test as a *skip* -- so the one control over the loud
    # half of the rule would go quiet in exactly the case that broke it,
    # which is the failure the rule itself exists to refuse.
    with pytest.raises((pytest.fail.Exception, pytest.skip.Exception)) as raised:
        _toolchain_absent("app/node_modules is missing", "Run `npm ci` in app/.")
    assert isinstance(raised.value, expected), (
        f"with {environment or 'nothing'} set this must "
        f"{'fail' if automated else 'skip'}, and it did the other"
    )
    assert "app/node_modules is missing" in str(raised.value)
    assert "Run `npm ci` in app/." in str(raised.value)
    assert (_NEVER_BUILT in str(raised.value)) is automated


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


def _declared_values(data: object, path: str = "") -> Iterator[tuple[str, str]]:
    """Every string a declaration actually declares, with the key that
    holds it. `_comment` keys are prose about the file and not values of
    it; `owner` is the boundary's own answer, the same word in every
    instance's copy; `v` is a number."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key.startswith("_") or key in ("owner", "v"):
                continue
            yield from _declared_values(value, f"{path}.{key}" if path else key)
    elif isinstance(data, str):
        yield path, data


def test_every_value_the_declaration_holds_is_swept() -> None:
    """A key nothing derives a needle from is a value a second instance's
    build can carry with nothing looking for it.

    A near miss is why this exists. `instance_identity.needles` was a
    hand-typed dictionary of eight identity fields; a ninth appeared
    (`strapline`, the poster's own hero line) and the sweep went on
    passing green over a poster hard-typing this instance's motto, because
    nobody thought to add the needle beside the key. That was fixed by
    enumerating `published.IDENTITY_FIELDS` -- but the address half and
    the edition prefix are still written out by hand, for
    reasons those entries state. This is the clause that makes the
    hand-written half safe: it reads the declaration rather than the
    reader, so a *new key* fails here on the first run after it is added.

    What it claims and what it does not. It says every declared string
    participates in some needle -- the needle is the value, or the value
    is part of one (`edition_prefix: MRG` inside the needle `MRG-`), or a
    needle is part of it (a host inside an address). It does not claim the
    needle is the best form of the value; that is
    `test_every_needle_is_found_in_the_second_instances_own_output`'s job,
    and it runs against a real build.
    """
    declaration = json.loads(
        (ROOT / published.INSTANCE_PATH).read_text(encoding="utf-8")
    )
    forms = set(instance_identity.needles(ROOT).values())
    unswept = {
        key: value
        for key, value in _declared_values(declaration)
        if not any(value in form or form in value for form in forms)
    }
    assert unswept == {}, (
        "instance/config.json declares these values and no needle in "
        "`instance_identity.needles` derives from any of them, so a second "
        "instance's build could carry them and the sweep would pass: "
        f"{unswept}"
    )


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_the_two_instances_disagree_about_every_needle(
    second_instance_tree: Path,
) -> None:
    """A needle whose two instances happen to write the same value proves
    nothing at all: it would be absent from a build for the same reason it
    is present. This is what makes the sweep below meaningful, so it runs
    before it rather than being assumed.

    On the laid-out tree, not the built one, and deliberately: a needle is
    read out of a declaration, never out of an artefact, so this needs no
    toolchain -- and the half of this module's claim that can hold on
    every machine should not be lost with the half that cannot.
    """
    here = instance_identity.needles(ROOT)
    there = instance_identity.needles(second_instance_tree)
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


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_a_second_instances_build_carries_nothing_of_this_one(
    second_instance: Built,
) -> None:
    """What the separation between the instance and the code rests on.

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
        "this instance's identity, which is the one thing this separation "
        f"exists to make impossible: {offending}"
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


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_the_sweep_sees_what_the_deferred_register_accounts_for(
    second_instance: Built,
) -> None:
    """The deferred register, proved rather than trusted.

    Run the same sweep with nothing allowed. Everything it finds must sit
    in an artefact some entry claims -- that is what fails the day a *new*
    leak hides behind an old entry's name.

    The other half is conditional on there being a claim to prove.
    While some entry named a built artefact, a sweep that
    found *nothing* meant the entry was being kept for a file that no
    longer reaches a build -- a list of apologies for nothing -- so this
    asserted that it found something. No entry claims one now (the
    demonstration points at the example instance, and the
    poster's wordmark and strapline are derived), and with nothing claimed that
    assertion would be demanding a leak in order to prove an exemption
    that has no subject -- the exact opposite of what it is for, and it
    would contradict `test_a_second_instances_build_carries_nothing_of_
    this_one` outright. It comes back by itself the moment a
    `carried_into` does, which is the state it was written for.
    """
    wanted = instance_identity.needles(ROOT)
    offending = _leaks(second_instance, wanted, {})
    if any(entry.carried_into for entry in instance_identity.DEFERRED):
        assert offending, (
            "nothing in the build carries this instance's identity any "
            "more, not even what the deferred register accounts for -- the "
            "entries with a `carried_into` should lose it, or leave the "
            "register"
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

    No entry claims one any more, so this asserts nothing
    today. It is kept rather than deleted for the same reason the
    machinery it exercises is: the next entry that needs a `carried_into`
    should meet this on its way in, not after somebody notices the
    exemption stopped matching.
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


# ------------------------------------------------------------------ #
# 4 -- a declared value that is only a placeholder
# ------------------------------------------------------------------ #


def test_the_second_instances_showcase_offers_its_own_proposal_form(
    second_instance: Built,
) -> None:
    """The configured half of `published.Identity.proposal_form_url`, on a
    build rather than on a reading.

    This repository declares `proposal_form:
    https://forms.example.test/propose` -- a placeholder -- so its own `/propose/`
    renders the state that offers the contact address instead
    (`test_site.py::test_the_propose_page_offers_a_form_or_says_it_is_not_
    open`). The example declares a real form, so the same template on the
    same page must link *its* address here. Without this, a degradation
    that never stopped degrading would look exactly like a feature that
    works.
    """
    form = instance_identity.needles(second_instance.root)["proposal_form"]
    page = second_instance.root / "site" / "_site" / "propose" / "index.html"
    assert page.is_file(), "the second instance built no propose page"
    text = page.read_text(encoding="utf-8")
    assert f'href="{form}"' in text, (
        f"the second instance's propose page does not link its own form ({form})"
    )
    assert "The proposal form is not published yet." not in text


# ------------------------------------------------------------------ #
# 5 -- a duplicate that has not been configured says so, out loud
# ------------------------------------------------------------------ #


def test_this_tree_is_what_an_unconfigured_duplicate_looks_like(
    second_instance_tree: Path,
) -> None:
    """The premise the two tests below rest on, checked rather than
    assumed -- and checked on the laid-out tree, which needs no toolchain,
    so it is proved on every machine whether or not anything can be built
    here.

    `_lay_out` copies `instances/example/`'s files into the holes the
    boundary leaves, so the declaration this build is made from *is* the
    example's, value for value -- which is precisely the state a duplicate
    is in on the day it is made and before anybody has edited anything.
    The demonstration is therefore not a special build with a warning
    switched on for effect: it is the unconfigured state, and the warning
    is the one any duplicate would get.
    """
    example = json.loads(
        (ROOT / published.EXAMPLE_INSTANCE_PATH).read_text(encoding="utf-8")
    )
    assert published.unconfigured(second_instance_tree) == tuple(
        sorted(published.declared_values(example))
    ), (
        "the tree this module builds no longer declares the example's own "
        "values, so it is not the unconfigured state any more"
    )


def test_the_second_instances_showcase_says_it_has_not_been_configured(
    second_instance: Built,
) -> None:
    """The banner on a build rather than in a template, so that a
    duplicate that has not been configured says so, loudly, rather than
    publishing silently under the template's identity.

    Every page, not one: `_includes/layout.njk` is the one piece of chrome
    the whole showcase shares, and a warning on the home page alone is a
    warning anybody arriving by a direct link never sees. And the keys are
    named on the page, so what a reader is told is which line to go and
    edit rather than that something, somewhere, is wrong.
    """
    pages = [
        (relative, text)
        for relative, text in second_instance.readable()
        if relative.startswith("site/_site/") and relative.endswith(".html")
    ]
    assert len(pages) > 5, f"the second instance built almost no pages: {pages}"
    silent = [
        relative for relative, text in pages if "unconfigured__eyebrow" not in text
    ]
    assert silent == [], (
        "these pages of an unconfigured duplicate publish the example's "
        f"identity without saying so: {silent[:10]}"
    )
    named = published.unconfigured(second_instance.root)
    for relative, text in pages:
        for key in named:
            assert key in text, f"{relative} does not name {key}"


def test_the_second_instances_cockpit_says_it_too(second_instance: Built) -> None:
    """The other half of what a visitor can reach without installing
    anything, and the half that is behind a sign-in for everybody except a
    visitor: `auth/Login.tsx` is the screen somebody with no GitHub account
    lands on, and it carries the same band as the cockpit itself.

    Read out of the built bundle rather than out of the source, because
    what is being asked is whether the *define* survived into it: the
    ordinary value of that define is the empty list, so a bundle that lost
    it would render nothing and look exactly like a configured instance.
    """
    bundles = [
        (relative, text)
        for relative, text in second_instance.readable()
        if relative.startswith("app/dist/") and relative.endswith(".js")
    ]
    assert bundles, "the second instance built no application bundle"
    carrying = [relative for relative, text in bundles if "Not configured" in text]
    assert carrying, (
        "no bundle of an unconfigured duplicate's cockpit carries the "
        "warning -- vite.config.ts's own VITE_INSTANCE_UNCONFIGURED define, "
        "or the component that reads it, has stopped reaching the build"
    )
