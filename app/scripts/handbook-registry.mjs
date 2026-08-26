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
 * That leaves a narrower, real gap: whatever these two functions capture
 * from that text must actually be the object and array literals
 * `registry.ts` declares, not any string that merely appears somewhere in
 * the file. The first version of this file did not make
 * that distinction -- `/\bfile:\s*'([^']+)'/g` ran over the *entire* source,
 * so an ordinary explanatory comment mentioning `file: 'reference/operations.md'`
 * anywhere in `registry.ts` -- even one written to warn against exactly
 * that path -- would have been read back out as a published file, silently
 * reopening the leak this task exists to close. `extractDeclaration` below
 * locates each export's own literal by its opening and closing delimiter
 * (`{`…`};` for `CONTENT_REGISTRY`, `[`…`];` for `PUBLIC_ASSETS`) and
 * `stripComments` removes `//` and `/* *\/` comments from *that slice only*,
 * string literals left untouched -- so a comment inside the literal cannot
 * contribute a path either. Both are still text-based, not a real
 * TypeScript parse: `app/tests/copy-handbook.test.ts` pins the result
 * against the real `CONTENT_REGISTRY` and `PUBLIC_ASSETS`, imported
 * natively by the test runner, on every run, and separately proves a decoy
 * comment inside either literal is ignored. A drift here fails that test;
 * it does not ship silently.
 */
import { cp, mkdir, readdir, rm, stat } from 'node:fs/promises';
import { dirname, extname, join } from 'node:path';

/** Removes `//line` and `/* block *\/` comments from `text`, leaving
 *  single-quoted string contents untouched (so a string that happened to
 *  contain `//` would survive intact -- none of `registry.ts`'s file paths
 *  do, but this does not rely on that). Not a general JS/TS tokeniser: it
 *  only has to be correct for the narrow slice of source it is given here,
 *  a flat object or array literal of string properties. */
export function stripComments(text) {
  let out = '';
  for (let i = 0; i < text.length; ) {
    const two = text.slice(i, i + 2);
    if (two === '//') {
      const nl = text.indexOf('\n', i);
      i = nl === -1 ? text.length : nl;
    } else if (two === '/*') {
      const end = text.indexOf('*/', i + 2);
      i = end === -1 ? text.length : end + 2;
    } else if (text[i] === "'") {
      let j = i + 1;
      while (j < text.length && text[j] !== "'") {
        if (text[j] === '\\') j++;
        j++;
      }
      out += text.slice(i, j + 1);
      i = j + 1;
    } else {
      out += text[i];
      i++;
    }
  }
  return out;
}

/** The text strictly between `startMarker`'s first occurrence and the next
 *  occurrence of `endMarker` after it -- `''` if either is missing. Used to
 *  isolate one export's own literal, so a decoy string elsewhere in the
 *  file (in a different export, or in a comment above or below this one)
 *  is never even looked at, let alone matched. */
function extractDeclaration(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  if (start === -1) return '';
  const end = source.indexOf(endMarker, start + startMarker.length);
  if (end === -1) return '';
  return source.slice(start + startMarker.length, end);
}

/** Every `file: '...'` value inside `CONTENT_REGISTRY`'s own object literal
 *  -- one per entry, several entries sharing a file (a page and the
 *  fragments transcluded from it) collapsed to one. Comments inside the
 *  literal, and anything outside it, are never considered. */
export function parseContentFiles(source) {
  const block = stripComments(
    extractDeclaration(source, 'export const CONTENT_REGISTRY', '\n};'),
  );
  const files = new Set();
  for (const m of block.matchAll(/\bfile:\s*'([^']+)'/g)) files.add(m[1]);
  return [...files].sort();
}

/** The string literals inside `PUBLIC_ASSETS`'s own array literal. Returns
 *  `[]` if the export is missing or empty -- a normal state for a caller
 *  probing a hand-built fixture in a test, never for the real
 *  `registry.ts`, which `copy-handbook.test.ts` checks always defines it. */
export function parsePublicAssets(source) {
  const block = stripComments(
    extractDeclaration(source, 'export const PUBLIC_ASSETS', '\n];'),
  );
  const files = new Set();
  for (const m of block.matchAll(/'([^']+)'/g)) files.add(m[1]);
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
