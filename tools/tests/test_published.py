"""One declaration, read from every side, and nowhere written twice.

Phase 10, task 2. This project's published address used to be written out
thirty times across twelve files -- four `base:` in `app/vite.config.ts`,
two constants in `site/.eleventy.js`, three in `tools/convener_ops/`, a
calendar UID domain, two relay configurations, two templates' links, two
shared fixtures -- with tests binding the copies to each other. Those
tests were honest about what they could say, and it was never "there is
one": only "these still agree today".

`config/instance.json` is the one. This module holds four things, and the
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
   `base` and the `define` each configuration actually produces.

Then the sweep: no file outside the declaration writes the address again.

What this module does **not** cover, stated rather than left to be found:

- **The published output itself.** Nothing here builds the site and reads
  the emitted HTML for a second instance's address; that is task 5's own
  build sweep, and it is the acceptance criterion the whole phase rests
  on. `test_site.py` covers today's instance at the built-page level
  (`test_no_built_page_emits_a_root_relative_link_without_the_prefix`,
  `test_the_governance_record_link_resolves_to_the_published_handbook`).
- **`docs/`.** The handbook names this organisation's address in prose,
  which is task 3's substitution work, not an address a build derives.
- **Where the build *pushes*.** `deploy.yml` and `publish-vitrine.yml`
  clone a named repository, and that name is not derived from anything.
  Changing `published_url` alone therefore moves every address a visitor
  ever sees while leaving the push target where it was -- a real gap,
  named here so that nobody reads clause 4 as covering more than it does.
"""

from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

from convener_ops import (
    agenda,
    boundary,
    certificate,
    published,
    registration,
    survey_invite,
)
from convener_ops.paths import repo_root

ROOT = repo_root()

_MINIMAL: dict[str, Any] = {
    "owner": boundary.INSTANCE,
    "v": published.DECLARATION_VERSION,
    published.PUBLISHED_URL_KEY: "https://example.test/somewhere/",
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


def test_the_declaration_is_the_instances_own_file() -> None:
    """The boundary of task 1, applied to the file this task adds: a
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
        pytest.skip("node is not on PATH -- cannot run the build's own config")
    assert result.returncode == 0, result.stdout + result.stderr
    loaded = json.loads(result.stdout)
    assert isinstance(loaded, dict)
    return loaded


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
    answer = _node_json(ROOT / "app" / "scripts" / "print-published.mjs", ROOT / "app")
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

#: The one place the address is allowed to appear a second time, and why.
#: A Cloudflare Worker deploys from its own `wrangler.toml` and can read
#: nothing else -- no repository, no include, and no TOML parser here that
#: would not be a new dependency. So the copy has to exist; what must not
#: happen is that it drifts, which each relay's own suite refuses (see
#: `services/*/test/index.test.js`) and which this module checks once more
#: from the side that owns the declaration.
_DEPLOYED_ORIGIN_FILES = (
    Path("services/auth-proxy/wrangler.toml"),
    Path("services/signup-relay/wrangler.toml"),
)

#: `docs/` is task 3's: the handbook names this organisation's address in
#: prose a substitution engine will carry, not in an address a build
#: derives. Everything else this repository tracks is swept.
_UNSWEPT = ("docs/",)

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


def test_no_source_file_writes_the_published_address_a_second_time() -> None:
    """The clause that makes "one declaration" a fact rather than a
    claim.

    Every writable form of the address is swept for -- the whole URL, the
    origin, the bare host and the path prefix -- because a copy does not
    have to be a copy of the whole thing to drift. Not the bare
    repository *name*: that is a different identity fact (which repository
    a build pushes to, what the architecture diagram calls it), owned by
    tasks 3 and 5, and folding it in here would make this test fail for a
    reason it cannot fix.
    """
    address = published.load()
    needles = (
        address.url,
        address.origin,
        address.host,
        address.path_prefix,
    )
    allowed = {path.as_posix() for path in _DEPLOYED_ORIGIN_FILES}
    allowed.add(published.INSTANCE_PATH.as_posix())

    offending: list[tuple[str, str]] = []
    for name in _tracked_files():
        if name.startswith(_UNSWEPT) or name in allowed:
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
        "these files write this project's published address a second time, "
        f"which config/instance.json exists to make impossible: {offending}"
    )


def test_the_sweep_would_see_a_second_copy_if_there_were_one() -> None:
    """A sweep that matched nothing would pass for free. This proves the
    needles are the right shape by finding them where a copy legitimately
    is -- the two relay configurations -- rather than by trusting an
    empty result."""
    address = published.load()
    for path in _DEPLOYED_ORIGIN_FILES:
        assert address.origin in (ROOT / path).read_text(encoding="utf-8"), path


def test_the_relays_deploy_the_address_this_project_is_published_at() -> None:
    """The exemption above, checked rather than merely granted. Each
    worker answers CORS preflights for one origin, handed to it as
    `env.ALLOWED_ORIGIN` from the file it deploys from; if that stopped
    being the address the application is served from, every request the
    registration form makes would be refused, in production, silently
    from the browser's point of view. Parsed with `tomllib` rather than
    matched, so a value moved into a different table is a failure and not
    a false pass."""
    expected = published.load().origin
    for path in _DEPLOYED_ORIGIN_FILES:
        config = tomllib.loads((ROOT / path).read_text(encoding="utf-8"))
        assert config["vars"]["ALLOWED_ORIGIN"] == expected, (
            f"{path.as_posix()} deploys ALLOWED_ORIGIN="
            f"{config['vars']['ALLOWED_ORIGIN']!r}, which is not the origin "
            f"this project is published at ({expected!r})"
        )


def test_no_build_configuration_reads_the_address_out_of_another_readers_source() -> (
    None
):
    """The shape this task replaced, refused so it cannot come back.

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
            "PATH_PREFIX again -- read config/instance.json through the "
            "reader for that side of the boundary instead of scraping "
            "another reader's source"
        )
