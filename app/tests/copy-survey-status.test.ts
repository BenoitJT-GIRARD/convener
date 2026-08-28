import { afterEach, describe, expect, it } from 'vitest';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  DEST_FILENAME,
  PUBLIC_DIR,
  readProjection,
  writeProjection,
} from '../scripts/survey-status-projection.mjs';
import { SURVEY_STATUS_FILENAME } from '../src/survey/surveyStatus';

// This suite exercises real filesystem paths under a temp directory, never
// the app's own `public/survey-status.json` -- `copy-survey-status.mjs`
// itself is never imported here, the same reason
// `copy-certificates.test.ts` never imports `copy-certificates.mjs`: a
// top-level script has side effects the moment it is imported.

const REAL_PROJECTION = ['mrg-05', 'mrg-12'];

// app/tests/.. = app/
const APP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

describe('PUBLIC_DIR is the exact directory the survey island fetches from', () => {
  it('resolves to app/public, independent of cwd', () => {
    expect(PUBLIC_DIR).toBe(resolve(APP_ROOT, 'public'));
  });
});

describe('the filename copy-survey-status.mjs writes and the survey island fetches -- two literals, pinned equal, not one shared import', () => {
  it('pins scripts/survey-status-projection.mjs::DEST_FILENAME to src/survey/surveyStatus.ts::SURVEY_STATUS_FILENAME', () => {
    // Not one shared import -- survey-status-projection.mjs reaches into
    // node:fs, node:path and node:url, none of which exist in a browser
    // bundle, so the island cannot import this module directly. Before
    // this test, either constant could be renamed alone and every other
    // test in this suite (and survey-island.test.tsx's own) stayed green:
    // the build would still publish under the old name, the page would
    // still fetch under the new one, both would 404, and the survey
    // switch would read as closed for every event, forever, with nothing
    // turning red anywhere.
    expect(DEST_FILENAME).toBe(SURVEY_STATUS_FILENAME);
  });
});

describe('readProjection', () => {
  let dir: string;

  afterEach(async () => {
    if (dir) await rm(dir, { recursive: true, force: true });
  });

  it('returns [] when instance/public-data/survey-status.json does not exist -- a normal state, no event enabled yet', async () => {
    expect(
      await readProjection(join(tmpdir(), 'convener-survey-status-test-does-not-exist.json')),
    ).toEqual([]);
  });

  it('returns [] for unparsable content rather than throwing', async () => {
    dir = await mkdtemp(join(tmpdir(), 'convener-survey-status-'));
    const path = join(dir, 'survey-status.json');
    await writeFile(path, 'not json at all');
    expect(await readProjection(path)).toEqual([]);
  });

  it('returns [] for valid JSON that is not an array -- fail closed, not a guess', async () => {
    dir = await mkdtemp(join(tmpdir(), 'convener-survey-status-'));
    const path = join(dir, 'survey-status.json');
    await writeFile(path, JSON.stringify({ enabled: REAL_PROJECTION }));
    expect(await readProjection(path)).toEqual([]);
  });

  it('round-trips the real, bare-array projection unchanged', async () => {
    dir = await mkdtemp(join(tmpdir(), 'convener-survey-status-'));
    const path = join(dir, 'survey-status.json');
    await writeFile(path, JSON.stringify(REAL_PROJECTION));

    expect(await readProjection(path)).toEqual(REAL_PROJECTION);
  });
});

describe('writeProjection -- the real write, run against a temporary tree', () => {
  let root: string;

  afterEach(async () => {
    if (root) await rm(root, { recursive: true, force: true });
  });

  it('writes to <dstDir>/<DEST_FILENAME> with no extra nesting -- the exact path SurveyForm.tsx fetches, relative to BASE', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-survey-status-write-'));
    const src = join(root, 'survey-status.json');
    await writeFile(src, JSON.stringify(REAL_PROJECTION));
    const dstDir = join(root, 'public');

    const { ids, dest } = await writeProjection(src, dstDir);

    expect(relative(dstDir, dest)).toBe(DEST_FILENAME);
    expect(ids).toEqual(REAL_PROJECTION);
  });

  it('creates dstDir when it does not exist yet', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-survey-status-write-'));
    const src = join(root, 'survey-status.json');
    await writeFile(src, JSON.stringify(REAL_PROJECTION));
    const dstDir = join(root, 'public', 'nested', 'once', 'more');

    const { dest } = await writeProjection(src, dstDir);
    expect(await readProjection(dest)).toEqual(REAL_PROJECTION);
  });

  it('writes [] when the source is absent -- the ordinary D-13 state, no event enabled yet', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-survey-status-write-'));
    const dstDir = join(root, 'public');
    const { ids, dest } = await writeProjection(join(root, 'does-not-exist.json'), dstDir);
    expect(ids).toEqual([]);
    expect(await readProjection(dest)).toEqual([]);
  });
});
