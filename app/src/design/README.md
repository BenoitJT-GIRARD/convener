# Design tokens

TEC brand identity, derived from `data/brand.json` -- Anonymous's own turquoise
and purple, warm neutrals, never a reconstruction's guess at them. Archivo
for both display and body, JetBrains Mono for IDs, both self-hosted from the
repository root's `fonts/` (`app/scripts/copy-fonts.mjs`) -- never a request
to Google, on pages that carry a signup form and a certificate lookup.
Restrained, intentional, never generic.

`tokens.css`'s custom properties are generated:
`scripts/generate_brand_css.py` owns the block between the
`GENERATED TOKENS` markers. Do not hand-edit it -- change `data/brand.json`
and run `uv run python ../scripts/generate_brand_css.py` from `tools/`, then
commit what it writes. A colour with no brand equivalent (`--danger`,
`--info`) is the one deliberate exception, and is named as such in the
generator.

`tokens.ts` used to sit alongside `tokens.css`, generated the same way.
Retired rather than kept generated: nothing under `app/src` ever imported
it, and a generated file nobody reads still drifts from what actually
renders -- it only looks maintained. Its two exports (`colors`, `fonts`)
have no live consumer; if one ever needs them, wire it up and regenerate,
rather than resurrect an unread copy.
