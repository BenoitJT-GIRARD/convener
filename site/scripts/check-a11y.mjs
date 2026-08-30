/* The automatic half of "AA accessibility, verified".
 * Runs axe-core (Deque's rule engine, MIT-licensed, no
 * account, no third-party call at run time) against every page the
 * showcase actually generates, rendered in a real, JavaScript-executing
 * browser -- not a static-HTML sweep, which would report the three
 * islands (the registration form, the certificate-verification panel,
 * the post-event survey) as empty `<div>`s and pass
 * for the wrong reason (D-25: "a control that cannot fail loudly is not a
 * control").
 *
 * Zero cost, by construction
 * ---------------------------
 * `puppeteer-core` (not `puppeteer`) is a thin remote-control client with
 * no bundled Chromium of its own -- nothing is downloaded from anywhere
 * but the npm registry when this project's own `npm ci` already runs.
 * `--chrome` (or `CHROME_PATH`) must name an already-installed browser:
 * GitHub's own `ubuntu-latest` runner image ships Google Chrome
 * preinstalled for exactly this kind of job (confirmed against that
 * image's own published software list), so `.github/workflows/a11y.yml`
 * finds it with a plain `which google-chrome-stable` rather than adding a
 * download step. `axe-core` ships its rule engine as a plain script,
 * injected into the page under test -- no network call of its own either.
 *
 * D-26: served at the address it will actually be served at
 * -------------------------------------------------------------
 * GitHub Pages serves this project's build one path segment below a bare
 * domain root (no CNAME, no custom domain) -- `instance/config.json` is
 * the one place that address is written down, and every template's
 * `| url` filter call resolves against the prefix `.eleventy.js` derives
 * from it. D-26 ("Verify the shape that will actually be deployed, never
 * a convenient local one") is exactly the lesson this project's own
 * screenshot passes paid for: seven of them, all served at a bare
 * `localhost` root,
 * all green, on a site where every relative path -- style sheet, fonts,
 * every island's own fetches -- would have 404'd once actually published.
 * This script reads that same declaration, through the same
 * `scripts/published.cjs` the build itself uses, and serves the assembled
 * tree under the prefix it names, never at a bare root.
 *
 * The three islands
 * -------------------
 * `assembleTree` merges the site's own build with the *app's* build --
 * `app/dist` (the main SPA, skipped by the crawl below -- it is the
 * operators' cockpit, not a public page) plus its three island bundles
 * (`app/dist/islands/signup`, `app/dist/islands/verify`,
 * `app/dist/islands/survey`) and the static files
 * they fetch at runtime (`instance/keys/events/*.pub`, `certificates.json`,
 * `instance/keys/signing/index.json`, `survey-status.json`) -- into one tree, at
 * the one subtree (`app/`) every real deployment already uses.
 * `assertIslandsAreNotEmpty` is the explicit guard: after the page has
 * finished running its own JavaScript, the three mount points
 * (`#registration-form`, `#verify-app`, `#survey-form`) must hold real
 * content, not an empty `<div>` a checker could shrug past.
 *
 * `a11y.yml` generates a throw-away `<event-id>.pub` per fixture event
 * with `convener_ops.journey.eventkeys.generate()` -- a fresh, never-committed key
 * pair -- *before* building the app, so the registration island actually
 * reaches its `ready` state and renders its real `<input>`/`<label>`
 * markup for axe to see, rather than the "registration is not available"
 * fallback a missing key produces. Both states are legitimate, real
 * content either way -- this is what lets the automated run, not only
 * the manual keyboard pass, catch a label regression in the form itself.
 *
 * The page count is asserted, not assumed
 * ------------------------------------------
 * `expectedPageCount` derives the exact number of HTML pages this build
 * *should* produce from the same fixture data Eleventy itself paginates
 * over (`events.json`), rather than a hand-typed number that could
 * silently stop matching reality. A crawler stuck on a stale directory,
 * an empty build, or one page out of many would otherwise pass forever
 * -- this is the guard against that, checked on every run, not only
 * argued for in a report.
 */

import { createServer } from 'node:http';
import { readFile, readdir, mkdtemp, rm, mkdir, cp } from 'node:fs/promises';
import { existsSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import puppeteer from 'puppeteer-core';
// The instance's own published address, read through the same module
// `.eleventy.js` reads it through -- so this checker serves the tree at the
// address the build itself was configured for, and cannot drift from it.
import { publishedAddress } from './published.cjs';

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SITE_DIR = path.resolve(__dirname, '..');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.xml': 'application/xml; charset=utf-8',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.pub': 'application/x-pem-file',
};

/** Tags this project treats as "AA": WCAG 2.1's own level A and AA rules
 *  (AA is defined to include A -- a page failing an A rule is not AA
 *  either), plus 2.1's own AA additions. Never the whole of `best-practice`:
 *  axe bundles opinions there that are not part of the standard this checker
 *  targets, and failing the build on one would blur "not AA" with "a
 *  maintainer's taste" -- manufacturing a false positive rather than
 *  finding one. */
const WCAG_AA_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa'];

/** One `best-practice`-only rule opted back in by name, not by tag: axe
 *  classifies `heading-order` ("heading levels should only increase by
 *  one") as `best-practice`, never a `wcag2a`/`wcag2aa`/`wcag21aa` rule, so
 *  `WCAG_AA_TAGS` alone never runs it -- confirmed by reproducing the gap
 *  (a page's own heading order was deliberately broken and the run stayed
 *  green before this was added). A correct reading order is exactly what
 *  lets a screen reader user skim a page's own structure the way a sighted
 *  visitor skims its headings, which is why heading order is one of the
 *  violations this checker has to be proven against -- so this one rule is
 *  named individually, rather than pulling in the rest of `best-practice`
 *  to get it. */
const EXTRA_RULES = ['heading-order'];


function parseArgs(argv) {
  const args = { chrome: process.env.CHROME_PATH };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--site-dir') args.siteDir = argv[++i];
    else if (arg === '--app-dir') args.appDir = argv[++i];
    else if (arg === '--chrome') args.chrome = argv[++i];
    else throw new Error(`unrecognised argument: ${arg}`);
  }
  args.siteDir = path.resolve(args.siteDir || path.join(SITE_DIR, '_site'));
  if (args.appDir) args.appDir = path.resolve(args.appDir);
  return args;
}

/** Merges the site's own build and (optionally) the app's, into one tree
 *  addressed exactly the way `publish-vitrine.yml` and `deploy.yml`
 *  together publish it: the site's own files at the root, the app's under
 *  `app/`. `appDir` is optional -- a quick, site-only run (used while
 *  iterating on a template-only fix) still serves real pages under the
 *  real prefix; it simply cannot reach the islands' `ready` state, since
 *  their bundles would not be there to fetch. When `appDir` is given, its
 *  own `instance/keys/events/*.pub` (copied there by the app's build itself,
 *  `copy-event-keys.mjs`) travels with it -- `a11y.yml` generates its
 *  throw-away event keys *before* building the app for exactly this
 *  reason, so they are already inside `appDir` by the time this runs. */
async function assembleTree({ siteDir, appDir }) {
  const scratch = await mkdtemp(path.join(tmpdir(), 'convener-a11y-'));
  await cp(siteDir, scratch, { recursive: true });
  if (appDir) {
    const appDest = path.join(scratch, 'app');
    await mkdir(appDest, { recursive: true });
    await cp(appDir, appDest, { recursive: true });
  }
  return scratch;
}

function contentType(filePath) {
  return MIME[path.extname(filePath)] || 'application/octet-stream';
}

/** A static file server with no dependency of its own -- this project's
 *  own idiom (`.eleventy.js`, the copy scripts) already prefers a short
 *  hand-written function over a package for something this small. Listens
 *  on an OS-assigned port (`0`) so nothing here can collide with a port
 *  already busy on a shared runner. */
function serveStatic(root) {
  return new Promise((resolve) => {
    const server = createServer(async (req, res) => {
      try {
        const decodedPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        let filePath = path.join(root, decodedPath);
        if (!filePath.startsWith(root)) {
          res.writeHead(403);
          res.end();
          return;
        }
        if (existsSync(filePath) && statSync(filePath).isDirectory()) {
          filePath = path.join(filePath, 'index.html');
        }
        if (!existsSync(filePath) || statSync(filePath).isDirectory()) {
          res.writeHead(404);
          res.end('not found');
          return;
        }
        const body = await readFile(filePath);
        res.writeHead(200, { 'content-type': contentType(filePath) });
        res.end(body);
      } catch (err) {
        res.writeHead(500);
        res.end(String(err));
      }
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

/** Every `*.html` file this build wrote, under the site's own root --
 *  never under `app/`, which this checker deliberately does not scan: the
 *  operators' cockpit requires a GitHub sign-in and is not a page the
 *  public ever lands on, so it is out of scope here -- what is in scope is
 *  the pages this site generates. A recursive walk, not a hand-typed
 *  list of routes -- the exact difference between a crawler that notices
 *  a fifteenth page appearing and one that would not. */
async function discoverHtmlPages(root) {
  const found = [];
  async function walk(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (path.relative(root, full) === 'app') continue;
        await walk(full);
      } else if (entry.name.endsWith('.html')) {
        found.push(full);
      }
    }
  }
  await walk(root);
  return found.sort();
}

/** The exact number of HTML pages `site/src/event.njk`, `survey.njk`,
 *  `archives.njk`, `archives-year.njk` and `archives-filter.njk` together
 *  generate from `events.json`, computed the same way
 *  `site/src/_data/archive.js` does (distinct years among
 *  delivered/archived editions) -- so a crawler fed a stale or truncated
 *  build, or a future page nobody wired into the discovery walk above, is
 *  caught by a mismatched count rather than a silently-smaller passing
 *  run. Five fixed pages (home, archives index, propose, data, verify)
 *  plus two fixed facets (recordings, discussions, `archives-filter.njk`'s
 *  own front matter -- always generated, not data-derived) plus one page
 *  per distinct past year plus one event page per event (`event.njk`)
 *  plus one survey page per event (`survey.njk` -- one
 *  static page per event, the same D-19 addressing `event.njk` already
 *  uses).
 */
function expectedPageCount(events) {
  const pastYears = new Set(
    events
      .filter((event) => event.status === 'delivered' || event.status === 'archived')
      .map((event) => String(event.date).slice(0, 4))
  );
  const FIXED_PAGES = 5;
  const FIXED_FACETS = 2;
  return FIXED_PAGES + FIXED_FACETS + pastYears.size + events.length + events.length;
}

/** After the page has run its own JavaScript, a mount point this build's
 *  markup reserves for an island (`#registration-form`, `#verify-app`,
 *  `#survey-form`) must hold real content -- an empty one is exactly what
 *  a checker that only ever saw the server-rendered HTML would report as
 *  "nothing here, no violations, pass" (D-25). Returns `null` when the
 *  page carries no such mount point at all (every page except the one
 *  event page currently accepting registrations, the verify page, and a
 *  survey page), which is not a failure -- most pages have no island to
 *  check. */
async function emptyIslandMountIds(page) {
  return page.evaluate(() => {
    const ids = ['registration-form', 'verify-app', 'survey-form'];
    const empty = [];
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el && el.children.length === 0) empty.push(id);
    }
    return empty;
  });
}

async function runAxe(page, axeSource) {
  await page.evaluate(axeSource);
  return page.evaluate(
    (tags, extraRules) => {
      // Resolved by rule id, not by tag, so `extraRules` (best-practice
      // rules opted in individually -- see EXTRA_RULES's own comment) can
      // join the WCAG-tagged set without pulling in the rest of
      // best-practice along with it: `runOnly: {type: 'tag'}` alone has no
      // way to add one rule from outside the tags it was given.
      const ruleIds = window.axe.getRules(tags).map((r) => r.ruleId);
      const values = [...new Set([...ruleIds, ...extraRules])];
      return window.axe.run(document, { runOnly: { type: 'rule', values } });
    },
    WCAG_AA_TAGS,
    EXTRA_RULES
  );
}

/** axe-core's own `incomplete` category means "a human must look", not "a
 *  violation" -- but treating every incomplete result as a mere warning,
 *  forever, would be exactly the wholesale suppression this project
 *  refuses: a finding judged to be a false positive is suppressed named
 *  and justified, with the measurement beside it, never wholesale. So only
 *  these specific, reviewed
 *  `color-contrast` *nodes* are ever waved through; anything else axe
 *  reports as incomplete fails the build like a real violation, because
 *  nobody has looked at it yet.
 *
 *  Each entry names one hand-measured node by **both** its `messageKey`
 *  (axe's own reason it gave up resolving the pairing statically) **and**
 *  the CSS selector axe's target resolution produced for it. The reason
 *  alone is not an identity: `pseudoContent`/`elmPartiallyObscuring`/
 *  `imgNode` each name a whole *shape* of node axe cannot statically
 *  resolve -- any `::before`-painted band or any decorative element that
 *  grazes text produces one of these three, regardless of what the
 *  actual rendered contrast is. A build with only the `messageKey` on
 *  this list (the shape this project shipped, and closed here) waves
 *  through a newly-added, never-measured node that happens to share the
 *  shape -- reproduced by hand for this fix: a `::before`-painted
 *  ~1.07:1 white-on-yellow pairing reports `pseudoContent`, identical to
 *  the legitimate ones, and was silently accepted before this change.
 *  Selector included, it is rejected, correctly, as unreviewed.
 *
 *  Selectors are recorded literally, exactly as axe emits them --
 *  including any `:nth-child` axe adds to disambiguate a class repeated
 *  on one page (`.section` appears twice on `/` and `/data/`, so
 *  `.section__num` there resolves as `.section:nth-child(2) > … >
 *  .section__num`, `.section:nth-child(3) > …`, etc., while every page
 *  with a single `.section` reports the bare class -- both forms
 *  captured below, from a real build). This is a deliberate trade: a
 *  markup change that shifts which `nth-child` index an already-reviewed
 *  node falls under (adding a third `.section` to a page that only had
 *  two, say) makes this list stop matching, and the build fails, noisily,
 *  on a pairing that is probably still fine visually, and has to be
 *  re-added by name. That is the correct failure direction (D-25): a
 *  list that tolerates "close enough" selectors degrades back into the
 *  shape-only suppression this fix exists to close. Re-adding an entry
 *  after a legitimate refactor costs one line and a rebuild; a silent
 *  false pass costs nobody ever noticing.
 *
 *  All ten were found and measured against the real thing, by
 *  rendering the real built pages and reading axe's own explanation for
 *  each flagged node (`node.any[].data.messageKey`), not assumed from the
 *  rule's name:
 *
 *  - `pseudoContent` -- `.section__head`'s cream band is painted by a
 *    `::before` pseudo-element (`site/src/style.css`), not a `background`
 *    on the text's own ancestor, so axe cannot resolve it statically. The
 *    real pairings it is asking about are `.section__num` (purple on
 *    cream, `instance/data/brand.json`'s `purple_on_cream`, 11.26), `.section__label`
 *    (ink on cream, `ink_on_cream`, 10.12) and `.section__count` (ink-faint
 *    on cream, `ink_faint_on_cream`, 4.99) -- all three already measured,
 *    all AA or better, on every page they appear on (bare class where
 *    `.section` is unique on the page, `:nth-child`-qualified on `/` and
 *    `/data/`, which each render more than one `.section`).
 *  - `imgNode` -- the ribbon motif (D-16's "one continuous meandering
 *    stroke"; `.masthead__loops` on every page, `.hero__loops` on
 *    several, `.coda__loops` on the homepage) is `aria-hidden` and
 *    deliberately positioned to run into a page's own text -- and at some
 *    widths its thin stroke visually grazes real text:
 *    `.masthead__brand-mark` at 390px (confirmed by rendering and
 *    screenshotting the actual pixels, not assumed -- a purple line a few
 *    screen pixels wide crossing part of a glyph, the rest of the word
 *    untouched) and, on the homepage, `.coda__text > em`. Neither is a
 *    real reduction in legibility -- the text's own colour against its
 *    *designed* background clears AA with room to spare either way:
 *    purple on cream (`purple_on_cream`, 11.26) for the masthead;
 *    turquoise on purple (`turquoise_on_purple`, 7.93 -- added to
 *    `instance/data/brand.json` on review, since the pairing had
 *    existed unmeasured by name) for `.coda__text em`.
 *  - `elmPartiallyObscuring` -- `.coda__text` itself (the element `em`
 *    sits inside, not the `em` alone), where `.coda__loops` sits in a
 *    lower stacking position than `.coda__inner` (`z-index: 1`): white on
 *    purple (`white_on_purple`, 12.74).
 */
const REVIEWED_INCOMPLETE_NODES = [
  { messageKey: 'pseudoContent', selector: '.section__num' },
  { messageKey: 'pseudoContent', selector: '.section__label' },
  { messageKey: 'pseudoContent', selector: '.section__count' },
  {
    messageKey: 'pseudoContent',
    selector: '.section:nth-child(2) > .section__head > .section__num',
  },
  {
    messageKey: 'pseudoContent',
    selector: '.section:nth-child(2) > .section__head > .section__label',
  },
  {
    messageKey: 'pseudoContent',
    selector: '.section:nth-child(3) > .section__head > .section__num',
  },
  {
    messageKey: 'pseudoContent',
    selector: '.section:nth-child(3) > .section__head > .section__label',
  },
  { messageKey: 'imgNode', selector: '.masthead__brand-mark' },
  { messageKey: 'elmPartiallyObscuring', selector: '.coda__text' },
  { messageKey: 'imgNode', selector: '.coda__text > em' },
];

/** The `color-contrast` check's own `messageKey` for one axe `incomplete`
 *  node, or `null` when the node's shape does not match what this project
 *  has ever reviewed -- which must never be treated as reviewed by
 *  default (D-25: an unfamiliar shape is a reason to fail, not to guess). */
function messageKeyFor(node) {
  const check = node.any.find((c) => c.id === 'color-contrast');
  return check?.data?.messageKey ?? null;
}

/** Whether this specific node -- `messageKey` *and* the selector axe
 *  resolved it to, both -- is one this project has actually measured (see
 *  `REVIEWED_INCOMPLETE_NODES`'s own comment). A node sharing only the
 *  `messageKey` with a reviewed entry, at a selector nobody has looked
 *  at, is not reviewed: that gap is exactly what this function closes. */
function isReviewedIncomplete(messageKey, node) {
  if (!messageKey) return false;
  const selector = node.target.join(' ');
  return REVIEWED_INCOMPLETE_NODES.some(
    (entry) => entry.messageKey === messageKey && entry.selector === selector
  );
}

/** Splits one axe `incomplete` item into nodes this project has already
 *  reviewed and named (see `REVIEWED_INCOMPLETE_NODES`'s own comment) and
 *  nodes it has not -- the latter must fail the build. */
function classifyIncomplete(item) {
  const reviewed = [];
  const unreviewed = [];
  for (const node of item.nodes) {
    const key = messageKeyFor(node);
    if (item.id === 'color-contrast' && isReviewedIncomplete(key, node)) {
      reviewed.push({ node, key });
    } else {
      unreviewed.push({ node, key });
    }
  }
  return { reviewed, unreviewed };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.chrome) {
    throw new Error(
      'no Chrome executable given -- pass --chrome <path> or set CHROME_PATH ' +
        '(this checker never downloads a browser of its own; see this file’s own module comment)'
    );
  }

  const prefix = publishedAddress().pathPrefix;
  const events = JSON.parse(
    await readFile(path.join(SITE_DIR, 'src', '_data', 'events.json'), 'utf8')
  );
  const expected = expectedPageCount(events);

  const scratch = await assembleTree(args);
  // The prefix names exactly one path segment in this project; serving
  // the scratch directory's *parent* under
  // that name reproduces the real deployment without copying the tree a
  // second time -- a symlink would do the same, but Windows requires a
  // privilege this checker should not need to ask for.
  const publishRoot = await mkdtemp(path.join(tmpdir(), 'convener-a11y-root-'));
  const prefixSegment = prefix.replace(/^\/|\/$/g, '');
  await cp(scratch, path.join(publishRoot, prefixSegment), { recursive: true });

  const server = await serveStatic(publishRoot);
  const { port } = server.address();
  const baseUrl = `http://127.0.0.1:${port}${prefix}`;

  let browser;
  const violationsByPage = [];
  const reviewedIncompleteByPage = [];
  const unreviewedIncompleteByPage = [];
  const emptyIslands = [];
  let pagesChecked = 0;

  try {
    browser = await puppeteer.launch({ executablePath: args.chrome, headless: true });
    const vitrineRoot = path.join(publishRoot, prefixSegment);
    const htmlFiles = await discoverHtmlPages(vitrineRoot);

    console.log(
      `check-a11y: examined ${htmlFiles.length} of ${expected} expected page(s) ` +
        `(5 fixed + 2 facets + ${new Set(
          events
            .filter((e) => e.status === 'delivered' || e.status === 'archived')
            .map((e) => String(e.date).slice(0, 4))
        ).size} year(s) + ${events.length} event(s))`
    );
    if (htmlFiles.length !== expected) {
      throw new Error(
        `expected ${expected} built HTML page(s) under ${prefix}, found ${htmlFiles.length} -- ` +
          'refusing to treat a mismatched build as a passing run (D-25)'
      );
    }

    const axeSource = require.resolve('axe-core/axe.min.js');
    const axeScript = await readFile(axeSource, 'utf8');

    for (const filePath of htmlFiles) {
      const relUrl = path
        .relative(vitrineRoot, filePath)
        .split(path.sep)
        .join('/');
      const url = `${baseUrl}${relUrl === 'index.html' ? '' : relUrl.replace(/index\.html$/, '')}`;
      for (const viewport of [
        { width: 1280, height: 900, label: 'desktop' },
        { width: 390, height: 844, label: 'mobile' },
      ]) {
        const page = await browser.newPage();
        try {
          await page.setViewport({ width: viewport.width, height: viewport.height });
          await page.goto(url, { waitUntil: 'networkidle0', timeout: 30_000 });
          const results = await runAxe(page, axeScript);
          if (results.violations.length > 0) {
            violationsByPage.push({ url, viewport: viewport.label, violations: results.violations });
          }
          for (const item of results.incomplete) {
            const { reviewed, unreviewed } = classifyIncomplete(item);
            if (reviewed.length > 0) {
              reviewedIncompleteByPage.push({ url, viewport: viewport.label, item, nodes: reviewed });
            }
            if (unreviewed.length > 0) {
              unreviewedIncompleteByPage.push({ url, viewport: viewport.label, item, nodes: unreviewed });
            }
          }
          if (viewport.label === 'desktop') {
            const empty = await emptyIslandMountIds(page);
            if (empty.length > 0) emptyIslands.push({ url, empty });
          }
          pagesChecked += 1;
        } finally {
          await page.close();
        }
      }
    }
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
    await rm(scratch, { recursive: true, force: true });
    await rm(publishRoot, { recursive: true, force: true });
  }

  console.log(`check-a11y: rendered ${pagesChecked} page-viewport combination(s)`);

  if (reviewedIncompleteByPage.length > 0) {
    console.log(
      '::notice::axe flagged colour-contrast as "incomplete" on nodes already reviewed and ' +
        'measured by hand (see check-a11y.mjs\'s own REVIEWED_INCOMPLETE_NODES comment):'
    );
    for (const { url, viewport, item, nodes } of reviewedIncompleteByPage) {
      const targets = nodes.map((n) => n.node.target.join(' ')).join(' | ');
      console.log(`::notice::${url} (${viewport}) -- ${item.id}: ${targets}`);
    }
  }

  if (unreviewedIncompleteByPage.length > 0) {
    console.log(
      '::error::axe reported an "incomplete" result this project has not reviewed -- ' +
        'treated as a failure until a human looks at it and either fixes it or adds it, ' +
        'named and justified, to REVIEWED_INCOMPLETE_NODES:'
    );
    for (const { url, viewport, item, nodes } of unreviewedIncompleteByPage) {
      for (const { node, key } of nodes) {
        console.log(
          `::error::${url} (${viewport}) -- [${item.id}] ${item.help} -- messageKey=${key ?? '(none)'} -- ${node.target.join(' ')}`
        );
      }
    }
  }

  if (emptyIslands.length > 0) {
    console.log('::error::an island mount point rendered with no content:');
    for (const { url, empty } of emptyIslands) {
      console.log(`::error::${url} -- empty mount point(s): ${empty.join(', ')}`);
    }
  }

  if (violationsByPage.length > 0) {
    console.log('::error::accessibility violations found:');
    for (const { url, viewport, violations } of violationsByPage) {
      for (const violation of violations) {
        const targets = violation.nodes.map((n) => n.target.join(' ')).join(' | ');
        console.log(
          `::error::${url} (${viewport}) -- [${violation.impact}] ${violation.id}: ${violation.help} -- ${targets}`
        );
      }
    }
  }

  if (
    violationsByPage.length > 0 ||
    emptyIslands.length > 0 ||
    unreviewedIncompleteByPage.length > 0
  ) {
    process.exitCode = 1;
  } else {
    console.log(
      'check-a11y: no AA violations, no unreviewed incomplete results, ' +
        'every island mount point rendered content'
    );
  }
}

await main();
