/* What `copy-handbook.mjs` is actually allowed to publish, derived from
 * `../src/content/registry.ts` -- never from walking `docs/` and hoping a
 * skip-list stays complete.
 *
 * The script that runs this (`copy-handbook.mjs`) executes under bare `node`
 * in `prebuild`/`predev`, on a Node version this repository does not control
 * (see `.github/workflows/deploy.yml`), so it cannot `import` a `.ts` file
 * the way the app and its test suite do. `parseContentFiles` and
 * `parsePublicAssets` below read `registry.ts`'s own source text instead of
 * evaluating it -- no TypeScript toolchain, no dynamic `eval`, nothing
 * beyond two regular expressions over a file whose format is exactly as
 * regular as an object literal of string properties.
 *
 * That is a real gap between "what this file extracts" and "what registry.ts
 * actually exports" for anyone who reformats it by hand -- which is exactly
 * why `app/tests/copy-handbook.test.ts` pins both extractors against the
 * real `CONTENT_REGISTRY` and `PUBLIC_ASSETS`, imported natively by the test
 * runner, on every run. A drift here fails that test; it does not ship
 * silently.
 */
import { cp, mkdir, readdir, rm, stat } from 'node:fs/promises';
import { dirname, extname, join } from 'node:path';

/** Every `file: '...'` value in `registry.ts`'s source text -- one per
 *  `CONTENT_REGISTRY` entry, several entries sharing a file (a page and the
 *  fragments transcluded from it) collapsed to one. */
export function parseContentFiles(source) {
  const files = new Set();
  for (const m of source.matchAll(/\bfile:\s*'([^']+)'/g)) files.add(m[1]);
  return [...files].sort();
}

/** The string literals inside `PUBLIC_ASSETS`'s own array literal. Returns
 *  `[]` if the export is missing or empty -- a normal state for a caller
 *  probing a hand-built fixture in a test, never for the real
 *  `registry.ts`, which `copy-handbook.test.ts` checks always defines it. */
export function parsePublicAssets(source) {
  const block = /PUBLIC_ASSETS[^=]*=\s*\[([\s\S]*?)\]/.exec(source);
  if (!block) return [];
  const files = new Set();
  for (const m of block[1].matchAll(/'([^']+)'/g)) files.add(m[1]);
  return [...files].sort();
}

/** The complete allowlist: every path `copy-handbook.mjs` may publish,
 *  sorted and deduplicated. Nothing under `docs/` reaches
 *  `public/handbook/` unless its path appears here. */
export function publishedPaths(registrySource) {
  return [...new Set([...parseContentFiles(registrySource), ...parsePublicAssets(registrySource)])].sort();
}

/** Every file under `dir`, as slash-separated paths relative to it --
 *  regardless of extension or directory name. Used only to sweep a
 *  *destination* the copy step just wrote, in tests: proof of what actually
 *  landed on disk, not of what the filter meant to allow. */
export async function walkAll(dir, base = '') {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const out = [];
  for (const entry of entries) {
    const rel = base ? `${base}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      out.push(...(await walkAll(join(dir, entry.name), rel)));
    } else if (entry.isFile()) {
      out.push(rel);
    }
  }
  return out;
}

/**
 * Publishes exactly `publishedPaths(registrySource)` from `docsDir` into
 * `dst`, replacing whatever `dst` held. This is the one function that
 * decides what ships -- `copy-handbook.mjs` is a thin wrapper over it with
 * real paths, and `app/tests/copy-handbook.test.ts` calls this directly
 * against a temporary destination, the same reason
 * `certificates-projection.mjs::writeProjection` is kept apart from
 * `copy-certificates.mjs`.
 *
 * A path named in the registry but missing on disk throws (from `cp`)
 * rather than being silently skipped: a broken link the visual-kit suite
 * itself checks for separately would otherwise fail the build only in
 * production, not here.
 */
export async function copyHandbook({ docsDir, registrySource, dst }) {
  const files = publishedPaths(registrySource);

  if (await pathExists(dst)) await rm(dst, { recursive: true });
  await mkdir(dst, { recursive: true });

  const counts = new Map();
  for (const rel of files) {
    const from = join(docsDir, rel);
    const to = join(dst, rel);
    await mkdir(dirname(to), { recursive: true });
    await cp(from, to);
    const ext = extname(rel).toLowerCase();
    counts.set(ext, (counts.get(ext) ?? 0) + 1);
  }
  return { files, counts };
}

async function pathExists(path) {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}
