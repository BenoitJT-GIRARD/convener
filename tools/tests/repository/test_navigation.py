"""The demonstration is an instance, and this is what holds it.

The maintainer stated the rule this module exists for:

    if the demonstration does not have the same structure and the same way
    of navigating as a deployed instance, that is an incoherence.

It is not a thing a reading can hold. The demonstration and the instance
are the same templates, which is exactly why a divergence is easy to
introduce and invisible to review: one `{% if site.demo %}` around a link,
one page generated in one build and not the other, and the two have
different shapes while every file still looks right. So this builds both
and compares them.

Two clauses, and they refuse different things
=============================================
**One.** The showcase is built twice out of one tree -- once as the
product's own demonstration (`site/scripts/demonstration.cjs`, from one
environment variable) and once as an ordinary instance -- and the two must
carry the same pages, and on each page the same set of places a link goes
to. The one difference allowed is the demonstration's own flag,
`?demo=1`, on a link into the cockpit: that is what stops a visitor
following a link out of the demonstration and landing on a sign-in screen,
and it changes where a link *lands*, never where it *goes*. Anything else
is refused by name.

**Two.** A deployed instance has five surfaces: the showcase, the cockpit,
and the three islands mounted on public pages -- registration, certificate
verification and the post-event survey. All five have to be reachable from
the home page, by following links rather than by knowing an address; and
each of the four this build actually publishes has to come back to it.
Both halves were false when this was written: nothing on the showcase
linked to the verifier or to a survey, so two of the five existed and were
reachable only from an address printed on a certificate or sent in an
e-mail.

The fifth surface is the cockpit, which is a single-page application: what
this can see of it is that a link reaches it, and its own half of the
rule -- that it comes back -- is
`app/tests/components/back-to-the-showcase.test.tsx`, on the other side of
the language boundary and for the ordinary reason (D-14).

Why an island is found by its mount point
=========================================
`#registration-form`, `#verify-app` and `#survey-form` are the three
islands' own `MOUNT_ID`s (`app/src/islands/*/main.tsx`). A page carrying
one *is* that surface, whatever it is called and wherever it is published;
a page found by its path would only be that path. The event page's own
address is `/events/<id>/` (D-19) and the survey's is `/survey/<id>/`, and
neither is written here.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from typing import Final, NamedTuple
from urllib.parse import urlsplit

import demonstration_build
import pytest
from helpers import toolchain

from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()
SITE: Final = ROOT / "site"

#: Eleventy's own entry point, in the built tree's terms.
ELEVENTY: Final = Path("node_modules") / "@11ty" / "eleventy" / "cmd.cjs"

#: The environment variable `site/scripts/demonstration.cjs` reads, and the
#: query it puts on a link into the cockpit. Read out of that module rather
#: than spelled again here: a second spelling of either is a demonstration
#: build this sweep would silently compare with itself.
_DECLARATION: Final = (SITE / "scripts" / "demonstration.cjs").read_text(
    encoding="utf-8"
)


def _declared(name: str) -> str:
    found = re.search(rf"^const {name} = '([^']+)';$", _DECLARATION, re.MULTILINE)
    assert found is not None, (
        f"site/scripts/demonstration.cjs no longer declares {name}, so this "
        "sweep cannot tell a demonstration build from an ordinary one and "
        "would compare one of them with itself"
    )
    return found.group(1)


DEMO_ENV: Final = _declared("DEMO_ENV")
DEMO_QUERY: Final = _declared("DEMO_QUERY")


def test_both_sides_of_the_flag_spell_it_the_same_way() -> None:
    """The demonstration's build sets the variable in Python and the
    showcase's build reads it in Node. A build that set a name nothing
    read would publish a demonstration with no band on it and a sign-in
    screen behind every link into the cockpit -- green, and wrong."""
    assert demonstration_build.DEMO_ENV == DEMO_ENV


#: The three islands, by the mount point each one's own entry module
#: declares. `app/src/islands/<name>/main.tsx::MOUNT_ID`.
ISLANDS: Final = {
    "the registration form": "registration-form",
    "the certificate verifier": "verify-app",
    "the post-event survey": "survey-form",
}


class Page(NamedTuple):
    """One built page: where it is served, and where it points."""

    url: str
    html: str
    links: tuple[str, ...]


class _Links(HTMLParser):
    """Every `href` of every `<a>`, in order. The stdlib parser rather than
    a dependency: what is wanted is the anchors of a document this
    repository generated itself, not a tolerant reading of the web."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value is not None:
                self.found.append(value)


def _links(html: str) -> tuple[str, ...]:
    parser = _Links()
    parser.feed(html)
    return tuple(parser.found)


def _build(into: Path, *, demonstration: bool) -> dict[str, Page]:
    """The showcase, built into `into`, read back as pages by address.

    In this repository rather than in a scratch copy of it: what is being
    compared is the *shape* of the two builds, which is the product's and
    not any instance's, and building here is one second where laying out a
    second instance is a minute.
    """
    env = {k: v for k, v in os.environ.items() if k != DEMO_ENV}
    if demonstration:
        env[DEMO_ENV] = "1"
    result = subprocess.run(  # nosec B603
        ["node", str(SITE / ELEVENTY), f"--output={into.as_posix()}"],
        cwd=SITE,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        "the showcase would not build "
        f"{'as a demonstration' if demonstration else 'as an instance'}:\n"
        f"{result.stdout[-3000:]}\n{result.stderr[-3000:]}"
    )

    prefix = _prefix(into)
    pages: dict[str, Page] = {}
    for path in sorted(into.rglob("*.html")):
        served = path.relative_to(into).as_posix().removesuffix("index.html")
        html = path.read_text(encoding="utf-8")
        pages[f"{prefix}{served}"] = Page(f"{prefix}{served}", html, _links(html))
    assert len(pages) > 5, f"the build wrote {len(pages)} page(s), which is not a site"
    return pages


def _prefix(built: Path) -> str:
    """The path the showcase is served under, read off the build itself.

    The home page's own masthead links to it, so the build states its own
    prefix and nothing here has to read the declaration a second time.
    """
    home = (built / "index.html").read_text(encoding="utf-8")
    found = re.search(r'<link rel="stylesheet" href="([^"]*)style\.css">', home)
    assert found is not None, "the home page carries no stylesheet to read a prefix off"
    return found.group(1)


@pytest.fixture(scope="module")
def builds(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Page], ...]:
    """The showcase as a demonstration and as an instance, built once for
    this module."""
    if shutil.which("node") is None:
        toolchain.absent(
            "node is not on PATH, so the showcase cannot be built",
            "Install Node 22.",
            unrun="the demonstration and an instance were never compared",
        )
    if not (SITE / "node_modules").is_dir():
        toolchain.absent(
            "site/node_modules is missing",
            "Run `npm ci` in site/ before this suite.",
            unrun="the demonstration and an instance were never compared",
        )
    root = tmp_path_factory.mktemp("navigation")
    return (
        _build(root / "demonstration", demonstration=True),
        _build(root / "instance", demonstration=False),
    )


def _without_the_flag(href: str) -> str:
    """A link with the demonstration's own flag taken off it. The flag says
    which mode the *cockpit* opens in; it never says where a link goes, and
    it is the one difference between the two builds this sweep allows."""
    return href.replace(DEMO_QUERY, "") if href.endswith(DEMO_QUERY) else href


# ------------------------------------------------------------------ #
# 1 -- the demonstration and an instance are the same site
# ------------------------------------------------------------------ #


def test_both_builds_publish_the_same_pages(
    builds: tuple[dict[str, Page], ...],
) -> None:
    demonstration, instance = builds
    assert sorted(demonstration) == sorted(instance), (
        "the demonstration and an instance publish different pages. A "
        "demonstration is the same site built from the worked example, so "
        "a page in one and not the other is a page a visitor is shown that "
        "no instance has, or one an instance has that the demonstration "
        "never shows"
    )


def test_no_page_navigates_differently_in_the_two_builds(
    builds: tuple[dict[str, Page], ...],
) -> None:
    """The clause the whole module is for. Compared as a *set*, because
    what has to be the same is where a page can take you, not how many
    times it offers to: the demonstration's own band repeats the link to
    the cockpit the masthead beside it already carries, which is exactly
    what it is allowed to do and nothing more."""
    demonstration, instance = builds
    divergent: list[str] = []
    for url in sorted(set(demonstration) & set(instance)):
        theirs = {_without_the_flag(href) for href in demonstration[url].links}
        ours = set(instance[url].links)
        if theirs != ours:
            divergent.append(
                f"{url}: only in the demonstration {sorted(theirs - ours)}, "
                f"only in an instance {sorted(ours - theirs)}"
            )
    assert divergent == [], (
        "the demonstration navigates somewhere an instance does not, or the "
        "other way round:\n" + "\n".join(divergent)
    )


def test_the_comparison_is_of_two_builds_that_really_differ(
    builds: tuple[dict[str, Page], ...],
) -> None:
    """Two identical builds would satisfy everything above by saying
    nothing. The demonstration does differ -- it carries the flag on its
    links into the cockpit -- and that is what the flag is for."""
    demonstration, instance = builds
    flagged = [
        url
        for url, page in demonstration.items()
        if any(href.endswith(DEMO_QUERY) for href in page.links)
    ]
    assert len(flagged) == len(demonstration), (
        "a demonstration page carries no link into the demonstration's own "
        f"cockpit: {sorted(set(demonstration) - set(flagged))}"
    )
    assert not any(
        href.endswith(DEMO_QUERY) for page in instance.values() for href in page.links
    ), "an ordinary instance is publishing the demonstration's own flag"


# ------------------------------------------------------------------ #
# 2 -- the five surfaces, walked from the home page
# ------------------------------------------------------------------ #


def _home(pages: dict[str, Page]) -> str:
    """The showcase's own root. Every other page is published under it, so
    it is the shortest address the build wrote."""
    return min(pages, key=len)


def _walk(pages: dict[str, Page]) -> dict[str, Page]:
    """Every page reachable from the home page by following links.

    A walk rather than a lookup, and that is the whole of what this
    proves: a page nothing links to is a page a visitor never finds,
    however real its address is.
    """
    home = _home(pages)
    seen: dict[str, Page] = {}
    queue: deque[str] = deque([home])
    while queue:
        url = queue.popleft()
        if url in seen:
            continue
        page = pages.get(url)
        if page is None:
            continue  # a link out of the site, or into the cockpit's bundle
        seen[url] = page
        for href in page.links:
            target = urlsplit(_without_the_flag(href))
            if target.scheme or target.netloc or not target.path.startswith(home):
                continue
            queue.append(target.path)
    return seen


@pytest.mark.parametrize("which", [0, 1], ids=["demonstration", "instance"])
def test_every_surface_is_reachable_from_the_home_page(
    builds: tuple[dict[str, Page], ...], which: int
) -> None:
    """Reachable by *walking*, never by knowing the address. The verifier
    had a page and no link to it anywhere on this site, and so did every
    survey: both existed and neither could be found."""
    pages = builds[which]
    home = _home(pages)
    reached = _walk(pages)
    assert len(reached) > 3, "the walk from the home page found almost nothing"

    for surface, mount in ISLANDS.items():
        assert any(f'id="{mount}"' in page.html for page in reached.values()), (
            f"{surface} is not reachable from the home page by following "
            f"links: none of the {len(reached)} page(s) the walk reached "
            f"carries its own mount point (#{mount}). It has an address all "
            "the same, and a surface a visitor cannot find is a surface a "
            "visitor does not have"
        )

    cockpit = f"{home}app/"
    assert any(
        _without_the_flag(href) == cockpit
        for page in reached.values()
        for href in page.links
    ), (
        "the cockpit is not reachable from the home page. It is gated by "
        "sign-in, which is correct; being unreachable is not"
    )


@pytest.mark.parametrize("which", [0, 1], ids=["demonstration", "instance"])
def test_every_surface_comes_back_to_the_showcase(
    builds: tuple[dict[str, Page], ...], which: int
) -> None:
    """And back. A visitor who has followed a link to a form, a verifier or
    a survey must not have to use the browser's own history to return to
    the site they came from."""
    pages = builds[which]
    home = _home(pages)
    stranded: list[str] = []
    carriers = 0
    for url, page in sorted(pages.items()):
        if url == home:
            continue
        if not any(f'id="{mount}"' in page.html for mount in ISLANDS.values()):
            continue
        carriers += 1
        if home not in {urlsplit(href).path for href in page.links}:
            stranded.append(url)
    assert carriers >= len(ISLANDS), (
        f"only {carriers} page(s) of this build carry an island, and there "
        f"are {len(ISLANDS)} of them -- the sweep below would pass over the "
        "ones it could not find"
    )
    assert stranded == [], (
        "these pages carry one of the product's own islands and no link "
        f"back to the showcase: {stranded}"
    )
