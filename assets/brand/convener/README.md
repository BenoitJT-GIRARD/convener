<!-- cspell:ignore currentColor color -->
# Convener — the product's own mark

**This is the product's identity.** It is what appears on Convener's README,
its documentation and the demonstration built out of it.
`declarations/boundary.yml` says why this directory sits outside the instance's
paths, and `instance/data/brand.json` is where an instance's own charter goes.

## The mark

Two concentric arcs closing on a single dot. The arcs read as the C of Convener
and as two parties coming together; the dot is the moment they meet.

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

**There are no light and dark variants, and no rasters** — one file per shape.

## How the colour works

The ink is `currentColor`. **The file takes the colour of whatever it is placed
in**, so one file serves a white page and a near-black one.

- **Inlined into a page** — it inherits. Set `color` on the element or an
  ancestor: `#012765` on a light ground, `#fff` on a dark one. Set nothing and it
  inherits the page's text colour, usually black. That is the trade: it follows
  any ground, and in exchange the page has to say which.
- **Opened on its own, or loaded through an image tag** — a
  `svg:root { color: #012765 }` rule inside each file makes it navy, and a
  `prefers-color-scheme: dark` rule beside it makes it white.

`svg:root` matches only when the file *is* the document. An attribute would win
over inheritance instead, and the mark would stay navy on a dark ground.

The dark-scheme half of that rule is there for the one surface that renders the
file as a document and cannot be told what colour to use: a browser tab. The
mark is the cockpit's own favicon (`app/scripts/copy-mark.mjs`), and navy on
Chrome's own dark tab strip — `#202124` — measures **1.13:1**. White there
measures **16.1:1**.

## The palette

Measured from the original artwork, WCAG 2.1 relative luminance, recomputed with
the repository's own arithmetic (`tools/convener_ops/publication/brand.py`).

| | value | on white | on navy |
|---|---|---|---|
| navy | `#012765` | **14.19** | — |
| coral | `#fd6b52` | 2.84 | **5.00** |

**The role those numbers impose:** coral is an accent **on the ink**, never text
on white — 2.84 is below AA at any size. Navy on white clears AAA with room.

Both values are declared in `brand.json` beside this file, and
`generate_brand_css.py --check` recomputes every pairing in it on every run and
fails the build if one drops below AA.

## The charter beside this file

`brand.json` is what `tools/convener_ops/publication/brand.py` reads when an instance has written
no `instance/data/brand.json` of its own — so a fresh duplicate builds a
finished-looking site rather than a grey one. Two of its values are the two above; every other
token is derived from them by one stated rule, and `brand.json`'s own
`derived._derivation` gives it: **the product's own hues, at the lightness the
system measures each role at.** The neutrals come from navy and coral in equal
parts, which are near enough to opposite that their blend is this palette's own
grey.

**`colour.field` is the one role that rule no longer sets**, and the exception
is worth knowing before anybody retouches it. Matching a luminance across two
hues does not match what the eye is asked to sit in front of: the coral at the
luminance the rule copies filled a whole page harder than the colour it was
matched to. It is the same coral, mixed further toward white, and what stops it
there is a bound rather than a preference — `layout._grounds` in that file
measures the three separations the composition sets between one ground and
another and states the floor, and
`convener_ops.publication.brand.GROUND_SEPARATION_FLOOR` is what refuses a
charter that crosses it.

Two things follow:

- **The token names are the system's**, and each names a position in the
  composition: `dominant` holds the navy, `field` the coral ground, `band` the
  bands across it — see `brand.json`'s own `_names`.
- **It carries a `motif`, and the motif is this mark taken apart.** The
  drawing is `bracket`: each of the two arcs above is struck on a circle, and
  a bracket is that circle's own box with the same opening left in the side
  the dot faces — a spine, two arms, and a return on each arm, straight
  segments throughout, one bracket standing against each vertical edge of the
  page (`tools/convener_ops/publication/motifs/bracket.py`). The stroke is the
  navy; the wordmark's dots are the coral of the dot above; the stroke weight
  is the proportion the outer arc is drawn at — 68.69 on a radius of 205.66,
  0.334 of its own radius — carried onto the left bracket's own half-width,
  0.061 of the shorter side. That gives 0.0204, and it means a bracket on a
  poster is drawn at the weight this mark's own arc is drawn at, at any size.

A duplicate that has configured no charter therefore builds against this one.
What a duplicate has to supply is identity — an organisation's name, its
published address, the title of its series — and the unconfigured banner on
the public pages is what says it has not yet.

## How the mark and the wordmark were made

**The mark is measured.** Radii, stroke widths and one 81 degree opening read
off the original artwork and rebuilt as two arcs and a circle. The
reconstruction was overlaid on the original: it matched exactly.

**The wordmark is Archivo at weight 400, converted to outlines.** The face of
the original artwork was never identified; the only Archivo axis pair whose
proportions match it is weight 800 at width 80, a condensed heavy the logo
visibly is not.

Archivo is the face and weight `instance/data/brand.json` already declares
as `body`, and it ships here under the SIL Open Font License 1.1 (`assets/fonts/`,
`Archivo-LICENSE.txt`). The glyphs are paths, so no font is needed to render.

It reads about 9 % wider than the original wordmark at the same cap height,
because Archivo is a grotesque and the original is geometric.
