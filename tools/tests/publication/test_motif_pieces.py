"""Pieces of a motif drawn for a page: every stroke enters and leaves
through its own box's edges, and never stops inside it.

That is the whole defect the pieces exist to remove. A drawing made for a
square and set in a box of another shape stopped wherever the square did,
in the middle of the field, and read as a mark cut off by mistake. So the
rule is measured on every piece of every family that draws any, on the
path's own two ends, with the round cap included.
"""

from __future__ import annotations

import math
import re

import pytest

from convener_ops.publication import motifs
from convener_ops.publication.motif_pieces import Arc, Through, cubics, piece

_FAMILIES_WITH_PIECES = sorted(
    name for name in motifs.FAMILIES if motifs.page_pieces(name)
)
_PIECES = [
    (family, name, drawn)
    for family in _FAMILIES_WITH_PIECES
    for name, drawn in sorted(motifs.page_pieces(family).items())
]


def _ends(path: str) -> tuple[tuple[float, float], tuple[float, float]]:
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path)]
    return (numbers[0], numbers[1]), (numbers[-2], numbers[-1])


def _outside(
    point: tuple[float, float], width: float, height: float, margin: float
) -> bool:
    x, y = point
    return x < -margin or y < -margin or x > width + margin or y > height + margin


def test_at_least_one_family_draws_pieces() -> None:
    """Otherwise every rule below passes over an empty list."""
    assert _PIECES, "no family draws pieces for a page, so nothing here is measured"


@pytest.mark.parametrize(
    ("family", "name", "drawn"), _PIECES, ids=lambda v: str(v)[:24]
)
def test_every_piece_enters_and_leaves_through_its_own_edges(
    family: str, name: str, drawn: motifs.Piece
) -> None:
    start, end = _ends(drawn.path)
    cap = drawn.stroke_width / 2
    for which, point in (("starts", start), ("ends", end)):
        assert _outside(point, drawn.width, drawn.height, cap), (
            f"{family}'s {name} piece {which} at {point}, inside its "
            f"{drawn.width}x{drawn.height} box: the stroke would stop in the "
            "middle of the field instead of running off an edge"
        )


@pytest.mark.parametrize(
    ("family", "name", "drawn"), _PIECES, ids=lambda v: str(v)[:24]
)
def test_every_piece_is_one_move_then_cubics(
    family: str, name: str, drawn: motifs.Piece
) -> None:
    """The same `M` then `C` grammar every family's single path keeps."""
    assert re.fullmatch(r"M [-\d. ]+( C [-\d. ]+)+", drawn.path), (
        f"{family}'s {name} piece is not one move followed by cubics"
    )


def test_the_ribbon_crosses_the_first_band_where_the_piece_below_takes_it_up() -> None:
    """The hero's piece runs on behind the first band and the piece under
    the band brings it out: both must cross at the same distance from the
    right edge, heading straight down, or the stroke would jump sideways
    behind the band."""
    pieces = motifs.page_pieces("ribbon")
    above, below = pieces["hero-wide"], pieces["below-band"]
    hero_end = _ends(above.path)[1]
    band_start = _ends(below.path)[0]
    assert above.width - hero_end[0] == below.width - band_start[0]
    last = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", above.path)][-6:]
    first = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", below.path)][:4]
    assert last[2] == last[4] == hero_end[0], (
        "the hero's piece does not end heading straight down"
    )
    assert first[0] == first[2], (
        "the piece under the band does not start heading straight down"
    )


def test_a_family_without_pieces_answers_with_none() -> None:
    """The showcase keeps its single drawing for those, so an empty answer
    must be a real, empty mapping rather than a refusal."""
    without = [name for name in motifs.FAMILIES if not motifs.page_pieces(name)]
    assert without, "every family draws pieces, so the fallback is never exercised"
    for name in without:
        assert dict(motifs.page_pieces(name)) == {}


def test_an_arc_stays_on_its_circle() -> None:
    """Each quarter-turn cubic's midpoint sits on the circle, within the
    standard approximation's own error (about 0.03 % of the radius)."""
    arc = Arc((100.0, 100.0), 80.0, 200.0, 20.0)
    for p0, p1, p2, p3 in cubics((arc,)):
        mid = tuple(
            (a + 3 * b + 3 * c + d) / 8
            for a, b, c, d in zip(p0, p1, p2, p3, strict=True)
        )
        assert math.hypot(mid[0] - 100.0, mid[1] - 100.0) == pytest.approx(
            80.0, rel=1e-3
        )


def test_a_join_leaves_and_arrives_along_the_directions_it_was_given() -> None:
    """The handles follow the tangents, so a curve meets the next step
    without a corner."""
    ((start, c1, c2, end),) = cubics(
        (Through((0, 0), (1, 0)), Through((100, 100), (0, 1)))
    )
    assert c1[1] == start[1] and c1[0] > start[0]
    assert c2[0] == end[0] and c2[1] < end[1]


def test_a_piece_needs_a_stroke() -> None:
    with pytest.raises(ValueError, match="stroke"):
        piece(10, 10, align="none", stroke_width=1, steps=(Through((0, 0), (1, 0)),))
