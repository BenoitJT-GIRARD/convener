<!-- cspell:ignore currentColor color -->
# Convener — the product's own mark

**This is the product's identity, not an instance's.** It is what appears on
Convener's README, its documentation and its demonstration site. It is **not**
one of the themes an instance chooses. `config/boundary.yml` says why this
directory sits outside the instance's paths, and `data/brand.json` is where an
instance's own charter goes instead.

## The mark

Two concentric arcs closing on a single dot. The arcs read as the C of Convener
and as two parties coming together; the dot is the moment they meet. Nothing in
it depicts a calendar, deliberately — a calendar glyph says what a scheduling
tool *does*, which every scheduling tool does.

It is built from circles and arcs, so it holds at the sizes that decide whether a
mark works: a browser tab, an avatar.

## The files

| file | what it is |
|---|---|
| `convener-mark.svg` | the mark — ink follows the page, dot is coral |
| `convener-mark-mono.svg` | the mark in a single ink, dot included |
| `convener-banner.svg` | mark and wordmark side by side |
| `convener-banner-mono.svg` | the same, single ink |
| `brand.json` | the product's own charter — the palette *and* the motif a duplicate builds with when it has chosen neither |

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
| navy | `#012765` | **14.19** | — |
| coral | `#fd6b52` | 2.84 | **5.00** |

Navy read **14.23** here until it was recomputed with the repository's own
WCAG 2.1 arithmetic (`tools/convener_ops/brand.py`), which gives 14.194. Nothing
turns on the difference — it clears AAA either way — but a measurement nobody
rechecks is exactly what D-16 was decided over, so the figure the build asserts
and the figure written here are the same one.

**The role those numbers impose:** coral is an accent **on the ink**, never text
on white — 2.84 is below AA at any size. Navy on white clears AAA with room.

This is the same shape of constraint `data/brand.json` records for the other
palette here, so these values entered the system without bending it. **They are
declared now**, in `brand.json` beside this file, and
`generate_brand_css.py --check` recomputes every pairing in it on every run and
fails the build if one drops below AA. It is no longer a measurement in a
README; it is a rule.

## The charter beside this file

`brand.json` is what `tools/convener_ops/brand.py` reads when an instance has written
no `data/brand.json` of its own — so a fresh duplicate builds a finished-looking
site rather than a grey one. Two of its values are the two above; every other
token is derived from them by one stated rule, and `brand.json`'s own
`derived._derivation` gives it: **the product's own hues, at the lightness the
system measures each role at.** The neutrals come from navy and coral in equal
parts, which are near enough to opposite that their blend is this palette's own
grey.

Two consequences worth knowing before using it:

- **The token names are the system's, not this palette's.** `purple` is the
  navy, `turquoise` is a coral field. They name positions in the composition,
  never hues — see `brand.json`'s own `_names`.
- **It carries a `motif`, and the motif is this mark taken apart.** The
  ribbon's stroke is the navy; the wordmark's dots are the coral of the dot
  above; the stroke weight is the proportion the inner arc is drawn at — 25.86
  on a radius of 131.72, 0.196 of its own radius — carried onto the ribbon's
  curls, which `tools/convener_ops/ribbon.py` builds at radius 0.105 and 0.103
  of the shorter side. That gives 0.0204, and it means a curl on a poster is
  drawn at the weight this mark's own line is drawn at, at any size.
  **That section had no default at all until 2026-08-26**, on the reasoning
  that a mark somebody drew must not be lent to a duplicate that forgot to
  configure one. The mark half of that is right and has not moved. The
  “therefore no default may exist” half did not follow from it, and what it
  produced was a clone whose first build stopped, asking a seminar organiser
  for a design file. Identity is what has to be supplied — an organisation's
  name, its published address, the title of its series. Design never is, and
  the guard against a duplicate passing for somebody else is the unconfigured
  banner on the public pages, not a build that will not run.

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
