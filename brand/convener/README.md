# Convener — the product's own mark

**This is the product's identity, not an instance's.** It is what appears on
Convener's README, on its documentation and on the demonstration site. It is
**not** one of the themes an instance chooses: see
the instance inventory under `docs/superpowers/` for that distinction, and
`config/boundary.yml` for why this directory sits outside the instance's paths.

## The ten files

Named `convener-<layout>-<treatment>-<background>.png`.

| layout | what it is |
|---|---|
| `banner` | horizontal — mark on the left, wordmark on the right. 2172 × 724, 3∶1 |
| `stacked` | mark above the wordmark. 1254 × 1254 |
| `mark` | the mark alone, no wordmark. 1254 × 1254 |

`treatment` is `colour` or `mono`; `background` is `light` (near-white) or `dark`
(near-black). Pick the file whose background matches the surface it sits on —
none of these is transparent.

**There is no `mark-mono`.** It is the one combination the set does not carry,
and it is the one a favicon and a small avatar want. Recorded here rather than
discovered later.

## What these files cannot do, and why it matters here

**They are raster.** Every other visual rule in this repository derives from a
declared source with measured contrast (`data/brand.json`,
`scripts/generate_brand_css.py --check`). A PNG derives from nothing: it cannot
be recoloured by rule for a dark surface, and it is sharp only at the sizes it
was exported at. **An SVG is not a refinement here — it is the format the rest of
the system assumes.**

**They will not survive at small sizes.** The calendar carries nine dots and two
clasps, and two waves cross the letterform. At 32 px — a browser tab, a GitHub
avatar — that becomes noise. A simplified mark for small use is a real need, not
a nicety.

**The colour version's palette is not declared anywhere.** It carries a
blue-to-cyan gradient, a violet, a coral and a cyan, plus four more colours
inside the calendar. Until those values are written down and their contrasts
measured, this palette **cannot become a theme** in this project — the `--check`
that holds every other colour would have nothing to hold.

## Where this is going

The demonstration instance shipped with Convener is meant to wear Convener's own
identity, which would also be the first theme proving the theme mechanism with
something real rather than hypothetical. That needs the palette above extracted,
declared and measured first. Phase 12.
