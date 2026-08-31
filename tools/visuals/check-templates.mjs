/* Does any stroke of the motif cross any word of the three downloadable
 * templates? Measured, on the pinned engine, for every charter this
 * repository holds crossed with every family it draws.
 *
 * Why this file exists
 * ---------------------
 * `brand_templates.py` places every block of type against the corridor the
 * family in force reports (`motifs.safe_margins`, `motifs.free_spans`), and
 * that arithmetic is held by unit tests. What no unit test can hold is the
 * half of the question that needs glyphs: how *wide* a line actually sets.
 * A corridor is only respected if the words fit inside it, and how much
 * room a word takes is a property of the face, the weight and the string --
 * measurable in a browser and nowhere else in this repository.
 *
 * Before this check, the answer was a person looking at a picture. That is
 * the defect class D-25 names, and it had already cost something: rendered
 * here for the first time, the example instance's own flyer drew its
 * motif **11.9 units through its tagline**, and this instance's own flyer
 * cleared its headline by **1.6 units** on a 2100-unit page. Neither is
 * visible in a diff, and nothing in the repository would ever have gone
 * red for either.
 *
 * What it measures, exactly
 * --------------------------
 * For each fixture `convener-render-template-fixtures` wrote:
 *
 * 1. Every block of type. Each `<text>` with `<tspan>` children is read as
 *    its tspans and not as their union: the union of a nine-line column is
 *    a rectangle covering ground the column never inks, and clearing that
 *    is a different, harder question than the one being asked.
 * 2. Each block's four corners in the page's own coordinates, so the
 *    tilted photo plate is measured as the tilted quadrilateral it is
 *    rather than as its upright bounding box.
 * 3. The motif's own path, sampled along its length, and the distance from
 *    each sample to each block, less half the stroke's width -- which is
 *    how far the *painted* edge of the drawing stays from the *inked*
 *    extent of the words. Negative means a stroke crosses a word.
 *
 * The face it measures in is the one the charter names and this repository
 * self-hosts (D-17), injected as an `@font-face` the way `visual.py`'s own
 * pages carry one. The committed templates deliberately embed no font --
 * they are opened in Inkscape by a volunteer -- so a rendering with no
 * webfont falls back to whatever that machine has, and no check here can
 * pin a face this repository does not ship. What it can do is measure the
 * one face every rendering this project performs actually uses, and that
 * is what it does.
 *
 * It also re-measures `convener_ops.publication.typeface`'s own advance
 * tables against the same font file. Those tables are what sizes a line in
 * Python, where there is no rasteriser; a table that quietly stopped
 * describing the face beside it would put the words back through the
 * drawing with every unit test still green.
 *
 * Usage, from `tools/visuals/`:
 *
 *     node check-templates.mjs --fixtures DIR [--report FILE]
 *
 * `--report` writes the whole measurement as JSON for a person who wants
 * the numbers rather than the verdict; the verdict is the exit code, and
 * every block's clearance is printed either way.
 */

import { createServer } from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** How close the painted edge of the drawing may come to the inked extent
 *  of a word before this check calls it a collision.
 *
 *  Zero, and deliberately: the question the layout answers is "does a
 *  stroke pass behind a word", and anything above zero would be this file
 *  inventing a design rule of its own on top of the one
 *  `motifs.CLEARANCE_STROKE_WIDTHS` already states -- each family declares
 *  the gutter it keeps, and holding the render to a *second*, larger
 *  number here would make the two disagree with nothing to say which is
 *  right. The clearance every block actually achieves is printed, so a
 *  margin that is merely thin is visible without being fatal. */
const MINIMUM_CLEARANCE = 0;

/** How far apart the samples along the motif's path are, in the page's own
 *  units, before the search is refined.
 *
 *  The nearest approach is then bisected around the best coarse sample, so
 *  this number decides only whether the coarse pass can miss the right
 *  neighbourhood entirely -- not the precision of the answer. Four units
 *  on a page whose stroke is between 24 and 63 wide cannot: a stroke that
 *  came within four units of a word would be reported as a collision by
 *  its neighbouring samples anyway. */
const SAMPLE_STEP = 4;

/** How many times the nearest approach is bisected around the best coarse
 *  sample. Ten halvings take a four-unit interval under a hundredth of a
 *  unit, which is finer than the two decimal places the templates are
 *  written to. */
const REFINEMENTS = 10;

/** How far a re-measured advance may differ from the table
 *  `typeface.py` carries, in ems.
 *
 *  The table is rounded up to fiftieths of an em, so a faithful entry sits
 *  between the measurement and one fiftieth above it. Anything outside
 *  that is either a different font file or a table nobody re-measured. */
const ADVANCE_ROUNDING = 0.02;

const MIME = {
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.json': 'application/json',
  '.html': 'text/html; charset=utf-8',
};

function parseArgs(argv) {
  const args = { fixtures: undefined, report: undefined };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--fixtures') args.fixtures = argv[++i];
    else if (arg === '--report') args.report = argv[++i];
    else throw new Error(`unrecognised argument: ${arg}`);
  }
  if (!args.fixtures) {
    throw new Error(
      '--fixtures DIR is required -- the directory convener-render-template-fixtures ' +
        'wrote (manifest.json, advances.json, one *.svg per charter and family, a copy of fonts/)'
    );
  }
  args.fixtures = path.resolve(args.fixtures);
  if (args.report) args.report = path.resolve(args.report);
  return args;
}

/** The same dependency-free static server `render-and-compare.mjs` uses,
 *  and for the same reason: a `file://` origin cannot load a relative
 *  `@font-face url` without a flag this project has no reason to carry. */
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
        res.writeHead(200, { 'content-type': MIME[path.extname(filePath)] || 'application/octet-stream' });
        res.end(body);
      } catch (err) {
        res.writeHead(500);
        res.end(String(err));
      }
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

/** The charter's own face, self-hosted beside the fixtures. The same two
 *  subsets `visual._FONT_FACE_CSS` declares, without their unicode ranges:
 *  nothing here paints a screenshot, so which subset serves a glyph does
 *  not matter -- only that the face is the real one. */
const FACE_CSS = [
  'archivo-latin-standard-normal.woff2',
  'archivo-latin-ext-standard-normal.woff2',
]
  .map(
    (file) =>
      `@font-face{font-family:'Archivo';font-style:normal;font-weight:100 900;` +
      `font-display:block;src:url('fonts/${file}') format('woff2');}`
  )
  .join('\n');

/** Every block of type in one rendered template, with its clearance from
 *  the motif's own painted edge. Runs entirely inside the page. */
async function measureTemplate(page) {
  return page.evaluate(
    async (faceCss, sampleStep, refinements) => {
      const svg = document.documentElement;
      const style = document.createElementNS('http://www.w3.org/2000/svg', 'style');
      style.textContent = faceCss;
      svg.insertBefore(style, svg.firstChild);
      await document.fonts.load('900 100px Archivo');
      await document.fonts.load('400 100px Archivo');
      await document.fonts.ready;

      const motifGroup = svg.querySelector('#motif');
      if (!motifGroup) throw new Error('no element with id="motif" in this template');
      const motif = motifGroup.querySelector('path');
      const strokeWidth = parseFloat(motifGroup.getAttribute('stroke-width'));
      if (!motif || !Number.isFinite(strokeWidth)) {
        throw new Error('the motif group carries no path, or no stroke width');
      }

      const rootMatrix = svg.getScreenCTM().inverse();
      function quadOf(element) {
        const box = element.getBBox();
        const matrix = rootMatrix.multiply(element.getScreenCTM());
        return [
          [box.x, box.y],
          [box.x + box.width, box.y],
          [box.x + box.width, box.y + box.height],
          [box.x, box.y + box.height],
        ].map(([x, y]) => {
          const point = svg.createSVGPoint();
          point.x = x;
          point.y = y;
          const mapped = point.matrixTransform(matrix);
          return [mapped.x, mapped.y];
        });
      }

      const blocks = [];
      for (const text of svg.querySelectorAll('text')) {
        const spans = [...text.querySelectorAll('tspan')];
        for (const element of spans.length ? spans : [text]) {
          const box = element.getBBox();
          if (box.width <= 0 || box.height <= 0) continue;
          blocks.push({
            text: (element.textContent || '').trim(),
            size: parseFloat(getComputedStyle(element).fontSize),
            box: [box.x, box.y, box.width, box.height],
            quad: quadOf(element),
          });
        }
      }

      /** Distance from a point to a convex quadrilateral, zero inside it.
       *  The quads come from an untilted or a clockwise-tilted box, so
       *  their winding is consistent and one sign test decides "inside". */
      function distanceToQuad(px, py, quad) {
        let inside = true;
        for (let i = 0; i < 4; i += 1) {
          const [ax, ay] = quad[i];
          const [bx, by] = quad[(i + 1) % 4];
          if ((bx - ax) * (py - ay) - (by - ay) * (px - ax) < 0) {
            inside = false;
            break;
          }
        }
        if (inside) return 0;
        let nearest = Infinity;
        for (let i = 0; i < 4; i += 1) {
          const [ax, ay] = quad[i];
          const [bx, by] = quad[(i + 1) % 4];
          const dx = bx - ax;
          const dy = by - ay;
          const squared = dx * dx + dy * dy;
          let t = squared ? ((px - ax) * dx + (py - ay) * dy) / squared : 0;
          t = Math.max(0, Math.min(1, t));
          nearest = Math.min(nearest, Math.hypot(px - (ax + t * dx), py - (ay + t * dy)));
        }
        return nearest;
      }

      const total = motif.getTotalLength();
      const steps = Math.max(1, Math.ceil(total / sampleStep));
      const step = total / steps;
      const samples = [];
      for (let i = 0; i <= steps; i += 1) {
        const point = motif.getPointAtLength(i * step);
        samples.push([point.x, point.y, i * step]);
      }

      const measured = blocks.map((block) => {
        let nearest = Infinity;
        let at = 0;
        let where = null;
        for (const [x, y, along] of samples) {
          const distance = distanceToQuad(x, y, block.quad);
          if (distance < nearest) {
            nearest = distance;
            at = along;
            where = [x, y];
          }
        }
        let window = step;
        for (let round = 0; round < refinements; round += 1) {
          for (const along of [at - window, at + window]) {
            if (along < 0 || along > total) continue;
            const point = motif.getPointAtLength(along);
            const distance = distanceToQuad(point.x, point.y, block.quad);
            if (distance < nearest) {
              nearest = distance;
              at = along;
              where = [point.x, point.y];
            }
          }
          window /= 2;
        }
        return {
          text: block.text,
          size: block.size,
          box: block.box,
          clearance: nearest - strokeWidth / 2,
          nearestPoint: where,
        };
      });
      return { strokeWidth, pathLength: total, blocks: measured };
    },
    FACE_CSS,
    SAMPLE_STEP,
    REFINEMENTS
  );
}

/** Re-measures every advance `typeface.py` claims, in the same face. */
async function measureAdvances(page, declared) {
  return page.evaluate(
    async (table, weights) => {
      await Promise.all(weights.map((weight) => document.fonts.load(`${weight} 100px Archivo`)));
      await document.fonts.ready;
      const canvas = document.createElementNS('http://www.w3.org/1999/xhtml', 'canvas');
      const context = canvas.getContext('2d');
      const drifted = [];
      for (const [character, byWeight] of Object.entries(table)) {
        for (const [weight, claimed] of Object.entries(byWeight)) {
          context.font = `${weight} 100px Archivo`;
          const measured = context.measureText(character).width / 100;
          drifted.push({ character, weight: Number(weight), claimed, measured });
        }
      }
      return drifted;
    },
    declared.em,
    [declared.light, declared.heavy]
  );
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const manifest = JSON.parse(await readFile(path.join(args.fixtures, 'manifest.json'), 'utf8'));
  if (!Array.isArray(manifest) || manifest.length === 0) {
    throw new Error(`manifest.json at ${args.fixtures} is empty or malformed`);
  }
  const declared = JSON.parse(await readFile(path.join(args.fixtures, 'advances.json'), 'utf8'));

  const server = await serveStatic(args.fixtures);
  const { port } = server.address();
  const baseUrl = `http://127.0.0.1:${port}/`;

  let browser;
  const results = [];
  let advances = [];
  try {
    browser = await puppeteer.launch({ headless: true });
    for (const entry of manifest) {
      const page = await browser.newPage();
      try {
        await page.setViewport({
          width: Math.round(entry.width),
          height: Math.round(entry.height),
        });
        await page.goto(`${baseUrl}${entry.file}`, { waitUntil: 'networkidle0', timeout: 30_000 });
        results.push({ ...entry, ...(await measureTemplate(page)) });
      } finally {
        await page.close();
      }
    }
    const page = await browser.newPage();
    try {
      await page.goto(`${baseUrl}${manifest[0].file}`, { waitUntil: 'networkidle0' });
      await page.evaluate((faceCss) => {
        const style = document.createElementNS('http://www.w3.org/2000/svg', 'style');
        style.textContent = faceCss;
        document.documentElement.insertBefore(style, document.documentElement.firstChild);
      }, FACE_CSS);
      advances = await measureAdvances(page, declared);
    } finally {
      await page.close();
    }
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  if (args.report) {
    await writeFile(args.report, `${JSON.stringify({ results, advances }, null, 2)}\n`);
  }

  let failed = false;
  for (const result of results) {
    const worst = result.blocks.reduce((a, b) => (a.clearance <= b.clearance ? a : b));
    console.log(
      `templates: ${result.name} -- ${result.blocks.length} block(s) of type, ` +
        `stroke ${result.strokeWidth}, closest ${worst.clearance.toFixed(1)} units ` +
        `(${JSON.stringify(worst.text.slice(0, 40))})`
    );
    for (const block of result.blocks) {
      if (block.clearance >= MINIMUM_CLEARANCE) continue;
      failed = true;
      const [x, y, w, h] = block.box;
      console.log(
        `::error::${result.name} -- the motif crosses ${JSON.stringify(block.text.slice(0, 60))}: ` +
          `the stroke's painted edge reaches ${(-block.clearance).toFixed(1)} units into a block ` +
          `set at ${block.size} and inking x[${x.toFixed(1)}-${(x + w).toFixed(1)}] ` +
          `y[${y.toFixed(1)}-${(y + h).toFixed(1)}]. Nearest point on the stroke: ` +
          `(${block.nearestPoint[0].toFixed(1)}, ${block.nearestPoint[1].toFixed(1)}).`
      );
    }
  }

  for (const entry of advances) {
    const drift = entry.claimed - entry.measured;
    if (drift >= 0 && drift <= ADVANCE_ROUNDING) continue;
    failed = true;
    console.log(
      `::error::typeface.py claims ${JSON.stringify(entry.character)} advances ` +
        `${entry.claimed} em at weight ${entry.weight}; this font file gives ` +
        `${entry.measured.toFixed(4)}. A table entry must sit between the measurement ` +
        `and ${ADVANCE_ROUNDING} em above it -- re-measure the table against the font ` +
        'beside it rather than adjusting this tolerance.'
    );
  }
  console.log(`templates: re-measured ${advances.length} advance(s) against the committed face`);

  if (failed) {
    process.exitCode = 1;
  } else {
    console.log(
      `templates: no stroke crosses any word, in ${results.length} rendering(s) of ` +
        'every template at every charter and every family'
    );
  }
}

await main();
