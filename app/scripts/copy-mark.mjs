/* Copies `assets/brand/convener/convener-mark.svg` -- the product's own mark --
 * into `public/favicon.svg`, which is the icon `index.html` points a
 * browser tab at.
 *
 * What was there before
 * ----------------------
 * A hand-drawn purple bolt, carrying `#863bff` and a `color(display-p3)`
 * variant of it as literals. It arrived with the Vite scaffold and never
 * left. It is in no charter, it is not this product's mark, and no check
 * in this repository could see it: `generate_brand_css.py --check` knows
 * the two stylesheets it writes, and `test_brand.py`'s own sweeps knew a
 * list of files nobody had added it to. That is the same class of defect
 * as the palette the two downloadable templates carried until they were
 * generated -- a colour shipping to every duplicate under a name no
 * declaration holds, in a medium no check reads.
 *
 * `app/public/icons.svg` went with it, and for a stronger reason: it was
 * scaffold too -- a sprite of six symbols, two of them drawn in `#aa3bff`
 * from the same undeclared purple lineage as the bolt, four of them other
 * organisations' logos -- and nothing in this repository ever referenced
 * it. It was shipped into every duplicate's bundle and rendered by
 * nothing.
 *
 * Why the product's mark and not the charter's
 * ---------------------------------------------
 * Because a charter has no mark to give. It declares a palette and a
 * motif family (`assets/brand/convener/brand.json`), and a motif is a drawing
 * for the margin of a page, not a logotype -- an instance naming `ribbon`
 * has no mark of its own anywhere in its declaration, so "follow the
 * charter" would have nothing to follow.
 *
 * And because this is the *cockpit*, which is the product. `index.html`'s
 * own `<title>` already settles the same question the same way and says
 * so: this file is served before any script has run, so the instance's
 * own name cannot be in it -- `src/main.tsx` sets `document.title` from
 * `instance/config.json` the moment it runs. The instance's identity
 * reaches the cockpit at runtime, through its title and its palette; what
 * the tab shows before that is the product a volunteer is running.
 *
 * Why a copy at build time rather than a second committed file
 * -------------------------------------------------------------
 * `docs/engineering/content-rules.md`: one notion, one home. The mark is
 * `assets/brand/convener/convener-mark.svg` and nowhere else, so there is no
 * second copy to keep in step and no way for a tab icon to drift from the
 * artwork it is meant to be. This is the same arrangement `copy-fonts.mjs`
 * makes for the self-hosted faces, for the same reason, and it runs in the
 * same `prebuild`/`predev` chain.
 *
 * An absent source is a broken checkout rather than an unconfigured
 * integration, so this fails loudly (D-25) rather than shipping a build
 * with no icon at all.
 */
import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(__dirname, '..', '..', 'assets', 'brand', 'convener', 'convener-mark.svg');
const DEST = resolve(__dirname, '..', 'public', 'favicon.svg');

if (!existsSync(SRC)) {
  console.error(`copy-mark: source not found at ${SRC}`);
  process.exit(1);
}

mkdirSync(dirname(DEST), { recursive: true });
copyFileSync(SRC, DEST);

console.log(`copy-mark: copied the product's mark -> ${relative(process.cwd(), DEST)}`);
