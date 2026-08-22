"""The announcement composition -- pinning the properties that make it
compose rather than a byte-identical page, the same discipline
`test_ribbon.py` already applies to task 1's own module (see that file's
own docstring). Four groups matter most, because each is where this task's
own brief names a defect that would otherwise be invisible in a single
screenshot: a long title staying inside its band, a missing portrait
composing rather than breaking, every colour coming from `data/brand.json`
rather than a hand-typed literal, and the date line reflecting the
edition's real Europe/Paris offset -- pinned for a winter *and* a summer
edition, because a test that only ever checked a winter date would pass
against the reference poster's own hard-typed "(CET)" defect.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, tzinfo
from typing import Any

import pytest
from conftest import speaker

import convener_ops.visual as visual
from convener_ops.paths import repo_root
from convener_ops.public_data import to_public
from convener_ops.visual import (
    _AFFILIATION_FONT_MAX_VMIN,
    _AFFILIATION_FONT_MIN_VMIN,
    _NAME_FONT_MAX_VMIN,
    _NAME_FONT_MIN_VMIN,
    _TITLE_FONT_MAX_MRG,
    _TITLE_FONT_MIN_MRG,
    Announcement,
    _affiliation_font_size,
    _frame_photo_html,
    _name_font_size,
    _title_font_size,
    date_line,
    paris_standing_start,
    render_announcement,
)

ROOT = repo_root()

#: A small canvas is enough for every structural assertion below and keeps
#: the suite fast; nothing here inspects pixels, only the generated markup
#: and CSS text (rendering to an actual image is task 5's own job, done by
#: hand for this task's own report, never inside this test suite -- no test
#: here touches a browser or the network).
_W, _H = 1200.0, 1200.0


def _announcement(**overrides: Any) -> Announcement:
    base: dict[str, Any] = {
        "title": "On analytical engines",
        "talk_date": date(2026, 3, 12),
        "speaker_name": "Ada Lovelace",
        "speaker_affiliation": "Analytical Engines Institute",
        "portrait_data_uri": None,
    }
    base.update(overrides)
    return Announcement(**base)


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
# <img> (P-4).
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
# Every colour comes from data/brand.json's generated block, never a
# hand-typed literal.
# ---------------------------------------------------------------------------

#: The exact mapping `visual._root_css_block` uses -- reimplemented here,
#: independently, rather than imported: a bug in that mapping could not
#: then also hide from the test meant to catch it (the same reasoning
#: `test_brand.py::_all_brand_colours` gives for its own, near-identical
#: duplication).
_ROOT_VAR_SOURCES = {
    "--paper": ("colour", "white"),
    "--surface": ("colour", "cream"),
    "--surface-2": ("colour", "turquoise"),
    "--ink": ("colour", "ink"),
    "--ink-mute": ("colour", "ink_muted"),
    "--ink-faint": ("derived", "ink_faint"),
    "--turquoise": ("colour", "turquoise"),
    "--turquoise-d": ("derived", "turquoise_text"),
    "--turquoise-l": ("derived", "turquoise_tint"),
    "--purple": ("colour", "purple"),
    "--purple-d": ("derived", "purple_hover"),
    "--purple-l": ("derived", "purple_tint"),
    "--rule": ("colour", "rule"),
    "--rule-strong": ("derived", "rule_strong"),
    "--white": ("colour", "white"),
    "--black": ("colour", "black"),
}


def _brand() -> dict[str, Any]:
    return dict(json.loads((ROOT / "data" / "brand.json").read_text(encoding="utf-8")))


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
            f"(data/brand.json::{section}.{key})"
        )


def test_no_brand_colour_hand_typed_outside_root_or_ribbon_stroke() -> None:
    """The same guard `test_brand.py` already runs on the ribbon templates
    and the two generated stylesheets, applied to this third consumer of
    `data/brand.json`. The ribbon's own `stroke="#..."` is the one
    accepted exception -- task 1's own precedent, an SVG attribute filled
    in from `ribbon_stroke_colour(root)` at render time, never hand-typed
    in this module's source."""
    brand = _brand()
    colours = {value for value in brand["colour"].values() if isinstance(value, str)}
    colours |= {value for value in brand["derived"].values() if isinstance(value, str)}
    doc = render_announcement(_announcement(), width=_W, height=_H, root=ROOT)

    root_block = _root_block_text(doc)
    rest = doc.replace(root_block, "")
    # The ribbon path's own stroke attribute -- the one accepted exception.
    rest = re.sub(r'stroke="#[0-9a-fA-F]{6}"', 'stroke="EXCLUDED"', rest)

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
    )
    assert ann.portrait_data_uri is None


def test_an_empty_title_falls_back_rather_than_rendering_a_blank_band() -> None:
    doc = render_announcement(_announcement(title=""), width=_W, height=_H, root=ROOT)
    assert "Talk title" in doc


def test_the_ribbon_is_painted_last_so_it_sits_on_top_of_everything() -> None:
    doc = render_announcement(_announcement(), width=_W, height=_H, root=ROOT)
    assert doc.rindex("ribbon-overlay") > doc.rindex("registration-code-slot")
    assert doc.rindex("</svg>") > doc.rindex("</figure>")


def test_the_ribbon_geometry_matches_the_requested_canvas() -> None:
    doc = render_announcement(_announcement(), width=900.0, height=1200.0, root=ROOT)
    assert 'viewBox="0 0 900 1200"' in doc
