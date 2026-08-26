"""The design tokens, and the guards that keep them derived from one file.

`data/brand.json` measured the designer's own colours. Before this module
existed, two implementations each carried their own hand-typed copy of them --
`site/src/style.css` and `app/src/design/tokens.css` -- and the application
had drifted to a reconstruction's palette without anyone deciding that on
purpose: purple on turquoise measured 4.44 there, below AA, where the
measured charter gives 7.93, AAA (`docs/superpowers/deferred-work.md`, entry 1).
`scripts/generate_brand_css.py` derives both from the brand file instead,
and this module holds what makes that stick.

A third file, `app/src/design/tokens.ts`, used to be generated here too and
was covered by this module's own tests. It was retired -- nothing
under `app/src` ever imported it -- so it is guarded only by
`test_the_reconstructions_palette_never_reappears` staying silent about it
now, not by a generation test for a file that no longer exists.

**The loop is proved, not assumed**, the same way `test_schema_doc.py` proves
it for the handbook appendix: the tests below read the committed files off
disk and compare them with what today's `data/brand.json` derives. That
catches a token hand-edited without regenerating, and a `data/brand.json`
value changed without regenerating -- the two mutations named in this task's
own brief.

**Contrast is recomputed, not re-read.** `data/brand.json` carries measured
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
that: one asks whether any of `data/brand.json`'s own colours are hand-typed
in either template (they must come from a generated CSS custom property or
a Tailwind class instead), and one asks whether the reconstruction's three
known-wrong values have reappeared anywhere across every file this task
touched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
from generate_brand_css import (
    _BEGIN,
    _END,
    ANNOUNCEMENT_SVG_PATH,
    APP_TOKENS_CSS_PATH,
    BRAND_PATH,
    COMMAND,
    FLYER_SVG_PATH,
    SITE_CSS_PATH,
    load_brand,
    main,
    render_app_tokens_css,
    render_site_css,
)

from convener_ops import brand, brand_templates, published, ribbon
from convener_ops.brand import (
    contrast_ratio,
    hex_to_rgb,
    relative_luminance,
    rgb_triplet,
    rgba,
)
from convener_ops.paths import repo_root

ROOT = repo_root()

#: The templates that draw the ribbon motif directly, outside any generated
#: stylesheet. None may hand-type a colour `data/brand.json` carries; each
#: must take it from a generated token instead. `layout.njk` joined this list
#: when the shared masthead grew its own loop, so every page built on it --
#: not only the home page -- carries the motif (D-18).
_RIBBON_TEMPLATES = (
    Path("site") / "src" / "index.njk",
    Path("site") / "src" / "_includes" / "layout.njk",
    Path("app") / "src" / "auth" / "Login.tsx",
)

#: Every file this task touched. None of them may ever carry the
#: reconstruction's palette again.
_GUARDED_FILES = (
    Path("site") / "src" / "style.css",
    Path("site") / "src" / "index.njk",
    Path("app") / "src" / "design" / "tokens.css",
    Path("app") / "src" / "auth" / "Login.tsx",
    # The two files a collaborator downloads. They carried
    # all three of these values until they stopped being drawn by hand.
    ANNOUNCEMENT_SVG_PATH,
    FLYER_SVG_PATH,
)

#: The reconstruction's own three values, exactly as they shipped: the
#: application's deep-purple accent, its turquoise primary, and its
#: cyan-tinted paper. See `docs/superpowers/deferred-work.md`, entry 1.
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
        f"{SITE_CSS_PATH.as_posix()} is not what {BRAND_PATH.as_posix()}"
        f" derives; run `{COMMAND}` from `tools/`."
    )


def test_the_committed_app_tokens_css_is_what_brand_json_derives() -> None:
    committed = (ROOT / APP_TOKENS_CSS_PATH).read_text(encoding="utf-8")
    assert committed == render_app_tokens_css(ROOT), (
        f"{APP_TOKENS_CSS_PATH.as_posix()} is not what {BRAND_PATH.as_posix()}"
        f" derives; run `{COMMAND}` from `tools/`."
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
    """`data/brand.json`'s `contrast` section names a foreground and a
    ground in its own key (`purple_on_turquoise`); this looks both up and
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
            f"{name}: data/brand.json claims {stored}, "
            f"{colours[fg]} on {colours[bg]} computes to {computed}"
        )
        checked += 1
    # Every entry data/brand.json currently carries -- a change to that
    # section without a matching change here would otherwise pass silently.
    # Nine at first, plus two the verify page's own
    # panel needed (turquoise_text_on_cream, ink_muted_on_cream), plus one
    # (turquoise_on_purple) the accessibility sweep found had gone
    # unnamed.
    assert checked == 12


def test_purple_on_turquoise_is_the_measurement_d16_turned_on() -> None:
    """The one number this whole task exists over: a reconstruction that
    darkened the ground under dark text shipped 4.44, below AA for normal
    text, and the measured charter that replaced it clears it.

    The two colours are read from the charter in force rather than typed.
    They used to be typed, and the two hexadecimal values
    in them were `data/brand.json`'s own -- one instance's declared
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
    computed = round(contrast_ratio(palette["purple"], palette["turquoise"]), 2)
    assert computed == charter["contrast"]["purple_on_turquoise"]
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


def test_the_page_ground_is_turquoise_not_white() -> None:
    """D-18: the showcase's ground is turquoise, crossed by cream bands --
    the inverse of the white-ground/turquoise-accent design that stood
    before this task. `body`'s own background is the one declaration that
    carries it; a reversion to `--paper` would put the whole composition
    back the wrong way round without any generated-token test noticing,
    since that check only covers the `:root` block, not how the rest of
    the stylesheet uses it.
    """
    css = (ROOT / SITE_CSS_PATH).read_text(encoding="utf-8")
    block = _rule_block(css, "body")
    assert "background: var(--turquoise);" in block
    assert "var(--paper)" not in block


def test_no_selector_reverts_to_a_colour_that_fails_aa_on_the_new_ground() -> None:
    """Turning the ground turquoise (D-18) made several selectors move off
    the white/paper ground they were designed against, onto one where their
    old colour fails AA: turquoise-d on turquoise measures 3.81, ink-faint
    on turquoise measures 3.51, and white on a turquoise fill measures 1.61
    -- all below the 4.5 floor for normal text (`data/brand.json`'s
    `_forbidden` note). Each of these selectors was moved to a colour that
    clears AA on whichever ground it can now appear on; this pins that each
    one stays off the value that would fail there again.

    `.archive__action:hover` joined this dict late: it was found early
    (a solid turquoise fill under white text, 1.61 -- measured at 2.54 by
    a real browser) and deliberately left it, out of its own scope, for
    the accessibility task to fix. That task moved it to the same purple
    fill `.archive__action--alt:hover` already used; this is the guard
    that keeps it from reverting.
    """
    css = (ROOT / SITE_CSS_PATH).read_text(encoding="utf-8")
    risky: dict[str, str] = {
        "a": "var(--turquoise-d)",
        ".hero__title em": "var(--turquoise-d)",
        ".feature__vol": "var(--turquoise-d)",
        ".archive__date": "var(--ink-faint)",
        ".archive__action--disabled": "var(--ink-faint)",
        ".btn--primary": "var(--turquoise)",
        ".archive__action:hover": "var(--turquoise)",
    }
    for selector, bad_value in risky.items():
        block = _rule_block(css, selector)
        assert bad_value not in block, (
            f"{selector} carries {bad_value}, which fails AA on the "
            "turquoise field this task made the page's ground"
        )


# --------------------------------------------------------------------------
# No colour hand-typed outside a generated token
# --------------------------------------------------------------------------


def test_no_brand_colour_is_hand_typed_in_the_ribbon_templates() -> None:
    """No colour that appears in `data/brand.json` is hand-typed anywhere
    else -- including inside a template. Both ribbons draw with a stroke
    the surrounding CSS/Tailwind sets, never an attribute of their own.
    """
    brand = load_brand(ROOT)
    colours = set(_all_brand_colours(brand).values())
    pattern = re.compile("|".join(re.escape(v) for v in colours), re.IGNORECASE)
    for rel in _RIBBON_TEMPLATES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert not pattern.search(text), (
            f"{rel.as_posix()} hand-types a data/brand.json colour"
        )


def test_the_reconstructions_palette_never_reappears() -> None:
    """The mutation this task exists to catch: `stroke="#3D2D7C"` restored
    in a ribbon, or any of the reconstruction's three values typed back in
    anywhere this task removed them from.
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


def _skeleton(root: Path) -> None:
    """Everything a generation run reads except the instance's own charter:
    the product's default charter, the instance declaration the two
    templates take their names from, and a marked-but-empty stylesheet for
    each of the two spliced targets.
    """
    _copy(root, brand.DEFAULT_PATH)
    _copy(root, published.INSTANCE_PATH)
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
    "ribbon_stroke": _SYNTHETIC_STROKE,
    "ribbon_width_ratio": 0.02,
    "logo_dots": _SYNTHETIC_DOTS,
}


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository holding this instance's own `data/brand.json`, the
    product's default charter beside it, and marked-but-empty stylesheets
    for both spliced targets.
    """
    _skeleton(tmp_path)
    _copy(tmp_path, BRAND_PATH)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def default_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A duplicate that has chosen nothing: no `data/brand.json` at all.

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
    """Mutation 1: a generated value edited by hand, `data/brand.json`
    untouched. Exactly what a contributor does when they "fix" a colour
    directly in the stylesheet instead of in the brand file.
    """
    assert main([]) == 0
    css_path = fake_repo / SITE_CSS_PATH
    text = css_path.read_text(encoding="utf-8")
    mutated = text.replace("--purple:       #012765;", "--purple:       #000000;")
    assert mutated != text
    css_path.write_text(mutated, encoding="utf-8")
    assert main(["--check"]) == 1


def test_brand_json_changed_without_regenerating_makes_check_fail(
    fake_repo: Path,
) -> None:
    """Mutation 2: `data/brand.json` edited, nothing regenerated. Exactly
    what a contributor does when they change the brand file and forget the
    command the header of every generated file names.
    """
    assert main([]) == 0
    brand_path = fake_repo / BRAND_PATH
    data = json.loads(brand_path.read_text(encoding="utf-8"))
    # `purple_tint` and not `purple`, deliberately: no pairing in the
    # `contrast` table names it, so the run reaches the file comparison
    # this test is about rather than stopping one step earlier at the
    # contrast gate, which has mutations of its own below.
    data["derived"]["purple_tint"] = "#000000"
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
    assert brand.source(ROOT) == brand.INSTANCE_PATH, (
        "this instance has values of its own and must still build from them"
    )


def test_the_default_charter_names_the_same_tokens_as_this_instances() -> None:
    """The *system* is the product's, and a default answering a different
    set of names would be no default for this system at all -- every
    template that reads a colour reads it by name.
    """
    assert sorted(_charter_colours(brand.DEFAULT_PATH)) == sorted(
        _charter_colours(BRAND_PATH)
    )


def test_the_default_charter_carries_the_same_contrast_obligations() -> None:
    """The pairings belong to the composition, not to a palette: a default
    recording fewer of them would be measured against less.
    """

    def pairings(rel: Path) -> list[str]:
        return sorted(k for k in _charter(rel)["contrast"] if not k.startswith("_"))

    assert pairings(brand.DEFAULT_PATH) == pairings(BRAND_PATH)


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
    assert [field for field in brand.MOTIF_FIELDS if field not in section] == []


def test_the_default_motif_is_the_products_own_mark() -> None:
    """Not a variant of this instance's, and not an invention either.

    Every value is read back out of a file this repository already
    ships -- the two colours off `convener-mark.svg`, and the stroke
    weight the same file draws its inner arc at, carried onto the two
    curls `ribbon.py` builds. A default motif nobody can trace is exactly
    what the refusal it replaced was afraid of.
    """
    section = _charter(brand.DEFAULT_PATH)[brand.MOTIF_KEY]
    instance = _charter(BRAND_PATH)[brand.MOTIF_KEY]
    for field in brand.MOTIF_FIELDS:
        assert section[field] != instance[field], (
            f"{field} is this instance's own value wearing the product's name"
        )

    mark = (ROOT / "brand" / "convener" / "convener-mark.svg").read_text(
        encoding="utf-8"
    )
    colours = _charter_colours(brand.DEFAULT_PATH)
    assert section["ribbon_stroke"] == colours["purple"], (
        "the ribbon is drawn in the charter's own dominant ink, which "
        "`colour._roles` already names as the ribbon's colour"
    )
    assert str(section["logo_dots"]) in mark, (
        "the wordmark's dots are the colour of the dot in the mark itself"
    )

    inner_stroke, inner_radius = 25.86, 131.72
    for radius in (0.105, 0.103):
        carried = inner_stroke / inner_radius * radius
        assert abs(section["ribbon_width_ratio"] - carried) / carried < 0.011, (
            "the stroke weight is the mark's inner arc, at the size the "
            "ribbon draws it: the midpoint of what the two curls give, "
            "1.0 percent from one and 0.9 percent from the other"
        )
    assert f'stroke-width="{inner_stroke}"' in mark
    assert f"A {inner_radius} " in mark


def test_the_default_palette_is_not_this_instances_wearing_a_new_name() -> None:
    """A "default" shipping this organisation's own colours would make the
    acceptance criterion true only for duplicates that remember to
    configure something.
    """
    default = _charter_colours(brand.DEFAULT_PATH)
    instance = _charter_colours(BRAND_PATH)
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
    assert brand.colours(brand.load(fake_repo)) == _charter_colours(BRAND_PATH)


def test_the_charter_in_force_is_the_products_when_the_instance_has_none(
    default_repo: Path,
) -> None:
    assert brand.source(default_repo) == brand.DEFAULT_PATH
    assert brand.colours(brand.load(default_repo)) == _charter_colours(
        brand.DEFAULT_PATH
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
    for field in brand.MOTIF_FIELDS:
        assert section[field] == default[field]


def test_an_instance_that_wrote_colours_but_no_motif_gets_the_products(
    fake_repo: Path,
) -> None:
    """The same answer one step further in, and the step that matters
    most in practice: somebody edits `data/brand.json` to set their own
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
    instance = _charter(BRAND_PATH)[brand.MOTIF_KEY]
    for field in brand.MOTIF_FIELDS:
        assert section[field] == default[field]
        assert section[field] != instance[field]


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
    with pytest.raises(brand.MissingMotifError, match="ribbon_stroke"):
        brand.motif(fake_repo)


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
    for field in brand.MOTIF_FIELDS:
        assert field in message


def test_the_ribbon_draws_the_products_mark_when_the_instance_has_none(
    default_repo: Path,
) -> None:
    """The generated posters complete as well, not only the downloadable
    templates: `ribbon.py` is the other thing that draws the mark.
    """
    default = _charter(brand.DEFAULT_PATH)[brand.MOTIF_KEY]
    assert ribbon.ribbon_stroke_colour(default_repo) == default["ribbon_stroke"]
    assert ribbon.ribbon_width_ratio(default_repo) == default["ribbon_width_ratio"]


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
    instance = _charter(BRAND_PATH)[brand.MOTIF_KEY]
    for rel in (ANNOUNCEMENT_SVG_PATH, FLYER_SVG_PATH):
        svg = (default_repo / rel).read_text(encoding="utf-8")
        assert str(default["ribbon_stroke"]) in svg
        assert str(default["logo_dots"]) in svg
        assert str(instance["ribbon_stroke"]) not in svg
        assert str(instance["logo_dots"]) not in svg

    written = (default_repo / SITE_CSS_PATH).read_text(encoding="utf-8")
    assert _charter_colours(brand.DEFAULT_PATH)["turquoise"] in written
    assert _charter_colours(BRAND_PATH)["turquoise"] not in written


def test_the_command_refuses_a_half_written_mark_and_says_what_is_missing(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal that is left, driven the same way: a `motif` somebody
    wrote and left a field short stops the build, names the file, the
    field and both ways out, and leaves no half-written template behind.
    """
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    del data[brand.MOTIF_KEY]["ribbon_stroke"]
    _write_json(fake_repo / BRAND_PATH, data)
    (fake_repo / ANNOUNCEMENT_SVG_PATH).unlink(missing_ok=True)

    assert main([]) == 1
    captured = capsys.readouterr()
    assert "ribbon_stroke" in captured.err
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
    assert _charter_colours(BRAND_PATH)["purple"] not in svg


# --------------------------------------------------------------------------
# A palette that does not clear AA does not build
# --------------------------------------------------------------------------


def test_a_palette_whose_measurement_no_longer_recomputes_does_not_build(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = json.loads((fake_repo / BRAND_PATH).read_text(encoding="utf-8"))
    data["contrast"]["purple_on_turquoise"] = 21.0
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
    data["contrast"]["saffron_on_cream"] = 4.6
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
    data["colour"]["turquoise"] = ground
    # Recomputed against the charter in force rather than written out.
    # The five figures used to be literals, and they were
    # honest only for one instance's purple and ink: under another's the
    # generator reported a *mismatch* first and this test lost its
    # subject, which is not the failure it exists to provoke.
    colours = brand.colours(data)
    data["contrast"].update(
        {
            name: round(contrast_ratio(colours[over], ground), 2)
            for name, over in (
                ("purple_on_turquoise", "purple"),
                ("black_on_turquoise", "black"),
                ("ink_on_turquoise", "ink"),
                ("ink_muted_on_turquoise", "ink_muted"),
            )
        }
    )
    data["contrast"]["turquoise_on_purple"] = data["contrast"]["purple_on_turquoise"]
    assert data["contrast"]["ink_muted_on_turquoise"] < 4.5, (
        "the palette this test is about has to be one that fails AA"
    )
    _write_json(fake_repo / BRAND_PATH, data)
    assert main([]) == 1
    err = capsys.readouterr().err
    assert "below the 4.5" in err
    assert "does not build" in err


# --------------------------------------------------------------------------
# The two files a collaborator downloads
# --------------------------------------------------------------------------

_TEMPLATES = (ANNOUNCEMENT_SVG_PATH, FLYER_SVG_PATH)
_RENDERERS = {
    ANNOUNCEMENT_SVG_PATH: brand_templates.render_announcement_template,
    FLYER_SVG_PATH: brand_templates.render_flyer_template,
}


@pytest.mark.parametrize("rel", _TEMPLATES, ids=lambda p: p.name)
def test_the_committed_template_is_what_the_charter_derives(rel: Path) -> None:
    committed = (ROOT / rel).read_text(encoding="utf-8")
    assert committed == _RENDERERS[rel](ROOT), (
        f"{rel.as_posix()} is not what the charter derives; run `{COMMAND}`"
    )


@pytest.mark.parametrize("rel", _TEMPLATES, ids=lambda p: p.name)
def test_the_committed_template_parses_as_xml(rel: Path) -> None:
    """Found by rendering one in a browser rather than by reading it: `--`
    anywhere inside an XML comment makes the whole document unparseable,
    and this project writes `--` for an em dash everywhere. Chrome drew an
    error page instead of a poster. A parser is cheaper than a browser, so
    the guard is a parser.
    """
    ElementTree.parse(ROOT / rel)


@pytest.mark.parametrize("rel", _TEMPLATES, ids=lambda p: p.name)
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


@pytest.mark.parametrize("rel", _TEMPLATES, ids=lambda p: p.name)
def test_a_template_says_it_is_generated(rel: Path) -> None:
    assert "generate_brand_css.py" in (ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", _TEMPLATES, ids=lambda p: p.name)
def test_a_template_reaches_out_to_nothing(rel: Path) -> None:
    """The property `app/tests/visual-kit.test.tsx` holds from the other
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
    data["colour"]["cream"] = data["colour"]["purple"]
    data["contrast"] = {"_comment": "emptied so the palette gate is not what bites"}
    _write_json(fake_repo / BRAND_PATH, data)
    with pytest.raises(ValueError, match=r"below the 4\.5"):
        brand_templates.render_announcement_template(fake_repo)


def test_every_pairing_the_templates_draw_clears_aa_in_both_charters() -> None:
    """Both palettes against the same list, so neither is legible by luck."""
    for rel in (BRAND_PATH, brand.DEFAULT_PATH):
        problems = brand_templates._legibility_problems(
            _charter_colours(rel), named=rel.as_posix()
        )
        assert problems == []


def test_the_legibility_list_would_notice_a_pairing_that_failed() -> None:
    """A list that matched nothing would pass for free."""
    assert brand_templates._LEGIBILITY
    flat = dict.fromkeys(_charter_colours(BRAND_PATH), "#fecac1")
    problems = brand_templates._legibility_problems(flat, named="a flat palette")
    assert len(problems) == len(brand_templates._LEGIBILITY)
