# Design tokens

TEC brand identity, derived from `data/brand.json` -- Anonymous's own turquoise
and purple, warm neutrals, never a reconstruction's guess at them. Archivo
for both display and body, JetBrains Mono for IDs. Restrained, intentional,
never generic.

`tokens.css` and `tokens.ts` are generated: `scripts/generate_brand_css.py`
owns the block of custom properties between the `GENERATED TOKENS` markers
in `tokens.css`, and the whole of `tokens.ts`. Do not hand-edit either --
change `data/brand.json` and run `uv run python ../scripts/generate_brand_css.py`
from `tools/`, then commit what it writes. A colour with no brand equivalent
(`--danger`, `--info`) is the one deliberate exception, and is named as such
in the generator.
