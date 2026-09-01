import { describe, expect, it } from 'vitest';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { walkAll } from '../scripts/handbook-registry.mjs';

/**
 * The application's own hold on D-17 -- no request to a third party from a
 * published page. `site/`'s showcase already has one
 * (`tools/tests/repository/test_site.py::test_no_page_requests_a_third_party_font_host`),
 * scoped to `site/src/`; this is the application's, scoped to `app/`,
 * because the two are built and served separately and neither test can see
 * the other's tree. `app/src/design/tokens.css` once
 * `@import`-ed Archivo and JetBrains Mono from fonts.googleapis.com, and
 * `app/index.html` preconnected to fonts.googleapis.com and
 * fonts.gstatic.com and loaded a stylesheet from the former besides -- four
 * references sending every visitor's address to Google, on the exact pages
 * (signup, certificate verification, the survey) this project built a
 * consent apparatus to keep third parties away from.
 */

const APP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/** Strips CSS/JS block comments and HTML comments, in that order, so a
 *  comment that names the forbidden hosts by way of explaining why they
 *  are forbidden (this test file's own docstring above, `index.html`'s
 *  and `tokens.css`'s own explanatory comments) is not itself flagged as
 *  the violation -- the same discipline `test_site.py::_without_comments`
 *  applies on the showcase's side.
 *
 *  Deliberately does NOT also strip `//` line comments: a first version of
 *  this test did, and a real `https://fonts.googleapis.com/...` URL was
 *  silently truncated at its own `//`, hiding the exact violation the test
 *  exists to catch -- verified by planting one and watching this test stay
 *  green. Neither CSS nor HTML has `//` comments in the first place, and
 *  nothing under `app/src` currently needs one stripped from a `.ts`/`.tsx`
 *  file for this test to read correctly either. */
function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/<!--[\s\S]*?-->/g, '');
}

const FORBIDDEN_HOSTS = ['fonts.googleapis.com', 'fonts.gstatic.com'];

/** Every source text file the application actually ships or builds from:
 *  the HTML entry point, and every TypeScript/TSX/CSS file under `src/`.
 *  Not `public/` (build output some of it never commits, none of it
 *  hand-authored) and not `node_modules` (`walkAll` never descends into a
 *  directory this repository does not itself author). */
async function applicationTextFiles(): Promise<Array<{ path: string; text: string }>> {
  const indexHtml = resolve(APP_ROOT, 'index.html');
  const files = [{ path: indexHtml, text: await readFile(indexHtml, 'utf8') }];

  const srcDir = resolve(APP_ROOT, 'src');
  const relPaths = await walkAll(srcDir);
  const scanned = relPaths.filter(p => /\.(ts|tsx|css)$/.test(p));
  expect(scanned.length).toBeGreaterThan(0); // the glob itself may be wrong

  for (const rel of scanned) {
    const full = resolve(srcDir, rel);
    files.push({ path: full, text: await readFile(full, 'utf8') });
  }
  return files;
}

describe('no application source file requests a third-party font host', () => {
  it('never mentions fonts.googleapis.com or fonts.gstatic.com outside a comment', async () => {
    const offending: Array<[string, string]> = [];
    for (const { path, text } of await applicationTextFiles()) {
      const stripped = withoutComments(text);
      for (const host of FORBIDDEN_HOSTS) {
        if (stripped.includes(host)) offending.push([path, host]);
      }
    }
    expect(offending).toEqual([]);
  });
});

describe('the application declares its own self-hosted font faces', () => {
  it('tokens.css carries an @font-face block naming Archivo and JetBrains Mono', async () => {
    const tokensCss = await readFile(resolve(APP_ROOT, 'src', 'design', 'tokens.css'), 'utf8');
    expect(tokensCss).toContain('@font-face');
    expect(tokensCss).toContain('Archivo');
    expect(tokensCss).toContain('JetBrains Mono');
    expect(tokensCss).toContain("url('/fonts/");
  });

  it('index.html preloads a font from /fonts/', async () => {
    const indexHtml = await readFile(resolve(APP_ROOT, 'index.html'), 'utf8');
    expect(indexHtml).toContain('href="/fonts/');
  });
});
