/* The pinned render step and its image comparison.
 *
 * The argument for it, restated because it is the reason this file exists:
 * "a picture comparison that gets regenerated every time it fails is not a
 * check -- it is D-25 in slow motion." Pinning the engine is not a belt
 * beside a brace; it is what gives a red result its meaning -- "the visual
 * changed", never "the runner changed". `puppeteer` (full, this package's
 * one dependency, isolated here rather than added to `site/package.json`
 * so its ~430MB Chrome-for-Testing download is paid for only by the one
 * job that needs it, a footprint measured rather than
 * estimated) downloads a Chromium build pinned by this package's
 * own committed lockfile: the same input renders matching output on every
 * machine that installs this exact lock, within the tolerance this file's
 * own comparison already carries for ordinary anti-aliasing noise
 * (`PER_CHANNEL_THRESHOLD`, `MAX_DIFF_PIXEL_FRACTION` below) -- not
 * "byte-identical" stated flatly. Measured,
 * not assumed, and the two are not the same claim. `BANNER` -- the one
 * format this project actually diffs byte-for-byte with zero tolerance
 * (`site/src/banners/<event id>.png`, `visuals-production.yml`'s own
 * `git diff --staged --quiet` gate) -- showed zero drift across repeated
 * runs against the committed reference. `PRINT` (never committed, only
 * ever compared through the tolerance below) showed a reproducible
 * single-level anti-aliasing shift against the committed reference across
 * three separate runs -- comfortably inside that tolerance, and exactly
 * the class of run-to-run rasteriser noise it exists to absorb, not
 * evidence it is papering over a real design difference. `puppeteer-core`
 * (the accessibility checker's own dependency, deliberately bundling
 * nothing) cannot promise even this much -- it hands rendering to
 * whatever Chrome happens to already be on the machine it runs on.
 *
 * What this script does, in order
 * ----------------------------------
 * 1. Reads `manifest.json` from a fixtures directory that
 *    `convener-render-visual-fixtures` (Python, `tools/convener_ops/cli.py`) already
 *    wrote -- one HTML page per named format (`formats.FORMATS`), plus a
 *    copy of the repository's self-hosted `fonts/` beside them. This
 *    script never re-derives a page's own markup in JavaScript: D-14's own
 *    shape applied to a language boundary this project had not crossed
 *    before -- the *fixture* (the manifest) is shared, not the code that
 *    produces a page.
 * 2. Serves that directory over a local, ephemeral HTTP server -- never
 *    `file://`. A `file://` origin cannot load a relative `@font-face url`
 *    without `--allow-file-access-from-files` (a flag this project has no
 *    reason to carry), and every earlier render of this composition
 *    already used a local server for exactly that reason.
 * 3. Launches this package's own pinned Chromium and screenshots each
 *    named format at its own real pixel size, waiting for the self-hosted
 *    webfonts to finish loading (`document.fonts.ready`) before the
 *    screenshot -- otherwise a race between the font request and the
 *    capture could render a fallback face on a slow run and the real one
 *    on a fast one, which is exactly the kind of run-to-run instability
 *    that would make this comparison meaningless before a single design
 *    change is even in question.
 * 4. Compares each screenshot against `references/<name>.png`, a versioned
 *    image already committed to this repository. Decoded through the
 *    *browser's own* `<canvas>`/`getImageData` -- no image-diffing
 *    dependency was added for this (no `pixelmatch`, no `pngjs`): the
 *    engine already pinned to render is the same engine asked to
 *    decode both PNGs, so nothing new was installed to make the
 *    comparison possible at all.
 * 5. Fails loudly on a regression -- see PER_CHANNEL_THRESHOLD and
 *    MAX_DIFF_PIXEL_FRACTION below for what "regression" means and why,
 *    and `reportOutcome` for what gets printed: which format, how many
 *    pixels differed, the worst single-channel delta found, and a
 *    bounding box of where they cluster -- "naming what differs and
 *    where", not merely "different".
 *
 * `--update` (only ever run by a human, never by CI -- `visuals.yml` never
 * passes it) overwrites `references/<name>.png` with the current render
 * instead of comparing against it, for a deliberate, reviewed design
 * change. Every other invocation only ever reads the references directory.
 */

import { createServer } from 'node:http';
import { readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Per-channel (R, G, B or A, each 0-255) absolute difference below which
 *  a pixel is not counted as "different" at all.
 *
 *  Anti-aliasing is what this has to tolerate: the exact fraction of a
 *  pixel a glyph edge or the ribbon's curved stroke covers depends on
 *  sub-pixel positioning decisions the rasteriser makes, and those can
 *  shift by a level or two between two runs that agree on every design
 *  decision -- the self-hosted webfont fixes *which* glyph outlines are
 *  used, not how a rasteriser blends one partially-
 *  covered edge pixel against its background. 24 is comfortably above
 *  that kind of single-digit blending noise (confirmed empirically: two
 *  renders of this exact fixture on this machine, nothing changed between
 *  them, differ by exactly 0 pixels at any threshold) and comfortably
 *  below the smallest gap
 *  between any two colours this composition actually paints next to each
 *  other -- `instance/data/brand.json`'s own palette (purple #012765, cream
 *  #F4F0F1, turquoise #FECAC1, white, black) differs by dozens to
 *  hundreds of levels per channel between any pair, so a real colour
 *  swap, a moved element revealing a different background underneath it,
 *  or a moved element's own edge crossing into new territory clears this
 *  threshold by a wide margin -- proven against a real five-pixel
 *  translation, not assumed.
 */
const PER_CHANNEL_THRESHOLD = 24;

/** The fraction of a canvas's total pixels that may exceed
 *  PER_CHANNEL_THRESHOLD before this script calls the format a regression.
 *
 *  Anti-aliasing only ever touches a thin halo of pixels along an edge --
 *  a glyph's outline, the ribbon's stroke, the photo frame's border --
 *  never a filled region's own interior, so even a page dense with text
 *  and curves only ever has a small fraction of its total area sitting on
 *  such an edge at all. 0.001 (0.1%) is the same order of magnitude
 *  several established visual-regression tools default to (BackstopJS's
 *  own `misMatchThreshold`, for one) for exactly this reason. Moving a
 *  real element -- this project's own proof, not a hypothetical -- shifts
 *  a filled region's own boundary across a much larger area than an
 *  anti-aliasing halo ever occupies, and clears this budget by well over
 *  an order of magnitude, measured rather than estimated.
 */
const MAX_DIFF_PIXEL_FRACTION = 0.001;

function parseArgs(argv) {
  const args = { fixtures: undefined, references: undefined, actual: undefined, update: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--fixtures') args.fixtures = argv[++i];
    else if (arg === '--references') args.references = argv[++i];
    else if (arg === '--actual') args.actual = argv[++i];
    else if (arg === '--update') args.update = true;
    else throw new Error(`unrecognised argument: ${arg}`);
  }
  if (!args.fixtures) {
    throw new Error(
      '--fixtures DIR is required -- the directory convener-render-visual-fixtures wrote ' +
        '(manifest.json, one *.html per named format, a copy of fonts/)'
    );
  }
  args.fixtures = path.resolve(args.fixtures);
  args.references = path.resolve(args.references || path.join(__dirname, 'references'));
  if (args.actual) args.actual = path.resolve(args.actual);
  return args;
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.woff2': 'font/woff2',
};

/** A static file server with no dependency of its own -- the same idiom
 *  `site/scripts/check-a11y.mjs`'s own `serveStatic` already uses, small
 *  enough in both places that sharing it across two otherwise-unrelated
 *  npm packages (this one has no other reason to depend on `site/`) would
 *  cost more than it saves. Listens on an OS-assigned port so nothing here
 *  can collide with a port already busy on a shared runner. */
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

/** Decodes two PNG buffers and diffs them, entirely inside the same pinned
 *  browser already launched to render them -- see the module
 *  comment for why this needed no new dependency. Runs inside the page
 *  (`page.evaluate`) rather than serialising the raw pixel arrays back to
 *  Node: a 1200x1200 RGBA buffer is ~5.7MB, and returning only the small
 *  summary below keeps this fast and keeps CDP's own message size out of
 *  the question entirely. */
async function diffAgainstReference(page, actualPngBuffer, referencePngBuffer) {
  const actualDataUrl = `data:image/png;base64,${actualPngBuffer.toString('base64')}`;
  const referenceDataUrl = `data:image/png;base64,${referencePngBuffer.toString('base64')}`;
  return page.evaluate(
    async (actualSrc, referenceSrc, perChannelThreshold, maxDiffFraction) => {
      function loadImage(src) {
        return new Promise((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve(img);
          img.onerror = () => reject(new Error('failed to decode a PNG for comparison'));
          img.src = src;
        });
      }
      const [actualImg, referenceImg] = await Promise.all([
        loadImage(actualSrc),
        loadImage(referenceSrc),
      ]);
      if (
        actualImg.naturalWidth !== referenceImg.naturalWidth ||
        actualImg.naturalHeight !== referenceImg.naturalHeight
      ) {
        return {
          dimensionMismatch: true,
          actualSize: { width: actualImg.naturalWidth, height: actualImg.naturalHeight },
          referenceSize: { width: referenceImg.naturalWidth, height: referenceImg.naturalHeight },
        };
      }
      const width = actualImg.naturalWidth;
      const height = actualImg.naturalHeight;
      function pixelsOf(img) {
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        ctx.drawImage(img, 0, 0);
        return ctx.getImageData(0, 0, width, height).data;
      }
      const actualPixels = pixelsOf(actualImg);
      const referencePixels = pixelsOf(referenceImg);

      let diffCount = 0;
      let maxDelta = 0;
      let minX = width;
      let minY = height;
      let maxX = -1;
      let maxY = -1;
      const samples = [];
      for (let y = 0; y < height; y += 1) {
        for (let x = 0; x < width; x += 1) {
          const i = (y * width + x) * 4;
          const dr = Math.abs(actualPixels[i] - referencePixels[i]);
          const dg = Math.abs(actualPixels[i + 1] - referencePixels[i + 1]);
          const db = Math.abs(actualPixels[i + 2] - referencePixels[i + 2]);
          const da = Math.abs(actualPixels[i + 3] - referencePixels[i + 3]);
          const delta = Math.max(dr, dg, db, da);
          if (delta > maxDelta) maxDelta = delta;
          if (delta > perChannelThreshold) {
            diffCount += 1;
            if (x < minX) minX = x;
            if (y < minY) minY = y;
            if (x > maxX) maxX = x;
            if (y > maxY) maxY = y;
            if (samples.length < 5) {
              samples.push({
                x,
                y,
                actual: [actualPixels[i], actualPixels[i + 1], actualPixels[i + 2], actualPixels[i + 3]],
                reference: [
                  referencePixels[i],
                  referencePixels[i + 1],
                  referencePixels[i + 2],
                  referencePixels[i + 3],
                ],
              });
            }
          }
        }
      }
      const totalPixels = width * height;
      const diffFraction = diffCount / totalPixels;
      return {
        dimensionMismatch: false,
        width,
        height,
        totalPixels,
        diffCount,
        diffFraction,
        maxDelta,
        boundingBox: diffCount > 0 ? { minX, minY, maxX, maxY } : null,
        samples,
        regression: diffFraction > maxDiffFraction,
      };
    },
    actualDataUrl,
    referenceDataUrl,
    PER_CHANNEL_THRESHOLD,
    MAX_DIFF_PIXEL_FRACTION
  );
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const manifest = JSON.parse(
    await readFile(path.join(args.fixtures, 'manifest.json'), 'utf8')
  );
  if (!Array.isArray(manifest) || manifest.length === 0) {
    throw new Error(`manifest.json at ${args.fixtures} is empty or malformed`);
  }

  if (args.actual) await mkdir(args.actual, { recursive: true });
  await mkdir(args.references, { recursive: true });

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
        await page.setViewport({ width: entry.width, height: entry.height });
        await page.goto(`${baseUrl}${entry.file}`, { waitUntil: 'networkidle0', timeout: 30_000 });
        await page.evaluate(() => document.fonts.ready);
        const png = await page.screenshot({ type: 'png' });

        if (args.actual) {
          await writeFile(path.join(args.actual, `${entry.name}.png`), png);
        }

        const referencePath = path.join(args.references, `${entry.name}.png`);
        if (args.update) {
          await writeFile(referencePath, png);
          results.push({ name: entry.name, updated: true });
          continue;
        }
        if (!existsSync(referencePath)) {
          results.push({
            name: entry.name,
            missingReference: true,
          });
          continue;
        }
        const referencePng = await readFile(referencePath);
        const diff = await diffAgainstReference(page, png, referencePng);
        results.push({ name: entry.name, ...diff });
      } finally {
        await page.close();
      }
    }
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  if (args.update) {
    for (const result of results) {
      console.log(`visuals: wrote ${result.name}.png as the new reference`);
    }
    return;
  }

  let failed = false;
  for (const result of results) {
    if (result.missingReference) {
      failed = true;
      console.log(
        `::error::${result.name} -- no reference image at ${path.join(args.references, `${result.name}.png`)}. ` +
          'Run `npm run update-references` by hand and commit the result only after reviewing it -- ' +
          'this script never creates one on its own (D-25: a check that supplies its own missing baseline cannot fail).'
      );
      continue;
    }
    if (result.dimensionMismatch) {
      failed = true;
      console.log(
        `::error::${result.name} -- size changed: rendered ${result.actualSize.width}x${result.actualSize.height}, ` +
          `reference is ${result.referenceSize.width}x${result.referenceSize.height}`
      );
      continue;
    }
    if (result.regression) {
      failed = true;
      const pct = (result.diffFraction * 100).toFixed(4);
      console.log(
        `::error::${result.name} -- ${result.diffCount} of ${result.totalPixels} pixels ` +
          `(${pct}%) differ by more than ${PER_CHANNEL_THRESHOLD} on some channel, ` +
          `above the ${(MAX_DIFF_PIXEL_FRACTION * 100).toFixed(2)}% budget. ` +
          `Worst single-channel delta: ${result.maxDelta}. ` +
          `Bounding box of differing pixels: x[${result.boundingBox.minX}-${result.boundingBox.maxX}] ` +
          `y[${result.boundingBox.minY}-${result.boundingBox.maxY}].`
      );
      for (const sample of result.samples) {
        console.log(
          `::error::${result.name} -- pixel (${sample.x}, ${sample.y}): ` +
            `rendered rgba(${sample.actual.join(',')}), reference rgba(${sample.reference.join(',')})`
        );
      }
    } else {
      console.log(
        `visuals: ${result.name} matches its reference ` +
          `(${result.diffCount} of ${result.totalPixels} pixel(s) over threshold, ` +
          `worst delta ${result.maxDelta})`
      );
    }
  }

  if (failed) {
    process.exitCode = 1;
  } else {
    console.log('visuals: every rendered format matches its versioned reference');
  }
}

await main();
