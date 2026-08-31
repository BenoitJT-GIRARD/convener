"""The motif the chrome draws, for the two builds that draw it.

The showcase's masthead, its home page, its verification page and the
cockpit's sign-in screen each carry a decorative drawing behind the words.
All four hand-wrote the same three cubic-Bezier paths and the same
`stroke-width="9"`, in Nunjucks and in TypeScript -- three open loops that
`motifs/ribbon.py`'s own docstring names as the stand-in the downloadable
templates carried "until 2026-08-28", still shipping on every public page of
every duplicate. A charter naming `bracket` changed the posters and left the
pages drawing an approximation of the ribbon.

This script is what the chrome reads instead. It asks
`convener_ops.publication.motifs` for the family the charter in force names,
takes that family's own path and its own stroke weight on a square canvas,
and writes both into the one place each language reads data:

- `site/src/_data/motif.json`, which Eleventy's global-data convention hands
  every template as `motif`;
- `app/src/design/motif.ts`, which `auth/Login.tsx` imports.

Neither side derives geometry. The path is computed once, in Python, by the
family the charter names; the two generated files carry the result, and a
template interpolates it. That is D-14's shape -- the boundary is the
fixture -- and `convener-render-visual-fixtures` is the worked precedent:
its `manifest.json` is read by the pinned renderer, which "never re-derives
a page's own markup a second time in JavaScript".

Two files, one derivation
--------------------------
`generate_brand_css.py` writes the charter's colours into
`site/src/style.css` and into `app/src/design/tokens.css`, and the same
reasoning holds here: each build reads data through its own convention, and
a file placed for one of them is reached by the other only through a path
that leaves its own tree. Both files below are rendered from one call to
`motif` and both are inside `--check`, so a value can be in one and not the
other only by an edit the check refuses.

The canvas
-----------
A square of `CANVAS` units. A family expresses its drawing in fractions of
the canvas it is asked for (`motifs/ribbon.py::waypoints`,
`motifs/bracket.py::waypoints`), so the number sets the units the `viewBox`
and the stroke weight are quoted in and nothing else; the chrome sizes the
drawing in CSS, with a `width` and `height: auto`. It is 400 because that is
the `viewBox` the four templates already carried, which leaves every rule in
`site/src/style.css` and every Tailwind width in `Login.tsx` measuring what
it measured before.

What the chrome draws
-----------------------
One path, the family's own. The four templates layered three at `.85`, `.9`
and `.75`, an arrangement no family has: `motifs.path` returns a single `d`
per family, and every other surface this product draws -- the posters, the
three downloadable templates -- paints that one path. Each surface keeps the
opacity its own stylesheet sets on the element (`.masthead__motif` at `.5`,
`.hero__motif` at `.85`, `.coda__motif` at `.35`, the cockpit's
`opacity-90`), so the per-path attributes go and the per-surface weighting
stays.

The colour is untouched. The stroke comes from `--dominant` -- from
`--field` in the coda, where the dominant is the ground -- through
`site/src/style.css`, and from Tailwind's `stroke-dominant` in the cockpit,
both generated from the charter by `generate_brand_css.py`. Nothing here
writes a colour.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python scripts/generate_motif.py            # write the files
    uv run python scripts/generate_motif.py --check    # assert only

There is no mode that prints a file, and nothing this repository's Python
writes to a terminal may be non-ASCII.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, motifs

SITE_DATA_PATH: Final = Path("site") / "src" / "_data" / "motif.json"
APP_MODULE_PATH: Final = Path("app") / "src" / "design" / "motif.ts"

#: How the script is invoked, quoted in every failure message. One string,
#: so the messages cannot come to name two different commands.
COMMAND: Final = "uv run python scripts/generate_motif.py"

#: The square the drawing is computed on. See the module docstring.
CANVAS: Final = 400.0


@dataclass(frozen=True)
class Motif:
    """The family's drawing on the chrome's canvas, and its weight."""

    #: The family the charter in force names.
    family: str
    #: The `viewBox` both markup sites set.
    view_box: str
    #: The `d` attribute, one line, commands separated by a space.
    path: str
    #: The `stroke-width`, in the canvas's own units.
    stroke_width: str


def _num(value: float) -> str:
    """A number, without a trailing `.0` on a whole one."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text else "0"


def motif(root: Path) -> Motif:
    """The drawing the charter in force asks for, on the chrome's canvas.

    `brand.motif_family` answers which family, and `motifs` answers what
    that family draws; a family this product does not have raises out of
    `motifs.family`, which names the ones that exist.
    """
    family = brand.motif_family(root)
    drawing = motifs.path(family, CANVAS, CANVAS)
    weight = motifs.stroke_width(CANVAS, CANVAS, ratio=brand.motif_width_ratio(root))
    return Motif(
        family=family,
        view_box=f"0 0 {_num(CANVAS)} {_num(CANVAS)}",
        # `motifs.path` returns one command a line, which is how a hundred
        # cubics stay readable in a file a person opens. An attribute is
        # not that file: both sites below interpolate this into a `d`, and
        # a newline there is legal whitespace with nothing to gain.
        path=" ".join(drawing.splitlines()),
        stroke_width=_num(weight),
    )


#: The header a JSON file carries instead of a comment, in the shape
#: `instance/data/brand.json` and `instances/example/` already use for the
#: same purpose: an underscore-prefixed key no reader looks up.
_SITE_NOTE: Final = (
    "Generated, not authored: tools/scripts/generate_motif.py writes this "
    "file from the family the charter in force names, through "
    "tools/convener_ops/publication/motifs/. Eleventy's global-data "
    "convention hands it to every template as `motif`. Edit the charter, "
    "not this file."
)


def render_site_data(root: Path) -> str:
    """`site/src/_data/motif.json` in full."""
    drawn = motif(root)
    return (
        json.dumps(
            {
                "_generated": _SITE_NOTE,
                "family": drawn.family,
                "view_box": drawn.view_box,
                "path": drawn.path,
                "stroke_width": drawn.stroke_width,
            },
            indent=2,
        )
        + "\n"
    )


_APP_TEMPLATE: Final = """\
/**
 * The motif the cockpit's chrome draws.
 *
 * Generated, not authored: `tools/scripts/generate_motif.py` writes this
 * file from the family the charter in force names, through
 * `tools/convener_ops/publication/motifs/`. The showcase reads the same
 * drawing from `site/src/_data/motif.json`, written by the same run. Edit
 * the charter, not this file.
 *
 * The geometry is never derived here. `auth/Login.tsx` interpolates the
 * values below into an `<svg>`; the path and the weight were computed by
 * the family itself, on the square canvas `generate_motif.py::CANVAS`
 * names -- D-14's boundary, which is the fixture rather than the code
 * that produces it.
 *
 * The colour is not here either. The stroke is Tailwind's
 * `stroke-dominant`, which resolves to `--dominant`, the charter's dominant,
 * generated into `design/tokens.css` by `generate_brand_css.py`.
 *
 * `snake_case` keys: they are `site/src/_data/motif.json`'s own, and one
 * drawing spelled two ways across the boundary is what this file exists
 * to stop.
 */
export interface Motif {{
  /** The family a charter's `motif.family` names. */
  family: string;
  /** The square the drawing was computed on. */
  view_box: string;
  /** The `d` attribute, whole. */
  path: string;
  /** The `stroke-width`, in the canvas's own units. */
  stroke_width: string;
}}

export const MOTIF: Motif = {{
  family: '{family}',
  view_box: '{view_box}',
  path:
    '{path}',
  stroke_width: '{stroke_width}',
}};
"""


def render_app_module(root: Path) -> str:
    """`app/src/design/motif.ts` in full."""
    drawn = motif(root)
    return _APP_TEMPLATE.format(
        family=drawn.family,
        view_box=drawn.view_box,
        path=drawn.path,
        stroke_width=drawn.stroke_width,
    )


@dataclass(frozen=True)
class _Target:
    """One generated file: where it lives, and how to render it."""

    rel_path: Path
    render: Callable[[Path], str]


#: Both readers of the one drawing. Written whole, with no markers and no
#: splice: nothing in either file is hand-authored.
_TARGETS: Final = (
    _Target(SITE_DATA_PATH, render_site_data),
    _Target(APP_MODULE_PATH, render_app_module),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the chrome's motif from the charter in force."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if a committed file is not what "
        "the charter derives",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    named = brand.source(root).as_posix()

    # A charter written in a shape this product has moved past, or one
    # naming a drawing that does not exist, before anything is drawn: the
    # one useful thing to print is which file it is and what may be
    # written in it. Never a fall back to whichever family this product
    # happens to have -- a duplicate would wear a mark its charter does
    # not name, on every page it publishes.
    try:
        brand.load(root)
    except (brand.SupersededCharterError, motifs.UnknownMotifFamilyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    problems: list[str] = []
    for target in _TARGETS:
        path = root / target.rel_path
        try:
            rendered = target.render(root)
        except (brand.MissingMotifError, motifs.UnknownMotifFamilyError) as exc:
            # Nothing can regenerate this. A `motif` left half-written
            # names no weight to draw the family at, and neither the
            # charter in force nor the product's own can supply the
            # missing half without inventing a value.
            print(f"{target.rel_path.as_posix()}: {exc}", file=sys.stderr)
            return 1

        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if args.check:
            if current != rendered:
                problems.append(
                    f"{target.rel_path.as_posix()} is not what {named} derives."
                )
            continue

        if current == rendered:
            print(f"{target.rel_path.as_posix()} unchanged")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8", newline="")
            print(f"wrote {target.rel_path.as_posix()}")

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(
            f"Generated, not authored: run `{COMMAND}` from `tools/` and "
            "commit what it writes.",
            file=sys.stderr,
        )
        return 1

    if args.check:
        print(f"every generated file matches {named}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
