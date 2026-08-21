/**
 * The one filter between `docs/` and the app's public bundle.
 *
 * `copy-handbook.mjs` used to copy every file under `docs/` that had a
 * recognised extension and sat outside a couple of skipped directories --
 * an extension filter and a directory skip-list standing in for an
 * allowlist, and never one. `docs/reference/operations.md` shipped into the
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
 *    the filter were removed, or replaced with a denylist of today's three
 *    known-bad paths (`operations.md`, `docs/assets/`, `docs/superpowers/`)
 *    -- a denylist passes every check in section 2 above and still fails
 *    this one, because the probe page sits outside all three.
 */
import { readFileSync, existsSync } from 'node:fs';
import { cp, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { CONTENT_REGISTRY, PUBLIC_ASSETS } from '../src/content/registry';
import {
  copyHandbook,
  parseContentFiles,
  parsePublicAssets,
  publishedPaths,
  walkAll,
} from '../scripts/handbook-registry.mjs';

const DOCS = resolve(__dirname, '../../docs');
const REGISTRY_SOURCE = readFileSync(resolve(__dirname, '../src/content/registry.ts'), 'utf-8');

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

describe('a real run against the real docs/ tree', () => {
  let dst: string;

  afterEach(async () => {
    if (dst) await rm(dst, { recursive: true, force: true });
  });

  it('publishes exactly the registry allowlist, swept from the destination rather than from the filter\'s own return value', async () => {
    dst = await mkdtemp(join(tmpdir(), 'convener-handbook-real-'));
    const { files } = await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });
    const onDisk = slash(await walkAll(dst));
    expect(onDisk).toEqual(slash(files));
    expect(onDisk).toEqual(publishedPaths(REGISTRY_SOURCE));
  });

  it('never publishes docs/reference/operations.md -- entry 2 of the deferred-work register', async () => {
    dst = await mkdtemp(join(tmpdir(), 'convener-handbook-real-'));
    await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });
    expect(slash(await walkAll(dst))).not.toContain('reference/operations.md');
  });

  it('never publishes anything under docs/superpowers/ -- the specs and plans this project never releases', async () => {
    dst = await mkdtemp(join(tmpdir(), 'convener-handbook-real-'));
    await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });
    expect(slash(await walkAll(dst)).some(p => p.startsWith('superpowers/'))).toBe(false);
  });

  it('publishes nothing under docs/assets/ beyond what PUBLIC_ASSETS names', async () => {
    dst = await mkdtemp(join(tmpdir(), 'convener-handbook-real-'));
    await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });
    const publishedAssets = slash(await walkAll(dst)).filter(p => p.startsWith('assets/'));
    expect(publishedAssets).toEqual([...PUBLIC_ASSETS].sort());
  });

  it('never republishes docs/assets/flyer-example.png -- fix round 1: a real, named speaker\'s photograph, withdrawn from PUBLIC_ASSETS, not a synthetic example', async () => {
    // Hard-coded, deliberately not derived from PUBLIC_ASSETS: the test
    // above would still agree with itself if this path were ever added
    // back there, which is exactly the silent-reinstatement this
    // assertion exists to catch instead.
    dst = await mkdtemp(join(tmpdir(), 'convener-handbook-real-'));
    await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });
    expect(slash(await walkAll(dst))).not.toContain('assets/flyer-example.png');
  });

  it('never publishes docs/index.md, docs/README.md or governance/register.md -- real, unregistered pages meant for a reader browsing the repository itself, not the app', async () => {
    // Distinct from the probes below: these three are not invented for
    // this test, they are real files under docs/ today. If any of them
    // were ever added to CONTENT_REGISTRY or PUBLIC_ASSETS this
    // assertion would need updating -- which is the point: it is pinned
    // to the registry's current, deliberate silence about them, not to
    // an assumption that they are harmless.
    dst = await mkdtemp(join(tmpdir(), 'convener-handbook-real-'));
    await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });
    const onDisk = slash(await walkAll(dst));
    expect(onDisk).not.toContain('index.md');
    expect(onDisk).not.toContain('README.md');
    expect(onDisk).not.toContain('governance/register.md');
  });
});

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
    const dir = await mkdtemp(join(tmpdir(), 'convener-handbook-docs-'));
    await cp(DOCS, dir, { recursive: true });
    return dir;
  }

  it('does not publish a brand-new page the registry has never heard of', async () => {
    sandbox = await sandboxDocs();
    await writeFile(
      resolve(sandbox, 'zzz-not-in-the-registry.md'),
      '# Not registered\n\nA page nobody has added to CONTENT_REGISTRY.\n',
    );
    dst = await mkdtemp(join(tmpdir(), 'convener-handbook-mut-'));

    const { files } = await copyHandbook({ docsDir: sandbox, registrySource: REGISTRY_SOURCE, dst });

    // The probe sits at the top level of docs/ -- not under
    // `reference/`, `assets/` or `superpowers/` -- exactly so that a
    // denylist of today's three known-bad paths would still let it
    // through. Only a real allowlist stops it.
    expect(files).not.toContain('zzz-not-in-the-registry.md');
    expect(existsSync(resolve(dst, 'zzz-not-in-the-registry.md'))).toBe(false);
  });

  it('does not publish a probe file added under docs/superpowers/', async () => {
    sandbox = await sandboxDocs();
    await writeFile(resolve(sandbox, 'superpowers', 'zzz-probe.md'), '# probe\n');
    dst = await mkdtemp(join(tmpdir(), 'convener-handbook-mut-'));

    const { files } = await copyHandbook({ docsDir: sandbox, registrySource: REGISTRY_SOURCE, dst });

    expect(files.some(f => f.startsWith('superpowers/'))).toBe(false);
    expect(existsSync(resolve(dst, 'superpowers', 'zzz-probe.md'))).toBe(false);
  });

  it('does not publish a probe file added under docs/assets/ that no registered page links to', async () => {
    sandbox = await sandboxDocs();
    await writeFile(resolve(sandbox, 'assets', 'zzz-probe.png'), Buffer.from([0]));
    dst = await mkdtemp(join(tmpdir(), 'convener-handbook-mut-'));

    const { files } = await copyHandbook({ docsDir: sandbox, registrySource: REGISTRY_SOURCE, dst });

    expect(files).not.toContain('assets/zzz-probe.png');
    expect(existsSync(resolve(dst, 'assets', 'zzz-probe.png'))).toBe(false);
  });
});
