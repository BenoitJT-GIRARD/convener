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

The `banner-mono-*` and the `stacked-*` files carry the strapline
*PLAN · HOST · SHARE*; the rest do not. **The bare lockups are the stronger
ones** and should lead.

**There is no `mark-mono`.** It is what a favicon and a small avatar want. With a
single ink plus one dot it is a trivial derivation — see below.

## What is still missing

**These are raster.** Every other visual rule in this repository derives from a
declared source with measured contrast. A PNG derives from nothing: it cannot be
recoloured by rule for a dark surface, and it is sharp only at the sizes it was
exported at.

That mattered before; it matters **more** now, because the mark has become simple
enough that the vector form is a handful of arcs and a circle. `convener-mark.svg`
in this directory is that reconstruction — see its own header for what was
measured and what it does not cover.
