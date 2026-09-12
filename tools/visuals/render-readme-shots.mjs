/* The README's own screenshots -- the mark at the top of it and the
 * three pages a visitor is shown before they have installed anything,
 * rendered from a real build on the same pinned engine
 * `render-and-compare.mjs` and `render-production.mjs` already use.
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
 * `deploy.yml` and `publish-showcase.yml` push -- the showcase at the path
 * prefix `instance/config.json` declares, the cockpit one level under it
 * at `app/`. D-26's rule, applied to the pictures: a page served at a
 * bare local root looks right and is not the shape anybody visits.
 *
 * Whose build, and why this refuses to be told
 * ============================================
 * The example collective's, always. A masthead is compiled rather than
 * fetched -- `app/vite.config.ts` carries `identity` into the bundle
 * through Vite's own `define`, `site/.eleventy.js` composes the same
 * values into every showcase page -- so a picture taken here would be a
 * picture of whichever series happens to run this repository, in every
 * file `assets/screenshots/` hands to a public repository exactly as
 * committed. Nothing downstream could catch it: no check here reads a
 * raster, and `tools/tests/repository/test_second_instance.py`'s sweep
 * skips a `.png` and says why. `docs/assets/zoom-background.png` was
 * deleted for exactly that once.
 *
 * So `refuseUnlessTheExampleDeclares` is a refusal rather than a
 * convention: this script stops unless every value the declaration it can
 * see carries about *who is publishing* is still the one
 * `examples/the-example-collective/instance/config.json` ships -- the same value-by-value
 * comparison `published.unconfigured` makes on the Python side, and for
 * the reason its docstring gives (a half-configured duplicate is the
 * dangerous state, so file-against-file would be the wrong test). If the
 * only repository it can run in is one nobody's identity reaches, the
 * images can only ever show the example.
 *
 * `tools/scripts/render_readme_shots.py` is what provides such a
 * repository: it lays `examples/the-example-collective/` into a scratch copy of this
 * one, builds it, runs *that tree's own copy of this file*, and brings the
 * pictures back. Run this script here instead and it refuses, naming
 * every value it finds configured. That is the same answer
 * `convener-render-visual-fixtures` already gives for the reference
 * renders in `references/`: render as the example, and there is nothing
 * in the file to leak.
 *
 * `serveStatic` and the MIME map are the same small dependency-free
 * server the two sibling scripts already carry, duplicated for the same
 * reason theirs are duplicates of each other: small enough that anyone
 * auditing this file on its own reads the whole thing.
 *
 * The subjects, and what each is allowed to show
 * ==============================================
 * Three groups, because `README.md` shows them as three: what a visitor
 * sees, what the team sees, and what a duplicate chooses.
 *
 * - **The banner**, the charter's own mark on the charter's own ground.
 *   Product-owned on both sides, and `stageTheBanner` below gives the
 *   whole of why it is a raster at all.
 * - **The showcase**, the front page a series publishes about itself, at
 *   the path prefix its own declaration names.
 * - **A public event page**, from `site/src/_data/events.json`, which the
 *   build this runs against has already refreshed from the example
 *   instance's own public projection the way `publish-showcase.yml`
 *   refreshes it from the real records. The edition is the one that file
 *   leaves `scheduled`, read from it rather than named here: an edition
 *   code carries the declared prefix, so a code written into this file
 *   would be one instance's value inside the product's own renderer.
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
 * - **Three screens of the cockpit**, all at `?demo=1`. That is the
 *   product's own demonstration mode -- no account, no repository, the
 *   example instance under `examples/the-example-collective/` compiled
 *   into the bundle. Nothing here invents data for any of them. The inbox
 *   is what is waiting, the pipeline is where every live record stands,
 *   and the diversity screen is what the programme adds up to.
 * - **One poster per charter**, and the same poster four times. What is
 *   being shown is that the palette is chosen, so four different subjects
 *   would mix two messages and carry neither. These are the only shots
 *   this script does not render itself: `visual.render_announcement` is
 *   Python and composes the page, `tools/scripts/render_readme_shots.py`
 *   writes one per charter into a directory named by `--charters`, and
 *   this screenshots them. That is D-14's own shape, the same seam
 *   `render-and-compare.mjs` reads its own fixtures across -- the
 *   *fixture* is the boundary, never the code that produces a page.
 *
 * The day they are all photographed on
 * ====================================
 * One day, fixed, and it is the day the certificate above was earned.
 *
 * The cockpit's three screens are the ones that read a clock:
 * `app/src/state/sla.ts::lateness` counts calendar days between a step's
 * deadline and today, and the inbox prints the count -- "Forum summary is
 * 277 days overdue". That number goes up by one every night, so the
 * committed raster changes overnight for a reason that has nothing to do
 * with the software, and nobody can refresh one of these pictures
 * without a diff appearing on the cockpit as well. Measured both ways
 * before this was written: with the clock free, two runs on the same day
 * leave every file byte-identical; with the clock fixed, moving it by a
 * single day changes `cockpit.png` and leaves the rest byte-identical.
 *
 * So each page is handed a fixed `Date` before anything in it runs, and
 * the instant comes off `FIXTURE`'s own payload -- the day the one signed
 * certificate this repository commits says its holder attended. Read off a
 * committed fixture rather than written out here, for the reason
 * `visual.FIXTURE_ANNOUNCEMENT` is a fixture rather than a date somebody
 * retypes; and that day rather than another because the verification shot
 * already prints it on screen, so the pictures are one moment in the
 * example instance's life instead of one moment each.
 *
 * Midnight *UTC* on that day, because Europe/Paris is never behind UTC:
 * 00:00Z is the same calendar day in Paris at either offset, and the Paris
 * day is what the app computes (`app/src/state/derived.ts::parisToday`).
 * The browser's own zone is left as it is, having been measured and found
 * not to matter -- with the instant fixed, a run under `TZ=UTC` and a run
 * under Europe/Paris produce byte-identical files, because every day
 * this app computes it computes through `Intl` with `Europe/Paris` named
 * outright.
 *
 * Every one of the three pages carries the product's own **not
 * configured** band, and that is the build being honest rather than a
 * defect in the picture: the declaration these are rendered from *is*
 * still the example's, which is the condition `published.unconfigured`
 * warns on and the whole reason these pictures can be published at all.
 * The three heights below leave room for it, so each shot still frames
 * what `README.md`'s own caption for it promises.
 *
 * D-25's trap, the same one `render-production.mjs` names: a run that
 * quietly wrote six of seven images still leaves a non-empty directory.
 * `SHOTS` is what was promised and the count is checked against it.
 */

import { createServer } from 'node:http';
import { readFile, writeFile, mkdir, rm, cp } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
// `browser.mjs` states the one launch argument this repository ever
// passes, and why. Imported at the top even though `puppeteer` below is
// not: this module has no dependencies of its own, so it costs nothing
// on a machine that never installed the renderer.
import { launch as launchBrowser } from './browser.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');

const APP_DIST = path.join(ROOT, 'app', 'dist');
const SITE_DIST = path.join(ROOT, 'site', '_site');
const OUT = path.join(ROOT, 'assets', 'screenshots');
const STAGE = path.join(HERE, 'readme-shots-stage');
const FIXTURE = path.join(ROOT, 'tools', 'tests', 'fixtures', 'certificate-verification.json');
const DECLARATION = path.join(ROOT, 'instance', 'config.json');
const EXAMPLE = path.join(ROOT, 'examples', 'the-example-collective', 'instance', 'config.json');
const EVENTS = path.join(ROOT, 'site', 'src', '_data', 'events.json');
const CHARTER = path.join(ROOT, 'assets', 'brand', 'convener', 'brand.json');
const BANNER = path.join(ROOT, 'assets', 'brand', 'convener', 'convener-banner.svg');

/** Every value a declaration carries about *who* is publishing, under the
 *  name the declaration itself gives it -- the address, the edition
 *  prefix, and the fields of `identity`. The Node half of
 *  `published.declared_values`, read raw for the reason that function
 *  gives: the question is whether somebody has typed their own value
 *  here, which is a question about text. */
function declaredValues(data) {
  const values = new Map();
  for (const key of ['published_url', 'edition_prefix']) {
    if (typeof data?.[key] === 'string' && data[key]) values.set(key, data[key]);
  }
  if (data?.identity && typeof data.identity === 'object') {
    for (const [field, value] of Object.entries(data.identity)) {
      if (typeof value === 'string' && value) values.set(`identity.${field}`, value);
    }
  }
  return values;
}

/** The refusal the module comment argues for. Every declared value must
 *  still be the example's; the ones that are not are named, because a
 *  reader who is told "configured" and not *what* is configured goes
 *  looking through a file rather than at a line. */
async function refuseUnlessTheExampleDeclares() {
  const [declared, example] = await Promise.all(
    [DECLARATION, EXAMPLE].map(async (file) =>
      declaredValues(JSON.parse(await readFile(file, 'utf8')))
    )
  );
  const configured = [...declared].filter(([name, value]) => example.get(name) !== value);
  if (configured.length > 0) {
    const named = configured
      .map(([name, value]) => `  ${name}: ${JSON.stringify(value)}`)
      .join('\n');
    throw new Error(
      'this repository is configured, so no picture may be taken in it. ' +
        'instance/config.json declares its own value for:\n' +
        `${named}\n` +
        'A capture made here would carry that identity into every copy of ' +
        'assets/screenshots/, and nothing downstream can read a raster back out ' +
        'again. Run `tools/scripts/render_readme_shots.py`, which builds ' +
        'this repository as the instance examples/the-example-collective/ declares and ' +
        'runs this script inside that build.'
    );
  }
}

/** The path prefix the published address declares, read from the one file
 *  that says it rather than typed here -- the same derivation
 *  `app/scripts/published.mjs` and `site/scripts/published.cjs` make for
 *  the builds this assembles. */
async function pathPrefix() {
  const declared = JSON.parse(await readFile(DECLARATION, 'utf8')).published_url;
  return new URL(declared).pathname;
}

/** What this run promises to write. A subject added here and not rendered
 *  fails the count at the end.
 *
 *  **The six pages share one frame, and that is what the frame is for.**
 *  `README.md` lays them out as two rows of three thumbnails, each one
 *  scaled to the same width, so a page rendered 1440 wide and a page
 *  rendered 1200 wide would arrive at the same column and the wider one's
 *  type would land smaller. One width makes one scale factor serve all
 *  six, so the size a word is set at in the application is the size it is
 *  read at on the page -- and one *height* as well, now that they stand
 *  beside each other: six thumbnails of six shapes is a row that reads as
 *  a mistake before it reads as anything else.
 *
 *  Equal width rather than an equal scale factor, because the cockpit's
 *  layout holds at 1200 -- measured, not assumed: it lays out 1200 CSS
 *  pixels wide with nothing overflowing, and its own document is 1319
 *  pixels tall at 1200 exactly as it is at 1440, so nothing reflowed and
 *  nothing was squeezed. `laidOut` below is that measurement made on
 *  every run rather than once: a page that stops fitting its frame is a
 *  layout question, and this refuses rather than photographing the crop.
 *
 *  **`deviceScaleFactor` is 1, and used to be 2.** At two it wrote four
 *  times the pixels of a picture `README.md` now shows 260 CSS pixels
 *  wide -- 1200 source pixels is already better than four times what any
 *  display asks of that column -- and this repository carries every one
 *  of them for ever. Measured rather than assumed: the three pages this
 *  set started with weighed 279k, 364k and 285k at two.
 *
 *  The banner is not one of the six. It is a rendering of one SVG on a
 *  ground, at the proportion the mark is drawn to, and it shares no type
 *  with anything; the four charter posters are not either, and
 *  `CHARTER_FRAME` below says what frames them. */
const PAGE_FRAME = { width: 1200, height: 1340 };

/** What one charter's poster is photographed at. Square, because
 *  `formats.SQUARE` is the canvas the composition was built for and
 *  reviewed at, and small: `README.md` shows four of these in one row, the
 *  subject is the colour rather than the layout, and a 1200-pixel poster
 *  four times over would weigh more than every other picture in this
 *  repository put together. */
const CHARTER_FRAME = { width: 640, height: 640 };

const SHOTS = [
  {
    name: 'banner',
    url: null, // written into the served copy by `stageTheBanner`
    width: 1280,
    height: 320,
    ready: 'svg',
  },
  {
    name: 'showcase',
    // The front page, at the prefix the declaration names -- `base`
    // already carries it, so the empty string is the index of the
    // published tree rather than of a bare root (D-26).
    url: '',
    ...PAGE_FRAME,
    ready: 'main',
  },
  {
    name: 'event-page',
    // The one edition the build's own data leaves `scheduled`, so the
    // page carries its abstract and its registration form rather than an
    // archive entry; read below by `scheduledEvent`.
    url: null,
    ...PAGE_FRAME,
    ready: 'main',
  },
  {
    name: 'verification',
    url: null, // built below from the fixture's own verification path
    ...PAGE_FRAME,
    ready: '.verify',
  },
  {
    name: 'cockpit',
    // The demonstration mode README points a visitor at, so the picture
    // and the link show the same thing. The inbox is what it opens on.
    url: 'app/?demo=1',
    ...PAGE_FRAME,
    // The board's own inbox has rendered once the demonstration's speakers
    // are on screen; `networkidle0` alone only says the bundle arrived.
    ready: 'main',
  },
  {
    name: 'pipeline',
    // The working board, one column per status that still asks for work.
    // The route is the cockpit's own (`app/src/App.tsx`), reached through
    // the hash so that no server has to know it.
    url: 'app/?demo=1#/pipeline',
    ...PAGE_FRAME,
    ready: 'main',
  },
  {
    name: 'diversity',
    // What the programme adds up to, applicants beside those selected.
    url: 'app/?demo=1#/diversity',
    ...PAGE_FRAME,
    ready: 'main',
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
  return {
    path: example.verification_url_path,
    // The day the module comment fixes every picture to, taken from
    // the payload the verification shot itself prints on screen.
    photographedAt: `${example.payload_decoded.date}T00:00:00Z`,
  };
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
 * the way `assets/brand/convener/README.md`'s own "How the colour works"
 * section describes, refreshed by the same command as everything else in
 * `assets/screenshots/`. It is not a second banner to keep in step.
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
    background: ${charter.dominant};
    color: ${charter.white};
    display: flex; align-items: center; justify-content: center;
  }
  svg { width: 62%; height: auto; }
</style></head><body>${svg}</body></html>
`;
  await writeFile(path.join(served, 'banner.html'), html, 'utf8');
  return 'banner.html';
}

/** The address of the one edition this build leaves `scheduled`, in the
 *  form `event.njk`'s own permalink gives it (`/events/<id>/`, lowered).
 *  Refuses rather than picking one when there is not exactly one: a
 *  README showing an archive entry where it promises a registration form
 *  is a false claim, and so is one that silently chose between two. */
async function scheduledEvent() {
  const events = JSON.parse(await readFile(EVENTS, 'utf8'));
  const scheduled = events.filter((event) => event.status === 'scheduled');
  if (scheduled.length !== 1) {
    throw new Error(
      `site/src/_data/events.json leaves ${scheduled.length} editions scheduled, ` +
        'and this picture is of an event page before its event -- there is no ' +
        'second-best page to photograph instead'
    );
  }
  return `events/${scheduled[0].id.toLowerCase()}/`;
}

/** The fixed clock, installed in a page before anything in it runs.
 *
 *  `evaluateOnNewDocument` rather than `page.evaluate`: the bundle reads
 *  the clock while it renders, so an override applied after navigation
 *  would arrive after the number it was meant to fix had been printed.
 *  The page's own `Date` global is replaced, in the page and for the life
 *  of that one tab. Every constructor form but the empty one is passed
 *  through -- a page that parses its own data's dates has to keep getting
 *  them back -- so what is fixed is `new Date()` and `Date.now()`, which
 *  is the whole of how this app asks what day it is
 *  (`app/src/state/derived.ts::parisToday`). */
async function fixTheClock(page, iso) {
  await page.evaluateOnNewDocument((instant) => {
    const fixed = new Date(instant).getTime();
    const Real = Date;
    Date = class extends Real {
      constructor(...args) {
        if (args.length === 0) super(fixed);
        else super(...args);
      }

      static now() {
        return fixed;
      }
    };
  }, iso);
}

/** The four charter posters, as shots, from the directory Python wrote
 *  them into. Copied under the served prefix rather than read off disk by
 *  the browser: a page opened from the filesystem is an opaque origin and
 *  Chrome refuses its own `@font-face` request there, which would
 *  photograph four posters set in the system stack -- a picture of the
 *  typography lying, which is the one thing a design shot must not do.
 *
 *  Absent when `--charters` is not passed, and that is not a silent skip:
 *  the count at the end is taken against what this function returned, so a
 *  run without it writes seven pictures and says seven. */
async function stageTheCharters(served, from) {
  if (!from) return [];
  const manifest = JSON.parse(await readFile(path.join(from, 'manifest.json'), 'utf8'));
  const into = path.join(served, 'charters');
  await cp(from, into, { recursive: true });
  return manifest.map((entry) => ({
    name: `charter-${entry.charter}`,
    url: `charters/${entry.file}`,
    ...CHARTER_FRAME,
    // The composition's own outermost element. `main` is the showcase's
    // and the cockpit's; a poster is one page and has neither.
    ready: '.poster',
  }));
}

/** The value of a `--name value` argument, or `null`. Two arguments and no
 *  parser: `render-and-compare.mjs` beside this file reads its own two the
 *  same way, and a dependency to read two flags would be a dependency the
 *  one job that renders has to install. */
function argument(name) {
  const at = process.argv.indexOf(`--${name}`);
  return at === -1 ? null : process.argv[at + 1];
}

async function main() {
  await refuseUnlessTheExampleDeclares();
  const prefix = await pathPrefix();
  const served = await assemble(prefix);
  const certificate = await stageTheTestCertificate(served);
  const bannerPath = await stageTheBanner(served);
  const eventPath = await scheduledEvent();
  const charters = await stageTheCharters(served, argument('charters'));
  const shots = [...SHOTS, ...charters];
  for (const shot of shots) {
    if (shot.name === 'verification') shot.url = certificate.path;
    if (shot.name === 'banner') shot.url = bannerPath;
    if (shot.name === 'event-page') shot.url = eventPath;
  }

  await mkdir(OUT, { recursive: true });
  const server = await serveStatic(STAGE);
  const { port } = server.address();
  const base = `http://127.0.0.1:${port}${prefix}`;

  let browser;
  let written = 0;
  try {
    // Imported here rather than at the top of the file, so that the
    // refusal above runs on a machine that has never installed this
    // package. A top-level import fails first, with a resolver error
    // about puppeteer, which tells a reader nothing about the thing this
    // script actually stopped for -- and it would put the one heavy
    // dependency in the way of the one check that costs nothing.
    const { default: puppeteer } = await import('puppeteer');
    browser = await launchBrowser(puppeteer);
    for (const shot of shots) {
      const page = await browser.newPage();
      try {
        await page.setViewport({
          width: shot.width,
          height: shot.height,
          // One device pixel per CSS pixel -- see the SHOTS table for the
          // measurement that says two was four times what the page needs.
          deviceScaleFactor: 1,
        });
        await fixTheClock(page, certificate.photographedAt);
        await page.goto(`${base}${shot.url}`, {
          waitUntil: 'networkidle0',
          timeout: 30_000,
        });
        await page.waitForSelector(shot.ready, { timeout: 30_000 });
        await page.evaluate(() => document.fonts.ready);
        const laidOut = await page.evaluate(
          () => document.documentElement.scrollWidth
        );
        if (laidOut > shot.width) {
          throw new Error(
            `${shot.name} lays out ${laidOut} CSS pixels wide in a ${shot.width}` +
              ' frame, so this picture is of a page cut down its right-hand ' +
              'side. The three application pages are framed at one width so ' +
              'that README.md scales all three by the same factor; a page ' +
              'that stops fitting the frame it is taken in is a layout ' +
              'question and never a crop to accept quietly.'
          );
        }
        const png = await page.screenshot({ type: 'png' });
        await writeFile(path.join(OUT, `${shot.name}.png`), png);
        written += 1;
        console.log(`shots: wrote assets/screenshots/${shot.name}.png`);
      } finally {
        await page.close();
      }
    }
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
    await rm(STAGE, { recursive: true, force: true });
  }

  if (written !== shots.length) {
    console.log(
      `::error::expected ${shots.length} screenshot(s), actually wrote ${written} ` +
        '-- refusing to report success'
    );
    process.exitCode = 1;
    return;
  }
  console.log(
    `shots: wrote ${written} screenshot(s) into assets/screenshots/, ` +
      `photographed at ${certificate.photographedAt}`
  );
}

await main();
