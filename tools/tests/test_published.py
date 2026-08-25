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

- **The published output itself.** Nothing here builds anything and
  reads what came out. `test_second_instance.py` does, as of task 5: it
  builds this whole repository as a *different* instance and sweeps the
  showcase, all four bundles, the handbook copied into them, the
  generated templates, the published feeds and the posters. That is the
  acceptance criterion the whole phase rests on, and it is a different
  claim from this module's -- a source can be clean while what a reader
  receives is not. `test_site.py` covers today's instance at the
  built-page level besides
  (`test_no_built_page_emits_a_root_relative_link_without_the_prefix`,
  `test_the_governance_record_link_resolves_to_the_published_handbook`).
- **`docs/superpowers/`.** The specs, the plans and the phase reports are
  this project's own record of its own decisions, quoting the address as
  it stood when each was written. Nothing builds them and nothing ships
  them. The rest of `docs/` *is* swept, as of task 3.

Task 3 added the second half of the same declaration -- who runs this
series -- and closed the gap this module used to name:

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
   either checked against the declaration (the relays, `CODEOWNERS`) or
   named with the phase that owns it.

What clause 8 does **not** sweep, stated rather than left to be found:
the series' *title* and the organisation's *short name*. "Monthly Reading Group
Series" is at present also this product's own name -- `convener_ops`,
`convener-register` -- and "TEC" is in the two downloadable SVG templates,
which derive it (phase 10 task 4), and in the demo instance (phase 11).
Sweeping either here would fail for a reason no source edit can fix, so
each is left to the phase that renames it.

**Task 5 sweeps both, and can, because it compares two instances rather
than looking for one.** `test_second_instance.py` builds this repository
with `instances/example/` in place of everything `config/boundary.yml`
hands to the instance, so the series' title and the short name in that
build are the *example's*; finding this instance's is then unambiguous in
a way it can never be in a source tree the product's own names live in.
"""

from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import instance_identity
import pytest
import yaml

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

#: A second instance's identity, manifestly synthetic: no real name, no
#: real address. Read from `instances/example/`, the fictional instance
#: phase 10 task 5 builds this whole repository as, rather than typed
#: here: a second synthetic identity would be a second answer to "what
#: does another instance look like", free to drift from the one an actual
#: build is made with. Every field `IDENTITY_FIELDS` names has to be
#: there, so a field added to the declaration and not to the example
#: fails loudly rather than being skipped.
_OTHER_IDENTITY: dict[str, Any] = json.loads(
    (ROOT / "instances" / "example" / "config" / "instance.json").read_text(
        encoding="utf-8"
    )
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

#: This project's own record of its own decisions. Every spec, plan and
#: phase report quotes the state of the world at the moment it was
#: written, including addresses and names that have since moved; nothing
#: builds them, nothing ships them, and rewriting them would be rewriting
#: history rather than code. The rest of `docs/` is swept -- it was
#: exempt in full until task 3 carried the handbook onto the substitution
#: vocabulary.
_UNSWEPT = ("docs/superpowers/",)

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
        ({published.IDENTITY_KEY: "The Example Collective"}, "must be an object"),
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
    is not proportionate; publishing it is what this instance did for two
    phases (phase 10 bilan, section 7.2)."""
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

    The composition is pinned here rather than restated: `title` is
    `short_name` and `series` with a space between them, and
    `tools/tests/test_site.py::_site_config` builds the same map to check
    the built pages against. Two spellings of that would be the copy this
    whole module exists to refuse.
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
    answer = _node_json(ROOT / "app" / "scripts" / "print-published.mjs", ROOT / "app")
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
    """S-4, applied to the largest thing in this repository that could be
    put in the wrong place. A custom domain says nothing whatever about
    which repository serves it; a bare `github.io` root and a two-segment
    path are not project-page shapes either. There is no safe default for
    "push a whole site somewhere", so each of these stops."""
    with pytest.raises(ValueError, match="not a GitHub Pages project address"):
        _ = published.Published(url=url).publish_repository


def _push_step_scripts() -> dict[Path, str]:
    """The `run:` block of each workflow's own push step, found by the
    secret it reads rather than by its `name:` -- the same rule
    `tools/tests/test_workflows.py` already applies, so a rename of a step
    does not silently stop either module checking it."""
    found: dict[Path, str] = {}
    for name, job in (
        (Path(".github/workflows/deploy.yml"), "build"),
        (Path(".github/workflows/publish-vitrine.yml"), "publish"),
    ):
        workflow = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
        for step in workflow["jobs"][job]["steps"]:
            env = step.get("env", {})
            if any("VITRINE_DEPLOY_TOKEN" in str(value) for value in env.values()):
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
#: - the two relays' `wrangler.toml` and their Worker sources: a Worker
#:   deploys from its own package and never sees this repository, exactly
#:   the argument task 2 already made and proved for `ALLOWED_ORIGIN`;
#: - `.github/CODEOWNERS`: GitHub reads it verbatim, with no expansion of
#:   any kind, before any of this project's own code runs.
_LITERAL_IDENTITY_FILES = (
    Path("services/auth-proxy/wrangler.toml"),
    Path("services/signup-relay/wrangler.toml"),
    Path("services/signup-relay/src/index.js"),
    Path("services/form-relay/src/index.js"),
    Path(".github/CODEOWNERS"),
)

#: Files that hold this instance's identity because something *generated*
#: them from the declaration. Not a second copy in the sense this module
#: refuses -- nothing here is authored, and
#: `scripts/generate_brand_css.py --check` fails the build the moment one
#: of them stops agreeing with `config/instance.json`. Checked below all
#: the same, rather than exempted: a generated file nobody compares is a
#: hand-written one with better manners.
_DERIVED_IDENTITY_FILES = (
    Path("docs/assets/announcement-template.svg"),
    Path("docs/assets/flyer-template.svg"),
)

#: Files that still name this organisation and are somebody else's task,
#: each with the phase that owns it. Not a general exemption: adding a
#: path here is a decision, and the reason is beside it.
#:
#: Phase 10 task 5 moved the list itself into `instance_identity.DEFERRED`
#: and left this reading of it. It is the same fact answering two
#: questions -- which *source* this module may forgive, and which phrases
#: task 5's sweep of a *built* second instance may find -- and two lists
#: would let a file be forgiven on one side while the other still refused
#: it. Each entry carries its own reason there, beside the path.
_IDENTITY_DEFERRED = {entry.path: entry.owner for entry in instance_identity.DEFERRED}

#: Test trees. A fixture naming this organisation is a fixture of *this*
#: instance, and the check that actually matters for behaviour is task 5's
#: build of a second instance and sweep of its output -- not the absence
#: of a string from a test double.
_IDENTITY_UNSWEPT_TREES = ("tools/tests/", "app/tests/", "services/")


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
        f"config/instance.json exists to make impossible: {offending}"
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

    These two files are what a collaborator downloads, so the identity
    travelling outward is whatever they say. They are generated from
    `config/instance.json` (phase 10, task 4) and
    `scripts/generate_brand_css.py --check` refuses them the moment they
    stop being what it derives -- this is the assertion that the
    derivation is of *this* declaration and not of a literal somebody
    typed and forgot.
    """
    identity = published.load_identity()
    for path in _DERIVED_IDENTITY_FILES:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert identity.forum_host in text, (
            f"{path.as_posix()} no longer names the forum this instance "
            f"declares ({identity.forum_host})"
        )
        assert identity.series.upper() in text, (
            f"{path.as_posix()} no longer names this series ({identity.series})"
        )


def test_the_literals_that_cannot_read_the_declaration_still_agree_with_it() -> None:
    """The exemption above, checked rather than merely granted -- the same
    discipline `test_the_relays_deploy_the_address_this_project_is_
    published_at` already holds for `ALLOWED_ORIGIN`.

    Each of these files is read by something that cannot reach
    `config/instance.json`: a Worker deploys from its own package, and
    GitHub reads `CODEOWNERS` verbatim before any code of this project's
    runs. So the copy has to exist. What must not happen is that it
    drifts, and a copy nothing compares is a copy that will.
    """
    identity = published.load_identity()
    owner, _, repository = identity.repository.partition("/")

    for path in (
        Path("services/signup-relay/src/index.js"),
        Path("services/form-relay/src/index.js"),
    ):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert identity.repository in text, (
            f"{path.as_posix()} no longer names the repository this cockpit "
            f"writes to ({identity.repository})"
        )

    codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert f"@{owner}/editorial-board" in codeowners, (
        ".github/CODEOWNERS names a team outside the organisation "
        f"config/instance.json declares ({owner}) -- every review request it "
        "makes would go to nobody"
    )
    assert repository, "the declared repository has no name half"


# ------------------------------------------------------------------ #
# 9 -- the prefix this instance numbers its editions under
# ------------------------------------------------------------------ #


def test_this_repository_declares_the_prefix_its_editions_are_numbered_under() -> None:
    """Phase 11, task 4. `validate.py` used to fix an edition code as
    `^MRG-\\d{1,4}$` -- the initials of *this* series, in the product's own
    validator -- and the one sweep that compares two instances could never
    catch it, because both instances were forced to write it.

    The two derived forms are asserted beside the value because they are
    what actually reaches a reader: the code the showcase prints and the
    poster sets, and the event id (D-19) that is in the address of every
    event page, in `keys/events/<id>.pub` and in a certificate's own
    verification link."""
    editions = published.load_edition_prefix()
    assert editions.code_prefix == f"{editions.value}-"
    assert editions.event_prefix == editions.code_prefix.lower()
    assert editions.describes(f"{editions.code_prefix}05")
    assert not editions.describes(f"{editions.event_prefix}05")
    assert not editions.describes(f"{editions.code_prefix}00000")


def test_the_declared_prefix_is_the_one_this_instances_editions_use() -> None:
    """The freeze, seen from the repository rather than from the
    validator: every edition this instance has assigned is numbered under
    the prefix it declares.

    That is what makes changing the declaration impossible in practice
    rather than merely discouraged -- an edition code is in a published
    address, on an issued certificate and in a key filename, so the day
    the two disagree the file is wrong, not the editions."""
    editions = published.load_edition_prefix()
    speakers = yaml.safe_load(
        (ROOT / "data" / "speakers.yml").read_text(encoding="utf-8")
    )
    assigned = [
        entry["edition_code"]
        for entry in speakers
        if isinstance(entry, dict) and entry.get("edition_code")
    ]
    assert assigned, "this instance has assigned no edition at all"
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
        ("ConvenerÉ", "other than ASCII capitals and digits"),
    ],
)
def test_a_prefix_that_reads_plausibly_and_is_wrong_is_refused_at_declaration(
    value: Any, expected: str
) -> None:
    """Each of these is a shape somebody would actually type, and each
    fails somewhere nobody would look.

    A lower-case prefix breaks the one identity D-19 rests on -- an event
    id *is* the edition code lower-cased -- so `Vw-1` and `MRG-1` would be
    two codes with one address, one `keys/events/mrg-1.pub` and one
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
    answer = _node_json(ROOT / "app" / "scripts" / "print-published.mjs", ROOT / "app")
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
    agree. `app/tests/edition-prefix.test.ts` reads this same fixture
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
