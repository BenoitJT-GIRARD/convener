/* The README's own screenshots -- the three pages a visitor is shown
 * before they have installed anything, rendered from a real build on the
 * same pinned engine `render-and-compare.mjs` and `render-production.mjs`
 * already use.
 *
 * Its own file, beside those two, for the reason `render-production.mjs`'s
 * module comment gives for being one: each of the three renders a
 * different subject and answers to a different rule. That one renders
 * real edition data and compares nothing; `render-and-compare.mjs`
 * renders one fixed fictional fixture and compares it against a committed
 * reference; this one renders the *product*, assembled at the shape it is
 * actually published in, and writes the images `README.md` shows. Keeping
 * them apart is what lets anyone auditing one read the whole of it.
 *
 * Why a build and not a mock-up
 * =============================
 * A screenshot in a README is a claim about what the software does. The
 * only way to keep that claim true is to take it from the thing itself,
 * so this script refuses to run against anything but `app/dist` and
 * `site/_site`, and it assembles them into the exact tree
 * `deploy.yml` and `publish-vitrine.yml` push -- the showcase at the path
 * prefix `instance/config.json` declares, the cockpit one level under it
 * at `app/`. D-26's rule, applied to the pictures: a page served at a
 * bare local root looks right and is not the shape anybody visits.
 *
 * `serveStatic` and the MIME map are the same small dependency-free
 * server the two sibling scripts already carry, duplicated for the same
 * reason theirs are duplicates of each other: small enough that anyone
 * auditing this file on its own reads the whole thing.
 *
 * The three subjects, and what each is allowed to show
 * ===================================================
 * - **The cockpit**, at `?demo=1`. That is the product's own
 *   demonstration mode -- no account, no repository, the example instance
 *   under `instances/example/` compiled into the bundle. Nothing here
 *   invents data for it.
 * - **A public event page**, from `site/src/_data/events.json`, the build
 *   fixture that repository already commits. Invented people, invented
 *   talks; `publish-vitrine.yml` overwrites it from the real records in
 *   continuous integration and this script deliberately does not.
 * - **The verification page**, holding the one signed certificate this
 *   repository already commits -- `tools/tests/fixtures/certificate-
 *   verification.json`, a real RSA-3072 signature over an invented name,
 *   made with a private key that was never written to disk. The two
 *   files the page fetches to check it (`keys/signing/index.json` and
 *   `certificates.json`) are written into the *served copy only*, from
 *   that fixture, and never into `app/dist`: an instance that has issued
 *   nothing publishes an empty register, which is correct and shows a
 *   reader nothing. The screenshot is the page doing its actual work on
 *   this project's own test certificate, which is what it would do on a
 *   real one.
 *
 * D-25's trap, the same one `render-production.mjs` names: a run that
 * quietly wrote two of three images still leaves a non-empty directory.
 * `SHOTS` is what was promised and the count is checked against it.
 */

import { createServer } from 'node:http';
import { readFile, writeFile, mkdir, rm, cp } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');

const APP_DIST = path.join(ROOT, 'app', 'dist');
const SITE_DIST = path.join(ROOT, 'site', '_site');
const OUT = path.join(ROOT, 'screenshots');
const STAGE = path.join(HERE, 'readme-shots-stage');
const FIXTURE = path.join(ROOT, 'tools', 'tests', 'fixtures', 'certificate-verification.json');
const DECLARATION = path.join(ROOT, 'instance', 'config.json');
const CHARTER = path.join(ROOT, 'brand', 'convener', 'brand.json');
const BANNER = path.join(ROOT, 'brand', 'convener', 'convener-banner.svg');

/** The path prefix the published address declares, read from the one file
 *  that says it rather than typed here -- the same derivation
 *  `app/scripts/published.mjs` and `site/scripts/published.cjs` make for
 *  the builds this assembles. */
async function pathPrefix() {
  const declared = JSON.parse(await readFile(DECLARATION, 'utf8')).published_url;
  return new URL(declared).pathname;
}

/** What this run promises to write. A subject added here and not rendered
 *  fails the count at the end. */
const SHOTS = [
  {
    name: 'banner',
    url: null, // written into the served copy by `stageTheBanner`
    width: 1280,
    height: 320,
    ready: 'svg',
  },
  {
    name: 'cockpit',
    // The demonstration mode README points a visitor at, so the picture
    // and the link show the same thing.
    url: 'app/?demo=1',
    width: 1440,
    height: 1010,
    // The board's own inbox has rendered once the demonstration's speakers
    // are on screen; `networkidle0` alone only says the bundle arrived.
    ready: 'main',
  },
  {
    name: 'event-page',
    // The one edition the committed fixture leaves `scheduled`, so the
    // page carries its abstract and its registration form rather than an
    // archive entry.
    url: 'events/mrg-05/',
    width: 1200,
    height: 1150,
    ready: 'main',
  },
  {
    name: 'verification',
    url: null, // built below from the fixture's own verification path
    width: 1200,
    height: 1150,
    ready: '.verify',
  },
];

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.xml': 'application/xml; charset=utf-8',
  '.ics': 'text/calendar; charset=utf-8',
};

/** See the module comment for why this is a third copy rather than an
 *  import of either sibling's. */
function serveStatic(root) {
  return new Promise((resolve) => {
    const server = createServer(async (req, res) => {
      try {
        const decoded = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        let filePath = path.join(root, decoded);
        if (!filePath.startsWith(root)) {
          res.writeHead(403);
          res.end('outside the served root');
          return;
        }
        if (decoded.endsWith('/')) filePath = path.join(filePath, 'index.html');
        if (!existsSync(filePath)) {
          res.writeHead(404);
          res.end('not found');
          return;
        }
        const body = await readFile(filePath);
        res.writeHead(200, {
          'content-type': MIME[path.extname(filePath)] || 'application/octet-stream',
        });
        res.end(body);
      } catch (err) {
        res.writeHead(500);
        res.end(String(err));
      }
    });
    // Port 0: the operating system hands back one nothing is holding. A
    // port chosen by hand is a port some earlier run may still be bound
    // to, and a still-bound port serves the *old* build to a screenshot
    // that then claims to be the new one.
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

/** The published tree, assembled: the showcase at the declared prefix,
 *  the cockpit one level under it, exactly as the two publishing
 *  workflows push them into the same repository root. */
async function assemble(prefix) {
  for (const [name, dir] of [
    ['app', APP_DIST],
    ['site', SITE_DIST],
  ]) {
    if (!existsSync(dir)) {
      throw new Error(
        `${dir} is not there -- build it first (\`cd ${name} && npm run build\`); ` +
          'this script renders a real build and refuses to invent one'
      );
    }
  }
  await rm(STAGE, { recursive: true, force: true });
  const served = path.join(STAGE, ...prefix.split('/').filter(Boolean));
  await mkdir(served, { recursive: true });
  await cp(SITE_DIST, served, { recursive: true });
  await cp(APP_DIST, path.join(served, 'app'), { recursive: true });
  return served;
}

/** The two files the verification page fetches, written into the served
 *  copy from the committed fixture. See the module comment for why this
 *  is here and never in `app/dist`. */
async function stageTheTestCertificate(served) {
  const fixture = JSON.parse(await readFile(FIXTURE, 'utf8'));
  const example = fixture.signed_example;
  await mkdir(path.join(served, 'app', 'keys', 'signing'), { recursive: true });
  await writeFile(
    path.join(served, 'app', 'keys', 'signing', 'index.json'),
    JSON.stringify([example.public_pem]),
    'utf8'
  );
  await writeFile(
    path.join(served, 'app', 'certificates.json'),
    JSON.stringify([{ identifier: example.identifier, state: fixture.states.issued }]),
    'utf8'
  );
  return example.verification_url_path;
}

/**
 * The README's banner, as a page holding the charter's own banner file on
 * the charter's own ground.
 *
 * A raster rather than the `.svg` itself, and the reason is the one
 * surface the charter cannot follow. Its ink is `currentColor` and its
 * `svg:root { color }` rule fixes that to the dark ink whenever the file
 * *is* the document -- which is what a Markdown image is. GitHub renders
 * a README on a near-black ground for half its readers, and the dark ink
 * on that ground is a shape nobody can see. So the file is **inlined**
 * here instead, which is the case the charter designed the ink for: it
 * inherits, and this page sets `color` to the charter's own white over
 * the charter's own dark ground -- the pair `brand.json` itself measures
 * at 14.19. Both values are read from `brand.json`, never typed here.
 *
 * The banner PNG is therefore a *rendering* of the one banner file, in
 * the way `brand/convener/README.md`'s own "How the colour works"
 * section describes, refreshed by the same command as everything else in
 * `screenshots/`. It is not a second banner to keep in step.
 */
async function stageTheBanner(served) {
  const charter = JSON.parse(await readFile(CHARTER, 'utf8')).colour;
  const file = await readFile(BANNER, 'utf8');
  // From `<svg` on: the file opens with its own long comment, which is
  // documentation for whoever edits it and is not part of the mark.
  const svg = file.slice(file.indexOf('<svg'));
  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Convener</title>
<style>
  html, body { margin: 0; height: 100%; }
  body {
    background: ${charter.purple};
    color: ${charter.white};
    display: flex; align-items: center; justify-content: center;
  }
  svg { width: 62%; height: auto; }
</style></head><body>${svg}</body></html>
`;
  await writeFile(path.join(served, 'banner.html'), html, 'utf8');
  return 'banner.html';
}

async function main() {
  const prefix = await pathPrefix();
  const served = await assemble(prefix);
  const verificationPath = await stageTheTestCertificate(served);
  const bannerPath = await stageTheBanner(served);
  for (const shot of SHOTS) {
    if (shot.name === 'verification') shot.url = verificationPath;
    if (shot.name === 'banner') shot.url = bannerPath;
  }

  await mkdir(OUT, { recursive: true });
  const server = await serveStatic(STAGE);
  const { port } = server.address();
  const base = `http://127.0.0.1:${port}${prefix}`;

  let browser;
  let written = 0;
  try {
    browser = await puppeteer.launch({ headless: true });
    for (const shot of SHOTS) {
      const page = await browser.newPage();
      try {
        await page.setViewport({
          width: shot.width,
          height: shot.height,
          deviceScaleFactor: 2,
        });
        await page.goto(`${base}${shot.url}`, {
          waitUntil: 'networkidle0',
          timeout: 30_000,
        });
        await page.waitForSelector(shot.ready, { timeout: 30_000 });
        await page.evaluate(() => document.fonts.ready);
        const png = await page.screenshot({ type: 'png' });
        await writeFile(path.join(OUT, `${shot.name}.png`), png);
        written += 1;
        console.log(`shots: wrote screenshots/${shot.name}.png`);
      } finally {
        await page.close();
      }
    }
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
    await rm(STAGE, { recursive: true, force: true });
  }

  if (written !== SHOTS.length) {
    console.log(
      `::error::expected ${SHOTS.length} screenshot(s), actually wrote ${written} ` +
        '-- refusing to report success'
    );
    process.exitCode = 1;
    return;
  }
  console.log(`shots: wrote ${written} screenshot(s) into screenshots/`);
}

await main();
