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

A single file, `instance/data/brand.json`, holds the visual identity, and **every
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

## Amended — the one file is the *instance's*, and the product ships a default

Separating the instance from the code changed which file this decision is
about, and nothing else about it. `instance/data/brand.json` still holds this series'
own values, unchanged, and every implementation still reads it. What is new is
that the file is now **optional**: it belongs to the instance, and a duplicate
that has not chosen colours yet has none. `tools/convener_ops/publication/brand.py` is the one
reader, and it takes the product's own charter — `assets/brand/convener/brand.json` —
whenever the instance has written nothing, so a fresh duplicate builds a
finished-looking site rather than a grey one. Whole file or whole file, never a
merge of the two: ownership here is a property of a file.

Shipping a default palette at all is only safe because of what this decision
was decided over. An *invented* palette that measured worse than the one it
replaced is exactly what happened before; so the generator now recomputes every
contrast the charter records, on every run, and **a palette measuring below AA
does not build**. The default is the product's own navy and coral, derived to
the lightness the system measures each role at, and it clears the same table.

**`motif` has a default too, and the line is drawn somewhere else.** `motif`
— the ribbon's stroke, its width ratio, the logo's dots — is design, and no
part of a duplicate's design has to be supplied before the thing will build:
the product ships its own, taken from its own mark, and a duplicate that has
configured nothing draws that one. What tells a reader an instance is not
configured is the unconfigured banner on its public pages, which is what an
undeclared *identity* produces — the organisation's name, its published
address, the title of its series are the values nothing can guess, and that is
where this repository refuses. A build that refuses instead publishes no page
on which to say anything at all.

The one refusal left inside the charter is a `motif` somebody wrote and left a
field short. An absence has an answer; half a section does not, and completing
it from the default would hand back three values that appear in no file — the
same reason the two charters are never merged.

The two templates a collaborator downloads (`docs/handbook/assets/*.svg`) are derived
from the charter now as well, so "nothing may hard-code a colour" finally holds
for the files that leave the repository. They had drifted onto the very palette
this decision rejected, and one line in them was set in the page's own
background colour: 1.00:1, invisible, in every poster ever downloaded.
