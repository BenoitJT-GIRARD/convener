<!-- cspell:ignore currentColor color -->
# Convener — the product's own mark

**This is the product's identity, not an instance's.** It is what appears on
Convener's README, its documentation and its demonstration site. It is **not**
one of the themes an instance chooses: see the instance inventory under
`docs/superpowers/` for that distinction, and `config/boundary.yml` for why this
directory sits outside the instance's paths.

## The mark

Two concentric arcs closing on a single dot. The arcs read as the C of Convener
and as two parties coming together; the dot is the moment they meet. Nothing in
it depicts a calendar, deliberately — a calendar glyph says what a scheduling
tool *does*, which every scheduling tool does.

It is built from circles and arcs, so it holds at the sizes that decide whether a
mark works: a browser tab, an avatar.

## The four files

| file | what it is |
|---|---|
| `convener-mark.svg` | the mark — ink follows the page, dot is coral |
| `convener-mark-mono.svg` | the mark in a single ink, dot included |
| `convener-banner.svg` | mark and wordmark side by side |
| `convener-banner-mono.svg` | the same, single ink |

**There are no light and dark variants, and no rasters.** There is nothing to
keep in step, because there is only one file per shape.

## How the colour works — read this before using them

The ink is `currentColor`. **The file takes the colour of whatever it is placed
in**, so one file serves a white page and a near-black one.

- **Inlined into a page** — it inherits. Set `color` on the element or an
  ancestor: `#012765` on a light ground, `#fff` on a dark one. Set nothing and it
  inherits the page's text colour, usually black. That is the trade: it follows
  any ground, and in exchange the page has to say which.
- **Opened on its own, or loaded through an image tag** — a
  `svg:root { color: #012765 }` rule inside each file makes it navy.

That rule is `svg:root` and **not** a `color` attribute, which is the whole
point: an attribute wins over inheritance, so the mark would stay navy on a dark
ground and the single-file idea would collapse. `svg:root` matches only when the
file *is* the document. Rendered on both grounds and looked at, not assumed.

## The palette

Measured from the original artwork, WCAG 2.1 relative luminance.

| | value | on white | on navy |
|---|---|---|---|
| navy | `#012765` | **14.23** | — |
| coral | `#fd6b52` | 2.84 | **5.00** |

**The role those numbers impose:** coral is an accent **on the ink**, never text
on white — 2.84 is below AA at any size. Navy on white clears AAA with room.

This is the same shape of constraint `data/brand.json` records for the other
palette here, so these values can enter the system without bending it — but
**they are not declared anywhere yet.** Until they are, and until
`generate_brand_css.py --check` holds them, this is a measurement in a README,
not a rule the build enforces.

## Two things that were decided rather than defaulted

**The mark is measured, not traced.** Radii, stroke widths and one 81 degree
opening read off the original artwork and rebuilt as two arcs and a circle. The
reconstruction was overlaid on the original: it matched exactly.

**The wordmark is Archivo at weight 400, converted to outlines — and it is not
the face of the original artwork.** That face was never identified; the only
Archivo axis pair whose proportions match it is weight 800 at width 80, a
condensed heavy the logo visibly is not, so a coincidence rather than a match.
Two alternatives were rejected: tracing letterforms out of a raster gives exactly
the wobbly curves a vector exists to avoid, and building a publicly redistributed
product's identity on an unidentified, unlicensed face is a liability nobody
would notice until it mattered.

Archivo is the face and weight `data/brand.json` already declares as `body`, and
it ships here under the SIL Open Font License 1.1 (`fonts/`,
`Archivo-LICENSE.txt`). The glyphs are paths, so no font is needed to render.

It reads about 9 % wider than the original wordmark at the same cap height,
because Archivo is a grotesque and the original is geometric. **Matching it would
mean condensing Archivo to imitate a face this project decided not to use** —
the wrong trade, and a visible one.

## What is still open

**At 16 px the inner arc thins to a hairline.** Legible, but a true 16 px favicon
would be better served by a heavier inner stroke, or by the outer arc and the dot
alone. Rendered at 16, 32 and 64 and looked at.

**A raster will be needed eventually** — a social preview card cannot be SVG.
When that day comes it is generated from these files, never drawn again: one
source, derived outputs, the rule everything else in this repository follows.
