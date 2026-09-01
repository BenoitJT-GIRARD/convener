"""Every charter this product ships, at every canvas it renders, on one page.

Four charters live under `assets/brand/` and a duplicate chooses one of them by
name in its own declaration (`instance/config.json::charter`). Which one it
should choose is a decision somebody makes by *looking*, and until now
there was nowhere to look: the charters are measured (`generate_brand_css.py
--check` recomputes every pairing), swept for clearance
(`convener-render-template-fixtures` plus `tools/visuals/check-templates.mjs`)
and compared pixel by pixel at one of them (`render-and-compare.mjs`), and
not one of those says what any of them looks like. A maintainer answering
"which of these four should a duplicate arrive holding" had to render them
one at a time, by hand, and hold the results side by side in memory.

This writes them side by side instead.

Not a committed image, and not a page under `site/` or `app/`
--------------------------------------------------------------
Two things this deliberately is not.

It is **not a raster committed to this repository**. Every rendered image
this project has committed has had to be withdrawn or regenerated -- the
finished flyer example that carried a speaker's photograph, the reference
poster that was a frozen photograph of whichever instance ran the
repository, the README's own screenshots that had to be re-taken on the
day their certificate was earned. A board of twelve posters would be the
largest of them and the fastest to rot: it changes with every charter,
every family, every colour token and every line of `visual.py`. So the
*command* is the artefact this repository keeps, and the page is a run
artefact like `convener-render-visual-fixtures`' own output -- written to
a directory the caller names, outside this tree, never into it.

It is **not a published page**. Nothing under `site/` or `app/` grows a
route for it: the showcase is what an instance publishes about itself and
the cockpit is what a volunteer signs in to, and neither audience is the
person choosing between four charters. This is the maintainer's own
working surface, and it belongs where working artefacts belong.

Self-contained, and why that costs three megabytes
---------------------------------------------------
The page embeds the two Archivo subsets as `data:` URIs rather than
copying `assets/fonts/` beside itself as `fonts/`. A poster's own
`@font-face` asks for
`url('fonts/...')`, which resolves against the document that loads it, and
a document opened from the filesystem is an opaque origin: Chrome refuses
the font request and the board silently falls back to the system stack --
a design board lying about the typography, which is the one thing it must
not do. Inlining is what makes "a page a person can open" true with no
server, no directory and no flags. The cost is the same two font files
repeated once per poster, which is a few megabytes on a scratch file
nobody keeps.

What is on it
--------------
Per charter, read off `assets/brand/` rather than listed (the same reading
`brand.shipped` gives every other sweep, so a fifth charter appears here
on the commit that adds it):

- the composition `visual.py` generates, at every canvas `formats.FORMATS`
  names -- the square, the share banner and the A4 print poster -- each in
  an `<iframe>` at its true pixel size and scaled down, because the whole
  composition is sized in `vmin` and a poster in a box of the wrong shape
  is a different poster;
- the drawing the chrome sets, on the 400-unit square `generate_motif.py`
  computes it on, stroked and grounded the way `.masthead__motif` sets it.
  That is the one surface on the board that is not a poster, and it is
  here because it is what a duplicate's *pages* wear -- a charter chosen
  for its poster and never looked at in the masthead is half a decision.

Each charter is drawn against **this instance's declaration**, not an
invented one, for the reason `cli._template_charters` gives: a charter is
not an identity, and what a duplicate actually gets the first time it
builds is its own names in somebody else's palette.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run --frozen python scripts/render_charter_board.py OUTPUT_DIR

There is no `--check`. Nothing about this page is a claim continuous
integration could hold: it is a photograph taken to be looked at, and the
checks that hold the charters themselves already exist elsewhere.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from generate_motif import CANVAS
from generate_motif import motif as chrome_motif

from convener_ops.declaration import published
from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, formats, visual

#: The file the board is written as, inside whatever directory the caller
#: names. One name, so a second run overwrites the first rather than
#: leaving two boards a maintainer has to date by hand.
BOARD: Final = "charter-board.html"

#: How wide one poster's own cell is drawn, in CSS pixels. Every canvas is
#: scaled to this width and keeps its own aspect ratio, which is what puts
#: a 1200x1200 square and a 2480x3508 print poster in one row without
#: either being cropped.
CELL_WIDTH: Final = 300.0

#: What a poster's `@font-face` asks for, and what is put in its place.
_FONT_URL: Final = re.compile(r"url\('fonts/([^']+)'\)")


@dataclass(frozen=True)
class Cell:
    """One rendering on the board: its label and the page it holds."""

    label: str
    #: The canvas the document inside is laid out on, in its own pixels.
    width: float
    height: float
    document: str


def _font_data_uris(root: Path) -> dict[str, str]:
    """Every self-hosted face, by filename, as a `data:` URI."""
    return {
        path.name: "data:font/woff2;base64,"
        + base64.b64encode(path.read_bytes()).decode("ascii")
        for path in sorted((root / "assets" / "fonts").glob("*.woff2"))
    }


def _inlined(document: str, fonts: dict[str, str]) -> str:
    """A rendered page with its font requests answered inside itself."""

    def replace(match: re.Match[str]) -> str:
        return f"url('{fonts[match.group(1)]}')"

    return _FONT_URL.sub(replace, document)


def _charter_root(scratch: Path, root: Path, charter: Path) -> Path:
    """A repository root holding one shipped charter and this instance's
    own declaration.

    The same two files `cli._template_fixture_root` lays down, and for the
    same reason -- they are all the composition reads -- without that
    function's family override: this board asks what each charter looks
    like drawn the way it asks to be drawn, not what it looks like under
    every family in turn. That cross product is
    `convener-render-poster-fixtures`' question and it already has ninety
    renderings of its own.
    """
    made = scratch / charter.parent.name
    (made / brand.INSTANCE_PATH.parent).mkdir(parents=True, exist_ok=True)
    (made / published.INSTANCE_PATH).write_bytes(
        (root / published.INSTANCE_PATH).read_bytes()
    )
    shutil.copyfile(root / charter, made / brand.INSTANCE_PATH)
    shutil.copytree(root / "assets" / "fonts", made / "fonts")
    return made


def _chrome_document(made: Path, colours: dict[str, str]) -> str:
    """The chrome's own drawing, on its own square.

    `.masthead__motif` in `site/src/style.css` is what this restates in
    miniature and the only thing restated is the three declarations that
    are visible at this size: the drawing is stroked in the dominant, at
    half opacity, over the band the masthead sets as its ground. The
    geometry is not restated at all -- `generate_motif.motif` is the one
    function that computes it, and the chrome reads its output through two
    generated files rather than deriving it a second time.
    """
    drawn = chrome_motif(made)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; height: 100%; }}
  body {{ background: {colours["band"]}; display: grid; place-items: center; }}
  svg {{ width: 100%; height: 100%; opacity: .5; }}
</style></head><body>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="{drawn.view_box}"
     fill="none" stroke="{colours["dominant"]}"
     stroke-width="{drawn.stroke_width}"
     stroke-linecap="round" stroke-linejoin="round">
  <path d="{drawn.path}"/>
</svg>
</body></html>
"""


def cells(made: Path, colours: dict[str, str]) -> list[Cell]:
    """Every rendering one charter contributes, in the order it is read."""
    drawn = [
        Cell(
            label=f"{fmt.name} {fmt.width:.0f}x{fmt.height:.0f}",
            width=fmt.width,
            height=fmt.height,
            document=visual.render_announcement(
                visual.FIXTURE_ANNOUNCEMENT,
                width=fmt.width,
                height=fmt.height,
                root=made,
            ),
        )
        for fmt in formats.FORMATS
    ]
    drawn.append(
        Cell(
            label=f"chrome {CANVAS:.0f}x{CANVAS:.0f}",
            width=CANVAS,
            height=CANVAS,
            document=_chrome_document(made, colours),
        )
    )
    return drawn


def _cell_html(cell: Cell, fonts: dict[str, str]) -> str:
    """One cell: a box of the canvas's own shape, holding it scaled down.

    An `<iframe>` and not a `<div>`, because the composition is sized in
    `vmin` throughout: it reads its own viewport, so it has to be given
    one. `transform: scale` on a frame at the true pixel size is what
    shows the real layout rather than a reflow of it -- the print poster
    at 2480 wide reflows into something no printer will ever produce if it
    is handed a 300-pixel viewport instead.
    """
    scale = CELL_WIDTH / cell.width
    srcdoc = html.escape(_inlined(cell.document, fonts), quote=True)
    return f"""      <figure class="cell">
        <div class="frame" style="width: {CELL_WIDTH:.0f}px;
             height: {cell.height * scale:.0f}px;">
          <iframe loading="lazy" title="{html.escape(cell.label)}"
                  style="width: {cell.width:.0f}px; height: {cell.height:.0f}px;
                         transform: scale({scale:.6f});"
                  srcdoc="{srcdoc}"></iframe>
        </div>
        <figcaption>{html.escape(cell.label)}</figcaption>
      </figure>"""


def _swatches(colours: dict[str, str]) -> str:
    """The five colours a poster is actually drawn from, as chips.

    Named rather than every key in the charter: these are the positions
    the composition sets type and grounds at, and a chip for a token no
    poster on this board draws would be a palette catalogue instead of a
    reading of what is above it.
    """
    named = ("dominant", "field", "band", "ink", "field_text")
    chips = "".join(
        f'<span class="chip" style="background: {colours[name]}"></span>'
        f"<code>{name} {colours[name]}</code>"
        for name in named
    )
    return f'<div class="swatches">{chips}</div>'


def render_board(root: Path) -> str:
    """The whole page, every charter under `assets/brand/` in name order."""
    fonts = _font_data_uris(root)
    sections: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        for charter in brand.shipped(root):
            made = _charter_root(Path(scratch), root, charter)
            values = json.loads((root / charter).read_text(encoding="utf-8"))
            colours = brand.colours(values)
            family = str(values[brand.MOTIF_KEY][brand.MOTIF_FAMILY])
            drawn = "\n".join(_cell_html(cell, fonts) for cell in cells(made, colours))
            sections.append(
                f"""    <section>
      <h2>{html.escape(charter.parent.name)}"""
                f' <span class="family">{html.escape(family)}</span></h2>\n'
                f"      {_swatches(colours)}\n"
                f'      <div class="row">\n{drawn}\n      </div>\n'
                "    </section>"
            )
    body = "\n".join(sections)
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<title>Charters this product ships</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; padding: 2rem; background: #f6f6f4; color: #1b1b1b;
         font: 14px/1.5 'Segoe UI', system-ui, sans-serif; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 .25rem; }}
  p.lede {{ margin: 0 0 2rem; max-width: 60ch; color: #444; }}
  h2 {{ font-size: 1.1rem; margin: 0 0 .5rem; text-transform: lowercase; }}
  .family {{ font-weight: 400; color: #666; }}
  .family::before {{ content: 'drawn with '; }}
  section {{ margin-bottom: 3rem; }}
  .swatches {{ display: flex; flex-wrap: wrap; gap: .35rem 1rem;
               align-items: center; margin-bottom: .75rem; }}
  .chip {{ width: 1rem; height: 1rem; border: 1px solid #0002;
           display: inline-block; vertical-align: -.2rem; }}
  code {{ font: 12px/1 ui-monospace, 'JetBrains Mono', monospace;
          color: #555; margin-left: .3rem; }}
  .row {{ display: flex; flex-wrap: wrap; gap: 1.25rem; align-items: flex-end; }}
  .cell {{ margin: 0; }}
  .frame {{ overflow: hidden; border: 1px solid #0002; background: #fff; }}
  iframe {{ border: 0; transform-origin: 0 0; display: block; }}
  figcaption {{ font-size: 12px; color: #666; margin-top: .35rem; }}
</style>
</head>
<body>
  <h1>Charters this product ships</h1>
  <p class="lede">Generated by
  <code>tools/scripts/render_charter_board.py</code>: every charter under
  <code>assets/brand/</code>, at every canvas <code>formats.FORMATS</code> names,
  plus the drawing the chrome sets. Each is rendered against this
  instance's own declaration, which is what a duplicate gets the first
  time it builds. Nothing here is committed; run the command again.</p>
{body}
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", help="where to write the board")
    args = parser.parse_args(argv)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    board = out / BOARD
    board.write_text(render_board(repo_root()), encoding="utf-8")
    print(f"wrote {board}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
