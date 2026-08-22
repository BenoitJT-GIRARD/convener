"""The showcase's templates, moved into this repository by phase 5's task 2.

`example-showcase` used to hold `index.njk`, `layout.njk`, `style.css`,
`.eleventy.js`, `package.json` and the self-hosted fonts directly -- source
outside this repository's own quality chain, tests and decision record (D-15:
private source, public artefact). They now live under `site/`, and this module
is the quality chain's own hold on the one guarantee a reconstruction already
broke once: no request to a third party from a published page (D-17).

Most of this module is text assertions on the templates and stylesheet
themselves, never a build. The task 5 section further down is the one
exception: it needs the real, *rendered* event pages to prove acceptance
criterion 2 (no room link on any public page), so it builds `site/` itself
into a scratch directory -- see `built_site`'s own docstring for why, and
for why that still touches no network (`site/`'s own `node_modules` must
already be installed, exactly the `npm ci` every other job that touches
`site/` already runs).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from convener_ops.confirmation import CONTACT_EMAIL
from convener_ops.paths import repo_root

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

#: Every text file a page actually ships: templates and the stylesheet. Fonts
#: (`.woff2`) are binary; licence files are third-party text nobody here
#: authored, so scanning them for our own supposed third-party requests would
#: be nonsensical, not just noisy.
_TEXT_GLOBS = ("**/*.njk", "**/*.css", "**/*.js")

#: D-17: the vitrine used to load Archivo and JetBrains Mono from Google,
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
    assert 'href="/fonts/' in layout, (
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
        "Mono -- D-17's chosen substitutes for Anonymous's own commercially "
        "licensed faces"
    )


# -------------------------------------------------------------------------- #
# Task 5: the event page -- one addressable page per edition (D-19), no
# room link on any public page (acceptance criterion 2), and the phase 4
# notice ahead of the reserved place for task 6's registration island.
#
# The address and no-room-link checks below build the real `site/` project
# with its own committed fixture (`src/_data/events.json`) and sweep the
# *built* output, deliberately, rather than reading `event.njk`'s source
# the way the tests above read `layout.njk`'s and `style.css`'s: the public
# schema calls the room link `registration_link`
# (`public_data.py::PUBLIC_FIELD_SOURCES`), never `zoom_link`, so a source
# scan for that literal -- the technique
# `test_confirmation.py::test_no_public_announcement_template_publishes_
# the_room_link` already uses for the toolkit's Markdown templates -- would
# stay green even with a leak, because the string it looks for never
# appears in this page's own vocabulary at all. Only the rendered page
# shows what a visitor would actually see.
# -------------------------------------------------------------------------- #

_EVENT_TEMPLATE = SITE_SRC / "event.njk"
_EVENTS_FIXTURE = SITE_SRC / "_data" / "events.json"
_ELEVENTY_CMD = ROOT / "site" / "node_modules" / "@11ty" / "eleventy" / "cmd.js"


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
    script (`node cmd.js`), never `npm run build` or `npx`: no shell, no
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
    """Acceptance criterion 2, absolute: no room link on any public page
    -- the room link is delivered only by the confirmation e-mail. Swept
    across every file the build wrote, not only the event page's own
    output: the claim is about *any* public page, and a leak from, say,
    the homepage's "up next" card would be exactly as real a breach.

    Sweeps for the literal, non-empty `registration_link` value(s) the
    fixture carries -- `public_data.py` publishes `zoom_link` under
    that column name, and only while an event is `scheduled`
    (`PUBLIC_FIELD_SOURCES`, `to_public`'s own status gate) -- which is
    what a template regression would actually leak onto a page.
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
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            continue  # a font or another binary passthrough copy
        for link in room_links:
            if link in text:
                offending.append((path.relative_to(built_site).as_posix(), link))
    assert offending == [], f"room link leaked into the built site: {offending}"


def test_a_built_html_page_never_mentions_the_internal_field_name_either(
    built_site: Path,
) -> None:
    """Belt and braces beside the value-based sweep above: even the
    *name* `zoom_link` -- the speaker record's own internal field,
    `public_data.py`'s allowlist renames it to `registration_link` before
    anything public ever sees it -- must never appear on a built page,
    which would mean some future template reached past that renaming
    boundary and read the private record directly.
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
    """Phase 4 spec §4 ("Formalités"): a one-screen notice on the event
    page, *before* the form. Task 6 mounts the registration island itself
    (`app/src/islands/signup/`); until then this page reserves its place
    -- this test pins the ordering promise task 6 must not quietly invert
    by mounting the island above the notice instead of beneath it.
    """
    event_id = _the_one_scheduled_event_id()
    page = (built_site / "events" / event_id / "index.html").read_text(encoding="utf-8")
    notice_at = page.index("Before you register")
    placeholder_at = page.index('id="registration-form"')
    assert notice_at < placeholder_at


def test_the_event_pages_contact_address_matches_confirmations_own_constant() -> None:
    """The same D-14 binding `test_confirmation.py::test_the_contact_
    email_matches_the_signup_pages_own_notice` already holds against
    `SignupForm.tsx`, held here against `event.njk`'s own copy: phase 4
    already settled a real contact address, and it must never become a
    second, driftable copy typed by hand a third place."""
    source = _EVENT_TEMPLATE.read_text(encoding="utf-8")
    match = re.search(r"mailto:([^\"]+)", source)
    assert match is not None, "event.njk no longer names a contact address"
    assert match.group(1) == CONTACT_EMAIL
