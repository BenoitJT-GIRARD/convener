"""The design tokens, and the guards that keep them derived from one file.

`data/brand.json` measured Anonymous's own colours. Before this module existed,
two implementations each carried their own hand-typed copy of them --
`site/src/style.css` and `app/src/design/tokens.css` -- and the application
had drifted to a reconstruction's palette without anyone deciding that on
purpose: purple on turquoise measured 4.44 there, below AA, where Anonymous's
own value gives 7.93, AAA (`docs/superpowers/deferred-work.md`, entry 1).
`scripts/generate_brand_css.py` derives both from the brand file instead,
and this module holds what makes that stick.

A third file, `app/src/design/tokens.ts`, used to be generated here too and
was covered by this module's own tests. Fix round 1 retired it -- nothing
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

import pytest
from generate_brand_css import (
    _BEGIN,
    _END,
    APP_TOKENS_CSS_PATH,
    BRAND_PATH,
    COMMAND,
    SITE_CSS_PATH,
    contrast_ratio,
    hex_to_rgb,
    load_brand,
    main,
    relative_luminance,
    render_app_tokens_css,
    render_site_css,
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
    assert checked == 9


def test_purple_on_turquoise_is_the_measurement_d16_turned_on() -> None:
    """The one number this whole task exists over. The reconstruction's
    shipped value was 4.44, below AA for normal text; Anonymous's own colours
    give 7.93, AAA. This pins the arithmetic to that fact directly, rather
    than through whatever `data/brand.json` currently claims.
    """
    computed = round(contrast_ratio("#012765", "#fecac1"), 2)
    assert computed == 7.93
    assert computed != 4.44


def test_relative_luminance_of_white_and_black_are_the_extremes() -> None:
    assert relative_luminance("#ffffff") == pytest.approx(1.0)
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0, abs=0.01)


def test_hex_to_rgb_and_the_css_literals_built_from_it() -> None:
    assert hex_to_rgb("#fecac1") == (130, 219, 215)
    assert rgba("#fecac1", 0.35) == "rgba(130, 219, 215, 0.35)"
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
    """
    css = (ROOT / SITE_CSS_PATH).read_text(encoding="utf-8")
    risky: dict[str, str] = {
        "a": "var(--turquoise-d)",
        ".hero__title em": "var(--turquoise-d)",
        ".feature__vol": "var(--turquoise-d)",
        ".archive__date": "var(--ink-faint)",
        ".archive__action--disabled": "var(--ink-faint)",
        ".btn--primary": "var(--turquoise)",
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


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository holding `data/brand.json` and marked-but-empty
    stylesheets for both generated targets.
    """
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "brand.json").write_text(
        (ROOT / BRAND_PATH).read_text(encoding="utf-8"), encoding="utf-8"
    )
    for rel in (SITE_CSS_PATH, APP_TOKENS_CSS_PATH):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_marked_stub(), encoding="utf-8")
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
    data["colour"]["purple"] = "#000000"
    brand_path.write_text(json.dumps(data), encoding="utf-8")
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
