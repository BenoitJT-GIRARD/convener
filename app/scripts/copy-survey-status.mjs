/* Publishes `../../public-data/survey-status.json` into
 * `public/survey-status.json`, for `src/survey/SurveyForm.tsx` to fetch at
 * runtime -- R-37 (fix round 1, task 16): the survey switch, published as
 * an operational fact rather than left unreachable by the browser (see
 * `tools/convener_ops/cli.py::survey_status_public_data`'s own docstring for
 * why this is a second file rather than folded into `events-public.json`).
 * Ships as part of the app's own built output (`dist/survey-status.json`)
 * the identical way `copy-certificates.mjs` publishes `certificates.json`
 * -- this file is that script's own twin, cut down to its shape.
 *
 * `public-data/survey-status.json` itself is CI-generated, gitignored
 * output (`uv run convener-survey-status-public-data`, see
 * `.github/workflows/deploy.yml`'s "Build survey status" step) -- not
 * committed source, so it will not exist for a plain local `npm run dev`
 * or `npm run build` unless that command was run first. An absent source
 * is a normal state here, not an error: it produces an empty projection
 * (`[]`), which SurveyForm.tsx reads as "no event has an open survey" --
 * the fail-closed direction R-37 asks for, never a build failure.
 *
 * The actual write (`writeProjection`) and the destination directory
 * (`PUBLIC_DIR`) both live in `survey-status-projection.mjs`, not here --
 * this file is a thin wrapper around them so
 * `app/tests/copy-survey-status.test.ts` can run the real write against a
 * temporary directory without triggering this file's own side effect.
 *
 * Runs before `vite dev` and `vite build`, alongside the other copy
 * scripts.
 */
import { relative, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PUBLIC_DIR, writeProjection } from './survey-status-projection.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(__dirname, '..', '..', 'public-data', 'survey-status.json');

const { ids, dest } = await writeProjection(SRC, PUBLIC_DIR);

console.log(
  `copy-survey-status: published ${ids.length} event(s) with the survey open -> ${relative(process.cwd(), dest)}`,
);
