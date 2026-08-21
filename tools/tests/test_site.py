"""The showcase's templates, moved into this repository by phase 5's task 2.

`example-showcase` used to hold `index.njk`, `layout.njk`, `style.css`,
`.eleventy.js`, `package.json` and the self-hosted fonts directly -- source
outside this repository's own quality chain, tests and decision record (D-15:
private source, public artefact). They now live under `site/`, and this module
is the quality chain's own hold on the one guarantee a reconstruction already
broke once: no request to a third party from a published page (D-17).

Text assertions on the templates and stylesheet themselves, not on a build:
running `npm run build` here would need `site/`'s own `node_modules` present,
which this suite cannot assume and must not fetch -- exactly the kind of
network access `test_workflows.py`'s own docstring already refuses on the
workflow side of this same repository.
"""

from __future__ import annotations

import re
from pathlib import Path

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
