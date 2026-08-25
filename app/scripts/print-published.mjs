/**
 * Phase 10, task 2: what this application's build actually resolves its
 * `base` to, for each of the four configurations `npm run build` invokes,
 * printed as JSON for `tools/tests/test_published.py` to compare against
 * the same declaration read from Python.
 *
 * `vite.config.ts` is TypeScript, so it cannot simply be `require`d the
 * way `site/scripts/print-published.cjs` requires `.eleventy.js`.
 * `loadConfigFromFile` is Vite's own published API for exactly this --
 * it bundles and evaluates the real, committed configuration file the
 * same way a build does, `define` and all -- so what is printed below is
 * what the build would use, not what the source text looks like. That
 * distinction is the whole point: a comment claiming a derivation, or a
 * regular expression agreeing with one, would both survive a `base` that
 * had quietly stopped being derived.
 *
 * Run through Node from the Python suite, never from a browser and never
 * over a network, the same arrangement `check-paris-standing-start.cjs`
 * already uses for the showcase's own config.
 */

import { fileURLToPath } from 'node:url';
import { loadConfigFromFile } from 'vite';

import { identity, published } from './published.mjs';

/** The real, committed configuration file, as an OS path -- `fileURLToPath`
 *  rather than `new URL(...).pathname`, which keeps a leading slash before
 *  a Windows drive letter and would hand Vite a path it cannot open. This
 *  project is developed on Windows and run on Linux; both have to work. */
const CONFIG = fileURLToPath(new URL('../vite.config.ts', import.meta.url));

/** The four modes `package.json`'s own `build` script runs, in order.
 *  `production` is the operators' cockpit; the other three are the
 *  islands `site/` mounts on its own pages. All four must land on the
 *  same base -- an island published under a different one 404s its own
 *  fetches once served from the single `app/` subtree they all share. */
const MODES = ['production', 'island-signup', 'island-verify', 'island-survey'];

const bases = {};
const defines = {};
const identityDefines = {};
for (const mode of MODES) {
  const loaded = await loadConfigFromFile({ command: 'build', mode }, CONFIG);
  if (!loaded) throw new Error(`vite.config.ts did not load for mode ${mode}`);
  bases[mode] = loaded.config.base;
  defines[mode] = loaded.config.define?.['import.meta.env.VITE_PUBLISHED_URL'];
  // Phase 10, task 3: the identity define, read the same way and for the
  // same reason. `src/content/render.ts` resolves `{{ instance.* }}` in a
  // volunteer's browser and the cockpit's chrome names the organisation,
  // so a configuration that carried the address but not the identity
  // would build four bundles that throw on their first render.
  identityDefines[mode] =
    loaded.config.define?.['import.meta.env.VITE_INSTANCE_IDENTITY'];
}

console.log(
  JSON.stringify({ reader: published(), identity: identity(), bases, defines, identityDefines }),
);
