"""The cockpit's own chrome, held against every charter this product ships.

`app/src/auth/Login.tsx` filled the sign-in button with the charter's
*field* and set white on it. White on the field is 1.61 at this instance's
charter and 1.61 to 1.71 at the four a duplicate may choose, and every one
of those files names that exact pairing in its own `contrast._forbidden`
-- `assets/brand/convener/brand.json` spells out the consequence in the same
sentence: "which is why a primary button fills with the dominant". It
shipped anyway, in eighteen class lists across nine files, because
nothing measured it:

- `site/scripts/check-a11y.mjs` sweeps the pages the showcase generates
  and skips `app/` by name. The cockpit is behind a GitHub sign-in and is
  not a page the public lands on, so no run of that checker has ever
  looked at a cockpit token pairing.
- Even if it had, it renders **one** charter -- the one in force. The
  defect was at every charter, and four of the five are palettes nothing
  in this repository ever builds.

So the control is a sweep of the source measured against every palette:
`convener_ops.publication.cockpit`, run by `generate_brand_css.py` in the
same loop that already refuses a charter whose own contrast table falls
below AA. This module is what proves the sweep reads what it claims to
read, and that it bites.

The fixtures below are written as source rather than mined out of
`app/src`: a test whose fixture is the repository can only ever say
"unchanged", and what has to be proved here is what the sweep does with a
class list that has never existed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from generate_brand_css import _DANGER, _INFO, app_tokens

from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, cockpit

ROOT = repo_root()

#: Every charter a build of this product can be drawn from: the one in
#: force here, and the four `assets/brand/` ships for a duplicate to choose.
#: Read off the directory rather than listed, for the reason
#: `brand.shipped` gives -- a charter added there is measured on the
#: commit that adds it, with no entry to make here.
#:
#: `brand.source` and not `brand.INSTANCE_PATH`, because an instance is in
#: one of two states and both are the product's: it wrote its own charter,
#: or it named one of the product's. In the second, the file in force is
#: already in the second half of this tuple, which is what the filter is
#: for -- one file under two names would be measured twice and say nothing
#: the once did not.
CHARTERS = (
    brand.source(ROOT),
    *(rel for rel in brand.shipped(ROOT) if rel != brand.source(ROOT)),
)


def _charter(rel: Path) -> dict[str, Any]:
    return dict(json.loads((ROOT / rel).read_text(encoding="utf-8")))


def _tokens(rel: Path) -> dict[str, str]:
    return app_tokens(_charter(rel))


def _scan(tmp_path: Path, source: str, *, name: str = "Chrome.tsx") -> Any:
    """One invented component, swept the way the repository's own are."""
    directory = tmp_path / cockpit.APP_SRC
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(source, encoding="utf-8", newline="")
    return cockpit.scan(tmp_path)


# --------------------------------------------------------------------------
# The repository as it stands
# --------------------------------------------------------------------------


def test_every_pairing_the_cockpit_sets_clears_aa_at_every_charter() -> None:
    """The property the sign-in screen broke, at every palette a duplicate
    could be running -- not only at the one this repository builds."""
    found, refused = cockpit.scan(ROOT)
    assert refused == []
    assert cockpit.unresolved_foregrounds(found) == []
    assert found, "the sweep found no class lists at all in app/src"
    for rel in CHARTERS:
        problems = cockpit.contrast_problems(
            found, _charter(rel), named=rel.as_posix(), danger=_DANGER, info=_INFO
        )
        assert problems == []


def test_white_on_the_field_is_the_pairing_every_charter_forbids() -> None:
    """The measurement behind the fix, recomputed rather than quoted: the
    field is a ground, and white on it is 1.60 to 1.71 wherever it is
    tried -- 1.60 at the example's, which is the charter in force in a
    repository `convener-derive` has produced. Each charter says so in
    its own `contrast._forbidden`."""
    for rel in CHARTERS:
        tokens = _tokens(rel)
        ratio = brand.contrast_ratio(cockpit.BUILT_IN_COLOURS["white"], tokens["field"])
        assert ratio < 2, f"{rel.as_posix()} gives white on the field {ratio}"
        assert "white as text on the field" in _charter(rel)["contrast"]["_forbidden"]


def test_the_dominant_is_what_a_filled_button_clears_aa_with() -> None:
    """The other half of the same sentence: white on the dominant, which is
    what every filled control in the cockpit now sets."""
    for rel in CHARTERS:
        tokens = _tokens(rel)
        for ground in ("dominant", "dominant-hover"):
            ratio = brand.contrast_ratio(
                cockpit.BUILT_IN_COLOURS["white"], tokens[ground]
            )
            assert ratio >= 7, f"{rel.as_posix()}: white on {ground} is {ratio}"


def test_every_token_names_a_colour_every_charter_carries() -> None:
    """A token added to the table without a colour behind it would render
    a `KeyError` into a stylesheet nobody could regenerate."""
    for rel in CHARTERS:
        named = brand.colours(_charter(rel))
        missing = [
            token for token, key in cockpit.TOKEN_COLOURS.items() if key not in named
        ]
        assert missing == [], f"{rel.as_posix()} carries no colour for {missing}"


def test_the_table_is_exactly_what_tailwind_declares() -> None:
    """`app/src/index.css`'s `@theme` block turns each colour key into the
    utilities a component writes. A key there with no entry in
    `TOKEN_COLOURS` is a utility this sweep would refuse as an unknown
    word; an entry here with no key there is a custom property nothing can
    reach. Both are caught by reading the stylesheet rather than trusting
    the two to agree.

    The stylesheet is where this lives because Tailwind v4 has no
    JavaScript configuration to read: `--color-dominant: var(--dominant)`
    under `@theme` is what `bg-dominant` is now declared by, and
    `postcss.config.js`/`tailwind.config.ts` are gone with the plugin that
    needed them.
    """
    stylesheet = (ROOT / "app" / "src" / "index.css").read_text(encoding="utf-8")
    block = stylesheet.split("@theme {", 1)[1].split("}", 1)[0]
    declared = {
        match["key"]: match["prop"]
        for match in re.finditer(
            r"^\s*--color-(?P<key>[\w-]+):\s*var\(--(?P<prop>[\w-]+)\);",
            block,
            re.MULTILINE,
        )
    }
    # Every utility a component can write, and the custom property behind
    # it: `bg-field-text` has to reach `--field-text`, not `--field-hover`
    # under another name, or the sweep would resolve a colour the browser
    # never paints.
    expected = set(cockpit.TOKEN_COLOURS) | set(cockpit.LITERAL_TOKENS)
    assert set(declared) == expected, (
        f"`@theme` declares {sorted(set(declared) - expected)} that this "
        f"module measures nothing for, and measures "
        f"{sorted(expected - set(declared))} that no utility can reach"
    )
    crossed = {u: p for u, p in declared.items() if u != p}
    assert crossed == {}, f"a utility reaching another token's property: {crossed}"


def test_no_cockpit_source_names_the_superseded_token_vocabulary() -> None:
    """`--primary` and `--accent` are gone, and stay gone: the cockpit
    reads the showcase's names now. The islands' own BEM classes
    (`btn--primary`, `verify__panel--accent`) belong to
    `site/src/style.css` and are not these tokens, so the sweep is for the
    utility and the custom property, not for the word."""
    for rel in cockpit.sources(ROOT):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for forbidden in (
            "bg-primary",
            "text-primary",
            "border-primary",
            "bg-accent",
            "text-accent",
            "border-accent",
            "stroke-accent",
            "var(--primary",
            "var(--accent",
        ):
            assert forbidden not in text, f"{rel.as_posix()} still names {forbidden}"


# --------------------------------------------------------------------------
# What the sweep reads
# --------------------------------------------------------------------------


def test_a_filled_button_in_the_field_is_refused_at_every_charter(
    tmp_path: Path,
) -> None:
    """The defect itself, planted back: this is the control biting."""
    found, refused = _scan(
        tmp_path,
        'export const Sign = () => <button className="px-6 py-3 bg-field '
        'text-white">Sign in</button>;\n',
    )
    assert refused == []
    for rel in CHARTERS:
        problems = cockpit.contrast_problems(
            found, _charter(rel), named=rel.as_posix(), danger=_DANGER, info=_INFO
        )
        assert len(problems) == 1
        assert "text-white on bg-field" in problems[0]
        assert "below the 4.5" in problems[0]


def test_the_same_button_in_the_dominant_is_not(tmp_path: Path) -> None:
    found, refused = _scan(
        tmp_path,
        'export const Sign = () => <button className="px-6 py-3 bg-dominant '
        'text-white">Sign in</button>;\n',
    )
    assert refused == []
    for rel in CHARTERS:
        assert (
            cockpit.contrast_problems(
                found, _charter(rel), named=rel.as_posix(), danger=_DANGER, info=_INFO
            )
            == []
        )


def test_a_variant_is_resolved_before_the_pairing_is_made(tmp_path: Path) -> None:
    """`text-dominant ... hover:bg-dominant hover:text-white` is two
    pairings in two states, not one nonsense pairing of the two words
    standing side by side."""
    found, _ = _scan(
        tmp_path,
        'const c = "text-dominant border-2 border-dominant hover:bg-dominant '
        'hover:text-white";\n',
    )
    assert {(p.variant, p.foreground, p.ground) for p in found} == {
        ("", "dominant", "paper"),
        ("hover:", "white", "dominant"),
    }


def test_a_variant_with_no_ground_of_its_own_keeps_the_unvariant_one(
    tmp_path: Path,
) -> None:
    found, _ = _scan(
        tmp_path, 'const c = "bg-dominant text-white hover:bg-dominant-hover";\n'
    )
    assert {(p.variant, p.foreground, p.ground) for p in found} == {
        ("", "white", "dominant"),
        ("hover:", "white", "dominant-hover"),
    }


def test_an_inert_control_is_not_measured(tmp_path: Path) -> None:
    """WCAG 2.1 exempts text in an inactive user-interface component from
    1.4.3 by name, so `disabled:opacity-50` on a filled button is not a
    pairing -- and the button's own live states still are."""
    found, refused = _scan(
        tmp_path,
        'const c = "bg-dominant text-white hover:opacity-90 disabled:opacity-50";\n',
    )
    assert refused == []
    assert {p.variant for p in found} == {"", "hover:"}


def test_an_opacity_the_class_list_names_its_type_for_is_composited(
    tmp_path: Path,
) -> None:
    """The agenda's archived card, as it stood: ink-muted on paper is 7.42
    at the product's own charter and 2.88 once the whole element is
    painted at 60%. Found by this sweep on its first run over the
    repository.

    Measured against `brand.DEFAULT_PATH` rather than against the charter
    in force, which is what it read until a derived repository failed
    here: `convener-derive` lays the example instance into
    `instance/data/`, so "the charter in force" is a different palette on
    the other side of the derivation and a figure written down beside it
    cannot be right in both trees. The product's own charter is the one
    palette every duplicate has and no derivation replaces. What is
    proved here is that an opacity changes the measurement, and any
    palette proves it."""
    found, refused = _scan(
        tmp_path, 'const c = "bg-paper border-border text-ink-muted opacity-60";\n'
    )
    assert refused == []
    tokens = _tokens(brand.DEFAULT_PATH)
    (pairing,) = found
    assert round(cockpit.measure(pairing, tokens), 2) == 2.88
    assert round(brand.contrast_ratio(tokens["ink-muted"], tokens["paper"]), 2) == 7.42


def test_an_opacity_dimming_type_it_does_not_name_is_refused(
    tmp_path: Path,
) -> None:
    """The half of the same hazard nothing can measure: what a bare
    `opacity-70` reduces the contrast of belongs to an element this sweep
    cannot see, so it is a finding rather than a silence."""
    _, refused = _scan(tmp_path, 'const c = "font-mono opacity-70 ml-1";\n')
    assert len(refused) == 1
    assert "opacity-70 dims type this class list does not name" in refused[0]


def test_a_light_foreground_with_no_ground_of_its_own_is_refused(
    tmp_path: Path,
) -> None:
    """The other limit, asserted rather than trusted: a `text-white` whose
    ground is on an ancestor is the one shape a sweep of class lists
    cannot resolve, so it may not be quietly measured against the page."""
    found, _ = _scan(tmp_path, 'const c = "font-mono text-sm text-white";\n')
    problems = cockpit.unresolved_foregrounds(found)
    assert len(problems) == 1
    assert "names no ground in its own class list" in problems[0]


def test_a_value_this_module_cannot_place_is_a_finding(tmp_path: Path) -> None:
    """A typo that paints the browser's default is exactly what a sweep
    which skipped whatever it did not recognise would let through."""
    _, refused = _scan(tmp_path, 'const c = "px-2 text-domiant";\n')
    assert len(refused) == 1
    assert "names neither a colour token" in refused[0]


def test_a_size_is_not_a_colour(tmp_path: Path) -> None:
    _, refused = _scan(
        tmp_path, 'const c = "text-xs text-center bg-transparent text-[11px]";\n'
    )
    assert refused == []


def test_a_comment_is_not_a_class_list(tmp_path: Path) -> None:
    """This module's own prose quotes `bg-field text-white` more than once,
    and so does `cockpit.py`'s header. A sweep that read comments would
    measure the sentence explaining the defect and report the defect."""
    found, refused = _scan(
        tmp_path,
        "// The pairing every charter forbids is bg-field text-white.\n"
        "/* And so does this one: bg-field text-paper. */\n"
        'const c = "bg-dominant text-white";\n',
    )
    assert refused == []
    assert [(p.foreground, p.ground) for p in found] == [("white", "dominant")]


def test_both_branches_of_a_conditional_inside_a_template_are_read(
    tmp_path: Path,
) -> None:
    """`TopTabs`'s active tab and `Archive`'s filter chips are written this
    way, and a pattern that swallowed the backticks whole would measure
    neither."""
    found, _ = _scan(
        tmp_path,
        "const c = `px-3 py-2 border-b-2 ${active\n"
        "  ? 'bg-field text-white'\n"
        "  : 'text-ink-muted'}`;\n",
    )
    assert ("white", "field") in {(p.foreground, p.ground) for p in found}
    assert ("ink-muted", "paper") in {(p.foreground, p.ground) for p in found}


def test_a_ground_opacity_is_composited_over_the_page(tmp_path: Path) -> None:
    """`bg-field/10` is not a colour any charter holds, and it is a colour
    somebody reads type on.

    Against the product's own charter, for the reason
    `test_an_opacity_the_class_list_names_its_type_for_is_composited`
    gives: the charter in force is not the same palette on both sides of
    the derivation."""
    found, _ = _scan(tmp_path, "const c = 'bg-field/10 text-field-text';\n")
    (pairing,) = found
    assert pairing.ground_alpha == 0.10
    tokens = _tokens(brand.DEFAULT_PATH)
    # 5.90 at the product's charter, and 5.82 before its ground was
    # lightened: a tenth of the field composited over white is nearer white
    # the lighter the field is, so `field-text` on it reads a little
    # further. Every pairing the field takes part in moved the same way and
    # none moved down.
    assert round(cockpit.measure(pairing, tokens), 2) == 5.90


def test_a_string_table_is_swept_as_well_as_markup(tmp_path: Path) -> None:
    """`components/Button.tsx` names its filled variant's classes in a
    lookup object, never in a `className=` attribute -- which is where the
    seventeenth `text-paper` on the field was written."""
    found, _ = _scan(
        tmp_path,
        "const styles = {\n"
        "  primary: 'bg-field text-paper',\n"
        "  ghost: 'hover:bg-paper',\n"
        "};\n",
    )
    assert ("paper", "field") in {(p.foreground, p.ground) for p in found}


def test_the_line_a_pairing_is_reported_at_is_the_line_it_is_written_on(
    tmp_path: Path,
) -> None:
    found, _ = _scan(
        tmp_path, "const a = 1;\nconst b = 2;\nconst c = 'bg-field text-white';\n"
    )
    (pairing,) = found
    assert pairing.line == 3


# --------------------------------------------------------------------------
# The arithmetic
# --------------------------------------------------------------------------


def test_compositing_at_full_alpha_changes_nothing() -> None:
    assert cockpit.composite("#123456", "#ffffff", 1.0) == "#123456"


def test_compositing_at_no_alpha_is_the_ground() -> None:
    assert cockpit.composite("#123456", "#ffffff", 0.0) == "#ffffff"


def test_compositing_is_the_arithmetic_a_browser_does() -> None:
    """Half of black on white is the midpoint, rounded the way a channel
    is."""
    assert cockpit.composite("#000000", "#ffffff", 0.5) == "#808080"


@pytest.mark.parametrize("rel", CHARTERS, ids=lambda rel: rel.as_posix())
def test_the_two_literal_tokens_are_the_same_at_every_charter(rel: Path) -> None:
    """`--danger` and `--info` have no charter behind them, and the sweep
    has to be handed them rather than inventing a value that appears in no
    file."""
    tokens = _tokens(rel)
    assert tokens["danger"] == _DANGER
    assert tokens["info"] == _INFO
