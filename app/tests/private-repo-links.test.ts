/**
 * No page this application publishes may link into `example-cockpit`'s own
 * repository -- that repository is private, so the link is a 404 for every
 * reader who is not a collaborator on it.
 *
 * `registered-links.test.ts` already forbids a registered page from linking
 * to an *unregistered* one, but only for local, relative, `.md`-suffixed
 * links resolved through `CONTENT_REGISTRY` -- its own extractor explicitly
 * excludes anything with a URL scheme. The twelve links this test exists to
 * catch are absolute `https://github.com/...` addresses, so that guard never
 * saw them: a guard whose stated scope did not match the real shape of the
 * defect, the same failure this project's iCalendar leak guard had while
 * blind to line folding.
 *
 * The forbidden prefix is derived from `repoUrl()` -- the one reader every
 * *legitimate* link to this repository already goes through
 * (`content/fetch.ts`'s edit link, `content/transclude.ts`'s attribution
 * line) -- rather than a second, hand-typed copy of the same private
 * address living in this test. That is the exact shape
 * `site/src/_includes/layout.njk` was fixed to stop doing (see
 * `tools/tests/test_site.py::test_the_organiser_link_points_at_the_apps_real_published_base`):
 * a hand-typed address naming a repository the public reader can never
 * reach became one derived from something that actually resolves.
 *
 * Checked on both sides, because either alone leaves half the door open:
 * the **source** text of every page `CONTENT_REGISTRY` names (a link could
 * be added and never reach the build in some other, unrelated way), and the
 * **built** output `copy-handbook.mjs` actually publishes (the source sweep
 * alone would miss a defect in the copy step itself -- see
 * `copy-handbook.test.ts`'s own reasoning for why a real run is checked
 * separately from the registry's intent).
 */
import { readFileSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { CONTENT_REGISTRY, repoUrl } from '../src/content/registry';
import { copyHandbook } from '../scripts/handbook-registry.mjs';

const DOCS = resolve(__dirname, '../../docs');
const REGISTRY_SOURCE = readFileSync(resolve(__dirname, '../src/content/registry.ts'), 'utf-8');

/** The private repository's own blob-link prefix -- the shape every one of
 *  the twelve dead links took (`${repoUrl()}/blob/main/docs/...`). */
const PRIVATE_BLOB_PREFIX = `${repoUrl()}/blob/`;

function page(file: string): string {
  return readFileSync(resolve(DOCS, file), 'utf-8');
}

describe('no published page links into the private repository (source)', () => {
  const registryFiles = [...new Set(Object.values(CONTENT_REGISTRY).map(e => e.file))].sort();

  it('is a real sweep: at least one registered page exists to check', () => {
    // An empty sweep would pass every case below vacuously -- the same
    // guard `registered-links.test.ts` and `message-templates.test.ts` put
    // on their own walk of the registry / docs/.
    expect(registryFiles.length).toBeGreaterThan(0);
  });

  for (const file of registryFiles) {
    it(`${file} does not link into the private repository`, () => {
      expect(page(file)).not.toContain(PRIVATE_BLOB_PREFIX);
    });
  }
});

describe('no published page links into the private repository (built output)', () => {
  let dst: string;

  afterEach(async () => {
    if (dst) await rm(dst, { recursive: true, force: true });
  });

  it('a real run of copyHandbook publishes no such link either', async () => {
    dst = await mkdtemp(join(tmpdir(), 'convener-handbook-private-link-'));
    const { files } = await copyHandbook({ docsDir: DOCS, registrySource: REGISTRY_SOURCE, dst });

    const mdFiles = files.filter(f => f.endsWith('.md'));
    expect(mdFiles.length).toBeGreaterThan(0);

    const carrying = mdFiles.filter(f =>
      readFileSync(resolve(dst, f), 'utf-8').includes(PRIVATE_BLOB_PREFIX),
    );
    expect(carrying, `built page(s) link into the private repository: ${JSON.stringify(carrying)}`).toEqual([]);
  });
});
