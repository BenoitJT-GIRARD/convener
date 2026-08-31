"""The announcement composition -- pinning the properties that make it
compose rather than a byte-identical page, the same discipline
`motifs/test_ribbon.py` already applies to the ribbon (see that file's
own docstring). Five groups matter most, because each is a defect that
would otherwise be
invisible in a single screenshot: a long title staying inside its band, a
missing portrait composing rather than breaking, every colour coming from
`instance/data/brand.json` rather than a hand-typed literal, the date line
reflecting the edition's real Europe/Paris offset -- pinned for a winter
*and* a summer edition, because a test that only ever checked a winter date
would pass against the reference poster's own hard-typed "(CET)" defect --
and every text element staying inside a safe area that
clears the ribbon on both sides, checked against `motifs/ribbon.py::waypoints`
itself rather than against a rendered pixel (see
`test_the_safe_area_clears_every_ribbon_waypoint`'s own docstring for why a
pixel could not be part of this suite).
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Final

import pytest
from conftest import speaker

import convener_ops.publication.visual as visual
from convener_ops.declaration.paths import repo_root
from convener_ops.publication.formats import BANNER, FORMATS, PRINT, SQUARE
from convener_ops.publication.motifs.ribbon import waypoints
from convener_ops.publication.public_data import to_public
from convener_ops.publication.visual import (
    _AFFILIATION_FONT_MAX_VMIN,
    _AFFILIATION_FONT_MIN_VMIN,
    _NAME_FONT_MAX_VMIN,
    _NAME_FONT_MIN_VMIN,
    _TITLE_FONT_MAX_MRG,
    _TITLE_FONT_MIN_MRG,
    FIXTURE_ANNOUNCEMENT,
    Announcement,
    _affiliation_font_size,
    _frame_photo_html,
    _motif_content_right_margin,
    _motif_safe_margins,
    _name_font_size,
    _title_font_size,
    date_line,
    is_wide,
    paris_standing_start,
    render_announcement,
)

ROOT = repo_root()

#: A small canvas is enough for every structural assertion below and keeps
#: the suite fast; nothing here inspects pixels, only the generated markup
#: and CSS text (rendering to an actual image is the pinned renderer's own
#: job, never inside this test suite -- no test
#: here touches a browser or the network).
_W, _H = 1200.0, 1200.0


def _announcement(**overrides: Any) -> Announcement:
    """Derived from `visual.FIXTURE_ANNOUNCEMENT` rather than a second,
    hand-typed identity: the versioned reference images are
    rendered from that exact constant, so this suite's own default state
    and the one a reviewer sees in a reference PNG are provably the same
    fixture, not two that happen to agree today."""
    return replace(FIXTURE_ANNOUNCEMENT, **overrides)


def _rule_block(css: str, selector: str) -> str:
    """The body of one flat CSS rule (no nested braces), found by its exact
    selector at the start of a line. Mirrors `test_brand.py::_rule_block`
    exactly -- a small, generic utility, not a shared notion worth
    importing across two otherwise-independent test modules."""
    pattern = re.compile(r"(?:^|\n)\s*" + re.escape(selector) + r"\s*\{([^}]*)\}")
    match = pattern.search(css)
    assert match, f"no rule found for selector {selector!r}"
    return match.group(1)


# ---------------------------------------------------------------------------
# The date line: real Europe/Paris offset, pinned for a winter AND a summer
# edition (three of this project's own five fixture editions are in DST --
# `site/src/_data/events.json` -- so a test that only ever checked a winter
# date would pass against a hard-typed "(CET)", exactly the reference
# poster's own defect).
# ---------------------------------------------------------------------------

#: The exact five dates `site/src/_data/events.json` carries, with the
#: offset and abbreviation each one resolves to in Europe/Paris at this
#: project's standing 12:30 local start time -- verified once, by hand,
#: against the real calendar (Europe/Paris observes CEST from the last
#: Sunday of March to the last Sunday of October) rather than recomputed
#: here through the same `zoneinfo` call the implementation itself makes,
#: which would only restate the code under test, not check it against
#: anything independent.
_FIXTURE_EDITIONS = (
    ("2025-02-05", "+01:00", "CET"),  # winter
    ("2025-06-12", "+02:00", "CEST"),  # summer
    ("2026-03-12", "+01:00", "CET"),  # winter (before 2026's DST start, Mar 29)
    ("2026-04-02", "+02:00", "CEST"),  # summer
    ("2026-09-10", "+02:00", "CEST"),  # summer
)


@pytest.mark.parametrize("iso_date, offset, abbreviation", _FIXTURE_EDITIONS)
def test_paris_standing_start_matches_the_known_offset_for_every_fixture_edition(
    iso_date: str, offset: str, abbreviation: str
) -> None:
    talk_date = date.fromisoformat(iso_date)
    assert paris_standing_start(talk_date) == (offset, abbreviation)


def test_the_fixture_actually_covers_both_seasons() -> None:
    """An empty or winter-only fixture would make the parametrized test
    above pass for the wrong reason -- see this module's own docstring."""
    abbreviations = {abbreviation for _, _, abbreviation in _FIXTURE_EDITIONS}
    assert abbreviations == {"CET", "CEST"}


def test_date_line_states_the_computed_weekday_and_zone_in_winter() -> None:
    assert date_line(date(2026, 3, 12)) == "Thursday, 12 March 2026 at 12:30 CET"


def test_date_line_states_the_computed_weekday_and_zone_in_summer() -> None:
    assert date_line(date(2026, 4, 2)) == "Thursday, 2 April 2026 at 12:30 CEST"


def test_date_line_computes_the_real_weekday_not_a_fixed_one() -> None:
    # 2025-02-05 is a Wednesday, not the reference poster's own "Thursday" --
    # a value left over from whichever edition it was hand-drawn for.
    assert date_line(date(2025, 2, 5)).startswith("Wednesday, 5 February 2025")


def test_paris_standing_start_never_returns_an_empty_offset_or_abbreviation() -> None:
    offset, abbreviation = paris_standing_start(date(2026, 1, 1))
    assert offset and abbreviation


class _NoOffsetZone(tzinfo):
    """A `tzinfo` that resolves neither an offset nor a name -- real
    `zoneinfo.ZoneInfo` never does this for an aware `datetime`, so the two
    guards in `paris_standing_start` that handle it are otherwise
    unreachable through the public function. Monkeypatching `visual.PARIS`
    to this is the only way to exercise them at all."""

    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None


class _OffsetNoNameZone(tzinfo):
    """Resolves an offset but no abbreviation -- the second guard, on its
    own, without also tripping the first."""

    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return timedelta(hours=1)

    def tzname(self, dt: datetime | None) -> str | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return timedelta(0)


def test_paris_standing_start_raises_when_the_zone_resolves_no_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(visual, "PARIS", _NoOffsetZone())
    with pytest.raises(ValueError, match="UTC offset"):
        paris_standing_start(date(2026, 1, 1))


def test_paris_standing_start_raises_when_the_zone_resolves_no_abbreviation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(visual, "PARIS", _OffsetNoNameZone())
    with pytest.raises(ValueError, match="abbreviation"):
        paris_standing_start(date(2026, 1, 1))


# ---------------------------------------------------------------------------
# A long title composes: it wraps and the band grows, it does not overflow
# or get clipped (D-08's own lived problem).
# ---------------------------------------------------------------------------


def test_the_title_shrinks_as_it_grows_past_the_soft_limit() -> None:
    short = "A short title"
    long_title = "A" * 200
    assert _title_font_size(short) == _TITLE_FONT_MAX_MRG
    assert _title_font_size(long_title) == _TITLE_FONT_MIN_MRG
    assert _title_font_size(long_title) < _title_font_size(short)


def test_the_talk_title_band_can_wrap_and_grow_rather_than_clip() -> None:
    """The two CSS properties that make "compose instead of overflow" true:
    wrapping is enabled on the title paragraph, and the band that holds it
    is never given a fixed height that wrapped text could be clipped
    against -- only padding, so a flex `auto` band grows to fit."""
    doc = render_announcement(_announcement(), width=_W, height=_H, root=ROOT)
    title_rule = _rule_block(doc, ".band--talk-title p")
    assert "overflow-wrap" in title_rule
    assert "nowrap" not in title_rule
    assert "text-overflow" not in title_rule
    band_rule = _rule_block(doc, ".band")
    assert "height" not in band_rule


def test_a_very_long_title_renders_the_full_text_uncut() -> None:
    long_title = (
        "A very long and unnecessarily verbose academic talk title that "
        "goes on and on about many different subtopics including "
        "behaviour, cognition, ethology, neuroscience, computation, "
        "statistics, methodology, reproducibility, open science practices, "
        "and cross-species comparisons in the wild"
    )
    doc = render_announcement(
        _announcement(title=long_title), width=_W, height=_H, root=ROOT
    )
    # The full title text reaches the page -- nothing ellipsised, nothing
    # truncated -- and the "compose, not overflow" mechanism used to fit it
    # (the smallest available size) is the one actually applied.
    assert long_title in doc
    assert f"font-size: {_TITLE_FONT_MIN_MRG}vw" in doc
    assert "…" not in doc
    assert "text-overflow" not in _rule_block(doc, ".band--talk-title p")


# ---------------------------------------------------------------------------
# A missing portrait composes a placeholder -- never a hole, never a broken
# <img>.
# ---------------------------------------------------------------------------


def test_no_portrait_renders_a_placeholder_not_an_img_tag() -> None:
    html = _frame_photo_html(None, "Jane Doe")
    assert "<img" not in html
    assert "frame__placeholder" in html
    assert "J" in html


def test_no_portrait_and_no_name_still_renders_a_placeholder() -> None:
    html = _frame_photo_html(None, "")
    assert "<img" not in html
    assert "frame__placeholder" in html


def test_a_portrait_renders_an_img_tag_carrying_the_given_source() -> None:
    html = _frame_photo_html("data:image/png;base64,AAAA", "Jane Doe")
    assert '<img src="data:image/png;base64,AAAA"' in html
    assert "frame__placeholder" not in html


def test_the_full_page_has_no_portrait_at_all_when_none_is_given() -> None:
    # The class name alone would also match the page's own static CSS rule
    # for it, present in every render -- what must actually appear is the
    # placeholder *element*.
    doc = render_announcement(
        _announcement(portrait_data_uri=None), width=_W, height=_H, root=ROOT
    )
    assert "<img" not in doc
    assert '<div class="frame__placeholder"' in doc


def test_withheld_consent_reaches_the_composition_as_no_portrait_end_to_end() -> None:
    """The calling convention this module's own docstring asks for: feed
    `render_announcement` the *public projection* (`public_data.to_public`),
    never the raw record -- and prove that alone is enough to withhold a
    portrait whose consent has not been granted, with no second check to
    bypass here."""
    raw = speaker(
        status="scheduled",
        edition_code="MRG-09",
        date="2026-03-12",
        photo_url="https://example.org/ada.jpg",
        publication={
            "consent": "pending",
            "approved_by": "",
            "approved_on": "",
            "objections": [],
            "outcome": "",
        },
    )
    public_row = to_public([raw])[0]
    assert public_row["photo_url"] == ""  # the gate itself, proved once more

    doc = render_announcement(
        _announcement(portrait_data_uri=public_row["photo_url"] or None),
        width=_W,
        height=_H,
        root=ROOT,
    )
    assert "<img" not in doc
    assert '<div class="frame__placeholder"' in doc


# ---------------------------------------------------------------------------
# Every colour comes from instance/data/brand.json's generated block, never a
# hand-typed literal.
# ---------------------------------------------------------------------------

#: The exact mapping `visual._root_css_block` uses -- reimplemented here,
#: independently, rather than imported: a bug in that mapping could not
#: then also hide from the test meant to catch it (the same reasoning
#: `test_brand.py::_all_brand_colours` gives for its own, near-identical
#: duplication).
_ROOT_VAR_SOURCES = {
    "--paper": ("colour", "white"),
    "--surface": ("colour", "band"),
    "--surface-2": ("colour", "field"),
    "--ink": ("colour", "ink"),
    "--ink-mute": ("colour", "ink_muted"),
    "--ink-faint": ("derived", "ink_faint"),
    "--field": ("colour", "field"),
    "--field-text": ("derived", "field_text"),
    "--field-tint": ("derived", "field_tint"),
    "--dominant": ("colour", "dominant"),
    "--dominant-hover": ("derived", "dominant_hover"),
    "--dominant-tint": ("derived", "dominant_tint"),
    "--rule": ("colour", "rule"),
    "--rule-strong": ("derived", "rule_strong"),
    "--white": ("colour", "white"),
    "--black": ("colour", "black"),
}


def _brand() -> dict[str, Any]:
    return dict(
        json.loads(
            (ROOT / "instance" / "data" / "brand.json").read_text(encoding="utf-8")
        )
    )


def _root_block_text(doc: str) -> str:
    match = re.search(r":root\s*\{(.*?)\n\s*\}\s*\n\s*\*", doc, re.S)
    assert match, "no :root block found in the rendered page"
    return match.group(1)


def test_colours_in_the_root_block_match_brand_json_exactly() -> None:
    brand = _brand()
    doc = render_announcement(_announcement(), width=_W, height=_H, root=ROOT)
    root_block = _root_block_text(doc)
    for var, (section, key) in _ROOT_VAR_SOURCES.items():
        expected = brand[section][key]
        assert re.search(rf"{re.escape(var)}:\s*{re.escape(expected)};", root_block), (
            f"{var} in the rendered :root block is not {expected!r} "
            f"(instance/data/brand.json::{section}.{key})"
        )


#: The two attributes a colour may legitimately reach at render time:
#: the drawing's own `stroke`, filled in from `brand.motif_stroke(root)`,
#: and the lock-up device's own dot, filled in from `motif.logo_dots`
#: (`publication/lockup.py`). Neither is hand-typed in any module's
#: source -- what this guard is for is a colour retyped rather than read.
_FILLED_IN_AT_RENDER: Final = re.compile(r'(?:stroke|fill)="#[0-9a-fA-F]{6}"')


def _outside_the_root_block(doc: str) -> str:
    """Everything but the generated `:root` block and the two attributes
    a colour is legitimately filled into."""
    return _FILLED_IN_AT_RENDER.sub(
        'EXCLUDED="EXCLUDED"', doc.replace(_root_block_text(doc), "")
    )


def test_no_brand_colour_hand_typed_outside_root_or_motif_stroke() -> None:
    """The same guard `test_brand.py` already runs on the downloadable
    templates and the two generated stylesheets, applied to this third
    consumer of `instance/data/brand.json`."""
    brand = _brand()
    colours = {value for value in brand["colour"].values() if isinstance(value, str)}
    colours |= {value for value in brand["derived"].values() if isinstance(value, str)}
    doc = render_announcement(_announcement(), width=_W, height=_H, root=ROOT)

    rest = _outside_the_root_block(doc)

    pattern = re.compile("|".join(re.escape(c) for c in colours), re.IGNORECASE)
    match = pattern.search(rest)
    assert match is None, (
        f"{match.group(0) if match else ''} is hand-typed outside :root"
    )


# ---------------------------------------------------------------------------
# A long speaker name and affiliation: shrink, and wrap rather than an
# ellipsis, on the same "compose, not break" reasoning as the title.
# ---------------------------------------------------------------------------


def test_the_name_and_affiliation_shrink_as_they_grow() -> None:
    short_name, long_name = "Ada", "A" * 200
    assert _name_font_size(short_name) == _NAME_FONT_MAX_VMIN
    assert _name_font_size(long_name) == _NAME_FONT_MIN_VMIN
    assert _name_font_size(long_name) < _name_font_size(short_name)

    short_aff, long_aff = "MIT", "B" * 200
    assert _affiliation_font_size(short_aff) == _AFFILIATION_FONT_MAX_VMIN
    assert _affiliation_font_size(long_aff) == _AFFILIATION_FONT_MIN_VMIN
    assert _affiliation_font_size(long_aff) < _affiliation_font_size(short_aff)


def test_a_long_name_and_affiliation_wrap_rather_than_being_ellipsised() -> None:
    doc = render_announcement(
        _announcement(
            speaker_name="Maria Alexandra Konstantinopoulou-Papadopoulos",
            speaker_affiliation=(
                "Interdisciplinary Institute for the Study of Animal "
                "Behaviour, Cognition and Computational Ethology"
            ),
        ),
        width=_W,
        height=_H,
        root=ROOT,
    )
    name_rule = _rule_block(doc, ".frame__name")
    affiliation_rule = _rule_block(doc, ".frame__affiliation")
    for rule in (name_rule, affiliation_rule):
        assert "overflow-wrap" in rule
        assert "nowrap" not in rule
        assert "text-overflow" not in rule
    assert "Konstantinopoulou-Papadopoulos" in doc
    assert "Computational Ethology" in doc
    assert "…" not in doc


def test_an_empty_affiliation_omits_the_second_caption_line() -> None:
    # The class name alone is not enough to assert on: it also names the
    # static CSS rule, present in every render regardless of content. What
    # must be absent is the *element* -- the span the caption would need.
    doc = render_announcement(
        _announcement(speaker_affiliation=""), width=_W, height=_H, root=ROOT
    )
    assert '<span class="frame__affiliation"' not in doc


# ---------------------------------------------------------------------------
# Non-Latin characters, in a title or a name, pass through intact.
# ---------------------------------------------------------------------------


def test_non_latin_title_and_name_pass_through_intact() -> None:
    doc = render_announcement(
        _announcement(
            title="Понимание поведения: нейроэтологический подход",
            speaker_name="田中 陽子",
            speaker_affiliation="東京大学",
        ),
        width=_W,
        height=_H,
        root=ROOT,
    )
    assert "Понимание поведения: нейроэтологический подход" in doc
    assert "田中 陽子" in doc
    assert "東京大学" in doc
    assert '<meta charset="utf-8">' in doc


# ---------------------------------------------------------------------------
# Escaping, validation, and the reserved registration-code slot.
# ---------------------------------------------------------------------------


def test_title_name_and_affiliation_are_html_escaped() -> None:
    doc = render_announcement(
        _announcement(
            title="<script>alert(1)</script>",
            speaker_name="<b>Ada</b>",
            speaker_affiliation="Tom & Jerry's <lab>",
        ),
        width=_W,
        height=_H,
        root=ROOT,
    )
    assert "<script>" not in doc
    assert "&lt;script&gt;" in doc
    assert "<b>Ada</b>" not in doc
    assert "&lt;b&gt;Ada&lt;/b&gt;" in doc
    assert "Tom &amp; Jerry" in doc


def test_render_announcement_rejects_a_non_positive_canvas() -> None:
    with pytest.raises(ValueError, match="positive"):
        render_announcement(_announcement(), width=0, height=100, root=ROOT)
    with pytest.raises(ValueError, match="positive"):
        render_announcement(_announcement(), width=100, height=-1, root=ROOT)


def test_the_registration_code_slot_is_reserved_exactly_once() -> None:
    doc = render_announcement(_announcement(), width=_W, height=_H, root=ROOT)
    assert doc.count("data-registration-code-slot") == 1
    assert "registration-code-slot" in doc


def test_announcement_defaults_portrait_to_none() -> None:
    ann = Announcement(
        title="t",
        talk_date=date(2026, 1, 1),
        speaker_name="n",
        speaker_affiliation="a",
        event_id="mrg-1",
    )
    assert ann.portrait_data_uri is None


def test_an_empty_title_falls_back_rather_than_rendering_a_blank_band() -> None:
    doc = render_announcement(_announcement(title=""), width=_W, height=_H, root=ROOT)
    assert "Talk title" in doc


def test_the_ribbon_is_painted_last_so_it_sits_on_top_of_everything() -> None:
    doc = render_announcement(_announcement(), width=_W, height=_H, root=ROOT)
    assert doc.rindex("motif-overlay") > doc.rindex("registration-code-slot")
    assert doc.rindex("</svg>") > doc.rindex("</figure>")


def test_the_ribbon_geometry_matches_the_requested_canvas() -> None:
    doc = render_announcement(_announcement(), width=900.0, height=1200.0, root=ROOT)
    assert 'viewBox="0 0 900 1200"' in doc


# ---------------------------------------------------------------------------
# Text stays inside a safe area that clears the ribbon on both
# sides -- in every early render, it did not (the ribbon struck
# through "READ TOGETHER", "Join the discussion" and the talk
# title, on both left and right). See the module docstring's "Why a safe
# area, and why derived rather than hand-typed".
# ---------------------------------------------------------------------------


def test_the_safe_area_clears_every_ribbon_waypoint() -> None:
    """The property this whole fix rests on: no on-curve point of the
    ribbon -- either loop's own arc, the left tail's fitted bulge, the
    points where the stroke crosses an edge -- lies inside the horizontal
    band the page reserves for text. Checked against `motifs/ribbon.py::waypoints`
    directly (imported here, not reached through `_motif_safe_margins`'s
    own call to it) so a bug shared by both functions could not hide from
    this test the way it could if this re-derived the same numbers through
    the function under test.

    This pins the property, not a pixel: nothing here renders an image or
    opens a browser (no test in this module does -- see the module
    docstring), because the collisions were only ever visible in a
    screenshot, not in this module's own generated markup -- checking the
    geometry that produces the collision is what makes the property visible
    to a test at all.

    Checked at three aspect ratios, not only the square:
    `_motif_safe_margins` is built to survive a change of aspect ratio
    (see the module docstring's own argument for why), and a
    property that only happened to hold at one aspect ratio would not be
    evidence of that.
    """
    for width, height in ((1200.0, 1200.0), (1200.0, 630.0), (900.0, 1200.0)):
        left_vw, right_vw = _motif_safe_margins(width, height, ROOT)
        left_px = left_vw / 100.0 * width
        right_px = right_vw / 100.0 * width

        w = waypoints(width, height)
        left_points = (
            w.left_top_entry,
            w.left_top_exit,
            *w.left_loop_arc,
            w.left_tail_bulge,
            w.left_bottom_exit,
        )
        right_points = (
            *w.right_loop_arc,
            w.right_loop_out,
            w.right_tail_start,
            w.right_tail_bulge,
            w.right_tail_exit,
        )
        deepest_left = max(x for x, _y in left_points)
        deepest_right = width - min(x for x, _y in right_points)

        assert deepest_left <= left_px, (width, height, deepest_left, left_px)
        assert deepest_right <= right_px, (width, height, deepest_right, right_px)


def test_the_safe_area_is_not_the_whole_canvas() -> None:
    """A guard against the property test above passing for the wrong
    reason: `_motif_safe_margins` could clear every waypoint trivially by
    reserving the entire canvas for margin, leaving no room for content at
    all. Both margins must leave a real content strip -- this project's
    reference poster leaves roughly 72% of the width for content; this only
    checks that *some* substantial majority remains, not that exact figure,
    since this fix's own margins are deliberately more conservative than the
    reference's (see the module docstring)."""
    left_vw, right_vw = _motif_safe_margins(_W, _H, ROOT)
    assert left_vw + right_vw < 50.0


def test_every_text_bearing_rule_reads_the_derived_safe_area() -> None:
    """`_motif_safe_margins` returning the right numbers is not enough on
    its own -- every rule a collision was ever traced to (the wordmark and
    talk-title bands share `.band`, the hero section, the date line) has to
    actually spend them, not fall back to a fixed `vw`
    that happens to look similar. `.content` and `.register` (the
    band sibling to `.content` -- see that module's own "Why the code can
    never be clipped" section) are the two rules that read a *narrower*
    right margin, `--safe-r-content` -- `_motif_content_right_margin`'s own
    docstring explains why -- but still read the full `--safe-l` on their
    own left."""
    doc = render_announcement(_announcement(), width=_W, height=_H, root=ROOT)
    for selector in (".band", ".hero", ".date-line"):
        rule = _rule_block(doc, selector)
        assert "var(--safe-l)" in rule
        assert "var(--safe-r)" in rule
    for selector in (".content", ".register"):
        rule = _rule_block(doc, selector)
        assert "var(--safe-l)" in rule
        assert "var(--safe-r-content)" in rule
        assert "var(--safe-r)" not in rule


def test_the_register_band_is_never_squeezed_by_flexible_content() -> None:
    """A carried defect: on the tallest content this page ever
    composes (a long, heavily-wrapped non-Latin title), the registration
    slot used to run off the bottom edge of the canvas -- see the module
    docstring's "Why the code can never be clipped" section for the full
    mechanism. `.register` used to be nested inside `.content`'s own
    `.expect-col` (a fix for an earlier, different bug --
    `position: absolute`, pinned to the viewport); once `.content` itself
    became the flexible element absorbing whatever height the rigid bands
    above it did not use, a squeezed `.content` spilled its own children,
    the register block included, straight past the canvas edge.

    The fix is structural, not a tuned size: `.register` is now a sibling
    band, never a descendant of `.content`, with `flex: 0 0 auto` -- a
    property flexbox never shrinks below the element's own natural size,
    however tall the bands before it grow. `.content` and
    `.band--talk-title` are the two elements now allowed to give up space
    instead (`flex: 1 1 auto; min-height: 0; overflow: hidden`) -- checked
    here by CSS properties and DOM position, the same kind of property test
    `test_the_safe_area_clears_every_ribbon_waypoint` already uses for the
    ribbon, not a rendered pixel (nothing in this module renders one --
    see the module docstring).

    Mutating each property back reproduces the original bug, and this test
    catches it (checked by hand, not committed): dropping `.register`'s own
    `flex: 0 0 auto` back to nothing lets it shrink again; removing
    `.content`'s `overflow: hidden` lets an over-tall `.content` spill past
    `.register` instead of clipping itself; nesting `.register` back inside
    `.content` reintroduces the exact squeeze this
    test exists to catch."""
    doc = render_announcement(_announcement(), width=_W, height=_H, root=ROOT)

    content_start = doc.index('<div class="content">')
    content_end = doc.index("</div>", doc.index('<div class="frame-wrap">'))
    register_start = doc.index('<div class="register">')
    motif_start = doc.index('<svg class="motif-overlay"')
    # `.register` is a sibling AFTER `.content`, never between its opening
    # and closing tags.
    assert content_start < content_end < register_start < motif_start

    register_rule = _rule_block(doc, ".register")
    assert "flex: 0 0 auto" in register_rule
    assert "position: absolute" not in register_rule

    content_rule = _rule_block(doc, ".content")
    assert "overflow: hidden" in content_rule
    assert "min-height: 0" in content_rule

    title_band_rule = _rule_block(doc, ".band--talk-title")
    assert "overflow: hidden" in title_band_rule
    assert "min-height: 0" in title_band_rule

    # `.content`'s own flex-shrink factor must be the larger of the two --
    # it is the element meant to give up space first, ordinary growth
    # absorbed there alone; `.band--talk-title` only shrinks once
    # `.content` is already exhausted (see the module docstring's "Why the
    # code can never be clipped").
    content_flex = re.search(r"flex:\s*[\d.]+\s+([\d.]+)\s+auto", content_rule)
    title_flex = re.search(r"flex:\s*[\d.]+\s+([\d.]+)\s+auto", title_band_rule)
    assert content_flex and title_flex
    assert float(content_flex.group(1)) > float(title_flex.group(1))


def test_the_safe_area_variables_match_the_derived_margins() -> None:
    doc = render_announcement(_announcement(), width=_W, height=_H, root=ROOT)
    poster_rule = _rule_block(doc, ".poster")
    left_vw, right_vw = _motif_safe_margins(_W, _H, ROOT)
    content_right_vw = _motif_content_right_margin(_W, _H, ROOT)
    assert f"--safe-l: {left_vw:g}vw" in poster_rule
    assert f"--safe-r: {right_vw:g}vw" in poster_rule
    assert f"--safe-r-content: {content_right_vw:g}vw" in poster_rule


def test_the_content_right_margin_is_narrower_than_the_full_corridor() -> None:
    """The whole point of `_motif_content_right_margin` existing as a
    second function: `.content` would lose real width for nothing if it
    read the full-corridor `--safe-r` instead -- this is the property a
    second bug rested on (see `_motif_content_right_margin`'s
    own docstring for the collision that first exposed it: `.expect`'s copy
    re-wrapping into the "register" label beneath it)."""
    _, full_right_vw = _motif_safe_margins(_W, _H, ROOT)
    content_right_vw = _motif_content_right_margin(_W, _H, ROOT)
    assert content_right_vw < full_right_vw


def test_the_right_motif_never_reaches_below_its_own_tail_exit() -> None:
    """The property `_motif_content_right_margin` relies on:
    `right_tail_exit` is the lowest any right-side on-curve point of the
    ribbon ever reaches down the page. If `motifs/ribbon.py::waypoints` ever grew a
    right-side point further down than that, `.content`'s own narrower
    margin would need widening to match -- this is the canary for that,
    checked at the same three aspect ratios the main safe-area property
    test above is."""
    for width, height in ((1200.0, 1200.0), (1200.0, 630.0), (900.0, 1200.0)):
        w = waypoints(width, height)
        right_points = (
            *w.right_loop_arc,
            w.right_loop_out,
            w.right_tail_start,
            w.right_tail_bulge,
            w.right_tail_exit,
        )
        assert max(y for _x, y in right_points) == w.right_tail_exit[1]


def test_the_series_title_is_centred_like_the_talk_title_and_date() -> None:
    """The reference sets "READ TOGETHER" centred, like the talk
    title (`.band--talk-title p`, already centred) and the date line
    (`.date-line`, already centred) beneath it -- one heading had been left
    flush left, and this corrects it."""
    doc = render_announcement(_announcement(), width=_W, height=_H, root=ROOT)
    assert "text-align: center" in _rule_block(doc, ".hero h1")


# ---------------------------------------------------------------------------
# Three formats, one template (`formats.py` names the three real
# sizes). Every property established above for the square is re-checked
# here at the banner's and the print poster's own real dimensions, not
# assumed to carry over -- the banner is exactly where the known defect
# lived (it overflowed at the bottom), and a test that only ever renders
# the square proves nothing about it.
# ---------------------------------------------------------------------------


def _real_long_title() -> str:
    """The real fixture's own longest title (`site/src/_data/events.json`,
    MRG-04) -- read directly rather than retyped, so a future edit to that
    title could not silently desync this suite's own "does the real long
    title still compose" check from what the fixture actually contains."""
    events = json.loads(
        (ROOT / "site" / "src" / "_data" / "events.json").read_text(encoding="utf-8")
    )
    entry = next(e for e in events if e["id"] == "MRG-04")
    return str(entry["title"])


# --- `is_wide`: the plain function that chooses a canvas's derivation. ---


def test_is_wide_classifies_the_three_named_formats_correctly() -> None:
    assert is_wide(SQUARE.width, SQUARE.height) is False
    assert is_wide(BANNER.width, BANNER.height) is True
    assert is_wide(PRINT.width, PRINT.height) is False


def test_is_wide_reads_the_shape_not_the_pixel_count() -> None:
    # Scaling both sides up together must not flip the classification.
    assert is_wide(2400.0, 1260.0) is True  # the banner's own shape, doubled
    assert is_wide(2400.0, 2400.0) is False  # the square's own shape, doubled


def test_is_wide_rejects_a_non_positive_canvas() -> None:
    with pytest.raises(ValueError, match="positive"):
        is_wide(0, 100)
    with pytest.raises(ValueError, match="positive"):
        is_wide(100, -1)


# --- The banner derivation drops the hero and "what to expect" copy; the
# square and the print poster keep both. ---


def test_the_banner_drops_the_hero_and_expect_the_square_and_print_keep_both() -> None:
    banner_doc = render_announcement(
        _announcement(), width=BANNER.width, height=BANNER.height, root=ROOT
    )
    assert '<div class="poster poster--wide">' in banner_doc
    assert '<section class="hero">' not in banner_doc
    assert "What to expect?" not in banner_doc
    assert '<div class="expect-col">' not in banner_doc

    for fmt in (SQUARE, PRINT):
        doc = render_announcement(
            _announcement(), width=fmt.width, height=fmt.height, root=ROOT
        )
        assert '<div class="poster">' in doc, fmt.name
        assert "poster--wide" not in doc.split("</style>")[1], fmt.name
        assert '<section class="hero">' in doc, fmt.name
        assert "What to expect?" in doc, fmt.name


def test_the_banner_still_shows_title_date_frame_and_register() -> None:
    """Fewer elements, not fewer of the ones that matter: the talk title,
    the date, the speaker's own frame and the registration code all
    survive the banner's own reduction -- only the series hero and the
    process explanation are dropped (see the test above)."""
    doc = render_announcement(
        _announcement(), width=BANNER.width, height=BANNER.height, root=ROOT
    )
    assert "On analytical engines" in doc
    assert date_line(date(2026, 3, 12)) in doc
    assert '<figure class="frame">' in doc
    assert doc.count("data-registration-code-slot") == 1


def test_a_long_real_title_composes_without_clipping_in_every_format() -> None:
    """The real fixture's own longest title (MRG-04), which already needed
    four lines in the square -- it reaches the page whole in every one of
    the three named formats: never truncated, never ellipsised, and never at the cost of
    the registration code."""
    title = _real_long_title()
    for fmt in FORMATS:
        doc = render_announcement(
            _announcement(title=title), width=fmt.width, height=fmt.height, root=ROOT
        )
        assert title in doc, fmt.name
        assert "…" not in doc, fmt.name
        assert "text-overflow" not in _rule_block(doc, ".band--talk-title p"), fmt.name
        assert doc.count("data-registration-code-slot") == 1, fmt.name


# --- Properties already pinned for the square, re-pinned at the three
# named formats rather than assumed to transfer. ---


def test_the_safe_area_clears_every_ribbon_waypoint_at_each_named_format() -> None:
    """The same property `test_the_safe_area_clears_every_ribbon_waypoint`
    already pins at three generic aspect ratios, re-checked here at the
    three real, named sizes (`formats.py`) -- pinning
    the actual numbers a caller really renders at, not only placeholders
    that happen to share their shape."""
    for fmt in FORMATS:
        left_vw, right_vw = _motif_safe_margins(fmt.width, fmt.height, ROOT)
        left_px = left_vw / 100.0 * fmt.width
        right_px = right_vw / 100.0 * fmt.width

        w = waypoints(fmt.width, fmt.height)
        left_points = (
            w.left_top_entry,
            w.left_top_exit,
            *w.left_loop_arc,
            w.left_tail_bulge,
            w.left_bottom_exit,
        )
        right_points = (
            *w.right_loop_arc,
            w.right_loop_out,
            w.right_tail_start,
            w.right_tail_bulge,
            w.right_tail_exit,
        )
        deepest_left = max(x for x, _y in left_points)
        deepest_right = fmt.width - min(x for x, _y in right_points)

        assert deepest_left <= left_px, fmt.name
        assert deepest_right <= right_px, fmt.name


def test_no_portrait_is_ever_rendered_without_consent_in_any_format() -> None:
    for fmt in FORMATS:
        doc = render_announcement(
            _announcement(portrait_data_uri=None),
            width=fmt.width,
            height=fmt.height,
            root=ROOT,
        )
        assert "<img" not in doc, fmt.name
        assert '<div class="frame__placeholder"' in doc, fmt.name


def test_no_brand_colour_hand_typed_outside_root_or_stroke_in_any_format() -> None:
    """The same guard already run once at the square, re-run at all three
    formats: the banner's own extra `.poster--wide` rules are new CSS this
    task wrote, and nothing already checked them for a hand-typed colour."""
    brand = _brand()
    colours = {value for value in brand["colour"].values() if isinstance(value, str)}
    colours |= {value for value in brand["derived"].values() if isinstance(value, str)}

    for fmt in FORMATS:
        doc = render_announcement(
            _announcement(), width=fmt.width, height=fmt.height, root=ROOT
        )
        rest = _outside_the_root_block(doc)
        pattern = re.compile("|".join(re.escape(c) for c in colours), re.IGNORECASE)
        match = pattern.search(rest)
        assert match is None, (fmt.name, match.group(0) if match else "")


# --- The register row in the wide grid can never be the one that shrinks
# -- the banner's own version of
# `test_the_register_band_is_never_squeezed_by_flexible_content`. ---


def test_the_register_row_never_shrinks_in_the_wide_grid() -> None:
    """`.poster--wide`'s `wordmark` and `register` rows are both `auto` --
    a track CSS Grid never sizes below its own item's natural size, exactly
    the guarantee `flex: 0 0 auto` gives the square's own `.register` band
    (see that test's own docstring). Only the `heading` row (title and date,
    wrapped together in `.wide-heading`) is `minmax(0, 1fr)`, the one
    allowed to give first when the banner's own 630px runs short.

    Checked as a CSS property, not a rendered pixel. This test alone does
    not catch the banner being forced back to the square's own vertical
    rhythm (`is_wide` hard-coded to always return `False`): the
    `.poster--wide` *rule* is always present in the stylesheet, wide render
    or not (see that rule's own comment), so `_rule_block` still finds it
    either way. `test_the_banner_drops_the_hero_and_expect_the_square_and_
    print_keep_both` is the one that actually bites -- it checks whether the
    rendered `<div>` at banner dimensions *carries* the `poster--wide`
    class, which the mutation above removes; four tests fail against that
    mutation in total, checked by hand and not committed."""
    doc = render_announcement(
        _announcement(), width=BANNER.width, height=BANNER.height, root=ROOT
    )
    poster_wide_rule = _rule_block(doc, ".poster--wide")
    assert re.search(r"auto\s+minmax\(0,\s*1fr\)\s+auto", poster_wide_rule)
    assert '"wordmark wordmark"' in poster_wide_rule
    assert '"heading  frame"' in poster_wide_rule
    assert '"register frame"' in poster_wide_rule


# ---------------------------------------------------------------------------
# The banner's own title band was once a band in name only --
# flush at the left edge, stopping short of the right (the "heading" grid
# area is only `.wide-heading`'s own column, beside the frame's own
# column), reading as a rendering accident rather than the "bands run
# the full width" rule `instance/data/brand.json`'s own `layout._bands` states
# outright. The square and the print poster never had this defect
# (`.band--talk-title` is a plain flex child of `.poster`'s own flex
# column there, stretched to the canvas's own full width by the same
# default every other band already relies on) -- only the banner's own
# two-column grid confined it.
#
# The fix is two boxes, not one: `.band--talk-title__backdrop` (wide-only
# markup, a sibling of `.band--talk-title` inside the new `.wide-title-row`
# wrapper) breaks out to the canvas's own full width and paints the band;
# `.band--talk-title` itself keeps exactly the width it always had, so the
# talk title's own text never reaches the frame's own column. The first
# attempt at this fix widened `.band--talk-title` itself instead, and the
# real fixture's own longest title (MRG-04) then wrapped a word directly
# under the frame -- caught by rendering, not by any test below, which is
# why `test_the_banner_title_text_itself_never_widens_into_the_frames_
# column` exists: a property the render-and-look step cannot substitute
# for on every future change.
# ---------------------------------------------------------------------------


def test_the_talk_title_band_runs_the_full_canvas_width_in_every_format() -> None:
    """Pins the property directly, at all three named formats -- would
    fail against the pre-fix banner, which carried no backdrop at all
    (`'<div class="band--talk-title__backdrop"' in doc` is false there).
    Checked by hand: reverting the backdrop rule's own `width: 100vw` to
    `width: 50vw` reproduces exactly that failure."""
    for fmt in FORMATS:
        doc = render_announcement(
            _announcement(), width=fmt.width, height=fmt.height, root=ROOT
        )
        if fmt is BANNER:
            assert '<div class="band--talk-title__backdrop"' in doc, fmt.name
            backdrop_rule = _rule_block(
                doc, ".poster--wide .wide-title-row .band--talk-title__backdrop"
            )
            assert "width: 100vw" in backdrop_rule, fmt.name
            assert "left: 0" in backdrop_rule, fmt.name
            assert "top: 0" in backdrop_rule, fmt.name
            assert "background: var(--surface)" in backdrop_rule, fmt.name
        else:
            # The square and print formats need no backdrop at all --
            # `.band--talk-title` is already full width by the plain flex
            # default (see `test_the_talk_title_band_can_wrap_and_grow_
            # rather_than_clip`'s own `band_rule` check that `.band` sets
            # no `height`; the same rule sets no `width` either). The CSS
            # rule and its comment are shared, unconditional text (present
            # in every format's `<style>` block, same as `.poster--wide`
            # itself), so what must be absent is the *element* -- the div
            # `render_announcement`'s wide branch alone ever emits.
            assert '<div class="band--talk-title__backdrop"' not in doc, fmt.name
            assert "width" not in _rule_block(doc, ".band"), fmt.name


def test_the_banner_title_text_itself_never_widens_into_the_frames_column() -> None:
    """The property the fix's own first (reverted) attempt violated:
    `.band--talk-title` -- the element the talk title's own text actually
    sits inside -- carries no `width` of its own in any format, wide
    included. Only `.band--talk-title__backdrop`, a sibling, breaks out to
    100vw; the text stays exactly as wide as `.wide-title-row`'s own
    (column-confined, unset-width) flex default already makes it, clear of
    the frame's own column at any title length. `_rule_block` retrieves
    the one, shared, unscoped `.band--talk-title` rule (it appears earlier
    in the stylesheet than anything under `.poster--wide`), so this holds
    regardless of format."""
    for fmt in FORMATS:
        doc = render_announcement(
            _announcement(), width=fmt.width, height=fmt.height, root=ROOT
        )
        assert "width" not in _rule_block(doc, ".band--talk-title"), fmt.name


def test_a_long_real_title_never_wraps_under_the_banners_frame() -> None:
    """The exact regression a first attempt introduced and
    a rendering pass caught: the real fixture's own
    longest title (MRG-04) wrapping a word ("across") directly underneath
    the speaker's frame once `.band--talk-title` itself was widened to
    100mrg. `assert title in doc` alone (already checked by
    `test_a_long_real_title_composes_without_clipping_in_every_format`)
    cannot catch this -- the full text is still *in* the document even
    when a word renders visually under an opaque photo, which is exactly
    why that defect shipped past this suite the first time and was only
    found by looking at the actual render. Pinned here as the CSS property
    that structurally rules it out (see the test above) rather than
    re-asserted as a second, weaker string check."""
    title = _real_long_title()
    doc = render_announcement(
        _announcement(title=title), width=BANNER.width, height=BANNER.height, root=ROOT
    )
    assert title in doc
    assert "width" not in _rule_block(doc, ".band--talk-title")


def test_the_frame_still_paints_over_the_banner_backdrop_not_the_reverse() -> None:
    """`.band--talk-title__backdrop` sits at `z-index: -1`, but *within*
    `.wide-title-row`'s own local stacking context (`position: relative;
    z-index: 0`) -- not the page's, which would risk it sinking behind
    unrelated ancestors instead of merely behind its own sibling text.
    `.frame-wrap` carries no stacking context of its own and is later in
    this page's own DOM order, so it paints over whatever part of the
    backdrop its own column overlaps regardless -- checked here as the
    DOM-order property and the two z-indexes it depends on, not a
    rendered pixel."""
    doc = render_announcement(
        _announcement(), width=BANNER.width, height=BANNER.height, root=ROOT
    )
    backdrop_start = doc.index('<div class="band--talk-title__backdrop"')
    frame_wrap_start = doc.index('<div class="frame-wrap">')
    assert backdrop_start < frame_wrap_start

    wide_title_row_rule = _rule_block(doc, ".poster--wide .wide-title-row")
    assert "position: relative" in wide_title_row_rule
    assert "z-index: 0" in wide_title_row_rule
    backdrop_rule = _rule_block(
        doc, ".poster--wide .wide-title-row .band--talk-title__backdrop"
    )
    assert "position: absolute" in backdrop_rule
    assert "z-index: -1" in backdrop_rule


def test_the_talk_title_still_shrinks_and_clips_rather_than_spills_when_wide() -> None:
    """The vertical backstop (`.band--talk-title`'s `flex: 0 1
    auto; min-height: 0; overflow: hidden`) still has a real flex
    container to shrink within now that it sits one level deeper, inside
    `.wide-title-row` rather than directly inside `.wide-heading`:
    `.wide-title-row` is itself `display: flex; flex-direction: column`
    with `flex: 0 1 auto; min-height: 0` at the *outer* level (wide-
    heading's own flex column), re-establishing, one level further out,
    exactly the shrink-then-clip chain that already existed before this
    fix. Without this, `.band--talk-title`'s own `flex: 0 1 auto` would be
    inert (a flex-only property has no effect on an element that is not
    itself a flex item), and a squeezed banner could spill text past
    `.wide-title-row`'s own visible-overflow box -- necessary, because
    that box cannot also be `overflow: hidden` without clipping the
    backdrop's own horizontal breakout."""
    doc = render_announcement(
        _announcement(), width=BANNER.width, height=BANNER.height, root=ROOT
    )
    wide_title_row_rule = _rule_block(doc, ".poster--wide .wide-title-row")
    assert "display: flex" in wide_title_row_rule
    assert "flex-direction: column" in wide_title_row_rule
    assert re.search(r"flex:\s*0\s+1\s+auto", wide_title_row_rule)
    assert "min-height: 0" in wide_title_row_rule
    # `.band--talk-title` itself keeps its own unconditional backstop,
    # shared with the square and print formats, unchanged by this fix.
    title_band_rule = _rule_block(doc, ".band--talk-title")
    assert "overflow: hidden" in title_band_rule
    assert "min-height: 0" in title_band_rule


# ---------------------------------------------------------------------------
# A second finding: the banner's own affiliation caption was
# illegible at the size a share preview is actually displayed at (the
# banner's own 630px-tall canvas puts `_AFFILIATION_FONT_MAX_VMIN`,
# 1.7vmin, at ~10.7px before a preview surface then scales the whole image
# down further). Dropped outright on the banner alone -- the same
# treatment, and the same reasoning, this derivation already gives the
# series hero and the "what to expect" copy.
# ---------------------------------------------------------------------------


def test_the_banner_drops_the_affiliation_the_square_and_print_keep_it() -> None:
    banner_doc = render_announcement(
        _announcement(), width=BANNER.width, height=BANNER.height, root=ROOT
    )
    assert '<span class="frame__affiliation"' not in banner_doc
    assert "Analytical Engines Institute" not in banner_doc
    # The name alone survives -- the one fact the affiliation's absence
    # does not cost the reader.
    assert '<span class="frame__name"' in banner_doc
    assert "Ada Lovelace" in banner_doc

    for fmt in (SQUARE, PRINT):
        doc = render_announcement(
            _announcement(), width=fmt.width, height=fmt.height, root=ROOT
        )
        assert '<span class="frame__affiliation"' in doc, fmt.name
        assert "Analytical Engines Institute" in doc, fmt.name


def test_an_affiliation_less_speaker_is_unaffected_by_the_banners_own_drop() -> None:
    """The banner's own affiliation drop reuses `_frame_html`'s existing
    empty-affiliation path (`speaker_affiliation=""`) rather than a new
    branch -- so a speaker who already has no affiliation to show renders
    identically on the banner as on the square: this is not a new code
    path with its own, unchecked failure mode."""
    doc = render_announcement(
        _announcement(speaker_affiliation=""),
        width=BANNER.width,
        height=BANNER.height,
        root=ROOT,
    )
    assert '<span class="frame__affiliation"' not in doc
    assert '<span class="frame__name"' in doc
