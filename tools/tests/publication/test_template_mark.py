"""No drawing in the two downloadable templates is traced off anybody's
artwork.

What was there
---------------
`brand_templates._MARK_SQUARES`, `_MARK_PIN_LEFT`, `_MARK_PIN_RIGHT`,
`_MARK_CONNECTOR` and `_MARK_TAIL` were five squares, two drop-shaped
markers with a hole through each, the arc joining them and the tail that
became the rule under the address -- every coordinate measured pixel by
pixel off `announcement-template_initial.png`, this instance's own
announcement poster, which `.gitignore` keeps out of this repository
because it carries a real person's photograph. Both templates drew that
device **for every charter**, so a duplicate choosing `assets/brand/lattice/`
downloaded two files carrying a mark taken from this instance's artwork.

It is the same provenance that keeps `ribbon` named by no charter but this
instance's own, the same as the video-call background this repository once
shipped as a raster, the screenshots `README.md` carries, and the motif a
charter that names none is drawn with.

What holds it now
------------------
The rule this module states is stronger than "those five constants are
gone", because the next traced device would be five different constants:
**the only geometry either template may draw is geometry the registry
produced.** Both files are swept, at every charter this product ships and
at every family it draws, and every `<path>` in them has to be a `d` that
`motifs.path` returns for that family -- the page's own drawing at the
page's canvas, and the lock-up's device at the lock-up's box. A path that
is neither is a drawing from somewhere, and where a drawing came from is
exactly the question that could not be asked of a literal.

`brand_templates.py`'s own source is swept for path data besides, so that
a device can be neither drawn into the markup nor assembled out of a
constant in the module that writes it. Comments are not swept and this
module's own prose is why: the paragraph above quotes a traced coordinate,
and a sweep that read prose would refuse the explanation along with the
thing it explains.

The one measurement that is still a measurement is the dot the device
closes on, and it is a measurement of the product's *own* artwork:
`assets/brand/convener/convener-mark.svg`, three numbers, read back out of that
file here.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Final

import pytest

from convener_ops.cli import publication as cli
from convener_ops.declaration import published
from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, brand_templates, lockup, motifs, visual

ROOT: Final = repo_root()
SVG: Final = "{http://www.w3.org/2000/svg}"

#: The two files a volunteer downloads that carry the lock-up. The
#: video-call background carries no wordmark and no device, and the one
#: `<path>` besides its motif is the registration code's, drawn by `segno`
#: from the address rather than by anything here.
PAGES: Final = (
    ("announcement", brand_templates.render_announcement_template, 1200.0, 1200.0),
    ("flyer", brand_templates.render_flyer_template, 2100.0, 2970.0),
)

#: Every module that draws the identity, and so every place a coordinate
#: of it could still be typed: the two templates' own composer, the
#: device all three surfaces share, and the poster the cockpit generates
#: -- which drew its own reading of the same traced device until this.
MODULES: Final = tuple(
    Path(module.__file__ or "") for module in (brand_templates, lockup, visual)
)

#: The product's own mark, and the box it is drawn on. The dot's three
#: numbers are read back out of this file rather than restated.
MARK: Final = Path("assets") / "brand" / "convener" / "convener-mark.svg"
MARK_BOX: Final = 512.0

#: What path data is, said tightly enough that prose is not mistaken for
#: it. Every `d` starts with a move, so a string that does not begin with
#: one is not path data whatever else it contains -- which is what keeps
#: the templates' own markup, full of English sentences inside SVG
#: comments, out of the sweep. Two commands with a coordinate after each,
#: besides, so that a bare "M 1" in some future message is not a drawing.
#:
#: What this shape cannot see is geometry *assembled* -- `"M " + point` --
#: and nothing here pretends otherwise:
#: `test_every_drawing_in_both_templates_came_from_the_registry` is what
#: catches that, because it compares the `d` a rendered file actually
#: carries against the one the registry returns.
_STARTS_WITH_A_MOVE: Final = re.compile(r"^[Mm]\s*-?\d")
_PATH_COMMAND: Final = re.compile(r"[MmLlHhVvCcSsQqTtAa]\s*-?\d")
_ENOUGH: Final = 2


def path_data(source: str) -> list[str]:
    """Every string constant in `source` that carries SVG path data.

    Docstrings are excluded, and comments never reach the tree at all --
    which is the distinction this module's own header argues for: prose
    about a traced coordinate is not a traced coordinate.
    """
    tree = ast.parse(source)
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node in docstrings:
            continue
        value = node.value.strip()
        if not _STARTS_WITH_A_MOVE.match(value):
            continue
        if len(_PATH_COMMAND.findall(value)) >= _ENOUGH:
            found.append(node.value)
    return found


def _charters() -> tuple[Path, ...]:
    """Every charter a build can be drawn from, root-relative.

    The one in force first, then every other charter this product ships --
    the shape `generate_brand_css.main` builds, for its reason. An instance
    that *names* one of the product's is drawn from a file the second half
    already holds, so asking for it twice would measure one file under two
    names and say nothing the once did not.
    """
    in_force = brand.source(ROOT)
    return (in_force, *(rel for rel in brand.shipped(ROOT) if rel != in_force))


def _fixture_root(tmp_path: Path, charter: Path, family: str) -> Path:
    """A repository root drawn from one charter with one family named.

    Through `cli`'s own function, so that a tree this measures and a tree
    the fixture renderer writes cannot differ -- and so that a declaration
    which *names* a charter has that key taken out on the way in, which is
    what lets this lay any charter beside any declaration.
    """
    made = tmp_path / charter.parent.name / family
    return cli._fixture_root(made, ROOT, charter, published.INSTANCE_PATH, family)


def _paths(svg: str) -> list[str]:
    root = ElementTree.fromstring(svg)
    return [
        " ".join(str(element.get("d")).split()) for element in root.iter(f"{SVG}path")
    ]


def _flat(value: str) -> str:
    return " ".join(value.split())


# --------------------------------------------------------------------------
# The rule
# --------------------------------------------------------------------------


@pytest.mark.parametrize("family", sorted(motifs.FAMILIES))
@pytest.mark.parametrize("charter", _charters(), ids=lambda rel: rel.parent.name)
@pytest.mark.parametrize("page", PAGES, ids=lambda page: page[0])
def test_every_drawing_in_both_templates_came_from_the_registry(
    tmp_path: Path,
    page: tuple[str, object, float, float],
    charter: Path,
    family: str,
) -> None:
    """The whole rule, over the cross product a duplicate can actually be
    in: every charter this product ships crossed with every family it
    draws. A `d` that `motifs.path` did not return is a drawing whose
    provenance nothing can answer for.
    """
    _name, render, width, height = page
    root = _fixture_root(tmp_path, charter, family)
    allowed = {
        _flat(motifs.path(family, width, height)),
        _flat(motifs.path(family, lockup.BOX, lockup.BOX)),
    }
    drawn = _paths(render(root))  # type: ignore[operator]
    assert drawn, "neither the page's drawing nor the device was found"
    for value in drawn:
        assert value in allowed, (
            f"a <path> in this file is not a drawing {family} produced: {value[:80]!r}"
        )


@pytest.mark.parametrize("module", MODULES, ids=lambda path: path.name)
def test_no_module_that_draws_the_identity_holds_path_data(module: Path) -> None:
    """The other end of the same rule: a device can be neither drawn into
    the markup nor assembled out of a constant in the code that writes
    it."""
    found = path_data(module.read_text(encoding="utf-8"))
    assert found == [], (
        f"{module.name} writes path data out: {[value[:60] for value in found]}. "
        "A drawing belongs to a family in publication/motifs/, where it says "
        "what it was measured from."
    )


def test_the_sweep_finds_a_traced_device_put_back() -> None:
    """Proof the rule bites, on the exact constant that was removed."""
    planted = (
        "_MARK_PIN_LEFT = (\n"
        '    "M 15.5 39 C 21 39.5 24.5 42 24.5 45.5 C 24.5 52 20.5 57.5 15.5 61 "\n'
        '    "C 10.5 57.5 6.5 52 6.5 45.5 C 6.5 42 10 39.5 15.5 39 Z"\n'
        ")\n"
    )
    # One string, not two: Python concatenates adjacent literals before
    # the tree this reads is built, which is exactly how the constant was
    # written.
    assert len(path_data(planted)) == 1


def test_prose_about_a_traced_coordinate_is_not_one() -> None:
    """The distinction the sweep has to draw, or this module's own header
    would refuse itself."""
    assert path_data('"""M 15.5 39 C 21 39.5 24.5 42 24.5 45.5 Z"""\n') == []
    assert path_data("# M 15.5 39 C 21 39.5 24.5 42 24.5 45.5 Z\nx = 1\n") == []


# --------------------------------------------------------------------------
# The one measurement that is left, and whose artwork it is
# --------------------------------------------------------------------------


def test_the_dot_is_the_one_the_products_own_mark_closes_on() -> None:
    """Three fractions, read back out of `convener-mark.svg` itself.

    The only numbers in the lock-up that were measured off any artwork,
    and the artwork is the product's own -- measured off its own original
    raster and rebuilt as two arcs and a circle
    (`assets/brand/convener/README.md`). `assets/brand/convener/brand.json`'s
    `motif._logo_dots` already reads its *colour* off this same circle, so
    the dot the charter has been colouring all along is the dot that is
    drawn.
    """
    mark = ElementTree.fromstring((ROOT / MARK).read_text(encoding="utf-8"))
    circle = next(mark.iter(f"{SVG}circle"))
    measured = tuple(
        float(str(circle.get(name))) / MARK_BOX for name in ("cx", "cy", "r")
    )
    assert measured == pytest.approx(lockup.DOT, abs=5e-7)


#: A colour no charter here writes, so that counting what `logo_dots`
#: inks is a count of that field rather than of a hex two roles happen to
#: share -- this instance's charter sets `field` and `logo_dots` to the
#: same turquoise, and the page's own ground is a `<rect>` filled in it.
_ONLY_THE_DOT: Final = "#010203"


@pytest.mark.parametrize("family", sorted(motifs.FAMILIES))
@pytest.mark.parametrize("page", PAGES, ids=lambda page: page[0])
def test_the_charters_dot_colour_fills_one_circle_and_nothing_else(
    tmp_path: Path, page: tuple[str, object, float, float], family: str
) -> None:
    """`logo_dots` is a colour for one shape, and the shape is the dot.

    Its name is plural because it once inked a row of filled squares in the
    wordmark, traced off one instance's poster. Those went with the rest of
    the traced device, and seven comments went on describing them: three
    said four squares (`brand.py`, `motifs/bracket.py` and
    `assets/brand/convener/`'s own `_logo_dots`) and four an uncounted row
    of them (`brand_templates.py` and the other three charters), against a
    drawing that had been one circle for as long as nothing counted it.
    This counts.
    """
    _name, render, _width, _height = page
    root = _fixture_root(tmp_path, brand.source(ROOT), family)
    charter = root / brand.INSTANCE_PATH
    values = json.loads(charter.read_text(encoding="utf-8"))
    values["motif"]["logo_dots"] = _ONLY_THE_DOT
    charter.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    drawn = [
        element
        for element in ElementTree.fromstring(render(root)).iter()  # type: ignore[operator]
        if str(element.get("fill", "")).lower() == _ONLY_THE_DOT
    ]
    assert len(drawn) == 1, (
        f"{len(drawn)} element(s) are filled in the charter's logo_dots and "
        "exactly one may be: the dot the lock-up closes on"
    )
    assert drawn[0].tag == f"{SVG}circle", (
        f"the one element filled in logo_dots is a <{drawn[0].tag}> and has "
        "to be the lock-up's <circle>"
    )


def test_the_device_is_the_charters_own_drawing_and_not_the_products_mark(
    tmp_path: Path,
) -> None:
    """Where this parts company with `aa3c8b6`.

    That commit put `convener-mark.svg` in the cockpit's browser tab,
    because the cockpit *is* the product: the tab says which software a
    volunteer is running, and the instance's identity arrives afterwards,
    at run time. These two files are the instance's own artefacts,
    published under the instance's name, and the device stands in the
    logotype position beside that organisation's own address. Convener's
    two arcs closing on a dot there would read as that organisation's
    logo, and `TRADEMARK.md` reserves exactly those arcs from the licence
    and asks a fork to rename.
    """
    arcs = [
        line.strip()
        for line in (ROOT / MARK).read_text(encoding="utf-8").splitlines()
        if 'd="M' in line
    ]
    assert arcs, "the product's mark draws no arc any more"
    for family in sorted(motifs.FAMILIES):
        root = _fixture_root(tmp_path, brand.source(ROOT), family)
        for _name, render, _width, _height in PAGES:
            svg = render(root)
            for arc in arcs:
                fragment = arc.split('d="', 1)[1].split('"', 1)[0]
                assert fragment not in svg


# --------------------------------------------------------------------------
# What the box guarantees, now that it is a window rather than a device
# --------------------------------------------------------------------------


@pytest.mark.parametrize("family", sorted(motifs.FAMILIES))
@pytest.mark.parametrize("page", PAGES, ids=lambda page: page[0])
def test_the_device_is_clipped_to_its_own_box(
    tmp_path: Path, page: tuple[str, object, float, float], family: str
) -> None:
    """A nested `<svg>` rather than a `<g>` with a transform, and that is
    the whole of why the address beside it is safe.

    Every family this product draws runs off the edges of whatever canvas
    it is given -- the ribbon's own connector travels twice the canvas's
    longer side past two of them -- so a `<g>` would paint the lock-up's
    drawing straight across the address. A nested `<svg>` establishes a
    viewport of its own and clips to it.
    """
    _name, render, _width, _height = page
    root = _fixture_root(tmp_path, brand.source(ROOT), family)
    document = ElementTree.fromstring(render(root))  # type: ignore[operator]
    nested = [
        element
        for element in document.iter(f"{SVG}svg")
        if element is not document and element.get("viewBox")
    ]
    assert len(nested) == 1, "the lock-up's device is not one nested viewport"
    box = nested[0]
    assert box.get("viewBox") == "0 0 100 100"
    east = float(str(box.get("x"))) + float(str(box.get("width")))
    addresses = [
        element
        for element in document.iter(f"{SVG}text")
        if element.get("font-weight") == "500"
    ]
    assert addresses, "no address found beside the device"
    assert east <= float(str(addresses[0].get("x")))


def test_the_devices_weight_is_the_charters_own(tmp_path: Path) -> None:
    """The stroke is `motifs.stroke_width` at the charter's own ratio on
    the box, not a number of this module's -- the same arithmetic the
    page's own drawing is given."""
    for charter in _charters():
        root = _fixture_root(tmp_path, charter, brand.motif_family(ROOT))
        ratio = brand.motif_width_ratio(root)
        expected = motifs.stroke_width(lockup.BOX, lockup.BOX, ratio=ratio)
        svg = brand_templates.render_announcement_template(root)
        document = ElementTree.fromstring(svg)
        nested = next(
            element
            for element in document.iter(f"{SVG}svg")
            if element is not document and element.get("viewBox")
        )
        drawn = next(nested.iter(f"{SVG}path"))
        assert float(str(drawn.get("stroke-width"))) == pytest.approx(
            round(expected, 2)
        )


# --------------------------------------------------------------------------
# The file the device came from is still not in this repository
# --------------------------------------------------------------------------


def test_the_poster_the_device_was_traced_from_is_not_tracked() -> None:
    """Why the provenance mattered at all: the source is a photograph of a
    real person, and `.gitignore` keeps it out. A device traced from a
    file this repository may not hold is a copy of that file by another
    route.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "*announcement-template_initial*"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert tracked == []
