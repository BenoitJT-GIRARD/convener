# Convener — the product's own mark

**This is the product's identity, not an instance's.** It is what appears on
Convener's README, on its documentation and on the demonstration site. It is
**not** one of the themes an instance chooses: see the instance inventory under
`docs/superpowers/` for that distinction, and `config/boundary.yml` for why this
directory sits outside the instance's paths.

## The mark

Two concentric arcs closing on a single dot. The arcs read as the C of Convener
and as two parties coming together; the dot is the moment they meet — an event, a
date, a point in time. Nothing in it depicts a calendar, deliberately: a calendar
glyph says what a scheduling tool *does*, which every scheduling tool does.

It is built from circles and arcs, so it stays legible at the sizes that matter
most — a browser tab, an avatar — which is the test a mark either passes or fails.

## The palette

Measured from `convener-mark-colour-light.png`, WCAG 2.1 relative luminance.

| | value | on white | on navy |
|---|---|---|---|
| navy | `#012765` | **14.23** | — |
| coral | `#fd6b52` | 2.84 | **5.00** |

**The role that follows from those numbers:** coral is an accent **on navy**, and
never text on white — 2.84 is below AA for any text size. Navy on white clears
AAA with room to spare and carries the wordmark.

This is the same shape of constraint `data/brand.json` records for the other
palette in this repository, which is why these values can enter the system
without bending it — but **they are not declared anywhere yet**. Until they are,
and until `generate_brand_css.py --check` holds them, this is a measurement in a
README, not a rule the build can enforce.

## The files

Named `convener-<layout>-<treatment>-<background>.png`.

| layout | what it is |
|---|---|
| `banner` | horizontal — mark left, wordmark right. 2172 × 724, 3∶1 |
| `stacked` | mark above the wordmark. 1254 × 1254 |
| `mark` | the mark alone. 1254 × 1254 |

`treatment` is `colour` (navy and coral) or `mono` (one ink); `background` is
`light` or `dark`. **None is transparent** — pick the file whose background
matches the surface it sits on.

The `banner-mono-*` and the `stacked-*` files carry the line
*PLAN · HOST · SHARE* beneath the wordmark; the rest do not. **The bare ones are
stronger** and should lead.

**There is no raster `mark-mono`** — but `convener-mark-mono.svg` is exactly
that, and it inherits `currentColor`, so it takes the colour of whatever it sits
in rather than needing one file per surface.

**At 16 px the inner arc thins to a hairline.** It is still legible, but a true
16 px favicon would be better served by a variant with a heavier inner stroke, or
by the outer arc and the dot alone. Rendered and looked at, not assumed.

## What is still missing

**These are raster.** Every other visual rule in this repository derives from a
declared source with measured contrast. A PNG derives from nothing: it cannot be
recoloured by rule for a dark surface, and it is sharp only at the sizes it was
exported at.

## The vectors

| file | what it is |
|---|---|
| `convener-mark.svg` | the mark, navy and coral |
| `convener-mark-mono.svg` | the mark, `currentColor` — takes the colour of whatever it sits in |
| `convener-banner.svg` | mark and wordmark, navy and coral |
| `convener-banner-mono.svg` | the same, `currentColor` |

**The mark is measured, not traced** — radii, stroke widths and one 81° opening
read off the raster and rebuilt as two arcs and a circle. It overlays the PNG
exactly; that was rendered and looked at, not assumed.

**The wordmark is not the face in the raster, and that face was not identified.**
The only Archivo axis pair whose proportions match it is weight 800 at width 80 —
a condensed heavy the logo visibly is not, so a coincidence rather than a match.
Two alternatives were rejected: tracing letterforms out of a raster gives exactly
the wobbly curves a vector exists to avoid, and building a publicly redistributed
product's identity on an unidentified, unlicensed face is a liability.

So the wordmark is **Archivo at weight 400** — the face and weight
`data/brand.json` already declares as `body`, already shipped here under the SIL
Open Font License 1.1 — converted to outlines, so no font is needed at render
time. It reads about 9 % wider than the raster (1333 px against 1223 px at the
same cap height) because Archivo is a grotesque and the raster's face is
geometric. **Matching it would mean condensing Archivo to imitate a face this
project has decided not to use**, which is the wrong trade.

The raster lockups stay for now. Compare them and pick which leads.
