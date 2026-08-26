/* The site must stay usable on a poor connection, and that has to be
 * verified automatically. This is that verification: it
 * sums the real bytes a visitor's browser downloads to render one of this
 * project's public pages, gzip-compressed (D-26's own "measure the deployed
 * shape" applied to weight, not just to address: GitHub Pages serves gzip on
 * every compressible response, so a raw byte count is wrong in the exact
 * direction that flatters this check), against the real built output --
 * never a source directory, never an unminified intermediate.
 *
 * Two different problems, two budgets
 * -------------------------------------
 * A static page (the home page, an archive, a past event) and a page
 * carrying a client-side island (the one event page currently accepting
 * registrations, the certificate-verification page) are not the same
 * problem, and one number covering both would either be loose enough to
 * wave the island pages through or tight enough to fail every static page
 * on the first paragraph of added copy. `STATIC_PAGE_BUDGET_GZIP_BYTES` and
 * `ISLAND_PAGE_BUDGET_GZIP_BYTES` are set and justified separately, below,
 * against this task's own measurement of the real built site on
 * 2026-08-22 -- see this task's own report for the full reasoning; the
 * short version is in each constant's own comment.
 *
 * A page's class is read from what it actually references, not from a
 * hardcoded list of page names: any page whose HTML loads a script under
 * `app/islands/` is "island", everything else is "static" -- so a future
 * event page that starts (or stops) accepting registrations reclassifies
 * itself the next time this runs, rather than silently being checked
 * against the wrong budget forever.
 *
 * Fonts are accounted for, not folded in
 * -----------------------------------------
 * D-17: the self-hosted font family is a deliberate, non-negotiable choice
 * -- a webfont request to a third party discloses every visitor's address,
 * which this project's own data notice forbids.
 * It is also, by a wide margin, the largest static weight on this site
 * (~193 KB across two Archivo subsets and one JetBrains Mono weight, all
 * already woff2-compressed -- see `FONT_PAYLOAD_BUDGET_RAW_BYTES`'s own
 * comment). Folding that into a per-page budget would make the page
 * numbers meaningless (every page would look font-dominated) and would
 * eventually read, to whoever next sees this job red, as "drop the fonts"
 * -- exactly the pressure D-17 forbids creating. So it is measured and
 * reported on its own, as a bloat guard against a font file growing or a
 * new one being added un-subsetted, never as a lever on page weight: if
 * this ever fails, the fix is to look at what changed under `fonts/`, not
 * to reconsider self-hosting.
 *
 * Proving this can fail (D-25)
 * --------------------------------
 * A budget that cannot fail is not a budget -- this phase has already paid
 * for that shape six times (D-25's own tally). This task deliberately
 * lowered each threshold below a real measurement and watched this script
 * exit 1 with the right page named, before setting the real numbers below
 * -- see this task's own report for the transcript. It is not re-proven at
 * every run (that would defeat the point of a fixed budget), but the
 * technique is named here for the next person who changes a number: lower
 * it, watch it fail, then set it back.
 *
 * Zero cost, by construction
 * ------------------------------
 * No dependency beyond Node's own built-in `zlib` -- nothing installed,
 * nothing downloaded, nothing that could phone home. No network call of
 * any kind: every byte counted here already sits in `site/_site` and
 * `app/dist` before this script runs a single line.
 */

import { readFile, readdir, mkdtemp, rm, mkdir, cp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import zlib from 'node:zlib';
// The instance's own published address, read through the same module
// `.eleventy.js` reads it through -- so every page reference is resolved
// against the address the build itself was configured for.
import { publishedAddress } from './published.cjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SITE_DIR = path.resolve(__dirname, '..');

/** Static pages -- home, archives (its index, year and facet pages),
 *  propose, data, and every past event page: plain text and layout, no
 *  client-side island. Transfer weight is the page's own HTML plus the one
 *  stylesheet every page loads, gzip.
 *
 *  Measured on the real built output, 2026-08-22: the heaviest static page
 *  is the home page, 11,948 B gzip (2,425 B HTML + 9,523 B CSS -- both
 *  measured by this same script, not estimated). This budget gives
 *  roughly 3.4x headroom over that: enough for the archive to grow by
 *  years and editions, or the stylesheet to grow with them, without
 *  nearing the ceiling -- tight enough that an unminified script pasted
 *  in, an inline base64 image, or a copy-pasted third-party embed would
 *  trip it well before the page became slow on a poor connection.
 */
const STATIC_PAGE_BUDGET_GZIP_BYTES = 40 * 1024;

/** Pages carrying a client-side island -- the one event page accepting
 *  registrations, the certificate-verification page, and every survey
 *  page (`survey.njk`): HTML plus the shared stylesheet
 *  plus the one island bundle the page mounts, gzip.
 *
 *  Measured on the real built output, 2026-08-22: the heavier of the two
 *  islands then in existence was the verify page, 72,968 B gzip (1,462 B
 *  HTML + 9,523 B CSS + 61,983 B for `verify.js`); the registration
 *  island's own event page comes out within a few hundred bytes of it.
 *  The survey island, measured the same way, comes out
 *  close to the same weight as its two siblings (one shared HTML/CSS
 *  shape, one island bundle of comparable size).
 *  This budget allows roughly 50% growth over the
 *  2026-08-22 measurement -- a dependency bump, more form fields, more
 *  verification detail -- while staying well under half of what a visitor
 *  downloaded before these forms moved out of the operators'
 *  cockpit (183.65-189.53 KB gzip for the whole application).
 *  The regression this budget exists to catch is a
 *  visitor silently going back to downloading something close to that,
 *  not a few hundred bytes of copy.
 */
const ISLAND_PAGE_BUDGET_GZIP_BYTES = 110 * 1024;

/** The self-hosted font payload -- see this file's own module comment for
 *  why this is separate from the two page budgets above, and why "drop
 *  the fonts" is never the right response to this failing.
 *
 *  Measured on the real built output, 2026-08-22: two Archivo subsets
 *  (regular Latin range and Latin Extended, one variable file each,
 *  weights 100-900) and one JetBrains Mono weight, 197,512 B combined --
 *  already woff2-compressed, so gzip saves nothing further on top of it
 *  (confirmed by measuring: gzipping a woff2 file in this project adds a
 *  few dozen bytes of container overhead rather than shrinking it), which
 *  is why this budget is stated in raw bytes rather than gzip like the
 *  two above. This leaves roughly 35% headroom -- a subset-boundary
 *  correction, a variable-font update -- without being loose enough to
 *  wave through a careless multi-weight, non-variable family, which is
 *  exactly what the substitution in D-17 was chosen to avoid.
 */
const FONT_PAYLOAD_BUDGET_RAW_BYTES = 260 * 1024;

function gzipSize(buffer) {
  return zlib.gzipSync(buffer, { level: 9 }).length;
}


function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--site-dir') args.siteDir = argv[++i];
    else if (arg === '--app-dir') args.appDir = argv[++i];
    else throw new Error(`unrecognised argument: ${arg}`);
  }
  args.siteDir = path.resolve(args.siteDir || path.join(SITE_DIR, '_site'));
  if (!args.appDir) {
    throw new Error(
      '--app-dir is required -- the island pages this budget covers ' +
        "cannot be weighed without the app's own built islands (D-25: a " +
        'run that silently skipped them would not be checking what it ' +
        'claims to check)'
    );
  }
  args.appDir = path.resolve(args.appDir);
  return args;
}

/** Merges the site's own build and the app's, addressed exactly the way
 *  `deploy.yml` and `publish-vitrine.yml` together publish them: the
 *  site's own files at the root, the app's (including every island
 *  bundle) under `app/`. The same merge `check-a11y.mjs`'s own
 *  `assembleTree` performs, for the identical reason -- both scripts need
 *  to resolve a page's real, prefixed references against one tree that
 *  matches the real deployment. */
async function assembleTree({ siteDir, appDir }) {
  const scratch = await mkdtemp(path.join(tmpdir(), 'convener-perf-'));
  await cp(siteDir, scratch, { recursive: true });
  const appDest = path.join(scratch, 'app');
  await mkdir(appDest, { recursive: true });
  await cp(appDir, appDest, { recursive: true });
  return scratch;
}

/** Every `*.html` file this build wrote, under the site's own root --
 *  never under `app/`, the operators' cockpit, which is not a public page
 *  (the same exclusion `check-a11y.mjs`'s own `discoverHtmlPages` makes,
 *  for the identical reason). A recursive walk, not a hand-typed list of
 *  routes, so a future page nobody wired in here still gets weighed. */
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

/** The exact number of HTML pages this build should produce -- the same
 *  formula `check-a11y.mjs`'s own `expectedPageCount` derives from the
 *  same fixture data, kept as its own small copy here rather than shared:
 *  these are two independent, single-purpose scripts, and neither needs
 *  the other's dependencies. See that file's own comment for the full
 *  breakdown this formula encodes, including `survey.njk`'s own one page
 *  per event. */
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

/** A `<link rel="stylesheet" href="...">` tag's own `href` -- deliberately
 *  never matching `rel="preload"` (the font preload; accounted for
 *  separately, see this file's own module comment), `rel="canonical"` or
 *  `rel="alternate"` (metadata links a browser does not fetch to render
 *  the page), because none of those literally contain the string
 *  `rel="stylesheet"` this pattern requires. */
const STYLESHEET_HREF_RE = /<link[^>]*\brel=["']stylesheet["'][^>]*\bhref=["']([^"']+)["'][^>]*>/gi;

/** A `<script ... src="...">...</script>` tag's own `src` -- the three
 *  island mount scripts (`signup.js`, `verify.js`, `survey.js`) are the
 *  only script tags this project's templates emit with a `src` attribute
 *  at all (the structured-data block on an event page is an inline
 *  `<script type="application/ld+json">` with no `src`, already counted
 *  as part of that page's own HTML weight). */
const SCRIPT_SRC_RE = /<script[^>]*\bsrc=["']([^"']+)["'][^>]*><\/script>/gi;

/** The distinct, same-origin resource references one rendered page's HTML
 *  actually asks the browser to fetch to render it -- never a hardcoded
 *  per-page list, so a template change that adds or removes a resource
 *  changes what gets weighed automatically. */
function localResourceHrefs(html) {
  const hrefs = new Set();
  for (const match of html.matchAll(STYLESHEET_HREF_RE)) hrefs.add(match[1]);
  for (const match of html.matchAll(SCRIPT_SRC_RE)) hrefs.add(match[1]);
  return [...hrefs];
}

/** Resolves one page-relative resource href (e.g.
 *  `<prefix>app/islands/verify/verify.js`) to its real file inside
 *  the merged tree `assembleTree` produced. D-26, applied to this
 *  resolution step specifically: every href this project's templates emit
 *  must already carry `prefix` (a separate, repository-wide guard,
 *  `tools/tests/test_site.py::
 *  test_no_built_page_emits_a_root_relative_link_without_the_prefix`,
 *  already enforces this on every build) -- an href reaching here without
 *  it is exactly the class of defect D-26 exists to catch, so this throws
 *  rather than silently skipping it, which would under-count the page's
 *  real weight and pass for the wrong reason. */
function resolveLocalHref(href, prefix, scratch) {
  if (!href.startsWith(prefix)) {
    throw new Error(
      `resource href '${href}' does not carry the configured prefix ` +
        `'${prefix}' -- a page reference missing D-26's own prefix would ` +
        '404 once published, and would also make this budget under-count ' +
        'the page (fixing the reference, not this checker, is the correct response)'
    );
  }
  const relative = href.slice(prefix.length);
  return path.join(scratch, relative);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const prefix = publishedAddress().pathPrefix;

  const events = JSON.parse(
    await readFile(path.join(SITE_DIR, 'src', '_data', 'events.json'), 'utf8')
  );
  const expected = expectedPageCount(events);

  const scratch = await assembleTree(args);
  const results = [];
  let failed = false;

  try {
    const htmlFiles = await discoverHtmlPages(scratch);
    console.log(
      `check-performance-budget: examined ${htmlFiles.length} of ${expected} expected page(s)`
    );
    if (htmlFiles.length !== expected) {
      throw new Error(
        `expected ${expected} built HTML page(s), found ${htmlFiles.length} -- ` +
          'refusing to treat a mismatched build as a passing run (D-25)'
      );
    }

    for (const filePath of htmlFiles) {
      const htmlBuffer = await readFile(filePath);
      const html = htmlBuffer.toString('utf8');
      const hrefs = localResourceHrefs(html);

      let resourceBytes = 0;
      let isIsland = false;
      for (const href of hrefs) {
        if (href.includes('/app/islands/')) isIsland = true;
        const resolved = resolveLocalHref(href, prefix, scratch);
        const resourceBuffer = await readFile(resolved);
        resourceBytes += gzipSize(resourceBuffer);
      }

      const totalGzip = gzipSize(htmlBuffer) + resourceBytes;
      const budget = isIsland ? ISLAND_PAGE_BUDGET_GZIP_BYTES : STATIC_PAGE_BUDGET_GZIP_BYTES;
      const rel = path.relative(scratch, filePath).split(path.sep).join('/');
      const withinBudget = totalGzip <= budget;
      if (!withinBudget) failed = true;
      results.push({ rel, isIsland, totalGzip, budget, withinBudget });
    }

    for (const { rel, isIsland, totalGzip, budget, withinBudget } of results) {
      const label = isIsland ? 'island' : 'static';
      const line =
        `check-performance-budget: ${rel} (${label}) -- ${totalGzip} B gzip ` +
        `/ ${budget} B budget`;
      console.log(withinBudget ? line : `::error::${line} -- OVER BUDGET`);
    }

    // Font payload: a bloat guard, not a per-page cost -- see this file's
    // own module comment for why it is reported and judged separately.
    const fontsDir = path.join(scratch, 'fonts');
    let fontBytes = 0;
    const fontFiles = (await readdir(fontsDir)).filter((name) => name.endsWith('.woff2'));
    for (const name of fontFiles) {
      const buffer = await readFile(path.join(fontsDir, name));
      fontBytes += buffer.length;
    }
    const fontWithinBudget = fontBytes <= FONT_PAYLOAD_BUDGET_RAW_BYTES;
    const fontLine =
      `check-performance-budget: fonts (${fontFiles.length} file(s)) -- ` +
      `${fontBytes} B raw / ${FONT_PAYLOAD_BUDGET_RAW_BYTES} B budget`;
    if (!fontWithinBudget) {
      failed = true;
      console.log(
        `::error::${fontLine} -- OVER BUDGET (self-hosting stays, D-17 -- ` +
          'look at what changed under fonts/, do not remove it)'
      );
    } else {
      console.log(fontLine);
    }
  } finally {
    await rm(scratch, { recursive: true, force: true });
  }

  if (failed) {
    process.exitCode = 1;
  } else {
    console.log(
      `check-performance-budget: all ${results.length} page(s) and the font ` +
        'payload are within budget'
    );
  }
}

await main();
