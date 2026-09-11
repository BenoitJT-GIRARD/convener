/* Which files under ../docs the app serves, and under what relative path.
 *
 * Kept apart from the copy script itself so the rule can be asserted rather
 * than assumed: a template committed under `docs/` that this walk does not
 * return is a download link that 404s for every volunteer, and nothing in the
 * build would say so. `app/tests/content/visual-kit.test.tsx` calls `walk()` on the
 * real `docs/` tree for exactly that reason.
 */
import { readdir } from 'node:fs/promises';
import { join } from 'node:path';

/** Directories under `docs/` that never reach the app.
 *  - `stylesheets` — belongs to the handbook's own rendering, not the app's.
 *  - `app` — `docs/handbook/assets/app/` is the deployed bundle (git-ignored); copying
 *    a build output back into the next build is how a bundle eats itself. */
export const SKIP_DIRS = new Set(['stylesheets', 'app']);

/** Extensions served to the app. Markdown is the content; SVG and PNG are the
 *  visual kit — open formats a volunteer downloads and opens in their own
 *  tool, on their own account (D-08's fallback). Nothing else is copied: the
 *  handbook is not a file drop. */
export const SERVED_EXTENSIONS = ['.md', '.svg', '.png'];

export function isServed(name) {
  return SERVED_EXTENSIONS.some(ext => name.toLowerCase().endsWith(ext));
}

/** Every served file under `dir`, as paths relative to it. */
export async function walk(dir, base = '') {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const rel = join(base, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      out.push(...(await walk(join(dir, entry.name), rel)));
    } else if (entry.isFile() && isServed(entry.name)) {
      out.push(rel);
    }
  }
  return out;
}
