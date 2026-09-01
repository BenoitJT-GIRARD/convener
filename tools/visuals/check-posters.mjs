/* Does the charter's drawing cross anything on the poster the cockpit
 * generates? Measured, on the pinned engine, for every charter this
 * repository holds crossed with every family it draws crossed with every
 * canvas it renders.
 *
 * Why this file exists
 * ---------------------
 * `render-and-compare.mjs` beside it renders the same composition and
 * compares its pixels -- but at **one** charter, the example's, at three
 * canvases, because that is what a pinned reference image can be. It is
 * deliberately blind to a duplicate's own charter (`visuals.yml`'s own
 * path filter, and `test_visuals_workflow.py` holds it there), and it
 * could not sweep a cross product without either pinning ninety images or
 * comparing none.
 *
 * `check-templates.mjs` beside it *does* sweep the cross product -- of the
 * three files a volunteer downloads. The poster the cockpit generates for
 * each event is not one of them, and it is the composition every
 * duplicate actually publishes.
 *
 * So the assumption this measures had nothing measuring it.
 * `visual._motif_content_right_margin` pads `.content` -- the "what to
 * expect" copy and the speaker's photographic plate -- with the family's
 * own clearance rather than with its right-hand reach, on an argument
 * about where the ribbon's right side runs. That argument is true of the
 * ribbon and of the bracket, and it is an argument about two drawings
 * rather than a property of any: a family with a deep right-hand drawing
 * would paint across the speaker's frame in every duplicate's poster with
 * every gate green. Every drawing this product ships is short on the
 * right; until this, that was a coincidence rather than a rule.
 *
 * What it measures, exactly
 * --------------------------
 * For each fixture `convener-render-poster-fixtures` wrote, at that
 * fixture's own viewport:
 *
 * 1. Every line of type, as the browser laid it out -- one client
 *    rectangle per line box, taken from a `Range` over each text node
 *    rather than from the elements, so a paragraph that wrapped into four
 *    lines is four rectangles and not one block covering ground it never
 *    inks.
 * 2. Every plate the composition places: the speaker's photographic frame,
 *    the registration code's slot, the wordmark's own device.
 * 3. The motif's own path, sampled along its length and mapped into the
 *    page's own pixels, and the distance from each sample to each
 *    rectangle, less half the painted stroke. Negative means the drawing
 *    is on top of the words -- which it is painted to be (`.motif-overlay`
 *    is the last element in the document on purpose), and which is exactly
 *    why nothing was ever going to notice.
 *
 * A line box is read as the browser laid it out, leading and all, which
 * is a little more than the ink and errs toward reporting a collision --
 * the safe direction for a check whose job is to refuse a family nobody
 * has drawn yet. A plate is not: the frame is rotated six degrees, and
 * its upright bounding rectangle reaches most of a stroke past its own
 * corner, which is enough to report a collision against a drawing running
 * down the canvas edge beside it and never touching it. So plates are
 * read through `getBoxQuads`, as the quadrilaterals they occupy. The
 * clearance every block achieves is printed, so a margin that is merely
 * thin is visible without being fatal.
 *
 * What it found on its first run: at this instance's own charter, its own
 * family and the square canvas its own forum gets, the ribbon's right
 * loop was painted **14.4 pixels across the speaker's plate**, and 29.8
 * across it on the print -- at every charter under `assets/brand/` besides,
 * because the reach belongs to the family and every charter can name it.
 * Nothing had ever rendered that combination.
 *
 * Usage, from `tools/visuals/`:
 *
 *     node check-posters.mjs --fixtures DIR [--report FILE]
 */

import { createServer } from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer';

/** How close the painted edge of the drawing may come to a line of type or
 *  to a plate, in the page's own pixels.
 *
 *  Zero, and for the reason `check-templates.mjs` gives for its own: the
 *  clearance each family keeps is the family's to declare
 *  (`motifs.CLEARANCE_STROKE_WIDTHS`), and a second, larger number here
 *  would be this file inventing a design rule on top of it. */
const MINIMUM_CLEARANCE = 0;

/** How far apart the samples along the motif's path are, in the path's own
 *  user units, before the search is refined -- and how many times the
 *  nearest approach is then bisected. The same numbers
 *  `check-templates.mjs` uses, for the same reason: the coarse pass only
 *  has to find the right neighbourhood. */
const SAMPLE_STEP = 4;
const REFINEMENTS = 10;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.woff2': 'font/woff2',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
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
      '--fixtures DIR is required -- the directory convener-render-poster-fixtures ' +
        'wrote (manifest.json, one *.html per charter, family and format, a copy of fonts/)'
    );
  }
  args.fixtures = path.resolve(args.fixtures);
  if (args.report) args.report = path.resolve(args.report);
  return args;
}

/** The same dependency-free static server the two checkers beside this one
 *  use, and for the same reason: a `file://` origin cannot load a relative
 *  `@font-face url` without a flag this project has no reason to carry. */
function serveStatic(root) {
  return new Promise((resolve) => {
    const server = createServer(async (req, res) => {
      try {
        const decoded = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        const filePath = path.join(root, decoded);
        if (!filePath.startsWith(root) || !existsSync(filePath)) {
          res.writeHead(404);
          res.end('not found');
          return;
        }
        res.writeHead(200, {
          'content-type': MIME[path.extname(filePath)] || 'application/octet-stream',
        });
        res.end(await readFile(filePath));
      } catch (err) {
        res.writeHead(500);
        res.end(String(err));
      }
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

/** Every block on one rendered poster, with its clearance from the motif's
 *  own painted edge. Runs entirely inside the page. */
async function measurePoster(page) {
  return page.evaluate(
    async (sampleStep, refinements) => {
      await document.fonts.ready;

      const overlay = document.querySelector('.motif-overlay');
      if (!overlay) throw new Error('no .motif-overlay in this poster');
      const motif = overlay.querySelector('path');
      if (!motif) throw new Error('the motif overlay carries no path');
      const strokeWidth = parseFloat(motif.getAttribute('stroke-width'));
      const matrix = motif.getScreenCTM();
      // One user unit of the drawing, in the page's own pixels: the
      // overlay is stretched over the whole poster, so the stroke's
      // painted width has to be scaled the same way its geometry is.
      const scale = Math.sqrt(Math.abs(matrix.a * matrix.d - matrix.b * matrix.c));
      if (!Number.isFinite(strokeWidth) || !(scale > 0)) {
        throw new Error('the motif carries no stroke width, or no usable matrix');
      }

      const blocks = [];
      const asQuad = (rect) => [
        [rect.x, rect.y],
        [rect.x + rect.width, rect.y],
        [rect.x + rect.width, rect.y + rect.height],
        [rect.x, rect.y + rect.height],
      ];
      const bounds = (quad) => {
        const xs = quad.map(([x]) => x);
        const ys = quad.map(([, y]) => y);
        return [
          Math.min(...xs),
          Math.min(...ys),
          Math.max(...xs) - Math.min(...xs),
          Math.max(...ys) - Math.min(...ys),
        ];
      };

      // Every line of type. A `Range` over a text node reports one
      // rectangle per line box, which is what makes a paragraph that
      // wrapped four times four blocks rather than one.
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) =>
          node.textContent.trim() && node.parentElement.closest('svg') === null
            ? NodeFilter.FILTER_ACCEPT
            : NodeFilter.FILTER_REJECT,
      });
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const range = document.createRange();
        range.selectNodeContents(node);
        for (const rect of range.getClientRects()) {
          if (rect.width <= 0 || rect.height <= 0) continue;
          blocks.push({
            text: node.textContent.split(/\s+/).join(' ').trim().slice(0, 60),
            kind: 'type',
            quad: asQuad(rect),
          });
        }
      }
      // Every plate, as the quadrilateral it actually occupies.
      // `getBoxQuads` respects the transform, and the frame is rotated six
      // degrees: its upright bounding rectangle reaches most of a stroke's
      // width past its own corner, which is enough to report a collision
      // against a drawing that runs down the canvas edge beside it and
      // never touches it.
      const origin = document.documentElement.getBoundingClientRect();
      for (const selector of ['.frame', '.registration-code-slot', '.wordmark-logo']) {
        for (const element of document.querySelectorAll(selector)) {
          const quads = element.getBoxQuads
            ? element.getBoxQuads({ relativeTo: document.documentElement, box: 'border' })
            : [];
          const quad = quads.length
            ? [quads[0].p1, quads[0].p2, quads[0].p3, quads[0].p4].map((point) => [
                point.x + origin.x,
                point.y + origin.y,
              ])
            : asQuad(element.getBoundingClientRect());
          const [, , width, height] = bounds(quad);
          if (width <= 0 || height <= 0) continue;
          blocks.push({ text: selector, kind: 'plate', quad });
        }
      }

      /** Distance from a point to a convex quadrilateral, zero inside it.
       *  The same arithmetic `check-templates.mjs` uses on the tilted plate
       *  in the downloadable templates, for the same reason. */
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
      const at = (along) => {
        const point = motif.getPointAtLength(along);
        return point.matrixTransform(matrix);
      };
      const samples = [];
      for (let i = 0; i <= steps; i += 1) {
        const point = at(i * step);
        samples.push([point.x, point.y, i * step]);
      }

      const measured = blocks.map((block) => {
        let nearest = Infinity;
        let along = 0;
        let where = null;
        for (const [x, y, distance] of samples) {
          const gap = distanceToQuad(x, y, block.quad);
          if (gap < nearest) {
            nearest = gap;
            along = distance;
            where = [x, y];
          }
        }
        let window = step;
        for (let round = 0; round < refinements; round += 1) {
          for (const candidate of [along - window, along + window]) {
            if (candidate < 0 || candidate > total) continue;
            const point = at(candidate);
            const gap = distanceToQuad(point.x, point.y, block.quad);
            if (gap < nearest) {
              nearest = gap;
              along = candidate;
              where = [point.x, point.y];
            }
          }
          window /= 2;
        }
        return {
          text: block.text,
          kind: block.kind,
          box: bounds(block.quad),
          clearance: nearest - (strokeWidth * scale) / 2,
          nearestPoint: where,
        };
      });
      return { strokeWidth: strokeWidth * scale, pathLength: total, blocks: measured };
    },
    SAMPLE_STEP,
    REFINEMENTS
  );
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const manifest = JSON.parse(await readFile(path.join(args.fixtures, 'manifest.json'), 'utf8'));
  if (!Array.isArray(manifest) || manifest.length === 0) {
    throw new Error(`manifest.json at ${args.fixtures} is empty or malformed`);
  }

  const server = await serveStatic(args.fixtures);
  const { port } = server.address();
  const baseUrl = `http://127.0.0.1:${port}/`;

  let browser;
  const results = [];
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
        results.push({ ...entry, ...(await measurePoster(page)) });
      } finally {
        await page.close();
      }
    }
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  if (args.report) {
    await writeFile(args.report, `${JSON.stringify({ results }, null, 2)}\n`);
  }

  let failed = false;
  for (const result of results) {
    const worst = result.blocks.reduce((a, b) => (a.clearance <= b.clearance ? a : b));
    console.log(
      `posters: ${result.name} -- ${result.blocks.length} block(s), stroke ` +
        `${result.strokeWidth.toFixed(1)}, closest ${worst.clearance.toFixed(1)} px ` +
        `(${JSON.stringify(worst.text)})`
    );
    for (const block of result.blocks) {
      if (block.clearance >= MINIMUM_CLEARANCE) continue;
      failed = true;
      const [x, y, w, h] = block.box;
      console.log(
        `::error::${result.name} -- the ${result.family} motif crosses ` +
          `${JSON.stringify(block.text)}: the stroke's painted edge reaches ` +
          `${(-block.clearance).toFixed(1)} px into a ${block.kind} occupying ` +
          `x[${x.toFixed(1)}-${(x + w).toFixed(1)}] y[${y.toFixed(1)}-${(y + h).toFixed(1)}]. ` +
          `Nearest point on the stroke: (${block.nearestPoint[0].toFixed(1)}, ` +
          `${block.nearestPoint[1].toFixed(1)}).`
      );
    }
  }

  if (failed) {
    process.exitCode = 1;
  } else {
    const blocks = results.reduce((total, result) => total + result.blocks.length, 0);
    console.log(
      `posters: no stroke crosses any line of type or any plate, in ` +
        `${results.length} rendering(s) of the generated poster at every charter, ` +
        `every family and every canvas (${blocks} block(s) measured)`
    );
  }
}

await main();
