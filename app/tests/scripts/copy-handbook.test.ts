/**
 * The one filter between `docs/` and the app's public bundle.
 *
 * `copy-handbook.mjs` used to copy every file under `docs/` that had a
 * recognised extension and sat outside a couple of skipped directories --
 * an extension filter and a directory skip-list standing in for an
 * allowlist, and never one. `docs/operating/operations.md` shipped into the
 * built app because of exactly that: a recognised extension (`.md`),
 * outside every skipped directory. `handbook-registry.mjs::publishedPaths`
 * replaces that with the allowlist that already existed for a different
 * purpose -- `CONTENT_REGISTRY`, the exact set of pages the app knows how
 * to render -- plus the small, explicit `PUBLIC_ASSETS` list for the
 * handful of files a registered page links to without ever being looked up
 * by content key.
 *
 * Three things are checked here, in order of how much each one proves:
 *
 * 1. The two regex-based extractors in `handbook-registry.mjs` agree with
 *    the real, TypeScript-parsed `CONTENT_REGISTRY` and `PUBLIC_ASSETS` --
 *    the safety net for the one place this filter reads `registry.ts` as
 *    text instead of importing it (the script that calls it runs under
 *    bare `node` in `prebuild`/`predev`, on a Node version this repository
 *    does not control; see that module's own comment).
 * 2. A real run of `copyHandbook`, against the real `docs/` tree, produces
 *    a destination containing exactly the registry's allowlist and nothing
 *    else -- swept from the destination outward, not asserted from the
 *    filter's own return value.
 * 3. The filter is doing the work, not the current, accidental shape of
 *    `docs/`: a page added to a *private copy* of `docs/` that the
 *    registry has never heard of is run through the real copy step and
 *    does not reach the destination. This is the test that would fail if
 *    the filter were removed, or replaced with a denylist of today's two
 *    known-bad paths (`operations.md`, `docs/handbook/assets/`) -- a
 *    denylist passes every check in section 2 above and still fails this
 *    one, because the probe page sits outside both.
 */
import { readFileSync, existsSync } from 'node:fs';
import { mkdir, cp, rm, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { scratch } from '../helpers/scratch';
import { afterEach, describe, expect, it } from 'vitest';
import { CONTENT_REGISTRY, PUBLIC_ASSETS } from '../../src/content/registry';
import {
  copyHandbook,
  parseContentFiles,
  parsePublicAssets,
  publishedPaths,
  walkAll,
} from '../../scripts/handbook-registry.mjs';

const DOCS = resolve(__dirname, '../../../docs');
/** This module's own scratch root -- see `helpers/scratch.ts`. */
const OWNER = 'copy-handbook';
const REGISTRY_SOURCE = readFileSync(resolve(__dirname, '../../src/content/registry.ts'), 'utf-8');

/** Windows path separators normalised, the same way every other sweep test
 *  in this suite does (see `visual-kit.test.tsx`). */
function slash(paths: string[]): string[] {
  return paths.map(p => p.split('\\').join('/')).sort();
}

describe('the two extractors that read registry.ts as text agree with the real module', () => {
  it('parseContentFiles finds exactly the file paths CONTENT_REGISTRY holds, deduplicated', () => {
    const expected = [...new Set(Object.values(CONTENT_REGISTRY).map(e => e.file))].sort();
    expect(parseContentFiles(REGISTRY_SOURCE)).toEqual(expected);
  });

  it('parsePublicAssets finds exactly PUBLIC_ASSETS', () => {
    expect(parsePublicAssets(REGISTRY_SOURCE)).toEqual([...PUBLIC_ASSETS].sort());
  });

  it('publishedPaths is the union of the two, with no duplicate', () => {
    const union = new Set([...parseContentFiles(REGISTRY_SOURCE), ...parsePublicAssets(REGISTRY_SOURCE)]);
    expect(publishedPaths(REGISTRY_SOURCE)).toEqual([...union].sort());
  });
});

describe('the extraction reads each export\'s own literal, not the whole file', () => {
  // A reviewer proved by execution that the first version of these two
  // functions ran `/\bfile:\s*'([^']+)'/g` over the *entire* source text:
  // an ordinary explanatory comment mentioning `file: 'operating/operations.md'`
  // anywhere in registry.ts -- inside the object literal, outside it,
  // anywhere -- would have been read back out as a path to publish. These
  // fixtures put that exact decoy in three places a real edit to
  // registry.ts might one day put it, and pin that none of them survive.

  it('ignores a decoy comment inside CONTENT_REGISTRY\'s own object literal', () => {
    const source = `
// file: 'operating/operations.md' -- decoy, before the block entirely
export const CONTENT_REGISTRY = {
  'a': {
    // file: 'operating/operations.md' -- decoy, inside one entry
    file: 'a.md',
    anchor: null,
  },
};
export const PUBLIC_ASSETS = [
  'handbook/assets/x.svg',
];
`;
    expect(parseContentFiles(source)).toEqual(['a.md']);
  });

  it('ignores a decoy comment inside PUBLIC_ASSETS\'s own array literal', () => {
    const source = `
export const CONTENT_REGISTRY = {
  'a': { file: 'a.md', anchor: null },
};
export const PUBLIC_ASSETS = [
  // 'operating/operations.md' -- decoy, inside the array
  'handbook/assets/x.svg',
];
`;
    expect(parsePublicAssets(source)).toEqual(['handbook/assets/x.svg']);
  });

  it('ignores a decoy string outside both blocks entirely', () => {
    const source = `
/* a block comment mentioning file: 'operating/operations.md', above everything */
export const CONTENT_REGISTRY = {
  'a': { file: 'a.md', anchor: null },
};
export const PUBLIC_ASSETS = [
  'handbook/assets/x.svg',
];
// a trailing comment mentioning file: 'operating/operations.md' and 'handbook/assets/y.png'
`;
    expect(parseContentFiles(source)).toEqual(['a.md']);
    expect(parsePublicAssets(source)).toEqual(['handbook/assets/x.svg']);
  });
});

/** How long a real run of `copyHandbook` is given, and why it is not the
 *  default five seconds.
 *
 *  This block copies the whole of `docs/` -- eighty files -- clearing the
 *  destination first, and does it under the coverage instrumentation the
 *  `test:cov` gate runs with. Measured, these tests take about half a
 *  second alone and have been seen past five with the whole suite running
 *  beside them.
 *
 *  Thirty seconds weakens no assertion below -- each one still compares
 *  exactly what it compared -- and it takes out of them the one thing that
 *  was never theirs to test: how busy the machine is. A check whose colour
 *  is the machine's is a check people learn to re-run, which is D-25's own
 *  failure in slow motion. Where the tree is written, and why that is not
 *  the machine's temp directory any more, is `tests/helpers/scratch.ts`. */
const REAL_TREE_TIMEOUT = 30_000;

describe('a real run against the real docs/ tree', () => {
  let dst: string;

  afterEach(async () => {
    if (dst) await rm(dst, { recursive: true, force: true });
  });

  it('publishes exactly the registry allowlist, swept from the destination rather than from the filter\'s own return value', async () => {
    dst = await scratch(OWNER, 'real');
    const { files } = await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });
    const onDisk = slash(await walkAll(dst));
    // Named, because this block was seen to fail intermittently under the
    // full suite and a bare list comparison says which paths differ but
    // never where they were read from. It is what made the cause legible
    // once it was reproduced: thirteen of eighty files, in a directory
    // something else on the machine had emptied (`helpers/scratch.ts`).
    expect(onDisk, `copied from ${DOCS} into ${dst}`).toEqual(slash(files));
    expect(onDisk, `copied into ${dst}`).toEqual(publishedPaths(REGISTRY_SOURCE));
  });

  it('never publishes docs/operating/operations.md -- it names every secret this project uses', async () => {
    dst = await scratch(OWNER, 'real');
    await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });
    expect(slash(await walkAll(dst))).not.toContain('operating/operations.md');
  });

  it('publishes nothing under docs/handbook/assets/ beyond what PUBLIC_ASSETS names', async () => {
    dst = await scratch(OWNER, 'real');
    await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });
    const publishedAssets = slash(await walkAll(dst)).filter(p => p.startsWith('handbook/assets/'));
    expect(publishedAssets).toEqual([...PUBLIC_ASSETS].sort());
  });

  it('never republishes docs/assets/flyer-example.png -- a real, named speaker\'s photograph, withdrawn from PUBLIC_ASSETS, not a synthetic example', async () => {
    // Hard-coded, deliberately not derived from PUBLIC_ASSETS: the test
    // above would still agree with itself if this path were ever added
    // back there, which is exactly the silent-reinstatement this
    // assertion exists to catch instead.
    dst = await scratch(OWNER, 'real');
    await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });
    expect(slash(await walkAll(dst))).not.toContain('handbook/assets/flyer-example.png');
  });

  it('never publishes docs/handbook/index.md -- a real, unregistered page meant for a reader browsing the repository itself, not the app', async () => {
    // Distinct from the probes below: this one is not invented for this
    // test, it is a real file under docs/ today. If it were ever
    // added to CONTENT_REGISTRY or PUBLIC_ASSETS this assertion would
    // need updating -- which is the point: it is pinned to the
    // registry's current, deliberate silence about it, not to an
    // assumption that it is harmless. (`handbook/governance/register.md` was
    // another such page until it was registered -- see
    // `registry.ts`'s own comment on that entry, and
    // `app/tests/content/registered-links.test.ts`.)
    dst = await scratch(OWNER, 'real');
    await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });
    const onDisk = slash(await walkAll(dst));
    expect(onDisk).not.toContain('handbook/index.md');
  });
}, REAL_TREE_TIMEOUT);

describe('the filter is doing the work, not the current shape of docs/', () => {
  let sandbox: string;
  let dst: string;

  afterEach(async () => {
    if (sandbox) await rm(sandbox, { recursive: true, force: true });
    if (dst) await rm(dst, { recursive: true, force: true });
  });

  /** A private copy of docs/, so the probe files below never touch the
   *  real tree this repository tracks -- writing into the real `docs/`,
   *  even briefly, is exactly the kind of stray file `git status` in this
   *  project's Drive-hosted working copy is known to misreport. */
  async function sandboxDocs(): Promise<string> {
    const dir = await scratch(OWNER, 'docs');
    await cp(DOCS, dir, { recursive: true });
    return dir;
  }

  it('does not publish a brand-new page the registry has never heard of', async () => {
    sandbox = await sandboxDocs();
    await writeFile(
      resolve(sandbox, 'zzz-not-in-the-registry.md'),
      '# Not registered\n\nA page nobody has added to CONTENT_REGISTRY.\n',
    );
    dst = await scratch(OWNER, 'mut');

    const { files } = await copyHandbook({ docsDir: sandbox, registrySource: REGISTRY_SOURCE, dst });

    // The probe sits at the top level of docs/ -- not under
    // `operating/` and not under `handbook/assets/` -- exactly so that a
    // denylist of today's two known-bad paths would still let it
    // through. Only a real allowlist stops it.
    expect(files).not.toContain('zzz-not-in-the-registry.md');
    expect(existsSync(resolve(dst, 'zzz-not-in-the-registry.md'))).toBe(false);
  });

  it('does not publish a probe file added in a directory of its own that no registered page names', async () => {
    sandbox = await sandboxDocs();
    // The directory is created here rather than found: the claim is about
    // the allowlist, not about which directories happen to exist under
    // `docs/` on the day. A whole directory rather than the file above,
    // because a walk meets the two differently -- one it may descend
    // into, the other it may only copy.
    await mkdir(resolve(sandbox, 'zzz-unregistered-tree'), { recursive: true });
    await writeFile(resolve(sandbox, 'zzz-unregistered-tree', 'zzz-probe.md'), '# probe\n');
    dst = await scratch(OWNER, 'mut');

    const { files } = await copyHandbook({ docsDir: sandbox, registrySource: REGISTRY_SOURCE, dst });

    expect(files.some(f => f.startsWith('zzz-unregistered-tree/'))).toBe(false);
    expect(existsSync(resolve(dst, 'zzz-unregistered-tree', 'zzz-probe.md'))).toBe(false);
  });

  it('does not publish a probe file added under docs/handbook/assets/ that no registered page links to', async () => {
    sandbox = await sandboxDocs();
    await writeFile(resolve(sandbox, 'handbook', 'assets', 'zzz-probe.png'), Buffer.from([0]));
    dst = await scratch(OWNER, 'mut');

    const { files } = await copyHandbook({ docsDir: sandbox, registrySource: REGISTRY_SOURCE, dst });

    expect(files).not.toContain('handbook/assets/zzz-probe.png');
    expect(existsSync(resolve(dst, 'handbook', 'assets', 'zzz-probe.png'))).toBe(false);
  });
});
