"""One declaration, read from every side, and nowhere written twice.

This project's published address used to be written out
thirty times across twelve files -- four `base:` in `app/vite.config.ts`,
two constants in `site/.eleventy.js`, three in `tools/convener_ops/`, a
calendar UID domain, two relay configurations, two templates' links, two
shared fixtures -- with tests binding the copies to each other. Those
tests were honest about what they could say, and it was never "there is
one": only "these still agree today".

`instance/config.json` is the one. This module holds four things, and the
order matters because the last two are the only ones a reader should
trust without checking:

1. **The declaration reads, or nothing runs.** `published.from_data`
   refuses every shape that would publish a plausible wrong address, and
   is exercised on each of them. A file that cannot be read stops the
   process rather than substituting a guess.

2. **Every address Python builds starts at the declared root.** Cheap,
   and it is the clause that would catch a constant quietly re-typed.

3. **The showcase's own build resolves the declared prefix** -- proven by
   `require`-ing the real `.eleventy.js` and *calling* it, never by
   reading its source.

4. **All four bundles the application builds resolve the declared base**
   -- proven by loading the real `vite.config.ts` through Vite's own
   `loadConfigFromFile`, which is what a build does, and reading the
   `base` and the `define` each configuration actually produces. That is
   the one thing here needing a toolchain, so the four tests that ask for
   it skip on a machine with no `app/node_modules` and fail on a runner,
   where `quality.yml` installs it before `pytest` runs
   (`_bundle_configurations`, `tools/tests/helpers/toolchain.py`).

Then the sweep: no file outside the declaration writes the address again.

What this module does **not** cover, stated rather than left to be found:

- **The published output itself.** Nothing here builds anything and
  reads what came out. `test_second_instance.py` does: it
  builds this whole repository as a *different* instance and sweeps the
  showcase, all four bundles, the handbook copied into them, the
  generated templates, the published feeds and the posters. That is the
  property the whole separation rests on, and it is a different
  claim from this module's -- a source can be clean while what a reader
  receives is not. `test_site.py` covers today's instance at the
  built-page level besides
  (`test_no_built_page_emits_a_root_relative_link_without_the_prefix`,
  `test_the_governance_record_link_resolves_to_the_published_handbook`).
- Nothing is held out of the sweep any more. The one directory that was
  -- this project's own record of its own decisions, quoting the address
  as it stood when each entry was written -- is not in the repository, so
  the whole of `docs/` is swept.

The second half of the same declaration -- who runs this
series -- closed a gap this module used to name:

5. **The identity reads, or nothing runs**, on the same refuse-rather-than-
   repair terms as the address.
6. **Both builds resolve the declared identity**, again by running the real
   configurations: what `.eleventy.js` hands every template as `site.*`,
   and what `vite.config.ts` defines into all four bundles.
7. **The push target is derived from the published address**, so changing
   one address moves the public URLs *and* the repository they are pushed
   into. It used to move only the first, which is worse than either being
   wrong alone.
8. **The identity sweep**: no file writes the organisation's name, its
   contact address or its forum a second time, with every exemption
   either checked against the declaration (the generated templates,
   `CODEOWNERS`) or named with the phase that owns it. Beside it, the
   same pair of clauses the address already has for the relays: no
   Worker source names a repository, and each deploy workflow that needs
   one derives it.

What clause 8 does **not** sweep, stated rather than left to be found:
the series' *title* and the organisation's *short name*. Both are in the
two downloadable SVG templates, which *derive* them and
are committed here as this instance rendered them, and both are in the
demo instance. Sweeping either here would fail on a generated
artefact rather than on a source edit, so each is left to the check that
regenerates it.

**The second-instance sweep covers both, and can, because it compares two
instances rather than looking for one.** `test_second_instance.py` builds
this repository
with `examples/the-example-collective/` in place of everything
`declarations/boundary.yml` hands to the instance, so the series' title and
the short name in that build are the *example's*; finding this instance's is
then unambiguous in a way it can never be in a source tree the product's own
names live in.
"""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

import pytest
import yaml
from helpers import instance_identity, toolchain

from convener_ops.declaration import boundary, published
from convener_ops.declaration.paths import PUBLIC_DATA_DIR, repo_root
from convener_ops.journey import certificate, registration, survey_invite
from convener_ops.publication import agenda

ROOT = repo_root()

_MINIMAL: dict[str, Any] = {
    "owner": boundary.INSTANCE,
    "v": published.DECLARATION_VERSION,
    published.PUBLISHED_URL_KEY: "https://example.test/somewhere/",
}

#: A second instance's identity, manifestly synthetic: no real name, no
#: real address. Read from `examples/the-example-collective/`, the fictional instance
#: the second-instance build uses, rather than typed
#: here: a second synthetic identity would be a second answer to "what
#: does another instance look like", free to drift from the one an actual
#: build is made with. Every field `IDENTITY_FIELDS` names has to be
#: there, so a field added to the declaration and not to the example
#: fails loudly rather than being skipped.
_OTHER_IDENTITY: dict[str, Any] = json.loads(
    (
        ROOT / "examples" / "the-example-collective" / "instance" / "config.json"
    ).read_text(encoding="utf-8")
)[published.IDENTITY_KEY]

_MINIMAL_IDENTITY: dict[str, Any] = {
    "v": published.DECLARATION_VERSION,
    published.IDENTITY_KEY: _OTHER_IDENTITY,
}


# ------------------------------------------------------------------ #
# 1 -- the declaration reads, or nothing runs
# ------------------------------------------------------------------ #


def test_this_repository_declares_one_published_address() -> None:
    address = published.load()
    assert address.url.startswith("https://")
    assert address.url.endswith("/")
    assert address.origin + address.path_prefix == address.url
    assert address.app_base == f"{address.path_prefix}app/"
    assert address.host in address.origin


def test_the_example_sits_in_a_directory_named_after_what_it_declares() -> None:
    """The directory and the identity agree, or the example is filed under
    a word that says nothing about which instance it is.

    It was `instances/example/` -- one letter from `instance/`, saying the
    word twice on the way to `instances/example/instance/data/`, and giving
    a second worked example nothing to be called but `example-2/`. Both
    halves are read: the name off the tree, the organisation out of the
    file that sits in it.
    """
    root = ROOT / published.EXAMPLE_INSTANCE_ROOT
    declared = published.load_identity(root).organisation
    expected = published.example_directory_name(declared)
    assert root.name == expected, (
        f"the example declares {declared!r} and sits in {root.name!r}. An "
        f"example directory is named after the organisation its own "
        f"declaration carries, so that the tree says which instance it is"
    )
    assert root.parent.name == "examples", (
        f"{root.parent.name!r} holds the worked examples; `examples/` is "
        "what the directory map names and what every reader is sent to"
    )


def test_an_example_directory_name_is_the_organisation_and_nothing_else() -> None:
    """The reader itself, on the shapes an organisation's name can take.

    Held here rather than trusted, because the check above compares its
    output with a directory and would agree with a reader that returned the
    directory's own name for anything.
    """
    assert published.example_directory_name("The Example Collective") == (
        "the-example-collective"
    )
    assert published.example_directory_name("  A.B  C ") == "a-b-c"
    assert published.example_directory_name("Foo & Bar 2") == "foo-bar-2"
    assert published.example_directory_name("---") == ""


def test_the_declaration_is_the_instances_own_file() -> None:
    """The boundary, applied to this file: a
    duplicate edits this and merges everything else. If it were ever
    reclassified as the product's, upstream would be shipping one
    organisation's address to everybody who forked."""
    assert boundary.load().owner_of(published.INSTANCE_PATH) == boundary.INSTANCE


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("not a mapping", "not a supported format version"),
        ({"v": 99, "published_url": "https://a.test/b/"}, "not a supported format"),
        ({**_MINIMAL, "published_url": None}, "must be the address"),
        ({**_MINIMAL, "published_url": ""}, "must be the address"),
        (
            {**_MINIMAL, "published_url": " https://a.test/b/ "},
            "surrounding whitespace",
        ),
        ({**_MINIMAL, "published_url": "http://a.test/b/"}, "must be an https"),
        ({**_MINIMAL, "published_url": "https:///b/"}, "names no host"),
        ({**_MINIMAL, "published_url": "https://a.test/b/?x=1"}, "query or a fragment"),
        ({**_MINIMAL, "published_url": "https://a.test/b/#x"}, "query or a fragment"),
        ({**_MINIMAL, "published_url": "https://a.test/b"}, "must end in '/'"),
        ({**_MINIMAL, "published_url": "https://a.test"}, "must end in '/'"),
    ],
)
def test_a_declaration_that_cannot_be_read_stops_rather_than_guesses(
    data: Any, expected: str
) -> None:
    """Every clause is a shape that reads plausible and publishes wrong.
    A missing trailing slash eats a path segment the moment anything is
    appended to it; a bare origin publishes at a domain root this project
    does not own; `http` puts a certificate verification link -- meant to
    stand for years -- on a transport that can be rewritten in flight."""
    with pytest.raises(ValueError, match=expected):
        published.from_data(data)


def test_a_root_relative_path_is_refused_rather_than_normalised() -> None:
    """D-26 in one function. `/x` against a prefixed deployment resolves
    to the *domain* root, one segment above where this project lives --
    the whole of the defect that decision exists for. Accepting it here
    would put that defect back behind a helper that reads correct."""
    address = published.from_data(_MINIMAL)
    assert address.under("verify/") == "https://example.test/somewhere/verify/"
    with pytest.raises(ValueError, match="root-relative"):
        address.under("/verify/")


# ------------------------------------------------------------------ #
# 2 -- every address Python builds starts at the declared root
# ------------------------------------------------------------------ #


def test_every_address_this_package_publishes_comes_from_the_declaration() -> None:
    address = published.load()
    assert address.under("events/") == registration.SIGNUP_BASE
    assert address.under("survey/") == survey_invite.SURVEY_BASE
    assert f"{address.under('verify/')}#/" == certificate.VERIFICATION_BASE
    assert address.host == agenda._UID_DOMAIN


def test_the_verification_address_keeps_the_fragment_that_protects_a_name() -> None:
    """Deriving the root must not have quietly changed the shape. The
    `#/` is not a routing detail: `verification_url` puts the token --
    which carries the holder's name -- after it, and a browser never
    sends a fragment in a request nor keeps it in `Referer`. See
    `certificate.py`'s own module docstring. Anything that changes this
    address is a maintainer's call, because it is printed on documents
    already delivered."""
    assert certificate.VERIFICATION_BASE.endswith("verify/#/")
    minted = certificate.verification_url("abc", '{"v":1}')
    assert "#" in minted
    assert "token=" in minted.split("#", 1)[1]


# ------------------------------------------------------------------ #
# 3 and 4 -- what the two builds actually resolve
#
# Run, never read. `site/` carries no JS test runner of its own and the
# application's configuration is TypeScript, so both answers are obtained
# by executing the real, committed configuration through Node and printed
# back as JSON -- the same arrangement `test_paris_standing_start_
# fixture.py` already uses, and for the same reason: a source text
# agreeing with a value proves nothing about what a build does with it.
# ------------------------------------------------------------------ #


def _node_json(script: Path, cwd: Path, timeout: int = 120) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["node", str(script)],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        toolchain.absent(
            "node is not on PATH, so no build's own configuration can be run",
            "Install Node 22.",
            unrun=f"{script.name} never ran",
        )
    assert result.returncode == 0, result.stdout + result.stderr
    loaded = json.loads(result.stdout)
    assert isinstance(loaded, dict)
    return loaded


#: What `app/scripts/print-published.mjs` imports, and the one thing in
#: this module that a fresh tree does not have. `site/`'s own reader
#: `require`s nothing outside the standard library, which is why only the
#: four tests below take this route.
_VITE = ROOT / "app" / "node_modules" / "vite"


def _bundle_configurations() -> dict[str, Any]:
    """What the four configurations `npm run build` invokes actually
    resolve, loaded the way a build loads them.

    Behind a toolchain check, on the same terms
    `test_second_instance.py`'s build is: `print-published.mjs` loads the
    real `vite.config.ts` through Vite's own `loadConfigFromFile`, so
    without `app/node_modules` there is no answer to compare and the four
    tests below reported an absent install as four failures. That is D-25
    read backwards -- loud where nothing is broken -- and it is the first
    thing a freshly-built tree with no `npm ci` in it used to walk into.
    On a runner the same absence still fails, by name,
    because `quality.yml` installs `app/`'s packages before `pytest` runs.
    """
    if not _VITE.is_dir():
        toolchain.absent(
            "app/node_modules is missing, so vite.config.ts cannot be loaded",
            "Run `npm ci` in app/ before this suite.",
            unrun="the four bundle configurations were never read",
        )
    return _node_json(ROOT / "app" / "scripts" / "print-published.mjs", ROOT / "app")


def test_the_showcase_build_resolves_the_declared_prefix() -> None:
    """The real, committed `.eleventy.js` is `require`d and *called* with
    a stub, and what it hands Eleventy as `pathPrefix` is what is
    compared here. Every internal link the showcase emits resolves
    against that value, so it is the one that decides whether a page
    404s once published."""
    answer = _node_json(
        ROOT / "site" / "scripts" / "print-published.cjs", ROOT / "site"
    )
    address = published.load()
    assert answer["reader"]["url"] == address.url
    assert answer["reader"]["origin"] == address.origin
    assert answer["reader"]["pathPrefix"] == address.path_prefix
    assert answer["eleventyPathPrefix"] == address.path_prefix


def test_every_bundle_the_application_builds_resolves_the_declared_base() -> None:
    """All four configurations `npm run build` invokes, loaded the way a
    build loads them. `base` decides where every asset URL resolves, and
    the `define` is the only way the published address reaches
    `src/content/render.ts`, which composes a public registration link
    inside a browser that can read no file.

    A missing island here is the failure this replaces a text scrape to
    catch: an island published under a different base 404s its own
    fetches -- event keys, the certificate register, the signing keys --
    while every other check stays green."""
    answer = _bundle_configurations()
    address = published.load()
    assert answer["reader"]["appBase"] == address.app_base
    assert set(answer["bases"]) == {
        "production",
        "island-signup",
        "island-verify",
        "island-survey",
    }
    assert set(answer["bases"].values()) == {address.app_base}
    assert set(answer["defines"].values()) == {json.dumps(address.url)}


# ------------------------------------------------------------------ #
# The sweep -- nowhere written twice
# ------------------------------------------------------------------ #

#: Every Worker configuration in this repository. Two of them used to be
#: the one place the address was allowed to appear a second time: a
#: Cloudflare Worker deploys from its own `wrangler.toml` and can read
#: nothing else, so `ALLOWED_ORIGIN` was written out there and each
#: relay's own suite refused it disagreeing with the declaration. The copy
#: is gone rather than merely checked -- the deploy workflows derive the
#: origin and pass it to `wrangler deploy --var` -- so these files are
#: swept like every other, and what is asserted about them below is that
#: they name no origin at all.
_RELAY_CONFIGURATIONS = (
    Path("services/auth-proxy/wrangler.toml"),
    Path("services/form-relay/wrangler.toml"),
    Path("services/signup-relay/wrangler.toml"),
)

#: The two workflows that deploy a relay answering CORS preflights, and
#: therefore the two that have to hand it an origin. `deploy-form-relay.yml`
#: is not here: that worker answers no preflight and takes no origin.
_RELAY_DEPLOY_WORKFLOWS = (
    Path(".github/workflows/deploy-auth-proxy.yml"),
    Path(".github/workflows/deploy-signup-relay.yml"),
)

#: Nothing is exempt from this sweep. The entry that used to be here
#: named this project's own record of its own decisions -- quoting
#: addresses and names as they stood when each was written, built by
#: nothing and shipped by nothing. That subtree is not in the repository,
#: so the exemption named nothing and hid the fact that every tracked
#: file is now swept. `docs/` was exempt in full before that, until the
#: handbook moved onto the substitution vocabulary.
_UNSWEPT: tuple[str, ...] = ()

#: The instance's projections, exempt from the address sweep alone.
#:
#: `declarations/boundary.yml` calls this directory "everything the
#: instance publishes about itself, derived from instance/data/ by the
#: product's own commands". An address appearing there is this declaration
#: being *read*, which is what it exists for, not copied: the next run of
#: the command that writes the file rewrites it from the declaration
#: again, so it cannot drift the way a source file can.
#:
#: Concretely, `agenda-internal.ics` puts the host in every `UID` -- the
#: iCalendar convention for a globally unique identifier -- and in
#: `LOCATION` and `URL` for a scheduled event. Upstream's own committed
#: copy does it with the example instance's host, and this test never sees
#: that because the skipif below excuses the one repository where the
#: example *is* the instance. Every configured duplicate saw it instead,
#: the first time its publisher refreshed the feed.
#:
#: Read from the declaration rather than written out here, and handed to
#: the sweep rather than folded into `_UNSWEPT`, which two sweeps share.
#: The identity sweep already skips whatever the boundary hands the
#: instance, so it needs nothing -- and sharing this would have taken
#: `public-data/README.md`, which is the product's, out of it.
#:
#: What stops this from outliving the directory it names: `paths.handed`
#: raises when the declaration hands over no path ending in
#: `public-data`, so an exemption for a tree the boundary has retired
#: fails at import rather than quietly covering nothing.
_PROJECTIONS: Final = (f"{PUBLIC_DATA_DIR.as_posix()}/",)

_BINARY_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".ico", ".pdf", ".woff2", ".woff", ".ttf"}
)


def _tracked_files() -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert len(listing) > 100, f"the file listing found almost nothing: {listing}"
    return listing


def _files_writing_the_address(
    allowed: set[str], unswept: tuple[str, ...] = ()
) -> list[tuple[str, str]]:
    """Every tracked file writing any form of the published address,
    except the ones `allowed` names and the trees `unswept` prefixes.
    Taking the exemptions as arguments is what lets the test below the
    sweep prove the sweep works: it runs the identical loop with nothing
    exempt and requires the declaration itself to come back."""
    address = published.load()
    needles = (
        address.url,
        address.origin,
        address.host,
        address.path_prefix,
    )
    offending: list[tuple[str, str]] = []
    for name in _tracked_files():
        if name.startswith(_UNSWEPT + unswept) or name in allowed:
            continue
        path = ROOT / name
        if path.suffix.lower() in _BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for needle in needles:
            if needle in text:
                offending.append((name, needle))
                break
    return offending


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_no_source_file_writes_the_published_address_a_second_time() -> None:
    """The clause that makes "one declaration" a fact rather than a
    claim.

    Every writable form of the address is swept for -- the whole URL, the
    origin, the bare host and the path prefix -- because a copy does not
    have to be a copy of the whole thing to drift. Not the bare
    repository *name*: that is a different identity fact (which repository
    a build pushes to, what the architecture diagram calls it), owned
    elsewhere, and folding it in here would make this test fail for a
    reason it cannot fix.

    **The declaration is the only file exempt, and there is no second
    entry any more.** The two relay configurations were one until the
    origin they deploy stopped being written in them
    (`services/auth-proxy/wrangler.toml`); so a `[vars]` entry putting it
    back fails here, on the Python suite, with no Worker suite run.

    The instance's own projections are not a second entry: `_PROJECTIONS`
    is a tree this sweep does not read, for the reason stated there, and
    a file that is *written* from the declaration cannot be a second copy
    of it.
    """
    offending = _files_writing_the_address(
        {published.INSTANCE_PATH.as_posix()}, _PROJECTIONS
    )
    assert offending == [], (
        "these files write this project's published address a second time, "
        f"which instance/config.json exists to make impossible: {offending}"
    )


def test_the_sweep_would_see_a_second_copy_if_there_were_one() -> None:
    """A sweep that matched nothing would pass for free.

    There is no legitimate second copy left to find it in, so the proof is
    the loop itself: run with nothing exempt at all, it must report the
    one file that does write the address -- the declaration. A sweep that
    had stopped reading files, or stopped matching, comes back empty here
    and fails.
    """
    offending = _files_writing_the_address(set())
    assert (published.INSTANCE_PATH.as_posix(), published.load().url) in offending, (
        "the sweep does not find the address in the file that declares it, "
        f"so it would not find a copy either: {offending}"
    )


def test_no_relay_configuration_names_an_origin_at_all() -> None:
    """The binding that replaced the copy, and the one that has to bite.

    Each of the two relays that answer CORS preflights takes one origin as
    `env.ALLOWED_ORIGIN`, and that origin is the address this project is
    published at. It used to be written into the file the Worker deploys
    from, because a Worker can read nothing else -- checked against the
    declaration, and still a second home for it: the published product
    shipped the example instance's origin inside a product file, and a
    duplicate had that file to edit before its first deploy. It is passed
    to `wrangler deploy --var` now, so no configuration here names an
    origin.

    Parsed with `tomllib` rather than matched, so a value put back under a
    different table is a failure and not a false pass. All three worker
    configurations are read, not only the two: a var that is wrong to hold
    here is wrong to hold in any of them.
    """
    for path in _RELAY_CONFIGURATIONS:
        config = tomllib.loads((ROOT / path).read_text(encoding="utf-8"))
        assert "ALLOWED_ORIGIN" not in config.get("vars", {}), (
            f"{path.as_posix()} declares ALLOWED_ORIGIN again "
            f"({config['vars']['ALLOWED_ORIGIN']!r}). That value is "
            "instance/config.json's published_url and has one home; the "
            "deploy workflow derives it and passes it to `wrangler deploy "
            "--var`, so nothing has to be written here"
        )


def _deploy_scripts(names: tuple[Path, ...]) -> dict[Path, str]:
    """The `run:` block of the Deploy step of each named workflow."""
    found: dict[Path, str] = {}
    for name in names:
        workflow = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                if step.get("name") == "Deploy":
                    found[name] = step["run"]
        if name not in found:
            raise AssertionError(f"{name.as_posix()} has no Deploy step to read")
    return found


def test_both_relay_deploys_hand_the_worker_the_declared_origin() -> None:
    """The other half: a configuration naming no origin deploys a worker
    that refuses everything unless the deploy supplies one.

    Asserted on the `run:` block each workflow actually executes -- it
    must reach the derivation, it must pass what it read to `--var`, and
    it must not spell the answer out. The same three clauses
    `test_both_publishing_workflows_read_the_push_target_rather_than_
    naming_it` already holds for the repository a built site is pushed
    into.
    """
    origin = published.load().origin
    for name, script in _deploy_scripts(_RELAY_DEPLOY_WORKFLOWS).items():
        # `print(load().origin)` rather than the import line alone: the
        # signup relay's own deploy step imports `load_identity` beside
        # it for the repository, and an import needle would have matched
        # that and passed with the origin's derivation gone.
        assert "print(load().origin)" in script, (
            f"{name.as_posix()}'s deploy step does not read the declared "
            "origin -- naming it in the worker's own configuration is how "
            "the published address and the origin it answers for start "
            "disagreeing"
        )
        assert "ALLOWED_ORIGIN:$origin" in script, (
            f"{name.as_posix()} never hands what it read to wrangler"
        )
        assert origin not in script, (
            f"{name.as_posix()} writes the origin out as well as deriving it"
        )


def test_no_build_configuration_reads_the_address_out_of_another_readers_source() -> (
    None
):
    """The shape this replaced, refused so it cannot come back.

    Two checkers and one workflow used to recover the prefix by running a
    regular expression over `site/.eleventy.js`, because that file was
    where the value lived. Scraping the source of *a reader* is one
    indirection further from the answer than reading the declaration, and
    it fails silently the day that reader stops spelling the value out --
    which is exactly what happened here.
    """
    scrapers = {
        Path("site/scripts/check-a11y.mjs"),
        Path("site/scripts/check-performance-budget.mjs"),
        Path(".github/workflows/preview.yml"),
    }
    for path in sorted(scrapers):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "PATH_PREFIX" not in text, (
            f"{path.as_posix()} names site/.eleventy.js's own former "
            "PATH_PREFIX again -- read instance/config.json through the "
            "reader for that side of the boundary instead of scraping "
            "another reader's source"
        )


# ------------------------------------------------------------------ #
# 5 -- who runs this series, read from the same declaration
# ------------------------------------------------------------------ #


def test_this_repository_declares_who_runs_the_series() -> None:
    identity = published.load_identity()
    for field in published.IDENTITY_FIELDS:
        assert getattr(identity, field), f"identity.{field} is empty"
    assert identity.namespace["forum_host"] == urlsplit(identity.forum).netloc


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ({published.IDENTITY_KEY: None}, "must be an object"),
        ({published.IDENTITY_KEY: "a bare string"}, "must be an object"),
        ({"v": 99}, "not a supported format version"),
    ],
)
def test_an_identity_that_cannot_be_read_stops_rather_than_guesses(
    mutation: dict[str, Any], expected: str
) -> None:
    """Every field here is printed to somebody outside this project -- the
    name at the top of a public page, the sign-off of an e-mail to a
    speaker, the address a participant writes to about their own data.
    There is nothing safe to substitute for one, so a declaration that
    cannot be read stops the process."""
    with pytest.raises(ValueError, match=expected):
        published.identity_from_data({**_MINIMAL_IDENTITY, **mutation})


@pytest.mark.parametrize("field", published.IDENTITY_FIELDS)
def test_every_identity_field_is_required_by_name(field: str) -> None:
    """Not "the object is there" but "this field is there", one at a time
    and named in the message. A duplicate deleting a key it thinks it does
    not need must be told which one at the first command it runs, not by a
    participant receiving an e-mail signed by nobody."""
    without = {k: v for k, v in _OTHER_IDENTITY.items() if k != field}
    with pytest.raises(ValueError, match=f"identity.{field}"):
        published.identity_from_data(
            {**_MINIMAL_IDENTITY, published.IDENTITY_KEY: without}
        )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("organisation", "", "must be a non-empty string"),
        ("organisation", "  padded  ", "surrounding whitespace"),
        ("contact", 42, "must be a non-empty string"),
        ("forum", "forum.example.test", "must be the forum's own address"),
        ("forum", "https://", "must be the forum's own address"),
        ("repository", "example-cockpit", "must be `owner/name`"),
        ("repository", "a/b/c", "must be `owner/name`"),
    ],
)
def test_an_identity_field_that_reads_plausibly_and_is_wrong_is_refused(
    field: str, value: Any, expected: str
) -> None:
    """Each of these is a shape somebody would actually type. A forum
    written as a bare name links to nothing and prints as neither a host
    nor an address; a repository without its owner names a repository
    inside whatever organisation the API call happens to default to."""
    broken = {**_OTHER_IDENTITY, field: value}
    with pytest.raises(ValueError, match=expected):
        published.identity_from_data(
            {**_MINIMAL_IDENTITY, published.IDENTITY_KEY: broken}
        )


@pytest.mark.parametrize(
    "field",
    [f for f in published.IDENTITY_FIELDS if f not in published.DEGRADABLE_FIELDS],
)
def test_a_field_still_carrying_a_placeholder_is_refused_by_name(field: str) -> None:
    """`REPLACE` is how this repository writes a value nobody has filled
    in -- `services/*/wrangler.toml` ships `REPLACE_WITH_KV_NAMESPACE_ID`
    and both relay deploys already grep for it. It reads as a string and
    passes every check a string passes, so until this clause a placeholder
    in `organisation` would have been printed at the top of a public page
    exactly as a real name is."""
    broken = {**_OTHER_IDENTITY, field: f"{_OTHER_IDENTITY[field]}-REPLACE"}
    with pytest.raises(ValueError, match=f"identity.{field} is still a placeholder"):
        published.identity_from_data(
            {**_MINIMAL_IDENTITY, published.IDENTITY_KEY: broken}
        )


@pytest.mark.parametrize("field", published.DEGRADABLE_FIELDS)
def test_the_fields_with_a_fallback_degrade_instead_of_stopping(field: str) -> None:
    """The other half of the same rule, and the reason it is a list rather
    than a blanket refusal.

    `proposal_form` is the one declared value the showcase can publish
    *without*: `/propose/` has the contact address to send a visitor to
    instead. So a placeholder there is read, kept as the declared value --
    it is still a needle of the second-instance sweep -- and derived away
    at the one point a reader would have been shown it. Refusing it
    outright would stop every command a duplicate runs over a link, which
    is not proportionate; publishing it is what this instance did for a
    long time."""
    assert field == "proposal_form", "a new degradable field needs its own fallback"
    declared = f"https://forms.example.test/{published.PLACEHOLDER_MARKER}"
    identity = published.identity_from_data(
        {
            **_MINIMAL_IDENTITY,
            published.IDENTITY_KEY: {**_OTHER_IDENTITY, field: declared},
        }
    )
    assert identity.proposal_form == declared
    assert identity.proposal_form_url == ""
    assert identity.namespace[field] == declared


def test_a_declared_form_this_instance_could_publish_survives_the_derivation() -> None:
    """The branch above only says what is taken away. This says the
    derivation takes nothing away from an address that is real, which is
    the state the example instance is in and the state a configured
    duplicate is in."""
    identity = published.identity_from_data(_MINIMAL_IDENTITY)
    assert published.PLACEHOLDER_MARKER not in identity.proposal_form
    assert identity.proposal_form_url == identity.proposal_form


def test_the_substitution_vocabulary_is_the_declaration_plus_one_derived_name() -> None:
    """`{{ instance.* }}`, as both rendering engines resolve it. Asserted
    as the whole set rather than as membership: a name in one engine and
    not the other is exactly the drift D-14 exists to refuse, and the
    cheapest way to see it is to pin what the map contains."""
    identity = published.identity_from_data(_MINIMAL_IDENTITY)
    assert set(identity.namespace) == set(published.IDENTITY_FIELDS) | {"forum_host"}
    assert identity.namespace["forum_host"] == "forum.example.test"


# ------------------------------------------------------------------ #
# 6 -- what the two builds actually resolve, identity included
# ------------------------------------------------------------------ #


def test_the_showcase_feeds_its_templates_the_declared_identity() -> None:
    """The real, committed `.eleventy.js`, called with a stub that records
    what it registers as global data. `site.*` is what every template
    reads, so this is the value a visitor sees in the masthead, in the
    footer, in `og:site_name` and in every `mailto:` on the site.

    The composition is pinned here and nowhere else: `title` is
    `short_name` and `series` with a space between them. `test_site.py`
    used to carry a `_site_config` helper that built the same map, cited
    from this very docstring as the check against the built pages -- it
    was called by nothing, so the citation described a control that could
    not fail and the map it built was never compared with anything. This
    function is the one place the composition is held.
    """
    answer = _node_json(
        ROOT / "site" / "scripts" / "print-published.cjs", ROOT / "site"
    )
    identity = published.load_identity()
    assert answer["identity"] == identity.namespace | {
        "forum_host": identity.forum_host
    }
    site = answer["siteData"]
    assert site["title"] == f"{identity.short_name} {identity.series}"
    assert site["shortName"] == identity.short_name
    assert site["series"] == identity.series
    # The home page's own headline, the masthead's sub-line and the
    # footer's sentence, in that order. All three were typed into the
    # templates until the hero was rewritten from the declaration, so all
    # three are pinned here beside the composed `title` rather than left
    # to the one that happened to be checked first.
    assert site["strapline"] == identity.strapline
    assert site["tagline"] == identity.tagline
    assert site["forum"] == identity.forum
    assert site["forumHost"] == identity.forum_host
    # Not `identity.proposal_form`: the showcase publishes the derived
    # address, which is empty while the declaration still carries a
    # placeholder. This comparison *is* the boundary fixture for that rule
    # -- `published.cjs` has its own copy of it (D-14), and a copy nothing
    # compares is a copy that drifts.
    assert site["applyForm"] == identity.proposal_form_url
    assert site["organisation"] == identity.organisation
    assert site["contact"] == identity.contact
    assert site["repository"] == identity.repository
    assert site["publishRepository"] == published.load().publish_repository


def test_every_bundle_the_application_builds_carries_the_declared_identity() -> None:
    """All four configurations, and all four `define`s.

    `src/content/render.ts` resolves `{{ instance.* }}` inside a
    volunteer's browser and `src/instance.ts` throws when the define is
    absent, so a configuration that carried the address but not the
    identity would build a bundle that fails on its first render -- and
    would do it in exactly one of the four, which is the shape that passes
    a test suite and ships broken.
    """
    answer = _bundle_configurations()
    identity = published.load_identity()
    assert set(answer["identityDefines"]) == {
        "production",
        "island-signup",
        "island-verify",
        "island-survey",
    }
    for mode, defined in answer["identityDefines"].items():
        assert defined is not None, f"{mode} builds without the identity define"
        assert json.loads(json.loads(defined)) == identity.namespace, mode


# ------------------------------------------------------------------ #
# 7 -- where the build pushes, derived from where it is served
# ------------------------------------------------------------------ #


def test_the_push_target_is_derived_from_the_published_address() -> None:
    """GitHub Pages serves a project repository at
    `https://<owner>.github.io/<repository>/` and at no other shape of
    address, so the two are one fact. The owner is compared
    case-insensitively on purpose: GitHub lower-cases it in the host and a
    clone URL does not care, so nothing here has to know the
    organisation's own capitalisation."""
    address = published.load()
    owner, _, repository = address.publish_repository.partition("/")
    assert address.host == f"{owner}.github.io"
    assert address.path_prefix == f"/{repository}/"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/",
        "https://example.test/somewhere/",
        "https://example-collective.github.io/",
        "https://example-collective.github.io/one/two/",
        "https://github.io/repository/",
    ],
)
def test_the_push_target_refuses_an_address_it_cannot_derive_one_from(
    url: str,
) -> None:
    """Refusing what has no safe default, applied to the largest thing in
    this repository that could be
    put in the wrong place. A custom domain says nothing whatever about
    which repository serves it; a bare `github.io` root and a two-segment
    path are not project-page shapes either. There is no safe default for
    "push a whole site somewhere", so each of these stops."""
    with pytest.raises(ValueError, match="not a GitHub Pages project address"):
        _ = published.Published(url=url).publish_repository


def _push_step_scripts() -> dict[Path, str]:
    """The `run:` block of each workflow's own push step, found by the
    secret it reads rather than by its `name:` -- the same rule
    `tools/tests/repository/test_workflows.py` already applies, so a rename of a step
    does not silently stop either module checking it."""
    found: dict[Path, str] = {}
    for name, job in (
        (Path(".github/workflows/deploy.yml"), "build"),
        (Path(".github/workflows/publish-showcase.yml"), "publish"),
    ):
        workflow = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
        for step in workflow["jobs"][job]["steps"]:
            env = step.get("env", {})
            if any("SHOWCASE_DEPLOY_TOKEN" in str(value) for value in env.values()):
                found[name] = str(step["run"])
                break
        else:  # pragma: no cover - the assertion below is the report
            raise AssertionError(f"{name.as_posix()} has no push step to read")
    return found


def test_both_publishing_workflows_read_the_push_target_rather_than_naming_it() -> None:
    """The gap this module used to name, closed.

    Both workflows cloned `<organisation>/<repository>` in hard text, so
    changing `published_url` moved every address a visitor sees and left
    the push where it was -- a duplicate publishing its own site into the
    previous instance's repository, which is worse than either half being
    wrong on its own. Asserted on the `run:` block each one actually
    executes: it must reach the derivation, and it must not spell the
    answer out.
    """
    target = published.load().publish_repository
    for name, script in _push_step_scripts().items():
        assert "publish_repository" in script, (
            f"{name.as_posix()}'s push step does not read the derived push "
            "target -- naming it there is how the address and the repository "
            "start disagreeing"
        )
        assert "${target}" in script, f"{name.as_posix()} never uses what it read"
        assert target not in script, (
            f"{name.as_posix()} writes the push target out as well as deriving it"
        )


# ------------------------------------------------------------------ #
# 8 -- the identity sweep: nowhere written twice
# ------------------------------------------------------------------ #

#: Files that must hold this instance's identity as a literal because they
#: are read by something that cannot reach the declaration, and that are
#: therefore *checked* against it below rather than merely exempted.
#:
#: One is left. `.github/CODEOWNERS` is read by GitHub verbatim, with no
#: expansion of any kind, before any of this project's own code runs, so
#: the literal has nowhere else to be.
#:
#: The two Worker sources that were here named the repository they
#: dispatch into, on the argument that a Worker runs on Cloudflare and
#: never sees this repository. That argument has the answer
#: `ALLOWED_ORIGIN` already took -- a deploy-time `--var` -- and it has
#: been taken: neither source names a repository now, and
#: `test_no_relay_source_names_a_repository_at_all` below refuses one
#: coming back. Nothing under `services/` is exempt from this sweep any
#: more either, which is what `_IDENTITY_UNSWEPT_TREES` no longer says.
_LITERAL_IDENTITY_FILES = (Path(".github/CODEOWNERS"),)

#: Files that hold this instance's identity because something *generated*
#: them from the declaration. Not a second copy in the sense this module
#: refuses -- nothing here is authored, and
#: `tools/scripts/generate_brand_css.py --check` fails the build the moment one
#: of them stops agreeing with `instance/config.json`. Checked below all
#: the same, rather than exempted: a generated file nobody compares is a
#: hand-written one with better manners.
_DERIVED_IDENTITY_FILES = (
    Path("docs/handbook/assets/announcement-template.svg"),
    Path("docs/handbook/assets/flyer-template.svg"),
    Path("docs/handbook/assets/video-call-background.svg"),
)

#: Files that still name this organisation and are somebody else's task,
#: each with the phase that owns it. Not a general exemption: adding a
#: path here is a decision, and the reason is beside it.
#:
#: The list itself lives in `instance_identity.DEFERRED`
#: and this reads it. It is the same fact answering two
#: questions -- which *source* this module may forgive, and which phrases
#: a sweep of a *built* second instance may find -- and two lists
#: would let a file be forgiven on one side while the other still refused
#: it. Each entry carries its own reason there, beside the path.
_IDENTITY_DEFERRED = {entry.path: entry.owner for entry in instance_identity.DEFERRED}

#: Test trees. A fixture naming this organisation is a fixture of *this*
#: instance, and the check that actually matters for behaviour is the
#: build of a second instance and the sweep of its output -- not the absence
#: of a string from a test double.
#:
#: The whole of `services/` was one entry here, which was a tree exemption
#: doing a test tree's job: it covered each relay's suite and, silently,
#: each relay's source and README beside it. Only the three suites are
#: named now, so a Worker source or a worker's own documentation naming
#: this organisation fails here.
_IDENTITY_UNSWEPT_TREES = (
    "tools/tests/",
    "app/tests/",
    "services/auth-proxy/test/",
    "services/form-relay/test/",
    "services/signup-relay/test/",
)


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_no_source_file_writes_this_instances_identity_a_second_time() -> None:
    """The clause that makes "one declaration" a fact for the identity
    the way `test_no_source_file_writes_the_published_address_a_second_
    time` already does for the address.

    The organisation's name, its contact address and its forum -- in both
    the form a link takes and the form a sentence takes. Not the series'
    title and not the short name: see this module's own docstring for the
    two phases that still own those.
    """
    identity = published.load_identity()
    needles = (
        identity.organisation,
        identity.contact,
        identity.forum,
        identity.forum_host,
    )
    allowed = {path.as_posix() for path in _LITERAL_IDENTITY_FILES}
    allowed |= {path.as_posix() for path in _DERIVED_IDENTITY_FILES}
    allowed |= {path.as_posix() for path in _IDENTITY_DEFERRED}
    allowed.add(published.INSTANCE_PATH.as_posix())
    instance_boundary = boundary.load()

    offending: list[tuple[str, str]] = []
    for name in _tracked_files():
        if name.startswith(_UNSWEPT) or name.startswith(_IDENTITY_UNSWEPT_TREES):
            continue
        if name in allowed:
            continue
        # The instance's own records are where its own identity belongs.
        if instance_boundary.owner_of(name) == boundary.INSTANCE:
            continue
        path = ROOT / name
        if path.suffix.lower() in _BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for needle in needles:
            if needle in text:
                offending.append((name, needle))
                break

    assert offending == [], (
        "these files write this instance's own identity a second time, which "
        f"instance/config.json exists to make impossible: {offending}"
    )


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_the_identity_sweep_would_see_a_second_copy_if_there_were_one() -> None:
    """A sweep that matched nothing would pass for free. Each needle is
    found where a copy legitimately is, rather than trusted for coming
    back empty."""
    identity = published.load_identity()
    found = {
        needle: [
            name
            for name in (path.as_posix() for path in _LITERAL_IDENTITY_FILES)
            if needle in (ROOT / name).read_text(encoding="utf-8")
        ]
        for needle in (identity.organisation, identity.forum_host)
    }
    assert found[identity.organisation], "the organisation needle matches nothing"
    assert _IDENTITY_DEFERRED, "the deferred list is empty -- widen the sweep"
    for path, reason in _IDENTITY_DEFERRED.items():
        assert (ROOT / path).exists(), f"{path.as_posix()} ({reason}) is gone"


def test_the_generated_templates_carry_the_identity_the_declaration_names() -> None:
    """The exemption above, checked rather than merely granted.

    These three files are what a collaborator downloads, so the identity
    travelling outward is whatever they say. They are generated from
    `instance/config.json` and
    `tools/scripts/generate_brand_css.py --check` refuses them the moment they
    stop being what it derives -- this is the assertion that the
    derivation is of *this* declaration and not of a literal somebody
    typed and forgot.

    Each value is looked for in the declared spelling *or* in capitals,
    because a display line is set in capitals and a document title is not,
    and which of the two a given file uses is a typographic decision that
    belongs to the composition rather than to this check. What is asserted
    either way is that the string came from the declaration.
    """
    identity = published.load_identity()
    for path in _DERIVED_IDENTITY_FILES:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert identity.forum_host in text, (
            f"{path.as_posix()} no longer names the forum this instance "
            f"declares ({identity.forum_host})"
        )
        assert identity.series in text or identity.series.upper() in text, (
            f"{path.as_posix()} no longer names this series ({identity.series})"
        )


#: The team an *instance* sends its review requests to, and the slug
#: `app/src/auth/role.ts` asks GitHub about when it decides who signs in
#: as a Board member. The literal that file writes, rather than a name for
#: it: it is the value being compared here, and GitHub is the thing that
#: has to agree with it.
BOARD_TEAM: Final = "editorial-board"


def _codeowners_owners(text: str) -> list[str]:
    """Every owner `.github/CODEOWNERS` names, in file order.

    GitHub reads that file with a comment syntax and nothing else, so a
    `#` opens a comment wherever it appears and the first token of what is
    left is the pattern. `tools/tests/repository/test_codeowners.py` takes
    the file apart the same way and asks a different question of the same
    tokens: whether each pattern matches anything. This one asks who the
    tokens after it are.
    """
    owners: list[str] = []
    for raw in text.splitlines():
        line = raw.partition("#")[0].strip()
        if not line:
            continue
        _pattern, *rest = line.split()
        owners.extend(rest)
    return owners


def test_the_literals_that_cannot_read_the_declaration_still_agree_with_it() -> None:
    """The exemption above, checked rather than merely granted -- and two
    shapes are correct, because two kinds of repository carry this file.

    `.github/CODEOWNERS` is read by GitHub verbatim, before any code of
    this project's runs, so the copy has to exist. What must not happen is
    that it drifts, and a copy nothing compares is a copy that will.

    **An instance** is a series run by an Editorial Board. Every review
    request goes to that board's GitHub team, whose slug is `BOARD_TEAM`
    above -- the same one `app/src/auth/role.ts` asks GitHub about when it
    decides who signs in as a Board member -- inside the organisation that
    is the owner half of `instance/config.json`'s `identity.repository`. A
    team under any other organisation is the defect this check was written
    for: every review request goes to nobody, and nothing anywhere else
    says so.

    **The product** is a public repository with one maintainer. There is
    no Editorial Board in it and no organisation team to name, and the one
    thing the file earns there is that an outside contributor's pull
    request reaches that maintainer; the value is a single user handle.
    That shape is not hypothetical: a repository published from this one
    declares the worked example's identity, so a check that knew only the
    first shape would demand `@example-instance/editorial-board` -- a team
    in an organisation nobody owns -- of the one repository where a
    maintainer's own handle is the right answer, and where it is written
    from the account that publication is made under.

    So two clauses, and they divide the way the two kinds of repository
    do. **Wherever a team is named at all**, it has to be the declared
    organisation's board -- that clause holds in every repository, product
    included, and it is the original check. **Wherever an instance is
    declared**, the team has to be there: a file that quietly lost it
    would leave a board's own repository routing nothing to the board.
    `helpers.instance_identity` is what tells the two apart, and it is the
    same condition the twenty-four abstaining tests use -- a repository
    still shipping the example as its instance is either a derived product
    or a duplicate that has not been made anybody's yet, and neither has a
    board to name.
    """
    identity = published.load_identity()
    owner, _, _ = identity.repository.partition("/")
    board = f"@{owner}/{BOARD_TEAM}"

    codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    owners = _codeowners_owners(codeowners)
    assert owners, (
        ".github/CODEOWNERS names no owner on any rule, so it requests no "
        "review from anybody -- neither of the two shapes this file has is "
        "one with nobody in it"
    )

    named_teams = [name for name in owners if "/" in name]
    outside = [name for name in named_teams if name != board]
    assert outside == [], (
        f".github/CODEOWNERS asks {outside} for a review, and "
        f"instance/config.json declares the organisation {owner}. A team "
        "outside it does not exist as far as GitHub is concerned, so every "
        "review request that rule makes goes to nobody, silently"
    )

    if instance_identity.ships_the_example_as_its_instance():
        return
    assert board in owners, (
        f".github/CODEOWNERS names no {board}, and instance/config.json "
        "declares an instance of its own -- so this is a board's repository "
        "with nothing routing a review to the board. The single-handle "
        "shape belongs to a public repository with one maintainer, which "
        "declares the worked example's identity and carries that "
        "maintainer's own account on its catch-all rule"
    )


#: Every Worker source in this repository. Two of them used to be where the
#: repository this cockpit lives in was allowed to be written a second
#: time: a Cloudflare Worker deploys from its own package and can read
#: nothing else, so `owner/name` was a constant in each and every GitHub
#: address in the file was built off it. The copy is gone rather than
#: merely checked -- the deploy workflows derive it and pass it to
#: `wrangler deploy --var` -- so what is asserted below is that they name
#: no repository at all. All three are read, not only the two: a value
#: that is wrong to hold in one of these files is wrong to hold in any of
#: them.
_RELAY_SOURCES = (
    Path("services/auth-proxy/src/index.js"),
    Path("services/form-relay/src/index.js"),
    Path("services/signup-relay/src/index.js"),
)

#: The two workflows that deploy a worker talking to this repository's own
#: GitHub API, and therefore the two that have to hand it one.
#: `deploy-auth-proxy.yml` is not here: that worker forwards two
#: `github.com` OAuth paths and touches no repository at all.
_REPOSITORY_DEPLOY_WORKFLOWS = (
    Path(".github/workflows/deploy-form-relay.yml"),
    Path(".github/workflows/deploy-signup-relay.yml"),
)

#: A GitHub REST address whose repository is written out rather than
#: interpolated. `${` is the only thing allowed to follow `/repos/`, which
#: is what makes this a check on *any* repository literal rather than only
#: on this instance's: a duplicate that pasted its own in fails here too,
#: and so does a derived product carrying the example's.
_REPOSITORY_LITERAL = re.compile(r"api\.github\.com/repos/(?!\$\{)")


def test_no_relay_source_names_a_repository_at_all() -> None:
    """The binding that replaced the constant, and the one that has to
    bite.

    Two of the three workers talk to this repository's own GitHub API: the
    form relay to send one `repository_dispatch`, the signup relay to read
    a published event key, check the survey switch, write a queue entry and
    dispatch. Which repository that is, is `instance/config.json`'s
    `identity.repository`, and it is passed to `wrangler deploy --var` as
    `REPOSITORY`, so no source here writes one.

    Checked twice, on purpose. The declared repository must not appear at
    all -- that is this instance's own copy coming back. And no GitHub REST
    address may write its repository out instead of interpolating one --
    that is the example's copy, or a duplicate's, neither of which the
    first assertion could ever see.
    """
    declared = published.load_identity().repository
    for path in _RELAY_SOURCES:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert declared not in text, (
            f"{path.as_posix()} names the repository this cockpit lives in "
            f"({declared}) again. That value is instance/config.json's "
            "identity.repository and has one home; the deploy workflow "
            "derives it and passes it to `wrangler deploy --var`, so "
            "nothing has to be written here"
        )
        found = _REPOSITORY_LITERAL.search(text)
        assert found is None, (
            f"{path.as_posix()} builds a GitHub address on a repository "
            "written out rather than on the REPOSITORY binding "
            f"({text[found.start() : found.start() + 60]!r}) -- a worker "
            "naming any repository is a worker a duplicate has to edit "
            "before its first deploy"
        )


def test_both_dispatching_deploys_hand_the_worker_the_declared_repository() -> None:
    """The other half: a source naming no repository deploys a worker that
    refuses every request unless the deploy supplies one.

    Asserted on the `run:` block each workflow actually executes -- it must
    reach the derivation, it must pass what it read to `--var`, and it must
    not spell the answer out. The same three clauses
    `test_both_relay_deploys_hand_the_worker_the_declared_origin` holds for
    the origin beside it.
    """
    repository = published.load_identity().repository
    for name, script in _deploy_scripts(_REPOSITORY_DEPLOY_WORKFLOWS).items():
        assert "print(load_identity().repository)" in script, (
            f"{name.as_posix()}'s deploy step does not read the declared "
            "repository -- naming it in the worker's own source is how a "
            "duplicate ends up with a relay dispatching at somebody else's"
        )
        assert "REPOSITORY:$repository" in script, (
            f"{name.as_posix()} never hands what it read to wrangler"
        )
        assert repository not in script, (
            f"{name.as_posix()} writes the repository out as well as deriving it"
        )


# ------------------------------------------------------------------ #
# 9 -- the prefix this instance numbers its editions under
# ------------------------------------------------------------------ #


def test_this_repository_declares_the_prefix_its_editions_are_numbered_under() -> None:
    """`validate.py` used to fix an edition code as
    `^MRG-\\d{1,4}$` -- the initials of *this* series, in the product's own
    validator -- and the one sweep that compares two instances could never
    catch it, because both instances were forced to write it.

    The two derived forms are asserted beside the value because they are
    what actually reaches a reader: the code the showcase prints and the
    poster sets, and the event id (D-19) that is in the address of every
    event page, in `instance/keys/events/<id>.pub` and in a certificate's own
    verification link."""
    editions = published.load_edition_prefix()
    assert editions.code_prefix == f"{editions.value}-"
    assert editions.event_prefix == editions.code_prefix.lower()
    assert editions.describes(f"{editions.code_prefix}05")
    assert not editions.describes(f"{editions.event_prefix}05")
    assert not editions.describes(f"{editions.code_prefix}00000")


#: The fact this reading is about: an edition this instance has actually
#: assigned. A series that has not held a session yet has assigned none --
#: `next_edition_number` is still 1 and no row carries a code -- so there
#: is no edition for a declared prefix to disagree with, and the freeze
#: below has nothing yet to freeze. Every instance starts in that state,
#: and a duplicate stays in it from the moment it carries out
#: `declarations/standing-up.yml`'s `own_records` until it schedules its
#: first event.
#:
#: Said rather than left to a green run, because abstaining is not
#: passing: a reading that quietly checks nothing is how a guard stops
#: guarding without anybody being told. `test_retired_paths.py` states the
#: same thing for a history a duplicate does not have.
#:
#: Narrower than "the counter is 1", deliberately. A counter of 1 beside
#: rows that do carry codes is the renumbering this check exists to
#: refuse -- the counter reset while the editions it numbered stayed -- so
#: that state is read here, never skipped.
_NO_EDITION_ASSIGNED: Final = (
    "this instance has assigned no edition yet: next_edition_number is still "
    "1 and no row carries an edition code, so there is nothing here for the "
    "declared prefix to be checked against"
)


def test_the_declared_prefix_is_the_one_this_instances_editions_use() -> None:
    """The freeze, seen from the repository rather than from the
    validator: every edition this instance has assigned is numbered under
    the prefix it declares.

    That is what makes changing the declaration impossible in practice
    rather than merely discouraged -- an edition code is in a published
    address, on an issued certificate and in a key filename, so the day
    the two disagree the file is wrong, not the editions.

    **Where the evidence lives has moved**, and the
    reasoning is worth keeping. This used to read the `edition_code` of
    every row of `instance/data/speakers.yml` and refuse an empty list, so that the
    check could not pass by having nothing to check (D-25). Those rows
    were then cleared of personal data and every code went with them --
    but the editions themselves did not. `instance/data/config.yml`'s
    `next_edition_number` is a **high-water mark, not a count of rows**:
    it is what still says this series is already numbering under this
    prefix, and it is the one thing left in the repository that a
    renumbering would have to go through. So the non-vacuity comes from
    the counter now, and the rows are still held to the prefix whenever
    there are any.

    Which makes this the check that holds the counter still, too. Resetting
    it to 1 alongside the emptied rows would have renumbered MRG-01..MRG-04 --
    editions that already exist on posters and in sent mail -- and this
    assertion is what refuses that.
    """
    editions = published.load_edition_prefix()
    config = yaml.safe_load(
        (ROOT / "instance" / "data" / "config.yml").read_text(encoding="utf-8")
    )
    counter = config["next_edition_number"]
    speakers = yaml.safe_load(
        (ROOT / "instance" / "data" / "speakers.yml").read_text(encoding="utf-8")
    )
    assigned = [
        entry["edition_code"]
        for entry in speakers or ()
        if isinstance(entry, dict) and entry.get("edition_code")
    ]

    if counter == 1 and not assigned:
        pytest.skip(_NO_EDITION_ASSIGNED)

    assert isinstance(counter, int) and counter > 1, (
        "this instance has assigned no edition at all"
    )
    assert editions.describes(f"{editions.code_prefix}{counter - 1}")
    assert [code for code in assigned if not editions.describes(code)] == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "must be the prefix this instance numbers"),
        ("", "must be the prefix this instance numbers"),
        (7, "must be the prefix this instance numbers"),
        (" MRG", "surrounding whitespace"),
        ("MRG ", "surrounding whitespace"),
        ("vw", "is not upper case"),
        ("Vw", "is not upper case"),
        ("1W", "does not start with an ASCII letter"),
        ("TOOLONGABBREVIATION", "longer than 8 characters"),
        ("MRG-", "other than ASCII capitals and digits"),
        ("V.W", "other than ASCII capitals and digits"),
        ("V_W", "other than ASCII capitals and digits"),
        ("V W", "other than ASCII capitals and digits"),
        ("ABCÉ", "other than ASCII capitals and digits"),
    ],
)
def test_a_prefix_that_reads_plausibly_and_is_wrong_is_refused_at_declaration(
    value: Any, expected: str
) -> None:
    """Each of these is a shape somebody would actually type, and each
    fails somewhere nobody would look.

    A lower-case prefix breaks the one identity D-19 rests on -- an event
    id *is* the edition code lower-cased -- so `Vw-1` and `MRG-1` would be
    two codes with one address, one `instance/keys/events/mrg-1.pub` and one
    `CONVENER_EVENT_KEY_MRG_1`. A prefix carrying its own separator collides two
    editions on one repository secret, because `eventkeys.secret_name`
    folds `.` and `-` to `_` and says itself that the fold is lossy. A
    non-ASCII capital makes `str.lower()` a place where a URL path segment
    quietly acquires a percent-encoding. None of those is visible in the
    string, which is why the refusal is here and not where the value
    lands."""
    with pytest.raises(ValueError, match=expected):
        published.edition_prefix_from_data(
            {"v": published.DECLARATION_VERSION, published.EDITION_PREFIX_KEY: value}
        )


@pytest.mark.parametrize("value", ["MRG", "A", "MRG", "ABCDEFGH", "S2", "V0W9"])
def test_a_prefix_a_duplicate_could_reasonably_want_is_accepted(value: str) -> None:
    """The other half of the rule above. The refusals are narrow on
    purpose: what is refused is a shape that breaks a URL, a filename or a
    secret name, never a prefix somebody's series happens to want."""
    editions = published.edition_prefix_from_data(
        {"v": published.DECLARATION_VERSION, published.EDITION_PREFIX_KEY: value}
    )
    assert editions.value == value
    assert editions.describes(f"{value}-1")


def test_a_declaration_of_the_wrong_version_stops_before_the_prefix() -> None:
    with pytest.raises(ValueError, match="not a supported format version"):
        published.edition_prefix_from_data({"v": 99, "edition_prefix": "MRG"})


def test_every_bundle_the_application_builds_carries_the_declared_prefix() -> None:
    """All four configurations, and all four `define`s -- the same claim
    `test_every_bundle_the_application_builds_carries_the_declared_
    identity` makes, for the same reason.

    `src/state/agenda.ts::nextEditionCode` composes the next edition code
    inside a volunteer's browser, where no file can be read, and
    `src/instance.ts::editionPrefix` throws rather than defaulting. A
    configuration carrying the identity but not the prefix would build a
    bundle that throws the moment somebody locks a date -- in exactly one
    of the four, which is the shape that passes a test suite and ships
    broken."""
    answer = _bundle_configurations()
    editions = published.load_edition_prefix()
    assert answer["editionPrefix"] == editions.value
    assert set(answer["editionPrefixDefines"]) == {
        "production",
        "island-signup",
        "island-verify",
        "island-survey",
    }
    for mode, defined in answer["editionPrefixDefines"].items():
        assert defined is not None, f"{mode} builds without the prefix define"
        assert json.loads(defined) == editions.value, mode


def test_this_side_of_the_prefix_boundary_reads_the_shared_cases() -> None:
    """D-14's own discipline: one declaration, one reader per language,
    and a worked example binding them rather than a comment claiming they
    agree. `app/tests/scripts/edition-prefix.test.ts` reads this same fixture
    against `app/scripts/published.mjs::isEditionPrefix`.

    The showcase has no reader of this and needs none -- it prints the
    codes `site/src/_data/events.json` hands it and never composes one --
    so this boundary has two sides, not three."""
    fixture = json.loads(
        (ROOT / "tools" / "tests" / "fixtures" / "edition-prefix.json").read_text(
            encoding="utf-8"
        )
    )
    for case in fixture["cases"]:
        value, accepted = case["value"], case["accepted"]
        assert (published.EDITION_PREFIX_RE.match(value) is not None) is accepted, value
        declaration = {
            "v": published.DECLARATION_VERSION,
            published.EDITION_PREFIX_KEY: value,
        }
        if accepted:
            assert published.edition_prefix_from_data(declaration).value == value
        else:
            with pytest.raises(ValueError, match=published.EDITION_PREFIX_KEY):
                published.edition_prefix_from_data(declaration)
    assert any(case["accepted"] for case in fixture["cases"])
    assert any(not case["accepted"] for case in fixture["cases"])


# ------------------------------------------------------------------ #
# 9 -- a duplicate that has not been configured says so
# ------------------------------------------------------------------ #


def _laid_out(root: Path, declaration: dict[str, Any]) -> Path:
    """A scratch repository root holding a declaration and the example the
    product ships beside it -- the two files `published.unconfigured`
    reads, and nothing else."""
    (root / published.INSTANCE_PATH.parent).mkdir(parents=True, exist_ok=True)
    (root / published.INSTANCE_PATH).write_text(
        json.dumps(declaration), encoding="utf-8", newline="\n"
    )
    example = root / published.EXAMPLE_INSTANCE_PATH
    example.parent.mkdir(parents=True, exist_ok=True)
    example.write_text(
        (ROOT / published.EXAMPLE_INSTANCE_PATH).read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="\n",
    )
    return root


def _example_declaration() -> dict[str, Any]:
    loaded = json.loads(
        (ROOT / published.EXAMPLE_INSTANCE_PATH).read_text(encoding="utf-8")
    )
    assert isinstance(loaded, dict)
    return loaded


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_this_repository_has_been_configured() -> None:
    """The control that makes every other case here mean something: this
    instance shares no declared value with the example, so the banner is
    silent on the site people actually read."""
    assert published.unconfigured() == ()


def test_the_declaration_names_every_value_that_says_who_is_publishing() -> None:
    """Eleven, enumerated from the declaration's own lists rather than
    written out again: the address, the edition prefix and each identity
    field. A field added to `IDENTITY_FIELDS` and not to this comparison
    would be a field a duplicate could leave as the example's without
    anything noticing -- which is exactly how `strapline` once slipped past
    the second-instance sweep."""
    values = published.declared_values(_example_declaration())
    assert set(values) == {
        published.PUBLISHED_URL_KEY,
        published.EDITION_PREFIX_KEY,
    } | {f"{published.IDENTITY_KEY}.{field}" for field in published.IDENTITY_FIELDS}


def test_a_deployment_of_the_example_itself_is_unconfigured_in_every_value(
    tmp_path: Path,
) -> None:
    """What a duplicate deployed before it was configured actually looks
    like, and what `tools/tests/repository/test_second_instance.py` builds on every
    run: `examples/the-example-collective/`'s own declaration, sitting in
    `instance/`."""
    root = _laid_out(tmp_path, _example_declaration())
    assert published.unconfigured(root) == tuple(
        sorted(published.declared_values(_example_declaration()))
    )


def test_a_half_configured_duplicate_is_still_unconfigured(tmp_path: Path) -> None:
    """The dangerous state, and the reason this compares value by value
    rather than file against file: somebody who renames the organisation
    and forgets the address publishes at a prefix that is not theirs while
    every page reads as their own. A whole-file comparison calls that
    configured."""
    declaration = _example_declaration()
    declaration[published.IDENTITY_KEY]["organisation"] = "A Real Society"
    root = _laid_out(tmp_path, declaration)
    remaining = published.unconfigured(root)
    assert f"{published.IDENTITY_KEY}.organisation" not in remaining
    assert published.PUBLISHED_URL_KEY in remaining
    assert f"{published.IDENTITY_KEY}.contact" in remaining


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_a_placeholder_in_a_degradable_field_is_not_this_warning(
    tmp_path: Path,
) -> None:
    """`REPLACE` decides nothing here, and that is a decision.

    This repository has declared `proposal_form: https://tally.so/r/
    REPLACE` since before the declaration existed, and D-13 makes that an
    ordinary state that degrades at the point of use -- `/propose/` offers
    the contact address instead of a dead link, and says so on the page
    where it matters. A banner across every page of a working site because
    one optional form is not open yet is a banner somebody deletes within
    the week, and it would take the real warning with it.

    In the other eight identity fields the marker never reaches a build at
    all: `identity_from_data` refuses the declaration outright, so there
    would be no page to carry a banner. The marker is therefore already
    handled twice, in opposite directions, and both of them are right.
    """
    declaration = json.loads(
        (ROOT / published.INSTANCE_PATH).read_text(encoding="utf-8")
    )
    # The placeholder is put here rather than found here. This instance's
    # own `proposal_form` is whatever it happens to declare, and
    # standing-up's `proposal_form_live` is the step that fills it in -- so
    # reading the live value made this claim hold only until a duplicate
    # opened its form, and fail from that commit onwards, in the one place
    # the skipif above lets this run at all. What is under test is a
    # property of `unconfigured`, not a fact about anybody's declaration.
    declaration[published.IDENTITY_KEY]["proposal_form"] = (
        f"https://tally.so/r/{published.PLACEHOLDER_MARKER}"
    )
    assert published.is_placeholder(
        declaration[published.IDENTITY_KEY]["proposal_form"]
    )
    assert published.unconfigured(_laid_out(tmp_path, declaration)) == ()


def test_an_example_that_cannot_be_read_stops_rather_than_reporting_configured(
    tmp_path: Path,
) -> None:
    """D-25 at the one place it is easiest to get backwards. With nothing
    to compare against, nothing can be *proved* about this declaration --
    and a check that answers "configured" when it could not run is not a
    check. The application's build already depends on that directory
    outright (`app/scripts/example-instance.mjs`), so this adds no failure
    a duplicate did not already have."""
    root = _laid_out(tmp_path, _example_declaration())
    (root / published.EXAMPLE_INSTANCE_PATH).unlink()
    with pytest.raises(ValueError, match="cannot be read"):
        published.unconfigured(root)


def test_the_showcase_tells_its_templates_whether_this_instance_is_configured() -> None:
    """The real, committed `.eleventy.js`, called with a stub -- so this is
    the value `_includes/layout.njk` actually tests before deciding whether
    to publish the banner, not a reading of the file that computes it."""
    answer = _node_json(
        ROOT / "site" / "scripts" / "print-published.cjs", ROOT / "site"
    )
    assert answer["siteData"]["unconfigured"] == list(published.unconfigured())


def test_every_bundle_the_application_builds_carries_the_unconfigured_verdict() -> None:
    """All four configurations, and all four `define`s.

    Named separately from the identity define for a reason the other three
    do not have: the ordinary answer here is the *empty* list, so a
    configuration that had quietly lost this define would be
    indistinguishable from a configured instance, and the warning would
    fall silent precisely where the build was broken. `src/instance.ts`
    therefore throws on an absent define and the value travels as JSON --
    `"[]"` is a value, an absent define is not.
    """
    answer = _bundle_configurations()
    assert answer["unconfigured"] == list(published.unconfigured())
    assert set(answer["unconfiguredDefines"]) == {
        "production",
        "island-signup",
        "island-verify",
        "island-survey",
    }
    for mode, defined in answer["unconfiguredDefines"].items():
        assert defined is not None, f"{mode} builds without the verdict define"
        assert json.loads(json.loads(defined)) == list(published.unconfigured()), mode
