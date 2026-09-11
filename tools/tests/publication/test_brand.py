"""The design tokens, and the guards that keep them derived from one file.

`instance/data/brand.json` measured the designer's own colours. Before this module
existed, two implementations each carried their own hand-typed copy of them --
`site/src/style.css` and `app/src/design/tokens.css` -- and the application
had drifted to a reconstruction's palette without anyone deciding that on
purpose: purple on turquoise measured 4.44 there, below AA, where the
measured charter gives 7.93, AAA.
`tools/scripts/generate_brand_css.py` derives both from the brand file instead,
and this module holds what makes that stick.

A third file, `app/src/design/tokens.ts`, used to be generated here too and
was covered by this module's own tests. It was retired -- nothing
under `app/src` ever imported it -- so it is guarded only by
`test_the_reconstructions_palette_never_reappears` staying silent about it
now, not by a generation test for a file that no longer exists.

**The loop is proved, not assumed**, the same way `test_schema_doc.py` proves
it for the handbook appendix: the tests below read the committed files off
disk and compare them with what today's `instance/data/brand.json` derives. That
catches a token hand-edited without regenerating, and a `instance/data/brand.json`
value changed without regenerating -- the two ways the committed copies
and their source can drift apart.

**Contrast is recomputed, not re-read.** `instance/data/brand.json` carries measured
ratios; `test_every_measured_contrast_ratio_is_recomputed_from_its_colours`
walks every one, recomputes it from the colours that produce it with the WCAG
2.1 arithmetic in `generate_brand_css.py`, and fails the moment they disagree.
A ratio nobody rechecks is exactly how the reconstruction's own claim --
"darkening the turquoise defends itself, the contrast is marginal" -- went
unmeasured for months while being false.

**A generated token is not the only place a colour can drift back in.** The
ribbon SVGs in `site/src/index.njk` and `app/src/auth/Login.tsx` carried
`stroke="#3D2D7C"` / `stroke="#3FB1C2"` -- the reconstruction's values, typed
directly into markup no generator ever touches. Two further guards cover
that: one asks whether any of `instance/data/brand.json`'s own colours are hand-typed
in either template (they must come from a generated CSS custom property or
a Tailwind class instead), and one asks whether the reconstruction's three
known-wrong values have reappeared anywhere across the guarded files.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Final
from xml.etree import ElementTree

import pytest
from generate_brand_css import (
    _BEGIN,
    _END,
    ANNOUNCEMENT_SVG_PATH,
    APP_TOKENS_CSS_PATH,
    BACKGROUND_SVG_PATH,
    BRAND_PATH,
    COMMAND,
    FLYER_SVG_PATH,
    SITE_CSS_PATH,
    load_brand,
    main,
    render_app_tokens_css,
    render_site_css,
)

from convener_ops.declaration import published
from convener_ops.declaration.paths import repo_root
from convener_ops.publication import (
    brand,
    brand_templates,
    motifs,
    typeface,
    visual,
)
from convener_ops.publication.brand import (
    GROUND_PAIRS,
    GROUND_SEPARATION_FLOOR,
    contrast_ratio,
    ground_problems,
    hex_to_rgb,
    relative_luminance,
    rgb_triplet,
    rgba,
)
from convener_ops.publication.motifs import bracket

ROOT = repo_root()

#: Every charter this repository ships, by the name a declaration writes to
#: choose it -- the directory it sits in. Off `brand.shipped` rather than
#: listed, so a charter added tomorrow is in the tests below on the commit
#: that adds it.
ROOT_CHARTERS = {rel.parent.name: rel for rel in brand.shipped(ROOT)}

#: The charter this repository's own build is drawn from, then every other
#: charter it ships. `brand.source` gives three answers and an instance is
#: always on one of them: it wrote `instance/data/brand.json`, its
#: declaration names one of the product's, or it does neither and the
#: product's own default is in force. The second and third answer a file
#: `assets/brand/` already holds, which is what the filter is for -- one
#: file asked for under two names is measured twice and says nothing the
#: once did not.
CHARTERS_HELD: Final = (
    brand.source(ROOT),
    *(rel for rel in brand.shipped(ROOT) if rel != brand.source(ROOT)),
)

#: Whether the charter in force here *is* the product's own default. True
#: in every repository that ships the example as its instance -- the example
#: collective names `convener` and writes no charter -- and false upstream,
#: which has a designer and a file. The two comparisons that carry it are
#: about the difference between a duplicate's palette and the product's,
#: and where the two are one file there is no difference to be about.
DRAWN_BY_THE_PRODUCTS_OWN: Final = brand.source(ROOT) == brand.DEFAULT_PATH

#: What those two say when they abstain, in the shape
#: `instance_identity.ONE_INSTANCE` already uses: the condition, and what
#: brings the test back.
NO_SECOND_PALETTE: Final = (
    "the charter in force here is the product's own default "
    "(brand.source answers brand.DEFAULT_PATH), so there is no second "
    "palette for this to hold it apart from -- it runs again as soon as "
    "an instance writes a charter of its own"
)

#: The templates that draw the ribbon motif directly, outside any generated
#: stylesheet. None may hand-type a colour `instance/data/brand.json` carries; each
#: must take it from a generated token instead. `layout.njk` joined this list
#: when the shared masthead grew its own loop, so every page built on it --
#: not only the home page -- carries the motif (D-18).
_RIBBON_TEMPLATES = (
    Path("site") / "src" / "index.njk",
    Path("site") / "src" / "_includes" / "layout.njk",
    Path("app") / "src" / "auth" / "Login.tsx",
)

#: Every file the palette reaches. None of them may ever carry the
#: reconstruction's values again.
_GUARDED_FILES = (
    Path("site") / "src" / "style.css",
    Path("site") / "src" / "index.njk",
    Path("app") / "src" / "design" / "tokens.css",
    Path("app") / "src" / "auth" / "Login.tsx",
    # The files a collaborator downloads. The two templates carried
    # all three of these values until they stopped being drawn by hand;
    # the background was a PNG, where no sweep could have found one.
    ANNOUNCEMENT_SVG_PATH,
    FLYER_SVG_PATH,
    BACKGROUND_SVG_PATH,
)

#: The reconstruction's own three values, exactly as they shipped: the
#: application's deep-purple accent, its turquoise primary, and its
#: cyan-tinted paper -- measured, and recorded, before they were discarded.
_RECONSTRUCTION_VALUES = ("#3D2D7C", "#3FB1C2", "#f7fafa")


def _rule_block(css: str, selector: str) -> str:
    """The body of one flat CSS rule (no nested braces), found by its exact
    selector at the start of a line -- `_rule_block(css, "a")` finds `a {
    ... }` itself, not `a.btn {` or `a:hover {`, because the pattern
    requires the selector to be followed only by optional whitespace and
    then `{`.
    """
    pattern = re.compile(
        r"(?:^|\n)" + re.escape(selector) + r"\s*\{([^}]*)\}", re.MULTILINE
    )
    match = pattern.search(css)
    assert match, f"no rule found for selector {selector!r}"
    return match.group(1)


def _all_brand_colours(brand: dict[str, Any]) -> dict[str, str]:
    """`colour` and `derived`, merged -- reimplemented here rather than
    imported from `generate_brand_css._colours`, so a bug in that filter
    could not also hide from the tests that are supposed to catch it."""
    merged: dict[str, str] = {}
    for section in ("colour", "derived"):
        for key, value in brand[section].items():
            if not key.startswith("_"):
                merged[key] = value
    return merged


# --------------------------------------------------------------------------
# The repository's own files
# --------------------------------------------------------------------------


def test_the_committed_site_css_tokens_are_what_brand_json_derives() -> None:
    committed = (ROOT / SITE_CSS_PATH).read_text(encoding="utf-8")
    assert committed == render_site_css(ROOT), (
        f"{SITE_CSS_PATH.as_posix()} is not what "
        f"{brand.source(ROOT).as_posix()} derives; run `{COMMAND}` from "
        "`tools/`."
    )


def test_the_committed_app_tokens_css_is_what_brand_json_derives() -> None:
    committed = (ROOT / APP_TOKENS_CSS_PATH).read_text(encoding="utf-8")
    assert committed == render_app_tokens_css(ROOT), (
        f"{APP_TOKENS_CSS_PATH.as_posix()} is not what "
        f"{brand.source(ROOT).as_posix()} derives; run `{COMMAND}` from "
        "`tools/`."
    )


def test_the_rendering_is_a_function_of_brand_json_alone() -> None:
    """Byte-identical over two runs, which is what makes `--check` a fact."""
    assert render_site_css(ROOT) == render_site_css(ROOT)
    assert render_app_tokens_css(ROOT) == render_app_tokens_css(ROOT)


def test_the_generated_files_say_so() -> None:
    """A derived file that does not say so is one somebody will edit."""
    site_css = (ROOT / SITE_CSS_PATH).read_text(encoding="utf-8")
    assert "generate_brand_css.py" in site_css
    app_css = (ROOT / APP_TOKENS_CSS_PATH).read_text(encoding="utf-8")
    assert "generate_brand_css.py" in app_css


# --------------------------------------------------------------------------
# Contrast: recomputed, not re-read
# --------------------------------------------------------------------------


def test_every_measured_contrast_ratio_is_recomputed_from_its_colours() -> None:
    """`instance/data/brand.json`'s `contrast` section names a foreground and a
    ground in its own key (`dominant_on_field`); this looks both up and
    recomputes the ratio from the colours themselves, rather than trusting
    the number already written beside them.
    """
    brand = load_brand(ROOT)
    colours = _all_brand_colours(brand)
    checked = 0
    for name, stored in brand["contrast"].items():
        if name.startswith("_"):
            continue
        fg, _, bg = name.rpartition("_on_")
        assert fg in colours, f"{name}: no colour named {fg!r}"
        assert bg in colours, f"{name}: no colour named {bg!r}"
        computed = round(contrast_ratio(colours[fg], colours[bg]), 2)
        assert computed == stored, (
            f"{name}: instance/data/brand.json claims {stored}, "
            f"{colours[fg]} on {colours[bg]} computes to {computed}"
        )
        checked += 1
    # Every entry instance/data/brand.json currently carries -- a change to that
    # section without a matching change here would otherwise pass silently.
    # Nine at first, plus two the verify page's own
    # panel needed (field_text_on_band, ink_muted_on_band), plus one
    # (field_on_dominant) the accessibility sweep found had gone
    # unnamed, plus the two the archive's own pills set on a tint
    # (dominant_on_field_tint, dominant_on_dominant_tint) -- found by
    # building the showcase at each of the four charters a duplicate may
    # name, where the ink that pill used to take failed AA at two of them
    # against a ground no table here had ever measured it on.
    assert checked == 14


def test_every_charter_keeps_its_grounds_far_enough_apart_to_be_told_apart() -> None:
    """The bound R61 turned on, over every charter a duplicate may choose.

    Not a contrast obligation and not checkable as one: none of these pairs
    is text, every pairing `contrast` records has a text colour on one
    side, and WCAG's own floor for a graphical object is about a control's
    boundary rather than about one flat area lying on another. So the floor
    is this product's, and it is measured -- `assets/brand/chevrons/`
    already ships the tightest of them.
    """
    assert len(ROOT_CHARTERS) == 4, (
        "a charter added under assets/brand/ is swept here too"
    )
    for rel in CHARTERS_HELD:
        assert ground_problems(_charter(rel), named=rel.as_posix()) == []


def test_the_ground_floor_refuses_a_field_lightened_past_it() -> None:
    """The control, broken deliberately. A floor nothing recomputes is a
    marker, and this project has already paid for one of those: the whole
    of `layout._grounds` would be a sentence a reader could lighten a
    ground straight past.
    """
    values = _charter(brand.DEFAULT_PATH)
    values["colour"]["field"] = values["derived"]["field_tint"]
    problems = ground_problems(values, named="a charter with no ground left")
    assert problems, "a field lightened onto its own tint has to be refused"
    assert "field_tint on field" in problems[0]
    assert str(GROUND_SEPARATION_FLOOR) in problems[0]


def test_the_pair_that_binds_is_the_pill_and_not_the_bands() -> None:
    """Written down because the review that asked for the lighter ground
    named the wrong bound. `band_on_field` is the separation the charters
    quote and it is the *looser* of the two: the archive pill reaches the
    floor first, so a reader who lightens the field while watching only the
    bands takes the pill down with them.
    """
    values = _charter(brand.DEFAULT_PATH)
    palette = brand.colours(values)
    measured = {
        (nearer, further): contrast_ratio(palette[nearer], palette[further])
        for nearer, further in GROUND_PAIRS
    }
    assert measured[("field_tint", "field")] < measured[("band", "field")]
    assert measured[("field_tint", "field")] == pytest.approx(1.12, abs=0.005)
    assert measured[("band", "field")] == pytest.approx(1.29, abs=0.005)


def test_the_dominant_on_the_field_is_the_measurement_d16_turned_on() -> None:
    """The one number this whole task exists over: a reconstruction that
    darkened the ground under dark text shipped 4.44, below AA for normal
    text, and the measured charter that replaced it clears it.

    The two colours are read from the charter in force rather than typed.
    They used to be typed, and the two hexadecimal values
    in them were `instance/data/brand.json`'s own -- one instance's declared
    palette, written into a test of the *product's* arithmetic, where the
    derivation quite correctly replaced them with another instance's and
    left the expected figure behind. Nothing was hurt by that here; what
    it showed is that this test was pinned to a repository rather than to
    a claim. The claim is that the figure beside the colours is the one
    the colours compute to, and that it clears AA -- true of whichever
    charter is in force, and the thing `generate_brand_css.py --check`
    stops a build over.
    """
    charter = brand.load(ROOT)
    palette = brand.colours(charter)
    computed = round(contrast_ratio(palette["dominant"], palette["field"]), 2)
    assert computed == charter["contrast"]["dominant_on_field"]
    assert computed >= 4.5
    # And the arithmetic itself, against a pair that is nobody's: black on
    # white is 21 by definition, and 21 is the only value it can be.
    assert round(contrast_ratio("#000000", "#ffffff"), 2) == 21.0


def test_relative_luminance_of_white_and_black_are_the_extremes() -> None:
    assert relative_luminance("#ffffff") == pytest.approx(1.0)
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0, abs=0.01)


def test_hex_to_rgb_and_the_css_literals_built_from_it() -> None:
    # A colour that is nobody's: this used to read one instance's declared
    # turquoise, which made a test of six lines of
    # arithmetic depend on which instance was running the repository.
    assert hex_to_rgb("#0080ff") == (0, 128, 255)
    assert rgba("#0080ff", 0.35) == "rgba(0, 128, 255, 0.35)"
    assert rgb_triplet("#ffffff") == "255, 255, 255"


# --------------------------------------------------------------------------
# D-18: the page's own ground, and the pairings its flip put at risk
# --------------------------------------------------------------------------


def test_the_page_ground_is_the_field_not_white() -> None:
    """D-18: the showcase's ground is the field, crossed by the bands --
    the inverse of the white-ground design it replaced. `--field` holds
    whatever colour the charter in force gives that position.
    `body`'s own background is the one declaration that
    carries it; a reversion to `--paper` would put the whole composition
    back the wrong way round without any generated-token test noticing,
    since that check only covers the `:root` block, not how the rest of
    the stylesheet uses it.
    """
    css = (ROOT / SITE_CSS_PATH).read_text(encoding="utf-8")
    block = _rule_block(css, "body")
    assert "background: var(--field);" in block
    assert "var(--paper)" not in block


def test_no_selector_reverts_to_a_colour_that_fails_aa_on_the_new_ground() -> None:
    """Making the field the ground (D-18) moved several selectors off the
    white/paper ground they were designed against, onto one where their
    old colour fails AA: field-text on the field measures 3.81, ink-faint
    on the field measures 3.51, and white on a field fill measures 1.61
    -- all below the 4.5 floor for normal text (`instance/data/brand.json`'s
    `_forbidden` note). Each of these selectors was moved to a colour that
    clears AA on whichever ground it can now appear on; this pins that each
    one stays off the value that would fail there again.

    `.archive__action:hover` joined this dict late: it was found early
    (a solid field fill under white text, 1.61 -- measured at 2.54 by
    a real browser) and deliberately left it, out of its own scope, for
    the accessibility task to fix. That task moved it to the same dominant
    fill `.archive__action--alt:hover` already used; this is the guard
    that keeps it from reverting.
    """
    css = (ROOT / SITE_CSS_PATH).read_text(encoding="utf-8")
    risky: dict[str, str] = {
        "a": "var(--field-text)",
        ".hero__title em": "var(--field-text)",
        ".feature__vol": "var(--field-text)",
        ".archive__date": "var(--ink-faint)",
        ".archive__action--disabled": "var(--ink-faint)",
        ".btn--primary": "var(--field)",
        ".archive__action:hover": "var(--field)",
    }
    for selector, bad_value in risky.items():
        block = _rule_block(css, selector)
        assert bad_value not in block, (
            f"{selector} carries {bad_value}, which fails AA on the "
            "field that is now the page's ground"
        )


# --------------------------------------------------------------------------
# No colour hand-typed outside a generated token
# --------------------------------------------------------------------------


def test_no_brand_colour_is_hand_typed_in_the_ribbon_templates() -> None:
    """No colour that appears in `instance/data/brand.json` is hand-typed anywhere
    else -- including inside a template. Both ribbons draw with a stroke
    the surrounding CSS/Tailwind sets, never an attribute of their own.
    """
    brand = load_brand(ROOT)
    colours = set(_all_brand_colours(brand).values())
    pattern = re.compile("|".join(re.escape(v) for v in colours), re.IGNORECASE)
    for rel in _RIBBON_TEMPLATES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert not pattern.search(text), (
            f"{rel.as_posix()} hand-types a instance/data/brand.json colour"
        )


#: A colour written out rather than read from somewhere: a hex literal, an
#: `rgb()`/`hsl()` function, or one of the wide-gamut forms a design tool
#: exports beside a hex. The last is not a curiosity -- the icon this sweep
#: was written for carried `fill:#863bff` *and*
#: `fill:color(display-p3 .5252 .23 1)` on the same element, so a sweep
#: that read only the hex would have found half of it.
_COLOUR_LITERAL = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|color)\s*\(", re.IGNORECASE
)

#: The one directory whose `.svg` files may write a colour out: the
#: product's own artwork. A mark's ink is not a copy of a declared value,
#: it *is* the declaration -- `assets/brand/convener/brand.json` reads its own
#: `motif.logo_dots` off `convener-mark.svg`'s coral circle, and
#: `assets/brand/convener/README.md` carries the contrast measurements for both.
#: There is nowhere further upstream for those two values to come from,
#: which is exactly what makes every other `.svg` in the repository a copy
#: of something if it carries one.
_ARTWORK_DIR = Path("assets") / "brand"

#: And the three files a generator writes from the charter, whose every
#: colour is a substituted value that `generate_brand_css.py --check` holds
#: to `instance/data/brand.json` character for character. They are full of
#: literals and none of them was typed.
_GENERATED_SVGS = frozenset(
    {ANNOUNCEMENT_SVG_PATH, FLYER_SVG_PATH, BACKGROUND_SVG_PATH}
)


def _tracked_svgs() -> list[Path]:
    """Every `.svg` this repository ships, as git holds them.

    `git ls-files` rather than a directory walk, for two reasons that both
    bite: a build copies the product's mark into `app/public/favicon.svg`,
    which is ignored and would otherwise be swept as though it were a
    committed file; and a scratch drawing in somebody's working copy is not
    something this repository publishes.
    """
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "*.svg"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return sorted(Path(name) for name in listed)


def test_the_sweep_over_committed_drawings_finds_the_drawings() -> None:
    """A sweep that found nothing would pass for free."""
    found = _tracked_svgs()
    assert len(found) >= 4
    assert Path("assets/brand/convener/convener-mark.svg") in found


@pytest.mark.parametrize("rel", _tracked_svgs(), ids=lambda rel: rel.as_posix())
def test_no_committed_drawing_writes_a_colour_out(rel: Path) -> None:
    """Every `.svg` this repository ships takes its colours from
    somewhere, or is the place they come from.

    The defect this closes had shipped in every duplicate's browser tab:
    `app/public/favicon.svg` was a hand-drawn bolt carrying `#863bff` and
    a `color(display-p3)` variant of it, in no charter, in nobody's
    declaration, and invisible to every check in this repository --
    `generate_brand_css.py --check` knows the two stylesheets it writes,
    and the sweeps above knew a list of files nobody had added it to. The
    same scaffold left `app/public/icons.svg` beside it, two of its six
    symbols drawn in `#aa3bff` from the same undeclared purple, referenced
    by nothing and built into every bundle. Both are gone; the cockpit's
    tab shows the product's own mark, copied from `assets/brand/` at build time
    (`app/scripts/copy-mark.mjs`).

    Reading a list of files is what let it hide, so this reads the
    repository instead. Two exemptions, and each is a statement rather
    than a hole:

    * a drawing under `assets/brand/` is the product's own artwork, and its ink
      is the source a charter reads rather than a copy of one;
    * a drawing a generator writes is the charter's own values, held to
      the charter character for character by `--check`.

    Anything else that writes a colour out is writing down a value that
    lives somewhere else, and this is where that stops.
    """
    if rel.is_relative_to(_ARTWORK_DIR) or rel in _GENERATED_SVGS:
        return
    text = (ROOT / rel).read_text(encoding="utf-8")
    found = _COLOUR_LITERAL.findall(text)
    assert not found, (
        f"{rel.as_posix()} writes a colour out ({len(found)} literal(s)). A "
        "drawing this product ships takes its colours from a generated "
        "token or from the charter; only the artwork under assets/brand/ is where "
        "a colour comes from, and only a generated file may carry the "
        "charter's own values"
    )


def test_the_rule_catches_both_forms_the_removed_icon_carried() -> None:
    """The sweep above has nothing left to refuse -- every drawing this
    repository ships is now either the artwork colours come from or a file
    a generator writes -- so the rule itself is exercised here rather than
    left to be proved by whatever happens to be committed.

    Both forms, because the icon carried both on one element: a design
    tool exports a wide-gamut `color(display-p3 ...)` beside the hex it
    falls back to, and a sweep reading only the hex would have called that
    file clean the moment somebody deleted six characters.
    """
    bolt = (
        '<path fill="#863bff" d="M0 0z" style="fill:#863bff;'
        'fill:color(display-p3 .5252 .23 1)"/>'
    )
    assert _COLOUR_LITERAL.findall(bolt) == ["#863bff", "#863bff", "color("]
    for written in ("rgb(1 2 3)", "rgba(1,2,3,.5)", "hsl(210 50% 40%)", "#FFF"):
        assert _COLOUR_LITERAL.search(written), written
    for taken in (
        'fill="currentColor"',
        'stroke="var(--dominant)"',
        'fill="url(#gradient)"',
        'class="motif"',
    ):
        assert not _COLOUR_LITERAL.search(taken), taken


def test_the_cockpits_tab_icon_is_the_products_own_mark() -> None:
    """Copied at build time rather than committed twice, so a tab icon
    cannot drift from the artwork it is meant to be
    (`docs/engineering/content-rules.md`: one notion, one home)."""
    mark = ROOT / "assets" / "brand" / "convener" / "convener-mark.svg"
    script = (ROOT / "app" / "scripts" / "copy-mark.mjs").read_text(encoding="utf-8")
    assert "convener-mark.svg" in script
    assert "favicon.svg" in script
    package = json.loads((ROOT / "app" / "package.json").read_text(encoding="utf-8"))
    for stage in ("prebuild", "predev"):
        assert "scripts/copy-mark.mjs" in package["scripts"][stage]
    ignored = (ROOT / "app" / ".gitignore").read_text(encoding="utf-8").split()
    assert "public/favicon.svg" in ignored
    assert mark.is_file()


def test_nothing_points_at_an_icon_this_repository_no_longer_ships() -> None:
    """The other half of removing a file: a `<link>` or a `<use>` left
    behind would ship a build asking for something that is not there.

    Searched in the markup and the sources a browser is actually served,
    not in the whole repository -- naming a removed file in prose is how a
    reader finds out it was removed, and both this module and
    `app/scripts/copy-mark.mjs` do exactly that.
    """
    listed = subprocess.run(  # nosec B603 B607
        [
            "git",
            "grep",
            "-l",
            "icons.svg",
            "--",
            "app/index.html",
            "app/src",
            "site/src",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    assert listed == []
    index = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
    assert index.count('rel="icon"') == 1
    assert 'href="/favicon.svg"' in index


def test_the_reconstructions_palette_never_reappears() -> None:
    """The mutation this module exists to catch: `stroke="#3D2D7C"`
    restored in a ribbon, or any of the reconstruction's three values typed
    back in anywhere they were taken out of.
    """
    pattern = re.compile(
        "|".join(re.escape(v) for v in _RECONSTRUCTION_VALUES), re.IGNORECASE
    )
    for rel in _GUARDED_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert not pattern.search(text), (
            f"{rel.as_posix()} carries a reconstruction colour"
        )


# --------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------


def _marked_stub() -> str:
    """A stylesheet holding nothing but an empty, markered `:root` block --
    enough for `_splice` to have somewhere to write, and nothing else this
    script would ever need to preserve.
    """
    return f":root {{\n{_BEGIN}\n{_END}\n}}\n"


def _copy(root: Path, rel: Path) -> None:
    """One committed file, copied into a throw-away repository."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8", newline=""
    )


def _declaring_no_charter(root: Path) -> None:
    """This repository's declaration, in a throw-away repository, naming no
    charter.

    The `charter` key is the one thing that has to go, and taking it out is
    what makes both fixtures below mean the same thing wherever this suite
    runs. Each is about an instance that has a charter file or has none;
    a declaration that also *names* one is the third state, which
    `brand.source` refuses -- and which of the three the instance running
    this repository is in is not a property a fixture may inherit.
    Upstream writes its own charter and names none; every repository
    that ships the example as its instance names one and writes none.
    `cli.publication._fixture_root` takes the key out for this reason, and
    this is the same decision at the same seam.
    """
    path = root / published.INSTANCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (ROOT / published.INSTANCE_PATH).read_bytes()
    declared = json.loads(raw.decode("utf-8"))
    if published.CHARTER_KEY in declared:
        del declared[published.CHARTER_KEY]
        raw = (json.dumps(declared, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)


def _wrote_its_own_charter(root: Path) -> None:
    """The charter in force here, written where an instance that wrote its
    own keeps it.

    `brand.source` rather than `brand.INSTANCE_PATH`, so this reads a file
    that exists in either state: upstream's own charter where upstream has
    one, and the charter the declaration names where it names one. What
    the fixture is for is an instance with values of its own, and values
    are what this copies.
    """
    path = root / BRAND_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (ROOT / brand.source(ROOT)).read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="",
    )


def _skeleton(root: Path) -> None:
    """Everything a generation run reads except the instance's own charter:
    the product's default charter, the instance declaration the two
    templates take their names from, and a marked-but-empty stylesheet for
    each of the two spliced targets.
    """
    _copy(root, brand.DEFAULT_PATH)
    _declaring_no_charter(root)
    for rel in (SITE_CSS_PATH, APP_TOKENS_CSS_PATH):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_marked_stub(), encoding="utf-8", newline="")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8", newline="")


#: A motif that is manifestly nobody's -- neither this instance's nor the
#: product's -- so that a test can tell which of the two a build reached
#: for, and never mistake one for a mark somebody drew.
_SYNTHETIC_STROKE = "#123456"
_SYNTHETIC_DOTS = "#654321"
_SYNTHETIC_MOTIF: dict[str, Any] = {
    brand.MOTIF_FAMILY: motifs.RIBBON.name,
    "stroke": _SYNTHETIC_STROKE,
    "width_ratio": 0.02,
    "logo_dots": _SYNTHETIC_DOTS,
}


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository holding a charter of its own at
    `instance/data/brand.json`, the product's default charter beside it,
    and marked-but-empty stylesheets for both spliced targets.
    """
    _skeleton(tmp_path)
    _wrote_its_own_charter(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def default_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A duplicate that has chosen nothing: no `instance/data/brand.json` at all.

    The state the product has to survive, and since 2026-08-26 the state
    it has to *build* in: the product's own palette and the product's own
    motif, all the way to both downloadable templates.
    """
    _skeleton(tmp_path)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    return tmp_path


def test_check_fails_when_a_target_file_does_not_exist_at_all(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A guard around a file that does not exist has to fail loudly, and
    has to say what to run, rather than crash uncaught or silently pass.
    """
    (fake_repo / APP_TOKENS_CSS_PATH).unlink()
    assert main(["--check"]) == 1
    err = capsys.readouterr().err
    assert APP_TOKENS_CSS_PATH.as_posix() in err
    assert COMMAND in err


def test_writing_then_checking_passes(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The loop end to end: generate, and the guard is satisfied."""
    assert main([]) == 0
    assert main(["--check"]) == 0
    assert "matches" in capsys.readouterr().out


def test_a_second_write_changes_nothing_and_says_so(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([]) == 0
    capsys.readouterr()
    assert main([]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_check_leaves_a_stale_file_exactly_as_it_found_it(
    fake_repo: Path,
) -> None:
    """A check that repairs is not a check: it would turn the one signal
    that a file is wrong into a green tick.
    """
    assert main([]) == 0
    css_path = fake_repo / APP_TOKENS_CSS_PATH
    original = css_path.read_text(encoding="utf-8")
    stale = original.replace(_END, "STALE-MUTATION " + _END)
    assert stale != original
    css_path.write_text(stale, encoding="utf-8")
    assert main(["--check"]) == 1
    assert css_path.read_text(encoding="utf-8") == stale


def test_a_hand_edited_generated_token_makes_check_fail(
    fake_repo: Path,
) -> None:
    """Mutation 1: a generated value edited by hand, `instance/data/brand.json`
    untouched. Exactly what a contributor does when they "fix" a colour
    directly in the stylesheet instead of in the brand file.
    """
    assert main([]) == 0
    css_path = fake_repo / SITE_CSS_PATH
    text = css_path.read_text(encoding="utf-8")
    # The value comes off the charter the fixture was given rather than
    # being typed: a hexadecimal written here is one instance's dominant,
    # and the mutation silently stopped being one in a repository drawn by
    # any other charter -- which is a test that passes by changing
    # nothing.
    dominant = _charter_colours(brand.source(ROOT))["dominant"]
    mutated = text.replace(
        f"--dominant:       {dominant};", "--dominant:       #000000;"
    )
    assert mutated != text, (
        f"the generated block carries no `--dominant: {dominant}` to edit, "
        "so this mutation changes nothing and the check below would pass "
        "over an unedited file"
    )
    css_path.write_text(mutated, encoding="utf-8")
    assert main(["--check"]) == 1


def test_brand_json_changed_without_regenerating_makes_check_fail(
    fake_repo: Path,
) -> None:
    """Mutation 2: `instance/data/brand.json` edited, nothing regenerated. Exactly
    what a contributor does when they change the brand file and forget the
    command the header of every generated file names.
    """
    assert main([]) == 0
    brand_path = fake_repo / BRAND_PATH
    data = json.loads(brand_path.read_text(encoding="utf-8"))
    # `dominant_tint` and not `dominant`, deliberately: no pairing in the
    # `contrast` table names it, so the run reaches the file comparison
    # this test is about rather than stopping one step earlier at the
    # contrast gate, which has mutations of its own below.
    data["derived"]["dominant_tint"] = "#000000"
    _write_json(brand_path, data)
    assert main(["--check"]) == 1


def test_missing_markers_fails_loudly_rather_than_silently_matching(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A marker removed by hand has nowhere left to splice into. Silently
    treating that as "nothing to generate" would let `--check` pass over a
    stylesheet that no longer has anywhere the brand file's values reach.
    """
    css_path = fake_repo / SITE_CSS_PATH
    css_path.write_text(":root {\n  --gutter: 1rem;\n}\n", encoding="utf-8")
    assert main(["--check"]) == 1
    assert "markers not found" in capsys.readouterr().err


def test_the_terminal_output_is_ascii(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nothing this repository's Python prints may be non-ASCII: the
    volunteers' console renders it as mojibake.
    """
    main([])
    main(["--check"])
    captured = capsys.readouterr()
    (captured.out + captured.err).encode("ascii")


# --------------------------------------------------------------------------
# One charter, a product default, and a mark that refuses
# --------------------------------------------------------------------------


def _charter(rel: Path) -> dict[str, Any]:
    return dict(json.loads((ROOT / rel).read_text(encoding="utf-8")))


def _charter_colours(rel: Path) -> dict[str, str]:
    return _all_brand_colours(_charter(rel))


def test_the_product_ships_a_charter_of_its_own() -> None:
    """The palette a duplicate that has chosen nothing builds with."""
    assert (ROOT / brand.DEFAULT_PATH).is_file()
    assert (ROOT / brand.source(ROOT)).is_file(), (
        f"the charter in force is {brand.source(ROOT).as_posix()} and this "
        "repository does not hold that file, so nothing here builds"
    )


@pytest.mark.parametrize("rel", CHARTERS_HELD, ids=lambda p: p.as_posix())
def test_every_charter_names_the_same_tokens_as_the_products_own(rel: Path) -> None:
    """The *system* is the product's, and a charter answering a different
    set of names would be no charter for this system at all -- every
    template that reads a colour reads it by name.

    Over every charter this repository holds rather than over the one it
    happens to be drawn by. Written as the default against this instance's
    own, it said nothing at all in a repository where the two are one file,
    which is every repository that ships the example as its instance.
    """
    assert sorted(_charter_colours(rel)) == sorted(_charter_colours(brand.DEFAULT_PATH))


@pytest.mark.parametrize("rel", CHARTERS_HELD, ids=lambda p: p.as_posix())
def test_every_charter_carries_the_same_contrast_obligations(rel: Path) -> None:
    """The pairings belong to the composition, not to a palette: a charter
    recording fewer of them would be measured against less.
    """

    def pairings(path: Path) -> list[str]:
        return sorted(k for k in _charter(path)["contrast"] if not k.startswith("_"))

    assert pairings(rel) == pairings(brand.DEFAULT_PATH)


def test_every_contrast_the_default_charter_claims_recomputes_and_clears_aa() -> None:
    """The whole reason a default palette is allowed to exist. D-16 was an
    *invented* palette that measured worse than the one it replaced; this
    is the parade, held here as well as at the command.
    """
    default = _charter(brand.DEFAULT_PATH)
    assert brand.contrast_problems(default, named="default") == []
    colours = _all_brand_colours(default)
    for name, stored in default["contrast"].items():
        if name.startswith("_"):
            continue
        fg, _, bg = name.rpartition("_on_")
        assert round(contrast_ratio(colours[fg], colours[bg]), 2) == stored
        assert stored >= brand.AA_NORMAL_TEXT, f"{name} is {stored}, below AA"


def test_the_default_charter_carries_a_motif_of_its_own() -> None:
    """Design is never something a duplicate has to supply to start.

    The section carried no default until 2026-08-26, so that no duplicate
    could wear a mark somebody else drew. The mark half of that stands;
    "therefore no default may exist" did not follow from it, and what it
    produced was a clone whose first build stopped asking for a design
    file. This is the other half of that correction: the product's
    charter answers all three fields, and the test below is what keeps
    the answer from drifting into somebody else's.
    """
    section = _charter(brand.DEFAULT_PATH)[brand.MOTIF_KEY]
    wanted = brand.MOTIF_FIELDS[section[brand.MOTIF_FAMILY]]
    assert [field for field in wanted if field not in section] == []


@pytest.mark.skipif(DRAWN_BY_THE_PRODUCTS_OWN, reason=NO_SECOND_PALETTE)
def test_the_default_motif_is_not_the_instances_wearing_the_products_name() -> None:
    """A "default" carrying the mark of whoever happened to draw first
    would leave every duplicate wearing it.
    """
    section = _charter(brand.DEFAULT_PATH)[brand.MOTIF_KEY]
    instance = _charter(brand.source(ROOT))[brand.MOTIF_KEY]
    for field in brand.MOTIF_FIELDS[section[brand.MOTIF_FAMILY]]:
        if field == brand.MOTIF_FAMILY:
            continue
        assert section[field] != instance[field], (
            f"{field} is this instance's own value wearing the product's name"
        )


def test_the_default_motif_is_the_products_own_mark() -> None:
    """Not an invention: every value is read back out of a file this
    repository already ships -- the two colours off `convener-mark.svg`,
    and the stroke weight the same file draws its outer arc at, carried
    onto the half-width `motifs/bracket.py` draws the left bracket at. A
    default motif nobody can trace is exactly what the refusal it replaced
    was afraid of.
    """
    section = _charter(brand.DEFAULT_PATH)[brand.MOTIF_KEY]
    mark = (ROOT / "assets" / "brand" / "convener" / "convener-mark.svg").read_text(
        encoding="utf-8"
    )
    colours = _charter_colours(brand.DEFAULT_PATH)
    assert section["stroke"] == colours["dominant"], (
        "the motif is drawn in the charter's own dominant ink, which "
        "`colour._roles` already names as the motif's colour"
    )
    assert str(section["logo_dots"]) in mark, (
        "the wordmark's dots are the colour of the dot in the mark itself"
    )

    outer_stroke, outer_radius = 68.69, 205.66
    carried = outer_stroke / outer_radius * bracket._OUTER_HALF_WIDTH
    assert abs(section["width_ratio"] - carried) / carried < 0.005, (
        "the stroke weight is the mark's outer arc, at the size the motif "
        "draws it: 0.334 of a radius, carried onto the left bracket's own "
        "half-width, within half a percent"
    )
    assert f'stroke-width="{outer_stroke}"' in mark
    assert f"A {outer_radius} " in mark


@pytest.mark.skipif(DRAWN_BY_THE_PRODUCTS_OWN, reason=NO_SECOND_PALETTE)
def test_the_default_palette_is_not_this_instances_wearing_a_new_name() -> None:
    """A "default" shipping this organisation's own colours would leave a
    duplicate wearing them until somebody remembered to configure
    something.
    """
    default = _charter_colours(brand.DEFAULT_PATH)
    instance = _charter_colours(brand.source(ROOT))
    shared = {
        name for name in default if default[name].lower() == instance[name].lower()
    }
    assert shared == {"white", "black"}, (
        "only the two achromatic ends may coincide; everything else has to "
        f"be the product's own, and these are shared: {sorted(shared)}"
    )


def test_the_charter_in_force_is_the_instances_when_it_has_one(
    fake_repo: Path,
) -> None:
    assert brand.source(fake_repo) == brand.INSTANCE_PATH
    assert brand.colours(brand.load(fake_repo)) == _charter_colours(brand.source(ROOT))


def test_the_charter_in_force_is_the_products_when_the_instance_has_none(
    default_repo: Path,
) -> None:
    assert brand.source(default_repo) == brand.DEFAULT_PATH
    assert brand.colours(brand.load(default_repo)) == _charter_colours(
        brand.DEFAULT_PATH
    )


# --------------------------------------------------------------------------
# `source`: named, written, neither -- and never both
# --------------------------------------------------------------------------


#: A charter this repository ships that is not the product's own default,
#: read off `assets/brand/` rather than typed: the tests below are about choosing
#: one of the others, and which others exist is the directory's answer.
_ANOTHER_CHARTER = next(
    name for name in ROOT_CHARTERS if name != brand.DEFAULT_PATH.parent.name
)


def _name_a_charter(root: Path, name: str) -> None:
    """Write `charter` into a throw-away repository's declaration -- the one
    line a duplicate adds to choose a design it does not copy."""
    path = root / published.INSTANCE_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    data[published.CHARTER_KEY] = name
    _write_json(path, data)


def test_a_duplicate_that_names_a_charter_reads_it_where_upstream_keeps_it(
    default_repo: Path,
) -> None:
    """The whole point of the key: the charter in force is a product file,
    at the path the product maintains it at, and nothing was copied into
    `instance/data/` for it to be chosen."""
    _copy(default_repo, ROOT_CHARTERS[_ANOTHER_CHARTER])
    _name_a_charter(default_repo, _ANOTHER_CHARTER)

    assert brand.source(default_repo) == ROOT_CHARTERS[_ANOTHER_CHARTER]
    assert brand.colours(brand.load(default_repo)) == _charter_colours(
        ROOT_CHARTERS[_ANOTHER_CHARTER]
    )
    assert not (default_repo / brand.INSTANCE_PATH).exists()


def test_a_duplicate_that_names_nothing_still_gets_the_products_own(
    default_repo: Path,
) -> None:
    """`assets/brand/convener/brand.json::_why_a_default`, unweakened by the key
    above: no design file and no name is a duplicate that builds and looks
    finished, which is the state this product has to survive."""
    assert published.CHARTER_KEY not in json.loads(
        (default_repo / published.INSTANCE_PATH).read_text(encoding="utf-8")
    )
    assert brand.source(default_repo) == brand.DEFAULT_PATH


def test_a_charter_this_product_does_not_ship_is_refused_and_the_rest_listed(
    default_repo: Path,
) -> None:
    """Never a silent fall back to the default: a duplicate that misspelt
    its charter would otherwise build, look finished, and wear a design
    nobody chose. `motifs.family` refuses an unknown family exactly this
    way one layer down, and the message lists what may be written
    instead."""
    _name_a_charter(default_repo, _NOT_A_CHARTER)
    with pytest.raises(brand.UnknownCharterError) as raised:
        brand.source(default_repo)
    message = str(raised.value)
    assert _NOT_A_CHARTER in message
    assert published.CHARTER_KEY in message
    for rel in brand.shipped(default_repo):
        assert rel.parent.name in message


def test_naming_a_charter_and_writing_one_is_refused_rather_than_ranked(
    fake_repo: Path,
) -> None:
    """Two declarations of one notion, free to disagree. Whichever won, the
    other would sit in a committed file doing nothing -- so neither does,
    and the refusal names both files and the line to delete."""
    _copy(fake_repo, ROOT_CHARTERS[_ANOTHER_CHARTER])
    _name_a_charter(fake_repo, _ANOTHER_CHARTER)
    with pytest.raises(brand.AmbiguousCharterError) as raised:
        brand.source(fake_repo)
    message = str(raised.value)
    assert brand.INSTANCE_PATH.as_posix() in message
    assert published.INSTANCE_PATH.as_posix() in message
    assert _ANOTHER_CHARTER in message


def test_the_conflict_is_refused_ahead_of_the_name_being_unknown(
    fake_repo: Path,
) -> None:
    """When both are wrong the key is what has to go either way, so that is
    the message: correcting the spelling first would only reach the second
    refusal."""
    _name_a_charter(fake_repo, _NOT_A_CHARTER)
    with pytest.raises(brand.AmbiguousCharterError):
        brand.source(fake_repo)


def test_a_charter_committed_tomorrow_is_selectable_with_no_list_to_edit(
    default_repo: Path,
) -> None:
    """`shipped` reads `assets/brand/` off the directory and everything above
    reads `shipped`: a charter is offered, chosen and drawn with on the
    commit that adds the directory, with no entry to make anywhere."""
    invented = "throwaway"
    assert invented not in {rel.parent.name for rel in brand.shipped(default_repo)}
    made = default_repo / brand.SHIPPED_DIR / invented / brand.SHIPPED_FILE
    made.parent.mkdir(parents=True, exist_ok=True)
    made.write_bytes((default_repo / brand.DEFAULT_PATH).read_bytes())

    assert invented in brand.names(default_repo)
    _name_a_charter(default_repo, invented)
    assert brand.source(default_repo) == made.relative_to(default_repo)


def test_a_named_charter_is_matched_never_built_into_a_path(
    default_repo: Path,
) -> None:
    """A name is only ever answered by matching it against `shipped`, so a
    declaration cannot address a file `assets/brand/` does not hold however it is
    spelt -- including by spelling its way back out of the directory."""
    _name_a_charter(default_repo, "../" + brand.DEFAULT_PATH.parent.as_posix())
    with pytest.raises(brand.UnknownCharterError):
        brand.source(default_repo)


def test_this_repository_takes_exactly_one_of_the_two_routes() -> None:
    """The two routes are alternatives, and a repository is on one of them.

    Upstream takes the first: it has a designer, so it has a file, so its
    declaration carries no name for the resolution above to refuse. Every
    repository that ships the example as its instance takes the second: the example
    collective's declaration names the product's own charter and writes
    none. Both together is what `brand.source` refuses, and this asks that
    of the repository the suite is running in rather than of the one it was
    written in.
    """
    named = published.load_charter(ROOT)
    wrote_one = (ROOT / brand.INSTANCE_PATH).is_file()
    assert not (named and wrote_one), (
        f"this repository names the {named!r} charter and also writes "
        f"{brand.INSTANCE_PATH.as_posix()}; brand.source refuses that, so "
        "nothing here builds"
    )
    assert brand.source(ROOT) == (
        brand.INSTANCE_PATH if wrote_one else brand.chosen(ROOT) or brand.DEFAULT_PATH
    )


# --------------------------------------------------------------------------
# `motif`: absence is answered, incompleteness is refused
# --------------------------------------------------------------------------


def test_a_duplicate_with_no_charter_at_all_is_drawn_with_the_products_motif(
    default_repo: Path,
) -> None:
    """The correction of 2026-08-26, at the reader that carries it.

    Nothing about a seminar series' *design* can be demanded before its
    first build: a duplicate that has written no charter gets the
    product's palette and the product's mark, whole, and finds out that
    it is unconfigured from the banner on its own public pages rather
    than from a build that would not run.
    """
    section = brand.motif(default_repo)
    default = _charter(brand.DEFAULT_PATH)[brand.MOTIF_KEY]
    for field in brand.MOTIF_FIELDS[default[brand.MOTIF_FAMILY]]:
        assert section[field] == default[field]


def test_an_instance_that_wrote_colours_but_no_motif_gets_the_products(
    fake_repo: Path,
) -> None:
    """The same answer one step further in, and the step that matters
    most in practice: somebody edits `instance/data/brand.json` to set their own
    colours and never thinks about `motif` at all. Refusing there would
    be the same absurdity at a smaller scale.

    Whole section or whole section, the rule `load` already applies to
    the file: the product's three values, never two of theirs and one of
    the product's.
    """
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    del data[brand.MOTIF_KEY]
    _write_json(fake_repo / BRAND_PATH, data)

    section = brand.motif(fake_repo)
    default = _charter(brand.DEFAULT_PATH)[brand.MOTIF_KEY]
    # Another charter this repository ships, for the reason
    # `test_a_duplicate_that_has_configured_nothing_builds_every_file`
    # gives: what the second clause refuses is the build reaching for a
    # charter it was not given, and the charter in force is not one of
    # those wherever an instance is drawn by the product's own.
    other = _charter(ROOT_CHARTERS[_ANOTHER_CHARTER])[brand.MOTIF_KEY]
    for field in brand.MOTIF_FIELDS[default[brand.MOTIF_FAMILY]]:
        assert section[field] == default[field]
        if field != brand.MOTIF_FAMILY:
            assert section[field] != other[field]


def test_a_charter_whose_motif_is_incomplete_is_refused_by_the_missing_field(
    fake_repo: Path,
) -> None:
    """Half a motif is not a motif: a ribbon with no colour of its own
    would be drawn in whatever the surrounding ink happens to be.

    And it is not an absence either, so the product's own may not quietly
    complete it -- that would hand back three values that exist in no
    file. The message says both ways out.
    """
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    del data[brand.MOTIF_KEY]["logo_dots"]
    _write_json(fake_repo / BRAND_PATH, data)
    with pytest.raises(brand.MissingMotifError, match="logo_dots") as raised:
        brand.motif(fake_repo)
    message = str(raised.value)
    assert brand.INSTANCE_PATH.as_posix() in message
    assert brand.DEFAULT_PATH.as_posix() in message


def test_a_charter_whose_motif_is_not_an_object_is_refused(fake_repo: Path) -> None:
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    data[brand.MOTIF_KEY] = "the usual one"
    _write_json(fake_repo / BRAND_PATH, data)
    with pytest.raises(brand.MissingMotifError, match=brand.MOTIF_FAMILY):
        brand.motif(fake_repo)


#: A `motif.family` naming a drawing this product does not have. Held
#: against the registry below rather than typed into each test: the word
#: that stood here was `lattice`, and `motifs/lattice.py` draws one now.
_NOT_A_FAMILY = "no-such-drawing"

#: An `instance/config.json::charter` naming a charter this product does not
#: ship, held against `assets/brand/` below for the reason above: a word that
#: quietly becomes a real charter turns a test that proves a refusal into
#: one that proves a lookup.
_NOT_A_CHARTER = "no-such-charter"


def test_the_name_the_charter_refusals_are_proved_with_is_not_a_charter() -> None:
    assert _NOT_A_CHARTER not in ROOT_CHARTERS


def test_the_name_these_refusals_are_proved_with_is_not_a_family() -> None:
    """A placeholder that quietly becomes a real family turns a test that
    proves a refusal into one that proves a lookup."""
    assert _NOT_A_FAMILY not in motifs.FAMILIES


def test_a_charter_still_writing_the_ribbons_own_field_names_is_refused(
    fake_repo: Path,
) -> None:
    """The defect one section down from the colour keys: `ribbon_stroke`
    names the ink after one drawing, and a charter whose motif is a
    lattice would be writing it too.

    Answered by name at the load, and told which two keys to rename,
    rather than meeting a `KeyError` from inside a template.
    """
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    section = data[brand.MOTIF_KEY]
    for old, new in brand.SUPERSEDED_MOTIF_FIELDS.items():
        section[old] = section.pop(new)
    del section[brand.MOTIF_FAMILY]
    _write_json(fake_repo / BRAND_PATH, data)

    with pytest.raises(brand.SupersededCharterError) as raised:
        brand.load(fake_repo)

    message = str(raised.value)
    assert brand.INSTANCE_PATH.as_posix() in message
    assert "Rename the two keys in the file" in message
    for old, new in brand.SUPERSEDED_MOTIF_FIELDS.items():
        assert old in message
        assert new in message


def test_a_motif_that_names_no_family_is_refused_and_says_what_to_add(
    fake_repo: Path,
) -> None:
    """A section that cannot say which drawing it means. Guessing the one
    this product used to draw is the silent fall back the registry exists
    to refuse, so this stops instead and asks for the family by name."""
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    del data[brand.MOTIF_KEY][brand.MOTIF_FAMILY]
    _write_json(fake_repo / BRAND_PATH, data)

    with pytest.raises(brand.SupersededCharterError) as raised:
        brand.load(fake_repo)

    message = str(raised.value)
    assert brand.INSTANCE_PATH.as_posix() in message
    assert brand.MOTIF_FAMILY in message
    assert "Add the family to the section" in message


def test_a_stroke_heavier_than_the_drawings_clear_is_refused(
    fake_repo: Path,
) -> None:
    """The bound that was nowhere in the product until now.

    Three families reserve their own ground against `HEAVIEST_STROKE`, and
    the only thing holding a charter under it was three test modules
    asserting that no charter drew heavier than the heaviest charter --
    true of any set of numbers, and a duplicate writing its own charter
    never runs them. So the refusal is where a charter is read, and this
    is it being read.
    """
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    data[brand.MOTIF_KEY][brand.MOTIF_WIDTH_RATIO] = brand.HEAVIEST_STROKE + 0.001
    _write_json(fake_repo / BRAND_PATH, data)

    with pytest.raises(brand.HeavyStrokeError) as raised:
        brand.load(fake_repo)

    message = str(raised.value)
    assert brand.INSTANCE_PATH.as_posix() in message
    assert str(brand.HEAVIEST_STROKE) in message
    assert str(brand.HEAVIEST_STROKE + 0.001) in message


def test_a_stroke_at_the_bound_itself_loads(fake_repo: Path) -> None:
    """A ceiling, not a limit approached from below: the figure is what
    the clearances were measured *at*, so a charter drawing exactly there
    is the heaviest correct charter rather than the first wrong one."""
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    data[brand.MOTIF_KEY][brand.MOTIF_WIDTH_RATIO] = brand.HEAVIEST_STROKE
    _write_json(fake_repo / BRAND_PATH, data)

    loaded = brand.load(fake_repo)

    assert loaded[brand.MOTIF_KEY][brand.MOTIF_WIDTH_RATIO] == brand.HEAVIEST_STROKE


def test_every_charter_this_repository_holds_is_under_the_bound() -> None:
    """Every charter here, read through the same refusal a duplicate's own
    charter meets: the four the product ships, the one in force for this
    instance, and the one the worked example names. None of them may need
    editing for this bound to arrive, which is the whole claim -- the
    figure was a ceiling already and is now stated as one.

    The charter *in force* rather than `INSTANCE_PATH` by name, which is
    the same set `tests/publication/motifs/` reads and for the same
    reason: an instance that names one of the product's charters rather
    than writing one has no file at that path at all, and the derived
    repository is exactly such an instance. `brand.source` answers with
    the file whichever of the two routes an instance took.
    """
    root = repo_root()
    holdings = {
        brand.source(root),
        brand.source(root, published.EXAMPLE_INSTANCE_ROOT),
        *brand.shipped(root),
    }
    assert len(holdings) >= 4, f"only {len(holdings)} charter(s) were read"
    for rel in sorted(holdings):
        section = brand.charter(root, rel).get(brand.MOTIF_KEY)
        assert isinstance(section, dict)
        assert section[brand.MOTIF_WIDTH_RATIO] <= brand.HEAVIEST_STROKE, (
            f"{rel.as_posix()} draws heavier than {brand.HEAVIEST_STROKE}"
        )


def test_a_family_this_product_cannot_draw_is_refused_by_name(
    fake_repo: Path,
) -> None:
    """Never a fall back to the drawing that happens to exist: the file
    and the name it wrote, and every family it could have written."""
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    data[brand.MOTIF_KEY][brand.MOTIF_FAMILY] = _NOT_A_FAMILY
    _write_json(fake_repo / BRAND_PATH, data)

    with pytest.raises(motifs.UnknownMotifFamilyError) as raised:
        brand.load(fake_repo)

    message = str(raised.value)
    assert brand.INSTANCE_PATH.as_posix() in message
    assert _NOT_A_FAMILY in message
    for name in motifs.FAMILIES:
        assert name in message


def test_the_command_refuses_a_superseded_motif_and_names_the_migration(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Driven rather than read: the build stops before it measures a
    single contrast, because a charter nothing can draw from is not a
    palette question."""
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    del data[brand.MOTIF_KEY][brand.MOTIF_FAMILY]
    _write_json(fake_repo / BRAND_PATH, data)

    assert main([]) == 1
    captured = capsys.readouterr()
    assert "Add the family to the section" in captured.err
    assert "clears AA" not in captured.out


def test_the_command_refuses_a_family_it_cannot_draw(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    data[brand.MOTIF_KEY][brand.MOTIF_FAMILY] = _NOT_A_FAMILY
    _write_json(fake_repo / BRAND_PATH, data)

    assert main([]) == 1
    captured = capsys.readouterr()
    assert _NOT_A_FAMILY in captured.err
    assert motifs.RIBBON.name in captured.err


def test_the_products_own_charter_losing_its_motif_refuses_and_says_whose(
    default_repo: Path,
) -> None:
    """The one refusal a duplicate can meet without having done anything
    wrong, so it has to say so: this is the product being broken, not an
    instance being unconfigured, and the fix is to restore a file rather
    than to hire a designer.
    """
    data = _charter(brand.DEFAULT_PATH)
    del data[brand.MOTIF_KEY]
    _write_json(default_repo / brand.DEFAULT_PATH, data)
    with pytest.raises(brand.MissingMotifError) as raised:
        brand.motif(default_repo)
    message = str(raised.value)
    assert brand.DEFAULT_PATH.as_posix() in message
    for field in brand.MOTIF_COMMON_FIELDS:
        assert field in message
    for drawn in motifs.FAMILIES.values():
        for field in drawn.fields:
            assert field in message


def test_the_ribbon_draws_the_products_mark_when_the_instance_has_none(
    default_repo: Path,
) -> None:
    """The generated posters complete as well, not only the downloadable
    templates: `motifs/` is the other thing that draws the mark.
    """
    default = _charter(brand.DEFAULT_PATH)[brand.MOTIF_KEY]
    assert brand.motif_family(default_repo) == default[brand.MOTIF_FAMILY]
    assert brand.motif_stroke(default_repo) == default["stroke"]
    assert brand.motif_width_ratio(default_repo) == default["width_ratio"]


def test_a_duplicate_that_has_configured_nothing_builds_every_file(
    default_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Driven, not read: build a duplicate that supplies no charter at
    all and watch the command finish.

    Both stylesheets and both downloadable templates are written, the
    product's palette clears AA, and the mark on the two files that
    travel outward is the product's own -- never this instance's.
    """
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "clears AA" in captured.out
    assert brand.DEFAULT_PATH.as_posix() in captured.out
    assert main(["--check"]) == 0

    default = _charter(brand.DEFAULT_PATH)[brand.MOTIF_KEY]
    # The foil is another charter this repository ships rather than the one
    # in force. "Never this instance's" has nothing to exclude where the
    # instance is drawn by the product's own, which is every repository
    # that ships the example as its instance; a charter the build was not
    # given is the
    # claim either way, and this one is a charter in both.
    unchosen = _charter(ROOT_CHARTERS[_ANOTHER_CHARTER])
    other = unchosen[brand.MOTIF_KEY]
    for rel in (ANNOUNCEMENT_SVG_PATH, FLYER_SVG_PATH):
        svg = (default_repo / rel).read_text(encoding="utf-8")
        assert str(default["stroke"]) in svg
        assert str(default["logo_dots"]) in svg
        assert str(other["stroke"]) not in svg
        assert str(other["logo_dots"]) not in svg

    written = (default_repo / SITE_CSS_PATH).read_text(encoding="utf-8")
    assert _charter_colours(brand.DEFAULT_PATH)["field"] in written
    assert _all_brand_colours(unchosen)["field"] not in written


def test_the_command_refuses_a_half_written_mark_and_says_what_is_missing(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal that is left, driven the same way: a `motif` somebody
    wrote and left a field short stops the build, names the file, the
    field and both ways out, and leaves no half-written template behind.
    """
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    del data[brand.MOTIF_KEY]["stroke"]
    _write_json(fake_repo / BRAND_PATH, data)
    (fake_repo / ANNOUNCEMENT_SVG_PATH).unlink(missing_ok=True)

    assert main([]) == 1
    captured = capsys.readouterr()
    assert "stroke" in captured.err
    assert brand.INSTANCE_PATH.as_posix() in captured.err
    assert ANNOUNCEMENT_SVG_PATH.as_posix() in captured.err
    assert not (fake_repo / ANNOUNCEMENT_SVG_PATH).exists(), (
        "a refused template must not be half-written"
    )
    assert "clears AA" in captured.out


def test_a_duplicate_that_brings_only_its_own_mark_builds_completely(
    default_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The complement: an instance may replace the product's motif with
    one of its own without writing a palette, and the product's colours
    carry the rest.
    """
    charter = _charter(brand.DEFAULT_PATH)
    charter[brand.MOTIF_KEY] = _SYNTHETIC_MOTIF
    _write_json(default_repo / BRAND_PATH, charter)

    assert main([]) == 0
    capsys.readouterr()
    assert main(["--check"]) == 0
    assert "clears AA" in capsys.readouterr().out
    svg = (default_repo / ANNOUNCEMENT_SVG_PATH).read_text(encoding="utf-8")
    assert _SYNTHETIC_STROKE in svg
    assert _SYNTHETIC_DOTS in svg
    assert _charter_colours(ROOT_CHARTERS[_ANOTHER_CHARTER])["dominant"] not in svg


# --------------------------------------------------------------------------
# A palette that does not clear AA does not build
# --------------------------------------------------------------------------


def test_a_palette_whose_measurement_no_longer_recomputes_does_not_build(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    data["contrast"]["dominant_on_field"] = 21.0
    _write_json(fake_repo / BRAND_PATH, data)
    assert main([]) == 1
    assert "computes to" in capsys.readouterr().err


def test_a_measurement_of_a_colour_that_does_not_exist_does_not_build(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pairing naming a token nothing declares. Reported rather than
    raising a `KeyError` out of the command: the two halves of the name
    are how a reader finds which colour was renamed or dropped.
    """
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    data["contrast"]["saffron_on_band"] = 4.6
    _write_json(fake_repo / BRAND_PATH, data)
    assert main([]) == 1
    assert "names no such colour" in capsys.readouterr().err


def test_a_palette_that_measures_below_aa_does_not_build(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The clause the whole default rests on, and not a hypothetical:
    darkening the ground under dark text is exactly the move D-16 was
    decided over. The ratios below are honest -- every one recomputes from
    the colours beside it, so the *only* thing wrong with this palette is
    that secondary text on its ground measures 2.93. That is not a file to
    regenerate; it is a palette that must not ship.
    """
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    ground = "#3fb1c2"
    data["colour"]["field"] = ground
    # Recomputed against the charter in force rather than written out.
    # The five figures used to be literals, and they were
    # honest only for one instance's dominant and ink: under another's the
    # generator reported a *mismatch* first and this test lost its
    # subject, which is not the failure it exists to provoke.
    colours = brand.colours(data)
    data["contrast"].update(
        {
            name: round(contrast_ratio(colours[over], ground), 2)
            for name, over in (
                ("dominant_on_field", "dominant"),
                ("black_on_field", "black"),
                ("ink_on_field", "ink"),
                ("ink_muted_on_field", "ink_muted"),
            )
        }
    )
    data["contrast"]["field_on_dominant"] = data["contrast"]["dominant_on_field"]
    assert data["contrast"]["ink_muted_on_field"] < 4.5, (
        "the palette this test is about has to be one that fails AA"
    )
    _write_json(fake_repo / BRAND_PATH, data)
    assert main([]) == 1
    err = capsys.readouterr().err
    assert "below the 4.5" in err
    assert "does not build" in err


# --------------------------------------------------------------------------
# The three files a collaborator downloads
# --------------------------------------------------------------------------

#: The two a volunteer fills in for an event.
_TEMPLATES = (ANNOUNCEMENT_SVG_PATH, FLYER_SVG_PATH)

#: All three, including the one there is nothing to fill in on. Every
#: property below the section heading holds for a file this kit hands out,
#: not for a file with placeholders in it, so each is parametrised over
#: this and the two tests that really are about placeholders say so by
#: using `_TEMPLATES` instead.
_DOWNLOADS = (*_TEMPLATES, BACKGROUND_SVG_PATH)

_RENDERERS = {
    ANNOUNCEMENT_SVG_PATH: brand_templates.render_announcement_template,
    FLYER_SVG_PATH: brand_templates.render_flyer_template,
    BACKGROUND_SVG_PATH: brand_templates.render_video_call_background,
}


@pytest.mark.parametrize("rel", _DOWNLOADS, ids=lambda p: p.name)
def test_the_committed_template_is_what_the_charter_derives(rel: Path) -> None:
    committed = (ROOT / rel).read_text(encoding="utf-8")
    assert committed == _RENDERERS[rel](ROOT), (
        f"{rel.as_posix()} is not what the charter derives; run `{COMMAND}`"
    )


@pytest.mark.parametrize("rel", _DOWNLOADS, ids=lambda p: p.name)
def test_the_committed_template_parses_as_xml(rel: Path) -> None:
    """Found by rendering one in a browser rather than by reading it: `--`
    anywhere inside an XML comment makes the whole document unparseable,
    and this project writes `--` for an em dash everywhere. Chrome drew an
    error page instead of a poster. A parser is cheaper than a browser, so
    the guard is a parser.
    """
    ElementTree.parse(ROOT / rel)


@pytest.mark.parametrize("rel", _DOWNLOADS, ids=lambda p: p.name)
def test_no_colour_in_a_template_comes_from_anywhere_but_the_charter(
    rel: Path,
) -> None:
    """The defect these two files carried for months: `#3D2D7C`,
    `#3FB1C2`, `#F4F1E6` and four greys from no charter at all, in the
    files a collaborator downloads. Every hex in them is now a value the
    charter names.
    """
    charter = load_brand(ROOT)
    allowed = {value.lower() for value in _all_brand_colours(charter).values()}
    allowed |= {
        str(value).lower()
        for key, value in charter[brand.MOTIF_KEY].items()
        if not key.startswith("_") and str(value).startswith("#")
    }
    found = {
        match.lower()
        for match in re.findall(
            r"#[0-9a-fA-F]{6}", (ROOT / rel).read_text(encoding="utf-8")
        )
    }
    assert found, "a template that names no colour is not being checked"
    assert found <= allowed, f"{rel.as_posix()} draws in {sorted(found - allowed)}"


@pytest.mark.parametrize("rel", _DOWNLOADS, ids=lambda p: p.name)
def test_a_template_says_it_is_generated(rel: Path) -> None:
    assert "generate_brand_css.py" in (ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", _DOWNLOADS, ids=lambda p: p.name)
def test_a_template_reaches_out_to_nothing(rel: Path) -> None:
    """The property `app/tests/content/visual-kit.test.tsx` holds from the other
    side, restated where the generator lives so that a change to the
    generator fails in the generator's own suite: an SVG that fetches a
    font or an image is the shared-account dependency again, one request
    further away. The one URL allowed is the SVG namespace, which is an
    identifier and never fetched.
    """
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert "base64" not in text
    assert "@import" not in text
    for reach in ('href="http', 'src="http', "url(http", "url('http"):
        assert reach not in text
    assert (ROOT / rel).stat().st_size < 30_000


def test_the_templates_name_the_instance_the_declaration_names(
    default_repo: Path,
) -> None:
    """The other half of what these files carry outward. A second
    instance's templates say who *it* is, and nothing of the first.
    """
    charter = _charter(brand.DEFAULT_PATH)
    charter[brand.MOTIF_KEY] = _SYNTHETIC_MOTIF
    _write_json(default_repo / BRAND_PATH, charter)

    ours = published.load_identity(default_repo)
    declaration = json.loads(
        (default_repo / published.INSTANCE_PATH).read_text(encoding="utf-8")
    )
    declaration["identity"] = {
        **declaration["identity"],
        "organisation": "AnotherPlace",
        "short_name": "AP",
        "series": "Reading Group",
        "forum": "https://forum.example.org",
    }
    _write_json(default_repo / published.INSTANCE_PATH, declaration)

    svg = brand_templates.render_announcement_template(default_repo)
    assert "AP Reading Group" in svg
    assert "READING GROUP" in svg
    assert "forum.example.org" in svg
    assert ours.organisation not in svg
    assert ours.forum_host not in svg


def test_a_template_refuses_a_palette_whose_own_pairings_fail_aa(
    fake_repo: Path,
) -> None:
    """The pairings these two files create are not all in the charter's
    table -- a caption on a frame, a label beside a QR slot -- and it was
    exactly an unlisted pairing that let one line be set in the page's own
    ground colour, at 1.00, in every poster ever downloaded. So the
    renderer measures its own, whatever palette it is handed.
    """
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    data["colour"]["band"] = data["colour"]["dominant"]
    data["contrast"] = {"_comment": "emptied so the palette gate is not what bites"}
    _write_json(fake_repo / BRAND_PATH, data)
    with pytest.raises(ValueError, match=r"below the 4\.5"):
        brand_templates.render_announcement_template(fake_repo)


def test_every_pairing_the_templates_draw_clears_aa_in_every_charter() -> None:
    """Every palette against the same list, so none is legible by luck."""
    for rel in (*CHARTERS_HELD, brand.DEFAULT_PATH):
        problems = brand_templates._legibility_problems(
            _charter_colours(rel), named=rel.as_posix()
        )
        assert problems == []


def test_the_legibility_list_would_notice_a_pairing_that_failed() -> None:
    """A list that matched nothing would pass for free."""
    assert brand_templates._LEGIBILITY
    flat = dict.fromkeys(_charter_colours(brand.source(ROOT)), "#fecac1")
    problems = brand_templates._legibility_problems(flat, named="a flat palette")
    assert len(problems) == len(brand_templates._LEGIBILITY)


def _inked_text_roles(path: Path, colours: dict[str, str]) -> set[str]:
    """Every colour role either file actually sets a run of type in.

    `fill` inherits down the tree in SVG, and most of the type in these two
    files takes it from an ancestor, so the answer is only right if the walk
    carries the last one it saw.
    """
    by_value = {value.lower(): role for role, value in colours.items()}
    roles: set[str] = set()

    def walk(element: ElementTree.Element, inherited: str | None) -> None:
        fill = element.get("fill", inherited)
        tag = element.tag.removeprefix("{http://www.w3.org/2000/svg}")
        if tag in {"text", "tspan"} and (element.text or "").strip() and fill:
            roles.add(by_value.get(fill.lower(), fill))
        for child in element:
            walk(child, fill)

    walk(ElementTree.parse(path).getroot(), None)
    return roles


def test_the_only_colours_either_template_inks_type_in_are_the_measured_ones() -> None:
    """`_LEGIBILITY` is a claim about markup, and this is what reads it back.

    Every pairing in that list is measured at build time, so a colour named
    there can never ship below AA. What the arithmetic cannot see is a colour
    that is *not* named there: the second word of the wordmark takes
    `field_text` and the reference sets it in `field` itself, which measures
    1.40 to 1.43 on the band at the six charters this repository holds --
    about a third of AA. Moving the markup to `field` and leaving the entry
    beside it alone passed every gate here, `--check` and 2132 tests included,
    because nothing read a rendered `fill` back.

    This does. Set equality in both directions: an ink the markup adds without
    an entry fails, and an entry no run of type is set in any more fails as
    a measurement of nothing. The ground each run sits on is still the
    reviewer's -- resolving that needs the rendered geometry, which is
    `tools/visuals/check-templates.mjs`'s half of the claim.
    """
    colours = _charter_colours(brand.source(ROOT))
    measured = {pairing.ink for pairing in brand_templates._LEGIBILITY}
    # One entry's run is the declaration's to produce, and this reads the
    # declaration for it rather than assuming: the wordmark is set in two
    # tones only where the organisation's name appears inside its forum's
    # host, and in one where it does not (`_wordmark_runs`, which says why
    # inventing a split there would be worse). The example collective is
    # the second case, so in every repository that ships the example as its instance
    # nothing takes the accent and the entry measures a pairing no run of
    # type is set in -- which is correct rather than stale.
    accented = any(
        is_accent
        for _text, is_accent in brand_templates._wordmark_runs(
            published.load_identity(ROOT)
        )
    )
    expected = measured if accented else measured - {brand_templates.WORDMARK_ACCENT}
    for rel in (ANNOUNCEMENT_SVG_PATH, FLYER_SVG_PATH):
        inked = _inked_text_roles(ROOT / rel, colours)
        assert inked == expected, (
            f"{rel.as_posix()} inks type in {sorted(inked)}, and "
            f"_LEGIBILITY measures {sorted(expected)} for this declaration: "
            "every colour a run of type is set in has to have an entry "
            "there, and every entry has to name a colour some run of type "
            "is set in"
        )


# --------------------------------------------------------------------------
# The third file: the video-call background
# --------------------------------------------------------------------------


def _background_texts(svg: str) -> list[str]:
    """Every string the background actually sets as type, in order."""
    root = ElementTree.fromstring(svg)
    return [
        "".join(node.itertext()).strip()
        for node in root.iter("{http://www.w3.org/2000/svg}text")
    ]


def test_every_line_on_the_background_is_a_declared_string(
    default_repo: Path,
) -> None:
    """The defect this file replaced: a hand-drawn PNG whose middle line
    read `THE PLACE TO DISCUSS ANIMAL BEHAVIOUR` -- a third string, in no
    declaration, agreeing with neither `identity.strapline` nor
    `identity.tagline`, and invisible to every check in this repository
    because nothing here reads an image.

    So this asserts the whole list and not a membership: five lines, three
    of them declared values and two of them the product's own label. A
    sixth would fail here whatever it said.
    """
    charter = _charter(brand.DEFAULT_PATH)
    charter[brand.MOTIF_KEY] = _SYNTHETIC_MOTIF
    _write_json(default_repo / BRAND_PATH, charter)

    declaration = json.loads(
        (default_repo / published.INSTANCE_PATH).read_text(encoding="utf-8")
    )
    declaration["identity"] = {
        **declaration["identity"],
        "organisation": "ReadingRoomTrust",
        "strapline": "Read together",
        "forum": "https://forum.example.org",
    }
    _write_json(default_repo / published.INSTANCE_PATH, declaration)

    texts = _background_texts(
        brand_templates.render_video_call_background(default_repo)
    )
    assert texts == [
        "READING ROOM TRUST",
        "READ TOGETHER",
        "FORUM.EXAMPLE.ORG",
        *brand_templates._CODE_LABEL,
    ]


def test_the_background_carries_no_word_of_this_instance_for_another(
    default_repo: Path,
) -> None:
    """The other half, and the reason the file had to stop being a PNG: a
    duplicate's own background says who *it* is, and nothing of the first
    instance.

    The invented values are held apart from this instance's before they
    are used, because a duplicate that happened to write one of them
    would leave the three assertions below passing for a reason that is
    not separation. `Read together` stood in the strapline here and is
    the strapline `examples/the-example-collective/` declares, so in a repository whose
    instance is the example -- a derived one, and every duplicate before
    it declares its own -- the check demanded the absence of a string the
    duplicate was told to write.
    """
    charter = _charter(brand.DEFAULT_PATH)
    charter[brand.MOTIF_KEY] = _SYNTHETIC_MOTIF
    _write_json(default_repo / BRAND_PATH, charter)

    ours = published.load_identity(ROOT)
    theirs = {
        "organisation": "ReadingRoomTrust",
        "strapline": "Meet weekly",
        "forum": "https://forum.example.org",
    }
    assert theirs["organisation"] != ours.organisation
    assert theirs["strapline"] != ours.strapline
    assert ours.forum_host not in theirs["forum"]

    declaration = json.loads(
        (default_repo / published.INSTANCE_PATH).read_text(encoding="utf-8")
    )
    declaration["identity"] = {**declaration["identity"], **theirs}
    _write_json(default_repo / published.INSTANCE_PATH, declaration)

    svg = brand_templates.render_video_call_background(default_repo)
    assert ours.organisation not in svg
    assert ours.forum_host not in svg
    assert ours.strapline.upper() not in svg


def test_a_long_name_on_the_background_shrinks_instead_of_overflowing() -> None:
    """SVG does not wrap, and D-08 names the overflowing hand-made poster
    as a real, lived failure. A name twice the length of this instance's
    has to come back smaller, and small enough to fit the plate it is set
    in -- not merely smaller."""
    heavy = typeface.HEAVY
    short = brand_templates._fitted_font_size(
        "READING ROOM", cap_height=76.0, weight=heavy, available=1000.0
    )
    long = brand_templates._fitted_font_size(
        "READING ROOM AND LENDING LIBRARY TRUST",
        cap_height=76.0,
        weight=heavy,
        available=1000.0,
    )
    assert long < short
    assert (
        typeface.width(
            "READING ROOM AND LENDING LIBRARY TRUST", size=long, weight=heavy
        )
        <= 1000.0
    )
    # And a name that already fits is never shrunk merely for existing.
    assert short == pytest.approx(76.0 / brand_templates._CAP_HEIGHT_EM)


#: How far above its slot the code's label reaches: the higher of its
#: two baselines, plus the capitals that sit on it.
_LABEL_BAND = brand_templates._CODE_LABEL_BASELINES[0] + brand_templates._CODE_LABEL_CAP


def _sampled_motif(
    family: str, width: float, height: float
) -> list[tuple[float, float]]:
    """Points on the rendered drawing, not the waypoints it is fitted to.

    `motifs.safe_margins` answers from the waypoints, which is the right
    place to *derive* a margin from; this walks the segments that are
    actually drawn, so the tests below are a check on the composition
    rather than a restatement of the arithmetic that placed it. Both kinds
    of segment this product draws are walked: the ribbon's cubics, and the
    straight lines every other family is made of.
    """
    commands: list[tuple[str, list[float]]] = []
    for line in motifs.path(family, width, height).splitlines():
        parts = line.split()
        commands.append((parts[0], [float(value) for value in parts[1:]]))
    points: list[tuple[float, float]] = []
    current = (0.0, 0.0)
    for kind, numbers in commands:
        if kind == "M":
            current = (numbers[0], numbers[1])
            points.append(current)
            continue
        if kind == "L":
            end = (numbers[0], numbers[1])
            for step in range(1, 41):
                t = step / 40
                points.append(
                    (
                        current[0] + (end[0] - current[0]) * t,
                        current[1] + (end[1] - current[1]) * t,
                    )
                )
            current = end
            continue
        c1 = (numbers[0], numbers[1])
        c2 = (numbers[2], numbers[3])
        end = (numbers[4], numbers[5])
        for step in range(1, 41):
            t = step / 40
            u = 1 - t
            x = (
                u**3 * current[0]
                + 3 * u**2 * t * c1[0]
                + 3 * u * t**2 * c2[0]
                + t**3 * end[0]
            )
            y = (
                u**3 * current[1]
                + 3 * u**2 * t * c1[1]
                + 3 * u * t**2 * c2[1]
                + t**3 * end[1]
            )
            points.append((x, y))
        current = end
    return points


def test_the_background_keeps_the_ribbon_off_every_word_it_sets() -> None:
    """The property `motifs.safe_margins` exists to give the plate, held
    against the file that is actually committed.

    Both boxes are read out of the rendered document rather than
    recomputed here, and the ribbon is walked as the cubics it is drawn as
    rather than as the waypoints it is fitted to -- so this fails both
    ways round: a block moved onto the stroke, and a margin that agreed
    with the waypoints while the drawn curve went further.

    Neither block may be crossed. The plate carries three lines of type,
    and a heavy stroke behind dark type is unreadable type; the code carries
    a symbol whose whole job is to be scanned, and a stroke across it
    destroys modules no error correction was sized for. Half the stroke's
    own width is added to every box, because a `d` attribute describes a
    centreline and the stroke is painted either side of it.
    """
    width, height = (
        brand_templates.BACKGROUND_WIDTH,
        brand_templates.BACKGROUND_HEIGHT,
    )
    half = motifs.stroke_width(width, height, ratio=brand.motif_width_ratio(ROOT)) / 2

    document = ElementTree.fromstring(
        (ROOT / BACKGROUND_SVG_PATH).read_text(encoding="utf-8")
    )
    white = _charter_colours(brand.source(ROOT))["white"]
    boxes = [
        (
            float(rect.get("x", "0")),
            float(rect.get("y", "0")),
            float(rect.get("x", "0")) + float(rect.get("width", "0")),
            float(rect.get("y", "0")) + float(rect.get("height", "0")),
        )
        for rect in document.iter("{http://www.w3.org/2000/svg}rect")
        if rect.get("fill") == white
    ]
    assert len(boxes) == 2, "the plate and the code slot are what this checks"
    # The code's own label sits above its slot, on the field rather than
    # on white, so it has no rectangle of its own to read: the slot is
    # grown upwards by the label's own two baselines instead.
    lowest = max(boxes, key=lambda box: box[1])
    boxes = [
        box if box is not lowest else (box[0], box[1] - _LABEL_BAND, box[2], box[3])
        for box in boxes
    ]

    for x, y in _sampled_motif(brand.motif_family(ROOT), width, height):
        for x0, y0, x1, y1 in boxes:
            assert not (x0 - half < x < x1 + half and y0 - half < y < y1 + half), (
                f"the motif crosses ({x0:.0f}, {y0:.0f})-({x1:.0f}, {y1:.0f}) "
                f"at ({x:.1f}, {y:.1f})"
            )


def test_no_family_draws_across_the_code_this_background_sets() -> None:
    """The plate moves with the margins the family gives, so a family can
    never be drawn across it. The code's slot does not: it sits at a fixed
    distance from the bottom right corner, measured off the original, and
    nothing about it is derived from the drawing beside it.

    So the clearance the slot has is a property of each family rather than
    of the composition, and every family a charter may name is held to it
    here -- a stroke across a symbol whose whole job is to be scanned
    destroys modules no error correction was sized for.
    """
    width, height = (
        brand_templates.BACKGROUND_WIDTH,
        brand_templates.BACKGROUND_HEIGHT,
    )
    box = (
        width - brand_templates._CODE_RIGHT_GAP - brand_templates._CODE_SIDE,
        height - brand_templates._CODE_BOTTOM_GAP - brand_templates._CODE_SIDE,
    )
    top = box[1] - _LABEL_BAND

    for name in sorted(motifs.FAMILIES):
        half = motifs.stroke_width(width, height, ratio=0.03) / 2
        for x, y in _sampled_motif(name, width, height):
            if not (0.0 <= x <= width and 0.0 <= y <= height):
                continue  # the ribbon's connector, drawn well off the page
            assert not (x > box[0] - half and y > top - half), (
                f"{name} reaches ({x:.1f}, {y:.1f}), inside the corner the "
                f"code and its label occupy from ({box[0]:.0f}, {top:.0f})"
            )


# --------------------------------------------------------------------------
# The keys name positions, and no key names a hue
# --------------------------------------------------------------------------

#: Colour words a charter key may not be built from. Not a complete
#: vocabulary of English colours: the three the charter used to carry, the
#: hues those three actually held in each of the palettes this repository
#: ships, and the common neighbours of both. A key named after a hue is
#: wrong whichever palette it is read in, because the next palette chooses
#: its own colours and inherits the name.
_HUE_WORDS = frozenset(
    [
        "amber",
        "beige",
        "black",
        "blue",
        "bronze",
        "brown",
        "coral",
        "cream",
        "crimson",
        "cyan",
        "emerald",
        "fuchsia",
        "gold",
        "green",
        "grey",
        "indigo",
        "ivory",
        "jade",
        "lilac",
        "lime",
        "magenta",
        "maroon",
        "mauve",
        "moss",
        "navy",
        "ochre",
        "olive",
        "orange",
        "peach",
        "pink",
        "plum",
        "purple",
        "red",
        "rose",
        "ruby",
        "saffron",
        "salmon",
        "sand",
        "scarlet",
        "sepia",
        "silver",
        "slate",
        "stone",
        "tan",
        "teal",
        "turquoise",
        "violet",
        "white",
        "yellow",
    ]
)

#: The two keys that do name a hue, and the value each has to hold for the
#: name to be true. They are exempt from the rule above for one reason and
#: it is checked rather than asserted: `white` is white and `black` is
#: black in every charter, so neither name can put a colour in a reader's
#: head that the file does not hold.
_ACHROMATIC = {"white": "#ffffff", "black": "#000000"}


def _tracked_charters() -> tuple[Path, ...]:
    """Every `brand.json` this repository tracks, from `git ls-files`.

    Listed rather than written down here, so that a charter added later --
    another worked example, another instance -- is held to the same rule
    without anybody remembering to add it.
    """
    listed = subprocess.run(
        ["git", "ls-files", "*brand.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return tuple(Path(path) for path in listed)


def _charter_key_names(charter: dict[str, Any]) -> list[str]:
    """Every key in a charter that names a colour: the palette, the roles
    written beside it, the derived values and the contrast pairings."""
    names = list(charter["colour"]) + list(charter["derived"])
    names += list(charter["colour"].get("_roles", {}))
    names += list(charter["contrast"])
    return names


def test_every_charter_the_repository_tracks_is_held_to_the_naming_rule() -> None:
    """A sweep that found no charter would pass for free."""
    tracked = _tracked_charters()
    assert set(tracked) >= {brand.DEFAULT_PATH, brand.source(ROOT)}, (
        f"git ls-files found {[p.as_posix() for p in tracked]}, which does not "
        "include the product's own charter and the one in force here"
    )


@pytest.mark.parametrize("rel", _tracked_charters(), ids=lambda p: p.as_posix())
def test_no_colour_key_in_a_charter_names_a_hue(rel: Path) -> None:
    """The keys are positions in the composition: `dominant` is the ink the
    headlines, the ribbon and the wordmark are drawn in, `field` is the
    ground that fills the page, `band` is what runs across it.

    They used to be `purple`, `turquoise` and `cream`, and the product's
    own charter holds a navy under the first and a coral under the second.
    Every template reads a colour by name, so one palette's hue became
    every later palette's key, and a reader who trusted the key had the
    wrong colour in their head each time.
    """
    charter = _charter(rel)
    for key in _charter_key_names(charter):
        if key.startswith("_"):
            # Commentary. `derived._coral` is a note about a colour that
            # really is a coral, and a note is prose about the palette
            # rather than a name anything reads a colour by.
            continue
        for word in key.split("_"):
            if word in _ACHROMATIC:
                continue
            assert word not in _HUE_WORDS, (
                f"{rel.as_posix()}: the key {key!r} names the hue {word!r}; "
                "a charter key names the position a colour holds in the "
                "composition, which is true of every palette"
            )


@pytest.mark.parametrize("rel", _tracked_charters(), ids=lambda p: p.as_posix())
def test_the_two_keys_that_do_name_a_hue_hold_it(rel: Path) -> None:
    """`white` and `black` keep their names, and this is the whole reason:
    each holds the colour it names, in every charter."""
    colours = _charter_colours(rel)
    for name, value in _ACHROMATIC.items():
        assert colours[name].lower() == value, (
            f"{rel.as_posix()}: colour.{name} holds {colours[name]}, so the "
            "name no longer says what the value is"
        )


# --------------------------------------------------------------------------
# Nor does any custom property the stylesheets declare
# --------------------------------------------------------------------------

#: Every stylesheet this repository generates, read whole rather than
#: between its markers: the generated block is part of the file, and a hue
#: typed into the hand-authored half would be the same wrong name one
#: splice away from the same reader.
_GENERATED_STYLESHEETS = (SITE_CSS_PATH, APP_TOKENS_CSS_PATH)

#: A custom property being declared -- `--name:` at the head of a
#: declaration, not `var(--name)` where one is read.
_DECLARED_PROPERTY = re.compile(r"(--[a-z][a-z0-9-]*)\s*:")

#: `/* ... */`, dropped before the sweep so that a comment quoting a
#: declaration is prose rather than a declaration.
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _declared_properties(css: str) -> list[str]:
    return _DECLARED_PROPERTY.findall(_CSS_COMMENT.sub(" ", css))


def _stylesheet_sources() -> dict[str, str]:
    """The CSS this repository writes: the two committed stylesheets, and
    the poster page's own `:root` block, which `visual.py` derives from the
    same charter under the same names."""
    sources = {
        rel.as_posix(): (ROOT / rel).read_text(encoding="utf-8")
        for rel in _GENERATED_STYLESHEETS
    }
    sources["convener_ops/publication/visual.py::_root_css_block"] = (
        visual._root_css_block(brand.colours(brand.load(ROOT)))
    )
    return sources


@pytest.mark.parametrize("name", sorted(_stylesheet_sources()))
def test_no_custom_property_in_a_generated_stylesheet_names_a_hue(
    name: str,
) -> None:
    """The same rule the charter keys are held to, one step downstream.

    A stylesheet ships to every duplicate, and each duplicate reads it
    against its own palette. `--purple` fed `colour.dominant` for as long
    as one charter existed; the product's own charter holds a navy there
    and the worked example a moss green, so the name told three readers
    three different untruths from one line of CSS. Both stylesheets say
    `--field` and `--dominant` now. They were two vocabularies for a
    while, the cockpit's `--primary`/`--accent` being positions too and no
    hues either -- which is why this test stayed green over a cockpit that
    filled twenty-five class lists with the field as a button or a label.
    Naming no hue is the weaker half of the rule; the other half is that
    the position a name gives has to be the one the composition allows,
    and that is measured in `test_cockpit.py`.
    """
    properties = _declared_properties(_stylesheet_sources()[name])
    assert properties, f"{name} declares no custom property to check"
    for prop in properties:
        for word in prop.lstrip("-").split("-"):
            if word in _ACHROMATIC:
                # `--white`, `--white-rgb`, `--black`. Exempt for the
                # reason `test_the_two_keys_that_do_name_a_hue_hold_it`
                # checks rather than asserts: each is fed the charter key
                # of the same name, and that key holds the colour it names
                # in every charter.
                continue
            assert word not in _HUE_WORDS, (
                f"{name}: the custom property {prop!r} names the hue "
                f"{word!r}; a duplicate reads this stylesheet against its "
                "own palette, where the name holds a different colour"
            )


def test_a_charter_still_naming_its_colours_after_hues_is_refused(
    fake_repo: Path,
) -> None:
    """What a duplicate meets if it upgrades without running the migration.

    Every reader looks a colour up by name, so a charter under the old
    names answers none of them. The refusal names the file and the command
    that renames it; a `KeyError` raised from inside a format string names
    neither.
    """
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    data["colour"] = {
        old: data["colour"][new] for old, new in brand.SUPERSEDED_COLOURS.items()
    }
    _write_json(fake_repo / BRAND_PATH, data)

    with pytest.raises(brand.SupersededCharterError) as raised:
        brand.load(fake_repo)
    message = str(raised.value)
    assert brand.INSTANCE_PATH.as_posix() in message
    assert "Rename the keys in the file" in message
    for old in brand.SUPERSEDED_COLOURS:
        assert old in message


def test_the_command_stops_on_a_charter_that_still_names_hues(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same refusal where a person meets it, and before any file is
    written: nothing this charter names can be measured, so there is
    nothing to say about contrast yet."""
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    data["colour"] = {
        old: data["colour"][new] for old, new in brand.SUPERSEDED_COLOURS.items()
    }
    _write_json(fake_repo / BRAND_PATH, data)

    assert main([]) == 1
    captured = capsys.readouterr()
    assert "Rename the keys in the file" in captured.err
    assert "clears AA" not in captured.out
