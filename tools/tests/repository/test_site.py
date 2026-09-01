"""The showcase's templates, which live in this repository.

`example-showcase` used to hold `index.njk`, `layout.njk`, `style.css`,
`.eleventy.js`, `package.json` and the self-hosted fonts directly -- source
outside this repository's own quality chain, tests and decision record (D-15:
private source, public artefact). They now live under `site/`, and this module
is the quality chain's own hold on the one guarantee a reconstruction already
broke once: no request to a third party from a published page (D-17).

Most of this module is text assertions on the templates and stylesheet
themselves, never a build. The event-page section further down is the one
exception: it needs the real, *rendered* event pages to prove that no room
link reaches any public page, so it builds `site/` itself
into a scratch directory -- see `built_site`'s own docstring for why, and
for why that still touches no network (`site/`'s own `node_modules` must
already be installed, exactly the `npm ci` every other job that touches
`site/` already runs).
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import pytest
from helpers import instance_identity
from helpers.ics_reader import parse_calendar

from convener_ops.declaration import published
from convener_ops.declaration.paths import repo_root
from convener_ops.journey.certificate import VERIFICATION_BASE
from convener_ops.journey.confirmation import CONTACT_EMAIL
from convener_ops.journey.registration import SIGNUP_BASE, signup_url
from convener_ops.publication.formats import BANNER
from convener_ops.publication.public_data import PUBLISHABLE_ALWAYS

#: The same zone `tools/convener_ops/governance/rule.py::PARIS` already
#: anchors this project's Python side on -- `zoneinfo`, the standard
#: library's own IANA tzdata, rather than `site/.eleventy.js`'s `Intl`
#: reimplemented here, so this test suite proves the build against an
#: independent computation of the real Europe/Paris offset, not a second
#: copy of the same arithmetic that could carry the same mistake.
_PARIS = ZoneInfo("Europe/Paris")

#: Strips CSS/JS block comments (`/* ... */`), Nunjucks comments (`{# ... #}`)
#: and HTML comments (`<!-- ... -->`), in that order, DOTALL so a comment
#: spanning several lines is removed whole. `.eleventy.js`'s own comment
#: explaining *why* fonts are self-hosted, and style.css's identical one,
#: both name the forbidden hosts by way of explanation -- scanning raw text
#: would flag the very comments D-17 asks for as if they were the violation.
_COMMENT_RE = re.compile(r"/\*.*?\*/|\{#.*?#\}|<!--.*?-->", re.DOTALL)


def _without_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text)


ROOT = repo_root()
SITE_SRC = ROOT / "site" / "src"


def _configured_path_prefix() -> str:
    """This project's published path prefix -- GitHub Pages serves the
    build one path segment below a bare domain root (no CNAME, no custom
    domain), and that segment feeds every template's `| url` filter call.

    This used to scrape `PATH_PREFIX` out of
    `site/.eleventy.js` with a regular expression, because that file was
    where the value lived. It now lives in `instance/config.json`, which
    `.eleventy.js` reads for itself, so this reads the declaration
    directly rather than the source of another reader of it. That the two
    actually agree -- that the *build* resolves the same prefix this
    module asserts against -- is `test_published.py`'s own job, and it
    checks it by running the real configuration, not by reading it.
    """
    return published.load().path_prefix


def _pfx(path: str) -> str:
    """`path`, prefixed exactly the way Eleventy's own `url` filter prefixes
    every root-relative link this project's templates emit -- see
    `_configured_path_prefix`'s own docstring. `path` must itself start
    with `/`, the same contract every template's own `| url` filter call
    assumes."""
    assert path.startswith("/"), f"{path!r} is not root-relative"
    return _configured_path_prefix().rstrip("/") + path


def _configured_site_origin() -> str:
    """The origin half of the same declaration -- the absolute-URL
    counterpart to `_configured_path_prefix` above, and read the same way
    and for the same reason. The two cannot disagree about which
    deployment they describe, because they are two properties of one
    value rather than two values.
    """
    return published.load().origin


def _absolute(path: str) -> str:
    """`path`, made absolute exactly the way `site/.eleventy.js`'s own
    `absoluteUrl` filter makes it: this project's real published host, plus
    the same prefixing `_pfx` above already performs. `path` must itself
    start with `/`, the same contract `absoluteUrl`'s own template call
    sites assume."""
    return f"{_configured_site_origin()}{_pfx(path)}"


#: Every text file a page actually ships: templates and the stylesheet. Fonts
#: (`.woff2`) are binary; licence files are third-party text nobody here
#: authored, so scanning them for our own supposed third-party requests would
#: be nonsensical, not just noisy.
_TEXT_GLOBS = ("**/*.njk", "**/*.css", "**/*.js")

#: D-17: the showcase used to load Archivo and JetBrains Mono from Google,
#: which discloses every visitor's address to a third party. Both hostnames
#: are named, not only `googleapis.com`: a stylesheet link alone should
#: resolve to `fonts.googleapis.com`, but the font files themselves are
#: actually served from `fonts.gstatic.com`, and a reconstruction that only
#: dropped the first would still leak on the second.
_FORBIDDEN_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")


def _site_text_files() -> list[Path]:
    found: list[Path] = []
    for pattern in _TEXT_GLOBS:
        found.extend(SITE_SRC.glob(pattern))
    assert found, (
        f"no template or stylesheet found under {SITE_SRC.as_posix()} -- "
        "the glob itself may be wrong, which would silently pass this test "
        "on an empty scan"
    )
    return found


def test_no_page_requests_a_third_party_font_host() -> None:
    offending = []
    for path in _site_text_files():
        text = _without_comments(path.read_text(encoding="utf-8"))
        for host in _FORBIDDEN_HOSTS:
            if host in text:
                offending.append((path.relative_to(ROOT).as_posix(), host))
    assert offending == [], (
        f"third-party font host(s) reintroduced: {offending} -- D-17 requires "
        "self-hosted fonts precisely because a webfont request discloses "
        "every visitor's address to that host"
    )


def test_layout_preloads_a_self_hosted_font() -> None:
    """The negative check above passes on a layout that dropped fonts
    altogether just as readily as on one that self-hosts them properly --
    this is the positive half: the font actually served from `/fonts/`."""
    layout = (SITE_SRC / "_includes" / "layout.njk").read_text(encoding="utf-8")
    # `href="/fonts/..."` moved behind Eleventy's `| url`
    # filter (`href="{{ '/fonts/...' | url }}"`) so the preload resolves
    # under this project's real published prefix rather than a bare
    # domain root -- see `_configured_path_prefix`'s own docstring.
    assert "'/fonts/" in layout, (
        "layout.njk no longer preloads a font from /fonts/ -- either the "
        "self-hosting was dropped, or the page ships no display font at all"
    )


def test_style_sheet_declares_the_self_hosted_font_faces() -> None:
    style = (SITE_SRC / "style.css").read_text(encoding="utf-8")
    assert "@font-face" in style, (
        "style.css carries no @font-face block -- Archivo and JetBrains "
        "Mono would fall back to the system font, silently"
    )
    assert "Archivo" in style and "JetBrains Mono" in style, (
        "style.css's @font-face block no longer names Archivo or JetBrains "
        "Mono -- D-17's chosen substitutes for the designer's own "
        "commercially licensed faces"
    )


# -------------------------------------------------------------------------- #
# A Content-Security-Policy and an
# explicit referrer policy, both delivered by <meta> -- the only mechanism
# available at all, since GitHub Pages sets no response headers. `built_site`
# (below) is built with no VITE_SIGNUP_RELAY_URL set,
# so it also stands in for that variable's ordinary D-13 absence;
# `built_site_with_signup_relay` proves the other half -- the relay's own
# origin joining connect-src when the variable is configured, the identical
# one deploy.yml already forwards into the application build.
# -------------------------------------------------------------------------- #

#: `frame-ancestors`, `report-uri`/`report-to` and `sandbox` are directives
#: the CSP specification itself says a `<meta http-equiv>` delivery MUST
#: ignore -- carrying one here would not be wrong exactly, it would be
#: decorative: it reads as protection and does nothing. Closing the class,
#: not just today's instance: this fails the moment any of these three
#: tokens appears in the policy this project ships, regardless of which
#: directive introduces it or why.
_META_IGNORED_CSP_DIRECTIVES = ("frame-ancestors", "report-uri", "report-to", "sandbox")

#: Every directive this showcase's policy must name, and the sources each
#: one may admit. This policy used to name
#: `script-src`, `connect-src`, `object-src` and `form-action` and nothing
#: else, on the reasoning, written in `csp.js`'s own header, that those
#: four "work by `<meta>`". They do; so do these. The specification says a
#: `<meta>` delivery ignores exactly `frame-ancestors`, `report-uri` and
#: `sandbox` (see `_META_IGNORED_CSP_DIRECTIVES` below), so the omission
#: had no reason behind it at all, and its cost was that an image, a
#: frame, a font, a stylesheet, a media file or a worker was admitted from
#: any origin whatever. `default-src 'none'` is what closes the classes
#: nobody enumerated; the four `'self'` entries are what this build
#: actually loads (one stylesheet, three woff2 faces, three island
#: bundles, and the favicon a browser asks for by itself); `base-uri`
#: falls back to nothing, so it is named rather than left out.
#: `connect-src` is deliberately absent here: its value depends on
#: whether a relay is configured, and the two tests that own that
#: question are directly above and below.
_CSP_EXPECTED_SOURCES = {
    "default-src": "'none'",
    "script-src": "'self'",
    "style-src": "'self'",
    "img-src": "'self'",
    "font-src": "'self'",
    "base-uri": "'none'",
    "object-src": "'none'",
    "form-action": "'self'",
}

_CSP_META_RE = re.compile(
    r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">'
)
_REFERRER_META_RE = re.compile(r'<meta name="referrer" content="([^"]*)">')


def test_every_page_carries_the_content_security_policy_this_project_ships(
    built_site: Path,
) -> None:
    """Every built page -- not only the home page -- carries the one CSP
    `layout.njk` emits (`site/src/_data/csp.js`): `script-src 'self'`
    (this project's pages ship no inline script at all --
    `test_archive_pages_carry_no_script_tag_at_all` already holds the
    archive pages to that, and this is the same guarantee generalised),
    `object-src 'none'` (no plugin embed anywhere), `form-action 'self'`
    (no page under `site/` submits a form) and `connect-src 'self'` with
    no relay origin appended -- this fixture is built with
    `VITE_SIGNUP_RELAY_URL` unset, D-13's ordinary state.

    And the five directives whose absence nobody had
    examined for a long time. This policy once named four source lists and no
    fallback, so an image, a frame, a font, a stylesheet or a media file
    was admitted from *any origin at all* -- on every page a stranger
    loads, including the three that carry an island handling somebody's
    registration, certificate lookup or survey answer. See
    `_CSP_EXPECTED_SOURCES` for what each one is justified by.
    """
    checked = 0
    for path in built_site.rglob("*.html"):
        page = path.read_text(encoding="utf-8")
        match = _CSP_META_RE.search(page)
        assert match is not None, (
            f"{path.relative_to(built_site).as_posix()} carries no "
            "Content-Security-Policy <meta> tag"
        )
        content = match.group(1).replace("&#39;", "'")
        assert "script-src 'self'" in content, path
        assert "object-src 'none'" in content, path
        assert "form-action 'self'" in content, path
        assert "connect-src 'self'" in content, path
        emitted: dict[str, str] = {}
        for part in content.split("; "):
            name, _, sources = part.partition(" ")
            emitted[name] = sources
        assert emitted.keys() >= _CSP_EXPECTED_SOURCES.keys(), (
            f"{path.relative_to(built_site).as_posix()}'s CSP names "
            f"{sorted(emitted)}, and leaves "
            f"{sorted(_CSP_EXPECTED_SOURCES.keys() - emitted.keys())} to "
            "the browser's own default, which is to allow it from anywhere"
        )
        for directive, sources in _CSP_EXPECTED_SOURCES.items():
            assert emitted[directive] == sources, (
                f"{path.relative_to(built_site).as_posix()}'s CSP admits "
                f"{directive} from {emitted[directive]!r} rather than "
                f"{sources!r}"
            )
        assert "workers.dev" not in content, (
            f"{path.relative_to(built_site).as_posix()} names a relay "
            "origin though VITE_SIGNUP_RELAY_URL was never set for this "
            "build -- csp.js's own D-13 absence handling regressed"
        )
        checked += 1
    assert checked > 0, "no built page was found to check the CSP against"


def test_content_security_policy_never_carries_a_directive_meta_delivery_ignores(
    built_site: Path,
) -> None:
    for path in built_site.rglob("*.html"):
        page = path.read_text(encoding="utf-8")
        match = _CSP_META_RE.search(page)
        if match is None:
            continue
        content = match.group(1)
        for directive in _META_IGNORED_CSP_DIRECTIVES:
            assert directive not in content, (
                f"{path.relative_to(built_site).as_posix()}'s CSP names "
                f"{directive!r}, which a <meta> delivery ignores outright -- "
                "this reads as protection and does nothing; remove it "
                "rather than ship a decorative directive"
            )


def test_every_page_carries_an_explicit_referrer_policy(built_site: Path) -> None:
    checked = 0
    for path in built_site.rglob("*.html"):
        page = path.read_text(encoding="utf-8")
        match = _REFERRER_META_RE.search(page)
        assert match is not None, (
            f"{path.relative_to(built_site).as_posix()} sets no explicit "
            "referrer policy"
        )
        assert match.group(1) == "strict-origin-when-cross-origin", path
        checked += 1
    assert checked > 0, "no built page was found to check the referrer policy against"


@pytest.fixture(scope="module")
def built_site_with_signup_relay(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The real `site/` project, built exactly like `built_site` above but
    with `VITE_SIGNUP_RELAY_URL` set -- the configured state `deploy.yml`
    forwards into the application build and `publish-showcase.yml`'s own
    "Build site" step now forwards here too. Proves the other half of
    `csp.js`'s own D-13 handling: an address actually appears in
    connect-src once one is actually configured, not just that its
    absence is handled."""
    if not _ELEVENTY_CMD.exists():
        pytest.skip(
            f"{_ELEVENTY_CMD.as_posix()} not found -- run `npm ci` in site/ "
            "before this suite (quality.yml's own python job now does)"
        )
    out = tmp_path_factory.mktemp("site-build-signup-relay")
    try:
        subprocess.run(
            ["node", str(_ELEVENTY_CMD), f"--output={out.as_posix()}"],
            cwd=ROOT / "site",
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **os.environ,
                "VITE_SIGNUP_RELAY_URL": "https://convener-signup-relay.example.workers.dev",
            },
        )
    except FileNotFoundError:
        pytest.skip("node is not on PATH -- cannot build site/ for this suite")
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"site/ failed to build: {exc.stdout}\n{exc.stderr}"
        ) from exc
    return out


def test_content_security_policys_connect_src_admits_the_configured_signup_relay(
    built_site_with_signup_relay: Path,
) -> None:
    event = built_site_with_signup_relay / "events" / "mrg-05" / "index.html"
    page = event.read_text(encoding="utf-8")
    match = _CSP_META_RE.search(page)
    assert match is not None
    content = match.group(1).replace("&#39;", "'")
    assert (
        "connect-src 'self' https://convener-signup-relay.example.workers.dev"
        in content
    ), (
        "the registration island posts straight to the configured signup "
        "relay from this document -- connect-src must admit it or a real "
        "registration would be blocked by this project's own policy"
    )


def test_the_survey_pages_connect_src_also_admits_the_configured_signup_relay(
    built_site_with_signup_relay: Path,
) -> None:
    """The survey island posts to the identical relay's
    own `/survey` route (`SurveyForm.tsx::surveyRelayUrl`), from a
    *different* document (`survey.njk`, not `event.njk`) -- this pin is
    the equivalent proof for that page, not merely an inference from the
    event page's own test above."""
    event_id = _the_one_scheduled_event_id()
    page = (
        built_site_with_signup_relay / "survey" / event_id / "index.html"
    ).read_text(encoding="utf-8")
    match = _CSP_META_RE.search(page)
    assert match is not None
    content = match.group(1).replace("&#39;", "'")
    assert (
        "connect-src 'self' https://convener-signup-relay.example.workers.dev"
        in content
    ), (
        "the survey island posts straight to the configured signup relay "
        "from this document -- connect-src must admit it or a real survey "
        "response would be blocked by this project's own policy"
    )


# -------------------------------------------------------------------------- #
# The event page -- one addressable page per edition (D-19), no
# room link on any public page, and the data-protection
# notice ahead of the reserved place for the registration island.
#
# The address and no-room-link checks below build the real `site/` project
# with its own committed fixture (`src/_data/events.json`) and sweep the
# *built* output, deliberately, rather than reading `event.njk`'s source
# the way the tests above read `layout.njk`'s and `style.css`'s: the
# template's own vocabulary never names the room link `zoom_link` -- the
# internal field a source scan for that literal (the technique
# `test_confirmation.py::test_no_public_announcement_template_publishes_
# the_room_link` already uses for the toolkit's Markdown templates) would
# have to look for -- so such a scan would stay green even with a leak.
# (`public_data.py::PUBLIC_FIELD_SOURCES` used to publish it as
# `registration_link`, and publishes it under no name at
# all now, which makes this template-layer guard the only proof left that a
# future regression cannot slip a room-link-shaped value back onto a
# page.) Only the rendered page shows what a visitor would actually see.
# -------------------------------------------------------------------------- #

_EVENT_TEMPLATE = SITE_SRC / "event.njk"
_EVENTS_FIXTURE = SITE_SRC / "_data" / "events.json"
_ELEVENTY_CMD = ROOT / "site" / "node_modules" / "@11ty" / "eleventy" / "cmd.cjs"


def _events_fixture() -> list[dict[str, Any]]:
    data = json.loads(_EVENTS_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data, (
        f"{_EVENTS_FIXTURE.as_posix()} is empty -- nothing for the tests "
        "below to check the build against"
    )
    return data


@pytest.fixture(scope="module")
def built_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The real `site/` project, built once per test module from its own
    committed source and fixture data, into a scratch directory rather
    than the gitignored `site/_site` a developer's own `npm run build`
    may already have open in a browser.

    Invokes the already-installed Eleventy CLI directly by its own entry
    script (`node cmd.cjs`), never `npm run build` or `npx`: no shell, no
    `.cmd` wrapper to resolve (the same reason `deliver`'s own transport
    never shells out), and no network access of any kind -- `site/`'s own
    `node_modules` must already exist (`npm ci`, the same install every
    other job in this pipeline that touches `site/` already runs; the
    `python` job in `quality.yml` now runs it too, for exactly this
    fixture).
    """
    if not _ELEVENTY_CMD.exists():
        pytest.skip(
            f"{_ELEVENTY_CMD.as_posix()} not found -- run `npm ci` in site/ "
            "before this suite (quality.yml's own python job now does)"
        )
    out = tmp_path_factory.mktemp("site-build")
    try:
        subprocess.run(
            # `--output={out.as_posix()}`, not a bare `{out}`: on Windows,
            # `str(Path)` is backslash-separated, and Eleventy's own
            # passthrough-copy containment check ("Destination is not in
            # the site output directory") compares that argument against
            # forward-slash-normalised internal paths byte-for-byte --
            # verified by reproducing the failure with a backslash path
            # and watching it disappear with `.as_posix()` and nothing
            # else changed. `site/`'s own `npm run build` never hits this,
            # because its `--output=_site` is already a bare relative
            # name with no separator to disagree about.
            ["node", str(_ELEVENTY_CMD), f"--output={out.as_posix()}"],
            cwd=ROOT / "site",
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        pytest.skip("node is not on PATH -- cannot build site/ for this suite")
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"site/ failed to build: {exc.stdout}\n{exc.stderr}"
        ) from exc
    return out


def test_every_event_has_exactly_one_page_addressed_by_its_lower_cased_edition_code(
    built_site: Path,
) -> None:
    """D-19: `event_id` IS `edition_code`, lower-cased -- nothing else
    names an event, and in particular never the title, which an editor
    can reword at any time without moving the address a QR code or a
    shared link already points at.

    Checked against the actual output paths, not the permalink
    expression in `event.njk`'s front matter: a permalink that silently
    slugified the title instead would still read as plausible template
    source while producing entirely different addresses -- and this
    fixture's own `MRG-01` and `MRG-02` already share one title, so a
    title-derived address would collide the two into a single page,
    which this exact-set comparison catches as a missing page, not just
    a wrong one.
    """
    events = _events_fixture()
    expected = {f"events/{str(event['id']).lower()}/index.html" for event in events}
    actual = {
        path.relative_to(built_site).as_posix()
        for path in built_site.glob("events/*/index.html")
    }
    assert actual == expected


def test_a_built_public_page_never_carries_a_room_link(built_site: Path) -> None:
    """Absolute: no room link on any public page
    -- the room link is delivered only by the confirmation e-mail. Swept
    across every file the build wrote, not only the event page's own
    output: the claim is about *any* public page, and a leak from, say,
    the homepage's "up next" card would be exactly as real a breach.

    Sweeps for the literal, non-empty `registration_link` value(s) the
    committed *fixture* carries -- a synthetic room-link-shaped column,
    kept here as a template-regression canary even though `public_data.py`
    no longer emits any column carrying a room link (that mapping used to
    publish `zoom_link` under this same column name).
    This test does not depend on the generator: it proves the template
    still refuses to render a room-link-shaped value if one ever reached
    the page's own data again, under whatever name.

    Also strips RFC 5545 line folding ("\\r\\n "
    inserted every 75 octets, `agenda.ics`'s own format) before searching.
    A leaked link is folded exactly like any other long property value, so
    the literal, unfolded string this test searches for can straddle a
    fold point and never appear contiguously in the raw file even though it
    reached the published output -- confirmed by deliberately routing
    `LOCATION` through the fixture's own `registration_link` in
    `site/.eleventy.js::agendaVevent` and watching this sweep miss it until
    this line was added. Inert for every other file this build writes
    (HTML, XML, CSS): none of them ever folds a line this way, so stripping
    a sequence they do not contain changes nothing about how they are
    checked.
    """
    events = _events_fixture()
    room_links = [
        str(event["registration_link"])
        for event in events
        if event.get("registration_link")
    ]
    assert room_links, (
        f"{_EVENTS_FIXTURE.as_posix()} carries no non-empty registration_link "
        "-- nothing for this test to prove is kept off every page"
    )
    offending: list[tuple[str, str]] = []
    for path in built_site.rglob("*"):
        if not path.is_file():
            continue
        try:
            # `read_bytes().decode(...)`, not `read_text(...)`: the latter
            # opens in text mode with universal-newline translation on by
            # default, which silently rewrites every "\r\n" to "\n" before
            # this function ever sees the string -- so a search for the
            # literal "\r\n " fold-continuation marker below would never
            # match anything, on any file, and would look like it worked
            # only because it was vacuously true. Confirmed by watching
            # this exact difference make the fold-strip below a no-op.
            text = path.read_bytes().decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            continue  # a font or another binary passthrough copy
        unfolded = text.replace("\r\n ", "")
        for link in room_links:
            if link in text or link in unfolded:
                offending.append((path.relative_to(built_site).as_posix(), link))
    assert offending == [], f"room link leaked into the built site: {offending}"


def test_a_built_html_page_never_mentions_the_internal_field_name_either(
    built_site: Path,
) -> None:
    """Belt and braces beside the value-based sweep above: even the
    *name* `zoom_link` -- the speaker record's own internal field, which
    `public_data.py` never maps to any published column -- must
    never appear on a built page, which would mean some future template
    reached past the private/public boundary and read the record
    directly.
    """
    offending = []
    for path in built_site.rglob("*.html"):
        if "zoom_link" in path.read_text(encoding="utf-8"):
            offending.append(path.relative_to(built_site).as_posix())
    assert offending == [], f"zoom_link named on a built page: {offending}"


def _the_one_scheduled_event_id() -> str:
    scheduled = [e for e in _events_fixture() if e.get("status") == "scheduled"]
    assert scheduled, (
        f"{_EVENTS_FIXTURE.as_posix()} carries no 'scheduled' event -- "
        "nothing for the notice/placeholder ordering test below to check"
    )
    return str(scheduled[0]["id"]).lower()


def test_the_notice_precedes_the_reserved_place_for_the_registration_form(
    built_site: Path,
) -> None:
    """A one-screen data-protection notice on the event
    page, *before* the form. The registration island
    (`app/src/islands/signup/`) mounts beneath it; this test pins the
    ordering promise, which mounting the island above the notice would
    quietly invert.
    """
    event_id = _the_one_scheduled_event_id()
    page = (built_site / "events" / event_id / "index.html").read_text(encoding="utf-8")
    notice_at = page.index("Before you register")
    placeholder_at = page.index('id="registration-form"')
    assert notice_at < placeholder_at


# -------------------------------------------------------------------------- #
# The post-event survey's own static page
# (`site/src/survey.njk`), one per event (D-19) -- the same per-event
# addressing `event.njk` already uses for registration, mirrored here
# because both pages agree on what "this event" means.
# -------------------------------------------------------------------------- #


def test_every_event_has_one_survey_page_addressed_by_its_lower_cased_edition_code(
    built_site: Path,
) -> None:
    """The identical D-19 guarantee
    `test_every_event_has_exactly_one_page_addressed_by_its_lower_cased_
    edition_code` proves for `event.njk`, proved here for `survey.njk`:
    checked against the actual output paths, not the permalink expression
    in the template's own front matter."""
    events = _events_fixture()
    expected = {f"survey/{str(event['id']).lower()}/index.html" for event in events}
    actual = {
        path.relative_to(built_site).as_posix()
        for path in built_site.glob("survey/*/index.html")
    }
    assert actual == expected


def test_the_survey_notice_precedes_the_reserved_place_for_the_survey_form(
    built_site: Path,
) -> None:
    """The identical "notice before the form" ordering
    `test_the_notice_precedes_the_reserved_place_for_the_registration_
    form` already pins for registration -- `survey.njk` reserves this
    page's own place for `app/src/islands/survey/`'s mount point beneath
    its static notice, never above it.
    """
    event_id = _the_one_scheduled_event_id()
    page = (built_site / "survey" / event_id / "index.html").read_text(encoding="utf-8")
    notice_at = page.index("Before you answer")
    placeholder_at = page.index('id="survey-form"')
    assert notice_at < placeholder_at


def test_the_survey_pages_notice_states_anonymity_retention_and_a_real_contact_address(
    built_site: Path,
) -> None:
    """The static half of the notice `SurveyForm.tsx::Notice` used to
    render before it moved -- carried into `survey.njk` unchanged, so every
    claim a review already earned (the anonymity wording,
    the 90-day retention figure tied to the event's own key) still reads
    even with JavaScript disabled, and even before the island's own
    fetches ever run."""
    event_id = _the_one_scheduled_event_id()
    page = (built_site / "survey" / event_id / "index.html").read_text(encoding="utf-8")
    # Normalised, the same idiom `_normalised_docs_template` uses in
    # `test_survey_invite.py`: the source template wraps this prose across
    # several lines, so a literal multi-word phrase can straddle a
    # newline in the raw HTML even though it reads as one sentence to a
    # visitor's own browser, which collapses that whitespace itself.
    normalised = " ".join(page.split())
    assert "recorded as present" in normalised.lower()
    assert "anonymous" in normalised.lower()
    assert "cannot find your own answers" in normalised
    assert "destroyed together with the event" in normalised
    assert "90 days after the event" in normalised
    assert published.load_identity().contact in normalised


def test_a_survey_page_carries_the_noscript_fallback_and_the_island_script(
    built_site: Path,
) -> None:
    """The identical D-18 discipline `event.njk` and `verify.njk` already
    hold themselves to: an empty mount point renders nothing without
    JavaScript, so a `<noscript>` fallback must exist beside it, and the
    island's own bundle must actually be loaded."""
    event_id = _the_one_scheduled_event_id()
    page = (built_site / "survey" / event_id / "index.html").read_text(encoding="utf-8")
    assert "<noscript>" in page
    assert 'id="survey-form"' in page
    assert "/app/islands/survey/survey.js" in page


def _a_past_event_id() -> str:
    past = [e for e in _events_fixture() if e.get("status") != "scheduled"]
    assert past, (
        f"{_EVENTS_FIXTURE.as_posix()} carries no past event -- nothing for "
        "the section-ordering test below to check"
    )
    return str(past[0]["id"]).lower()


def test_an_upcoming_event_page_leads_with_registration_and_drops_the_recording_section(
    built_site: Path,
) -> None:
    """A visitor to an upcoming edition's page came to
    register, not to be told twice (once by "Upcoming" in the rail, once
    by "No recording yet"/"No thread yet" here) that the seminar has not
    happened. Registration is band 01, and the recording section -- which
    can carry nothing real yet, since `youtube_url` is only ever published
    once an edition reaches `archived`
    (`public_data.py::RECORDING_STATUSES`) -- is dropped rather than kept
    as a later, empty band. Mutating `event.njk` to render the recording
    section unconditionally, ahead of registration, the way it read before
    this fix, fails this test on the `"Recording &amp; discussion"` and
    `section__num` assertions below.
    """
    event_id = _the_one_scheduled_event_id()
    page = (built_site / "events" / event_id / "index.html").read_text(encoding="utf-8")
    assert "Recording &amp; discussion" not in page, (
        "an upcoming edition's page still carries the recording section -- "
        "it should be dropped entirely, not just reordered"
    )
    assert "No recording yet" not in page
    assert "No thread yet" not in page
    register_at = page.index('<span class="section__label">Register</span>')
    band_at = page.rindex('<span class="section__num">01</span>', 0, register_at)
    assert band_at < register_at, "band 01 no longer immediately precedes Register"


def test_a_past_event_page_still_leads_with_the_recording_section(
    built_site: Path,
) -> None:
    """The other half of the same fix: a past edition has no form, and the
    recording (or its absence) is the one thing a visitor came for -- this
    pins that this ordering is unchanged (band 01, and no "Register"
    section appears at all on a page with nothing to register for)."""
    event_id = _a_past_event_id()
    page = (built_site / "events" / event_id / "index.html").read_text(encoding="utf-8")
    assert "Register" not in page, (
        "a past edition's page carries a Register section -- there is no "
        "form to register for once an edition has happened"
    )
    recording_at = page.index(
        '<span class="section__label">Recording &amp; discussion</span>'
    )
    band_at = page.rindex('<span class="section__num">01</span>', 0, recording_at)
    assert band_at < recording_at, (
        "band 01 no longer immediately precedes Recording & discussion"
    )


# -------------------------------------------------------------------------- #
# `forum_thread` carries no status gate at all
# (`public_data.py::PUBLISHABLE_ALWAYS`, no companion to
# `RECORDING_STATUSES`), unlike `youtube_url` -- an operator can open a
# discussion thread ahead of the seminar, and an earlier design dropped the only
# place an upcoming page could ever show it. The committed fixture's one
# `scheduled` event carries no `forum_thread` (that gap is exactly why the
# regression shipped), so the "with a thread" case below builds from a
# scratch copy of `site/src` with that field filled in, rather than from
# `built_site` -- the committed fixture is left untouched.
# -------------------------------------------------------------------------- #

#: Not a real forum: only ever read back out of the scratch build below.
#: On a reserved domain (RFC 2606) rather than this instance's own, so
#: that a fixture nobody resolves cannot be mistaken for a live thread.
_FIXTURE_ONLY_THREAD_URL = "https://forum.example.test/t/mrg-05-fixture-only-thread/999"


@pytest.fixture(scope="module")
def built_site_with_upcoming_forum_thread(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    """The same build `built_site` produces, from a copied `src/` tree with
    the one `scheduled` event's `forum_thread` filled in -- proves the
    "upcoming edition, real thread" case without committing that
    combination to `_EVENTS_FIXTURE`, which today has no upcoming edition
    carrying one at all.

    Copies `site/src` wholesale (small: two templates, one include, one
    stylesheet, `_data/`, `.nojekyll`) rather than pointing Eleventy at the
    real one with an in-memory patch: `--input` accepts any directory, and
    a scratch copy is the only way to change what `_data/events.json`
    carries without writing through the committed file. `cwd` stays
    `ROOT / "site"` so `.eleventy.js`'s own passthrough-copy paths
    ('src/style.css', '../fonts') keep resolving against the real
    project, exactly as they do for `built_site`.
    """
    if not _ELEVENTY_CMD.exists():
        pytest.skip(
            f"{_ELEVENTY_CMD.as_posix()} not found -- run `npm ci` in site/ "
            "before this suite (quality.yml's own python job now does)"
        )
    scratch_src = tmp_path_factory.mktemp("site-src-with-thread") / "src"
    shutil.copytree(SITE_SRC, scratch_src)
    events_path = scratch_src / "_data" / "events.json"
    events = json.loads(events_path.read_text(encoding="utf-8"))
    patched = False
    for event in events:
        if event.get("status") == "scheduled":
            event["forum_thread"] = _FIXTURE_ONLY_THREAD_URL
            patched = True
    assert patched, (
        f"{_EVENTS_FIXTURE.as_posix()} carries no 'scheduled' event to patch "
        "-- nothing for this fixture to prove the 'real thread' case against"
    )
    events_path.write_text(json.dumps(events), encoding="utf-8")
    out = tmp_path_factory.mktemp("site-build-with-thread")
    try:
        subprocess.run(
            [
                "node",
                str(_ELEVENTY_CMD),
                f"--input={scratch_src.as_posix()}",
                f"--output={out.as_posix()}",
            ],
            cwd=ROOT / "site",
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        pytest.skip("node is not on PATH -- cannot build site/ for this suite")
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"site/ failed to build: {exc.stdout}\n{exc.stderr}"
        ) from exc
    return out


def test_an_upcoming_event_page_shows_no_discuss_link_without_a_thread(
    built_site: Path,
) -> None:
    """The committed fixture's one `scheduled` event carries no
    `forum_thread` -- nothing should render for it: no live link, and, by
    the rule against a returning "No thread yet", no
    empty-state placeholder in its place either."""
    event_id = _the_one_scheduled_event_id()
    page = (built_site / "events" / event_id / "index.html").read_text(encoding="utf-8")
    assert ">Discuss<" not in page, (
        "a discuss link rendered on an upcoming page with no forum_thread set"
    )
    assert "No thread yet" not in page, (
        "the empty-state placeholder this fix must not bring back is back"
    )


def test_an_upcoming_event_page_shows_the_discuss_link_when_a_thread_is_set(
    built_site_with_upcoming_forum_thread: Path,
) -> None:
    """The other half: once `forum_thread` is set on a `scheduled` event
    (`built_site_with_upcoming_forum_thread`, since the committed fixture
    never carries this combination), the link must actually appear --
    attached to the registration section, after it rather than ahead of
    it, and without resurrecting the recording section that was dropped.
    """
    event_id = _the_one_scheduled_event_id()
    page = (
        built_site_with_upcoming_forum_thread / "events" / event_id / "index.html"
    ).read_text(encoding="utf-8")
    assert f'href="{_FIXTURE_ONLY_THREAD_URL}"' in page, (
        "the thread link never rendered on an upcoming page that has one"
    )
    register_at = page.index('<span class="section__label">Register</span>')
    discuss_at = page.index(">Discuss<")
    assert register_at < discuss_at, (
        "the discuss link renders ahead of registration -- registration is "
        "what a visitor to an upcoming page came for and must stay first"
    )
    assert "Recording &amp; discussion" not in page, (
        "a real thread resurrected the recording section on an upcoming page"
    )


def test_the_event_pages_contact_address_matches_confirmations_own_constant() -> None:
    """There is one contact address, and no template writes it out.

    This used to bind `event.njk`'s own literal to `confirmation.py`'s.
    The literal is gone: the template names `site.contact`,
    which `.eleventy.js` derives from `instance/config.json`. So both
    halves are asserted -- the template names it rather than spelling it,
    and the *built* page carries the address `confirmation.py` sends from.
    """
    source = _EVENT_TEMPLATE.read_text(encoding="utf-8")
    matches = re.findall(r"mailto:([^\"]+)", source)
    assert matches, "event.njk no longer names a contact address"
    assert set(matches) == {"{{ site.contact }}"}, (
        f"event.njk writes a contact address out rather than naming it: "
        f"{sorted(set(matches))}"
    )


# -------------------------------------------------------------------------- #
# Archives, the speaker-proposal entry point, and the data page.
#
# Archives are filterable entirely without JavaScript: every option the
# filter bar offers (a year, "with a recording", "with a discussion") is a
# real, statically generated page reached by a plain link, never a script
# deciding what to show. `_ARCHIVE_TEMPLATES` and the tests below prove
# both directions of that claim -- that a filter genuinely narrows what is
# shown, and that no page it can reach carries a `<script>` tag at all.
#
# The speaker-proposal page is the public entry point to the pipeline
# `tools/convener_ops/journey/proposal.py` already implements (a Tally form, its
# webhook verified and turned into a candidate lead) -- not a new
# mechanism, so this section proves the page links to the one already
# configured (the declaration's own `proposal_form`), and that the home page's own
# two CTAs now go through it rather than around it.
#
# The data page cites the data-protection record rather than
# restating it -- in particular it never repeats a retention figure, on
# purpose (two documents stating the same number independently disagree
# the day one changes and the other does not). What is pinned hard here
# is that its link to that record actually resolves
# to something the app publishes: built from the same two constants that
# decide where the record lands (`registry.ts`'s own file path,
# `vite.config.ts`'s own published base) rather than a literal URL nothing
# would catch drifting, and proved once more by a real copy-handbook run
# against a scratch destination.
# -------------------------------------------------------------------------- #

_LAYOUT_TEMPLATE = SITE_SRC / "_includes" / "layout.njk"
_DONNEES_TEMPLATE = SITE_SRC / "donnees.njk"
_REGISTRY_TS = ROOT / "app" / "src" / "content" / "registry.ts"
_DOCS_DIR = ROOT / "docs"
_HANDBOOK_REGISTRY_MJS = ROOT / "app" / "scripts" / "handbook-registry.mjs"


def _past_events() -> list[dict[str, Any]]:
    return [
        e for e in _events_fixture() if e.get("status") in ("delivered", "archived")
    ]


def _year_of(event: dict[str, Any]) -> str:
    return str(event["date"])[:4]


def _first_event_id_and_year() -> tuple[str, str]:
    """The event `built_site_one_bare_past_edition` below patches -- always
    the fixture's own first entry, the same "first matching item" idiom
    `_a_past_event_id`/`_the_one_scheduled_event_id` already use above, so
    fixture and test read the one committed file rather than a literal
    copied into this function."""
    first = _events_fixture()[0]
    return str(first["id"]), _year_of(first)


def test_layout_links_to_every_page_this_task_added() -> None:
    """A page nobody can navigate to is not shipped: `layout.njk` is the
    one piece of chrome every public page shares, so a link here reaches
    every page from anywhere on the site, including the home page."""
    layout = _LAYOUT_TEMPLATE.read_text(encoding="utf-8")
    # Each `href="/foo/"` moved behind Eleventy's `| url`
    # filter -- `href="{{ '/foo/' | url }}"` -- so a bare, unfiltered href
    # here would fail this pin exactly as surely as a missing link would.
    for href in ("/archives/", "/propose/", "/data/"):
        expected = "href=\"{{ '" + href + "' | url }}\""
        assert expected in layout, (
            f"layout.njk no longer links to {href} through the `url` filter"
        )


def test_home_pages_proposal_ctas_go_through_the_entry_page_not_around_it() -> None:
    """Build the entry point to the real form, not to something invented
    -- both "Propose a speaker" buttons on the home page point at
    `/propose/` now, not at the external form directly, so there is
    exactly one place the live form's address needs to change."""
    index_source = (SITE_SRC / "index.njk").read_text(encoding="utf-8")
    # Both CTAs read `href="{{ '/propose/' | url }}"`.
    assert index_source.count("'/propose/' | url") == 2
    assert "site.applyForm" not in index_source


# ---- Archives: filterable without JavaScript ----------------------------


def test_archives_page_lists_every_past_edition_and_no_upcoming_one(
    built_site: Path,
) -> None:
    past = _past_events()
    upcoming = [e for e in _events_fixture() if e.get("status") == "scheduled"]
    assert past and upcoming, (
        f"{_EVENTS_FIXTURE.as_posix()} needs at least one past and one "
        "upcoming event for this test to prove anything"
    )
    page = (built_site / "archives" / "index.html").read_text(encoding="utf-8")
    assert page.count('class="archive__row"') == len(past)
    for event in past:
        assert event["id"] in page, f"{event['id']} missing from /archives/"
    for event in upcoming:
        assert event["id"] not in page, (
            f"{event['id']} (not yet delivered) appears on /archives/"
        )


def test_archive_filter_bar_marks_the_all_page_current_without_linking_to_it(
    built_site: Path,
) -> None:
    page = (built_site / "archives" / "index.html").read_text(encoding="utf-8")
    assert (
        '<span class="archive-filters__current" aria-current="page">All</span>' in page
    )
    # Checked against the real, prefixed address this page
    # would carry if it wrongly linked to itself -- checking the old,
    # unprefixed literal would pass even if a prefixed `archives/`
    # link had reappeared here.
    assert f'<a href="{_pfx("/archives/")}">All</a>' not in page


def test_year_pages_exist_for_every_year_with_a_past_edition_and_no_other(
    built_site: Path,
) -> None:
    years = {_year_of(e) for e in _past_events()}
    assert len(years) >= 2, (
        f"{_EVENTS_FIXTURE.as_posix()} carries past editions from fewer "
        "than two distinct years -- too weak to prove a year page excludes "
        "another year's entries"
    )
    actual = {
        p.name
        for p in (built_site / "archives").iterdir()
        if p.is_dir() and p.name not in ("recordings", "discussions")
    }
    assert actual == years


def test_a_year_page_lists_only_that_years_editions(built_site: Path) -> None:
    by_year: dict[str, list[dict[str, Any]]] = {}
    for event in _past_events():
        by_year.setdefault(_year_of(event), []).append(event)
    for year, events in by_year.items():
        page = (built_site / "archives" / year / "index.html").read_text(
            encoding="utf-8"
        )
        assert f'aria-current="page">{year}' in page
        # Same reasoning as the "All" pin above -- checked
        # against the real, prefixed address.
        assert f'<a href="{_pfx(f"/archives/{year}/")}">' not in page
        for event in events:
            assert event["id"] in page
        for other_year, other_events in by_year.items():
            if other_year == year:
                continue
            for event in other_events:
                assert event["id"] not in page, (
                    f"{event['id']} ({other_year}) leaked onto the {year} page"
                )


def test_recordings_filter_includes_only_editions_with_a_recording(
    built_site: Path,
) -> None:
    past = _past_events()
    with_recording = [e for e in past if e.get("youtube_url")]
    without = [e for e in past if not e.get("youtube_url")]
    assert with_recording and without, (
        f"{_EVENTS_FIXTURE.as_posix()} needs at least one past edition with "
        "a recording and one without for this test to prove the filter "
        "excludes anything"
    )
    page = (built_site / "archives" / "recordings" / "index.html").read_text(
        encoding="utf-8"
    )
    for event in with_recording:
        assert event["id"] in page
    for event in without:
        assert event["id"] not in page


def test_discussions_filter_includes_only_editions_with_a_thread(
    built_site: Path,
) -> None:
    past = _past_events()
    with_thread = [e for e in past if e.get("forum_thread")]
    without = [e for e in past if not e.get("forum_thread")]
    assert with_thread and without, (
        f"{_EVENTS_FIXTURE.as_posix()} needs at least one past edition with "
        "a thread and one without for this test to prove the filter "
        "excludes anything"
    )
    page = (built_site / "archives" / "discussions" / "index.html").read_text(
        encoding="utf-8"
    )
    for event in with_thread:
        assert event["id"] in page
    for event in without:
        assert event["id"] not in page


def test_archive_pages_carry_no_script_tag_at_all(built_site: Path) -> None:
    """The design decision pinned hard here: filtering the archive never
    needs JavaScript. Every page the filter
    bar can possibly link to -- the full listing, each year, and both
    field-presence filters -- is swept, not only the base page, since a
    script added to any one of them would just as surely gate real
    content behind it."""
    pages = [
        Path("archives") / "index.html",
        Path("archives") / "recordings" / "index.html",
        Path("archives") / "discussions" / "index.html",
    ] + [
        Path("archives") / year / "index.html"
        for year in {_year_of(e) for e in _past_events()}
    ]
    for rel in pages:
        path = built_site / rel
        assert path.is_file(), f"{rel.as_posix()} was not built"
        text = path.read_text(encoding="utf-8")
        assert "<script" not in text.lower(), (
            f"{rel.as_posix()} carries a <script> tag -- the archive must "
            "stay usable with JavaScript disabled"
        )


@pytest.fixture(scope="module")
def built_site_no_past_editions(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Every event pushed to `scheduled` -- the archive's own empty state,
    which the
    committed fixture can never exercise on its own since it always
    carries past editions. Same scratch-copy technique
    `built_site_with_upcoming_forum_thread` above already uses, for the
    same reason: the committed fixture stays untouched.
    """
    if not _ELEVENTY_CMD.exists():
        pytest.skip(
            f"{_ELEVENTY_CMD.as_posix()} not found -- run `npm ci` in site/ "
            "before this suite (quality.yml's own python job now does)"
        )
    scratch_src = tmp_path_factory.mktemp("site-src-no-past") / "src"
    shutil.copytree(SITE_SRC, scratch_src)
    events_path = scratch_src / "_data" / "events.json"
    events = json.loads(events_path.read_text(encoding="utf-8"))
    for event in events:
        event["status"] = "scheduled"
    events_path.write_text(json.dumps(events), encoding="utf-8")
    out = tmp_path_factory.mktemp("site-build-no-past")
    try:
        subprocess.run(
            [
                "node",
                str(_ELEVENTY_CMD),
                f"--input={scratch_src.as_posix()}",
                f"--output={out.as_posix()}",
            ],
            cwd=ROOT / "site",
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        pytest.skip("node is not on PATH -- cannot build site/ for this suite")
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"site/ failed to build: {exc.stdout}\n{exc.stderr}"
        ) from exc
    return out


def test_the_empty_archive_states_a_reason_instead_of_an_empty_list(
    built_site_no_past_editions: Path,
) -> None:
    page = (built_site_no_past_editions / "archives" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "0 entries" in page
    assert '<ol class="archive">' not in page
    assert "No edition has been delivered yet" in page


def test_an_empty_archive_generates_no_year_pages(
    built_site_no_past_editions: Path,
) -> None:
    """`archive.years` (`site/src/_data/archive.js`) is empty when nothing
    is past, so `archives-year.njk`'s own pagination produces zero
    `/archives/<year>/` pages -- proof the year filter is genuinely
    data-driven rather than a fixed list that would otherwise dangle."""
    archives_dir = built_site_no_past_editions / "archives"
    year_dirs = [
        p
        for p in archives_dir.iterdir()
        if p.is_dir() and p.name not in ("recordings", "discussions")
    ]
    assert year_dirs == []


def test_the_two_field_filters_still_exist_on_a_wholly_empty_archive(
    built_site_no_past_editions: Path,
) -> None:
    """Unlike a year page, "with a recording" and "with a discussion" are
    always real questions to ask (`archives-filter.njk`'s own front matter
    names them directly, never derived from the data) -- both pages stay
    reachable even when nothing at all is past, each with the reason
    worded for that specific filter."""
    recordings = (
        built_site_no_past_editions / "archives" / "recordings" / "index.html"
    ).read_text(encoding="utf-8")
    discussions = (
        built_site_no_past_editions / "archives" / "discussions" / "index.html"
    ).read_text(encoding="utf-8")
    assert "No past edition has a recording published yet." in recordings
    assert "No past edition has an open discussion thread yet." in discussions


@pytest.fixture(scope="module")
def built_site_one_bare_past_edition(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Exactly one past edition, with neither a recording nor a thread --
    the "an archive with one entry" state, and, in the same
    build, the two field-presence filters' "matches nothing" state on an
    archive that is *not* itself empty. Distinct from
    `built_site_no_past_editions` above, which can only prove "no
    editions"; this proves "editions exist, none of them qualify",
    a different branch of the same two `{% if %}` guards.
    """
    if not _ELEVENTY_CMD.exists():
        pytest.skip(
            f"{_ELEVENTY_CMD.as_posix()} not found -- run `npm ci` in site/ "
            "before this suite (quality.yml's own python job now does)"
        )
    scratch_src = tmp_path_factory.mktemp("site-src-one-bare") / "src"
    shutil.copytree(SITE_SRC, scratch_src)
    events_path = scratch_src / "_data" / "events.json"
    events = json.loads(events_path.read_text(encoding="utf-8"))
    assert events, f"{_EVENTS_FIXTURE.as_posix()} is empty"
    events[0]["status"] = "delivered"
    events[0]["youtube_url"] = ""
    events[0]["forum_thread"] = ""
    for event in events[1:]:
        event["status"] = "scheduled"
    events_path.write_text(json.dumps(events), encoding="utf-8")
    out = tmp_path_factory.mktemp("site-build-one-bare")
    try:
        subprocess.run(
            [
                "node",
                str(_ELEVENTY_CMD),
                f"--input={scratch_src.as_posix()}",
                f"--output={out.as_posix()}",
            ],
            cwd=ROOT / "site",
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        pytest.skip("node is not on PATH -- cannot build site/ for this suite")
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"site/ failed to build: {exc.stdout}\n{exc.stderr}"
        ) from exc
    return out


def test_a_lone_past_edition_is_the_only_row_and_counted_in_the_singular(
    built_site_one_bare_past_edition: Path,
) -> None:
    event_id, _year = _first_event_id_and_year()
    page = (built_site_one_bare_past_edition / "archives" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "1 entry" in page
    assert "entries" not in page
    assert page.count('class="archive__row"') == 1
    assert event_id in page


def test_a_lone_past_editions_year_page_shows_it_disabled_both_ways(
    built_site_one_bare_past_edition: Path,
) -> None:
    event_id, year = _first_event_id_and_year()
    page = (
        built_site_one_bare_past_edition / "archives" / year / "index.html"
    ).read_text(encoding="utf-8")
    assert event_id in page
    assert "No recording" in page
    assert "No thread" in page


def test_both_field_filters_show_their_own_empty_state_though_the_archive_is_not(
    built_site_one_bare_past_edition: Path,
) -> None:
    recordings = (
        built_site_one_bare_past_edition / "archives" / "recordings" / "index.html"
    ).read_text(encoding="utf-8")
    discussions = (
        built_site_one_bare_past_edition / "archives" / "discussions" / "index.html"
    ).read_text(encoding="utf-8")
    assert "No past edition has a recording published yet." in recordings
    assert "No past edition has an open discussion thread yet." in discussions
    assert "0 entries" in recordings
    assert "0 entries" in discussions


# ---- Proposing a speaker: the public entry point -------------------------


def test_the_propose_page_offers_a_form_or_says_it_is_not_open(
    built_site: Path,
) -> None:
    """One page, two states, and never the third one it used to have.

    `instance/config.json` declared `proposal_form:
    https://forms.example.test/propose` -- a placeholder inherited from the old
    `site/src/_data/site.json` -- and this page published it as its one
    call to action, a live button on a public page resolving to nothing.
    `Identity.proposal_form_url` is empty
    for a placeholder, and the template renders the other state instead.

    Written as an equivalence rather than as a branch: whichever state
    this instance's own declaration is in, exactly one of the two must be
    on the page. The configured state is exercised on a real build by
    `test_second_instance.py::test_the_second_instances_showcase_offers_
    its_own_proposal_form`, where the example instance declares a form.
    """
    identity = published.load_identity()
    page = (built_site / "propose" / "index.html").read_text(encoding="utf-8")
    linked = f'href="{identity.proposal_form}"' in page
    not_open = "The proposal form is not published yet." in page
    assert linked is bool(identity.proposal_form_url), (
        "the propose page links a form the declaration does not offer, or "
        f"offers none when it does: proposal_form={identity.proposal_form!r}"
    )
    assert not_open is not linked, (
        "the propose page must say the form is not open exactly when it cannot link one"
    )
    assert published.PLACEHOLDER_MARKER not in page


def test_propose_page_names_the_shared_contact_address(built_site: Path) -> None:
    page = (built_site / "propose" / "index.html").read_text(encoding="utf-8")
    assert f"mailto:{CONTACT_EMAIL}" in page


# ---- Information and data -------------------------------------------------


def test_the_data_pages_contact_address_matches_confirmations_own_constant() -> None:
    """The same thing held above for `event.njk`: one address, named
    rather than spelled, in every template that offers it."""
    source = _DONNEES_TEMPLATE.read_text(encoding="utf-8")
    matches = re.findall(r"mailto:([^\"]+)", source)
    assert matches, "donnees.njk no longer names a contact address"
    assert set(matches) == {"{{ site.contact }}"}, (
        f"donnees.njk writes a contact address out rather than naming it: "
        f"{sorted(set(matches))}"
    )


def test_every_built_page_that_offers_the_contact_address_gives_the_real_one(
    built_site: Path,
) -> None:
    """The other half: a template that names `site.contact` and a build
    that resolves it to something else would pass every assertion above.
    Read off the built HTML, which is what a participant sees."""
    pages = [
        p
        for p in sorted(built_site.rglob("*.html"))
        if "mailto:" in p.read_text(encoding="utf-8")
    ]
    assert pages, "no built page offers a contact address at all"
    for page in pages:
        addresses = set(
            re.findall(r"mailto:([^\"]+)", page.read_text(encoding="utf-8"))
        )
        assert addresses == {CONTACT_EMAIL}, (
            f"{page.relative_to(built_site).as_posix()} offers {addresses}, "
            f"not the one address this instance declares ({CONTACT_EMAIL})"
        )


def test_the_data_page_never_restates_the_retention_figure() -> None:
    """One notion, one home, checked: this page cites the governance
    record rather than restating it, and in particular never repeats the
    "90 days" retention figure that record gives -- a second copy of that
    number here is precisely the drift risk, whether or not it agrees
    with the record today."""
    source = _DONNEES_TEMPLATE.read_text(encoding="utf-8")
    assert "90" not in source


def _governance_record_file() -> str:
    """The `file` `CONTENT_REGISTRY['governance/data-protection-record']`
    names, read as text. Independent of `handbook-registry.mjs`'s own
    identical-in-spirit extraction: this test must fail if either
    side of the pairing it checks -- this constant, or `donnees.njk`'s own
    link -- changes without the other, not share a helper with the thing
    it verifies.
    """
    text = _REGISTRY_TS.read_text(encoding="utf-8")
    match = re.search(
        r"'governance/data-protection-record':\s*\{\s*file:\s*'([^']+)'", text
    )
    assert match is not None, (
        "registry.ts no longer registers 'governance/data-protection-record' "
        "-- donnees.njk links to a page this app may no longer publish"
    )
    return match.group(1)


def _published_app_base() -> str:
    """The base every published application asset URL is resolved
    against: the published prefix plus `app/`, where the cockpit and all
    three islands publish (the islands used to set a
    different, undocumented-in-production `/app/`; see `vite.config.ts`'s
    own comment for why that reasoning did not hold once the site itself
    became prefix-aware).

    Read from the declaration rather than matched out
    of `vite.config.ts`, which no longer writes it down at all. That the
    four builds really do resolve to this is checked by running each of
    them, in `test_published.py`.
    """
    return published.load().app_base


#: The private-repository defect (D-15): `event.njk` used to
#: link the same data-protection record straight at `example-cockpit` -- the
#: *private* source repository -- which hands a public visitor GitHub's own
#: 404. `donnees.njk` already linked the published handbook address; both
#: templates are checked against the identical `expected` string below, so
#: neither can quietly disagree with the other again.
_GOVERNANCE_LINK_TEMPLATES = (_DONNEES_TEMPLATE, _EVENT_TEMPLATE)


def test_the_governance_record_link_agrees_on_every_page_that_makes_it() -> None:
    """One of the two things pinned hard here: every page's link to the
    governance record resolves to something published,
    not to the private repository it actually lives in the source of.

    The templates no longer write the address at all --
    they pipe a root-relative path through `absoluteUrl`, which builds it
    from `instance/config.json`. So what is checked here is that both
    templates make the *same* call (they cannot state two different
    answers to the same question), and the address itself is checked
    where it is actually produced: on the built pages, by
    `test_the_governance_record_link_resolves_to_the_published_handbook`
    below.
    """
    expected_call = f"{{{{ '/app/docs/{_governance_record_file()}' | absoluteUrl }}}}"
    for template in _GOVERNANCE_LINK_TEMPLATES:
        source = template.read_text(encoding="utf-8")
        assert expected_call in source, (
            f"{template.relative_to(ROOT).as_posix()} does not link to "
            f"{expected_call!r} -- either the link drifted, or "
            "registry.ts changed under it"
        )
        # `_without_comments`: this fix's own explanatory comment names
        # "example-cockpit" by way of saying what was removed -- the same
        # reason `test_no_page_requests_a_third_party_font_host` strips
        # comments before scanning, rather than flag the very comment
        # explaining the fix as if it were the regression.
        assert "example-cockpit" not in _without_comments(source), (
            f"{template.relative_to(ROOT).as_posix()} links straight at the "
            "private example-cockpit repository -- a public visitor gets "
            "GitHub's own 404 (D-15: private source, public artefact)"
        )


def test_the_governance_record_link_resolves_to_the_published_handbook(
    built_site: Path,
) -> None:
    """The other half, and the half that matters: what a visitor's browser
    actually receives.

    D-26 -- checked at the deployed shape, never at the template. The
    address is composed at build time from `instance/config.json` and the
    application's own published base, so the only way to know it came out
    right is to read it off a built page. Both pages that carry this link
    are checked, and the expected value is built from the declaration
    rather than typed, so a duplicate publishing at its own address gets
    its own link with nothing to edit in either template.
    """
    expected = published.load().under(f"app/docs/{_governance_record_file()}")
    pages = [built_site / "data" / "index.html"]
    pages += sorted((built_site / "events").glob("*/index.html"))
    assert len(pages) >= 2, f"only {pages} to check -- the build wrote too little"

    carrying = [p for p in pages if expected in p.read_text(encoding="utf-8")]
    assert carrying, (
        f"no built page links the governance record at {expected!r} -- the "
        "data page and every event page make this link, so either it "
        "stopped resolving against the published address or it moved"
    )


@pytest.fixture(scope="module")
def published_handbook(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real run of `copyHandbook` (the allowlist filter in
    `app/scripts/handbook-registry.mjs`) against the real `docs/` tree,
    into a scratch destination -- proof that the file `donnees.njk` links
    to is actually among what the app publishes, not merely named
    correctly by the regex check above. `app/tests/copy-handbook.test.ts`
    already proves this exhaustively from the TypeScript side; this is
    the one file the data page depends on, checked once more from
    the Python side that owns `donnees.njk`, by a real copy rather than a
    second reading of the same registry text.
    """
    dst = tmp_path_factory.mktemp("handbook-out")
    probe = tmp_path_factory.mktemp("probe") / "probe.mjs"
    registry_path = json.dumps(str(_REGISTRY_TS))
    probe.write_text(
        "import { readFileSync } from 'node:fs';\n"
        f"import {{ copyHandbook }} from '{_HANDBOOK_REGISTRY_MJS.as_uri()}';\n"
        f"const registrySource = readFileSync({registry_path}, 'utf-8');\n"
        "const { files } = await copyHandbook({\n"
        f"  docsDir: {json.dumps(str(_DOCS_DIR))},\n"
        "  registrySource,\n"
        f"  dst: {json.dumps(str(dst))},\n"
        "});\n"
        "console.log(JSON.stringify(files));\n",
        encoding="utf-8",
    )
    try:
        subprocess.run(
            ["node", str(probe)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        pytest.skip("node is not on PATH -- cannot run the real copy-handbook step")
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"copyHandbook failed: {exc.stdout}\n{exc.stderr}"
        ) from exc
    return dst


def test_the_governance_record_is_actually_among_what_the_app_publishes(
    published_handbook: Path,
) -> None:
    target = published_handbook / Path(_governance_record_file())
    assert target.is_file(), (
        f"{target} does not exist after a real copy-handbook run -- "
        "donnees.njk's link would 404 even though its shape looks right"
    )


# -------------------------------------------------------------------------- #
# The path-prefix defect. GitHub Pages serves this project's
# build output one path segment below a bare domain root, not at
# a bare domain root -- there is no CNAME and no custom domain. Every
# template used to write its internal links as a bare `/foo`, which
# resolves one path segment short of where the site actually lives --
# invisible on a developer's own `localhost` build (a root-relative path
# resolves identically at any root), total once published: the stylesheet,
# every self-hosted font, every internal link, and both island `<script>`
# tags -- registration and certificate verification, the two things this
# phase exists to deliver -- would all 404.
#
# The fix: `site/.eleventy.js` now sets `pathPrefix`, and every template's
# internal `href`/`src` goes through Eleventy's own `url` filter, which
# applies it; `style.css`'s own font `url()`s are relative instead, which
# needs no prefix at all -- a relative URL inside a stylesheet resolves
# against the stylesheet's own address, at any prefix; and both islands'
# Vite `base` (`app/vite.config.ts`) now matches the main app's published
# address rather than diverging from it. The two tests below are what
# closes it: a built-output sweep over the whole class of defect (not just
# the instances anybody happened to enumerate), and a cross-boundary pin
# that keeps the site's own prefix
# from becoming a fourth, independent literal.
# -------------------------------------------------------------------------- #

_HREF_SRC_RE = re.compile(r'(?:href|src)="([^"]*)"')


def test_no_built_page_emits_a_root_relative_link_without_the_prefix(
    built_site: Path,
) -> None:
    """Asserted over the real, built output -- every `.html` file the real
    build actually wrote -- rather than the eleven paths one review
    happened to enumerate: a twelfth root-relative link, on a page this
    task does not know about, fails this test exactly the same way a
    thirteenth or a hundredth would. `built_site` is the same fixture the
    rest of this module already builds `site/` into (its own committed
    fixture data), so this runs against every page template this project
    ships: the home page, every event page, every archive view, `/propose/`
    and `/data/`.

    A link is "root-relative" here if it starts with a single `/` -- an
    absolute URL (`https://...`), a `mailto:` link, and a protocol-relative
    one (`//host/...`, excluded explicitly since it too starts with `/`)
    are all left alone, because none of them is resolved against this
    site's own published address at all.
    """
    prefix = _configured_path_prefix()
    html_files = list(built_site.rglob("*.html"))
    assert html_files, (
        f"no .html file found under {built_site} -- the glob itself may be "
        "wrong, which would silently pass this test on an empty scan"
    )
    offending: list[tuple[str, str]] = []
    for path in html_files:
        text = path.read_text(encoding="utf-8")
        for value in _HREF_SRC_RE.findall(text):
            if not value.startswith("/") or value.startswith("//"):
                continue  # relative, a fragment, mailto:, or an absolute URL
            if not value.startswith(prefix):
                offending.append((path.relative_to(built_site).as_posix(), value))
    assert offending == [], (
        f"root-relative href/src missing the {prefix!r} prefix: {offending} "
        "-- every internal link must go through Eleventy's `url` filter "
        "(site/.eleventy.js's own PATH_PREFIX), or it 404s once served from "
        "this project's real published address"
    )


def test_the_path_prefix_agrees_with_the_addresses_python_already_pins() -> None:
    """D-14: this project's published path prefix is not a second literal
    anywhere. `registration.SIGNUP_BASE`, `certificate.VERIFICATION_BASE`
    and the application's own `base` all used to carry it independently,
    bound to each other by tests that could say the copies still agreed
    but never that there was one. There is one now: this
    now checks that each of those addresses is genuinely *under* the
    declared root, which is the property the rest of this module's
    prefixed assertions rest on. What still needs a real run to be worth
    anything -- that the showcase and the four application builds resolve
    the same root -- is `test_published.py`'s.
    """
    root = published.load().url
    assert SIGNUP_BASE.startswith(root), (
        f"registration.SIGNUP_BASE ({SIGNUP_BASE!r}) no longer starts with "
        f"{root!r} -- it has stopped deriving from instance/config.json"
    )
    assert VERIFICATION_BASE.startswith(root), (
        f"certificate.VERIFICATION_BASE ({VERIFICATION_BASE!r}) no longer "
        f"starts with {root!r} -- it has stopped deriving from "
        "instance/config.json"
    )
    assert _published_app_base() == f"{_configured_path_prefix()}app/", (
        "the application's published base no longer sits under the "
        "showcase's own prefix -- the app and the site would publish to, "
        "and be addressed from, different places"
    )


def test_absolute_urls_share_the_one_origin_this_project_already_pins() -> None:
    """D-14/D-26: structured data, share metadata, the sitemap and the
    feed are this project's *absolute* URLs, and therefore
    its need for a full origin, not just the path prefix
    `test_the_path_prefix_agrees_with_the_addresses_python_already_pins`
    above already binds. The origin and the prefix are
    two properties of one declared value now, so this checks the property
    that still means something -- that every absolute address this
    project builds starts at that one root.
    """
    base = f"{_configured_site_origin()}{_configured_path_prefix()}"
    assert SIGNUP_BASE.startswith(base), (
        f"registration.SIGNUP_BASE ({SIGNUP_BASE!r}) does not start with "
        f"{base!r} -- site/.eleventy.js's SITE_ORIGIN has drifted from the "
        "host this project actually publishes to"
    )
    assert VERIFICATION_BASE.startswith(base), (
        f"certificate.VERIFICATION_BASE ({VERIFICATION_BASE!r}) does not "
        f"start with {base!r} -- site/.eleventy.js's SITE_ORIGIN has drifted"
    )


# -------------------------------------------------------------------------- #
# Structured event data, share metadata, a sitemap and a feed.
#
# Every URL this section checks is *absolute* (`_absolute`, above) -- this
# is the one part of the site where a merely-prefixed root-relative link
# (`<prefix>events/mrg-05/`) is still wrong: structured data, Open
# Graph/Twitter Card metadata, the sitemap and the feed are all read by a
# consumer with no document of its own to resolve a relative link against
# (a search engine's crawler, a link-preview bot, an RSS reader), so they
# need the real host too, not only the path Eleventy's `pathPrefix`
# supplies. `_built_file_for_absolute_url`, below, is the inverse
# operation: given one of these absolute URLs, the file `built_site`
# should already contain for it, so that every URL in the sitemap and the
# feed can be confirmed to resolve against the served tree.
# -------------------------------------------------------------------------- #

_JSON_LD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
)


def _json_ld(page_text: str) -> dict[str, Any]:
    match = _JSON_LD_RE.search(page_text)
    assert match is not None, "page carries no application/ld+json script"
    data = json.loads(match.group(1))
    assert isinstance(data, dict)
    return data


def _built_file_for_absolute_url(url: str, built_site: Path) -> Path:
    """The file `built_site` should already contain for `url`, an absolute
    address this project's own `absoluteUrl` filter produced -- the
    inverse of `_absolute`: strip the host and the path prefix, then
    resolve what remains exactly the way a static file server would (a
    path ending in `/`, including the bare root, serves `index.html`).
    """
    base = f"{_configured_site_origin()}{_configured_path_prefix()}"
    assert url.startswith(base), f"{url!r} does not start with {base!r}"
    remainder = url[len(base) :]
    if remainder == "" or remainder.endswith("/"):
        remainder += "index.html"
    return built_site / remainder


def _an_archived_event_with_recording_id() -> str:
    candidates = [
        e
        for e in _events_fixture()
        if e.get("status") == "archived" and e.get("youtube_url")
    ]
    assert candidates, (
        f"{_EVENTS_FIXTURE.as_posix()} carries no archived edition with a "
        "youtube_url -- nothing for the recording-state structured-data "
        "test below to check"
    )
    return str(candidates[0]["id"]).lower()


# ---- Structured event data -------------------------------------------------


def test_an_event_pages_structured_data_names_the_event_type_and_its_real_date(
    built_site: Path,
) -> None:
    """Structured event data on every event page, so a
    search engine shows date and place correctly rather than reading the
    page as an ordinary article."""
    event_id = _the_one_scheduled_event_id()
    event = next(e for e in _events_fixture() if str(e["id"]).lower() == event_id)
    page = (built_site / "events" / event_id / "index.html").read_text(encoding="utf-8")
    data = _json_ld(page)
    assert data["@context"] == "https://schema.org"
    assert data["@type"] == "Event"
    assert data["name"] == event["title"]
    assert data["startDate"].startswith(str(event["date"]))
    assert data["url"] == _absolute(f"/events/{event_id}/")
    assert data["location"]["url"] == _absolute(f"/events/{event_id}/")


def test_the_paris_offset_and_label_agree_across_every_edition_and_the_dst_boundary(
    built_site: Path,
) -> None:
    """`startDate`'s UTC offset must be the one Europe/Paris
    actually observes on the edition's own date, not a fixed `+01:00` --
    silently wrong by an hour for any edition in daylight-saving time,
    which three of this project's own five fixture editions are. And the
    page's own visible "12:30 CET"/"12:30 CEST" text must state the same
    season the structured data does (D-26): a page whose text and whose
    machine-readable data disagree about the start time is worse than
    either being wrong alone. The homepage's own "Up next" card is
    checked too -- `index.njk` prints this same label from the same
    filter, independently of `event.njk`.

    Checked against every edition in the committed fixture, not a single
    hand-picked one: a test that only ever exercised a winter date would
    have passed against the bug this fixes, since a hard-typed `+01:00`
    agrees with a CET edition by construction. The assertion below that
    both abbreviations actually occur in the fixture guards against that
    exact blind spot surviving a future edit to `events.json`.
    """
    events = _events_fixture()
    seen_abbreviations = set()
    for event in events:
        event_id = str(event["id"]).lower()
        page = (built_site / "events" / event_id / "index.html").read_text(
            encoding="utf-8"
        )
        data = _json_ld(page)
        offset, abbreviation = _expected_paris_start(str(event["date"]))
        seen_abbreviations.add(abbreviation)
        assert data["startDate"] == f"{event['date']}T12:30:00{offset}", (
            f"{event_id}'s startDate is {data['startDate']!r}, expected an "
            f"offset of {offset!r} for {event['date']} in Europe/Paris"
        )
        assert f"12:30 {abbreviation}" in page, (
            f"{event_id}'s page does not visibly state '12:30 {abbreviation}', "
            f"even though its structured data's startDate carries offset {offset}"
        )
    assert seen_abbreviations == {"CET", "CEST"}, (
        f"{_EVENTS_FIXTURE.as_posix()}'s editions all fall in the same "
        f"Europe/Paris season ({seen_abbreviations}) -- this test needs at "
        "least one edition on each side of the DST boundary to prove "
        "anything about it"
    )

    upcoming_id = _the_one_scheduled_event_id()
    upcoming = next(e for e in events if str(e["id"]).lower() == upcoming_id)
    _, upcoming_abbreviation = _expected_paris_start(str(upcoming["date"]))
    home_page = (built_site / "index.html").read_text(encoding="utf-8")
    assert f"12:30 {upcoming_abbreviation}" in home_page, (
        "the homepage's own 'Up next' card does not visibly state "
        f"'12:30 {upcoming_abbreviation}' for {upcoming_id}"
    )


def test_an_upcoming_events_structured_data_offers_registration_a_past_ones_does_not(
    built_site: Path,
) -> None:
    """A past seminar is not still accepting registrations.
    `potentialAction` (schema.org
    RegisterAction) appears on an upcoming edition's structured data and
    on no other -- mutate event.njk to emit it unconditionally, ahead of
    `isUpcoming`, and this is the test that objects.
    """
    upcoming_id = _the_one_scheduled_event_id()
    past_id = _a_past_event_id()
    upcoming = _json_ld(
        (built_site / "events" / upcoming_id / "index.html").read_text(encoding="utf-8")
    )
    past = _json_ld(
        (built_site / "events" / past_id / "index.html").read_text(encoding="utf-8")
    )
    assert upcoming["potentialAction"]["@type"] == "RegisterAction"
    assert upcoming["potentialAction"]["target"] == _absolute(f"/events/{upcoming_id}/")
    assert "potentialAction" not in past, (
        f"{past_id}'s structured data still offers registration for an "
        "edition that has already happened"
    )


def test_a_recordings_structured_data_names_it_a_recordingless_editions_does_not(
    built_site: Path,
) -> None:
    """The other state: an edition with a recording and one without must
    not read the same in structured data.
    """
    with_recording_id = _an_archived_event_with_recording_id()
    without_recording_id = _a_past_event_id()
    events = _events_fixture()
    assert not any(
        str(e["id"]).lower() == without_recording_id and e.get("youtube_url")
        for e in events
    ), (
        f"{without_recording_id} carries a youtube_url after all -- not the "
        "recording-less fixture this test needs"
    )
    with_recording = next(
        e for e in events if str(e["id"]).lower() == with_recording_id
    )

    with_page = _json_ld(
        (built_site / "events" / with_recording_id / "index.html").read_text(
            encoding="utf-8"
        )
    )
    without_page = _json_ld(
        (built_site / "events" / without_recording_id / "index.html").read_text(
            encoding="utf-8"
        )
    )
    assert with_page["subjectOf"]["@type"] == "VideoObject"
    assert with_page["subjectOf"]["url"] == with_recording["youtube_url"]
    assert "subjectOf" not in without_page, (
        f"{without_recording_id}'s structured data names a recording it does not have"
    )


def test_structured_datas_performer_never_exceeds_the_speakers_public_fields(
    built_site: Path,
) -> None:
    """No personal data beyond what is already public: `performer` (a
    schema.org Person) may carry only what `public_data.py`'s own
    `PUBLISHABLE_ALWAYS` already publishes about a speaker by name -- name,
    affiliation, country -- never a consent-gated field such as a photo or
    a biography, which this JSON-LD block does not even read. Checked
    against every built event page, not one sample: a fourth key could
    reach the page's data by a route this fixture's own speakers never
    exercise.
    """
    assert {"name", "affiliation", "country"} <= PUBLISHABLE_ALWAYS
    for path in sorted((built_site / "events").glob("*/index.html")):
        data = _json_ld(path.read_text(encoding="utf-8"))
        performer = data["performer"]
        assert performer["@type"] == "Person"
        assert set(performer.keys()) <= {"@type", "name", "affiliation"}, (
            f"{path.relative_to(built_site).as_posix()}'s performer carries "
            f"an unexpected key: {sorted(performer.keys())}"
        )
        if "affiliation" in performer:
            affiliation = performer["affiliation"]
            assert set(affiliation.keys()) <= {"@type", "name", "address"}, (
                f"{path.relative_to(built_site).as_posix()}'s affiliation "
                f"carries an unexpected key: {sorted(affiliation.keys())}"
            )
            if "address" in affiliation:
                assert set(affiliation["address"].keys()) <= {
                    "@type",
                    "addressCountry",
                }


# ---- Share metadata ---------------------------------------------------------

_OG_IMAGE_RE = re.compile(r'<meta property="og:image" content="([^"]*)"')


def test_every_page_carries_a_canonical_link_and_matching_open_graph_metadata(
    built_site: Path,
) -> None:
    """A shared page shows a correct preview.
    Checked on the home page, an event page, and one of every other kind
    of page this project generates -- `og:url`/the canonical link must be
    this project's real, absolute address, and title/description must be
    non-empty."""
    samples = {
        "/": built_site / "index.html",
        "/archives/": built_site / "archives" / "index.html",
        "/propose/": built_site / "propose" / "index.html",
        "/data/": built_site / "data" / "index.html",
        "/verify/": built_site / "verify" / "index.html",
        f"/events/{_the_one_scheduled_event_id()}/": built_site
        / "events"
        / _the_one_scheduled_event_id()
        / "index.html",
    }
    for route, path in samples.items():
        page = path.read_text(encoding="utf-8")
        expected_url = _absolute(route)
        canonical = re.search(r'<link rel="canonical" href="([^"]*)"', page)
        og_url = re.search(r'<meta property="og:url" content="([^"]*)"', page)
        og_title = re.search(r'<meta property="og:title" content="([^"]*)"', page)
        og_description = re.search(
            r'<meta property="og:description" content="([^"]*)"', page
        )
        assert canonical is not None and canonical.group(1) == expected_url, path
        assert og_url is not None and og_url.group(1) == expected_url, path
        assert og_title is not None and og_title.group(1).strip() != "", path
        assert og_description is not None and og_description.group(1).strip() != "", (
            path
        )


def test_no_page_ever_references_an_og_image_that_would_be_a_dangling_link(
    built_site: Path,
) -> None:
    """The other half of a correct preview: until a per-event social image
    exists, `layout.njk` emits
    no `og:image`/`twitter:image` at all rather than one pointing at a file
    that does not exist yet -- "a fallback that is not broken" read
    literally: a link-preview bot renders a correct text-only card, never
    a broken image. Written to survive a real image landing, not
    merely to prove today's absence: whichever this repository does,
    a referenced image must resolve to a file the build actually wrote.
    """
    checked_absence = 0
    for path in built_site.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        match = _OG_IMAGE_RE.search(text)
        if match is None:
            checked_absence += 1
            continue
        target = _built_file_for_absolute_url(match.group(1), built_site)
        assert target.is_file(), (
            f"{path.relative_to(built_site).as_posix()}'s og:image "
            f"({match.group(1)!r}) does not resolve to a file the build "
            "wrote -- a broken preview image, not a correct one"
        )
    assert checked_absence > 0, (
        "no built page was found to check the image-absence case against"
    )


# ---- Sitemap and feed -------------------------------------------------------


def test_every_addressable_page_is_in_the_sitemap_and_the_two_archive_filters_are_not(
    built_site: Path,
) -> None:
    """The worked mutation: remove a
    page from the sitemap and this is the test that notices. Every page
    this project's committed fixture actually generates is expected, by
    name, except the two archive facets (`archives-filter.njk`'s own
    `sitemap: false`) -- see `sitemap.njk`'s own comment for why those two,
    and not the year pages, are the deliberate exclusion.
    """
    events = _events_fixture()
    past_years = sorted(
        {
            str(e["date"])[:4]
            for e in events
            if e.get("status") in ("delivered", "archived")
        }
    )
    expected = {_absolute("/")}
    expected |= {_absolute(f"/events/{str(e['id']).lower()}/") for e in events}
    expected.add(_absolute("/archives/"))
    expected |= {_absolute(f"/archives/{year}/") for year in past_years}
    expected.add(_absolute("/propose/"))
    expected.add(_absolute("/data/"))
    expected.add(_absolute("/verify/"))

    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    tree = ET.parse(built_site / "sitemap.xml")
    actual = {loc.text for loc in tree.findall(".//s:url/s:loc", ns)}

    assert actual == expected
    assert _absolute("/archives/recordings/") not in actual
    assert _absolute("/archives/discussions/") not in actual


def test_every_sitemap_and_feed_url_resolves_to_a_file_the_build_actually_wrote(
    built_site: Path,
) -> None:
    """Every URL in the sitemap and the feed resolves against the served
    tree. Also the
    worked mutation "break one absolute URL so it loses its prefix": strip
    `SITE_ORIGIN` (or `PATH_PREFIX`) out of `site/.eleventy.js`'s
    `absoluteUrl` filter and every assertion below fails, since none of
    these URLs would start with this project's real published address any
    more.
    """
    base = f"{_configured_site_origin()}{_configured_path_prefix()}"

    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemap_tree = ET.parse(built_site / "sitemap.xml")
    sitemap_urls = [loc.text for loc in sitemap_tree.findall(".//s:url/s:loc", ns)]
    assert sitemap_urls, "sitemap.xml carries no <url> at all"

    feed_tree = ET.parse(built_site / "feed.xml")
    feed_urls = [el.text for el in feed_tree.findall(".//link")]
    feed_urls += [el.text for el in feed_tree.findall(".//guid")]
    assert feed_urls, "feed.xml carries no <link>/<guid> at all"

    for url in sitemap_urls + feed_urls:
        assert url is not None and url.startswith(base), (
            f"{url!r} is not an absolute URL under this project's own "
            f"published address ({base!r})"
        )
        target = _built_file_for_absolute_url(url, built_site)
        assert target.is_file(), (
            f"{url!r} resolves to {target}, which the build did not write"
        )
    # Belt and braces: the exact double-prefix shape a mistaken
    # `x | url | absoluteUrl` chain would produce.
    doubled = f"{_configured_path_prefix()}{_configured_path_prefix().lstrip('/')}"
    assert not any(doubled in url for url in sitemap_urls + feed_urls if url)


def test_the_feed_lists_every_edition_newest_first_and_nothing_else(
    built_site: Path,
) -> None:
    """The feed's item universe is editions, full stop -- upcoming and past
    alike, and nothing from the archive index, its year or filter pages,
    or any of the three other static pages, none of which is an edition.
    Newest first, since that is what a subscriber to a feed of editions
    wants to see first, including an edition not yet delivered.
    """
    events = _events_fixture()
    expected = [
        _absolute(f"/events/{str(e['id']).lower()}/")
        for e in sorted(events, key=lambda e: str(e["date"]), reverse=True)
    ]
    tree = ET.parse(built_site / "feed.xml")
    actual = [el.text for el in tree.findall(".//item/link")]
    assert actual == expected


def test_the_feed_description_agrees_with_the_event_pages_own_description(
    built_site: Path,
) -> None:
    """`feed.njk`'s fallback description
    for an edition with no `abstract` had drifted from `event.njk`'s
    identical rule -- missing the closing " — a <organisation> virtual
    seminar." sentence -- while `feed.njk`'s own comment claimed the two
    "never state the description of the same edition two different ways".
    Confirmed on the real built output for MRG-04 before this fix: the
    feed's `<description>` lacked the sentence its own `og:description`
    and JSON-LD `description` carried. Both templates now call the one
    shared filter (`site/.eleventy.js::eventDescriptionFallback`); this
    pins that the feed's `<description>` for every abstract-less edition
    matches that same edition's own page `og:description` (which the
    share-metadata tests above already require to be non-empty), so a
    future hand-edit to either template's copy of the rule is caught here
    rather than only found by inspection.
    """
    abstractless = [e for e in _events_fixture() if not e.get("abstract")]
    assert abstractless, (
        f"{_EVENTS_FIXTURE.as_posix()} carries no abstract-less edition -- "
        "nothing for this test to check the fallback against"
    )

    tree = ET.parse(built_site / "feed.xml")
    feed_description_by_link = {
        link.text: description.text
        for link, description in zip(
            tree.findall(".//item/link"),
            tree.findall(".//item/description"),
            strict=True,
        )
    }

    for event in abstractless:
        event_id = str(event["id"]).lower()
        url = _absolute(f"/events/{event_id}/")
        page = (built_site / "events" / event_id / "index.html").read_text(
            encoding="utf-8"
        )
        og_description = re.search(
            r'<meta property="og:description" content="([^"]*)"', page
        )
        assert og_description is not None, page
        assert feed_description_by_link.get(url) == og_description.group(1), (
            f"feed.xml's <description> for {event_id} disagrees with that "
            "edition's own og:description"
        )


_ENGLISH_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_ENGLISH_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def _expected_paris_start(iso_date: str) -> tuple[str, str]:
    """The real Europe/Paris UTC offset and CET/CEST abbreviation for the
    series' standing 12:30 local start time on `iso_date` -- computed
    independently via `zoneinfo`'s own IANA tzdata rather than by
    re-implementing `site/.eleventy.js::parisStandingStart`'s `Intl`
    arithmetic. `datetime.tzname()` on a `zoneinfo`-aware value is exactly
    'CET'/'CEST' for this zone; unambiguous at 12:30, since Europe/Paris's
    DST transitions all happen in the small hours.

    This replaces a fixed `timezone(timedelta(hours=1))` that
    silently assumed CET year-round -- wrong for any edition falling in
    daylight-saving time, which three of this project's own five fixture
    editions do.
    """
    year, month, day = (int(part) for part in iso_date.split("-"))
    local = datetime(year, month, day, 12, 30, 0, tzinfo=_PARIS)
    offset = local.utcoffset()
    assert offset is not None, f"{iso_date} resolved no UTC offset in Europe/Paris"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    abbreviation = local.tzname()
    assert abbreviation, f"{iso_date} resolved no timezone abbreviation in Europe/Paris"
    return f"{sign}{hours:02d}:{minutes:02d}", abbreviation


def _expected_rfc822(iso_date: str) -> str:
    """The RFC-822/1123 `pubDate` `site/.eleventy.js`'s own `rfc822` filter
    should produce for `iso_date`, computed independently in Python rather
    than by re-implementing that filter's own `Date` arithmetic: the
    series' standing 12:30 Europe/Paris local start time
    (`_expected_paris_start`), converted to UTC/GMT -- exactly what
    JavaScript's `Date.prototype.toUTCString()` emits. Day and month names
    are a fixed, English lookup table rather than `strftime('%a'/'%b')`:
    those are locale-dependent in Python, and this project has already
    found one Python/JavaScript date-formatting mismatch it did not expect
    (D-20) -- a test that could pass or fail depending on the runner's own
    locale would be exactly that kind of hidden disagreement again.
    """
    year, month, day = (int(part) for part in iso_date.split("-"))
    local = datetime(year, month, day, 12, 30, 0, tzinfo=_PARIS)
    utc = local.astimezone(UTC)
    weekday = _ENGLISH_WEEKDAYS[utc.weekday()]
    month_name = _ENGLISH_MONTHS[utc.month - 1]
    return (
        f"{weekday}, {utc.day:02d} {month_name} {utc.year} "
        f"{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d} GMT"
    )


def _child_text(item: ET.Element, tag: str) -> str:
    """The text of a feed `<item>`'s `<tag>` child.

    `ElementTree.find` answers `None` for an element that is not there, and
    `.text` is `None` for one that is there but empty -- a feed item that
    lost its `<link>` or its `<pubDate>` is exactly the regression the
    tests below exist to catch, and it must read as a named failure here
    rather than as an `AttributeError` raised from inside a comprehension
    that says nothing about which element or which item was missing."""
    child = item.find(tag)
    assert child is not None, (
        f"a <item> in feed.xml carries no <{tag}> at all: "
        f"{ET.tostring(item, encoding='unicode')}"
    )
    assert child.text is not None, (
        f"a <item> in feed.xml carries an empty <{tag}>: "
        f"{ET.tostring(item, encoding='unicode')}"
    )
    return child.text


def test_feed_publication_dates_come_from_the_editions_own_date_never_the_clock(
    built_site: Path,
) -> None:
    """Never `new Date().toISOString().slice(0, 10)` (or any other read of
    the wall clock): a feed needs timestamps, and this proves they come
    from the data -- computed independently here from each edition's own
    `date`, not merely asserted present, so a regression to `new Date()`
    with no argument would fail this test on every rebuild rather than
    only on days it happens to disagree with `_expected_rfc822`.
    """
    events = _events_fixture()
    tree = ET.parse(built_site / "feed.xml")
    by_link = {
        _child_text(item, "link"): _child_text(item, "pubDate")
        for item in tree.findall(".//item")
    }
    assert by_link, "feed.xml carries no <item> to check pubDate on"
    for event in events:
        url = _absolute(f"/events/{str(event['id']).lower()}/")
        assert by_link[url] == _expected_rfc822(str(event["date"]))


@pytest.fixture(scope="module")
def built_site_no_events(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A wholly empty `events.json` -- the "empty feed" state, distinct
    from `built_site_no_past_editions`
    above (every event `scheduled`, i.e. zero *past* editions): this
    fixture has no editions at all, upcoming or past, which the committed
    fixture (never empty) can never exercise on its own. Same scratch-copy
    technique that fixture already uses.
    """
    if not _ELEVENTY_CMD.exists():
        pytest.skip(
            f"{_ELEVENTY_CMD.as_posix()} not found -- run `npm ci` in site/ "
            "before this suite (quality.yml's own python job now does)"
        )
    scratch_src = tmp_path_factory.mktemp("site-src-no-events") / "src"
    shutil.copytree(SITE_SRC, scratch_src)
    (scratch_src / "_data" / "events.json").write_text("[]", encoding="utf-8")
    out = tmp_path_factory.mktemp("site-build-no-events")
    try:
        subprocess.run(
            [
                "node",
                str(_ELEVENTY_CMD),
                f"--input={scratch_src.as_posix()}",
                f"--output={out.as_posix()}",
            ],
            cwd=ROOT / "site",
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        pytest.skip("node is not on PATH -- cannot build site/ for this suite")
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"site/ failed to build: {exc.stdout}\n{exc.stderr}"
        ) from exc
    return out


def test_the_feed_still_renders_valid_and_empty_with_no_editions_at_all(
    built_site_no_events: Path,
) -> None:
    """The empty-feed state: zero editions at all still produces a valid,
    well-formed RSS document with a channel and no items -- not a build
    error, and not malformed XML from an empty `{% for %}` loop.
    """
    tree = ET.parse(built_site_no_events / "feed.xml")
    channel = tree.find("./channel")
    assert channel is not None
    assert channel.find("title") is not None
    assert channel.find("link") is not None
    assert channel.find("description") is not None
    assert tree.findall(".//item") == []


def test_the_sitemap_still_lists_the_static_pages_with_no_editions_at_all(
    built_site_no_events: Path,
) -> None:
    """With zero editions there is also no year page (`archive.years` is
    empty) and no event page -- the sitemap should list exactly the pages
    that do not depend on there being any edition at all.
    """
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    tree = ET.parse(built_site_no_events / "sitemap.xml")
    actual = {loc.text for loc in tree.findall(".//s:url/s:loc", ns)}
    assert actual == {
        _absolute("/"),
        _absolute("/archives/"),
        _absolute("/propose/"),
        _absolute("/data/"),
        _absolute("/verify/"),
    }


# ------------------------------------------------------------------ #
# The public agenda feed (`/agenda.ics`) -- iCalendar,
# distinct from `feed.xml`'s RSS syndication feed above. Every test below
# parses the real, built `agenda.ics` bytes with `ics_reader.parse_calendar`
# -- a reader written independently of `site/.eleventy.js`'s own escape/
# fold functions (see that module's own docstring) -- rather than grepping
# the file as text, the same "parse it back the way a client would" standard
# `tools/tests/publication/test_agenda.py` already holds the internal feed to.
# ------------------------------------------------------------------ #


def test_agenda_feed_is_a_valid_calendar_with_one_scheduled_edition(
    built_site: Path,
) -> None:
    events = _events_fixture()
    scheduled = [e for e in events if e["status"] == "scheduled"]
    assert len(scheduled) == 1, (
        "this test assumes exactly one scheduled fixture edition"
    )

    raw = (built_site / "agenda.ics").read_bytes()
    parsed = parse_calendar(raw)
    assert parsed.calendar.properties["VERSION"] == "2.0"
    assert parsed.calendar.properties["PRODID"]
    assert parsed.calendar.properties["CALSCALE"] == "GREGORIAN"
    assert len(parsed.events) == 1

    event = parsed.events[0].properties
    expected_url = signup_url(str(scheduled[0]["id"]).lower())
    assert event["SUMMARY"] == scheduled[0]["title"]
    assert event["UID"] == expected_url
    assert event["LOCATION"] == expected_url
    assert event["URL"] == expected_url
    assert event["DTSTAMP"] == event["DTSTART"]


def test_agenda_feed_excludes_delivered_and_archived_editions(built_site: Path) -> None:
    """A calendar is for what has not happened yet: the committed fixture
    carries four non-`scheduled` editions (`delivered`/`archived`) besides
    the one `scheduled` one, and none of them may appear."""
    events = _events_fixture()
    not_scheduled_urls = {
        signup_url(str(e["id"]).lower()) for e in events if e["status"] != "scheduled"
    }
    assert not_scheduled_urls, (
        "fixture carries no non-scheduled edition to check against"
    )

    raw = (built_site / "agenda.ics").read_bytes()
    uids = {event.properties["UID"] for event in parse_calendar(raw).events}
    assert uids.isdisjoint(not_scheduled_urls)


def test_agenda_feed_is_pure_crlf(built_site: Path) -> None:
    raw = (built_site / "agenda.ics").read_bytes()
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")


def test_agenda_feed_rebuilds_byte_identical_from_unchanged_data(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The churn check: two builds from the same committed data must
    produce the same bytes -- otherwise every subscriber's calendar client
    would re-sync on every rebuild for no real reason, and hide an actual
    change in that noise. A real, second Eleventy build, not merely calling
    the same JavaScript function twice in this process: the whole point is
    to prove the *build* is deterministic, not only the function."""
    if not _ELEVENTY_CMD.exists():
        pytest.skip(
            f"{_ELEVENTY_CMD.as_posix()} not found -- run `npm ci` in site/ "
            "before this suite (quality.yml's own python job now does)"
        )
    outputs = []
    for i in range(2):
        out = tmp_path_factory.mktemp(f"site-build-churn-{i}")
        subprocess.run(
            ["node", str(_ELEVENTY_CMD), f"--output={out.as_posix()}"],
            cwd=ROOT / "site",
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        outputs.append((out / "agenda.ics").read_bytes())
    assert outputs[0] == outputs[1]


def test_the_agenda_feed_still_renders_valid_and_empty_with_no_editions_at_all(
    built_site_no_events: Path,
) -> None:
    raw = (built_site_no_events / "agenda.ics").read_bytes()
    parsed = parse_calendar(raw)
    assert parsed.calendar.properties["VERSION"] == "2.0"
    assert parsed.events == []


@pytest.fixture(scope="module")
def built_site_agenda_dst_cases(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One `scheduled` edition per date in the shared `paris-standing-start.
    json` fixture -- both sides of both DST transitions, both years -- plus
    one with a title long enough to force line folding. The committed
    fixture (`built_site`) carries only a single `scheduled` edition, dated
    once, so it cannot exercise the DST rule anywhere near a transition; a
    test that only checked that one date would pass against a feed that
    hard-typed a single offset (three of this project's own five real
    fixture editions fall in summer, but none of them sits *next to* a
    transition the way this fixture's eight dates deliberately do).
    """
    if not _ELEVENTY_CMD.exists():
        pytest.skip(
            f"{_ELEVENTY_CMD.as_posix()} not found -- run `npm ci` in site/ "
            "before this suite (quality.yml's own python job now does)"
        )
    fixture_path = ROOT / "tools" / "tests" / "fixtures" / "paris-standing-start.json"
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    scratch_src = tmp_path_factory.mktemp("site-src-agenda-dst") / "src"
    shutil.copytree(SITE_SRC, scratch_src)
    events = [
        {
            "id": f"DST-{i:02d}",
            "title": f"DST case {case['iso_date']}",
            "date": case["iso_date"],
            "status": "scheduled",
            "abstract": "",
            "photo_url": "",
            "bio": "",
            "linkedin": "",
            "seed_questions": "",
            "youtube_url": "",
            "registration_link": "",
            "forum_thread": "",
            "speaker_name": "Test Speaker",
            "speaker_affiliation": "",
            "speaker_country": "",
        }
        for i, case in enumerate(cases)
    ]
    # A 123-character title on the first case too, to prove folding and
    # escaping survive alongside a real DST computation, not only in
    # isolation: a comma (needs escaping) and a length that forces the
    # SUMMARY property line past the 75-octet fold limit on its own.
    long_title = (
        "Reproducible, open-source behavioural neuroscience: motion tracking, "
        "kinematics and cross-species comparison across borders"
    )
    assert len(long_title) == 123
    events[0]["title"] = long_title

    (scratch_src / "_data" / "events.json").write_text(
        json.dumps(events), encoding="utf-8"
    )
    out = tmp_path_factory.mktemp("site-build-agenda-dst")
    try:
        subprocess.run(
            [
                "node",
                str(_ELEVENTY_CMD),
                f"--input={scratch_src.as_posix()}",
                f"--output={out.as_posix()}",
            ],
            cwd=ROOT / "site",
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        pytest.skip("node is not on PATH -- cannot build site/ for this suite")
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"site/ failed to build: {exc.stdout}\n{exc.stderr}"
        ) from exc
    return out


def test_agenda_feed_dtstart_matches_the_shared_paris_offset_fixture(
    built_site_agenda_dst_cases: Path,
) -> None:
    fixture_path = ROOT / "tools" / "tests" / "fixtures" / "paris-standing-start.json"
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    raw = (built_site_agenda_dst_cases / "agenda.ics").read_bytes()
    parsed = parse_calendar(raw)
    assert len(parsed.events) == len(cases)
    by_uid = {event.properties["UID"]: event.properties for event in parsed.events}

    for i, case in enumerate(cases):
        url = signup_url(f"dst-{i:02d}")
        event = by_uid[url]
        # Independent of `site/.eleventy.js`: plain arithmetic on the
        # fixture's own offset string, not a second call into `Intl` or
        # `zoneinfo`.
        sign = 1 if case["offset"].startswith("+") else -1
        offset_hours = int(case["offset"][1:3])
        utc_hour = 12 - sign * offset_hours
        expected = f"{case['iso_date'].replace('-', '')}T{utc_hour:02d}3000Z"
        assert event["DTSTART"] == expected, case["iso_date"]


def test_agenda_feed_long_title_folds_and_round_trips_intact(
    built_site_agenda_dst_cases: Path,
) -> None:
    long_title = (
        "Reproducible, open-source behavioural neuroscience: motion tracking, "
        "kinematics and cross-species comparison across borders"
    )
    raw = (built_site_agenda_dst_cases / "agenda.ics").read_bytes()
    parsed = parse_calendar(raw)  # raises if any physical line exceeds 75 octets
    titles = {event.properties["SUMMARY"] for event in parsed.events}
    assert long_title in titles


# -------------------------------------------------------------------------- #
# The share banner reaches a stable, published address.
#
# `og:image`/`twitter:image` (whose comment on the
# block these tests exercise explains why the tag was left out at first)
# resolve to real content only once a banner file actually exists at the
# address the tag names -- and the committed fixture this module's own
# `built_site` builds from can never exercise that on its own: no fixture
# banner is committed to this repository (a committed image is in git
# history for ever, and the real
# pipeline that produces one, `visuals-production.yml`, only ever commits
# a *real*, currently-scheduled edition's banner; there is nothing this
# project should carry permanently as a stand-in for that).
#
# `built_site_with_share_banner`, below, is deliberately not built the way
# every other scratch-copy fixture above is (`--input=<scratch>/src`
# against the real, unmodified `site/`): `.eleventy.js`'s own
# `addPassthroughCopy('src/banners')` resolves its source relative to the
# *project root* (Eleventy's own documented behaviour, confirmed by hand),
# never relative to a CLI `--input` override,
# so a fixture that only swapped `src/` while still running the *real*
# `site/.eleventy.js` would carry the real repository's own (currently
# empty) `src/banners/`, not the scratch one this fixture writes a file
# into. This fixture instead copies the *whole* `site/` project --
# `.eleventy.js` and `package.json` included, `node_modules`/`_site`
# excluded (Node resolves Eleventy's own CLI script, and everything it
# `require`s, relative to that script's real install location, never to
# `cwd`, so nothing here needs its own copy of the dependency tree) -- and
# builds with no `--input` override at all, so the passthrough copy
# resolves against *this* scratch copy's own root. That is what lets one
# build exercise the real pipeline end to end: `src/_data/banners.js`
# reading the scratch `src/banners/` it was actually given, `.eleventy.js::
# eventBannerUrl` building this edition's real address from it, the
# templates (`event.njk`, `layout.njk`) emitting the tag, and Eleventy's
# own passthrough copy delivering the exact bytes into the built tree.
# -------------------------------------------------------------------------- #

_SITE_PROJECT_ROOT = ROOT / "site"

#: The smallest byte sequence libpng accepts as a real image (a 1x1, true
#: colour PNG) -- a stand-in for a real rendered banner, not one: these
#: tests prove the *pipeline* (a file present, a tag built, its bytes
#: delivered), never the composition itself (`test_visual.py` and the
#: pinned image comparison already own that). Fabricated bytes, never
#: this instance's own identity or any real speaker's likeness -- there is
#: nothing here for the consent gate or the "no personal data in the
#: repository" constraint to say anything about.
_MINIMAL_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture(scope="module")
def built_site_with_share_banner(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A full, isolated copy of `site/` (config and source, never its
    installed `node_modules` or a stale `_site`) with one banner file
    added for the fixture's own scheduled edition -- see this section's
    own module comment for why this fixture cannot use the plain
    `--input` override every other scratch fixture in this module uses.
    """
    if not _ELEVENTY_CMD.exists():
        pytest.skip(
            f"{_ELEVENTY_CMD.as_posix()} not found -- run `npm ci` in site/ "
            "before this suite (quality.yml's own python job now does)"
        )
    scratch_root = tmp_path_factory.mktemp("site-with-banner")
    scratch_site = scratch_root / "site"
    shutil.copytree(
        _SITE_PROJECT_ROOT,
        scratch_site,
        ignore=shutil.ignore_patterns("node_modules", "_site"),
    )
    # `.eleventy.js` reads this project's published
    # address from `instance/config.json`, one level above `site/` -- the
    # same way it already passthrough-copies `../assets/fonts`. A copy of `site/`
    # alone is no longer a buildable tree, and the build says so loudly
    # rather than guessing an address, which is the whole point of that
    # module refusing a default.
    (scratch_root / "instance").mkdir()
    shutil.copy2(
        ROOT / "instance" / "config.json", scratch_root / "instance" / "config.json"
    )
    # And `.eleventy.js` also reads the declaration
    # the *product* ships, to decide whether this instance is still
    # publishing the example's identity. Same reasoning one paragraph up,
    # one file further out: a tree carrying the declaration but not the
    # example it is compared against cannot answer the question, so the
    # build refuses rather than reporting "configured" -- which is the
    # answer that would have made the banner go quiet exactly where it was
    # needed (D-25).
    example = scratch_root / published.EXAMPLE_INSTANCE_PATH
    example.parent.mkdir(parents=True)
    shutil.copy2(ROOT / published.EXAMPLE_INSTANCE_PATH, example)
    # And the product's own Appropriate Legal Notice, which
    # `.eleventy.js` reads from the repository root through
    # `scripts/notice.cjs` and hands every template. Same reasoning again:
    # `notice()` refuses rather than rendering a colophon with three
    # quarters of a notice in it, because three quarters of a notice is
    # not one (D-29).
    shutil.copy2(ROOT / "NOTICE.json", scratch_root / "NOTICE.json")
    banners_dir = scratch_site / "src" / "banners"
    banners_dir.mkdir(parents=True, exist_ok=True)
    (banners_dir / f"{_the_one_scheduled_event_id()}.png").write_bytes(
        _MINIMAL_PNG_BYTES
    )
    out = tmp_path_factory.mktemp("site-build-with-banner")
    try:
        subprocess.run(
            ["node", str(_ELEVENTY_CMD), f"--output={out.as_posix()}"],
            cwd=scratch_site,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        pytest.skip("node is not on PATH -- cannot build site/ for this suite")
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"site/ failed to build: {exc.stdout}\n{exc.stderr}"
        ) from exc
    return out


_OG_IMAGE_DIMENSION_RE = {
    "width": re.compile(r'<meta property="og:image:width" content="([^"]*)"'),
    "height": re.compile(r'<meta property="og:image:height" content="([^"]*)"'),
}
_TWITTER_CARD_RE = re.compile(r'<meta name="twitter:card" content="([^"]*)"')
_TWITTER_IMAGE_RE = re.compile(r'<meta name="twitter:image" content="([^"]*)"')


def test_a_scheduled_editions_share_banner_produces_a_correctly_dimensioned_tag(
    built_site_with_share_banner: Path,
) -> None:
    """`og:image` and its card equivalent, with
    dimensions, pointing at the published address -- built from a real
    banner file this fixture placed for the fixture's own scheduled
    edition, not asserted against an absence the way the sibling
    test still correctly does for the ordinary, no-banner build
    (`built_site`, above)."""
    event_id = _the_one_scheduled_event_id()
    page = (
        built_site_with_share_banner / "events" / event_id / "index.html"
    ).read_text(encoding="utf-8")

    og_image = _OG_IMAGE_RE.search(page)
    assert og_image is not None, "no og:image tag on a page with a real banner file"
    expected_url = _absolute(f"/banners/{event_id}.png")
    assert og_image.group(1) == expected_url

    width = _OG_IMAGE_DIMENSION_RE["width"].search(page)
    height = _OG_IMAGE_DIMENSION_RE["height"].search(page)
    assert width is not None and height is not None
    # Tied to `formats.py::BANNER` itself, not a hand-typed "1200"/"630" a
    # second time: if that constant's own dimensions ever changed without
    # `site/.eleventy.js`'s own hand-copied `SHARE_IMAGE_WIDTH`/
    # `SHARE_IMAGE_HEIGHT` being updated to match, this is the assertion
    # that would catch the drift (the same D-14 cross-language technique
    # `_configured_path_prefix`/`_configured_site_origin` already use for
    # this file's other hand-typed constants).
    assert width.group(1) == str(int(BANNER.width))
    assert height.group(1) == str(int(BANNER.height))

    twitter_card = _TWITTER_CARD_RE.search(page)
    twitter_image = _TWITTER_IMAGE_RE.search(page)
    assert twitter_card is not None and twitter_card.group(1) == "summary_large_image"
    assert twitter_image is not None and twitter_image.group(1) == expected_url


def test_the_share_banners_tagged_address_resolves_to_the_exact_bytes_committed(
    built_site_with_share_banner: Path,
) -> None:
    """The other half of acceptance step 1: the address is not merely
    well-formed, it resolves inside the *built* tree, to the *same* bytes
    this fixture placed under `src/banners/` -- proof that Eleventy's own
    passthrough copy actually delivered this file, not merely that the
    filter built a plausible-looking URL. Mutate this away (comment out
    `.eleventy.js::addPassthroughCopy('src/banners')`) and this is the
    test that notices the image has vanished from the built tree --
    proven by hand.
    """
    event_id = _the_one_scheduled_event_id()
    page = (
        built_site_with_share_banner / "events" / event_id / "index.html"
    ).read_text(encoding="utf-8")
    og_image = _OG_IMAGE_RE.search(page)
    assert og_image is not None

    target = _built_file_for_absolute_url(
        og_image.group(1), built_site_with_share_banner
    )
    assert target.is_file(), (
        f"{og_image.group(1)!r} does not resolve to a file the build wrote"
    )
    assert target.read_bytes() == _MINIMAL_PNG_BYTES


def test_an_edition_with_no_banner_file_still_emits_no_og_image_tag(
    built_site_with_share_banner: Path,
) -> None:
    """The mixed case: one edition in this same build has a banner, every
    other one does not -- proof that a banner appearing for one edition
    does not leak an `og:image` tag onto pages that have none of their
    own, and that the "correct absence, not a broken pointer" choice
    still holds once the feature it was waiting
    for exists."""
    events = _events_fixture()
    other_ids = [
        str(e["id"]).lower()
        for e in events
        if str(e["id"]).lower() != _the_one_scheduled_event_id()
    ]
    assert other_ids, f"{_EVENTS_FIXTURE.as_posix()} carries only one event"
    for other_id in other_ids:
        page = (
            built_site_with_share_banner / "events" / other_id / "index.html"
        ).read_text(encoding="utf-8")
        assert _OG_IMAGE_RE.search(page) is None, (
            f"{other_id} carries no banner file but still got an og:image tag"
        )
        twitter_card = _TWITTER_CARD_RE.search(page)
        assert twitter_card is not None and twitter_card.group(1) == "summary"


def test_the_organiser_link_points_at_the_apps_real_published_base(
    built_site: Path,
) -> None:
    """The masthead and the footer both offer "Organiser access" on every
    page. That link used to be a hand-typed absolute address in
    `site/src/_data/site.json`, naming a repository that will not exist and
    a path that never did -- a dead link on every public page, and one that
    only became visible when the cockpit's own directory was renamed to
    match the repository it is.

    It is now derived through Eleventy's `url` filter like every other
    internal link, so the prefix comes from the one place
    `test_the_path_prefix_agrees_with_the_addresses_python_already_pins`
    already binds. This pins the other half: that it resolves to the base
    the application is *actually* built with, which
    `tools/tests/repository/test_workflows.py::EXPECTED_BASE_PATH` pins on the Vite
    side. Change the app's base without changing this link and one of the
    two tests fails rather than the site quietly offering a 404.
    """
    expected = f'href="{_pfx("/app/")}"'
    pages = sorted(built_site.rglob("*.html"))
    assert pages, "the build wrote no pages at all"

    carrying = [p for p in pages if expected in p.read_text(encoding="utf-8")]
    assert carrying, (
        f"no built page links the organiser application at {expected!r} -- "
        "the masthead and footer offer it on every page, so either the link "
        "moved or it stopped resolving against the published prefix"
    )

    stale = [
        p.relative_to(built_site).as_posix()
        for p in pages
        if "workshop-series" in p.read_text(encoding="utf-8")
    ]
    assert not stale, (
        "built pages still name the cockpit's old directory: "
        f"{stale} -- the repository is example-cockpit, is private, and never "
        "serves the application; the application is published under the "
        "showcase's own prefix"
    )


def test_the_build_emits_the_published_repositorys_own_readme(
    built_site: Path,
) -> None:
    """`publish-showcase.yml::refresh_published_site` deletes everything at the
    showcase's root except `.git` and `app/`, then copies this build's output
    in. So anything that exists only as a commit in that repository -- its
    README, its ignore file -- is destroyed by the first publish, and the
    public repository anyone lands on becomes a bare listing of built HTML
    with nothing saying what it is.

    They therefore have to be *emitted here*, on every build, which also
    makes this repository their single source. The README must keep saying
    the thing that stops someone editing the wrong tree: that the showcase
    holds no source.
    """
    readme = built_site / "README.md"
    assert readme.is_file(), (
        "the build wrote no README.md -- the first publish would wipe the "
        "showcase's own copy and leave the public repository unexplained"
    )
    text = readme.read_text(encoding="utf-8")
    assert "holds no source" in text, (
        "the published README no longer warns that the showcase holds no "
        "source; that warning is what stops someone editing the generated "
        "tree and losing the change on the next publish"
    )
    assert (built_site / ".gitignore").is_file(), (
        "the build wrote no .gitignore for the published repository"
    )


@pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(),
    reason=instance_identity.ONE_INSTANCE,
)
def test_no_page_of_a_configured_instance_carries_the_unconfigured_banner(
    built_site: Path,
) -> None:
    """The half that decides whether the other half
    survives: a banner that shows when it should not is deleted within a
    week, and it takes the real warning with it.

    This instance shares no declared value with the example the product
    ships (`test_published.py::test_this_repository_has_been_configured`),
    so `site.unconfigured` is empty here and `_includes/layout.njk` emits
    nothing at all -- not a hidden element, not an empty band, no markup.
    Asserted on the built pages rather than on the template, because what
    a visitor gets is the build.

    `tools/tests/repository/test_second_instance.py::test_the_second_instances_
    showcase_says_it_has_not_been_configured` is the same claim made the
    other way round, on a build that *is* unconfigured. Neither half means
    anything without the other.
    """
    pages = sorted(built_site.rglob("*.html"))
    assert len(pages) > 5, f"the showcase built almost no pages: {pages}"
    # The band's own class names, not the bare word: a future page about
    # configuring a duplicate could legitimately write "unconfigured" in
    # its prose, and a check that failed on that is a check somebody
    # loosens rather than reads.
    shouting = [
        page.relative_to(built_site).as_posix()
        for page in pages
        if any(
            marker in page.read_text(encoding="utf-8")
            for marker in ('class="unconfigured"', "unconfigured__eyebrow")
        )
    ]
    assert shouting == [], (
        "these pages warn that this instance has not been configured, and "
        f"it has: {shouting[:10]}"
    )


# -------------------------------------------------------------------------- #
# The licence notice, on the pages a visitor actually gets
# -------------------------------------------------------------------------- #


def test_every_published_page_carries_the_whole_licence_notice(
    built_site: Path,
) -> None:
    """D-29: what makes the colophon's last line carry any weight is that
    it is an Appropriate Legal Notice in the sense section 0 of the
    licence defines -- a copyright notice, the absence of a warranty, the
    permission to convey, and a link to the licence itself. Section 5 then
    obliges every modified version's interfaces to display one, **because
    this one's do**.

    Which is why this is asserted against the built pages and against
    every one of them, rather than against `_includes/layout.njk`. A
    template that references a field is not a page that displays it; a
    page added later with a layout of its own would carry no notice at all
    while the template check stayed green; and the decay this guards
    against is a clause at a time, so each field is looked for
    separately.

    `tools/tests/repository/test_notice.py` holds the declaration itself and the
    cockpit's own footer is held by `app/tests/notice.test.tsx` -- two
    interfaces, two obligations, and neither test says anything about the
    other's.
    """
    notice = json.loads((ROOT / "NOTICE.json").read_text(encoding="utf-8"))
    pages = sorted(built_site.rglob("*.html"))
    assert len(pages) > 5, f"the showcase built almost no pages: {pages}"

    fields = ("product", "copyright", "terms", "warranty", "licence_name")
    for page in pages:
        rendered = page.read_text(encoding="utf-8")
        where = page.relative_to(built_site).as_posix()
        missing = [name for name in fields if notice[name] not in rendered]
        assert missing == [], (
            f"{where} displays no {missing} -- a page carrying part of a "
            "notice carries no Appropriate Legal Notice at all"
        )
        assert notice["licence_url"] in rendered, (
            f"{where} does not say where to read the licence"
        )
        # `rel="license"` rather than the bare address: the link has to be
        # the licence link, not the same address happening to appear in a
        # sentence somewhere on the page.
        assert 'rel="license"' in rendered, (
            f"{where} carries the licence address but not as its licence link"
        )
