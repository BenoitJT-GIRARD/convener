/* The production render step -- screenshots each real,
 * scheduled edition `convener-render-visuals` (Python, `tools/convener_ops/cli.py`)
 * already wrote as a self-contained HTML page, on the identical pinned
 * engine `render-and-compare.mjs` uses for its regression
 * check.
 *
 * Deliberately its own file, not a mode flag on `render-and-compare.mjs`:
 * that script's whole job is comparing one fixed, fictional fixture
 * against a versioned reference, and its own module comment is explicit
 * that the regression check must never depend on real edition data. This
 * script does the opposite -- it renders *only* real data and never
 * compares anything against a reference -- and keeping the two apart in
 * separate files is what keeps that promise checkable by reading either
 * one in isolation, rather than by trusting a `--production` flag was
 * threaded through every branch correctly.
 *
 * `serveStatic` and the MIME map below are the same small,
 * dependency-free static file server `render-and-compare.mjs` already
 * defines, for the identical reason (a relative `@font-face url(...)`
 * cannot load from a bare `file://` origin without a flag this project
 * has no reason to carry). Duplicated rather than shared: the same call
 * this project already made for `site/scripts/check-a11y.mjs`'s own copy
 * of the identical ~25 lines -- small enough that anyone auditing either
 * file on its own reads the whole thing, which costs less than a
 * cross-file import would save.
 *
 * D-25's own trap, applied here: a run that silently wrote fewer images
 * than `manifest.json` promised would still leave `--out` non-empty, so
 * the workflow's own `actions/upload-artifact` `if-no-files-found: error`
 * cannot catch it -- that guard only ever sees "some files" or "no
 * files", never "fewer than expected". This script counts what it
 * actually wrote against what the manifest said to expect, and refuses to
 * report success on a mismatch.
 */

import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer';

function parseArgs(argv) {
  const args = { fixtures: undefined, out: undefined };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--fixtures') args.fixtures = argv[++i];
    else if (arg === '--out') args.out = argv[++i];
    else throw new Error(`unrecognised argument: ${arg}`);
  }
  if (!args.fixtures) {
    throw new Error(
      '--fixtures DIR is required -- the directory convener-render-visuals wrote ' +
        '(manifest.json, one *.html per edition/format, a copy of fonts/)'
    );
  }
  if (!args.out) {
    throw new Error('--out DIR is required -- where the rendered PNGs are written');
  }
  args.fixtures = path.resolve(args.fixtures);
  args.out = path.resolve(args.out);
  return args;
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.woff2': 'font/woff2',
};

/** See the module comment for why this is a duplicate of
 *  `render-and-compare.mjs`'s own `serveStatic`, not an import of it. */
function serveStatic(root) {
  return new Promise((resolve) => {
    const server = createServer(async (req, res) => {
      try {
        const decodedPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        const filePath = path.join(root, decodedPath);
        if (!filePath.startsWith(root) || !existsSync(filePath)) {
          res.writeHead(404);
          res.end('not found');
          return;
        }
        const body = await readFile(filePath);
        const contentType = MIME[path.extname(filePath)] || 'application/octet-stream';
        res.writeHead(200, { 'content-type': contentType });
        res.end(body);
      } catch (err) {
        res.writeHead(500);
        res.end(String(err));
      }
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const manifestPath = path.join(args.fixtures, 'manifest.json');
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  if (!Array.isArray(manifest)) {
    throw new Error(`${manifestPath} is not a JSON array`);
  }
  if (manifest.length === 0) {
    // D-13: no scheduled edition is a normal state -- convener-render-visuals
    // already said so on its own stdout; this script only has to agree,
    // not treat an empty manifest as its own separate failure.
    console.log('visuals: manifest.json lists no edition -- nothing to render');
    return;
  }

  await mkdir(args.out, { recursive: true });

  const server = await serveStatic(args.fixtures);
  const { port } = server.address();
  const baseUrl = `http://127.0.0.1:${port}/`;

  let browser;
  let written = 0;
  try {
    browser = await puppeteer.launch({ headless: true });
    for (const entry of manifest) {
      const page = await browser.newPage();
      try {
        await page.setViewport({ width: entry.width, height: entry.height });
        await page.goto(`${baseUrl}${entry.file}`, { waitUntil: 'networkidle0', timeout: 30_000 });
        await page.evaluate(() => document.fonts.ready);
        const png = await page.screenshot({ type: 'png' });
        const eventDir = path.join(args.out, entry.event_id);
        await mkdir(eventDir, { recursive: true });
        await writeFile(path.join(eventDir, `${entry.name}.png`), png);
        written += 1;
        console.log(`visuals: wrote ${entry.event_id}/${entry.name}.png`);
      } finally {
        await page.close();
      }
    }
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  // The file-count guard the module comment names: if-no-files-found on
  // the workflow's own upload step cannot see a *partial* write, only an
  // empty one.
  if (written !== manifest.length) {
    console.log(
      `::error::expected ${manifest.length} rendered image(s), actually wrote ${written} ` +
        '-- refusing to report success'
    );
    process.exitCode = 1;
    return;
  }

  const editionCount = new Set(manifest.map((entry) => entry.event_id)).size;
  console.log(`visuals: wrote ${written} production visual(s) for ${editionCount} edition(s)`);
}

await main();
