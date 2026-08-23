# D-16 — The visual identity has one source of fact, and it is the original artwork

**Status:** Accepted

## Context

Three separate implementations of the visual identity had drifted, each
derived from a later reconstruction rather than from the organisation's own
original design files: a desaturated purple, a darkened turquoise, and —
doing the most damage to how recognisable the result was — the original's
warm neutrals replaced with a cool slate grey.

Measurement also refuted the reasoning the darkened turquoise had been given.
It had been justified as a defensible trade-off because text contrast on the
true turquoise was assumed to be borderline. It is not: one text colour on
the true turquoise measures 7.93:1 (AAA), another 13.06:1. The relationship
is the opposite of what was assumed — darkening a background under dark text
*loses* contrast, and the shipped darker version measured 4.44:1, under the
AA threshold, with two further text colours also failing. **Restoring the
original palette was the more accessible choice, not an aesthetic one made
against accessibility.**

## Decision

A single file, `data/brand.json`, holds the visual identity, and **every
implementation reads it** — the showcase's stylesheet, the visual generator,
the application's own design tokens. Its values are extracted from the
organisation's **original** design files — the original presentation for
colours and type, the original announcement image for composition. Later
reconstructions of those files in the same asset folder are not
authoritative.

## Rejected

Treating the reconstructed files as the source of truth, or leaving each
surface free to hold its own copy of the palette.

## Cost

Nothing may hard-code a colour that already has an entry in `brand.json`. A
deliberately retouched on-screen variant is still allowed — but only if it
is declared as a variant and measured, not simply arrived at by accident.
