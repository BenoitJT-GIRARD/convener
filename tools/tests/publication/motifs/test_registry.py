"""The registry: every drawing in the directory is a family a charter can
name, and a name that is not one stops the build.

Two rules, and the second is the whole reason the first one is measured
rather than reviewed. A family module nobody registered is a drawing no
charter can ask for, which reads at a glance as a family that exists; and a
`motif.family` naming something the registry does not hold must never be
answered by drawing whichever family happens to be first, because a
duplicate would then ship a mark it never asked for with nothing on the
page to say so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from convener_ops.publication import motifs

#: The directory the registry is a table of.
DIRECTORY = Path(motifs.__file__).parent


def family_modules() -> list[str]:
    """Every module in the directory that is not the registry itself, read
    off the directory rather than listed here: adding a family puts it
    under the rule below on the commit that adds it."""
    return sorted(
        path.stem for path in DIRECTORY.glob("*.py") if path.stem != "__init__"
    )


def test_the_walk_finds_the_family_modules() -> None:
    """A read that found nothing would make the rule below pass over an
    empty directory -- the shape six sweeps in this repository had already
    silently narrowed into."""
    assert family_modules(), (
        f"{DIRECTORY} holds no family module at all, so the rule below "
        "compares two empty lists and proves nothing"
    )


def test_the_registry_reaches_every_family_in_the_directory() -> None:
    """The rule, on the real directory.

    Matched by the module each family's own `path` was defined in, not by
    the name it was registered under: a `Family` entry pointing at a module
    that is not the one it is named for would otherwise pass.
    """
    registered = sorted(
        drawn.path.__module__.rsplit(".", 1)[-1] for drawn in motifs.FAMILIES.values()
    )

    assert registered == family_modules(), (
        f"{DIRECTORY.name} holds {family_modules()} and the registry names "
        f"{registered}. A module nobody registered draws nothing any charter "
        "can ask for, and a family registered twice hides one of them"
    )


def test_every_family_declares_the_fields_a_charter_writes_for_it() -> None:
    """A family that declared none would make `brand.MOTIF_FIELDS` ask a
    charter for nothing but the two fields every motif carries, and a
    half-written section would then build."""
    silent = [name for name, drawn in motifs.FAMILIES.items() if not drawn.fields]

    assert silent == [], (
        f"{silent} declare no fields of their own. A family says which "
        "fields a charter naming it has to write, and `brand.py` holds the "
        "charter to that list"
    )


def test_a_family_is_looked_up_by_the_name_a_charter_writes() -> None:
    assert motifs.family("ribbon") is motifs.RIBBON
    assert motifs.RIBBON.name == "ribbon"


def test_an_unknown_family_is_refused_and_the_known_ones_are_named() -> None:
    """The refusal, and what it has to say: never a fall back to whichever
    drawing exists."""
    with pytest.raises(motifs.UnknownMotifFamilyError) as raised:
        motifs.family("lattice")

    message = str(raised.value)
    assert "'lattice'" in message
    for name in motifs.FAMILIES:
        assert name in message, (
            f"{name} exists and the refusal does not offer it, so a person "
            "reading it cannot tell what they may write instead"
        )


def test_every_entry_point_refuses_an_unknown_family() -> None:
    """Not only the lookup: each of the three things a caller actually
    asks for goes through it, so none of them can grow a fall back of its
    own."""
    for call in (
        lambda: motifs.path("lattice", 1200, 1200),
        lambda: motifs.safe_margins("lattice", 1200, 1200, ratio=0.02),
        lambda: motifs.clearance("lattice", 1200, 1200, ratio=0.02),
    ):
        with pytest.raises(motifs.UnknownMotifFamilyError):
            call()


# ---------------------------------------------------------------------------
# The stroke's own weight: the motif's, not any one family's
# ---------------------------------------------------------------------------


def test_stroke_width_tracks_the_shorter_side_not_the_longer_one() -> None:
    # Same short side (1000), wildly different long side: the width must
    # not move. A `max` in place of `min` inside `stroke_width` breaks
    # exactly this -- confirmed by mutating it and watching this test
    # fail, not assumed.
    square = motifs.stroke_width(1000, 1000, ratio=0.02)
    tall = motifs.stroke_width(1000, 5000, ratio=0.02)
    wide = motifs.stroke_width(5000, 1000, ratio=0.02)
    assert square == tall == wide == pytest.approx(20.0)


def test_stroke_width_scales_with_the_short_side_when_it_changes() -> None:
    small = motifs.stroke_width(1000, 1000, ratio=0.02)
    big = motifs.stroke_width(2000, 2000, ratio=0.02)
    assert big == pytest.approx(2 * small)


def test_stroke_width_rejects_a_non_positive_canvas() -> None:
    with pytest.raises(ValueError, match="positive"):
        motifs.stroke_width(0, 100, ratio=0.02)
    with pytest.raises(ValueError, match="positive"):
        motifs.stroke_width(100, -1, ratio=0.02)


def test_the_clearance_a_family_keeps_is_read_off_that_family() -> None:
    """`clearance` is the family's own figure times the stroke this canvas
    draws it at, never a constant held here: a drawing that is not a
    Catmull-Rom curve measures its own overshoot."""
    ratio = 0.02
    for name, drawn in motifs.FAMILIES.items():
        assert motifs.clearance(name, 1200, 1200, ratio=ratio) == pytest.approx(
            motifs.stroke_width(1200, 1200, ratio=ratio) * drawn.clearance_stroke_widths
        )


def test_safe_margins_hands_the_family_the_clearance_it_asked_for() -> None:
    """The registry is the only thing that turns a ratio into a clearance,
    so a family never reads a charter to answer where a word may start."""
    ratio = 0.02
    for name, drawn in motifs.FAMILIES.items():
        assert motifs.safe_margins(name, 1200, 900, ratio=ratio) == drawn.margins(
            1200, 900, clearance=motifs.clearance(name, 1200, 900, ratio=ratio)
        )
