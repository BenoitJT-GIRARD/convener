"""Every block of type in the two downloadable templates stands in ground
the family in force leaves free.

The browser measures the same claim against real glyphs
(`tools/visuals/check-templates.mjs`, which is what actually proves it and
what CI runs). This module holds the arithmetic half, which is the half
that can fail without a browser in the room: that each block's own
coordinate came from `motifs` over that block's own rows rather than from a
number somebody fitted to one drawing, and that the estimate the placement
was made against puts every line inside the corridor.

Both halves are needed and neither replaces the other. This one runs in
every `pytest` and catches a coordinate typed back into the markup; the
browser one catches a face whose glyphs are wider than the table says they
are. A layout is only right if both hold.
"""

from __future__ import annotations

import json
import re
import shutil
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterator
from pathlib import Path
from typing import Final, NamedTuple

import pytest

from convener_ops.declaration import published
from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, brand_templates, motifs, typeface

ROOT: Final = repo_root()
SVG: Final = "{http://www.w3.org/2000/svg}"

#: The two files this module is about, with the canvas each is drawn on.
#: The background is not here: its one block of type has been placed from
#: `motifs.safe_margins` since it was first generated, and
#: `test_brand.py` already holds that plate against the corridor.
PAGES: Final = (
    (
        "announcement",
        brand_templates.render_announcement_template,
        1200.0,
        1200.0,
    ),
    (
        "flyer",
        brand_templates.render_flyer_template,
        2100.0,
        2970.0,
    ),
)


#: What the two-decimal rounding of a font size costs at the far end of a
#: line: a size rounded up by five thousandths, over the twenty-odd ems of
#: the longest line either file sets, moves its end by about a tenth of a
#: unit. A quarter of a unit is comfortably above that and far below the
#: full stroke width the corridor is widened by.
_ROUNDING: Final = 0.25

#: The announcement's registration block, which is the one thing on either
#: page placed *outside* the corridor rather than inside it -- see
#: `test_the_announcement_puts_its_registration_slot_west_of_the_ribbon`.
_OUTBOARD: Final = frozenset({"REGISTER", "HERE", "QR code"})


class Block(NamedTuple):
    """One line of type, as the markup sets it."""

    text: str
    x: float
    baseline: float
    size: float
    weight: int
    anchor: str
    letter_spacing: float


def _float(value: str | None, fallback: float) -> float:
    return fallback if value is None else float(value)


def _blocks(svg: str) -> Iterator[Block]:
    """Every line the markup sets at an x of its own.

    A `tspan` carrying no `x` continues the one before it and has no
    coordinate to check; the browser measures those, this does not.
    """
    root = ElementTree.fromstring(svg)
    for text in root.iter(f"{SVG}text"):
        size = _float(text.get("font-size"), 0.0)
        weight = int(_float(text.get("font-weight"), 400.0))
        anchor = text.get("text-anchor", "start")
        spacing = _float(text.get("letter-spacing"), 0.0)
        spans = [span for span in text.iter(f"{SVG}tspan") if span.get("x")]
        if spans:
            for span in spans:
                # A run that opens a line and the run continuing it are one
                # line and are measured as one: the continuation carries no
                # x, so it is the text following this span rather than an
                # element of its own.
                yield Block(
                    "".join(span.itertext()) + (span.tail or ""),
                    float(span.get("x", "0")),
                    float(span.get("y", "0")),
                    _float(span.get("font-size"), size),
                    int(_float(span.get("font-weight"), float(weight))),
                    anchor,
                    spacing,
                )
        else:
            content = "".join(text.itertext())
            if not content.strip():
                continue
            yield Block(
                content,
                float(text.get("x", "0")),
                float(text.get("y", "0")),
                size,
                weight,
                anchor,
                spacing,
            )


def _extent(block: Block) -> tuple[float, float]:
    """Where the line starts and ends, by the same estimate that placed it."""
    width = typeface.width(
        block.text,
        size=block.size,
        weight=block.weight,
        letter_spacing=block.letter_spacing,
    )
    if block.anchor == "middle":
        return block.x - width / 2, block.x + width / 2
    if block.anchor == "end":
        return block.x - width, block.x
    return block.x, block.x + width


def _fixture_root(tmp_path: Path, family: str) -> Path:
    """A repository root drawn with one family, the way
    `cli.render_template_fixtures` builds one."""
    made = tmp_path / family
    (made / brand.INSTANCE_PATH.parent).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / published.INSTANCE_PATH, made / published.INSTANCE_PATH)
    charter = json.loads((ROOT / brand.source(ROOT)).read_text(encoding="utf-8"))
    charter["motif"][brand.MOTIF_FAMILY] = family
    (made / brand.INSTANCE_PATH).write_text(
        json.dumps(charter, indent=2) + "\n", encoding="utf-8"
    )
    return made


@pytest.mark.parametrize("family", sorted(motifs.FAMILIES))
@pytest.mark.parametrize("page", PAGES, ids=lambda page: page[0])
def test_every_line_stands_inside_the_corridor_its_own_rows_leave(
    tmp_path: Path,
    page: tuple[str, object, float, float],
    family: str,
) -> None:
    """The property the whole placement exists for, at every family the
    registry draws rather than at the one this charter happens to name.

    Every block but the announcement's registration labels, which stand
    on the far side of the drawing on purpose -- the test below is theirs,
    because "inside the corridor" is not the claim they make.
    """
    name, render, width, height = page
    root = _fixture_root(tmp_path, family)
    ratio = brand.motif_width_ratio(root)
    canvas = brand_templates._Canvas(family, width, height, ratio)
    for block in _blocks(render(root)):  # type: ignore[operator]
        if name == "announcement" and block.text.strip() in _OUTBOARD:
            continue
        first, last = canvas.corridor(*canvas.rows(block.baseline, block.size))
        start, end = _extent(block)
        assert start >= first - _ROUNDING, (
            f"{block.text!r} starts at {start:.1f}, west of the "
            f"{first:.1f} the {family} motif leaves free over its rows"
        )
        assert end <= last + _ROUNDING, (
            f"{block.text!r} ends at {end:.1f}, east of the {last:.1f} "
            f"the {family} motif leaves free over its rows"
        )


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page[0])
def test_the_drawing_moves_the_words_rather_than_the_other_way_round(
    tmp_path: Path, page: tuple[str, object, float, float]
) -> None:
    """Rendered with two different families, these files disagree about
    where their words go.

    The one property a hand-placed layout cannot have. Before this, both
    files rendered byte-identically apart from the motif's own `d` and its
    colours: every coordinate was the same number whichever drawing the
    charter named, which is exactly what it means for a layout to be
    fitted to one of them.
    """
    _name, render, _width, _height = page
    drawn = {
        family: [
            (block.x, block.size)
            for block in _blocks(render(_fixture_root(tmp_path, family)))  # type: ignore[operator]
        ]
        for family in sorted(motifs.FAMILIES)
    }
    ribbon, bracket = drawn["ribbon"], drawn["bracket"]
    assert len(ribbon) == len(bracket)
    assert ribbon != bracket


def test_the_announcement_puts_its_registration_slot_west_of_the_ribbon(
    tmp_path: Path,
) -> None:
    """The one block on that page that stands on the far side of the
    drawing rather than in the corridor with the words.

    Held explicitly because it is the reason `motifs.free_spans` exists at
    all: over those rows the ribbon's tail runs down the middle of the
    page's lower left, and a single margin measured from an edge cannot
    say "there is ground on both sides of this".
    """
    root = _fixture_root(tmp_path, "ribbon")
    svg = brand_templates.render_announcement_template(root)
    slot = re.search(r'<rect x="([\d.]+)" y="960" width="([\d.]+)"', svg)
    assert slot is not None
    left, side = float(slot.group(1)), float(slot.group(2))
    ratio = brand.motif_width_ratio(root)
    free = motifs.free_spans(
        "ribbon",
        1200.0,
        1200.0,
        ratio=ratio,
        top=brand_templates._ANNOUNCEMENT_REGISTER_TOP,
        bottom=brand_templates._ANNOUNCEMENT_SLOT_TOP
        + brand_templates._ANNOUNCEMENT_SLOT_SIDE,
    )
    assert len(free) == 2, "the ribbon leaves ground on both sides of its tail here"
    assert left >= free[0][0]
    assert left + side <= free[0][1] + 0.01


def test_a_family_that_leaves_no_room_for_the_code_stops_the_build() -> None:
    """A slot too small to drop a code into is a poster nobody can
    register from, and shipping one quietly is the failure D-25 names."""
    canvas = brand_templates._Canvas("wall", 1200.0, 1200.0, 0.024)
    wall = motifs.Family(
        name="wall",
        fields=motifs.BRACKET.fields,
        path=motifs.BRACKET.path,
        outline=lambda width, height: (((100.0, 0.0), (100.0, height)),),
        clearance_stroke_widths=1.0,
    )
    try:
        motifs.FAMILIES["wall"] = wall
        with pytest.raises(ValueError, match="registration slot"):
            brand_templates._register_values(canvas)
    finally:
        del motifs.FAMILIES["wall"]


def test_the_column_lines_are_the_lines_the_markup_actually_sets() -> None:
    """The size the column is set at is decided by whichever of those
    lines needs the most room, so a line in the markup that is missing
    here would be sized against nothing."""
    host = published.load_identity(ROOT).forum_host
    declared = {
        "".join(text for text, _weight in line)
        for line in brand_templates._column_lines(host)
    }
    for template in (brand_templates._ANNOUNCEMENT, brand_templates._FLYER):
        column = template[
            template.index('<text font-size="{column_size}"') : template.index(
                "REGISTRATION QR"
            )
        ]
        runs = re.findall(r">([^<>]+)</tspan>", column)
        lines: list[str] = []
        for run in runs:
            if run.endswith(": "):
                lines.append(run)
            elif lines and lines[-1].endswith(": "):
                lines[-1] += run
            else:
                lines.append(run)
        rendered = {line.replace("{forum_host}", host) for line in lines}
        assert rendered == declared
