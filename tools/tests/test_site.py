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
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from convener_ops.certificate import VERIFICATION_BASE
from convener_ops.confirmation import CONTACT_EMAIL
from convener_ops.paths import repo_root
from convener_ops.registration import SIGNUP_BASE

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
_ELEVENTY_CONFIG = ROOT / "site" / ".eleventy.js"


def _configured_path_prefix() -> str:
    """`site/.eleventy.js`'s own `PATH_PREFIX` -- the one place this
    project's published address prefix (GitHub Pages serves this build's
    output under `/example-showcase/`, not at a bare domain root: no CNAME, no
    custom domain) is written down, feeding every template's `| url`
    filter call. Read here rather than hand-typed a second time, so every
    assertion below that expects a prefixed link fails immediately if this
    source value ever changes without the assertion being updated to
    match -- the same reason `_published_app_base` below reads
    `vite.config.ts` rather than restating its own literal.
    """
    text = _ELEVENTY_CONFIG.read_text(encoding="utf-8")
    match = re.search(r"PATH_PREFIX\s*=\s*'([^']+)'", text)
    assert match is not None, (
        f"{_ELEVENTY_CONFIG.as_posix()} no longer defines PATH_PREFIX -- "
        "every assertion in this module that expects a prefixed link would "
        "otherwise silently check against the wrong prefix"
    )
    return match.group(1)


def _pfx(path: str) -> str:
    """`path`, prefixed exactly the way Eleventy's own `url` filter prefixes
    every root-relative link this project's templates emit -- see
    `_configured_path_prefix`'s own docstring. `path` must itself start
    with `/`, the same contract every template's own `| url` filter call
    assumes."""
    assert path.startswith("/"), f"{path!r} is not root-relative"
    return _configured_path_prefix().rstrip("/") + path


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
    # Fix round 4: `href="/fonts/..."` moved behind Eleventy's `| url`
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
# the way the tests above read `layout.njk`'s and `style.css`'s: the
# template's own vocabulary never names the room link `zoom_link` -- the
# internal field a source scan for that literal (the technique
# `test_confirmation.py::test_no_public_announcement_template_publishes_
# the_room_link` already uses for the toolkit's Markdown templates) would
# have to look for -- so such a scan would stay green even with a leak.
# (`public_data.py::PUBLIC_FIELD_SOURCES` used to publish it as
# `registration_link`; task 9 stopped publishing it under any name at
# all, which makes this template-layer guard the only proof left that a
# future regression cannot slip a room-link-shaped value back onto a
# page.) Only the rendered page shows what a visitor would actually see.
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
    committed *fixture* carries -- a synthetic room-link-shaped column,
    kept here as a template-regression canary even though `public_data.py`
    no longer emits any column carrying a room link (task 9 removed it;
    that mapping used to publish `zoom_link` under this same column name).
    This test does not depend on the generator: it proves the template
    still refuses to render a room-link-shaped value if one ever reached
    the page's own data again, under whatever name.
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
    *name* `zoom_link` -- the speaker record's own internal field, which
    `public_data.py` never maps to any published column (task 9) -- must
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
    """Fix round 1: a visitor to an upcoming edition's page came to
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
# Fix round 2: `forum_thread` carries no status gate at all
# (`public_data.py::PUBLISHABLE_ALWAYS`, no companion to
# `RECORDING_STATUSES`), unlike `youtube_url` -- an operator can open a
# discussion thread ahead of the seminar, and round 1 dropped the only
# place an upcoming page could ever show it. The committed fixture's one
# `scheduled` event carries no `forum_thread` (that gap is exactly why the
# regression shipped), so the "with a thread" case below builds from a
# scratch copy of `site/src` with that field filled in, rather than from
# `built_site` -- the committed fixture is left untouched.
# -------------------------------------------------------------------------- #

#: Not a real forum: only ever read back out of the scratch build below.
_FIXTURE_ONLY_THREAD_URL = (
    "https://forum.example.test/t/mrg-05-fixture-only-thread/999"
)


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
    fix round 1's own rule against a returning "No thread yet", no
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
    it, and without resurrecting the recording section round 1 dropped.
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
    """The same D-14 binding `test_confirmation.py::test_the_contact_
    email_matches_the_signup_pages_own_notice` already holds against
    `SignupForm.tsx`, held here against `event.njk`'s own copy: phase 4
    already settled a real contact address, and it must never become a
    second, driftable copy typed by hand a third place."""
    source = _EVENT_TEMPLATE.read_text(encoding="utf-8")
    match = re.search(r"mailto:([^\"]+)", source)
    assert match is not None, "event.njk no longer names a contact address"
    assert match.group(1) == CONTACT_EMAIL


# -------------------------------------------------------------------------- #
# Task 8: archives, the speaker-proposal entry point, and the data page.
#
# Archives are filterable entirely without JavaScript: every option the
# filter bar offers (a year, "with a recording", "with a discussion") is a
# real, statically generated page reached by a plain link, never a script
# deciding what to show. `_ARCHIVE_TEMPLATES` and the tests below prove
# both directions of that claim -- that a filter genuinely narrows what is
# shown, and that no page it can reach carries a `<script>` tag at all.
#
# The speaker-proposal page is the public entry point to the pipeline
# `tools/convener_ops/proposal.py` already implements (a Tally form, its
# webhook verified and turned into a candidate lead) -- not a new
# mechanism, so this section proves the page links to the one already
# configured (`site.json`'s own `applyForm`), and that the home page's own
# two CTAs now go through it rather than around it.
#
# The data page cites phase 4's own data-protection record rather than
# restating it -- in particular it never repeats a retention figure, on
# purpose (two documents stating the same number independently disagree
# the day one changes and the other does not). What is pinned hard here,
# per the task brief, is that its link to that record actually resolves
# to something the app publishes: built from the same two constants that
# decide where the record lands (`registry.ts`'s own file path,
# `vite.config.ts`'s own published base) rather than a literal URL nothing
# would catch drifting, and proved once more by a real copy-handbook run
# against a scratch destination.
# -------------------------------------------------------------------------- #

_SITE_JSON = SITE_SRC / "_data" / "site.json"
_LAYOUT_TEMPLATE = SITE_SRC / "_includes" / "layout.njk"
_DONNEES_TEMPLATE = SITE_SRC / "donnees.njk"
_REGISTRY_TS = ROOT / "app" / "src" / "content" / "registry.ts"
_VITE_CONFIG = ROOT / "app" / "vite.config.ts"
_DOCS_DIR = ROOT / "docs"
_HANDBOOK_REGISTRY_MJS = ROOT / "app" / "scripts" / "handbook-registry.mjs"


def _site_config() -> dict[str, Any]:
    return json.loads(_SITE_JSON.read_text(encoding="utf-8"))


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
    # Fix round 4: each `href="/foo/"` moved behind Eleventy's `| url`
    # filter -- `href="{{ '/foo/' | url }}"` -- so a bare, unfiltered href
    # here would fail this pin exactly as surely as a missing link would.
    for href in ("/archives/", "/propose/", "/data/"):
        expected = "href=\"{{ '" + href + "' | url }}\""
        assert expected in layout, (
            f"layout.njk no longer links to {href} through the `url` filter"
        )


def test_home_pages_proposal_ctas_go_through_the_entry_page_not_around_it() -> None:
    """Task 8 brief: "build the entry point to that, not to something you
    invent" -- both "Propose a speaker" buttons on the home page point at
    `/propose/` now, not at the external form directly, so there is
    exactly one place the live form's address needs to change."""
    index_source = (SITE_SRC / "index.njk").read_text(encoding="utf-8")
    # Fix round 4: both CTAs now read `href="{{ '/propose/' | url }}"`.
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
    # Fix round 4: checked against the real, prefixed address this page
    # would carry if it wrongly linked to itself -- checking the old,
    # unprefixed literal would pass even if a `/example-showcase/archives/`
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
        # Fix round 4: same reasoning as the "All" pin above -- checked
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
    """The design decision this task's own brief asks to be pinned hard:
    filtering the archive never needs JavaScript. Every page the filter
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
    """Every event pushed to `scheduled` -- the archive's own empty state
    ("your states include an empty archive", task 8 brief), which the
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
    task 8's own "an archive with one entry" state, and, in the same
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


def test_propose_page_links_to_the_configured_proposal_form(built_site: Path) -> None:
    apply_form = _site_config()["applyForm"]
    page = (built_site / "propose" / "index.html").read_text(encoding="utf-8")
    assert f'href="{apply_form}"' in page


def test_propose_page_names_the_shared_contact_address(built_site: Path) -> None:
    page = (built_site / "propose" / "index.html").read_text(encoding="utf-8")
    assert f"mailto:{CONTACT_EMAIL}" in page


# ---- Information and data -------------------------------------------------


def test_the_data_pages_contact_address_matches_confirmations_own_constant() -> None:
    """The same D-14-style binding held above for `event.njk` -- one
    address, never a second, driftable copy typed by hand a third place."""
    source = _DONNEES_TEMPLATE.read_text(encoding="utf-8")
    matches = re.findall(r"mailto:([^\"]+)", source)
    assert matches, "donnees.njk no longer names a contact address"
    assert all(m == CONTACT_EMAIL for m in matches)


def test_the_data_page_never_restates_the_retention_figure() -> None:
    """The task brief's own reasoning, checked: this page cites the
    governance record rather than restating it, and in particular never
    repeats the "90 days" retention figure that record gives -- a second
    copy of that number here is precisely the drift risk the brief warns
    against, whether or not it agrees with the record today."""
    source = _DONNEES_TEMPLATE.read_text(encoding="utf-8")
    assert "90" not in source


def _governance_record_file() -> str:
    """The `file` `CONTENT_REGISTRY['governance/data-protection-record']`
    names, read as text. Independent of `handbook-registry.mjs`'s own
    identical-in-spirit extraction (task 1): this test must fail if either
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
    """`vite.config.ts`'s own production `base` -- the `/example-showcase/app/`
    every published asset URL is resolved against, including (fix round 4)
    the two islands' own, which used to read a different, undocumented-in-
    production `/app/` and now match this exactly (see that file's own
    comment for why they used to differ, and why that reasoning did not
    hold once the site itself became prefix-aware). Matched by its
    distinguishing `/example-showcase/` prefix rather than by position, so it
    stays the right one of the three `base:` literals in that file even if
    they are reordered.
    """
    text = _VITE_CONFIG.read_text(encoding="utf-8")
    match = re.search(r"base:\s*'(/example-showcase/[^']*)'", text)
    assert match is not None, (
        "vite.config.ts no longer sets a '/example-showcase/...' base -- "
        "donnees.njk's link to the governance record assumes this exact prefix"
    )
    return match.group(1)


#: Fix round 2 (the private-repository defect, D-15): `event.njk` used to
#: link the same data-protection record straight at `example-cockpit` -- the
#: *private* source repository -- which hands a public visitor GitHub's own
#: 404. `donnees.njk` already linked the published handbook address; both
#: templates are checked against the identical `expected` string below, so
#: neither can quietly disagree with the other again.
_GOVERNANCE_LINK_TEMPLATES = (_DONNEES_TEMPLATE, _EVENT_TEMPLATE)


def test_the_governance_record_link_agrees_on_every_page_that_makes_it() -> None:
    """One of the two things the task brief asks to be pinned hard: every
    page's link to the governance record resolves to something published,
    not to the private repository it actually lives in the source of. Built
    from the same two constants that decide where the record actually
    lands, rather than against a literal URL nothing would catch drifting
    out from under it -- and checked identically against every template
    that carries this link, so `event.njk` and `donnees.njk` cannot state
    two different answers to the same question again.
    """
    host = "https://example-instance.github.io"
    assert SIGNUP_BASE.startswith(f"{host}/example-showcase/"), (
        "registration.SIGNUP_BASE no longer shares this page's own "
        "assumed host -- update both together"
    )
    expected = f"{host}{_published_app_base()}handbook/{_governance_record_file()}"
    for template in _GOVERNANCE_LINK_TEMPLATES:
        source = template.read_text(encoding="utf-8")
        assert expected in source, (
            f"{template.relative_to(ROOT).as_posix()} does not link to "
            f"{expected!r} -- either the link drifted, or "
            "registry.ts/vite.config.ts changed under it"
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


@pytest.fixture(scope="module")
def published_handbook(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real run of `copyHandbook` (task 1's own allowlist filter,
    `app/scripts/handbook-registry.mjs`) against the real `docs/` tree,
    into a scratch destination -- proof that the file `donnees.njk` links
    to is actually among what the app publishes, not merely named
    correctly by the regex check above. `app/tests/copy-handbook.test.ts`
    already proves this exhaustively from the TypeScript side; this is
    the one file this task's own page depends on, checked once more from
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
# Fix round 4: the path-prefix defect. GitHub Pages serves this project's
# build output at <https://example-instance.github.io/example-showcase/>, not at
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
# address rather than diverging from it. The two tests below are the
# deliverable the task brief asks for: a built-output sweep that closes the
# whole class of defect (not just the instances one review happened to
# enumerate), and a cross-boundary pin that keeps the site's own prefix
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
    """D-14: this project's published path prefix must not become a
    fourth, independent literal. `registration.SIGNUP_BASE` and
    `certificate.VERIFICATION_BASE` already carry it (host and path both),
    and `vite.config.ts`'s own production `base` already pins the app's own
    half of it (`_published_app_base`, above) -- bound here to
    `site/.eleventy.js`'s `PATH_PREFIX` by a test, the same discipline that
    already binds those three literals to each other, rather than an
    import across the Python/JavaScript boundary this project builds no
    tooling to cross.
    """
    prefix = _configured_path_prefix()
    host = "https://example-instance.github.io"
    assert SIGNUP_BASE.startswith(f"{host}{prefix}"), (
        f"registration.SIGNUP_BASE ({SIGNUP_BASE!r}) no longer starts with "
        f"{host + prefix!r} -- update it and site/.eleventy.js's PATH_PREFIX "
        "together"
    )
    assert VERIFICATION_BASE.startswith(f"{host}{prefix}"), (
        f"certificate.VERIFICATION_BASE ({VERIFICATION_BASE!r}) no longer "
        f"starts with {host + prefix!r} -- update it and "
        "site/.eleventy.js's PATH_PREFIX together"
    )
    assert _published_app_base() == f"{prefix}app/", (
        f"vite.config.ts's own published base ({_published_app_base()!r}) no "
        f"longer agrees with site/.eleventy.js's PATH_PREFIX ({prefix!r}) -- "
        "the app and the site would publish to, and be addressed from, "
        "different places"
    )
